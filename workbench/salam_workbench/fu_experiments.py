"""Independent event replay for SALAM functional-unit scheduling evidence.

This reads the direct SALAM per-invocation trace. A configuration value or a
whole-guest timing difference alone cannot establish FU admission behavior.
"""
import configparser
import hashlib
import json
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

COUNTERS = ("attempts", "grants", "denials", "releases", "peak", "outstanding")
EVENTS = {"grant", "release", "deny"}
FIELDS = ("event", "cycle", "tick", "uid", "opcode", "fu_id", "lease_id")
FU_PREFIX = "fu-scheduling-"
GEMM_MULTIPLIER = "integer_multiplier"
UNUSED_UNIT = "double_divider"
FU_SECTION = ".hw_interface.functional_units."
MUL_CYCLE_SECTION = ".hw_interface.cycle_counts"


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _integer(value, *, positive=False):
    return type(value) is int and value >= (1 if positive else 0)


def _issue(result, code, detail):
    result["issues"].append({"code": code, "detail": detail})


def _ini(path):
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    with Path(path).open(encoding="utf-8") as stream:
        parser.read_file(stream)
    return parser


def validate_fu_trace(data):
    """Replay an untruncated direct SALAM trace and compare every counter.

    This function never accepts a counter-only trace, even when the counters
    are internally consistent. Lease IDs distinguish dynamic instructions
    across repeated execution of the same static LLVM UID.
    """
    result = {
        "schema_version": 1,
        "kind": "salam_fu_trace_replay",
        "state": "failed",
        "issues": [],
        "units": [],
        "totals": {},
        "events_replayed": 0,
        "trace_complete": False,
    }
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or data.get("kind") != "salam_fu_scheduling"
    ):
        _issue(result, "schema", "Expected direct SALAM FU schema version 1")
        return result
    if data.get("trace_truncated") is not False:
        _issue(
            result,
            "trace_truncated",
            "Full admission/release trace is required",
        )
        return result
    invocation = data.get("invocation")
    if (
        not isinstance(invocation, dict)
        or not isinstance(invocation.get("name"), str)
        or not invocation.get("name")
    ):
        _issue(result, "invocation", "Named accelerator invocation is required")
        return result
    for field in ("elapsed_cycles", "elapsed_ticks"):
        if not _integer(invocation.get(field), positive=True):
            _issue(result, "invocation_" + field, "Positive integer required")
    units, events, claimed_totals = (
        data.get("units"),
        data.get("trace"),
        data.get("totals"),
    )
    if (
        not isinstance(units, list)
        or not units
        or not isinstance(events, list)
        or not isinstance(claimed_totals, dict)
    ):
        _issue(result, "structure", "Units, trace, and totals must be present")
        return result
    indexed, names = {}, set()
    for item in units:
        if not isinstance(item, dict):
            _issue(result, "unit", "Unit must be a mapping")
            continue
        uid, name = item.get("id"), item.get("name")
        if (
            not _integer(uid, positive=True)
            or not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name)
            or uid in indexed
            or name in names
        ):
            _issue(
                result,
                "unit_identity",
                "Unique positive ID and unit name required",
            )
            continue
        names.add(name)
        indexed[uid] = item
        for field in ("limit",) + COUNTERS:
            if not _integer(item.get(field)):
                _issue(
                    result,
                    "unit_counter",
                    "{}:{} must be unsigned integer".format(name, field),
                )
    if result["issues"]:
        return result
    observed = {
        uid: {
            "attempts": 0,
            "grants": 0,
            "denials": 0,
            "releases": 0,
            "peak": 0,
            "outstanding": 0,
        }
        for uid in indexed
    }
    leases, seen_leases = {}, set()
    last_grant_lease = 0
    previous_cycle, previous_tick = -1, -1
    global_peak = 0
    for index, event in enumerate(events):
        if not isinstance(event, dict) or not set(FIELDS) <= set(event):
            _issue(
                result,
                "event_shape",
                "Event {} lacks required fields".format(index),
            )
            continue
        kind, uid, lease = event["event"], event["fu_id"], event["lease_id"]
        cycle, tick = event["cycle"], event["tick"]
        if (
            not isinstance(kind, str)
            or kind not in EVENTS
            or not _integer(uid, positive=True)
            or uid not in indexed
            or not _integer(cycle, positive=True)
            or not _integer(tick)
            or not _integer(event["uid"])
            or not _integer(event["opcode"])
            or not _integer(lease)
        ):
            _issue(result, "event_value", "Invalid FU event {}".format(index))
            continue
        if (
            _integer(invocation.get("elapsed_cycles"))
            and cycle > invocation["elapsed_cycles"]
        ):
            _issue(
                result,
                "event_cycle_bounds",
                "Event is after invocation cycle end",
            )
        if cycle < previous_cycle or tick < previous_tick:
            _issue(
                result,
                "event_order",
                "Cycle/tick moved backward at event {}".format(index),
            )
        previous_cycle, previous_tick = cycle, tick
        count = observed[uid]
        limit = indexed[uid]["limit"]
        if kind == "grant":
            if lease == 0 or lease in seen_leases or lease <= last_grant_lease:
                _issue(
                    result,
                    "duplicate_lease",
                    "Grant lease must be new, positive, and increasing",
                )
            last_grant_lease = max(last_grant_lease, lease)
            if limit and count["outstanding"] >= limit:
                _issue(
                    result,
                    "over_capacity_grant",
                    "{} exceeded cap {}".format(indexed[uid]["name"], limit),
                )
            seen_leases.add(lease)
            leases[lease] = (uid, event["uid"], event["opcode"])
            count["attempts"] += 1
            count["grants"] += 1
            count["outstanding"] += 1
            count["peak"] = max(count["peak"], count["outstanding"])
        elif kind == "deny":
            if lease != 0 or limit == 0 or count["outstanding"] < limit:
                _issue(
                    result,
                    "invalid_denial",
                    "Denied attempt was not blocked by a full positive cap",
                )
            count["attempts"] += 1
            count["denials"] += 1
        else:
            if lease == 0 or leases.pop(lease, None) != (
                uid,
                event["uid"],
                event["opcode"],
            ):
                _issue(
                    result,
                    "unmatched_release",
                    "Release has no matching granted lease",
                )
            count["releases"] += 1
            count["outstanding"] -= 1
            if count["outstanding"] < 0:
                _issue(result, "underflow", "FU occupancy became negative")
        global_peak = max(global_peak, sum(v["outstanding"] for v in observed.values()))
        result["events_replayed"] += 1
    if leases:
        _issue(
            result,
            "outstanding_leases",
            "Grants remained unreleased at invocation end",
        )
    for uid, item in indexed.items():
        replay = observed[uid]
        name = item["name"]
        for field in COUNTERS:
            if replay[field] != item[field]:
                _issue(
                    result,
                    "counter_mismatch",
                    "{}.{} expected {} observed {}".format(
                        name, field, replay[field], item[field]
                    ),
                )
        if replay["outstanding"] != 0:
            _issue(result, "nonzero_final_occupancy", name)
        result["units"].append(
            {"id": uid, "name": name, "limit": item["limit"], **replay}
        )
    totals = {
        field: sum(value[field] for value in observed.values())
        for field in COUNTERS
        if field != "peak"
    }
    totals["peak"] = global_peak
    for field in COUNTERS:
        if (
            not _integer(claimed_totals.get(field))
            or claimed_totals[field] != totals[field]
        ):
            _issue(
                result,
                "total_mismatch",
                "Total {} does not match event replay".format(field),
            )
    result["totals"] = totals
    result["trace_complete"] = not result["issues"]
    result["state"] = "passed" if not result["issues"] else "failed"
    return result


