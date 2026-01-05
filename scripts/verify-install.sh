#!/bin/bash
#===============================================================================
# gem5-SALAM Installation Verification Script
#
# Verifies that all dependencies are correctly installed and configured.
#
# Usage:
#   ./verify-install.sh              # Run all checks
#   ./verify-install.sh --verbose    # Verbose output
#   ./verify-install.sh --fix        # Attempt to fix issues
#
# Exit codes:
#   0 - All checks passed
#   1 - One or more checks failed
#
# Author: @agent_1 (gem5-SALAM Specialist)
# Created: 2026-01-05
#===============================================================================

# Note: Not using set -e because we want to continue checking even if some fail

#-------------------------------------------------------------------------------
# Configuration
#-------------------------------------------------------------------------------

VERBOSE=false
FIX_ISSUES=false
FAILED_CHECKS=0
PASSED_CHECKS=0
WARNED_CHECKS=0

#-------------------------------------------------------------------------------
# Colors
#-------------------------------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

#-------------------------------------------------------------------------------
# Logging
#-------------------------------------------------------------------------------

log_check()   { echo -e "${CYAN}[CHECK]${NC} $1"; }
log_pass()    { echo -e "${GREEN}[PASS]${NC} $1"; PASSED_CHECKS=$((PASSED_CHECKS + 1)); }
log_fail()    { echo -e "${RED}[FAIL]${NC} $1"; FAILED_CHECKS=$((FAILED_CHECKS + 1)); }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; WARNED_CHECKS=$((WARNED_CHECKS + 1)); }
log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_verbose() { $VERBOSE && echo -e "       $1" || true; }

#-------------------------------------------------------------------------------
# Parse Arguments
#-------------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose|-v) VERBOSE=true; shift ;;
        --fix)        FIX_ISSUES=true; shift ;;
        --help|-h)    head -20 "$0" | tail -15; exit 0 ;;
        *)            echo "Unknown option: $1"; exit 1 ;;
    esac
done

#-------------------------------------------------------------------------------
# Check Functions
#-------------------------------------------------------------------------------

check_command() {
    local cmd=$1
    local package=$2
    log_check "Checking $cmd..."
    if command -v "$cmd" &> /dev/null; then
        local version=$(eval "$cmd --version 2>/dev/null | head -1" || echo "unknown")
        log_pass "$cmd is installed ($version)"
        return 0
    else
        log_fail "$cmd is not installed (package: $package)"
        return 1
    fi
}

check_apt_package() {
    local pkg=$1
    log_check "Checking apt package: $pkg..."
    if dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
        log_pass "$pkg is installed"
        return 0
    else
        log_fail "$pkg is not installed"
        return 1
    fi
}

check_python_module() {
    local module=$1
    local pip_name=${2:-$module}
    log_check "Checking Python module: $module..."
    if python3 -c "import $module" 2>/dev/null; then
        log_pass "$module is available"
        return 0
    else
        log_fail "$module is not available (pip install $pip_name)"
        return 1
    fi
}

check_env_var() {
    local var=$1
    local expected=${2:-}
    log_check "Checking environment variable: $var..."
    if [[ -n "${!var:-}" ]]; then
        log_pass "$var is set: ${!var}"
        if [[ -n "$expected" && "${!var}" != "$expected" ]]; then
            log_warn "Expected: $expected"
        fi
        return 0
    else
        log_fail "$var is not set"
        return 1
    fi
}

check_path_exists() {
    local path=$1
    local desc=${2:-path}
    log_check "Checking $desc exists: $path..."
    if [[ -e "$path" ]]; then
        log_pass "$desc exists"
        return 0
    else
        log_fail "$desc does not exist: $path"
        return 1
    fi
}

#-------------------------------------------------------------------------------
# System Dependencies Check
#-------------------------------------------------------------------------------

check_system_deps() {
    echo ""
    echo "========================================"
    echo "System Dependencies"
    echo "========================================"

    check_command "gcc" "build-essential"
    check_command "g++" "build-essential"
    check_command "make" "build-essential"
    check_command "git" "git"
    check_command "m4" "m4"
    check_command "scons" "scons"
    check_command "pkg-config" "pkg-config"
    check_command "protoc" "protobuf-compiler"
    check_command "dot" "graphviz"

    # Check for ARM cross-compiler (optional)
    log_check "Checking ARM cross-compiler..."
    if command -v arm-none-eabi-gcc &> /dev/null; then
        log_pass "ARM cross-compiler is installed"
    else
        log_warn "ARM cross-compiler not installed (optional)"
    fi
}

#-------------------------------------------------------------------------------
# LLVM Check
#-------------------------------------------------------------------------------

check_llvm() {
    echo ""
    echo "========================================"
    echo "LLVM Installation"
    echo "========================================"

    check_command "clang" "clang"
    check_command "llvm-config" "llvm"
    check_command "llvm-link" "llvm"
    check_command "opt" "llvm"
    check_command "llc" "llvm"

    # Check LLVM version
    log_check "Checking LLVM version..."
    if command -v llvm-config &> /dev/null; then
        local llvm_version=$(llvm-config --version)
        log_info "LLVM version: $llvm_version"

        # Check if version is supported (9, 11, or 14)
        local major_version=$(echo "$llvm_version" | cut -d. -f1)
        case $major_version in
            9|11|14)
                log_pass "LLVM version $major_version is supported"
                ;;
            *)
                log_warn "LLVM version $major_version may not be fully tested"
                ;;
        esac
    fi

    # Test clang can emit LLVM IR
    log_check "Testing clang LLVM IR generation..."
    local test_file=$(mktemp --suffix=.c)
    echo "int main() { return 0; }" > "$test_file"
    if clang -emit-llvm -S "$test_file" -o /dev/null 2>/dev/null; then
        log_pass "clang can emit LLVM IR"
    else
        log_fail "clang cannot emit LLVM IR"
    fi
    rm -f "$test_file"
}

