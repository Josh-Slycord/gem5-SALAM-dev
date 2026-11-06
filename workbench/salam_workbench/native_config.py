# SPDX-License-Identifier: BSD-3-Clause
"""Strict, side-effect-free configuration model for the first native GEMM path.

The current typed SimObject ABI remains authoritative. Reading its Python
declarations uses AST only: no m5 imports, generators, writes or simulations.
This intentionally supports NonCoherent DMA and SPM, not every historical
SALAM dialect. Accepted metadata is labeled separately from active consumers.
"""

import ast
import copy
import hashlib
import json
import keyword
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from yaml.events import AliasEvent

SCHEMA_VERSION = 1
DEFAULT_BASE_ADDRESS = 0x10020000
ADDRESS_CEILING = 0x13FFFFFF
UINT32_MAX = 0xFFFFFFFF
_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_RESERVED = {
    "local_bus",
    "coherency_bus",
    "clk_domain",
    "voltage_domain",
    "system",
    "type",
    "pio",
    "dma",
    "cache",
    "cluster_cache",
    "localbus",
    "path",
    "descendants",
    "children",
    "name",
    "getccobject",
    "getport",
    "set_parent",
    "add_child",
}
# "dma" is the qualified device name, so permit it as a component name.
_RESERVED.remove("dma")
_SOURCES = (
    "configs/SALAM/HWAccConfig.py",
    "src/hwacc/FunctionalUnits.py",
    "src/hwacc/InstConfig.py",
    "src/hwacc/CycleCounts.py",
    "src/hwacc/CommInterface.py",
    "src/hwacc/NoncoherentDma.py",
)
_SPECIAL_CYCLES = {"load", "store", "ret", "br", "switch_inst", "call"}
_DISPATCHED_CYCLES = {
    "add",
    "fadd",
    "sub",
    "fsub",
    "mul",
    "fmul",
    "udiv",
    "sdiv",
    "fdiv",
    "urem",
    "srem",
    "frem",
    "shl",
    "lshr",
    "ashr",
    "and_inst",
    "or_inst",
    "xor_inst",
    "gep",
    "trunc",
    "zext",
    "sext",
    "fptoui",
    "fptosi",
    "uitofp",
    "sitofp",
    "fptrunc",
    "fpext",
    "ptrtoint",
    "inttoptr",
    "icmp",
    "fcmp",
    "phi",
    "select",
}


class ConfigurationError(ValueError):
    """A pre-instantiation failure with the authored source location."""

    def __init__(self, code, message, source, line=1, key_path=""):
        self.code = code
        self.source = str(source)
        self.line = line
        self.key_path = key_path
        self.message = message
        super().__init__(
            "{}:{}: {} [{}] {}".format(self.source, self.line, key_path, code, message)
        )

    def to_dict(self):
        return {
            "code": self.code,
            "message": self.message,
            "source": self.source,
            "line": self.line,
            "key_path": self.key_path,
        }


class _Map(dict):
    def __init__(self, source, line):
        super().__init__()
        self.source = source
        self.line = line
        self.marks = {}


class _Loader(yaml.SafeLoader):
    def __init__(self, stream, source):
        self.source_path = str(source)
        super().__init__(stream)


def _mapping(loader, node):
    result = _Map(loader.source_path, node.start_mark.line + 1)
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str):
            raise ConfigurationError(
                "invalid_key",
                "YAML mapping keys must be strings",
                loader.source_path,
                key_node.start_mark.line + 1,
            )
        if key in result:
            raise ConfigurationError(
                "duplicate_key",
                "Repeated key {!r}; first occurrence is line {}".format(
                    key, result.marks[key]
                ),
                loader.source_path,
                key_node.start_mark.line + 1,
                key,
            )
        result.marks[key] = key_node.start_mark.line + 1
        result[key] = loader.construct_object(value_node, deep=True)
    return result


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


@dataclass(frozen=True)
class NormalizedConfiguration:
    """Immutable canonical payload; accessors return detached copies."""

    _canonical_json: str

    def to_dict(self):
        return json.loads(self._canonical_json)

    def to_json(self, *, indent=2):
        if indent is None:
            return self._canonical_json
        return json.dumps(self.to_dict(), sort_keys=True, indent=indent) + "\n"

    @property
    def sha256(self):
        return hashlib.sha256(self._canonical_json.encode()).hexdigest()

    @property
    def model_sha256(self):
        return self.sha256

    @property
    def clusters(self):
        return tuple(self.to_dict()["clusters"])


