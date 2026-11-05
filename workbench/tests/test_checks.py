"""Check receipts use harmless child programs; no simulator or compiler is run."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import venv
from pathlib import Path
from unittest import mock

from salam_workbench import checks
from salam_workbench.runner import file_hash


class CheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="salam-check-fixture-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        (self.project / "salam_workbench").mkdir(parents=True)
        self.source = self.project / "salam_workbench" / "fixture.py"
        self.source.write_text("# original source\n")
        self.evidence = self.root / "evidence"
        self.engine = self.root / "engine"
        self.engine.mkdir()

    def plan(self, script=None):
        def make(tier, project, evidence, engine, **options):
            code = script
            if code is None:
                code = (
                    "from pathlib import Path; import json; "
                    "Path("
                    + repr(str(evidence / "unit-results.json"))
                    + ").write_text("
                    "json.dumps({'success': True, 'tests_run': 1, 'available': True})); "
                    "print('harmless check fixture')"
                )
            return [
                {
                    "name": "fixture",
                    "argv": [sys.executable, "-B", "-c", code],
                    "cwd": str(project),
                    "environment_overrides": {},
                }
            ]

        return mock.patch.object(checks, "build_plan", side_effect=make)

    def run_fixture(self, **options):
        return checks.run_checks(
            "fast",
            project_root=self.project,
            evidence_root=self.evidence,
            **options,
        )

    def test_pass_retains_commands_logs_sources_and_hashes(self):
        with self.plan():
            result = self.run_fixture(check_id="pass")
        self.assertEqual(result["state"], "passed", result["issues"])
        self.assertTrue(result["tooling_unchanged"])
        self.assertTrue(result["steps"][0]["executable_unchanged_after_run"])
        self.assertEqual(result["steps"][0]["argv"][0], sys.executable)
        directory = Path(result["evidence_directory"])
        snapshot = directory / "source-snapshot/files/salam_workbench/fixture.py"
        self.assertEqual(snapshot.read_bytes(), self.source.read_bytes())
        self.assertIn(
            "harmless check fixture",
            (directory / "00-fixture.stdout").read_text(),
        )
        for artifact in result["artifacts"]:
            self.assertEqual(
                file_hash(directory / artifact["path"]), artifact["sha256"]
            )
        self.assertEqual(
            json.loads((directory / "check.json").read_text())["state"],
            "passed",
        )

    def test_failure_preserves_output_without_claiming_validation(self):
        with self.plan("import sys; print('before failure'); sys.exit(7)"):
            result = self.run_fixture(check_id="failure")
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["steps"][0]["return_code"], 7)
        self.assertNotIn("validation_result", result)
        self.assertIn(
            "before failure",
            (self.evidence / "failure/00-fixture.stdout").read_text(),
        )

    def test_missing_required_result_cannot_pass_exit_zero(self):
        with self.plan("print('no structured test result')"):
            result = self.run_fixture(check_id="missing")
        self.assertEqual(result["state"], "failed")
        self.assertTrue(any("FileNotFoundError" in issue for issue in result["issues"]))

    def test_timeout_has_owned_process_receipt(self):
        with self.plan("import time; time.sleep(30)"):
            result = self.run_fixture(check_id="timeout", timeout_seconds=0.1)
        self.assertEqual(result["state"], "timed_out")
        self.assertTrue(result["steps"][0]["timed_out"])
        self.assertIsNotNone(result["steps"][0]["return_code"])

    def test_source_mutation_keeps_snapshot_and_invalidates_pass(self):
        code = (
            "from pathlib import Path; import json; "
            "Path(" + repr(str(self.source)) + ").write_text('# changed source\\n'); "
            "Path("
            + repr(str(self.evidence / "mutation/unit-results.json"))
            + ").write_text("
            "json.dumps({'success': True, 'available': True}))"
        )
        with self.plan(code):
            result = self.run_fixture(check_id="mutation")
        self.assertEqual(result["state"], "incomplete")
        self.assertFalse(result["tooling_unchanged"])
        self.assertEqual(
            (
                self.evidence
                / "mutation/source-snapshot/files/salam_workbench/fixture.py"
            ).read_text(),
            "# original source\n",
        )

    def test_independent_checker_mutation_invalidates_identity_and_retains_before_image(
        self,
    ):
        checker = self.project / "scripts/verify_numpy_outputs.py"
        checker.parent.mkdir()
        original = "# independent checker before image\n"
        checker.write_text(original)
        before = checks.source_identity(self.project)
        self.assertIn("scripts/verify_numpy_outputs.py", before["files"])
        code = (
            "from pathlib import Path; import json; "
            "Path(" + repr(str(checker)) + ").write_text('# altered checker\\n'); "
            "Path("
            + repr(str(self.evidence / "checker-mutation/unit-results.json"))
            + ").write_text(json.dumps({'success': True, 'available': True}))"
        )
        with self.plan(code):
            result = self.run_fixture(check_id="checker-mutation")
        self.assertEqual(result["state"], "incomplete")
        self.assertFalse(result["tooling_unchanged"])
        self.assertNotEqual(
            before["sha256"], checks.source_identity(self.project)["sha256"]
        )
        self.assertEqual(
            (
                self.evidence
                / "checker-mutation/source-snapshot/files/scripts/verify_numpy_outputs.py"
            ).read_text(),
            original,
        )

    def test_child_plan_preserves_real_venv_dependencies_and_hashes_resolved_binary(
        self,
    ):
        selected = self.root / "selected-python-environment"
        venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(selected)
        python = selected / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        site = (
            selected / "Lib/site-packages"
            if os.name == "nt"
            else next((selected / "lib").glob("python*/site-packages"))
        )
        (site / "salam_only_selected_venv_dependency.py").write_text("VALUE = 7351\n")
        self.evidence.mkdir()
        with mock.patch.object(checks.sys, "executable", str(python)):
            plan = checks.build_plan("fast", self.project, self.evidence)
        probe = (
            "import json,sys,salam_only_selected_venv_dependency as dependency; "
            "print(json.dumps({'prefix':sys.prefix,'dependency':dependency.VALUE}))"
        )
        step = dict(
            plan[0],
            name="selected-venv-dependency",
            argv=[plan[0]["argv"][0], "-B", "-c", probe],
        )
        result = checks._execute_step(step, 0, self.evidence, 20)
        self.assertEqual(
            result["return_code"], 0, (self.evidence / result["stderr"]).read_text()
        )
        observed = json.loads((self.evidence / result["stdout"]).read_text())
        self.assertEqual(Path(observed["prefix"]).resolve(), selected.resolve())
        self.assertEqual(observed["dependency"], 7351)
        self.assertEqual(step["argv"][0], str(python))
        self.assertEqual(
            result["executable_sha256"], file_hash(python.resolve(strict=True))
        )
        self.assertTrue(result["executable_unchanged_after_run"])
        base = Path(getattr(sys, "_base_executable", sys.executable)).resolve(
            strict=True
        )
        negative = subprocess.run(
            [str(base), "-B", "-c", "import salam_only_selected_venv_dependency"],
            cwd=self.project,
            capture_output=True,
            text=True,
            timeout=20,
            shell=False,
        )
        self.assertNotEqual(
            negative.returncode,
            0,
            "System Python unexpectedly imported the isolated venv dependency",
        )

    def test_reused_id_refuses_to_replace_previous_receipt(self):
        with self.plan():
            self.run_fixture(check_id="once", plan_only=True)
            before = (self.evidence / "once/check.json").read_bytes()
            with self.assertRaises(FileExistsError):
                self.run_fixture(check_id="once")
        self.assertEqual((self.evidence / "once/check.json").read_bytes(), before)

    def test_plan_only_does_not_launch_commands(self):
        with self.plan(), mock.patch.object(checks, "_execute_step") as execute:
            result = self.run_fixture(check_id="planned", plan_only=True)
        execute.assert_not_called()
        self.assertEqual(result["state"], "planned")
        self.assertEqual(result["steps"], [])
        self.assertTrue((self.evidence / "planned/plan.json").is_file())

    def test_simulation_refusal_is_durable_and_does_not_execute(self):
        with mock.patch.object(checks, "_execute_step") as execute:
            result = checks.run_checks(
                "gemm",
                project_root=self.project,
                engine=self.engine,
                evidence_root=self.evidence,
                check_id="no-simulation",
            )
        execute.assert_not_called()
        self.assertEqual(result["state"], "failed")
        self.assertTrue(
            any("--allow-simulation" in issue for issue in result["issues"])
        )
        self.assertTrue((self.evidence / "no-simulation/check.json").is_file())

    def test_gemm_plan_requires_separate_build_permission(self):
        evidence = self.evidence / "allowed"
        plan = checks.build_plan(
            "gemm", self.project, evidence, self.engine, allow_simulation=True
        )
        self.assertNotIn("--build-engine", plan[0]["argv"])
        self.assertEqual(
            plan[0]["argv"][plan[0]["argv"].index("--runs-root") + 1],
            str(evidence / "runs"),
        )
        built = checks.build_plan(
            "gemm",
            self.project,
            evidence,
            self.engine,
            allow_simulation=True,
            build_engine=True,
        )
        self.assertIn("--build-engine", built[0]["argv"])
        with self.assertRaises(ValueError):
            checks.build_plan("fast", self.project, evidence, build_engine=True)

    def test_missing_compiler_is_unavailable_not_passed(self):
        with mock.patch.object(checks.shutil, "which", return_value=None):
            result = checks.run_checks(
                "collector",
                project_root=self.project,
                engine=self.engine,
                evidence_root=self.evidence,
                check_id="no-compiler",
            )
        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(result["steps"], [])

    def test_collector_compiles_only_into_new_evidence_directory(self):
        for relative in (
            "src/hwacc/workbench_statistics.hh",
            "src/hwacc/tests/test_workbench_statistics.cc",
        ):
            path = self.engine / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("// synthetic planning fixture\n")
        with mock.patch.object(checks.shutil, "which", return_value=sys.executable):
            plan = checks.build_plan(
                "collector", self.project, self.evidence, self.engine
            )
        output = Path(plan[1]["argv"][plan[1]["argv"].index("-o") + 1])
        output.relative_to(self.evidence)
        self.assertEqual(plan[2]["argv"], [str(output)])
        self.assertNotIn(str(self.engine / "build"), str(plan))

    def test_gui_selection_and_dependency_failure_are_explicit(self):
        candidate = mock.Mock()
        candidate.id.return_value = "test_offline_viewer.Tests.test_offscreen_window"
        self.assertTrue(checks._gui_test(candidate))
        candidate.id.return_value = (
            "test_offline_viewer.Tests.test_historical_unavailable"
        )
        self.assertFalse(checks._gui_test(candidate))
        destination = self.root / "unavailable.json"
        with mock.patch.object(
            checks.importlib,
            "import_module",
            side_effect=ImportError("missing Qt fixture"),
        ):
            status = checks.run_unit_tier("gui", destination)
        result = json.loads(destination.read_text())
        self.assertEqual(status, 2)
        self.assertFalse(result["available"])
        self.assertFalse(result["success"])
        self.assertEqual(result["tests_run"], 0)

    def test_invalid_collector_json_is_not_simulation_evidence(self):
        output = self.root / "collector.stdout"
        output.write_text('{"kind":"not-a-collector"}')
        destination = self.root / "validation.json"
        self.assertEqual(checks._verify_collector(output, destination), 1)
        result = json.loads(destination.read_text())
        self.assertFalse(result["success"])
        self.assertFalse(result["simulation_evidence"])

    def gemm_session(self):
        check_dir = self.evidence / "gemm"
        check_dir.mkdir(parents=True)
        session = self.project / "evidence/gemm-fixture"
        session.mkdir(parents=True)
        paths = [check_dir / "runs" / name for name in ("a", "b", "negative")]
        document = {
            "state": "passed",
            "baseline_runs": [{"directory": str(path)} for path in paths[:2]],
            "negative_witness": {"directory": str(paths[2])},
        }
        (session / "session.json").write_text(json.dumps(document))
        output = check_dir / "00-gemm-reproduction.stdout"
        output.write_text("Session evidence: " + str(session) + "\n")
        negative = {
            "recorded_state": "failed",
            "raw_correctness": {"outcome": "failed"},
            "verified_required_artifacts": {"guest": True},
            "issues": ["Run state is not passed: failed"],
        }
        return output, session, document, negative

    def test_gemm_verifier_revalidates_raw_negative_and_fresh_comparison(self):
        output, session, document, negative = self.gemm_session()
        destination = output.parent / "validation.json"
        with mock.patch.object(checks, "PROJECT", self.project), mock.patch(
            "salam_workbench.report.compare_runs",
            return_value={"repeatability_accepted": True, "issues": []},
        ) as compare, mock.patch(
            "salam_workbench.report.load_run", return_value=negative
        ) as load:
            self.assertEqual(checks._verify_gemm(output, destination), 0)
            compare.assert_called_once()
            load.assert_called_once()
            negative["verified_required_artifacts"]["guest"] = False
            self.assertEqual(checks._verify_gemm(output, destination), 1)
        self.assertFalse(
            json.loads(destination.read_text())["negative_witness_verified"]
        )

    def test_gemm_verifier_rejects_old_or_unrelated_run_directories(self):
        output, session, document, negative = self.gemm_session()
        document["baseline_runs"][0]["directory"] = str(self.root / "old-run")
        (session / "session.json").write_text(json.dumps(document))
        with mock.patch.object(checks, "PROJECT", self.project), mock.patch(
            "salam_workbench.report.compare_runs"
        ) as compare:
            with self.assertRaises(ValueError):
                checks._verify_gemm(output, output.parent / "validation.json")
        compare.assert_not_called()

    def test_gemm_verifier_requires_distinct_baseline_runs(self):
        output, session, document, negative = self.gemm_session()
        document["baseline_runs"][1] = dict(document["baseline_runs"][0])
        (session / "session.json").write_text(json.dumps(document))
        with mock.patch.object(checks, "PROJECT", self.project), mock.patch(
            "salam_workbench.report.compare_runs"
        ) as compare:
            with self.assertRaisesRegex(ValueError, "two distinct"):
                checks._verify_gemm(output, output.parent / "validation.json")
        compare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
