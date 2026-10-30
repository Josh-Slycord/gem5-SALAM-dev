"""Known-case contract tests; synthetic event summaries are not engine runs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from salam_workbench.observability import (
    UNSUPPORTED, adapt_legacy, assess_run_observability, load_observability, validate_observability,
)
from salam_workbench.runner import file_hash


def payload(accelerator="system.gemm_clstr.gemm", invocation=1):
    return {
        "kind": "salam_observability", "schema_version": 1, "producer": "workbench-m3",
        "accelerator": accelerator, "invocation": invocation, "valid": True,
        "lifecycle": {"start_tick": 100, "end_tick": 120, "elapsed_ticks": 20,
                      "clock_period_ticks": 10, "tick_frequency_hz": 1000,
                      "interface_tick_calls": 3, "completed": True},
        "memory": {"availability": "observed", "scope": "Logical enqueue to final completion, including queue waiting",
                   "reads": {"started": 2, "completed": 2, "started_bytes": 8, "completed_bytes": 8,
                             "outstanding": 0, "latency_ticks": {"count": 2, "sum": 8, "min": 3, "max": 5}},
                   "writes": {"started": 1, "completed": 1, "started_bytes": 4, "completed_bytes": 4,
                              "outstanding": 0, "latency_ticks": {"count": 1, "sum": 2, "min": 2, "max": 2}}},
        "execution": {"availability": "observed_selected_commits",
                      "scope": "Successful queued compute and external load/store commit callbacks only",
                      "queued_compute_commits": 7, "memory_read_commits": 2, "memory_write_commits": 1,
                      "selected_commits_total": 10},
        "queues": {"availability": "observed", "sample_unit": "accelerator_interface_tick_entry",
                   "scope": "Sum across active functions at each interface tick entry",
                   "aggregation": "complete_streaming_sums_and_maxima",
                   "sample_count": 3, "aggregated_sample_count": 3, "dropped_sample_count": 0,
                   "raw_samples_available": False, "reservation": {"sum": 4, "max": 3},
                   "read": {"sum": 3, "max": 2}, "write": {"sum": 1, "max": 1},
                   "compute": {"sum": 3, "max": 2}, "active_functions": {"sum": 4, "max": 2}},
        "diagnostics": {"invalid_events": 0, "pending_requests": 0},
        "unsupported": {name: {"availability": "unavailable", "reason": "Not instrumented or characterized"}
                        for name in UNSUPPORTED},
    }


def set_field(data, path, value):
    cursor = data
    parts = path.split(".")
    for part in parts[:-1]:
        cursor = cursor[part]
    cursor[parts[-1]] = value


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="salam-observability-fixture-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)

    def write_payload(self, data, filename="summary.json"):
        path = self.base / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_known_request_and_queue_cases_have_exact_units(self):
        data = payload()
        result = validate_observability(data)
        self.assertTrue(result["contract_valid"], result["issues"])
        self.assertEqual(result["metrics"]["memory.reads.latency_ticks.sum"]["value"], 8)
        self.assertEqual(result["metrics"]["memory.reads.latency_ticks.sum"]["unit"], "tick")
        self.assertEqual(result["metrics"]["memory.reads.completed_bytes"]["unit"], "byte")
        self.assertEqual(result["metrics"]["execution.selected_commits_total"]["unit"], "selected_commit")
        self.assertEqual(result["metrics"]["queues.reservation.sum"]["value"], sum([1, 3, 0]))
        self.assertEqual(result["metrics"]["queues.reservation.max"]["value"], max([1, 3, 0]))
        self.assertEqual(result["metrics"]["queues.reservation.sum"]["unit"], "queue_entry*sample")
        self.assertEqual(result["metrics"]["memory.reads.latency_ticks.mean"]["value"], "4")
        self.assertEqual(result["metrics"]["memory.writes.latency_ticks.mean"]["value"], "2")
        mean = result["metrics"]["queues.reservation.mean"]
        self.assertEqual(mean["value"], "1." + "3" * 49)
        self.assertEqual(mean["derivation"]["exact_ratio"], "4/3")
        self.assertEqual(mean["derivation"]["denominator_path"], "queues.sample_count")
        self.assertEqual(mean["derivation"]["decimal_significant_digits"], 50)
        self.assertIs(result["data"], data)

    def test_zero_requests_are_observed_zero_without_invented_latency(self):
        data = payload()
        for direction in ("reads", "writes"):
            data["memory"][direction] = {"started": 0, "completed": 0, "started_bytes": 0,
                                        "completed_bytes": 0, "outstanding": 0,
                                        "latency_ticks": {"count": 0, "sum": 0, "min": None, "max": None}}
        data["execution"].update(memory_read_commits=0, memory_write_commits=0, selected_commits_total=7)
        result = validate_observability(data)
        self.assertTrue(result["contract_valid"], result["issues"])
        self.assertEqual(result["metrics"]["memory.reads.completed"]["value"], 0)
        self.assertEqual(result["metrics"]["memory.reads.completed"]["availability"], "observed")
        self.assertIsNone(result["metrics"]["memory.reads.latency_ticks.min"]["value"])
        self.assertEqual(result["metrics"]["memory.reads.latency_ticks.min"]["availability"], "not_observed")
        self.assertIsNone(result["metrics"]["memory.reads.latency_ticks.mean"]["value"])
        self.assertEqual(result["metrics"]["memory.reads.latency_ticks.mean"]["availability"], "not_observed")
        self.assertTrue(all(item["value"] is None for item in result["unsupported"].values()))

    def test_known_single_request_delay_and_large_ticks_remain_exact(self):
        data = payload()
        start = (1 << 53) + 1
        data["lifecycle"].update(start_tick=start, end_tick=start + 20)
        result = validate_observability(data)
        self.assertTrue(result["contract_valid"], result["issues"])
        self.assertEqual(result["metrics"]["lifecycle.start_tick"]["value"], start)
        self.assertEqual(result["metrics"]["memory.writes.latency_ticks.sum"]["value"], 2)
        self.assertEqual(result["metrics"]["lifecycle.tick_frequency_hz"]["unit"], "tick/second")

    def test_bad_counts_units_flags_and_timing_are_rejected(self):
        cases = [
            ("schema_version", True), ("producer", "old-stash"), ("invocation", 0),
            ("lifecycle.end_tick", 99), ("lifecycle.elapsed_ticks", 19),
            ("lifecycle.clock_period_ticks", 0), ("lifecycle.tick_frequency_hz", 0),
            ("memory.reads.completed", 3), ("memory.reads.completed_bytes", 9),
            ("memory.reads.outstanding", 1), ("memory.reads.latency_ticks.count", 1),
            ("memory.reads.latency_ticks.sum", 100), ("memory.reads.latency_ticks.min", 6),
            ("memory.reads.latency_ticks.max", None), ("memory.reads.started", True),
            ("execution.selected_commits_total", 100), ("execution.memory_read_commits", 3),
            ("execution.availability", "all_retired_instructions"),
            ("queues.sample_count", 2), ("queues.aggregated_sample_count", 2),
            ("queues.dropped_sample_count", 1), ("queues.raw_samples_available", True),
            ("queues.reservation.max", 5), ("queues.compute.sum", 99),
            ("queues.sample_unit", "per_active_function"), ("diagnostics.invalid_events", 1),
            ("diagnostics.pending_requests", 1), ("valid", False), ("lifecycle.completed", False),
            ("unsupported.power.availability", "observed"), ("unsupported.power.value", 0),
        ]
        for path, value in cases:
            with self.subTest(path=path, value=value):
                data = payload()
                set_field(data, path, value)
                self.assertFalse(validate_observability(data)["contract_valid"])

    def test_missing_field_is_unknown_not_zero_and_empty_sampling_has_no_observed_maximum(self):
        data = payload()
        del data["memory"]["reads"]["completed_bytes"]
        result = validate_observability(data)
        self.assertFalse(result["contract_valid"])
        self.assertIsNone(result["metrics"]["memory.reads.completed_bytes"]["value"])
        self.assertEqual(result["metrics"]["memory.reads.completed_bytes"]["availability"], "missing")
        data = payload()
        data["lifecycle"]["interface_tick_calls"] = 0
        data["queues"].update(sample_count=0, aggregated_sample_count=0)
        for name in ("reservation", "read", "write", "compute", "active_functions"):
            data["queues"][name] = {"sum": 0, "max": 0}
        result = validate_observability(data)
        self.assertTrue(result["contract_valid"], result["issues"])
        self.assertIsNone(result["metrics"]["queues.read.max"]["value"])
        self.assertEqual(result["metrics"]["queues.read.max"]["availability"], "not_observed")
        self.assertIsNone(result["metrics"]["queues.read.mean"]["value"])
        self.assertEqual(result["metrics"]["queues.read.mean"]["availability"], "not_observed")

    def test_current_loader_preserves_hash_provenance_and_rejects_tamper(self):
        path = self.write_payload(payload())
        digest = file_hash(path)
        result = load_observability(path, expected_sha256=digest)
        self.assertTrue(result["contract_valid"])
        self.assertTrue(result["provenance"]["hash_verified"])
        self.assertEqual(result["provenance"]["path"], str(path.resolve()))
        data = payload()
        data["execution"].update(queued_compute_commits=8, selected_commits_total=11)
        path.write_text(json.dumps(data))
        self.assertFalse(load_observability(path, expected_sha256=digest)["contract_valid"])

    def test_duplicate_nonfinite_and_unknown_schema_do_not_become_measurements(self):
        for content in ['{"kind":"a","kind":"b"}', '{"value": NaN}', '{"value": Infinity}', '[]']:
            path = self.base / "invalid.json"
            path.write_text(content)
            self.assertFalse(load_observability(path)["contract_valid"])
        data = payload()
        data["schema_version"] = 2
        result = validate_observability(data)
        self.assertEqual(result["status"], "unsupported_schema")
        self.assertFalse(result["contract_valid"])

    def test_explicit_nested_and_flat_legacy_paths_preserve_raw_values_without_defaults(self):
        data = {"salam_stats": {"version": "3.0", "memory_access": {
            "cache": {"hits": 37}, "spm": {"reads": 0}, "latency": {"avg_read": 12},
            "cache_hits": 99, "avg_read_latency": 17}, "power": {"total_power": 0}}}
        nested = adapt_legacy(data, "legacy_nested_v3")
        flat = adapt_legacy(data, "legacy_flat_v3")
        self.assertEqual(nested["metrics"]["cache_hits"]["raw_value"], 37)
        self.assertEqual(flat["metrics"]["cache_hits"]["raw_value"], 99)
        self.assertEqual(nested["metrics"]["cache_hits"]["source_path"], "/salam_stats/memory_access/cache/hits")
        self.assertEqual(nested["metrics"]["spm_reads"]["raw_value"], 0)
        self.assertEqual(flat["metrics"]["spm_reads"]["availability"], "missing")
        self.assertIsNone(flat["metrics"]["spm_reads"]["raw_value"])
        self.assertIsNone(nested["metrics"]["power"]["value"])
        self.assertIsNone(nested["metrics"]["avg_read_latency"]["unit"])
        self.assertEqual(nested["metrics"]["avg_read_latency"]["claimed_unit"], "unknown")
        self.assertFalse(nested["contract_valid"])
        self.assertEqual(nested["status"], "legacy_unvalidated")
        self.assertEqual(validate_observability(data)["status"], "unsupported_schema")
        self.assertFalse(adapt_legacy(payload(), "legacy_flat_v3")["contract_valid"])

    def test_legacy_file_keeps_source_hash_and_unknown_measurement_state(self):
        path = self.write_payload({"salam_stats": {"version": "3.0", "memory_access": {"cache_hits": 5}}})
        result = load_observability(path, legacy_format="legacy_flat_v3", expected_sha256=file_hash(path))
        self.assertTrue(result["provenance"]["hash_verified"])
        self.assertEqual(result["metrics"]["cache_hits"]["raw_value"], 5)
        self.assertIsNone(result["metrics"]["cache_hits"]["value"])
        self.assertEqual(result["status"], "legacy_unvalidated")

    def recorded_run(self):
        entries = []
        for name in ("system.gemm_clstr.gemm", "system.gemm_clstr.top"):
            relative = "simulator/observability/" + name + ".invocation-1.json"
            path = self.write_payload(payload(name), relative)
            entries.append({"path": relative, "sha256": file_hash(path)})
        record = {"artifacts": entries}
        experiment = {"observability": {"kind": "salam_observability", "schema_version": 1,
                      "expected_invocations": {"system.gemm_clstr.gemm": [1], "system.gemm_clstr.top": [1]},
                      "oracles": {"system.gemm_clstr.gemm": {"memory.reads.completed": 2,
                                  "memory.reads.completed_bytes": 8, "memory.writes.completed": 1,
                                  "memory.writes.completed_bytes": 4}}}}
        return record, experiment

    def test_absent_contract_is_unavailable_without_invalidating_historical_run(self):
        result = assess_run_observability(self.base, {}, {})
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["valid"])
        self.assertEqual(result["issues"], [])

    def test_exact_expected_invocations_and_known_oracles_are_accepted(self):
        record, experiment = self.recorded_run()
        result = assess_run_observability(self.base, record, experiment)
        self.assertTrue(result["valid"], result["issues"])
        self.assertEqual(result["observed_invocations"], experiment["observability"]["expected_invocations"])
        self.assertEqual(len(result["records"]), 2)
        self.assertTrue(all(item["provenance"]["hash_verified"] for item in result["records"]))

    def test_missing_extra_duplicate_wrong_oracle_and_tampered_hash_reject_run(self):
        record, experiment = self.recorded_run()
        missing = copy.deepcopy(record)
        missing["artifacts"].pop()
        self.assertFalse(assess_run_observability(self.base, missing, experiment)["valid"])
        duplicate = copy.deepcopy(record)
        duplicate["artifacts"].append(duplicate["artifacts"][0])
        self.assertFalse(assess_run_observability(self.base, duplicate, experiment)["valid"])
        extra = copy.deepcopy(record)
        relative = "simulator/observability/system.gemm_clstr.gemm.invocation-2.json"
        path = self.write_payload(payload(invocation=2), relative)
        extra["artifacts"].append({"path": relative, "sha256": file_hash(path)})
        self.assertFalse(assess_run_observability(self.base, extra, experiment)["valid"])
        wrong = copy.deepcopy(experiment)
        wrong["observability"]["oracles"]["system.gemm_clstr.gemm"]["memory.reads.completed"] = 1024
        self.assertFalse(assess_run_observability(self.base, record, wrong)["valid"])
        (self.base / record["artifacts"][0]["path"]).write_text(json.dumps(payload(invocation=2)))
        self.assertFalse(assess_run_observability(self.base, record, experiment)["valid"])

    def test_unrecorded_files_cannot_satisfy_required_invocation(self):
        record, experiment = self.recorded_run()
        record["artifacts"] = []
        result = assess_run_observability(self.base, record, experiment)
        self.assertFalse(result["valid"])
        self.assertEqual(result["records"], [])

    def test_artifact_traversal_and_identity_filename_mismatch_are_rejected(self):
        record, experiment = self.recorded_run()
        bad = copy.deepcopy(record)
        bad["artifacts"][0]["path"] = "simulator/observability/../../outside.json"
        self.assertFalse(assess_run_observability(self.base, bad, experiment)["valid"])
        data = payload("system.other")
        path = self.base / record["artifacts"][0]["path"]
        path.write_text(json.dumps(data))
        record["artifacts"][0]["sha256"] = file_hash(path)
        self.assertFalse(assess_run_observability(self.base, record, experiment)["valid"])


if __name__ == "__main__":
    unittest.main()
