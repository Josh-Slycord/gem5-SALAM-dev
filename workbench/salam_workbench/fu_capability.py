"""Fail-closed, source and build bound FU scheduling capability checks.

The marker is source-only. A successful configured build receipt separately
binds that source tree to the actual gem5.opt binary, avoiding hash cycles.
"""
import hashlib
import json
from pathlib import Path
import re


MARKER = "src/hwacc/workbench_fu_capability.json"
SCHEDULER_HEADER = "src/hwacc/fu_scheduling_pool.hh"
SCHEDULER_CONSUMER = "src/hwacc/llvm_interface.cc"
FEATURE = "salam_fu_scheduler_v1"
REQUIRED_SOURCE_FILES = (
    SCHEDULER_HEADER,
    SCHEDULER_CONSUMER,
    "src/hwacc/llvm_interface.hh",
    "src/hwacc/HWModeling/generated/instructions/base.hh",
    "src/hwacc/HWModeling/generated/functionalunits/base.hh",
    "src/hwacc/HWModeling/src/functional_units.cc",
    "SALAMClassGenerator.py",
)
_HASH = re.compile(r"^[0-9a-f]{64}$")
_SAFE_PART = re.compile(r"^[A-Za-z0-9._-]+$")
_UNIT_SECTION = re.compile(
    r"^system\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*"
    r"\.hw_interface\.functional_units\.[A-Za-z_][A-Za-z0-9_]*$")


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(value):
    if not isinstance(value, str) or "\\" in value or value.startswith("/"):
        raise ValueError("Capability source path must be relative")
    parts = value.split("/")
    if (not parts or any(not part or part in (".", "..") or
                         not _SAFE_PART.fullmatch(part) for part in parts)):
        raise ValueError("Capability source path is unsafe")
    if value != "SALAMClassGenerator.py" and not value.startswith("src/hwacc/"):
        raise ValueError("Capability source path is outside scheduler inputs")
    return Path(*parts)


def capability_source_paths(engine_root):
    """Return exact absolute source inputs to stage, empty on legacy engines."""
    engine = Path(engine_root).resolve(strict=True)
    marker = engine / MARKER
    if not marker.is_file():
        return []
    data = json.loads(marker.read_text(encoding="utf-8"))
    sources = data.get("source_files")
    if not isinstance(sources, dict) or not set(REQUIRED_SOURCE_FILES) <= set(sources):
        raise ValueError("FU capability manifest omits required source files")
    paths = [marker]
    for name in sorted(sources):
        relative = _relative(name)
        path = engine / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("FU capability source missing or symlinked: " + name)
        path.resolve(strict=True).relative_to(engine)
        paths.append(path)
    return paths


def inspect_fu_capability(engine_root, build_receipt=None):
    """Return support only for an exact source marker and optional verified build."""
    result = {"schema_version": 1, "feature": FEATURE, "supported": False,
              "engine": str(engine_root), "sources": {}, "build_verified": False,
              "reason": None}
    try:
        engine = Path(engine_root).resolve(strict=True)
        result["engine"] = str(engine)
        marker = engine / MARKER
        if not marker.is_file():
            result["reason"] = "No FU scheduler capability marker in this engine"
            return result
        data = json.loads(marker.read_text(encoding="utf-8"))
        expected = {
            "schema_version": 1,
            "capability": FEATURE,
            "scope": "scalar_compute",
            "semantics": "nonpipelined_issue_to_completion",
            "zero_limit": "unlimited",
        }
        for key, value in expected.items():
            if data.get(key) != value:
                raise ValueError("FU capability manifest field mismatch: " + key)
        if set(data) != set(expected) | {"source_files"}:
            raise ValueError("FU capability manifest has unrecognized fields")
        files = data.get("source_files")
        if not isinstance(files, dict) or not set(REQUIRED_SOURCE_FILES) <= set(files):
            raise ValueError("FU capability manifest omits required source files")
        for name, recorded in sorted(files.items()):
            relative = _relative(name)
            if not isinstance(recorded, str) or not _HASH.fullmatch(recorded):
                raise ValueError("Invalid FU capability source SHA: " + name)
            path = engine / relative
            if path.is_symlink() or not path.is_file():
                raise ValueError("FU capability source missing or symlinked: " + name)
            path.resolve(strict=True).relative_to(engine)
            actual = _sha(path)
            if actual != recorded:
                raise ValueError("FU capability source changed: " + name)
            result["sources"][name] = actual
        for name in (SCHEDULER_HEADER, SCHEDULER_CONSUMER):
            if "SALAM_FU_SCHEDULER_V1" not in (engine / name).read_text(encoding="utf-8"):
                raise ValueError("FU scheduler consumer marker absent: " + name)
        result["sources"][MARKER] = _sha(marker)
        if build_receipt is not None:
            from .configurator import verify_engine
            result["build"] = verify_engine(engine, build_receipt)
            result["build_verified"] = True
        result["supported"] = True
    except Exception as error:
        result["reason"] = type(error).__name__ + ": " + str(error)
    return result


def _uint(value, label):
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(label + " must be a UInt32")
    return value


def validate_limit_parameters(engine_root, parameters, build_receipt=None):
    """Reject unsupported explicit limit parameters before generation or run."""
    if not isinstance(parameters, dict):
        raise ValueError("Simulator parameters must be a mapping")
    requested = []
    for section, fields in parameters.items():
        if not isinstance(section, str) or not isinstance(fields, dict):
            raise ValueError("Simulator parameter section must be a mapping")
        for field, raw in fields.items():
            if field not in ("limit", "functional_unit_limit"):
                continue
            value = _uint(raw, section + "." + str(field))
            if not value:
                continue
            if field == "functional_unit_limit":
                raise ValueError("Per-instruction functional_unit_limit is not consumed by the FU scheduler")
            if not _UNIT_SECTION.fullmatch(section):
                if ".hw_interface." in section:
                    raise ValueError("Nonzero FU limit has no supported consumer at " + section)
                continue
            requested.append({"section": section, "field": field, "value": value})
    capability = inspect_fu_capability(engine_root, build_receipt) if requested else None
    if requested and not capability["supported"]:
        raise ValueError("Nonzero FU limits require a verified FU scheduler: " +
                         capability["reason"])
    return {"state": "passed", "requested": requested,
            "capability": capability}


def requested_fu_capacity(documents, profile_overrides=None):
    """List nonzero FU capacities requested by inline YAML or profile edits."""
    found = []
    for index, document in enumerate(documents or []):
        if not isinstance(document, dict):
            continue
        hardware = document.get("hw_config", {})
        if not isinstance(hardware, dict):
            continue
        for accelerator, settings in hardware.items():
            if not isinstance(settings, dict):
                continue
            units = settings.get("functional_units", {})
            if not isinstance(units, dict):
                continue
            for unit, values in units.items():
                if isinstance(values, dict) and type(values.get("limit")) is int and values["limit"] > 0:
                    found.append({"path": "documents[{}].hw_config.{}.functional_units.{}.limit".format(
                        index, accelerator, unit), "value": values["limit"]})
    for unit, values in (profile_overrides or {}).items():
        if isinstance(values, dict) and type(values.get("limit")) is int and values["limit"] > 0:
            found.append({"path": "hardware_profile.fu_overrides.{}.limit".format(unit),
                          "value": values["limit"]})
    return found
