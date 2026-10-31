"""Staged-only target SDK adaptation and real Make argument transport."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from salam_workbench import build_inputs, ir_toolchain, toolchain_profile

RECIPE = "KERN=kernel.c top.c\nbuild: $(FILES)\n\tclang -O1 -S -target armv7-pc-none-eabi -emit-llvm $(KERN)\n\nclean:\n\trm -f *.ll\n"


class IrToolchainTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.engine, self.workspace = self.root / "engine", self.root / "workspace"
        self.benchmark = "benchmarks/sys_validation/kernel"
        for base in (self.engine, self.workspace):
            folder = base / self.benchmark / "hw"
            folder.mkdir(parents=True)
            (folder / "Makefile").write_text(RECIPE)
            (folder / "top.c").write_text("void top(void) {}\n")
        self.makefile = self.workspace / self.benchmark / "hw/Makefile"
        self.profile = toolchain_profile.load_toolchain(
            manifest={
                "configuration_engine": {"toolchain_profile": "gem5-26-retained-salam"}
            }
        )
        llvm = self.root / "selected LLVM"
        llvm.mkdir()
        (llvm / "clang").write_bytes(b"synthetic compiler transport identity")
        sdk = self.root / "ARM SDK"
        include = sdk / "include"
        include.mkdir(parents=True)
        for name in ("stdio.h", "stdint.h", "stdlib.h", "math.h"):
            (include / name).write_text("/* synthetic SDK header */\n")
        arm_bin = self.root / "arm tools"
        arm_bin.mkdir()
        (arm_bin / "arm-none-eabi-g++").write_bytes(b"synthetic guest compiler")
        self.profile.update(
            llvm_bin=str(llvm),
            arm_sysroot=str(sdk),
            arm_include=str(include),
            arm_bin=str(arm_bin),
        )

    def adapt(self, **kwargs):
        return ir_toolchain.adapt_ir_toolchain(
            self.workspace,
            self.benchmark,
            self.root / "evidence",
            profile=self.profile,
            source_engine=self.engine,
            **kwargs,
        )

    def test_one_staged_recipe_is_adapted_with_complete_before_and_after_images(self):
        record = self.adapt()
        self.assertEqual(record["state"], "adapted")
        self.assertFalse(record["compilation_executed"])
        self.assertEqual(Path(record["before_image"]["path"]).read_text(), RECIPE)
        self.assertEqual(
            Path(record["after_image"]["path"]).read_bytes(), self.makefile.read_bytes()
        )
        self.assertEqual(
            (self.engine / self.benchmark / "hw/Makefile").read_text(), RECIPE
        )
        self.assertIn("--sysroot=", record["recipe_after"])
        self.assertIn("-isystem", record["recipe_after"])
        self.assertEqual(
            self.makefile.read_text().count("-target armv7-pc-none-eabi"), 1
        )
        self.assertTrue(self.makefile.read_text().endswith("clean:\n\trm -f *.ll\n"))

    def test_missing_arm_target_is_added_after_legacy_repairs_without_duplicate(self):
        self.makefile.write_text(RECIPE.replace("-target armv7-pc-none-eabi ", ""))
        result = self.adapt()
        self.assertTrue(result["target_added"])
        self.assertEqual(
            self.makefile.read_text().count("-target armv7-pc-none-eabi"), 1
        )

    def test_missing_or_duplicate_clang_recipe_fails_before_source_change(self):
        for content in (
            RECIPE.replace("\tclang ", "\tgcc "),
            RECIPE + "\tclang -S -emit-llvm top.c\n",
        ):
            with tempfile.TemporaryDirectory() as directory:
                self.makefile.write_text(content)
                with self.assertRaisesRegex(
                    ValueError, "exactly one literal clang recipe"
                ):
                    ir_toolchain.adapt_ir_toolchain(
                        self.workspace,
                        self.benchmark,
                        Path(directory) / "evidence",
                        profile=self.profile,
                    )
                self.assertEqual(self.makefile.read_text(), content)

    def test_different_target_or_preexisting_sdk_override_is_rejected(self):
        for content in (
            RECIPE.replace("armv7-pc-none-eabi", "x86_64-linux-gnu"),
            RECIPE.replace(" -O1", " --sysroot=/unreviewed -O1"),
        ):
            with tempfile.TemporaryDirectory() as directory:
                self.makefile.write_text(content)
                with self.assertRaises(ValueError):
                    ir_toolchain.adapt_ir_toolchain(
                        self.workspace,
                        self.benchmark,
                        Path(directory) / "evidence",
                        profile=self.profile,
                    )
                self.assertEqual(self.makefile.read_text(), content)

    def test_legacy_profile_does_not_change_recipe_or_create_adapter_evidence(self):
        directory = self.root / "legacy-evidence"
        legacy = toolchain_profile.load_toolchain(manifest={})
        result = ir_toolchain.adapt_ir_toolchain(
            self.workspace, self.benchmark, directory, profile=legacy
        )
        self.assertEqual(result["state"], "legacy_unchanged")
        self.assertFalse(directory.exists())
        self.assertEqual(self.makefile.read_text(), RECIPE)
        self.assertEqual(
            ir_toolchain.ir_compiler_argv(legacy),
            ["/usr/lib/llvm-12/bin/clang", "-target", "armv7-pc-none-eabi"],
        )

    def test_ambient_host_include_environment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "ambient include-path"):
            self.adapt(environment={"C_INCLUDE_PATH": "/usr/include"})
        self.assertEqual(self.makefile.read_text(), RECIPE)

    def test_sdk_include_must_be_declared_inside_target_sysroot(self):
        self.profile["arm_include"] = "/usr/include"
        with self.assertRaisesRegex(ValueError, "inside the declared target SDK"):
            self.adapt()

    def test_missing_sdk_headers_fail_before_makefile_change(self):
        self.profile["arm_include"] = str(self.root / "ARM SDK/missing-include")
        with self.assertRaises(ValueError):
            self.adapt()
        self.assertEqual(self.makefile.read_text(), RECIPE)

    def test_adapter_cannot_edit_the_source_engine_in_place(self):
        with self.assertRaisesRegex(ValueError, "separate staged workspace"):
            ir_toolchain.adapt_ir_toolchain(
                self.engine,
                self.benchmark,
                self.root / "evidence",
                profile=self.profile,
                source_engine=self.engine,
            )

    def test_real_make_preserves_spaces_and_literal_dollars_in_compiler_path(self):
        # Real make + a synthetic compiler records argv; this is not LLVM/gem5 validation.
        llvm = self.root / "LLVM$(touch HAZARD) with spaces"
        llvm.mkdir()
        capture = self.root / "compiler-argv.json"
        compiler = llvm / "clang"
        compiler.write_text(
            "#!"
            + sys.executable
            + "\nimport json,sys\nfrom pathlib import Path\nPath("
            + repr(str(capture))
            + ").write_text(json.dumps(sys.argv[1:]))\n"
        )
        compiler.chmod(0o755)
        self.profile["llvm_bin"] = str(llvm)
        self.adapt()
        completed = subprocess.run(
            ["/usr/bin/make", "-B", "-C", str(self.makefile.parent), "build"],
            capture_output=True,
            text=True,
            timeout=20,
            shell=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        argv = json.loads(capture.read_text())
        self.assertIn("--sysroot=" + self.profile["arm_sysroot"], argv)
        self.assertEqual(argv[argv.index("-isystem") + 1], self.profile["arm_include"])
        self.assertIn("kernel.c", argv)
        self.assertFalse((self.makefile.parent / "HAZARD").exists())

    def test_independent_address_witness_uses_same_selected_compilers_and_sdk_flags(
        self,
    ):
        benchmark = self.workspace / self.benchmark
        (benchmark / "sw").mkdir()
        (benchmark / "sw/main.cpp").write_text("int main(){}\n")
        (benchmark / "cluster_hw_defines.h").write_text("#define TOP 0x10020040\n")
        directory = self.root / "witness"
        directory.mkdir()
        contract = {
            "components": {"clusters": [{"name": "cluster"}]},
            "ir_paths": [self.benchmark + "/hw/top.ll"],
        }
        calls = []

        def command(argv, cwd, logs, label, environment, timeout):
            calls.append(argv)
            path = logs / (label + ".stdout")
            path.write_text("#define TOP 0x10020040\n")
            return {"stdout": path.name, "argv": argv}

        with mock.patch.object(
            build_inputs, "load_toolchain", return_value=self.profile
        ), mock.patch.object(build_inputs, "_command", side_effect=command):
            result = build_inputs.witness_build_inputs(
                self.workspace, {"benchmark": self.benchmark}, contract, directory, {}
            )
        self.assertEqual(result["state"], "passed")
        self.assertEqual(
            calls[0][0], str(Path(self.profile["arm_bin"]) / "arm-none-eabi-g++")
        )
        prefix = ir_toolchain.ir_compiler_argv(self.profile)
        self.assertEqual(calls[1][: len(prefix)], prefix)
        self.assertNotIn("llvm-12", json.dumps(calls))

    def test_modern_frontend_disables_contraction_in_build_and_preprocessor(self):
        prefix = ir_toolchain.ir_compiler_argv(self.profile)
        self.assertEqual(prefix.count("-ffp-contract=off"), 1)
        result = self.adapt()
        self.assertEqual(result["recipe_after"].count("-ffp-contract=off"), 1)
        self.assertEqual(
            result["toolchain"]["floating_point_policy"], "unfused_scalar_no_contract"
        )

    def test_conflicting_source_contraction_override_is_rejected(self):
        self.makefile.write_text(RECIPE.replace(" -O1", " -ffp-contract=fast -O1"))
        with self.assertRaisesRegex(ValueError, "floating-point contraction override"):
            self.adapt()

    def preflight(self, text, **options):
        path = self.workspace / "module.ll"
        path.write_text(text)
        receipt = self.root / "preflight.json"
        return ir_toolchain.preflight_known_ir_incompatibilities(
            [path],
            self.workspace,
            receipt,
            profile=options.get("profile", self.profile),
        )

    def test_known_fneg_and_fma_intrinsics_are_rejected_with_source_identity(self):
        text = """define double @f(double %a, double %b) {
  %neg = fneg double %a
  %v = call double @llvm.fmuladd.f64(double %a, double %b, double %neg)
  %w = call double @llvm.fma.f64(double %a, double %b, double %v)
  ret double %w
}
declare double @llvm.fmuladd.f64(double, double, double)
declare double @llvm.fma.f64(double, double, double)
"""
        with self.assertRaisesRegex(ValueError, "rejected before simulation"):
            self.preflight(text)
        record = json.loads((self.root / "preflight.json").read_text())
        self.assertEqual(record["state"], "rejected")
        self.assertEqual(
            {row["construct"] for row in record["findings"]},
            {"fneg", "llvm.fmuladd.f64", "llvm.fma.f64"},
        )
        self.assertEqual(
            record["files"][0]["sha256"],
            ir_toolchain._sha(self.workspace / "module.ll"),
        )
        self.assertFalse(record["complete_opcode_validation"])

    def test_scalar_ir_pass_is_explicitly_only_a_known_gap_check(self):
        result = self.preflight(
            "define double @f(double %a, double %b) {\n  %x = fmul double %a, %b\n  ret double %x\n}\n"
        )
        self.assertEqual(result["state"], "no_known_incompatibilities")
        self.assertFalse(result["complete_opcode_validation"])
        self.assertEqual(result["findings"], [])

    def test_unrelated_construct_is_not_falsely_advertised_as_validated(self):
        result = self.preflight(
            "define i32 @f(i32 %a) {\n  %v = freeze i32 %a\n  ret i32 %v\n}\n; fneg call @llvm.fma.f64\n"
        )
        self.assertEqual(result["state"], "no_known_incompatibilities")
        self.assertFalse(result["complete_opcode_validation"])
        self.assertIn("no claim", result["scope"])

    def test_legacy_ir_frontend_and_preflight_are_unchanged(self):
        legacy = toolchain_profile.load_toolchain(manifest={})
        self.assertNotIn("-ffp-contract=off", ir_toolchain.ir_compiler_argv(legacy))
        result = self.preflight("fneg unsupported legacy text", profile=legacy)
        self.assertEqual(result["state"], "legacy_not_checked")
        self.assertFalse((self.root / "preflight.json").exists())

    def test_modern_sdk_paths_are_explicit_profile_fields_and_legacy_stays_exact(self):
        modern = toolchain_profile.load_toolchain(
            manifest={
                "configuration_engine": {
                    "toolchain_profile": {
                        "id": "gem5-26-retained-salam",
                        "arm_sysroot": "/opt/target-sdk",
                        "arm_include": "/opt/target-sdk/include",
                    }
                }
            }
        )
        self.assertEqual(modern["arm_sysroot"], "/opt/target-sdk")
        self.assertNotIn("arm_sysroot", toolchain_profile.load_toolchain(manifest={}))
        with self.assertRaises(ValueError):
            toolchain_profile.load_toolchain(
                manifest={
                    "configuration_engine": {
                        "toolchain_profile": {
                            "id": "ubuntu20-llvm12-python38-armgcc9",
                            "arm_include": "/usr/include",
                        }
                    }
                }
            )
