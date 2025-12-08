#!/bin/bash
#
# gem5-SALAM Hardware Profile Generator
# Generates C++ functional unit and instruction classes for simulation
#
# Usage: ./generateHW.sh -b BENCHMARK [-m MODEL] [-l LATENCY] [-p PROFILE] [-d DIR]
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Default values
BENCH=""
MODEL="40nm_model"
LATENCY="5ns"
PROFILE="default_profile"
BENCH_DIR="benchmarks/sys_validation"
VERBOSE=false

usage() {
    echo "gem5-SALAM Hardware Profile Generator"
    echo ""
    echo "Usage: $0 -b BENCHMARK [OPTIONS]"
    echo ""
    echo "Required:"
    echo "  -b BENCHMARK   Benchmark name (e.g., gemm, bfs, fft)"
    echo ""
    echo "Options:"
    echo "  -m MODEL       Technology model (default: 40nm_model)"
    echo "  -l LATENCY     Cycle time: 1ns|2ns|3ns|4ns|5ns|6ns|10ns (default: 5ns)"
    echo "  -p PROFILE     Profile name (default: default_profile)"
    echo "  -d DIR         Benchmark directory (default: benchmarks/sys_validation)"
    echo "  -v             Verbose output"
    echo "  -h             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 -b gemm                           # Generate HW for gemm benchmark"
    echo "  $0 -b bfs -l 10ns                    # Generate with 10ns cycle time"
    echo "  $0 -b fft -d benchmarks/legacy       # Use legacy benchmark directory"
    echo ""
    exit 1
}

# Parse arguments
while getopts ":b:m:l:p:d:vh" opt; do
    case $opt in
        b)
            BENCH=${OPTARG}
            ;;
        m)
            MODEL=${OPTARG}
            ;;
        l)
            LATENCY=${OPTARG}
            ;;
        p)
            PROFILE=${OPTARG}
            ;;
        d)
            BENCH_DIR=${OPTARG}
            ;;
        v)
            VERBOSE=true
            ;;
        h)
            usage
            ;;
        *)
            log_error "Unknown option: -${OPTARG}"
            usage
            ;;
    esac
done

# Validate required arguments
if [ -z "${BENCH}" ]; then
    log_error "Benchmark name is required"
    echo ""
    usage
fi

# Validate M5_PATH
if [ -z "${M5_PATH}" ]; then
    log_error "M5_PATH environment variable is not set"
    log_info "Set M5_PATH to your gem5-SALAM directory"
    exit 1
fi

# Validate cycle time
case "${LATENCY}" in
    1ns|2ns|3ns|4ns|5ns|6ns|10ns)
        ;;
    *)
        log_error "Invalid cycle time: ${LATENCY}"
        log_info "Supported values: 1ns, 2ns, 3ns, 4ns, 5ns, 6ns, 10ns"
        exit 1
        ;;
esac

# Check if benchmark directory exists
FULL_BENCH_DIR="${M5_PATH}/${BENCH_DIR}/${BENCH}"
if [ ! -d "${FULL_BENCH_DIR}" ]; then
    log_error "Benchmark directory not found: ${FULL_BENCH_DIR}"
    exit 1
fi

# Print configuration
echo ""
log_info "gem5-SALAM Hardware Profile Generator"
echo "========================================"
log_info "Benchmark: ${BENCH}"
log_info "Directory: ${BENCH_DIR}/${BENCH}"
log_info "Model: ${MODEL}"
log_info "Cycle Time: ${LATENCY}"
log_info "Profile: ${PROFILE}"
echo ""

# Check for new salam_config module first, fall back to legacy HWProfileGenerator
if [ -d "${M5_PATH}/salam_config" ]; then
    log_info "Using salam_config module"

    VERBOSE_FLAG=""
    if [ "${VERBOSE}" = true ]; then
        VERBOSE_FLAG="-v"
    fi

    python3 -m salam_config.cli generate-hw \
        --benchmark "${BENCH}" \
        --model "${MODEL}" \
        --latency "${LATENCY}" \
        --profile "${PROFILE}" \
        --bench-dir "${BENCH_DIR}" \
        ${VERBOSE_FLAG}

elif [ -f "${M5_PATH}/HWProfileGenerator.py" ]; then
    log_info "Using legacy HWProfileGenerator"

    # Legacy mode - use old HWProfileGenerator.py
    # Note: Legacy script may not support all parameters
    python3 ${M5_PATH}/HWProfileGenerator.py -b ${BENCH}

else
    log_error "Neither salam_config module nor HWProfileGenerator.py found"
    exit 1
fi

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    log_success "Hardware profile generation complete!"
    log_info "Generated files in: ${M5_PATH}/src/hwacc/HWModeling/generated/"
else
    log_error "Hardware profile generation failed with exit code ${EXIT_CODE}"
fi

exit $EXIT_CODE
