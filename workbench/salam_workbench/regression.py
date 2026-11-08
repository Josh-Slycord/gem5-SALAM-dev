"""Selected fixed regression experiments with explicit per-workload oracles."""
import argparse
import ast
import cmath
import datetime
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import uuid
from collections import deque
from pathlib import Path

from .observability import assess_run_observability
from .report import parse_stats, write_report
from .runner import (
    ENV_ALLOWLIST,
    EXPECTED_EXIT_REASON,
    _terminate_owned_process,
    file_hash,
    run_experiment,
)
from .toolchain_profile import apply_environment, load_toolchain, require_legacy_harness

PROJECT = Path(__file__).resolve().parents[1]
CATALOG = PROJECT / "experiments/regression/catalog.json"
PYTHON = "/usr/bin/python3.8"
CORE_METRICS = ("simTicks", "simSeconds", "simInsts", "hostSeconds")
SOURCE_SUFFIXES = {
    ".c",
    ".cpp",
    ".h",
    ".s",
    ".ld",
    ".yml",
    ".yaml",
    ".ini",
    ".py",
}
GENERATOR = (
    "SALAM-Configurator/systembuilder.py",
    "SALAM-Configurator/parser.py",
    "SALAM-Configurator/fs_template.py",
)
ORACLE_KINDS = {
    "bfs": "fixed_csr_levels_v1",
    "nw": "fixed_alignments_v1",
    "fft": "fixed_complex_dft_v1",
    "stencil3d": "fixed_integer_stencil_v1",
}
IR_TARGET_TRIPLE = "armv7-pc-none-eabi"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _save(path, value):
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_catalog(path=CATALOG):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if (
        data.get("kind") != "salam_regression_catalog"
        or data.get("schema_version") != 1
    ):
        raise ValueError("Unsupported regression catalog")
    workloads = data.get("workloads")
    if (
        not isinstance(workloads, dict)
        or not workloads
        or not set(workloads).issubset(ORACLE_KINDS)
    ):
        raise ValueError("Regression catalog contains no supported reviewed workloads")
    for name, entry in workloads.items():
        if (
            not isinstance(entry, dict)
            or entry.get("name") != name
            or entry.get("relative_path") != "benchmarks/sys_validation/" + name
            or entry.get("oracle_kind") != ORACLE_KINDS[name]
            or not isinstance(entry.get("source_sha256"), dict)
            or not entry["source_sha256"]
        ):
            raise ValueError("Invalid reviewed regression entry: " + name)
        overlays = entry.get("overlays", [])
        if not isinstance(overlays, list) or any(
            not isinstance(item, dict) or set(item) != {"path", "source", "sha256"}
            for item in overlays
        ):
            raise ValueError("Malformed overlay declaration: " + name)
    return data


def _file_inside(path, root):
    resolved = path.resolve(strict=True)
    resolved.relative_to(root)
    if not resolved.is_file() or path.is_symlink():
        raise ValueError("Expected regular source inside root: " + str(path))
    cursor = path.parent
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError("Symlink source directory is unsupported: " + str(cursor))
        cursor = cursor.parent
    return resolved


def _overlay_manifest():
    path = _file_inside(
        PROJECT / "experiments/regression/overlays/manifest.json", PROJECT
    )
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "staged_benchmark_overlays"
        or not isinstance(manifest.get("entries"), list)
    ):
        raise ValueError("Unsupported staged benchmark overlay manifest")
    return path, manifest


def _selected_overlays(engine, entry):
    """Bind each replacement to a pinned original and the reviewed overlay manifest."""
    declared = entry.get("overlays", [])
    if not declared:
        return []
    manifest_path, manifest = _overlay_manifest()
    name = entry["name"]
    selected = [item for item in manifest["entries"] if item.get("benchmark") == name]
    if len(selected) != len(declared):
        raise ValueError("Overlay manifest and catalog disagree for " + name)
    by_path = {item.get("base"): item for item in selected}
    if len(by_path) != len(selected):
        raise ValueError("Duplicate overlay target in manifest")
    bound = []
    for item in declared:
        if not isinstance(item, dict) or set(item) != {
            "path",
            "source",
            "sha256",
        }:
            raise ValueError("Malformed catalog overlay")
        relative = item["path"]
        if (
            not isinstance(relative, str)
            or not relative
            or "\\" in relative
            or ":" in relative
            or any(part in (".", "..") for part in Path(relative).parts)
            or Path(relative).is_absolute()
        ):
            raise ValueError("Unsafe overlay target")
        base_relative = entry["relative_path"] + "/" + relative
        source_relative = "experiments/regression/overlays/" + name + "/" + relative
        if item["source"] != source_relative or relative not in entry["source_sha256"]:
            raise ValueError("Overlay is not bound to a pinned workload source")
        reviewed = by_path.get(base_relative)
        if (
            not isinstance(reviewed, dict)
            or reviewed.get("kind") != "replace"
            or reviewed.get("overlay") != source_relative
            or reviewed.get("base_sha256") != entry["source_sha256"][relative]
            or reviewed.get("overlay_sha256") != item["sha256"]
        ):
            raise ValueError("Overlay manifest hashes or paths disagree with catalog")
        original = _file_inside(Path(engine) / base_relative, Path(engine))
        overlay = _file_inside(PROJECT / source_relative, PROJECT)
        if (
            file_hash(original) != reviewed["base_sha256"]
            or file_hash(overlay) != reviewed["overlay_sha256"]
        ):
            raise ValueError("Original or overlay bytes changed before staging")
        bound.append(
            {
                "relative_path": relative,
                "base": str(original),
                "base_sha256": reviewed["base_sha256"],
                "overlay": str(overlay),
                "overlay_sha256": reviewed["overlay_sha256"],
                "manifest": str(manifest_path),
                "manifest_sha256": file_hash(manifest_path),
            }
        )
    return bound


