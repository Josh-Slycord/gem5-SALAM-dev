"""Verify generated addresses are consumed by the actual guest/IR toolchains."""
import hashlib
import json
import re
from pathlib import Path

import yaml

from .config_contract import _Loader
from .ir_toolchain import (
    assert_clean_ir_environment,
    compiler_binding,
    guest_compiler_argv,
    ir_compiler_argv,
)
from .regression import _command
from .toolchain_profile import is_modern, load_toolchain

PROJECT = Path(__file__).resolve().parents[1]


def address_macros(headers):
    expected = {}
    for header in headers:
        for name, value in re.findall(
            r"^\s*#define\s+(\w+)\s+(0x[0-9a-fA-F]+)\s*$",
            Path(header).read_text(),
            re.M,
        ):
            numeric = int(value, 16)
            if name in expected and expected[name] != numeric:
                raise ValueError("Conflicting generated address macro: " + name)
            expected[name] = numeric
    if not expected:
        raise ValueError("Generated headers have no address macros")
    return expected


def check_preprocessed_macros(text, expected):
    actual = {}
    for line in text.splitlines():
        match = re.match(r"^#define\s+(\w+)\s+(.+)$", line)
        if match and match.group(1) in expected:
            try:
                actual[match.group(1)] = int(match.group(2).strip(), 0)
            except ValueError:
                raise ValueError(
                    "Address macro is not a literal integer: " + match.group(1)
                )
    differences = {
        key: {"expected": value, "actual": actual.get(key)}
        for key, value in expected.items()
        if actual.get(key) != value
    }
    if differences:
        raise ValueError(
            "Compiler consumed missing/stale generated addresses: " + repr(differences)
        )
    return {"state": "passed", "matched_address_macros": actual}


def witness_build_inputs(workspace, spec, contract, directory, env):
    workspace, directory = Path(workspace), Path(directory)
    benchmark = workspace / spec["benchmark"]
    profile = load_toolchain(PROJECT)
    assert_clean_ir_environment(env, profile)
    headers = [
        benchmark / (cluster["name"] + "_hw_defines.h")
        for cluster in contract["components"]["clusters"]
    ]
    expected = address_macros(headers)
    sources = [("guest", benchmark / "sw/main.cpp", guest_compiler_argv(profile))]
    for index, relative in enumerate(contract["ir_paths"]):
        source = workspace / Path(relative).with_suffix(".c")
        if not source.is_file():
            source = source.with_suffix(".cpp")
        if not source.is_file():
            raise ValueError("Cannot witness IR compiler source for " + relative)
        sources.append(
            (
                "ir-" + str(index),
                source,
                ir_compiler_argv(profile),
            )
        )
    checks = []
    for label, source, compiler in sources:
        stem = "address-input-" + label
        command = _command(
            compiler + ["-dM", "-E", "-I", str(source.parent), str(source)],
            workspace,
            directory,
            stem,
            env,
            120,
        )
        text = (directory / command["stdout"]).read_text()
        # A pure arithmetic kernel may not use any MMIO addresses. If it does
        # include the address header, require the entire address table to match.
        has_any = any(
            re.search(r"^#define\s+" + re.escape(key) + r"\s", text, re.M)
            for key in expected
        )
        if label == "guest" or has_any:
            check = check_preprocessed_macros(text, expected)
        else:
            check = {
                "state": "no_address_macros",
                "reason": "Pure kernel source has no generated MMIO header",
            }
        checks.append(dict(check, source=str(source), command=command))
    record = {
        "state": "passed",
        "expected_macros": expected,
        "checks": checks,
        "scope": "Actual compiler preprocessor inputs, before simulator execution",
    }
    if is_modern(profile):
        guest = Path(guest_compiler_argv(profile)[0]).resolve(strict=True)
        if not guest.is_file():
            raise ValueError("Selected guest compiler is not a regular file")
        record["toolchain"] = compiler_binding(profile)
        record["selected_guest_compiler"] = {
            "path": str(guest),
            "sha256": hashlib.sha256(guest.read_bytes()).hexdigest(),
        }
    return record


