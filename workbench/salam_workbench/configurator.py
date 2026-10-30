"""Configuration-driven SALAM generation, build and simulation with receipts.

The legacy fixed regression commands remain independent. This pipeline accepts
benchmark source, YAML edits, gem5 system options and compiled scalar parameters.
"""
import argparse
import ast
import configparser
import hashlib
import json
import math
import re
import shutil
import sys
import uuid
from pathlib import Path

import yaml

from .regression import _command, _environment, _now, _save
from .report import parse_stats
from .runner import EXPECTED_EXIT_REASON, file_hash, run_experiment

PROJECT = Path(__file__).resolve().parents[1]
PYTHON = "/usr/bin/python3.8"
BUILD_DIRS = ("src", "ext", "build_opts", "site_scons")
OMIT_DIRS = {".git", "__pycache__", "build", "m5out", "outputs"}
OMIT_SUFFIXES = {".o", ".elf", ".ll", ".pyc", ".a", ".so"}
SYSTEM_DEFAULTS = {
    "mem-size": "4GB",
    "mem-type": "DDR4_2400_8x8",
    "machine-type": "VExpress_GEM5_V1",
    "dtb-file": "none",
    "bare-metal": True,
    "cpu-type": "DerivO3CPU",
    "caches": True,
    "l2cache": True,
}
RESERVED_OPTIONS = {
    "kernel",
    "disk-image",
    "accpath",
    "accbench",
    "outdir",
    "command-line-file",
    "script",
    "restore-with-cpu",
    "checkpoint-dir",
}


def _relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("Expected portable relative path")
    path = Path(value)
    if path.is_absolute() or any(p in ("", ".", "..") for p in value.split("/")):
        raise ValueError("Expected path within the engine")
    return path


def validate_spec(data):
    allowed = {
        "schema_version",
        "name",
        "benchmark",
        "config",
        "base_address",
        "edits",
        "system",
        "parameters",
        "accelerator_cache",
        "correctness",
        "timeout_seconds",
        "import_format",
        "configuration_documents",
        "benchmark_input",
    }
    if (
        not isinstance(data, dict)
        or set(data) - allowed
        or data.get("schema_version") != 1
    ):
        raise ValueError("Unsupported configuration specification or unknown fields")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", data.get("name", "")):
        raise ValueError("name must be a Python identifier")
    benchmark = _relative(data.get("benchmark"))
    if "benchmark_input" in data:
        from .benchmark_validation import validate_input_case

        validate_input_case(data["benchmark"], data["benchmark_input"])
    if data.get("import_format") not in (None, "legacy_gui"):
        raise ValueError("Unsupported configuration import format")
    if "configuration_documents" in data:
        docs = data["configuration_documents"]
        if (
            not isinstance(docs, list)
            or not docs
            or any(not isinstance(d, dict) for d in docs)
        ):
            raise ValueError("configuration_documents requires YAML mapping documents")
        json.dumps(docs, allow_nan=False)
    if benchmark.parts[0] != "benchmarks" or len(benchmark.parts) < 3:
        raise ValueError("benchmark must be below benchmarks/<suite>/<workload>")
    _relative(data.get("config", str(benchmark / "config.yml")))
    base = data.get("base_address", "0x10020000")
    base = int(base, 0) if isinstance(base, str) else base
    if type(base) is not int or base % 64 or not 0x10020000 <= base < 0x14000000:
        raise ValueError(
            "Base address must be 64-byte aligned in the ARM SALAM aperture"
        )
    for option, value in data.get("system", {}).items():
        if (
            not re.fullmatch(r"[a-z][a-z0-9_-]*", option)
            or option.replace("_", "-") in RESERVED_OPTIONS
        ):
            raise ValueError("Reserved or malformed system option: " + option)
        if (
            type(value) not in (str, int, float, bool)
            or isinstance(value, float)
            and not math.isfinite(value)
        ):
            raise ValueError("System option must be a finite scalar")
    for section, fields in data.get("parameters", {}).items():
        if not re.fullmatch(
            r"system(?:\.[A-Za-z][A-Za-z0-9_]*)*", section
        ) or not isinstance(fields, dict):
            raise ValueError("Invalid SimObject parameter section")
        for name, value in fields.items():
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) or type(value) not in (
                str,
                int,
                float,
                bool,
            ):
                raise ValueError("Parameters must be named scalar values")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Nonfinite parameter")
    cache_keys = {
        "assoc",
        "tag_latency",
        "data_latency",
        "response_latency",
        "mshrs",
        "tgts_per_mshr",
    }
    for key, value in data.get("accelerator_cache", {}).items():
        if key not in cache_keys or type(value) is not int or value <= 0:
            raise ValueError("Unknown or invalid accelerator-cache parameter: " + key)
    for edit in data.get("edits", []):
        if (
            not isinstance(edit, dict)
            or set(edit) != {"path", "value"}
            or not isinstance(edit["path"], list)
            or not edit["path"]
        ):
            raise ValueError(
                "Each YAML edit requires an explicit existing path and value"
            )
    timeout = data.get("timeout_seconds", 600)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Invalid timeout_seconds")
    correctness = data.get("correctness", {})
    if set(correctness) - {
        "expected_passed_markers",
        "description",
        "independent_oracle",
    }:
        raise ValueError("Unknown correctness contract")
    count = correctness.get("expected_passed_markers", 1)
    if type(count) is not int or count < 1:
        raise ValueError("Expected at least one guest correctness marker")
    return data


