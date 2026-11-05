"""Regressions for content-bound full-system template generation."""
import ast
import importlib.util
import keyword
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2]


class FullSystemTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ENGINE / "SALAM-Configurator/systembuilder.py"
        parsed = ast.parse(source.read_text())
        functions = [
            node
            for node in parsed.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "render_full_system_template"
        ]
        if len(functions) != 1:
            raise AssertionError("Expected one full-system template renderer")
        # The generator's module initializes CLI state on import. Execute only
        # this pure helper, preserving the actual source function under test.
        namespace = {"keyword": keyword}
        isolated = ast.Module(body=functions, type_ignores=[])
        exec(compile(isolated, str(source), "exec"), namespace)
        cls.render = staticmethod(namespace["render_full_system_template"])
        cls.template = (ENGINE / "SALAM-Configurator/fs_template.py").read_text()

    def assert_bound_template(self, text, name="fft"):
        rendered = self.render(text, name)
        parsed = ast.parse(rendered)
        compile(parsed, "generated-full-system.py", "exec")
        imports = [
            alias.name
            for node in ast.walk(parsed)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        calls = [
            node
            for node in ast.walk(parsed)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == name
            and node.func.attr == "makeHWAcc"
        ]
        self.assertEqual(imports.count(name), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            [ast.dump(argument) for argument in calls[0].args],
            [
                ast.dump(ast.parse(expression, mode="eval").body)
                for expression in ("args", "test_sys")
            ],
        )
        self.assertNotIn("TEMPLATE", imports)
        self.assertFalse(
            any(
                isinstance(node, ast.Name) and node.id == "TEMPLATE"
                for node in ast.walk(parsed)
            )
        )
        return rendered

    def test_actual_modern_template_has_bound_import_and_call(self):
        self.assert_bound_template(self.template)

    def test_template_length_changes_do_not_relocate_connections(self):
        prefix = "# Extra source line before the imports\n" * 300
        rendered = self.assert_bound_template(prefix + self.template, "gemm")
        self.assertTrue(rendered.startswith(prefix))
        baseline = self.assert_bound_template(self.template, "gemm")
        self.assertEqual(rendered[len(prefix) :], baseline)

    def test_call_indentation_and_line_endings_are_preserved(self):
        for indent, ending in (("        ", "\n"), ("\t\t", "\r\n")):
            with self.subTest(indent=repr(indent), ending=repr(ending)):
                text = ending.join(
                    (
                        "import TEMPLATE",
                        "def configure():",
                        indent[: len(indent) // 2] + "if True:",
                        indent + "TEMPLATE.makeHWAcc(args, test_sys)",
                        "",
                    )
                )
                rendered = self.assert_bound_template(text)
                self.assertIn(
                    indent + "fft.makeHWAcc(args, test_sys)" + ending, rendered
                )

    def test_missing_import_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.render(self.template.replace("import TEMPLATE\n", ""), "fft")

    def test_duplicate_import_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.render(self.template + "\nimport TEMPLATE\n", "fft")

    def test_missing_accelerator_call_is_rejected(self):
        text = self.template.replace("    TEMPLATE.makeHWAcc(args, test_sys)\n", "")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.render(text, "fft")

    def test_duplicate_accelerator_call_is_rejected(self):
        text = self.template + "\nTEMPLATE.makeHWAcc(args, test_sys)\n"
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.render(text, "fft")

    def test_path_like_module_name_is_rejected(self):
        with self.assertRaises(ValueError):
            self.render(self.template, "../escape")

    def test_dotted_module_name_is_rejected(self):
        with self.assertRaises(ValueError):
            self.render(self.template, "bad.name")

    def test_keyword_module_name_is_rejected(self):
        with self.assertRaises(ValueError):
            self.render(self.template, "for")

    def test_empty_module_name_is_rejected(self):
        with self.assertRaises(ValueError):
            self.render(self.template, "")

    def test_non_string_module_name_is_rejected(self):
        with self.assertRaises(ValueError):
            self.render(self.template, None)

    def test_parser_dma_optional_interrupt_and_int_port_counts(self):
        for rel in (
            "SALAM-Configurator/parser.py",
            "tools/SALAM-Configurator/config_parser.py",
        ):
            with self.subTest(rel=rel):
                path = ENGINE / rel
                spec = importlib.util.spec_from_file_location("cfg_parser", path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                dmas = [
                    {
                        "DMA": [
                            {
                                "Name": "dma0",
                                "Type": "NonCoherent",
                                "PIOMaster": "other,LocalBus",
                                "BufferSize": 128,
                                "MaxReqSize": 32,
                            }
                        ]
                    }
                ]
                accs = [
                    {
                        "Accelerator": [
                            {"Name": "top"},
                            {"PIOSize": 32},
                            {"IrPath": "hw/top.ll"},
                            {"PIOMaster": "LocalBus"},
                            {
                                "Var": [
                                    {
                                        "Name": "spm0",
                                        "Type": "SPM",
                                        "Size": 64,
                                        "Ports": 2,
                                        "Connections": "other:3",
                                    }
                                ]
                            },
                        ]
                    }
                ]
                cluster = mod.AccCluster(
                    "test_clstr", dmas, accs, 0x10020000, "/m5", "/m5/config.yml"
                )
                dma = cluster.dmas[0]
                self.assertIsNone(dma.int_num)
                self.assertEqual(dma.size, 128)
                self.assertEqual(dma.maxReq, 32)
                dma_lines = "\n".join(dma.genConfig())
                self.assertNotIn("int_num=None", dma_lines)
                self.assertIn("clstr.local_bus.mem_side_ports", dma_lines)
                spm = cluster.accs[0].variables[0]
                self.assertEqual(spm.connections[1].numPorts, 3)
                self.assertIsInstance(spm.connections[1].numPorts, int)


if __name__ == "__main__":
    unittest.main()
