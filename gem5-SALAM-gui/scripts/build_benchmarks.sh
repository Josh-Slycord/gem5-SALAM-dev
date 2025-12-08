#!/bin/bash
#
# gem5-SALAM Benchmark Build Script
# Builds benchmark applications for gem5-SALAM simulation
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
CLEAN_FIRST=false
LIST_ONLY=false
NUM_JOBS=$(nproc)

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
        --clean)
            CLEAN_FIRST=true
            shift
            ;;
        --list)
            LIST_ONLY=true
            shift
            ;;
        --jobs|-j)
            NUM_JOBS="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --dir PATH       Path to gem5-SALAM directory"
            echo "  --benchmark NAME Build specific benchmark (or 'all')"
            echo "  --clean          Clean before building"
            echo "  --list           List available benchmarks"
            echo "  --jobs N         Number of parallel jobs (default: $(nproc))"
            echo ""
            echo "Benchmark categories:"
            echo "  legacy/          Original benchmarks (gemm, fft, etc.)"
            echo "  sys_validation/  System validation benchmarks"
            echo "  lenet5-*/        LeNet5 CNN variants"
            echo "  mobilenetv2/     MobileNetV2 deep learning"
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

BENCHMARKS_DIR="$GEM5_DIR/benchmarks"

if [ ! -d "$BENCHMARKS_DIR" ]; then
    log_error "Benchmarks directory not found: $BENCHMARKS_DIR"
    exit 1
fi

# Function to list available benchmarks
list_benchmarks() {
    log_step "Available Benchmarks"
    echo ""

    echo "=== Legacy Benchmarks ==="
    if [ -d "$BENCHMARKS_DIR/legacy" ]; then
        for bench in "$BENCHMARKS_DIR/legacy"/*/; do
            if [ -f "${bench}Makefile" ]; then
                echo "  legacy/$(basename "$bench")"
            fi
        done
    fi

    echo ""
    echo "=== System Validation ==="
    if [ -d "$BENCHMARKS_DIR/sys_validation" ]; then
        for bench in "$BENCHMARKS_DIR/sys_validation"/*/; do
            if [ -f "${bench}Makefile" ] || [ -d "${bench}hw" ]; then
                echo "  sys_validation/$(basename "$bench")"
            fi
        done
    fi

    echo ""
    echo "=== Deep Learning ==="
    for variant in nounroll kernelunroll channelunroll; do
        if [ -d "$BENCHMARKS_DIR/lenet5-$variant" ]; then
            for bench in "$BENCHMARKS_DIR/lenet5-$variant"/*/; do
                if [ -f "${bench}Makefile" ]; then
                    echo "  lenet5-$variant/$(basename "$bench")"
                fi
            done
        fi
    done

    if [ -d "$BENCHMARKS_DIR/mobilenetv2" ]; then
        echo "  mobilenetv2"
    fi
}

# Check for required tools
check_tools() {
    log_step "Checking build tools..."

    MISSING=""

    if ! command -v arm-none-eabi-gcc &> /dev/null; then
        MISSING="$MISSING arm-none-eabi-gcc"
    fi

    if ! command -v clang &> /dev/null; then
        MISSING="$MISSING clang"
    fi

    if ! command -v make &> /dev/null; then
        MISSING="$MISSING make"
    fi

    if [ -n "$MISSING" ]; then
        log_error "Missing required tools:$MISSING"
        log_info "Run the dependency installer first"
        exit 1
    fi

    log_success "All build tools available"

    # Show tool versions
    log_info "ARM GCC: $(arm-none-eabi-gcc --version | head -1)"
    log_info "Clang: $(clang --version | head -1)"
}

# Build a single benchmark
build_benchmark() {
    local bench_path="$1"
    local bench_name="$2"

    log_step "Building: $bench_name"

    if [ ! -d "$bench_path" ]; then
        log_error "Benchmark not found: $bench_path"
        return 1
    fi

    cd "$bench_path"

    # Clean if requested
    if [ "$CLEAN_FIRST" = true ]; then
        log_info "Cleaning..."
        make clean 2>/dev/null || true
    fi

    # Build
    log_info "Compiling..."
    if make -j"$NUM_JOBS" 2>&1; then
        log_success "Built: $bench_name"

        # Check for output files
        if [ -f "sw/main.elf" ] || [ -f "host/main.elf" ]; then
            log_info "  -> main.elf generated"
        fi

        # Count .ll files
        ll_count=$(find . -name "*.ll" 2>/dev/null | wc -l)
        if [ "$ll_count" -gt 0 ]; then
            log_info "  -> $ll_count LLVM IR file(s) generated"
        fi

        return 0
    else
        log_error "Failed to build: $bench_name"
        return 1
    fi
}

# Build all benchmarks in a category
build_category() {
    local category="$1"
    local category_dir="$BENCHMARKS_DIR/$category"

    log_step "Building category: $category"

    if [ ! -d "$category_dir" ]; then
        log_warn "Category not found: $category"
        return 0
    fi

    local success=0
    local failed=0

    for bench in "$category_dir"/*/; do
        if [ -f "${bench}Makefile" ]; then
            bench_name="$category/$(basename "$bench")"
            if build_benchmark "$bench" "$bench_name"; then
                ((success++))
            else
                ((failed++))
            fi
        fi
    done

    log_info "Category $category: $success succeeded, $failed failed"
}

# Main build function
build_all() {
    log_step "Building all benchmarks"

    local total_success=0
    local total_failed=0

    # Build legacy benchmarks
    if [ -d "$BENCHMARKS_DIR/legacy" ]; then
        build_category "legacy"
    fi

    # Build sys_validation
    if [ -d "$BENCHMARKS_DIR/sys_validation" ]; then
        build_category "sys_validation"
    fi

    # Build lenet5 variants
    for variant in nounroll kernelunroll channelunroll; do
        if [ -d "$BENCHMARKS_DIR/lenet5-$variant" ]; then
            build_category "lenet5-$variant"
        fi
    done

    # Build mobilenetv2
    if [ -d "$BENCHMARKS_DIR/mobilenetv2" ] && [ -f "$BENCHMARKS_DIR/mobilenetv2/Makefile" ]; then
        build_benchmark "$BENCHMARKS_DIR/mobilenetv2" "mobilenetv2"
    fi
}

# Main
main() {
    echo "=============================================="
    echo "  gem5-SALAM Benchmark Builder"
    echo "=============================================="
    echo ""

    log_info "gem5-SALAM: $GEM5_DIR"
    log_info "Benchmarks: $BENCHMARKS_DIR"

    # List only mode
    if [ "$LIST_ONLY" = true ]; then
        list_benchmarks
        exit 0
    fi

    # Check tools
    check_tools

    # Build
    if [ -z "$BENCHMARK" ] || [ "$BENCHMARK" = "all" ]; then
        build_all
    else
        # Build specific benchmark
        bench_path="$BENCHMARKS_DIR/$BENCHMARK"
        if [ -d "$bench_path" ]; then
            build_benchmark "$bench_path" "$BENCHMARK"
        else
            log_error "Benchmark not found: $BENCHMARK"
            log_info "Use --list to see available benchmarks"
            exit 1
        fi
    fi

    echo ""
    log_success "Benchmark build complete!"
}

main "$@"