#-------------------------------------------------------------------------------
# Python Check
#-------------------------------------------------------------------------------

check_python() {
    echo ""
    echo "========================================"
    echo "Python Environment"
    echo "========================================"

    check_command "python3" "python3"
    check_command "pip3" "python3-pip"

    # Check Python version
    log_check "Checking Python version..."
    local py_version=$(python3 --version 2>&1 | awk '{print $2}')
    local py_major=$(echo "$py_version" | cut -d. -f1)
    local py_minor=$(echo "$py_version" | cut -d. -f2)
    log_info "Python version: $py_version"
    if [[ "$py_major" -eq 3 && "$py_minor" -ge 8 ]]; then
        log_pass "Python $py_version is supported"
    else
        log_warn "Python 3.8+ recommended (found $py_version)"
    fi

    # Core modules
    check_python_module "yaml" "PyYAML"
    check_python_module "pydot"

    # Dev modules (optional)
    log_check "Checking optional dev modules..."
    for module in pytest black isort mypy; do
        if python3 -c "import $module" 2>/dev/null; then
            log_verbose "$module: installed"
        else
            log_verbose "$module: not installed (optional)"
        fi
    done
}

#-------------------------------------------------------------------------------
# GUI Dependencies Check
#-------------------------------------------------------------------------------

check_gui_deps() {
    echo ""
    echo "========================================"
    echo "GUI Dependencies (Optional)"
    echo "========================================"

    local gui_modules=("PySide6" "pyqtgraph" "networkx" "pandas" "matplotlib" "zmq")
    local all_installed=true

    for module in "${gui_modules[@]}"; do
        log_check "Checking $module..."
        if python3 -c "import $module" 2>/dev/null; then
            log_pass "$module is available"
        else
            log_warn "$module not installed (GUI optional)"
            all_installed=false
        fi
    done

    if $all_installed; then
        log_pass "All GUI dependencies installed"
    else
        log_warn "Some GUI dependencies missing - GUI features may be limited"
    fi
}

#-------------------------------------------------------------------------------
# gem5-SALAM Environment Check
#-------------------------------------------------------------------------------

check_gem5_salam() {
    echo ""
    echo "========================================"
    echo "gem5-SALAM Environment"
    echo "========================================"

    # Check M5_PATH
    check_env_var "M5_PATH"

    # Check if gem5-SALAM directory exists
    if [[ -n "${M5_PATH:-}" ]]; then
        check_path_exists "$M5_PATH" "gem5-SALAM directory"
        check_path_exists "$M5_PATH/src/hwacc" "SALAM hardware accelerator source"
        check_path_exists "$M5_PATH/benchmarks" "Benchmarks directory"
        check_path_exists "$M5_PATH/SALAM-Configurator" "SALAM-Configurator"

        # Check for built gem5
        log_check "Checking for compiled gem5..."
        if [[ -f "$M5_PATH/build/ARM/gem5.opt" ]]; then
            log_pass "gem5.opt binary exists"
        elif [[ -f "$M5_PATH/build/ARM/gem5.debug" ]]; then
            log_pass "gem5.debug binary exists"
        else
            log_warn "No compiled gem5 binary found (run: scons build/ARM/gem5.opt)"
        fi
    fi

    # Check environment file
    check_path_exists "$HOME/.gem5-salam-env" "Environment file"
}

#-------------------------------------------------------------------------------
# Summary
#-------------------------------------------------------------------------------

print_summary() {
    echo ""
    echo "========================================"
    echo "Verification Summary"
    echo "========================================"
    echo ""
    echo -e "  ${GREEN}Passed:${NC}  $PASSED_CHECKS"
    echo -e "  ${YELLOW}Warnings:${NC} $WARNED_CHECKS"
    echo -e "  ${RED}Failed:${NC}  $FAILED_CHECKS"
    echo ""

    if [[ $FAILED_CHECKS -eq 0 ]]; then
        echo -e "${GREEN}All required checks passed!${NC}"
        if [[ $WARNED_CHECKS -gt 0 ]]; then
            echo -e "${YELLOW}Note: Some optional components are missing.${NC}"
        fi
        return 0
    else
        echo -e "${RED}Some required checks failed.${NC}"
        echo "Please review the output above and install missing dependencies."
        return 1
    fi
}

#-------------------------------------------------------------------------------
# Main
#-------------------------------------------------------------------------------

main() {
    echo "========================================"
    echo "gem5-SALAM Installation Verification"
    echo "========================================"
    echo "Date: $(date)"
    echo "Host: $(hostname)"

    check_system_deps
    check_llvm
    check_python
    check_gui_deps
    check_gem5_salam

    print_summary
}

main "$@"
