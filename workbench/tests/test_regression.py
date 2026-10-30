"""Synthetic harness tests; these are not guest simulator correctness proof."""
import cmath
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from salam_workbench import regression as r
from salam_workbench.runner import file_hash, run_experiment


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def nw_tree(self):
        engine = self.root / "engine"
        base = engine / "benchmarks/sys_validation/nw"
        (base / "sw").mkdir(parents=True)
        (base / "hw").mkdir()
        (base / "sw/data.c").write_text(
            "\n".join(
                'const char *%s = "%s";' % (name, "a" * count)
                for name, count in (
                    ("a", 128),
                    ("b", 128),
                    ("alia", 256),
                    ("alib", 256),
                )
            )
        )
        (base / "defines.h").write_text(
            "#define CHECK\n#define ALEN 128\n#define BLEN 128\n"
        )
        (base / "config.yml").write_text("acc_cluster: []\n")
        (base / "hw/old.ll").write_text("saved IR is not a fresh build")
        (base / "sw/main.elf").write_bytes(b"saved binary")
        for name in r.GENERATOR:
            path = engine / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# generator fixture, not executed\n")
        (engine / "configs/common").mkdir(parents=True)
        (engine / "configs/common/Options.py").write_text("# runtime fixture\n")
        (engine / "benchmarks/common").mkdir(parents=True)
        (engine / "benchmarks/common/Makefile").write_text("# common fixture\n")
        entry = {
            "name": "nw",
            "oracle_kind": r.ORACLE_KINDS["nw"],
            "relative_path": "benchmarks/sys_validation/nw",
            "cluster": "nw_clstr",
            "header": "nw_clstr_hw_defines.h",
            "source_sha256": {},
        }
        for name in ("sw/data.c", "defines.h", "config.yml"):
            entry["source_sha256"][name] = file_hash(base / name)
        return engine, base, entry

    def test_staging_copies_sources_without_saved_artifacts_or_engine_writes(
        self,
    ):
        engine, base, entry = self.nw_tree()
        before = file_hash(base / "config.yml")
        workspace = self.root / "fresh"
        result = r.stage_sources(engine, workspace, entry)
        self.assertEqual(before, file_hash(base / "config.yml"))
        self.assertFalse((workspace / entry["relative_path"] / "hw/old.ll").exists())
        self.assertFalse((workspace / entry["relative_path"] / "sw/main.elf").exists())
        self.assertTrue((workspace / "configs/common/Options.py").is_file())
        self.assertTrue(result["no_saved_ir_or_guest_binary_copied"])
        self.assertEqual(result["oracle_data"]["byte_lengths"]["alia"], 256)

    def test_staging_refuses_existing_directory_and_engine_subdirectory(self):
        engine, base, entry = self.nw_tree()
        with self.assertRaises(ValueError):
            r.stage_sources(engine, engine / "work", entry)
        target = self.root / "existing"
        target.mkdir()
        (target / "keep").write_text("do not overwrite")
        with self.assertRaises(FileExistsError):
            r.stage_sources(engine, target, entry)
        self.assertEqual((target / "keep").read_text(), "do not overwrite")

    def test_fixed_contract_rejects_changed_oracle_source(self):
        engine, base, entry = self.nw_tree()
        (base / "sw/data.c").write_text("changed")
        with self.assertRaisesRegex(ValueError, "source changed"):
            r.verify_fixed_sources(engine, entry)

    def test_catalog_has_reviewed_oracle_and_overlay_bindings(self):
        catalog = r.load_catalog()
        self.assertEqual(set(catalog["workloads"]), {"bfs", "nw", "fft", "stencil3d"})
        self.assertEqual(
            [item["path"] for item in catalog["workloads"]["stencil3d"]["overlays"]],
            ["sw/bench.h", "hw/Makefile"],
        )
        altered = self.root / "catalog.json"
        catalog["workloads"]["fft"]["oracle_kind"] = "unreviewed"
        altered.write_text(json.dumps(catalog))
        with self.assertRaisesRegex(ValueError, "Invalid reviewed"):
            r.load_catalog(altered)

    def test_staging_replaces_only_copied_bytes_after_both_hash_checks(self):
        engine, base, entry = self.nw_tree()
        project = self.root / "project"
        overlay = project / "experiments/regression/overlays/nw/config.yml"
        overlay.parent.mkdir(parents=True)
        overlay.write_text("reviewed: true\n")
        original_hash = file_hash(base / "config.yml")
        entry["overlays"] = [
            {
                "path": "config.yml",
                "source": "experiments/regression/overlays/nw/config.yml",
                "sha256": file_hash(overlay),
            }
        ]
        manifest = overlay.parents[1] / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "staged_benchmark_overlays",
                    "entries": [
                        {
                            "benchmark": "nw",
                            "kind": "replace",
                            "base": "benchmarks/sys_validation/nw/config.yml",
                            "base_sha256": original_hash,
                            "overlay": entry["overlays"][0]["source"],
                            "overlay_sha256": file_hash(overlay),
                        }
                    ],
                }
            )
        )
        with patch.object(r, "PROJECT", project):
            staged = r.stage_sources(engine, self.root / "overlay-stage", entry)
            self.assertEqual(file_hash(base / "config.yml"), original_hash)
            self.assertEqual(
                file_hash(
                    self.root / "overlay-stage/benchmarks/sys_validation/nw/config.yml"
                ),
                file_hash(overlay),
            )
            self.assertEqual(staged["overlays"][0]["staged_sha256"], file_hash(overlay))
            overlay.write_text("unreviewed: true\n")
            with self.assertRaisesRegex(ValueError, "changed before staging"):
                r.stage_sources(engine, self.root / "rejected-stage", entry)
            self.assertFalse((self.root / "rejected-stage").exists())

    def test_nw_does_not_accept_truncated_alignment(self):
        engine, base, entry = self.nw_tree()
        text = (
            (base / "sw/data.c")
            .read_text()
            .replace('"' + "a" * 256 + '"', '"' + "a" * 255 + '"')
        )
        (base / "sw/data.c").write_text(text)
        with self.assertRaisesRegex(ValueError, "byte length"):
            r.inspect_oracle_data(base, entry)

    def test_fft_reference_checks_all_fixed_complex_outputs_and_finiteness(
        self,
    ):
        base = self.root / "fft"
        (base / "sw").mkdir(parents=True)

        def array(name, values):
            return (
                "const double "
                + name
                + "["
                + str(len(values))
                + "]={"
                + ",".join(map(str, values))
                + "};\n"
            )

        real_twid = [cmath.exp(-2j * cmath.pi * k / 1024).real for k in range(512)]
        imag_twid = [cmath.exp(-2j * cmath.pi * k / 1024).imag for k in range(512)]
        arrays = {
            "re": [1] + [0] * 1023,
            "co": [0] * 1024,
            "re_twid": real_twid,
            "co_twid": imag_twid,
            "re_chk": [1] * 1024,
            "co_chk": [0] * 1024,
        }
        path = base / "sw/data.c"
        path.write_text(
            "#ifndef TEST\n"
            + "".join(array(name, values) for name, values in arrays.items())
            + "#else\n"
        )
        result = r.inspect_oracle_data(base, {"name": "fft"})
        self.assertEqual(result["array_lengths"]["re_chk"], 1024)
        self.assertLess(result["max_reference_error"], 1e-6)
        arrays["re_chk"][1023] = 2
        path.write_text(
            "#ifndef TEST\n"
            + "".join(array(name, values) for name, values in arrays.items())
            + "#else\n"
        )
        with self.assertRaisesRegex(ValueError, "independent direct DFT"):
            r.inspect_oracle_data(base, {"name": "fft"})
        path.write_text(
            path.read_text().replace(
                "const double co[1024]={0", "const double co[1024]={nan", 1
            )
        )
        with self.assertRaisesRegex(ValueError, "finiteness"):
            r.inspect_oracle_data(base, {"name": "fft"})

    def test_stencil3d_oracle_is_bound_to_pinned_guest_generator(self):
        base = self.root / "stencil3d"
        (base / "sw").mkdir(parents=True)
        (base / "defines.h").write_text(
            """#define C_SIZE 2
#define HYT 32
#define COL 32
#define ROW 16
#define TYPE int32_t
#define SIZE (ROW * COL * HYT)
#define INDX(_row_size,_col_size,_i,_j,_k) ((_i)+_row_size*((_j)+_col_size*(_k)))
"""
        )
        (base / "sw/bench.h").write_text(
            """for(i=0;i<SIZE;i++) if(sts->sol[i]!=sts->check[i]){}
sts->inp[i]=i; sts->C[i]=i+2;
sts->check[INDX(ROW,COL,k,j,0)]=sts->inp[INDX(ROW,COL,k,j,0)];
sts->check[INDX(ROW,COL,k,j,HYT-1)]=sts->inp[INDX(ROW,COL,k,j,HYT-1)];
sts->check[INDX(ROW,COL,k,0,i)]=sts->inp[INDX(ROW,COL,k,0,i)];
sts->check[INDX(ROW,COL,k,COL-1,i)]=sts->inp[INDX(ROW,COL,k,COL-1,i)];
sts->check[INDX(ROW,COL,0,j,i)]=sts->inp[INDX(ROW,COL,0,j,i)];
sts->check[INDX(ROW,COL,ROW-1,j,i)]=sts->inp[INDX(ROW,COL,ROW-1,j,i)];
for(i=1;i<HYT-1;i++) for(j=1;j<COL-1;j++) for(k=1;k<ROW-1;k++) {}
sum0=sts->inp[INDX(ROW,COL,k,j,i)];
sum1=sts->inp[INDX(ROW,COL,k,j,i+1)]+sts->inp[INDX(ROW,COL,k,j,i-1)]+
sts->inp[INDX(ROW,COL,k,j+1,i)]+sts->inp[INDX(ROW,COL,k,j-1,i)]+
sts->inp[INDX(ROW,COL,k+1,j,i)]+sts->inp[INDX(ROW,COL,k-1,j,i)];
mul0=sum0*sts->C[0]; mul1=sum1*sts->C[1];
sts->check[INDX(ROW,COL,k,j,i)]=mul0+mul1;
"""
        )
        result = r.inspect_oracle_data(base, {"name": "stencil3d"})
        self.assertEqual(result["interior_outputs"], 12600)
        self.assertEqual(result["boundary_outputs"], 3784)
        (base / "sw/bench.h").write_text(
            (base / "sw/bench.h").read_text().replace("i+1", "i+2")
        )
        with self.assertRaisesRegex(
            ValueError, "pinned guest oracle structure|six-neighbor"
        ):
            r.inspect_oracle_data(base, {"name": "stencil3d"})

    def test_bfs_independent_traversal_rejects_wrong_reference(self):
        base = self.root / "bfs"
        (base / "sw").mkdir(parents=True)
        # A fixed-size synthetic graph with no outgoing edges; expected counts
        # are deliberately wrong even though the source arrays have valid sizes.
        (base / "sw/data.c").write_text(
            "const int start = 38;\nconst int nod[512]={"
            + ",".join(["0"] * 512)
            + "};\nconst int edg[4096]={"
            + ",".join(["0"] * 4096)
            + "};\nconst int chk[10]={2,0,0,0,0,0,0,0,0,0};\n"
        )
        with self.assertRaisesRegex(ValueError, "independent traversal"):
            r.inspect_oracle_data(
                base,
                {
                    "name": "bfs",
                    "workload": {"expected_level_counts": [2] + [0] * 9},
                },
            )

    def test_macros_require_checker_dimensions_and_original_dataset(self):
        expected = {"CHECK": "", "ALEN": "128", "BLEN": "128"}
        text = "#define CHECK \n#define ALEN 128\n#define BLEN 128\n"
        r.verify_macros(text, expected)
        for bad in (
            text.replace("#define CHECK \n", ""),
            text.replace("ALEN 128", "ALEN 16"),
            text + "#define TEST\n",
        ):
            with self.assertRaises(ValueError):
                r.verify_macros(bad, expected)

    def generated_fixture(self):
        workspace = self.root / "generated"
        folder = workspace / "configs/SALAM/generated"
        folder.mkdir(parents=True)
        rel = Path("benchmarks/sys_validation/nw")
        (workspace / rel).mkdir(parents=True)
        (folder / "fs_nw.py").write_text("import nw\n")
        lines = []
        for name in ("top", "nw"):
            lines += [
                "ir = " + repr(str(workspace / rel / "hw" / (name + ".ll"))),
                "config = " + repr(str(workspace / rel / "config.yml")),
            ]
        (folder / "nw.py").write_text("\n".join(lines))
        (workspace / rel / "nw_clstr_hw_defines.h").write_text(
            "\n".join(
                "#define %s 0x%x" % (key, 0x10020000 + i)
                for i, key in enumerate(
                    (
                        "TOP",
                        "NW",
                        "DMA_Flags",
                        "DMA_RdAddr",
                        "DMA_WrAddr",
                        "DMA_CopyLen",
                    )
                )
            )
        )
        return workspace, {
            "name": "nw",
            "relative_path": str(rel),
            "header": "nw_clstr_hw_defines.h",
        }

    def test_generated_paths_must_bind_to_staged_sources(self):
        workspace, entry = self.generated_fixture()
        r.inspect_generated(workspace, entry)
        path = workspace / "configs/SALAM/generated/nw.py"
        original = repr(str(workspace / entry["relative_path"] / "hw/top.ll"))
        path.write_text(
            path.read_text().replace(original, repr("/unrelated-engine/top.ll"))
        )
        with self.assertRaisesRegex(ValueError, "bound"):
            r.inspect_generated(workspace, entry)

    def test_ir_target_triples_require_arm_for_both_generated_modules(self):
        workspace, entry = self.generated_fixture()
        hw = workspace / entry["relative_path"] / "hw"
        hw.mkdir()
        for name in ("top", "nw"):
            (hw / (name + ".ll")).write_text('target triple = "armv7-pc-none-eabi"\n')
        records = r.inspect_ir_targets(workspace, entry)
        self.assertEqual(len(records), 2)
        self.assertTrue(
            all(item["target_triple"] == "armv7-pc-none-eabi" for item in records)
        )
        (hw / "nw.ll").write_text('target triple = "x86_64-unknown-linux-gnu"\n')
        with self.assertRaisesRegex(ValueError, "unexpected target triple"):
            r.inspect_ir_targets(workspace, entry)

    def test_simulator_args_use_staged_artifacts_without_own_outdir(self):
        engine, workspace = self.root / "engine", self.root / "workspace"
        entry = {
            "name": "bfs",
            "relative_path": "benchmarks/sys_validation/bfs",
        }
        args = r.simulator_args(engine, workspace, entry)
        self.assertEqual(args[0], str(workspace / "configs/SALAM/generated/fs_bfs.py"))
        self.assertIn(
            "--kernel=" + str(workspace / entry["relative_path"] / "sw/main.elf"),
            args,
        )
        self.assertFalse(any(arg.startswith("--outdir") for arg in args))

    def test_build_command_nonzero_and_timeout_preserve_logs(self):
        env = {"PATH": os.environ.get("PATH", "")}
        for label, code, timeout in (
            (
                "bad",
                "import sys; print('failure detail',file=sys.stderr); sys.exit(7)",
                5,
            ),
            (
                "slow",
                "import time; print('started',flush=True); time.sleep(3)",
                0.1,
            ),
        ):
            with self.assertRaises(RuntimeError):
                r._command(
                    [sys.executable, "-c", code],
                    self.root,
                    self.root,
                    label,
                    env,
                    timeout,
                )
            saved = json.loads((self.root / (label + ".json")).read_text())
            self.assertEqual(
                saved["state"], "failed" if label == "bad" else "timed_out"
            )
            self.assertTrue((self.root / saved["stderr"]).exists())
            self.assertIn("finished_at", saved)

    def fixture_run(self, marker):
        project = self.root / "project"
        (project / "evidence").mkdir(parents=True)
        (project / "evidence/toolchain.json").write_text("{}")
        engine = self.root / "engine"
        (engine / "baremetal/common").mkdir(parents=True)
        (engine / "baremetal/common/fake.iso").write_text("fixture")
        workspace = self.root / "workspace"
        workspace.mkdir()
        source = workspace / "input.txt"
        source.write_text("fixed input")
        fixture = self.root / "simulator_fixture.py"
        fixture.write_text(
            "import pathlib,sys\nout=pathlib.Path(next(x.split('=',1)[1] for x in sys.argv if x.startswith('--outdir=')))\nout.mkdir(parents=True,exist_ok=True)\n(out/'system.terminal').write_text("
            + repr(marker)
            + ")\n(out/'config.ini').write_text('[fixture]\\n')\n(out/'config.json').write_text('{}')\n(out/'stats.txt').write_text('---------- Begin Simulation Statistics ----------\\nsimTicks 100\\nsimSeconds 0.0001\\nsimInsts 12\\nhostSeconds 0.1\\n---------- End Simulation Statistics   ----------\\n')\nprint('Exiting @ tick 100 because m5_exit instruction encountered')\n"
        )
        entry = {
            "name": "nw",
            "relative_path": "benchmarks/sys_validation/nw",
            "cluster": "nw_clstr",
            "workload": {},
            "timeout_seconds": 5,
            "limitations": ["synthetic fixture only"],
        }
        preparation = {
            "staging": {"workspace": str(workspace)},
            "inputs": [{"path": str(source), "sha256": file_hash(source)}],
        }

        def actual_fixture(prefix, args, **kwargs):
            return run_experiment([sys.executable, str(fixture)], args, **kwargs)

        with patch.object(r, "PROJECT", project), patch.object(
            r, "run_experiment", side_effect=actual_fixture
        ):
            return r.execute_workload(
                engine, entry, preparation, {}, self.root / "runs"
            )

    def test_success_fixture_requires_all_raw_evidence(self):
        record = self.fixture_run("Check Passed\n")
        self.assertEqual(record["state"], "passed")
        self.assertEqual(record["observability"]["status"], "unavailable")

    def test_duplicate_success_marker_is_incomplete(self):
        record = self.fixture_run("Check Passed\nCheck Passed\n")
        self.assertEqual(record["state"], "incomplete")

    def test_guest_failure_with_exit_zero_is_failed(self):
        record = self.fixture_run("Check Failed\n")
        self.assertEqual(record["return_code"], 0)
        self.assertEqual(record["state"], "failed")

    def test_zero_exit_without_check_is_not_passed(self):
        record = self.fixture_run("Job complete\n")
        self.assertNotEqual(record["state"], "passed")

    def test_preparation_failure_retains_state(self):
        engine, base, entry = self.nw_tree()
        entry.update(generation_timeout_seconds=10, build_timeout_seconds=10)
        output = self.root / "preparation"
        with patch.object(
            r,
            "_command",
            side_effect=RuntimeError("synthetic generation failure"),
        ):
            with self.assertRaises(RuntimeError):
                r.prepare_workload(engine, entry, output)
        record = json.loads((output / "preparation.json").read_text())
        self.assertEqual(record["state"], "failed")
        self.assertIn("synthetic generation failure", record["error"])


if __name__ == "__main__":
    unittest.main()
