"""Source-bound staged repair for RegisterBank requestor port multiplicity.

The recovered parser ignores Ports and emits one register connection per
device, regardless of Connections counts. This adapter changes only the copied
parser used by the checked configuration pipeline. It does not alter the
RegisterBank SimObject or its memory semantics.
"""
import ast
import difflib
import hashlib
import json
from pathlib import Path

PARSER = Path("SALAM-Configurator/parser.py")
MARKER = "WORKBENCH_REGISTERBANK_PORTS_V1 = 1"
_VERSION = '__version__ = "3.0.0.pre[1.0.0]"'
_OLD_INIT = """        elif self.type == "RegisterBank":
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
"""
_NEW_INIT = """        elif self.type == "RegisterBank":
            self.connections = []
            # Read in register-bank args; preserve requested vector cardinality.
            self.name = kwargs.get("Name")
            self.accName = kwargs.get("AccName")
            self.size = kwargs.get("Size")
            self.address = kwargs.get("Address")
            self.ports = kwargs.get("Ports", 1)
            if type(self.ports) is not int or self.ports <= 0:
                raise ValueError("RegisterBank Ports must be a positive integer")
            self.connections.append(PortedConnection(self.accName, self.ports))
            if "Connections" in kwargs:
                for conDef in kwargs.get("Connections").split(","):
                    con, numPorts = conDef.strip().split(":")
                    if not numPorts.isdigit() or int(numPorts) <= 0:
                        raise ValueError("RegisterBank connection port count must be positive")
                    self.connections.append(PortedConnection(con, int(numPorts)))
"""
_OLD_CONNECTION = """            for con in self.connections:
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
"""
_NEW_CONNECTION = """            for con in self.connections:
                if type(con.numPorts) is not int or con.numPorts <= 0:
                    raise ValueError("RegisterBank connection port count must be a positive integer")
                lines.append("")
                lines.append("# Connecting " + self.name + " to " + con.conName)
                lines.append("for i in range(" + str(con.numPorts) + "):")
                lines.append(
                    "\\tclstr."
                    + con.conName.lower()
                    + ".reg = "
                    + "clstr."
                    + self.name.lower()
                    + ".reg_port"
                )
"""


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _persist(path, record):
    if path is not None:
        with Path(path).open("x", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")


def registerbank_ports_supported(workspace):
    path = Path(workspace) / PARSER
    if not path.is_file():
        return False
    source = path.read_text(encoding="utf-8")
    return (
        source.count(MARKER) == 1
        and source.count(_NEW_INIT) == 1
        and source.count(_NEW_CONNECTION) == 1
        and _OLD_INIT not in source
        and _OLD_CONNECTION not in source
    )


def registerbank_port_kind(workspace):
    """Read the actual SimObject declaration; generation cannot add C++ ports."""
    path = Path(workspace) / "src/hwacc/RegisterBank.py"
    if not path.is_file():
        return "unknown"
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.ClassDef) and node.name == "RegisterBank":
            for field in node.body:
                if (
                    isinstance(field, ast.Assign)
                    and any(
                        isinstance(target, ast.Name) and target.id == "reg_port"
                        for target in field.targets
                    )
                    and isinstance(field.value, ast.Call)
                    and isinstance(field.value.func, ast.Name)
                ):
                    if field.value.func.id == "ResponsePort":
                        return "scalar"
                    if field.value.func.id == "VectorResponsePort":
                        return "vector"
    return "unknown"


def adapt_configured_registerbanks(
    workspace, benchmark, *, source_engine=None, receipt_path=None
):
    import yaml

    documents = list(
        yaml.safe_load_all((Path(workspace) / benchmark / "config.yml").read_text())
    )
    required = any(
        variable.get("Type") == "RegisterBank"
        for document in documents
        for entry in document.get("acc_cluster", [])
        for record in entry.get("Accelerator", [])
        for variable in record.get("Var", [])
    )
    if not required:
        return {
            "state": "not_required",
            "scope": "No RegisterBank in this configuration",
        }
    return adapt_registerbank_ports(
        workspace, source_engine=source_engine, receipt_path=receipt_path
    )


def adapt_registerbank_ports(workspace, *, source_engine=None, receipt_path=None):
    """Repair the staged legacy parser and return its exact byte-change receipt.

    Apply after any ConfigPath adaptation and before contract validation and
    generation. A second call accepts only the intact known adaptation. Optional
    source_engine is recorded read-only and must be outside the staging tree.
    """
    if receipt_path is not None and Path(receipt_path).exists():
        raise FileExistsError("RegisterBank adapter receipt already exists")
    stage = Path(workspace).resolve(strict=True)
    parser = stage / PARSER
    if parser.resolve(strict=True) != parser or not parser.is_file():
        raise ValueError("Staged parser must be a regular, non-symlinked file")
    before_bytes = parser.read_bytes()
    record = {
        "schema_version": 1,
        "kind": "registerbank_ports_adapter",
        "state": "failed",
        "marker": MARKER,
        "staged_path": str(parser),
        "before_sha256": _sha(before_bytes),
        "after_sha256": None,
        "unified_diff": "",
        "scope": "RegisterBank requestor vector port counts only",
    }
    try:
        if source_engine is not None:
            source = Path(source_engine).resolve(strict=True)
            if stage == source or source in stage.parents or stage in source.parents:
                raise ValueError(
                    "RegisterBank adaptation requires an independent staged workspace"
                )
            source_parser = source / PARSER
            if (
                source_parser.resolve(strict=True) != source_parser
                or not source_parser.is_file()
            ):
                raise ValueError("Source parser must be a regular, non-symlinked file")
            record.update(
                source_path=str(source_parser),
                source_sha256=_sha(source_parser.read_bytes()),
            )
        before = before_bytes.decode("utf-8")
        newline = "\r\n" if "\r\n" in before else "\n"
        old_init, new_init = (
            _OLD_INIT.replace("\n", newline),
            _NEW_INIT.replace("\n", newline),
        )
        old_connection = _OLD_CONNECTION.replace("\n", newline)
        new_connection = _NEW_CONNECTION.replace("\n", newline)
        if before.count(_VERSION + newline) != 1:
            raise ValueError(
                "Unexpected parser version; refusing RegisterBank adaptation"
            )
        if MARKER in before:
            if (
                before.count(MARKER) != 1
                or before.count(new_init) != 1
                or before.count(new_connection) != 1
                or old_init in before
                or old_connection in before
            ):
                raise ValueError(
                    "Existing RegisterBank adaptation changed; refusing reuse"
                )
            after = before
            compile(after, str(parser), "exec")
            record["state"] = "already_patched"
        else:
            if before.count(old_init) != 1 or before.count(old_connection) != 1:
                raise ValueError(
                    "Parser anchors changed; refusing RegisterBank adaptation"
                )
            after = before.replace(
                _VERSION + newline, _VERSION + newline + MARKER + newline, 1
            )
            after = after.replace(old_init, new_init, 1)
            after = after.replace(old_connection, new_connection, 1)
            compile(after, str(parser), "exec")
            parser.write_bytes(after.encode("utf-8"))
            record["state"] = "patched"
        record["after_sha256"] = _sha(parser.read_bytes())
        record["unified_diff"] = "".join(
            difflib.unified_diff(
                before.splitlines(True),
                after.splitlines(True),
                fromfile="staged-before/SALAM-Configurator/parser.py",
                tofile="staged-after/SALAM-Configurator/parser.py",
            )
        )
        _persist(receipt_path, record)
        return record
    except Exception as error:
        record["state"] = "failed"
        record["error"] = str(error)
        _persist(receipt_path, record)
        raise
