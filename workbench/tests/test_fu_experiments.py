"""Independent negative controls for direct SALAM FU event evidence."""
import hashlib
import json
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from salam_workbench.fu_experiments import (
    _load_image_identity,
    inspect_fu_invocation,
    inspect_fu_run,
    inspect_negative_control,
    validate_fu_trace,
    verify_fu_study,
)


def _sample():
    events = []

    def add(kind, cycle, unit, lease):
        events.append(
            {
                "event": kind,
                "cycle": cycle,
                "tick": cycle * 10000,
                "uid": 10,
                "opcode": 17,
                "fu_id": unit,
                "lease_id": lease,
            }
        )

    add("grant", 1, 1, 1)
    add("deny", 2, 1, 0)
    add("grant", 2, 2, 2)
    add("release", 3, 1, 1)
    add("grant", 4, 1, 3)
    add("release", 5, 2, 2)
    add("release", 6, 1, 3)
    for event in events:
        if event["fu_id"] == 2:
            event["opcode"] = 13
    return {
        "schema_version": 1,
        "kind": "salam_fu_scheduling",
        "trace_truncated": False,
        "invocation": {
            "name": "system.gemm_clstr.gemm",
            "elapsed_cycles": 6,
            "elapsed_ticks": 60000,
        },
        "units": [
            {
                "id": 1,
                "name": "integer_multiplier",
                "limit": 1,
                "attempts": 3,
                "grants": 2,
                "denials": 1,
                "releases": 2,
                "peak": 1,
                "outstanding": 0,
            },
            {
                "id": 2,
                "name": "integer_adder",
                "limit": 0,
                "attempts": 1,
                "grants": 1,
                "denials": 0,
                "releases": 1,
                "peak": 1,
                "outstanding": 0,
            },
        ],
        "totals": {
            "attempts": 4,
            "grants": 3,
            "denials": 1,
            "releases": 3,
            "peak": 2,
            "outstanding": 0,
        },
        "trace": events,
    }


