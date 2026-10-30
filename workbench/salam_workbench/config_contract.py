"""Source-backed, benchmark-independent SALAM configuration inspection.

This never runs a generator or simulator. A structural pass is not a claim
that a configured knob affected execution or that model data is calibrated.
"""

import ast
import configparser
import hashlib
import re
from pathlib import Path

import yaml


class _Loader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError("YAML keys must be unique strings")
        result[key] = loader.construct_object(value_node)
    return result


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")
_SOURCES = (
    "configs/SALAM/HWAccConfig.py",
    "src/hwacc/CycleCounts.py",
    "src/hwacc/FunctionalUnits.py",
    "src/hwacc/LLVMRead/src/instruction.hh",
)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _bad(result, path, code, message):
    result["issues"].append({"path": path, "code": code, "message": message})


def _uint(value, positive=False):
    return (
        type(value) is int
        and (0 < value if positive else 0 <= value)
        and value <= 0xFFFFFFFF
    )


def _ident(result, value, path):
    if not isinstance(value, str) or not _IDENT.fullmatch(value):
        _bad(result, path, "invalid_name", "Expected a Python-safe identifier")
        return None
    return value


def _keys(result, value, accepted, path):
    if not isinstance(value, dict):
        _bad(result, path, "wrong_type", "Expected mapping")
        return False
    for key in value:
        if key not in accepted:
            _bad(
                result,
                path + "." + str(key),
                "unconsumed_field",
                "No verified generator or runtime consumer for this field",
            )
    return True


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
    raise ValueError("Missing runtime registry " + name)


def _params(tree, class_name):
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            values = {}
            for item in node.body:
                if (
                    isinstance(item, ast.Assign)
                    and len(item.targets) == 1
                    and isinstance(item.targets[0], ast.Name)
                    and isinstance(item.value, ast.Call)
                    and item.value.args
                ):
                    try:
                        values[item.targets[0].id] = ast.literal_eval(
                            item.value.args[0]
                        )
                    except (ValueError, TypeError, SyntaxError):
                        pass
            return values
    raise ValueError("Missing SimObject class " + class_name)


def _consumers(result, engine):
    paths = [engine / relative for relative in _SOURCES]
    for relative, path in zip(_SOURCES, paths):
        if not path.is_file():
            _bad(
                result,
                relative,
                "missing_consumer_source",
                "Required engine source missing",
            )
    if result["issues"]:
        return None
    result["consumer_sources"] = {
        relative: _sha(path) for relative, path in zip(_SOURCES, paths)
    }
    registry_tree = ast.parse(paths[0].read_text(encoding="utf-8"))
    fu = _registry(registry_tree, "_FU_REGISTRY")
    inst = _registry(registry_tree, "_INST_REGISTRY")
    cycles = _params(ast.parse(paths[1].read_text(encoding="utf-8")), "CycleCounts")
    fu_tree = ast.parse(paths[2].read_text(encoding="utf-8"))
    fu_ids = {
        name: _params(fu_tree, class_name).get("enum_value")
        for name, class_name in fu.items()
    }
    if not fu_ids or any(not _uint(value) for value in fu_ids.values()):
        raise ValueError("Generated FU identifiers are incomplete")
    from .fu_capability import inspect_fu_capability

    capability = inspect_fu_capability(engine)
    result["fu_scheduler_capability"] = capability
    result["consumer_sources"].update(capability["sources"])
    limit_disabled = not capability["supported"]
    result["behavioral_limits"][0] = (
        "FU scheduler source capability present; a verified build and run are still required"
        if capability["supported"]
        else "Nonzero FU limits require the patched FU scheduler and a verified build"
    )
    return fu, inst, cycles, fu_ids, limit_disabled


def _pad(size):
    # Existing parser allocates one extra 64-byte unit for aligned payloads.
    return size + 64 - size % 64


def _expect(result, section, key, value):
    result["expected_effective"].setdefault(section, {})[key] = (
        str(value).lower() if type(value) is bool else str(value)
    )


def _ir(result, value, path):
    if not isinstance(value, str) or not value.endswith(".ll"):
        _bad(
            result,
            path,
            "invalid_ir_path",
            "Expected relative LLVM IR .ll path",
        )
        return
    relative = Path(value)
    if (
        relative.is_absolute()
        or "\\" in value
        or ":" in value
        or any(part in (".", "..") for part in relative.parts)
    ):
        _bad(
            result,
            path,
            "unsafe_ir_path",
            "IR path must stay inside staged workspace",
        )
    else:
        result["ir_paths"].append(value)


