# SPDX-License-Identifier: BSD-3-Clause
"""Regression checks for verified, bounded SALAM trace visualization."""
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "salam_trace_exporter", ROOT / "visualizer" / "export_salam_visualizer.py"
)
EXPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORTER)


def fixture(fu=9, name="double_multiplier", count=1):
    events = [
        {
            "event": "grant",
            "cycle": 1,
            "tick": 1000,
            "uid": i,
            "opcode": 18,
            "fu_id": fu,
            "lease_id": i,
        }
        for i in range(1, count + 1)
    ] + [
        {
            "event": "release",
            "cycle": 4,
            "tick": 4000,
            "uid": i,
            "opcode": 18,
            "fu_id": fu,
            "lease_id": i,
        }
        for i in range(1, count + 1)
    ]
    counters = {
        "attempts": count,
        "grants": count,
        "denials": 0,
        "releases": count,
        "peak": count,
        "outstanding": 0,
    }
    return {
        "kind": "salam_fu_scheduling",
        "schema_version": 1,
        "invocation": {
            "name": "test.accelerator",
            "elapsed_cycles": 5,
            "elapsed_ticks": 5000,
        },
        "units": [{"id": fu, "name": name, "limit": 0, **counters}],
        "totals": dict(counters),
        "trace": events,
        "trace_event_limit": 4194304,
        "trace_truncated": False,
    }


class ExecutionVisualizerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "trace.json"
        self.output = Path(self.tmp.name) / "viewer.html"

    def write(self, data):
        self.source.write_text(json.dumps(data), encoding="utf-8")
        return self.source

    def parse(self, data, **kwargs):
        return EXPORTER.parse_salam_trace(self.write(data), **kwargs)

    def rejected(self, data):
        with self.assertRaises(EXPORTER.TraceValidationError):
            EXPORTER.export_trace(self.write(data), self.output)
        self.assertFalse(self.output.exists())

    def test_full_replay_and_source_hash_are_reported(self):
        self.write(fixture())
        meta = EXPORTER.export_trace(self.source, self.output)
        self.assertEqual(
            meta["source"]["sha256"],
            hashlib.sha256(self.source.read_bytes()).hexdigest(),
        )
        self.assertEqual(meta["validation"]["events_replayed"], 2)
        self.assertEqual(meta["validation"]["numerical_correctness"], "not evaluated")
        self.assertFalse(meta["preview"]["limited"])
        self.assertTrue(self.output.is_file())

    def test_float_double_and_future_units_are_preserved(self):
        for fu, name in (
            (5, "float_adder"),
            (6, "double_adder"),
            (9, "double_multiplier"),
            (42, "future_tensor_unit"),
        ):
            data = self.parse(fixture(fu, name))
            self.assertEqual(data["spans"][0]["fu_name"], name)
            self.assertEqual(data["spans"][0]["fu_id"], fu)
        EXPORTER.generate_html(data, self.output)
        html = self.output.read_text()
        self.assertIn("const TRACK_ORDER = TRACE_DATA.units", html)

    def test_more_than_eight_lanes_do_not_alias(self):
        data = self.parse(fixture(count=12))
        self.assertEqual(data["fu_lane_counts"][9], 12)
        self.assertEqual({s["lane"] for s in data["spans"]}, set(range(12)))
        EXPORTER.generate_html(data, self.output)
        self.assertNotIn("lane % 8", self.output.read_text())

    def test_release_regrant_boundary_is_half_open(self):
        data = fixture(count=2)
        first, second, release_first, release_second = data["trace"]
        release_first.update(cycle=2, tick=2000)
        second.update(cycle=2, tick=2000)
        data["trace"] = [first, release_first, second, release_second]
        data["totals"]["peak"] = data["units"][0]["peak"] = 1
        result = self.parse(data)
        self.assertEqual([span["lane"] for span in result["spans"]], [0, 0])
        self.assertEqual(
            result["concurrency"],
            [
                {"cycle": 1, "count": 1},
                {"cycle": 2, "count": 1},
                {"cycle": 4, "count": 0},
            ],
        )

    def test_zero_duration_is_a_marker_not_a_fabricated_cycle(self):
        data = fixture()
        data["trace"][1].update(cycle=1, tick=1000)
        result = self.parse(data)
        self.assertEqual(result["spans"][0]["duration"], 0)
        self.assertEqual(result["concurrency"], [{"cycle": 1, "count": 0}])
        self.assertEqual(result["totals"]["peak"], 1)

    def test_preview_limit_does_not_limit_full_replay(self):
        result = self.parse(fixture(count=12), max_spans=2)
        self.assertEqual(result["validation"]["events_replayed"], 24)
        self.assertEqual(
            result["preview"],
            {
                "rendered_spans": 2,
                "total_spans": 12,
                "limited": True,
                "max_spans": 2,
            },
        )
        self.assertEqual(result["totals"]["peak"], 12)

    def test_truncated_trace_is_rejected(self):
        data = fixture()
        data["trace_truncated"] = True
        self.rejected(data)

    def test_missing_truncation_declaration_is_rejected(self):
        data = fixture()
        del data["trace_truncated"]
        self.rejected(data)

    def test_unreleased_grant_is_rejected(self):
        data = fixture()
        data["trace"].pop()
        self.rejected(data)

    def test_unmatched_release_is_rejected(self):
        data = fixture()
        data["trace"][1]["lease_id"] = 123
        self.rejected(data)

    def test_duplicate_grant_is_rejected(self):
        data = fixture()
        data["trace"].insert(1, dict(data["trace"][0]))
        self.rejected(data)

    def test_release_identity_mismatch_is_rejected(self):
        data = fixture()
        data["trace"][1]["opcode"] = 17
        self.rejected(data)

    def test_unit_and_total_counter_tampering_is_rejected(self):
        for field in ("grants", "denials", "peak", "outstanding"):
            data = fixture()
            data["totals"][field] += 1
            self.rejected(data)
            data = fixture()
            data["units"][0][field] += 1
            self.rejected(data)

    def test_over_capacity_grant_is_rejected(self):
        data = fixture(count=2)
        data["units"][0]["limit"] = 1
        self.rejected(data)

    def test_invalid_denial_is_rejected(self):
        data = fixture()
        denial = dict(data["trace"][0], event="deny", lease_id=0)
        data["trace"].insert(0, denial)
        self.rejected(data)

    def test_legitimate_denial_replays(self):
        data = fixture()
        data["units"][0]["limit"] = 1
        data["trace"].insert(1, dict(data["trace"][0], event="deny", lease_id=0))
        for counters in (data["units"][0], data["totals"]):
            counters["attempts"] += 1
            counters["denials"] += 1
        self.assertEqual(self.parse(data)["validation"]["events_replayed"], 3)

    def test_backwards_or_out_of_bounds_events_are_rejected(self):
        for field, value in (("cycle", 0), ("cycle", 6), ("tick", 999)):
            data = fixture()
            data["trace"][1][field] = value
            self.rejected(data)

    def test_boolean_numbers_are_rejected(self):
        data = fixture()
        data["trace"][0]["lease_id"] = True
        self.rejected(data)

    def test_missing_fields_unknown_events_and_units_are_rejected(self):
        for field in ("cycle", "tick", "uid", "opcode", "fu_id", "lease_id"):
            data = fixture()
            del data["trace"][0][field]
            self.rejected(data)
        data = fixture()
        data["trace"][0]["event"] = "pretend_pass"
        self.rejected(data)
        data = fixture()
        data["trace"][0]["fu_id"] = 50
        self.rejected(data)

    def test_wrong_schema_and_duplicate_units_are_rejected(self):
        data = fixture()
        data["schema_version"] = 2
        self.rejected(data)
        data = fixture()
        data["units"].append(copy.deepcopy(data["units"][0]))
        self.rejected(data)

    def test_declared_event_budget_is_enforced(self):
        data = fixture()
        data["trace_event_limit"] = 1
        self.rejected(data)

    def test_source_and_html_text_are_safe(self):
        attack = "</script><img src=x onerror=alert(1)>"
        data = fixture(name=attack)
        data["invocation"]["name"] = attack
        self.write(data)
        EXPORTER.export_trace(self.source, self.output)
        html = self.output.read_text()
        self.assertNotIn(attack, html)
        self.assertIn("escapeHtml(u.name)", html)
        self.assertIn("escapeHtml(s.fu_name)", html)
        self.assertIn("escapeHtml(hit.fu_name)", html)
        self.assertIn("\\u003c/script\\u003e", html)

    def test_wrong_recorded_hash_produces_no_html(self):
        self.write(fixture())
        with self.assertRaises(EXPORTER.TraceValidationError):
            EXPORTER.export_trace(self.source, self.output, expected_sha256="0" * 64)
        self.assertFalse(self.output.exists())

    def test_source_overwrite_and_non_html_outputs_are_rejected(self):
        self.write(fixture())
        original = self.source.read_bytes()
        for output in (self.source, self.output.with_suffix(".json")):
            with self.assertRaises(EXPORTER.TraceValidationError):
                EXPORTER.export_trace(self.source, output)
        self.assertEqual(self.source.read_bytes(), original)

    def test_malformed_json_and_duplicate_keys_are_rejected(self):
        for raw in (
            '{"kind":',
            '{"kind":"a","kind":"b"}',
            json.dumps(fixture()) + " false",
        ):
            self.source.write_text(raw)
            with self.assertRaises(EXPORTER.TraceValidationError):
                EXPORTER.parse_salam_trace(self.source)

    def test_stream_crosses_chunk_boundaries_without_retaining_trace(self):
        result = self.parse(fixture(count=1500), max_spans=3)
        self.assertEqual(result["validation"]["events_replayed"], 3000)
        self.assertEqual(result["preview"]["total_spans"], 1500)
        self.assertEqual(len(result["spans"]), 3)

    def test_elapsed_tick_span_is_enforced_without_assuming_zero_origin(self):
        data = fixture()
        data["invocation"]["elapsed_ticks"] = 1
        self.rejected(data)
        data["invocation"]["elapsed_ticks"] = 3000
        for event in data["trace"]:
            event["tick"] += 1000000
        self.assertEqual(self.parse(data)["validation"]["state"], "passed")

    def test_hash_is_computed_from_the_binary_stream_being_parsed(self):
        self.write(fixture())
        raw = self.source.read_bytes()
        real_open = Path.open
        opened = []

        def recording_open(path, *args, **kwargs):
            if path == self.source:
                opened.append(args[0] if args else kwargs.get("mode", "r"))
            return real_open(path, *args, **kwargs)

        with mock.patch.object(Path, "open", recording_open):
            result = EXPORTER.parse_salam_trace(self.source)
        self.assertEqual(opened, ["rb"])
        self.assertEqual(result["source"]["sha256"], hashlib.sha256(raw).hexdigest())

    def test_atomic_replacement_with_preserved_size_and_mtime_is_rejected(self):
        self.write(fixture())
        original = self.source.read_bytes()
        original_info = self.source.stat()
        replacement = original.replace(b"test.accelerator", b"fake.accelerator")
        self.assertEqual(len(original), len(replacement))
        replacement_path = self.source.with_name("replacement.json")
        replacement_path.write_bytes(replacement)
        os.utime(
            replacement_path, ns=(original_info.st_atime_ns, original_info.st_mtime_ns)
        )
        original_fill = EXPORTER._JSONStream._fill
        replaced = []

        def replace_after_read(reader):
            original_fill(reader)
            if not replaced:
                os.replace(replacement_path, self.source)
                os.utime(
                    self.source,
                    ns=(original_info.st_atime_ns, original_info.st_mtime_ns),
                )
                replaced.append(True)

        with mock.patch.object(EXPORTER._JSONStream, "_fill", replace_after_read):
            with self.assertRaisesRegex(
                EXPORTER.TraceValidationError, "Source changed"
            ):
                EXPORTER.export_trace(
                    self.source,
                    self.output,
                    expected_sha256=hashlib.sha256(replacement).hexdigest(),
                )
        self.assertEqual(self.source.stat().st_size, original_info.st_size)
        self.assertEqual(self.source.stat().st_mtime_ns, original_info.st_mtime_ns)
        self.assertFalse(self.output.exists())

    def test_cli_wrapper_uses_the_same_fail_closed_exporter(self):
        self.write(fixture())
        wrapper = ROOT.parent / "docker" / "export_salam_visualizer.py"
        proc = subprocess.run(
            [sys.executable, str(wrapper), str(self.source), str(self.output)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.output.exists())
        failed = subprocess.run(
            [
                sys.executable,
                str(wrapper),
                str(self.source),
                str(self.output),
                "--expected-sha256",
                "0" * 64,
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(failed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