class FuTraceTest(unittest.TestCase):
    def test_complete_replay_with_simultaneous_distinct_units(self):
        replay = validate_fu_trace(_sample())
        self.assertEqual(replay["state"], "passed", replay["issues"])
        self.assertEqual(replay["totals"]["peak"], 2)
        self.assertEqual(replay["events_replayed"], 7)

    def test_reject_over_capacity_grant(self):
        data = _sample()
        data["trace"].insert(1, {**data["trace"][0], "lease_id": 4})
        self.assertIn(
            "over_capacity_grant",
            [i["code"] for i in validate_fu_trace(data)["issues"]],
        )

    def test_reject_unmatched_release(self):
        data = _sample()
        data["trace"][-1]["lease_id"] = 99
        self.assertIn(
            "unmatched_release",
            [i["code"] for i in validate_fu_trace(data)["issues"]],
        )

    def test_reject_counter_only_or_truncated(self):
        for mutation in (
            lambda x: x.pop("trace"),
            lambda x: x.update(trace_truncated=True),
        ):
            data = _sample()
            mutation(data)
            self.assertEqual(validate_fu_trace(data)["state"], "failed")

    def test_reject_invalid_counter_and_lease_order(self):
        data = _sample()
        data["units"][0]["denials"] = 0
        self.assertIn(
            "counter_mismatch",
            [i["code"] for i in validate_fu_trace(data)["issues"]],
        )
        data = _sample()
        data["trace"][4]["lease_id"] = 1
        self.assertIn(
            "duplicate_lease",
            [i["code"] for i in validate_fu_trace(data)["issues"]],
        )

    def test_release_must_match_original_dynamic_instruction(self):
        data = _sample()
        data["trace"][-1]["opcode"] = 18
        self.assertIn(
            "unmatched_release",
            [i["code"] for i in validate_fu_trace(data)["issues"]],
        )

    def test_reject_wrong_producer_or_out_of_bound_cycle(self):
        data = _sample()
        data["kind"] = "not_salam_fu_scheduling"
        self.assertEqual(validate_fu_trace(data)["state"], "failed")
        data = _sample()
        data["trace"][-1]["cycle"] = 7
        self.assertIn(
            "event_cycle_bounds",
            [i["code"] for i in validate_fu_trace(data)["issues"]],
        )

    def test_malformed_event_is_failure_not_exception(self):
        data = _sample()
        data["trace"][0]["fu_id"] = []
        self.assertEqual(validate_fu_trace(data)["state"], "failed")

    def test_lifecycle_and_config_ini_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            direct = root / "fu-scheduling-system.gemm_clstr.gemm.invocation-1.json"
            adjacent = root / "system.gemm_clstr.gemm.invocation-1.json"
            ini = root / "config.ini"
            direct.write_text(json.dumps(_sample()), encoding="utf-8")
            adjacent.write_text(
                json.dumps(
                    {
                        "accelerator": "system.gemm_clstr.gemm",
                        "valid": True,
                        "lifecycle": {
                            "completed": True,
                            "start_tick": 0,
                            "end_tick": 60000,
                            "elapsed_ticks": 60000,
                            "clock_period_ticks": 10000,
                        },
                    }
                ),
                encoding="utf-8",
            )
            ini.write_text(
                "[system.gemm_clstr.gemm.hw_interface.functional_units.integer_multiplier]\n"
                "limit=1\nenum_value=1\n"
                "[system.gemm_clstr.gemm.hw_interface.functional_units.integer_adder]\n"
                "limit=0\nenum_value=2\n"
                "[system.gemm_clstr.gemm.hw_interface.inst_config.mul]\n"
                "opcode_num=17\nfunctional_unit=1\n"
                "[system.gemm_clstr.gemm.hw_interface.inst_config.add]\n"
                "opcode_num=13\nfunctional_unit=2\n"
                "[system.gemm_clstr.gemm.hw_interface.cycle_counts]\nmul=2\n",
                encoding="utf-8",
            )
            self.assertEqual(inspect_fu_invocation(direct, ini)["state"], "passed")
            ini.write_text(
                ini.read_text().replace("limit=1", "limit=2"), encoding="utf-8"
            )
            self.assertIn(
                "effective_limit",
                [i["code"] for i in inspect_fu_invocation(direct, ini)["issues"]],
            )
            ini.write_text(
                ini.read_text().replace("limit=2", "limit=1"), encoding="utf-8"
            )
            adjacent.write_text(
                adjacent.read_text().replace("60000", "50000"),
                encoding="utf-8",
            )
            self.assertIn(
                "lifecycle_mismatch",
                [i["code"] for i in inspect_fu_invocation(direct, ini)["issues"]],
            )

    def test_reject_event_outside_adjacent_tick_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            direct = root / "fu-scheduling-system.gemm_clstr.gemm.invocation-1.json"
            adjacent = root / "system.gemm_clstr.gemm.invocation-1.json"
            direct.write_text(json.dumps(_sample()), encoding="utf-8")
            adjacent.write_text(
                json.dumps(
                    {
                        "accelerator": "system.gemm_clstr.gemm",
                        "valid": True,
                        "lifecycle": {
                            "completed": True,
                            "start_tick": 100000,
                            "end_tick": 160000,
                            "elapsed_ticks": 60000,
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.assertIn(
                "event_tick_bounds",
                [i["code"] for i in inspect_fu_invocation(direct)["issues"]],
            )


def _study_data(case, ticks):
    limits = {
        "unlimited": (0, 0),
        "cap1": (1, 0),
        "cap2": (2, 0),
        "unused": (0, 1),
    }
    cap, unused = limits[case]
    if cap == 1:
        sequence = [
            ("grant", 1),
            ("deny", 0),
            ("release", 1),
            ("grant", 2),
            ("release", 2),
            ("grant", 3),
            ("release", 3),
        ]
        peak, denied = 1, 1
    elif cap == 2:
        sequence = [
            ("grant", 1),
            ("grant", 2),
            ("deny", 0),
            ("release", 1),
            ("grant", 3),
            ("release", 2),
            ("release", 3),
        ]
        peak, denied = 2, 1
    else:
        sequence = [
            ("grant", 1),
            ("grant", 2),
            ("grant", 3),
            ("release", 1),
            ("release", 2),
            ("release", 3),
        ]
        peak, denied = 3, 0
    events = [
        {
            "event": kind,
            "cycle": index + 1,
            "tick": (index + 1) * 10000,
            "uid": 10,
            "opcode": 17,
            "fu_id": 1,
            "lease_id": lease,
        }
        for index, (kind, lease) in enumerate(sequence)
    ]
    return {
        "schema_version": 1,
        "kind": "salam_fu_scheduling",
        "trace_truncated": False,
        "invocation": {
            "name": "system.gemm_clstr.gemm",
            "elapsed_cycles": ticks // 10000,
            "elapsed_ticks": ticks,
        },
        "units": [
            {
                "id": 1,
                "name": "integer_multiplier",
                "limit": cap,
                "attempts": 3 + denied,
                "grants": 3,
                "denials": denied,
                "releases": 3,
                "peak": peak,
                "outstanding": 0,
            },
            {
                "id": 2,
                "name": "double_divider",
                "limit": unused,
                "attempts": 0,
                "grants": 0,
                "denials": 0,
                "releases": 0,
                "peak": 0,
                "outstanding": 0,
            },
        ],
        "totals": {
            "attempts": 3 + denied,
            "grants": 3,
            "denials": denied,
            "releases": 3,
            "peak": peak,
            "outstanding": 0,
        },
        "trace": events,
    }


def _write_study_run(root, case, ticks, *, source_change=False):
    ticks *= 1000
    root.mkdir(parents=True)
    run = root / "runs" / "r1"
    sim = run / "simulator"
    obs = sim / "observability"
    obs.mkdir(parents=True)
    data = _study_data(case, ticks)
    cap = {"cap1": 1, "cap2": 2}.get(case, 512)
    events = []
    cycle = 1
    for begin in range(1, 513, cap):
        leases = range(begin, min(begin + cap, 513))
        for lease in leases:
            events.append(
                {
                    "event": "grant",
                    "cycle": cycle,
                    "tick": cycle * 10000,
                    "uid": 10,
                    "opcode": 17,
                    "fu_id": 1,
                    "lease_id": lease,
                }
            )
        if case in ("cap1", "cap2"):
            events.append(
                {
                    "event": "deny",
                    "cycle": cycle + 1,
                    "tick": (cycle + 1) * 10000,
                    "uid": 10,
                    "opcode": 17,
                    "fu_id": 1,
                    "lease_id": 0,
                }
            )
        for lease in leases:
            events.append(
                {
                    "event": "release",
                    "cycle": cycle + 16,
                    "tick": (cycle + 16) * 10000,
                    "uid": 10,
                    "opcode": 17,
                    "fu_id": 1,
                    "lease_id": lease,
                }
            )
        cycle += 17
    denied = sum(e["event"] == "deny" for e in events)
    data["trace"] = events
    data["units"][0].update(
        attempts=512 + denied,
        grants=512,
        denials=denied,
        releases=512,
        peak=cap,
    )
    data["totals"].update(
        attempts=512 + denied,
        grants=512,
        denials=denied,
        releases=512,
        peak=cap,
    )
    self_check = validate_fu_trace(data)
    assert self_check["state"] == "passed", self_check["issues"]
    (obs / "fu-scheduling-system.gemm_clstr.gemm.invocation-1.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    (obs / "system.gemm_clstr.gemm.invocation-1.json").write_text(
        json.dumps(
            {
                "accelerator": "system.gemm_clstr.gemm",
                "valid": True,
                "lifecycle": {
                    "completed": True,
                    "start_tick": 0,
                    "end_tick": ticks,
                    "elapsed_ticks": ticks,
                    "clock_period_ticks": 10000,
                },
            }
        ),
        encoding="utf-8",
    )
    cap, unused = {
        "unlimited": (0, 0),
        "cap1": (1, 0),
        "cap2": (2, 0),
        "unused": (0, 1),
    }[case]
    (sim / "config.ini").write_text(
        "[system.gemm_clstr.gemm.hw_interface.cycle_counts]\nmul=16\n"
        "[system.gemm_clstr.gemm.hw_interface.functional_units.integer_multiplier]\n"
        "limit={}\nenum_value=1\n".format(cap)
        + "[system.gemm_clstr.gemm.hw_interface.functional_units.double_divider]\n"
        "limit={}\nenum_value=2\n".format(unused)
        + "[system.gemm_clstr.gemm.hw_interface.inst_config.mul]\nopcode_num=17\nfunctional_unit=1\n"
        + "[system.gemm_clstr.gemm.llvm_interface]\nin_file="
        + str(root / "workspace/benchmarks/sys_validation/gemm/hw/gemm.ll")
        + "\n"
        + "[system.gemm_clstr.top.llvm_interface]\nin_file="
        + str(root / "workspace/benchmarks/sys_validation/gemm/hw/top.ll")
        + "\n"
        + "[system.workload]\nobject_file="
        + str(root / "workspace/benchmarks/sys_validation/gemm/sw/main.elf")
        + "\n",
        encoding="utf-8",
    )
    (sim / "system.terminal").write_text("Check Passed\n", encoding="utf-8")
    (root / "configuration.json").write_text(
        json.dumps(
            {
                "state": "passed",
                "run_state": "passed",
                "numerical_correctness": "guest_checker_passed",
                "run_directory": str(run),
                "engine": {
                    "binary": {"sha256": "a" * 64},
                    "compiled_source_sha256": "b" * 64,
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "contract-effective.json").write_text(
        json.dumps({"valid": True}), encoding="utf-8"
    )
    requested = {
        "system.gemm_clstr.gemm.hw_interface.functional_units.integer_multiplier": {
            "limit": cap
        }
    }
    if case == "unused":
        requested[
            "system.gemm_clstr.gemm.hw_interface.functional_units.double_divider"
        ] = {"limit": 1}
    (root / "specification.json").write_text(
        json.dumps(
            {
                "name": "gemm",
                "benchmark": "benchmarks/sys_validation/gemm",
                "base_address": "0x10020000",
                "system": {"mem-size": "2GB"},
                "configuration_documents": [{"same": True}],
                "parameters": requested,
            }
        ),
        encoding="utf-8",
    )
    records = []
    for suffix in (
        "config.yml",
        "hw/gemm.c",
        "hw/gemm.ll",
        "hw/top.c",
        "hw/top.ll",
        "sw/main.cpp",
        "sw/main.elf",
    ):
        path = root / "workspace/benchmarks/sys_validation/gemm" / suffix
        path.parent.mkdir(parents=True, exist_ok=True)
        content = suffix + (
            "changed" if source_change and suffix == "hw/gemm.ll" else ""
        )
        path.write_text(content, encoding="utf-8")
        records.append(
            {
                "path": str(path),
                "sha256": hashlib.sha256(content.encode()).hexdigest(),
            }
        )
    (root / "prepared-inputs.json").write_text(json.dumps(records), encoding="utf-8")
    names = [
        "simulator/system.terminal",
        "simulator/config.ini",
        "simulator/observability/fu-scheduling-system.gemm_clstr.gemm.invocation-1.json",
        "simulator/observability/system.gemm_clstr.gemm.invocation-1.json",
    ]
    (run / "run.json").write_text(
        json.dumps(
            {
                "state": "passed",
                "correctness": {
                    "outcome": "passed",
                    "passed_markers": 1,
                    "failed_markers": 0,
                    "guest_output": "simulator/system.terminal",
                },
                "required_artifact_checks": [
                    {"path": path, "available": True} for path in names[:3]
                ],
                "artifacts": [
                    {
                        "path": path,
                        "sha256": hashlib.sha256((run / path).read_bytes()).hexdigest(),
                    }
                    for path in names
                ],
            }
        ),
        encoding="utf-8",
    )
    # Full raw runner evidence for independent revalidation, still synthetic.
    (sim / "stats.txt").write_text(
        "---------- Begin Simulation Statistics ----------\n"
        "simTicks 100\nsimSeconds 0.0001\nsimInsts 10\nhostSeconds 0.01\n"
        "---------- End Simulation Statistics   ----------\n"
    )
    exit_text = "Exiting @ tick 100 because m5_exit instruction encountered\n"
    (run / "stdout.txt").write_text(exit_text)
    (run / "stderr.txt").write_text("")
    (run / "experiment.json").write_text("{}")
    from salam_workbench.runner import _read_correctness, _read_exit_events

    raw = json.loads((run / "run.json").read_text())
    raw.update(
        run_id=root.parent.name + "-" + root.name,
        return_code=0,
        correctness=_read_correctness(sim / "system.terminal"),
        simulator_exit_events=_read_exit_events(run / "stdout.txt"),
        experiment_spec_sha256=hashlib.sha256(b"{}").hexdigest(),
        snapshot_inputs=True,
        inputs=[],
        executable={
            "sha256": "a" * 64,
            "sha256_after_run": "a" * 64,
            "unchanged_after_run": True,
        },
        required_artifacts=names,
    )
    raw["simulator_exit"] = raw["simulator_exit_events"][-1]
    for index, record in enumerate(records):
        source = Path(record["path"])
        snapshot = run / "inputs" / str(index)
        snapshot.parent.mkdir(exist_ok=True)
        snapshot.write_bytes(source.read_bytes())
        raw["inputs"].append(
            {
                **record,
                "sha256_after_run": record["sha256"],
                "unchanged_after_run": True,
                "snapshot": {
                    "path": snapshot.relative_to(run).as_posix(),
                    "sha256": record["sha256"],
                    "sha256_after_run": record["sha256"],
                    "unchanged_after_run": True,
                },
            }
        )
    raw["artifacts"] = [
        {
            "path": p.relative_to(run).as_posix(),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in run.rglob("*")
        if p.is_file() and p.name != "run.json"
    ]
    (run / "run.json").write_text(json.dumps(raw))
    build = root / "build"
    build.mkdir()
    files = {"fixture.cc": "c" * 64}
    digest = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (build / "source-inputs.json").write_text(
        json.dumps({"files": files, "sha256": digest})
    )
    (build / "build.json").write_text(
        json.dumps(
            {
                "state": "built",
                "binary": {"sha256": "a" * 64},
                "compiled_source_sha256": digest,
                "source_inputs_sha256": hashlib.sha256(
                    (build / "source-inputs.json").read_bytes()
                ).hexdigest(),
            }
        )
    )
    receipt = json.loads((root / "configuration.json").read_text())
    receipt["engine"].update(
        compiled_source_sha256=digest,
        receipt={
            "path": str(build / "build.json"),
            "sha256": hashlib.sha256((build / "build.json").read_bytes()).hexdigest(),
        },
    )
    (root / "configuration.json").write_text(json.dumps(receipt))
    return root


def _verify_fixture_study(cases):
    # This isolates positive matrix/repeat logic; negative binding has separate tests.
    with patch(
        "salam_workbench.fu_experiments.inspect_negative_control",
        return_value={
            "state": "passed",
            "run_directory": "negative-fixture",
            "raw_run_id": "negative-fixture",
        },
    ):
        return verify_fu_study(cases, "negative-fixture")


class FuStudyTest(unittest.TestCase):
    def test_two_repeat_causal_controls(self):
        with tempfile.TemporaryDirectory() as folder, patch(
            "salam_workbench.fu_experiments._load_image_identity",
            return_value={
                "objcopy_sha256": "c" * 64,
                "load_image_sha256": "d" * 64,
                "load_image_bytes": 8,
            },
        ):
            root = Path(folder)
            cases = {
                case: [
                    _write_study_run(root / case / str(index), case, ticks)
                    for index in (1, 2)
                ]
                for case, ticks in (
                    ("unlimited", 100000),
                    ("cap1", 300000),
                    ("cap2", 200000),
                    ("unused", 100000),
                )
            }
            self.assertEqual(
                inspect_fu_run(cases["cap1"][0], "cap1")["state"], "passed"
            )
            result = _verify_fixture_study(cases)
            self.assertEqual(result["state"], "passed", result)
            cases["cap2"][1] = _write_study_run(
                root / "changed", "cap2", 200000, source_change=True
            )
            result = _verify_fixture_study(cases)
            self.assertIn("varying_inputs", [i["code"] for i in result["issues"]])

    def test_unrelated_parameter_change_fails_identity(self):
        with tempfile.TemporaryDirectory() as folder, patch(
            "salam_workbench.fu_experiments._load_image_identity",
            return_value={
                "objcopy_sha256": "c" * 64,
                "load_image_sha256": "d" * 64,
                "load_image_bytes": 8,
            },
        ):
            root = Path(folder)
            cases = {
                case: [
                    _write_study_run(root / case / str(index), case, ticks)
                    for index in (1, 2)
                ]
                for case, ticks in (
                    ("unlimited", 100000),
                    ("cap1", 300000),
                    ("cap2", 200000),
                    ("unused", 100000),
                )
            }
            path = cases["cap2"][0] / "specification.json"
            spec = json.loads(path.read_text())
            spec["parameters"][
                "system.gemm_clstr.gemm.hw_interface.functional_units.integer_adder"
            ] = {"cycles": 9}
            path.write_text(json.dumps(spec), encoding="utf-8")
            self.assertIn(
                "varying_inputs",
                [i["code"] for i in _verify_fixture_study(cases)["issues"]],
            )

    def test_missing_contention_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as folder, patch(
            "salam_workbench.fu_experiments._load_image_identity",
            return_value={
                "objcopy_sha256": "c" * 64,
                "load_image_sha256": "d" * 64,
                "load_image_bytes": 8,
            },
        ):
            root = Path(folder)
            cases = {
                case: [
                    _write_study_run(root / case / str(index), case, ticks)
                    for index in (1, 2)
                ]
                for case, ticks in (
                    ("unlimited", 100000),
                    ("cap1", 200000),
                    ("cap2", 200000),
                    ("unused", 100000),
                )
            }
            self.assertEqual(_verify_fixture_study(cases)["state"], "inconclusive")

    def test_repeats_must_match_exact_observations(self):
        with tempfile.TemporaryDirectory() as folder, patch(
            "salam_workbench.fu_experiments._load_image_identity",
            return_value={
                "objcopy_sha256": "c" * 64,
                "load_image_sha256": "d" * 64,
                "load_image_bytes": 8,
            },
        ):
            root = Path(folder)
            cases = {
                case: [
                    _write_study_run(root / case / str(index), case, ticks)
                    for index in (1, 2)
                ]
                for case, ticks in (
                    ("unlimited", 100000),
                    ("cap1", 300000),
                    ("cap2", 200000),
                    ("unused", 100000),
                )
            }
            cases["cap1"][1] = _write_study_run(
                root / "different_repeat", "cap1", 310000
            )
            self.assertEqual(_verify_fixture_study(cases)["state"], "inconclusive")

    def test_negative_control_requires_raw_failure_and_hashed_terminal(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder) / "run"
            sim = run / "simulator"
            sim.mkdir(parents=True)
            terminal = sim / "system.terminal"
            terminal.write_text("Check Failed\n", encoding="utf-8")
            raw = {
                "state": "failed",
                "run_id": "negative",
                "correctness": {
                    "outcome": "failed",
                    "failed_markers": 1,
                    "passed_markers": 0,
                },
                "required_artifact_checks": [
                    {"path": "simulator/system.terminal", "available": True}
                ],
                "artifacts": [
                    {
                        "path": "simulator/system.terminal",
                        "sha256": hashlib.sha256(terminal.read_bytes()).hexdigest(),
                    }
                ],
            }
            (run / "run.json").write_text(json.dumps(raw), encoding="utf-8")
            with patch(
                "salam_workbench.report.load_run",
                return_value={"issues": ["Run state is not passed: failed"]},
            ):
                self.assertEqual(inspect_negative_control(run)["state"], "passed")
                terminal.write_text("Check Passed\n", encoding="utf-8")
                self.assertEqual(inspect_negative_control(run)["state"], "failed")

    @unittest.skipUnless(
        shutil.which("arm-none-eabi-as") and shutil.which("arm-none-eabi-ld"),
        "ARM binutils unavailable",
    )
    def test_objcopy_binds_actual_loaded_arm_image(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "test.s"
            elf = root / "test.elf"
            obj = root / "test.o"
            source.write_text(
                ".syntax unified\n.text\n.global _start\n_start:\n  mov r0, #1\n",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    shutil.which("arm-none-eabi-as"),
                    "-o",
                    str(obj),
                    str(source),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            with self.assertRaises(ValueError):
                _load_image_identity(obj)
            subprocess.run(
                [
                    shutil.which("arm-none-eabi-ld"),
                    "-Ttext=0x80000000",
                    "-e",
                    "_start",
                    "-o",
                    str(elf),
                    str(obj),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            identity = _load_image_identity(elf)
            self.assertEqual(len(identity["load_image_sha256"]), 64)
            self.assertGreater(identity["load_image_bytes"], 0)
            self.assertEqual(identity["elf_load_contract"]["entry"], 0x80000000)


class FuHardeningTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="fu-hardening-fixture-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        patcher = patch(
            "salam_workbench.fu_experiments._load_image_identity",
            return_value={
                "load_image_sha256": "d" * 64,
                "load_image_bytes": 8,
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def cases(self):
        return {
            case: [
                _write_study_run(self.root / case / str(index), case, ticks)
                for index in (1, 2)
            ]
            for case, ticks in (
                ("unlimited", 100000),
                ("cap1", 300000),
                ("cap2", 200000),
                ("unused", 100000),
            )
        }

    def test_missing_negative_and_reused_directory_are_rejected(self):
        cases = self.cases()
        self.assertIn(
            "negative_control_missing",
            [i["code"] for i in verify_fu_study(cases)["issues"]],
        )
        cases["cap1"][1] = cases["cap1"][0]
        self.assertIn(
            "duplicate_pipeline",
            [i["code"] for i in _verify_fixture_study(cases)["issues"]],
        )

    def test_distinct_paths_with_duplicate_recorded_run_id_are_rejected(self):
        cases = self.cases()
        a, b = [p / "runs/r1/run.json" for p in cases["cap1"]]
        data = json.loads(b.read_text())
        data["run_id"] = json.loads(a.read_text())["run_id"]
        b.write_text(json.dumps(data))
        self.assertIn(
            "duplicate_run",
            [i["code"] for i in _verify_fixture_study(cases)["issues"]],
        )

    def test_engine_claim_must_equal_actual_executable_hash(self):
        path = _write_study_run(self.root / "cap1/1", "cap1", 300000)
        receipt = path / "runs/r1/run.json"
        data = json.loads(receipt.read_text())
        data["executable"].update(sha256="f" * 64, sha256_after_run="f" * 64)
        receipt.write_text(json.dumps(data))
        result = inspect_fu_run(path, "cap1")
        self.assertTrue(
            any("actual run executable" in i["detail"] for i in result["issues"])
        )

    def test_snapshot_corruption_fails_raw_revalidation(self):
        path = _write_study_run(self.root / "cap1/1", "cap1", 300000)
        (path / "runs/r1/inputs/0").write_text("changed only immutable snapshot")
        self.assertIn(
            "raw_revalidation",
            [i["code"] for i in inspect_fu_run(path, "cap1")["issues"]],
        )

    def test_effective_clock_change_cannot_hide_behind_same_specification(
        self,
    ):
        cases = self.cases()
        run = cases["cap2"][0] / "runs/r1"
        ini = run / "simulator/config.ini"
        ini.write_text(ini.read_text() + "[system.clk_domain]\nclock=12345\n")
        data = json.loads((run / "run.json").read_text())
        for artifact in data["artifacts"]:
            if artifact["path"] == "simulator/config.ini":
                artifact["sha256"] = hashlib.sha256(ini.read_bytes()).hexdigest()
        (run / "run.json").write_text(json.dumps(data))
        self.assertIn(
            "varying_inputs",
            [i["code"] for i in _verify_fixture_study(cases)["issues"]],
        )

    def test_opcode_mapping_and_exact_multiply_holding_time(self):
        path = _write_study_run(self.root / "cap1/1", "cap1", 300000)
        sim = path / "runs/r1/simulator"
        direct = (
            sim / "observability/fu-scheduling-system.gemm_clstr.gemm.invocation-1.json"
        )
        original = json.loads(direct.read_text())
        changed = json.loads(json.dumps(original))
        for event in changed["trace"]:
            event["opcode"] = 18
        direct.write_text(json.dumps(changed))
        self.assertIn(
            "effective_opcode_fu",
            [
                i["code"]
                for i in inspect_fu_invocation(direct, sim / "config.ini")["issues"]
            ],
        )
        changed = json.loads(json.dumps(original))
        changed["trace"][2]["cycle"] -= 1
        changed["trace"][2]["tick"] -= 10000
        direct.write_text(json.dumps(changed))
        self.assertIn(
            "multiply_lease_duration",
            [
                i["code"]
                for i in inspect_fu_invocation(direct, sim / "config.ini")["issues"]
            ],
        )


class ElfIdentityTest(unittest.TestCase):
    def test_loaded_address_entry_bss_and_flags_are_part_of_identity(self):
        import salam_workbench.fu_experiments as module

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.elf"
            ident = b"\x7fELF\x01\x01\x01" + b"\0" * 9
            header = struct.pack(
                "<HHIIIIIHHHHHH",
                2,
                40,
                1,
                0x8000,
                52,
                0,
                0x5000000,
                52,
                32,
                1,
                0,
                0,
                0,
            )
            program = struct.pack("<IIIIIIII", 1, 84, 0x8000, 0x8000, 8, 16, 5, 4)
            original = ident + header + program + b"12345678"
            path.write_bytes(original)
            baseline = module._load_image_identity(path)["load_image_sha256"]
            for offset, value in (
                (24, 0x8004),
                (52 + 12, 0x9000),
                (52 + 20, 20),
                (36, 0x5000001),
            ):
                changed = bytearray(original)
                struct.pack_into("<I", changed, offset, value)
                path.write_bytes(changed)
                self.assertNotEqual(
                    baseline,
                    module._load_image_identity(path)["load_image_sha256"],
                )
            changed = bytearray(original)
            struct.pack_into("<H", changed, 16, 1)
            path.write_bytes(changed)
            with self.assertRaises(ValueError):
                module._load_image_identity(path)


if __name__ == "__main__":
    unittest.main()
