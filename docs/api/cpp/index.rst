.. _cpp-api:

=================
C++ API Reference
=================

This section documents the C++ implementation of gem5-SALAM. The documentation
is automatically generated from Doxygen comments in the source code using the
Breathe extension.

.. contents:: Contents
   :local:
   :depth: 2

Core Components
===============

LLVMInterface
-------------

The central execution engine that processes LLVM IR instructions, manages the
dynamic Control-Data Flow Graph (CDFG), enforces functional unit capacity, and
implements ``Drainable`` and per-instance graph teardown semantics.

.. doxygenclass:: LLVMInterface
   :members:
   :protected-members:
   :undoc-members:

CommInterface
-------------

Communication interface between the accelerator compute unit and local/global
memory ports, scratchpad memories, register banks, and streaming endpoints.

.. doxygenclass:: CommInterface
   :members:
   :protected-members:
   :undoc-members:

AccCluster
----------

Container for accelerator components (compute units, memory, DMA).

.. doxygenclass:: AccCluster
   :members:
   :undoc-members:

ComputeUnit
-----------

Base class for compute units within an accelerator.

.. doxygenclass:: ComputeUnit
   :members:
   :undoc-members:

FUSchedulingPool
----------------

Non-pipelined functional unit capacity scheduler and diagnostic trace engine.

.. doxygenclass:: FUSchedulingPool
   :members:
   :undoc-members:

WorkbenchStatistics
-------------------

Observation-only runtime statistics collector for memory and compute activity.

.. doxygenclass:: gem5::salam::WorkbenchStatistics
   :members:
   :undoc-members:

LLVM IR Representation
======================

These classes represent the parsed LLVM IR structure and dynamic CDFG nodes.

Instruction
-----------

Base class for all executable LLVM instructions in the SALAM CDFG.

.. doxygenclass:: SALAM::Instruction
   :members:
   :protected-members:
   :undoc-members:

BasicBlock
----------

Represents a basic block containing instructions and control-flow predecessors.

.. doxygenclass:: SALAM::BasicBlock
   :members:
   :undoc-members:

Function
--------

Represents a function containing basic blocks and formal arguments.

.. doxygenclass:: SALAM::Function
   :members:
   :undoc-members:

Value
-----

Base class for all CDFG values (instructions, arguments, constants, blocks).

.. doxygenclass:: SALAM::Value
   :members:
   :undoc-members:

Operand
-------

Represents instruction operands and register-locking snapshots.

.. doxygenclass:: SALAM::Operand
   :members:
   :undoc-members:

Register
--------

Data storage container for ``SALAM::Value`` instances with read/write tracking.

.. doxygenclass:: SALAM::Register
   :members:
   :undoc-members:

MemoryRequest
-------------

Descriptor managing multi-word read and write transactions across ports.

.. doxygenclass:: MemoryRequest
   :members:
   :undoc-members:

Hardware Modeling
=================

HWInterface
-----------

Interface aggregating hardware timing, functional units, and power models.

.. doxygenclass:: HWInterface
   :members:
   :undoc-members:

FunctionalUnits
---------------

Models functional unit availability and allocation.

.. doxygenclass:: FunctionalUnits
   :members:
   :undoc-members:

CycleCounts
-----------

Tracks cycle counts for instructions and operations.

.. doxygenclass:: CycleCounts
   :members:
   :undoc-members:

HWStatistics
------------

Collects and reports hardware statistics.

.. doxygenclass:: HWStatistics
   :members:
   :undoc-members:

Memory Components
=================

ScratchpadMemory
----------------

Multi-port, bank-interleaved on-chip scratchpad memory for accelerator data.

.. doxygenclass:: ScratchpadMemory
   :members:
   :undoc-members:

RegisterBank
------------

Delta-cycled hardware register file for accelerator state.

.. doxygenclass:: RegisterBank
   :members:
   :undoc-members:

DMA Controllers
===============

NoncoherentDma
--------------

Non-coherent DMA controller for bulk data transfers.

.. doxygenclass:: NoncoherentDma
   :members:
   :undoc-members:

StreamDma
---------

Streaming DMA controller supporting MM2S and S2MM transfers.

.. doxygenclass:: StreamDma
   :members:
   :undoc-members:

StreamBuffer
------------

Clocked FIFO buffer for streaming data operations.

.. doxygenclass:: StreamBuffer
   :members:
   :undoc-members:

I/O & Verification Components
=============================

IOAcc
-----

I/O accelerator interface.

.. doxygenclass:: IOAcc
   :members:
   :undoc-members:

SalamLifecycleTester
--------------------

Protocol and lifecycle verification harness exercising port backpressure,
``Drainable`` transitions, and per-instance CDFG teardown.

.. doxygenclass:: SalamLifecycleTester
   :members:
   :undoc-members:

SalamRegisterBankTester
-----------------------

Protocol verification SimObject exercising ``RegisterBank`` delta writes,
response retry ordering, and drain completion.

.. doxygenclass:: SalamRegisterBankTester
   :members:
   :undoc-members:

File Index
==========

For a complete list of all documented files:

.. toctree::
   :maxdepth: 1

   files

.. note::

   If classes appear empty, ensure Doxygen XML has been generated via
   ``doxygen docs/Doxyfile.salam`` before running Sphinx.
