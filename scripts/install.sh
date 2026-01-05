#!/bin/bash
#===============================================================================
# gem5-SALAM Installation Script
#
# Automates the installation of gem5-SALAM and all dependencies on a fresh
# Ubuntu 20.04 system (including WSL).
#
# Usage:
#   ./install.sh                    # Full installation
#   ./install.sh --deps-only        # System dependencies only
#   ./install.sh --llvm-only        # LLVM installation only
#   ./install.sh --python-only      # Python dependencies only
#   ./install.sh --with-gui         # Include GUI dependencies
#   ./install.sh --llvm-version 14  # Specify LLVM version (9, 11, or 14)
#   ./install.sh --verify           # Run verification after install
#   ./install.sh --help             # Show this help
#
# Environment:
#   GEM5_SALAM_PATH   Path to gem5-SALAM-dev (default: /home/$USER/gem5-SALAM-dev)
#   LLVM_VERSION      LLVM version to install (default: 9)
#
# Author: @agent_1 (gem5-SALAM Specialist)
# Created: 2026-01-05
#===============================================================================

set -e  # Exit on error

#-------------------------------------------------------------------------------
# Configuration
#-------------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GEM5_SALAM_PATH="${GEM5_SALAM_PATH:-/home/$USER/gem5-SALAM-dev}"
LLVM_VERSION="${LLVM_VERSION:-9}"
INSTALL_GUI=false
VERIFY_AFTER=false
DEPS_ONLY=false
LLVM_ONLY=false
PYTHON_ONLY=false

#-------------------------------------------------------------------------------
# Colors and Logging
#-------------------------------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

#-------------------------------------------------------------------------------
# Usage
#-------------------------------------------------------------------------------

show_help() {
    head -30 "$0" | tail -20
    exit 0
}

#-------------------------------------------------------------------------------
# Parse Arguments
#-------------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case $1 in
        --deps-only)    DEPS_ONLY=true; shift ;;
        --llvm-only)    LLVM_ONLY=true; shift ;;
        --python-only)  PYTHON_ONLY=true; shift ;;
        --with-gui)     INSTALL_GUI=true; shift ;;
        --verify)       VERIFY_AFTER=true; shift ;;
        --llvm-version) LLVM_VERSION="$2"; shift 2 ;;
        --help|-h)      show_help ;;
        *)              log_error "Unknown option: $1"; show_help ;;
    esac
done

#-------------------------------------------------------------------------------
# Validation
#-------------------------------------------------------------------------------

validate_llvm_version() {
    case $LLVM_VERSION in
        9|11|12|14) log_info "LLVM version: $LLVM_VERSION" ;;
        *) log_error "Unsupported LLVM version: $LLVM_VERSION (use 9, 11, 12, or 14)"; exit 1 ;;
    esac
}

check_ubuntu_version() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        if [[ "$ID" != "ubuntu" ]]; then
            log_warn "This script is designed for Ubuntu. Detected: $ID"
        fi
        log_info "OS: $PRETTY_NAME"
    fi
}

#-------------------------------------------------------------------------------
# System Dependencies
#-------------------------------------------------------------------------------

install_system_deps() {
    log_info "Installing system dependencies..."

    sudo apt-get update

    # Core build tools
    sudo apt-get install -y \
        build-essential \
        git \
        m4 \
        scons \
        zlib1g \
        zlib1g-dev \
        pkg-config

    # Protobuf
    sudo apt-get install -y \
        libprotobuf-dev \
        protobuf-compiler \
        libprotoc-dev

    # Performance profiling
    sudo apt-get install -y \
        libgoogle-perftools-dev

    # Python development
    sudo apt-get install -y \
        python3-dev \
        python3-pip \
        python-is-python3

    # Boost libraries
    sudo apt-get install -y \
        libboost-all-dev

    # Graphviz (for dot file generation)
    sudo apt-get install -y \
        graphviz

    # ARM cross-compiler (for embedded targets)
    sudo apt-get install -y \
        gcc-arm-none-eabi

    log_success "System dependencies installed"
}

#-------------------------------------------------------------------------------
# LLVM Installation
#-------------------------------------------------------------------------------

install_llvm() {
    log_info "Installing LLVM-$LLVM_VERSION..."

    # Install LLVM and Clang
    sudo apt-get install -y \
        llvm-$LLVM_VERSION \
        llvm-$LLVM_VERSION-dev \
        llvm-$LLVM_VERSION-tools \
        clang-$LLVM_VERSION

    log_success "LLVM-$LLVM_VERSION installed"

    # Setup alternatives
    setup_llvm_alternatives
}