def apply_edits(documents, edits):
    for edit in edits:
        cursor = documents
        for key in edit["path"][:-1]:
            if isinstance(cursor, list) and type(key) is not int:
                raise ValueError("YAML list path requires integer index")
            cursor = cursor[key]
        key = edit["path"][-1]
        if isinstance(cursor, dict) and key not in cursor:
            raise ValueError(
                "YAML edits cannot silently introduce a misspelled key: " + str(key)
            )
        if isinstance(cursor, list) and type(key) is not int:
            raise ValueError("YAML list path requires integer index")
        cursor[key] = edit["value"]
    return documents


def _record(path):
    return {
        "path": str(path),
        "sha256": file_hash(path),
        "bytes": path.stat().st_size,
    }


def snapshot_pipeline_tooling(directory):
    directory.mkdir(exist_ok=False)
    hashes = {}
    sources = list((PROJECT / "salam_workbench").rglob("*.py"))
    sources.extend(path for path in (PROJECT / "experiments/breadth/overlays").rglob("*")
                   if path.is_file() and path.suffix in (".cpp", ".h"))
    for source in sorted(sources):
        if "__pycache__" in source.parts:
            continue
        relative = source.relative_to(PROJECT)
        destination = directory / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(source), str(destination))
        hashes[relative.as_posix()] = file_hash(destination)
    return hashes


