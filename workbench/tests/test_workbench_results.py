"""Synthetic reader tests; these fixtures are not simulator acceptance runs."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from salam_workbench.workbench_results import (
    discover_runs,
    load_run,
    read_artifact_text,
)


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value) if isinstance(value, dict) else value, encoding="utf-8"
    )
    return path


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _observation():
    reads = {
        "started": 2,
        "completed": 2,
        "started_bytes": 8,
        "completed_bytes": 8,
        "outstanding": 0,
        "latency_ticks": {"count": 2, "sum": 8, "min": 3, "max": 5},
    }
    writes = {
        "started": 1,
        "completed": 1,
        "started_bytes": 4,
        "completed_bytes": 4,
        "outstanding": 0,
        "latency_ticks": {"count": 1, "sum": 2, "min": 2, "max": 2},
    }
    return {
        "kind": "salam_observability",
        "schema_version": 1,
        "producer": "workbench-m3",
        "accelerator": "system.gemm_clstr.gemm",
        "invocation": 1,
        "valid": True,
        "lifecycle": {
            "start_tick": 100,
            "end_tick": 120,
            "elapsed_ticks": 20,
            "clock_period_ticks": 10,
            "tick_frequency_hz": 1000,
            "interface_tick_calls": 3,
            "completed": True,
        },
        "memory": {
            "availability": "observed",
            "scope": "Logical enqueue to final completion, including queue waiting",
            "reads": reads,
            "writes": writes,
        },
        "execution": {
            "availability": "observed_selected_commits",
            "scope": "Successful queued compute and external load/store commit callbacks only",
            "queued_compute_commits": 7,
            "memory_read_commits": 2,
            "memory_write_commits": 1,
            "selected_commits_total": 10,
        },
        "queues": {
            "availability": "observed",
            "sample_unit": "accelerator_interface_tick_entry",
            "scope": "Sum across active functions at each interface tick entry",
            "aggregation": "complete_streaming_sums_and_maxima",
            "sample_count": 3,
            "aggregated_sample_count": 3,
            "dropped_sample_count": 0,
            "raw_samples_available": False,
            "reservation": {"sum": 4, "max": 3},
            "read": {"sum": 3, "max": 2},
            "write": {"sum": 1, "max": 1},
            "compute": {"sum": 3, "max": 2},
            "active_functions": {"sum": 4, "max": 2},
        },
        "diagnostics": {"invalid_events": 0, "pending_requests": 0},
        "unsupported": {
            name: {
                "availability": "unavailable",
                "reason": "Not instrumented or characterized",
            }
            for name in (
                "cache_hits",
                "fu_utilization",
                "power",
                "area",
                "dma",
                "total_retired_instructions",
            )
        },
    }


class WorkbenchResultsTests(unittest.TestCase):
    def test_configured_study_history_uses_adjacent_saved_specification(self):
        directory = self.project / "evidence/breadth-stencil"
        directory.mkdir(parents=True)
        _write(directory / "configuration.json", {"state": "prepared"})
        _write(
            directory / "specification.json",
            {"benchmark": "benchmarks/sys_validation/stencil3d"},
        )
        rows = discover_runs(self.project)
        selected = next(row for row in rows if row["run_id"] == "breadth-stencil")
        self.assertEqual(selected["benchmark"], "benchmarks/sys_validation/stencil3d")
        self.assertEqual(selected["state"], "prepared")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="salam-results-fixture-")
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        (self.project / "evidence").mkdir()

    def raw_run(self, name="run-a", state="passed", direct=False):
        directory = self.project / "evidence" / name
        _write(
            directory / "experiment.json",
            {"benchmark": "benchmarks/sys_validation/gemm"},
        )
        _write(
            directory / "simulator/system.terminal",
            "Check Failed\n" if state == "failed" else "Check Passed\n",
        )
        _write(
            directory / "stdout.txt",
            "Exiting @ tick 100 because m5_exit instruction encountered\n",
        )
        _write(directory / "stderr.txt", "")
        _write(directory / "simulator/config.ini", "[root]\n")
        _write(
            directory / "simulator/stats.txt",
            "---------- Begin Simulation Statistics ----------\nsimTicks 100\nsimSeconds 0.1\nsimInsts 20\nhostSeconds 1\n---------- End Simulation Statistics ----------\n",
        )
        if direct:
            _write(
                directory
                / "simulator/observability/system.gemm_clstr.gemm.invocation-1.json",
                _observation(),
            )
        artifacts = [
            {"path": item.relative_to(directory).as_posix(), "sha256": _sha(item)}
            for item in sorted(directory.rglob("*"))
            if item.is_file()
        ]
        record = {
            "run_id": name,
            "state": state,
            "started_at": "2026-10-30T10:00:00+00:00",
            "finished_at": "2026-10-30T10:01:00+00:00",
            "return_code": 0,
            "correctness": {
                "guest_output": "simulator/system.terminal",
                "present": True,
                "passed_markers": 0 if state == "failed" else 1,
                "failed_markers": 1 if state == "failed" else 0,
                "outcome": state,
            },
            "artifacts": artifacts,
            "errors": [],
        }
        _write(directory / "run.json", record)
        return directory

    def test_passed_guest_is_not_independent_numerical_validation(self):
        directory = self.raw_run()
        result = load_run(directory, self.project)
        self.assertEqual(result["state"], "passed")
        self.assertEqual(result["benchmark"], "benchmarks/sys_validation/gemm")
        independent = next(
            x
            for x in result["checks"]
            if x["name"] == "Independent numerical validation"
        )
        self.assertEqual(independent["status"], "not_established")
        ticks = next(x for x in result["metrics"] if x["name"] == "simTicks")
        self.assertEqual(ticks["value"], "100")
        self.assertIn("full guest", ticks["scope"])

    def test_failed_negative_control_is_still_failed(self):
        result = load_run(self.raw_run("wrong-output", "failed"), self.project)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["validation_state"], "failed")
        checker = next(
            x for x in result["checks"] if x["name"] == "Guest numerical checker"
        )
        self.assertEqual(checker["status"], "failed")

    def test_tampered_artifact_invalidates_recorded_success(self):
        directory = self.raw_run()
        _write(directory / "simulator/stats.txt", "corrupted\n")
        result = load_run(directory, self.project)
        self.assertEqual(result["state"], "passed")
        self.assertEqual(result["validation_state"], "failed")
        self.assertTrue(any("hash mismatch" in value for value in result["errors"]))

    def test_missing_direct_output_is_unavailable_not_zero(self):
        result = load_run(self.raw_run(), self.project)
        metric = next(
            x for x in result["metrics"] if x["name"] == "Direct SALAM metrics"
        )
        self.assertIsNone(metric["value"])
        self.assertEqual(metric["status"], "unavailable")

    def test_missing_statistics_cannot_be_a_complete_current_assessment(self):
        directory = self.raw_run()
        record = json.loads((directory / "run.json").read_text())
        record["artifacts"] = [
            item
            for item in record["artifacts"]
            if item["path"] != "simulator/stats.txt"
        ]
        _write(directory / "run.json", record)
        # A receipt may not declare stats at all; absence is still incomplete.
        (directory / "simulator/stats.txt").rename(
            directory / "simulator/stats-preserved.txt"
        )
        result = load_run(directory, self.project)
        self.assertEqual(result["validation_state"], "incomplete")

    def test_direct_output_preserves_source_units_and_scope(self):
        result = load_run(self.raw_run(direct=True), self.project)
        metric = next(
            x
            for x in result["metrics"]
            if x["name"].endswith("memory.reads.completed_bytes")
        )
        self.assertEqual(metric["value"], 8)
        self.assertEqual(metric["unit"], "byte")
        self.assertTrue(metric["scope"].startswith("Direct SALAM"))
        self.assertIn(".json/", metric["source"])
        power = next(x for x in result["metrics"] if x["name"].endswith(".power"))
        self.assertIsNone(power["value"])

    def test_gui_history_deduplicates_pipeline_and_raw_aliases(self):
        directory = self.raw_run("gui-attempt/pipeline/runs/run-1")
        pipeline = directory.parent.parent
        pipeline_path = _write(
            pipeline / "configuration.json",
            {"state": "passed", "run_directory": str(directory)},
        )
        gui = pipeline.parent
        _write(gui / "request.json", {"benchmark": "benchmarks/sys_validation/gemm"})
        receipt = _write(
            gui / "gui-execution.json",
            {
                "state": "passed",
                "started_at": "2026-10-30T11:00:00Z",
                "pipeline_receipt": {
                    "path": str(pipeline_path),
                    "sha256": _sha(pipeline_path),
                },
                "effective_witness": {"state": "passed", "checks": 17, "issues": []},
            },
        )
        rows = discover_runs(self.project)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["path"], str(receipt))
        result = load_run(receipt, self.project)
        self.assertTrue(any(x["name"] == "simTicks" for x in result["metrics"]))
        _write(
            pipeline_path,
            {"state": "passed", "run_directory": str(self.project / "outside")},
        )
        result = load_run(receipt, self.project)
        self.assertTrue(any("hash mismatch" in x for x in result["errors"]))

    def test_incomplete_attempt_without_simulation_is_retained(self):
        receipt = _write(
            self.project / "evidence/attempt/gui-execution.json",
            {
                "state": "failed",
                "errors": ["Configuration unsupported"],
                "started_at": "2026-10-30T11:00:00Z",
            },
        )
        rows = discover_runs(self.project)
        self.assertEqual(len(rows), 1)
        result = load_run(receipt, self.project)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["validation_state"], "failed")
        self.assertEqual(result["metrics"], [])

    def test_history_is_bounded_sorted_and_skips_generated_workspace(self):
        self.raw_run("a")
        self.raw_run("b")
        self.raw_run("workspace/not-a-run")
        rows = discover_runs(self.project, limit=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["run_id"], "b")

    def test_outside_evidence_path_and_traversal_are_rejected(self):
        outside = _write(self.project / "outside/run.json", {"state": "passed"})
        with self.assertRaises(ValueError):
            load_run(outside, self.project)
        directory = self.raw_run()
        record = json.loads((directory / "run.json").read_text())
        record["artifacts"].append(
            {"path": "../../outside/run.json", "sha256": _sha(outside)}
        )
        _write(directory / "run.json", record)
        result = load_run(directory, self.project)
        self.assertEqual(result["validation_state"], "failed")
        self.assertTrue(any("Unsafe/missing artifact" in x for x in result["errors"]))

    def test_reference_wrapper_keeps_mode_and_original_session_link(self):
        directory = self.raw_run("reference/runs/one")
        session = _write(
            self.project / "evidence/source/session.json", {"state": "passed"}
        )
        wrapper = _write(
            self.project / "evidence/reference/reference-session.json",
            {
                "state": "passed",
                "mode": "fixed_reference",
                "benchmark": "benchmarks/sys_validation/gemm",
                "editor_settings_applied": False,
                "run_directory": str(directory),
                "source_session": str(session),
                "source_session_sha256": _sha(session),
                "run_directories": [str(directory)],
            },
        )
        result = load_run(wrapper, self.project)
        self.assertEqual(result["provenance"]["mode"], "fixed_reference")
        self.assertFalse(result["provenance"]["editor_settings_applied"])
        self.assertTrue(any(x["name"] == "simTicks" for x in result["metrics"]))

    def test_duplicate_json_keys_cannot_manufacture_success(self):
        receipt = _write(
            self.project / "evidence/bad/run.json",
            '{"state":"failed","state":"passed"}',
        )
        with self.assertRaises(ValueError):
            load_run(receipt, self.project)
        self.assertEqual(discover_runs(self.project)[0]["state"], "unreadable")

    def test_artifact_preview_accepts_runs_root_and_bounds_the_tail(self):
        path = _write(self.project / "runs/one/stdout.txt", "0123456789" * 10)
        text = read_artifact_text(path, self.project, max_bytes=12)
        self.assertTrue(text.startswith("[Showing final 12 bytes of 100 bytes]"))
        self.assertTrue(text.endswith("890123456789"))
        with self.assertRaises(ValueError):
            read_artifact_text(path, self.project, max_bytes=0)

    def test_artifact_preview_keeps_binaries_inert_and_refuses_outside_files(self):
        path = self.project / "evidence/binary.elf"
        path.write_bytes(b"ELF\x00\x01\x02")
        self.assertTrue(
            read_artifact_text(path, self.project).startswith("Binary artifact")
        )
        outside = _write(self.project / "outside.txt", "outside data")
        with self.assertRaises(ValueError):
            read_artifact_text(outside, self.project)

    def test_artifact_preview_refuses_symlinked_parent(self):
        outside = self.project / "external"
        _write(outside / "notes.txt", "outside data")
        link = self.project / "evidence/symlink"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Host does not permit creation of a test symlink")
        with self.assertRaises(ValueError):
            read_artifact_text(link / "notes.txt", self.project)

    def test_multiple_invocations_keep_distinct_metric_keys(self):
        directory = self.raw_run(direct=True)
        second = _observation()
        second["invocation"] = 2
        source = _write(
            directory
            / "simulator/observability/system.gemm_clstr.gemm.invocation-2.json",
            second,
        )
        raw = json.loads((directory / "run.json").read_text())
        raw["artifacts"].append(
            {"path": source.relative_to(directory).as_posix(), "sha256": _sha(source)}
        )
        _write(directory / "run.json", raw)
        result = load_run(directory, self.project)
        metrics = [
            x
            for x in result["metrics"]
            if x["name"].endswith("memory.reads.completed_bytes")
        ]
        self.assertEqual(len(metrics), 2)
        self.assertEqual(len({x["name"] for x in metrics}), 2)


if __name__ == "__main__":
    unittest.main()
