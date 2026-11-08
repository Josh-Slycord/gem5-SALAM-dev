# Experimental source-identified simulator appliance; see README.md.
# The build context is produced by build_gem5_wsl.ps1 from git archive.
# GUI/runtime acceptance is separate from building a simulator.
ARG BASE_IMAGE=ubuntu:22.04
FROM ${BASE_IMAGE}
ARG SALAM_COMMIT
ARG SOURCE_ARCHIVE_SHA256
ARG BUILD_JOBS=2
LABEL org.opencontainers.image.source="https://github.com/Josh-Slycord/gem5-SALAM-dev"
LABEL org.opencontainers.image.revision="${SALAM_COMMIT}"
LABEL org.salam.source-archive.sha256="${SOURCE_ARCHIVE_SHA256}"

ENV DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential clang-14 llvm-14 llvm-14-dev python3 python3-dev \
    python3-pip python-is-python3 git pkg-config zlib1g-dev \
    libprotobuf-dev protobuf-compiler libgoogle-perftools-dev \
    libboost-all-dev libpng-dev libhdf5-dev libunwind-dev \
    gcc-arm-none-eabi libstdc++-arm-none-eabi-newlib \
    libnewlib-arm-none-eabi gcc-aarch64-linux-gnu \
    libgl1 libegl1 libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 \
    libdbus-1-3 libxcb-cursor0 libxcb-xinerama0 libxcb-keysyms1 \
    libx11-xcb1 ca-certificates

RUN useradd -m -s /bin/bash salam && \
    printf '[user]\ndefault=salam\n' > /etc/wsl.conf && \
    mkdir -p /opt/salam/engine /opt/salam/provenance && \
    chown -R salam:salam /opt/salam
COPY source.tar /opt/salam/provenance/source.tar
WORKDIR /opt/salam/engine
RUN test -n "${SALAM_COMMIT}" && \
    test "${#SALAM_COMMIT}" -eq 40 && \
    echo "${SOURCE_ARCHIVE_SHA256}  /opt/salam/provenance/source.tar" \
      | sha256sum --check --strict && \
    tar -xf /opt/salam/provenance/source.tar && \
    chown -R salam:salam /opt/salam
RUN python3 -m pip install --no-cache-dir \
    -r workbench/requirements-gui-gem5-26-validated.txt

USER salam
ENV M5_PATH=/opt/salam/engine
ENV PATH=/usr/lib/llvm-14/bin:/usr/local/bin:/usr/bin:/bin
ENV PYTHONPATH=/home/salam/workbench
ENV PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
# Build the exact archived sources. No line-number sed patches or overlays.
RUN make -C system/arm/bootloader/arm CROSS_COMPILE=arm-none-eabi- && \
    make -C system/arm/bootloader/arm64 CROSS_COMPILE=aarch64-linux-gnu-
RUN python3 /usr/local/bin/scons build/ARM/gem5.opt \
    --with-salam LLVM_CONFIG=/usr/bin/llvm-config-14 \
    CXX=/usr/bin/g++ PYTHON_CONFIG=/usr/bin/python3-config \
    USE_KVM=0 PROTOCOL=CHI -j${BUILD_JOBS}
RUN ./build/ARM/gem5.opt --build-info \
      > /opt/salam/provenance/gem5-build-info.txt && \
    sha256sum build/ARM/gem5.opt \
      > /opt/salam/provenance/simulator.sha256 && \
    python3 -m pip freeze > /opt/salam/provenance/python-packages.txt && \
    dpkg-query -W > /opt/salam/provenance/debian-packages.txt && \
    printf '%s\n' "${SALAM_COMMIT}" \
      > /opt/salam/provenance/source-commit.txt && \
    cp -a workbench /home/salam/workbench

# DISABLED: the former ad-hoc GEMM compilation and workspace.json generation.
# They bypassed the supported generator/SDK flow and supplied no genuine build
# or generation receipts or GUI adapter. A successful --build-info is not GUI
# readiness, numerical validation, or a usable configured simulation.
# Use the supported Workbench bootstrap with actual verified receipts first.
# RUN python3 -m salam_workbench.configurator_app --inspect

WORKDIR /home/salam
CMD ["/bin/bash"]
