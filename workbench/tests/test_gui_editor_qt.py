"""Offscreen tests of actual independent GUI widgets; no simulator build here."""
import json
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFormLayout, QWidget

_PROJECT = Path(__file__).resolve().parents[1]
_WORKSPACE = _PROJECT / "workspace.json"
ENGINE = (
    Path(
        json.loads(_WORKSPACE.read_text(encoding="utf-8-sig"))["configuration_engine"][
            "path"
        ]
    )
    if _WORKSPACE.is_file()
    else _PROJECT / "unbound-engine"
)
GUI_SRC = ENGINE / "gem5-SALAM-gui/src"


class _WSLStatus:
    def get_selected_distro(self):
        return "Ubuntu-20.04"


@unittest.skipUnless(GUI_SRC.is_dir(), "independent WSL GUI unavailable")
class GuiEditorQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        os.environ["SALAM_WORKBENCH_ROOT"] = str(_PROJECT)
        sys.path.insert(0, str(GUI_SRC))
        from gui.config_generator import ConfigGeneratorDialog

        cls.dialog_class = ConfigGeneratorDialog

    def setUp(self):
        self.parent = QWidget()
        self.parent.wsl_status = _WSLStatus()
        self.dialog = self.dialog_class(ENGINE, self.parent)
        index = self.dialog.benchmark_combo.findData("gemm")
        self.assertGreaterEqual(index, 0)
        self.dialog.benchmark_combo.setCurrentIndex(index)
        self.assertIsNotNone(self.dialog._base_document)

    def tearDown(self):
        self.dialog.close()
        self.parent.close()

    def _component(self, name):
        tree = self.dialog.component_tree
        for index in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(index)
            if item.text(0) == name:
                return item
        self.fail("Missing component: " + name)

    def _detail(self, label):
        form = self.dialog.details_layout
        for row in range(form.rowCount()):
            name = form.itemAt(row, QFormLayout.LabelRole)
            field = form.itemAt(row, QFormLayout.FieldRole)
            if name and field and name.widget().text() == label:
                return field.widget()
        self.fail("Missing detail control: " + label)

    def test_offscreen_instruction_ids_round_trip_including_zero(self):
        source = self.dialog._base_document["hw_config"]["gemm"]["instructions"]
        rendered = self.dialog.build_config()["hw_config"]["gemm"]["instructions"]
        self.assertIn("addrspacecast", source)
        self.assertEqual(source["addrspacecast"]["functional_unit"], 0)
        self.assertEqual(
            {key: row["functional_unit"] for key, row in source.items()},
            {key: row["functional_unit"] for key, row in rendered.items()},
        )
        self.assertEqual(rendered["addrspacecast"]["functional_unit"], 0)
        row = next(
            self.dialog.inst_tree.topLevelItem(index)
            for index in range(self.dialog.inst_tree.topLevelItemCount())
            if self.dialog.inst_tree.topLevelItem(index).text(0) == "addrspacecast"
        )
        self.assertEqual(self.dialog.inst_tree.itemWidget(row, 2).currentData(), 0)

    def test_offscreen_unknown_source_id_remains_raw_until_contract_check(
        self,
    ):
        document = deepcopy(self.dialog._base_document)
        document["hw_config"]["gemm"]["instructions"]["add"]["functional_unit"] = 99
        self.dialog.apply_config(document)
        row = next(
            self.dialog.inst_tree.topLevelItem(index)
            for index in range(self.dialog.inst_tree.topLevelItemCount())
            if self.dialog.inst_tree.topLevelItem(index).text(0) == "add"
        )
        self.assertEqual(self.dialog.inst_tree.itemWidget(row, 2).currentData(), 99)
        self.assertEqual(
            self.dialog.build_config()["hw_config"]["gemm"]["instructions"]["add"][
                "functional_unit"
            ],
            99,
        )

    def test_offscreen_live_widgets_export_topology_runtime_system_and_model(
        self,
    ):
        self.dialog.component_tree.setCurrentItem(self._component("dma"))
        self._detail("Buffer Size:").setValue(256)
        self.dialog.component_tree.setCurrentItem(self._component("MATRIX1"))
        self._detail("Ports:").setValue(3)
        self.dialog.mem_size_edit.setText("2GB")
        self.dialog.mem_type_edit.setText("DDR3_1600_8x8")
        self.dialog.cpu_clock_edit.setText("1GHz")
        self.dialog.sys_clock_edit.setText("500MHz")
        self.dialog.base_addr_edit.setText("0x10320000")
        for index in range(self.dialog.inst_tree.topLevelItemCount()):
            item = self.dialog.inst_tree.topLevelItem(index)
            if item.text(0) == "mul":
                item.setText(1, "3")
                break
        else:
            self.fail("Missing mul instruction")
        for index in range(self.dialog.model_tree.topLevelItemCount()):
            item = self.dialog.model_tree.topLevelItem(index)
            if item.text(0) == "integer_adder":
                item.setText(1, "0.012345")
                item.setText(8, "6")
                break
        else:
            self.fail("Missing model FU")
        request = self.dialog._make_request()
        self.assertEqual(
            request["provenance"]["source_config"]["relative_path"],
            "benchmarks/sys_validation/gemm/config.yml",
        )
        self.assertEqual(request["system"]["mem-size"], "2GB")
        self.assertEqual(
            request["hardware_profile"]["fu_overrides"],
            {"integer_adder": {"internal_power": 0.012345, "fu_latency": 6}},
        )
        self.assertEqual(request["base_address"], "0x10320000")
        document = request["configuration_documents"][0]
        dma = next(
            entry["DMA"][0] for entry in document["acc_cluster"] if "DMA" in entry
        )
        gemm = next(
            entry["Accelerator"]
            for entry in document["acc_cluster"]
            if "Accelerator" in entry and entry["Accelerator"][0].get("Name") == "gemm"
        )
        self.assertEqual(dma["BufferSize"], 256)
        self.assertEqual(gemm[1]["Var"][0]["Ports"], 3)
        self.assertEqual(
            document["hw_config"]["gemm"]["instructions"]["mul"]["runtime_cycles"],
            3,
        )
        from salam_workbench.gui_execution import validate_request

        base, _, source = validate_request(request)
        self.assertEqual(base, ENGINE)
        self.assertEqual(source, ENGINE / "benchmarks/sys_validation/gemm/config.yml")

    def test_offscreen_duplicate_model_row_rejected(self):
        first = self.dialog.model_tree.topLevelItem(0)
        second = self.dialog.model_tree.topLevelItem(1)
        second.setText(0, first.text(0))
        with self.assertRaisesRegex(ValueError, "Duplicate visible model FU row"):
            self.dialog._make_request()

    def test_offscreen_incomplete_visible_rows_rejected_and_identity_explained(
        self,
    ):
        self.dialog.component_tree.setCurrentItem(self._component("gemm"))
        name_field = self._detail("Name:")
        self.assertTrue(name_field.isReadOnly())
        self.assertIn("Rename migration", name_field.toolTip())
        instruction = next(
            self.dialog.inst_tree.topLevelItem(index)
            for index in range(self.dialog.inst_tree.topLevelItemCount())
            if self.dialog.inst_tree.topLevelItem(index).text(0) == "mul"
        )
        original_runtime = instruction.text(1)
        instruction.setText(1, "")
        with self.assertRaisesRegex(ValueError, "Incomplete visible instruction row"):
            self.dialog._make_request()
        instruction.setText(1, original_runtime)
        fu = next(
            self.dialog.fu_tree.topLevelItem(index)
            for index in range(self.dialog.fu_tree.topLevelItemCount())
            if self.dialog.fu_tree.topLevelItem(index).text(0) == "integer_multiplier"
        )
        original_cycles = fu.text(1)
        original_limit = fu.text(2)
        fu.setText(1, "2")
        fu.setText(2, "")
        with self.assertRaisesRegex(ValueError, "Incomplete visible FU row"):
            self.dialog._make_request()
        fu.setText(2, "0")
        self.dialog._make_request()
        fu.setText(1, original_cycles)
        fu.setText(2, original_limit)
        self.dialog._make_request()

    def test_offscreen_success_summary_requires_durable_workbench_receipt(
        self,
    ):
        self.dialog._gui_request = self.dialog._make_request()
        with self.assertRaisesRegex(ValueError, "outside workbench evidence"):
            self.dialog._verify_passing_receipt(
                {"state": "passed", "evidence_directory": "/tmp/forged-run"}
            )

    def test_offscreen_native_linux_uses_real_backend_command(self):
        program, arguments = self.dialog._backend_command(self.dialog._make_request())
        self.assertEqual(program, "/usr/bin/python3.8")
        self.assertEqual(
            arguments,
            ["-B", "-m", "salam_workbench.gui_execution", "--request-stdin"],
        )

    def test_offscreen_fu_telemetry_words_are_source_bound_counters(self):
        from salam_workbench.gui_editor_qt import _fu_telemetry_lines

        lines = _fu_telemetry_lines(
            {
                "fu_scheduling_summary": {
                    "state": "validated_direct_salam_trace",
                    "invocations": [
                        {
                            "accelerator": "system.gemm_clstr.gemm",
                            "units": [
                                {
                                    "name": "integer_multiplier",
                                    "limit": 1,
                                    "attempts": 8,
                                    "grants": 2,
                                    "denials": 6,
                                    "releases": 2,
                                    "peak": 1,
                                    "outstanding": 0,
                                }
                            ],
                        }
                    ],
                }
            }
        )
        self.assertIn("validated direct SALAM trace", lines[0])
        self.assertIn("integer_multiplier (capacity 1)", lines[1])
        self.assertIn("issue attempts 8, grants 2, blocked 6, releases 2", lines[1])
        self.assertEqual(_fu_telemetry_lines({}), [])

    def test_offscreen_period_choices_follow_selected_model_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark = root / "benchmarks/sys_validation/gemm"
            benchmark.mkdir(parents=True)
            (benchmark / "config.yml").write_text("{}\n")
            (
                benchmark / "configs/hw_interface/functional_units/"
                "test_model/2ns/default_profile"
            ).mkdir(parents=True)
            self.dialog.gem5_path = root
            self.dialog.model_edit.setText("test_model")
            self.assertEqual(self.dialog.cycle_time_combo.count(), 1)
            self.assertEqual(self.dialog.cycle_time_combo.itemText(0), "2ns")
            self.assertEqual(self.dialog.cycle_time_combo.currentIndex(), -1)
            self.dialog.cycle_time_combo.setCurrentIndex(0)
            self.assertEqual(self.dialog.cycle_time_combo.currentText(), "2ns")
            self.dialog.profile_edit.setText("missing_profile")
            self.assertEqual(self.dialog.cycle_time_combo.count(), 0)
            self.assertFalse(self.dialog.cycle_time_combo.isEnabled())
            self.assertIn(
                "No source-backed profile periods",
                self.dialog.cycle_time_combo.toolTip(),
            )


if __name__ == "__main__":
    unittest.main()
