# ==============================================================================
# validate_acc.py - Validation Accelerator Cluster Setup
# ==============================================================================
"""Validation Accelerator Cluster Setup for gem5-SALAM.

This module provides a specialized makeHWAcc function for validation benchmarks.
It creates a two-level accelerator architecture with a "top" controller that
manages DMA operations and a "bench" accelerator that performs computation.

Key Differences from HWAcc.py:
    - Uses address range 0x14000000-0x17FFFFFF (Reserved PSRAM, CS1 space)
      to avoid conflict with PCI IO space at 0x2F000000-0x2FFFFFFF
    - Two-level hierarchy: top controller + bench accelerator
    - Benchmark-specific DMA buffer sizing

Cluster Architecture::

    +------------------------------------------------------------------+
    |                    AccCluster (system.acctest)                   |
    |  Local Range: 0x14000000 - 0x17FFFFFF                            |
    |                                                                  |
    |  +------------------+                                            |
    |  |  CommInterface   |  (top)                                     |
    |  |  Manages DMA &   |                                            |
    |  |  bench control   |                                            |
    |  +--------+---------+                                            |
    |           |                                                      |
    |           v                                                      |
    |  +------------------+     +------------------+                   |
    |  |  CommInterface   |---->|  ScratchpadMemory |                  |
    |  |  (bench)         |     |  (spm)            |                  |
    |  |  reset_spm=False |     +------------------+                   |
    |  +------------------+                                            |
    |           |                                                      |
    |           v                                                      |
    |  +------------------+                                            |
    |  |  NoncoherentDma  |                                            |
    |  |  @ 0x17F00000    |                                            |
    |  |  int: 98         |                                            |
    |  +------------------+                                            |
    +------------------------------------------------------------------+

DMA Buffer Sizing (per benchmark):
    | Benchmark   | max_req_size | buffer_size |
    |-------------|--------------|-------------|
    | fft         | 8            | 48          |
    | gemm        | 8            | 64          |
    | md-knn      | 4            | 24          |
    | stencil2d   | 4            | 24          |
    | stencil3d   | 4            | 32          |
    | (default)   | 4            | 16          |

Example:
    In sys_validation.py::

        from validate_acc import makeHWAcc
        makeHWAcc(options, test_sys)

See Also:
    - HWAcc.py: Standard accelerator setup
    - sys_validation.py: Entry point for validation tests
"""

__version__ = "3.0.0.pre[1.0.0]"

import m5
from m5.objects import *
from m5.util import *
from configparser import ConfigParser  # Python 3 compatible
from HWAccConfig import *


def makeHWAcc(options, system):
    """Create a two-level validation accelerator cluster.

    This function builds a hierarchical accelerator setup with:
    - A "top" CommInterface that orchestrates DMA and controls the benchmark
    - A "bench" CommInterface that executes the actual computation
    - Shared scratchpad memory
    - A NoncoherentDma with benchmark-specific buffer sizing

    The two-level hierarchy allows measuring total system execution time
    including data movement overhead.

    Args:
        options: Parsed command-line arguments containing:
            - accpath: Path to accelerator benchmark directory
            - accbench: Name of the accelerator benchmark (e.g., 'fft', 'gemm')
        system: The gem5 System object to attach the cluster to.

    Returns:
        None. Modifies system in-place by adding system.acctest cluster.

    Note:
        Configuration files are read from:
        - {accpath}/{accbench}/hw/top.ll and top.ini
        - {accpath}/{accbench}/hw/{accbench}.ll and {accbench}.ini
    """
    hw_path = options.accpath + "/" + options.accbench + "/hw/"

    ############################# Creating the Accelerator Cluster #################################
    # Create a new Accelerator Cluster
    # Use address range 0x14000000-0x17FFFFFF (Reserved PSRAM, CS1 space) to avoid
    # conflict with PCI IO space at 0x2F000000-0x2FFFFFFF in VExpress_GEM5_V1
    system.acctest = AccCluster()
    local_low = 0x14000000
    local_high = 0x17FFFFFF
    local_range = AddrRange(local_low, local_high)
    external_range = [
        AddrRange(0x00000000, local_low - 1),
        AddrRange(local_high + 1, 0xFFFFFFFF),
    ]
    system.acctest._attach_bridges(system, local_range, external_range)
    system.acctest._connect_caches(system, options, l2coherent=False)
    gic = system.realview.gic

    ############################# Adding Devices to Cluster ##################################
    # Add the top function
    # The top function manages the DMA and bench accelerator, and is used to measure the
    # total system execution time, including data movement.
    acc = "top"
    config = hw_path + acc + ".ini"
    ir = hw_path + acc + ".ll"
    system.acctest.top = CommInterface(devicename=acc, gic=gic)
    AccConfig(system.acctest.top, ir, config)
    system.acctest._connect_hwacc(system.acctest.top)

    # Add the benchmark function
    acc = options.accbench
    config = hw_path + acc + ".ini"
    ir = hw_path + acc + ".ll"
    system.acctest.bench = CommInterface(devicename=acc, gic=gic, reset_spm=False)
    AccConfig(system.acctest.bench, ir, config)
    system.acctest.bench.pio = system.acctest.top.local
    system.acctest.spm = ScratchpadMemory()
    # AccSPMConfig(system.acctest.bench, system.acctest.spm, config)
    system.acctest._connect_spm(system.acctest.spm)
    # system.acctest.bench.enable_debug_msgs = True

    if acc == "fft":
        max_req_size = 8
        buffer_size = 48
    elif acc == "gemm":
        max_req_size = 8
        buffer_size = 64
    elif acc == "md-knn":
        max_req_size = 4
        buffer_size = 24
    elif acc == "stencil2d":
        max_req_size = 4
        buffer_size = 24
    elif acc == "stencil3d":
        max_req_size = 4
        buffer_size = 32
    else:
        max_req_size = 4
        buffer_size = 16

    # Add the cluster DMA (address within 0x14000000-0x17FFFFFF range)
    system.acctest.dma = NoncoherentDma(
        pio_addr=0x17F00000, pio_size=21, gic=gic, int_num=98
    )
    system.acctest.dma.cluster_dma = system.acctest.local_bus.slave
    system.acctest.dma.dma = system.acctest.coherency_bus.slave
    system.acctest.dma.pio = system.acctest.top.local
    system.acctest.dma.max_req_size = max_req_size
    system.acctest.dma.buffer_size = buffer_size