def compiled_identity(engine):
    """Actual simulator build inputs, independent of a Git index or branch name."""
    engine = Path(engine).resolve(strict=True)
    files = []
    for relative in BUILD_DIRS:
        directory = engine / relative
        if directory.is_dir():
            files.extend(
                p
                for p in directory.rglob("*")
                if p.is_file()
                and not set(p.relative_to(directory).parts) & {".git", "__pycache__"}
                and p.suffix not in {".pyc", ".o", ".a", ".so"}
            )
    files.extend(
        p
        for p in engine.iterdir()
        if p.is_file()
        and (p.name.startswith("SConstruct") or p.name.startswith("SConscript"))
    )
    if not (engine / "SConstruct").is_file() or not files:
        raise ValueError("Not a complete simulator source tree")
    hashes = {
        p.relative_to(engine).as_posix(): file_hash(p) for p in sorted(set(files))
    }
    digest = hashlib.sha256(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {"sha256": digest, "files": hashes}


def build_engine(engine, directory, *, jobs=8, timeout=7200):
    engine, directory = (
        Path(engine).resolve(strict=True),
        Path(directory).resolve(),
    )
    directory.mkdir(parents=True, exist_ok=False)
    receipt = {
        "schema_version": 1,
        "kind": "configured_engine_build",
        "state": "running",
        "started_at": _now(),
        "engine": str(engine),
        "errors": [],
    }
    _save(directory / "build.json", receipt)
    try:
        if type(jobs) is not int or not 1 <= jobs <= 32:
            raise ValueError("jobs must be 1..32")
        before = compiled_identity(engine)
        _save(directory / "source-inputs.json", before)
        receipt["toolchain"] = [
            _record(Path(p).resolve(strict=True))
            for p in (
                PYTHON,
                "/usr/bin/scons",
                "/usr/bin/g++",
                "/usr/bin/python3.8-config",
                "/usr/bin/ld",
            )
        ]
        receipt["toolchain_record"] = _record(PROJECT / "evidence/toolchain.json")
        receipt["command"] = _command(
            [
                PYTHON,
                "/usr/bin/scons",
                "build/ARM/gem5.opt",
                "-j" + str(jobs),
                "CXX=/usr/bin/g++",
                "PYTHON_CONFIG=/usr/bin/python3.8-config",
                "USE_KVM=0",
                "PROTOCOL=CHI",
            ],
            engine,
            directory,
            "scons",
            _environment(engine),
            timeout,
        )
        if before != compiled_identity(engine):
            raise ValueError("Simulator sources changed during build")
        if any(file_hash(i["path"]) != i["sha256"] for i in receipt["toolchain"]):
            raise ValueError("Build toolchain changed during compilation")
        receipt.update(
            state="built",
            binary=_record(engine / "build/ARM/gem5.opt"),
            compiled_source_sha256=before["sha256"],
            source_inputs_sha256=file_hash(directory / "source-inputs.json"),
        )
    except Exception as error:
        receipt.update(state="failed")
        receipt["errors"].append(type(error).__name__ + ": " + str(error))
    receipt["finished_at"] = _now()
    _save(directory / "build.json", receipt)
    return receipt


def verify_engine(engine, configured_receipt=None):
    if configured_receipt:
        path = Path(configured_receipt).resolve(strict=True)
        receipt = json.loads(path.read_text())
        if (
            receipt.get("kind") != "configured_engine_build"
            or receipt.get("state") != "built"
        ):
            raise ValueError("Configured simulator has no successful build receipt")
        if receipt["binary"]["sha256"] != file_hash(engine / "build/ARM/gem5.opt"):
            raise ValueError("Configured simulator binary changed")
        if receipt["compiled_source_sha256"] != compiled_identity(engine)["sha256"]:
            raise ValueError("Configured simulator sources changed; rebuild required")
        return {
            "receipt": _record(path),
            "binary": _record(engine / "build/ARM/gem5.opt"),
            "compiled_source_sha256": receipt["compiled_source_sha256"],
        }
    from .builds import verify_receipt
    from .gemm import engine_source_digest

    path, receipt = verify_receipt(PROJECT, engine, engine_source_digest(engine))
    return {
        "receipt": _record(path),
        "binary": _record(engine / "build/ARM/gem5.opt"),
        "engine_source_sha256": receipt["engine_source_sha256"],
    }


def install_hardware_overlay(
    generation_path, target_engine, directory, *, previous_overlay=None
):
    """Apply exact generated bytes only to a separate, matching source copy."""
    generation_path, target = Path(generation_path).resolve(strict=True), Path(
        target_engine
    ).resolve(strict=True)
    record = json.loads(generation_path.read_text())
    source = Path(record["engine_root"]).resolve(strict=True)
    if target == source or source in target.parents or target in source.parents:
        raise ValueError("Hardware overlay requires an independent source copy")
    if not record.get("valid") or record.get("state") != "generated":
        raise ValueError("Hardware generation is not valid")
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    stage = Path(record["staged_engine_root"]).resolve(strict=True)
    result = {
        "state": "planned",
        "generation": _record(generation_path),
        "target_engine": str(target),
        "outputs": [],
        "errors": [],
    }
    _save(directory / "overlay.json", result)
    try:
        prior_outputs = {}
        if previous_overlay:
            previous_path = Path(previous_overlay).resolve(strict=True)
            previous = json.loads(previous_path.read_text())
            if previous.get("state") != "installed_requires_rebuild" or previous.get(
                "target_engine"
            ) != str(target):
                raise ValueError(
                    "Previous overlay is not a successful installation for this engine"
                )
            prior_outputs = {
                i["relative_path"]: i["installed_sha256"] for i in previous["outputs"]
            }
            result["previous_overlay"] = _record(previous_path)
        plan = []
        for item in record["outputs"]:
            relative = _relative(item["relative_path"])
            incoming, destination = stage / relative, target / relative
            incoming.resolve(strict=True).relative_to(stage)
            destination.resolve().relative_to(target)
            if destination.is_symlink() or file_hash(incoming) != item["sha256"]:
                raise ValueError("Unsafe or changed generated output")
            current = file_hash(destination) if destination.is_file() else None
            expected = prior_outputs.get(
                item["relative_path"], item.get("source_engine_sha256")
            )
            if current != expected:
                raise ValueError(
                    "Target engine no longer matches generation base: " + str(relative)
                )
            plan.append((relative, incoming, destination, item))
        for relative, incoming, destination, item in plan:
            installed = dict(item, installed_path=str(destination), state="pending")
            result["outputs"].append(installed)
            if destination.is_file():
                before = directory / "before" / relative
                before.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(destination), str(before))
                installed["before"] = _record(before)
                if file_hash(destination) != installed["before"]["sha256"]:
                    raise ValueError("Target source changed during snapshot")
            _save(directory / "overlay.json", result)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(incoming), str(destination))
            installed.update(installed_sha256=file_hash(destination), state="installed")
            if installed["installed_sha256"] != item["sha256"]:
                raise ValueError("Installed source differs from generation receipt")
            _save(directory / "overlay.json", result)
        result["state"] = "installed_requires_rebuild"
    except Exception as error:
        result["state"] = "failed_partial" if result["outputs"] else "failed_preflight"
        result["errors"].append(type(error).__name__ + ": " + str(error))
    finally:
        _save(directory / "overlay.json", result)
    return result


