.. _python-api:

====================
Python API Reference
====================

This section documents the Python components of gem5-SALAM, including
SimObject definitions, configuration modules, and the SALAM GUI.

.. contents:: Contents
   :local:
   :depth: 2

SimObject Classes
=================

These Python classes define the gem5 SimObjects for SALAM components.
They are used in configuration scripts to instantiate accelerator hardware.

Core SimObjects
---------------

LLVMInterface
~~~~~~~~~~~~~

.. automodule:: LLVMInterface
   :members:
   :show-inheritance:
   :undoc-members:

CommInterface
~~~~~~~~~~~~~

.. automodule:: CommInterface
   :members:
   :show-inheritance:
   :undoc-members:

AccCluster
~~~~~~~~~~

.. automodule:: AccCluster
   :members:
   :show-inheritance:
   :undoc-members:

ComputeUnit
~~~~~~~~~~~

.. automodule:: ComputeUnit
   :members:
   :show-inheritance:
   :undoc-members:

Memory SimObjects
-----------------

ScratchpadMemory
~~~~~~~~~~~~~~~~

.. automodule:: ScratchpadMemory
   :members:
   :show-inheritance:
   :undoc-members:

RegisterBank
~~~~~~~~~~~~

.. automodule:: RegisterBank
   :members:
   :show-inheritance:
   :undoc-members:

DMA SimObjects
--------------

NoncoherentDma
~~~~~~~~~~~~~~

.. automodule:: NoncoherentDma
   :members:
   :show-inheritance:
   :undoc-members:

StreamDma
~~~~~~~~~

.. automodule:: StreamDma
   :members:
   :show-inheritance:
   :undoc-members:

StreamBuffer
~~~~~~~~~~~~

.. automodule:: StreamBuffer
   :members:
   :show-inheritance:
   :undoc-members:

Hardware Modeling SimObjects
----------------------------

HWInterface
~~~~~~~~~~~

.. automodule:: HWInterface
   :members:
   :show-inheritance:
   :undoc-members:

FunctionalUnits
~~~~~~~~~~~~~~~

.. automodule:: FunctionalUnits
   :members:
   :show-inheritance:
   :undoc-members:

CycleCounts
~~~~~~~~~~~

.. automodule:: CycleCounts
   :members:
   :show-inheritance:
   :undoc-members:

HWStatistics
~~~~~~~~~~~~

.. automodule:: HWStatistics
   :members:
   :show-inheritance:
   :undoc-members:

Configuration Modules
=====================

These modules provide configuration helpers for setting up SALAM simulations.

HWAcc Configuration
-------------------

.. automodule:: HWAcc
   :members:
   :undoc-members:

SALAM GUI
=========

The SALAM GUI provides a graphical interface for configuring and running
accelerator simulations.

Main Application
----------------

.. automodule:: salam_gui.app
   :members:
   :undoc-members:

Widgets
-------

Simulation Panel
~~~~~~~~~~~~~~~~

.. automodule:: salam_gui.widgets.simulation_panel
   :members:
   :undoc-members:

Hardware Configuration
~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: salam_gui.widgets.hardware_config
   :members:
   :undoc-members:

Benchmark Selection
~~~~~~~~~~~~~~~~~~~

.. automodule:: salam_gui.widgets.benchmark_panel
   :members:
   :undoc-members:

.. note::

   If modules appear empty, they may not have docstrings yet. See the
   :ref:`contributing` guide for documentation standards.

Usage Examples
==============

Creating an Accelerator Cluster
-------------------------------

.. code-block:: python

   from m5.objects import *

   # Create the accelerator cluster
   cluster = AccCluster()
   cluster.local_bus = NoncoherentXBar()

   # Create communication interface
   cluster.comm = CommInterface()
   cluster.comm.pio_addr = 0x2f100000
   cluster.comm.pio_size = 64

   # Create LLVM interface (compute engine)
   cluster.llvm = LLVMInterface()
   cluster.llvm.ir_file = "benchmark.ll"

   # Create scratchpad memory
   cluster.spm = ScratchpadMemory()
   cluster.spm.size = "64kB"

   # Create DMA controller
   cluster.dma = NoncoherentDma()

Configuring Hardware Parameters
-------------------------------

.. code-block:: python

   # Configure functional units
   hw = HWInterface()
   hw.fu = FunctionalUnits()
   hw.fu.num_adders = 4
   hw.fu.num_multipliers = 2

   # Configure cycle counts
   hw.cycles = CycleCounts()
   hw.cycles.add_latency = 1
   hw.cycles.mul_latency = 3
   hw.cycles.load_latency = 2
