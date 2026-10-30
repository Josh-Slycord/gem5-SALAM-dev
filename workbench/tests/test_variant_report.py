"""Synthetic M2 evidence fixtures; no simulator is executed by these tests."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from salam_workbench.runner import file_hash
from salam_workbench.variant_report import STUDY, compare_variant_runs, write_variant_report


def yaml_text(value):
    return "acc_cluster: []\nhw_config:\n  gemm:\n    instructions:\n      mul:\n        runtime_cycles: " + str(value) + "\n        opcode_num: 17\n"


@unittest.skipUnless(importlib.util.find_spec("yaml"), "PyYAML is required by the supported configuration loader")
class VariantReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="salam-variant-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def fixture(self, name, latency, ticks=1000, seconds="0.000001", host="1.0", extra_stats=""):
        path = self.base / name
        (path / "simulator").mkdir(parents=True)
        (path / "inputs").mkdir()
        original_config = "/fixture/engine/benchmarks/sys_validation/gemm/config.yml"
        spec = {
            "experiment_id": "synthetic-gemm-" + str(latency),
            "source": {"revision": "r" * 40, "tree": "t" * 40, "patch_sha256": str(latency) * 64, "llvmread_tree": "same"},
            "environment": {"id": "synthetic", "toolchain_sha256": "same"},
            "workload": {"fixture": "integer gemm"}, "machine": {"cpu": "fixture-cpu"},
            "correctness": {"required_guest_marker": "Check Passed"},
            "metrics": {"deterministic": {key: {"unit": unit, "absolute_tolerance": 0} for key, unit in (("simTicks", "tick"), ("simSeconds", "second"), ("simInsts", "instruction"))}},
            "parameter_study": dict(STUDY), "hardware_parameters": {"integer_multiply_latency_cycles": latency},
        }
        (path / "experiment.json").write_text(json.dumps(spec))
        (path / "inputs/0001-config.yml").write_text(yaml_text(latency))
        (path / "inputs/0002-main.elf").write_text("synthetic unchanged guest bytes")
        (path / "simulator/system.terminal").write_text("Check Passed\n")
        (path / "stdout.txt").write_text("Exiting @ tick 2000 because m5_exit instruction encountered\n")
        (path / "stderr.txt").write_text("")
        (path / "simulator/config.ini").write_text(
            "[" + STUDY["effective_section"] + "]\nmul=" + str(latency)
            + "\nadd=0\n[system.gemm_clstr.gemm.hw_interface.inst_config.mul]\nruntime_cycles=1\n"
            + "[system]\ncache_line_size=64\n[system.terminal]\noutput_file=" + str(path / "simulator/system.terminal") + "\n")
        (path / "simulator/config.json").write_text("{}")
        (path / "simulator/stats.txt").write_text("---------- Begin Simulation Statistics ----------\n"
            + "simTicks " + str(ticks) + "\nsimSeconds " + seconds + "\nsimInsts 200\nhostSeconds " + host
            + "\n" + extra_stats + "---------- End Simulation Statistics ----------\n")
        record = {"run_id": name, "run_directory": str(path), "state": "passed", "return_code": 0,
                  "correctness": {"outcome": "passed", "passed_markers": 1, "failed_markers": 0, "guest_output": "simulator/system.terminal", "present": True},
                  "simulator_exit": {"tick": 2000, "reason": "m5_exit instruction encountered"},
                  "simulator_exit_events": [{"tick": 2000, "reason": "m5_exit instruction encountered"}],
                  "experiment_spec_sha256": file_hash(path / "experiment.json"),
                  "executable": {"path": "/fixture/gem5", "sha256": "a" * 64, "sha256_after_run": "a" * 64, "unchanged_after_run": True},
                  "inputs": [], "snapshot_inputs": True,
                  "argv": ["/fixture/gem5", "--outdir=" + str(path / "simulator"), "/fixture/config.py"],
                  "cwd": "/fixture", "environment": {"M5_PATH": "/fixture"}, "artifacts": [],
                  "required_artifacts": ["simulator/config.ini", "simulator/config.json"]}
        for original, relative in ((original_config, "inputs/0001-config.yml"), ("/fixture/engine/main.elf", "inputs/0002-main.elf")):
            digest = file_hash(path / relative)
            record["inputs"].append({"path": original, "sha256": digest, "sha256_after_run": digest, "unchanged_after_run": True,
                                    "snapshot": {"path": relative, "sha256": digest, "sha256_after_run": digest, "unchanged_after_run": True}})
        for item in path.rglob("*"):
            if item.is_file():
                record["artifacts"].append({"path": item.relative_to(path).as_posix(), "sha256": file_hash(item)})
        (path / "run.json").write_text(json.dumps(record))
        return path

    def update_file(self, run, relative, text, snapshot=False):
        path = run / relative
        path.write_text(text)
        digest = file_hash(path)
        record = json.loads((run / "run.json").read_text())
        for item in record["artifacts"]:
            if item["path"] == relative:
                item["sha256"] = digest
        if snapshot:
            for item in record["inputs"]:
                if item["snapshot"]["path"] == relative:
                    item.update(sha256=digest, sha256_after_run=digest)
                    item["snapshot"].update(sha256=digest, sha256_after_run=digest)
        if relative == "experiment.json":
            record["experiment_spec_sha256"] = digest
        (run / "run.json").write_text(json.dumps(record))

    def modify_spec(self, run, update):
        spec = json.loads((run / "experiment.json").read_text())
        update(spec)
        self.update_file(run, "experiment.json", json.dumps(spec))

    def test_one_parameter_change_accepted_with_observed_deltas(self):
        a = self.fixture("a", 1)
        b = self.fixture("b", 2, ticks=1100, seconds="0.0000011", host="1.8")
        result = compare_variant_runs(a, b)
        self.assertTrue(result["accepted"], result["issues"] + result["violations"])
        self.assertEqual(result["kind"], "gem5_parameter_comparison")
        self.assertEqual(result["metrics"][0]["delta"], "100")
        self.assertEqual(result["metrics"][0]["percent_change"], "10")
        self.assertEqual(result["metrics"][0]["unit"], "tick")
        self.assertTrue(result["effective_configuration"]["other_fields_match"])
        self.assertEqual(result["effective_configuration"]["non_witness"]["b"], "1")
        self.assertTrue(result["warnings"])  # Explicitly normalized output path.

    def test_no_speedup_or_direction_is_required(self):
        a = self.fixture("a", 1, ticks=1000)
        b = self.fixture("b", 2, ticks=900)
        result = compare_variant_runs(a, b)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["metrics"][0]["percent_change"], "-10")

    def test_additional_yaml_semantic_change_rejected(self):
        a = self.fixture("a", 1)
        b = self.fixture("b", 2)
        self.update_file(b, "inputs/0001-config.yml", yaml_text(2).replace("opcode_num: 17", "opcode_num: 18"), snapshot=True)
        self.assertEqual(compare_variant_runs(a, b)["outcome"], "rejected")

    def test_duplicate_alias_multidocument_and_boolean_yaml_fail_closed(self):
        a = self.fixture("a", 1)
        invalid = [yaml_text(2).replace("runtime_cycles: 2", "runtime_cycles: 2\n        runtime_cycles: 2"),
                   yaml_text(2) + "extra: &anchor x\nalias: *anchor\n", yaml_text(2) + "---\nx: 1\n",
                   yaml_text(2).replace("runtime_cycles: 2", "runtime_cycles: true")]
        for index, text in enumerate(invalid):
            b = self.fixture("b" + str(index), 2)
            self.update_file(b, "inputs/0001-config.yml", text, snapshot=True)
            self.assertEqual(compare_variant_runs(a, b)["outcome"], "incomplete")

    def test_only_effective_cycle_counts_field_is_parameter_witness(self):
        a = self.fixture("a", 1)
        b = self.fixture("b", 2)
        text = (b / "simulator/config.ini").read_text().replace("mul=2", "mul=1").replace("runtime_cycles=1", "runtime_cycles=2")
        self.update_file(b, "simulator/config.ini", text)
        result = compare_variant_runs(a, b)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["effective_configuration"]["parameter_witness"]["verified"])

    def test_other_effective_hardware_difference_rejected(self):
        a = self.fixture("a", 1)
        b = self.fixture("b", 2)
        self.update_file(b, "simulator/config.ini", (b / "simulator/config.ini").read_text().replace("cache_line_size=64", "cache_line_size=128"))
        result = compare_variant_runs(a, b)
        self.assertEqual(result["outcome"], "rejected")
        self.assertTrue(any(item["key"] == "cache_line_size" and item["classification"] == "unexpected" for item in result["effective_configuration"]["differences"]))

    def test_unrecognized_paths_are_not_blanket_normalized(self):
        a = self.fixture("a", 1)
        b = self.fixture("b", 2)
        self.update_file(a, "simulator/config.ini", (a / "simulator/config.ini").read_text() + "readfile=/baseline/inputs.bin\n")
        self.update_file(b, "simulator/config.ini", (b / "simulator/config.ini").read_text() + "readfile=/variant/inputs.bin\n")
        self.assertEqual(compare_variant_runs(a, b)["outcome"], "rejected")

    def test_config_ini_duplicates_or_missing_artifact_are_incomplete(self):
        a = self.fixture("a", 1)
        b = self.fixture("b", 2)
        self.update_file(b, "simulator/config.ini", (b / "simulator/config.ini").read_text().replace("mul=2", "mul=2\nmul=2"))
        self.assertEqual(compare_variant_runs(a, b)["outcome"], "incomplete")
        c = self.fixture("c", 2)
        record = json.loads((c / "run.json").read_text())
        record["artifacts"] = [item for item in record["artifacts"] if item["path"] != "simulator/config.ini"]
        (c / "run.json").write_text(json.dumps(record))
        self.assertEqual(compare_variant_runs(a, c)["outcome"], "incomplete")

    def test_non_config_input_or_source_identity_change_rejected(self):
        a = self.fixture("a", 1)
        b = self.fixture("b", 2)
        self.update_file(b, "inputs/0002-main.elf", "different executable bytes", snapshot=True)
        self.assertEqual(compare_variant_runs(a, b)["outcome"], "rejected")
        c = self.fixture("c", 2)
        self.modify_spec(c, lambda spec: spec["source"].update(tree="different tree"))
        self.assertEqual(compare_variant_runs(a, c)["outcome"], "rejected")

    def test_changed_metrics_contract_or_unsupported_parameter_rejected(self):
        a = self.fixture("a", 1)
        b = self.fixture("b", 2)
        self.modify_spec(b, lambda spec: spec["metrics"]["deterministic"]["simTicks"].update(absolute_tolerance=1))
        self.assertEqual(compare_variant_runs(a, b)["outcome"], "rejected")
        c = self.fixture("c", 2)
        self.modify_spec(c, lambda spec: spec["parameter_study"].update(id="other-study"))
        self.assertEqual(compare_variant_runs(a, c)["outcome"], "rejected")

    def test_failed_raw_correctness_or_snapshot_tampering_prevents_acceptance(self):
        a = self.fixture("a", 1)
        b = self.fixture("b", 2)
        self.update_file(b, "simulator/system.terminal", "Check Failed\n")
        self.assertEqual(compare_variant_runs(a, b)["outcome"], "incomplete")
        c = self.fixture("c", 2)
        (c / "inputs/0001-config.yml").write_text(yaml_text(3))
        self.assertEqual(compare_variant_runs(a, c)["outcome"], "incomplete")

    def test_zero_baseline_percent_and_optional_nan_are_explicit(self):
        a = self.fixture("a", 1, ticks=0)
        b = self.fixture("b", 2, extra_stats="system.gemm_clstr.gemm.cycles nan\n")
        result = compare_variant_runs(a, b)
        self.assertTrue(result["accepted"])
        self.assertIsNone(result["metrics"][0]["percent_change"])
        self.assertIn("zero", result["metrics"][0]["observation"])
        self.assertTrue(any("Optional metric" in warning for warning in result["warnings"]))

    def test_html_escaped_provenance_and_json_round_trip(self):
        a = self.fixture("a", 1)
        b = self.fixture("b", 2)
        for path in (a, b):
            self.modify_spec(path, lambda spec: spec["workload"].update(label="<script>alert(1)</script>"))
        output = self.base / "report"
        result = write_variant_report(a, b, output)
        self.assertEqual(result, json.loads((output / "comparison.json").read_text()))
        text = (output / "index.html").read_text()
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)
        self.assertIn("Full-run measurement window", text)
        self.assertIn("../a/inputs/0001-config.yml", text)
        self.assertIn("runtime_cycles: 2", text)
        with self.assertRaises(FileExistsError):
            write_variant_report(a, b, output)


if __name__ == "__main__":
    unittest.main()
