#!/bin/bash
#
# gem5-SALAM Build Script
# Builds gem5-SALAM from source
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
BUILD_TYPE="opt"  # opt, debug, fast
NUM_JOBS=$(nproc)
TARGET_ISA="ARM"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dir)
            GEM5_DIR="$2"
            shift 2
            ;;
        --type)
            BUILD_TYPE="$2"
            shift 2
            ;;
        --jobs|-j)
            NUM_JOBS="$2"
            shift 2
            ;;
        --isa)
            TARGET_ISA="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --dir PATH      Path to gem5-SALAM directory"
            echo "  --type TYPE     Build type: opt (default), debug, fast"
            echo "  --jobs N        Number of parallel jobs (default: $(nproc))"
            echo "  --isa ISA       Target ISA: ARM (default), X86, RISCV"
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

if [ ! -f "$GEM5_DIR/SConstruct" ]; then
    log_error "Not a valid gem5 directory (SConstruct not found): $GEM5_DIR"
    exit 1
fi

# Check for scons
if ! command -v scons &> /dev/null; then
    if [ -f "$HOME/.local/bin/scons" ]; then
        export PATH="$HOME/.local/bin:$PATH"
    else
        log_error "scons not found. Please install it: pip3 install scons"
        exit 1
    fi
fi

log_step "Building gem5-SALAM"
log_info "Directory: $GEM5_DIR"
log_info "Build type: $BUILD_TYPE"
log_info "Target ISA: $TARGET_ISA"
log_info "Parallel jobs: $NUM_JOBS"

cd "$GEM5_DIR"

# Build command
BUILD_TARGET="build/${TARGET_ISA}/gem5.${BUILD_TYPE}"

log_step "Running scons..."
echo ""

# Run scons with output
scons "$BUILD_TARGET" -j"$NUM_JOBS" 2>&1

if [ $? -eq 0 ]; then
    echo ""
    log_success "Build completed successfully!"
    log_info "Binary location: $GEM5_DIR/$BUILD_TARGET"
else
    echo ""
    log_error "Build failed!"
    exit 1
fi
