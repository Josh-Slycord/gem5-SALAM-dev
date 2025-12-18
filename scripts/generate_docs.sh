#!/bin/bash
# =============================================================================
# gem5-SALAM Unified Documentation Generator
# =============================================================================
#
# Purpose:
#   Generates integrated C++ and Python documentation using Doxygen + Sphinx
#   with the Breathe extension for unified output.
#
# Usage:
#   ./scripts/generate_docs.sh [options]
#
# Options:
#   --html      Generate HTML documentation (default)
#   --pdf       Generate PDF documentation
#   --serve     Start local documentation server after building
#   --clean     Clean build directory first
#   --all       Generate all formats
#   -h, --help  Show this help message
#
# Outputs:
#   docs/_build/html/      - HTML documentation site
#   docs/_build/latex/     - LaTeX/PDF documentation
#   docs/_build/doxygen/   - Doxygen XML (intermediate)
#
# Requirements:
#   - doxygen, graphviz: sudo apt install doxygen graphviz
#   - Python packages: pip install -r docs/requirements.txt
#
# Examples:
#   ./scripts/generate_docs.sh              # Build HTML docs
#   ./scripts/generate_docs.sh --all        # Build all formats
#   ./scripts/generate_docs.sh --serve      # Build and serve locally
#   ./scripts/generate_docs.sh --clean      # Clean and rebuild
#
# =============================================================================

set -e

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DOCS_DIR="${PROJECT_ROOT}/docs"
BUILD_DIR="${DOCS_DIR}/_build"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default options
GENERATE_HTML=true
GENERATE_PDF=false
SERVE_DOCS=false
CLEAN_FIRST=false

# =============================================================================
# Functions
# =============================================================================

usage() {
    cat << EOF
Usage: $0 [options]

gem5-SALAM Documentation Generator

Options:
  --html      Generate HTML documentation (default)
  --pdf       Generate PDF documentation
  --serve     Start local documentation server after building
  --clean     Clean build directory first
  --all       Generate all formats
  -h, --help  Show this help message

Examples:
  $0                    # Build HTML docs
  $0 --all              # Build all formats
  $0 --serve            # Build and serve locally
  $0 --clean --all      # Clean and rebuild everything
EOF
}

