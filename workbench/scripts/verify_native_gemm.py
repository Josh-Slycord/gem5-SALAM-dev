#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Compare saved retained/direct GEMM runs using raw numerical and event evidence.

No guest/checker pass flag is consumed. A report verifies saved artifacts,
not cryptographic proof that a simulator process executed. The run driver
must preserve its command, executable identity, inputs and output artifacts.
"""
import argparse
import configparser
import datetime
import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH_FIELDS = {"in_file", "object_file", "image_file"}
ACTORS = ("system.gemm_clstr.top", "system.gemm_clstr.gemm")
CLOCK_ACTORS = (
    ACTORS
    + tuple(name + ".llvm_interface" for name in ACTORS)
    + ("system.gemm_clstr.dma",)
)
_HASH_CACHE = {}


def _helper(name, relative):
    path = ROOT / relative
    before = _file_record(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if _file_record(path)["sha256"] != before["sha256"]:
        raise ValueError("Checker implementation changed during import")
    return module, before


def _identity(item):
    return (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )


def _file_record(path, maximum=2 * 1024**3):
    """Hash bounded regular files without accepting a symlink or mid-read edit."""
    path = Path(path).absolute()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ValueError("Not a bounded regular file: " + str(path))
        key = (str(path), _identity(before))
        if key in _HASH_CACHE:
            return dict(_HASH_CACHE[key])
        digest = hashlib.sha256()
        length = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            length += len(chunk)
            if length > maximum:
                raise ValueError("Source exceeded bounded reader limit")
            digest.update(chunk)
        after = os.fstat(descriptor)
        if _identity(before) != _identity(after) or length != before.st_size:
            raise ValueError("Source changed during read: " + str(path))
        result = {
            "path": str(path),
            "sha256": digest.hexdigest(),
            "bytes": length,
        }
        _HASH_CACHE[key] = result
        return dict(result)
    finally:
        os.close(descriptor)


def _load_helpers():
    numpy_checker, numpy_source = _helper(
        "native_gemm_numpy", "workbench/scripts/verify_numpy_outputs.py"
    )
    stats_checker, stats_source = _helper(
        "native_gemm_stats", "src/hwacc/tests/verify_native_stats.py"
    )
    fu_checker, fu_source = _helper(
        "native_gemm_fu", "workbench/salam_workbench/fu_experiments.py"
    )
    return (
        numpy_checker,
        stats_checker,
        fu_checker,
        {
            "numpy": numpy_source,
            "native_statistics": stats_source,
            "fu_event_replay": fu_source,
        },
    )


def extract_result_frames(payload):
    """Extract only whole result frames; reject extra/partial protocol rows."""
    text = payload.decode("ascii").replace("\r\n", "\n")
    if "\r" in text:
        raise ValueError("Unexpected carriage return in result transport")
    frames, active = [], None
    for line in text.split("\n"):
        if line.startswith("SALAM_RESULT_BEGIN "):
            if active is not None:
                raise ValueError("Nested result frame")
            active = [line]
        elif line.startswith("SALAM_RESULT_END "):
            if active is None:
                raise ValueError("Result end without begin")
            active.append(line)
            frames.append(("\n".join(active) + "\n").encode("ascii"))
            active = None
        elif line.startswith("SALAM_RESULT "):
            if active is None:
                raise ValueError("Result row outside frame")
            active.append(line)
        elif active is not None:
            raise ValueError("Non-protocol row inside result frame")
    if active is not None:
        raise ValueError("Incomplete result frame")
    if not frames:
        raise ValueError("No complete numerical output frame")
    return frames


def verify_numerical(fixture_paths, output_payload, numpy_checker):
    frames = extract_result_frames(output_payload)
    if len(frames) != len(fixture_paths):
        raise ValueError("Result-frame count does not match fixture count")
    results, hashes = [], set()
    for index, (fixture_path, frame) in enumerate(zip(fixture_paths, frames), 1):
        payload, source = numpy_checker.read_snapshot(fixture_path, 2 * 1024**2)
        fixture = numpy_checker.load_fixture(payload)
        if fixture["benchmark"] != "gemm":
            raise ValueError("Only fixed-shape GEMM fixtures are supported")
        if fixture["fixture_sha256"] in hashes:
            raise ValueError("Each launch requires a distinct fixture identity")
        hashes.add(fixture["fixture_sha256"])
        observed, bits = numpy_checker.parse_observed(frame, fixture)
        expected = numpy_checker.expected_outputs(fixture)
        comparison = numpy_checker.compare_vectors(expected, observed, "int32")
        comparison.update(
            invocation=index,
            fixture=source,
            fixture_sha256=fixture["fixture_sha256"],
            observed_bits_sha256=hashlib.sha256(bits).hexdigest(),
        )
        results.append(comparison)
    return results


def _read_ini(path, numpy_checker):
    payload, source = numpy_checker.read_snapshot(path, 16 * 1024**2)
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read_string(payload.decode("utf-8"))
    if not parser.sections():
        raise ValueError("Effective config.ini has no sections")
    return parser, source


def compare_effective_configs(left_path, right_path):
    """Compare every effective key; normalize only children and same-byte inputs."""
    numpy_checker, _, _, _ = _load_helpers()
    left, left_source = _read_ini(left_path, numpy_checker)
    right, right_source = _read_ini(right_path, numpy_checker)
    differences, equal_files, child_orders = [], [], []

    def add(section, key, first, second):
        differences.append(
            {
                "section": section,
                "parameter": key,
                "retained": first,
                "direct": second,
            }
        )

    for section in sorted(set(left.sections()) | set(right.sections())):
        if section not in left or section not in right:
            add(section, None, section in left, section in right)
            continue
        for key in sorted(set(left[section]) | set(right[section])):
            first, second = left[section].get(key), right[section].get(key)
            if first == second:
                continue
            if key == "children" and first is not None and second is not None:
                if sorted(first.split()) == sorted(second.split()):
                    child_orders.append({"section": section, "parameter": key})
                    continue
            if key in INPUT_PATH_FIELDS and first and second:
                try:
                    a, b = _file_record(first), _file_record(second)
                except (OSError, ValueError):
                    pass
                else:
                    if a["sha256"] == b["sha256"]:
                        equal_files.append(
                            {
                                "section": section,
                                "parameter": key,
                                "retained": a,
                                "direct": b,
                            }
                        )
                        continue
            add(section, key, first, second)
    return {
        "state": "passed" if not differences else "failed",
        "scope": "All effective config.ini sections and parameters",
        "retained_source": left_source,
        "direct_source": right_source,
        "difference_count": len(differences),
        "differences": differences,
        "equivalent_file_identities": equal_files,
        "equivalent_child_orderings": child_orders,
        "excluded_parameters": [],
    }


def _run_receipt(run, stats_checker):
    payload, source = stats_checker.read_snapshot(run / "run.json", 64 * 1024**2)
    record = stats_checker.strict_json(payload)
    if type(record.get("return_code")) is not int or record["return_code"] != 0:
        raise ValueError("Simulator process did not return zero")
    if (
        record.get("simulator_exit", {}).get("reason")
        != "m5_exit instruction encountered"
    ):
        raise ValueError("Missing expected m5_exit event")
    if Path(record.get("run_directory", "")).resolve() != run.resolve():
        raise ValueError("Run receipt belongs to a different evidence directory")
    executable = record.get("executable", {})
    binary = _file_record(executable["path"])
    if (
        binary["sha256"] != executable.get("sha256")
        or binary["sha256"] != executable.get("sha256_after_run")
        or not record.get("argv")
        or Path(record["argv"][0]).absolute() != Path(binary["path"])
    ):
        raise ValueError("Run executable identity does not match actual binary")
    return {
        "source": source,
        "binary": binary,
        "argv": record["argv"],
        "return_code": record["return_code"],
        "simulator_exit": record["simulator_exit"],
        "process_id": record.get("process_id"),
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at"),
        "claims_not_consumed": ["state", "correctness", "required_artifact_checks"],
    }


def verify_run(
    run_directory,
    fixture_paths,
    *,
    expected_period_ns,
    expected_mul_limit=None,
    expected_mul_cycles=None,
):
    """Recompute numerical, effective-clock, reset-window and lease checks."""
    report = {
        "schema_version": 1,
        "kind": "native_gemm_run_evidence",
        "state": "failed",
        "run_directory": str(Path(run_directory).absolute()),
        "errors": [],
    }
    try:
        numpy_checker, stats_checker, fu_checker, helpers = _load_helpers()
        report["implementations"] = helpers
        run = Path(run_directory).absolute()
        simulator = run / "simulator"
        parser, report["effective_config"] = _read_ini(
            simulator / "config.ini", numpy_checker
        )
        report["execution_receipt"] = _run_receipt(run, stats_checker)
        stats_bytes, report["stats_source"] = stats_checker.read_snapshot(
            simulator / "stats.txt", 64 * 1024**2
        )
        blocks = stats_checker.parse_blocks(stats_bytes.decode("utf-8"))
        frequency = stats_checker.integer(blocks[0]["simFreq"], "simFreq")
        if (
            type(expected_period_ns) is not int
            or expected_period_ns < 1
            or frequency < 1
            or expected_period_ns * frequency % 10**9
        ):
            raise ValueError("Expected integer nanoseconds need an exact tick period")
        period = expected_period_ns * frequency // 10**9
        report["expected_period_ticks"] = period
        for actor in CLOCK_ACTORS:
            if parser.getint(actor, "clock_period") != expected_period_ns:
                raise ValueError("Effective clock_period differs: " + actor)
            domain = parser.get(actor, "clk_domain")
            if parser.getint(domain, "clock") != period:
                raise ValueError("Effective native clock differs: " + actor)

        output = simulator / "salam-results.txt"
        if not output.exists():
            output = simulator / "system.terminal"
        output_bytes, report["output_source"] = numpy_checker.read_snapshot(
            output, 16 * 1024**2
        )
        report["numerical"] = verify_numerical(
            fixture_paths, output_bytes, numpy_checker
        )
        report["numerical_state"] = (
            "passed"
            if all(item["state"] == "passed" for item in report["numerical"])
            else "failed"
        )
        report["observations"] = []
        report["native_reset_windows"] = []
        report["fu_replays"] = []
        observations = simulator / "observability"
        for actor in ACTORS:
            found = list(observations.glob(actor + ".invocation-*.json"))
            if len(found) != len(fixture_paths):
                raise ValueError("Unexpected invocation count for " + actor)
            selected_windows = set()
            for invocation in range(1, len(fixture_paths) + 1):
                path = observations / (
                    actor + ".invocation-" + str(invocation) + ".json"
                )
                payload, source = stats_checker.read_snapshot(path, 8 * 1024**2)
                data = stats_checker.strict_json(payload)
                if (
                    data.get("invocation") != invocation
                    or data.get("accelerator") != actor
                ):
                    raise ValueError("Invocation identity did not advance")
                life = data["lifecycle"]
                if (
                    life.get("tick_frequency_hz") != frequency
                    or life.get("clock_period_ticks") != period
                    or type(life.get("interface_tick_calls")) is not int
                    or life["interface_tick_calls"] < 1
                    or life.get("elapsed_ticks")
                    != (life["interface_tick_calls"] - 1) * period
                ):
                    raise ValueError("Compute passes and elapsed native ticks disagree")
                if (
                    data.get("diagnostics", {}).get("pending_requests") != 0
                    or data.get("diagnostics", {}).get("invalid_events") != 0
                ):
                    raise ValueError("Invocation ended with pending/invalid events")
                candidates = []
                for index, block in enumerate(blocks):
                    try:
                        result = stats_checker.reconcile(block, [data], period)
                    except (KeyError, TypeError, ValueError):
                        continue
                    candidates.append((index, result))
                if not candidates:
                    raise ValueError("No exact native reset window for " + path.name)
                window, native = candidates[0]
                if window in selected_windows:
                    raise ValueError("Distinct invocations reused one reset window")
                selected_windows.add(window)
                native.update(native_block=window, observation_source=source)
                report["native_reset_windows"].append(native)
                report["observations"].append(
                    {
                        "accelerator": actor,
                        "invocation": invocation,
                        "lifecycle": life,
                        "memory": data["memory"],
                        "execution": data.get("execution"),
                        "source": source,
                    }
                )
                fu_path = path.with_name("fu-scheduling-" + path.name)
                replay = fu_checker.inspect_fu_invocation(
                    fu_path, simulator / "config.ini"
                )
                if replay["state"] != "passed":
                    raise ValueError(
                        "FU event replay failed: " + json.dumps(replay["issues"])
                    )
                report["fu_replays"].append(replay)

        prefix = "system.gemm_clstr.gemm.hw_interface."
        knobs = {
            "mul_limit": parser.getint(
                prefix + "functional_units.integer_multiplier", "limit"
            ),
            "mul_runtime_cycles": parser.getint(prefix + "cycle_counts", "mul"),
        }
        if expected_mul_limit is not None and knobs["mul_limit"] != expected_mul_limit:
            raise ValueError("Effective multiplier limit differs from request")
        if (
            expected_mul_cycles is not None
            and knobs["mul_runtime_cycles"] != expected_mul_cycles
        ):
            raise ValueError("Effective multiplier latency differs from request")
        report["multiplier_capacity_witnesses"] = [
            {
                "invocation": index + 1,
                "units": [
                    unit
                    for unit in item["trace"]["units"]
                    if unit["name"] == "integer_multiplier"
                ],
            }
            for index, item in enumerate(
                replay
                for replay in report["fu_replays"]
                if ".gemm.invocation-" in Path(replay["path"]).name
            )
        ]
        report["effective_knobs"] = knobs
        report["structural_state"] = "passed"
        report["state"] = report["numerical_state"]
    except Exception as error:
        report["errors"].append(type(error).__name__ + ": " + str(error))
        report.setdefault("structural_state", "failed")
    return report


def compare_runs(
    retained_run,
    direct_run,
    fixture_paths,
    *,
    expected_period_ns,
    expected_mul_limit=None,
    expected_mul_cycles=None,
):
    """Require independent evidence and full effective parity for both paths."""
    if Path(retained_run).resolve() == Path(direct_run).resolve():
        return {
            "schema_version": 1,
            "kind": "retained_direct_gemm_differential",
            "state": "failed",
            "issues": ["Retained and direct evidence must be distinct runs"],
        }
    options = {
        "expected_period_ns": expected_period_ns,
        "expected_mul_limit": expected_mul_limit,
        "expected_mul_cycles": expected_mul_cycles,
    }
    retained = verify_run(retained_run, fixture_paths, **options)
    direct = verify_run(direct_run, fixture_paths, **options)
    report = {
        "schema_version": 1,
        "kind": "retained_direct_gemm_differential",
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "state": "failed",
        "retained": retained,
        "direct": direct,
        "scope": "Saved real-run artifacts, complete NumPy output checks, exact effective configuration and direct/native event witnesses",
        "issues": [],
    }
    try:
        report["effective_parity"] = compare_effective_configs(
            Path(retained_run) / "simulator/config.ini",
            Path(direct_run) / "simulator/config.ini",
        )
        if retained["state"] != "passed" or direct["state"] != "passed":
            raise ValueError(
                "Both paths require independent numerical and structural success"
            )
        if report["effective_parity"]["state"] != "passed":
            raise ValueError("Effective configurations differ")
        if (
            retained["execution_receipt"]["binary"]["sha256"]
            != direct["execution_receipt"]["binary"]["sha256"]
        ):
            raise ValueError("Paths used different simulator binaries")
        comparisons = []
        for left, right in zip(retained["observations"], direct["observations"]):
            for field in ("accelerator", "invocation", "memory", "execution"):
                if left[field] != right[field]:
                    raise ValueError("Invocation evidence differs: " + field)
            for field in (
                "elapsed_ticks",
                "clock_period_ticks",
                "interface_tick_calls",
            ):
                if left["lifecycle"][field] != right["lifecycle"][field]:
                    raise ValueError("Invocation timing differs: " + field)
            comparisons.append(
                {
                    "accelerator": left["accelerator"],
                    "invocation": left["invocation"],
                    "elapsed_ticks": left["lifecycle"]["elapsed_ticks"],
                    "compute_passes": left["lifecycle"]["interface_tick_calls"],
                    "memory_and_selected_commits_equal": True,
                }
            )
        for left, right in zip(retained["fu_replays"], direct["fu_replays"]):
            if (
                left["trace"]["units"] != right["trace"]["units"]
                or left["trace"]["totals"] != right["trace"]["totals"]
            ):
                raise ValueError("FU event replay totals/units differ")
        for left, right in zip(retained["numerical"], direct["numerical"]):
            if left["observed_bits_sha256"] != right["observed_bits_sha256"]:
                raise ValueError("Raw numerical output bits differ")
        report["invocation_parity"] = comparisons
        report["state"] = "passed"
    except Exception as error:
        report["issues"].append(type(error).__name__ + ": " + str(error))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retained-run", required=True, type=Path)
    parser.add_argument("--direct-run", required=True, type=Path)
    parser.add_argument("--fixture", action="append", required=True, type=Path)
    parser.add_argument("--expected-period-ns", type=int, required=True)
    parser.add_argument("--expected-mul-limit", type=int)
    parser.add_argument("--expected-mul-cycles", type=int)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    report = compare_runs(
        args.retained_run,
        args.direct_run,
        args.fixture,
        expected_period_ns=args.expected_period_ns,
        expected_mul_limit=args.expected_mul_limit,
        expected_mul_cycles=args.expected_mul_cycles,
    )
    with args.receipt.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"state": report["state"], "receipt": str(args.receipt)}))
    return 0 if report["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
