"""The GUI gate must execute whole desktop suites and expose import errors."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from salam_workbench import checks


class WorkbenchTierCoverageTests(unittest.TestCase):
    def test_gui_entrypoint_executes_desktop_methods_without_name_prefix(self):
        called = []
        desktop = type(
            "DesktopCase",
            (unittest.TestCase,),
            {
                "__module__": "test_workbench_window",
                "test_actual_window_contract": lambda self: called.append("window"),
            },
        )
        topology = type(
            "TopologyCase",
            (unittest.TestCase,),
            {
                "__module__": "test_workbench_topology",
                "test_original_graph_rendering": lambda self: called.append("topology"),
            },
        )
        suites = [
            unittest.TestSuite([desktop("test_actual_window_contract")]),
            unittest.TestSuite([topology("test_original_graph_rendering")]),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "tests").mkdir()
            with patch.object(checks, "PROJECT", project), patch.object(
                checks,
                "GUI_MODULES",
                ("test_workbench_window", "test_workbench_topology"),
            ), patch.object(checks.importlib, "import_module"), patch.object(
                unittest.TestLoader, "loadTestsFromName", side_effect=suites
            ):
                with contextlib.redirect_stderr(io.StringIO()):
                    code = checks.run_unit_tier("gui", project / "result.json")
            self.assertEqual(code, 0)
            self.assertEqual(called, ["window", "topology"])

    def test_import_failure_is_executed_as_failure_instead_of_filtered_out(self):
        failed = unittest.loader._FailedTest(
            "broken_desktop_module", ImportError("missing Qt dependency")
        )
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "tests").mkdir()
            with patch.object(checks, "PROJECT", project), patch.object(
                checks, "GUI_MODULES", ("broken_desktop_module",)
            ), patch.object(checks.importlib, "import_module"), patch.object(
                unittest.TestLoader,
                "loadTestsFromName",
                return_value=unittest.TestSuite([failed]),
            ):
                with contextlib.redirect_stderr(io.StringIO()):
                    code = checks.run_unit_tier("gui", project / "result.json")
            self.assertEqual(code, 1)
            result = json.loads((project / "result.json").read_text())
            self.assertEqual(result["tests_run"], 1)
            self.assertEqual(len(result["errors"]), 1)
            self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
