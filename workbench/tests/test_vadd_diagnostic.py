"""Unit challenges for source-bound VADD pre-launch evidence."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from salam_workbench.vadd_diagnostic import (
    BENCHMARK,
    witness_vadd_build,
    witness_vadd_execution,
)


class VaddBuildWitnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.bench = self.workspace / BENCHMARK
        self.logs = self.root / "logs"
        (self.bench / "hw").mkdir(parents=True)
        (self.bench / "sw").mkdir()
        self.logs.mkdir()
        self.spec = {"benchmark": BENCHMARK, "benchmark_input": {"length": 7}}
        self.config = """acc_cluster:
  - Name: vadd_clstr
  - Accelerator:
    - Name: Top
      PIOSize: 25
  - Accelerator:
    - Name: vadd
      PIOSize: 1
    - Var:
      - {Name: VECTOR_A, Type: SPM, Size: 1024}
    - Var:
      - {Name: VECTOR_B, Type: SPM, Size: 1024}
    - Var:
      - {Name: VECTOR_C, Type: SPM, Size: 1024}
"""
        self.contract = {
            "ir_paths": [BENCHMARK + "/hw/top.ll", BENCHMARK + "/hw/vadd.ll"],
            "components": {
                "clusters": [
                    {
                        "name": "vadd_clstr",
                        "accelerators": [{"name": "Top", "pio_size": 64}],
                        "memories": [
                            {"name": name, "size": 1024}
                            for name in ("VECTOR_A", "VECTOR_B", "VECTOR_C")
                        ],
                    }
                ]
            },
        }
        self.write("config.yml", self.config)
        self.write("defines.h", "#define VADD_LENGTH 7\n#define TYPE int32_t\n")
        self.write("vadd_clstr_hw_defines.h", "#define VECTOR_A 0x1000\n")
        self.write("sw/main.cpp", '#include "../defines.h"\n')
        self.write("sw/main.elf", "synthetic guest object")
        self.write("hw/top.c", '#include "../defines.h"\n')
        self.write("hw/vadd.c", '#include "../defines.h"\n')
        self.write(
            "hw/top.ll",
            "define void @top(i64 %a, i64 %b, i64 %c) {\n"
            + "store volatile i32 28, i32* inttoptr (i32 8192 to i32*)\n" * 3
            + "ret void\n}\n",
        )
        self.write(
            "hw/vadd.ll",
            "define void @vadd() {\n"
            "%x = getelementptr inbounds i32, i32* inttoptr (i32 4096 to i32*), i32 %i\n"
            "%y = getelementptr inbounds i32, i32* inttoptr (i32 5120 to i32*), i32 %i\n"
            "%z = getelementptr inbounds i32, i32* inttoptr (i32 6144 to i32*), i32 %i\n"
            "%a = load i32, i32* %x\n%b = load i32, i32* %y\n"
            "%r = add nsw i32 %a, %b\nstore i32 %r, i32* %z\n"
            "%more = icmp eq i32 %i, 7\nret void\n}\n",
        )
        checks = []
        for name, relative in (
            ("guest", "sw/main.cpp"),
            ("ir-0", "hw/top.c"),
            ("ir-1", "hw/vadd.c"),
        ):
            content = b"#define VADD_LENGTH 7\n#define VADD_ELEMENT_BYTES 4\n#define TYPE int32_t\n"
            stdout = name + ".stdout"
            (self.logs / stdout).write_bytes(content)
            checks.append(
                {
                    "source": str(self.bench / relative),
                    "command": {
                        "argv": ["clang", "-dM", "-E", str(self.bench / relative)],
                        "state": "completed",
                        "return_code": 0,
                        "stdout": stdout,
                        "stdout_sha256": hashlib.sha256(content).hexdigest(),
                    },
                }
            )
        self.witness = {
            "state": "passed",
            "checks": checks,
            "expected_macros": {
                "VECTOR_A": 4096,
                "VECTOR_B": 5120,
                "VECTOR_C": 6144,
                "DMA_CopyLen": 8192,
            },
        }

    def write(self, relative, text):
        (self.bench / relative).write_text(text)

    def run_witness(self):
        return witness_vadd_build(
            self.workspace, self.spec, self.contract, self.logs, self.witness
        )

    def test_valid_witness_binds_three_compilers_and_artifacts(self):
        result = self.run_witness()
        self.assertEqual(result["state"], "passed")
        self.assertEqual(
            {x["role"] for x in result["probes"]}, {"guest", "top", "vadd"}
        )
        self.assertEqual(result["topology"]["transfer_bytes"], 28)
        self.assertEqual(result["top_dma_length_stores"], 3)
        self.assertEqual(len(result["guest_elf"]["sha256"]), 64)

    def test_missing_compiler_probe_fails(self):
        self.witness["checks"].pop()
        with self.assertRaisesRegex(ValueError, "three"):
            self.run_witness()

    def test_tampered_compiler_probe_fails(self):
        (self.logs / "guest.stdout").write_text("#define VADD_LENGTH 6\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.run_witness()

    def test_compiler_probe_must_target_recorded_source(self):
        self.witness["checks"][1]["command"]["argv"][-1] = "wrong.c"
        with self.assertRaisesRegex(ValueError, "compiler macro probe"):
            self.run_witness()

    def test_wrong_compiler_shape_even_with_matching_hash_fails(self):
        content = b"#define VADD_LENGTH 8\n#define VADD_ELEMENT_BYTES 4\n#define TYPE int32_t\n"
        (self.logs / "guest.stdout").write_bytes(content)
        self.witness["checks"][0]["command"]["stdout_sha256"] = hashlib.sha256(
            content
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "macros differ"):
            self.run_witness()

    def test_wrong_compiler_width_even_with_matching_hash_fails(self):
        content = b"#define VADD_LENGTH 7\n#define VADD_ELEMENT_BYTES 8\n#define TYPE int32_t\n"
        (self.logs / "ir-1.stdout").write_bytes(content)
        self.witness["checks"][2]["command"]["stdout_sha256"] = hashlib.sha256(
            content
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "macros differ"):
            self.run_witness()

    def test_length_one_does_not_require_a_loop(self):
        self.spec["benchmark_input"]["length"] = 1
        for check in self.witness["checks"]:
            content = b"#define VADD_LENGTH 1\n#define VADD_ELEMENT_BYTES 4\n#define TYPE int32_t\n"
            (self.logs / check["command"]["stdout"]).write_bytes(content)
            check["command"]["stdout_sha256"] = hashlib.sha256(content).hexdigest()
        kernel = (
            (self.bench / "hw/vadd.ll")
            .read_text()
            .replace("%more = icmp eq i32 %i, 7\n", "")
        )
        self.write("hw/vadd.ll", kernel)
        self.write(
            "hw/top.ll",
            "define void @top() {\n"
            + "store volatile i32 4, i32* inttoptr (i32 8192 to i32*)\n" * 3
            + "ret void\n}\n",
        )
        self.assertEqual(self.run_witness()["length"], 1)

    def test_rejects_wrong_memory_capacity_or_pio(self):
        self.write("config.yml", self.config.replace("Size: 1024", "Size: 27", 1))
        with self.assertRaisesRegex(ValueError, "too small"):
            self.run_witness()
        self.write("config.yml", self.config.replace("PIOSize: 25", "PIOSize: 24"))
        with self.assertRaisesRegex(ValueError, "PIO"):
            self.run_witness()

    def test_rejects_empty_or_wrong_width_kernel_and_dma(self):
        for ir in (
            "define void @vadd() {\nret void\n}\n",
            (self.bench / "hw/vadd.ll")
            .read_text()
            .replace("add nsw i32", "add nsw i64"),
            (self.bench / "hw/vadd.ll")
            .read_text()
            .replace("icmp eq i32 %i, 7", "icmp eq i32 %i, 8"),
        ):
            self.write("hw/vadd.ll", ir)
            with self.subTest(ir=ir), self.assertRaises(ValueError):
                self.run_witness()

    def test_rejects_incorrect_dma_length(self):
        self.write(
            "hw/top.ll",
            "define void @top() {\n"
            + "store volatile i32 32, i32* inttoptr (i32 8192 to i32*)\n" * 3
            + "ret void\n}\n",
        )
        with self.assertRaisesRegex(ValueError, "DMA transfers"):
            self.run_witness()

    def test_rejects_wrong_dma_destination_or_vector_address(self):
        top = (self.bench / "hw/top.ll").read_text().replace("i32 8192", "i32 8193")
        self.write("hw/top.ll", top)
        with self.assertRaisesRegex(ValueError, "DMA transfers"):
            self.run_witness()
        self.write("hw/top.ll", top.replace("i32 8193", "i32 8192"))
        kernel = (self.bench / "hw/vadd.ll").read_text().replace("i32 6144", "i32 6148")
        self.write("hw/vadd.ll", kernel)
        with self.assertRaisesRegex(ValueError, "runtime i32"):
            self.run_witness()


class VaddRuntimeWitnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sim = self.root / "simulator"
        self.obs = self.sim / "observability"
        self.obs.mkdir(parents=True)
        self.actor = "system.renamed_cluster.vadd"
        self.spec = {"benchmark": BENCHMARK, "benchmark_input": {"length": 3}}
        self.config = (
            "[" + self.actor + ".llvm_interface]\n"
            "in_file=/staged/benchmarks/sys_validation/vadd/hw/vadd.ll\n"
            "[" + self.actor + ".hw_interface.inst_config.add]\n"
            "opcode_num=13\nfunctional_unit=1\n"
        )
        (self.sim / "config.ini").write_text(self.config)
        self.life = {
            "kind": "salam_observability",
            "valid": True,
            "accelerator": self.actor,
            "invocation": 1,
            "lifecycle": {
                "completed": True,
                "start_tick": 100,
                "end_tick": 130,
                "elapsed_ticks": 30,
                "clock_period_ticks": 10,
                "interface_tick_calls": 4,
            },
            "memory": {
                "availability": "observed",
                "reads": {"completed": 6, "started_bytes": 24, "completed_bytes": 24},
                "writes": {"completed": 3, "started_bytes": 12, "completed_bytes": 12},
            },
            "execution": {
                "availability": "observed_selected_commits",
                "memory_read_commits": 6,
                "memory_write_commits": 3,
            },
            "diagnostics": {"pending_requests": 0, "invalid_events": 0},
        }
        self.trace = {
            "kind": "salam_fu_scheduling",
            "invocation": {"name": self.actor},
            "trace": [
                {"event": kind, "opcode": 13, "fu_id": 1}
                for _ in range(3)
                for kind in ("grant", "release")
            ],
        }
        self.run = {
            "state": "passed",
            "return_code": 0,
            "simulator_exit": {"reason": "m5_exit instruction encountered"},
            "executable": {
                "sha256": "a" * 64,
                "sha256_after_run": "a" * 64,
                "unchanged_after_run": True,
            },
        }
        self.sync()

    def sync(self):
        life = self.obs / (self.actor + ".invocation-1.json")
        trace = self.obs / ("fu-scheduling-" + self.actor + ".invocation-1.json")
        life.write_text(json.dumps(self.life))
        trace.write_text(json.dumps(self.trace))
        config = self.sim / "config.ini"
        entries = []
        for path in (config, life, trace):
            data = path.read_bytes()
            entries.append(
                {
                    "path": str(path.relative_to(self.root)),
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
        self.run["artifacts"] = entries
        (self.root / "run.json").write_text(json.dumps(self.run))
        self.replay = {
            "state": "passed",
            "invocations": [
                {
                    "state": "passed",
                    "path": str(trace),
                    "source_sha256": entries[2]["sha256"],
                    "config_ini": {"sha256": entries[0]["sha256"]},
                    "adjacent_lifecycle": {"sha256": entries[1]["sha256"]},
                    "trace": {"trace_complete": True},
                }
            ],
        }

    def check(self, **kwargs):
        return witness_vadd_execution(self.root, self.spec, self.replay, **kwargs)

    def test_active_bound_renamed_accelerator(self):
        result = self.check()
        self.assertEqual(result["state"], "passed")
        self.assertEqual(result["accelerator"], self.actor)
        self.assertEqual((result["add_grants"], result["add_releases"]), (3, 3))

    def test_inactive_events_or_missing_memory_completions_fail(self):
        self.trace["trace"] = []
        self.sync()
        with self.assertRaisesRegex(ValueError, "add grants"):
            self.check()
        self.trace["trace"] = [
            {"event": kind, "opcode": 13, "fu_id": 1}
            for _ in range(3)
            for kind in ("grant", "release")
        ]
        self.life["memory"]["reads"]["completed_bytes"] = 0
        self.sync()
        with self.assertRaisesRegex(ValueError, "memory completion"):
            self.check()

    def test_incomplete_or_wrong_component_fails(self):
        self.life["lifecycle"]["completed"] = False
        self.sync()
        with self.assertRaisesRegex(ValueError, "unfinished"):
            self.check()
        self.life["lifecycle"]["completed"] = True
        self.life["accelerator"] = "system.other.vadd"
        self.sync()
        with self.assertRaisesRegex(ValueError, "unfinished"):
            self.check()

    def test_extra_logical_memory_bytes_fail_despite_successful_run_and_replay(self):
        # A fixed-size kernel could produce the requested first results while
        # performing extra iterations; both run and replay remain otherwise valid.
        self.life["memory"]["reads"]["started_bytes"] += 8
        self.life["memory"]["reads"]["completed_bytes"] += 8
        self.life["memory"]["writes"]["started_bytes"] += 4
        self.life["memory"]["writes"]["completed_bytes"] += 4
        self.sync()
        with self.assertRaisesRegex(ValueError, "memory completion"):
            self.check()

    def test_tampering_or_wrong_ir_binding_fails(self):
        (self.sim / "config.ini").write_text(self.config + "# changed\n")
        with self.assertRaisesRegex(ValueError, "artifact identity"):
            self.check()
        (self.sim / "config.ini").write_text(
            self.config.replace("hw/vadd.ll", "hw/top.ll")
        )
        self.sync()
        with self.assertRaisesRegex(ValueError, "LLVM interface"):
            self.check()

    def test_expected_guest_failure_requires_explicit_control(self):
        self.run["state"] = "failed"
        self.run["correctness"] = {
            "outcome": "failed",
            "passed_markers": 0,
            "failed_markers": 1,
        }
        self.sync()
        with self.assertRaisesRegex(ValueError, "did not pass"):
            self.check()
        with self.assertRaisesRegex(ValueError, "explicit mismatch"):
            self.check(allow_failed_guest=True)
        self.spec["benchmark_input"]["inject_mismatch"] = True
        result = self.check(allow_failed_guest=True)
        self.assertTrue(result["expected_guest_failure"])
        self.spec["benchmark_input"]["force_guest_pass"] = True
        with self.assertRaisesRegex(ValueError, "explicit mismatch"):
            self.check(allow_failed_guest=True)


if __name__ == "__main__":
    unittest.main()
