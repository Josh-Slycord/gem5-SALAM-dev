"""Execute repaired generated connections without gem5 or a simulator build."""
import hashlib
import importlib.util
import json
import runpy
import tempfile
import types
import unittest
from pathlib import Path

from salam_workbench.registerbank_adapter import (
    MARKER, adapt_registerbank_ports, registerbank_port_kind,
)


# Minimal unchanged legacy parser sections. The tests execute the generated
# connections into synthetic vector-port stubs; these do not establish that
# the compiled RegisterBank has vector ports. Contract tests below separately
# enforce the actual declared scalar/vector port shape.
PARSER_SOURCE = '''__version__ = "3.0.0.pre[1.0.0]"

class PortedConnection:
    def __init__(self, conName, numPorts):
        self.conName = conName
        self.numPorts = numPorts

class Variable:
    def __init__(self, **kwargs):
        self.type = kwargs.get("Type")
        if self.type == "SPM":
            pass
        elif self.type == "RegisterBank":
            self.connections = []
            # Read in SPM args
            self.name = kwargs.get("Name")
            self.accName = kwargs.get("AccName")
            self.size = kwargs.get("Size")
            self.address = kwargs.get("Address")
            # Append the default connection here... probably need to be more elegant
            self.connections.append(PortedConnection(self.accName, 1))
            # Append other connections to the connections list
            if "Connections" in kwargs:
                for conDef in kwargs.get("Connections").split(","):
                    con, numPorts = conDef.split(":")
                    self.connections.append(PortedConnection(con, numPorts))
        elif self.type == "Cache":
            pass

    def genConfig(self, lines):
        if self.type == "SPM":
            pass
        elif self.type == "RegisterBank":
            lines.append("# " + self.name + " (Variable)")
            lines.append("addr = " + hex(self.address))
            lines.append("regRange = AddrRange(addr, addr + " + hex(self.size) + ")")
            # When appending convert all connections to lowercase for standardization
            lines.append(
                "clstr." + self.name.lower() + " = RegisterBank(range = regRange)"
            )
            lines.append(
                "clstr."
                + self.name.lower()
                + "."
                + "load_port"
                + " = "
                + "clstr.local_bus.mem_side_ports"
            )
            for con in self.connections:
                lines.append("")
                lines.append("# Connecting " + self.name + " to " + con.conName)
                lines.append(
                    "clstr."
                    + con.conName.lower()
                    + ".reg = "
                    + "clstr."
                    + self.name.lower()
                    + ".reg_port"
                )
        elif self.type == "Cache":
            pass
        return lines
'''


class _Requestor:
    def __init__(self):
        self.peers = []

    @property
    def reg(self):
        return self.peers

    @reg.setter
    def reg(self, value):
        self.peers.append(value)


class _Memory:
    def __init__(self, range):
        self.range = range
        self.reg_port = object()


class RegisterBankAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.stage = self.root / "engine", self.root / "stage"
        for root in (self.source, self.stage):
            parser = root / "SALAM-Configurator/parser.py"
            parser.parent.mkdir(parents=True)
            parser.write_text(PARSER_SOURCE, encoding="utf-8")
        self.parser = self.stage / "SALAM-Configurator/parser.py"

    def variable(self, **kwargs):
        defaults = dict(Type="RegisterBank", Name="Coefficients", AccName="Compute",
                        Size=64, Address=0x10000)
        defaults.update(kwargs)
        return runpy.run_path(str(self.parser))["Variable"](**defaults)

    def execute(self, variable):
        clstr = types.SimpleNamespace(compute=_Requestor(), reader=_Requestor(),
                                      other=_Requestor(),
                                      local_bus=types.SimpleNamespace(mem_side_ports=object()))
        lines = variable.genConfig([])
        code = "\n".join(lines)
        exec(compile(code, "generated-register-bank", "exec"),
             {"clstr": clstr, "RegisterBank": _Memory,
              "AddrRange": lambda start, end: (start, end)})
        return clstr, code

    def contract_for_registerbank(self, *, ports, connections=None,
                                  port_kind="ResponsePort"):
        fixture_path = Path(__file__).with_name("test_config_contract.py")
        spec = importlib.util.spec_from_file_location("_register_contract_fixture", fixture_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fixture = module.ConfigContractTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture._write(fixture.root / "SALAM-Configurator/parser.py", PARSER_SOURCE)
        adapt_registerbank_ports(fixture.root)
        fixture._write(fixture.root / "src/hwacc/RegisterBank.py",
                       "class RegisterBank:\n    reg_port = {}('private register port')\n".format(port_kind))
        replacement = ("            Type: RegisterBank\n            Size: 128\n"
                       "            Ports: {}".format(ports))
        if connections is not None:
            replacement += "\n            Connections: " + connections
        fixture._write(fixture.config, module.YAML.replace(
            "            Type: SPM\n            Size: 128\n            Ports: 2\n            ReadyMode: true",
            replacement,
        ))
        return fixture.analyze()

    def test_port_kind_reads_scalar_vector_and_unknown_declarations_without_execution(self):
        path = self.stage / "src/hwacc/RegisterBank.py"
        path.parent.mkdir(parents=True)
        self.assertEqual(registerbank_port_kind(self.stage), "unknown")
        declarations = (
            ("class RegisterBank:\n    reg_port = ResponsePort('register port')\n", "scalar"),
            ("class RegisterBank:\n    reg_port = VectorResponsePort('register ports')\n", "vector"),
            ("class Other:\n    reg_port = ResponsePort('unrelated')\n", "unknown"),
            ("class RegisterBank:\n    reg_port = UnrecognizedPort('unknown')\n", "unknown"),
            ("raise RuntimeError('must not execute')\nclass RegisterBank:\n    reg_port = ResponsePort('register port')\n", "scalar"),
        )
        for source, expected in declarations:
            with self.subTest(expected=expected, source=source):
                path.write_text(source, encoding="utf-8")
                self.assertEqual(registerbank_port_kind(self.stage), expected)

    def test_structural_contract_rejects_two_private_peers_for_declared_scalar_port(self):
        result = self.contract_for_registerbank(ports=2)
        self.assertFalse(result["valid"])
        self.assertIn("scalar_register_port_limit", {issue["code"] for issue in result["issues"]})

    def test_structural_contract_accepts_one_scalar_private_peer_and_witnesses_its_index(self):
        result = self.contract_for_registerbank(ports=1)
        self.assertTrue(result["valid"], result["issues"])
        self.assertEqual(result["expected_effective"]["system.demo_clstr.data"]["reg_port"],
                         "system.demo_clstr.demo.reg[0]")

    def test_structural_contract_sums_default_and_extra_peers_for_scalar_limit(self):
        result = self.contract_for_registerbank(ports=1, connections="TOP:1")
        self.assertFalse(result["valid"])
        self.assertIn("scalar_register_port_limit", {issue["code"] for issue in result["issues"]})

    def test_structural_contract_does_not_infer_multiport_support_from_unknown_descriptor(self):
        result = self.contract_for_registerbank(ports=1, port_kind="UnknownPort")
        self.assertFalse(result["valid"])
        self.assertIn("unknown_register_port", {issue["code"] for issue in result["issues"]})

    def test_default_port_and_source_bytes_preserved_with_hash_receipt(self):
        source_parser = self.source / "SALAM-Configurator/parser.py"
        original = source_parser.read_bytes()
        receipt = self.root / "adapter.json"
        result = adapt_registerbank_ports(self.stage, source_engine=self.source,
                                         receipt_path=receipt)
        self.assertEqual(result["state"], "patched")
        self.assertEqual(source_parser.read_bytes(), original)
        self.assertEqual(result["before_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(result["after_sha256"], hashlib.sha256(self.parser.read_bytes()).hexdigest())
        self.assertEqual(json.loads(receipt.read_text())["after_sha256"], result["after_sha256"])
        self.assertIn("PortedConnection(self.accName, self.ports)", result["unified_diff"])
        clstr, _ = self.execute(self.variable())
        self.assertEqual(len(clstr.compute.peers), 1)

    def test_requested_default_two_and_additional_three_ports_reach_generated_graph(self):
        adapt_registerbank_ports(self.stage)
        clstr, code = self.execute(self.variable(Ports=2, Connections="Reader:3,Other:2"))
        self.assertEqual(len(clstr.compute.peers), 2)
        self.assertEqual(len(clstr.reader.peers), 3)
        self.assertEqual(len(clstr.other.peers), 2)
        self.assertTrue(all(peer is clstr.coefficients.reg_port
                            for peer in clstr.compute.peers + clstr.reader.peers + clstr.other.peers))
        self.assertIs(clstr.coefficients.load_port, clstr.local_bus.mem_side_ports)
        self.assertIn("for i in range(3):", code)

    def test_multiple_banks_accumulate_target_vector_indices_in_generation_order(self):
        adapt_registerbank_ports(self.stage)
        first = self.variable(Name="First", Ports=2, Connections="Reader:3")
        second = self.variable(Name="Second", AccName="Reader", Ports=1,
                               Connections="COMPUTE:2,reader:2")
        clstr = types.SimpleNamespace(compute=_Requestor(), reader=_Requestor(),
                                      local_bus=types.SimpleNamespace(mem_side_ports=object()))
        lines = first.genConfig([])
        lines = second.genConfig(lines)
        exec(compile("\n".join(lines), "generated-multiple-register-banks", "exec"),
             {"clstr": clstr, "RegisterBank": _Memory,
              "AddrRange": lambda start, end: (start, end)})
        self.assertEqual(clstr.compute.peers,
                         [clstr.first.reg_port] * 2 + [clstr.second.reg_port] * 2)
        self.assertEqual(clstr.reader.peers,
                         [clstr.first.reg_port] * 3 + [clstr.second.reg_port] * 3)

    def test_zero_negative_boolean_and_string_ports_rejected(self):
        adapt_registerbank_ports(self.stage)
        for value in (0, -1, True, False, "2", 1.5, None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    self.variable(Ports=value)

    def test_bad_additional_counts_rejected(self):
        adapt_registerbank_ports(self.stage)
        for value in ("Reader:0", "Reader:-2", "Reader:True", "Reader:1.5", "Reader:"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.variable(Connections=value)

    def test_mutated_runtime_connection_count_rejected_before_generation(self):
        adapt_registerbank_ports(self.stage)
        variable = self.variable(Ports=2)
        variable.connections[0].numPorts = True
        with self.assertRaisesRegex(ValueError, "positive integer"):
            variable.genConfig([])

    def test_existing_configpath_adaptation_is_preserved(self):
        helper = '\nCONFIGPATH_CONSUMER_VERSION = 1\n\ndef _workbench_config_path(root, raw):\n    return raw\n'
        original = self.parser.read_text()
        self.parser.write_text(original.replace(_VERSION_LINE, _VERSION_LINE + helper), encoding="utf-8")
        adapt_registerbank_ports(self.stage)
        self.assertIn(helper, self.parser.read_text())
        self.assertEqual(runpy.run_path(str(self.parser))["_workbench_config_path"]("a", "b"), "b")

    def test_intact_second_application_is_idempotent(self):
        adapt_registerbank_ports(self.stage)
        first = self.parser.read_bytes()
        result = adapt_registerbank_ports(self.stage)
        self.assertEqual(result["state"], "already_patched")
        self.assertEqual(result["unified_diff"], "")
        self.assertEqual(self.parser.read_bytes(), first)

    def test_changed_anchor_and_spoofed_marker_fail_closed(self):
        original = self.parser.read_text()
        for changed in (original.replace("self.accName, 1", "self.accName, 2"),
                        original + "\n" + MARKER + "\n",
                        original.replace('3.0.0.pre[1.0.0]', '4.0.0')):
            self.parser.write_text(changed, encoding="utf-8")
            before = self.parser.read_bytes()
            with self.assertRaises(ValueError):
                adapt_registerbank_ports(self.stage)
            self.assertEqual(before, self.parser.read_bytes())

    def test_changed_patched_block_is_not_silently_reused(self):
        adapt_registerbank_ports(self.stage)
        changed = self.parser.read_text().replace("PortedConnection(self.accName, self.ports)",
                                                "PortedConnection(self.accName, 1)")
        self.parser.write_text(changed, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "adaptation changed"):
            adapt_registerbank_ports(self.stage)

    def test_source_workspace_cannot_be_patched(self):
        before = self.parser.read_bytes()
        with self.assertRaisesRegex(ValueError, "independent staged"):
            adapt_registerbank_ports(self.stage, source_engine=self.stage)
        self.assertEqual(before, self.parser.read_bytes())

    def test_failed_receipt_retains_before_hash_and_error(self):
        self.parser.write_text("unknown parser", encoding="utf-8")
        receipt = self.root / "failed.json"
        with self.assertRaises(ValueError):
            adapt_registerbank_ports(self.stage, receipt_path=receipt)
        record = json.loads(receipt.read_text())
        self.assertEqual(record["state"], "failed")
        self.assertIsNone(record["after_sha256"])
        self.assertIn("version", record["error"])

    def test_crlf_parser_keeps_its_newline_convention(self):
        self.parser.write_bytes(PARSER_SOURCE.replace("\n", "\r\n").encode("utf-8"))
        adapt_registerbank_ports(self.stage)
        raw = self.parser.read_bytes()
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        clstr, _ = self.execute(self.variable(Ports=3))
        self.assertEqual(len(clstr.compute.peers), 3)


_VERSION_LINE = '__version__ = "3.0.0.pre[1.0.0]"\n'


if __name__ == "__main__":
    unittest.main()
