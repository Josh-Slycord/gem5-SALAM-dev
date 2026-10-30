"""Acceptance checks for generated topology and overlay provenance."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from salam_workbench import configurator as c


class GeneratedTopologyReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.generated = self.workspace / "configs/SALAM/generated"
        self.generated.mkdir(parents=True)
        self.benchmark = self.workspace / "benchmarks/suite/custom"
        self.benchmark.mkdir(parents=True)
        self.spec = {"name": "custom", "benchmark": "benchmarks/suite/custom"}
        (self.generated / "fs_custom.py").write_text("import custom\n")
        (self.benchmark / "custom_hw_defines.h").write_text(
            "//BEGIN GENERATED CODE\n#define TOP 0x10020040\n//END GENERATED CODE\n"
        )

    def test_generated_ir_and_config_must_bind_to_requested_benchmark(self):
        other = self.workspace / "benchmarks/suite/other"
        other.mkdir(parents=True)
        (other / "config.yml").write_text("acc_cluster: []\n")
        (other / "hw").mkdir()
        (other / "hw/top.ll").write_text('target triple = "armv7-pc-none-eabi"\n')
        (self.generated / "custom.py").write_text(
            "ir = " + repr(str(other / "hw/top.ll")) + "\n"
            "config = " + repr(str(other / "config.yml")) + "\n"
        )
        with self.assertRaises(ValueError):
            c.inspect_generated(self.workspace, self.spec)

    def test_partial_overlay_failure_is_durable_and_bounded(self):
        source = self.workspace / "source"
        stage = self.workspace / "stage"
        target = self.workspace / "target"
        rels = [Path("src/hwacc/generated/a.cc"), Path("src/hwacc/generated/b.cc")]
        outputs = []
        for rel, old, new in zip(rels, (b"old-a", b"old-b"), (b"new-a", b"new-b")):
            source_file, stage_file, target_file = source / rel, stage / rel, target / rel
            for path in (source_file, stage_file, target_file):
                path.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_bytes(old)
            stage_file.write_bytes(new)
            target_file.write_bytes(old)
            outputs.append({"relative_path": rel.as_posix(), "sha256": c.file_hash(stage_file),
                            "source_engine_sha256": c.file_hash(source_file)})
        generation = self.workspace / "generation.json"
        generation.write_text(json.dumps({"valid": True, "state": "generated", "engine_root": str(source),
                                          "staged_engine_root": str(stage), "outputs": outputs}))
        original_copyfile = c.shutil.copyfile

        def fail_second_copy(src, dst, *args, **kwargs):
            if Path(dst) == target / rels[1]:
                raise OSError("controlled second-file copy failure")
            return original_copyfile(src, dst, *args, **kwargs)

        evidence = self.workspace / "install"
        with patch.object(c.shutil, "copyfile", side_effect=fail_second_copy):
            result = c.install_hardware_overlay(generation, target, evidence)
        self.assertEqual(result["state"], "failed_partial")
        self.assertEqual(json.loads((evidence / "overlay.json").read_text())["state"], "failed_partial")
        self.assertEqual((target / rels[0]).read_bytes(), b"new-a")
        self.assertEqual((target / rels[1]).read_bytes(), b"old-b")
        self.assertEqual(result["outputs"][0]["state"], "installed")
        self.assertEqual(result["outputs"][1]["state"], "pending")
        self.assertTrue((evidence / "before" / rels[0]).is_file())
        self.assertTrue((evidence / "before" / rels[1]).is_file())


if __name__ == "__main__":
    unittest.main()