def _configpath_consumer(workspace):
    """Require an active staged parser adapter, not a comment or marker alone."""
    if workspace is None:
        return False
    parser = Path(workspace) / "SALAM-Configurator/parser.py"
    if not parser.is_file():
        return False
    tree = ast.parse(parser.read_text(encoding="utf-8"))
    marker = any(
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "CONFIGPATH_CONSUMER_VERSION"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and node.value.value == 1
        for node in tree.body
    )

    def matching_call(node):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_workbench_config_path"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "M5_Path"
            and isinstance(node.args[1], ast.Subscript)
            and isinstance(node.args[1].value, ast.Name)
            and node.args[1].value.id == "deviceDict"
        ):
            return False
        key = node.args[1].slice
        if isinstance(key, ast.Index):
            key = key.value
        return isinstance(key, ast.Constant) and key.value == "ConfigPath"

    call = any(matching_call(node) for node in ast.walk(tree))
    return marker and call


def _external_hw(result, workspace, relative, accelerator, path):
    if not isinstance(relative, str) or not relative.startswith(
        ("benchmarks/", "configs/")
    ):
        _bad(
            result,
            path,
            "invalid_config_path",
            "Expected benchmarks/... or configs/... YAML path",
        )
        return None
    rel = Path(relative)
    if (
        rel.suffix not in (".yml", ".yaml")
        or rel.is_absolute()
        or "\\" in relative
        or ":" in relative
        or any(part in (".", "..") for part in rel.parts)
    ):
        _bad(
            result,
            path,
            "invalid_config_path",
            "ConfigPath must be safe relative YAML",
        )
        return None
    root = Path(workspace).resolve()
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        _bad(
            result,
            path,
            "config_path_escape",
            "ConfigPath escapes staged workspace",
        )
        return None
    if not target.is_file():
        _bad(
            result,
            path,
            "missing_config_path",
            "Referenced ConfigPath file is missing",
        )
        return None
    external = list(yaml.load_all(target.read_text(encoding="utf-8"), Loader=_Loader))
    if len(external) != 1 or not isinstance(external[0], dict):
        _bad(
            result,
            path,
            "invalid_external_config",
            "Referenced YAML must have one mapping document",
        )
        return None
    hw = external[0].get("hw_config")
    if (
        not isinstance(hw, dict)
        or not isinstance(hw.get(accelerator), dict)
        or not hw[accelerator]
    ):
        _bad(
            result,
            path,
            "missing_external_hardware",
            "Referenced YAML must contain nonempty hw_config." + accelerator,
        )
        return None
    result["external_config_paths"][accelerator] = {
        "path": str(target),
        "relative_path": relative,
        "sha256": _sha(target),
    }
    result["external_hardware"][accelerator] = hw[accelerator]
    return str(target)


