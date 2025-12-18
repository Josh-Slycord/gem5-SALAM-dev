#!/bin/bash
# =============================================================================
# gem5-SALAM Valgrind Runner Script
# =============================================================================
# Run gem5-SALAM under Valgrind for memory debugging.
#
# Usage:
#   ./scripts/run_valgrind.sh [gem5_args...]
#
# Examples:
#   ./scripts/run_valgrind.sh configs/SALAM/generated/fs_vadd.py
#   ./scripts/run_valgrind.sh configs/SALAM/generated/fs_vadd.py --mem-size=512MB
#
# Requirements:
#   - gem5.debug build: scons build/ARM/gem5.debug -j$(nproc)
#   - M5_PATH environment variable set
#   - Valgrind installed: sudo apt install valgrind
#
# Output:
#   - valgrind-output.txt: Main Valgrind report
#   - Standard gem5 output in m5out/
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Check for arguments
if [ $# -lt 1 ]; then
    echo -e "${YELLOW}Usage: $0 <gem5_args...>${NC}"
    echo ""
    echo "Examples:"
    echo "  $0 configs/SALAM/generated/fs_vadd.py"
    echo "  $0 configs/SALAM/generated/fs_vadd.py --mem-size=512MB"
    echo ""
    echo "Options (via environment variables):"
    echo "  VALGRIND_OPTS    Additional Valgrind options"
    echo "  VALGRIND_OUTPUT  Output file (default: valgrind-output.txt)"
    exit 1
fi

# Check M5_PATH
if [ -z "$M5_PATH" ]; then
    echo -e "${RED}Error: M5_PATH environment variable not set${NC}"
    echo "Set it with: export M5_PATH=/path/to/gem5-SALAM-dev"
    exit 1
fi

# Check Valgrind
if ! command -v valgrind &> /dev/null; then
    echo -e "${RED}Error: Valgrind not installed${NC}"
    echo "Install with: sudo apt install valgrind"
    exit 1
fi

# Paths
GEM5_DEBUG="${M5_PATH}/build/ARM/gem5.debug"
SUPP_FILE="${M5_PATH}/util/salam.supp"
OUTPUT_FILE="${VALGRIND_OUTPUT:-valgrind-output.txt}"

# Check gem5.debug exists
if [ ! -f "$GEM5_DEBUG" ]; then
    echo -e "${RED}Error: gem5.debug not found at ${GEM5_DEBUG}${NC}"
    echo "Build it with: scons build/ARM/gem5.debug -j\$(nproc)"
    exit 1
fi

# Build suppression argument
SUPP_ARG=""
if [ -f "$SUPP_FILE" ]; then
    SUPP_ARG="--suppressions=${SUPP_FILE}"
    echo -e "${GREEN}Using suppression file: ${SUPP_FILE}${NC}"
else
    echo -e "${YELLOW}Warning: Suppression file not found at ${SUPP_FILE}${NC}"
    echo "You may see false positives from Python and gem5 internals."
fi

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  gem5-SALAM Valgrind Memory Check${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""
echo -e "Binary:  ${GEM5_DEBUG}"
echo -e "Output:  ${OUTPUT_FILE}"
echo -e "Args:    $@"
echo ""
echo -e "${YELLOW}Note: Valgrind runs MUCH slower than normal execution.${NC}"
echo -e "${YELLOW}      Consider using a smaller benchmark for testing.${NC}"
echo ""

# Run Valgrind
valgrind \
    --leak-check=full \
    --show-leak-kinds=definite,possible \
    --track-origins=yes \
    --verbose \
    ${SUPP_ARG} \
    ${VALGRIND_OPTS} \
    --log-file="${OUTPUT_FILE}" \
    "$GEM5_DEBUG" "$@"

EXIT_CODE=$?

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Valgrind Complete${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""
echo -e "Output saved to: ${GREEN}${OUTPUT_FILE}${NC}"
echo ""

# Parse summary from output
if [ -f "$OUTPUT_FILE" ]; then
    echo -e "${CYAN}Summary:${NC}"
    grep -E "(definitely lost|possibly lost|still reachable|ERROR SUMMARY)" "$OUTPUT_FILE" | head -10
    echo ""

    # Check for errors
    ERRORS=$(grep "ERROR SUMMARY" "$OUTPUT_FILE" | grep -oP '\d+ errors' | head -1)
    if echo "$ERRORS" | grep -q "0 errors"; then
        echo -e "${GREEN}No memory errors detected!${NC}"
    else
        echo -e "${RED}Memory errors detected: ${ERRORS}${NC}"
        echo -e "Review ${OUTPUT_FILE} for details."
    fi
fi

exit $EXIT_CODE
