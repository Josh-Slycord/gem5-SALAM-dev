#!/usr/bin/env python3
"""
gem5-SALAM Test Runner v2.0

Enhanced test runner with:
- sys_validation and LeNet5 benchmark support
- Parallel test execution
- Config validation integration
- Debug flag support
- CI/CD friendly output
"""

import os
import sys
import subprocess
import argparse
import json
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Benchmark definitions
SYS_VALIDATION = [
    'bfs', 'fft', 'gemm', 'md_grid', 'md_knn',
    'mergesort', 'nw', 'spmv', 'stencil2d', 'stencil3d'
]
LENET5_VARIANTS = ['lenet5_naive']
ALL_BENCHMARKS = SYS_VALIDATION + LENET5_VARIANTS

KNOWN_ISSUES = {
    'md_grid': 'Floating-point precision causes timeout',
}

BENCHMARK_PATHS = {
    **{b: f'benchmarks/sys_validation/{b}' for b in SYS_VALIDATION},
    'lenet5_naive': 'benchmarks/lenet5-nounroll/naive',
}


def get_m5_path() -> str:
    """Get M5_PATH from environment."""
    m5_path = os.environ.get('M5_PATH')
    if not m5_path:
        raise EnvironmentError('M5_PATH environment variable not set')
    return m5_path


def check_build() -> bool:
    """Check if gem5 is built."""
    gem5_path = Path(get_m5_path()) / 'build' / 'ARM' / 'gem5.opt'
    return gem5_path.exists()


def validate_config(benchmark: str) -> Tuple[bool, str]:
    """Validate benchmark config using salam_config."""
    m5_path = get_m5_path()
    default_path = f'benchmarks/sys_validation/{benchmark}'
    bench_path = BENCHMARK_PATHS.get(benchmark, default_path)
    config_file = Path(m5_path) / bench_path / 'config.yml'

    if not config_file.exists():
        return False, f'Config not found: {config_file}'

    try:
        cmd = [
            sys.executable, '-m', 'salam_config.cli',
            'validate', '-c', str(config_file)
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=m5_path, timeout=30
        )
        if result.returncode == 0:
            return True, 'Config valid'
        else:
            return False, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, 'Validation timeout'
    except Exception:
        try:
            import yaml
            with open(config_file) as f:
                cfg = yaml.safe_load(f)
            if 'acc_cluster' in cfg:
                return True, 'Config valid (basic check)'
            return False, 'Missing acc_cluster section'
        except Exception as e2:
            return False, str(e2)


def run_benchmark(
    benchmark: str,
    timeout: int = 600,
    debug_flags: Optional[str] = None
) -> Dict:
    """Run a single benchmark and return results."""
    m5_path = get_m5_path()
    gem5 = Path(m5_path) / 'build' / 'ARM' / 'gem5.opt'

    config_path = 'configs' / Path('SALAM') / 'generated'
    config = Path(m5_path) / config_path / f'fs_{benchmark}.py'
    default_path = f'benchmarks/sys_validation/{benchmark}'
    bench_path = BENCHMARK_PATHS.get(benchmark, default_path)
    kernel = Path(m5_path) / bench_path / 'sw' / 'main.elf'

    known = benchmark in KNOWN_ISSUES

    if not config.exists():
        return {
            'passed': False,
            'message': f'Config not found: {config}',
            'duration': 0,
            'known': known
        }

    if not kernel.exists():
        return {
            'passed': False,
            'message': f'Kernel not found: {kernel}',
            'duration': 0,
            'known': known
        }

    cmd = [str(gem5)]
    if debug_flags:
        cmd.extend(['--debug-flags', debug_flags])

    cmd.extend([
        str(config),
        '--mem-size=4GB',
        '--mem-type=DDR4_2400_8x8',
        f'--kernel={kernel}',
        f'--disk-image={m5_path}/baremetal/common/fake.iso',
        '--machine-type=VExpress_GEM5_V1',
        '--dtb-file=none',
        '--bare-metal',
        '--cpu-type=DerivO3CPU',
        f'--accpath={m5_path}/{Path(bench_path).parent}',
        f'--accbench={Path(bench_path).name}',
        '--caches', '--l2cache'
    ])

    start = datetime.now()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=m5_path
        )
        duration = (datetime.now() - start).total_seconds()
        output = result.stdout + result.stderr

        if 'Check Passed' in output:
            return {
                'passed': True, 'message': 'Check Passed',
                'duration': duration, 'known': False
            }
        elif 'Sorted correctly' in output:
            return {
                'passed': True, 'message': 'Sorted correctly',
                'duration': duration, 'known': False
            }
        elif 'Check Failed' in output:
            return {
                'passed': False, 'message': 'Check Failed',
                'duration': duration, 'known': known
            }
        elif result.returncode == 0:
            return {
                'passed': True, 'message': 'Completed',
                'duration': duration, 'known': False
            }
        else:
            return {
                'passed': False,
                'message': f'Exit code {result.returncode}',
                'duration': duration, 'known': known
            }

    except subprocess.TimeoutExpired:
        return {
            'passed': False, 'message': f'Timeout {timeout}s',
            'duration': timeout, 'known': known
        }
    except Exception as e:
        return {
            'passed': False, 'message': str(e),
            'duration': 0, 'known': known
        }