def _topology(result, documents, base_address, config_path, generated_root):
    configpath_enabled = _configpath_consumer(generated_root)
    from .registerbank_adapter import registerbank_ports_supported, registerbank_port_kind

    registerbank_enabled = registerbank_ports_supported(generated_root)
    registerbank_kind = registerbank_port_kind(generated_root)
    address, seen_clusters = base_address, set()
    for di, doc in enumerate(documents):
        root = "documents[{}]".format(di)
        if not _keys(result, doc, {"acc_cluster", "hw_config"}, root):
            continue
        entries = doc.get("acc_cluster")
        if not isinstance(entries, list) or not entries:
            _bad(
                result,
                root + ".acc_cluster",
                "invalid_cluster",
                "Expected nonempty list",
            )
            continue
        for ei, entry in enumerate(entries):
            if (
                not isinstance(entry, dict)
                or len(entry) != 1
                or next(iter(entry), None) not in ("Name", "DMA", "Accelerator")
            ):
                _bad(
                    result,
                    root + ".acc_cluster[{}]".format(ei),
                    "invalid_cluster_item",
                    "Expected exactly one Name, DMA, or Accelerator key",
                )
        names = [
            item["Name"]
            for item in entries
            if isinstance(item, dict) and "Name" in item
        ]
        if len(names) != 1:
            _bad(
                result,
                root + ".acc_cluster",
                "cluster_name",
                "Exactly one Name required",
            )
            continue
        name = _ident(result, names[0], root + ".Name")
        if name is None:
            continue
        if name.lower() in seen_clusters:
            _bad(
                result,
                root + ".Name",
                "duplicate_cluster",
                "Cluster names must be unique",
            )
        seen_clusters.add(name.lower())
        cluster = {
            "name": name,
            "base_address": address,
            "dmas": [],
            "accelerators": [],
            "memories": [],
        }
        result["components"]["clusters"].append(cluster)
        devices = set()
        register_indices = {}
        # Generator processes all DMA objects before all accelerator objects.
        for kind in ("DMA", "Accelerator"):
            for ei, entry in enumerate(entries):
                if not isinstance(entry, dict) or kind not in entry:
                    continue
                records = entry[kind]
                path = root + ".acc_cluster[{}].{}".format(ei, kind)
                if not isinstance(records, list) or not records:
                    _bad(
                        result,
                        path,
                        "empty_device",
                        "Expected nonempty device list",
                    )
                    continue
                if kind == "DMA":
                    for ri, dma in enumerate(records):
                        dp = path + "[{}]".format(ri)
                        if not _keys(
                            result,
                            dma,
                            {
                                "Name",
                                "Type",
                                "BufferSize",
                                "MaxReqSize",
                                "PIOMaster",
                                "InterruptNum",
                                "ReadInt",
                                "WriteInt",
                            },
                            dp,
                        ):
                            continue
                        dn = _ident(result, dma.get("Name"), dp + ".Name")
                        if dma.get("Type") != "NonCoherent":
                            _bad(
                                result,
                                dp + ".Type",
                                "unsupported_dma_type",
                                "This DMA path needs its own actual simulator witness",
                            )
                            continue
                        if "ReadInt" in dma or "WriteInt" in dma:
                            _bad(
                                result,
                                dp,
                                "unconsumed_interrupt",
                                "NonCoherent DMA ignores stream interrupts",
                            )
                        if not _uint(dma.get("BufferSize"), True) or not _uint(
                            dma.get("MaxReqSize"), True
                        ):
                            _bad(
                                result,
                                dp,
                                "invalid_dma_size",
                                "Positive BufferSize and MaxReqSize required",
                            )
                            continue
                        if dma["MaxReqSize"] > dma["BufferSize"]:
                            _bad(
                                result,
                                dp,
                                "dma_size_conflict",
                                "MaxReqSize exceeds BufferSize",
                            )
                        if dma.get("PIOMaster", "LocalBus") != "LocalBus":
                            _bad(
                                result,
                                dp + ".PIOMaster",
                                "unsupported_connection",
                                "Non-LocalBus generator path is not verified",
                            )
                        if dn:
                            if dn.lower() in devices:
                                _bad(
                                    result,
                                    dp + ".Name",
                                    "duplicate_device",
                                    "Duplicate device name",
                                )
                            devices.add(dn.lower())
                            section = "system.{}.{}".format(name.lower(), dn.lower())
                            for key, value in (
                                ("buffer_size", dma["BufferSize"]),
                                ("max_req_size", dma["MaxReqSize"]),
                                ("pio_addr", address),
                                ("pio_size", 21),
                            ):
                                _expect(result, section, key, value)
                            if "InterruptNum" in dma:
                                if _uint(dma["InterruptNum"]):
                                    _expect(
                                        result,
                                        section,
                                        "int_num",
                                        dma["InterruptNum"],
                                    )
                                else:
                                    _bad(
                                        result,
                                        dp + ".InterruptNum",
                                        "invalid_interrupt",
                                        "Expected UInt32",
                                    )
                            cluster["dmas"].append(
                                {
                                    "name": dn,
                                    "type": "NonCoherent",
                                    "address": address,
                                }
                            )
                        address += _pad(21)
                else:
                    fields, variables = {}, []
                    for ri, item in enumerate(records):
                        ap = path + "[{}]".format(ri)
                        if not isinstance(item, dict):
                            _bad(
                                result,
                                ap,
                                "invalid_device_field",
                                "Expected mapping",
                            )
                        elif "Var" in item:
                            if set(item) != {"Var"} or not isinstance(
                                item["Var"], list
                            ):
                                _bad(
                                    result,
                                    ap,
                                    "invalid_variables",
                                    "Var must be a list",
                                )
                            else:
                                variables.extend((ap, v) for v in item["Var"])
                        else:
                            accepted = {
                                "Name",
                                "IrPath",
                                "PIOSize",
                                "PIOMaster",
                                "LocalSlaves",
                                "InterruptNum",
                                "Debug",
                                "StreamIn",
                                "StreamOut",
                            }
                            if configpath_enabled:
                                accepted.add("ConfigPath")
                            _keys(result, item, accepted, ap)
                            fields.update(item)
                    an = _ident(result, fields.get("Name"), path + ".Name")
                    if not _uint(fields.get("PIOSize"), True):
                        _bad(
                            result,
                            path + ".PIOSize",
                            "invalid_pio_size",
                            "Positive PIOSize required",
                        )
                        continue
                    if fields.get("PIOMaster", "LocalBus") != "LocalBus":
                        _bad(
                            result,
                            path + ".PIOMaster",
                            "unsupported_connection",
                            "Non-LocalBus PIO generator path is not verified",
                        )
                    if fields.get("LocalSlaves") not in (None, "LocalBus"):
                        _bad(
                            result,
                            path + ".LocalSlaves",
                            "unsupported_connection",
                            "Non-LocalBus slave path needs a simulator witness",
                        )
                    if (
                        fields.get("StreamIn") is not None
                        or fields.get("StreamOut") is not None
                    ):
                        _bad(
                            result,
                            path,
                            "unwitnessed_stream_connection",
                            "Stream connection needs a separate actual simulator witness",
                        )
                    if "Debug" in fields and type(fields["Debug"]) is not bool:
                        _bad(
                            result,
                            path + ".Debug",
                            "invalid_debug",
                            "Debug must be Boolean",
                        )
                    _ir(result, fields.get("IrPath"), path + ".IrPath")
                    pio = _pad(fields["PIOSize"])
                    if an:
                        ir_path = fields.get("IrPath")
                        if (
                            isinstance(ir_path, str)
                            and Path(ir_path).stem != an.lower()
                        ):
                            _bad(
                                result,
                                path + ".IrPath",
                                "ir_hardware_name_mismatch",
                                "Runtime hardware lookup uses IR basename",
                            )
                        config_binding = str(Path(config_path).resolve())
                        if "ConfigPath" in fields and configpath_enabled:
                            external = _external_hw(
                                result,
                                generated_root,
                                fields["ConfigPath"],
                                Path(ir_path).stem
                                if isinstance(ir_path, str)
                                else an.lower(),
                                path + ".ConfigPath",
                            )
                            if external:
                                config_binding = external
                        result["config_paths"].append(config_binding)
                        if an.lower() in devices:
                            _bad(
                                result,
                                path + ".Name",
                                "duplicate_device",
                                "Duplicate device name",
                            )
                        devices.add(an.lower())
                        section = "system.{}.{}".format(name.lower(), an.lower())
                        for key, value in (
                            ("pio_addr", address),
                            ("pio_size", pio),
                            ("enable_debug_msgs", fields.get("Debug", False)),
                        ):
                            _expect(result, section, key, value)
                        if "InterruptNum" in fields:
                            if _uint(fields["InterruptNum"]):
                                _expect(
                                    result,
                                    section,
                                    "int_num",
                                    fields["InterruptNum"],
                                )
                            else:
                                _bad(
                                    result,
                                    path + ".InterruptNum",
                                    "invalid_interrupt",
                                    "Expected UInt32",
                                )
                        cluster["accelerators"].append(
                            {
                                "name": an,
                                "ir_path": fields.get("IrPath"),
                                "address": address,
                                "pio_size": pio,
                            }
                        )
                    address += pio
                    for vp, var in variables:
                        if not _keys(
                            result,
                            var,
                            {
                                "Name",
                                "Type",
                                "Size",
                                "Ports",
                                "ReadyMode",
                                "ResetOnRead",
                                "ReadOnInvalid",
                                "WriteOnValid",
                                "Connections",
                                "StreamSize",
                                "BufferSize",
                                "InCon",
                                "OutCon",
                            },
                            vp,
                        ):
                            continue
                        vn = _ident(result, var.get("Name"), vp + ".Name")
                        if var.get("Type") not in ("SPM", "RegisterBank"):
                            _bad(
                                result,
                                vp + ".Type",
                                "unsupported_memory_type",
                                "Memory type needs a separate actual simulator witness",
                            )
                            continue
                        if var["Type"] == "RegisterBank" and any(
                            key in var
                            for key in (
                                "ReadyMode",
                                "ResetOnRead",
                                "ReadOnInvalid",
                                "WriteOnValid",
                            )
                        ):
                            _bad(
                                result,
                                vp,
                                "unconsumed_register_field",
                                "RegisterBank generator ignores SPM controls",
                            )
                        if var["Type"] == "RegisterBank" and "Ports" in var and not registerbank_enabled:
                            _bad(result, vp + ".Ports", "unconsumed_register_field", "RegisterBank port count requires the verified staged generator adapter")
                        if not _uint(var.get("Size"), True):
                            _bad(
                                result,
                                vp + ".Size",
                                "invalid_memory_size",
                                "Positive Size required",
                            )
                            continue
                        if (
                            var.get("Type") in ("SPM", "RegisterBank")
                            and "Ports" in var
                            and not _uint(var["Ports"], True)
                        ):
                            _bad(
                                result,
                                vp + ".Ports",
                                "invalid_ports",
                                "Ports must be positive",
                            )
                        for flag in (
                            "ReadyMode",
                            "ResetOnRead",
                            "ReadOnInvalid",
                            "WriteOnValid",
                        ):
                            if flag in var and type(var[flag]) is not bool:
                                _bad(
                                    result,
                                    vp + "." + flag,
                                    "invalid_flag",
                                    "Expected Boolean",
                                )
                        if "Connections" in var:
                            connections = var["Connections"]
                            tokens = (
                                connections.split(",")
                                if isinstance(connections, str)
                                else []
                            )
                            if not tokens or any(
                                len(parts) != 2
                                or not _IDENT.fullmatch(parts[0])
                                or not parts[1].isdigit()
                                or not _uint(int(parts[1]), True)
                                for parts in (
                                    token.strip().split(":") for token in tokens
                                )
                            ):
                                _bad(
                                    result,
                                    vp + ".Connections",
                                    "invalid_connection",
                                    "Expected comma-separated device:positive-port-count",
                                )
                            elif var["Type"] == "RegisterBank" and not registerbank_enabled and any(
                                int(token.strip().split(":")[1]) != 1
                                for token in tokens
                            ):
                                _bad(
                                    result,
                                    vp + ".Connections",
                                    "unconsumed_register_ports",
                                    "RegisterBank generator ignores the requested port count",
                                )
                        if vn:
                            if vn.lower() in devices:
                                _bad(
                                    result,
                                    vp + ".Name",
                                    "duplicate_device",
                                    "Duplicate device name",
                                )
                            devices.add(vn.lower())
                            section = "system.{}.{}".format(name.lower(), vn.lower())
                            _expect(
                                result,
                                section,
                                "range",
                                "{}:{}".format(address, address + var["Size"]),
                            )
                            if var["Type"] == "RegisterBank" and registerbank_enabled:
                                connections = [(an, var.get("Ports", 1))]
                                if "Connections" in var and isinstance(var["Connections"], str):
                                    for token in var["Connections"].split(","):
                                        device, count = token.strip().split(":")
                                        connections.append((device, int(count)))
                                if registerbank_kind == "unknown":
                                    _bad(result, vp, "unknown_register_port", "Cannot establish compiled RegisterBank private-port declaration")
                                if registerbank_kind == "scalar" and sum(count for _, count in connections) != 1:
                                    _bad(result, vp, "scalar_register_port_limit", "Compiled RegisterBank exposes one private response port; multiple private connections require a simulator implementation and rebuild")
                                peers = []
                                for device, count in connections:
                                    if not _uint(count, True):
                                        continue
                                    for _ in range(count):
                                        index = register_indices.get(device.lower(), 0)
                                        peers.append("system.{}.{}.reg[{}]".format(name.lower(), device.lower(), index))
                                        register_indices[device.lower()] = index + 1
                                _expect(result, section, "reg_port", " ".join(peers))
                            if var["Type"] == "SPM":
                                for y, k, default in (
                                    ("ReadyMode", "ready_mode", False),
                                    (
                                        "ResetOnRead",
                                        "reset_on_scratchpad_read",
                                        True,
                                    ),
                                    (
                                        "ReadOnInvalid",
                                        "read_on_invalid",
                                        False,
                                    ),
                                    ("WriteOnValid", "write_on_valid", True),
                                ):
                                    _expect(result, section, k, var.get(y, default))
                            cluster["memories"].append(
                                {
                                    "name": vn,
                                    "type": var["Type"],
                                    "address": address,
                                    "size": var["Size"],
                                }
                            )
                        address += _pad(var["Size"])
        cluster["end_address"] = address
        # The legacy generator otherwise prints a warning and returns zero.
        if address >= 0x14000000:
            _bad(
                result,
                root + ".acc_cluster",
                "address_range_exceeded",
                "Generated cluster end exceeds gem5's 0x13ffffff address ceiling",
            )
        address += 64 - address % 64


