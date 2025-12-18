# ==============================================================================
# gem5-SALAM GUI Package
# ==============================================================================
"""gem5-SALAM GUI - Interactive Visualization Tool for Hardware Accelerators.

This package provides a PySide6-based graphical interface for visualizing
and analyzing gem5-SALAM simulation outputs, as well as running simulations
directly from the GUI.

Package Structure::

    salam_gui/
    +-- __init__.py          # This file
    +-- __main__.py          # Entry point (python -m salam_gui)
    +-- app.py               # QApplication subclass with theming
    +-- main_window.py       # Main window with dockable widgets
    +-- data/                # Data parsing modules
    |   +-- dot_parser.py    # CDFG DOT file parser
    |   +-- stats_parser.py  # Statistics output parser
    |   +-- config_loader.py # Configuration file loader
    |   +-- realtime_connection.py  # ZeroMQ live connection
    +-- widgets/             # UI widget modules
    |   +-- cdfg_viewer.py   # CDFG visualization (central)
    |   +-- stats_dashboard.py    # Performance summary
    |   +-- file_browser.py  # File/directory browser
    |   +-- queue_monitor.py # Instruction queue depth charts
    |   +-- fu_utilization.py    # FU utilization heatmap
    |   +-- power_area.py    # Power/area treemap
    |   +-- execution_timeline.py # Gantt-style timeline
    |   +-- comparison.py    # Run comparison
    |   +-- simulation_panel.py   # WSL simulation runner
    +-- dialogs/             # Dialog windows
        +-- connection_dialog.py  # Live connection dialog

Features:
    - **CDFG Visualization**: Interactive pan/zoom graph of accelerator dataflow
    - **Performance Dashboard**: Key metrics at a glance
    - **Queue Monitoring**: Real-time instruction queue depth tracking
    - **FU Utilization**: Heatmap of functional unit usage over time
    - **Power & Area Analysis**: Treemap visualization of power/area breakdown
    - **Execution Timeline**: Gantt-style view of instruction execution
    - **Run Comparison**: Side-by-side comparison of multiple runs
    - **Simulation Runner**: Launch simulations with WSL integration
    - **Live Connection**: Real-time updates via ZeroMQ

Usage:
    From command line::

        python -m salam_gui                     # Launch GUI
        python -m salam_gui --load m5out/       # Load simulation output
        python -m salam_gui --dark              # Use dark theme

    From Python::

        from salam_gui.app import SALAMGuiApp
        from salam_gui.main_window import MainWindow

        app = SALAMGuiApp(sys.argv)
        window = MainWindow()
        window.show()
        sys.exit(app.exec())

Requirements:
    - PySide6 >= 6.0
    - NetworkX (for CDFG layout)
    - PyZMQ (for live connection, optional)

See Also:
    - gem5-SALAM documentation at docs/
    - configs/SALAM/ for simulation configuration examples
"""

__version__ = "3.0.0.pre[1.0.0]"
__author__ = "gem5-SALAM Team"
