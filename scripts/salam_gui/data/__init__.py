# ==============================================================================
# data/__init__.py - Data Parsing and Loading Module
# ==============================================================================
"""Data Parsing and Loading Modules for gem5-SALAM GUI.

This subpackage provides utilities for parsing simulation outputs,
loading configurations, and establishing real-time connections to
running simulations.

Module Structure::

    salam_gui/data/
    +-- __init__.py          # This file (exports)
    +-- dot_parser.py        # CDFG DOT file parser
    +-- stats_parser.py      # Statistics output parser
    +-- config_loader.py     # YAML configuration loader
    +-- realtime_connection.py  # Live ZeroMQ connection

Primary Exports:
    - parse_cdfg_dot(): Parse CDFG .dot files
    - parse_stats_output(): Parse statistics files
    - load_config(): Load YAML configuration
    - SimulationConnection: Real-time data connection

Example:
    Typical usage in the GUI::

        from salam_gui.data import (
            parse_cdfg_dot,
            parse_stats_output,
            load_config,
            SimulationConnection
        )

        # Load static data
        graph = parse_cdfg_dot(Path("m5out/cdfg.dot"))
        stats = parse_stats_output(Path("m5out/stats.txt"))
        config = load_config(Path("config.yml"))

        # Connect to live simulation
        conn = SimulationConnection()
        conn.connect("tcp://localhost:5555")
"""


__version__ = "3.0.0.pre[1.0.0]"

from .dot_parser import parse_cdfg_dot, CDFGGraph
from .stats_parser import parse_stats_output, SimulationStats
from .config_loader import load_config
from .realtime_connection import (
    SimulationConnection,
    SimulationReceiver,
    SimulationMessage,
    MessageType,
    ConnectionState,
    LiveDataBuffer
)

__all__ = [
    'parse_cdfg_dot', 'CDFGGraph',
    'parse_stats_output', 'SimulationStats',
    'load_config',
    # Real-time connection
    'SimulationConnection',
    'SimulationReceiver',
    'SimulationMessage',
    'MessageType',
    'ConnectionState',
    'LiveDataBuffer',
]
