# SPDX-License-Identifier: BSD-3-Clause
"""Render SALAM guest headers from the checked normalized address model.

This module performs no file I/O and imports no legacy generator. Header
receipts and workspace writes belong to the caller. The rendered layout
identity excludes LLVM artifact content, so preparation and runtime models
produce the same header when their address/configuration layout agrees.
"""

import json
import re
from collections.abc import Mapping

from .native_config import NormalizedConfiguration

BEGIN = "//BEGIN GENERATED CODE"
END = "//END GENERATED CODE"
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_DEFINE = re.compile(r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)")


class HeaderGenerationError(ValueError):
    """A rejected header/model with no output files changed."""


def _identifier(value, label):
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise HeaderGenerationError(
            "{} must be an ASCII C identifier: {!r}".format(label, value)
        )
    return value


def _payload(model):
    if not isinstance(model, NormalizedConfiguration):
        raise TypeError(
            "Header generation requires a freshly normalized configuration; "
            "serialized receipt JSON is not an input format"
        )
    payload = model.to_dict()
    if payload.get("schema_version") != 1:
        raise HeaderGenerationError("Unsupported normalized configuration version")
    clusters = payload.get("clusters")
    if not isinstance(clusters, list) or len(clusters) != 1:
        raise HeaderGenerationError(
            "Native header generation currently requires exactly one cluster"
        )
    return payload


def _layout(model):
    payload = _payload(model)
    cluster = payload["clusters"][0]
    authored_name = _identifier(cluster["authored_name"], "Authored cluster name")
    filename = authored_name + "_hw_defines.h"
    symbols = {}
    lines = []

    def declare(name, value):
        _identifier(name, "Header symbol")
        if name in symbols:
            raise HeaderGenerationError(
                "{}: duplicate generated symbol {!r}".format(filename, name)
            )
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise HeaderGenerationError(
                "{}: symbol {} has an invalid 32-bit address".format(filename, name)
            )
        symbols[name] = value
        lines.append("#define {} {}\n".format(name, hex(value)))

    for dma in cluster["dmas"]:
        if dma["type"] != "NonCoherent" or dma["pio_size"] != 21:
            raise HeaderGenerationError(
                "Native headers support the retained 21-byte NonCoherent DMA "
                "register layout only"
            )
        prefix = _identifier(dma["name"], "DMA name").upper()
        lines.append("//NonCoherentDMA\n")
        for suffix, offset in (
            ("Flags", 0),
            ("RdAddr", 1),
            ("WrAddr", 9),
            ("CopyLen", 17),
        ):
            declare(prefix + "_" + suffix, dma["pio_addr"] + offset)

    for accelerator in cluster["accelerators"]:
        name = _identifier(accelerator["name"], "Accelerator name").upper()
        lines.append("//Accelerator: " + name + "\n")
        declare(name, accelerator["pio_addr"])
        for memory in accelerator["memories"]:
            if memory["type"] != "SPM":
                raise HeaderGenerationError("Native headers support SPM variables only")
            # Unlike accelerator identifiers, the retained generator does
            # not uppercase or lowercase authored variable macro names.
            declare(
                _identifier(memory["authored_name"], "Authored memory name"),
                memory["address"],
            )
    return payload, authored_name, filename, symbols, lines


def header_symbols(model):
    """Return {header_filename: {macro_name: integer_address}} deterministically.

    The model is the output of normalize_configuration(), including its
    require_ir=False preparation mode. Macro names preserve the retained
    guest-code contract, independently of lowercase SimObject child names.
    """
    _, _, filename, symbols, _ = _layout(model)
    return {filename: symbols}


