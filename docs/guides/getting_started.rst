.. _getting-started:

===============
Getting Started
===============

This guide will help you set up gem5-SALAM and run your first accelerator
simulation.

Prerequisites
=============

System Requirements
-------------------

- **OS**: Ubuntu 20.04+ or compatible Linux distribution
- **RAM**: 8GB minimum, 16GB+ recommended
- **Disk**: 20GB+ for build artifacts
- **CPU**: Multi-core recommended for faster builds

Required Software
-----------------

.. code-block:: bash

   # Build essentials
   sudo apt install build-essential git m4 scons python3-dev \
       zlib1g zlib1g-dev libprotobuf-dev protobuf-compiler \
       libprotoc-dev libgoogle-perftools-dev python3-pydot \
       libboost-all-dev pkg-config python3-pip

   # LLVM (for IR generation)
   sudo apt install llvm clang

   # ARM cross-compiler (for benchmarks)
   sudo apt install gcc-arm-linux-gnueabihf g++-arm-linux-gnueabihf

Installation
============

Clone the Repository
--------------------

.. code-block:: bash

   git clone https://github.com/TeCSAR-UNCC/gem5-SALAM.git
   cd gem5-SALAM

Set Environment
---------------

.. code-block:: bash

   export M5_PATH=$(pwd)
   echo 'export M5_PATH=/path/to/gem5-SALAM' >> ~/.bashrc

Build gem5-SALAM
----------------

For development and debugging:

.. code-block:: bash

   # Optimized build (recommended for development)
   scons build/ARM/gem5.opt -j$(nproc)

For production runs:

.. code-block:: bash

   # Fast build (no debug support)
   scons build/ARM/gem5.fast -j$(nproc)

For debugging with GDB/Valgrind:

.. code-block:: bash

   # Debug build (full symbols)
   scons build/ARM/gem5.debug -j$(nproc)

Running Your First Simulation
=============================

Using the GUI
-------------

The easiest way to run simulations is with the SALAM GUI:

.. code-block:: bash

   cd scripts/salam_gui
   python3 main.py

The GUI allows you to:

1. Select a benchmark
2. Configure hardware parameters
3. Run the simulation
4. View results

Using Command Line
------------------

Run a vector addition benchmark:

.. code-block:: bash

   ./build/ARM/gem5.opt configs/SALAM/generated/fs_vadd.py

Run with debug output:

.. code-block:: bash

   ./build/ARM/gem5.opt \
       --debug-flags=SALAMQuick \
       configs/SALAM/generated/fs_vadd.py

Understanding Output
--------------------

Simulation output is written to ``m5out/`` by default:

- ``stats.txt`` - Performance statistics
- ``config.ini`` - Configuration dump
- ``simerr`` - Error messages
- ``simout`` - Standard output

Project Structure
=================

Key directories:

.. code-block:: text

   gem5-SALAM/
   ├── build/              # Build output
   ├── configs/            # Simulation configurations
   │   └── SALAM/          # SALAM-specific configs
   ├── docs/               # Documentation
   ├── src/hwacc/          # SALAM source code
   │   ├── LLVMRead/       # IR parsing
   │   └── HWModeling/     # Hardware models
   ├── scripts/            # Helper scripts
   │   └── salam_gui/      # GUI application
   └── benchmarks/         # Example benchmarks

Next Steps
==========

- :ref:`accelerator-design` - Design your own accelerator
- :ref:`debugging` - Debug simulation issues
- :ref:`cpp-api` - C++ API reference
- :ref:`python-api` - Python API reference
