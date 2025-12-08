#!/bin/bash
#
# gem5-SALAM Dependency Installer
# This script installs all required dependencies for building gem5-SALAM
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "\n${GREEN}==>${NC} $1"
}

# Check if running as root or with sudo
check_sudo() {
    if [ "$EUID" -ne 0 ]; then
        if ! command -v sudo &> /dev/null; then
            log_error "This script requires root privileges. Please run as root or install sudo."
            exit 1
        fi
        SUDO="sudo"
    else
        SUDO=""
    fi
}

# Detect the Linux distribution
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO=$ID
        DISTRO_VERSION=$VERSION_ID
        log_info "Detected distribution: $DISTRO $DISTRO_VERSION"
    else
        log_error "Cannot detect Linux distribution"
        exit 1
    fi
}

# Update package lists
update_packages() {
    log_step "Updating package lists..."
    case $DISTRO in
        ubuntu|debian)
            $SUDO apt-get update
            ;;
        fedora)
            $SUDO dnf check-update || true
            ;;
        arch)
            $SUDO pacman -Sy
            ;;
        *)
            log_warn "Unknown distribution, skipping package update"
            ;;
    esac
    log_success "Package lists updated"
}

# Install build essentials
install_build_essentials() {
    log_step "Installing build essentials..."
    case $DISTRO in
        ubuntu|debian)
            $SUDO apt-get install -y \
                build-essential \
                gcc \
                g++ \
                make \
                cmake \
                git \
                wget \
                curl \
                pkg-config \
                zlib1g-dev \
                libssl-dev
            ;;
        fedora)
            $SUDO dnf install -y \
                @development-tools \
                gcc \
                gcc-c++ \
                make \
                cmake \
                git \
                wget \
                curl \
                pkgconfig \
                zlib-devel \
                openssl-devel
            ;;
        arch)
            $SUDO pacman -S --noconfirm \
                base-devel \
                gcc \
                make \
                cmake \
                git \
                wget \
                curl \
                pkg-config \
                zlib \
                openssl
            ;;
        *)
            log_error "Unsupported distribution: $DISTRO"
            exit 1
            ;;
    esac
    log_success "Build essentials installed"
}

# Install Python and required packages
install_python() {
    log_step "Installing Python 3 and pip..."
    case $DISTRO in
        ubuntu|debian)
            $SUDO apt-get install -y \
                python3 \
                python3-pip \
                python3-dev \
                python3-venv \
                python3-setuptools
            ;;
        fedora)
            $SUDO dnf install -y \
                python3 \
                python3-pip \
                python3-devel \
                python3-setuptools
            ;;
        arch)
            $SUDO pacman -S --noconfirm \
                python \
                python-pip \
                python-setuptools
            ;;
    esac

    # Install Python packages for gem5
    log_info "Installing Python packages for gem5..."
    pip3 install --user scons pyyaml

    log_success "Python installed"
}

