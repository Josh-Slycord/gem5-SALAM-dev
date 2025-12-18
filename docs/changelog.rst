.. _changelog:

=========
Changelog
=========

All notable changes to gem5-SALAM are documented in this file.

The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_,
and this project adheres to `Semantic Versioning <https://semver.org/spec/v2.0.0.html>`_.

[Unreleased]
============

Added
-----

- Comprehensive documentation infrastructure (Sphinx + Breathe)
- New debug flag system with hierarchical naming (SALAM* prefix)
- Compound debug flags for common debugging scenarios
- GDB initialization file with SALAM-specific commands
- Valgrind suppression file for known false positives
- Debug launcher scripts (run_debug.sh, run_valgrind.sh)
- Documentation generation script (generate_docs.sh)
- SALAM GUI for simulation configuration

Changed
-------

- Migrated DPRINTF calls to new SALAM* flag naming convention
- Updated debug flag organization with clear categories

Deprecated
----------

- Old debug flag names (Runtime, RuntimeCompute, etc.) - use SALAM* equivalents

Removed
-------

- Unused debug flags (Trace, Step)
- JDEV compound flag (replaced by SALAMVerbose)

Fixed
-----

- IOAcc debug flag now properly defined
- Results output re-enabled in hw_statistics.cc

[1.0.0] - Initial Release
=========================

Features
--------

- LLVM IR-based accelerator simulation
- Full system simulation with ARM cores
- Configurable functional units and cycle counts
- Scratchpad memory and register bank support
- DMA controllers (coherent and streaming)
- Power modeling integration (CACTI, McPAT)
- Python-based configuration system

Known Issues
------------

- Some benchmarks require specific memory sizes
- Debug output can be verbose with SALAMAll flag
