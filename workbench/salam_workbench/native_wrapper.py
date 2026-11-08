# SPDX-License-Identifier: BSD-3-Clause
"""Render a native-only board wrapper from a normalized final model.

Only strictly identified AST statement spans change in the maintained text
template. Its inherited license and other board setup bytes stay intact.
This module imports no gem5 code, runs no generator and writes no files.
"""
import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .native_config import NormalizedConfiguration

_SHA256 = re.compile(r"[0-9a-f]{64}")
_DISPATCH = """\
if args.salam_builder == "native":
    from native_factory import makeHWAcc as make_native_hwacc

    make_native_hwacc(args, test_sys)
else:
    import TEMPLATE

    TEMPLATE.makeHWAcc(args, test_sys)
"""
_RESERVED = {
    "_SalamNativePath",
    "_salam_native_contract_guard",
    "_SALAM_NATIVE_CONFIG_PATH",
    "_SALAM_NATIVE_BASE_ADDRESS",
    "_SALAM_NATIVE_MODEL_PATH",
    "_SALAM_NATIVE_MODEL_SHA256",
    "_SALAM_NATIVE_LAYOUT_SHA256",
}


class WrapperTemplateError(ValueError):
    """The template no longer has the reviewed transformation shape."""


@dataclass(frozen=True)
class WrapperGeneration:
    text: str
    provenance: dict


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _dump(node):
    return ast.dump(node, include_attributes=False)


def _one(values, description):
    values = list(values)
    if len(values) != 1:
        raise WrapperTemplateError(
            "Expected exactly one {} (found {})".format(description, len(values))
        )
    return values[0]


def _span(node, lines):
    """Select statement lines without discarding adjacent statements."""
    if not hasattr(node, "end_lineno") or node.end_lineno is None:
        raise WrapperTemplateError("AST statement lacks its source span")
    prefix = lines[node.lineno - 1].encode("utf-8")[: node.col_offset].decode("utf-8")
    tail = (
        lines[node.end_lineno - 1]
        .encode("utf-8")[node.end_col_offset :]
        .decode("utf-8")
    )
    if prefix.strip() or (tail.strip() and not tail.lstrip().startswith("#")):
        raise WrapperTemplateError(
            "Transformation anchor shares a line with another statement"
        )
    return node.lineno - 1, node.end_lineno


def _option(statement, label):
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Attribute)
        and isinstance(statement.value.func.value, ast.Name)
        and statement.value.func.value.id == "parser"
        and statement.value.func.attr == "add_argument"
        and len(statement.value.args) == 1
        and isinstance(statement.value.args[0], ast.Constant)
        and statement.value.args[0].value == label
    )


def _model_contract(model, model_path):
    if not isinstance(model, NormalizedConfiguration):
        raise TypeError("render_wrapper requires a freshly normalized model object")
    data = model.to_dict()
    if (
        data.get("schema_version") != 1
        or data.get("kind") != "salam_native_configuration"
        or not isinstance(data.get("engine_root"), str)
        or not isinstance(data.get("source"), dict)
        or not isinstance(data["source"].get("path"), str)
        or type(data.get("base_address")) is not int
    ):
        raise ValueError("Incomplete normalized native model")
    dependencies = data.get("dependencies")
    if not isinstance(dependencies, list):
        raise ValueError("Final normalized model lacks dependency identities")
    llvm = [item for item in dependencies if item.get("kind") == "llvm_ir"]
    if not llvm or any(
        item.get("state") == "unbuilt"
        or not isinstance(item.get("sha256"), str)
        or not _SHA256.fullmatch(item["sha256"])
        or type(item.get("bytes")) is not int
        or item["bytes"] < 0
        for item in llvm
    ):
        raise ValueError("Generate wrapper only after final strict IR normalization")
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if model.sha256 != _sha(canonical.encode("utf-8")):
        raise ValueError("Normalized canonical model identity differs")
    layout = model.layout_sha256
    if not isinstance(layout, str) or not _SHA256.fullmatch(layout):
        raise ValueError("Normalized model lacks its layout identity")
    engine = Path(data["engine_root"]).resolve()
    config = (engine / data["source"]["path"]).resolve()
    snapshot = Path(model_path)
    if not snapshot.is_absolute():
        snapshot = engine / snapshot
    snapshot = snapshot.resolve()
    for path, label in ((config, "configuration"), (snapshot, "model snapshot")):
        try:
            path.relative_to(engine)
        except ValueError as error:
            raise ValueError(
                "Native wrapper {} leaves workspace".format(label)
            ) from error
    if snapshot.suffix != ".json":
        raise ValueError("Native model snapshot must be a contained JSON path")
    if config == snapshot:
        raise ValueError("Configuration and immutable model snapshot must be distinct")
    return {
        "config_path": str(config),
        "base_address": data["base_address"],
        "model_path": str(snapshot),
        "model_sha256": model.sha256,
        "layout_sha256": layout,
    }


