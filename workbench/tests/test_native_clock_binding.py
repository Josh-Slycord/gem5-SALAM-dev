# SPDX-License-Identifier: BSD-3-Clause
"""Native domain binding preserves explicit SALAM periods and rejects no-ops."""
import ast
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

PROJECT = Path(__file__).resolve().parents[1]


def helper():
    source = PROJECT.parent / "configs/SALAM/HWAccConfig.py"
    tree = ast.parse(source.read_text())
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "configure_native_salam_clocks"
    )
    namespace = {"SrcClockDomain": lambda **kwargs: types.SimpleNamespace(**kwargs)}
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"),
        namespace,
    )
    return namespace["configure_native_salam_clocks"]


class NativeClockBindingTests(unittest.TestCase):
    def fixture(self):
        llvm = types.SimpleNamespace(
            type="LLVMInterface",
            clock_period=10,
            path=lambda: "system.cluster.acc.llvm_interface",
        )
        comm = types.SimpleNamespace(
            type="CommInterface", clock_period=10, path=lambda: "system.cluster.acc"
        )
        dma = types.SimpleNamespace(
            type="NoncoherentDma", clock_period=10, path=lambda: "system.cluster.dma"
        )
        root = types.SimpleNamespace(
            descendants=lambda: iter([llvm, comm, dma]),
            system=types.SimpleNamespace(voltage_domain=object()),
        )
        root.apply_config = Mock()
        return root, llvm, comm, dma

    def test_each_actor_uses_legacy_period_not_system_clock(self):
        root, llvm, comm, dma = self.fixture()
        llvm.clock_period, comm.clock_period, dma.clock_period = 3, 7, 11
        options = types.SimpleNamespace(param=[])
        result = helper()(root, options)
        self.assertEqual([item["clock_period_ns"] for item in result], [3, 7, 11])
        self.assertEqual(llvm.clk_domain.clock, "3ns")
        self.assertEqual(comm.clk_domain.clock, "7ns")
        self.assertEqual(dma.clk_domain.clock, "11ns")
        self.assertIs(llvm.clk_domain.voltage_domain, root.system.voltage_domain)

    def test_overrides_are_applied_before_binding_once(self):
        root, llvm, comm, dma = self.fixture()
        options = types.SimpleNamespace(
            param=["system.cluster.acc.llvm_interface.clock_period=5"]
        )
        root.apply_config.side_effect = lambda values: setattr(llvm, "clock_period", 5)
        helper()(root, options)
        root.apply_config.assert_called_once_with(
            ["system.cluster.acc.llvm_interface.clock_period=5"]
        )
        self.assertEqual(llvm.clk_domain.clock, "5ns")
        self.assertEqual(options.param, [])

    def test_domain_replacement_is_rejected_instead_of_silently_overwritten(self):
        root, *_ = self.fixture()
        options = types.SimpleNamespace(
            param=["system.cluster.acc.llvm_interface.clk_domain.clock='5ns'"]
        )
        with self.assertRaisesRegex(ValueError, "direct SALAM domain replacement"):
            helper()(root, options)
        root.apply_config.assert_not_called()

    def test_cpu_switching_is_explicitly_unqualified(self):
        root, *_ = self.fixture()
        with self.assertRaisesRegex(ValueError, "fixed CPU"):
            helper()(root, types.SimpleNamespace(param=[]), object())

    def test_invalid_periods_fail_before_simulation(self):
        for value in (0, -1, 1000001):
            with self.subTest(value=value):
                root, llvm, *_ = self.fixture()
                llvm.clock_period = value
                with self.assertRaisesRegex(ValueError, "clock_period"):
                    helper()(root, types.SimpleNamespace(param=[]))

    def test_no_salam_objects_leave_native_options_untouched(self):
        root = types.SimpleNamespace(descendants=lambda: iter([]), apply_config=Mock())
        options = types.SimpleNamespace(param=["system.cpu.numThreads=1"])
        self.assertEqual(helper()(root, options), [])
        self.assertEqual(options.param, ["system.cpu.numThreads=1"])
        root.apply_config.assert_not_called()