def verify_fixed_sources(root, entry):
    """Freeze the reviewed source contract, including the guest oracle and data."""
    base = root / entry["relative_path"]
    if (
        entry["name"] not in ORACLE_KINDS
        or entry.get("oracle_kind") != ORACLE_KINDS[entry["name"]]
        or entry["relative_path"] != "benchmarks/sys_validation/" + entry["name"]
    ):
        raise ValueError("Unsupported workload path")
    if not entry.get("source_sha256"):
        raise ValueError("Missing fixed-source fingerprints")
    for relative, expected in entry["source_sha256"].items():
        path = _file_inside(base / relative, root)
        if file_hash(path) != expected:
            raise ValueError("Reviewed workload source changed: " + str(path))
    return inspect_oracle_data(base, entry)


def inspect_oracle_data(base, entry):
    """Independently inspect constants as data, never execute recovered C code."""
    name = entry["name"]
    if name == "stencil3d":
        return _inspect_stencil3d(base)
    if name not in ("bfs", "nw", "fft"):
        raise ValueError("No independent oracle for " + str(name))
    text = (base / "sw/data.c").read_text()
    if name == "fft":
        return _inspect_fft(text)
    if name == "bfs":

        def array(name):
            match = re.search(r"\b" + name + r"\[[^\]]+\]\s*=\s*\{([^}]+)\}", text)
            if not match:
                raise ValueError("Missing BFS data array " + name)
            return [
                int(value.strip())
                for value in match.group(1).split(",")
                if value.strip()
            ]

        nodes, edges, expected = array("nod"), array("edg"), array("chk")
        if len(nodes) != 512 or len(edges) != 4096 or len(expected) != 10:
            raise ValueError("Unexpected BFS array dimensions")
        if any(not 0 <= node < 256 for node in edges) or any(
            not 0 <= nodes[2 * i] <= nodes[2 * i + 1] <= 4096 for i in range(256)
        ):
            raise ValueError("BFS CSR bounds are invalid")
        if not re.search(r"\bstart\s*=\s*38\s*;", text):
            raise ValueError("BFS data start is not 38")
        distances, queue = {38: 0}, deque([38])
        while queue:
            node = queue.popleft()
            for other in edges[nodes[2 * node] : nodes[2 * node + 1]]:
                if other not in distances:
                    distances[other] = distances[node] + 1
                    queue.append(other)
        actual = [
            sum(value == level for value in distances.values()) for level in range(10)
        ]
        if (
            max(distances.values()) >= 9
            or actual != expected
            or expected != entry["workload"]["expected_level_counts"]
        ):
            raise ValueError(
                "BFS fixed-data oracle does not agree with independent traversal"
            )
        return {
            "method": "independent traversal of fixed CSR data",
            "expected": expected,
            "reachable_nodes": len(distances),
            "simulation_evidence": False,
        }
    strings = {}
    for name, size in (("a", 128), ("b", 128), ("alia", 256), ("alib", 256)):
        matches = re.findall(
            r"const char \*" + name + r"\s*=\s*(\"[^\"\n]*\")\s*;", text
        )
        if not matches:
            raise ValueError("Missing NW fixed string " + name)
        value = ast.literal_eval(
            matches[0]
        )  # The first definitions are the non-TEST dataset.
        if len(value.encode("ascii")) != size:
            raise ValueError("Unexpected NW byte length: " + name)
        strings[name] = size
    return {
        "method": "fixed non-TEST strings and full-length output comparison",
        "byte_lengths": strings,
        "simulation_evidence": False,
    }


