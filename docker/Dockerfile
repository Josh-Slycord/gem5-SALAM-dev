# ==============================================================================
# gem5-SALAM Dockerfile (Pre-configured, Pre-compiled for WSL2 Export)
#
# Target: Ubuntu 22.04 LTS (Jammy)
# Toolchains: Python 3.10 + LLVM 14 + GCC 11 + SCons 4.0 + PySide6
# Pinned Ref: Josh-Slycord/gem5-SALAM-dev @ 9c83f862e4ce96f85680e255c12164106e79986d
# ==============================================================================

FROM ubuntu:22.04

# Prevent interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

# ------------------------------------------------------------------------------
# 1. System toolchains, LLVM 14, cross-compilers, and GUI libraries
# ------------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    make \
    clang-14 \
    llvm-14 \
    llvm-14-dev \
    python3 \
    python3-dev \
    python3-pip \
    python-is-python3 \
    git \
    scons \
    pkg-config \
    zlib1g-dev \
    libprotobuf-dev \
    protobuf-compiler \
    libgoogle-perftools-dev \
    libboost-all-dev \
    libpng-dev \
    libhdf5-dev \
    libunwind-dev \
    gcc-arm-none-eabi \
    libstdc++-arm-none-eabi-newlib \
    libnewlib-arm-none-eabi \
    gcc-aarch64-linux-gnu \
    libgl1 \
    libegl1 \
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    libfontconfig1 \
    libdbus-1-3 \
    sudo \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------------------------
# 2. Pin LLVM 14 as default clang & llvm-config
# ------------------------------------------------------------------------------
RUN update-alternatives --install /usr/bin/clang clang /usr/bin/clang-14 100 && \
    update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-14 100 && \
    update-alternatives --install /usr/bin/llvm-config llvm-config /usr/bin/llvm-config-14 100

# ------------------------------------------------------------------------------
# 3. Python packages required by SALAM, Configurator, and PySide6 Workbench GUI
# ------------------------------------------------------------------------------
RUN python3 -m pip install --no-cache-dir \
    "PyYAML>=6.0" \
    "numpy>=1.24.0,<2.0.0" \
    "pydot>=4.0.0" \
    "networkx>=3.0" \
    "pytest>=7.0.0" \
    "packaging>=24.0" \
    "ply>=3.11" \
    "PySide6==6.8.3" \
    "shiboken6==6.8.3"

# ------------------------------------------------------------------------------
# 4. User setup matching the Windows/WSL environment
# ------------------------------------------------------------------------------
RUN useradd -m -s /bin/bash -G sudo jslycord && \
    echo "jslycord ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Pre-configure WSL initialization (default user + systemd support)
RUN printf "[user]\ndefault=jslycord\n[boot]\nsystemd=true\n" > /etc/wsl.conf

USER jslycord
WORKDIR /home/jslycord

# ------------------------------------------------------------------------------
# 5. Clone gem5-SALAM-dev at target commit
# ------------------------------------------------------------------------------
ARG REPO_URL="https://github.com/Josh-Slycord/gem5-SALAM-dev.git"
ARG COMMIT_HASH="9c83f862e4ce96f85680e255c12164106e79986d"

RUN git clone ${REPO_URL} /home/jslycord/gem5-SALAM-dev && \
    cd /home/jslycord/gem5-SALAM-dev && \
    git checkout ${COMMIT_HASH}

# ------------------------------------------------------------------------------
# 6. Pre-compile ARM32 & ARM64 Bootloaders
# ------------------------------------------------------------------------------
WORKDIR /home/jslycord/gem5-SALAM-dev
RUN make -C system/arm/bootloader/arm CROSS_COMPILE=arm-none-eabi- && \
    make -C system/arm/bootloader/arm64 CROSS_COMPILE=aarch64-linux-gnu-

# ------------------------------------------------------------------------------
# 7. Pre-compile gem5.opt simulator with SALAM accelerator model enabled
# ------------------------------------------------------------------------------
ENV M5_PATH=/home/jslycord/gem5-SALAM-dev
ENV PATH=/usr/lib/llvm-14/bin:/home/jslycord/.local/bin:$PATH
ENV PYTHONPATH=/home/jslycord/gem5-SALAM-dev/workbench:$PYTHONPATH

RUN scons build/ARM/gem5.opt --with-salam LLVM_CONFIG=/usr/bin/llvm-config-14 PROTOCOL=CHI USE_KVM=0 -j$(nproc)

# Verify the compiled binary runs cleanly and reports SALAM capabilities
RUN ./build/ARM/gem5.opt --build-info