_HEADER_START = b"//BEGIN GENERATED CODE"
_HEADER_END = b"//END GENERATED CODE"
_CLUSTER_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _header_parts(raw):
    """Split the exact generated block from manual prefix and suffix bytes."""
    if raw.count(_HEADER_START) != 1 or raw.count(_HEADER_END) != 1:
        raise ValueError("Cluster header needs one generated block")
    start = raw.index(_HEADER_START)
    end = raw.index(_HEADER_END, start) + len(_HEADER_END)
    prefix, block, suffix = raw[:start], raw[start:end], raw[end:]
    if (prefix and not prefix.endswith(b"\n")) or (
        suffix and not suffix.startswith((b"\n", b"\r\n"))
    ):
        raise ValueError("Generated block markers must occupy whole lines")
    return prefix, block, suffix


def _macro_names(block):
    names = re.findall(
        rb"(?m)^[ \t]*#define[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]+", block
    )
    if not names or len(set(names)) != len(names):
        raise ValueError("Generated block needs unique object-like address macros")
    return {name.decode("ascii") for name in names}


def _cluster_names(config):
    documents = list(
        yaml.load_all(Path(config).read_text(encoding="utf-8"), Loader=_Loader)
    )
    result = []
    for document in documents:
        if not isinstance(document, dict) or not isinstance(
            document.get("acc_cluster"), list
        ):
            raise ValueError("Source configuration has no cluster list")
        result.extend(
            row["Name"]
            for row in document["acc_cluster"]
            if isinstance(row, dict) and "Name" in row
        )
    if not result or any(
        not isinstance(name, str) or not _CLUSTER_NAME.fullmatch(name)
        for name in result
    ):
        raise ValueError("Source cluster names are unsupported")
    return result


def _header_consumers(benchmark, old_basename):
    include = re.compile(
        rb'(?m)^[ \t]*#[ \t]*include[ \t]*[<"](?:[^">]*/)?'
        + re.escape(old_basename.encode("ascii"))
        + rb'[">]'
    )
    sites = []
    for folder in (benchmark / "hw", benchmark / "sw"):
        if not folder.is_dir():
            continue
        for source in folder.rglob("*"):
            if source.is_file() and source.suffix in (
                ".c",
                ".cc",
                ".cpp",
                ".h",
                ".hh",
                ".hpp",
            ):
                if include.search(source.read_bytes()):
                    sites.append(str(source))
    if not sites:
        raise ValueError("No C source includes the original cluster header")
    return sites


