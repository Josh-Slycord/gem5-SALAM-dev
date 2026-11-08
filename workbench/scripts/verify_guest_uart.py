#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Verify the bare-metal UART hook with fresh, source-bound guest evidence.

Guest objects are built only inside the new evidence directory. Host checks
compare exact UART bytes and the expected simulator exit; errno/zero-length
cases remain guest assertions, identified explicitly in the receipt.
"""

import argparse
import datetime
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_BYTES = b"[TEST_OK][NUL\x00OK]\nGUEST_UART_CONTRACT_PASSED\n"
EXPECTED_EXIT_REASON = "m5_exit instruction encountered"
MAX_TERMINAL_BYTES = 1024 * 1024


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while True:
            chunk = source.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _record(path):
    path = Path(path)
    return {
        "path": str(path),
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
    }


def _save(path, value):
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _bytes(value):
    if value is None:
        return b""
    return value if isinstance(value, bytes) else value.encode("utf-8", "replace")


def _exit_witness(stdout):
    """Require one actual gem5 exit line, not an earlier textual mention."""
    lines = _bytes(stdout).decode("utf-8", "replace").splitlines()
    exits = [line for line in lines if line.startswith("Exiting ")]
    match = (
        re.fullmatch(r"Exiting @ tick ([0-9]+) because (.+)", exits[0])
        if len(exits) == 1
        else None
    )
    passed = match is not None and match.group(2) == EXPECTED_EXIT_REASON
    return {
        "state": "passed" if passed else "failed",
        "expected_reason": EXPECTED_EXIT_REASON,
        "exit_lines": exits,
        "exit_line_count": len(exits),
        "tick": int(match.group(1)) if match is not None else None,
        "reason": match.group(2) if match is not None else None,
    }


def _timeout(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(name + " must be a positive finite number")
    return value


def _input(repo_root, relative):
    path = Path(relative)
    if not path.is_absolute():
        path = repo_root / path
    resolved = path.resolve(strict=True)
    resolved.relative_to(repo_root)
    if resolved != path or not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(
            "UART source input must be ordinary contained data: " + str(path)
        )
    return path


def _tools(prefix):
    result = {}
    for role in ("cpp", "as", "gcc"):
        command = shutil.which(prefix + role)
        if command is None:
            raise FileNotFoundError("Missing ARM tool: " + prefix + role)
        result[role] = Path(command).absolute()
    return result


def _command(argv, cwd, directory, label, timeout, commands, env=None):
    number = len(commands) + 1
    logs = directory / "commands"
    logs.mkdir(exist_ok=True)
    stdout_path = logs / ("%02d-%s.stdout" % (number, label))
    stderr_path = logs / ("%02d-%s.stderr" % (number, label))
    item = {
        "label": label,
        "argv": [str(value) for value in argv],
        "cwd": str(cwd),
        "timeout_seconds": timeout,
        "started_utc": _now(),
        "state": "running",
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }
    commands.append(item)
    started = time.monotonic()
    try:
        result = subprocess.run(
            item["argv"],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        stdout_path.write_bytes(_bytes(error.stdout))
        stderr_path.write_bytes(_bytes(error.stderr))
        item.update(
            state="timed_out",
            returncode=None,
            elapsed_seconds=time.monotonic() - started,
        )
        raise
    except OSError as error:
        stdout_path.write_bytes(b"")
        stderr_path.write_bytes(str(error).encode("utf-8", "replace"))
        item.update(
            state="failed",
            returncode=None,
            elapsed_seconds=time.monotonic() - started,
        )
        raise
    stdout_path.write_bytes(_bytes(result.stdout))
    stderr_path.write_bytes(_bytes(result.stderr))
    item.update(
        state="passed" if result.returncode == 0 else "failed",
        returncode=result.returncode,
        elapsed_seconds=time.monotonic() - started,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "UART command %s failed with code %s; see %s"
            % (label, result.returncode, stderr_path)
        )
    return result


def run_verification(
    repo_root=REPO_ROOT,
    outdir=None,
    *,
    simulator=None,
    config_script="configs/SALAM/generated/fs_gemm.py",
    toolchain_prefix="arm-none-eabi-",
    timeout_seconds=120,
    build_timeout_seconds=60,
    cpu_type="ArmO3CPU",
):
    """Return a passed/failed/timed_out receipt; never reuse run artifacts.

    repo_root may be an independently prepared workspace. simulator can point
    to a separately qualified binary; this verifier records its identity but
    does not establish a new C++ build qualification.
    """
    repo_root = Path(repo_root).resolve(strict=True)
    if not repo_root.is_dir():
        raise ValueError("repo_root must be a directory")
    if not isinstance(cpu_type, str) or not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9_]*", cpu_type
    ):
        raise ValueError("cpu_type must be a bare gem5 CPU identifier")
    _timeout(timeout_seconds, "timeout_seconds")
    _timeout(build_timeout_seconds, "build_timeout_seconds")
    if outdir is None:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
        outdir = (
            repo_root
            / "evidence"
            / ("uart-regression-" + stamp + "-" + uuid.uuid4().hex[:8])
        )
    directory = Path(outdir).resolve()
    # This deliberately refuses even an empty existing directory.
    directory.mkdir(parents=True, exist_ok=False)
    receipt_path = directory / "guest_uart_regression_receipt.json"
    receipt = {
        "schema_version": 2,
        "kind": "guest_uart_regression",
        "state": "running",
        "started_utc": _now(),
        "repo_root": str(repo_root),
        "requested_cpu_type": cpu_type,
        "evidence_directory": str(directory),
        "wsl_distribution": os.environ.get("WSL_DISTRO_NAME"),
        "commands": [],
        "source_files": {},
        "errors": [],
        "checks": {"fresh_evidence_directory": True},
        "claim_boundary": (
            "Host checks exact UART bytes and simulator exit. Argument/errno "
            "cases are guest assertions gated by the fresh pass marker. "
            "This is not simulator-wide or independent hardware qualification."
        ),
    }
    _save(receipt_path, receipt)
    identities = {}
    try:
        binary = Path(simulator) if simulator else repo_root / "build/ARM/gem5.opt"
        binary = binary.resolve(strict=True)
        if not binary.is_file():
            raise FileNotFoundError("Simulator binary missing: " + str(binary))
        receipt["simulator_binary"] = _record(binary)
        identities["simulator_binary"] = receipt["simulator_binary"]

        sw = repo_root / "benchmarks/sys_validation/gemm/sw"
        inputs = {
            "syscalls": _input(repo_root, "benchmarks/common/syscalls.c"),
            "guest_regression": _input(
                repo_root, "benchmarks/common/guest_uart_regression.c"
            ),
            "boot_assembly": _input(repo_root, sw / "boot.s"),
            "linker_script": _input(repo_root, sw / "boot.ld"),
            "board_configuration": _input(repo_root, config_script),
            "disk_image": _input(repo_root, "baremetal/common/fake.iso"),
        }
        for role, path in inputs.items():
            receipt["source_files"][role] = _record(path)
            identities[role] = receipt["source_files"][role]
        receipt["syscalls_source"] = receipt["source_files"]["syscalls"]
        tools = _tools(toolchain_prefix)
        receipt["toolchain"] = {role: _record(path) for role, path in tools.items()}
        for role, record in receipt["toolchain"].items():
            identities["tool_" + role] = record
        for role, path in tools.items():
            _command(
                [path, "--version"],
                repo_root,
                directory,
                role + "-version",
                build_timeout_seconds,
                receipt["commands"],
            )

        build = directory / "build"
        build.mkdir()
        boot_pp = build / "boot.preprocessed.s"
        boot_o = build / "boot.o"
        syscalls_o = build / "syscalls.o"
        guest_o = build / "guest_uart_regression.o"
        guest_elf = build / "guest_uart_regression.elf"
        commands = (
            (
                "boot-cpp",
                [
                    tools["cpp"],
                    inputs["boot_assembly"],
                    "-g",
                    "-O3",
                    "-fcommon",
                    "-I",
                    sw,
                    "-o",
                    boot_pp,
                ],
                sw,
            ),
            (
                "boot-as",
                [tools["as"], "-EL", "-o", boot_o, boot_pp],
                build,
            ),
            (
                "compile-syscalls",
                [
                    tools["gcc"],
                    "-g",
                    "-O3",
                    "-fcommon",
                    "-I",
                    repo_root / "benchmarks/common",
                    "-c",
                    inputs["syscalls"],
                    "-o",
                    syscalls_o,
                ],
                build,
            ),
            (
                "compile-guest",
                [
                    tools["gcc"],
                    "-g",
                    "-O2",
                    "-I",
                    repo_root / "benchmarks/common",
                    "-c",
                    inputs["guest_regression"],
                    "-o",
                    guest_o,
                ],
                build,
            ),
            (
                "link-guest",
                [
                    tools["gcc"],
                    "-nostartfiles",
                    "-Xlinker",
                    "-T" + str(inputs["linker_script"]),
                    "-o",
                    guest_elf,
                    syscalls_o,
                    guest_o,
                ],
                build,
            ),
        )
        for label, argv, cwd in commands:
            _command(
                argv,
                cwd,
                directory,
                label,
                build_timeout_seconds,
                receipt["commands"],
            )
        receipt["guest_test_binary"] = _record(guest_elf)
        identities["guest_test_binary"] = receipt["guest_test_binary"]
        simulation_dir = directory / "simulator"
        if simulation_dir.exists():
            raise ValueError("Simulator output directory already exists")
        argv = [
            binary,
            "--outdir=" + str(simulation_dir),
            inputs["board_configuration"],
            "--mem-size=4GB",
            "--mem-type=DDR4_2400_8x8",
            "--kernel=" + str(guest_elf),
            "--disk-image=" + str(inputs["disk_image"]),
            "--machine-type=VExpress_GEM5_V1",
            "--dtb-file=none",
            "--bare-metal",
            "--cpu-type=" + cpu_type,
            "--accpath=" + str(repo_root / "benchmarks/sys_validation"),
            "--accbench=gemm",
            "--caches",
            "--l2cache",
        ]
        env = dict(os.environ)
        env["M5_PATH"] = str(repo_root)
        result = _command(
            argv,
            repo_root,
            directory,
            "simulate",
            timeout_seconds,
            receipt["commands"],
            env=env,
        )
        terminal = simulation_dir / "system.terminal"
        if terminal.resolve(strict=True) != terminal or not stat.S_ISREG(
            terminal.lstat().st_mode
        ):
            raise ValueError("Fresh UART output is not an ordinary terminal file")
        if terminal.stat().st_size > MAX_TERMINAL_BYTES:
            raise ValueError("UART output exceeds the bounded regression size")
        raw = terminal.read_bytes()
        receipt["simulator_exit"] = _exit_witness(result.stdout)
        expected_exit = receipt["simulator_exit"]["state"] == "passed"
        marker = b"GUEST_UART_CONTRACT_PASSED\n" in raw
        receipt["terminal_output"] = dict(
            _record(terminal), raw_repr=repr(raw), hex=raw.hex()
        )
        receipt["checks"].update(
            exact_bytes_match=raw == EXPECTED_BYTES,
            contains_passed_marker=marker,
            canary_bytes_not_emitted=b"CANARY" not in raw,
            embedded_nul_preserved=b"[NUL\x00OK]" in raw,
            expected_simulator_exit=expected_exit,
        )
        guest_assertions_completed = marker and expected_exit
        receipt["guest_assertions"] = {
            "state": "completed" if guest_assertions_completed else "not_completed",
            "evidence": "Fresh guest pass marker and expected simulator exit",
            "cases": [
                "bounded non-terminated slice and return length",
                "embedded NUL across requested length",
                "zero length with null and invalid pointers",
                "negative length EINVAL",
                "null positive-length buffer EFAULT",
            ],
            "independent_host_observations": False,
        }
        if not all(receipt["checks"].values()):
            raise ValueError("Fresh UART output or expected exit contract failed")
        receipt["state"] = "passed"
    except subprocess.TimeoutExpired as error:
        receipt["state"] = "timed_out"
        receipt["errors"].append(
            "TimeoutExpired: command exceeded %s seconds" % error.timeout
        )
    except Exception as error:
        receipt["state"] = "failed"
        receipt["errors"].append(type(error).__name__ + ": " + str(error))
    finally:
        changed = []
        for role, identity in identities.items():
            path = Path(identity["path"])
            try:
                if file_sha256(path) != identity["sha256"]:
                    changed.append(role)
            except OSError:
                changed.append(role)
        receipt["checks"]["recorded_inputs_unchanged"] = not changed
        if changed:
            receipt["state"] = "failed"
            receipt["errors"].append("Recorded inputs changed: " + ", ".join(changed))
        receipt["finished_utc"] = _now()
        _save(receipt_path, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--outdir")
    parser.add_argument("--simulator")
    parser.add_argument("--config-script", default="configs/SALAM/generated/fs_gemm.py")
    parser.add_argument("--toolchain-prefix", default="arm-none-eabi-")
    parser.add_argument("--cpu-type", default="ArmO3CPU")
    parser.add_argument("--timeout-seconds", type=float, default=120)
    parser.add_argument("--build-timeout-seconds", type=float, default=60)
    args = parser.parse_args()
    try:
        receipt = run_verification(
            args.repo_root,
            args.outdir,
            simulator=args.simulator,
            config_script=args.config_script,
            toolchain_prefix=args.toolchain_prefix,
            timeout_seconds=args.timeout_seconds,
            build_timeout_seconds=args.build_timeout_seconds,
            cpu_type=args.cpu_type,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["state"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
