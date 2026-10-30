"""Pure conversion between legacy GUI widgets and checked SALAM requests.

The editor preserves source YAML fields that its widgets do not expose. Every
visible setting that affects generation or simulation is represented in the
request; unsupported choices fail rather than disappearing from the document.
"""
import ast
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import re


_COMPONENT_KEYS = {"dma", "accelerator", "memory"}
_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_SAFE_RELATIVE = re.compile(r"^[A-Za-z0-9._/-]+$")
_PROFILE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
MODEL_FLOAT_FIELDS = ("internal_power", "switch_power", "dynamic_power",
                      "dynamic_energy", "leakage_power", "area", "path_delay")
MODEL_INT_FIELDS = ("fu_latency", "limit")


def source_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_fu_registry(engine_root):
    """Read actual generated FU names without importing simulator modules."""
    path = Path(engine_root) / "configs/SALAM/HWAccConfig.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "_FU_REGISTRY"
                for target in node.targets):
            if not isinstance(node.value, ast.Dict):
                raise ValueError("FU registry is not a dictionary")
            names = [key.value for key in node.value.keys
                     if isinstance(key, ast.Constant) and isinstance(key.value, str)]
            if not names or len(names) != len(node.value.keys):
                raise ValueError("FU registry has invalid names")
            return names
    raise ValueError("Active FU registry missing")


def read_fu_ids(engine_root):
    """Read numeric IDs from the active generated SimObject source."""
    from .config_contract import _params, _registry
    engine = Path(engine_root)
    registry_tree = ast.parse(
        (engine / "configs/SALAM/HWAccConfig.py").read_text(encoding="utf-8"))
    fu_tree = ast.parse(
        (engine / "src/hwacc/FunctionalUnits.py").read_text(encoding="utf-8"))
    names = _registry(registry_tree, "_FU_REGISTRY")
    ids = {name: _params(fu_tree, class_name).get("enum_value")
           for name, class_name in names.items()}
    if (not ids or any(type(value) is not int or value < 0 for value in ids.values())
            or len(set(ids.values())) != len(ids)):
        raise ValueError("Generated FU identifiers are incomplete or duplicate")
    return ids


def discover_profile_periods(engine_root, benchmark, model, profile):
    """List periods with actual model/profile directories under this benchmark."""
    if not isinstance(benchmark, str) or not re.fullmatch(
            r"benchmarks/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", benchmark):
        raise ValueError("Invalid selected benchmark")
    for label, value in (("model", model), ("profile", profile)):
        if not isinstance(value, str) or not _PROFILE_TOKEN.fullmatch(value):
            raise ValueError("Invalid hardware " + label)
    engine = Path(engine_root).resolve(strict=True)
    model_dir = engine / benchmark / "configs/hw_interface/functional_units" / model
    if not model_dir.exists():
        return []
    if model_dir.is_symlink():
        raise ValueError("Hardware model directory is symlinked")
    model_dir = model_dir.resolve(strict=True)
    model_dir.relative_to(engine)
    if not model_dir.is_dir():
        return []
    periods = []
    for period_dir in sorted(model_dir.iterdir(), key=lambda item: item.name):
        if not _PROFILE_TOKEN.fullmatch(period_dir.name):
            continue
        if period_dir.is_symlink():
            raise ValueError("Hardware period directory is symlinked")
        candidate = period_dir / profile
        if not candidate.exists():
            continue
        if candidate.is_symlink():
            raise ValueError("Hardware profile directory is symlinked")
        candidate = candidate.resolve(strict=True)
        candidate.relative_to(engine)
        if candidate.is_dir():
            periods.append(period_dir.name)
    return periods