def rebind_cluster_header(engine, workspace, spec, contract, evidence_dir):
    """Retarget only an old generated header block to a renamed cluster header.

    The original engine and its headers remain untouched. A before-image of the
    staged old header is stored in evidence before replacement. Macro names must
    match exactly; changed accelerator identities require an explicit source edit.
    """
    engine = Path(engine).resolve(strict=True)
    workspace = Path(workspace).resolve(strict=True)
    evidence = Path(evidence_dir).resolve()
    if (
        engine == workspace
        or engine in workspace.parents
        or workspace in engine.parents
        or evidence == workspace
        or workspace in evidence.parents
        or evidence == engine
        or engine in evidence.parents
    ):
        raise ValueError("Cluster header rebind needs isolated evidence and workspace")
    evidence.mkdir(parents=True, exist_ok=True)
    receipt_path = evidence / "cluster-header-rebind.json"
    if receipt_path.exists():
        raise ValueError("Cluster header rebind receipt already exists")
    result = {
        "schema_version": 1,
        "kind": "cluster_header_rebind",
        "state": "checking",
        "engine": str(engine),
        "workspace": str(workspace),
        "errors": [],
    }
    receipt_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    try:
        benchmark_relative = Path(spec["benchmark"])
        config_relative = Path(spec.get("config", spec["benchmark"] + "/config.yml"))
        if (
            benchmark_relative.is_absolute()
            or config_relative.parent != benchmark_relative
            or config_relative.name not in ("config.yml", "config.yaml")
            or any(
                part in ("", ".", "..")
                for part in benchmark_relative.parts + config_relative.parts
            )
        ):
            raise ValueError("Source benchmark configuration path is unsafe")
        source_config = engine / config_relative
        resolved_config = source_config.resolve(strict=True)
        resolved_config.relative_to(engine)
        if (
            source_config.is_symlink()
            or resolved_config != source_config
            or not source_config.is_file()
        ):
            raise ValueError("Source benchmark configuration must be a regular file")
        original_names = _cluster_names(source_config)
        requested_names = [item["name"] for item in contract["components"]["clusters"]]
        if original_names == requested_names:
            result.update(
                state="unchanged",
                original_clusters=original_names,
                requested_clusters=requested_names,
            )
            return result
        if len(original_names) != 1 or len(requested_names) != 1:
            raise ValueError("Only a single cluster rename is supported")
        old_name, new_name = original_names[0], requested_names[0]
        if not isinstance(new_name, str) or not _CLUSTER_NAME.fullmatch(new_name):
            raise ValueError("Requested cluster name is unsafe")
        benchmark = workspace / benchmark_relative
        source_benchmark = engine / benchmark_relative
        old_basename = old_name + "_hw_defines.h"
        new_basename = new_name + "_hw_defines.h"
        source_old = source_benchmark / old_basename
        staged_old = benchmark / old_basename
        staged_new = benchmark / new_basename
        for header, root in (
            (source_old, engine),
            (staged_old, workspace),
            (staged_new, workspace),
        ):
            if (
                header.is_symlink()
                or not header.is_file()
                or header.resolve(strict=True) != header
            ):
                raise ValueError("Cluster header missing or symlinked: " + str(header))
            header.relative_to(root)
        original = source_old.read_bytes()
        before = staged_old.read_bytes()
        if before != original:
            raise ValueError("Staged old cluster header changed before rebind")
        old_prefix, old_block, old_suffix = _header_parts(before)
        _, new_block, _ = _header_parts(staged_new.read_bytes())
        old_names, new_names = _macro_names(old_block), _macro_names(new_block)
        if old_names != new_names:
            raise ValueError(
                "Cluster rename changed generated macro names: "
                + repr(sorted(old_names ^ new_names))
            )
        consumers = _header_consumers(benchmark, old_basename)
        before_path = evidence / ("cluster-header-before-" + old_basename)
        with before_path.open("xb") as stream:
            stream.write(before)
        if before_path.read_bytes() != before:
            raise ValueError("Cluster header before-image differs")
        newline = b"\r\n" if b"\r\n" in before else b"\n"
        replacement = (
            _HEADER_START
            + newline
            + b'#include "'
            + new_basename.encode("ascii")
            + b'"'
            + newline
            + _HEADER_END
        )
        after = old_prefix + replacement + old_suffix
        staged_old.write_bytes(after)
        if staged_old.read_bytes() != after or source_old.read_bytes() != original:
            raise ValueError("Cluster header rebind changed unexpected bytes")
        result.update(
            state="rebound",
            original_cluster=old_name,
            requested_cluster=new_name,
            old_header=str(staged_old),
            new_header=str(staged_new),
            original_source_sha256=hashlib.sha256(original).hexdigest(),
            before_image={
                "path": str(before_path),
                "sha256": hashlib.sha256(before).hexdigest(),
            },
            staged_sha256=hashlib.sha256(after).hexdigest(),
            new_header_sha256=hashlib.sha256(staged_new.read_bytes()).hexdigest(),
            macro_names=sorted(old_names),
            include_sites=consumers,
            manual_prefix_unchanged=after.startswith(old_prefix),
            manual_suffix_unchanged=after.endswith(old_suffix),
        )
    except Exception as error:
        result["state"] = "failed"
        result["errors"].append(type(error).__name__ + ": " + str(error))
    finally:
        receipt_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if result["state"] == "failed":
        raise ValueError("Cluster header rebind failed: " + "; ".join(result["errors"]))
    return result
