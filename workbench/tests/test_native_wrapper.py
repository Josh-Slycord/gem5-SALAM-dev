# SPDX-License-Identifier: BSD-3-Clause
"""Native wrapper contract and maintained-template transformation controls."""
import argparse
import ast
import contextlib
import hashlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from salam_workbench.native_config import normalize_configuration
from salam_workbench.native_wrapper import WrapperTemplateError, render_wrapper

REPO = Path(__file__).resolve().parents[2]
ABI_FILES = (
    "configs/SALAM/HWAccConfig.py",
    "src/hwacc/FunctionalUnits.py",
    "src/hwacc/InstConfig.py",
    "src/hwacc/CycleCounts.py",
    "src/hwacc/CommInterface.py",
    "src/hwacc/NoncoherentDma.py",
)
GEMM = "benchmarks/sys_validation/gemm/config.yml"
TEMPLATE = (REPO / "SALAM-Configurator/fs_template.py").read_text()


class NativeWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="native-wrapper-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for relative in ABI_FILES + (GEMM,):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, destination)
        self.config = self.root / GEMM
        for name in ("top", "gemm"):
            destination = self.config.parent / "hw" / (name + ".ll")
            destination.parent.mkdir(exist_ok=True)
            destination.write_text("define void @{}() {{ ret void }}\n".format(name))
        self.model = normalize_configuration(self.config, self.root)
        self.sidecar = self.root / "configs/SALAM/generated/native_fixture.json"

    def render(self, template=TEMPLATE, model=None, model_path=None):
        return render_wrapper(
            self.model if model is None else model,
            template,
            model_path=self.sidecar if model_path is None else model_path,
        )

    def runtime_namespace(self, rendered):
        tree = ast.parse(rendered.text)
        nodes = []
        for node in tree.body:
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "pathlib"
                and any(item.asname == "_SalamNativePath" for item in node.names)
            ):
                nodes.append(node)
            elif isinstance(node, ast.Assign) and any(
                isinstance(item, ast.Name) and item.id.startswith("_SALAM_NATIVE_")
                for item in node.targets
            ):
                nodes.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name in (
                "_salam_native_contract_guard",
                "addHWAccOptions",
            ):
                nodes.append(node)
        namespace = {}
        exec(
            compile(ast.Module(body=nodes, type_ignores=[]), "<guard-only>", "exec"),
            namespace,
        )
        return namespace

    def test_full_inherited_license_and_unmodified_board_functions_preserved(self):
        result = self.render()
        tree = ast.parse(TEMPLATE)
        prefix = "".join(TEMPLATE.splitlines(keepends=True)[: tree.body[0].lineno - 1])
        self.assertTrue(result.text.startswith(prefix))
        self.assertEqual(
            result.provenance["inherited_license_prefix_sha256"],
            hashlib.sha256(prefix.encode()).hexdigest(),
        )
        original = {
            node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        generated = {
            node.name: node
            for node in ast.parse(result.text).body
            if isinstance(node, ast.FunctionDef)
        }
        for name in set(original) - {"addHWAccOptions", "build_test_system"}:
            self.assertEqual(
                ast.dump(original[name], include_attributes=False),
                ast.dump(generated[name], include_attributes=False),
            )
            segment = ast.get_source_segment(TEMPLATE, original[name])
            self.assertIn(segment, result.text)
        self.assertIn("Simulation.run(args, root, test_sys, FutureClass)", result.text)

    def test_fixed_native_call_has_all_snapshot_contract_keywords(self):
        result = self.render()
        self.assertNotIn("TEMPLATE", result.text)
        tree = ast.parse(result.text)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "make_native_hwacc"
        ]
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            {item.arg for item in calls[0].keywords},
            {"expected_model_path", "expected_model_sha256", "expected_layout_sha256"},
        )
        self.assertFalse(result.provenance["legacy_systembuilder_executed"])
        self.assertFalse(result.provenance["generated_topology_module_imported"])
        self.assertEqual(result.provenance["model_sha256"], self.model.sha256)
        self.assertEqual(result.provenance["layout_sha256"], self.model.layout_sha256)

    def test_native_defaults_and_identity_guard_bind_config_and_base(self):
        namespace = self.runtime_namespace(self.render())
        parser = argparse.ArgumentParser()
        namespace["addHWAccOptions"](parser)
        options = parser.parse_args([])
        namespace["_salam_native_contract_guard"](options)
        self.assertEqual(options.salam_builder, "native")
        self.assertEqual(options.salam_config, str(self.config))
        self.assertEqual(
            options.salam_base_address, self.model.to_dict()["base_address"]
        )

    def test_cli_cannot_select_generated_route_or_different_config_or_base(self):
        namespace = self.runtime_namespace(self.render())
        parser = argparse.ArgumentParser()
        namespace["addHWAccOptions"](parser)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["--salam-builder=generated"])
        for options in (
            ["--salam-config=" + str(self.root / "different.yml")],
            ["--salam-base-address=0x10024000"],
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                namespace["_salam_native_contract_guard"](parser.parse_args(options))
        value = parser.parse_args([])
        value.salam_builder = "generated"
        with self.assertRaises(ValueError):
            namespace["_salam_native_contract_guard"](value)

    def test_guard_runs_immediately_after_parse_and_before_system_setup(self):
        tree = ast.parse(self.render().text)
        parsed = next(
            index
            for index, node in enumerate(tree.body)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "parse_args"
        )
        guard = tree.body[parsed + 1]
        self.assertIsInstance(guard, ast.Expr)
        self.assertEqual(guard.value.func.id, "_salam_native_contract_guard")
        self.assertGreater(
            next(
                index
                for index, node in enumerate(tree.body)
                if isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "build_test_system"
            ),
            parsed + 1,
        )

    def test_same_model_and_template_have_deterministic_text_and_identity(self):
        first, second = self.render(), self.render()
        self.assertEqual(first, second)
        self.assertEqual(
            first.provenance["wrapper_sha256"],
            hashlib.sha256(first.text.encode()).hexdigest(),
        )
        self.assertEqual(
            first.provenance["template_sha256"],
            hashlib.sha256(TEMPLATE.encode()).hexdigest(),
        )

    def test_new_layout_changes_wrapper_and_fixed_addresses(self):
        model = normalize_configuration(self.config, self.root, base_address=0x10024000)
        original, changed = self.render(), self.render(model=model)
        self.assertNotEqual(original.text, changed.text)
        self.assertNotEqual(
            original.provenance["layout_sha256"], changed.provenance["layout_sha256"]
        )
        namespace = self.runtime_namespace(changed)
        parser = argparse.ArgumentParser()
        namespace["addHWAccOptions"](parser)
        self.assertEqual(parser.parse_args([]).salam_base_address, 0x10024000)

    def test_provisional_ir_model_is_not_a_runnable_wrapper(self):
        (self.config.parent / "hw/top.ll").rename(self.config.parent / "hw/top.unbuilt")
        provisional = normalize_configuration(self.config, self.root, require_ir=False)
        with self.assertRaisesRegex(ValueError, "final strict IR"):
            self.render(model=provisional)

    def test_source_paths_cannot_escape_workspace(self):
        with self.assertRaisesRegex(ValueError, "leaves workspace"):
            self.render(model_path=self.root.parent / "unrelated.json")
        with self.assertRaisesRegex(ValueError, "JSON path"):
            self.render(model_path=self.sidecar.with_suffix(".py"))
        with self.assertRaises(TypeError):
            self.render(model=self.model.to_dict())

    def test_snapshot_path_quotes_are_literal_data(self):
        path = self.sidecar.with_name('native "quote\'s".json')
        rendered = self.render(model_path=path)
        namespace = self.runtime_namespace(rendered)
        self.assertEqual(namespace["_SALAM_NATIVE_MODEL_PATH"], str(path))
        compile(rendered.text, "<quoted-path>", "exec")

    def test_missing_or_duplicate_dispatch_is_rejected(self):
        old = '    if args.salam_builder == "native":'
        tree = ast.parse(TEMPLATE)
        dispatch = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Attribute)
            and node.test.left.attr == "salam_builder"
        )
        block = "".join(
            TEMPLATE.splitlines(keepends=True)[
                dispatch.lineno - 1 : dispatch.end_lineno
            ]
        )
        for template in (
            TEMPLATE.replace(old, '    if args.salam_builder == "other":', 1),
            TEMPLATE.replace(block, block + block, 1),
        ):
            ast.parse(template)
            with self.subTest(template=template[-150:]), self.assertRaises(
                WrapperTemplateError
            ):
                self.render(template)

    def test_unreviewed_logic_inside_dispatch_is_not_silently_dropped(self):
        template = TEMPLATE.replace(
            "        make_native_hwacc(args, test_sys)",
            "        mutate_unreviewed_state()\n        make_native_hwacc(args, test_sys)",
            1,
        )
        with self.assertRaisesRegex(WrapperTemplateError, "unreviewed logic"):
            self.render(template)

    def test_missing_duplicate_or_redeclared_managed_options_rejected(self):
        for template in (
            TEMPLATE.replace('"--salam-config"', '"--different-config"', 1),
            TEMPLATE.replace(
                '    parser.add_argument("--acc_cache", action="store_true")',
                '    parser.add_argument("--acc_cache", action="store_true")\n'
                '    parser.add_argument("--salam-config", "--alias")',
                1,
            ),
            TEMPLATE.replace('default="generated"', 'default="native"', 1),
        ):
            with self.subTest(template=template[:30]), self.assertRaises(
                WrapperTemplateError
            ):
                self.render(template)

    def test_helper_name_collisions_do_not_override_the_runtime_guard(self):
        for suffix in (
            "\n_SALAM_NATIVE_BASE_ADDRESS = 1\n",
            "\ndef _salam_native_contract_guard(options):\n    pass\n",
            "\nfrom pathlib import Path as _SalamNativePath\n",
        ):
            with self.subTest(suffix=suffix), self.assertRaisesRegex(
                WrapperTemplateError, "collides"
            ):
                self.render(TEMPLATE + suffix)

    def test_adjacent_statement_on_anchor_line_is_not_discarded(self):
        template = TEMPLATE.replace(
            "args = parser.parse_args()",
            "args = parser.parse_args(); unexpected_side_effect()",
            1,
        )
        with self.assertRaisesRegex(WrapperTemplateError, "shares a line"):
            self.render(template)

    def test_missing_license_and_non_lf_source_are_rejected(self):
        for template in (
            TEMPLATE[TEMPLATE.index("__version__") :],
            TEMPLATE.replace("\n", "\r\n"),
            TEMPLATE.rstrip("\n"),
        ):
            with self.subTest(template=template[:30]), self.assertRaises(
                WrapperTemplateError
            ):
                self.render(template)


if __name__ == "__main__":
    unittest.main()