def stage_configuration(engine, workspace, spec):
    engine, workspace = (
        Path(engine).resolve(strict=True),
        Path(workspace).resolve(),
    )
    if workspace == engine or engine in workspace.parents:
        raise ValueError("Configuration staging must be outside the source engine")
    workspace.mkdir(parents=True, exist_ok=False)
    roots = [
        Path(spec["benchmark"]),
        Path("benchmarks/common"),
        Path("configs"),
        Path("SALAM-Configurator"),
    ]
    files = set()
    for relative in roots:
        for path in (engine / relative).rglob("*"):
            subparts = path.relative_to(engine).parts
            if (
                path.is_file()
                and not set(subparts) & OMIT_DIRS
                and path.suffix not in OMIT_SUFFIXES
            ):
                if relative == Path("configs") and "generated" in subparts:
                    continue
                files.add(path)
    config_source = engine / _relative(
        spec.get("config", spec["benchmark"] + "/config.yml")
    )
    files.add(config_source)
    # The contract examines the actual declarations and C++ consumer too.
    files.update((engine / "src/hwacc").glob("*.py"))
    files.add(engine / "src/hwacc/LLVMRead/src/instruction.hh")
    from .fu_capability import capability_source_paths

    files.update(engine / relative for relative in capability_source_paths(engine))
    inputs = []
    for source in sorted(files):
        source.resolve(strict=True).relative_to(engine)
        destination = workspace / source.relative_to(engine)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(source), str(destination))
        record = dict(_record(source), staged=str(destination))
        if file_hash(destination) != record["sha256"]:
            raise ValueError("Staged input mismatch")
        inputs.append(record)
    config = workspace / spec["benchmark"] / "config.yml"
    if "configuration_documents" in spec:
        docs = json.loads(json.dumps(spec["configuration_documents"], allow_nan=False))
        if spec.get("import_format"):
            raise ValueError("Inline configuration must be normalized before staging")
        _save(
            workspace.parent / "inline-configuration.json",
            {
                "source": "specification.configuration_documents",
                "documents": docs,
            },
        )
    elif spec.get("import_format") == "legacy_gui":
        from .configuration_import import import_configuration

        imported = import_configuration(config_source, engine)
        docs = imported["documents"]
        _save(workspace.parent / "configuration-import.json", imported)
    else:
        from .config_contract import _Loader

        docs = list(yaml.load_all(config_source.read_text(), Loader=_Loader))
    apply_edits(docs, spec.get("edits", []))
    config.write_text(yaml.safe_dump_all(docs, sort_keys=False))
    return {
        "workspace": str(workspace),
        "inputs": inputs,
        "configuration": _record(config),
    }


def inspect_generated(workspace, spec):
    workspace, name = Path(workspace).resolve(), spec["name"]
    generated = workspace / "configs/SALAM/generated"
    module, fs = generated / (name + ".py"), generated / ("fs_" + name + ".py")
    tree = ast.parse(module.read_text())
    fs_tree = ast.parse(fs.read_text())
    imports = [
        a.name for n in ast.walk(fs_tree) if isinstance(n, ast.Import) for a in n.names
    ]
    if imports.count(name) != 1:
        raise ValueError("Generated full-system module has wrong topology import")
    ir, configs = [], []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            key = node.targets[0].id
            if key in ("ir", "config"):
                if not isinstance(node.value, ast.Constant) or not isinstance(
                    node.value.value, str
                ):
                    raise ValueError("Expected literal generated accelerator input")
                path = Path(node.value.value).resolve()
                path.relative_to(workspace)
                (ir if key == "ir" else configs).append(str(path))
    if not ir or len(ir) != len(configs):
        raise ValueError("Generated topology has no complete accelerator bindings")
    config_path = workspace / spec["benchmark"] / "config.yml"
    expected_ir, expected_configs = [], []
    if not config_path.is_file():
        raise ValueError("Requested staged YAML is missing")
    for doc in yaml.safe_load_all(config_path.read_text()):
        for item in doc.get("acc_cluster", []):
            accelerator = {}
            for fields in item.get("Accelerator", []):
                accelerator.update(fields)
            if "IrPath" in accelerator:
                expected_ir.append(
                    str((workspace / _relative(accelerator["IrPath"])).resolve())
                )
                expected_configs.append(
                    str((workspace / _relative(accelerator["ConfigPath"])).resolve())
                    if "ConfigPath" in accelerator
                    else str(config_path)
                )
    if sorted(ir) != sorted(expected_ir):
        raise ValueError("Generated accelerator IR bindings differ from requested YAML")
    if configs != expected_configs:
        raise ValueError(
            "Generated hardware configuration does not bind to requested staged YAML"
        )
    headers = sorted((workspace / spec["benchmark"]).glob("*_hw_defines.h"))
    if not headers:
        raise ValueError("Generator did not produce address headers")
    for header in headers:
        if "//END GENERATED CODE" not in header.read_text():
            raise ValueError("Incomplete generated address header")
    return {
        "state": "generated",
        "ir_bindings": ir,
        "config_bindings": configs,
        "outputs": [_record(p) for p in [module, fs] + headers],
    }