def _hardware(result, documents, consumer):
    fus, instructions, cycles, fu_ids, limit_disabled = consumer
    accel = {
        a["name"].lower(): c["name"].lower()
        for c in result["components"]["clusters"]
        for a in c["accelerators"]
    }
    for di, doc in enumerate(documents):
        hw = doc.get("hw_config", {}) if isinstance(doc, dict) else {}
        root = "documents[{}].hw_config".format(di)
        if not isinstance(hw, dict):
            _bad(result, root, "invalid_hardware", "Expected hardware mapping")
            continue
        selected = dict(hw)
        for external_name, external_settings in result["external_hardware"].items():
            if external_name in selected and selected[external_name] is not None:
                _bad(
                    result,
                    root + "." + external_name,
                    "shadowed_hardware",
                    "Primary hw_config is ignored when accelerator ConfigPath is set",
                )
            selected[external_name] = external_settings
        for name, settings in selected.items():
            path = root + "." + str(name)
            if name == "name":
                if not isinstance(settings, str):
                    _bad(
                        result,
                        path,
                        "invalid_metadata",
                        "name metadata must be text",
                    )
                continue
            if name.lower() not in accel:
                _bad(
                    result,
                    path,
                    "unused_hardware",
                    "No generated accelerator has this name",
                )
                continue
            if settings is None:
                continue
            if not _keys(result, settings, {"instructions", "functional_units"}, path):
                continue
            if not isinstance(settings.get("instructions", {}), dict):
                _bad(
                    result,
                    path + ".instructions",
                    "invalid_instructions",
                    "Expected mapping",
                )
                continue
            if not isinstance(settings.get("functional_units", {}), dict):
                _bad(
                    result,
                    path + ".functional_units",
                    "invalid_functional_units",
                    "Expected mapping",
                )
                continue
            prefix = "system.{}.{}.hw_interface".format(
                accel[name.lower()], name.lower()
            )
            for inst, fields in settings.get("instructions", {}).items():
                ip = path + ".instructions." + str(inst)
                if inst not in instructions:
                    _bad(
                        result,
                        ip,
                        "unknown_instruction",
                        "Absent from runtime registry",
                    )
                    continue
                if not _keys(
                    result,
                    fields,
                    {
                        "functional_unit",
                        "functional_unit_limit",
                        "opcode_num",
                        "runtime_cycles",
                    },
                    ip,
                ):
                    continue
                for field, value in fields.items():
                    if field not in {
                        "functional_unit",
                        "functional_unit_limit",
                        "opcode_num",
                        "runtime_cycles",
                    }:
                        continue
                    if not _uint(value):
                        _bad(
                            result,
                            ip + "." + field,
                            "invalid_uint32",
                            "Expected UInt32",
                        )
                        continue
                    if field == "functional_unit" and value not in (
                        {0} | set(fu_ids.values())
                    ):
                        _bad(
                            result,
                            ip + ".functional_unit",
                            "unknown_fu_id",
                            "No generated FU has this identifier",
                        )
                    if field == "functional_unit_limit" and value:
                        _bad(
                            result,
                            ip + ".functional_unit_limit",
                            "inactive_fu_limit",
                            "Per-instruction functional_unit_limit has no scheduler consumer",
                        )
                    if field == "runtime_cycles":
                        key = {
                            "and": "and_inst",
                            "or": "or_inst",
                            "xor": "xor_inst",
                        }.get(inst, inst)
                        if key not in cycles:
                            _bad(
                                result,
                                ip + ".runtime_cycles",
                                "unknown_cycle_param",
                                "No CycleCounts parameter receives this value",
                            )
                        else:
                            _expect(result, prefix + ".cycle_counts", key, value)
                    else:
                        _expect(
                            result,
                            prefix + ".inst_config." + inst,
                            field,
                            value,
                        )
            for fu, fields in settings.get("functional_units", {}).items():
                fp = path + ".functional_units." + str(fu)
                if fu not in fus:
                    _bad(
                        result,
                        fp,
                        "unknown_fu",
                        "Absent from runtime registry",
                    )
                    continue
                if not _keys(result, fields, {"cycles", "limit"}, fp):
                    continue
                for field, value in fields.items():
                    if field not in {"cycles", "limit"}:
                        continue
                    if not _uint(value):
                        _bad(
                            result,
                            fp + "." + field,
                            "invalid_uint32",
                            "Expected UInt32",
                        )
                    elif field == "limit" and value and limit_disabled:
                        _bad(
                            result,
                            fp + ".limit",
                            "inactive_fu_limit",
                            "No source-verified FU scheduler consumes nonzero limit",
                        )
                    else:
                        _expect(
                            result,
                            prefix + ".functional_units." + fu,
                            field,
                            value,
                        )