def _contract_source(contract):
    values = (
        ("_SALAM_NATIVE_CONFIG_PATH", contract["config_path"]),
        ("_SALAM_NATIVE_BASE_ADDRESS", contract["base_address"]),
        ("_SALAM_NATIVE_MODEL_PATH", contract["model_path"]),
        ("_SALAM_NATIVE_MODEL_SHA256", contract["model_sha256"]),
        ("_SALAM_NATIVE_LAYOUT_SHA256", contract["layout_sha256"]),
    )
    declarations = "\n".join("{} = {!r}".format(key, value) for key, value in values)
    return (
        "\n# Native inputs are bound to the compiled guest/header layout.\n"
        "from pathlib import Path as _SalamNativePath\n\n"
        + declarations
        + """

def _salam_native_contract_guard(options):
    if options.salam_builder != "native":
        raise ValueError("This wrapper supports only the native builder")
    if (
        not isinstance(options.salam_config, str)
        or _SalamNativePath(options.salam_config).resolve()
        != _SalamNativePath(_SALAM_NATIVE_CONFIG_PATH).resolve()
    ):
        raise ValueError("CLI configuration differs from the normalized guest layout")
    if (
        type(options.salam_base_address) is not int
        or options.salam_base_address != _SALAM_NATIVE_BASE_ADDRESS
    ):
        raise ValueError("CLI base address differs from the compiled guest layout")
    # The factory verifies source/snapshot identities before attaching objects.
    options.salam_config = _SALAM_NATIVE_CONFIG_PATH
    options.salam_base_address = _SALAM_NATIVE_BASE_ADDRESS
    options.salam_builder = "native"

"""
    )


