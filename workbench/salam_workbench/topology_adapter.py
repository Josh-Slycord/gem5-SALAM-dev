"""Staged, source-bound support for per-accelerator YAML ConfigPath.

The engine's parser currently ignores ConfigPath. This adapter inspects the
edited staged benchmark YAML, copies referenced profile YAML inputs into the
staged workspace, and patches only its copied parser. The source engine is
never modified. Legacy .ini references remain unsupported because AccConfig
loads hardware settings from YAML.
"""
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil

import yaml


PARSER = Path("SALAM-Configurator/parser.py")
_VERSION = '__version__ = "3.0.0.pre[1.0.0]"'
_IGNORED = (
    "                # if 'ConfigPath' in deviceDict:\n"
    "                #     configPath = deviceDict['ConfigPath']"
)
_ACTIVE = (
    '                if "ConfigPath" in deviceDict:\n'
    '                    configPath = _workbench_config_path(M5_Path, deviceDict["ConfigPath"])'
)
_HELPER = '''
from pathlib import Path
import re

CONFIGPATH_CONSUMER_VERSION = 1

def _workbench_config_path(root, raw):
    if not isinstance(raw, str) or not re.fullmatch(r"[A-Za-z0-9._/-]+", raw):
        raise ValueError("ConfigPath must be a portable relative path")
    parts = raw.split("/")
    if (parts[0] not in ("benchmarks", "configs") or len(parts) < (3 if parts[0] == "benchmarks" else 2) or any(
            part in ("", ".", "..") for part in parts)):
        raise ValueError("ConfigPath must stay below benchmarks or configs")
    if Path(raw).suffix.lower() not in (".yml", ".yaml"):
        raise ValueError("ConfigPath must identify YAML hardware configuration")
    base = Path(root).resolve(strict=True)
    path = (base / raw).resolve(strict=True)
    path.relative_to(base)
    if not path.is_file():
        raise ValueError("ConfigPath is not a regular file")
    return str(path)

'''


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(raw, suffixes):
    if not isinstance(raw, str) or not re.fullmatch(r"[A-Za-z0-9._/-]+", raw):
        raise ValueError("Expected portable relative path")
    parts = raw.split("/")
    if (parts[0] not in ("benchmarks", "configs") or len(parts) < (3 if parts[0] == "benchmarks" else 2) or any(
            part in ("", ".", "..") for part in parts)):
        raise ValueError("Path must stay below benchmarks or configs")
    path = Path(raw)
    if path.suffix.lower() not in suffixes:
        raise ValueError("Unexpected path extension: " + raw)
    return path


def _contained_file(root, relative):
    candidate = root / relative
    resolved = candidate.resolve(strict=True)
    resolved.relative_to(root)
    if resolved != candidate or not candidate.is_file():
        raise ValueError("Referenced file must be regular, not symlinked: " + str(relative))
    return candidate


def _save(path, record):
    if path is not None:
        Path(path).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8")


def _bindings(config_file):
    documents = list(yaml.safe_load_all(config_file.read_text(encoding="utf-8")))
    bindings = []
    for di, document in enumerate(documents):
        if not isinstance(document, dict):
            raise ValueError("Configuration document must be a mapping")
        entries = document.get("acc_cluster", [])
        if not isinstance(entries, list):
            raise ValueError("acc_cluster must be a list")
        for ei, entry in enumerate(entries):
            if not isinstance(entry, dict) or "Accelerator" not in entry:
                continue
            fields = entry["Accelerator"]
            if not isinstance(fields, list) or any(not isinstance(item, dict) for item in fields):
                raise ValueError("Accelerator fields must be a list of mappings")
            config_paths = [item["ConfigPath"] for item in fields if "ConfigPath" in item]
            if not config_paths:
                continue
            ir_paths = [item["IrPath"] for item in fields if "IrPath" in item]
            names = [item["Name"] for item in fields if "Name" in item]
            if len(config_paths) != 1 or len(ir_paths) != 1 or len(names) != 1:
                raise ValueError("ConfigPath accelerator needs exactly one Name, IrPath, and ConfigPath")
            ir = _safe_relative(ir_paths[0], {".ll"})
            profile = _safe_relative(config_paths[0], {".yml", ".yaml"})
            bindings.append({"document": di, "entry": ei, "accelerator": names[0],
                             "ir_path": ir.as_posix(), "ir_stem": ir.stem,
                             "config_path": profile.as_posix()})
    return bindings


def _patch_parser(source_parser, staged_parser):
    before_bytes = staged_parser.read_bytes()
    if before_bytes != source_parser.read_bytes():
        raise ValueError("Staged parser differs from source before ConfigPath patch")
    before = before_bytes.decode("utf-8")
    newline = "\r\n" if "\r\n" in before else "\n"
    version = _VERSION + newline
    ignored = _IGNORED.replace("\n", newline)
    active = _ACTIVE.replace("\n", newline)
    if before.count(version) != 1 or before.count(ignored) != 1:
        raise ValueError("Parser patch anchors changed; refusing ConfigPath support")
    helper = _HELPER.strip("\n").replace("\n", newline) + newline + newline
    after = before.replace(version, version + newline + helper, 1)
    after = after.replace(ignored, active, 1)
    compile(after, str(staged_parser), "exec")
    staged_parser.write_bytes(after.encode("utf-8"))
    return {"source_path": str(source_parser), "staged_path": str(staged_parser),
            "before_sha256": hashlib.sha256(before_bytes).hexdigest(),
            "after_sha256": _sha(staged_parser),
            "unified_diff": "".join(difflib.unified_diff(
                before.splitlines(True), after.splitlines(True),
                fromfile="source/SALAM-Configurator/parser.py",
                tofile="staged/SALAM-Configurator/parser.py"))}


