#!/bin/bash
#===============================================================================
# gem5-SALAM Installation Script
#
# Automates the installation of gem5-SALAM and all dependencies on a fresh
# Ubuntu system (20.04 or 24.04, including WSL).
#
# Usage:
#   ./install.sh                    # Full installation
#   ./install.sh --deps-only        # System dependencies only
#   ./install.sh --llvm-only        # LLVM installation only
#   ./install.sh --python-only      # Python dependencies only
#   ./install.sh --with-gui         # Include GUI dependencies
#   ./install.sh --llvm-version 14  # Specify LLVM version
#   ./install.sh --verify           # Run verification after install
#   ./install.sh --help             # Show this help
#
# LLVM Version Availability:
#   Ubuntu 20.04: LLVM 9, 11, 12, 14 (default: 9)
#   Ubuntu 24.04: LLVM 14, 15, 17, 18 (default: 14)
#
# Environment:
#   GEM5_SALAM_PATH   Path to gem5-SALAM-dev (default: /home/$USER/gem5-SALAM-dev)
#   LLVM_VERSION      LLVM version to install (auto-detected if not set)
#
# Author: @agent_1 (gem5-SALAM Specialist)
# Created: 2026-01-05
# Updated: 2026-01-06 (Ubuntu 24.04 support)
#===============================================================================

set -e  # Exit on error

#-------------------------------------------------------------------------------
# Configuration
#-------------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GEM5_SALAM_PATH="${GEM5_SALAM_PATH:-/home/$USER/gem5-SALAM-dev}"
LLVM_VERSION="${LLVM_VERSION:-}"  # Will be auto-detected if not set
INSTALL_GUI=false
VERIFY_AFTER=false
DEPS_ONLY=false
LLVM_ONLY=false
PYTHON_ONLY=false

# Ubuntu version detection (set after parsing args)
UBUNTU_VERSION=""
UBUNTU_CODENAME=""

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
    head -34 "$0" | tail -28
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
# Ubuntu Version Detection
#-------------------------------------------------------------------------------

detect_ubuntu_version() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        if [[ "$ID" != "ubuntu" ]]; then
            log_warn "This script is designed for Ubuntu. Detected: $ID"
            log_warn "Attempting to continue anyway..."
        fi
        UBUNTU_VERSION="$VERSION_ID"
        UBUNTU_CODENAME="$VERSION_CODENAME"
        log_info "Detected: $PRETTY_NAME"
    else
        log_warn "Cannot detect OS version. Assuming Ubuntu 20.04."
        UBUNTU_VERSION="20.04"
        UBUNTU_CODENAME="focal"
    fi
}

get_default_llvm_version() {
    case "$UBUNTU_VERSION" in
        20.04|20.*)  echo "9" ;;
        22.04|22.*)  echo "14" ;;
        24.04|24.*)  echo "14" ;;
        *)           echo "14" ;;  # Default to 14 for unknown versions
    esac
}

get_supported_llvm_versions() {
    case "$UBUNTU_VERSION" in
        20.04|20.*)  echo "9, 11, 12, 14" ;;
        22.04|22.*)  echo "11, 12, 13, 14, 15" ;;
        24.04|24.*)  echo "14, 15, 17, 18" ;;
        *)           echo "14, 15, 17, 18" ;;
    esac
}

validate_llvm_version() {
    local supported=""
    case "$UBUNTU_VERSION" in
        20.04|20.*)
            case $LLVM_VERSION in
                9|11|12|14) : ;;  # Valid
                *) supported="9, 11, 12, 14" ;;
            esac
            ;;
        22.04|22.*)
            case $LLVM_VERSION in
                11|12|13|14|15) : ;;  # Valid
                *) supported="11, 12, 13, 14, 15" ;;
            esac
            ;;
        24.04|24.*)
            case $LLVM_VERSION in
                14|15|17|18) : ;;  # Valid
                *) supported="14, 15, 17, 18" ;;
            esac
            ;;
        *)
            case $LLVM_VERSION in
                14|15|17|18) : ;;  # Default to 24.04 support
                *) supported="14, 15, 17, 18" ;;
            esac
            ;;
    esac

    if [[ -n "$supported" ]]; then
        log_error "LLVM $LLVM_VERSION is not available on Ubuntu $UBUNTU_VERSION"
        log_error "Supported versions: $supported"
        exit 1
    fi

    log_info "LLVM version: $LLVM_VERSION"
}

#-------------------------------------------------------------------------------
# pip Compatibility
#-------------------------------------------------------------------------------

# Ubuntu 24.04 requires --break-system-packages for pip
get_pip_flags() {
    case "$UBUNTU_VERSION" in
        24.04|24.*|23.10|23.*)
            echo "--break-system-packages"
            ;;
        *)
            echo ""
            ;;
    esac
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

    local pip_flags=$(get_pip_flags)
    if [[ -n "$pip_flags" ]]; then
        log_info "Using pip flags: $pip_flags"
    fi

    # Upgrade pip
    python3 -m pip install --upgrade pip $pip_flags

    # Core dependencies
    pip3 install --user $pip_flags \
        "PyYAML>=5.0" \
        "pydot>=1.4.0"

    # Development dependencies
    pip3 install --user $pip_flags \
        "black>=22.6.0" \
        "isort>=5.10.0" \
        "mypy>=1.0.0" \
        "pytest>=7.0.0" \
        "pytest-cov>=4.0.0" \
        "pre-commit>=3.0.0"

    # Documentation
    pip3 install --user $pip_flags \
        "sphinx>=7.0.0" \
        "breathe>=4.35.0" \
        "sphinx-rtd-theme>=2.0.0" \
        "myst-parser>=2.0.0"

    log_success "Python dependencies installed"
}

install_gui_deps() {
    log_info "Installing GUI dependencies..."

    local pip_flags=$(get_pip_flags)

    pip3 install --user $pip_flags \
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
# Ubuntu: $UBUNTU_VERSION ($UBUNTU_CODENAME)
# LLVM: $LLVM_VERSION

export M5_PATH="$GEM5_SALAM_PATH"
export LLVM_VERSION="$LLVM_VERSION"
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

    # Detect Ubuntu version first
    detect_ubuntu_version

    # Set default LLVM version if not specified
    if [[ -z "$LLVM_VERSION" ]]; then
        LLVM_VERSION=$(get_default_llvm_version)
        log_info "Auto-selected LLVM version: $LLVM_VERSION"
    fi

    validate_llvm_version

    echo ""
    log_info "Installation options:"
    log_info "  Ubuntu version: $UBUNTU_VERSION ($UBUNTU_CODENAME)"
    log_info "  Supported LLVM: $(get_supported_llvm_versions)"
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
