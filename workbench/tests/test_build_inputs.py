import json
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest

from salam_workbench.build_inputs import (address_macros, check_preprocessed_macros,
                                           rebind_cluster_header)


class BuildInputWitnessTests(unittest.TestCase):
    def test_relocated_compiler_macros_must_match_generated_headers(self):
        expected = {"TOP": 0x10320040, "MATRIX1": 0x103200c0}
        good = '#define TOP 0x10320040\n#define MATRIX1 0x103200c0\n'
        self.assertEqual(check_preprocessed_macros(good, expected)["state"], "passed")
        with self.assertRaisesRegex(ValueError, "stale"):
            check_preprocessed_macros(good.replace('0x10320040', '0x10020040'), expected)
        with self.assertRaises(ValueError):
            check_preprocessed_macros('#define TOP 0x10320040\n', expected)

    def test_conflicting_multi_header_addresses_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            one, two = Path(temporary) / 'one.h', Path(temporary) / 'two.h'
            one.write_text('#define TOP 0x10020040\n')
            two.write_text('#define TOP 0x10320040\n')
            with self.assertRaisesRegex(ValueError, 'Conflicting'):
                address_macros([one, two])

    def _rename_fixture(self, root, *, changed_names=False):
        engine, stage, evidence = root / "engine", root / "stage", root / "evidence"
        relative = Path("benchmarks/sys_validation/gemm")
        source, staged = engine / relative, stage / relative
        source.mkdir(parents=True)
        staged.mkdir(parents=True)
        (source / "config.yml").write_text(
            "acc_cluster:\n  - Name: gemm_clstr\n", encoding="utf-8")
        original = (b"// manual prefix\r\n#define MANUAL_FLAG 1\r\n"
                    b"//BEGIN GENERATED CODE\r\n"
                    b"#define TOP 0x10020040\r\n"
                    b"#define GEMM 0x10020080\r\n"
                    b"//END GENERATED CODE\r\n// manual suffix\r\n")
        old_name, new_name = "gemm_clstr_hw_defines.h", "new_clstr_hw_defines.h"
        (source / old_name).write_bytes(original)
        (staged / old_name).write_bytes(original)
        macro = b"OTHER" if changed_names else b"GEMM"
        (staged / new_name).write_bytes(
            b"//BEGIN GENERATED CODE\n"
            b"#define TOP 0x10320040\n#define " + macro + b" 0x10320080\n"
            b"//END GENERATED CODE\n")
        (staged / "sw").mkdir()
        (staged / "sw/main.cpp").write_text(
            '#include "../gemm_clstr_hw_defines.h"\nint main(){return TOP;}\n',
            encoding="utf-8")
        spec = {"benchmark": relative.as_posix(),
                "config": (relative / "config.yml").as_posix()}
        contract = {"components": {"clusters": [{"name": "new_clstr"}]}}
        return engine, stage, evidence, spec, contract, original

    def test_cluster_rename_preserves_before_image_and_new_macros(self):
        with tempfile.TemporaryDirectory() as temporary:
            engine, stage, evidence, spec, contract, original = self._rename_fixture(
                Path(temporary))
            record = rebind_cluster_header(engine, stage, spec, contract, evidence)
            self.assertEqual(record["state"], "rebound")
            self.assertEqual(record["macro_names"], ["GEMM", "TOP"])
            self.assertEqual(Path(record["before_image"]["path"]).read_bytes(), original)
            old = stage / spec["benchmark"] / "gemm_clstr_hw_defines.h"
            changed = old.read_bytes()
            self.assertTrue(changed.startswith(
                b"// manual prefix\r\n#define MANUAL_FLAG 1\r\n"))
            self.assertTrue(changed.endswith(b"\r\n// manual suffix\r\n"))
            self.assertIn(b'#include "new_clstr_hw_defines.h"', changed)
            self.assertEqual((engine / spec["benchmark"] /
                              "gemm_clstr_hw_defines.h").read_bytes(), original)
            compiler = shutil.which("gcc")
            if compiler:
                source = stage / spec["benchmark"] / "sw/main.cpp"
                run = subprocess.run([compiler, "-dM", "-E", str(source)],
                                     capture_output=True, text=True, check=True)
                check_preprocessed_macros(
                    run.stdout, {"TOP": 0x10320040, "GEMM": 0x10320080})
            saved = json.loads((evidence / "cluster-header-rebind.json").read_text())
            self.assertEqual(saved["state"], "rebound")

    def test_cluster_rename_rejects_changed_macro_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            engine, stage, evidence, spec, contract, original = self._rename_fixture(
                Path(temporary), changed_names=True)
            with self.assertRaisesRegex(ValueError, "macro names"):
                rebind_cluster_header(engine, stage, spec, contract, evidence)
            self.assertEqual((stage / spec["benchmark"] /
                              "gemm_clstr_hw_defines.h").read_bytes(), original)
            saved = json.loads((evidence / "cluster-header-rebind.json").read_text())
            self.assertEqual(saved["state"], "failed")

    def test_unchanged_cluster_needs_no_wrapper(self):
        with tempfile.TemporaryDirectory() as temporary:
            engine, stage, evidence, spec, contract, original = self._rename_fixture(
                Path(temporary))
            contract["components"]["clusters"][0]["name"] = "gemm_clstr"
            spec.pop("config")
            record = rebind_cluster_header(engine, stage, spec, contract, evidence)
            self.assertEqual(record["state"], "unchanged")
            self.assertEqual((stage / spec["benchmark"] /
                              "gemm_clstr_hw_defines.h").read_bytes(), original)

    def test_multicluster_rename_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            engine, stage, evidence, spec, contract, original = self._rename_fixture(
                Path(temporary))
            contract["components"]["clusters"].append({"name": "another"})
            with self.assertRaisesRegex(ValueError, "single cluster"):
                rebind_cluster_header(engine, stage, spec, contract, evidence)
            self.assertEqual((stage / spec["benchmark"] /
                              "gemm_clstr_hw_defines.h").read_bytes(), original)