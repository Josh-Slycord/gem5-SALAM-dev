#!/bin/bash
#
# CACTI Build Script
# Builds CACTI for memory modeling in gem5-SALAM
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

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dir)
            GEM5_DIR="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --dir PATH    Path to gem5-SALAM directory"
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

CACTI_DIR="$GEM5_DIR/ext/mcpat/cacti"

if [ ! -d "$CACTI_DIR" ]; then
    log_error "CACTI directory not found: $CACTI_DIR"
    exit 1
fi

log_step "Building CACTI"
log_info "Directory: $CACTI_DIR"

cd "$CACTI_DIR"

# Clean previous build
log_info "Cleaning previous build..."
make clean 2>/dev/null || true

# Build
log_step "Compiling CACTI..."
make all 2>&1

if [ $? -eq 0 ] && [ -f "$CACTI_DIR/cacti" ]; then
    log_success "CACTI build completed successfully!"

    # Run a quick test
    log_step "Running verification test..."
    if [ -f "$CACTI_DIR/cache.cfg" ]; then
        ./cacti -infile cache.cfg > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            log_success "CACTI verification passed!"
        else
            log_warn "CACTI verification failed, but binary was built"
        fi
    else
        log_warn "No cache.cfg found for verification, skipping test"
    fi

    log_info "CACTI binary: $CACTI_DIR/cacti"
else
    log_error "CACTI build failed!"
    exit 1
fi

# Make cacti-SALAM scripts executable
CACTI_SALAM_DIR="$GEM5_DIR/cacti-SALAM"
if [ -d "$CACTI_SALAM_DIR" ]; then
    log_step "Setting up cacti-SALAM scripts..."
    chmod +x "$CACTI_SALAM_DIR"/*.sh 2>/dev/null || true
    log_success "cacti-SALAM scripts configured"
fi

echo ""
log_success "CACTI setup complete!"
