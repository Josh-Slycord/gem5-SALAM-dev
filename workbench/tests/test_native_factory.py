# SPDX-License-Identifier: BSD-3-Clause
"""Graph and fail-closed checks; real simulation parity is a separate gate."""

import copy
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "tested_native_factory", ROOT / "configs/SALAM/native_factory.py"
)
FACTORY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FACTORY)


class Port:
    def __init__(self, owner, name):
        self.owner = owner
        self.name = name


class Node:
    PORTS = {
        "mem_side_ports",
        "cpu_side_ports",
        "pio",
        "dma",
        "cluster_dma",
        "local",
        "spm",
        "port",
        "spm_ports",
    }

    def __init__(self, **parameters):
        object.__setattr__(self, "assignments", [])
        object.__setattr__(self, "_ports", {})
        for key, value in parameters.items():
            setattr(self, key, value)

    def __getattr__(self, key):
        if key in self.PORTS:
            return self._ports.setdefault(key, Port(self, key))
        raise AttributeError(key)

    def __setattr__(self, key, value):
        if key in self.PORTS and isinstance(value, Port):
            self.assignments.append((key, value))
        else:
            object.__setattr__(self, key, value)


class AccCluster(Node):
    def __init__(self):
        super().__init__()
        self.local_bus = Node()
        self.coherency_bus = Node()

    def _connect_caches(self, system, options, l2coherent, cache_size=0):
        self.cache_call = (system, options, l2coherent, cache_size)
        self.coherency_bus.mem_side_ports = system.membus.cpu_side_ports


class IntegerMultiplier(Node):
    def __init__(self):
        super().__init__(limit=0, cycles=1, enum_value=2)


class Add(Node):
    def __init__(self):
        super().__init__(functional_unit=1, functional_unit_limit=0, opcode_num=13)


class Mul(Node):
    def __init__(self):
        super().__init__(functional_unit=2, functional_unit_limit=0, opcode_num=17)


def unused_yaml_reader(*args):
    raise AssertionError("Factory must not reload raw YAML or call AccConfig")


def runtime_modules(drop_fu_override=False):
    m5 = types.ModuleType("m5")
    objects = types.ModuleType("m5.objects")
    for name in (
        "NoncoherentDma",
        "CommInterface",
        "ScratchpadMemory",
    ):
        setattr(objects, name, type(name, (Node,), {}))
    objects.AccCluster = AccCluster
    objects.AddrRange = lambda start, end: (start, end)
    m5.objects = objects
    hardware = types.ModuleType("HWAccConfig")
    for name in (
        "LLVMInterface",
        "HWInterface",
        "CycleCounts",
        "SALAMPowerModel",
        "HWStatistics",
        "SimulatorConfig",
        "InstOpCodes",
    ):
        setattr(hardware, name, type(name, (Node,), {}))
    hardware._FU_REGISTRY = {"integer_multiplier": IntegerMultiplier}
    hardware._INST_REGISTRY = {"add": Add, "mul": Mul}
    hardware._CYCLE_COUNT_NAME_MAP = {}
    hardware._load_hw_config = unused_yaml_reader
    hardware.AccConfig = unused_yaml_reader

    def functional_units(acc, requested):
        acc.hw_interface.functional_units = Node()
        obj = IntegerMultiplier()
        if not drop_fu_override:
            for key, value in (
                requested.get("functional_units", {})
                .get("integer_multiplier", {})
                .items()
            ):
                setattr(obj, key, value)
        acc.hw_interface.functional_units.integer_multiplier = obj

    def instructions(acc, requested):
        acc.hw_interface.inst_config = Node()
        for name, cls in hardware._INST_REGISTRY.items():
            obj = cls()
            for key, value in requested.get("instructions", {}).get(name, {}).items():
                if key != "runtime_cycles":
                    setattr(obj, key, value)
            setattr(acc.hw_interface.inst_config, name, obj)

    def cycles(acc, requested):
        for name, values in requested.get("instructions", {}).items():
            if "runtime_cycles" in values:
                setattr(
                    acc.hw_interface.cycle_counts,
                    name,
                    values["runtime_cycles"],
                )

    hardware._instantiate_functional_units = functional_units
    hardware._instantiate_instructions = instructions
    hardware._apply_cycle_counts = cycles
    return {"m5": m5, "m5.objects": objects, "HWAccConfig": hardware}


def model():
    memory = {
        "name": "matrix1",
        "type": "SPM",
        "address": 0x100200C0,
        "range_end": 0x100280C0,
        "size": 32768,
        "ports": 2,
        "ready_mode": False,
        "reset_on_read": True,
        "read_on_invalid": False,
        "write_on_valid": True,
        "connections": [{"accelerator": "gemm", "ports": 2}],
    }
    common = {
        "requested_pio_size": 1,
        "pio_size": 64,
        "ir_path": "/fixture/hw/top.ll",
        "config_path": "/fixture/config.yml",
        "debug": False,
        "pio_masters": ["LocalBus"],
        "local_slaves": [],
        "interrupt_num": -1,
        "memories": [],
        "hardware": {},
    }
    top = dict(
        common,
        name="top",
        pio_addr=0x10020040,
        interrupt_num=68,
        local_slaves=["LocalBus"],
    )
    gemm = dict(
        common,
        name="gemm",
        pio_addr=0x10020080,
        ir_path="/fixture/hw/gemm.ll",
        memories=[memory],
        hardware={
            "functional_units": {"integer_multiplier": {"limit": 1}},
            "instructions": {
                "add": {
                    "functional_unit": 1,
                    "functional_unit_limit": 0,
                    "opcode_num": 13,
                    "runtime_cycles": 0,
                },
                "mul": {
                    "functional_unit": 2,
                    "functional_unit_limit": 0,
                    "opcode_num": 17,
                    "runtime_cycles": 4,
                },
            },
        },
    )
    return {
        "schema_version": 1,
        "engine_root": "/fixture",
        "base_address": 0x10020000,
        "clusters": [
            {
                "name": "gemm_clstr",
                "base_address": 0x10020000,
                "top_address": 0x10028100,
                "dmas": [
                    {
                        "name": "dma",
                        "type": "NonCoherent",
                        "pio_addr": 0x10020000,
                        "pio_size": 21,
                        "buffer_size": 128,
                        "max_req_size": 64,
                        "interrupt_num": 95,
                        "pio_masters": ["LocalBus"],
                    }
                ],
                "accelerators": [top, gemm],
            }
        ],
    }


