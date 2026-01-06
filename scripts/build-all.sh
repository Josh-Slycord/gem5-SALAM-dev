#!/bin/bash
#===============================================================================
# gem5-SALAM Build Script
#
# Builds gem5-SALAM binaries and benchmarks.
#
# Usage:
#   ./build-all.sh                  # Build gem5.opt and all benchmarks
#   ./build-all.sh --gem5-only      # Build only gem5 binaries
#   ./build-all.sh --benchmarks-only # Build only benchmarks
#   ./build-all.sh --target opt     # Build specific target (opt|debug|fast)
#   ./build-all.sh --all-targets    # Build all gem5 targets
#   ./build-all.sh --clean          # Clean before building
#   ./build-all.sh -j 8             # Use 8 parallel jobs
#
# Environment:
#   M5_PATH   Path to gem5-SALAM-dev (required)
#
# Author: @agent_1 (gem5-SALAM Specialist)
# Created: 2026-01-05
# Updated: 2026-01-06 (Ubuntu 24.04 Python 3.10 support)
#===============================================================================

#-------------------------------------------------------------------------------
# Configuration
#-------------------------------------------------------------------------------

M5_PATH="${M5_PATH:-}"
BUILD_TARGET="opt"
BUILD_ALL_TARGETS=false
BUILD_GEM5=true
BUILD_BENCHMARKS=true
CLEAN_FIRST=false
JOBS=$(nproc)

#-------------------------------------------------------------------------------
# Colors
#-------------------------------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

#-------------------------------------------------------------------------------
# Ubuntu/Python Detection
#-------------------------------------------------------------------------------

detect_scons_command() {
    # Detect Ubuntu version and configure appropriate scons command
    # Ubuntu 24.04 requires Python 3.10 for gem5 (due to pybind11 compatibility)

    local ubuntu_version=""
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        ubuntu_version="$VERSION_ID"
    fi

    # Check if we need to use Python 3.10 (Ubuntu 24.04)
    case "$ubuntu_version" in
        24.04|24.*)
            if command -v python3.10 &> /dev/null; then
                SCONS_CMD="python3.10 $(which scons)"
                log_info "Ubuntu 24.04 detected - using Python 3.10 for scons"
            else
                log_warn "Ubuntu 24.04 detected but Python 3.10 not found"
                log_warn "gem5 may fail to build - install with: sudo apt install python3.10"
                SCONS_CMD="scons"
            fi
            ;;
        *)
            SCONS_CMD="scons"
            ;;
    esac
}

#-------------------------------------------------------------------------------
# Usage
#-------------------------------------------------------------------------------

show_help() {
    head -20 "$0" | tail -15
    exit 0
}

#-------------------------------------------------------------------------------
# Parse Arguments
#-------------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case $1 in
        --gem5-only)       BUILD_BENCHMARKS=false; shift ;;
        --benchmarks-only) BUILD_GEM5=false; shift ;;
        --target)          BUILD_TARGET="$2"; shift 2 ;;
        --all-targets)     BUILD_ALL_TARGETS=true; shift ;;
        --clean)           CLEAN_FIRST=true; shift ;;
        -j)                JOBS="$2"; shift 2 ;;
        --help|-h)         show_help ;;
        *)                 log_error "Unknown option: $1"; show_help ;;
    esac
done

#-------------------------------------------------------------------------------
# Validation
#-------------------------------------------------------------------------------

if [[ -z "$M5_PATH" ]]; then
    log_error "M5_PATH environment variable is not set"
    log_info "Set it with: export M5_PATH=/path/to/gem5-SALAM-dev"
    exit 1
fi

if [[ ! -d "$M5_PATH" ]]; then
    log_error "M5_PATH does not exist: $M5_PATH"
    exit 1
fi

# Detect correct scons command for this Ubuntu version
detect_scons_command

#-------------------------------------------------------------------------------
# Build gem5
#-------------------------------------------------------------------------------

build_gem5() {
    local target=$1
    log_info "Building gem5.$target with $JOBS parallel jobs..."

    cd "$M5_PATH"

    if $CLEAN_FIRST; then
        log_info "Cleaning build directory..."
        rm -rf "build/ARM/gem5.$target"
    fi

    local start_time=$(date +%s)

    if $SCONS_CMD "build/ARM/gem5.$target" -j"$JOBS"; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        log_success "gem5.$target built successfully in ${duration}s"
        return 0
    else
        log_error "gem5.$target build failed"
        return 1
    fi
}

#-------------------------------------------------------------------------------
# Build Benchmarks
#-------------------------------------------------------------------------------

build_benchmark() {
    local benchmark=$1
    local benchmark_path="$M5_PATH/benchmarks/$benchmark"

    if [[ ! -d "$benchmark_path" ]]; then
        log_warn "Benchmark directory not found: $benchmark"
        return 1
    fi

    if [[ ! -f "$benchmark_path/Makefile" ]]; then
        log_warn "No Makefile in $benchmark"
        return 1
    fi

    log_info "Building benchmark: $benchmark"

    cd "$benchmark_path"

    if $CLEAN_FIRST; then
        make clean 2>/dev/null || true
    fi

    if make; then
        log_success "$benchmark built"
        return 0
    else
        log_error "$benchmark build failed"
        return 1
    fi
}

build_all_benchmarks() {
    log_info "Building all benchmarks..."

    local success=0
    local failed=0

    # System validation benchmarks
    if [[ -d "$M5_PATH/benchmarks/sys_validation" ]]; then
        for bench_dir in "$M5_PATH/benchmarks/sys_validation"/*/; do
            if [[ -d "$bench_dir" ]]; then
                local bench_name=$(basename "$bench_dir")
                if build_benchmark "sys_validation/$bench_name"; then
                    ((success++))
                else
                    ((failed++))
                fi
            fi
        done
    fi

    # Comprehensive test benchmark
    if [[ -d "$M5_PATH/benchmarks/comprehensive_test" ]]; then
        if build_benchmark "comprehensive_test"; then
            ((success++))
        else
            ((failed++))
        fi
    fi

    echo ""
    log_info "Benchmark build summary:"
    log_info "  Successful: $success"
    log_info "  Failed: $failed"

    if [[ $failed -gt 0 ]]; then
        return 1
    fi
    return 0
}

#-------------------------------------------------------------------------------
# Main
#-------------------------------------------------------------------------------

main() {
    echo "========================================"
    echo "gem5-SALAM Build Script"
    echo "========================================"
    echo ""
    log_info "M5_PATH: $M5_PATH"
    log_info "Jobs: $JOBS"
    log_info "Build gem5: $BUILD_GEM5"
    log_info "Build benchmarks: $BUILD_BENCHMARKS"
    log_info "Scons command: $SCONS_CMD"
    echo ""

    local gem5_result=0
    local bench_result=0

    # Build gem5
    if $BUILD_GEM5; then
        if $BUILD_ALL_TARGETS; then
            log_info "Building all gem5 targets..."
            for target in opt debug fast; do
                build_gem5 "$target" || gem5_result=1
            done
        else
            build_gem5 "$BUILD_TARGET" || gem5_result=1
        fi
    fi

    echo ""

    # Build benchmarks
    if $BUILD_BENCHMARKS; then
        build_all_benchmarks || bench_result=1
    fi

    echo ""
    echo "========================================"
    if [[ $gem5_result -eq 0 && $bench_result -eq 0 ]]; then
        log_success "All builds completed successfully!"
    else
        log_error "Some builds failed"
        exit 1
    fi
    echo "========================================"
}

main "$@"