# Install LLVM/Clang
install_llvm() {
    log_step "Installing LLVM and Clang..."

    LLVM_VERSION=${LLVM_VERSION:-14}

    case $DISTRO in
        ubuntu|debian)
            # Check if specific LLVM version is available
            if apt-cache policy llvm-$LLVM_VERSION 2>/dev/null | grep -q "Candidate:"; then
                # Version available, try to install
                if $SUDO apt-get install -y \
                    llvm-$LLVM_VERSION \
                    llvm-$LLVM_VERSION-dev \
                    clang-$LLVM_VERSION \
                    libclang-$LLVM_VERSION-dev 2>/dev/null; then

                    # Create symlinks if they don't exist
                    if [ ! -f /usr/bin/llvm-config ] && [ -f /usr/bin/llvm-config-$LLVM_VERSION ]; then
                        $SUDO update-alternatives --install /usr/bin/llvm-config llvm-config /usr/bin/llvm-config-$LLVM_VERSION 100
                    fi
                    if [ ! -f /usr/bin/clang ] && [ -f /usr/bin/clang-$LLVM_VERSION ]; then
                        $SUDO update-alternatives --install /usr/bin/clang clang /usr/bin/clang-$LLVM_VERSION 100
                    fi
                else
                    log_warn "LLVM $LLVM_VERSION installation failed, trying to add LLVM repository..."
                    # Add LLVM official repository
                    wget -qO- https://apt.llvm.org/llvm-snapshot.gpg.key | $SUDO apt-key add - 2>/dev/null || true
                    $SUDO add-apt-repository -y "deb http://apt.llvm.org/$VERSION_CODENAME/ llvm-toolchain-$VERSION_CODENAME-$LLVM_VERSION main" 2>/dev/null || true
                    $SUDO apt-get update
                    $SUDO apt-get install -y llvm-$LLVM_VERSION llvm-$LLVM_VERSION-dev clang-$LLVM_VERSION libclang-$LLVM_VERSION-dev || \
                        $SUDO apt-get install -y llvm llvm-dev clang libclang-dev
                fi
            else
                log_info "LLVM $LLVM_VERSION not in default repos, adding LLVM repository..."
                # Add LLVM official repository for the specific version
                wget -qO- https://apt.llvm.org/llvm-snapshot.gpg.key | $SUDO apt-key add - 2>/dev/null || true
                # Get Ubuntu codename (focal, jammy, etc.)
                CODENAME=$(lsb_release -cs 2>/dev/null || echo "focal")
                $SUDO add-apt-repository -y "deb http://apt.llvm.org/$CODENAME/ llvm-toolchain-$CODENAME-$LLVM_VERSION main" 2>/dev/null || true
                $SUDO apt-get update
                if ! $SUDO apt-get install -y llvm-$LLVM_VERSION llvm-$LLVM_VERSION-dev clang-$LLVM_VERSION libclang-$LLVM_VERSION-dev 2>/dev/null; then
                    log_warn "Could not install LLVM $LLVM_VERSION, falling back to default version"
                    $SUDO apt-get install -y llvm llvm-dev clang libclang-dev
                fi
            fi
            ;;
        fedora)
            $SUDO dnf install -y llvm llvm-devel clang clang-devel
            ;;
        arch)
            $SUDO pacman -S --noconfirm llvm clang
            ;;
    esac
    log_success "LLVM/Clang installed"
}

# Install ARM cross-compiler
install_arm_toolchain() {
    log_step "Installing ARM cross-compilation toolchain..."
    case $DISTRO in
        ubuntu|debian)
            $SUDO apt-get install -y \
                gcc-arm-none-eabi \
                binutils-arm-none-eabi \
                libnewlib-arm-none-eabi
            ;;
        fedora)
            $SUDO dnf install -y arm-none-eabi-gcc arm-none-eabi-newlib
            ;;
        arch)
            $SUDO pacman -S --noconfirm arm-none-eabi-gcc arm-none-eabi-newlib
            ;;
    esac
    log_success "ARM toolchain installed"
}

# Install gem5 specific dependencies
install_gem5_deps() {
    log_step "Installing gem5 specific dependencies..."
    case $DISTRO in
        ubuntu|debian)
            $SUDO apt-get install -y \
                libgoogle-perftools-dev \
                protobuf-compiler \
                libprotobuf-dev \
                libhdf5-dev \
                libpng-dev \
                libboost-all-dev \
                m4 \
                swig \
                libcapstone-dev
            ;;
        fedora)
            $SUDO dnf install -y \
                gperftools-devel \
                protobuf-compiler \
                protobuf-devel \
                hdf5-devel \
                libpng-devel \
                boost-devel \
                m4 \
                swig \
                capstone-devel
            ;;
        arch)
            $SUDO pacman -S --noconfirm \
                gperftools \
                protobuf \
                hdf5 \
                libpng \
                boost \
                m4 \
                swig \
                capstone
            ;;
    esac
    log_success "gem5 dependencies installed"
}

# Install multilib for CACTI (32-bit support)
install_multilib() {
    log_step "Installing 32-bit libraries for CACTI..."
    case $DISTRO in
        ubuntu|debian)
            $SUDO apt-get install -y gcc-multilib g++-multilib
            ;;
        fedora)
            $SUDO dnf install -y glibc-devel.i686 libstdc++-devel.i686
            ;;
        arch)
            # Arch requires enabling multilib repo first
            log_warn "For Arch Linux, ensure multilib repository is enabled in /etc/pacman.conf"
            $SUDO pacman -S --noconfirm lib32-gcc-libs lib32-glibc || true
            ;;
    esac
    log_success "32-bit libraries installed"
}