class NativeFactoryTests(unittest.TestCase):
    def setUp(self):
        self.system = Node()
        self.system.iobus = Node()
        self.system.membus = Node()
        self.system.realview = types.SimpleNamespace(gic=Node())
        self.options = types.SimpleNamespace(acc_cache=False, l2cache=False)

    def build(self, value=None, **runtime_options):
        with patch.dict("sys.modules", runtime_modules(**runtime_options)):
            return FACTORY._build_clusters(
                self.options, self.system, model() if value is None else value
            )

    def test_graph_and_requests_reach_retained_typed_objects(self):
        result = self.build()
        cluster = self.system.gemm_clstr
        self.assertEqual(cluster.dma.pio_addr, 0x10020000)
        self.assertEqual(cluster.dma.buffer_size, 128)
        self.assertEqual(cluster.dma.max_req_size, 64)
        self.assertEqual(cluster.dma.int_num, 95)
        self.assertEqual(cluster.top.int_num, 68)
        self.assertEqual(cluster.gemm.int_num, -1)
        self.assertEqual(cluster.matrix1.range, (0x100200C0, 0x100280C0))
        self.assertEqual(len([a for a in cluster.gemm.assignments if a[0] == "spm"]), 2)
        self.assertIs(
            cluster.gemm.assignments[0][1],
            cluster.local_bus.mem_side_ports,
        )
        hw = cluster.gemm.hw_interface
        self.assertIsInstance(hw.functional_units.integer_multiplier, IntegerMultiplier)
        self.assertEqual(hw.functional_units.integer_multiplier.limit, 1)
        self.assertEqual(hw.cycle_counts.add, 0)
        self.assertEqual(hw.cycle_counts.mul, 4)
        self.assertEqual(hw.inst_config.mul.functional_unit_limit, 0)
        self.assertEqual(cluster.cache_call[2:], (False, 0))
        self.assertTrue(
            any(
                edge["to"].endswith(".matrix1.spm_ports") and edge["count"] == 2
                for edge in result["edges"]
            )
        )

    def test_factory_does_not_bind_native_domains_early(self):
        self.build()
        cluster = self.system.gemm_clstr
        self.assertNotIn("clk_domain", vars(cluster.top))
        self.assertNotIn("clk_domain", vars(cluster.top.llvm_interface))
        self.assertNotIn("clk_domain", vars(cluster.dma))

    def test_zero_fu_capacity_is_preserved_as_zero(self):
        data = model()
        data["clusters"][0]["accelerators"][1]["hardware"]["functional_units"][
            "integer_multiplier"
        ]["limit"] = 0
        self.build(data)
        self.assertEqual(
            self.system.gemm_clstr.gemm.hw_interface.functional_units.integer_multiplier.limit,
            0,
        )

    def test_nonzero_instruction_limit_rejected_before_system_mutation(self):
        data = model()
        data["clusters"][0]["accelerators"][1]["hardware"]["instructions"]["mul"][
            "functional_unit_limit"
        ] = 1
        with self.assertRaisesRegex(ValueError, "instruction FU cap"):
            self.build(data)
        self.assertFalse(hasattr(self.system, "gemm_clstr"))

    def test_silent_adapter_drop_cannot_be_reported_as_constructed(self):
        with self.assertRaisesRegex(ValueError, "override did not reach Params"):
            self.build(drop_fu_override=True)

    def test_unsupported_memory_is_rejected_before_system_mutation(self):
        data = model()
        data["clusters"][0]["accelerators"][1]["memories"][0]["type"] = "RegisterBank"
        with self.assertRaisesRegex(ValueError, "SPM memory only"):
            self.build(data)
        self.assertFalse(hasattr(self.system, "gemm_clstr"))

    def test_cluster_or_child_collision_cannot_overwrite_existing_objects(self):
        self.system.gemm_clstr = Node()
        existing = self.system.gemm_clstr
        with self.assertRaisesRegex(ValueError, "collides with system"):
            self.build()
        self.assertIs(self.system.gemm_clstr, existing)
        del self.system.gemm_clstr
        data = model()
        data["clusters"][0]["accelerators"][0]["name"] = "local_bus"
        with self.assertRaisesRegex(ValueError, "child name collision"):
            self.build(data)
        self.assertFalse(hasattr(self.system, "gemm_clstr"))

    def test_model_hash_is_deterministic_for_same_normalized_input(self):
        original = model()
        expected = FACTORY._canonical_json(original)
        self.assertEqual(FACTORY._canonical_json(copy.deepcopy(original)), expected)

    def test_factory_semantic_hash_matches_normalized_model_hash(self):
        with patch.object(sys, "path", [str(ROOT / "workbench"), *sys.path]):
            from salam_workbench.native_config import NormalizedConfiguration

        payload = model()
        normalized = NormalizedConfiguration(
            json.dumps(payload, sort_keys=True, separators=(",", ":"))
        )
        receipt = self.build(normalized)
        self.assertEqual(receipt["model_sha256"], normalized.sha256)


if __name__ == "__main__":
    unittest.main()
