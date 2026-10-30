# Fixture: recovered GEMM config.yml at 42539ecca54ff0fed455a7afe0bda0603554e360.
BASELINE_YAML = "---\nacc_cluster:\n  - Name: gemm_clstr\n  - DMA:\n    - Name: dma\n      MaxReqSize: 64\n      BufferSize: 128\n      PIOMaster: LocalBus\n      Type: NonCoherent\n      InterruptNum: 95\n  - Accelerator:\n    - Name: Top\n      IrPath: benchmarks/sys_validation/gemm/hw/top.ll\n      PIOSize: 25\n      InterruptNum: 68\n      PIOMaster: LocalBus\n      # Local to PIO\n      LocalSlaves: LocalBus\n      Debug: False\n  - Accelerator:\n    - Name: gemm\n      IrPath: benchmarks/sys_validation/gemm/hw/gemm.ll\n      Debug: False\n      PIOSize: 1\n      PIOMaster: LocalBus\n    - Var:\n      - Name: MATRIX1\n        Type: SPM\n        Size: 32768\n        Ports: 2\n    - Var:\n      - Name: MATRIX2\n        Type: SPM\n        Size: 32768\n        Ports: 2\n    - Var:\n      - Name: MATRIX3\n        Type: SPM\n        Size: 32768\n        Ports: 2\nhw_config:\n  name: gemm_clstr\n  top:\n  gemm:\n    instructions:\n      add:\n        functional_unit: 1\n        functional_unit_limit: 0\n        opcode_num: 13\n        runtime_cycles: 0\n      addrspacecast:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 50\n        runtime_cycles: 1\n      alloca:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 31\n        runtime_cycles: 0\n      and_inst:\n        functional_unit: 4\n        functional_unit_limit: 0\n        opcode_num: 28\n        runtime_cycles: 1\n      ashr:\n        functional_unit: 3\n        functional_unit_limit: 0\n        opcode_num: 27\n        runtime_cycles: 1\n      bitcast:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 49\n        runtime_cycles: 0\n      br:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 2\n        runtime_cycles: 0\n      call:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 56\n        runtime_cycles: 0\n      fadd:\n        functional_unit: 6\n        functional_unit_limit: 0\n        opcode_num: 14\n        runtime_cycles: 5\n      fcmp:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 54\n        runtime_cycles: 1\n      fdiv:\n        functional_unit: 10\n        functional_unit_limit: 0\n        opcode_num: 21\n        runtime_cycles: 16\n      fence:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 35\n        runtime_cycles: 0\n      fmul:\n        functional_unit: 9\n        functional_unit_limit: 0\n        opcode_num: 18\n        runtime_cycles: 4\n      fpext:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 46\n        runtime_cycles: 0\n      fptosi:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 42\n        runtime_cycles: 0\n      fptoui:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 41\n        runtime_cycles: 0\n      fptrunc:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 45\n        runtime_cycles: 0\n      frem:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 24\n        runtime_cycles: 16\n      fsub:\n        functional_unit: 6\n        functional_unit_limit: 0\n        opcode_num: 16\n        runtime_cycles: 5\n      gep:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 34\n        runtime_cycles: 0\n      icmp:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 53\n        runtime_cycles: 0\n      indirectbr:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 4\n        runtime_cycles: 0\n      inttoptr:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 48\n        runtime_cycles: 0\n      invoke:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 5\n        runtime_cycles: 0\n      landingpad:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 66\n        runtime_cycles: 0\n      load:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 32\n        runtime_cycles: 0\n      lshr:\n        functional_unit: 3\n        functional_unit_limit: 0\n        opcode_num: 26\n        runtime_cycles: 1\n      mul:\n        functional_unit: 2\n        functional_unit_limit: 0\n        opcode_num: 17\n        runtime_cycles: 1\n      or_inst:\n        functional_unit: 4\n        functional_unit_limit: 0\n        opcode_num: 29\n        runtime_cycles: 1\n      phi:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 55\n        runtime_cycles: 0\n      ptrtoint:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 47\n        runtime_cycles: 0\n      resume:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 6\n        runtime_cycles: 0\n      ret:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 1\n        runtime_cycles: 0\n      sdiv:\n        functional_unit: 2\n        functional_unit_limit: 0\n        opcode_num: 20\n        runtime_cycles: 1\n      select:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 57\n        runtime_cycles: 0\n      sext:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 40\n        runtime_cycles: 0\n      shl:\n        functional_unit: 3\n        functional_unit_limit: 0\n        opcode_num: 25\n        runtime_cycles: 1\n      srem:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 23\n        runtime_cycles: 1\n      store:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 33\n        runtime_cycles: 0\n      sub:\n        functional_unit: 1\n        functional_unit_limit: 0\n        opcode_num: 15\n        runtime_cycles: 1\n      switch_inst:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 3\n        runtime_cycles: 0\n      trunc:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 38\n        runtime_cycles: 0\n      udiv:\n        functional_unit: 2\n        functional_unit_limit: 0\n        opcode_num: 19\n        runtime_cycles: 1\n      uitofp:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 43\n        runtime_cycles: 0\n      unreachable:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 7\n        runtime_cycles: 0\n      urem:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 22\n        runtime_cycles: 1\n      vaarg:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 60\n        runtime_cycles: 0\n      xor_inst:\n        functional_unit: 4\n        functional_unit_limit: 0\n        opcode_num: 30\n        runtime_cycles: 1\n      zext:\n        functional_unit: 0\n        functional_unit_limit: 0\n        opcode_num: 39\n        runtime_cycles: 0\n"

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from salam_workbench.config import ConfigValidationError, validate_gemm_config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="salam-config-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bench = self.root / "benchmarks/sys_validation/gemm"
        (self.bench / "hw").mkdir(parents=True)
        for stem in ("top", "gemm"):
            (self.bench / "hw" / (stem + ".ll")).write_text(
                "; synthetic IR fixture\n", encoding="utf-8"
            )
            (self.bench / "hw" / (stem + ".c")).write_text(
                "void " + stem + "(void) {}\n", encoding="utf-8"
            )
        (self.bench / "defines.h").write_text(
            "#define CHECK\n#define TYPE int\n#define ROW 8\n#define COL 8\n",
            encoding="utf-8",
        )
        self.config = self.bench / "config.yml"
        self.config.write_text(BASELINE_YAML, encoding="utf-8")
        self.data = yaml.safe_load(BASELINE_YAML)

    def write(self):
        self.config.write_text(
            yaml.safe_dump(self.data, sort_keys=False), encoding="utf-8"
        )

    def reject(self, fragment):
        self.write()
        with self.assertRaisesRegex(ConfigValidationError, fragment):
            validate_gemm_config(self.config, self.root)

    def test_baseline_and_parser_address_padding(self):
        result = validate_gemm_config(self.config, self.root)
        self.assertTrue(result["valid"])
        self.assertEqual(result["instruction_count"], 49)
        self.assertEqual(
            [v["address"] for v in result["layout"]],
            [
                0x10020000,
                0x10020040,
                0x10020080,
                0x100200C0,
                0x10028100,
                0x10030140,
            ],
        )
        self.assertEqual(result["cluster_top_address"], 0x10038180)
        self.assertEqual(result["stage"], "postbuild")
        self.assertEqual(result["pending_artifacts"], [])

    def test_missing_required_field(self):
        del self.data["acc_cluster"][2]["Accelerator"][0]["PIOSize"]
        self.reject("missing required fields: PIOSize")

    def test_unknown_bus_is_not_silently_ignored(self):
        self.data["acc_cluster"][1]["DMA"][0]["PIOMaster"] = "MissingBus"
        self.reject("DMA.PIOMaster")

    def test_duplicate_matrix_name(self):
        self.data["acc_cluster"][3]["Accelerator"][2]["Var"][0]["Name"] = "MATRIX1"
        self.reject("MATRIX2.Name")

    def test_boolean_not_valid_numeric_capacity(self):
        self.data["acc_cluster"][1]["DMA"][0]["BufferSize"] = True
        self.reject("DMA.BufferSize")

    def test_undersized_memory(self):
        self.data["acc_cluster"][3]["Accelerator"][1]["Var"][0]["Size"] = 128
        self.reject("MATRIX1.Size")

    def test_address_overflow(self):
        self.data["acc_cluster"][3]["Accelerator"][1]["Var"][0]["Size"] = 0x4000000
        self.reject("address range exceeds")

    def test_invalid_latency_and_opcode(self):
        instructions = self.data["hw_config"]["gemm"]["instructions"]
        instructions["mul"]["runtime_cycles"] = -1
        self.reject("mul.runtime_cycles")
        instructions["mul"]["runtime_cycles"] = 1
        instructions["mul"]["opcode_num"] = 99
        self.reject("mul.opcode_num")

    def test_unknown_instruction(self):
        self.data["hw_config"]["gemm"]["instructions"]["made_up"] = {}
        self.reject("unsupported fields.*made_up")

    def test_unknown_root_field(self):
        self.data["unhandled"] = True
        self.reject("unsupported fields.*unhandled")

    def test_duplicate_yaml_key(self):
        self.config.write_text(
            BASELINE_YAML.replace(
                "MaxReqSize: 64", "MaxReqSize: 64\n      MaxReqSize: 1"
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ConfigValidationError, "duplicate YAML key"):
            validate_gemm_config(self.config, self.root)

    def test_multiple_documents(self):
        self.config.write_text(BASELINE_YAML + "\n---\na: 1\n", encoding="utf-8")
        with self.assertRaisesRegex(ConfigValidationError, "exactly one YAML document"):
            validate_gemm_config(self.config, self.root)

    def test_path_traversal_rejected(self):
        self.data["acc_cluster"][2]["Accelerator"][0]["IrPath"] = "../../outside.ll"
        self.reject("Top.IrPath")

    def test_missing_ir_is_not_postbuild_valid(self):
        path = self.bench / "hw/gemm.ll"
        path.rename(path.with_suffix(".ll.kept"))
        with self.assertRaisesRegex(ConfigValidationError, "gemm.IrPath"):
            validate_gemm_config(self.config, self.root)
        prebuild = validate_gemm_config(self.config, self.root, require_ir=False)
        self.assertEqual(prebuild["stage"], "prebuild")
        self.assertEqual(len(prebuild["pending_artifacts"]), 2)
        self.assertTrue(
            all(
                v["state"] == "requires_fresh_build_and_postbuild_validation"
                for v in prebuild["pending_artifacts"]
            )
        )

    def test_prebuild_requires_c_source(self):
        path = self.bench / "hw/gemm.c"
        path.rename(path.with_suffix(".c.kept"))
        with self.assertRaisesRegex(ConfigValidationError, "gemm.CSource"):
            validate_gemm_config(self.config, self.root, require_ir=False)

    def test_invalid_cli_returns_nonzero_and_diagnostic(self):
        del self.data["acc_cluster"][2]["Accelerator"][0]["PIOSize"]
        self.write()
        process = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "salam_workbench.config",
                str(self.config),
                "--engine-root",
                str(self.root),
            ],
            cwd=str(Path(__file__).resolve().parents[1]),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.assertEqual(process.returncode, 2)
        self.assertIn("missing required fields: PIOSize", process.stderr)
        self.assertEqual(process.stdout, "")

    def test_dimensions_outside_supported_contract(self):
        (self.bench / "defines.h").write_text(
            "#define CHECK\n#define TYPE int\n#define ROW 16\n#define COL 8\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ConfigValidationError, "define ROW 8"):
            validate_gemm_config(self.config, self.root)


if __name__ == "__main__":
    unittest.main()
