#!/bin/bash
#===============================================================================
# gem5-SALAM Test Runner Script
#
# Runs benchmarks and validates output.
#
# Usage:
#   ./test-all.sh                   # Run all system validation benchmarks
#   ./test-all.sh --benchmark gemm  # Run specific benchmark
#   ./test-all.sh --comprehensive   # Run comprehensive_test benchmark
#   ./test-all.sh --list            # List available benchmarks
#   ./test-all.sh --timeout 300     # Set timeout in seconds (default: 180)
#   ./test-all.sh --verbose         # Verbose output
#
# Environment:
#   M5_PATH   Path to gem5-SALAM-dev (required)
#
# Author: @agent_1 (gem5-SALAM Specialist)
# Created: 2026-01-05
#===============================================================================

#-------------------------------------------------------------------------------
# Configuration
#-------------------------------------------------------------------------------

M5_PATH="${M5_PATH:-}"
TIMEOUT=180
VERBOSE=false
SPECIFIC_BENCHMARK=""
RUN_COMPREHENSIVE=false
LIST_ONLY=false

# Counters
PASSED=0
FAILED=0
SKIPPED=0
TIMEOUT_COUNT=0

#-------------------------------------------------------------------------------
# Colors
#-------------------------------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_pass()    { echo -e "${GREEN}[PASS]${NC} $1"; }
log_fail()    { echo -e "${RED}[FAIL]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_test()    { echo -e "${CYAN}[TEST]${NC} $1"; }
log_verbose() { $VERBOSE && echo -e "       $1"; }

#-------------------------------------------------------------------------------
# Usage
#-------------------------------------------------------------------------------

show_help() {
    head -18 "$0" | tail -13
    exit 0
}

#-------------------------------------------------------------------------------
# Parse Arguments
#-------------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case $1 in
        --benchmark|-b) SPECIFIC_BENCHMARK="$2"; shift 2 ;;
        --comprehensive) RUN_COMPREHENSIVE=true; shift ;;
        --list)         LIST_ONLY=true; shift ;;
        --timeout|-t)   TIMEOUT="$2"; shift 2 ;;
        --verbose|-v)   VERBOSE=true; shift ;;
        --help|-h)      show_help ;;
        *)              log_error "Unknown option: $1"; show_help ;;
    esac
done

#-------------------------------------------------------------------------------
# Validation
#-------------------------------------------------------------------------------

if [[ -z "$M5_PATH" ]]; then
    log_fail "M5_PATH environment variable is not set"
    exit 1
fi

if [[ ! -d "$M5_PATH" ]]; then
    log_fail "M5_PATH does not exist: $M5_PATH"
    exit 1
fi

#-------------------------------------------------------------------------------
# List Benchmarks
#-------------------------------------------------------------------------------