def _inspect_fft(text):
    """Check every fixed complex reference output with a direct DFT in bit-reversed order."""
    fixed = text.split("#else", 1)[0]
    lengths = {
        "re": 1024,
        "co": 1024,
        "re_twid": 512,
        "co_twid": 512,
        "re_chk": 1024,
        "co_chk": 1024,
    }
    arrays = {}
    for name, size in lengths.items():
        match = re.search(
            r"\bconst\s+double\s+" + name + r"\s*\[[^\]]+\]\s*=\s*\{([^}]*)\}",
            fixed,
        )
        if not match:
            raise ValueError("Missing fixed FFT array: " + name)
        values = [
            float(value.strip()) for value in match.group(1).split(",") if value.strip()
        ]
        if len(values) != size or not all(math.isfinite(value) for value in values):
            raise ValueError("FFT array dimension or finiteness failed: " + name)
        arrays[name] = values
    samples = [complex(real, imag) for real, imag in zip(arrays["re"], arrays["co"])]
    twiddle_error = max(
        abs(
            complex(arrays["re_twid"][k], arrays["co_twid"][k])
            - cmath.exp(-2j * math.pi * k / 1024)
        )
        for k in range(512)
    )
    if twiddle_error > 1e-12:
        raise ValueError("FFT twiddle array differs from independent roots of unity")
    max_error = 0.0
    for output_index in range(1024):
        frequency = int(format(output_index, "010b")[::-1], 2)
        step = cmath.exp(-2j * math.pi * frequency / 1024)
        power, actual = 1 + 0j, 0j
        for sample in samples:
            actual += sample * power
            power *= step
        expected = complex(
            arrays["re_chk"][output_index], arrays["co_chk"][output_index]
        )
        error = abs(actual - expected)
        if (
            not math.isfinite(actual.real)
            or not math.isfinite(actual.imag)
            or not math.isfinite(error)
        ):
            raise ValueError("FFT independent DFT produced a nonfinite result")
        max_error = max(max_error, error)
    if max_error > 1e-6:
        raise ValueError("FFT fixed reference differs from independent direct DFT")
    return {
        "method": "direct complex DFT of all 1024 fixed samples, bit-reversed output order",
        "array_lengths": lengths,
        "max_reference_error": max_error,
        "max_twiddle_error": twiddle_error,
        "simulation_evidence": False,
    }


def _inspect_stencil3d(base):
    """Bind the closed form to the pinned fixture's dimensions, input, weights and stencil."""
    defines = (base / "defines.h").read_text()
    header = (base / "sw/bench.h").read_text()
    required_defines = {
        "C_SIZE": "2",
        "HYT": "32",
        "COL": "32",
        "ROW": "16",
        "TYPE": "int32_t",
        "SIZE": "(ROW * COL * HYT)",
        "INDX": "((_i)+_row_size*((_j)+_col_size*(_k)))",
    }
    macros = dict(
        re.findall(r"^#define\s+(\w+)(?:\([^\n]*?\))?\s+([^\n]+)$", defines, re.M)
    )
    for key, expected in required_defines.items():
        if macros.get(key, "").strip() != expected:
            raise ValueError("Stencil3d fixed definition changed: " + key)
    compact = re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", header))
    fragments = (
        "for(i=0;i<SIZE;i++)",
        "if(sts->sol[i]!=sts->check[i])",
        "sts->inp[i]=i;",
        "sts->C[i]=i+2;",
        "sts->check[INDX(ROW,COL,k,j,0)]=sts->inp[INDX(ROW,COL,k,j,0)];",
        "sts->check[INDX(ROW,COL,k,j,HYT-1)]=sts->inp[INDX(ROW,COL,k,j,HYT-1)];",
        "sts->check[INDX(ROW,COL,k,0,i)]=sts->inp[INDX(ROW,COL,k,0,i)];",
        "sts->check[INDX(ROW,COL,k,COL-1,i)]=sts->inp[INDX(ROW,COL,k,COL-1,i)];",
        "sts->check[INDX(ROW,COL,0,j,i)]=sts->inp[INDX(ROW,COL,0,j,i)];",
        "sts->check[INDX(ROW,COL,ROW-1,j,i)]=sts->inp[INDX(ROW,COL,ROW-1,j,i)];",
        "sum0=sts->inp[INDX(ROW,COL,k,j,i)];",
        "sum1=sts->inp[INDX(ROW,COL,k,j,i+1)]",
        "mul0=sum0*sts->C[0];",
        "mul1=sum1*sts->C[1];",
        "sts->check[INDX(ROW,COL,k,j,i)]=mul0+mul1;",
    )
    if any(fragment not in compact for fragment in fragments):
        raise ValueError("Stencil3d pinned guest oracle structure changed")
    neighbors = ("i+1", "i-1", "j+1", "j-1", "k+1", "k-1")
    if any(
        "sts->inp[INDX(ROW,COL,"
        + (
            "k,j," + axis
            if axis.startswith("i")
            else "k," + axis + ",i"
            if axis.startswith("j")
            else axis + ",j,i"
        )
        + ")]"
        not in compact
        for axis in neighbors
    ):
        raise ValueError("Stencil3d fixed six-neighbor expression changed")
    if not all(
        loop in compact
        for loop in (
            "for(i=1;i<HYT-1;i++)",
            "for(j=1;j<COL-1;j++)",
            "for(k=1;k<ROW-1;k++)",
        )
    ):
        raise ValueError("Stencil3d interior loop bounds changed")
    digest, interior = hashlib.sha256(), 0
    for z in range(32):
        for y in range(32):
            for x in range(16):
                index = x + 16 * (y + 32 * z)
                inside = 0 < x < 15 and 0 < y < 31 and 0 < z < 31
                interior += inside
                digest.update(struct.pack("<i", 20 * index if inside else index))
    return {
        "method": "all 16384 values from pinned linear input and seven-point stencil",
        "dimensions": {"row": 16, "col": 32, "hyt": 32},
        "coefficients": [2, 3],
        "interior_outputs": interior,
        "boundary_outputs": 16384 - interior,
        "expected_int32_le_sha256": digest.hexdigest(),
        "simulation_evidence": False,
    }


