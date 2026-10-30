"""Independent GUI-to-simulation witness regression cases."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from salam_workbench.configurator import compiled_identity
from salam_workbench.gui_editor import build_gui_request, extract_components
from salam_workbench.gui_effective import _sha, witness_gui_effective


BASE = {
    "acc_cluster": [
        {"Name": "demo_clstr"},
        {"DMA": [{"Name": "dma", "Type": "NonCoherent", "BufferSize": 256,
                  "MaxReqSize": 32, "PIOMaster": "LocalBus", "InterruptNum": 95}]},
        {"Accelerator": [
            {"Name": "demo", "IrPath": "benchmarks/sys_validation/demo/hw/demo.ll",
             "PIOSize": 32, "PIOMaster": "LocalBus", "LocalSlaves": "LocalBus",
             "Debug": False},
            {"Var": [{"Name": "DATA", "Type": "SPM", "Size": 128,
                      "Ports": 3, "ReadyMode": True}]}]},
    ],
    "hw_config": {"demo": {
        "instructions": {"add": {"runtime_cycles": 2, "functional_unit": 1}},
        "functional_units": {"integer_adder": {"cycles": 3, "limit": 0}},
    }},
}


INI = """[system.demo_clstr.dma]
buffer_size=256
max_req_size=32
int_num=95
pio_addr=268566528
cluster_dma=system.demo_clstr.local_bus.cpu_side_ports[0]
dma=system.demo_clstr.coherency_bus.cpu_side_ports[0]
pio=system.demo_clstr.local_bus.mem_side_ports[0]
[system.demo_clstr.demo]
type=CommInterface
enable_debug_msgs=false
pio=system.demo_clstr.local_bus.mem_side_ports[1]
local=system.demo_clstr.local_bus.cpu_side_ports[1]
[system.demo_clstr.data]
type=ScratchpadMemory
range=268566656:268566784
ready_mode=true
port=system.demo_clstr.local_bus.mem_side_ports[2]
spm_ports=system.demo_clstr.demo.spm[0] system.demo_clstr.demo.spm[1] system.demo_clstr.demo.spm[2]
[system.demo_clstr.demo.hw_interface.cycle_counts]
add=2
[system.demo_clstr.demo.hw_interface.inst_config.add]
functional_unit=1
[system.demo_clstr.demo.hw_interface.functional_units.integer_adder]
cycles=3
limit=0
"""


class GuiEffectiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = self.root / "engine"
        self.workspace = self.root / "pipeline/workspace"
        self.evidence = self.root / "pipeline"
        self.benchmark = "benchmarks/sys_validation/demo"
        source = self.engine / self.benchmark / "config.yml"
        self.write(source, yaml.safe_dump(BASE, sort_keys=False))
        cluster, components = extract_components(BASE)
        self.snapshot = {"cluster_name": cluster, "components": components,
                         "hardware_target": "demo",
                         "functional_units": {"integer_adder": {"cycles": 3, "limit": 0}},
                         "instructions": {"add": {"runtime_cycles": 2, "functional_unit": 1}},
                         "base_address": "0x10020000", "alignment": 64,
                         "system": {"mem-size": "2GB"},
                         "hardware_profile": {"model": "40nm_model", "period": "10ns",
                                              "profile": "default_profile", "fu_overrides": {}}}
        self.request = build_gui_request(BASE, self.snapshot, benchmark=self.benchmark,
                                         engine_root=self.engine, distro="Ubuntu-20.04",
                                         source_config_relative=self.benchmark + "/config.yml",
                                         source_config_sha256=_sha(source))
        self.spec = {"schema_version": 1, "name": "demo", "benchmark": self.benchmark,
                     "configuration_documents": self.request["configuration_documents"],
                     "system": self.request["system"], "parameters": {},
                     "base_address": self.request["base_address"]}
        self.write(self.evidence / "request.json", json.dumps(self.request, sort_keys=True))
        self.write(self.evidence / "normalization.json", json.dumps({
            "raw_request_sha256": _sha(self.evidence / "request.json"),
            "configuration_documents_before": self.request["configuration_documents"],
            "configuration_documents_after": self.spec["configuration_documents"],
            "transformations": [], "consumer_sources": {}}, sort_keys=True))
        self.write(self.workspace / self.benchmark / "config.yml",
                   yaml.safe_dump_all(self.spec["configuration_documents"], sort_keys=False))
        self.write(self.workspace / self.benchmark / "hw/demo.ll", 'target triple = "armv7--linux-gnueabihf"\n')
        config = self.workspace / self.benchmark / "config.yml"
        ir = self.workspace / self.benchmark / "hw/demo.ll"
        self.write(self.workspace / "configs/SALAM/generated/demo.py",
                   "def makeHWAcc():\n    ir = {!r}\n    config = {!r}\n".format(str(ir), str(config)))
        self.ini = self.evidence / "runs/test/simulator/config.ini"
        self.write(self.ini, INI)
        self.write(self.ini.parent / "stats.txt", "simFreq 1000000000000\n")
        self.write(self.evidence / "system-live.json", "{}")
        self.write(self.engine / "SConstruct", "# build\n")
        outputs = []
        for kind, relative in (("compiled_source", "src/hwacc/a.cc"),
                               ("simobject_source", "src/hwacc/FunctionalUnits.py"),
                               ("build_declaration", "src/hwacc/SConscript")):
            path = self.engine / relative
            self.write(path, "# " + kind + "\n")
            outputs.append({"kind": kind, "relative_path": relative, "sha256": _sha(path)})
        binary = self.engine / "build/ARM/gem5.opt"
        self.write(binary, "binary")
        self.build = {"state": "built", "compiled_source_sha256": compiled_identity(self.engine)["sha256"],
                      "binary": {"path": str(binary), "sha256": _sha(binary)}}
        self.write(self.evidence / "gui-execution.json",
                   json.dumps({"selected_engine": str(self.engine)}, sort_keys=True))
        self.generation = {"state": "generated", "valid": True,
                           "engine_root": str(self.engine), "outputs": outputs,
                           "selection": {"benchmark": "demo", "model": "40nm_model",
                                         "period": "10ns", "profile": "default_profile"},
                           "profile_overrides": {}}
        self.write(self.evidence / "configuration.json", json.dumps({
            "state": "passed", "simulation_requested": True,
            "run_state": "passed", "numerical_correctness": "guest_checker_passed",
            "commands": [{"stdout": name + ".stdout", "state": "completed", "return_code": 0}
                         for name in ("generate", "build-ir", "build-guest")],
            "engine": {"binary": {"sha256": self.build["binary"]["sha256"]},
                       "compiled_source_sha256": self.build["compiled_source_sha256"]}}, sort_keys=True))

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def witness(self, *, gui_evidence_dir=None, normalization_receipt=None):
        with patch("salam_workbench.gui_effective.witness_system", return_value={"state": "passed"}), \
                patch("salam_workbench.gui_effective.witness_profiles", return_value={"state": "passed"}):
            return witness_gui_effective(self.request, self.spec, self.workspace,
                                         self.evidence, self.ini, build_receipt=self.build,
                                         generation_receipt=self.generation,
                                         normalization_receipt=normalization_receipt or
                                         self.evidence / "normalization.json",
                                         gui_evidence_dir=gui_evidence_dir)

    def test_matching_request_port_graph_and_receipts_pass(self):
        result = self.witness()
        self.assertEqual(result["state"], "passed", result["issues"])
        ports = [item for item in result["checks"] if item["field"] == "graph.data.spm_ports.demo"]
        self.assertEqual(ports[0]["observed"], 3)

    def test_corrupt_effective_memory_or_port_count_fails(self):
        self.write(self.ini, INI.replace("buffer_size=256", "buffer_size=128").replace(
            "system.demo_clstr.demo.spm[2]", "system.demo_clstr.top.spm[2]"))
        result = self.witness()
        self.assertEqual(result["state"], "failed")
        fields = {item["field"] for item in result["issues"]}
        self.assertIn("dma.dma.BufferSize", fields)
        self.assertIn("graph.data.spm_ports.demo", fields)

    def test_selected_gui_profile_different_from_generated_build_fails(self):
        self.generation["selection"]["period"] = "5ns"
        result = self.witness()
        self.assertEqual(result["state"], "failed")
        self.assertIn("hardware_profile.period", {item["field"] for item in result["issues"]})

    def test_legacy_generation_receipt_without_empty_overrides_passes(self):
        del self.generation["profile_overrides"]
        result = self.witness()
        self.assertEqual(result["state"], "passed", result["issues"])

    def test_legacy_generation_receipt_cannot_cover_nonempty_overrides(self):
        del self.generation["profile_overrides"]
        self.request["provenance"]["editor_snapshot"]["hardware_profile"][
            "fu_overrides"] = {"integer_adder": {"internal_power": "0.0125"}}
        self.request["hardware_profile"]["fu_overrides"] = {
            "integer_adder": {"internal_power": 0.0125}}
        self.write(self.evidence / "request.json", json.dumps(self.request, sort_keys=True))
        receipt = json.loads((self.evidence / "normalization.json").read_text())
        receipt["raw_request_sha256"] = _sha(self.evidence / "request.json")
        self.write(self.evidence / "normalization.json", json.dumps(receipt, sort_keys=True))
        result = self.witness()
        self.assertEqual(result["state"], "failed")
        self.assertIn("hardware_profile.fu_overrides",
                      {item["field"] for item in result["issues"]})

    def test_widget_snapshot_disagreement_fails(self):
        self.request["provenance"]["editor_snapshot"]["components"][1]["pio_size"] = 64
        self.write(self.evidence / "request.json", json.dumps(self.request, sort_keys=True))
        receipt = json.loads((self.evidence / "normalization.json").read_text())
        receipt["raw_request_sha256"] = _sha(self.evidence / "request.json")
        self.write(self.evidence / "normalization.json", json.dumps(receipt, sort_keys=True))
        result = self.witness()
        self.assertEqual(result["state"], "failed")
        self.assertIn("editor_snapshot.rendered_configuration",
                      {item["field"] for item in result["issues"]})

    def test_parent_gui_request_and_child_pipeline_receipts_are_distinct(self):
        gui = self.root / "gui-apply"
        self.write(gui / "request.json", (self.evidence / "request.json").read_text())
        self.write(gui / "normalization.json",
                   (self.evidence / "normalization.json").read_text())
        self.write(gui / "gui-execution.json",
                   (self.evidence / "gui-execution.json").read_text())
        result = self.witness(gui_evidence_dir=gui,
                              normalization_receipt=gui / "normalization.json")
        self.assertEqual(result["state"], "passed", result["issues"])

    def test_rebuilt_variant_engine_can_differ_from_gui_source_checkout(self):
        variant = self.root / "variant"
        shutil.copytree(self.engine, variant)
        self.build["binary"]["path"] = str(variant / "build/ARM/gem5.opt")
        self.write(self.evidence / "gui-execution.json",
                   json.dumps({"selected_engine": str(variant)}, sort_keys=True))
        # The generation source remains the GUI's base checkout; installed
        # output hashes and the compiled binary belong to the selected variant.
        self.generation["engine_root"] = str(self.engine)
        result = self.witness()
        self.assertEqual(result["state"], "passed", result["issues"])

    def test_raw_numeric_profile_widget_and_blank_system_field_normalize(self):
        self.request["provenance"]["editor_snapshot"]["hardware_profile"][
            "fu_overrides"] = {"integer_adder": {"internal_power": "0.012345",
                                                 "fu_latency": ""}}
        self.request["provenance"]["editor_snapshot"]["system"]["cpu-clock"] = ""
        self.request["hardware_profile"]["fu_overrides"] = {
            "integer_adder": {"internal_power": 0.012345}}
        self.generation["profile_overrides"] = {
            "integer_adder": {"internal_power": 0.012345}}
        self.write(self.evidence / "request.json", json.dumps(self.request, sort_keys=True))
        receipt = json.loads((self.evidence / "normalization.json").read_text())
        receipt["raw_request_sha256"] = _sha(self.evidence / "request.json")
        self.write(self.evidence / "normalization.json", json.dumps(receipt, sort_keys=True))
        result = self.witness()
        self.assertEqual(result["state"], "passed", result["issues"])

    def test_precision_losing_gui_profile_number_fails_closed(self):
        self.request["provenance"]["editor_snapshot"]["hardware_profile"][
            "fu_overrides"] = {"integer_adder": {"internal_power": "0.01234567890123456789"}}
        self.request["hardware_profile"]["fu_overrides"] = {
            "integer_adder": {"internal_power": 0.012345678901234568}}
        self.generation["profile_overrides"] = self.request["hardware_profile"]["fu_overrides"]
        self.write(self.evidence / "request.json", json.dumps(self.request, sort_keys=True))
        receipt = json.loads((self.evidence / "normalization.json").read_text())
        receipt["raw_request_sha256"] = _sha(self.evidence / "request.json")
        self.write(self.evidence / "normalization.json", json.dumps(receipt, sort_keys=True))
        result = self.witness()
        self.assertEqual(result["state"], "failed")
        self.assertIn("editor_snapshot.hardware_profile.fu_overrides.integer_adder.internal_power",
                      {item["field"] for item in result["issues"]})

    def test_tampered_installed_profile_data_fails_even_if_staged_copy_matches(self):
        relative = ("benchmarks/sys_validation/demo/configs/hw_interface/functional_units/"
                    "40nm_model/10ns/default_profile/integer_adder/integer_adder.yml")
        staged_root = self.root / "generation-stage"
        staged = staged_root / relative
        installed = self.engine / relative
        self.write(staged, "functional_unit:\n  power_model:\n    area: 7.25\n")
        self.write(installed, staged.read_text())
        self.generation["staged_engine_root"] = str(staged_root)
        self.generation["outputs"].append({
            "kind": "profile_data", "relative_path": relative,
            "sha256": _sha(staged), "differs_from_engine": True})
        self.write(installed, "functional_unit:\n  power_model:\n    area: 99\n")
        result = self.witness()
        self.assertEqual(result["state"], "failed")
        self.assertIn("hardware_profile.installed_output." + relative,
                      {item["field"] for item in result["issues"]})
        staged_checks = [item for item in result["checks"] if item["field"] ==
                         "hardware_profile.staged_profile." + relative]
        self.assertEqual(staged_checks[0]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
