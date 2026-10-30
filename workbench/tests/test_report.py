"""Synthetic recorded-evidence tests; these do not execute or validate gem5."""
import json
import tempfile
import unittest
from pathlib import Path

from salam_workbench.report import compare_runs, parse_stats, write_report
from salam_workbench.runner import file_hash


def block(ticks="926491000", seconds="0.000926", insts="22660", host="1.72", extra=""):
    return (
        "---------- Begin Simulation Statistics ----------\n"
        + "simTicks "
        + ticks
        + " # Number of ticks simulated (Tick)\n"
        + "simSeconds "
        + seconds
        + " # Number of seconds simulated (Second)\n"
        + "simInsts "
        + insts
        + " # Number of instructions simulated (Count)\n"
        + "hostSeconds "
        + host
        + " # Real time elapsed on the host (Second)\n"
        + extra
        + "---------- End Simulation Statistics   ----------\n"
    )


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="salam-report-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def run_fixture(self, name, stats=None, state="passed", experiment=None):
        path = self.base / name
        (path / "simulator").mkdir(parents=True)
        (path / "simulator" / "stats.txt").write_text(
            block() if stats is None else stats
        )
        (path / "simulator" / "system.terminal").write_text("Check Passed\n")
        (path / "stdout.txt").write_text(
            "Exiting @ tick 927689000 because m5_exit instruction encountered\n"
        )
        (path / "stderr.txt").write_text("")
        spec = experiment or {
            "kind": "synthetic-record-fixture",
            "workload": "gemm",
        }
        (path / "experiment.json").write_text(json.dumps(spec))
        record = {
            "run_id": name,
            "state": state,
            "return_code": 0,
            "correctness": {
                "outcome": "passed",
                "passed_markers": 1,
                "failed_markers": 0,
                "guest_output": "simulator/system.terminal",
                "present": True,
            },
            "simulator_exit": {
                "tick": 927689000,
                "reason": "m5_exit instruction encountered",
            },
            "simulator_exit_events": [
                {
                    "tick": 927689000,
                    "reason": "m5_exit instruction encountered",
                }
            ],
            "experiment_spec_sha256": file_hash(path / "experiment.json"),
            "executable": {
                "path": "/fixture/gem5",
                "sha256": "a" * 64,
                "sha256_after_run": "a" * 64,
                "unchanged_after_run": True,
            },
            "inputs": [
                {
                    "path": "/fixture/input",
                    "sha256": "b" * 64,
                    "sha256_after_run": "b" * 64,
                    "unchanged_after_run": True,
                }
            ],
            "argv": [
                "/fixture/gem5",
                "--outdir=" + str(path / "simulator"),
                "/fixture/config.py",
            ],
            "cwd": "/fixture",
            "environment": {"M5_PATH": "/fixture"},
            "artifacts": [],
        }
        for relative in (
            "simulator/stats.txt",
            "simulator/system.terminal",
            "stdout.txt",
            "stderr.txt",
            "experiment.json",
        ):
            record["artifacts"].append(
                {"path": relative, "sha256": file_hash(path / relative)}
            )
        (path / "run.json").write_text(json.dumps(record))
        return path

    def rewrite_record(self, path, change):
        record = json.loads((path / "run.json").read_text())
        change(record)
        (path / "run.json").write_text(json.dumps(record))

    def replace_artifact(self, path, relative, text):
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

        def update(record):
            record["artifacts"] = [
                entry for entry in record["artifacts"] if entry["path"] != relative
            ]
            record["artifacts"].append({"path": relative, "sha256": file_hash(target)})

        self.rewrite_record(path, update)

    def add_snapshot(self, path):
        relative = "inputs/0001-input"
        self.replace_artifact(path, relative, "synthetic input")
        digest = file_hash(path / relative)

        def update(record):
            record["snapshot_inputs"] = True
            record["inputs"][0].update(
                sha256=digest,
                sha256_after_run=digest,
                snapshot={
                    "path": relative,
                    "sha256": digest,
                    "sha256_after_run": digest,
                    "unchanged_after_run": True,
                },
            )

        self.rewrite_record(path, update)

    def test_final_complete_block_selected_without_using_partial_tail(self):
        path = self.base / "stats.txt"
        path.write_text(
            block(ticks="1")
            + block(ticks="2")
            + "---------- Begin Simulation Statistics ----------\nsimTicks 999\n"
        )
        parsed = parse_stats(path)
        self.assertEqual(parsed["block_count"], 3)
        self.assertEqual(parsed["complete_block_count"], 2)
        self.assertEqual(parsed["incomplete_block_count"], 1)
        self.assertEqual(parsed["selected_block"]["index"], 2)
        self.assertEqual(parsed["metrics"]["simTicks"]["value"], "2")
        self.assertTrue(parsed["issues"])

    def test_missing_stats_and_unclosed_only_are_not_selected(self):
        self.assertIsNone(parse_stats(self.base / "absent")["selected_block"])
        path = self.base / "stats.txt"
        path.write_text(
            "---------- Begin Simulation Statistics ----------\nsimTicks 1\n"
        )
        self.assertIsNone(parse_stats(path)["selected_block"])

    def test_nonfinite_invalid_duplicate_and_distribution_tokens(self):
        path = self.base / "stats.txt"
        path.write_text(
            block(
                seconds="nan",
                extra="badMetric garbage\nsimTicks 88\nhist::0 3 25% 25% # distribution\n",
            )
        )
        parsed = parse_stats(path)
        self.assertEqual(parsed["metrics"]["simSeconds"]["status"], "nonfinite")
        self.assertEqual(parsed["metrics"]["badMetric"]["status"], "invalid")
        self.assertEqual(parsed["metrics"]["simTicks"]["status"], "duplicate")
        self.assertEqual(parsed["metrics"]["hist::0"]["value"], "3")

    def test_matching_repeats_allow_host_time_difference(self):
        a = self.run_fixture("a", block(host="1.2"))
        b = self.run_fixture("b", block(host="9.8"))
        result = compare_runs(a, b)
        self.assertEqual(result["outcome"], "matched")
        self.assertTrue(result["repeatability_accepted"])
        self.assertFalse(result["runs"][0]["accelerator_metrics_available"])
        host = next(
            metric for metric in result["metrics"] if metric["name"] == "hostSeconds"
        )
        self.assertFalse(host["deterministic"])
        self.assertIsNone(host["match"])

    def test_large_integer_difference_is_not_rounded_away(self):
        a = self.run_fixture("a", block(ticks="9007199254740992"))
        b = self.run_fixture("b", block(ticks="9007199254740993"))
        result = compare_runs(a, b)
        self.assertEqual(result["outcome"], "different")
        self.assertFalse(result["repeatability_accepted"])
        self.assertEqual(result["metrics"][0]["difference"], "1")

    def test_unselected_gem5_anomalies_remain_visible_without_invalidating_core_metrics(
        self,
    ):
        stats = block(
            extra="system.cpu.idleCycles 1\nsystem.cpu.idleCycles 2\nunselectedRate nan\n"
        )
        a = self.run_fixture("a", stats)
        b = self.run_fixture("b", stats)
        result = compare_runs(a, b)
        self.assertEqual(result["outcome"], "matched")
        self.assertIn(
            "system.cpu.idleCycles",
            result["runs"][0]["statistics"]["invalid_metrics"],
        )
        self.assertIn(
            "unselectedRate",
            result["runs"][0]["statistics"]["nonfinite_metrics"],
        )
        self.assertTrue(result["runs"][0]["statistics"]["warnings"])

    def test_missing_nonfinite_and_partial_metrics_prevent_acceptance(self):
        a = self.run_fixture("a")
        variants = [
            block().replace(
                "simInsts 22660 # Number of instructions simulated (Count)\n",
                "",
            ),
            block(seconds="inf"),
            block() + "---------- Begin Simulation Statistics ----------\n",
        ]
        for index, stats in enumerate(variants):
            with self.subTest(index=index):
                b = self.run_fixture("b" + str(index), stats)
                result = compare_runs(a, b)
                self.assertEqual(result["outcome"], "incomplete")
                self.assertFalse(result["repeatability_accepted"])

    def test_failed_record_cannot_claim_correctness(self):
        a = self.run_fixture("a")
        b = self.run_fixture("b", state="failed")
        result = compare_runs(a, b)
        self.assertEqual(result["outcome"], "incomplete")
        self.assertFalse(result["runs"][1]["correctness_verified"])

    def test_specification_input_and_command_differences_prevent_acceptance(
        self,
    ):
        a = self.run_fixture("a")
        b = self.run_fixture("b", experiment={"kind": "different-fixture"})
        self.assertEqual(compare_runs(a, b)["outcome"], "different")
        c = self.run_fixture("c")
        self.rewrite_record(
            c,
            lambda record: record["inputs"][0].update(
                sha256="c" * 64, sha256_after_run="c" * 64
            ),
        )
        self.assertEqual(compare_runs(a, c)["outcome"], "different")
        d = self.run_fixture("d")
        self.rewrite_record(
            d, lambda record: record["argv"].append("--different-config")
        )
        self.assertEqual(compare_runs(a, d)["outcome"], "different")

    def test_artifact_mutation_is_detected(self):
        a = self.run_fixture("a")
        b = self.run_fixture("b")
        (b / "simulator" / "system.terminal").write_text("Check Failed\n")
        self.assertEqual(compare_runs(a, b)["outcome"], "incomplete")

    def test_same_run_is_not_two_repeats(self):
        a = self.run_fixture("a")
        self.assertEqual(compare_runs(a, a)["outcome"], "incomplete")

    def test_optional_accelerator_differences_are_observations(self):
        a = self.run_fixture(
            "a",
            block(extra="system.gemm_clstr.gemm.cycles 99 # fixture counter\n"),
        )
        b = self.run_fixture(
            "b",
            block(extra="system.gemm_clstr.gemm.cycles 100 # fixture counter\n"),
        )
        result = compare_runs(a, b)
        self.assertEqual(result["outcome"], "matched")
        self.assertTrue(result["observations"])
        optional = next(
            item
            for item in result["metrics"]
            if item["name"] == "system.gemm_clstr.gemm.cycles"
        )
        self.assertIsNone(optional["match"])
        self.assertEqual(optional["observation"], "different values")
        c = self.run_fixture("c")
        self.assertEqual(compare_runs(a, c)["outcome"], "matched")
        d = self.run_fixture(
            "d",
            block(
                extra="system.gemm_clstr.gemm.cycles nan # undefined fixture counter\n"
            ),
        )
        result = compare_runs(a, d)
        self.assertEqual(result["outcome"], "matched")
        self.assertTrue(result["observations"])

    def test_declared_optional_counter_and_nonzero_tolerance_do_not_silently_pass(
        self,
    ):
        contract = {
            name: {"absolute_tolerance": 0}
            for name in (
                "simTicks",
                "simSeconds",
                "simInsts",
                "system.gemm_clstr.gemm.cycles",
            )
        }
        spec = {
            "kind": "synthetic-record-fixture",
            "metrics": {"deterministic": contract},
        }
        a = self.run_fixture(
            "a",
            block(extra="system.gemm_clstr.gemm.cycles 99\n"),
            experiment=spec,
        )
        b = self.run_fixture(
            "b",
            block(extra="system.gemm_clstr.gemm.cycles 100\n"),
            experiment=spec,
        )
        self.assertEqual(compare_runs(a, b)["outcome"], "different")
        contract["simTicks"]["absolute_tolerance"] = 1
        c = self.run_fixture(
            "c",
            block(extra="system.gemm_clstr.gemm.cycles 99\n"),
            experiment=spec,
        )
        d = self.run_fixture(
            "d",
            block(extra="system.gemm_clstr.gemm.cycles 99\n"),
            experiment=spec,
        )
        self.assertEqual(compare_runs(c, d)["outcome"], "incomplete")

    def test_declared_config_artifacts_must_be_hashed_and_present(self):
        a = self.run_fixture("a")
        b = self.run_fixture("b")
        for path in (a, b):
            self.rewrite_record(
                path,
                lambda record: record.update(
                    required_artifacts=[
                        "simulator/config.ini",
                        "simulator/config.json",
                    ]
                ),
            )
            self.replace_artifact(path, "simulator/config.ini", "synthetic config")
            self.replace_artifact(path, "simulator/config.json", "{}")
        self.assertEqual(compare_runs(a, b)["outcome"], "matched")
        self.rewrite_record(
            b,
            lambda record: record.update(
                artifacts=[
                    entry
                    for entry in record["artifacts"]
                    if entry["path"] != "simulator/config.json"
                ]
            ),
        )
        self.assertEqual(compare_runs(a, b)["outcome"], "incomplete")

    def test_raw_guest_recount_rejects_stale_summaries_even_with_updated_hash(
        self,
    ):
        a = self.run_fixture("a")
        b = self.run_fixture("b")
        self.replace_artifact(
            b, "simulator/system.terminal", "Check Passed\nCheck Failed\n"
        )
        result = compare_runs(a, b)
        self.assertEqual(result["outcome"], "incomplete")
        self.assertEqual(result["runs"][1]["raw_correctness"]["failed_markers"], 1)
        c = self.run_fixture("c")
        self.rewrite_record(
            c, lambda record: record["correctness"].update(passed_markers=2)
        )
        self.assertEqual(compare_runs(a, c)["outcome"], "incomplete")

    def test_raw_final_exit_reason_and_tick_must_agree_with_record(self):
        a = self.run_fixture("a")
        b = self.run_fixture("b")
        self.replace_artifact(
            b,
            "stdout.txt",
            "Exiting @ tick 927689000 because m5_exit instruction encountered\nExiting @ tick 927689001 because simulate() limit reached\n",
        )
        self.assertEqual(compare_runs(a, b)["outcome"], "incomplete")
        c = self.run_fixture("c")
        self.replace_artifact(
            c,
            "stdout.txt",
            "Exiting @ tick 927689001 because m5_exit instruction encountered\n",
        )
        self.assertEqual(compare_runs(a, c)["outcome"], "incomplete")

    def test_snapshot_hashes_and_recorded_executable_integrity_are_required(
        self,
    ):
        a = self.run_fixture("a")
        b = self.run_fixture("b")
        self.add_snapshot(a)
        self.add_snapshot(b)
        self.assertEqual(compare_runs(a, b)["outcome"], "matched")
        # Original executable/input paths do not exist: archived verification is local.
        self.replace_artifact(
            b,
            "inputs/0001-input",
            "changed snapshot with refreshed artifact hash",
        )
        self.assertEqual(compare_runs(a, b)["outcome"], "incomplete")
        c = self.run_fixture("c")
        self.add_snapshot(c)
        self.rewrite_record(
            c,
            lambda record: record["executable"].update(unchanged_after_run=False),
        )
        self.assertEqual(compare_runs(a, c)["outcome"], "incomplete")
        d = self.run_fixture("d")
        self.rewrite_record(d, lambda record: record.update(snapshot_inputs=True))
        self.assertEqual(compare_runs(a, d)["outcome"], "incomplete")

    def test_html_is_escaped_and_report_does_not_overwrite(self):
        spec = {
            "kind": "synthetic-record-fixture",
            "label": '<script>alert("unsafe")</script>&',
        }
        a = self.run_fixture("a", experiment=spec)
        b = self.run_fixture("b", experiment=spec)
        output = self.base / "report"
        result = write_report(a, b, output)
        document = (output / "index.html").read_text(encoding="utf-8")
        self.assertEqual(result, json.loads((output / "comparison.json").read_text()))
        self.assertNotIn("<script>", document)
        self.assertIn("&lt;script&gt;", document)
        self.assertIn("Full-run measurement window", document)
        self.assertIn("CPU reference validation", document)
        self.assertIn("../a/simulator/stats.txt", document)
        self.assertIn("direct SALAM event measurements are shown below", document)
        original = (output / "index.html").read_bytes()
        with self.assertRaises(FileExistsError):
            write_report(a, b, output)
        self.assertEqual(original, (output / "index.html").read_bytes())


if __name__ == "__main__":
    unittest.main()
