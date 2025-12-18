.. _accelerator-design:

==================
Accelerator Design
==================

This guide explains how to design and simulate custom hardware accelerators
using gem5-SALAM.

Overview
========

gem5-SALAM accelerators consist of:

1. **LLVM IR** - The accelerator's computational logic
2. **Hardware Configuration** - Functional units, memory, timing
3. **System Integration** - Memory mapping, DMA, interrupts

Design Workflow
---------------

.. code-block:: text

   C/C++ Source → Clang → LLVM IR → gem5-SALAM → Simulation Results
        ↓                    ↓
   Host Driver Code    Hardware Config

Writing Accelerator Code
========================

Source Code Guidelines
----------------------

Write your accelerator kernel in C:

.. code-block:: c

   // vadd.c - Vector Addition Accelerator
   #define N 1024

   void vadd(int* a, int* b, int* c) {
       for (int i = 0; i < N; i++) {
           c[i] = a[i] + b[i];
       }
   }

Guidelines:

- Use fixed-size arrays or pointer arithmetic
- Avoid dynamic memory allocation
- Avoid recursive functions
- Use simple control flow

Generating LLVM IR
------------------

Compile to LLVM IR:

.. code-block:: bash

   clang -S -emit-llvm -O2 -target arm-linux-gnueabihf vadd.c -o vadd.ll

Optimization flags:

- ``-O0``: No optimization (easier to debug)
- ``-O2``: Standard optimization (recommended)
- ``-O3``: Aggressive optimization

Hardware Configuration
======================

Functional Units
----------------

Configure the number of each functional unit type:

.. code-block:: python

   # In your Python config file
   hw.fu = FunctionalUnits()
   hw.fu.num_int_adders = 4      # Integer adders
   hw.fu.num_int_multipliers = 2  # Integer multipliers
   hw.fu.num_fp_adders = 2        # Floating-point adders
   hw.fu.num_fp_multipliers = 2   # Floating-point multipliers
   hw.fu.num_comparators = 2      # Comparison units
   hw.fu.num_gep_units = 2        # Address calculation
   hw.fu.num_conversion_units = 1 # Type conversion

Cycle Counts
------------

Configure latencies for operations:

.. code-block:: python

   hw.cycles = CycleCounts()
   hw.cycles.int_add_latency = 1    # Integer add: 1 cycle
   hw.cycles.int_mul_latency = 3    # Integer multiply: 3 cycles
   hw.cycles.fp_add_latency = 4     # FP add: 4 cycles
   hw.cycles.fp_mul_latency = 5     # FP multiply: 5 cycles
   hw.cycles.load_latency = 2       # Memory load: 2 cycles
   hw.cycles.store_latency = 1      # Memory store: 1 cycle

Memory Configuration
--------------------

Configure scratchpad memory:

.. code-block:: python

   spm = ScratchpadMemory()
   spm.size = "64kB"           # Total size
   spm.latency = "2ns"         # Access latency
   spm.read_ports = 2          # Concurrent reads
   spm.write_ports = 1         # Concurrent writes

System Integration
==================

Memory Mapping
--------------

Map accelerator registers to system memory:

.. code-block:: python

   # Communication interface (control registers)
   comm = CommInterface()
   comm.pio_addr = 0x2f100000  # Base address
   comm.pio_size = 64          # Register space size

   # Scratchpad memory
   spm = ScratchpadMemory()
   spm.addr_range = AddrRange(0x2f200000, size='64kB')

DMA Configuration
-----------------

Configure DMA for bulk data transfers:

.. code-block:: python

   dma = NoncoherentDma()
   dma.max_pending = 16        # Max in-flight requests
   dma.buffer_size = 256       # Transfer buffer size

Host Driver Code
================

Write driver code to control the accelerator from Linux:

.. code-block:: c

   #include <stdio.h>
   #include <fcntl.h>
   #include <sys/mman.h>

   #define ACC_BASE     0x2f100000
   #define ACC_CONTROL  0x00
   #define ACC_STATUS   0x04
   #define ACC_DMA_SRC  0x10
   #define ACC_DMA_DST  0x14
   #define ACC_DMA_LEN  0x18

   volatile uint32_t* acc_regs;

   void init_accelerator() {
       int fd = open("/dev/mem", O_RDWR | O_SYNC);
       acc_regs = mmap(NULL, 4096, PROT_READ | PROT_WRITE,
                       MAP_SHARED, fd, ACC_BASE);
   }

   void run_vadd(uint32_t* src_a, uint32_t* src_b,
                 uint32_t* dst, size_t len) {
       // Configure DMA transfers
       acc_regs[ACC_DMA_SRC/4] = (uint32_t)src_a;
       acc_regs[ACC_DMA_DST/4] = (uint32_t)dst;
       acc_regs[ACC_DMA_LEN/4] = len;

       // Start accelerator
       acc_regs[ACC_CONTROL/4] = 1;

       // Wait for completion
       while (acc_regs[ACC_STATUS/4] != 0) {
           // Polling or use interrupt
       }
   }

Example: Matrix Multiplication
==============================

Here's a complete example for a matrix multiplication accelerator.

Accelerator Kernel
------------------

.. code-block:: c

   // matmul.c
   #define N 32

   void matmul(int A[N][N], int B[N][N], int C[N][N]) {
       for (int i = 0; i < N; i++) {
           for (int j = 0; j < N; j++) {
               int sum = 0;
               for (int k = 0; k < N; k++) {
                   sum += A[i][k] * B[k][j];
               }
               C[i][j] = sum;
           }
       }
   }

Hardware Configuration
----------------------

.. code-block:: python

   # matmul_config.py
   from m5.objects import *

   # Create cluster
   cluster = AccCluster()

   # High-performance configuration
   hw = HWInterface()
   hw.fu = FunctionalUnits()
   hw.fu.num_int_adders = 8
   hw.fu.num_int_multipliers = 4  # More multipliers for matmul

   hw.cycles = CycleCounts()
   hw.cycles.int_mul_latency = 3

   # Large scratchpad for matrices
   spm = ScratchpadMemory()
   spm.size = "128kB"  # 3 x 32x32 matrices

Performance Analysis
====================

After simulation, analyze results:

.. code-block:: bash

   # Enable performance debug flags
   ./build/ARM/gem5.opt \
       --debug-flags=SALAMPerfDebug \
       configs/SALAM/generated/fs_matmul.py

Key metrics to examine:

- **Cycles**: Total execution time
- **Stall cycles**: Time waiting for resources
- **FU utilization**: How well FUs are used
- **Memory bandwidth**: Data transfer efficiency

See :ref:`debugging` for detailed performance analysis.
