# SPDX-License-Identifier: BSD-3-Clause
"""Reader failure controls; these fixtures do not claim simulator execution."""
import unittest
from copy import deepcopy

from verify_native_stats import (
    BEGIN,
    END,
    parse_blocks,
    reconcile,
    strict_json,
)


def observation(invocation, calls, elapsed, start):
    return {
        "kind": "salam_observability",
        "schema_version": 1,
        "valid": True,
        "accelerator": "system.cluster.accel",
        "invocation": invocation,
        "lifecycle": {
            "completed": True,
            "start_tick": start,
            "end_tick": start + elapsed,
            "elapsed_ticks": elapsed,
            "clock_period_ticks": 1000,
            "interface_tick_calls": calls,
        },
        "memory": {
            "reads": {"started": 2, "completed": 2, "completed_bytes": 8},
            "writes": {"started": 1, "completed": 1, "completed_bytes": 4},
        },
    }


def block(observations):
    p = "system.cluster.accel"
    q = p + ".llvm_interface."
    calls = sum(x["lifecycle"]["interface_tick_calls"] for x in observations)
    final_tick = max(x["lifecycle"]["end_tick"] for x in observations) + 1000
    first_tick = min(x["lifecycle"]["start_tick"] for x in observations)
    values = {
        "finalTick": final_tick,
        "simTicks": final_tick - first_tick,
        q + "invocations": len(observations),
        q + "completedInvocations": len(observations),
        q + "cycles": calls,
        q
        + "invocationTicks": sum(
            x["lifecycle"]["elapsed_ticks"] for x in observations
        ),
        p + ".starts": len(observations),
        p + ".finishes": len(observations),
        p + ".requests::read": 2 * len(observations),
        p + ".requests::write": len(observations),
        p + ".bytes::read": 8 * len(observations),
        p + ".bytes::write": 4 * len(observations),
    }
    for category in ("issue", "fuStall", "memoryWait", "computeWait", "other"):
        values[q + "cycleCategories::" + category] = (
            calls if category == "issue" else 0
        )
    return {key: str(value) for key, value in values.items()}


class NativeStatsReaderTests(unittest.TestCase):
    def setUp(self):
        self.first = observation(1, 4, 3000, 1000)
        self.second = observation(2, 5, 4000, 10000)

    def test_two_invocation_cumulative_window(self):
        result = reconcile(
            block([self.first, self.second]), [self.first, self.second], 1000
        )
        self.assertEqual(result["invocations"], 2)
        self.assertEqual(result["compute_passes"], 9)
        self.assertEqual(result["elapsed_ticks"], 7000)

    def test_native_reset_window_keeps_process_invocation_id(self):
        result = reconcile(block([self.second]), [self.second], 1000)
        self.assertEqual(result["invocations"], 1)
        self.assertEqual(result["invocation_ids"], [2])

    def test_cumulative_counters_cannot_impersonate_a_reset_window(self):
        with self.assertRaisesRegex(ValueError, "Native statistic differs"):
            reconcile(block([self.first, self.second]), [self.second], 1000)

    def test_wrong_clock_or_duration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "clock period"):
            reconcile(block([self.first]), [self.first], 2000)
        altered = deepcopy(self.first)
        altered["lifecycle"]["elapsed_ticks"] = 1
        with self.assertRaisesRegex(ValueError, "duration"):
            reconcile(block([self.first]), [altered], 1000)

    def test_partial_and_duplicate_invocations_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            reconcile(block([self.first]), [self.first, self.first], 1000)
        altered = deepcopy(self.first)
        altered["lifecycle"]["completed"] = False
        with self.assertRaisesRegex(ValueError, "did not complete"):
            reconcile(block([self.first]), [altered], 1000)

    def test_category_or_byte_mismatch_is_rejected(self):
        values = block([self.first])
        values[
            "system.cluster.accel.llvm_interface.cycleCategories::other"
        ] = "1"
        with self.assertRaisesRegex(ValueError, "cycle categories"):
            reconcile(values, [self.first], 1000)
        values = block([self.first])
        values["system.cluster.accel.bytes::read"] = "9"
        with self.assertRaisesRegex(ValueError, "Native statistic differs"):
            reconcile(values, [self.first], 1000)

    def test_wrong_reset_window_and_overlap_are_rejected(self):
        values = block([self.first])
        values["simTicks"] = "1"
        with self.assertRaisesRegex(
            ValueError, "outside the native reset window"
        ):
            reconcile(values, [self.first], 1000)
        altered = deepcopy(self.second)
        altered["lifecycle"]["start_tick"] = 2000
        altered["lifecycle"]["end_tick"] = 6000
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            reconcile(
                block([self.first, altered]), [self.first, altered], 1000
            )

    def test_duplicate_and_nonfinite_json_fields_are_rejected(self):
        for payload in (
            '{"valid":true,"valid":false}',
            '{"x":NaN}',
            '{"x":Infinity}',
        ):
            with self.assertRaises(ValueError):
                strict_json(payload)

    def test_incomplete_or_duplicate_native_blocks_are_rejected(self):
        self.assertEqual(parse_blocks(BEGIN + "\na 1\n" + END), [{"a": "1"}])
        for text in (
            BEGIN + "\na 1",
            BEGIN + "\na 1\na 2\n" + END,
            BEGIN + "\n" + BEGIN + "\n" + END,
        ):
            with self.assertRaises(ValueError):
                parse_blocks(text)
