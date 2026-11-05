"""Verify the actual compiler-driver linker, including cache-time rejection."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from salam_workbench import toolchain_profile as profiles


class LinkerSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.linker = self.root / "selected-ld"
        self.linker.write_bytes(b"synthetic linker identity")
        self.other = self.root / "other-ld"
        self.other.write_bytes(b"different linker identity")
        self.profile = profiles.load_toolchain(
            manifest={
                "configuration_engine": {"toolchain_profile": "gem5-26-retained-salam"}
            }
        )
        self.profile["linker"] = str(self.linker)

    def query(self, output, code=0):
        return mock.patch.object(
            profiles.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], code, output, ""),
        )

    def test_absolute_driver_result_must_equal_selected_resolved_linker(self):
        with self.query(str(self.linker) + "\n") as probe:
            result = profiles._linker_selection(self.profile, {"PATH": "/fixed"})
        self.assertEqual(result["argv"], [self.profile["cxx"], "-print-prog-name=ld"])
        self.assertEqual(result["resolved_path"], str(self.linker.resolve()))
        self.assertEqual(result["sha256"], profiles._hash(self.linker))
        self.assertEqual(result["binding"], "compiler_driver_default_verified")
        self.assertFalse(probe.call_args.kwargs["shell"])

    def test_driver_basename_is_resolved_only_in_selected_environment_path(self):
        with self.query("ld\n"), mock.patch.object(
            profiles.shutil, "which", return_value=str(self.linker)
        ) as resolve:
            result = profiles._linker_selection(
                self.profile, {"PATH": "/selected/tool/path"}
            )
        resolve.assert_called_once_with("ld", path="/selected/tool/path")
        self.assertEqual(result["resolved_path"], str(self.linker))

    def test_unapplied_custom_linker_override_is_rejected(self):
        with self.query(str(self.other) + "\n"), self.assertRaisesRegex(
            ValueError, "Configured linker does not match compiler-driver selection"
        ):
            profiles._linker_selection(self.profile, {"PATH": "/fixed"})

    def test_failed_empty_multiline_relative_or_oversized_driver_query_is_rejected(
        self,
    ):
        for output, code in (
            ("", 1),
            ("", 0),
            ("ld\nother", 0),
            ("relative/ld", 0),
            ("x" * 4097, 0),
        ):
            with self.subTest(output=output[:40], code=code), self.query(
                output, code
            ), self.assertRaises(ValueError):
                profiles._linker_selection(self.profile, {"PATH": "/fixed"})

    def test_modern_cache_record_cannot_bypass_driver_selection_verification(self):
        with mock.patch.object(
            profiles, "tool_files", return_value={"linker": self.linker}
        ), mock.patch.object(
            profiles, "_llvm_shared_libraries", return_value={"libraries": []}
        ), mock.patch.object(
            profiles, "_linker_selection", side_effect=ValueError("linker gate witness")
        ) as gate, self.assertRaisesRegex(
            ValueError, "linker gate witness"
        ):
            profiles.record_toolchain(self.profile, versions=False)
        gate.assert_called_once()

    def test_actual_default_gcc_driver_resolves_the_recorded_system_linker(self):
        # A bounded read-only real tool query; it does not compile, link or run gem5.
        profile = profiles.load_toolchain(
            manifest={
                "configuration_engine": {"toolchain_profile": "gem5-26-retained-salam"}
            }
        )
        result = profiles._linker_selection(
            profile, profiles.apply_environment({"PATH": "/usr/bin:/bin"}, profile)
        )
        self.assertEqual(
            result["resolved_path"], str(Path("/usr/bin/ld").resolve(strict=True))
        )
