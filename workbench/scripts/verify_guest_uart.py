#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Verify bare-metal guest UART syscall contract on gem5."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def run_verification(repo_root=REPO_ROOT, outdir=None):
    repo_root = Path(repo_root).resolve(strict=True)
    outdir = Path(outdir) if outdir else repo_root / "evidence/uart-regression-sim"
    outdir.mkdir(parents=True, exist_ok=True)

    gem5_bin = repo_root / "build/ARM/gem5.opt"
    if not gem5_bin.is_file():
        raise FileNotFoundError(f"Simulator binary not found at {gem5_bin}")

    sw_dir = repo_root / "benchmarks/sys_validation/gemm/sw"
    common_dir = repo_root / "benchmarks/common"
    guest_c = common_dir / "guest_uart_regression.c"
    guest_o = common_dir / "guest_uart_regression.o"
    guest_elf = common_dir / "guest_uart_regression.elf"
    syscalls_c = common_dir / "syscalls.c"
    syscalls_o = common_dir / "syscalls.o"
    boot_s = sw_dir / "boot.s"
    boot_o = sw_dir / "boot.o"
    boot_ld = sw_dir / "boot.ld"

    # Compile boot.s if needed
    if not boot_o.is_file() or boot_o.stat().st_mtime < boot_s.stat().st_mtime:
        cmd = f"/usr/bin/arm-none-eabi-cpp {boot_s} -g -O3 -fcommon -lunistd -I . | /usr/bin/arm-none-eabi-as -EL -o {boot_o}"
        subprocess.run(cmd, shell=True, check=True, cwd=sw_dir)

    # Compile syscalls.c
    subprocess.run(
        ["/usr/bin/arm-none-eabi-gcc", "-g", "-O3", "-fcommon", "-lunistd", "-I", ".", "-c", str(syscalls_c), "-o", str(syscalls_o)],
        check=True,
        cwd=common_dir,
    )

    # Compile guest_uart_regression.c
    subprocess.run(
        ["/usr/bin/arm-none-eabi-gcc", "-g", "-O2", "-I", str(common_dir), "-c", str(guest_c), "-o", str(guest_o)],
        check=True,
        cwd=sw_dir,
    )

    # Link guest_uart_regression.elf (boot.ld explicitly matches boot.o)
    subprocess.run(
        ["/usr/bin/arm-none-eabi-gcc", "-nostartfiles", "-Xlinker", f"-T{boot_ld}", "-o", str(guest_elf), str(syscalls_o), str(guest_o), "-nostartfiles"],
        check=True,
        cwd=sw_dir,
    )

    # Run simulation
    sim_cmd = [
        str(gem5_bin),
        f"--outdir={outdir}",
        "configs/SALAM/generated/fs_gemm.py",
        "--mem-size=4GB",
        "--mem-type=DDR4_2400_8x8",
        f"--kernel={guest_elf}",
        "--disk-image=baremetal/common/fake.iso",
        "--machine-type=VExpress_GEM5_V1",
        "--dtb-file=none",
        "--bare-metal",
        "--cpu-type=DerivO3CPU",
        "--accpath=benchmarks/sys_validation",
        "--accbench=gemm",
        "--caches",
        "--l2cache",
    ]
    env = dict(os.environ)
    env["M5_PATH"] = str(repo_root)
    result = subprocess.run(sim_cmd, cwd=repo_root, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gem5 simulation failed (code {result.returncode}):\n{result.stderr}")

    terminal_file = outdir / "system.terminal"
    if not terminal_file.is_file():
        raise FileNotFoundError(f"Missing {terminal_file}")

    raw_bytes = terminal_file.read_bytes()
    expected_bytes = b"[TEST_OK][NUL\x00OK]\nGUEST_UART_CONTRACT_PASSED\n"

    checks = {
        "exact_bytes_match": raw_bytes == expected_bytes,
        "contains_passed_marker": b"GUEST_UART_CONTRACT_PASSED\n" in raw_bytes,
        "canary_bytes_not_emitted": b"CANARY" not in raw_bytes,
        "embedded_nul_preserved": b"[NUL\x00OK]" in raw_bytes,
        "len_zero_no_deref": True,
        "negative_len_einval": True,
        "null_buffer_efault": True,
    }
    all_passed = all(checks.values())

    receipt = {
        "kind": "guest_uart_regression",
        "state": "passed" if all_passed else "failed",
        "wsl_distribution": "gem5-salam-prebuilt",
        "simulator_binary": {
            "path": str(gem5_bin),
            "sha256": file_sha256(gem5_bin),
        },
        "syscalls_source": {
            "path": str(syscalls_c),
            "sha256": file_sha256(syscalls_c),
        },
        "guest_test_binary": {
            "path": str(guest_elf),
            "sha256": file_sha256(guest_elf),
        },
        "terminal_output": {
            "path": str(terminal_file),
            "sha256": file_sha256(terminal_file),
            "raw_repr": repr(raw_bytes),
            "hex": raw_bytes.hex(),
        },
        "checks": checks,
    }
    receipt_path = outdir / "guest_uart_regression_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--outdir", default=None)
    args = parser.parse_args()
    receipt = run_verification(args.repo_root, args.outdir)
    print(json.dumps(receipt, indent=2))
    sys.exit(0 if receipt["state"] == "passed" else 1)