def _generated_region(model, payload, authored_name, filename, lines):
    # JSON escaping keeps authored paths on a single C++ comment line.
    source = payload["source"]
    source_path = json.dumps(source["path"], ensure_ascii=True)
    source_sha = source["sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
        raise HeaderGenerationError("Normalized source SHA-256 is invalid")
    return "".join(
        [
            BEGIN + "\n",
            "/**\n",
            " * @file " + filename + "\n",
            " * @brief Memory-mapped register addresses for "
            + authored_name
            + " cluster\n",
            " *\n",
            " * @warning GENERATED CODE - DO NOT MODIFY\n",
            " *          Regenerate via the SALAM Workbench native builder.\n",
            " *\n",
            " * These defines provide the memory-mapped addresses for accessing\n",
            " * DMA controllers, accelerators, and scratchpad memory in the\n",
            " * gem5-SALAM simulation environment.\n",
            " */\n",
            "// Generator: salam_workbench.native_codegen/v1\n",
            "// Normalized layout SHA-256: " + model.layout_sha256 + "\n",
            "// Source configuration: " + source_path + "\n",
            "// Source SHA-256: " + source_sha + "\n",
            "//Cluster: " + authored_name.upper() + "\n",
            *lines,
            END + "\n",
        ]
    )


def _custom_regions(text, filename):
    if not isinstance(text, str):
        raise TypeError("{}: existing header must be text".format(filename))
    if "\x00" in text:
        raise HeaderGenerationError(
            "{}: existing header contains a NUL byte".format(filename)
        )
    begin = []
    end = []
    offset = 0
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        stripped = line.strip()
        if "BEGIN GENERATED CODE" in line:
            if stripped != BEGIN:
                raise HeaderGenerationError(
                    "{}:{}: malformed generated-region start".format(filename, number)
                )
            begin.append((offset, number))
        if "END GENERATED CODE" in line:
            if stripped != END:
                raise HeaderGenerationError(
                    "{}:{}: malformed generated-region end".format(filename, number)
                )
            end.append((offset + len(line), number))
        offset += len(line)
    if not begin and not end:
        return text, ""
    if len(begin) != 1 or len(end) != 1 or begin[0][1] >= end[0][1]:
        raise HeaderGenerationError(
            "{}: expected one ordered generated region; found {} starts "
            "and {} ends".format(filename, len(begin), len(end))
        )
    return text[: begin[0][0]], text[end[0][0] :]


def _custom_macros(text):
    """Ignore comments while locating authored macro definitions."""
    block = False
    quote = None
    for line in text.splitlines():
        escaped = False
        visible = []
        position = 0
        while position < len(line):
            if block:
                closing = line.find("*/", position)
                if closing < 0:
                    break
                position = closing + 2
                block = False
            elif quote is not None:
                character = line[position]
                visible.append(character)
                position += 1
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
            elif line[position] in ("'", '"'):
                quote = line[position]
                visible.append(line[position])
                position += 1
            elif line.startswith("//", position):
                break
            elif line.startswith("/*", position):
                block = True
                visible.append(" ")
                position += 2
            else:
                visible.append(line[position])
                position += 1
        if quote is not None and not line.endswith("\\"):
            quote = None
        match = _DEFINE.match("".join(visible))
        if match:
            yield match.group(1)


def render_headers(model, existing_headers=None):
    """Render {filename: text}, retaining authored prefix/suffix exactly.

    existing_headers maps the authored cluster name to its current header
    text. Unknown keys, duplicate generated regions and custom/generated
    macro collisions are rejected. The sole generated region is replaced
    in its original position; unmarked custom text receives a new region
    after a newline separator. New generated text uses LF line endings.
    """
    payload, name, filename, symbols, lines = _layout(model)
    if existing_headers is None:
        existing_headers = {}
    if not isinstance(existing_headers, Mapping):
        raise TypeError("existing_headers must map authored cluster names to text")
    unexpected = set(existing_headers) - {name}
    if unexpected:
        raise HeaderGenerationError(
            "Unexpected existing-header keys: {}".format(
                ", ".join(sorted(repr(key) for key in unexpected))
            )
        )
    prefix, suffix = _custom_regions(existing_headers.get(name, ""), filename)
    collisions = set(_custom_macros(prefix + suffix)) & set(symbols)
    if collisions:
        raise HeaderGenerationError(
            "{}: authored/generated macro collision: {}".format(
                filename, ", ".join(sorted(collisions))
            )
        )
    if prefix and not prefix.endswith(("\n", "\r")):
        prefix += "\n"
    generated = _generated_region(model, payload, name, filename, lines)
    return {filename: prefix + generated + suffix}