def _registry(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            if isinstance(node.value, ast.Dict):
                return {
                    key.value: value.id
                    for key, value in zip(node.value.keys, node.value.values)
                    if isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and isinstance(value, ast.Name)
                }
    raise ValueError("Missing typed registry " + name)


def _class_params(tree, name):
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != name:
            continue
        result = {}
        for item in node.body:
            if (
                isinstance(item, ast.Assign)
                and len(item.targets) == 1
                and isinstance(item.targets[0], ast.Name)
                and isinstance(item.value, ast.Call)
                and item.value.args
            ):
                try:
                    value = ast.literal_eval(item.value.args[0])
                except (ValueError, TypeError, SyntaxError):
                    continue
                if isinstance(value, (str, int, float, bool, list)):
                    result[item.targets[0].id] = {
                        "value": value,
                        "line": item.lineno,
                    }
        return result
    raise ValueError("Missing typed class " + name)


class _Normalizer:
    def __init__(self, config_path, engine_root, base_address):
        self.root = Path(engine_root).resolve()
        self.config = Path(config_path).resolve()
        self.provenance = []
        self.dependencies = {}
        self.memory_sources = {}
        if not self.root.is_dir():
            self.fail("missing_engine", "Engine root is not a directory", self.config)
        self.contained(self.config, self.config)
        self.base = DEFAULT_BASE_ADDRESS if base_address is None else base_address
        if (
            type(self.base) is not int
            or not 0x10000000 <= self.base <= ADDRESS_CEILING
            or self.base % 64
        ):
            self.fail(
                "invalid_base_address",
                "Base address must be aligned to 64 bytes in " "0x10000000..0x13ffffff",
                self.config,
            )
        self.provenance.append(
            {
                "field": "base_address",
                "value": self.base,
                "origin": "default" if base_address is None else "argument",
                "source": "normalize_configuration:base_address",
                "line": None,
                "consumer": "address_allocation",
                "units": "bytes",
            }
        )
        self.catalog = self.load_catalog()

    def relative(self, path):
        return Path(path).relative_to(self.root).as_posix()

    def fail(self, code, message, source, key=None, key_path=""):
        if isinstance(source, _Map):
            line = source.marks.get(key, source.line)
            filename = source.source
        else:
            filename = str(source)
            line = 1
        raise ConfigurationError(code, message, filename, line, key_path)

    def contained(self, target, source, key=None, key_path=""):
        try:
            Path(target).relative_to(self.root)
        except ValueError:
            self.fail(
                "unsafe_path",
                "Resolved path leaves the engine root",
                source,
                key,
                key_path,
            )

    def dependency(self, path, kind):
        path = Path(path)
        try:
            data = path.read_bytes()
        except OSError as error:
            self.fail("missing_dependency", str(error), path)
        relative = self.relative(path)
        self.dependencies[relative] = {
            "path": relative,
            "kind": kind,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
        return data

    def load_catalog(self):
        trees = {}
        for relative in _SOURCES:
            path = (self.root / relative).resolve()
            self.contained(path, self.config)
            data = self.dependency(path, "typed_abi_source")
            try:
                trees[relative] = ast.parse(data, filename=str(path))
            except SyntaxError as error:
                self.fail("invalid_abi_source", str(error), path)
        try:
            registry_tree = trees[_SOURCES[0]]
            fus = _registry(registry_tree, "_FU_REGISTRY")
            instructions = _registry(registry_tree, "_INST_REGISTRY")
            result = {
                "functional_units": {
                    key: {
                        "class": name,
                        "parameters": _class_params(trees[_SOURCES[1]], name),
                    }
                    for key, name in sorted(fus.items())
                },
                "instructions": {
                    key: {
                        "class": name,
                        "parameters": _class_params(trees[_SOURCES[2]], name),
                    }
                    for key, name in sorted(instructions.items())
                },
                "cycle_counts": _class_params(trees[_SOURCES[3]], "CycleCounts"),
                "comm_defaults": _class_params(trees[_SOURCES[4]], "CommInterface"),
                "dma_defaults": _class_params(trees[_SOURCES[5]], "NoncoherentDma"),
            }
            ids = [
                unit["parameters"]["enum_value"]["value"]
                for unit in result["functional_units"].values()
            ]
            if len(set(ids)) != len(ids) or any(
                type(value) is not int or value <= 0 for value in ids
            ):
                raise ValueError("FU IDs must be positive and unique")
            if (
                result["comm_defaults"]["int_num"]["value"] != -1
                or result["dma_defaults"]["int_num"]["value"] != 200
            ):
                raise ValueError("Audited native IRQ defaults changed")
            for family, source in (
                ("functional_units", _SOURCES[1]),
                ("instructions", _SOURCES[2]),
            ):
                for declaration in result[family].values():
                    declaration["source"] = source
                    for parameter in declaration["parameters"].values():
                        parameter["source"] = source
                        parameter["origin"] = "typed_default"
            for family, source in (
                ("cycle_counts", _SOURCES[3]),
                ("comm_defaults", _SOURCES[4]),
                ("dma_defaults", _SOURCES[5]),
            ):
                for parameter in result[family].values():
                    parameter["source"] = source
                    parameter["origin"] = "typed_default"
            return result
        except (KeyError, ValueError) as error:
            self.fail(
                "unsupported_typed_abi",
                str(error),
                self.root / _SOURCES[0],
            )

    def load_yaml(self, path):
        data = self.dependency(path, "configuration")
        try:
            for event in yaml.parse(data, Loader=yaml.SafeLoader):
                if isinstance(event, AliasEvent):
                    raise ConfigurationError(
                        "yaml_alias",
                        "Aliases/merges are not supported by this "
                        "source-located schema",
                        path,
                        event.start_mark.line + 1,
                    )
            loader = _Loader(data, path)
            try:
                documents = []
                while loader.check_data():
                    documents.append(loader.get_data())
            finally:
                loader.dispose()
        except ConfigurationError:
            raise
        except yaml.YAMLError as error:
            mark = getattr(error, "problem_mark", None)
            raise ConfigurationError(
                "invalid_yaml",
                str(error),
                path,
                mark.line + 1 if mark else 1,
            ) from error
        if len(documents) != 1:
            self.fail(
                "unsupported_documents",
                "The first native GEMM path requires one YAML document",
                path,
            )
        return documents[0]

    def mapping(self, value, source, key, key_path):
        if not isinstance(value, dict):
            self.fail("wrong_type", "Expected a mapping", source, key, key_path)
        return value

    def keys(self, value, accepted, key_path):
        for key in value:
            if key not in accepted:
                self.fail(
                    "unknown_field",
                    "No native GEMM consumer for {!r}".format(key),
                    value,
                    key,
                    key_path + "." + key,
                )

    def integer(self, value, source, key, key_path, *, positive=False):
        if (
            type(value) is not int
            or value < (1 if positive else 0)
            or value > UINT32_MAX
        ):
            self.fail(
                "invalid_uint32",
                "Expected {}UInt32".format("positive " if positive else ""),
                source,
                key,
                key_path,
            )
        return value

    def name(self, value, source, key, key_path):
        if (
            not isinstance(value, str)
            or not _IDENT.fullmatch(value)
            or keyword.iskeyword(value)
            or value.lower() in _RESERVED
        ):
            self.fail(
                "invalid_name",
                "Expected an unreserved identifier",
                source,
                key,
                key_path,
            )
        return value

    def record(
        self,
        source,
        key,
        destination,
        value,
        *,
        default=False,
        derived=False,
        consumer="effective",
        units=None,
    ):
        self.provenance.append(
            {
                "field": destination,
                "value": copy.deepcopy(value),
                "origin": (
                    "derived" if derived else "default" if default else "explicit"
                ),
                "source": self.relative(Path(source.source)),
                "line": source.marks.get(key, source.line),
                "input_key": key,
                "consumer": consumer,
                "units": units,
            }
        )

    def resolved(self, destination, value, transform):
        for record in reversed(self.provenance):
            if record["field"] == destination:
                record["authored_value"] = record["value"]
                record["value"] = copy.deepcopy(value)
                record["transform"] = transform
                return
        raise AssertionError("Missing provenance field " + destination)

    def field(
        self,
        source,
        key,
        destination,
        default=None,
        *,
        required=False,
        consumer="effective",
        units=None,
    ):
        if required and key not in source:
            self.fail(
                "missing_field",
                "Required field is missing",
                source,
                key,
                destination,
            )
        value = source.get(key, default)
        self.record(
            source,
            key,
            destination,
            value,
            default=key not in source,
            consumer=consumer,
            units=units,
        )
        return value

    def path(self, value, source, key, destination, suffix):
        if (
            not isinstance(value, str)
            or not value
            or "\\" in value
            or ":" in value
            or Path(value).is_absolute()
            or any(part in ("", ".", "..") for part in value.split("/"))
            or Path(value).suffix not in suffix
        ):
            self.fail(
                "unsafe_path",
                "Expected a contained engine-relative {} path".format("/".join(suffix)),
                source,
                key,
                destination,
            )
        resolved = (self.root / value).resolve()
        self.contained(resolved, source, key, destination)
        if not resolved.is_file():
            self.fail(
                "missing_dependency",
                "Requested file does not exist",
                source,
                key,
                destination,
            )
        self.dependency(resolved, "llvm_ir")
        return str(resolved)

    def names(self, value, source, key, destination, *, required=False):
        if value is None and not required:
            return []
        if not isinstance(value, str) or not value:
            self.fail(
                "invalid_connection",
                "Expected comma-separated connection names",
                source,
                key,
                destination,
            )
        result = []
        for item in value.split(","):
            if item != item.strip() or not item:
                self.fail(
                    "invalid_connection",
                    "Connection names cannot be empty or padded with spaces",
                    source,
                    key,
                    destination,
                )
            normalized = (
                "LocalBus"
                if item == "LocalBus"
                else self.name(item, source, key, destination).lower()
            )
            if normalized in result:
                self.fail(
                    "duplicate_connection",
                    "Repeated connection",
                    source,
                    key,
                    destination,
                )
            result.append(normalized)
        return result

    @staticmethod
    def stride(size):
        # Exact retained allocator: aligned sizes intentionally get extra 64.
        return size + (64 - size % 64)

    def hardware(self, settings, destination, *, source=None, key=None):
        if settings is None:
            return {"instructions": {}, "functional_units": {}}
        self.mapping(
            settings,
            source if source is not None else self.config,
            key,
            destination,
        )
        self.keys(settings, {"instructions", "functional_units"}, destination)
        result = {"instructions": {}, "functional_units": {}}
        valid_ids = {
            unit["parameters"]["enum_value"]["value"]
            for unit in self.catalog["functional_units"].values()
        }
        for family in result:
            entries = settings.get(family, {})
            self.mapping(entries, settings, family, destination + "." + family)
            registry = self.catalog[family]
            for name, fields in entries.items():
                entry_path = destination + "." + family + "." + name
                if name not in registry:
                    self.fail(
                        "unknown_" + family,
                        "Absent from the current typed runtime registry",
                        entries,
                        name,
                        entry_path,
                    )
                self.mapping(fields, entries, name, entry_path)
                accepted = (
                    {"cycles", "limit"}
                    if family == "functional_units"
                    else {
                        "functional_unit",
                        "functional_unit_limit",
                        "opcode_num",
                        "runtime_cycles",
                    }
                )
                self.keys(fields, accepted, entry_path)
                normalized = {}
                for field, value in fields.items():
                    path = entry_path + "." + field
                    self.integer(value, fields, field, path)
                    consumer = "effective"
                    if field == "functional_unit":
                        consumer = "active_fu_mapping" if value else "zero_fu_id_bypass"
                    if field == "functional_unit_limit":
                        consumer = "neutral_instruction_cap"
                    if family == "functional_units" and field == "limit":
                        consumer = (
                            "finite_fu_capacity" if value else "unlimited_fu_capacity"
                        )
                    if field == "functional_unit" and value not in (valid_ids | {0}):
                        self.fail(
                            "unknown_fu_id",
                            "No typed FU has this identifier",
                            fields,
                            field,
                            path,
                        )
                    if field == "functional_unit_limit" and value:
                        self.fail(
                            "unsupported_instruction_cap",
                            "Nonzero per-instruction caps are rejected by "
                            "the current scheduler; zero is neutral",
                            fields,
                            field,
                            path,
                        )
                    if field == "opcode_num":
                        expected = registry[name]["parameters"]["opcode_num"]["value"]
                        if value != expected:
                            self.fail(
                                "unsupported_opcode_remap",
                                "opcode_num is part of the current typed "
                                "LLVM ABI (expected {})".format(expected),
                                fields,
                                field,
                                path,
                            )
                        consumer = "active_mapping_identity"
                    if field == "runtime_cycles":
                        if name not in self.catalog["cycle_counts"]:
                            self.fail(
                                "missing_cycle_consumer",
                                "No CycleCounts parameter receives this value",
                                fields,
                                field,
                                path,
                            )
                        consumer = (
                            "active_scalar_latency"
                            if name in _DISPATCHED_CYCLES
                            else "forwarded_special_path"
                            if name in _SPECIAL_CYCLES
                            else "stored_without_current_dispatch"
                        )
                        if name in {"load", "store"} and value != 0:
                            self.fail(
                                "unsupported_memory_latency",
                                "Load/store latency is controlled by memory; "
                                "CycleCounts must remain zero",
                                fields,
                                field,
                                path,
                            )
                    if family == "functional_units" and field == "cycles":
                        consumer = "stored_metadata"
                    normalized[field] = value
                    self.record(
                        fields,
                        field,
                        path,
                        value,
                        consumer=consumer,
                        units="cycles"
                        if field in ("cycles", "runtime_cycles")
                        else None,
                    )
                result[family][name] = normalized
        effective_limits = {
            unit["parameters"]["enum_value"]["value"]: result["functional_units"]
            .get(name, {})
            .get("limit", unit["parameters"]["limit"]["value"])
            for name, unit in self.catalog["functional_units"].items()
        }
        special = _SPECIAL_CYCLES | {
            "phi",
            "indirectbr",
            "invoke",
            "resume",
            "unreachable",
        }
        for name, declaration in self.catalog["instructions"].items():
            fields = result["instructions"].get(name, {})
            fu_id = fields.get(
                "functional_unit",
                declaration["parameters"]["functional_unit"]["value"],
            )
            if fu_id not in valid_ids | {0}:
                self.fail(
                    "unknown_fu_id",
                    "Effective instruction FU is undefined",
                    entries,
                    None,
                    destination + ".instructions." + name,
                )
            if (
                fu_id
                and effective_limits[fu_id]
                and (name in special or name not in _DISPATCHED_CYCLES)
            ):
                authored = settings.get("instructions", {}).get(name)
                source = authored if authored is not None else settings
                self.fail(
                    "unsupported_special_fu",
                    "Finite FU capacity cannot map special/undispatched "
                    "instruction " + name,
                    source,
                    "functional_unit",
                    destination + ".instructions." + name,
                )
        return result

    def memory(self, node, owner, destination, address, component_names):
        self.mapping(node, node, None, destination)
        self.keys(
            node,
            {
                "Name",
                "Type",
                "Size",
                "Ports",
                "Connections",
                "ReadyMode",
                "ResetOnRead",
                "ReadOnInvalid",
                "WriteOnValid",
            },
            destination,
        )
        kind = self.field(node, "Type", destination + ".type", required=True)
        if kind != "SPM":
            self.fail(
                "unsupported_memory_type",
                "First native GEMM route supports SPM only",
                node,
                "Type",
                destination + ".type",
            )
        authored_name = self.field(node, "Name", destination + ".name", required=True)
        name = self.name(authored_name, node, "Name", destination + ".name").lower()
        if name in component_names:
            self.fail(
                "duplicate_name",
                "Case-insensitive component name collision",
                node,
                "Name",
                destination + ".name",
            )
        self.resolved(destination + ".name", name, "lowercase identifier")
        component_names.add(name)
        self.memory_sources[name] = node
        size = self.field(
            node, "Size", destination + ".size", required=True, units="bytes"
        )
        self.integer(size, node, "Size", destination + ".size", positive=True)
        ports = self.field(node, "Ports", destination + ".ports", 1)
        self.integer(ports, node, "Ports", destination + ".ports", positive=True)
        result = {
            "name": name,
            "authored_name": authored_name,
            "type": "SPM",
            "address": address,
            "size": size,
            "range_end": address + size,
            "ports": ports,
            "connections": [{"accelerator": owner, "ports": ports}],
        }
        self.record(
            node,
            "Size",
            destination + ".address",
            address,
            derived=True,
            consumer="legacy_address_allocation",
            units="bytes",
        )
        self.record(
            node,
            "Size",
            destination + ".range_end",
            address + size,
            derived=True,
            consumer="retained_addr_range_endpoint",
            units="bytes",
        )
        for key, output, default in (
            ("ReadyMode", "ready_mode", False),
            ("ResetOnRead", "reset_on_read", True),
            ("ReadOnInvalid", "read_on_invalid", False),
            ("WriteOnValid", "write_on_valid", True),
        ):
            value = self.field(node, key, destination + "." + output, default)
            if type(value) is not bool:
                self.fail(
                    "wrong_type",
                    "Expected a YAML boolean",
                    node,
                    key,
                    destination + "." + output,
                )
            result[output] = value
        if "Connections" in node:
            value = self.field(node, "Connections", destination + ".connections")
            if not isinstance(value, str) or not value:
                self.fail(
                    "invalid_connection",
                    "Expected accelerator:ports pairs",
                    node,
                    "Connections",
                    destination + ".connections",
                )
            seen = {owner}
            for pair in value.split(","):
                try:
                    peer, count = pair.split(":")
                    if not count.isdecimal():
                        raise ValueError("port count")
                    count = int(count)
                    self.integer(
                        count,
                        node,
                        "Connections",
                        destination + ".connections",
                        positive=True,
                    )
                    peer = self.name(
                        peer,
                        node,
                        "Connections",
                        destination + ".connections",
                    ).lower()
                except ValueError:
                    self.fail(
                        "invalid_connection",
                        "Expected accelerator:positive_ports pairs",
                        node,
                        "Connections",
                        destination + ".connections",
                    )
                if peer in seen:
                    self.fail(
                        "duplicate_connection",
                        "Repeated SPM accelerator connection",
                        node,
                        "Connections",
                        destination + ".connections",
                    )
                seen.add(peer)
                result["connections"].append(
                    {
                        "accelerator": peer,
                        "ports": count,
                    }
                )
        if "Connections" in node:
            self.resolved(
                destination + ".connections",
                result["connections"],
                "Owner connection followed by parsed accelerator:ports pairs",
            )
        else:
            self.record(
                node,
                "Ports",
                destination + ".connections",
                result["connections"],
                derived=True,
                consumer="effective_spm_wiring",
            )
        return result

    def normalize(self):
        document = self.load_yaml(self.config)
        self.mapping(document, self.config, None, "documents[0]")
        self.keys(document, {"acc_cluster", "hw_config"}, "documents[0]")
        entries = document.get("acc_cluster")
        if not isinstance(entries, list) or not entries:
            self.fail(
                "missing_cluster",
                "Expected nonempty acc_cluster list",
                document,
                "acc_cluster",
                "acc_cluster",
            )
        cluster_names = []
        raw_dmas, raw_accs = [], []
        for index, entry in enumerate(entries):
            position = "acc_cluster[{}]".format(index)
            self.mapping(entry, document, "acc_cluster", position)
            self.keys(entry, {"Name", "DMA", "Accelerator"}, position)
            if len(entry) != 1:
                self.fail(
                    "ambiguous_cluster_entry",
                    "Each cluster list entry must contain one field",
                    entry,
                    None,
                    position,
                )
            if "Name" in entry:
                cluster_names.append((entry, position))
            elif "DMA" in entry:
                if not isinstance(entry["DMA"], list) or not entry["DMA"]:
                    self.fail(
                        "wrong_type",
                        "Expected nonempty DMA list",
                        entry,
                        "DMA",
                        position + ".DMA",
                    )
                for di, dma in enumerate(entry["DMA"]):
                    raw_dmas.append((dma, position + ".DMA[{}]".format(di)))
            elif "Accelerator" in entry:
                if (
                    not isinstance(entry["Accelerator"], list)
                    or not entry["Accelerator"]
                ):
                    self.fail(
                        "wrong_type",
                        "Expected nonempty Accelerator list",
                        entry,
                        "Accelerator",
                        position + ".Accelerator",
                    )
                raw_accs.append((entry["Accelerator"], position + ".Accelerator"))
        if len(cluster_names) != 1:
            self.fail(
                "ambiguous_cluster_name",
                "Exactly one cluster Name is required",
                document,
                "acc_cluster",
                "acc_cluster.Name",
            )
        name_node, name_path = cluster_names[0]
        authored_cluster_name = self.field(
            name_node, "Name", "clusters[0].name", required=True
        )
        name = self.name(
            authored_cluster_name, name_node, "Name", name_path + ".Name"
        ).lower()
        self.resolved("clusters[0].name", name, "lowercase identifier")
        if not raw_accs:
            self.fail(
                "missing_accelerator",
                "At least one accelerator is required",
                document,
                "acc_cluster",
                "acc_cluster",
            )
        cluster = {
            "name": name,
            "authored_name": authored_cluster_name,
            "base_address": self.base,
            "dmas": [],
            "accelerators": [],
        }
        address = self.base
        component_names = set()
        for dma_index, (node, input_path) in enumerate(raw_dmas):
            self.mapping(node, document, "acc_cluster", input_path)
            self.keys(
                node,
                {
                    "Name",
                    "Type",
                    "BufferSize",
                    "MaxReqSize",
                    "PIOMaster",
                    "InterruptNum",
                },
                input_path,
            )
            destination = "clusters[0].dmas[{}]".format(dma_index)
            kind = self.field(node, "Type", destination + ".type", required=True)
            if kind != "NonCoherent":
                self.fail(
                    "unsupported_dma_type",
                    "First native GEMM route supports NonCoherent DMA only",
                    node,
                    "Type",
                    input_path + ".Type",
                )
            authored = self.field(node, "Name", destination + ".name", required=True)
            normalized_name = self.name(
                authored, node, "Name", input_path + ".Name"
            ).lower()
            self.resolved(
                destination + ".name",
                normalized_name,
                "lowercase identifier",
            )
            if normalized_name in component_names:
                self.fail(
                    "duplicate_name",
                    "Case-insensitive component collision",
                    node,
                    "Name",
                    input_path + ".Name",
                )
            component_names.add(normalized_name)
            result = {
                "name": normalized_name,
                "authored_name": authored,
                "type": kind,
                "pio_addr": address,
                "pio_size": 21,
            }
            self.record(
                node,
                "Type",
                destination + ".pio_addr",
                address,
                derived=True,
                consumer="legacy_address_allocation",
                units="bytes",
            )
            self.record(
                node,
                "Type",
                destination + ".pio_size",
                21,
                derived=True,
                consumer="retained_dma_mmio",
                units="bytes",
            )
            for key, field in (
                ("BufferSize", "buffer_size"),
                ("MaxReqSize", "max_req_size"),
            ):
                value = self.field(
                    node,
                    key,
                    destination + "." + field,
                    required=True,
                    units="bytes",
                )
                result[field] = self.integer(
                    value, node, key, input_path + "." + key, positive=True
                )
            irq = self.field(node, "InterruptNum", destination + ".interrupt_num", 200)
            result["interrupt_num"] = self.integer(
                irq, node, "InterruptNum", input_path + ".InterruptNum"
            )
            masters = self.field(
                node,
                "PIOMaster",
                destination + ".pio_masters",
                required=True,
            )
            result["pio_masters"] = self.names(
                masters,
                node,
                "PIOMaster",
                input_path + ".PIOMaster",
                required=True,
            )
            self.resolved(
                destination + ".pio_masters",
                result["pio_masters"],
                "Comma-separated connection list",
            )
            if result["pio_masters"] != ["LocalBus"]:
                self.fail(
                    "unsupported_dma_master",
                    "Native NonCoherent DMA requires PIOMaster: LocalBus",
                    node,
                    "PIOMaster",
                    input_path + ".PIOMaster",
                )
            cluster["dmas"].append(result)
            address += self.stride(21)

        # Resolve all accelerator names before validating references.
        pending = []
        for ai, (parts, input_path) in enumerate(raw_accs):
            fields = _Map(str(self.config), 1)
            field_nodes = {}
            variables = []
            for pi, part in enumerate(parts):
                position = input_path + "[{}]".format(pi)
                self.mapping(part, document, "acc_cluster", position)
                self.keys(
                    part,
                    {
                        "Name",
                        "IrPath",
                        "PIOSize",
                        "PIOMaster",
                        "LocalSlaves",
                        "InterruptNum",
                        "Debug",
                        "Var",
                        "ConfigPath",
                    },
                    position,
                )
                for key, value in part.items():
                    if key == "Var":
                        if not isinstance(value, list) or not value:
                            self.fail(
                                "wrong_type",
                                "Expected nonempty Var list",
                                part,
                                key,
                                position + ".Var",
                            )
                        variables.extend(value)
                        continue
                    if key in fields:
                        self.fail(
                            "duplicate_field",
                            "Repeated accelerator field across list mappings",
                            part,
                            key,
                            position + "." + key,
                        )
                    fields[key] = value
                    fields.marks[key] = part.marks[key]
                    field_nodes[key] = part
            authored = self.field(
                fields,
                "Name",
                "clusters[0].accelerators[{}].name".format(ai),
                required=True,
            )
            normalized_name = self.name(
                authored, fields, "Name", input_path + ".Name"
            ).lower()
            if normalized_name in component_names:
                self.fail(
                    "duplicate_name",
                    "Case-insensitive component collision",
                    fields,
                    "Name",
                    input_path + ".Name",
                )
            self.resolved(
                "clusters[0].accelerators[{}].name".format(ai),
                normalized_name,
                "lowercase identifier",
            )
            component_names.add(normalized_name)
            pending.append((parts, fields, normalized_name, input_path))

        for ai, (parts, fields, acc_name, input_path) in enumerate(pending):
            destination = "clusters[0].accelerators[{}]".format(ai)
            if "ConfigPath" in fields:
                self.fail(
                    "unsupported_config_path",
                    "External ConfigPath needs a separate qualified adapter; "
                    "use this document's hw_config for the first native path",
                    fields,
                    "ConfigPath",
                    input_path + ".ConfigPath",
                )
            ir_relative = self.field(
                fields, "IrPath", destination + ".ir_relative", required=True
            )
            ir_path = self.path(
                ir_relative,
                fields,
                "IrPath",
                input_path + ".IrPath",
                {".ll"},
            )
            requested_pio = self.field(
                fields,
                "PIOSize",
                destination + ".requested_pio_size",
                required=True,
                units="bytes",
            )
            self.integer(
                requested_pio,
                fields,
                "PIOSize",
                input_path + ".PIOSize",
                positive=True,
            )
            debug = self.field(fields, "Debug", destination + ".debug", False)
            if type(debug) is not bool:
                self.fail(
                    "wrong_type",
                    "Debug must be a YAML boolean",
                    fields,
                    "Debug",
                    input_path + ".Debug",
                )
            irq = self.field(fields, "InterruptNum", destination + ".interrupt_num", -1)
            if irq != -1:
                self.integer(
                    irq,
                    fields,
                    "InterruptNum",
                    input_path + ".InterruptNum",
                )
            if type(irq) is not int or irq > 0x7FFFFFFF:
                self.fail(
                    "invalid_irq",
                    "Expected integer interrupt number",
                    fields,
                    "InterruptNum",
                    input_path + ".InterruptNum",
                )
            masters = self.field(
                fields,
                "PIOMaster",
                destination + ".pio_masters",
                required=True,
            )
            local = self.field(
                fields, "LocalSlaves", destination + ".local_slaves", None
            )
            result = {
                "name": acc_name,
                "authored_name": fields["Name"],
                "requested_pio_size": requested_pio,
                "pio_size": self.stride(requested_pio),
                "ir_path": ir_path,
                "ir_relative": ir_relative,
                "hardware_key": Path(ir_path).stem,
                "config_path": str(self.config),
                "debug": debug,
                "interrupt_num": irq,
                "memories": [],
                "pio_masters": self.names(
                    masters,
                    fields,
                    "PIOMaster",
                    input_path + ".PIOMaster",
                    required=True,
                ),
                "local_slaves": self.names(
                    local,
                    fields,
                    "LocalSlaves",
                    input_path + ".LocalSlaves",
                ),
            }
            if len(result["pio_masters"]) != 1:
                self.fail(
                    "unsupported_pio_fan_in",
                    "CommInterface.pio is scalar: exactly one PIO master "
                    "is supported",
                    fields,
                    "PIOMaster",
                    input_path + ".PIOMaster",
                )
            if result["pio_masters"] != ["LocalBus"]:
                self.fail(
                    "unsupported_pio_master",
                    "The first native GEMM path requires PIOMaster: LocalBus; "
                    "named PIO networks need separate qualification",
                    fields,
                    "PIOMaster",
                    input_path + ".PIOMaster",
                )
            if result["local_slaves"] not in ([], ["LocalBus"]):
                self.fail(
                    "unsupported_local_peer",
                    "The first native GEMM path allows only LocalBus "
                    "LocalSlaves or omission; named peers can double-connect "
                    "a scalar PIO port",
                    fields,
                    "LocalSlaves",
                    input_path + ".LocalSlaves",
                )
            self.resolved(
                destination + ".pio_masters",
                result["pio_masters"],
                "Comma-separated connection list",
            )
            self.resolved(
                destination + ".local_slaves",
                result["local_slaves"],
                "Comma-separated connection list; omission creates no edge",
            )
            for output, value, consumer in (
                ("ir_path", ir_path, "contained_ir_path"),
                ("config_path", str(self.config), "selected_primary_yaml"),
                ("hardware_key", result["hardware_key"], "retained_ir_stem"),
            ):
                self.record(
                    fields,
                    "IrPath",
                    destination + "." + output,
                    value,
                    derived=True,
                    consumer=consumer,
                )
            for part in parts:
                if "PIOSize" in part:
                    result["pio_addr"] = address
                    self.record(
                        part,
                        "PIOSize",
                        destination + ".pio_addr",
                        address,
                        derived=True,
                        consumer="legacy_address_allocation",
                        units="bytes",
                    )
                    self.record(
                        part,
                        "PIOSize",
                        destination + ".pio_size",
                        result["pio_size"],
                        derived=True,
                        consumer="retained_padded_mmio",
                        units="bytes",
                    )
                    address += result["pio_size"]
                for vi, node in enumerate(part.get("Var", [])):
                    memory_path = destination + ".memories[{}]".format(
                        len(result["memories"])
                    )
                    memory = self.memory(
                        node, acc_name, memory_path, address, component_names
                    )
                    result["memories"].append(memory)
                    address += self.stride(memory["size"])
            cluster["accelerators"].append(result)

        accelerator_names = {a["name"] for a in cluster["accelerators"]}
        for ai, accelerator in enumerate(cluster["accelerators"]):
            _, fields, _, input_path = pending[ai]
            for family in ("pio_masters", "local_slaves"):
                for peer in accelerator[family]:
                    if peer != "LocalBus" and peer not in accelerator_names:
                        self.fail(
                            "unknown_connection",
                            "Connection must name LocalBus or an accelerator",
                            fields,
                            "PIOMaster" if family == "pio_masters" else "LocalSlaves",
                            input_path + "." + family,
                        )
            for memory in accelerator["memories"]:
                for connection in memory["connections"]:
                    if connection["accelerator"] not in accelerator_names:
                        self.fail(
                            "unknown_connection",
                            "SPM connection names an unknown accelerator",
                            self.memory_sources[memory["name"]],
                            "Connections",
                            input_path + ".Var.Connections",
                        )
        if address > ADDRESS_CEILING:
            self.fail(
                "address_range_exceeded",
                "Derived cluster end exceeds 0x13ffffff",
                document,
                "acc_cluster",
                "acc_cluster",
            )
        cluster["top_address"] = address
        cluster["local_range"] = [self.base, address]
        self.record(
            document,
            "acc_cluster",
            "clusters[0].top_address",
            address,
            derived=True,
            consumer="retained_local_range",
            units="bytes",
        )
        hardware = document.get("hw_config", {})
        self.mapping(hardware, document, "hw_config", "hw_config")
        keys = {a["hardware_key"] for a in cluster["accelerators"]}
        self.keys(hardware, keys | {"name"}, "hw_config")
        if "name" in hardware:
            value = self.field(
                hardware,
                "name",
                "hardware_metadata.name",
                consumer="metadata",
            )
            if not isinstance(value, str):
                self.fail(
                    "wrong_type",
                    "Hardware name metadata must be text",
                    hardware,
                    "name",
                    "hw_config.name",
                )
        for accelerator in cluster["accelerators"]:
            key = accelerator["hardware_key"]
            accelerator["hardware"] = self.hardware(
                hardware.get(key),
                "hw_config." + key,
                source=hardware,
                key=key,
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "salam_native_configuration",
            "scope": "NonCoherent DMA and SPM, current typed SALAM ABI",
            "engine_root": str(self.root),
            "source": copy.deepcopy(self.dependencies[self.relative(self.config)]),
            "base_address": self.base,
            "clusters": [cluster],
            "typed_abi": self.catalog,
            "profile_context": {
                "authority": "Current typed SimObject declarations and "
                "the separately validated simulator build receipt",
                "selection": "No generator is imported or invoked",
                "runtime_clock": "Bound after final scalar overrides; "
                "characterization period is not a runtime clock",
                "physical_model": "Uncalibrated profile coefficients",
            },
            "dependencies": [
                self.dependencies[key] for key in sorted(self.dependencies)
            ],
            "provenance": self.provenance,
        }


def normalize_configuration(config_path, engine_root, *, base_address=None):
    """Validate and normalize the first native configuration route.

    Paths must remain within engine_root. No source file is modified and no
    configuration Python is executed. ConfigPath, stream/cache/register
    devices and additional YAML documents are deliberately unsupported.
    """
    result = _Normalizer(config_path, engine_root, base_address).normalize()
    return NormalizedConfiguration(
        json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
    )
