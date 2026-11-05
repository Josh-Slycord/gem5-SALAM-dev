"""Source-bound, run-local ARM SDK adaptation for modern LLVM IR builds."""
import hashlib
import json
import re
import shlex
from pathlib import Path, PurePosixPath

from .toolchain_profile import is_modern, load_toolchain, profile_identity

PROJECT = Path(__file__).resolve().parents[1]
TARGET = "armv7-pc-none-eabi"
_RECIPE = re.compile(r"(?m)^\tclang(?P<args>[ \t][^\r\n]*)(?P<ending>\r?\n|$)")
_INCLUDE_ENV = frozenset(
    ("CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "OBJC_INCLUDE_PATH", "SDKROOT")
)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _record(path):
    path = Path(path)
    return {"path": str(path), "sha256": _sha(path), "bytes": path.stat().st_size}


def ir_compiler_argv(profile):
    """The IR build and independent preprocessor use the same target SDK flags."""
    command = [str(PurePosixPath(profile["llvm_bin"]) / "clang"), "-target", TARGET]
    if is_modern(profile):
        command += [
            "--sysroot=" + profile["arm_sysroot"],
            "-isystem",
            profile["arm_include"],
            "-ffp-contract=off",
        ]
    return command


def guest_compiler_argv(profile):
    return [str(PurePosixPath(profile["arm_bin"]) / "arm-none-eabi-g++")]


def assert_clean_ir_environment(environment, profile):
    if is_modern(profile) and any(environment.get(key) for key in _INCLUDE_ENV):
        raise ValueError(
            "Modern IR builds require explicit target SDK flags, without ambient include-path overrides"
        )


def compiler_binding(profile):
    compiler = Path(ir_compiler_argv(profile)[0]).resolve(strict=True)
    if not compiler.is_file():
        raise ValueError("Selected IR compiler is not a regular file")
    result = {
        "profile": profile["id"],
        "profile_sha256": profile_identity(profile),
        "compiler": _record(compiler),
        "ir_argv_prefix": ir_compiler_argv(profile),
    }
    if not is_modern(profile):
        return result
    result["floating_point_policy"] = "unfused_scalar_no_contract"
    declared_root = PurePosixPath(profile["arm_sysroot"])
    declared_include = PurePosixPath(profile["arm_include"])
    try:
        declared_include.relative_to(declared_root)
    except ValueError:
        raise ValueError(
            "IR include directory must be inside the declared target SDK sysroot"
        )
    root = Path(str(declared_root)).resolve(strict=True)
    include = Path(str(declared_include)).resolve(strict=True)
    if not root.is_dir() or not include.is_dir():
        raise ValueError("Selected ARM target SDK directories are unavailable")
    headers = []
    for name in ("stdio.h", "stdint.h", "stdlib.h", "math.h"):
        header = (include / name).resolve(strict=True)
        if not header.is_file():
            raise ValueError("Selected target SDK header is unavailable: " + name)
        headers.append(dict(_record(header), name=name))
    result["target_sdk"] = {
        "declared_sysroot": str(declared_root),
        "resolved_sysroot": str(root),
        "declared_include": str(declared_include),
        "resolved_include": str(include),
        "header_identities": headers,
        "meaning": "Explicit target SDK paths; packaged include symlink resolution is recorded",
    }
    return result


def _make_word(value):
    # GNU make expands dollars before the shell parses single quotes.
    return shlex.quote(value).replace("$", "$$")


def adapt_ir_toolchain(
    workspace,
    benchmark,
    evidence_dir,
    *,
    profile=None,
    source_engine=None,
    environment=None,
):
    """Replace one reviewed staged clang recipe; never edit the source engine."""
    selected = profile if profile is not None else load_toolchain(PROJECT)
    if not is_modern(selected):
        return {
            "kind": "staged_ir_toolchain_adapter",
            "state": "legacy_unchanged",
            "profile": selected["id"],
        }
    workspace = Path(workspace).resolve(strict=True)
    relative = PurePosixPath(benchmark)
    if not isinstance(benchmark, str) or not re.fullmatch(
        r"benchmarks/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", benchmark
    ):
        raise ValueError("IR benchmark must be benchmarks/<suite>/<workload>")
    evidence = Path(evidence_dir).resolve()
    if evidence == workspace or workspace in evidence.parents:
        raise ValueError("IR adapter evidence must be outside its staged workspace")
    engine = (
        Path(source_engine).resolve(strict=True) if source_engine is not None else None
    )
    if engine is not None and (
        engine == workspace
        or engine in workspace.parents
        or workspace in engine.parents
    ):
        raise ValueError("IR recipe adaptation requires a separate staged workspace")
    evidence.mkdir(parents=True, exist_ok=False)
    receipt_path = evidence / "ir-toolchain.json"
    record = {
        "schema_version": 1,
        "kind": "staged_ir_toolchain_adapter",
        "state": "checking",
        "profile": selected["id"],
        "workspace": str(workspace),
        "benchmark": benchmark,
        "errors": [],
        "source_engine_changed": False,
        "compilation_executed": False,
    }
    path = workspace / Path(relative.as_posix()) / "hw/Makefile"
    try:
        if environment is not None:
            assert_clean_ir_environment(environment, selected)
        resolved = path.resolve(strict=True)
        resolved.relative_to(workspace)
        if resolved != path or not path.is_file():
            raise ValueError("Staged IR Makefile must be a regular local file")
        before = path.read_bytes()
        record["before"] = _record(path)
        text = before.decode("utf-8")
        matches = list(_RECIPE.finditer(text))
        if len(matches) != 1:
            raise ValueError(
                "Expected exactly one literal clang recipe in staged IR Makefile"
            )
        match = matches[0]
        tokens = shlex.split(match.group("args"))
        if tokens.count("-emit-llvm") != 1:
            raise ValueError("Staged clang recipe must emit LLVM IR exactly once")
        if any(
            token.startswith("--sysroot") or token == "-isystem" for token in tokens
        ):
            raise ValueError(
                "Staged clang recipe already has unreviewed target SDK overrides"
            )
        if any(token.startswith("-ffp-contract") for token in tokens):
            raise ValueError(
                "Staged clang recipe has an unreviewed floating-point contraction override"
            )
        targets = [index for index, token in enumerate(tokens) if token == "-target"]
        if len(targets) > 1 or any(token.startswith("--target") for token in tokens):
            raise ValueError("Staged clang recipe has ambiguous target options")
        if targets and (
            targets[0] + 1 >= len(tokens) or tokens[targets[0] + 1] != TARGET
        ):
            raise ValueError("Staged clang recipe has a different target")
        binding = compiler_binding(selected)
        prefix = ir_compiler_argv(selected)
        injected = prefix[:1] + (prefix[1:3] if not targets else []) + prefix[3:]
        replacement = (
            "\t"
            + " ".join(_make_word(word) for word in injected)
            + match.group("args")
            + match.group("ending")
        )
        after = (text[: match.start()] + replacement + text[match.end() :]).encode(
            "utf-8"
        )
        record.update(
            toolchain=binding,
            recipe_before=match.group(0),
            recipe_after=replacement,
            target_added=not bool(targets),
        )
        source_before = None
        if engine is not None:
            source = engine / Path(relative.as_posix()) / "hw/Makefile"
            if source.resolve(strict=True) != source or not source.is_file():
                raise ValueError("Source IR Makefile is not a regular local file")
            source_before = _record(source)
            record["source_makefile"] = source_before
        before_path, after_path = (
            evidence / "Makefile.before",
            evidence / "Makefile.after",
        )
        with before_path.open("xb") as stream:
            stream.write(before)
        with after_path.open("xb") as stream:
            stream.write(after)
        if path.read_bytes() != before:
            raise ValueError("Staged IR Makefile changed before adaptation")
        path.write_bytes(after)
        if path.read_bytes() != after or (
            source_before is not None
            and _sha(source_before["path"]) != source_before["sha256"]
        ):
            raise ValueError("IR recipe adaptation changed unexpected input bytes")
        record.update(
            state="adapted",
            before_image=_record(before_path),
            after_image=_record(after_path),
            after=_record(path),
        )
    except Exception as error:
        record["state"] = "failed"
        record["errors"].append(type(error).__name__ + ": " + str(error))
    receipt_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if record["state"] != "adapted":
        raise ValueError(
            "Modern IR toolchain adaptation failed: " + "; ".join(record["errors"])
        )
    return record


def preflight_known_ir_incompatibilities(ir_paths, workspace, receipt_path, *, profile):
    """Reject a bounded list of known gaps; this is not a complete LLVM validator."""
    if not is_modern(profile):
        return {"state": "legacy_not_checked", "complete_opcode_validation": False}
    workspace = Path(workspace).resolve(strict=True)
    receipt = Path(receipt_path).resolve()
    if receipt == workspace or workspace in receipt.parents:
        raise ValueError(
            "IR compatibility receipt must be outside the staged workspace"
        )
    limits = {
        "max_files": 128,
        "max_file_bytes": 8 * 1024 * 1024,
        "max_total_bytes": 32 * 1024 * 1024,
    }
    result = {
        "schema_version": 1,
        "kind": "known_ir_incompatibility_preflight",
        "state": "checking",
        "profile": profile["id"],
        "frontend_policy": "unfused_scalar_no_contract",
        "complete_opcode_validation": False,
        "scope": "Only known unsupported fneg and llvm.fmuladd/llvm.fma calls or declarations; no claim that other LLVM constructs are implemented",
        "limits": limits,
        "analyzer_sha256": _sha(__file__),
        "files": [],
        "findings": [],
        "errors": [],
    }
    assignment = re.compile(r'^(?:%"[^"]+"|%[-A-Za-z0-9_.$]+)\s*=\s*(.*)$')
    intrinsic = re.compile(
        r'@(?:"(?P<quoted>llvm\.(?:fmuladd|fma)(?:\.[^"]+)?)"|(?P<plain>llvm\.(?:fmuladd|fma)(?:\.[A-Za-z0-9_.]+)?))\s*\('
    )
    try:
        if (
            not isinstance(ir_paths, (list, tuple))
            or not 1 <= len(ir_paths) <= limits["max_files"]
        ):
            raise ValueError(
                "IR compatibility preflight file count is outside its bounded scope"
            )
        total = 0
        for value in ir_paths:
            path = Path(value)
            resolved = path.resolve(strict=True)
            resolved.relative_to(workspace)
            if resolved != path or not path.is_file() or path.suffix != ".ll":
                raise ValueError("IR preflight requires regular staged .ll files")
            size = path.stat().st_size
            total += size
            if size > limits["max_file_bytes"] or total > limits["max_total_bytes"]:
                raise ValueError(
                    "IR compatibility preflight exceeds its recorded byte budget"
                )
            payload = path.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            if digest != _sha(path):
                raise ValueError("IR changed during compatibility preflight")
            result["files"].append(
                {"path": str(path), "sha256": digest, "bytes": len(payload)}
            )
            for number, line in enumerate(payload.decode("utf-8").splitlines(), 1):
                code = line.split(";", 1)[0].strip()
                match = assignment.match(code)
                body = match.group(1) if match else code
                construct = None
                if re.match(r"fneg\b", body):
                    construct = "fneg"
                elif body.startswith("declare ") or re.match(
                    r"(?:(?:tail|musttail|notail)\s+)?(?:call|invoke|callbr)\b", body
                ):
                    symbol = intrinsic.search(body)
                    if symbol:
                        construct = symbol.group("quoted") or symbol.group("plain")
                if construct:
                    result["findings"].append(
                        {
                            "path": str(path),
                            "line": number,
                            "construct": construct,
                            "statement": code[:600],
                        }
                    )
        result["state"] = (
            "rejected" if result["findings"] else "no_known_incompatibilities"
        )
    except Exception as error:
        result["state"] = "failed"
        result["errors"].append(type(error).__name__ + ": " + str(error))
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if result["state"] == "rejected":
        details = "; ".join(
            Path(item["path"]).name + ":" + str(item["line"]) + " " + item["construct"]
            for item in result["findings"][:8]
        )
        raise ValueError(
            "Known unsupported LLVM IR rejected before simulation: " + details
        )
    if result["state"] == "failed":
        raise ValueError(
            "Known IR compatibility preflight failed: " + "; ".join(result["errors"])
        )
    return result