def stage_sources(engine, workspace, entry):
    engine = Path(engine).resolve(strict=True)
    workspace = Path(workspace).resolve()
    if workspace == engine or engine in workspace.parents:
        raise ValueError("Staging must be outside the engine checkout")
    oracle = verify_fixed_sources(engine, entry)
    overlays = _selected_overlays(engine, entry)
    workspace.mkdir(parents=True, exist_ok=False)
    selected = {engine / path for path in GENERATOR}
    for relative in (entry["relative_path"], "benchmarks/common", "configs"):
        for path in (engine / relative).rglob("*"):
            if path.is_file() and (
                path.name == "Makefile" or path.suffix in SOURCE_SUFFIXES
            ):
                if (
                    relative == "configs"
                    and "generated" in path.relative_to(engine / relative).parts
                ):
                    continue
                if (
                    relative == entry["relative_path"]
                    and "configs" in path.relative_to(engine / relative).parts
                ):
                    continue  # Fixed configs embed the selected instruction values directly.
                selected.add(path)
    copied = []
    for path in sorted(selected):
        path = _file_inside(path, engine)
        relative = path.relative_to(engine)
        destination = workspace / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(path), str(destination))
        digest = file_hash(path)
        if file_hash(destination) != digest:
            raise ValueError("Staged byte copy differs: " + str(relative))
        copied.append(
            {
                "source": str(path),
                "relative_path": str(relative),
                "sha256": digest,
            }
        )
    applied = []
    for overlay in overlays:
        destination = _file_inside(
            workspace / entry["relative_path"] / overlay["relative_path"],
            workspace,
        )
        if file_hash(destination) != overlay["base_sha256"]:
            raise ValueError("Staged overlay base no longer matches pinned original")
        shutil.copyfile(overlay["overlay"], destination)
        if file_hash(destination) != overlay["overlay_sha256"]:
            raise ValueError("Staged overlay copy differs from reviewed bytes")
        applied.append(
            dict(
                overlay,
                staged=str(destination),
                staged_sha256=file_hash(destination),
            )
        )
    for item in copied:
        staged = workspace / Path(item["relative_path"])
        item["staged_sha256"] = file_hash(staged)
        if file_hash(item["source"]) != item["sha256"]:
            raise ValueError("Original engine source changed during staged copy")
    return {
        "workspace": str(workspace),
        "source_files": copied,
        "overlays": applied,
        "oracle_data": oracle,
        "no_saved_ir_or_guest_binary_copied": True,
    }


def _environment(workspace):
    env = {key: value for key, value in os.environ.items() if key in ENV_ALLOWLIST}
    env["M5_PATH"] = str(workspace)
    return apply_environment(env, load_toolchain(PROJECT))


