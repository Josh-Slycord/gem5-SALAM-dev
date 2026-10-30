"""Completion gates replay evidence; process summary flags are insufficient."""
import copy
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from salam_workbench import workbench_completion as completion
from salam_workbench.runner import file_hash


class WorkbenchCompletionTests(unittest.TestCase):
    benchmark = "benchmarks/sys_validation/gemm"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.evidence = self.project / "evidence"
        self.directory = self.evidence / "attempt"
        self.directory.mkdir(parents=True)
        self.engine = self.root / "engine"
        self.engine.mkdir()
        self.base_build = self.write(
            self.evidence / "base/build.json", {"state": "built"}
        )
        self.base_generation = self.write(
            self.evidence / "base/generation.json", {"state": "generated"}
        )
        self.configuration = {
            "path": str(self.engine),
            "distribution": "Ubuntu-20.04",
            "build_receipt": self.base_build.relative_to(self.project).as_posix(),
            "generation_receipt": self.base_generation.relative_to(
                self.project
            ).as_posix(),
        }
        self.manifest = self.write(
            self.project / "workspace.json",
            {
                "engine": {"path": str(self.engine)},
                "configuration_engine": self.configuration,
            },
        )
        self.source = self.engine / self.benchmark / "config.yml"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("acc_cluster: []\n", encoding="utf-8")
        self.request = {
            "schema_version": 2,
            "action": "apply_and_run",
            "benchmark": self.benchmark,
            "engine_root": str(self.engine),
            "distro": "Ubuntu-20.04",
            "base_address": "0x10020000",
            "configuration_documents": [{"acc_cluster": []}],
            "system": {},
            "parameters": {},
            "hardware_profile": {
                "model": "40nm_model",
                "period": "5ns",
                "profile": "default_profile",
            },
            "provenance": {
                "source_config": {
                    "relative_path": self.benchmark + "/config.yml",
                    "sha256": file_hash(self.source),
                }
            },
        }
        self.request_path = self.write(self.directory / "request.json", self.request)
        (self.directory / "request-configuration.yml").write_text("acc_cluster: []\n")
        self.spec = {
            "schema_version": 1,
            "name": "gemm",
            "benchmark": self.benchmark,
            "config": self.benchmark + "/config.yml",
            "configuration_documents": self.request["configuration_documents"],
            "system": {},
            "parameters": {},
            "base_address": "0x10020000",
            "correctness": {
                "expected_passed_markers": 1,
                "description": "Real benchmark guest checker; numerical acceptance and configuration transport are assessed separately",
            },
        }
        self.spec_path = self.write(
            self.directory / "normalized-specification.json", self.spec
        )
        self.write(self.directory / "normalization.json", {"schema_version": 1})
        self.pipeline_dir = self.directory / "pipeline"
        self.workspace = self.pipeline_dir / "workspace"
        self.workspace.mkdir(parents=True)
        self.run = self.pipeline_dir / "runs/run-1"
        (self.run / "simulator").mkdir(parents=True)
        (self.run / "simulator/config.ini").write_text("[system]\n")
        self.pipeline = {
            "state": "passed",
            "simulation_requested": True,
            "run_state": "passed",
            "run_directory": str(self.run),
            "staging": {"workspace": str(self.workspace)},
            "specification": self.record(self.spec_path),
        }
        self.pipeline_path = self.write(
            self.pipeline_dir / "configuration.json", self.pipeline
        )
        self.recorded = {
            "schema_version": 1,
            "kind": "salam_gui_execution",
            "state": "passed",
            "evidence_directory": str(self.directory),
            "editor_form_applied": True,
            "simulation_requested": True,
            "pipeline_state": "passed",
            "source_config_unchanged": True,
            "source_config": self.record(self.source),
            "workspace_manifest": self.record(self.manifest),
            "selected_engine": str(self.engine),
            "pipeline_receipt": self.record(self.pipeline_path),
            "run_directory": str(self.run),
            "hardware": {
                "state": "reused_base",
                "engine_path": str(self.engine),
                "build_receipt": str(self.base_build),
                "generation_receipt": str(self.base_generation),
            },
        }
        self.receipt_path = self.write(
            self.directory / "gui-execution.json", self.recorded
        )
        self.raw_result = {
            "state": "passed",
            "benchmark": self.benchmark,
            "validation_state": "checked_recorded_evidence",
            "errors": [],
        }
        self.mocks = ExitStack()
        self.loader = self.mocks.enter_context(
            patch.object(completion, "load_run", return_value=self.raw_result)
        )
        self.validate = self.mocks.enter_context(
            patch(
                "salam_workbench.gui_execution.validate_request",
                return_value=(self.engine, self.configuration, self.source),
            )
        )
        self.importer = self.mocks.enter_context(
            patch(
                "salam_workbench.configuration_import.import_configuration",
                return_value={"documents": self.request["configuration_documents"]},
            )
        )
        self.witness = self.mocks.enter_context(
            patch(
                "salam_workbench.gui_effective.witness_gui_effective",
                return_value={
                    "state": "passed",
                    "issues": [],
                    "checks": [{"field": "test semantic check", "status": "passed"}],
                },
            )
        )

    def tearDown(self):
        self.mocks.close()
        self.temp.cleanup()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def record(self, path):
        return {
            "path": str(path),
            "sha256": file_hash(path),
            "bytes": path.stat().st_size,
        }

    def verify(self):
        return completion.verify_completion(
            self.directory,
            self.project,
            self.benchmark,
            "configured",
            expected_request=self.request,
        )

    def test_current_configured_witness_is_replayed_read_only(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = self.verify()
        self.assertEqual(result["state"], "passed", result)
        self.validate.assert_called_once_with(self.request, project=self.project)
        self.witness.assert_called_once_with(
            self.request,
            self.spec,
            self.workspace,
            self.pipeline_dir,
            self.run / "simulator/config.ini",
            build_receipt=self.base_build,
            generation_receipt=self.base_generation,
            normalization_receipt=self.directory / "normalization.json",
            gui_evidence_dir=self.directory,
        )
        after = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_saved_request_change_is_rejected_before_semantic_witness(self):
        modified = copy.deepcopy(self.request)
        modified["base_address"] = "0x10020100"
        self.write(self.request_path, modified)
        result = self.verify()
        self.assertEqual(result["state"], "failed")
        self.assertIn("dispatched live GUI request", result["errors"][0])
        self.witness.assert_not_called()

    def test_unavailable_or_failed_current_raw_result_never_completes(self):
        for validation in ("incomplete", "failed"):
            with self.subTest(validation=validation):
                self.loader.return_value = dict(
                    self.raw_result, validation_state=validation
                )
                self.assertEqual(self.verify()["state"], "failed")
        self.witness.assert_not_called()

    def test_forged_passed_wrapper_without_raw_simulation_is_rejected(self):
        from salam_workbench.workbench_results import load_run

        self.loader.side_effect = load_run
        result = self.verify()
        self.assertEqual(result["state"], "failed")
        self.assertNotEqual(
            result["result"]["validation_state"], "checked_recorded_evidence"
        )
        self.witness.assert_not_called()

    def test_recorded_passed_flags_do_not_override_semantic_witness_failure(self):
        self.witness.return_value = {
            "state": "failed",
            "issues": [{"field": "system.mem_size"}],
        }
        result = self.verify()
        self.assertEqual(result["state"], "failed")
        self.assertIn("effective settings witness failed", result["errors"][0])

    def test_empty_semantic_replay_is_not_a_pass(self):
        self.witness.return_value = {"state": "passed", "issues": [], "checks": []}
        result = self.verify()
        self.assertEqual(result["state"], "failed")
        self.assertIn("effective settings witness failed", result["errors"][0])

    def test_changed_pipeline_hash_is_rejected(self):
        changed = dict(self.pipeline, run_state="failed")
        self.write(self.pipeline_path, changed)
        result = self.verify()
        self.assertEqual(result["state"], "failed")
        self.assertIn("source hash differs", result["errors"][0])

    def test_another_workspace_manifest_cannot_be_substituted(self):
        other = self.write(self.project / "other.json", {"same": "bytes"})
        self.recorded["workspace_manifest"] = self.record(other)
        self.write(self.receipt_path, self.recorded)
        result = self.verify()
        self.assertEqual(result["state"], "failed")
        self.assertIn("another workspace manifest", result["errors"][0])

    def test_external_build_receipt_cannot_override_manifest_binding(self):
        other = self.write(self.root / "external-build.json", {"state": "built"})
        self.recorded["hardware"]["build_receipt"] = str(other)
        self.write(self.receipt_path, self.recorded)
        result = self.verify()
        self.assertEqual(result["state"], "failed")
        self.witness.assert_not_called()

    def test_typed_live_request_comparison_does_not_treat_true_as_one(self):
        self.request["test"] = True
        modified = copy.deepcopy(self.request)
        modified["test"] = 1
        self.write(self.request_path, modified)
        result = self.verify()
        self.assertEqual(result["state"], "failed")
        self.assertIn("dispatched live GUI request", result["errors"][0])

    def test_current_gui_request_validation_can_invalidate_saved_success(self):
        self.validate.side_effect = ValueError("Original source YAML changed")
        result = self.verify()
        self.assertEqual(result["state"], "failed")
        self.assertIn("Original source YAML changed", result["errors"][0])

    def test_selected_benchmark_must_match_current_raw_result(self):
        self.loader.return_value = dict(
            self.raw_result, benchmark="benchmarks/sys_validation/fft"
        )
        self.assertEqual(self.verify()["state"], "failed")

    def test_evidence_outside_project_is_rejected(self):
        result = completion.verify_completion(
            self.root,
            self.project,
            self.benchmark,
            "configured",
            expected_request=self.request,
        )
        self.assertEqual(result["state"], "failed")
        self.loader.assert_not_called()

    def test_reference_rechecks_both_positive_runs_and_the_original_session(self):
        name = "fft"
        benchmark = "benchmarks/sys_validation/fft"
        runs_root = self.directory / "runs"
        first, second = runs_root / "a", runs_root / "b"
        first.mkdir(parents=True)
        second.mkdir()
        saved = {
            "state": "passed",
            "scope": [name],
            "workloads": {
                name: {
                    "state": "supported_fixed_dataset",
                    "runs": [
                        {"directory": str(first), "state": "passed"},
                        {"directory": str(second), "state": "passed"},
                    ],
                    "comparison": {"repeatability_accepted": True},
                }
            },
        }
        session = self.write(self.evidence / "reference-original/session.json", saved)
        reference = {
            "schema_version": 1,
            "kind": "workbench_reference_session",
            "mode": "fixed_reference",
            "state": "passed",
            "benchmark": benchmark,
            "editor_settings_applied": False,
            "evidence_directory": str(self.directory),
            "engine": str(self.engine),
            "source_session": str(session),
            "source_session_sha256": file_hash(session),
            "run_directories": [str(first), str(second)],
            "run_directory": str(second),
        }
        self.write(self.directory / "reference-session.json", reference)
        self.loader.return_value = dict(self.raw_result, benchmark=benchmark)
        with patch(
            "salam_workbench.report.load_run",
            return_value={"correctness_verified": True},
        ) as raw:
            result = completion.verify_completion(
                self.directory, self.project, benchmark, "reference"
            )
        self.assertEqual(result["state"], "passed", result)
        self.assertEqual([call.args[0] for call in raw.call_args_list], [first, second])
        self.witness.assert_not_called()
        with patch(
            "salam_workbench.report.load_run",
            side_effect=[
                {"correctness_verified": True},
                {"correctness_verified": False, "issues": ["changed artifact"]},
            ],
        ):
            result = completion.verify_completion(
                self.directory, self.project, benchmark, "reference"
            )
        self.assertEqual(result["state"], "failed")
        self.assertIn("changed artifact", result["errors"][0])


if __name__ == "__main__":
    unittest.main()
