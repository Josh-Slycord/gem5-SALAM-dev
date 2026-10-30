"""One evidence-preserving configuration entry point for the supported GEMM topology."""
import argparse
import ast
import datetime
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess

from .config import validate_gemm_config
from .runner import ENV_ALLOWLIST, file_hash

PYTHON = "/usr/bin/python3.8"
REL = Path("benchmarks/sys_validation/gemm")
GENERATED = (
    Path("configs/SALAM/generated/gemm.py"),
    Path("configs/SALAM/generated/fs_gemm.py"),
    REL / "gemm_clstr_hw_defines.h",
)
GENERATOR_SOURCES = (
    Path("SALAM-Configurator/systembuilder.py"),
    Path("SALAM-Configurator/parser.py"),
    Path("SALAM-Configurator/fs_template.py"),
)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _save(path, data):
    temporary = path.with_name(path.name + ".writing")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(str(temporary), str(path))


def _inside(path, root):
    resolved = path.resolve(strict=True)
    resolved.relative_to(root)
    if not resolved.is_file():
        raise ValueError("Expected regular file: " + str(path))
    return resolved


def _hash_record(path):
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": file_hash(path)}


def _attribute(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _attribute(node.value) + "." + node.attr
    raise ValueError("Unsupported generated assignment target")


def _constant(node, variables):
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.Name) and node.id in variables:
        return variables[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _constant(node.left, variables) + _constant(node.right, variables)
    raise ValueError("Expected static integer expression in generated address layout")


def _expect(actual, expected, label):
    if actual != expected:
        raise ValueError(label + ": expected " + repr(expected) + "; found " + repr(actual))


def inspect_generated(generated_root, validation, engine_root):
    """Parse generated files without importing/executing their Python code."""
    generated_root = Path(generated_root).resolve()
    engine_root = Path(engine_root).resolve()
    paths = [_inside(generated_root / p, generated_root) for p in GENERATED]
    trees = [ast.parse(paths[i].read_text(encoding="utf-8"), filename=str(paths[i]))
             for i in (0, 1)]
    functions = [node for node in trees[0].body
                 if isinstance(node, ast.FunctionDef) and node.name == "buildgemm_clstr"]
    _expect(len(functions), 1, "buildgemm_clstr function count")
    layout = {item["name"]: item for item in validation["layout"]}
    variables, devices, memories, ir_bindings = {}, {}, {}, {}
    pending_ir, pending_config = None, None
    for node in functions[0].body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = _attribute(node.targets[0])
        value = node.value
        if target in {"local_low", "local_high", "addr"}:
            variables[target] = _constant(value, variables)
        elif target in {"ir", "config"}:
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                raise ValueError("Expected literal " + target + " path")
            if target == "ir":
                pending_ir = value.value
            else:
                pending_config = value.value
        elif target == "spmRange":
            if not isinstance(value, ast.Call) or _attribute(value.func) != "AddrRange" or len(value.args) != 2 or value.keywords:
                raise ValueError("Unsupported generated scratchpad range expression")
            variables["spmRange"] = [_constant(arg, variables) for arg in value.args]
        elif target in {"clstr.dma", "clstr.top", "clstr.gemm"}:
            if target in devices:
                raise ValueError("Duplicate generated device: " + target)
            if not isinstance(value, ast.Call):
                raise ValueError("Expected device constructor for " + target)
            kwargs = {item.arg: item.value for item in value.keywords}
            if len(kwargs) != len(value.keywords) or None in kwargs:
                raise ValueError("Duplicate or expanded device keyword arguments")
            _expect(_attribute(value.func), "NoncoherentDma" if target == "clstr.dma" else "CommInterface", target + " constructor")
            devices[target] = {
                key: _constant(kwargs[key], variables) for key in ("pio_addr", "pio_size")
            }
            if target != "clstr.dma":
                ir_bindings[target] = {"ir": pending_ir, "config": pending_config}
        elif target in {"clstr.matrix1", "clstr.matrix2", "clstr.matrix3"}:
            if target in memories:
                raise ValueError("Duplicate generated scratchpad: " + target)
            if not isinstance(value, ast.Call) or _attribute(value.func) != "ScratchpadMemory":
                raise ValueError("Expected ScratchpadMemory constructor")
            if len(value.keywords) != 1 or value.keywords[0].arg != "range" or not isinstance(value.keywords[0].value, ast.Name) or value.keywords[0].value.id != "spmRange":
                raise ValueError("Unsupported generated scratchpad range binding")
            memories[target] = list(variables["spmRange"])

    _expect(variables.get("local_low"), validation["base_address"], "cluster start")
    _expect(variables.get("local_high"), validation["cluster_top_address"], "cluster exclusive end")
    device_evidence = []
    for name, key in (("dma", "clstr.dma"), ("Top", "clstr.top"), ("gemm", "clstr.gemm")):
        item = layout[name]
        allocated = item["bytes"] if name == "dma" else item["bytes"] + 64 - item["bytes"] % 64
        expected = {"pio_addr": item["address"], "pio_size": allocated}
        _expect(devices.get(key), expected, key)
        device_evidence.append({"name": name, "address": item["address"],
                                "declared_payload_bytes": item["bytes"],
                                "allocated_pio_bytes": allocated})
    for name in ("MATRIX1", "MATRIX2", "MATRIX3"):
        item = layout[name]
        _expect(memories.get("clstr." + name.lower()),
                [item["address"], item["address"] + item["bytes"]], name + " half-open range")
    for name in ("top", "gemm"):
        expected = {"ir": str(engine_root / REL / "hw" / (name + ".ll")),
                    "config": str(engine_root / REL / "config.yml")}
        _expect(ir_bindings.get("clstr." + name), expected, name + " input bindings")
    bindings = [node for node in ast.walk(functions[0])
                if isinstance(node, ast.Call) and _attribute(node.func) == "AccConfig"]
    _expect(len(bindings), 2, "AccConfig binding count")
    for node, name in zip(bindings, ("top", "gemm")):
        _expect([_attribute(arg) for arg in node.args], ["clstr." + name, "ir", "config"],
                name + " AccConfig arguments")
    imports = [alias.name for node in ast.walk(trees[1]) if isinstance(node, ast.Import) for alias in node.names]
    _expect(imports.count("gemm"), 1, "full-system gemm import count")
    calls = [node for node in ast.walk(trees[1])
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and isinstance(node.func.value, ast.Name) and node.func.value.id == "gemm"
             and node.func.attr == "makeHWAcc"]
    _expect(len(calls), 1, "full-system gemm.makeHWAcc call count")

    expected_macros = {
        "DMA_Flags": layout["dma"]["address"], "DMA_RdAddr": layout["dma"]["address"] + 1,
        "DMA_WrAddr": layout["dma"]["address"] + 9, "DMA_CopyLen": layout["dma"]["address"] + 17,
        "TOP": layout["Top"]["address"], "GEMM": layout["gemm"]["address"],
    }
    expected_macros.update({name: layout[name]["address"] for name in ("MATRIX1", "MATRIX2", "MATRIX3")})
    macros = {}
    for number, line in enumerate(paths[2].read_text(encoding="utf-8").splitlines(), 1):
        match = re.match(r"^\s*#\s*define\s+([A-Za-z_]\w*)(?:\s+(.*))?$", line)
        if not match or match.group(1) not in expected_macros:
            continue
        name, expression = match.groups()
        if name in macros:
            raise ValueError("Duplicate generated header macro: " + name)
        try:
            macros[name] = int(expression.strip(), 0)
        except (ValueError, AttributeError):
            raise ValueError("Expected integer address macro at header line " + str(number))
    _expect(macros, expected_macros, "generated header addresses")
    return {
        "valid": True, "python_syntax": "parsed_without_execution",
        "address_semantics": "half-open [start, end)",
        "devices": device_evidence, "scratchpad_ranges": memories, "header_macros": macros,
        "generated_files": [_hash_record(path) for path in paths],
        "limitations": [
            "Checks cover the scoped generated GEMM structure, not arbitrary Python semantics.",
            "Effective hardware parameters and numerical correctness still require simulator evidence.",
        ],
    }


def validate_and_generate(engine_root, output_evidence_dir, *, timeout_seconds=120):
    """Validate, stage generated outputs, inspect them, then install validated files.

    The evidence directory must be new. Failure returns valid=False and retains
    facade.json plus available logs/snapshots. This API does not compile IR or run
    the simulator. Call postbuild validation after compiling workload artifacts.
    """
    evidence = Path(output_evidence_dir).expanduser().resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    result = {"schema_version": 1, "facade": "gemm-generation-v1", "state": "running",
              "valid": False, "stage": "validation", "started_at": _now(),
              "finished_at": None, "evidence_directory": str(evidence),
              "command": None, "inputs": [], "before": [], "installed": [], "errors": []}
    _save(evidence / "facade.json", result)
    try:
        engine = Path(engine_root).expanduser().resolve(strict=True)
        if not engine.is_dir():
            raise ValueError("engine_root must be a directory")
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        validation = validate_gemm_config(engine / REL / "config.yml", engine, require_ir=False)
        result["validation"] = validation
        result["inputs"] = list(validation["inputs"])
        for relative in GENERATOR_SOURCES:
            result["inputs"].append(_hash_record(_inside(engine / relative, engine)))
        # systembuilder preserves non-generated header content; record that input.
        for relative in GENERATED:
            target = engine / relative
            if target.exists():
                target = _inside(target, engine)
                destination = evidence / "before" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(target), str(destination))
                item = _hash_record(target)
                item["snapshot"] = str(destination.relative_to(evidence))
                result["before"].append(item)
                if relative == GENERATED[2]:
                    result["inputs"].append(_hash_record(target))
        generated = evidence / "generated"
        environment = {key: value for key, value in os.environ.items() if key in ENV_ALLOWLIST}
        environment["M5_PATH"] = str(engine)
        environment["PATH"] = "/usr/lib/llvm-12/bin:" + environment.get("PATH", "")
        argv = [PYTHON, "SALAM-Configurator/systembuilder.py", "--sysName", "gemm",
                "--benchDir", REL.as_posix(), "--output-dir", str(generated),
                "--base-address", hex(validation["base_address"])]
        result["command"] = {"argv": argv, "cwd": str(engine), "environment": environment,
                             "timeout_seconds": timeout_seconds, "return_code": None,
                             "executable": _hash_record(Path(PYTHON).resolve(strict=True)),
                             "stdout": "generator.stdout.txt", "stderr": "generator.stderr.txt"}
        result["stage"] = "generation"
        _save(evidence / "facade.json", result)
        with (evidence / "generator.stdout.txt").open("wb") as stdout, (evidence / "generator.stderr.txt").open("wb") as stderr:
            try:
                process = subprocess.run(argv, cwd=str(engine), env=environment, shell=False,
                                         stdout=stdout, stderr=stderr, timeout=timeout_seconds)
                result["command"]["return_code"] = process.returncode
            except subprocess.TimeoutExpired:
                result["state"] = "timed_out"
                raise RuntimeError("Configuration generation timed out")
        if process.returncode != 0:
            raise RuntimeError("Configuration generator returned " + str(process.returncode))
        for item in result["inputs"]:
            item["unchanged_after_generation"] = file_hash(item["path"]) == item["sha256"]
            if not item["unchanged_after_generation"]:
                raise ValueError("Generator input changed during generation: " + item["path"])
        result["stage"] = "generated_validation"
        result["generated_validation"] = inspect_generated(generated, validation, engine)
        result["stage"] = "installation"
        for relative in GENERATED:
            source = _inside(generated / relative, generated)
            destination = engine / relative
            destination.parent.resolve(strict=True).relative_to(engine)
            if destination.is_symlink():
                raise ValueError("Refusing to replace generated symlink: " + str(destination))
            shutil.copyfile(str(source), str(destination))
            installed = _hash_record(destination)
            installed["staged_sha256"] = file_hash(source)
            if installed["sha256"] != installed["staged_sha256"]:
                raise ValueError("Installed output differs from validated staged file")
            result["installed"].append(installed)
        result["state"], result["valid"], result["stage"] = "generated", True, "complete"
    except Exception as error:
        if result["state"] != "timed_out":
            result["state"] = "failed"
        result["errors"].append(type(error).__name__ + ": " + str(error))
    finally:
        result["finished_at"] = _now()
        result["artifacts"] = [_hash_record(path) for path in sorted(evidence.rglob("*"))
                               if path.is_file() and path.name not in {"facade.json", "facade.json.writing"}]
        _save(evidence / "facade.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    result = validate_and_generate(args.engine_root, args.evidence_dir, timeout_seconds=args.timeout)
    print(json.dumps({"state": result["state"], "valid": result["valid"],
                      "evidence_directory": result["evidence_directory"], "errors": result["errors"]}))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