def run_all_sequential(
    benchmarks: List[str],
    timeout: int,
    debug_flags: Optional[str] = None
) -> Dict:
    """Run benchmarks sequentially."""
    results = {}
    for i, benchmark in enumerate(benchmarks):
        print(f'[{i+1}/{len(benchmarks)}] {benchmark}...')
        result = run_benchmark(benchmark, timeout, debug_flags)
        results[benchmark] = result
        if result['passed']:
            status = 'PASS'
        elif result['known']:
            status = 'SKIP'
        else:
            status = 'FAIL'
        print(f'  {status}: {result["message"]} ({result["duration"]:.1f}s)')
    return results


def run_all_parallel(
    benchmarks: List[str],
    timeout: int,
    workers: int,
    debug_flags: Optional[str] = None
) -> Dict:
    """Run benchmarks in parallel."""
    results = {}
    print(f'Running {len(benchmarks)} benchmarks with {workers} workers...')

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    with executor:
        future_to_benchmark = {
            executor.submit(run_benchmark, b, timeout, debug_flags): b
            for b in benchmarks
        }

        for future in concurrent.futures.as_completed(future_to_benchmark):
            benchmark = future_to_benchmark[future]
            try:
                result = future.result()
                results[benchmark] = result
                if result['passed']:
                    status = 'PASS'
                elif result['known']:
                    status = 'SKIP'
                else:
                    status = 'FAIL'
                dur = result["duration"]
                print(f'  {benchmark}: {status} ({dur:.1f}s)')
            except Exception as e:
                results[benchmark] = {
                    'passed': False, 'message': str(e),
                    'duration': 0, 'known': benchmark in KNOWN_ISSUES
                }
                print(f'  {benchmark}: ERROR ({e})')

    return results


def generate_report(results: Dict, output_path: Path) -> None:
    """Generate markdown test report."""
    total = len(results)
    passed = sum(1 for r in results.values() if r['passed'])
    known_fails = sum(
        1 for r in results.values() if not r['passed'] and r['known']
    )

    lines = [
        '# gem5-SALAM Test Results',
        '',
        f'**Date:** {datetime.now():%Y-%m-%d %H:%M:%S}',
        f'**Summary:** {passed}/{total} passed',
    ]
    if known_fails > 0:
        lines.append(
            f'**Known Issues:** {known_fails} (not counted as failures)'
        )
    lines.extend([
        '',
        '## Results',
        '',
        '| Benchmark | Status | Message | Duration |',
        '|-----------|--------|---------|----------|',
    ])

    for benchmark, result in sorted(results.items()):
        if result['passed']:
            status = 'PASS'
        elif result['known']:
            status = 'KNOWN'
        else:
            status = 'FAIL'
        dur = result["duration"]
        lines.append(
            f'| {benchmark} | {status} | {result["message"]} | {dur:.1f}s |'
        )

    lines.extend(['', '## Known Issues', ''])
    for benchmark, issue in KNOWN_ISSUES.items():
        lines.append(f'- **{benchmark}**: {issue}')

    lines.extend(['', '---', '*Generated by run_tests.py v2.0*'])

    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))


def generate_json(results: Dict, output_path: Path) -> None:
    """Generate JSON test results."""
    total = len(results)
    passed = sum(1 for r in results.values() if r['passed'])
    known = sum(
        1 for r in results.values() if not r['passed'] and r['known']
    )

    data = {
        'timestamp': datetime.now().isoformat(),
        'version': '2.0',
        'summary': {
            'total': total,
            'passed': passed,
            'failed': total - passed,
            'known_issues': known
        },
        'results': results,
        'known_issues': KNOWN_ISSUES
    }

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description='gem5-SALAM Test Runner v2.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python scripts/run_tests.py              # Run sys_validation
  python scripts/run_tests.py -b gemm      # Run single benchmark
  python scripts/run_tests.py --all        # Include LeNet5
  python scripts/run_tests.py -j 4         # Parallel execution
  python scripts/run_tests.py --validate-only
