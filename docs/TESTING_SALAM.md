# gem5-SALAM Testing Guide

This document describes how to test the gem5-SALAM hardware accelerator framework.

## Quick Start

```bash
# Set environment
export M5_PATH=/home/jslycord/gem5-SALAM-dev

# Run all sys_validation tests
python scripts/run_tests.py

# Run single benchmark
python scripts/run_tests.py -b gemm

# Run all benchmarks (including LeNet5)
python scripts/run_tests.py --all
```

## Test Runner v2.0

The SALAM test runner (`scripts/run_tests.py`) provides:

- **11 benchmarks**: 10 sys_validation + 1 LeNet5 variant
- **Parallel execution**: `-j 4` runs 4 tests simultaneously
- **Config validation**: `--validate-only` checks configs without simulation
- **Debug support**: `--debug SALAMData` enables debug output
- **CI mode**: `--ci` for machine-readable JSON output

### Command Reference

| Command | Description |
|---------|-------------|
| `python scripts/run_tests.py` | Run all sys_validation benchmarks |
| `python scripts/run_tests.py -l` | List available benchmarks |
| `python scripts/run_tests.py -b <name>` | Run single benchmark |
| `python scripts/run_tests.py --all` | Include LeNet5 benchmarks |
| `python scripts/run_tests.py -j 4` | Run 4 tests in parallel |
| `python scripts/run_tests.py -t 300` | Set timeout to 300 seconds |
| `python scripts/run_tests.py --validate-only` | Only validate configs |
| `python scripts/run_tests.py --skip-known` | Skip benchmarks with known issues |
| `python scripts/run_tests.py --debug SALAMData` | Enable debug flags |
| `python scripts/run_tests.py --ci` | CI-friendly JSON output |

### Output Files

After running tests, two files are generated:

- `TEST_RESULTS.md` - Human-readable markdown report
- `test_results.json` - Machine-readable JSON for CI/CD

## Available Benchmarks

### sys_validation (10 benchmarks)

| Benchmark | Description | Typical Time |
|-----------|-------------|--------------|
| bfs | Breadth-first search | ~3s |
| fft | Fast Fourier Transform | ~9s |
| gemm | General Matrix Multiply | ~3s |
| md_grid | Molecular dynamics (grid) | TIMEOUT |
| md_knn | Molecular dynamics (k-NN) | ~11s |
| mergesort | Merge sort algorithm | ~220s |
| nw | Needleman-Wunsch alignment | ~4s |
| spmv | Sparse matrix-vector multiply | ~3s |
| stencil2d | 2D stencil computation | ~36s |
| stencil3d | 3D stencil computation | ~32s |

### LeNet5 Variants

| Variant | Description |
|---------|-------------|
| lenet5_naive | Basic unrolled implementation |

## Known Issues

### md_grid Timeout

**Status:** Known issue - skipped in pass/fail evaluation

**Root Cause:** Floating-point precision differences between accelerator and reference implementation cause either:
1. Verification failure (Check Failed)
2. Simulation hang waiting for DEV_INTR signal

**Workaround:** Use `--skip-known` to exclude from testing:
```bash
python scripts/run_tests.py --skip-known
```

See [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) for detailed analysis.

## Testing Workflow

### Before Commits

```bash
# 1. Validate all configs
python scripts/run_tests.py --validate-only

# 2. Run quick test (skip timeout-prone benchmarks)
python scripts/run_tests.py --skip-known -j 4

# 3. Check results
cat TEST_RESULTS.md
```

### Full Test Suite

```bash
# Run everything except known issues
python scripts/run_tests.py --all --skip-known -j 4
```

### Debugging Failures

```bash
# Run single benchmark with debug output
python scripts/run_tests.py -b gemm --debug SALAMData

# Run with increased timeout
python scripts/run_tests.py -b mergesort -t 600

# Check validation only
python scripts/run_tests.py -b mybench --validate-only
```

## CI/CD Integration

The test runner supports CI/CD pipelines with:

```bash
# Machine-readable output
python scripts/run_tests.py --ci --skip-known
```

Output format:
```json
{
  "passed": 9,
  "failed": 0,
  "known_issues": 1,
  "total": 10,
  "success": true
}
```

Exit codes:
- `0`: All tests passed (known issues don't count as failures)
- `1`: One or more tests failed

### Example GitHub Actions

```yaml
- name: Run SALAM Tests
  run: |
    export M5_PATH=${{ github.workspace }}
    python scripts/run_tests.py --ci --skip-known -j 4
```

## Adding New Benchmarks

1. Add benchmark path to `BENCHMARK_PATHS` in `run_tests.py`
2. Add to `SYS_VALIDATION` or `LENET5_VARIANTS` list
3. Generate config: `python SALAM-Configurator/systembuilder.py --sysName <name> --benchDir <dir>`
4. Run: `python scripts/run_tests.py -b <name>`

## Related Documentation

- [docs/BENCHMARKS.md](BENCHMARKS.md) - Benchmark descriptions
- [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues
- [docs/DEBUG_FLAGS.md](DEBUG_FLAGS.md) - Debug flag reference
- [docs/GENERATION.md](GENERATION.md) - Config generation
