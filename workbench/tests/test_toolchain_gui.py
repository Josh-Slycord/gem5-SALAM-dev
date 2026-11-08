"""Exercise the actual editor transport with legacy and modern manifests."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from salam_workbench import gui_editor_qt, toolchain_profile


class SelectedRuntimeGuiTests(unittest.TestCase):
    def setUp(self):
        # The installed command method is exercised directly. Qt widget creation,
        # editing and output checks remain in the existing whole-GUI suites.
        hooks = (
            "setup_basic_tab",
            "setup_accelerator_tab",
            "setup_hw_config_tab",
            "show_dma_details",
            "show_accelerator_details",
            "on_component_selected",
            "add_accelerator",
            "update_component_data",
        )
        dialog_class = type(
            "TransportFixture", (), {name: lambda self: None for name in hooks}
        )
        gui_editor_qt.install_editor(dialog_class)
        self.dialog = object.__new__(dialog_class)
        self.dialog._backend_command_provider = None
        self.dialog._checked_wsl_path = lambda path, distro: "/mnt/c/work bench"

    def command(self, profile, os_name):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configuration = {} if profile is None else {"toolchain_profile": profile}
            (root / "workspace.json").write_text(
                json.dumps({"configuration_engine": configuration})
            )
            with mock.patch.object(
                gui_editor_qt, "WORKBENCH_HOST", root
            ), mock.patch.object(gui_editor_qt, "os", SimpleNamespace(name=os_name)):
                return self.dialog._backend_command({"distro": "Ubuntu-24.04"})

    def test_actual_native_backend_selects_modern_python(self):
        program, argv = self.command(toolchain_profile.MODERN_ID, "posix")
        self.assertEqual(program, "/home/jslycord/.venvs/salam26-20261030/bin/python")
        self.assertEqual(
            argv, ["-B", "-m", "salam_workbench.gui_execution", "--request-stdin"]
        )

    def test_actual_wsl_backend_keeps_paths_as_single_arguments(self):
        program, argv = self.command(
            {
                "id": toolchain_profile.MODERN_ID,
                "python": "/opt/test runtime/bin/python",
            },
            "nt",
        )
        self.assertEqual(program, "wsl")
        self.assertEqual(
            argv[:7],
            [
                "-d",
                "Ubuntu-24.04",
                "--cd",
                "/mnt/c/work bench",
                "--exec",
                "/opt/test runtime/bin/python",
                "-B",
            ],
        )
        self.assertNotIn("bash", argv)
        self.assertNotIn("-c", argv)

    def test_absent_profile_preserves_native_and_wsl_legacy_python(self):
        self.assertEqual(self.command(None, "posix")[0], "/usr/bin/python3.8")
        self.assertEqual(self.command(None, "nt")[1][5], "/usr/bin/python3.8")

    def test_explicit_test_backend_still_takes_precedence(self):
        self.dialog._backend_command_provider = lambda request: (
            "injected",
            [request["distro"]],
        )
        with mock.patch.object(
            gui_editor_qt,
            "load_toolchain",
            side_effect=AssertionError("profile should not be queried"),
        ):
            self.assertEqual(
                self.dialog._backend_command({"distro": "test"}), ("injected", ["test"])
            )