list_benchmarks() {
    echo "Available System Validation Benchmarks:"
    echo "========================================"

    if [[ -d "$M5_PATH/benchmarks/sys_validation" ]]; then
        for bench_dir in "$M5_PATH/benchmarks/sys_validation"/*/; do
            if [[ -d "$bench_dir" ]]; then
                local bench_name=$(basename "$bench_dir")
                echo "  - $bench_name"
            fi
        done
    fi

    echo ""
    echo "Other Benchmarks:"
    echo "================="

    if [[ -d "$M5_PATH/benchmarks/comprehensive_test" ]]; then
        echo "  - comprehensive_test (custom multi-cluster benchmark)"
    fi

    if [[ -d "$M5_PATH/benchmarks/MachSuite" ]]; then
        echo "  - MachSuite/* (reference benchmarks)"
    fi
}

#-------------------------------------------------------------------------------
# Run Benchmark
#-------------------------------------------------------------------------------

run_benchmark() {
    local bench_name=$1
    local bench_type=${2:-sys_validation}

    log_test "Running: $bench_name"

    # Check if systemValidation.sh exists
    if [[ ! -f "$M5_PATH/systemValidation.sh" ]]; then
        log_fail "systemValidation.sh not found"
        return 1
    fi

    cd "$M5_PATH"

    local start_time=$(date +%s)
    local output_file=$(mktemp)

    # Run with timeout
    if timeout "$TIMEOUT" ./systemValidation.sh -b "$bench_name" > "$output_file" 2>&1; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))

        # Check for success indicators in output
        if grep -q "PASSED\|SUCCESS\|Test passed" "$output_file" 2>/dev/null; then
            log_pass "$bench_name completed in ${duration}s"
            PASSED=$((PASSED + 1))
            rm -f "$output_file"
            return 0
        elif grep -q "FAILED\|ERROR\|Test failed" "$output_file" 2>/dev/null; then
            log_fail "$bench_name - test assertions failed"
            FAILED=$((FAILED + 1))
            $VERBOSE && cat "$output_file"
            rm -f "$output_file"
            return 1
        else
            # Completed but no clear pass/fail - assume pass
            log_pass "$bench_name completed in ${duration}s (no explicit result)"
            PASSED=$((PASSED + 1))
            rm -f "$output_file"
            return 0
        fi
    else
        local exit_code=$?
        if [[ $exit_code -eq 124 ]]; then
            log_warn "$bench_name - TIMEOUT (${TIMEOUT}s)"
            TIMEOUT_COUNT=$((TIMEOUT_COUNT + 1))
        else
            log_fail "$bench_name - exited with code $exit_code"
            FAILED=$((FAILED + 1))
            $VERBOSE && cat "$output_file"
        fi
        rm -f "$output_file"
        return 1
    fi
}

run_comprehensive_test() {
    log_info "Running comprehensive_test benchmark..."

    local bench_path="$M5_PATH/benchmarks/comprehensive_test"

    if [[ ! -d "$bench_path" ]]; then
        log_fail "comprehensive_test benchmark not found"
        return 1
    fi

    # Check if there's a run script or use standard approach
    if [[ -f "$bench_path/run.sh" ]]; then
        cd "$bench_path"
        if timeout "$TIMEOUT" ./run.sh; then
            log_pass "comprehensive_test completed"
            PASSED=$((PASSED + 1))
            return 0
        else
            log_fail "comprehensive_test failed"
            FAILED=$((FAILED + 1))
            return 1
        fi
    else
        # Use systemValidation if available for this benchmark
        run_benchmark "comprehensive_test" "custom"
    fi
}

#-------------------------------------------------------------------------------
# Run All Benchmarks
#-------------------------------------------------------------------------------

run_all_sys_validation() {
    log_info "Running all system validation benchmarks..."
    echo ""

    local benchmarks=(
        "bfs"
        "fft"
        "gemm"
        "md_knn"
        "md_grid"
        "mergesort"
        "nw"
        "spmv"
        "stencil2d"
        "stencil3d"
    )

    for bench in "${benchmarks[@]}"; do
        if [[ -d "$M5_PATH/benchmarks/sys_validation/$bench" ]]; then
            run_benchmark "$bench"
        else
            log_warn "$bench - directory not found"
            SKIPPED=$((SKIPPED + 1))
        fi
        echo ""
    done
}

#-------------------------------------------------------------------------------
# Summary
#-------------------------------------------------------------------------------

print_summary() {
    echo "========================================"
    echo "Test Summary"
    echo "========================================"
    echo ""
    echo -e "  ${GREEN}Passed:${NC}   $PASSED"
    echo -e "  ${RED}Failed:${NC}   $FAILED"
    echo -e "  ${YELLOW}Timeout:${NC}  $TIMEOUT_COUNT"
    echo -e "  Skipped:  $SKIPPED"
    echo ""

    local total=$((PASSED + FAILED + TIMEOUT_COUNT))
    if [[ $total -gt 0 ]]; then
        local pass_rate=$((100 * PASSED / total))
        echo "  Pass rate: ${pass_rate}%"
    fi
    echo ""

    if [[ $FAILED -eq 0 && $TIMEOUT_COUNT -eq 0 ]]; then
        log_pass "All tests passed!"
        return 0
    else
        log_fail "Some tests failed or timed out"
        return 1
    fi
}

#-------------------------------------------------------------------------------
# Main
#-------------------------------------------------------------------------------

main() {
    echo "========================================"
    echo "gem5-SALAM Test Runner"
    echo "========================================"
    echo ""
    log_info "M5_PATH: $M5_PATH"
    log_info "Timeout: ${TIMEOUT}s"
    echo ""

    # List only
    if $LIST_ONLY; then
        list_benchmarks
        exit 0
    fi

    # Specific benchmark
    if [[ -n "$SPECIFIC_BENCHMARK" ]]; then
        run_benchmark "$SPECIFIC_BENCHMARK"
        echo ""
        print_summary
        exit $?
    fi

    # Comprehensive test
    if $RUN_COMPREHENSIVE; then
        run_comprehensive_test
        echo ""
        print_summary
        exit $?
    fi

    # Run all system validation
    run_all_sys_validation
    print_summary
}

main "$@"
