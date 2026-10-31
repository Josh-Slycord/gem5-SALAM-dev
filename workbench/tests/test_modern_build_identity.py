"""Changing real gem5 build generators or public headers must require a rebuild."""
import tempfile
import unittest
from pathlib import Path

from salam_workbench.configurator import compiled_identity


class ModernBuildIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.engine = Path(temporary.name) / "engine"
        self.engine.mkdir()
        (self.engine / "SConstruct").write_text("# synthetic build entry\n")
        (self.engine / "src").mkdir()
        (self.engine / "src/test.cc").write_text("// source\n")

    def test_generator_public_header_and_kconfig_changes_invalidate_identity(self):
        for relative in (
            "build_tools/sim_object_param_struct_cc.py",
            "include/gem5/hypercall_ids.h",
            "include/gem5/asm/generic/m5ops.h",
            "build_opts/ARM",
            "src/Kconfig",
            "Kconfig",
        ):
            with self.subTest(relative=relative):
                source = self.engine / relative
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("first build input\n")
                before = compiled_identity(self.engine)
                self.assertIn(relative, before["files"])
                source.write_text("different build input\n")
                self.assertNotEqual(
                    before["sha256"], compiled_identity(self.engine)["sha256"]
                )

    def test_build_outputs_and_python_caches_do_not_change_source_identity(self):
        before = compiled_identity(self.engine)
        for relative in (
            "build/ARM/params/LLVMInterface.hh",
            "build/ARM/python/_m5/param_LLVMInterface.o",
            "build_tools/__pycache__/marshal.cpython-312.pyc",
            "build_tools/temporary.o",
        ):
            path = self.engine / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"rebuildable output")
        self.assertEqual(before, compiled_identity(self.engine))

    def test_only_exact_derived_ply_caches_are_excluded_while_grammar_stays_bound(self):
        before = compiled_identity(self.engine)
        for relative in ("src/mem/slicc/parser.out", "src/mem/slicc/parsetab.py"):
            path = self.engine / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("first derived parser cache\n")
            self.assertEqual(before, compiled_identity(self.engine))
            path.write_text("different derived parser cache\n")
            self.assertEqual(before, compiled_identity(self.engine))
        for relative in (
            "src/mem/slicc/parser.py",
            "src/mem/slicc/other.py",
            "src/mem/slicc/other.out",
        ):
            path = self.engine / relative
            path.write_text("actual source input\n")
            first = compiled_identity(self.engine)
            self.assertIn(relative, first["files"])
            path.write_text("changed actual source input\n")
            self.assertNotEqual(
                first["sha256"], compiled_identity(self.engine)["sha256"]
            )

    def test_legacy_tree_without_modern_directories_remains_supported(self):
        identity = compiled_identity(self.engine)
        self.assertEqual(set(identity["files"]), {"SConstruct", "src/test.cc"})


if __name__ == "__main__":
    unittest.main()