def _generated(result, root, config_path, system_name):
    root = Path(root).resolve()
    config_path = Path(config_path).resolve()
    try:
        benchmark_dir = config_path.parent.relative_to(root)
    except ValueError:
        _bad(
            result,
            str(config_path),
            "generated_root_mismatch",
            "Configuration is not inside the generated workspace",
        )
        result["witnesses"]["generated"] = {"state": "failed"}
        return
    files = [
        root / "configs/SALAM/generated" / (system_name + ".py"),
        root / "configs/SALAM/generated" / ("fs_" + system_name + ".py"),
    ]
    files += [
        root / benchmark_dir / (c["name"] + "_hw_defines.h")
        for c in result["components"]["clusters"]
    ]
    missing = [str(p) for p in files if not p.is_file()]
    if missing:
        _bad(result, str(root), "missing_generated", "Generator outputs missing")
        result["witnesses"]["generated"] = {
            "state": "failed",
            "missing": missing,
        }
        return
    try:
        tree = ast.parse(files[0].read_text(encoding="utf-8"))
        fs = ast.parse(files[1].read_text(encoding="utf-8"))
    except SyntaxError as error:
        _bad(result, str(root), "invalid_generated_python", str(error))
        result["witnesses"]["generated"] = {"state": "failed"}
        return
    literals = {"ir": [], "config": []}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in literals
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            literals[node.targets[0].id].append(node.value.value)
    expected_ir = sorted(str(root / path) for path in result["ir_paths"])
    expected_config = sorted(result["config_paths"])
    if (
        sorted(literals["ir"]) != expected_ir
        or sorted(literals["config"]) != expected_config
    ):
        _bad(
            result,
            str(files[0]),
            "generated_input_mismatch",
            "Generated IR/config literals do not bind to the staged inputs",
        )
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    for cluster in result["components"]["clusters"]:
        if "build" + cluster["name"] not in functions:
            _bad(
                result,
                str(files[0]),
                "missing_cluster_function",
                "Generated cluster construction function is absent",
            )
    if "makeHWAcc" not in functions:
        _bad(
            result,
            str(files[0]),
            "missing_setup_function",
            "makeHWAcc is absent",
        )
    imports = [
        alias.name
        for node in ast.walk(fs)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    if imports.count(system_name) != 1:
        _bad(
            result,
            str(files[1]),
            "wrong_system_import",
            "Full-system config imports wrong generated system",
        )
    for cluster, header in zip(result["components"]["clusters"], files[2:]):
        macros = {}
        for macro, value in re.findall(
            r"^#define\s+(\w+)\s+(0x[0-9a-fA-F]+)\s*$",
            header.read_text(encoding="utf-8"),
            re.M,
        ):
            if macro in macros:
                _bad(result, str(header), "duplicate_address_macro", macro)
            macros[macro] = int(value, 16)
        expected = {
            device["name"].upper(): device["address"]
            for device in cluster["accelerators"] + cluster["memories"]
        }
        if len(cluster["dmas"]) == 1:
            dma = cluster["dmas"][0]
            expected.update(
                {
                    "DMA_Flags": dma["address"],
                    "DMA_RdAddr": dma["address"] + 1,
                    "DMA_WrAddr": dma["address"] + 9,
                    "DMA_CopyLen": dma["address"] + 17,
                }
            )
        for macro, value in expected.items():
            if macros.get(macro) != value:
                _bad(
                    result,
                    str(header),
                    "address_macro_mismatch",
                    "{} expected {} but found {}".format(
                        macro, hex(value), macros.get(macro)
                    ),
                )
    state = "failed" if result["issues"] else "passed"
    result["witnesses"]["generated"] = {
        "state": state,
        "outputs": [{"path": str(p), "sha256": _sha(p)} for p in files],
    }


def _effective(result, path):
    path = Path(path)
    if not path.is_file():
        _bad(result, str(path), "missing_effective", "config.ini missing")
        result["witnesses"]["effective"] = {"state": "failed"}
        return
    ini = configparser.ConfigParser(interpolation=None, strict=False)
    ini.read(str(path), encoding="utf-8")
    differences = []
    for section, values in result["expected_effective"].items():
        for key, expected in values.items():
            actual = ini.get(section, key, fallback=None)
            if actual is None or actual.lower() != expected.lower():
                differences.append(
                    {
                        "section": section,
                        "key": key,
                        "expected": expected,
                        "actual": actual,
                    }
                )
    result["witnesses"]["effective"] = {
        "state": "passed" if not differences else "failed",
        "path": str(path),
        "sha256": _sha(path),
        "differences": differences,
    }
    if differences:
        _bad(
            result,
            str(path),
            "effective_mismatch",
            "Requested fields differ in config.ini",
        )


def analyze_configuration(
    config_path,
    engine_root,
    *,
    generated_root=None,
    effective_config=None,
    base_address=0x10020000,
    simulator_source=None,
    system_name=None,
):
    """Return structural and optional generated/effective witness evidence.

    ``valid`` means all requested fields have known source consumers and all
    supplied witnesses match. It never means a simulation ran or power was
    measured. A simulator rebuild is determined from generated C++/SimObject
    source identity versus the binary receipt by the calling pipeline.
    """
    config_path, engine = (
        Path(config_path).resolve(),
        Path(engine_root).resolve(),
    )
    result = {
        "schema_version": 1,
        "kind": "salam_configuration_contract",
        "valid": False,
        "issues": [],
        "source": {"path": str(config_path)},
        "consumer_sources": {},
        "components": {"clusters": []},
        "ir_paths": [],
        "config_paths": [],
        "external_config_paths": {},
        "external_hardware": {},
        "expected_effective": {},
        "required_actions": {
            "regenerate_python_and_headers": True,
            "rebuild_guest": True,
            "rebuild_ir": True,
            "rebuild_simulator": None,
            "rebuild_simulator_reason": "Compare generated C++/SimObject and model-profile source identity with binary receipt",
        },
        "dependency_classes": {
            "topology_memory_dma": [
                "regenerate_python_and_headers",
                "rebuild_guest",
                "run_simulation",
            ],
            "accelerator_c_or_ir": ["rebuild_ir", "run_simulation"],
            "yaml_hardware_parameter": [
                "run_simulation",
                "verify_effective_config",
            ],
            "generated_cpp_simobject_or_profile": [
                "regenerate_cpp_and_simobjects",
                "rebuild_simulator",
                "run_simulation",
            ],
        },
        "model_claims": {
            "power_energy_area_characterization_verified": False,
            "simulation_usage_power_estimate_verified": False,
        },
        "behavioral_limits": [
            "Current C++ hasFunctionalUnit() returns false, so nonzero FU limits do not enforce contention",
            "Model coefficients have no verified synthesis provenance or calibrated run-level aggregation",
        ],
        "witnesses": {
            "generated": {"state": "not_checked"},
            "effective": {"state": "not_checked"},
        },
    }
    try:
        if not config_path.is_file() or not engine.is_dir():
            raise ValueError("Config file or engine root missing")
        if not _uint(base_address) or base_address < 0x10000000 or base_address % 64:
            raise ValueError(
                "Base address must be 64-byte aligned ARM accelerator address"
            )
        result["source"]["sha256"] = _sha(config_path)
        documents = list(
            yaml.load_all(config_path.read_text(encoding="utf-8"), Loader=_Loader)
        )
        if not documents:
            raise ValueError("Configuration has no YAML documents")
        if len(documents) != 1:
            _bad(
                result,
                str(config_path),
                "multi_document_profile_unverified",
                "Generator loads multiple documents, but standard HWAccConfig "
                "loads one document except its special MobileNetV2 path",
            )
        consumer = _consumers(result, engine)
        if consumer is None:
            return result
        # The staged parser can consume ConfigPath before generated files exist.
        # A later call with generated_root separately verifies generated outputs.
        _topology(
            result,
            documents,
            base_address,
            config_path,
            generated_root if generated_root is not None else engine,
        )
        _hardware(result, documents, consumer)
        if generated_root is not None:
            selected_name = system_name or config_path.parent.name
            if _ident(result, selected_name, "system_name"):
                _generated(result, generated_root, config_path, selected_name)
        if effective_config is not None:
            _effective(result, effective_config)
        if simulator_source is not None:
            result["required_actions"]["simulator_source_reference"] = str(
                simulator_source
            )
        result["valid"] = not result["issues"]
    except Exception as error:
        _bad(
            result,
            str(config_path),
            "contract_error",
            type(error).__name__ + ": " + str(error),
        )
    return result