def extract_components(document):
    """Flatten one cluster into editable records while retaining raw fields."""
    if not isinstance(document, dict):
        raise ValueError("GUI editor requires one YAML mapping document")
    entries = document.get("acc_cluster")
    if not isinstance(entries, list):
        raise ValueError("YAML acc_cluster must be a list")
    names = [entry["Name"] for entry in entries
             if isinstance(entry, dict) and "Name" in entry]
    if len(names) != 1 or not isinstance(names[0], str):
        raise ValueError("GUI editor requires exactly one cluster Name")
    components = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Cluster entry must be a mapping")
        if "Name" in entry:
            if set(entry) != {"Name"}:
                raise ValueError("Cluster Name entry has fields the editor cannot position")
            continue
        if set(entry) == {"DMA"}:
            records = entry["DMA"]
            if not isinstance(records, list):
                raise ValueError("DMA entry must be a list")
            for fields in records:
                if not isinstance(fields, dict):
                    raise ValueError("DMA fields must be a mapping")
                components.append({
                    "type": "dma", "fields": deepcopy(fields),
                    "name": fields.get("Name", ""), "dma_type": fields.get("Type", "NonCoherent"),
                    "max_req_size": fields.get("MaxReqSize", 128),
                    "buffer_size": fields.get("BufferSize", 256),
                    "pio_master": fields.get("PIOMaster", "LocalBus"),
                    "interrupt_num": fields.get("InterruptNum"),
                })
            continue
        if set(entry) == {"Accelerator"}:
            records = entry["Accelerator"]
            if not isinstance(records, list):
                raise ValueError("Accelerator entry must be a list")
            scalar = {}
            memory = []
            for fields in records:
                if not isinstance(fields, dict):
                    raise ValueError("Accelerator field must be a mapping")
                if "Var" in fields:
                    if set(fields) != {"Var"} or not isinstance(fields["Var"], list):
                        raise ValueError("Var field must contain a list only")
                    memory.extend(fields["Var"])
                else:
                    overlap = set(scalar) & set(fields)
                    if overlap:
                        raise ValueError("Duplicate accelerator fields: " + ",".join(sorted(overlap)))
                    scalar.update(fields)
            if not isinstance(scalar.get("Name"), str):
                raise ValueError("Accelerator needs a Name")
            accelerator = {
                "type": "accelerator", "fields": deepcopy(scalar),
                "name": scalar["Name"], "ir_path": scalar.get("IrPath", ""),
                "pio_size": scalar.get("PIOSize", 1),
                "pio_master": scalar.get("PIOMaster", "LocalBus"),
                "local_slaves": scalar.get("LocalSlaves", ""),
                "config_path": scalar.get("ConfigPath", ""),
                "interrupt_num": scalar.get("InterruptNum"),
                "debug": scalar.get("Debug", False),
            }
            components.append(accelerator)
            for fields in memory:
                if not isinstance(fields, dict):
                    raise ValueError("Var record must be a mapping")
                components.append({
                    "type": "memory", "owner": scalar["Name"], "fields": deepcopy(fields),
                    "name": fields.get("Name", ""), "memory_type": fields.get("Type", "SPM"),
                    "size": fields.get("Size", 1), "ports": fields.get("Ports"),
                    "connections": fields.get("Connections", ""),
                    "ready_mode": fields.get("ReadyMode"),
                    "reset_on_read": fields.get("ResetOnRead"),
                    "read_on_invalid": fields.get("ReadOnInvalid"),
                    "write_on_valid": fields.get("WriteOnValid"),
                })
            continue
        raise ValueError("Cluster entry has unsupported shape")
    return names[0], components


