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

    def _run_fixture_tier(self, tier, modules, cases):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "tests").mkdir()
            loader = unittest.TestLoader()
            with patch.object(checks, "PROJECT", project), patch.object(
                checks, "FAST_MODULES", modules["fast"]
            ), patch.object(checks, "CONFIG_MODULES", modules["config"]), patch.object(
                checks, "GUI_MODULES", modules["gui"]
            ), patch.object(
                checks.importlib, "import_module"
            ), patch.object(
                unittest.TestLoader,
                "loadTestsFromName",
                side_effect=lambda name: loader.loadTestsFromTestCase(cases[name]),
            ):
                with contextlib.redirect_stderr(io.StringIO()):
                    code = checks.run_unit_tier(tier, project / "result.json")
            return code, json.loads((project / "result.json").read_text())

    def test_gui_editor_methods_without_offscreen_prefix_are_executed(self):
        called = []
        editor = type(
            "EditorCase",
            (unittest.TestCase,),
            {
                "__module__": "test_gui_editor_qt",
                "test_generated_input": lambda self: called.append("input"),
                "test_fft_profile_transport": lambda self: called.append("fft"),
                "test_stencil_profile_transport": lambda self: called.append("stencil"),
            },
        )
        code, result = self._run_fixture_tier(
            "gui",
            {"fast": (), "config": (), "gui": ("test_gui_editor_qt",)},
            {"test_gui_editor_qt": editor},
        )
        self.assertEqual(code, 0)
        self.assertEqual(set(called), {"input", "fft", "stencil"})
        self.assertEqual(result["tests_run"], 3)
        self.assertEqual(result["discovered_tests"], result["selected_tests"])
        self.assertEqual(result["excluded_tests"], [])
        self.assertEqual(result["unassigned_tests"], [])

    def test_dedicated_fast_and_config_modules_keep_every_method(self):
        for tier in ("fast", "config"):
            with self.subTest(tier=tier):
                module = "test_dedicated_" + tier
                called = []
                case = type(
                    "DedicatedCase",
                    (unittest.TestCase,),
                    {
                        "__module__": module,
                        "test_offscreen_named_contract": lambda self: called.append(
                            True
                        ),
                    },
                )
                modules = {"fast": (), "config": (), "gui": ()}
                modules[tier] = (module,)
                code, result = self._run_fixture_tier(tier, modules, {module: case})
                self.assertEqual(code, 0)
                self.assertEqual(called, [True])
                self.assertEqual(result["tests_run"], 1)
                self.assertEqual(result["excluded_tests"], [])

    def test_shared_viewer_methods_form_exact_once_union_across_tiers(self):
        called = []
        viewer = type(
            "ViewerCase",
            (unittest.TestCase,),
            {
                "__module__": "test_offline_viewer",
                "test_saved_evidence": lambda self: called.append("saved"),
                "test_offscreen_preview": lambda self: called.append("preview"),
                "test_actual_recovered_parser_contract_and_hash_gate": lambda self: called.append(
                    "parser"
                ),
                "test_non_instruction_dot_does_not_claim_available_cdfg": lambda self: called.append(
                    "graph"
                ),
            },
        )
        modules = {
            "fast": ("test_offline_viewer",),
            "config": (),
            "gui": ("test_offline_viewer",),
        }
        selections = []
        for tier in ("fast", "gui"):
            code, result = self._run_fixture_tier(
                tier, modules, {"test_offline_viewer": viewer}
            )
            self.assertEqual(code, 0)
            self.assertEqual(len(result["discovered_tests"]), 4)
            self.assertEqual(result["unassigned_tests"], [])
            self.assertEqual(
                len(result["selected_tests"]) + len(result["excluded_tests"]), 4
            )
            self.assertTrue(
                all(row["owner"] != tier for row in result["excluded_tests"])
            )
            selections.extend(result["selected_tests"])
        self.assertEqual(len(selections), len(set(selections)))
        self.assertEqual(len(selections), 4)
        self.assertCountEqual(called, ["saved", "preview", "parser", "graph"])

    def test_ambiguous_tier_ownership_is_reported_and_fails(self):
        case = type(
            "AmbiguousCase",
            (unittest.TestCase,),
            {"__module__": "test_shared_ambiguous", "test_contract": lambda self: None},
        )
        code, result = self._run_fixture_tier(
            "fast",
            {
                "fast": ("test_shared_ambiguous",),
                "config": ("test_shared_ambiguous",),
                "gui": (),
            },
            {"test_shared_ambiguous": case},
        )
        self.assertEqual(code, 1)
        self.assertFalse(result["success"])
        self.assertEqual(result["tests_run"], 0)
        self.assertEqual(result["selected_tests"], [])
        self.assertEqual(len(result["unassigned_tests"]), 1)
        self.assertIn("no unique tier owner", result["unassigned_tests"][0]["reason"])

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
