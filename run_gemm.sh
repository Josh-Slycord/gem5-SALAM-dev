#!/bin/bash
# Run GEMM benchmark with proper workflow
# Usage: ./run_gemm.sh

set -e

# Set M5_PATH to current directory
export M5_PATH="$(pwd)"
BENCH="gemm"
OUTDIR="BM_ARM_OUT/gemm_run"

echo "=== gem5-SALAM GEMM Benchmark ==="
echo "M5_PATH: $M5_PATH"
echo "Output dir: $OUTDIR"
echo ""

# Step 1: Run systembuilder to generate configs
echo "=== Step 1: Running systembuilder.py ==="
python3 SALAM-Configurator/systembuilder.py \
    --sysName "$BENCH" \
    --benchDir "benchmarks/sys_validation/${BENCH}"
echo "Config generation complete."
echo ""

# Step 2: Create output directory
mkdir -p "$OUTDIR"

# Step 3: Run gem5 simulation
echo "=== Step 2: Running gem5 simulation ==="

# Debug flags:
# IOAcc, ClassDetail, CommInterface, ComputeUnit, LLVMInterface,
# ComputeNode, LLVMRegister, LLVMOp, LLVMParse, LLVMGEP,
# LLVMRuntime (= ComputeNode + LLVMRegister + LLVMOp + LLVMParse)
# NoncoherentDma, JDEV
DEBUG_FLAGS="IOAcc,ClassDetail,CommInterface,ComputeUnit,LLVMInterface,ComputeNode,LLVMRegister,LLVMOp,LLVMParse,LLVMGEP,NoncoherentDma,JDEV"

./build/ARM/gem5.opt \
    --debug-flags=$DEBUG_FLAGS \
    --outdir="$OUTDIR" \
    configs/SALAM/generated/fs_${BENCH}.py \
    --mem-size=4GB \
    --mem-type=DDR4_2400_8x8 \
    --kernel=benchmarks/sys_validation/${BENCH}/sw/main.elf \
    --disk-image=baremetal/common/fake.iso \
    --machine-type=VExpress_GEM5_V1 \
    --dtb-file=none \
    --bare-metal \
    --cpu-type=DerivO3CPU \
    --accpath=benchmarks/sys_validation \
    --accbench=${BENCH} \
    --caches \
    --l2cache

echo ""
echo "=== Simulation complete ==="
echo "Terminal output: $OUTDIR/system.terminal"
echo ""
cat "$OUTDIR/system.terminal"
