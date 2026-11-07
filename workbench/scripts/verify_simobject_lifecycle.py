#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Joshua Slycord
"""Run real SALAM drain, timing-port and independent-restart regressions.

Requires an opt-in ARM binary built with SALAM_PROTOCOL_TESTS=1. The host
recomputes observed bytes/results and checks effective production SimObjects.
Expected failures must fail for their specified cause, not merely exit nonzero.
"""
import argparse
import configparser
import datetime
import hashlib
import json
import os
import resource
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/gem5/salam"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sources():
    paths = [Path(__file__).resolve(), ROOT / "configs/SALAM/HWAccConfig.py"]
    paths.extend(
        p
        for p in (ROOT / "src/hwacc").rglob("*")
        if p.is_file() and p.suffix in (".cc", ".hh", ".py", ".ll")
    )
    paths.extend(
        p for p in FIXTURES.iterdir() if p.is_file() and p.suffix in (".py", ".ll")
    )
    paths.append(ROOT / "src/hwacc/SConscript")
    paths.append(ROOT / "src/hwacc/workbench_fu_capability.json")
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(set(paths))}


def cases(baseline):
    if baseline:
        return [
            ("baseline-sync", "sync", "local", [], "Could not find memory request"),
            ("baseline-drain", "retry", "local", [], "drain manager did not wait"),
            (
                "baseline-lifetime",
                "lifetime",
                "local",
                [],
                "drain manager did not wait",
            ),
            (
                "baseline-bank-delta",
                "delta",
                None,
                [],
                "RegisterBank reported drained before pending work",
            ),
            ("baseline-bank-retry", "response-retry", None, [], None),
        ]
    result = [
        (mode + "-" + route, mode, route, [], None)
        for route in ("local", "acp", "reg")
        for mode in ("async", "sync", "retry", "retry-sync")
    ]
    result.extend(
        [
            ("independent-restarts", "lifetime", "local", [], None),
            ("bank-pending-delta", "delta", None, [], None),
            ("bank-response-retry-reentry", "response-retry", None, [], None),
            (
                "reject-wrong-read",
                "retry",
                "local",
                ["--corrupt-expected"],
                "read bytes differ",
            ),
            (
                "reject-retained-graph",
                "lifetime",
                "local",
                ["--retain-graph"],
                "finished actor retained graph values",
            ),
            (
                "reject-wrong-lifetime-result",
                "lifetime",
                "local",
                ["--corrupt-expected"],
                "multi-accelerator numerical output differs",
            ),
            (
                "reject-wrong-bank-delta",
                "delta",
                None,
                ["--corrupt-expected"],
                "register delta value differs",
            ),
            (
                "reject-wrong-bank-response",
                "response-retry",
                None,
                ["--corrupt-expected"],
                "bank response value differs",
            ),
        ]
    )
    return result


def effective_config(path, mode, route, extra):
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read_string(path.read_text())

    def value(section, key, expected):
        require(
            parser.get(section, key) == expected,
            f"Effective {section}.{key} differs from {expected}",
        )

    value("system", "mem_mode", "timing")
    value("system.clk_domain", "clock", "10000")
    value("system.tester", "mode", mode)
    value(
        "system.tester", "corrupt_expected", str("--corrupt-expected" in extra).lower()
    )
    if route is None:
        value("system.bank", "type", "RegisterBank")
        value("system.bank", "delta_time", "17000")
        value("system.tester", "type", "SalamRegisterBankTester")
        value("system.tester", "bank", "system.bank")
        value("system.tester", "port", "system.bank.reg_port")
        value("system.tester", "load", "system.bank.load_port")
    else:
        value("system.tester", "type", "SalamLifecycleTester")
        value("system.tester", "comm_int", "system.a")
        value("system.tester", "route", route)
        value("system.tester", "retain_graph", str("--retain-graph" in extra).lower())
        actors = ("a", "b") if mode == "lifetime" else ("a",)
        for index, actor in enumerate(actors):
            prefix = "system." + actor
            value(prefix, "type", "CommInterface")
            value(prefix, "clock_period", "10")
            value(prefix, route, f"system.tester.memory[{index}]")
            if mode == "lifetime":
                value(prefix + ".llvm_interface", "type", "LLVMInterface")
                value(prefix + ".llvm_interface", "comm_int", prefix)
                value(prefix + ".hw_interface", "type", "HWInterface")
                value("system.tester", "actor_" + actor, prefix + ".llvm_interface")
    return {"state": "passed", "sha256": digest(path)}


