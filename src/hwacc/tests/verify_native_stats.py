#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Reconcile one native statistics reset window with complete invocation JSON.

This checker requires complete invocations wholly inside the selected native
window. It never treats guest pass markers or native totals as numerical
correctness. Invocation IDs remain process-lifetime IDs even after native reset.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

BEGIN = "---------- Begin Simulation Statistics ----------"
END = "---------- End Simulation Statistics   ----------"
UINT = re.compile(r"[0-9]+")


def read_snapshot(path, maximum):
    path = Path(path)
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        payload = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )
    if len(payload) > maximum or identity(before) != identity(after):
        raise ValueError("Source changed or exceeded bounded size")
    return payload, {
        "path": str(path.absolute()),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def strict_json(payload):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate direct observation field: " + key)
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("Nonfinite direct observation value: " + value)

    return json.loads(
        payload,
        object_pairs_hook=unique_object,
        parse_constant=invalid_constant,
    )


def parse_blocks(text):
    blocks, active = [], None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == BEGIN:
            if active is not None:
                raise ValueError("Nested native statistics block")
            active = {}
        elif stripped == END:
            if active is None:
                raise ValueError("End without native statistics begin")
            blocks.append(active)
            active = None
        elif active is not None and stripped and not stripped.startswith("#"):
            parts = stripped.split()
            if len(parts) < 2 or parts[0] in active:
                raise ValueError("Malformed or duplicate native statistic")
            active[parts[0]] = parts[1]
    if active is not None or not blocks:
        raise ValueError("Incomplete or missing native statistics block")
    return blocks


def integer(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("Expected integer " + name)
    text = str(value)
    if not UINT.fullmatch(text) or int(text) > (1 << 64) - 1:
        raise ValueError("Invalid uint64 " + name)
    return int(text)


def reconcile(block, observations, expected_period):
    expected_period = integer(expected_period, "period")
    if not expected_period or not observations:
        raise ValueError(
            "Choose complete invocation observations and a period"
        )
    names = {item.get("accelerator") for item in observations}
    if len(names) != 1 or not isinstance(next(iter(names)), str):
        raise ValueError("Observations must belong to one accelerator")
    accelerator = next(iter(names))
    final_tick = integer(block["finalTick"], "native finalTick")
    window_ticks = integer(block["simTicks"], "native simTicks")
    if window_ticks > final_tick:
        raise ValueError("Invalid native reset-window duration")
    window_start = final_tick - window_ticks
    intervals = []
    invocations = set()
    calls = ticks = reads = writes = read_bytes = write_bytes = 0
    for item in observations:
        if (
            item.get("kind") != "salam_observability"
            or type(item.get("schema_version")) is not int
            or item["schema_version"] != 1
            or item.get("valid") is not True
        ):
            raise ValueError("Invalid direct observation")
        invocation = integer(item["invocation"], "invocation")
        if not invocation or invocation in invocations:
            raise ValueError("Duplicate or zero invocation")
        invocations.add(invocation)
        life = item["lifecycle"]
        if life.get("completed") is not True:
            raise ValueError("Invocation did not complete")
        if integer(life["clock_period_ticks"], "clock") != expected_period:
            raise ValueError("Effective clock period differs")
        elapsed = integer(life["elapsed_ticks"], "elapsed")
        start_tick = integer(life["start_tick"], "start")
        end_tick = integer(life["end_tick"], "end")
        if end_tick - start_tick != elapsed:
            raise ValueError("Invocation duration differs")
        if start_tick < window_start or end_tick > final_tick:
            raise ValueError(
                "Invocation falls outside the native reset window"
            )
        intervals.append((start_tick, end_tick))
        ticks += elapsed
        calls += integer(life["interface_tick_calls"], "tick calls")
        for memory, counts in (
            (item["memory"]["reads"], "read"),
            (item["memory"]["writes"], "write"),
        ):
            started = integer(memory["started"], counts + " started")
            completed = integer(memory["completed"], counts + " completed")
            if started != completed:
                raise ValueError("Incomplete logical request")
            if counts == "read":
                reads += started
                read_bytes += integer(memory["completed_bytes"], "read bytes")
            else:
                writes += started
                write_bytes += integer(
                    memory["completed_bytes"], "write bytes"
                )
    intervals.sort()
    if any(
        left[1] > right[0] for left, right in zip(intervals, intervals[1:])
    ):
        raise ValueError("Overlapping invocations for one accelerator")
    prefix = accelerator + ".llvm_interface."
    expected = {
        prefix + "invocations": len(observations),
        prefix + "completedInvocations": len(observations),
        prefix + "cycles": calls,
        prefix + "invocationTicks": ticks,
        accelerator + ".starts": len(observations),
        accelerator + ".finishes": len(observations),
        accelerator + ".requests::read": reads,
        accelerator + ".requests::write": writes,
        accelerator + ".bytes::read": read_bytes,
        accelerator + ".bytes::write": write_bytes,
    }
    for name, value in expected.items():
        if name not in block or integer(block[name], name) != value:
            raise ValueError("Native statistic differs: " + name)
    categories = sum(
        integer(block[prefix + "cycleCategories::" + name], name)
        for name in ("issue", "fuStall", "memoryWait", "computeWait", "other")
    )
    if categories != calls:
        raise ValueError(
            "Native cycle categories do not cover all compute passes"
        )
    return {
        "state": "passed",
        "scope": "complete native reset window",
        "accelerator": accelerator,
        "invocation_ids": sorted(invocations),
        "native_window": {"start_tick": window_start, "end_tick": final_tick},
        "invocations": len(observations),
        "compute_passes": calls,
        "elapsed_ticks": ticks,
        "clock_period_ticks": expected_period,
        "numerical_correctness": "not evaluated",
        "matched": expected,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stats", required=True, type=Path)
    parser.add_argument("--block", required=True, type=int)
    parser.add_argument(
        "--observation", action="append", required=True, type=Path
    )
    parser.add_argument("--expected-period-ticks", required=True, type=int)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    payload, stats_source = read_snapshot(args.stats, 64 * 1024 * 1024)
    blocks = parse_blocks(payload.decode("utf-8"))
    if not 0 <= args.block < len(blocks):
        parser.error("--block is outside the completed statistics dumps")
    observations, sources = [], []
    for path in args.observation:
        payload, source = read_snapshot(path, 8 * 1024 * 1024)
        observations.append(strict_json(payload))
        sources.append(source)
    report = reconcile(
        blocks[args.block], observations, args.expected_period_ticks
    )
    report.update(
        stats_source=stats_source,
        observation_sources=sources,
        native_block=args.block,
    )
    with args.receipt.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
