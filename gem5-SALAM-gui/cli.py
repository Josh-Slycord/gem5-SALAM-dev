#!/usr/bin/env python3
"""
gem5-SALAM Installer CLI

Command-line interface for gem5-SALAM operations including:
- Running simulations
- Generating configurations
- Building benchmarks
- Checking WSL status
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from utils.wsl import get_wsl_status


def get_m5_path(distro: str) -> str:
    """Extract M5_PATH from WSL environment."""
    cmd = (
        "grep -h 'export M5_PATH=' ~/.bashrc ~/.profile 2>/dev/null | "
        "tail -1 | sed 's/.*M5_PATH=[\"]*\\([^\"]*\\)[\"]*$/\\1/'"
    )
    try:
        result = subprocess.run(
            ['wsl', '-d', distro, 'bash', '-c', cmd],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"Error getting M5_PATH: {e}")
        return ""


def cmd_status(args):
    """Check WSL and environment status."""
    print("==> Checking WSL Status...")
    status = get_wsl_status()

    print(f"WSL Installed: {status.installed}")
    if status.version:
        print(f"WSL Version: {status.version.split(chr(10))[0]}")

    print(f"\nAvailable Distributions:")
    for distro in status.distros:
        default = " [default]" if distro.is_default else ""
        print(f"  - {distro.name} (WSL{distro.version}){default}")

    if args.distro:
        distro = args.distro
    elif status.distros:
        distro = status.distros[0].name
    else:
        print("\nNo WSL distributions found!")
        return 1

    print(f"\n==> Checking M5_PATH in {distro}...")
    m5_path = get_m5_path(distro)
    if m5_path:
        print(f"M5_PATH: {m5_path}")
    else:
        print("M5_PATH: Not set")
        print("  Run: export M5_PATH=/path/to/gem5-SALAM-dev")

    return 0


def cmd_simulate(args):
    """Run a gem5-SALAM simulation."""
    distro = args.distro
    benchmark = args.benchmark
    build_type = args.build or "opt"
    num_cpus = args.cpus or 1
    use_sysval = args.sysval  # Use systemValidation.sh style

    # Get M5_PATH
    m5_path = get_m5_path(distro)
    if not m5_path:
        print("Error: M5_PATH not set in WSL environment")
        return 1

    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bench_name_clean = benchmark.replace("/", "_").replace("\\", "_")
    outdir = f"{m5_path}/BM_ARM_OUT/sys_validation/{benchmark}" if use_sysval else f"{m5_path}/m5out/{bench_name_clean}_{timestamp}"

    # Build gem5 binary path
    gem5_binary = f"{m5_path}/build/ARM/gem5.{build_type}"

    if use_sysval:
        # Use GENERATED config (bare-metal mode - matches systemValidation.sh)
        # The generated config fs_{benchmark}.py has proper accelerator setup
        config_script = f"configs/SALAM/generated/fs_{benchmark}.py"
        kernel = f"{m5_path}/benchmarks/sys_validation/{benchmark}/sw/main.elf"

        # Build bare-metal simulation command (matches systemValidation.sh)
        sys_opts = (
            f"--mem-size=4GB "
            f"--mem-type=DDR4_2400_8x8 "
            f"--kernel={kernel} "
            f"--disk-image={m5_path}/baremetal/common/fake.iso "
            f"--machine-type=VExpress_GEM5_V1 "
            f"--dtb-file=none --bare-metal "
            f"--cpu-type=DerivO3CPU"
        )
        cache_opts = "--caches --l2cache"

        sim_cmd = (
            f"cd '{m5_path}' && "
            f"export M5_PATH='{m5_path}' && "
            f"'{gem5_binary}' "
            f"--outdir='{outdir}' "
            f"'{m5_path}/{config_script}' "
            f"{sys_opts} "
            f"--accpath='{m5_path}/benchmarks/sys_validation' "
            f"--accbench='{benchmark}' "
            f"{cache_opts}"
        )
    else:
        # Standard full-system mode
        config_script = args.config or "configs/SALAM/fs_hwacc.py"

        sim_cmd = (
            f"cd '{m5_path}' && "
            f"export M5_PATH='{m5_path}' && "
            f"'{gem5_binary}' "
            f"--outdir='{outdir}' "
            f"'{m5_path}/{config_script}' "
            f"--num-cpus={num_cpus}"
        )

        # Add benchmark-specific options
        bench_parts = benchmark.split("/")
        if len(bench_parts) >= 2:
            bench_dir = "/".join(bench_parts[:-1])
            bench_name = bench_parts[-1]
            sim_cmd += f" --accpath='{m5_path}/benchmarks/{bench_dir}'"
            sim_cmd += f" --accbench='{bench_name}'"
        else:
            sim_cmd += f" --accpath='{m5_path}/benchmarks/sys_validation'"
            sim_cmd += f" --accbench='{benchmark}'"

    # Add any extra arguments
    if args.extra:
        sim_cmd += f" {args.extra}"

    print("==> gem5-SALAM Simulation")
    print(f"[INFO] Distro: {distro}")
    print(f"[INFO] gem5 binary: {gem5_binary}")
    print(f"[INFO] Config script: {config_script}")
    print(f"[INFO] Benchmark: {benchmark}")
    print(f"[INFO] Mode: {'bare-metal (sysval)' if use_sysval else 'full-system'}")
    print(f"[INFO] Output directory: {outdir}")
    print()
    print("==> Running simulation...")
    print(f"[INFO] Command: {sim_cmd}")
    print()

    # Run the simulation
    try:
        process = subprocess.Popen(
            ['wsl', '-d', distro, 'bash', '-c', sim_cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Stream output in real-time
        for line in process.stdout:
            print(line, end='')

        process.wait()

        if process.returncode == 0:
            print()
            print(f"[OK] Simulation completed successfully")
            print(f"  Output: {outdir}")
            return 0
        else:
            print()
            print(f"[FAIL] Simulation failed with exit code {process.returncode}")
            return process.returncode

    except KeyboardInterrupt:
        print("\n\nSimulation interrupted by user")
        process.terminate()
        return 130
    except Exception as e:
        print(f"Error running simulation: {e}")
        return 1


def cmd_generate(args):
    """Generate configuration files for a benchmark."""
    distro = args.distro
    benchmark = args.benchmark
    bench_dir = args.bench_dir or "benchmarks/sys_validation"
    cycle_time = args.cycle_time or "5ns"

    # Get M5_PATH
    m5_path = get_m5_path(distro)
    if not m5_path:
        print("Error: M5_PATH not set in WSL environment")
        return 1

    # Build the CLI command
    cli_cmd = (
        f"export M5_PATH='{m5_path}' && "
        f"export PYTHONPATH='{m5_path}':$PYTHONPATH && "
        f"cd '{m5_path}' && python3 -m salam_config.cli generate "
        f"-b '{benchmark}' "
        f"-d '{bench_dir}' "
        f"--cycle-time '{cycle_time}' "
        f"-v"
    )

    print("==> Generating Configuration")
    print(f"[INFO] Distro: {distro}")
    print(f"[INFO] Benchmark: {benchmark}")
    print(f"[INFO] Bench dir: {bench_dir}")
    print(f"[INFO] Cycle time: {cycle_time}")
    print()

    try:
        result = subprocess.run(
            ['wsl', '-d', distro, 'bash', '-c', cli_cmd],
            capture_output=True, text=True, timeout=60
        )

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        if result.returncode == 0:
            print("[OK] Generation completed successfully")
        else:
            print(f"[FAIL] Generation failed with exit code {result.returncode}")

        return result.returncode

    except subprocess.TimeoutExpired:
        print("Error: Generation timed out")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_build(args):
    """Build a benchmark."""
    distro = args.distro
    benchmark = args.benchmark

    # Get M5_PATH
    m5_path = get_m5_path(distro)
    if not m5_path:
        print("Error: M5_PATH not set in WSL environment")
        return 1

    # Determine benchmark path
    bench_path = f"{m5_path}/benchmarks/sys_validation/{benchmark}"

    build_cmd = f"cd '{bench_path}' && make clean && make"

    print("==> Building Benchmark")
    print(f"[INFO] Distro: {distro}")
    print(f"[INFO] Benchmark: {benchmark}")
    print(f"[INFO] Path: {bench_path}")
    print()

    try:
        process = subprocess.Popen(
            ['wsl', '-d', distro, 'bash', '-c', build_cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        for line in process.stdout:
            print(line, end='')

        process.wait()

        if process.returncode == 0:
            print()
            print("[OK] Build completed successfully")
        else:
            print()
            print(f"[FAIL] Build failed with exit code {process.returncode}")

        return process.returncode

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_list_benchmarks(args):
    """List available benchmarks."""
    distro = args.distro

    # Get M5_PATH
    m5_path = get_m5_path(distro)
    if not m5_path:
        print("Error: M5_PATH not set in WSL environment")
        return 1

    print("==> Available Benchmarks")
    print()

    # List sys_validation benchmarks
    list_cmd = f"ls -1 '{m5_path}/benchmarks/sys_validation/' 2>/dev/null | grep -v '^common$'"

    try:
        result = subprocess.run(
            ['wsl', '-d', distro, 'bash', '-c', list_cmd],
            capture_output=True, text=True
        )

        if result.stdout:
            print("sys_validation benchmarks:")
            for bench in result.stdout.strip().split('\n'):
                if bench:
                    print(f"  - {bench}")

        # List legacy benchmarks
        list_cmd = f"ls -1 '{m5_path}/benchmarks/legacy/' 2>/dev/null"
        result = subprocess.run(
            ['wsl', '-d', distro, 'bash', '-c', list_cmd],
            capture_output=True, text=True
        )

        if result.stdout:
            print("\nlegacy benchmarks:")
            for bench in result.stdout.strip().split('\n'):
                if bench:
                    print(f"  - legacy/{bench}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_shell(args):
    """Open an interactive shell in WSL with M5_PATH set."""
    distro = args.distro

    m5_path = get_m5_path(distro)
    if not m5_path:
        print("Warning: M5_PATH not set")
        shell_cmd = "bash"
    else:
        shell_cmd = f"export M5_PATH='{m5_path}' && cd '{m5_path}' && bash"

    print(f"Opening shell in {distro}...")
    if m5_path:
        print(f"M5_PATH={m5_path}")
    print()

    os.system(f'wsl -d {distro} bash -c "{shell_cmd}"')
    return 0




def cmd_install_optional(args):
    """Install optional dependencies for visualization and debugging."""
    distro = args.distro
    
    print("==> Installing Optional Dependencies")
    print("    Graphviz, pydot, valgrind for visualization")
    
    install_python = args.python or args.all
    install_system = args.system or args.all
    
    if not install_python and not install_system:
        print("Specify what to install:")
        print("  --python    Install Python packages")
        print("  --system    Install system packages")
        print("  --all       Install all")
        return 1
    
    if install_python:
        print("[1/2] Installing Python packages...")
        for pkg in ["pydot", "graphviz"]:
            print(f"  Installing {pkg}...", end=" ", flush=True)
            try:
                result = subprocess.run(
                    ["wsl", "-d", distro, "pip3", "install", "--user", pkg],
                    capture_output=True, text=True, timeout=120
                )
                print("OK" if result.returncode == 0 else "FAILED")
            except Exception as e:
                print(f"ERROR: {e}")
    
    if install_system:
        print("[2/2] Installing system packages (requires sudo)...")
        try:
            result = subprocess.run(
                ["wl", "-d", distro, "sudo", "apt-get", "install", "-y", "graphviz", "valgrind"],
                capture_output=True, text=True, timeout=300
            )
            print("  System packages installed" if result.returncode == 0 else "  Warning: apt may have failed")
        except Exception as e:
            print(f"  Error: {e}")
    
    print("")
    print("==> Verifying...")
    for cmd, name in [("dot -V", "graphviz"), ("valgrind --version", "valgrind")]:
        try:
            result = subprocess.run(
                ["wsl", "-d", distro, "bash", "-c", cmd],
                capture_output=True, text=True, timeout=10
            )
            print(f"  [OK] {name}" if result.returncode == 0 else f"  [--] {name}")
        except:
            print(f"  [??] {name}")
    
    print("Done!")
    return 0



def main():
    parser = argparse.ArgumentParser(
        description="gem5-SALAM Installer CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check WSL status
  python cli.py status

  # List available benchmarks
  python cli.py list -d Ubuntu-20.04

  # Generate config for gemm benchmark
  python cli.py generate -d Ubuntu-20.04 -b gemm

  # Run simulation
  python cli.py simulate -d Ubuntu-20.04 -b legacy/gemm

  # Run simulation with custom config
  python cli.py simulate -d Ubuntu-20.04 -b gemm -c configs/SALAM/sys_validation.py

  # Build a benchmark
  python cli.py build -d Ubuntu-20.04 -b gemm

  # Open WSL shell with M5_PATH set
  python cli.py shell -d Ubuntu-20.04
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # status command
    status_parser = subparsers.add_parser("status", help="Check WSL and environment status")
    status_parser.add_argument("-d", "--distro", help="WSL distribution to check")

    # simulate command
    sim_parser = subparsers.add_parser("simulate", aliases=["sim", "run"],
                                        help="Run a gem5-SALAM simulation")
    sim_parser.add_argument("-d", "--distro", required=True, help="WSL distribution")
    sim_parser.add_argument("-b", "--benchmark", required=True, help="Benchmark name (e.g., gemm, legacy/gemm)")
    sim_parser.add_argument("-c", "--config", help="Config script (default: configs/SALAM/fs_hwacc.py)")
    sim_parser.add_argument("--build", choices=["opt", "debug", "fast"], default="opt",
                           help="gem5 build type (default: opt)")
    sim_parser.add_argument("--cpus", type=int, default=1, help="Number of CPUs (default: 1)")
    sim_parser.add_argument("--sysval", action="store_true",
                           help="Use systemValidation.sh style (bare-metal mode)")
    sim_parser.add_argument("--extra", help="Extra arguments to pass to config script")

    # generate command
    gen_parser = subparsers.add_parser("generate", aliases=["gen"],
                                        help="Generate configuration files")
    gen_parser.add_argument("-d", "--distro", required=True, help="WSL distribution")
    gen_parser.add_argument("-b", "--benchmark", required=True, help="Benchmark name")
    gen_parser.add_argument("--bench-dir", default="benchmarks/sys_validation",
                           help="Benchmark directory (default: benchmarks/sys_validation)")
    gen_parser.add_argument("--cycle-time", default="5ns",
                           choices=["1ns", "2ns", "3ns", "4ns", "5ns", "6ns", "10ns"],
                           help="Cycle time (default: 5ns)")

    # build command
    build_parser = subparsers.add_parser("build", help="Build a benchmark")
    build_parser.add_argument("-d", "--distro", required=True, help="WSL distribution")
    build_parser.add_argument("-b", "--benchmark", required=True, help="Benchmark name")

    # list command
    list_parser = subparsers.add_parser("list", help="List available benchmarks")
    list_parser.add_argument("-d", "--distro", required=True, help="WSL distribution")

    # shell command
    shell_parser = subparsers.add_parser("shell", help="Open WSL shell with M5_PATH set")
    shell_parser.add_argument("-d", "--distro", required=True, help="WSL distribution")

    # install-optional command
    opt_parser = subparsers.add_parser("install-optional", aliases=["install-opt"],
                                        help="Install optional dependencies (graphviz, valgrind, pydot)")
    opt_parser.add_argument("-d", "--distro", required=True, help="WSL distribution")
    opt_parser.add_argument("--python", action="store_true", help="Install Python packages only")
    opt_parser.add_argument("--system", action="store_true", help="Install system packages only")
    opt_parser.add_argument("--all", action="store_true", help="Install all optional dependencies")


    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Route to appropriate command
    commands = {
        "status": cmd_status,
        "simulate": cmd_simulate,
        "sim": cmd_simulate,
        "run": cmd_simulate,
        "generate": cmd_generate,
        "gen": cmd_generate,
        "build": cmd_build,
        "list": cmd_list_benchmarks,
        "shell": cmd_shell,
        "install-optional": cmd_install_optional,
        "install-opt": cmd_install_optional,
    }

    if args.command in commands:
        return commands[args.command](args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())

