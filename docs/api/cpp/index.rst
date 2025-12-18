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

The central execution engine that processes LLVM IR instructions.

.. doxygenclass:: gem5::LLVMInterface
   :members:
   :protected-members:
   :undoc-members:

CommInterface
-------------

Communication interface between the accelerator and the system bus.

.. doxygenclass:: gem5::CommInterface
   :members:
   :protected-members:
   :undoc-members:

AccCluster
----------

Container for accelerator components (compute units, memory, DMA).

.. doxygenclass:: gem5::AccCluster
   :members:
   :undoc-members:

ComputeUnit
-----------

Base class for compute units within an accelerator.

.. doxygenclass:: gem5::ComputeUnit
   :members:
   :undoc-members:

LLVM IR Representation
======================

These classes represent the parsed LLVM IR structure.

Instruction
-----------

Base class for all LLVM instructions.

.. doxygenclass:: SALAM::Instruction
   :members:
   :protected-members:
   :undoc-members:

BasicBlock
----------

Represents a basic block containing instructions.

.. doxygenclass:: SALAM::BasicBlock
   :members:
   :undoc-members:

Function
--------

Represents a function containing basic blocks.

.. doxygenclass:: SALAM::Function
   :members:
   :undoc-members:

Value
-----

Base class for all values (instructions, arguments, constants).

.. doxygenclass:: SALAM::Value
   :members:
   :undoc-members:

Operand
-------

Represents instruction operands.

.. doxygenclass:: SALAM::Operand
   :members:
   :undoc-members:

Hardware Modeling
=================

HWInterface
-----------

Interface for querying hardware characteristics.

.. doxygenclass:: gem5::HWInterface
   :members:
   :undoc-members:

FunctionalUnits
---------------

Models functional unit availability and allocation.

.. doxygenclass:: gem5::FunctionalUnits
   :members:
   :undoc-members:

CycleCounts
-----------

Tracks cycle counts for instructions and operations.

.. doxygenclass:: gem5::CycleCounts
   :members:
   :undoc-members:

HWStatistics
------------

Collects and reports hardware statistics.

.. doxygenclass:: gem5::HWStatistics
   :members:
   :undoc-members:

Memory Components
=================

ScratchpadMemory
----------------

On-chip scratchpad memory for accelerator data.

.. doxygenclass:: gem5::ScratchpadMemory
   :members:
   :undoc-members:

RegisterBank
------------

Register file for accelerator state.

.. doxygenclass:: gem5::RegisterBank
   :members:
   :undoc-members:

DMA Controllers
===============

NoncoherentDma
--------------

Non-coherent DMA controller for bulk data transfers.

.. doxygenclass:: gem5::NoncoherentDma
   :members:
   :undoc-members:

StreamDma
---------

Streaming DMA controller for continuous data flow.

.. doxygenclass:: gem5::StreamDma
   :members:
   :undoc-members:

StreamBuffer
------------

Buffer for streaming data operations.

.. doxygenclass:: gem5::StreamBuffer
   :members:
   :undoc-members:

I/O Components
==============

IOAcc
-----

I/O accelerator interface.

.. doxygenclass:: gem5::IOAcc
   :members:
   :undoc-members:

File Index
==========

For a complete list of all documented files:

.. toctree::
   :maxdepth: 1

   files

.. note::

   If classes appear empty, the C++ source files may not have Doxygen
   documentation comments yet. See the :ref:`contributing` guide for
   documentation standards.