def adapt_staged_configpaths(source_engine, workspace, benchmark_relative, *,
                             receipt_path=None, source_config_relative=None):
    """Copy and validate per-accelerator YAML profiles, then patch staged parser.

    Call after edits to staged benchmark/config.yml and before configuration
    contract/generation. Returns a receipt; optional receipt_path persists it.
    An exception leaves the original engine untouched and persists a failed
    receipt when receipt_path is supplied.
    """
    engine = Path(source_engine).resolve(strict=True)
    stage = Path(workspace).resolve(strict=True)
    if engine == stage or engine in stage.parents or stage in engine.parents:
        raise ValueError("ConfigPath adaptation requires an independent staged workspace")
    benchmark = _safe_relative(str(benchmark_relative).replace("\\", "/") + "/config.yml",
                               {".yml"})
    config_file = _contained_file(stage, benchmark)
    source_config_raw = source_config_relative or benchmark.as_posix()
    if (not isinstance(source_config_raw, str) or
            not re.fullmatch(r"[A-Za-z0-9._/-]+", source_config_raw) or
            any(part in ("", ".", "..") for part in source_config_raw.split("/")) or
            Path(source_config_raw).suffix.lower() not in (".yml", ".yaml")):
        raise ValueError("source_config_relative must be an engine-relative YAML path")
    source_config = Path(source_config_raw)
    record = {"schema_version": 1, "kind": "staged_configpath_adapter",
              "state": "planned", "source_engine": str(engine), "workspace": str(stage),
              "config_path": str(config_file), "config_sha256": _sha(config_file),
              "source_config_path": str(engine / source_config),
              "bindings": [], "referenced_inputs": [], "parser": None, "errors": []}
    _save(receipt_path, record)
    try:
        bindings = _bindings(config_file)
        if not bindings:
            record["state"] = "not_required"
            return record
        source_parser = _contained_file(engine, PARSER)
        staged_parser = _contained_file(stage, PARSER)
        if staged_parser.read_bytes() != source_parser.read_bytes():
            raise ValueError("Staged parser changed before ConfigPath adaptation")

        # Validate every referenced profile before copying or patching anything.
        files = {}
        for binding in bindings:
            relative = Path(binding["config_path"])
            original = _contained_file(engine, source_config if relative == benchmark else relative)
            staged = stage / relative
            if staged.exists():
                if staged.is_symlink() or staged.resolve() != staged or not staged.is_file():
                    raise ValueError("Staged ConfigPath target is not a regular file")
            elif staged.parent.resolve() != staged.parent:
                raise ValueError("Staged ConfigPath parent is symlinked")
            if relative == benchmark:
                profile_file = config_file  # Keep explicit edits in the staged main YAML.
            elif staged.exists():
                if _sha(staged) != _sha(original):
                    raise ValueError("Existing staged ConfigPath file differs from source")
                profile_file = staged
            else:
                profile_file = original
            profile_docs = list(yaml.safe_load_all(profile_file.read_text(encoding="utf-8")))
            if len(profile_docs) != 1 or not isinstance(profile_docs[0], dict):
                raise ValueError("ConfigPath requires one YAML mapping document")
            hardware = profile_docs[0].get("hw_config")
            selected = hardware.get(binding["ir_stem"]) if isinstance(hardware, dict) else None
            if not isinstance(selected, dict) or not selected:
                raise ValueError("ConfigPath lacks hw_config for IR stem: " + binding["ir_stem"])
            binding["source_path"] = str(original)
            binding["source_sha256"] = _sha(original)
            binding["staged_path"] = str(staged)
            binding["expected_staged_sha256"] = _sha(profile_file)
            files[relative] = (original, staged)
        record["bindings"] = bindings

        for relative, (original, staged) in sorted(files.items()):
            if relative != benchmark and not staged.exists():
                staged.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(original), str(staged))
            expected = next(b["expected_staged_sha256"] for b in bindings
                            if b["config_path"] == relative.as_posix())
            if _sha(staged) != expected:
                raise ValueError("Staged ConfigPath bytes changed during copy")
            record["referenced_inputs"].append({
                "path": str(original), "sha256": _sha(original),
                "staged": str(staged), "staged_sha256": _sha(staged),
                "relative_path": relative.as_posix()})
        record["parser"] = _patch_parser(source_parser, staged_parser)
        record["state"] = "patched"
        return record
    except Exception as error:
        record["state"] = "failed"
        record["errors"].append(type(error).__name__ + ": " + str(error))
        raise
    finally:
        _save(receipt_path, record)