check_dependencies() {
    local missing=()

    echo -e "${CYAN}Checking dependencies...${NC}"

    # Check for doxygen
    if ! command -v doxygen &> /dev/null; then
        missing+=("doxygen (sudo apt install doxygen)")
    fi

    # Check for graphviz (optional but recommended)
    if ! command -v dot &> /dev/null; then
        echo -e "${YELLOW}Warning: graphviz not found (optional, for diagrams)${NC}"
        echo "  Install with: sudo apt install graphviz"
    fi

    # Check for sphinx-build
    if ! command -v sphinx-build &> /dev/null; then
        missing+=("sphinx (pip install sphinx)")
    fi

    # Check for breathe
    if ! python3 -c "import breathe" 2>/dev/null; then
        missing+=("breathe (pip install breathe)")
    fi

    # Check for sphinx_rtd_theme
    if ! python3 -c "import sphinx_rtd_theme" 2>/dev/null; then
        missing+=("sphinx-rtd-theme (pip install sphinx-rtd-theme)")
    fi

    # Report missing dependencies
    if [ ${#missing[@]} -ne 0 ]; then
        echo -e "${RED}Missing required dependencies:${NC}"
        printf '  - %s\n' "${missing[@]}"
        echo ""
        echo "Install all Python dependencies with:"
        echo "  pip install -r docs/requirements.txt"
        echo ""
        echo "Install system packages with:"
        echo "  sudo apt install doxygen graphviz"
        exit 1
    fi

    echo -e "${GREEN}All dependencies satisfied${NC}"
}

clean_build() {
    echo -e "${CYAN}Cleaning build directory...${NC}"
    rm -rf "$BUILD_DIR"
    echo -e "${GREEN}Clean complete${NC}"
}

generate_doxygen() {
    echo -e "${CYAN}Generating Doxygen XML...${NC}"

    # Create output directory
    mkdir -p "${BUILD_DIR}/doxygen"

    # Run doxygen from project root
    cd "$PROJECT_ROOT"
    doxygen "${DOCS_DIR}/Doxyfile.salam"

    # Check for warnings
    if [ -f "${BUILD_DIR}/doxygen/warnings.log" ]; then
        local warn_count=$(wc -l < "${BUILD_DIR}/doxygen/warnings.log")
        if [ "$warn_count" -gt 0 ]; then
            echo -e "${YELLOW}Doxygen warnings: ${warn_count} (see ${BUILD_DIR}/doxygen/warnings.log)${NC}"
        fi
    fi

    echo -e "${GREEN}Doxygen XML generated in ${BUILD_DIR}/doxygen/xml/${NC}"
}

generate_html() {
    echo -e "${CYAN}Building HTML documentation...${NC}"

    cd "$DOCS_DIR"
    sphinx-build -b html . _build/html -q

    echo -e "${GREEN}HTML documentation built in ${BUILD_DIR}/html/${NC}"
}

generate_pdf() {
    echo -e "${CYAN}Building PDF documentation...${NC}"

    # Check for LaTeX
    if ! command -v pdflatex &> /dev/null; then
        echo -e "${YELLOW}Warning: pdflatex not found, skipping PDF generation${NC}"
        echo "  Install with: sudo apt install texlive-latex-recommended texlive-fonts-recommended"
        return
    fi

    cd "$DOCS_DIR"
    sphinx-build -b latex . _build/latex -q

    # Build PDF
    cd _build/latex
    make all-pdf 2>/dev/null || pdflatex gem5-SALAM.tex

    echo -e "${GREEN}PDF documentation built in ${BUILD_DIR}/latex/${NC}"
}

serve_docs() {
    echo -e "${CYAN}Starting documentation server at http://localhost:8000${NC}"
    echo "Press Ctrl+C to stop"
    cd "${BUILD_DIR}/html"
    python3 -m http.server 8000
}

print_summary() {
    echo ""
    echo -e "${CYAN}============================================${NC}"
    echo -e "${CYAN}  Documentation Build Complete!${NC}"
    echo -e "${CYAN}============================================${NC}"
    echo ""

    if [ "$GENERATE_HTML" = true ] && [ -d "${BUILD_DIR}/html" ]; then
        echo -e "  HTML: ${GREEN}${BUILD_DIR}/html/index.html${NC}"
    fi

    if [ "$GENERATE_PDF" = true ] && [ -f "${BUILD_DIR}/latex/gem5-SALAM.pdf" ]; then
        echo -e "  PDF:  ${GREEN}${BUILD_DIR}/latex/gem5-SALAM.pdf${NC}"
    fi

    echo ""
    echo "To view HTML documentation:"
    echo "  1. Open ${BUILD_DIR}/html/index.html in a browser"
    echo "  2. Or run: $0 --serve"
    echo ""
}

# =============================================================================
# Main
# =============================================================================

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --html)
            GENERATE_HTML=true
            ;;
        --pdf)
            GENERATE_PDF=true
            ;;
        --serve)
            SERVE_DOCS=true
            ;;
        --clean)
            CLEAN_FIRST=true
            ;;
        --all)
            GENERATE_HTML=true
            GENERATE_PDF=true
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            exit 1
            ;;
    esac
    shift
done

# Print header
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  gem5-SALAM Documentation Generator${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# Check dependencies
check_dependencies

# Clean if requested
if [ "$CLEAN_FIRST" = true ]; then
    clean_build
fi

# Create build directory
mkdir -p "$BUILD_DIR"

# Step 1: Generate Doxygen XML (always needed for Breathe)
generate_doxygen

# Step 2: Build requested formats
if [ "$GENERATE_HTML" = true ]; then
    generate_html
fi

if [ "$GENERATE_PDF" = true ]; then
    generate_pdf
fi

# Print summary
print_summary

# Serve if requested
if [ "$SERVE_DOCS" = true ]; then
    serve_docs
fi