def inspect_fu_invocation(path, config_ini=None):
    """Validate one direct SALAM FU JSON file and its adjacent lifecycle JSON."""
    source = Path(path)
    result = {
        "schema_version": 1,
        "kind": "salam_fu_invocation_witness",
        "state": "failed",
        "path": str(source),
        "issues": [],
        "trace": None,
        "source_sha256": None,
    }
    try:
        if not source.name.startswith(FU_PREFIX) or not source.name.endswith(".json"):
            raise ValueError("Expected fu-scheduling-<accelerator>.invocation-N.json")
        data = json.loads(source.read_text(encoding="utf-8"))
        result["source_sha256"] = _sha(source)
        replay = validate_fu_trace(data)
        result["trace"] = replay
        result["issues"].extend(replay["issues"])
        adjacent = source.with_name(source.name[len(FU_PREFIX) :])
        original = json.loads(adjacent.read_text(encoding="utf-8"))
        result["adjacent_lifecycle"] = {
            "path": str(adjacent),
            "sha256": _sha(adjacent),
        }
        lifecycle = original.get("lifecycle", {})
        if (
            original.get("accelerator") != data.get("invocation", {}).get("name")
            or original.get("valid") is not True
            or lifecycle.get("completed") is not True
            or lifecycle.get("elapsed_ticks")
            != data.get("invocation", {}).get("elapsed_ticks")
        ):
            _issue(
                result,
                "lifecycle_mismatch",
                "FU and existing SALAM invocation differ",
            )
        start, end = lifecycle.get("start_tick"), lifecycle.get("end_tick")
        if (
            not _integer(start)
            or not _integer(end)
            or end < start
            or end - start != data.get("invocation", {}).get("elapsed_ticks")
        ):
            _issue(
                result,
                "lifecycle_bounds",
                "Adjacent invocation has no valid tick bounds",
            )
        else:
            for index, event in enumerate(data.get("trace", [])):
                if (
                    not isinstance(event, dict)
                    or not _integer(event.get("tick"))
                    or not start <= event["tick"] <= end
                ):
                    _issue(
                        result,
                        "event_tick_bounds",
                        "Event {} lies outside adjacent invocation".format(index),
                    )
        if config_ini is not None:
            parser = _ini(config_ini)
            accelerator = data["invocation"]["name"]
            for unit in replay["units"]:
                section = accelerator + FU_SECTION + unit["name"]
                actual = parser.get(section, "limit", fallback=None)
                if actual != str(unit["limit"]):
                    _issue(
                        result,
                        "effective_limit",
                        "{} requested {}, config.ini {}".format(
                            section, unit["limit"], actual
                        ),
                    )
                if parser.get(section, "enum_value", fallback=None) != str(unit["id"]):
                    _issue(
                        result,
                        "effective_fu_id",
                        section + " enum differs from event FU ID",
                    )
            opcodes = {}
            prefix = accelerator + ".hw_interface.inst_config."
            for section in parser.sections():
                if section.startswith(prefix):
                    opcode = int(parser.get(section, "opcode_num"))
                    unit_id = int(parser.get(section, "functional_unit"))
                    if opcode in opcodes and opcodes[opcode] != unit_id:
                        raise ValueError("Ambiguous effective opcode/FU mapping")
                    opcodes[opcode] = unit_id
            period = lifecycle.get("clock_period_ticks")
            if not _integer(period, positive=True):
                _issue(result, "event_clock", "Lifecycle clock period is required")
            intercept = None
            grants = {}
            for event in data.get("trace", []):
                if not isinstance(event, dict) or not set(FIELDS) <= set(event):
                    continue
                if opcodes.get(event["opcode"]) != event["fu_id"]:
                    _issue(
                        result,
                        "effective_opcode_fu",
                        "Event opcode is not mapped to its claimed FU",
                    )
                if _integer(period, positive=True):
                    observed = event["tick"] - event["cycle"] * period
                    if intercept is None:
                        intercept = observed
                    elif observed != intercept:
                        _issue(
                            result,
                            "event_clock",
                            "Event tick/cycle progression differs from lifecycle clock",
                        )
                if event["event"] == "grant":
                    grants[event["lease_id"]] = event
                elif event["event"] == "release" and event["lease_id"] in grants:
                    grant = grants.pop(event["lease_id"])
                    # This study proves scalar nonpipelined multiply occupancy.
                    # cycle_counts is the consumed latency, not InstConfig.runtime_cycles.
                    if event["opcode"] == 17:
                        expected = int(
                            parser.get(accelerator + MUL_CYCLE_SECTION, "mul")
                        )
                        if event["cycle"] - grant["cycle"] != expected:
                            _issue(
                                result,
                                "multiply_lease_duration",
                                "Multiply lease did not span its effective cycle count",
                            )
            result["config_ini"] = {
                "path": str(config_ini),
                "sha256": _sha(config_ini),
            }
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        json.JSONDecodeError,
        configparser.Error,
    ) as error:
        _issue(
            result,
            "invalid_evidence",
            type(error).__name__ + ": " + str(error),
        )
    result["state"] = "passed" if not result["issues"] else "failed"
    return result


