.. gem5-SALAM documentation master file

====================================
gem5-SALAM Documentation
====================================

**gem5-SALAM** (System-Level Accelerator Modeling) is a framework for
modeling and simulating custom hardware accelerators within the gem5
full-system simulator. It enables cycle-accurate simulation of accelerators
described in LLVM IR alongside a complete ARM-based system.

.. note::

   This documentation covers the SALAM-specific components. For general
   gem5 documentation, see the `gem5 documentation <https://www.gem5.org/documentation/>`_.

Getting Started
---------------

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   guides/getting_started
   guides/accelerator_design
   guides/debugging

Key Features
------------

- **LLVM IR-Based Design**: Define accelerators using LLVM IR for hardware/software co-design
- **Cycle-Accurate Simulation**: Model functional units, memory interfaces, and DMA controllers
- **Full System Integration**: Run complete Linux workloads with accelerator offloading
- **Configurable Hardware**: Parameterizable functional units, memory hierarchies, and interfaces
- **Power Modeling**: Integration with CACTI and McPAT for power/area estimation
- **Rich Debugging**: Comprehensive debug flags and Valgrind/GDB integration

Architecture Overview
---------------------

.. code-block:: text

   +------------------+     +-------------------+
   |   ARM Cores      |     |   SALAM Cluster   |
   |  (gem5 CPUs)     |     |                   |
   +--------+---------+     |  +-----------+    |
            |               |  | CommIface |    |
            v               |  +-----+-----+    |
   +--------+---------+     |        |          |
   |  System Bus      +-----+        v          |
   |  (Coherent)      |     |  +-----------+    |
   +--------+---------+     |  | LLVMIface |    |
            |               |  | (Compute) |    |
            v               |  +-----+-----+    |
   +--------+---------+     |        |          |
   |  Memory Ctrl     |     |  +-----------+    |
   |  (DDR/DRAM)      |     |  |    DMA    |    |
   +------------------+     |  +-----------+    |
                            +-------------------+

API Reference
-------------

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/cpp/index
   api/python/index

Development
-----------

.. toctree::
   :maxdepth: 1
   :caption: Development

   guides/contributing
   changelog

Quick Links
-----------

- **GitHub Repository**: `TeCSAR-UNCC/gem5-SALAM <https://github.com/TeCSAR-UNCC/gem5-SALAM>`_
- **Issue Tracker**: `GitHub Issues <https://github.com/TeCSAR-UNCC/gem5-SALAM/issues>`_
- **gem5 Website**: `gem5.org <https://www.gem5.org/>`_

Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
