#!/bin/bash
# =============================================================================
# gem5-SALAM Debug Launcher Script
# =============================================================================
# Launch gem5-SALAM under GDB or DDD for interactive debugging.
#
# Usage:
#   ./scripts/run_debug.sh gdb [break_tick] [gem5_args...]
#   ./scripts/run_debug.sh ddd [break_tick] [gem5_args...]
#
# Examples:
#   ./scripts/run_debug.sh gdb 0 configs/SALAM/generated/fs_vadd.py
#   ./scripts/run_debug.sh gdb 1000000 configs/SALAM/generated/fs_vadd.py
#   ./scripts/run_debug.sh ddd 0 configs/SALAM/generated/fs_vadd.py
#
# Requirements:
#   - gem5.debug build: scons build/ARM/gem5.debug
#   - M5_PATH environment variable set
#   - GDB or DDD installed
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
MODE="${1:-gdb}"
BREAK_TICK="${2:-0}"

# Check for minimum arguments
if [ $# -lt 3 ]; then
    echo -e "${YELLOW}Usage: $0 <gdb|ddd> <break_tick> <gem5_args...>${NC}"
    echo ""
    echo "Examples:"
    echo "  $0 gdb 0 configs/SALAM/generated/fs_vadd.py"
    echo "  $0 gdb 1000000 configs/SALAM/generated/fs_vadd.py --mem-size=512MB"
    echo "  $0 ddd 0 configs/SALAM/generated/fs_vadd.py"
    exit 1
fi

# Skip first two args (mode and break_tick)
shift 2

# Check M5_PATH
if [ -z "$M5_PATH" ]; then
    echo -e "${RED}Error: M5_PATH environment variable not set${NC}"
    echo "Set it with: export M5_PATH=/path/to/gem5-SALAM-dev"
    exit 1
fi

# Paths
GEM5_DEBUG="${M5_PATH}/build/ARM/gem5.debug"
GDB_INIT="${M5_PATH}/scripts/gdb/salam.gdbinit"

# Check gem5.debug exists
if [ ! -f "$GEM5_DEBUG" ]; then
    echo -e "${RED}Error: gem5.debug not found at ${GEM5_DEBUG}${NC}"
    echo "Build it with: scons build/ARM/gem5.debug -j\$(nproc)"
    exit 1
fi

# Check gdbinit exists
if [ ! -f "$GDB_INIT" ]; then
    echo -e "${YELLOW}Warning: GDB init file not found at ${GDB_INIT}${NC}"
    GDB_INIT=""
fi

# Build debug-break argument
DEBUG_BREAK=""
if [ "$BREAK_TICK" != "0" ]; then
    DEBUG_BREAK="--debug-break=${BREAK_TICK}"
    echo -e "${GREEN}Will break at tick: ${BREAK_TICK}${NC}"
fi

echo -e "${GREEN}Launching gem5-SALAM in ${MODE} mode...${NC}"
echo "Binary: ${GEM5_DEBUG}"
echo "Args: ${DEBUG_BREAK} $@"
echo ""

case "$MODE" in
    gdb)
        if [ -n "$GDB_INIT" ]; then
            gdb -x "$GDB_INIT" --args "$GEM5_DEBUG" $DEBUG_BREAK "$@"
        else
            gdb --args "$GEM5_DEBUG" $DEBUG_BREAK "$@"
        fi
        ;;
    ddd)
        if ! command -v ddd &> /dev/null; then
            echo -e "${RED}Error: DDD not installed${NC}"
            echo "Install with: sudo apt install ddd"
            exit 1
        fi
        if [ -n "$GDB_INIT" ]; then
            ddd --gdb -x "$GDB_INIT" "$GEM5_DEBUG" -- $DEBUG_BREAK "$@"
        else
            ddd --gdb "$GEM5_DEBUG" -- $DEBUG_BREAK "$@"
        fi
        ;;
    *)
        echo -e "${RED}Error: Unknown mode '${MODE}'. Use 'gdb' or 'ddd'${NC}"
        exit 1
        ;;
esac
