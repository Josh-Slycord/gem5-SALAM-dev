#!/usr/bin/env python3
"""
Validate generation of all sys_validation benchmarks.
Runs systembuilder.py with --validate-only to compare generated files
against existing files without modifying anything.
"""

import os
import subprocess
import sys
from pathlib import Path

# Benchmark configurations
SYS_VALIDATION_BENCHMARKS = [
    ('gemm', 'benchmarks/sys_validation/gemm'),
    ('bfs', 'benchmarks/sys_validation/bfs'),
    ('fft', 'benchmarks/sys_validation/fft'),
    ('md_knn', 'benchmarks/sys_validation/md_knn'),
    ('md_grid', 'benchmarks/sys_validation/md_grid'),
    ('mergesort', 'benchmarks/sys_validation/mergesort'),
    ('nw', 'benchmarks/sys_validation/nw'),
    ('spmv', 'benchmarks/sys_validation/spmv'),
    ('stencil2d', 'benchmarks/sys_validation/stencil2d'),
    ('stencil3d', 'benchmarks/sys_validation/stencil3d'),
]

def get_m5_path():
    """Get M5_PATH from environment or use default"""
    m5_path = os.environ.get('M5_PATH')
    if not m5_path:
        # Try to infer from script location
        script_dir = Path(__file__).parent
        if (script_dir.parent / 'configs').exists():
            m5_path = str(script_dir.parent)
    return m5_path

def validate_benchmark(sys_name, bench_dir, m5_path, verbose=False):
    """
    Validate a single benchmark.
    Returns: (success: bool, output: str)
    """
    script_path = Path(__file__).parent / 'systembuilder.py'
    
    cmd = [
        sys.executable,
        str(script_path),
        '--sysName', sys_name,
        '--benchDir', bench_dir,
        '--validate-only',
        '--path', m5_path
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        output = result.stdout + result.stderr
        success = result.returncode == 0
        
        return success, output
    
    except subprocess.TimeoutExpired:
        return False, "Validation timed out"
    except Exception as e:
        return False, f"Error: {str(e)}"

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Validate generation for all benchmarks')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    parser.add_argument('--benchmark', '-b', help='Validate specific benchmark only')
    parser.add_argument('--path', help='M5_PATH override')
    args = parser.parse_args()
    
    m5_path = args.path or get_m5_path()
    if not m5_path:
        print("ERROR: M5_PATH not set and could not be inferred")
        print("Set M5_PATH environment variable or use --path option")
        return 1
    
    print(f"Using M5_PATH: {m5_path}")
    print()
    
    benchmarks = SYS_VALIDATION_BENCHMARKS
    if args.benchmark:
        benchmarks = [(n, d) for n, d in benchmarks if n == args.benchmark]
        if not benchmarks:
            print(f"ERROR: Unknown benchmark '{args.benchmark}'")
            return 1
    
    results = []
    
    for sys_name, bench_dir in benchmarks:
        print(f"Validating {sys_name}...", end=' ', flush=True)
        
        success, output = validate_benchmark(sys_name, bench_dir, m5_path, args.verbose)
        
        if success:
            print("[OK]")
        else:
            print("[DIFF]")
        
        if args.verbose or not success:
            # Show relevant output
            for line in output.split('\n'):
                if line.startswith('[DIFF]') or line.startswith('[OK]') or line.startswith('[NEW]'):
                    print(f"  {line}")
                elif args.verbose and line.strip():
                    print(f"  {line}")
        
        results.append((sys_name, success, output))
    
    # Summary
    print()
    print("=" * 50)
    print("VALIDATION SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for _, s, _ in results if s)
    total = len(results)
    
    for sys_name, success, _ in results:
        status = "PASS" if success else "DIFF"
        print(f"  {sys_name:15} [{status}]")
    
    print()
    print(f"Passed: {passed}/{total}")
    
    if passed < total:
        print()
        print("Note: Differences may be due to whitespace changes (tabs vs spaces).")
        print("Review the diffs above to determine if changes are acceptable.")
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