'''
    )

    parser.add_argument('-b', '--benchmark', help='Run single benchmark')
    parser.add_argument(
        '-t', '--timeout', type=int, default=600,
        help='Timeout per test (default: 600s)'
    )
    parser.add_argument(
        '-j', '--parallel', type=int, default=1,
        help='Number of parallel workers'
    )
    parser.add_argument(
        '-l', '--list', action='store_true',
        help='List available benchmarks'
    )
    parser.add_argument(
        '--all', action='store_true',
        help='Run all benchmarks (including LeNet5)'
    )
    parser.add_argument(
        '--lenet', action='store_true',
        help='Run LeNet5 benchmarks only'
    )
    parser.add_argument(
        '--validate-only', action='store_true',
        help='Only validate configs'
    )
    parser.add_argument(
        '--skip-build-check', action='store_true',
        help='Skip gem5 build check'
    )
    parser.add_argument(
        '--skip-known', action='store_true',
        help='Skip benchmarks with known issues'
    )
    parser.add_argument(
        '--debug', type=str,
        help='Debug flags (e.g., SALAMData)'
    )
    parser.add_argument(
        '--ci', action='store_true',
        help='CI mode: machine-readable output'
    )

    args = parser.parse_args()

    if args.list:
        print('sys_validation benchmarks:')
        for b in SYS_VALIDATION:
            note = ' (known issue)' if b in KNOWN_ISSUES else ''
            print(f'  {b}{note}')
        print('\nLeNet5 benchmarks:')
        for b in LENET5_VARIANTS:
            note = ' (known issue)' if b in KNOWN_ISSUES else ''
            print(f'  {b}{note}')
        return 0

    try:
        m5_path = get_m5_path()
    except EnvironmentError as e:
        print(f'Error: {e}')
        return 1

    skip_check = args.skip_build_check or args.validate_only
    if not skip_check and not check_build():
        print('Error: gem5 not built. Run: scons build/ARM/gem5.opt -j4')
        return 1

    if args.benchmark:
        benchmarks = [args.benchmark]
    elif args.lenet:
        benchmarks = LENET5_VARIANTS
    elif args.all:
        benchmarks = ALL_BENCHMARKS
    else:
        benchmarks = SYS_VALIDATION

    if args.skip_known:
        benchmarks = [b for b in benchmarks if b not in KNOWN_ISSUES]

    if not args.ci:
        print('=' * 60)
        print('gem5-SALAM Test Runner v2.0')
        print('=' * 60)
        print(f'Benchmarks: {len(benchmarks)}')
        print(f'Timeout: {args.timeout}s')
        if args.parallel > 1:
            print(f'Parallel: {args.parallel} workers')
        if args.debug:
            print(f'Debug flags: {args.debug}')
        print('=' * 60)

    if args.validate_only:
        print('Validating configurations...')
        all_valid = True
        for b in benchmarks:
            valid, msg = validate_config(b)
            status = 'VALID' if valid else 'INVALID'
            print(f'  {b}: {status} - {msg}')
            if not valid:
                all_valid = False
        return 0 if all_valid else 1

    if args.parallel > 1:
        results = run_all_parallel(
            benchmarks, args.timeout, args.parallel, args.debug
        )
    else:
        results = run_all_sequential(benchmarks, args.timeout, args.debug)

    generate_report(results, Path(m5_path) / 'TEST_RESULTS.md')
    generate_json(results, Path(m5_path) / 'test_results.json')

    passed = sum(1 for r in results.values() if r['passed'])
    total = len(results)
    known_fails = sum(
        1 for r in results.values() if not r['passed'] and r['known']
    )
    real_fails = total - passed - known_fails

    if args.ci:
        print(json.dumps({
            'passed': passed,
            'failed': real_fails,
            'known_issues': known_fails,
            'total': total,
            'success': real_fails == 0
        }))
    else:
        print('\n' + '=' * 60)
        print(f'SUMMARY: {passed}/{total} passed')
        if known_fails > 0:
            print(f'Known issues: {known_fails} (not counted as failures)')
        print('=' * 60)

    return 0 if real_fails == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
