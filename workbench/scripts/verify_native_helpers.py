#!/usr/bin/env python3
"""Compile/run SALAM production-helper GTests with ASan, UBSan and checked STL.

The default covers three pure helper suites without gem5/LLVM generation.
Pass --generated-headers from a real opt-in build to add the FU/Params suite.
No substitute headers are generated. This is not an end-to-end simulator test.
"""
import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(command, cwd, timeout, environment=None):
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )
    return completed.returncode, completed.stdout + completed.stderr


def main(argv=None):
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="New evidence directory; existing paths are refused",
    )
    parser.add_argument(
        "--compiler",
        default=shutil.which("g++"),
        help="Compiler executable path (default: g++ on PATH)",
    )
    parser.add_argument(
        "--generated-headers",
        type=Path,
        help="Real gem5 build directory containing params/config",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=600,
        help="Per-command limit, from 30 through 3600",
    )
    args = parser.parse_args(argv)
    if not 30 <= args.timeout_seconds <= 3600:
        parser.error("--timeout-seconds must be from 30 through 3600")
    if not args.compiler:
        parser.error("g++ was not found; pass --compiler")
    compiler = Path(args.compiler).expanduser().resolve()
    if not compiler.is_file() or not os.access(compiler, os.X_OK):
        parser.error("--compiler must identify an executable file")
    generated = None
    if args.generated_headers is not None:
        generated = args.generated_headers.expanduser().resolve()
        required = ("params/SALAMPowerModel.hh", "config/have_fenv.hh")
        if not all((generated / item).is_file() for item in required):
            parser.error("--generated-headers needs a real SALAM-enabled build")
    output = args.output.expanduser().resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error("--output already exists; choose a new evidence path")

    sources = [
        root / "src/hwacc/tests/response_queue.test.cc",
        root / "src/hwacc/tests/float_bits.test.cc",
        root / "src/hwacc/native_helpers.test.cc",
    ]
    excluded = ["src/hwacc/fu_scheduling_pool.test.cc"]
    if generated is not None:
        sources.append(root / excluded.pop())
    expected_tests = 30 if generated is not None else 26
    gtest = root / "ext/googletest/googletest"
    translation_units = sources + [
        gtest / "src/gtest-all.cc",
        gtest / "src/gtest_main.cc",
    ]
    if generated is not None:
        # Existing gem5 GTest support, including SimpleFlag initialization.
        translation_units.extend(
            root / item
            for item in (
                "src/base/debug.cc",
                "src/base/cprintf.cc",
                "src/base/gtest/logging.cc",
                "src/base/gtest/logging_mock.cc",
            )
        )
    includes = [root / "src", root / "ext", gtest / "include", gtest]
    if generated is not None:
        includes.append(generated)
    flags = [
        "-std=c++20",
        "-O1",
        "-g",
        "-fsanitize=address,undefined",
        "-fno-omit-frame-pointer",
        "-D_GLIBCXX_DEBUG",
        "-DTRACING_ON=1",
        "-pthread",
    ] + ["-I" + str(path) for path in includes]
    receipt = {
        "state": "failed",
        "scope": "production-helper GTests; no simulator execution",
        "expected_tests": expected_tests,
        "excluded_test_sources": excluded,
        "generated_headers": str(generated) if generated else None,
        "compiler": str(compiler),
        "compiler_sha256": digest(compiler),
        "script": {
            "path": str(Path(__file__).resolve()),
            "sha256": digest(Path(__file__).resolve()),
        },
        "commands": [],
        "sanitizers": ["address", "undefined"],
        "checked_stl": True,
        "started_unix_seconds": time.time(),
    }
    exit_code = 1
    try:
        code, version = execute(
            [str(compiler), "--version"], root, args.timeout_seconds
        )
        if code:
            raise RuntimeError("Compiler version query failed")
        receipt["compiler_version"] = version
        dependencies = set(translation_units)
        for index, source in enumerate(translation_units):
            command = (
                [str(compiler)]
                + flags
                + [
                    "-MM",
                    "-MT",
                    "salam_native_" + str(index),
                    str(source),
                ]
            )
            code, log = execute(command, root, args.timeout_seconds)
            receipt["commands"].append({"argv": command, "exit": code})
            if code:
                (output / "dependencies.log").write_text(log)
                raise RuntimeError("Compiler dependency scan failed")
            _, separator, tail = log.replace("\\\n", "").partition(":")
            if not separator:
                raise RuntimeError("Malformed compiler dependency output")
            for item in shlex.split(tail):
                dependency = Path(item)
                if not dependency.is_absolute():
                    dependency = root / dependency
                dependencies.add(dependency.resolve())
        before = {str(path): digest(path) for path in sorted(dependencies)}
        receipt["source_sha256"] = before
        binary = output / "salam-native-helpers-sanitized"
        command = (
            [str(compiler)]
            + flags
            + [str(path) for path in translation_units]
            + ["-o", str(binary)]
        )
        code, log = execute(command, root, args.timeout_seconds)
        (output / "compile.log").write_text(log)
        receipt["commands"].append({"argv": command, "exit": code})
        if code:
            raise RuntimeError("Native helper compilation failed")
        if before != {path: digest(Path(path)) for path in before}:
            raise RuntimeError("A compiler input changed during compilation")
        receipt["binary_sha256"] = digest(binary)
        environment = dict(os.environ)
        environment.update(
            ASAN_OPTIONS="detect_leaks=1:halt_on_error=1",
            UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1",
        )
        receipt["run_environment"] = {
            name: environment[name] for name in ("ASAN_OPTIONS", "UBSAN_OPTIONS")
        }
        command = [str(binary), "--gtest_output=xml:" + str(output / "gtest.xml")]
        code, log = execute(command, root, args.timeout_seconds, environment)
        (output / "tests.log").write_text(log)
        receipt["commands"].append({"argv": command, "exit": code})
        if code:
            raise RuntimeError("Native helper tests or sanitizers failed")
        xml_path = output / "gtest.xml"
        result = ET.parse(xml_path).getroot()
        tests = int(result.attrib.get("tests", 0))
        failures = int(result.attrib.get("failures", 0))
        errors = int(result.attrib.get("errors", 0))
        if tests != expected_tests or failures or errors:
            raise RuntimeError("Unexpected GTest XML totals")
        receipt.update(
            state="passed",
            tests=tests,
            failures=failures,
            errors=errors,
            xml_sha256=digest(xml_path),
        )
        exit_code = 0
    except (
        OSError,
        RuntimeError,
        ValueError,
        subprocess.TimeoutExpired,
        ET.ParseError,
    ) as error:
        receipt["error"] = str(error)
    finally:
        receipt["ended_unix_seconds"] = time.time()
        (output / "validation.json").write_text(
            json.dumps(receipt, indent=2, allow_nan=False) + "\n"
        )
    print(
        json.dumps(
            {
                "state": receipt["state"],
                "tests": receipt.get("tests"),
                "excluded_test_sources": excluded,
                "receipt": str(output / "validation.json"),
                "error": receipt.get("error"),
            }
        )
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