def verify_observations(data, mode, route):
    require(
        data.get("state") == "passed" and data.get("mode") == mode,
        "Fixture receipt identity differs",
    )
    if route is None:
        require(
            data["drained_tick"] > data["drain_requested_tick"],
            "RegisterBank drain did not wait",
        )
        expected = int.from_bytes(bytes(range(1, 9)), "little")
        if mode == "delta":
            require(data["value"] == expected, "Host delta oracle differs")
        else:
            require(
                data["rejected_responses"] == 2
                and data["completed_responses"] == 2
                and data["response_order"] == [0, 0, 0, 1]
                and data["response_value"] == expected,
                "Host response/retry oracle differs",
            )
        return
    require(len(data.get("rounds", [])) == 1, "Unexpected round count")
    row = data["rounds"][0]
    require(row.get("state") == "passed", "Fixture round failed")
    require(
        row["drained_tick"] >= row["drain_requested_tick"],
        "Simulation time moved backwards",
    )
    if mode != "sync":
        require(
            row["drained_tick"] > row["drain_requested_tick"],
            "Busy drain did not advance the event queue",
        )
    if mode == "lifetime":
        expected = {
            "a_first_output": 17 + sum(range(4)),
            "b_first_output": sum(range(256)),
            "a_output": 17 + sum(range(512)),
            "b_output": sum(range(16)),
            "a_completed_invocations": 2,
            "b_completed_invocations": 2,
            "fresh_write_responses": 4,
        }
        require(
            all(row.get(k) == v for k, v in expected.items()),
            "Host independent-invocation numerical oracle differs",
        )
        require(
            all(
                row.get(k) is True
                for k in (
                    "a_restart_while_b_active",
                    "b_restart_while_a_active",
                    "b_finished_while_a_active",
                )
            ),
            "Independent overlap was not observed",
        )
        require(
            row["captured_a"] > 0 and row["captured_b"] > 0,
            "No real graph ownership handles captured",
        )
        require(
            all(
                row[k] == 0
                for k in (
                    "live_a_after",
                    "live_b_after",
                    "live_previous_a_after",
                    "live_previous_b_after",
                )
            ),
            "Captured per-instance graph objects survived completion",
        )
    else:
        packets = 2 if route == "reg" else 6
        rejections = 2 if mode in ("retry", "retry-sync") else 0
        expected = {
            "reads": 1,
            "writes": 1,
            "accepted_packets": packets,
            "responses": packets,
            "rejections": rejections,
            "send_attempts": packets + rejections,
            "observed_read": [((0x103D + i) * 17 + 3) & 255 for i in range(70)],
            "observed_write": [(i * 7 + 11) & 255 for i in range(70)],
        }
        require(
            all(row.get(k) == v for k, v in expected.items()),
            "Host raw-byte/packet-count oracle differs",
        )


def run_case(binary, output, case, timeout):
    name, mode, route, extra, expected = case
    directory = output / name
    directory.mkdir()
    script = FIXTURES / ("register_bank.py" if route is None else "lifecycle.py")
    argv = [
        str(binary),
        "--outdir=" + str(directory / "simulator"),
        str(script),
        "--mode",
        mode,
    ]
    if route is not None:
        argv.extend(["--route", route])
    argv.extend(extra)
    row = {
        "name": name,
        "state": "failed",
        "argv": argv,
        "expected_rejection": expected,
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    start = time.monotonic()
    try:
        with (directory / "stdout.txt").open("w") as stdout, (
            directory / "stderr.txt"
        ).open("w") as stderr:
            process = subprocess.Popen(argv, cwd=ROOT, stdout=stdout, stderr=stderr)
            row["process_id"] = process.pid
            try:
                row["return_code"] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise RuntimeError("Simulator timed out; its child was reaped")
        row["effective_configuration"] = effective_config(
            directory / "simulator/config.ini", mode, route, extra
        )
        if expected:
            text = (directory / "stdout.txt").read_text(errors="replace")
            text += (directory / "stderr.txt").read_text(errors="replace")
            require(
                row["return_code"] != 0 and expected in text,
                "Expected rejection cause was not observed: " + expected,
            )
            row["observed_expected_cause"] = expected
        else:
            require(row["return_code"] == 0, "Simulator process failed")
            receipt = (
                directory
                / "simulator"
                / ("register-bank.json" if route is None else "lifecycle.json")
            )
            require(receipt.stat().st_size < 1024**2, "Oversized fixture receipt")
            data = json.loads(receipt.read_text())
            verify_observations(data, mode, route)
            row.update(observations=data, receipt_sha256=digest(receipt))
        row["state"] = "passed"
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        row["error"] = type(error).__name__ + ": " + str(error)
    finally:
        row["elapsed_seconds"] = time.monotonic() - start
        row["artifacts"] = {
            p.name: digest(p)
            for p in (directory / "stdout.txt", directory / "stderr.txt")
            if p.is_file()
        }
        save(directory / "case.json", row)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gem5", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New evidence directory; existing paths are refused",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Expect the four pre-fix failures and healthy bank retry",
    )
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args(argv)
    if not 10 <= args.timeout_seconds <= 3600:
        parser.error("--timeout-seconds must be from 10 through 3600")
    binary = args.gem5.expanduser().resolve(strict=True)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        parser.error("--gem5 must be executable")
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    # Deliberate fatal controls must not produce large core files. Process only.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    before = sources()
    report = {
        "kind": "real_salam_simobject_lifecycle",
        "state": "failed",
        "baseline": args.baseline,
        "binary": {"path": str(binary), "sha256": digest(binary)},
        "source_before": before,
        "cases": [],
    }
    selected = cases(args.baseline)
    for case in selected:
        row = run_case(binary, output, case, args.timeout_seconds)
        report["cases"].append(row)
        save(output / "progress.json", report)
        print(
            json.dumps(
                {k: row.get(k) for k in ("name", "state", "return_code", "error")}
            ),
            flush=True,
        )
        if row["state"] != "passed":
            break
    report["source_after"] = sources()
    report["binary_after_sha256"] = digest(binary)
    report["expected_cases"] = len(selected)
    if (
        len(report["cases"]) == len(selected)
        and all(row["state"] == "passed" for row in report["cases"])
        and report["source_after"] == before
        and report["binary_after_sha256"] == report["binary"]["sha256"]
    ):
        report["state"] = "passed"
    save(output / "matrix.json", report)
    print(
        json.dumps(
            {
                "state": report["state"],
                "cases": len(report["cases"]),
                "receipt": str(output / "matrix.json"),
            }
        )
    )
    return 0 if report["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
