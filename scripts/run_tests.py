#!/usr/bin/env python3
import os, sys, subprocess, argparse, json
from datetime import datetime
from pathlib import Path

BENCHMARKS = ['bfs', 'fft', 'gemm', 'md_grid', 'md_knn', 'mergesort', 'nw', 'spmv', 'stencil2d', 'stencil3d']
KNOWN_ISSUES = {'md_grid': 'Floating-point precision issue'}

def get_m5_path():
    m5_path = os.environ.get('M5_PATH')
    if not m5_path: raise EnvironmentError('M5_PATH not set')
    return m5_path

def check_build():
    return (Path(get_m5_path()) / 'build' / 'ARM' / 'gem5.opt').exists()

def run_benchmark(benchmark, timeout=600):
    m5_path = get_m5_path()
    gem5 = Path(m5_path) / 'build' / 'ARM' / 'gem5.opt'
    config = Path(m5_path) / 'configs' / 'SALAM' / 'generated' / f'fs_{benchmark}.py'
    if not config.exists(): return False, f'Config not found: {config}', 0

    # Match systemValidation.sh options exactly
    cmd = [
        str(gem5), str(config),
        '--mem-size=4GB',
        '--mem-type=DDR4_2400_8x8',
        f'--kernel={m5_path}/benchmarks/sys_validation/{benchmark}/sw/main.elf',
        f'--disk-image={m5_path}/baremetal/common/fake.iso',
        '--machine-type=VExpress_GEM5_V1',
        '--dtb-file=none',
        '--bare-metal',
        '--cpu-type=DerivO3CPU',
        f'--accpath={m5_path}/benchmarks/sys_validation',
        f'--accbench={benchmark}',
        '--caches', '--l2cache'
    ]
    start = datetime.now()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=m5_path)
        duration = (datetime.now() - start).total_seconds()
        output = result.stdout + result.stderr
        if 'Check Passed' in output: return True, 'Check Passed', duration
        elif 'Check Failed' in output: return False, 'Check Failed', duration
        elif 'Sorted correctly' in output: return True, 'Sorted correctly', duration
        elif result.returncode == 0: return True, 'Completed', duration
        else: return False, f'Exit code {result.returncode}', duration
    except subprocess.TimeoutExpired: return False, f'Timeout {timeout}s', timeout
    except Exception as e: return False, str(e), 0

def run_all(benchmarks, timeout=600):
    results = {}
    for i, b in enumerate(benchmarks):
        print(f'[{i+1}/{len(benchmarks)}] {b}...')
        p, m, d = run_benchmark(b, timeout)
        results[b] = {'passed': p, 'message': m, 'duration': d, 'known': b in KNOWN_ISSUES}
        print(f'  {"PASS" if p else "FAIL"}: {(m)} ({d:.1f}s)')
    return results

def gen_report(results, path):
    total, passed = len(results), sum(1 for r in results.values() if r['passed'])
    lines = ['# Test Results', '', f'**{datetime.now():%Y-%m-%d %H:%M}** {passed}/{total} passed', '',
             '| Benchmark | Status | Message | Duration |', '|-----------|--------|---------|----------|']
    for b, r in sorted(results.items()):
        s = 'PASS' if r['passed'] else ('FAIL*' if r['known'] else 'FAIL')
        lines.append(f'| {b} | {s} | {r["message"]} | {r["duration"]:.1f}s |')
    lines.extend(['', '*Known issue', '', '## Known Issues'])
    for b, i in KNOWN_ISSUES.items(): lines.append(f'- **{b}**: {i}')
    with open(path, 'w') as f: f.write('\n'.join(lines))

def save_json(results, path):
    with open(path, 'w') as f:
        json.dump({'timestamp': datetime.now().isoformat(), 'results': results,
                   'summary': {'total': len(results), 'passed': sum(1 for r in results.values() if r['passed'])}}, f, indent=2)

def main():
    parser = argparse.ArgumentParser(description='gem5-SALAM Test Runner')
    parser.add_argument('-b', '--benchmark', help='Single benchmark')
    parser.add_argument('-t', '--timeout', type=int, default=600)
    parser.add_argument('-l', '--list', action='store_true')
    parser.add_argument('--skip-build-check', action='store_true')
    args = parser.parse_args()
    
    if args.list:
        for b in BENCHMARKS: print(f'  {b}' + (' (known issue)' if b in KNOWN_ISSUES else ''))
        return 0
    
    try: m5_path = get_m5_path()
    except: print('Error: M5_PATH not set'); return 1
    
    if not args.skip_build_check and not check_build():
        print('Error: gem5 not built'); return 1
    
    print('=' * 50 + '\ngem5-SALAM Test Runner\n' + '=' * 50)
    benchmarks = [args.benchmark] if args.benchmark else BENCHMARKS
    results = run_all(benchmarks, args.timeout)
    
    gen_report(results, Path(m5_path) / 'TEST_RESULTS.md')
    save_json(results, Path(m5_path) / 'test_results.json')
    
    passed = sum(1 for r in results.values() if r['passed'])
    print(f'\n{"=" * 50}\nSUMMARY: {passed}/{len(results)} passed\n{"=" * 50}')
    return 0 if all(r['passed'] or r['known'] for r in results.values()) else 1

if __name__ == '__main__': sys.exit(main())
