"""Source-bound pre-launch witnesses for the small VADD diagnostic."""

import configparser
import hashlib
import json
import re
from pathlib import Path

import yaml

from .config_contract import _Loader, _pad

BENCHMARK = "benchmarks/sys_validation/vadd"


def _file(path, root):
    path = Path(path)
    root = Path(root).resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError("VADD witness file is outside its evidence root")
    if not resolved.is_file():
        raise ValueError("VADD witness file is outside its evidence root")
    data = resolved.read_bytes()
    if not data:
        raise ValueError("VADD witness file is empty: " + str(path))
    return {
        "path": str(resolved),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _macros(text, length):
    expected = {
        "VADD_LENGTH": str(length),
        "VADD_ELEMENT_BYTES": "4",
        "TYPE": "int32_t",
    }
    actual = {}
    for name, value in re.findall(r"(?m)^#define\s+(\w+)\s+([^\n]+)$", text):
        if name in expected:
            if name in actual:
                raise ValueError("Duplicate VADD compiler macro: " + name)
            actual[name] = value.strip()
    if actual != expected:
        raise ValueError("Compiler VADD macros differ: " + repr(actual))
    return actual


def _function(ir, name):
    match = re.search(
        r"(?ms)^define\b[^\n]*@" + re.escape(name) + r"\([^\n]*\)[^\n]*\{\s*\n(.*?)^\}",
        ir,
    )
    if not match:
        raise ValueError("Missing VADD IR function " + name)
    return match.group(1)


def _kernel_ir(ir, length, addresses):
    body = _function(ir, "vadd")
    pointers = {
        name: int(address)
        for name, address in re.findall(
            r"(?m)^\s*(%[-\w.]+)\s*=\s*getelementptr[^\n]*"
            r"inttoptr\s*\(i32\s+(\d+)\s+to\s+i32\*\)",
            body,
        )
    }
    pointer = r"(%[-\w.]+|inttoptr\s*\(i32\s+\d+\s+to\s+i32\*\))"

    def base(value):
        match = re.fullmatch(r"inttoptr\s*\(i32\s+(\d+)\s+to\s+i32\*\)", value)
        return int(match.group(1)) if match else pointers.get(value)

    loads = {
        name: base(ptr)
        for name, ptr in re.findall(
            r"(?m)^\s*(%[-\w.]+)\s*=\s*load\s+(?:volatile\s+)?i32\s*,\s*i32\*\s+"
            + pointer,
            body,
        )
    }
    additions = re.findall(
        r"(?m)^\s*(%[-\w.]+)\s*=\s*add\s+(?:(?:nuw|nsw)\s+)*i32\s+(%[-\w.]+),\s*(%[-\w.]+)",
        body,
    )
    stores = {
        (value, base(ptr))
        for value, ptr in re.findall(
            r"(?m)^\s*store\s+(?:volatile\s+)?i32\s+(%[-\w.]+)\s*,\s*i32\*\s+"
            + pointer,
            body,
        )
    }
    if not any(
        a in loads
        and b in loads
        and a != b
        and {loads[a], loads[b]} == {addresses["VECTOR_A"], addresses["VECTOR_B"]}
        and (result, addresses["VECTOR_C"]) in stores
        for result, a, b in additions
    ):
        raise ValueError(
            "VADD IR lacks two runtime i32 loads, their add, and result store"
        )
    if length > 1 and not re.search(
        r"(?m)^\s*%[-\w.]+\s*=\s*icmp\s+\w+\s+i\d+\s+%[-\w.]+,\s*"
        + str(length)
        + r"\b",
        body,
    ):
        raise ValueError("VADD IR lacks the selected loop bound")
    return {"runtime_i32_add": True, "loop_bound": length if length > 1 else None}


def _topology(path, contract, length):
    documents = list(
        yaml.load_all(Path(path).read_text(encoding="utf-8"), Loader=_Loader)
    )
    accelerators, memories = [], []
    for doc in documents:
        if not isinstance(doc, dict):
            continue
        for cluster in doc.get("acc_cluster", []):
            if not isinstance(cluster, dict):
                continue
            group = cluster.get("Accelerator")
            if not isinstance(group, list):
                continue
            for item in group:
                if isinstance(item, dict) and "Name" in item:
                    accelerators.append(item)
                if isinstance(item, dict) and isinstance(item.get("Var"), list):
                    memories.extend(item["Var"])
    top = [x for x in accelerators if str(x.get("Name", "")).lower() == "top"]
    if len(top) != 1 or top[0].get("PIOSize") != 25:
        raise ValueError("VADD top PIO layout must be 25 bytes")
    sizes = {}
    for name in ("VECTOR_A", "VECTOR_B", "VECTOR_C"):
        found = [x for x in memories if isinstance(x, dict) and x.get("Name") == name]
        if (
            len(found) != 1
            or found[0].get("Type") != "SPM"
            or type(found[0].get("Size")) is not int
            or found[0]["Size"] < length * 4
        ):
            raise ValueError("VADD SPM is missing or too small: " + name)
        sizes[name] = found[0]["Size"]
    cluster_rows = contract.get("components", {}).get("clusters", [])
    contract_top = [
        item
        for cluster in cluster_rows
        for item in cluster.get("accelerators", [])
        if str(item.get("name", "")).lower() == "top"
    ]
    if (
        len(cluster_rows) != 1
        or len(contract_top) != 1
        or contract_top[0].get("pio_size") != _pad(25)
    ):
        raise ValueError("VADD top PIO differs from normalized contract")
    contract_memories = [
        item for cluster in cluster_rows for item in cluster.get("memories", [])
    ]
    for name, size in sizes.items():
        matches = [x for x in contract_memories if x.get("name") == name]
        if len(matches) != 1 or matches[0].get("size") != size:
            raise ValueError("VADD SPM differs from normalized contract: " + name)
    return {"top_pio_bytes": 25, "memory_sizes": sizes, "transfer_bytes": length * 4}


def witness_vadd_build(workspace, spec, contract, directory, build_input_witness):
    """Verify VADD's preprocessed shape and compiled inputs before launch."""
    workspace = Path(workspace).resolve(strict=True)
    directory = Path(directory).resolve(strict=True)
    if spec.get("benchmark") != BENCHMARK:
        raise ValueError("VADD build witness requires the VADD benchmark")
    case = spec.get("benchmark_input", {})
    length = case.get("length", 8)
    if type(length) is not int or not 1 <= length <= 256:
        raise ValueError("Invalid VADD length")
    bench = workspace / BENCHMARK
    expected_ir = {BENCHMARK + "/hw/top.ll", BENCHMARK + "/hw/vadd.ll"}
    if set(contract.get("ir_paths", [])) != expected_ir:
        raise ValueError("VADD contract does not name both expected IR files")
    source_paths = {
        str((bench / "sw/main.cpp").resolve()): "guest",
        str((bench / "hw/top.c").resolve()): "top",
        str((bench / "hw/vadd.c").resolve()): "vadd",
    }
    if build_input_witness.get("state") != "passed":
        raise ValueError("VADD requires successful compiler input witnesses")
    checks = build_input_witness.get("checks")
    if not isinstance(checks, list) or len(checks) != 3:
        raise ValueError("VADD requires exactly three compiler macro probes")
    seen, probes = set(), []
    for check in checks:
        source = str(Path(check.get("source", "")).resolve())
        if source not in source_paths or source in seen:
            raise ValueError("Unexpected or repeated VADD compiler source")
        seen.add(source)
        cmd = check.get("command", {})
        name = cmd.get("stdout")
        argv = cmd.get("argv")
        if (
            cmd.get("state") != "completed"
            or cmd.get("return_code") != 0
            or not isinstance(argv, list)
            or "-dM" not in argv
            or "-E" not in argv
            or source not in argv
            or not isinstance(name, str)
            or Path(name).name != name
        ):
            raise ValueError("Invalid VADD compiler macro probe")
        output = _file(directory / name, directory)
        if output["sha256"] != cmd.get("stdout_sha256"):
            raise ValueError("VADD compiler macro probe hash mismatch")
        macro_values = _macros(Path(output["path"]).read_text(), length)
        probes.append(
            {
                "role": source_paths[source],
                "source": _file(source, workspace),
                "stdout": output,
                "macros": macro_values,
            }
        )
    config_path = bench / "config.yml"
    topology = _topology(config_path, contract, length)
    vadd_ir = bench / "hw/vadd.ll"
    top_ir = bench / "hw/top.ll"
    ir_files = [_file(top_ir, workspace), _file(vadd_ir, workspace)]
    addresses = build_input_witness.get("expected_macros", {})
    if any(
        type(addresses.get(key)) is not int
        for key in ("VECTOR_A", "VECTOR_B", "VECTOR_C", "DMA_CopyLen")
    ):
        raise ValueError("Compiler input witness lacks VADD/DMA addresses")
    kernel = _kernel_ir(vadd_ir.read_text(), length, addresses)
    top = _function(top_ir.read_text(), "top")
    transfer = re.findall(
        r"(?m)^\s*store\s+volatile\s+i32\s+"
        + str(length * 4)
        + r"\s*,\s*i32\*\s+inttoptr\s*\(i32\s+"
        + str(addresses["DMA_CopyLen"])
        + r"\s+to\s+i32\*\)",
        top,
    )
    if len(transfer) < 3:
        raise ValueError("VADD top IR lacks three selected-length DMA transfers")
    headers = [bench / "defines.h"] + [
        bench / (row["name"] + "_hw_defines.h")
        for row in contract["components"]["clusters"]
    ]
    return {
        "state": "passed",
        "kind": "vadd_build_witness",
        "length": length,
        "probes": probes,
        "topology": topology,
        "kernel": kernel,
        "top_dma_length_stores": len(transfer),
        "headers": [_file(path, workspace) for path in headers],
        "config": _file(config_path, workspace),
        "ir": ir_files,
        "guest_elf": _file(bench / "sw/main.elf", workspace),
        "scope": "Pre-launch compiler and topology evidence; not simulator execution",
    }


def _read_bound_bytes(path, root, max_bytes=256 * 1024 * 1024):
    path = Path(path)
    root = Path(root).resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError("VADD runtime artifact is outside run directory")
    if not resolved.is_file() or resolved.stat().st_size > max_bytes:
        raise ValueError("VADD runtime artifact is missing or too large")
    payload = resolved.read_bytes()
    if not payload or len(payload) > max_bytes:
        raise ValueError("VADD runtime artifact is empty or too large")
    return payload, {
        "path": str(resolved),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _read_bound_json(path, root, max_bytes=256 * 1024 * 1024):
    payload, info = _read_bound_bytes(path, root, max_bytes)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate runtime JSON key: " + key)
            result[key] = value
        return result

    return json.loads(payload, object_pairs_hook=unique), info


def _require_recorded(run, relative, actual):
    items = [x for x in run.get("artifacts", []) if x.get("path") == relative]
    if (
        len(items) != 1
        or items[0].get("sha256") != actual["sha256"]
        or items[0].get("bytes") != actual["bytes"]
    ):
        raise ValueError("VADD run artifact identity mismatch: " + relative)


def witness_vadd_execution(
    run_directory, spec, fu_scheduling_witness, *, allow_failed_guest=False
):
    """Require executed VADD activity, independent of guest correctness markers."""
    root = Path(run_directory).resolve(strict=True)
    if spec.get("benchmark") != BENCHMARK:
        raise ValueError("VADD execution witness requires the VADD benchmark")
    length = spec.get("benchmark_input", {}).get("length", 8)
    if type(length) is not int or not 1 <= length <= 256:
        raise ValueError("Invalid VADD length")
    run, run_info = _read_bound_json(root / "run.json", root, 16 * 1024 * 1024)
    binary = run.get("executable", {})
    binary_hash = binary.get("sha256")
    if type(allow_failed_guest) is not bool:
        raise ValueError("allow_failed_guest must be Boolean")
    case = spec.get("benchmark_input", {})
    expected_guest_failure = (
        allow_failed_guest
        and case.get("inject_mismatch") is True
        and case.get("force_guest_pass", False) is False
    )
    if allow_failed_guest and not expected_guest_failure:
        raise ValueError("Guest failure opt-in requires explicit mismatch control")
    if expected_guest_failure:
        correctness = run.get("correctness", {})
        if (
            run.get("state") != "failed"
            or correctness.get("outcome") != "failed"
            or correctness.get("failed_markers", 0) < 1
            or correctness.get("passed_markers") != 0
        ):
            raise ValueError("Expected guest failure was not observed")
    elif run.get("state") != "passed":
        raise ValueError("VADD run did not pass")
    if (
        run.get("return_code") != 0
        or run.get("simulator_exit", {}).get("reason")
        != "m5_exit instruction encountered"
        or not isinstance(binary_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", binary_hash)
        or binary.get("unchanged_after_run") is not True
        or binary.get("sha256_after_run") != binary_hash
    ):
        raise ValueError("VADD run lacks a successful binary-bound execution receipt")
    ini_path = root / "simulator/config.ini"
    config_bytes, config_info = _read_bound_bytes(ini_path, root, 16 * 1024 * 1024)
    _require_recorded(run, "simulator/config.ini", config_info)
    ini = configparser.ConfigParser(interpolation=None)
    ini.read_string(config_bytes.decode("utf-8"))
    candidates = [
        section[: -len(".llvm_interface")]
        for section in ini.sections()
        if section.endswith(".llvm_interface")
        and ini.get(section, "in_file", fallback="")
        .replace("\\", "/")
        .endswith("/benchmarks/sys_validation/vadd/hw/vadd.ll")
    ]
    if len(candidates) != 1:
        raise ValueError("Expected exactly one instantiated VADD LLVM interface")
    actor = candidates[0]
    rel_life = "simulator/observability/" + actor + ".invocation-1.json"
    rel_trace = "simulator/observability/fu-scheduling-" + actor + ".invocation-1.json"
    life, life_info = _read_bound_json(root / rel_life, root, 8 * 1024 * 1024)
    trace, trace_info = _read_bound_json(root / rel_trace, root)
    _require_recorded(run, rel_life, life_info)
    _require_recorded(run, rel_trace, trace_info)
    if fu_scheduling_witness.get("state") != "passed":
        raise ValueError("VADD requires a successful FU trace replay")
    matches = [
        x
        for x in fu_scheduling_witness.get("invocations", [])
        if Path(x.get("path", "")).resolve() == Path(trace_info["path"])
    ]
    if len(matches) != 1:
        raise ValueError("No unique replay for the instantiated VADD trace")
    replay = matches[0]
    if (
        replay.get("state") != "passed"
        or replay.get("source_sha256") != trace_info["sha256"]
        or replay.get("config_ini", {}).get("sha256") != config_info["sha256"]
        or replay.get("adjacent_lifecycle", {}).get("sha256") != life_info["sha256"]
        or replay.get("trace", {}).get("trace_complete") is not True
    ):
        raise ValueError("VADD replay is not bound to this config, trace and lifecycle")
    lifecycle = life.get("lifecycle", {})
    if (
        life.get("kind") != "salam_observability"
        or life.get("valid") is not True
        or life.get("accelerator") != actor
        or life.get("invocation") != 1
        or lifecycle.get("completed") is not True
    ):
        raise ValueError("Missing or unfinished VADD invocation 1")
    ticks, period, start, end, elapsed = (
        lifecycle.get(x)
        for x in (
            "interface_tick_calls",
            "clock_period_ticks",
            "start_tick",
            "end_tick",
            "elapsed_ticks",
        )
    )
    if (
        any(type(x) is not int for x in (ticks, period, start, end, elapsed))
        or ticks <= 1
        or period <= 0
        or elapsed <= 0
        or end - start != elapsed
        or elapsed != (ticks - 1) * period
    ):
        raise ValueError("VADD invocation has no consistent active simulated time")
    diagnostics = life.get("diagnostics", {})
    if (
        diagnostics.get("pending_requests") != 0
        or diagnostics.get("invalid_events") != 0
    ):
        raise ValueError("VADD invocation has pending or invalid events")
    memory = life.get("memory", {})
    reads, writes, execution = (
        memory.get("reads", {}),
        memory.get("writes", {}),
        life.get("execution", {}),
    )
    if (
        memory.get("availability") != "observed"
        or execution.get("availability") != "observed_selected_commits"
        or type(reads.get("completed")) is not int
        or reads["completed"] < 2 * length
        or type(writes.get("completed")) is not int
        or writes["completed"] < length
        or type(reads.get("completed_bytes")) is not int
        or reads["completed_bytes"] != 8 * length
        or type(reads.get("started_bytes")) is not int
        or reads["started_bytes"] != 8 * length
        or type(writes.get("completed_bytes")) is not int
        or writes["completed_bytes"] != 4 * length
        or type(writes.get("started_bytes")) is not int
        or writes["started_bytes"] != 4 * length
        or type(execution.get("memory_read_commits")) is not int
        or execution["memory_read_commits"] < 2 * length
        or type(execution.get("memory_write_commits")) is not int
        or execution["memory_write_commits"] < length
    ):
        raise ValueError("VADD invocation lacks expected memory completion activity")
    add_section = actor + ".hw_interface.inst_config.add"
    opcode = ini.getint(add_section, "opcode_num")
    unit = ini.getint(add_section, "functional_unit")
    if (
        trace.get("kind") != "salam_fu_scheduling"
        or trace.get("invocation", {}).get("name") != actor
    ):
        raise ValueError("VADD FU trace belongs to a different accelerator")
    events = trace.get("trace")
    if not isinstance(events, list):
        raise ValueError("VADD FU events are missing")
    grants = sum(
        1
        for x in events
        if isinstance(x, dict)
        and x.get("event") == "grant"
        and x.get("opcode") == opcode
        and x.get("fu_id") == unit
    )
    releases = sum(
        1
        for x in events
        if isinstance(x, dict)
        and x.get("event") == "release"
        and x.get("opcode") == opcode
        and x.get("fu_id") == unit
    )
    if grants < length or releases < length:
        raise ValueError("VADD FU trace lacks required add grants and releases")
    return {
        "state": "passed",
        "kind": "vadd_execution_witness",
        "accelerator": actor,
        "invocation": 1,
        "length": length,
        "run_receipt": run_info,
        "binary_sha256_recorded": binary_hash,
        "config": config_info,
        "direct_lifecycle": life_info,
        "direct_fu_trace": trace_info,
        "add_opcode": opcode,
        "add_fu_id": unit,
        "add_grants": grants,
        "add_releases": releases,
        "lifecycle": lifecycle,
        "memory": memory,
        "execution": execution,
        "expected_guest_failure": expected_guest_failure,
        "scope": "Execution activity only; add counts may include loop-index instructions; numerical verification is separate.",
    }