# ------------------------------------------------------------------------------
# 8. Pre-compile Benchmarks (GEMM Hardware Bitcode & Software ELF)
# ------------------------------------------------------------------------------
RUN cd /home/jslycord/gem5-SALAM-dev/benchmarks/sys_validation/gemm/hw && \
    clang -O1 -S -fno-slp-vectorize -fno-vectorize -fno-unroll-loops -fno-inline -fno-builtin -emit-llvm -I/usr/include/newlib gemm.c top.c -target armv7-pc-none-eabi && \
    cd /home/jslycord/gem5-SALAM-dev/benchmarks/sys_validation/gemm/sw && \
    make LNK_OPT='-nostartfiles -Wl,--allow-multiple-definition'

# Copy execution trace visualizer
RUN mkdir -p /home/jslycord/gem5-SALAM-dev/workbench/visualizer
COPY --chown=jslycord:jslycord export_salam_visualizer.py /home/jslycord/gem5-SALAM-dev/workbench/visualizer/export_salam_visualizer.py
RUN chmod +x /home/jslycord/gem5-SALAM-dev/workbench/visualizer/export_salam_visualizer.py

# Update run_gemm.sh with gem5 26 debug flags and automatic visualizer export
RUN sed -i '36s/.*/DEBUG_FLAGS=SALAM_Debug/' /home/jslycord/gem5-SALAM-dev/run_gemm.sh && \
    printf '\nif [ -f "$OUTDIR/observability/fu-scheduling-system.${BENCH}_clstr.${BENCH}.invocation-1.json" ]; then\n    echo "=== Generating Execution Visualizer ==="\n    python3 workbench/visualizer/export_salam_visualizer.py "$OUTDIR/observability/fu-scheduling-system.${BENCH}_clstr.${BENCH}.invocation-1.json" "$OUTDIR/visualizer.html"\n    echo "Visualizer HTML ready: $OUTDIR/visualizer.html"\nfi\n' >> /home/jslycord/gem5-SALAM-dev/run_gemm.sh && \
    chmod +x /home/jslycord/gem5-SALAM-dev/run_gemm.sh

# ------------------------------------------------------------------------------
# 9. Pre-configure Workbench Workspace & Shell Environment
# ------------------------------------------------------------------------------
RUN python3 -c "import json; data = {'schema_version': 1, 'project': 'SALAM Research Workbench - gem5 26', 'engine': {'distribution': 'gem5-salam-prebuilt', 'path': '/home/jslycord/gem5-SALAM-dev'}, 'configuration_engine': {'distribution': 'gem5-salam-prebuilt', 'path': '/home/jslycord/gem5-SALAM-dev', 'toolchain_profile': {'id': 'gem5-26-retained-salam', 'python': '/usr/bin/python3', 'scons': '/usr/bin/scons', 'cxx': '/usr/bin/g++', 'python_config': '/usr/bin/python3-config', 'linker': '/usr/bin/ld', 'llvm_bin': '/usr/lib/llvm-14/bin', 'llvm_config': '/usr/bin/llvm-config-14', 'arm_bin': '/usr/bin'}}}; json.dump(data, open('/home/jslycord/gem5-SALAM-dev/workbench/workspace.json', 'w'), indent=2)"

# Verify offline GUI readiness check
RUN cd /home/jslycord/gem5-SALAM-dev/workbench && \
    QT_QPA_PLATFORM=offscreen python3 -m salam_workbench.configurator_app --inspect

# Populate user bashrc with paths and convenient aliases
RUN printf "\n# gem5-SALAM Environment & Shortcuts\nexport M5_PATH=/home/jslycord/gem5-SALAM-dev\nexport PYTHONPATH=/home/jslycord/gem5-SALAM-dev/workbench:\$PYTHONPATH\nexport PATH=/usr/lib/llvm-14/bin:/home/jslycord/.local/bin:\$PATH\n\nalias gem5='/home/jslycord/gem5-SALAM-dev/build/ARM/gem5.opt'\nalias workbench='cd /home/jslycord/gem5-SALAM-dev/workbench && python3 -m salam_workbench.configurator_app'\nalias run-gemm='cd /home/jslycord/gem5-SALAM-dev && ./run_gemm.sh'\nalias salam-inspect='cd /home/jslycord/gem5-SALAM-dev/workbench && QT_QPA_PLATFORM=offscreen python3 -m salam_workbench.configurator_app --inspect'\n" >> /home/jslycord/.bashrc

# Set landing directory
WORKDIR /home/jslycord/gem5-SALAM-dev
CMD ["/bin/bash"]
