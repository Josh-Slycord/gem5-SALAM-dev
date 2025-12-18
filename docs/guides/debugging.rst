.. _debugging:

=========
Debugging
=========

This guide covers debugging techniques for gem5-SALAM simulations.

.. note::

   For the complete debugging reference, see the
   `DEBUGGING.md <https://github.com/TeCSAR-UNCC/gem5-SALAM/blob/main/docs/DEBUGGING.md>`_
   file in the repository.

Quick Start
===========

Basic debug output:

.. code-block:: bash

   ./build/ARM/gem5.opt --debug-flags=SALAMQuick configs/SALAM/generated/fs_vadd.py

Verbose execution tracing:

.. code-block:: bash

   ./build/ARM/gem5.opt --debug-flags=SALAMVerbose configs/SALAM/generated/fs_vadd.py

Build Types
===========

Choose the appropriate build for your needs:

============  ==============  ========  ========  =======  ==============
Build         Debug Symbols   Asserts   DPRINTF   Speed    Use Case
============  ==============  ========  ========  =======  ==============
gem5.opt      Yes             Yes       Yes       Medium   Development
gem5.debug    Yes (full)      Yes       Yes       Slow     GDB, Valgrind
gem5.fast     No              No        No        Fast     Production
============  ==============  ========  ========  =======  ==============

Debug Flags
===========

Compound Flags (Presets)
------------------------

===============  ====================================  ===================
Preset           Flags Included                        Use Case
===============  ====================================  ===================
SALAMQuick       Exec, Comm, Stats                     Lightweight debugging
SALAMVerbose     Exec, ExecCompute, ExecQueue, etc.    Detailed execution
SALAMAll         All SALAM flags                       Everything
SALAMMemory      Comm, MemSPM, MemReg, DMA             Memory subsystem
SALAMStallDebug  ExecStall, FU, ExecQueue              Stall analysis
SALAMDMADebug    DMA, DMAStream, DMABuffer             DMA issues
SALAMPerfDebug   Stats, Results, ExecStall, FU         Performance profiling
===============  ====================================  ===================

Usage Examples
--------------

.. code-block:: bash

   # Single flag
   ./build/ARM/gem5.opt --debug-flags=SALAMExec configs/...

   # Multiple flags
   ./build/ARM/gem5.opt --debug-flags=SALAMExec,SALAMComm,Cache configs/...

   # Output to file
   ./build/ARM/gem5.opt --debug-flags=SALAMVerbose --debug-file=trace.out configs/...

   # Time-bounded tracing
   ./build/ARM/gem5.opt --debug-flags=SALAMExec \
       --debug-start=1000000 \
       --debug-end=2000000 \
       configs/...

GDB Debugging
=============

Using the Debug Script
----------------------

.. code-block:: bash

   # Basic GDB session
   ./scripts/run_debug.sh gdb 0 configs/SALAM/generated/fs_vadd.py

   # Break at specific tick
   ./scripts/run_debug.sh gdb 1000000 configs/SALAM/generated/fs_vadd.py

SALAM GDB Commands
------------------

Once in GDB with the SALAM init file loaded:

==================  =========================================
Command             Description
==================  =========================================
salam-help          Show all SALAM GDB commands
salam-break-compute Break at accelerator compute entry
salam-break-dma     Break on DMA response
salam-break-start   Break at accelerator start
salam-break-finish  Break at accelerator finish
salam-break-all     Set all common breakpoints
salam-events        Dump event queue
salam-tick          Print current tick
salam-flag-on       Enable debug flag at runtime
salam-flag-off      Disable debug flag at runtime
==================  =========================================

Example Session
---------------

.. code-block:: text

   (gdb) salam-break-all
   Breakpoint set at CommInterface::start
   Breakpoint set at LLVMInterface::compute
   Breakpoint set at CommInterface::finish

   (gdb) run
   ...
   Breakpoint 1, gem5::CommInterface::start()

   (gdb) salam-tick
   $1 = 1000000

   (gdb) salam-flag-on "SALAMExecCompute"
   Debug flag 'SALAMExecCompute' enabled

   (gdb) continue

Valgrind Memory Checking
========================

Using the Valgrind Script
-------------------------

.. code-block:: bash

   # Basic memory check
   ./scripts/run_valgrind.sh configs/SALAM/generated/fs_vadd.py

   # With custom output file
   VALGRIND_OUTPUT=my-valgrind.txt ./scripts/run_valgrind.sh configs/...

Understanding Output
--------------------

.. code-block:: text

   ==12345== LEAK SUMMARY:
   ==12345==    definitely lost: 0 bytes      <- Real leaks - FIX THESE
   ==12345==    indirectly lost: 0 bytes      <- Real leaks
   ==12345==      possibly lost: 1,234 bytes  <- Investigate
   ==12345==    still reachable: 45,678 bytes <- Usually OK
   ==12345==         suppressed: 123 bytes    <- Filtered (known issues)

Common Debug Scenarios
======================

"Why is my accelerator stalling?"
---------------------------------

.. code-block:: bash

   ./build/ARM/gem5.opt --debug-flags=SALAMStallDebug configs/...

Look for:

- RAW hazard messages (data dependencies)
- FU unavailable messages (resource contention)
- Memory stall messages (cache misses, DMA delays)

"Data is corrupted somewhere"
-----------------------------

.. code-block:: bash

   ./build/ARM/gem5.opt --debug-flags=SALAMDataDebug configs/...

Trace data through:

- Scratchpad memory operations
- Register bank reads/writes
- DMA transfers
- Computation results

"DMA isn't working right"
-------------------------

.. code-block:: bash

   ./build/ARM/gem5.opt --debug-flags=SALAMDMADebug configs/...

Check:

- DMA request/response timing
- Buffer fill levels
- Address translations
- CommInterface handshakes

"Performance analysis needed"
-----------------------------

.. code-block:: bash

   ./build/ARM/gem5.opt --debug-flags=SALAMPerfDebug configs/...

Collect:

- Cycle counts
- Stall breakdown
- FU utilization
- Statistics summary

Troubleshooting
===============

Debug flags not producing output
--------------------------------

1. Check you're using ``gem5.opt`` or ``gem5.debug`` (not ``gem5.fast``)
2. Verify flag name spelling (case-sensitive)
3. Check simulation reaches the code with debug output

GDB can't find symbols
----------------------

1. Use ``gem5.debug`` build
2. Ensure binary wasn't stripped
3. Rebuild: ``scons build/ARM/gem5.debug -j$(nproc)``

Valgrind is too slow
--------------------

1. Use a smaller benchmark
2. Disable unnecessary checks: ``--leak-check=no``
3. Focus on specific code with ``--toggle-collect``

Too much debug output
---------------------

1. Use ``--debug-start`` and ``--debug-end`` to limit time range
2. Use ``--debug-file`` to write to file
3. Use more specific flags instead of compound flags
4. Pipe through ``grep`` to filter