def _command(argv, cwd, logs, label, env, timeout):
    record = {
        "argv": list(map(str, argv)),
        "cwd": str(cwd),
        "environment": env,
        "timeout_seconds": timeout,
        "started_at": _now(),
        "state": "running",
        "return_code": None,
        "stdout": label + ".stdout",
        "stderr": label + ".stderr",
    }
    executable = shutil.which(record["argv"][0], path=env.get("PATH"))
    if executable:
        record["executable"] = {
            "path": executable,
            "sha256": file_hash(executable),
        }
    _save(logs / (label + ".json"), record)
    try:
        with (logs / record["stdout"]).open("wb") as out, (
            logs / record["stderr"]
        ).open("wb") as err:
            process = subprocess.Popen(
                record["argv"],
                cwd=str(cwd),
                env=env,
                stdout=out,
                stderr=err,
                start_new_session=os.name == "posix",
            )
            try:
                record["return_code"] = process.wait(timeout=timeout)
                record["state"] = "completed" if process.returncode == 0 else "failed"
            except subprocess.TimeoutExpired:
                _terminate_owned_process(process)
                record["state"] = "timed_out"
        if record["state"] != "completed":
            raise RuntimeError(label + " " + record["state"] + "; inspect " + str(logs))
    except Exception as error:
        if record["state"] == "running":
            record["state"] = "failed"
        record["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        record["finished_at"] = _now()
        for field in ("stdout", "stderr"):
            path = logs / record[field]
            if path.is_file():
                record[field + "_sha256"] = file_hash(path)
        _save(logs / (label + ".json"), record)
    return record


def verify_macros(text, expected):
    actual = {}
    for line in text.splitlines():
        match = re.match(r"^#define\s+(\w+)(?:\s+(.*))?$", line)
        if match:
            actual[match.group(1)] = (match.group(2) or "").strip()
    if "TEST" in actual:
        raise ValueError("TEST changes the fixed dataset")
    for name, value in expected.items():
        if actual.get(name) != value:
            raise ValueError("Required guest macro missing or changed: " + name)


def inspect_generated(workspace, entry):
    name, rel = entry["name"], Path(entry["relative_path"])
    generated = workspace / "configs/SALAM/generated"
    tree = ast.parse((generated / (name + ".py")).read_text())
    fs = ast.parse((generated / ("fs_" + name + ".py")).read_text())
    literal_ir, literal_configs = [], []
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
                    raise ValueError("Generated input path must be literal")
                (literal_ir if key == "ir" else literal_configs).append(
                    node.value.value
                )
    expected_ir = {
        str(workspace / rel / "hw/top.ll"),
        str(workspace / rel / ("hw/" + name + ".ll")),
    }
    if (
        len(literal_ir) != 2
        or set(literal_ir) != expected_ir
        or literal_configs != [str(workspace / rel / "config.yml")] * 2
    ):
        raise ValueError(
            "Generated config is not bound to the two staged accelerator inputs"
        )
    imports = [
        alias.name
        for node in ast.walk(fs)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    if imports.count(name) != 1:
        raise ValueError("Generated full-system file has wrong workload import")
    header = workspace / rel / entry["header"]
    macros = {}
    for key, value in re.findall(
        r"^#define\s+(\w+)\s+(0x[0-9a-fA-F]+)\s*$", header.read_text(), re.M
    ):
        if key in macros:
            raise ValueError("Duplicate generated address macro: " + key)
        macros[key] = int(value, 16)
    for key in (
        "TOP",
        name.upper(),
        "DMA_Flags",
        "DMA_RdAddr",
        "DMA_WrAddr",
        "DMA_CopyLen",
    ):
        if key not in macros or not 0x10020000 <= macros[key] < 0x14000000:
            raise ValueError("Missing or out-of-range generated address: " + key)
    return {
        "python_syntax": "parsed_without_execution",
        "staged_ir": sorted(literal_ir),
        "staged_configs": literal_configs,
        "header_macros": macros,
    }


def inspect_ir_targets(workspace, entry):
    """Reject host IR before any simulator invocation and retain the generated IR fingerprints."""
    base = workspace / entry["relative_path"] / "hw"
    records = []
    for name in ("top", entry["name"]):
        path = base / (name + ".ll")
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("Fresh IR artifact missing: " + str(path))
        matches = re.findall(
            r'^target triple\s*=\s*"([^"]+)"\s*$', path.read_text(), re.M
        )
        if matches != [IR_TARGET_TRIPLE]:
            raise ValueError(
                "Generated IR has unexpected target triple: "
                + str(path)
                + " "
                + repr(matches)
            )
        records.append(
            {
                "path": str(path),
                "target_triple": matches[0],
                "sha256": file_hash(path),
            }
        )
    return records


def prepare_workload(engine, entry, directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    record = {
        "state": "preparing",
        "workload": entry["name"],
        "started_at": _now(),
        "commands": [],
    }
    _save(directory / "preparation.json", record)
    try:
        workspace = directory / "workspace"
        record["staging"] = stage_sources(engine, workspace, entry)
        env, rel = _environment(workspace), Path(entry["relative_path"])
        plans = [
            (
                "generate",
                [
                    PYTHON,
                    "-B",
                    "SALAM-Configurator/systembuilder.py",
                    "--sysName",
                    entry["name"],
                    "--benchDir",
                    str(rel),
                    "--output-dir",
                    str(workspace),
                    "--base-address",
                    "0x10020000",
                ],
                entry["generation_timeout_seconds"],
            ),
            (
                "build-ir",
                ["make", "-B", "-C", str(rel / "hw"), "build"],
                entry["build_timeout_seconds"],
            ),
            (
                "build-guest",
                ["make", "-B", "-C", str(rel / "sw"), "main.elf"],
                entry["build_timeout_seconds"],
            ),
            (
                "checker-macros",
                [
                    "/usr/bin/arm-none-eabi-g++",
                    "-dM",
                    "-E",
                    "-I",
                    str(rel / "sw"),
                    str(rel / "sw/main.cpp"),
                ],
                60,
            ),
        ]
        for label, argv, timeout in plans:
            record["commands"].append(
                _command(argv, workspace, directory, label, env, timeout)
            )
            if label == "generate":
                record["generated_validation"] = inspect_generated(workspace, entry)
            if label == "build-ir":
                record["ir_target_validation"] = inspect_ir_targets(workspace, entry)
            _save(directory / "preparation.json", record)
        verify_macros(
            (directory / "checker-macros.stdout").read_text(),
            entry["expected_macros"],
        )
        for relative in (
            rel / "sw/main.elf",
            rel / "hw/top.ll",
            rel / ("hw/" + entry["name"] + ".ll"),
        ):
            if (
                not (workspace / relative).is_file()
                or (workspace / relative).stat().st_size == 0
            ):
                raise ValueError("Fresh build artifact missing: " + str(relative))
        for item in record["staging"]["source_files"]:
            if file_hash(item["source"]) != item["sha256"]:
                raise ValueError(
                    "Original engine source changed during preparation: "
                    + item["source"]
                )
        for item in record["staging"]["overlays"]:
            if (
                file_hash(item["overlay"]) != item["overlay_sha256"]
                or file_hash(item["staged"]) != item["staged_sha256"]
                or file_hash(item["manifest"]) != item["manifest_sha256"]
            ):
                raise ValueError(
                    "Overlay or staged replacement changed during preparation"
                )
        record["state"] = "built"
        record["inputs"] = [
            {"path": str(path), "sha256": file_hash(path)}
            for path in sorted(workspace.rglob("*"))
            if path.is_file()
            and (
                path.name == "Makefile"
                or path.suffix in SOURCE_SUFFIXES | {".ll", ".elf"}
            )
        ]
    except Exception as error:
        record.update(state="failed", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        record["finished_at"] = _now()
        _save(directory / "preparation.json", record)
    return record


def simulator_args(engine, workspace, entry):
    name, rel = entry["name"], Path(entry["relative_path"])
    return [
        str(workspace / "configs/SALAM/generated" / ("fs_" + name + ".py")),
        "--mem-size=4GB",
        "--mem-type=DDR4_2400_8x8",
        "--kernel=" + str(workspace / rel / "sw/main.elf"),
        "--disk-image=" + str(engine / "baremetal/common/fake.iso"),
        "--machine-type=VExpress_GEM5_V1",
        "--dtb-file=none",
        "--bare-metal",
        "--cpu-type=DerivO3CPU",
        "--accpath=" + str(workspace / "benchmarks/sys_validation"),
        "--accbench=" + name,
        "--caches",
        "--l2cache",
    ]


def experiment_spec(entry, source):
    spec = {
        "schema_version": 1,
        "experiment_id": entry["name"] + "-fixed-regression-v1",
        "benchmark": entry["relative_path"],
        "source": source,
        "workload": entry["workload"],
        "environment": {
            "id": "ubuntu20-llvm12-python38-armgcc9",
            "toolchain_sha256": file_hash(PROJECT / "evidence/toolchain.json"),
        },
        "machine": {
            "isa": "ARM",
            "cpu": "DerivO3CPU",
            "memory": "DDR4_2400_8x8",
            "memory_size": "4GB",
            "platform": "VExpress_GEM5_V1",
            "l1_caches": True,
            "l2_cache": True,
            "execution": "bare metal",
        },
        "correctness": {
            "required_guest_marker": "Check Passed",
            "required_passed_markers": 1,
            "rejected_guest_marker": "Check Failed",
            "required_process_exit": 0,
            "required_simulator_exit": EXPECTED_EXIT_REASON,
        },
        "metrics": {
            "scope": "Whole guest measurement window including data preparation, accelerator wait and oracle; final complete stats block",
            "deterministic": {
                name: {"unit": unit, "absolute_tolerance": 0}
                for name, unit in (
                    ("simTicks", "tick"),
                    ("simSeconds", "second"),
                    ("simInsts", "instruction"),
                )
            },
            "hostSeconds": {"unit": "second", "deterministic": False},
        },
        "timeout_seconds": entry["timeout_seconds"],
        "limitations": entry["limitations"]
        + [
            "Two executions, when requested, share one fresh staged build; inputs are not regenerated between these executions",
            "No full M4 acceptance or calibrated physical hardware performance claim",
        ],
    }
    if "salam_observability_v1" in source.get("engine_features", []):
        spec["observability"] = {
            "kind": "salam_observability",
            "schema_version": 1,
            "feature": "salam_observability_v1",
            "expected_invocations": {
                "system." + entry["cluster"] + "." + name: [1]
                for name in ("top", entry["name"])
            },
            "oracles": {},
        }
    return spec


def execute_workload(engine, entry, preparation, source, runs_root):
    workspace = Path(preparation["staging"]["workspace"])
    spec = experiment_spec(entry, source)
    required = [
        "simulator/system.terminal",
        "simulator/config.ini",
        "simulator/config.json",
        "simulator/stats.txt",
    ]
    for accelerator in spec.get("observability", {}).get("expected_invocations", {}):
        required.append("simulator/observability/" + accelerator + ".invocation-1.json")
    for item in preparation["inputs"]:
        if file_hash(item["path"]) != item["sha256"]:
            raise ValueError("Prepared input changed before execution: " + item["path"])
    record = run_experiment(
        [str(engine / "build/ARM/gem5.opt")],
        simulator_args(engine, workspace, entry),
        cwd=workspace,
        runs_root=runs_root,
        experiment=spec,
        input_paths=[Path(item["path"]) for item in preparation["inputs"]]
        + [engine / "baremetal/common/fake.iso"],
        env_overrides={
            "M5_PATH": str(workspace),
            "PATH": _environment(workspace)["PATH"],
        },
        timeout_seconds=entry["timeout_seconds"],
        required_artifacts=required,
        snapshot_inputs=True,
    )
    run_dir = Path(record["run_directory"])
    record["metrics"] = parse_stats(run_dir / "simulator/stats.txt")
    record["metrics_scope"] = spec["metrics"]["scope"]
    record["observability"] = assess_run_observability(run_dir, record, spec)
    if record["state"] == "passed":
        errors = []
        if record["correctness"]["passed_markers"] != 1:
            errors.append(
                "Fixed workload requires exactly one guest Check Passed marker"
            )
        if record["metrics"]["issues"] or any(
            record["metrics"]["metrics"].get(key, {}).get("status") != "present"
            for key in CORE_METRICS
        ):
            errors.append("Required whole-run metrics missing or invalid")
        if record["observability"]["status"] == "invalid":
            errors.extend(record["observability"]["issues"])
        if errors:
            record["state"] = "incomplete"
            record["errors"].extend(errors)
    _save(run_dir / "run.json", record)
    return record


def run_regression(engine, workloads=("bfs", "nw"), repeats=2, runs_root=None):
    require_legacy_harness(PROJECT, "regression")
    if repeats not in (1, 2):
        raise ValueError("repeats must be one or two")
    catalog = load_catalog()
    if (
        not workloads
        or len(set(workloads)) != len(workloads)
        or any(name not in catalog["workloads"] for name in workloads)
    ):
        raise ValueError(
            "Choose unique selected workloads from " + ", ".join(catalog["workloads"])
        )
    engine = Path(engine).resolve(strict=True)
    session = (
        PROJECT
        / "evidence"
        / (
            "regression-"
            + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
            + "-"
            + uuid.uuid4().hex[:8]
        )
    )
    session.mkdir(parents=True, exist_ok=False)
    summary = {
        "kind": "selected_regression_session",
        "schema_version": 1,
        "state": "running",
        "started_at": _now(),
        "scope": list(workloads),
        "repeats": repeats,
        "workloads": {},
        "full_m4_complete": False,
        "W18": "separate diagnosis/deferral",
        "W19": "deferred; see docs/M4_WORKLOAD_AUDIT.md",
    }
    _save(session / "session.json", summary)
    try:
        from .builds import verify_receipt
        from .gemm import BASELINE, engine_source_digest, git
        from .provenance import assert_tooling_unchanged, snapshot_tooling

        snapshot = session / "tooling-snapshot"
        tooling_hashes = snapshot_tooling(PROJECT, snapshot)
        own_relative = "salam_workbench/regression.py"
        own_snapshot = snapshot / own_relative
        own_snapshot.write_bytes((PROJECT / own_relative).read_bytes())
        tooling_hashes[own_relative] = file_hash(own_snapshot)
        overlay_paths = {"experiments/regression/catalog.json"}
        for name in workloads:
            for item in catalog["workloads"][name].get("overlays", []):
                overlay_paths.add(item["source"])
        if any(catalog["workloads"][name].get("overlays") for name in workloads):
            overlay_paths.add("experiments/regression/overlays/manifest.json")
        for relative in sorted(overlay_paths):
            origin = _file_inside(PROJECT / relative, PROJECT)
            destination = snapshot / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, destination)
            tooling_hashes[relative] = file_hash(destination)
        assert_tooling_unchanged(PROJECT, tooling_hashes)
        digest = engine_source_digest(engine)
        receipt_path, receipt = verify_receipt(PROJECT, engine, digest)
        revision = git(engine, "rev-parse", "HEAD").decode().strip()
        if "experiments/regression/overlays/manifest.json" in overlay_paths:
            unused_path, overlay_manifest = _overlay_manifest()
            if overlay_manifest.get("engine_commit") != revision:
                raise ValueError(
                    "Overlay manifest is for a different recovered engine revision"
                )
        source = {
            "recovered_baseline": BASELINE,
            "revision": git(engine, "rev-parse", "HEAD").decode().strip(),
            "tree": git(engine, "rev-parse", "HEAD^{tree}").decode().strip(),
            "engine_source_sha256": digest,
            "engine_build_receipt_sha256": file_hash(receipt_path),
            "engine_features": receipt.get("features", []),
            "catalog_sha256": file_hash(CATALOG),
            "tooling_sha256": tooling_hashes,
        }
        _save(session / "source.json", source)
        _save(session / "engine-build-receipt.json", receipt)
        shutil.copyfile(str(CATALOG), str(session / "catalog.json"))
        for name in workloads:
            result = {"state": "preparing", "runs": []}
            summary["workloads"][name] = result
            _save(session / "session.json", summary)
            try:
                entry = catalog["workloads"][name]
                assert_tooling_unchanged(PROJECT, tooling_hashes)
                preparation = prepare_workload(engine, entry, session / name)
                assert_tooling_unchanged(PROJECT, tooling_hashes)
                result["preparation"] = str(session / name / "preparation.json")
                for unused in range(repeats):
                    assert_tooling_unchanged(PROJECT, tooling_hashes)
                    if engine_source_digest(engine) != digest:
                        raise ValueError(
                            "Engine source changed during regression session"
                        )
                    verify_receipt(PROJECT, engine, digest)
                    record = execute_workload(
                        engine,
                        entry,
                        preparation,
                        source,
                        runs_root or PROJECT / "runs",
                    )
                    result["runs"].append(
                        {
                            "directory": record["run_directory"],
                            "state": record["state"],
                        }
                    )
                    _save(session / "session.json", summary)
                    assert_tooling_unchanged(PROJECT, tooling_hashes)
                    if record["state"] != "passed":
                        raise RuntimeError(
                            name
                            + " did not pass; preserved run: "
                            + record["run_directory"]
                        )
                if repeats == 2:
                    comparison = write_report(
                        result["runs"][0]["directory"],
                        result["runs"][1]["directory"],
                        session / name / "report",
                    )
                    result["comparison"] = comparison
                    if not comparison["repeatability_accepted"]:
                        raise RuntimeError(
                            name + " deterministic repeat comparison rejected"
                        )
                result["state"] = (
                    "supported_fixed_dataset" if repeats == 2 else "single_run_passed"
                )
            except Exception as error:
                result.update(
                    state="failed",
                    error=type(error).__name__ + ": " + str(error),
                )
            _save(session / "session.json", summary)
            print(name + ": " + result["state"], flush=True)
        assert_tooling_unchanged(PROJECT, tooling_hashes)
        summary["state"] = (
            "passed"
            if all(
                item["state"] in ("supported_fixed_dataset", "single_run_passed")
                for item in summary["workloads"].values()
            )
            else "failed"
        )
    except Exception as error:
        summary.update(state="failed", error=type(error).__name__ + ": " + str(error))
    finally:
        summary["finished_at"] = _now()
        _save(session / "session.json", summary)
        print("Selected regression evidence: " + str(session), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument(
        "--workloads",
        nargs="+",
        choices=tuple(load_catalog()["workloads"]),
        default=["bfs", "nw"],
    )
    parser.add_argument("--repeats", type=int, choices=(1, 2), default=2)
    parser.add_argument("--runs-root", type=Path)
    args = parser.parse_args()
    result = run_regression(args.engine, args.workloads, args.repeats, args.runs_root)
    return 0 if result["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