def _integer(value, field, *, positive=False, optional=False):
    if optional and value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(field + " must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(field + " must be an integer")
    if parsed < (1 if positive else 0) or parsed > 0xFFFFFFFF:
        raise ValueError(field + " is outside UInt32 range")
    return parsed


def _identifier(value, field):
    if not isinstance(value, str) or not _IDENT.fullmatch(value):
        raise ValueError(field + " must be a Python-safe identifier")
    return value


def _update_optional(fields, name, value):
    if value not in (None, ""):
        fields[name] = value
    else:
        fields.pop(name, None)


def _render_components(snapshot):
    components = snapshot.get("components")
    if not isinstance(components, list):
        raise ValueError("GUI components must be a list")
    cluster_name = _identifier(snapshot.get("cluster_name"), "cluster name")
    rendered = [{"Name": cluster_name}]
    accelerators = {}
    pending_memories = []
    seen_names = set()
    for item in components:
        if not isinstance(item, dict) or item.get("type") not in _COMPONENT_KEYS:
            raise ValueError("Unknown GUI component")
        kind = item["type"]
        fields = deepcopy(item.get("fields", {}))
        if not isinstance(fields, dict):
            raise ValueError("GUI component raw fields must be a mapping")
        name = _identifier(item.get("name"), "component name")
        if name.lower() in seen_names:
            raise ValueError("Duplicate GUI component name: " + name)
        seen_names.add(name.lower())
        fields["Name"] = name
        if kind == "dma":
            fields["Type"] = item.get("dma_type", "NonCoherent")
            fields["MaxReqSize"] = _integer(item.get("max_req_size"), "DMA MaxReqSize", positive=True)
            fields["BufferSize"] = _integer(item.get("buffer_size"), "DMA BufferSize", positive=True)
            _update_optional(fields, "PIOMaster", item.get("pio_master"))
            value = _integer(item.get("interrupt_num"), "DMA InterruptNum", optional=True)
            _update_optional(fields, "InterruptNum", value)
            rendered.append({"DMA": [fields]})
        elif kind == "accelerator":
            fields["IrPath"] = item.get("ir_path")
            fields["PIOSize"] = _integer(item.get("pio_size"), "Accelerator PIOSize", positive=True)
            _update_optional(fields, "PIOMaster", item.get("pio_master"))
            _update_optional(fields, "LocalSlaves", item.get("local_slaves"))
            _update_optional(fields, "ConfigPath", item.get("config_path"))
            value = _integer(item.get("interrupt_num"), "Accelerator InterruptNum", optional=True)
            _update_optional(fields, "InterruptNum", value)
            fields["Debug"] = bool(item.get("debug", False))
            entry = {"Accelerator": [fields]}
            rendered.append(entry)
            accelerators[name] = entry
        else:
            fields["Type"] = item.get("memory_type", "SPM")
            fields["Size"] = _integer(item.get("size"), "Memory Size", positive=True)
            ports = _integer(item.get("ports"), "Memory Ports", positive=True, optional=True)
            _update_optional(fields, "Ports", ports)
            _update_optional(fields, "Connections", item.get("connections"))
            for key, value in (
                    ("ReadyMode", item.get("ready_mode")),
                    ("ResetOnRead", item.get("reset_on_read")),
                    ("ReadOnInvalid", item.get("read_on_invalid")),
                    ("WriteOnValid", item.get("write_on_valid"))):
                if value is not None:
                    fields[key] = bool(value)
            pending_memories.append((item.get("owner"), fields))
    for owner, fields in pending_memories:
        if owner not in accelerators:
            raise ValueError("Memory owner accelerator is missing: " + str(owner))
        accelerators[owner]["Accelerator"].append({"Var": [fields]})
    if not accelerators:
        raise ValueError("GUI topology needs at least one accelerator")
    return rendered


def _profile_and_global(document, snapshot):
    profile = snapshot.get("hardware_profile")
    if not isinstance(profile, dict) or set(profile) - {"model", "period", "profile", "fu_overrides"}:
        raise ValueError("Invalid GUI hardware profile")
    for key in ("model", "period", "profile"):
        if not isinstance(profile.get(key), str) or not _PROFILE_TOKEN.fullmatch(profile[key]):
            raise ValueError("Hardware profile " + key + " is required")
    overrides = profile.get("fu_overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("FU model overrides must be a mapping")
    normalized = {}
    for fu, fields in overrides.items():
        _identifier(fu, "FU model name")
        if not isinstance(fields, dict) or set(fields) - (
                set(MODEL_FLOAT_FIELDS) | set(MODEL_INT_FIELDS)):
            raise ValueError("Unsupported FU model coefficient")
        values = {}
        for field, value in fields.items():
            if value in (None, ""):
                continue
            if field in MODEL_INT_FIELDS:
                values[field] = _integer(value, field, positive=True)
            else:
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    raise ValueError("Invalid FU model coefficient " + field)
                if not math.isfinite(number) or number < 0:
                    raise ValueError("Invalid FU model coefficient " + field)
                values[field] = number
        if values:
            normalized[fu] = values
    profile = deepcopy(profile)
    profile["fu_overrides"] = normalized
    global_config = document.pop("global", None)
    if global_config is not None:
        if not isinstance(global_config, dict) or set(global_config) != {"memory"}:
            raise ValueError("GUI global metadata has unhandled fields")
        memory = global_config["memory"]
        if not isinstance(memory, dict) or set(memory) - {"base_address", "alignment"}:
            raise ValueError("GUI global memory has unhandled fields")
    hardware = document.get("hw_config", {})
    if not isinstance(hardware, dict):
        raise ValueError("hw_config must be a mapping")
    for key, settings in hardware.items():
        if key == "name" or settings is None:
            continue
        if not isinstance(settings, dict):
            raise ValueError("hw_config." + str(key) + " must be a mapping")
        # Legacy GUI cycle_time never reached the generated model. The live
        # profile selection is explicit and the source bytes remain hashed.
        settings.pop("cycle_time", None)
    return {key: deepcopy(value) for key, value in profile.items()}


def _render_hardware(document, snapshot, *, allow_fu_capacity=False):
    edits = snapshot.get("hardware_by_accelerator")
    if edits is None:
        target = snapshot.get("hardware_target")
        edits = ({target: {"functional_units": snapshot.get("functional_units", {}),
                           "instructions": snapshot.get("instructions", {})}}
                 if target is not None else {})
    if not isinstance(edits, dict):
        raise ValueError("Per-accelerator hardware rows must be a mapping")
    accelerator_names = {item["Name"].lower() for entry in document["acc_cluster"]
                         for item in entry.get("Accelerator", []) if "Name" in item}
    hardware = document.setdefault("hw_config", {})
    if not isinstance(hardware, dict):
        raise ValueError("hw_config must be a mapping")
    for target, tables in edits.items():
        _identifier(target, "hardware target")
        if target.lower() not in accelerator_names:
            raise ValueError("Hardware target is not an accelerator")
        if not isinstance(tables, dict) or set(tables) - {"functional_units", "instructions"}:
            raise ValueError("Unknown per-accelerator hardware rows")
        if not tables.get("functional_units") and not tables.get("instructions"):
            continue
        key = next((name for name in hardware
                    if isinstance(name, str) and name.lower() == target.lower()), target.lower())
        settings = hardware.get(key)
        if settings is None:
            settings = {}
            hardware[key] = settings
        if not isinstance(settings, dict):
            raise ValueError("Hardware target settings must be a mapping")
        for kind in ("functional_units", "instructions"):
            requested = tables.get(kind, {})
            if not isinstance(requested, dict):
                raise ValueError(kind + " rows must be a mapping")
            current = settings.setdefault(kind, {})
            if not isinstance(current, dict):
                raise ValueError(kind + " source must be a mapping")
            for name, values in requested.items():
                if not isinstance(values, dict):
                    raise ValueError(kind + " row must be a mapping")
                if kind == "functional_units":
                    _identifier(name, "functional unit")
                    cycles = _integer(values.get("cycles"), "FU cycles")
                    limit = _integer(values.get("limit"), "FU limit")
                    if limit and not allow_fu_capacity:
                        raise ValueError("Nonzero FU limits require the source-verified FU scheduler")
                    current.setdefault(name, {}).update({"cycles": cycles, "limit": limit})
                else:
                    _identifier(name, "instruction")
                    runtime = _integer(values.get("runtime_cycles"), "instruction runtime_cycles")
                    fu = values.get("functional_unit")
                    if isinstance(fu, str) and fu.isdecimal():
                        fu = int(fu)
                    if not isinstance(fu, (str, int)) or isinstance(fu, bool):
                        raise ValueError("Invalid instruction functional_unit")
                    current.setdefault(name, {}).update(
                        {"runtime_cycles": runtime, "functional_unit": fu})

def render_document(base_document, snapshot, *, allow_fu_capacity=False):
    """Create consumer YAML from a loaded base plus exact edited widget values."""
    if not isinstance(base_document, dict) or not isinstance(snapshot, dict):
        raise ValueError("GUI requires a loaded YAML document and widget snapshot")
    document = deepcopy(base_document)
    document["acc_cluster"] = _render_components(snapshot)
    _profile_and_global(document, snapshot)
    _render_hardware(document, snapshot, allow_fu_capacity=allow_fu_capacity)
    return document


def build_gui_request(base_document, snapshot, *, benchmark, engine_root, distro,
                      source_config_relative, source_config_sha256,
                      capability_source_root=None):
    """Build immutable JSON-ready request for gui_execution.apply_request."""
    if not isinstance(benchmark, str) or not re.fullmatch(
            r"benchmarks/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", benchmark):
        raise ValueError("Invalid selected benchmark")
    if not isinstance(source_config_relative, str) or not _SAFE_RELATIVE.fullmatch(
            source_config_relative) or any(part in ("", ".", "..") for part in
                                           source_config_relative.split("/")):
        raise ValueError("Invalid source config path")
    if source_config_relative not in (benchmark + "/config.yml",
                                      benchmark + "/config.yaml"):
        raise ValueError("Source config is not selected benchmark YAML")
    if not isinstance(source_config_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", source_config_sha256):
        raise ValueError("Invalid source config hash")
    if snapshot.get("alignment") != 64:
        raise ValueError("Current generator implements fixed 64-byte alignment")
    base_address = snapshot.get("base_address")
    if not isinstance(base_address, str):
        raise ValueError("Base address must be text")
    try:
        address = int(base_address, 0)
    except ValueError:
        raise ValueError("Invalid accelerator base address")
    if address % 64 or not 0x10020000 <= address < 0x14000000:
        raise ValueError("Base address outside aligned ARM accelerator aperture")
    system = snapshot.get("system")
    if not isinstance(system, dict):
        raise ValueError("GUI system settings must be a mapping")
    allowed_system = {"mem-size", "mem-type", "cpu-clock", "sys-clock"}
    if set(system) - allowed_system:
        raise ValueError("Unsupported GUI system setting")
    system = {key: value for key, value in system.items() if value not in (None, "")}
    from .fu_capability import inspect_fu_capability
    local_source = (capability_source_root if capability_source_root is not None
                    else engine_root)
    allow_fu_capacity = inspect_fu_capability(local_source)["supported"]
    document = render_document(base_document, snapshot,
                               allow_fu_capacity=allow_fu_capacity)
    profile = _profile_and_global(deepcopy(base_document), snapshot)
    from .hardware_codegen import _normalize_profile_overrides
    profile["fu_overrides"] = _normalize_profile_overrides(
        profile["fu_overrides"], allow_fu_limit=allow_fu_capacity)
    return {
        "schema_version": 2, "action": "apply_and_run",
        "benchmark": benchmark, "engine_root": str(engine_root), "distro": distro,
        "configuration_documents": [document], "system": system,
        "parameters": {}, "base_address": base_address,
        "hardware_profile": profile,
        "provenance": {
            "source_config": {"relative_path": source_config_relative,
                              "sha256": source_config_sha256},
            "editor_snapshot": deepcopy(snapshot),
            "editor_conversion": "live_widgets_plus_preserved_loaded_fields",
        },
    }