setup_llvm_alternatives() {
    log_info "Setting up LLVM alternatives..."

    local priority=100

    # Main LLVM tools
    sudo update-alternatives --install /usr/bin/llvm-config llvm-config /usr/bin/llvm-config-$LLVM_VERSION $priority
    sudo update-alternatives --install /usr/bin/llvm-link llvm-link /usr/bin/llvm-link-$LLVM_VERSION $priority
    sudo update-alternatives --install /usr/bin/llvm-dis llvm-dis /usr/bin/llvm-dis-$LLVM_VERSION $priority
    sudo update-alternatives --install /usr/bin/llvm-as llvm-as /usr/bin/llvm-as-$LLVM_VERSION $priority
    sudo update-alternatives --install /usr/bin/opt opt /usr/bin/opt-$LLVM_VERSION $priority
    sudo update-alternatives --install /usr/bin/llc llc /usr/bin/llc-$LLVM_VERSION $priority

    # Clang
    sudo update-alternatives --install /usr/bin/clang clang /usr/bin/clang-$LLVM_VERSION $priority
    sudo update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-$LLVM_VERSION $priority

    # Set as default
    sudo update-alternatives --set llvm-config /usr/bin/llvm-config-$LLVM_VERSION
    sudo update-alternatives --set clang /usr/bin/clang-$LLVM_VERSION
    sudo update-alternatives --set clang++ /usr/bin/clang++-$LLVM_VERSION

    log_success "LLVM alternatives configured"
}

#-------------------------------------------------------------------------------
# Python Dependencies
#-------------------------------------------------------------------------------

install_python_deps() {
    log_info "Installing Python dependencies..."

    # Upgrade pip
    python3 -m pip install --upgrade pip

    # Core dependencies
    pip3 install --user \
        "PyYAML>=5.0" \
        "pydot>=1.4.0"

    # Development dependencies
    pip3 install --user \
        "black>=22.6.0" \
        "isort>=5.10.0" \
        "mypy>=1.0.0" \
        "pytest>=7.0.0" \
        "pytest-cov>=4.0.0" \
        "pre-commit>=3.0.0"

    # Documentation
    pip3 install --user \
        "sphinx>=7.0.0" \
        "breathe>=4.35.0" \
        "sphinx-rtd-theme>=2.0.0" \
        "myst-parser>=2.0.0"

    log_success "Python dependencies installed"
}

install_gui_deps() {
    log_info "Installing GUI dependencies..."

    pip3 install --user \
        "PySide6>=6.5.0" \
        "pyqtgraph>=0.13.0" \
        "networkx>=3.0" \
        "pandas>=2.0.0" \
        "matplotlib>=3.7.0" \
        "pyzmq>=25.0.0"

    log_success "GUI dependencies installed"
}

#-------------------------------------------------------------------------------
# Environment Setup
#-------------------------------------------------------------------------------

setup_environment() {
    log_info "Setting up environment..."

    local bashrc="$HOME/.bashrc"
    local env_file="$HOME/.gem5-salam-env"

    # Create environment file
    cat > "$env_file" << ENV_EOF
# gem5-SALAM Environment Configuration
# Generated by install.sh on $(date)

export M5_PATH="$GEM5_SALAM_PATH"
export PYTHONPATH="\$M5_PATH/packages/salam-config:\$PYTHONPATH"

# Optional: Add gem5 build to PATH
# export PATH="\$M5_PATH/build/ARM:\$PATH"
ENV_EOF

    # Add source to .bashrc if not already present
    if ! grep -q ".gem5-salam-env" "$bashrc" 2>/dev/null; then
        echo "" >> "$bashrc"
        echo "# gem5-SALAM environment" >> "$bashrc"
        echo "[ -f ~/.gem5-salam-env ] && source ~/.gem5-salam-env" >> "$bashrc"
        log_info "Added gem5-SALAM environment to .bashrc"
    else
        log_info "gem5-SALAM environment already in .bashrc"
    fi

    # Source for current session
    source "$env_file"

    log_success "Environment configured"
    log_info "Environment file: $env_file"
    log_info "M5_PATH: $M5_PATH"
}

#-------------------------------------------------------------------------------
# Main Installation
#-------------------------------------------------------------------------------

main() {
    echo "========================================"
    echo "gem5-SALAM Installation Script"
    echo "========================================"
    echo ""

    validate_llvm_version
    check_ubuntu_version

    echo ""
    log_info "Installation options:"
    log_info "  GEM5_SALAM_PATH: $GEM5_SALAM_PATH"
    log_info "  LLVM_VERSION: $LLVM_VERSION"
    log_info "  INSTALL_GUI: $INSTALL_GUI"
    log_info "  VERIFY_AFTER: $VERIFY_AFTER"
    echo ""

    # Selective installation
    if $DEPS_ONLY; then
        install_system_deps
        exit 0
    fi

    if $LLVM_ONLY; then
        install_llvm
        exit 0
    fi

    if $PYTHON_ONLY; then
        install_python_deps
        if $INSTALL_GUI; then
            install_gui_deps
        fi
        exit 0
    fi

    # Full installation
    install_system_deps
    install_llvm
    install_python_deps

    if $INSTALL_GUI; then
        install_gui_deps
    fi

    setup_environment

    echo ""
    echo "========================================"
    log_success "Installation complete!"
    echo "========================================"
    echo ""
    log_info "Next steps:"
    log_info "  1. Source your environment: source ~/.gem5-salam-env"
    log_info "  2. Verify installation: ./scripts/verify-install.sh"
    log_info "  3. Build gem5: scons build/ARM/gem5.opt -j\$(nproc)"
    echo ""

    if $VERIFY_AFTER; then
        log_info "Running verification..."
        if [[ -f "$SCRIPT_DIR/verify-install.sh" ]]; then
            "$SCRIPT_DIR/verify-install.sh"
        else
            log_warn "verify-install.sh not found"
        fi
    fi
}

main "$@"