def wire_runtime(workspace, spec, evidence):
    generated = workspace / "configs/SALAM/generated"
    module = generated / (spec["name"] + ".py")
    if spec.get("accelerator_cache"):
        has_cache = False
        for doc in yaml.safe_load_all(
            (workspace / spec["benchmark"] / "config.yml").read_text()
        ):
            for item in doc.get("acc_cluster", []):
                for fields in item.get("Accelerator", []):
                    has_cache = has_cache or any(
                        var.get("Type") == "Cache" for var in fields.get("Var", [])
                    )
        if not has_cache:
            raise ValueError(
                "Accelerator-cache settings have no Cache memory consumer in the requested topology"
            )
        text = module.read_text()
        for key, value in spec["accelerator_cache"].items():
            text, count = re.subn(
                r"(?m)^    " + re.escape(key) + r" = \d+$",
                "    " + key + " = " + str(value),
                text,
            )
            if count != 1:
                raise ValueError("Cache template assignment was not unique: " + key)
        module.write_text(text)
    shutil.copyfile(
        str(PROJECT / "salam_workbench/configurator_runtime.py"),
        str(workspace / "configs/SALAM/workbench_runtime.py"),
    )
    shutil.copyfile(
        str(PROJECT / "salam_workbench/system_witness.py"),
        str(workspace / "configs/SALAM/workbench_system_witness.py"),
    )
    system_options = dict(SYSTEM_DEFAULTS)
    system_options.update(spec.get("system", {}))
    request = evidence / "runtime-request.json"
    _save(
        request,
        {
            "parameters": spec.get("parameters", {}),
            "witness_path": str(evidence / "runtime-applied.json"),
            "system_witness_path": str(evidence / "system-live.json"),
            "system_options": system_options,
            "result_file_transport": "gem5_semihosting_writefile_text_v1" if "benchmark_input" in spec else None,
        },
    )
    fs = generated / ("fs_" + spec["name"] + ".py")
    text = fs.read_text()
    needle = "test_sys = build_test_system(np)"
    if text.count(needle) != 1:
        raise ValueError("Full-system template initialization hook was not unique")
    text = text.replace(
        needle,
        needle
        + "\nfrom workbench_runtime import configure_system\nconfigure_system(test_sys, "
        + repr(str(request))
        + ")",
    )
    ast.parse(text)
    fs.write_text(text)


def simulator_args(engine, workspace, spec):
    options = dict(SYSTEM_DEFAULTS)
    options.update(spec.get("system", {}))
    args = [str(workspace / "configs/SALAM/generated" / ("fs_" + spec["name"] + ".py"))]
    for key, value in sorted(options.items()):
        if value is True:
            args.append("--" + key)
        elif value is not False:
            args.append("--" + key + "=" + str(value))
    args += [
        "--kernel=" + str(workspace / spec["benchmark"] / "sw/main.elf"),
        "--disk-image=" + str(engine / "baremetal/common/fake.iso"),
        "--accpath=" + str((workspace / spec["benchmark"]).parent),
        "--accbench=" + Path(spec["benchmark"]).name,
    ]
    return args


def witness_parameters(config_ini, applied):
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(str(config_ini))
    issues, records = [], []
    for item in applied["parameters"]:
        actual = parser.get(item["section"], item["parameter"], fallback=None)
        matched = actual == str(item["normalized"])
        records.append(dict(item, actual=actual, matched=matched))
        if not matched:
            issues.append(
                "Effective parameter mismatch: "
                + item["section"]
                + "."
                + item["parameter"]
            )
    return {
        "state": "passed" if not issues else "failed",
        "parameters": records,
        "issues": issues,
    }


def witness_layered_contract(contract, config_ini, applied):
    expected = {
        section: dict(values)
        for section, values in contract["expected_effective"].items()
    }
    for item in applied["parameters"]:
        expected.setdefault(item["section"], {})[item["parameter"]] = str(
            item["normalized"]
        )
    fields = [
        {
            "section": section,
            "parameter": key,
            "normalized": str(value).lower() if type(value) is bool else str(value),
        }
        for section, values in expected.items()
        for key, value in values.items()
    ]
    witness = witness_parameters(config_ini, {"parameters": fields})
    witness[
        "precedence"
    ] = "compiled defaults < YAML < explicit SimObject scalar parameters"
    contract["witnesses"]["effective"] = witness
    if witness["state"] != "passed":
        contract["valid"] = False
        contract["issues"].extend(witness["issues"])
    return contract


def inventory_configurations(engine, directory):
    from .config_contract import analyze_configuration

    engine, directory = (
        Path(engine).resolve(strict=True),
        Path(directory).resolve(),
    )
    directory.mkdir(parents=True, exist_ok=False)
    configurations = []
    for config in sorted((engine / "benchmarks").rglob("config.yml")):
        result = analyze_configuration(config, engine)
        configurations.append(
            {
                "path": config.relative_to(engine).as_posix(),
                "sha256": file_hash(config),
                "structurally_supported": result["valid"],
                "issues": result["issues"],
                "clusters": result["components"]["clusters"],
                "required_actions": result["required_actions"],
            }
        )
    profiles = [
        {"path": p.relative_to(engine).as_posix(), "sha256": file_hash(p)}
        for p in sorted((engine / "benchmarks").rglob("*.yml"))
        if "functional_units" in p.parts
    ]
    result = {
        "schema_version": 1,
        "kind": "configuration_inventory",
        "state": "inventoried",
        "configurations": configurations,
        "hardware_profile_sources": profiles,
        "structural_passes": sum(c["structurally_supported"] for c in configurations),
        "simulation_coverage": "Structural inventory only; consult per-run receipts",
    }
    _save(directory / "inventory.json", result)
    return result


