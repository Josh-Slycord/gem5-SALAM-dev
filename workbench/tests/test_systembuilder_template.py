"""Regressions for content-bound full-system template generation."""
import ast
import importlib.util
import keyword
import logging
import tempfile
import types
import unittest
from pathlib import Path

import yaml

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

    def test_parser_dma_omitted_interrupt_and_int_port_counts(self):
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
                            {"PIOMaster": "other"},
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
                masters = getattr(dma, "pioMasters", getattr(dma, "pio_masters", None))
                self.assertEqual(masters, ["other", "local_bus"])
                accelerator_lines = "\n".join(cluster.accs[0].genConfig())
                self.assertIn("clstr.top.pio = clstr.other.local", accelerator_lines)
                with self.assertRaises(ValueError):
                    mod.Variable(
                        Name="bad_ports",
                        Type="SPM",
                        Size=64,
                        Address=0x1000,
                        AccName="top",
                        Connections="other:not_an_integer",
                    )
                dma_lines = "\n".join(dma.genConfig())
                self.assertNotIn("int_num=None", dma_lines)
                self.assertIn("clstr.local_bus.mem_side_ports", dma_lines)
                spm = cluster.accs[0].variables[0]
                self.assertEqual(spm.connections[1].numPorts, 3)
                self.assertIsInstance(spm.connections[1].numPorts, int)


def isolated_helpers(relative, names, namespace):
    source = ENGINE / relative
    tree = ast.parse(source.read_text())
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    if {node.name for node in functions} != set(names):
        raise AssertionError("Missing actual generator helpers: " + relative)
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"),
        namespace,
    )
    return namespace


class AdditionalConfigurationRegressions(unittest.TestCase):
    def test_both_renderers_preserve_simulation_hook_and_reject_broken_markers(
        self,
    ):
        template = (ENGINE / "SALAM-Configurator/fs_template.py").read_text()
        for relative in (
            "SALAM-Configurator/systembuilder.py",
            "tools/SALAM-Configurator/systembuilder.py",
        ):
            with self.subTest(relative=relative):
                render = isolated_helpers(
                    relative, ["render_full_system_template"], {"keyword": keyword}
                )["render_full_system_template"]
                actual = render("# shifted template\n" + template, "stencil")
                ast.parse(actual)
                self.assertIn(
                    "Simulation.run(args, root, test_sys, FutureClass)", actual
                )
                self.assertIn("stencil.makeHWAcc(args, test_sys)", actual)
                for malformed in (
                    template.replace("import TEMPLATE", "# missing import"),
                    template + "\nimport TEMPLATE\n",
                    template.replace(
                        "TEMPLATE.makeHWAcc(args, test_sys)", "# missing call"
                    ),
                ):
                    with self.assertRaisesRegex(ValueError, "exactly one"):
                        render(malformed, "stencil")

    def test_multi_cluster_headers_preserve_custom_sections_without_cross_contamination(
        self,
    ):
        for relative, load_name, generate_name in (
            (
                "SALAM-Configurator/systembuilder.py",
                "parseOriginalHeader",
                "genHeaderFiles",
            ),
            (
                "tools/SALAM-Configurator/systembuilder.py",
                "load_og_header",
                "gen_header",
            ),
        ):
            with self.subTest(
                relative=relative
            ), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                clusters = [
                    types.SimpleNamespace(name=name, dmas=[], accs=[])
                    for name in ("first", "second")
                ]
                for cluster in clusters:
                    (folder / (cluster.name + "_hw_defines.h")).write_text(
                        "// custom " + cluster.name + "\n"
                        "  //BEGIN GENERATED CODE  \n"
                        "#define OLD_ADDRESS 0xdead\n"
                        "  //END GENERATED CODE  \n"
                        "// retained footer\n"
                    )
                directory = str(folder) + "/"
                namespace = isolated_helpers(
                    relative,
                    [load_name, generate_name],
                    {
                        "workingDirectory": directory,
                        "HEADER_Path": directory,
                        "write_file": lambda path, content, label: Path(
                            path
                        ).write_text(content),
                    },
                )
                if relative.startswith("tools/"):
                    headers = namespace[load_name](clusters, directory)
                    namespace[generate_name](headers, clusters, directory)
                else:
                    headers = namespace[load_name](clusters)
                    namespace[generate_name](headers, clusters)
                for cluster, other in zip(clusters, reversed(clusters)):
                    content = (folder / (cluster.name + "_hw_defines.h")).read_text()
                    self.assertIn("// custom " + cluster.name, content)
                    self.assertIn("// retained footer", content)
                    self.assertIn("//Cluster: " + cluster.name.upper(), content)
                    self.assertNotIn(other.name.upper(), content)
                    self.assertNotIn("OLD_ADDRESS", content)
                    self.assertEqual(content.count("//BEGIN GENERATED CODE"), 1)

    def test_mobile_profiles_use_relative_path_parts_and_skip_empty_documents(self):
        load = isolated_helpers(
            "configs/SALAM/HWAccConfig.py",
            ["_load_hw_config"],
            {"yaml": yaml, "logger": logging.getLogger("profile-test")},
        )["_load_hw_config"]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.yml"
            path.write_text(
                "---\n---\nacc_cluster:\n  - Name: head\n"
                "hw_config:\n  head_NormalConv:\n    marker: head\n"
                "---\nacc_cluster:\n  - Name: body\n"
                "hw_config:\n  body_NormalConv:\n    marker: body\n"
            )
            for prefix in (Path("/a/short"), Path("/a/much/deeper/engine/root")):
                parts = (
                    prefix / "benchmarks/mobilenetv2/hw/ir/body/NormalConv.ll"
                ).parts
                result = load(path, "NormalConv", parts, len(prefix.parts))
                self.assertEqual(result, {"marker": "body"})
            missing = Path(
                "/engine/benchmarks/mobilenetv2/hw/ir/unknown/NormalConv.ll"
            ).parts
            self.assertIsNone(
                load(path, "NormalConv", missing, len(Path("/engine").parts))
            )
            # An engine directory named mobilenetv2 must not make an ordinary
            # benchmark use the multi-document profile route.
            path.write_text("hw_config:\n  gemm:\n    marker: standard\n")
            prefix = Path("/storage/mobilenetv2")
            parts = (prefix / "benchmarks/sys_validation/gemm/hw/gemm.ll").parts
            self.assertEqual(
                load(path, "gemm", parts, len(prefix.parts)), {"marker": "standard"}
            )


if __name__ == "__main__":
    unittest.main()