# Set up environment variables
setup_environment() {
    log_step "Setting up environment variables..."

    SALAM_ENV_FILE="$HOME/.gem5-salam-env"

    cat > "$SALAM_ENV_FILE" << 'EOF'
# gem5-SALAM Environment Variables
# Source this file in your .bashrc or .zshrc

# M5_PATH should point to your gem5-SALAM directory
# export M5_PATH=/path/to/gem5-SALAM

# Add local pip packages to PATH
export PATH="$HOME/.local/bin:$PATH"

# LLVM configuration (adjust version as needed)
if command -v llvm-config-14 &> /dev/null; then
    export LLVM_CONFIG=llvm-config-14
elif command -v llvm-config &> /dev/null; then
    export LLVM_CONFIG=llvm-config
fi
EOF

    # Add source line to .bashrc if not already present
    if ! grep -q "gem5-salam-env" "$HOME/.bashrc" 2>/dev/null; then
        echo "" >> "$HOME/.bashrc"
        echo "# gem5-SALAM environment" >> "$HOME/.bashrc"
        echo "[ -f \"$SALAM_ENV_FILE\" ] && source \"$SALAM_ENV_FILE\"" >> "$HOME/.bashrc"
    fi

    log_success "Environment configured in $SALAM_ENV_FILE"
    log_info "Run 'source ~/.bashrc' or restart your shell to apply changes"
}

# Verify installation
verify_installation() {
    log_step "Verifying installation..."

    MISSING=""

    # Check each component
    command -v gcc &> /dev/null || MISSING="$MISSING gcc"
    command -v g++ &> /dev/null || MISSING="$MISSING g++"
    command -v python3 &> /dev/null || MISSING="$MISSING python3"
    command -v pip3 &> /dev/null || MISSING="$MISSING pip3"
    command -v scons &> /dev/null || (pip3 show scons &> /dev/null) || MISSING="$MISSING scons"
    command -v git &> /dev/null || MISSING="$MISSING git"
    command -v make &> /dev/null || MISSING="$MISSING make"
    (command -v llvm-config &> /dev/null || command -v llvm-config-14 &> /dev/null) || MISSING="$MISSING llvm"
    (command -v clang &> /dev/null || command -v clang-14 &> /dev/null) || MISSING="$MISSING clang"
    command -v arm-none-eabi-gcc &> /dev/null || MISSING="$MISSING arm-none-eabi-gcc"

    if [ -n "$MISSING" ]; then
        log_warn "Some components may not be in PATH:$MISSING"
        log_info "They may still be installed but require PATH configuration"
    else
        log_success "All dependencies verified!"
    fi
}

# Print summary
print_summary() {
    echo ""
    echo "=============================================="
    echo "  gem5-SALAM Dependencies Installation Complete"
    echo "=============================================="
    echo ""
    echo "Installed components:"
    echo "  - Build essentials (gcc, g++, make, cmake)"
    echo "  - Python 3 with pip and scons"
    echo "  - LLVM/Clang toolchain"
    echo "  - ARM cross-compilation toolchain"
    echo "  - gem5 dependencies (protobuf, boost, etc.)"
    echo "  - 32-bit libraries for CACTI"
    echo ""
    echo "Next steps:"
    echo "  1. Source your environment: source ~/.bashrc"
    echo "  2. Set M5_PATH in ~/.gem5-salam-env"
    echo "  3. Build gem5-SALAM: scons build/ARM/gem5.opt -j\$(nproc)"
    echo ""
}

# Main installation flow
main() {
    echo "=============================================="
    echo "  gem5-SALAM Dependency Installer"
    echo "=============================================="
    echo ""

    check_sudo
    detect_distro
    update_packages
    install_build_essentials
    install_python
    install_llvm
    install_arm_toolchain
    install_gem5_deps
    install_multilib
    setup_environment
    verify_installation
    print_summary
}

# Run main function
main "$@"