def render_wrapper(model, template_text, *, model_path):
    """Return wrapper text/provenance without reading YAML or writing files.

    The final strict model follows guest/IR compilation. The caller writes
    its immutable JSON snapshot at model_path inside the same workspace.
    Runtime factory checks fresh source against the snapshot and identities.
    """
    contract = _model_contract(model, model_path)
    if not isinstance(template_text, str) or "\r" in template_text:
        raise WrapperTemplateError("Template must be LF Unicode source text")
    if not template_text.endswith("\n"):
        raise WrapperTemplateError("Template must end in a newline")
    tree = ast.parse(template_text, filename="<maintained SALAM fs_template.py>")
    lines = template_text.splitlines(keepends=True)
    if not tree.body:
        raise WrapperTemplateError("Empty maintained template")
    license_prefix = "".join(lines[: tree.body[0].lineno - 1])
    if (
        "Copyright" not in license_prefix
        or "Redistribution and use" not in license_prefix
        or "THIS SOFTWARE" not in license_prefix
    ):
        raise WrapperTemplateError("Maintained template license header is missing")
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.split(".")[0])
    if names & _RESERVED:
        raise WrapperTemplateError(
            "Template collides with native-wrapper contract names"
        )
    options = _one(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "addHWAccOptions"
        ),
        "addHWAccOptions function",
    )
    for label in ("--salam-builder", "--salam-config", "--salam-base-address"):
        declarations = [
            node
            for node in ast.walk(options)
            if isinstance(node, ast.Call)
            and any(
                isinstance(value, ast.Constant) and value.value == label
                for value in node.args
            )
        ]
        _one(declarations, label + " declaration")
    patches, transformations = [], []

    def replace(node, replacement, anchor):
        start, end = _span(node, lines)
        indentation = " " * node.col_offset
        replacement = "".join(
            indentation + line if line.strip() else line
            for line in replacement.splitlines(keepends=True)
        )
        patches.append((start, end, replacement))
        transformations.append(
            {"anchor": anchor, "start_line": start + 1, "end_line": end}
        )

    builder = _one(
        (
            statement
            for statement in options.body
            if _option(statement, "--salam-builder")
        ),
        "--salam-builder option",
    )
    keywords = {item.arg: item.value for item in builder.value.keywords}
    try:
        choices = ast.literal_eval(keywords["choices"])
        default = ast.literal_eval(keywords["default"])
    except (KeyError, ValueError, TypeError) as error:
        raise WrapperTemplateError("Unexpected builder-option declaration") from error
    if choices != ("generated", "native") or default != "generated":
        raise WrapperTemplateError("Maintained builder choices/default changed")
    replace(
        builder,
        'parser.add_argument("--salam-builder", choices=("native",), '
        'default="native", help="Fixed native wrapper construction path.")\n',
        "native_only_builder_option",
    )
    config_option = _one(
        (
            statement
            for statement in options.body
            if _option(statement, "--salam-config")
        ),
        "--salam-config option",
    )
    replace(
        config_option,
        'parser.add_argument("--salam-config", default=_SALAM_NATIVE_CONFIG_PATH, '
        'help="Fixed normalized topology configuration.")\n',
        "fixed_configuration_option",
    )
    base_option = _one(
        (
            statement
            for statement in options.body
            if _option(statement, "--salam-base-address")
        ),
        "--salam-base-address option",
    )
    replace(
        base_option,
        'parser.add_argument("--salam-base-address", type=lambda value: int(value, 0), '
        "default=_SALAM_NATIVE_BASE_ADDRESS, "
        'help="Fixed compiled guest/header base address.")\n',
        "fixed_base_option",
    )
    signature = ast.parse(_DISPATCH).body[0]
    dispatch = _one(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.If) and _dump(node.test) == _dump(signature.test)
        ),
        "native/generated construction dispatch",
    )
    if _dump(dispatch) != _dump(signature):
        raise WrapperTemplateError("Construction dispatch contains unreviewed logic")
    replace(
        dispatch,
        "from native_factory import makeHWAcc as make_native_hwacc\n\n"
        "make_native_hwacc(\n"
        "    args, test_sys,\n"
        "    expected_model_path=_SALAM_NATIVE_MODEL_PATH,\n"
        "    expected_model_sha256=_SALAM_NATIVE_MODEL_SHA256,\n"
        "    expected_layout_sha256=_SALAM_NATIVE_LAYOUT_SHA256,\n"
        ")\n",
        "direct_factory_without_generated_module",
    )
    sys_import = _one(
        (
            node
            for node in tree.body
            if isinstance(node, ast.Import)
            and any(
                alias.name == "sys" and alias.asname is None for alias in node.names
            )
        ),
        "top-level sys import",
    )
    _span(sys_import, lines)
    patches.append(
        (sys_import.end_lineno, sys_import.end_lineno, _contract_source(contract))
    )
    transformations.append(
        {"anchor": "fixed_model_contract", "after_line": sys_import.end_lineno}
    )
    parse_signature = ast.parse("args = parser.parse_args()").body[0]
    parse_args = _one(
        (node for node in tree.body if _dump(node) == _dump(parse_signature)),
        "top-level args = parser.parse_args()",
    )
    _span(parse_args, lines)
    patches.append(
        (
            parse_args.end_lineno,
            parse_args.end_lineno,
            "\n_salam_native_contract_guard(args)\n",
        )
    )
    transformations.append(
        {
            "anchor": "guard_before_system_construction",
            "after_line": parse_args.end_lineno,
        }
    )
    intervals = sorted((start, end) for start, end, _ in patches)
    for left, right in zip(intervals, intervals[1:]):
        if left[1] > right[0]:
            raise WrapperTemplateError("Transformation statement spans overlap")
    rendered_lines = list(lines)
    for start, end, replacement in sorted(
        patches, key=lambda item: item[0], reverse=True
    ):
        rendered_lines[start:end] = [replacement]
    rendered = "".join(rendered_lines)
    if not rendered.startswith(license_prefix):
        raise WrapperTemplateError("Inherited template license text changed")
    rendered_tree = ast.parse(rendered, filename="<normalized native wrapper>")
    if any(
        isinstance(node, ast.Name) and node.id == "TEMPLATE"
        for node in ast.walk(rendered_tree)
    ):
        raise WrapperTemplateError("Generated topology module reference survived")
    for node in ast.walk(rendered_tree):
        modules = (
            [item.name for item in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else []
        )
        if any(
            name == "TEMPLATE" or name.startswith("generated.") or ".generated." in name
            for name in modules
        ):
            raise WrapperTemplateError("Generated topology module import survived")
    compile(rendered_tree, "<normalized native wrapper>", "exec")
    provenance = {
        "schema_version": 1,
        "kind": "salam_normalized_native_wrapper",
        "method": "bounded_ast_statement_spans_on_maintained_template",
        "template_sha256": _sha(template_text.encode("utf-8")),
        "inherited_license_prefix_sha256": _sha(license_prefix.encode("utf-8")),
        "inherited_license_preserved_verbatim": True,
        "generator_sha256": _sha(Path(__file__).read_bytes()),
        "wrapper_sha256": _sha(rendered.encode("utf-8")),
        **contract,
        "runtime_factory": "native_factory.makeHWAcc",
        "construction": "fresh_source_normalization_against_fixed_snapshot",
        "expected_factory_keywords": [
            "expected_model_path",
            "expected_model_sha256",
            "expected_layout_sha256",
        ],
        "legacy_systembuilder_executed": False,
        "generated_topology_module_imported": False,
        "cli_identity_guard": ["salam_builder", "salam_config", "salam_base_address"],
        "transformations": transformations,
        "scope": "Board/system setup retained as template text; no simulation/build attestation.",
    }
    return WrapperGeneration(rendered, provenance)