STUDY_CASES = {
    "unlimited": (0, 0),
    "cap1": (1, 0),
    "cap2": (2, 0),
    "unused": (0, 1),
}
STUDY_INPUTS = (
    "config.yml",
    "hw/gemm.c",
    "hw/gemm.ll",
    "hw/top.c",
    "hw/top.ll",
    "sw/main.cpp",
    "sw/main.elf",
)


def _load_image_identity(elf_path):
    """Bind the ELF32 ARM loaded segments, entry point and zero-fill metadata."""
    payload = Path(elf_path).read_bytes()
    if len(payload) < 52 or payload[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError("Expected little-endian ELF32 version 1")
    fields = struct.unpack_from("<HHIIIIIHHHHHH", payload, 16)
    (
        typ,
        machine,
        version,
        entry,
        phoff,
        _,
        flags,
        ehsize,
        phsize,
        phnum,
    ) = fields[:10]
    if (
        (typ, machine, version) != (2, 40, 1)
        or ehsize != 52
        or phsize != 32
        or not phnum
    ):
        raise ValueError("Expected ARM ET_EXEC with ordinary ELF32 program headers")
    if phoff + phnum * phsize > len(payload):
        raise ValueError("ELF program headers exceed file")
    segments = []
    for index in range(phnum):
        (
            kind,
            offset,
            vaddr,
            paddr,
            filesz,
            memsz,
            mode,
            alignment,
        ) = struct.unpack_from("<IIIIIIII", payload, phoff + index * phsize)
        if kind != 1:
            continue
        if filesz > memsz or offset + filesz > len(payload) or paddr + memsz > 2**32:
            raise ValueError("Invalid ARM PT_LOAD bounds")
        segments.append(
            {
                "vaddr": vaddr,
                "paddr": paddr,
                "filesz": filesz,
                "memsz": memsz,
                "flags": mode,
                "alignment": alignment,
                "file_bytes_sha256": hashlib.sha256(
                    payload[offset : offset + filesz]
                ).hexdigest(),
            }
        )
    if not segments or not any(
        s["flags"] & 1 and s["vaddr"] <= (entry & ~1) < s["vaddr"] + s["memsz"]
        for s in segments
    ):
        raise ValueError("Entry point is not in an executable PT_LOAD segment")
    identity = {
        "format": "ELF32_ARM_ET_EXEC",
        "osabi": payload[7],
        "abi_version": payload[8],
        "entry": entry,
        "elf_flags": flags,
        "segments": segments,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return {
        "load_image_sha256": hashlib.sha256(canonical).hexdigest(),
        "load_image_bytes": sum(s["filesz"] for s in segments),
        "elf_load_contract": identity,
    }


def _verify_engine_binding(engine, raw):
    claimed = engine["binary"]["sha256"]
    if raw.get("executable", {}).get("sha256") != claimed:
        raise ValueError("Configured engine differs from actual run executable")
    build_path = Path(engine["receipt"]["path"])
    if _sha(build_path) != engine["receipt"]["sha256"]:
        raise ValueError("Configured engine build receipt hash mismatch")
    build = json.loads(build_path.read_text())
    source_path = build_path.parent / "source-inputs.json"
    source = json.loads(source_path.read_text())
    digest = hashlib.sha256(
        json.dumps(source["files"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if (
        build.get("state") != "built"
        or build.get("binary", {}).get("sha256") != claimed
        or build.get("compiled_source_sha256") != engine.get("compiled_source_sha256")
        or _sha(source_path) != build.get("source_inputs_sha256")
        or digest != source.get("sha256")
        or digest != engine.get("compiled_source_sha256")
    ):
        raise ValueError("Compiled source/build/binary identities are inconsistent")


def _raw_inputs(raw, run_dir, workspace, wanted):
    """Require immutable run-local snapshots for the exact executed inputs."""
    values = {}
    for relative in wanted:
        path = (workspace / "benchmarks/sys_validation/gemm" / relative).resolve()
        # Runner records canonical absolute paths. Do not perform thousands of
        # redundant filesystem resolutions for every critical input.
        matches = [
            r for r in raw.get("inputs", []) if str(Path(r["path"])) == str(path)
        ]
        if len(matches) != 1 or not matches[0].get("snapshot"):
            raise ValueError("Expected one snapshotted critical input: " + relative)
        item = matches[0]
        snapshot = (run_dir / item["snapshot"]["path"]).resolve()
        snapshot.relative_to(run_dir.resolve())
        if (
            item["sha256"] != item["snapshot"]["sha256"]
            or _sha(snapshot) != item["sha256"]
            or _sha(path) != item["sha256"]
        ):
            raise ValueError("Critical input differs from run snapshot: " + relative)
        values[relative] = item["sha256"]
    return values


def _effective_identity(parser, workspace):
    """Normalize only the exact local workspace prefix and two intended caps."""
    root = workspace.resolve().as_posix()
    result = {}
    for section in parser.sections():
        result[section] = {}
        for key, value in parser.items(section):
            if key == "limit" and section in (
                "system.gemm_clstr.gemm" + FU_SECTION + GEMM_MULTIPLIER,
                "system.gemm_clstr.gemm" + FU_SECTION + UNUSED_UNIT,
            ):
                continue
            # Absolute workspace paths are emitted as scalar file parameters.
            portable = value.replace("\\", "/")
            if portable == root or portable.startswith(root + "/"):
                value = "<WORKSPACE>" + portable[len(root) :]
            result[section][key] = value
    return result


def _bind_executed_paths(parser, workspace, raw, run_dir, kernel="sw/main.elf"):
    workspace = workspace.resolve()
    expected = {
        "system.workload": ("object_file", kernel),
        "system.gemm_clstr.gemm.llvm_interface": ("in_file", "hw/gemm.ll"),
        "system.gemm_clstr.top.llvm_interface": ("in_file", "hw/top.ll"),
    }
    for section, (field, relative) in expected.items():
        actual = parser.get(section, field, fallback=None)
        target = workspace / "benchmarks/sys_validation/gemm" / relative
        if actual is None or Path(actual).resolve() != target:
            raise ValueError(
                "Effective executed input differs: " + section + "." + field
            )
    return _raw_inputs(raw, run_dir, workspace, set(STUDY_INPUTS) | {kernel})


def _canonical_study_spec(spec, result):
    """Remove only the requested FU limit and descriptive metadata."""
    normalized = json.loads(json.dumps(spec, allow_nan=False))
    if not isinstance(normalized, dict):
        _issue(result, "specification", "Study specification must be a mapping")
        return None
    if normalized.get("name") != "gemm":
        _issue(
            result,
            "specification_name",
            "All runs must use the same generated system name",
        )
    normalized.pop("name", None)
    correctness = normalized.get("correctness")
    if isinstance(correctness, dict):
        correctness.pop("description", None)
    parameters = normalized.get("parameters", {})
    if not isinstance(parameters, dict):
        _issue(
            result,
            "specification_parameters",
            "Parameter requests must be a mapping",
        )
        return None
    for section in list(parameters):
        if section in (
            "system.gemm_clstr.gemm" + FU_SECTION + GEMM_MULTIPLIER,
            "system.gemm_clstr.gemm" + FU_SECTION + UNUSED_UNIT,
        ):
            fields = parameters[section]
            if not isinstance(fields, dict):
                _issue(
                    result,
                    "specification_parameters",
                    section + " must be a mapping",
                )
                continue
            fields.pop("limit", None)
            if not fields:
                del parameters[section]
    return normalized


def _study_input_hashes(records, result):
    """Bind the executable, IR, and independent CPU oracle to their receipts."""
    found = {}
    if not isinstance(records, list):
        _issue(result, "input_receipt", "Missing prepared-inputs list")
        return found
    for suffix in STUDY_INPUTS:
        matches = [
            record
            for record in records
            if isinstance(record, dict)
            and str(record.get("path", ""))
            .replace("\\", "/")
            .endswith("/benchmarks/sys_validation/gemm/" + suffix)
        ]
        if len(matches) != 1:
            _issue(result, "study_input", "Expected exactly one " + suffix)
            continue
        record = matches[0]
        path = Path(record["path"])
        claimed = record.get("sha256")
        if not path.is_file() or _sha(path) != claimed:
            _issue(
                result,
                "input_hash",
                suffix + " differs from prepared-inputs receipt",
            )
        found[suffix] = claimed
    return found


def inspect_fu_run(pipeline_dir, case):
    """Inspect one already completed GEMM run without trusting a pass label alone."""
    root = Path(pipeline_dir)
    result = {
        "schema_version": 1,
        "kind": "salam_fu_study_run",
        "state": "failed",
        "case": case,
        "evidence_directory": str(root),
        "issues": [],
        "fu_witness": None,
    }
    if case not in STUDY_CASES:
        _issue(result, "case", "Unknown study case")
        return result
    try:
        receipt = json.loads((root / "configuration.json").read_text(encoding="utf-8"))
        spec = json.loads((root / "specification.json").read_text(encoding="utf-8"))
        result["specification"] = spec
        prepared = json.loads(
            (root / "prepared-inputs.json").read_text(encoding="utf-8")
        )
        effective = json.loads(
            (root / "contract-effective.json").read_text(encoding="utf-8")
        )
        if (
            receipt.get("state") != "passed"
            or receipt.get("run_state") != "passed"
            or receipt.get("numerical_correctness") != "guest_checker_passed"
            or effective.get("valid") is not True
        ):
            _issue(
                result,
                "run_not_verified",
                "Pipeline, numerical oracle, or effective contract failed",
            )
        if spec.get("benchmark") != "benchmarks/sys_validation/gemm":
            _issue(result, "wrong_workload", "Study requires recovered GEMM")
        engine = receipt.get("engine", {})
        result["engine_identity"] = {
            "binary_sha256": engine.get("binary", {}).get("sha256"),
            "compiled_source_sha256": engine.get("compiled_source_sha256"),
        }
        if not all(
            isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
            for value in result["engine_identity"].values()
        ):
            _issue(result, "engine_identity", "Missing compiled engine identity")
        result["input_hashes"] = _study_input_hashes(prepared, result)
        result["load_image"] = _load_image_identity(
            root / "workspace/benchmarks/sys_validation/gemm/sw/main.elf"
        )
        result["canonical_specification"] = _canonical_study_spec(spec, result)
        run_directory = Path(receipt["run_directory"])
        if run_directory.parent.resolve() != (root / "runs").resolve():
            _issue(
                result,
                "run_path",
                "Run directory does not belong to pipeline evidence",
            )
        sim = run_directory / "simulator"
        ini_path = sim / "config.ini"
        parser = _ini(ini_path)
        run_receipt = json.loads(
            (run_directory / "run.json").read_text(encoding="utf-8")
        )
        from salam_workbench.report import load_run

        loaded = load_run(run_directory)
        result["raw_run_id"] = run_receipt.get("run_id")
        if not result["raw_run_id"] or not loaded["correctness_verified"]:
            _issue(result, "raw_revalidation", repr(loaded["issues"]))
        _verify_engine_binding(engine, run_receipt)
        workspace = root / "workspace"
        snapshot_hashes = _bind_executed_paths(
            parser, workspace, run_receipt, run_directory
        )
        if any(
            snapshot_hashes.get(key) != value
            for key, value in result["input_hashes"].items()
        ):
            _issue(
                result,
                "input_snapshot_binding",
                "Prepared inputs differ from actual run snapshots",
            )
        result["effective_configuration"] = _effective_identity(parser, workspace)
        correctness = run_receipt.get("correctness", {})
        if (
            run_receipt.get("state") != "passed"
            or correctness.get("outcome") != "passed"
            or correctness.get("passed_markers") != 1
            or correctness.get("failed_markers") != 0
            or correctness.get("guest_output") != "simulator/system.terminal"
        ):
            _issue(
                result,
                "raw_run",
                "Raw run receipt or independent guest marker failed",
            )
        paths = list(
            (sim / "observability").glob(FU_PREFIX + "*.gemm.invocation-1.json")
        )
        if len(paths) != 1:
            _issue(
                result,
                "fu_file",
                "Expected one direct GEMM FU invocation file",
            )
            return result
        fu = inspect_fu_invocation(paths[0], ini_path)
        result["fu_witness"] = fu
        if fu["state"] != "passed":
            _issue(result, "fu_replay", "Direct SALAM trace did not replay")
        direct = json.loads(paths[0].read_text(encoding="utf-8"))
        accelerator = direct["invocation"]["name"]
        mul_cycles = parser.get(accelerator + MUL_CYCLE_SECTION, "mul", fallback=None)
        if mul_cycles != "16":
            _issue(result, "mul_latency", "Effective mul cycle count is not 16")
        expected_mul, expected_unused = STUDY_CASES[case]
        units = {unit["name"]: unit for unit in fu["trace"]["units"]}
        for name, expected in (
            (GEMM_MULTIPLIER, expected_mul),
            (UNUSED_UNIT, expected_unused),
        ):
            if name not in units or units[name]["limit"] != expected:
                _issue(
                    result,
                    "study_limit",
                    "{} limit is not {}".format(name, expected),
                )
            section = accelerator + FU_SECTION + name
            request = spec.get("parameters", {}).get(section, {}).get("limit")
            if request != expected and (
                name == GEMM_MULTIPLIER or case == "unused" or request is not None
            ):
                _issue(
                    result,
                    "request_limit",
                    "{} request differs from case".format(name),
                )
        result["accelerator"] = accelerator
        result["elapsed_ticks"] = direct["invocation"]["elapsed_ticks"]
        result["elapsed_cycles"] = direct["invocation"]["elapsed_cycles"]
        result["multiplier"] = units.get(GEMM_MULTIPLIER)
        result["unused_unit"] = units.get(UNUSED_UNIT)
        result["run_directory"] = str(run_directory)
        terminal = sim / "system.terminal"
        transcript = terminal.read_text(encoding="utf-8", errors="replace")
        result["terminal_sha256"] = _sha(terminal)
        if transcript.count("Check Passed") != 1 or "Check Failed" in transcript:
            _issue(
                result,
                "numeric_oracle",
                "Independent CPU GEMM checker did not pass exactly once",
            )
        artifact_claims = {
            item.get("path"): item.get("sha256")
            for item in run_receipt.get("artifacts", [])
            if isinstance(item, dict)
        }
        required = {
            item.get("path"): item.get("available")
            for item in run_receipt.get("required_artifact_checks", [])
            if isinstance(item, dict)
        }
        required_artifacts = (
            "simulator/system.terminal",
            "simulator/config.ini",
            "simulator/observability/" + paths[0].name,
        )
        artifacts = required_artifacts + (
            "simulator/observability/" + paths[0].name[len(FU_PREFIX) :],
        )
        for artifact in artifacts:
            path = run_directory / artifact
            if (
                artifact in required_artifacts and required.get(artifact) is not True
            ) or artifact_claims.get(artifact) != _sha(path):
                _issue(
                    result,
                    "raw_artifact_hash",
                    artifact + " not bound to raw run receipt",
                )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        configparser.Error,
    ) as error:
        _issue(
            result,
            "invalid_evidence",
            type(error).__name__ + ": " + str(error),
        )
    result["state"] = "passed" if not result["issues"] else "failed"
    return result


def inspect_negative_control(pipeline_or_run_dir, baseline=None):
    """Verify a wrong-output guest was rejected by the raw run assessor."""
    source = Path(pipeline_or_run_dir)
    result = {
        "schema_version": 1,
        "kind": "salam_fu_wrong_output_control",
        "state": "failed",
        "path": str(source),
        "issues": [],
    }
    try:
        if (source / "configuration.json").is_file():
            pipeline = json.loads(
                (source / "configuration.json").read_text(encoding="utf-8")
            )
            run_dir = Path(pipeline["run_directory"])
            if (
                pipeline.get("state") == "passed"
                or pipeline.get("run_state") == "passed"
                or pipeline.get("numerical_correctness") == "guest_checker_passed"
            ):
                _issue(
                    result,
                    "pipeline_accepted",
                    "Pipeline accepted wrong output",
                )
        else:
            run_dir = source
        raw = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        from salam_workbench.report import load_run

        loaded = load_run(run_dir)
        permitted = {
            "Run state is not passed: failed",
            "Raw guest correctness evidence or recorded process exit does not satisfy the runner contract",
        }
        if any(issue not in permitted for issue in loaded["issues"]):
            _issue(result, "negative_raw_revalidation", repr(loaded["issues"]))
        terminal = run_dir / "simulator/system.terminal"
        text = terminal.read_text(encoding="utf-8", errors="replace")
        correctness = raw.get("correctness", {})
        if (
            raw.get("state") != "failed"
            or correctness.get("outcome") != "failed"
            or correctness.get("failed_markers", 0) < 1
            or correctness.get("passed_markers") != 0
            or text.count("Check Failed") < 1
            or "Check Passed" in text
        ):
            _issue(
                result,
                "raw_accepted",
                "Raw simulator run did not reject wrong output",
            )
        artifacts = {
            item.get("path"): item.get("sha256")
            for item in raw.get("artifacts", [])
            if isinstance(item, dict)
        }
        required = {
            item.get("path"): item.get("available")
            for item in raw.get("required_artifact_checks", [])
            if isinstance(item, dict)
        }
        if required.get("simulator/system.terminal") is not True or artifacts.get(
            "simulator/system.terminal"
        ) != _sha(terminal):
            _issue(
                result,
                "raw_artifact_hash",
                "Terminal is not bound to raw failed run",
            )
        result["run_directory"] = str(run_dir)
        result["terminal_sha256"] = _sha(terminal)
        result["raw_run_sha256"] = _sha(run_dir / "run.json")
        result["raw_run_id"] = raw.get("run_id")
        if not result["raw_run_id"]:
            raise ValueError("Negative run lacks recorded ID")
        if baseline is not None:
            pipeline = json.loads((source / "configuration.json").read_text())
            if pipeline.get("kind") != "configuration_fault_injection":
                raise ValueError("Expected deliberate fault-injection pipeline")
            _verify_engine_binding(pipeline["engine"], raw)
            identity = {
                "binary_sha256": pipeline["engine"]["binary"]["sha256"],
                "compiled_source_sha256": pipeline["engine"]["compiled_source_sha256"],
            }
            if identity != baseline["engine_identity"]:
                raise ValueError("Negative control used a different engine")
            spec = json.loads((source / "preparation/specification.json").read_text())
            if spec != baseline["specification"]:
                raise ValueError(
                    "Negative control did not prepare the cap-one specification"
                )
            workspace = source / "preparation/workspace"
            parser = _ini(run_dir / "simulator/config.ini")
            hashes = _bind_executed_paths(
                parser,
                workspace,
                raw,
                run_dir,
                kernel="sw/main-workbench-mismatch.elf",
            )
            for key, value in baseline["input_hashes"].items():
                if key != "sw/main.elf" and hashes.get(key) != value:
                    raise ValueError("Negative control changed source/IR: " + key)
            effective = _effective_identity(parser, workspace)
            effective["system.workload"][
                "object_file"
            ] = "<WORKSPACE>/benchmarks/sys_validation/gemm/sw/main.elf"
            if effective != baseline["effective_configuration"]:
                raise ValueError("Negative control changed effective system settings")
            for unit, limit in ((GEMM_MULTIPLIER, 1), (UNUSED_UNIT, 0)):
                if parser.get(
                    "system.gemm_clstr.gemm" + FU_SECTION + unit, "limit"
                ) != str(limit):
                    raise ValueError("Negative control is not the cap-one control")
            witness = loaded["experiment"].get("negative_witness", {})
            if witness.get("compile_flag") != "-DWORKBENCH_INJECT_MISMATCH":
                raise ValueError(
                    "Negative control lacks explicit mismatch macro declaration"
                )
            compile_path = source / "mismatch-build/compile-mismatch.json"
            link_path = source / "mismatch-build/link-mismatch.json"
            compile_record = json.loads(compile_path.read_text())
            link_record = json.loads(link_path.read_text())
            sw = workspace / "benchmarks/sys_validation/gemm/sw"
            for command in (compile_record, link_record):
                if (
                    command.get("state") != "completed"
                    or command.get("return_code") != 0
                    or Path(command["cwd"]).resolve() != sw.resolve()
                ):
                    raise ValueError(
                        "Negative compile/link command did not complete in its source directory"
                    )
            argv = compile_record["argv"]
            if (
                "-DWORKBENCH_INJECT_MISMATCH" not in argv
                or "main.cpp" not in argv
                or argv[argv.index("-o") + 1] != "main-workbench-mismatch.o"
            ):
                raise ValueError("Mismatch macro was not used to compile the guest")
            argv = link_record["argv"]
            if (
                "main-workbench-mismatch.o" not in argv
                or argv[argv.index("-o") + 1] != "main-workbench-mismatch.elf"
            ):
                raise ValueError(
                    "Mismatch object was not linked into the executed guest"
                )
            main = (sw / "main.cpp").read_text()
            if not re.search(
                r"#ifdef WORKBENCH_INJECT_MISMATCH\s+(?://[^\n]*\n\s*)?m3\[0\]\s*\^=\s*1;\s*#endif",
                main,
            ):
                raise ValueError(
                    "Bound source does not contain the reviewed XOR fault injection"
                )
            if _load_image_identity(sw / "main.elf") != baseline["load_image"]:
                raise ValueError("Negative preparation baseline load image differs")
            if (
                _load_image_identity(sw / "main-workbench-mismatch.elf")
                == baseline["load_image"]
            ):
                raise ValueError("Executed negative image did not differ from baseline")
            result["binding"] = {
                "engine": identity,
                "compile_receipt_sha256": _sha(compile_path),
                "link_receipt_sha256": _sha(link_path),
                "source_and_ir_match_cap1": True,
            }
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        _issue(
            result,
            "invalid_negative_evidence",
            type(error).__name__ + ": " + str(error),
        )
    result["state"] = "passed" if not result["issues"] else "failed"
    return result


def verify_fu_study(cases, negative_pipeline_dir=None):
    """Assess two independent repeats for each controlled FU capacity.

    The conclusion is inconclusive when recorded controls are valid but the
    observed accelerator trace does not show contention and timing response.
    """
    result = {
        "schema_version": 1,
        "kind": "salam_fu_scheduling_study",
        "state": "failed",
        "issues": [],
        "runs": {},
        "measurements": {},
        "negative_control": None,
    }
    if not isinstance(cases, dict) or set(cases) != set(STUDY_CASES):
        _issue(
            result,
            "study_shape",
            "Cases must be unlimited, cap1, cap2, unused",
        )
        return result
    identities = []
    pipeline_paths, run_paths, run_ids = set(), set(), set()
    for case in STUDY_CASES:
        paths = cases[case]
        if not isinstance(paths, (list, tuple)) or len(paths) != 2:
            _issue(result, "repeats", case + " requires exactly two runs")
            continue
        for path in paths:
            resolved = str(Path(path).resolve())
            if resolved in pipeline_paths:
                _issue(
                    result,
                    "duplicate_pipeline",
                    "Each repeat must have its own evidence directory",
                )
            pipeline_paths.add(resolved)
        runs = [inspect_fu_run(path, case) for path in paths]
        result["runs"][case] = runs
        for run in runs:
            if run["state"] != "passed":
                _issue(result, "run_failed", case + " has invalid evidence")
            else:
                if run["run_directory"] in run_paths or run["raw_run_id"] in run_ids:
                    _issue(
                        result,
                        "duplicate_run",
                        "Each repeat must have a distinct run directory and recorded ID",
                    )
                run_paths.add(run["run_directory"])
                run_ids.add(run["raw_run_id"])
                identities.append(
                    {
                        "engine_identity": run["engine_identity"],
                        "source_and_ir_hashes": {
                            key: value
                            for key, value in run["input_hashes"].items()
                            if key != "sw/main.elf"
                        },
                        "load_image": run["load_image"],
                        "canonical_specification": run["canonical_specification"],
                        "effective_configuration": run["effective_configuration"],
                        "accelerator": run["accelerator"],
                    }
                )
    if result["issues"]:
        return result
    if any(item != identities[0] for item in identities[1:]):
        _issue(
            result,
            "varying_inputs",
            "Compiled engine, IR, guest, or topology changed across cases",
        )
        return result
    if negative_pipeline_dir is None:
        _issue(
            result,
            "negative_control_missing",
            "A bound wrong-output control is required",
        )
    else:
        result["negative_control"] = inspect_negative_control(
            negative_pipeline_dir, result["runs"]["cap1"][0]
        )
        if result["negative_control"]["state"] != "passed":
            _issue(
                result,
                "negative_control_invalid",
                "Wrong-output rejection was not proven",
            )
        elif (
            result["negative_control"]["run_directory"] in run_paths
            or result["negative_control"]["raw_run_id"] in run_ids
        ):
            _issue(
                result,
                "duplicate_negative",
                "Negative control must have its own recorded run",
            )
    if result["issues"]:
        return result
    for case, runs in result["runs"].items():
        result["measurements"][case] = {
            "elapsed_ticks": [run["elapsed_ticks"] for run in runs],
            "multiplier_peak": [run["multiplier"]["peak"] for run in runs],
            "multiplier_grants": [run["multiplier"]["grants"] for run in runs],
            "multiplier_denials": [run["multiplier"]["denials"] for run in runs],
            "unused_grants": [run["unused_unit"]["grants"] for run in runs],
        }
    measure = result["measurements"]
    inconclusive = []
    for case, values in measure.items():
        for field, observations in values.items():
            if observations[0] != observations[1]:
                inconclusive.append("{} repeats differ for {}".format(case, field))
    if any(
        value != measure["unlimited"]["multiplier_grants"][0]
        for case in STUDY_CASES
        for value in measure[case]["multiplier_grants"]
    ):
        inconclusive.append("Dynamic multiply grant count changed across controls")
    if any(
        value != 8 * 8 * 8
        for case in STUDY_CASES
        for value in measure[case]["multiplier_grants"]
    ):
        _issue(
            result,
            "multiply_oracle",
            "Reviewed 8x8x8 GEMM requires exactly 512 multiply grants",
        )
    if (
        max(measure["unlimited"]["multiplier_peak"]) < 2
        or max(measure["cap2"]["multiplier_peak"]) < 2
    ):
        inconclusive.append("No observed overlap of two multipliers")
    if any(peak > 1 for peak in measure["cap1"]["multiplier_peak"]) or any(
        peak > 2 for peak in measure["cap2"]["multiplier_peak"]
    ):
        _issue(result, "capacity_breach", "Observed peak exceeds positive cap")
    if min(measure["cap1"]["multiplier_denials"]) == 0:
        inconclusive.append("Cap one produced no denied issue attempts")
    if any(
        value != 0
        for case in ("unlimited", "unused")
        for value in measure[case]["multiplier_denials"]
    ):
        _issue(result, "unlimited_denial", "Unlimited multiplier denied an issue")
    if any(value != 0 for value in measure["unused"]["unused_grants"]):
        inconclusive.append("Supposedly unused double divider was exercised")
    if min(measure["cap1"]["elapsed_ticks"]) <= max(measure["cap2"]["elapsed_ticks"]):
        inconclusive.append(
            "Cap one was not slower than cap two in both accelerator repeats"
        )
    if min(measure["cap1"]["elapsed_ticks"]) <= max(
        measure["unlimited"]["elapsed_ticks"]
    ):
        inconclusive.append(
            "Cap one was not slower than unlimited in both accelerator repeats"
        )
    if (
        measure["unused"]["elapsed_ticks"] != measure["unlimited"]["elapsed_ticks"]
        or measure["unused"]["multiplier_grants"]
        != measure["unlimited"]["multiplier_grants"]
    ):
        inconclusive.append(
            "Unused-unit control changed multiplier behavior or elapsed ticks"
        )
    result["inconclusive_reasons"] = inconclusive
    result["state"] = (
        "failed" if result["issues"] else ("inconclusive" if inconclusive else "passed")
    )
    return result