def run_configuration(
    engine, spec_path, directory, *, simulate=False, configured_receipt=None
):
    engine, spec_path, directory = (
        Path(engine).resolve(strict=True),
        Path(spec_path).resolve(strict=True),
        Path(directory).resolve(),
    )
    directory.mkdir(parents=True, exist_ok=False)
    result = {
        "schema_version": 1,
        "kind": "configuration_pipeline",
        "state": "running",
        "stage": "specification",
        "started_at": _now(),
        "evidence_directory": str(directory),
        "errors": [],
        "commands": [],
        "simulation_requested": simulate,
        "numerical_correctness": "not_run",
    }
    _save(directory / "configuration.json", result)
    try:
        spec = validate_spec(json.loads(spec_path.read_text(encoding="utf-8-sig")))
        from .fu_capability import inspect_fu_capability, validate_limit_parameters

        validate_limit_parameters(
            engine,
            spec.get("parameters", {}),
            build_receipt=configured_receipt if simulate else None,
        )
        from .config_contract import analyze_configuration
        from .provenance import assert_tooling_unchanged

        result["tooling"] = snapshot_pipeline_tooling(directory / "tooling-snapshot")
        _save(directory / "specification.json", spec)
        result["specification"] = _record(spec_path)
        result["stage"] = "source_staging"
        workspace = directory / "workspace"
        result["staging"] = stage_configuration(engine, workspace, spec)
        from .topology_adapter import adapt_staged_configpaths

        result["configpath_adapter"] = adapt_staged_configpaths(
            engine,
            workspace,
            spec["benchmark"],
            receipt_path=directory / "configpath-adapter.json",
            source_config_relative=spec.get(
                "config", spec["benchmark"] + "/config.yml"
            ),
        )
        result["staging"]["inputs"].extend(
            result["configpath_adapter"]["referenced_inputs"]
        )
        from .registerbank_adapter import adapt_configured_registerbanks

        result["registerbank_adapter"] = adapt_configured_registerbanks(
            workspace, spec["benchmark"], source_engine=engine,
            receipt_path=directory / "registerbank-adapter.json",
        )
        config = workspace / spec["benchmark"] / "config.yml"
        contract = analyze_configuration(
            config,
            workspace,
            base_address=int(str(spec.get("base_address", "0x10020000")), 0),
        )
        _save(directory / "contract-prebuild.json", contract)
        if not contract["valid"]:
            raise ValueError(
                "Configuration contract rejected: " + repr(contract["issues"])
            )
        result["required_actions"] = contract["required_actions"]
        result["stage"] = "topology_generation"
        base = spec.get("base_address", "0x10020000")
        env = _environment(workspace)
        result["commands"].append(
            _command(
                [
                    PYTHON,
                    "-B",
                    "SALAM-Configurator/systembuilder.py",
                    "--sysName",
                    spec["name"],
                    "--benchDir",
                    spec["benchmark"],
                    "--output-dir",
                    str(workspace),
                    "--base-address",
                    str(base),
                ],
                workspace,
                directory,
                "generate",
                env,
                120,
            )
        )
        result["generated"] = inspect_generated(workspace, spec)
        generated_contract = analyze_configuration(
            config,
            workspace,
            generated_root=workspace,
            base_address=int(str(base), 0),
            system_name=spec["name"],
        )
        _save(directory / "contract-generated.json", generated_contract)
        if not generated_contract["valid"]:
            raise ValueError(
                "Generated configuration contract rejected: "
                + repr(generated_contract["issues"])
            )
        from .build_inputs import rebind_cluster_header

        result["cluster_header_adapter"] = rebind_cluster_header(
            engine, workspace, spec, contract, directory
        )
        if "benchmark_input" in spec:
            from .benchmark_inputs import stage_benchmark_inputs
            from .benchmark_validation import fixture_for_spec

            fixture = fixture_for_spec(spec)
            fixture_path = directory / "benchmark-fixture.json"
            _save(fixture_path, fixture)
            result["benchmark_fixture"] = _record(fixture_path)
            result["benchmark_inputs"] = stage_benchmark_inputs(
                workspace, spec["benchmark"], fixture,
                inject_mismatch=spec["benchmark_input"].get("inject_mismatch", False),
                force_guest_pass=spec["benchmark_input"].get("force_guest_pass", False),
            )
            _save(directory / "benchmark-inputs.json", result["benchmark_inputs"])
        wire_runtime(workspace, spec, directory)
        result["stage"] = "workload_build"
        for label, relative, target in (
            ("build-ir", "hw", "build"),
            ("build-guest", "sw", "main.elf"),
        ):
            result["commands"].append(
                _command(
                    [
                        "make",
                        "-B",
                        "-C",
                        spec["benchmark"] + "/" + relative,
                        target,
                    ],
                    workspace,
                    directory,
                    label,
                    env,
                    300,
                )
            )
        for path in result["generated"]["ir_bindings"]:
            payload = Path(path).read_text()
            if not re.search(r'^target triple = "armv7-[^"]+"$', payload, re.M):
                raise ValueError("Accelerator IR not freshly built for ARM: " + path)
        if not (workspace / spec["benchmark"] / "sw/main.elf").is_file():
            raise ValueError("Fresh guest ELF missing")
        from .build_inputs import witness_build_inputs

        result["build_input_witness"] = witness_build_inputs(
            workspace, spec, contract, directory, env
        )
        _save(
            directory / "build-input-witness.json",
            result["build_input_witness"],
        )
        result["generated_after_build"] = inspect_generated(workspace, spec)
        result["state"], result["stage"] = "prepared", "complete"
        if simulate:
            result["stage"] = "simulator_identity"
            result["engine"] = verify_engine(engine, configured_receipt)
            capability = inspect_fu_capability(engine, build_receipt=configured_receipt)
            result["fu_scheduling_capability"] = capability
            required = [
                "simulator/system.terminal",
                "simulator/config.ini",
                "simulator/config.json",
                "simulator/stats.txt",
            ]
            if "benchmark_input" in spec:
                required.append("simulator/salam-results.txt")
            fu_artifacts = []
            if capability.get("supported"):
                for cluster in contract["components"]["clusters"]:
                    for accelerator in cluster["accelerators"]:
                        object_name = "system.{}.{}".format(
                            cluster["name"], accelerator["name"].lower()
                        )
                        fu_artifacts.append(
                            "simulator/observability/fu-scheduling-"
                            + object_name
                            + ".invocation-1.json"
                        )
                required.extend(fu_artifacts)
            inputs = [
                p
                for p in workspace.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts
            ]
            inputs += [
                directory / "specification.json",
                directory / "runtime-request.json",
                engine / "baremetal/common/fake.iso",
            ]
            if "benchmark_fixture" in result:
                inputs.append(directory / "benchmark-fixture.json")
            _save(
                directory / "prepared-inputs.json",
                [_record(p) for p in inputs],
            )
            result["stage"] = "simulation"
            run = run_experiment(
                [str(engine / "build/ARM/gem5.opt")],
                simulator_args(engine, workspace, spec),
                cwd=workspace,
                runs_root=directory / "runs",
                experiment={
                    "schema_version": 1,
                    "experiment_id": spec["name"],
                    "correctness": {
                        "required_guest_marker": "Check Passed",
                        "rejected_guest_marker": "Check Failed",
                        "required_simulator_exit": EXPECTED_EXIT_REASON,
                    },
                    "configuration_specification": spec,
                    "limits": [
                        "Guest checker result is not independent hardware validation"
                    ],
                },
                input_paths=inputs,
                env_overrides={"M5_PATH": str(workspace), "PATH": env["PATH"]},
                timeout_seconds=spec.get("timeout_seconds", 600),
                snapshot_inputs=True,
                required_artifacts=required,
            )
            result["run_directory"], result["run_state"] = (
                run["run_directory"],
                run["state"],
            )
            if run["state"] != "passed":
                raise ValueError("Simulator/guest did not pass: " + repr(run["errors"]))
            if run["correctness"]["passed_markers"] != spec.get("correctness", {}).get(
                "expected_passed_markers", 1
            ):
                raise ValueError("Guest success-marker count differs from contract")
            result["numerical_correctness"] = "guest_checker_passed"
            if "benchmark_input" in spec:
                from .benchmark_validation import assess_configured_output

                result["stage"] = "independent_numerical_validation"
                result["independent_oracle"] = assess_configured_output(
                    spec,
                    Path(run["run_directory"]) / "simulator/salam-results.txt",
                    directory / "benchmark-fixture.json",
                )
                _save(directory / "independent-oracle.json", result["independent_oracle"])
                if result["independent_oracle"].get("state") != "passed":
                    result["numerical_correctness"] = "independent_full_output_failed"
                    raise ValueError("Independent full-output numerical oracle rejected the simulation")
                result["numerical_correctness"] = "independent_full_output_passed"
            result["stage"] = "effective_configuration"
            ini = Path(run["run_directory"]) / "simulator/config.ini"
            if fu_artifacts:
                from .fu_experiments import inspect_fu_invocation

                fu_results = [
                    inspect_fu_invocation(Path(run["run_directory"]) / relative, ini)
                    for relative in fu_artifacts
                ]
                result["fu_scheduling_witness"] = {
                    "state": "passed"
                    if all(item["state"] == "passed" for item in fu_results)
                    else "failed",
                    "invocations": fu_results,
                }
                _save(
                    directory / "fu-scheduling-witness.json",
                    result["fu_scheduling_witness"],
                )
                if result["fu_scheduling_witness"]["state"] != "passed":
                    raise ValueError(
                        "Direct functional-unit scheduling evidence failed independent replay"
                    )
            applied = json.loads((directory / "runtime-applied.json").read_text())
            result["parameter_witness"] = witness_parameters(ini, applied)
            if "benchmark_input" in spec:
                result["output_transport_witness"] = witness_parameters(ini, {"parameters": [
                    {"section": "system", "parameter": "semihosting", "normalized": "system.semihosting"},
                    {"section": "system.semihosting", "parameter": "type", "normalized": "ArmSemihosting"},
                ]})
                if result["output_transport_witness"]["state"] != "passed":
                    raise ValueError("Guest result file transport is not instantiated as requested")
            effective = analyze_configuration(
                config,
                workspace,
                generated_root=workspace,
                base_address=int(str(spec.get("base_address", "0x10020000")), 0),
                system_name=spec["name"],
            )
            effective = witness_layered_contract(effective, ini, applied)
            _save(directory / "contract-effective.json", effective)
            if (
                not effective["valid"]
                or result["parameter_witness"]["state"] != "passed"
            ):
                raise ValueError("Effective configuration witness failed")
            from .system_witness import witness_system

            system_options = dict(SYSTEM_DEFAULTS)
            system_options.update(spec.get("system", {}))
            result["system_witness"] = witness_system(
                ini,
                system_options,
                stats_path=ini.parent / "stats.txt",
                runtime_system=directory / "system-live.json",
            )
            _save(directory / "system-witness.json", result["system_witness"])
            result["runtime_witnesses"] = [
                _record(directory / p)
                for p in ("runtime-applied.json", "system-live.json")
            ]
            if result["system_witness"]["state"] in {"failed", "unavailable"}:
                raise ValueError(
                    "Requested system settings do not match effective configuration"
                )
            from .profile_witness import witness_profiles

            result["profile_witness"] = witness_profiles(
                workspace, ini, parameter_overrides=spec.get("parameters", {})
            )
            _save(directory / "profile-witness.json", result["profile_witness"])
            if result["profile_witness"]["state"] != "passed":
                raise ValueError(
                    "Generated model coefficients do not match effective simulator parameters"
                )
            result["metrics"] = parse_stats(ini.parent / "stats.txt")
            if result["metrics"]["issues"] or result["metrics"].get(
                "missing_core_metrics"
            ):
                raise ValueError(
                    "Required whole-guest measurement fields missing or invalid"
                )
            result["state"], result["stage"] = "passed", "complete"
        for item in result["staging"]["inputs"]:
            if file_hash(item["path"]) != item["sha256"]:
                raise ValueError("Original source changed during configuration")
        result["original_sources_unchanged"] = True
        assert_tooling_unchanged(PROJECT, result["tooling"])
    except Exception as error:
        result["state"] = "failed"
        result["errors"].append(type(error).__name__ + ": " + str(error))
    result["finished_at"] = _now()
    _save(directory / "configuration.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "prepare",
            "run",
            "build",
            "inventory",
            "hardware",
            "install",
        ),
    )
    parser.add_argument("--engine", required=True)
    parser.add_argument("--spec")
    parser.add_argument("--evidence-dir")
    parser.add_argument("--build-receipt")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--generation")
    parser.add_argument("--previous-overlay")
    parser.add_argument("--benchmark-name", default="gemm")
    parser.add_argument("--model", default="40nm_model")
    parser.add_argument("--period", default="5ns")
    parser.add_argument("--profile", default="default_profile")
    args = parser.parse_args()
    directory = args.evidence_dir or str(
        PROJECT / "evidence" / ("configuration-" + uuid.uuid4().hex[:12])
    )
    if args.action == "build":
        result = build_engine(args.engine, directory, jobs=args.jobs)
    elif args.action == "inventory":
        result = inventory_configurations(args.engine, directory)
    elif args.action == "hardware":
        from .hardware_codegen import generate_hardware_code

        result = generate_hardware_code(
            args.engine,
            args.benchmark_name,
            directory,
            model=args.model,
            period=args.period,
            profile=args.profile,
        )
    elif args.action == "install":
        if not args.generation:
            parser.error("--generation is required")
        result = install_hardware_overlay(
            args.generation,
            args.engine,
            directory,
            previous_overlay=args.previous_overlay,
        )
    else:
        if not args.spec:
            parser.error("--spec is required")
        result = run_configuration(
            args.engine,
            args.spec,
            directory,
            simulate=args.action == "run",
            configured_receipt=args.build_receipt,
        )
    print(
        json.dumps(
            {
                "state": result["state"],
                "evidence_directory": directory,
                "errors": result.get("errors", []),
            }
        )
    )
    return (
        0
        if result["state"]
        in {
            "passed",
            "prepared",
            "built",
            "inventoried",
            "installed_requires_rebuild",
        }
        or result.get("valid")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
