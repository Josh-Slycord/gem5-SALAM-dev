"""Synthetic capability gate tests; they do not prove simulator behavior."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from salam_workbench.configurator import compiled_identity
from salam_workbench.fu_capability import (
    MARKER,
    REQUIRED_SOURCE_FILES,
    capability_source_paths,
    inspect_fu_capability,
    validate_limit_parameters,
)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FuCapabilityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.engine = Path(temp.name) / "engine"
        self.engine.mkdir()
        (self.engine / "SConstruct").write_text("# synthetic source\n")

    def _capable(self):
        sources = {}
        for name in REQUIRED_SOURCE_FILES:
            path = self.engine / name
            path.parent.mkdir(parents=True, exist_ok=True)
            text = (
                "// SALAM_FU_SCHEDULER_V1\n"
                if name.endswith(("fu_scheduling_pool.hh", "llvm_interface.cc"))
                else "// synthetic source\n"
            )
            path.write_text(text)
            sources[name] = _sha(path)
        marker = self.engine / MARKER
        marker.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "capability": "salam_fu_scheduler_v1",
                    "scope": "scalar_compute",
                    "semantics": "nonpipelined_issue_to_completion",
                    "zero_limit": "unlimited",
                    "source_files": sources,
                },
                sort_keys=True,
            )
        )
        return marker

    def _build_receipt(self):
        binary = self.engine / "build/ARM/gem5.opt"
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(b"synthetic binary")
        receipt = self.engine.parent / "build.json"
        receipt.write_text(
            json.dumps(
                {
                    "kind": "configured_engine_build",
                    "state": "built",
                    "binary": {"path": str(binary), "sha256": _sha(binary)},
                    "compiled_source_sha256": compiled_identity(self.engine)["sha256"],
                }
            )
        )
        return receipt

    def test_legacy_engine_rejects_nonzero_fu_limits(self):
        self.assertFalse(inspect_fu_capability(self.engine)["supported"])
        self.assertEqual(capability_source_paths(self.engine), [])
        with self.assertRaisesRegex(ValueError, "verified FU scheduler"):
            validate_limit_parameters(
                self.engine,
                {
                    "system.c.a.hw_interface.functional_units.integer_adder": {
                        "limit": 1
                    }
                },
            )
        self.assertEqual(
            validate_limit_parameters(
                self.engine,
                {
                    "system.c.a.hw_interface.functional_units.integer_adder": {
                        "limit": 0
                    }
                },
            )["requested"],
            [],
        )

    def test_capability_requires_matching_sources_and_build_identity(self):
        marker = self._capable()
        self.assertTrue(inspect_fu_capability(self.engine)["supported"])
        self.assertEqual(
            len(capability_source_paths(self.engine)),
            len(REQUIRED_SOURCE_FILES) + 1,
        )
        receipt = self._build_receipt()
        parameters = {
            "system.c.a.hw_interface.functional_units.integer_adder": {"limit": 2}
        }
        result = validate_limit_parameters(self.engine, parameters, receipt)
        self.assertTrue(result["capability"]["build_verified"])
        (self.engine / REQUIRED_SOURCE_FILES[0]).write_text("changed\n")
        self.assertFalse(inspect_fu_capability(self.engine, receipt)["supported"])
        with self.assertRaisesRegex(ValueError, "verified FU scheduler"):
            validate_limit_parameters(self.engine, parameters, receipt)
        self.assertTrue(marker.is_file())

    def test_instruction_limit_remains_unsupported_with_capable_source(self):
        self._capable()
        with self.assertRaisesRegex(ValueError, "not consumed"):
            validate_limit_parameters(
                self.engine,
                {
                    "system.c.a.hw_interface.inst_config.add": {
                        "functional_unit_limit": 1
                    }
                },
            )
        with self.assertRaisesRegex(ValueError, "not consumed"):
            validate_limit_parameters(
                self.engine,
                {"system.c.a.unrelated": {"functional_unit_limit": 1}},
            )
        with self.assertRaisesRegex(ValueError, "no supported consumer"):
            validate_limit_parameters(
                self.engine, {"system.c.a.hw_interface.other": {"limit": 1}}
            )

    def test_unlisted_compiled_source_change_invalidates_build_binding(self):
        self._capable()
        receipt = self._build_receipt()
        self.assertTrue(inspect_fu_capability(self.engine, receipt)["supported"])
        extra = self.engine / "src/hwacc/unlisted_scheduler_consumer.cc"
        extra.write_text("// altered compiled source identity\n")
        result = inspect_fu_capability(self.engine, receipt)
        self.assertFalse(result["supported"])
        self.assertIn("rebuild required", result["reason"])


if __name__ == "__main__":
    unittest.main()
