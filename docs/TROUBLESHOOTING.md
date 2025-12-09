# gem5-SALAM Troubleshooting Guide

Common issues and solutions for gem5-SALAM development and simulation.

---

## Table of Contents

1. [Build Issues](#build-issues)
2. [Configuration Issues](#configuration-issues)
3. [Simulation Issues](#simulation-issues)
4. [Debug Output Issues](#debug-output-issues)
5. [Benchmark Issues](#benchmark-issues)
6. [Environment Issues](#environment-issues)

---

## Build Issues

### scons: command not found

**Error:**
scons: command not found

**Solution:**
pip install scons
# or
sudo apt install scons

### Python.h not found

**Error:**
fatal error: Python.h: No such file or directory

**Solution:**
sudo apt install python3-dev

### protobuf errors

**Error:**
protobuf version mismatch

**Solution:**
pip install protobuf==3.20.0

### Build fails with C++ errors

**Cause:** Compiler version mismatch or missing dependencies.

**Solution:**
sudo apt install build-essential g++ m4 zlib1g-dev libprotobuf-dev

### ARM cross-compiler not found

**Error:**
arm-linux-gnueabihf-gcc: command not found

**Solution:**
sudo apt install gcc-arm-linux-gnueabihf

---

## Configuration Issues

### M5_PATH not set

**Error:**
M5_PATH environment variable not set

**Solution:**
export M5_PATH=/home/jslycord/gem5-SALAM-dev
# Add to ~/.bashrc for persistence
echo 'export M5_PATH=/home/jslycord/gem5-SALAM-dev' >> ~/.bashrc

### Missing acc_cluster section

**Error:**
Configuration missing 'acc_cluster' section

**Cause:** Invalid or malformed config.yml

**Solution:**
1. Verify YAML syntax (proper indentation)
2. Ensure file starts with:
   ---
   acc_cluster:
     - Name: your_cluster
3. Validate: python -m salam_config.cli validate -c config.yml

### Invalid cycle time

**Error:**
Invalid cycle time: 7ns

**Solution:**
Use supported values: 1ns, 2ns, 3ns, 4ns, 5ns, 6ns, 10ns

### Benchmark directory not found

**Error:**
Benchmark directory not found: ...

**Solution:**
1. Check --bench-dir option
2. Default is benchmarks/sys_validation
3. For LeNet: benchmarks/lenet5-nounroll

### Config file not found

**Error:**
Configuration file not found in ...

**Solution:**
1. Ensure config.yml exists in benchmark directory
2. Check alternate names: config.yaml, <benchmark>_config.yml

---

## Simulation Issues

### Kernel not found

**Error:**
Kernel file not found: ...

**Solution:**
1. Verify main.elf exists in benchmark sw/ directory
2. If missing, rebuild:
   cd benchmarks/sys_validation/<benchmark>/sw
   make

### gem5.opt not found

**Error:**
gem5 not built

**Solution:**
cd 
scons build/ARM/gem5.opt -j4

### Memory allocation failure

**Error:**
fatal: Cannot allocate memory

**Solution:**
1. Reduce --mem-size parameter
2. Close other applications
3. Check system memory: free -h

### Timeout during simulation

**Cause:** Benchmark takes too long or is stuck.

**Solutions:**
1. Increase timeout: python scripts/run_tests.py -t 1200
2. Check for infinite loops in accelerator code
3. Add debug flags to trace execution

### Check Failed

**Error:**
Check Failed in simulation output

**Cause:** Benchmark result verification failed.

**Solutions:**
1. Check input data integrity
2. Verify accelerator configuration matches software expectations
3. Enable debug flags to trace execution:
   --debug-flags=SALAMResults

---

## Debug Output Issues

### Too much debug output

**Problem:** Simulation generates excessive debug output

**Solution:**
1. Use specific debug flags instead of compound flags
2. Redirect output: ./gem5.opt ... 2>&1 | grep SALAM

### No debug output

**Problem:** Debug flags have no effect

**Causes:**
1. Wrong flag name
2. Code path not executed
3. DPRINTF/DPRINTFS guards missing

**Solution:**
1. List available flags: ./gem5.opt --debug-help | grep SALAM
2. Verify flag is correct (case-sensitive)
3. Check DTRACE guards in source

### Debug output format

**Problem:** Debug output hard to parse

**Solution:**
Use SALAMResultsCSV flag for machine-readable output:
--debug-flags=SALAMResultsCSV --debug-file=results.csv

---

## Benchmark Issues

### md_grid timeout

**Issue:** md_grid benchmark times out after 600 seconds

**Root Cause Analysis:**

1. **Algorithm Complexity:** md_grid uses 6 nested loops for grid-based neighbor finding with O(n²) complexity for force calculations

2. **Configuration:** blockSide=4, densityFactor=10, nAtoms=256

3. **Floating-Point Precision:** The Lennard-Jones potential uses double-precision math which accumulates rounding errors differently in hardware vs simulation

4. **Check Tolerance:** EPSILON = 1.0e-2 (1%) may be too strict for accumulated floating-point differences

5. **Hang Mechanism:** main.cpp polls for DEV_INTR (0x04) signal in a blocking loop - if the accelerator never signals completion, the simulation hangs indefinitely

**Status:** Known issue - floating-point precision differences between accelerator simulation and reference implementation cause either verification failure or simulation hang.

**Workaround:** Skip md_grid in automated testing - run other benchmarks individually.

**Potential Fixes (Not Implemented):**
- Increase EPSILON tolerance in defines.h
- Use single-precision floats instead of double
- Debug with --debug-flags=SALAMData to trace values

### LeNet5 validation fails

**Possible causes:**
1. Incorrect weight data
2. Memory configuration mismatch
3. Floating-point precision

**Debug steps:**
1. Validate config: python -m salam_config.cli validate -c config.yml
2. Check generated configs exist
3. Enable debug flags: --debug-flags=SALAMCfg,SALAMData

### Benchmark output mismatch

**Cause:** Expected vs actual output differs

**Solutions:**
1. Check input data
2. Verify accelerator configuration
3. Compare with known-good baseline

---

## Environment Issues

### WSL file access errors

**Problem:** Cannot access Windows files from WSL

**Solution:**
1. Use /mnt/c/ path prefix for Windows files
2. Or use Windows path: //wsl.localhost/Ubuntu-20.04/...

### Python module not found

**Error:**
ModuleNotFoundError: No module named 'salam_config'

**Solution:**
cd 
export PYTHONPATH=:
# or
pip install -e .

### Permission denied

**Error:**
Permission denied when running scripts

**Solution:**
chmod +x scripts/run_tests.py
chmod +x build/ARM/gem5.opt

### Git LFS issues

**Problem:** Large files not downloading

**Solution:**
git lfs install
git lfs pull

---

## Getting Help

### Debug Flags

See docs/DEBUG_FLAGS.md for complete debug flag reference.

### Assertion Analysis

See docs/ASSERTION_ANALYSIS.md for assertion failure analysis.

### Configuration Generation

See docs/GENERATION.md for config generation guide.

### Benchmark Reference

See docs/BENCHMARKS.md for benchmark documentation.

---

## Reporting Issues

When reporting issues, include:

1. Error message (full text)
2. Command that caused the error
3. Environment details:
   - gem5 version (git hash)
   - Python version
   - Operating system
4. Debug output (with appropriate --debug-flags)
5. config.yml contents (if applicable)

Example issue report:

    ## Error
    Simulation crashes with: ...
    
    ## Command
    ./build/ARM/gem5.opt configs/SALAM/generated/fs_gemm.py ...
    
    ## Environment
    - gem5: 74096887e
    - Python: 3.8.10
    - OS: Ubuntu 20.04 (WSL2)
    
    ## Debug output
    [attached file]

