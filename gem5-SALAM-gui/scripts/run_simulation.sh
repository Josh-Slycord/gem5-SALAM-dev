#!/bin/bash
#
# gem5-SALAM Simulation Runner
# Runs gem5-SALAM simulations with the specified benchmark
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "\n${GREEN}==>${NC} $1"; }

# Default values
GEM5_DIR=""
BENCHMARK=""
CONFIG_SCRIPT="configs/SALAM/sys_validation.py"
BUILD_TYPE="opt"
OUTPUT_DIR=""
KERNEL=""
DISK_IMAGE=""
NUM_CPUS=1
EXTRA_ARGS=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dir)
            GEM5_DIR="$2"
            shift 2
            ;;
        --benchmark|-b)
            BENCHMARK="$2"
            shift 2
            ;;
        --config)
            CONFIG_SCRIPT="$2"
            shift 2
            ;;
        --build-type)
            BUILD_TYPE="$2"
            shift 2
            ;;
        --output|-o)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --kernel)
            KERNEL="$2"
            shift 2
            ;;
        --disk)
            DISK_IMAGE="$2"
            shift 2
            ;;
        --cpus)
            NUM_CPUS="$2"
            shift 2
            ;;
        --extra)
            EXTRA_ARGS="$2"
            shift 2
            ;;
        --list-configs)
            LIST_CONFIGS=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --dir PATH        Path to gem5-SALAM directory"
            echo "  --benchmark NAME  Benchmark to run (e.g., sys_validation/gemm)"
            echo "  --config SCRIPT   Config script (default: configs/SALAM/sys_validation.py)"
            echo "  --build-type TYPE Build type: opt (default), debug, fast"
            echo "  --output DIR      Output directory for results"
            echo "  --kernel PATH     Path to kernel image"
            echo "  --disk PATH       Path to disk image"
            echo "  --cpus N          Number of CPUs (default: 1)"
            echo "  --extra ARGS      Additional arguments to pass to gem5"
            echo "  --list-configs    List available config scripts"
            echo ""
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate gem5 directory
if [ -z "$GEM5_DIR" ]; then
    if [ -n "$M5_PATH" ]; then
        GEM5_DIR="$M5_PATH"
    else
        log_error "gem5-SALAM directory not specified. Use --dir or set M5_PATH"
        exit 1
    fi
fi

if [ ! -d "$GEM5_DIR" ]; then
    log_error "Directory does not exist: $GEM5_DIR"
    exit 1
fi

# List configs mode
if [ "${LIST_CONFIGS:-false}" = true ]; then
    log_step "Available Configuration Scripts"
    echo ""
    echo "=== SALAM Configs ==="
    for f in "$GEM5_DIR/configs/SALAM"/*.py; do
        if [ -f "$f" ]; then
            echo "  configs/SALAM/$(basename "$f")"
        fi
    done
    echo ""
    echo "=== Example Configs ==="
    for f in "$GEM5_DIR/configs/example"/*.py; do
        if [ -f "$f" ]; then
            echo "  configs/example/$(basename "$f")"
        fi
    done
    exit 0
fi

# Check for gem5 binary
GEM5_BIN="$GEM5_DIR/build/ARM/gem5.$BUILD_TYPE"
if [ ! -f "$GEM5_BIN" ]; then
    log_error "gem5 binary not found: $GEM5_BIN"
    log_info "Please build gem5-SALAM first"
    exit 1
fi

# Check benchmark
if [ -z "$BENCHMARK" ]; then
    log_error "No benchmark specified. Use --benchmark"
    exit 1
fi

BENCHMARK_DIR="$GEM5_DIR/benchmarks/$BENCHMARK"
if [ ! -d "$BENCHMARK_DIR" ]; then
    log_error "Benchmark directory not found: $BENCHMARK_DIR"
    exit 1
fi

# Check for config file
CONFIG_FILE="$BENCHMARK_DIR/config.yml"
if [ ! -f "$CONFIG_FILE" ]; then
    log_warn "Config file not found: $CONFIG_FILE"
fi

# Set up output directory
if [ -z "$OUTPUT_DIR" ]; then
    OUTPUT_DIR="$GEM5_DIR/m5out/$(basename "$BENCHMARK")_$(date +%Y%m%d_%H%M%S)"
fi

mkdir -p "$OUTPUT_DIR"

# Set M5_PATH environment variable
export M5_PATH="$GEM5_DIR"

log_step "gem5-SALAM Simulation"
log_info "gem5 binary: $GEM5_BIN"
log_info "Config script: $CONFIG_SCRIPT"
log_info "Benchmark: $BENCHMARK"
log_info "Output directory: $OUTPUT_DIR"

# Build simulation command
SIM_CMD="$GEM5_BIN --outdir=$OUTPUT_DIR $GEM5_DIR/$CONFIG_SCRIPT"

# Add benchmark options if using sys_validation.py
if [[ "$CONFIG_SCRIPT" == *"sys_validation"* ]]; then
    BENCH_NAME=$(basename "$BENCHMARK")
    SIM_CMD="$SIM_CMD --accbench=$BENCH_NAME --accpath=$BENCHMARK_DIR"
fi

# Add kernel and disk if provided
if [ -n "$KERNEL" ]; then
    SIM_CMD="$SIM_CMD --kernel=$KERNEL"
fi

if [ -n "$DISK_IMAGE" ]; then
    SIM_CMD="$SIM_CMD --disk-image=$DISK_IMAGE"
fi

# Add CPU count
SIM_CMD="$SIM_CMD --num-cpus=$NUM_CPUS"

# Add extra arguments
if [ -n "$EXTRA_ARGS" ]; then
    SIM_CMD="$SIM_CMD $EXTRA_ARGS"
fi

log_step "Running simulation..."
log_info "Command: $SIM_CMD"
echo ""

# Run simulation
eval "$SIM_CMD"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    log_success "Simulation completed!"
    log_info "Results saved to: $OUTPUT_DIR"

    # Show stats summary if available
    if [ -f "$OUTPUT_DIR/stats.txt" ]; then
        log_step "Quick Stats Summary"
        echo ""
        head -50 "$OUTPUT_DIR/stats.txt" | grep -E "sim_seconds|sim_ticks|host_seconds|simulated_time"
    fi
else
    log_error "Simulation failed with exit code $EXIT_CODE"
fi

exit $EXIT_CODE
