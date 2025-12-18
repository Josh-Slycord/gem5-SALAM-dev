"""
Widget components for gem5-SALAM GUI.
"""


__version__ = "3.0.0.pre[1.0.0]"

# Phase 1 widgets
from .cdfg_viewer import CDFGViewer
from .stats_dashboard import StatsDashboard
from .file_browser import FileBrowser

# Phase 2 widgets
from .queue_monitor import QueueMonitor, QueueHistory
from .fu_utilization import FUUtilizationWidget, FUHistory
from .power_area import PowerAreaWidget, PowerAreaData
from .execution_timeline import ExecutionTimeline, ExecutionTrace
from .comparison import ComparisonWidget, ComparisonResult

# Simulation integration
from .simulation_panel import SimulationPanel

# Help system
from .help_browser import HelpBrowser, HelpIndexer

__all__ = [
    # Phase 1
    'CDFGViewer',
    'StatsDashboard',
    'FileBrowser',
    # Phase 2
    'QueueMonitor',
    'QueueHistory',
    'FUUtilizationWidget',
    'FUHistory',
    'PowerAreaWidget',
    'PowerAreaData',
    'ExecutionTimeline',
    'ExecutionTrace',
    'ComparisonWidget',
    'ComparisonResult',
    # Simulation
    'SimulationPanel',
    # Help
    'HelpBrowser',
    'HelpIndexer',
]
