# SPDX-License-Identifier: BSD-3-Clause
"""Native domain binding preserves explicit SALAM periods and rejects no-ops."""
import ast
import builtins
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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
        for mode in ("future_cpu", "standard_switch", "repeat_switch"):
            with self.subTest(mode=mode):
                root, *_ = self.fixture()
                options = types.SimpleNamespace(param=[])
                future = object() if mode == "future_cpu" else None
                if mode != "future_cpu":
                    setattr(options, mode, 100)
                with self.assertRaisesRegex(ValueError, "fixed CPU"):
                    helper()(root, options, future)
                root.apply_config.assert_not_called()

    def test_dual_root_is_explicitly_unqualified(self):
        root, *_ = self.fixture()
        del root.system
        with self.assertRaisesRegex(ValueError, "single-system root"):
            helper()(root, types.SimpleNamespace(param=[]))
        root.apply_config.assert_not_called()

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


def real_cli_fixture(include_salam=True):
    """Use gem5's actual CLI wrapper/application code without C++ objects."""
    source = PROJECT.parent / "src/python/m5/SimObject.py"
    tree = ast.parse(source.read_text())
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name in ("SimObjectCliWrapperException", "SimObjectCliWrapper")
    ]
    simobject = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SimObject"
    )
    selected.extend(
        node
        for node in simobject.body
        if isinstance(node, ast.FunctionDef)
        and node.name in ("_apply_config_get_dict", "apply_config")
    )
    namespace = {}
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), str(source), "exec"),
        namespace,
    )

    class Node:
        def __init__(self, path, kind, children=None, **params):
            self.type = kind
            self._path = path
            self._children = children or {}
            self._params = {
                key: types.SimpleNamespace(isCmdLineSettable=lambda: True)
                for key in params
            }
            for key, value in params.items():
                setattr(self, key, value)

        def path(self):
            return self._path

        def __iter__(self):
            yield self

        def __getitem__(self, index):
            if index != 0:
                raise IndexError(index)
            return self

        def descendants(self):
            yield self
            for child in self._children.values():
                yield from child.descendants()

    llvm = Node("system.cluster.acc.llvm_interface", "LLVMInterface", clock_period=10)
    acc = Node(
        "system.cluster.acc", "CommInterface", {"llvm_interface": llvm}, clock_period=10
    )
    cluster = Node("system.cluster", "AccCluster", {"acc": acc})
    cpu = Node("system.cpu0", "AtomicSimpleCPU", max_insts_any_thread=0)
    children = {"cpu": cpu}
    if include_salam:
        children["cluster"] = cluster
    system = Node("system", "System", children)
    system.voltage_domain = object()
    root = Node("root", "Root", {"system": system})
    root.system = system
    root._apply_config_get_dict = types.MethodType(
        namespace["_apply_config_get_dict"], root
    )
    calls = []

    def apply_config(params):
        calls.append(list(params))
        namespace["apply_config"](root, params)

    root.apply_config = apply_config
    return root, llvm, cpu, calls


def final_boundary():
    source = PROJECT.parent / "configs/common/Simulation.py"
    tree = ast.parse(source.read_text())
    run = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    instantiate = next(
        index
        for index, node in enumerate(run.body)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "m5"
        and node.value.func.attr == "instantiate"
    )
    boundary = run.body[instantiate - 1]
    if not isinstance(
        boundary, ast.If
    ) or "configure_native_salam_clocks" not in ast.dump(boundary):
        raise AssertionError(
            "Native clocks must bind at the final configuration boundary immediately before instantiate"
        )
    return compile(ast.Module(body=[boundary], type_ignores=[]), str(source), "exec")


class FinalClockBoundaryTests(unittest.TestCase):
    def test_final_binding_preserves_real_cli_scalar_priority(self):
        root, llvm, cpu, calls = real_cli_fixture()
        parameters = [
            "system.cpu[0].max_insts_any_thread=7",
            "system.cluster.acc.llvm_interface.clock_period=5",
        ]
        options = types.SimpleNamespace(param=list(parameters), maxinsts=100)
        # Simulation.run performs its ordinary option-derived CPU writes first.
        cpu.max_insts_any_thread = options.maxinsts
        package = types.ModuleType("SALAM")
        package.__path__ = []
        module = types.ModuleType("SALAM.HWAccConfig")
        module.configure_native_salam_clocks = helper()
        with patch.dict(sys.modules, {"SALAM": package, "SALAM.HWAccConfig": module}):
            exec(
                final_boundary(), {"root": root, "options": options, "cpu_class": None}
            )
        self.assertEqual(cpu.max_insts_any_thread, 7)
        self.assertEqual(llvm.clock_period, 5)
        self.assertEqual(llvm.clk_domain.clock, "5ns")
        self.assertEqual(calls, [parameters])
        self.assertEqual(options.param, [])

    def test_non_salam_run_uses_normal_final_apply_without_import(self):
        root, _, cpu, calls = real_cli_fixture(include_salam=False)
        parameters = ["system.cpu[0].max_insts_any_thread=9"]
        options = types.SimpleNamespace(param=list(parameters))
        with patch.object(builtins, "__import__", wraps=builtins.__import__) as imports:
            exec(
                final_boundary(), {"root": root, "options": options, "cpu_class": None}
            )
        self.assertFalse(
            any(
                call.args and call.args[0].startswith("SALAM")
                for call in imports.call_args_list
            )
        )
        self.assertEqual(cpu.max_insts_any_thread, 9)
        self.assertEqual(calls, [parameters])
        self.assertEqual(options.param, parameters)

    def test_generated_templates_do_not_consume_overrides_early(self):
        for relative in (
            "SALAM-Configurator/fs_template.py",
            "tools/SALAM-Configurator/fs_template.py",
        ):
            with self.subTest(relative=relative):
                tree = ast.parse((PROJECT.parent / relative).read_text())
                self.assertFalse(
                    any(
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "configure_native_salam_clocks"
                        for node in ast.walk(tree)
                    )
                )
