# ==============================================================================
# main_window.py - Main Application Window
# ==============================================================================
"""Main Application Window for gem5-SALAM GUI.

This module provides the MainWindow class, which is the central window of the
gem5-SALAM visualization application. It uses a dockable widget architecture
to provide flexible layout for various visualization and analysis tools.

Window Layout::

    +-------------------------------------------------------------------+
    |  Menu Bar: File | View | Tools | Help                              |
    +-------------------------------------------------------------------+
    |  Toolbar: Open | CDFG | Stats | Zoom +/- | Fit | Connect          |
    +-------------------+---------------------------+-------------------+
    |                   |                           |                   |
    |  [Files]          |                           |  Performance      |
    |  [Run Simulation] |      CDFG Viewer          |  Summary          |
    |                   |   (Central Widget)        |  (Dock)           |
    |  (Tabbed Docks)   |                           |                   |
    |                   |                           |                   |
    +-------------------+---------------------------+-------------------+
    |  [Queue Monitor] [FU Util] [Power] [Timeline] [Compare]           |
    |  (Bottom Dock - Tabbed)                                           |
    +-------------------------------------------------------------------+
    |  Status Bar: Ready | Connection Status | Cycle: -                  |
    +-------------------------------------------------------------------+

Dock Widgets:
    | Widget             | Location | Purpose                         |
    |--------------------|----------|----------------------------------|
    | FileBrowser        | Left     | Browse simulation output files  |
    | SimulationPanel    | Left     | Run simulations (tabbed)        |
    | StatsDashboard     | Right    | Performance metrics summary     |
    | QueueMonitor       | Bottom   | Instruction queue depths        |
    | FUUtilizationWidget| Bottom   | FU utilization heatmap          |
    | PowerAreaWidget    | Bottom   | Power/area treemap              |
    | ExecutionTimeline  | Bottom   | Gantt-style execution view      |
    | ComparisonWidget   | Bottom   | Compare multiple runs           |

Live Connection:
    The window supports real-time connection to running simulations via
    ZeroMQ, enabling live updates of queue states, FU utilization, and
    execution progress.

Example:
    Creating and showing the main window::

        from salam_gui.main_window import MainWindow
        window = MainWindow()
        window.load_simulation_output(Path('/path/to/m5out'))
        window.show()

See Also:
    - SALAMGuiApp: Application class that hosts this window
    - CDFGViewer: Central CDFG visualization widget
    - SimulationPanel: Run simulations from within the GUI
"""


__version__ = "3.0.0.pre[1.0.0]"

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QDockWidget, QToolBar, QStatusBar,
    QFileDialog, QMessageBox, QWidget, QVBoxLayout, QLabel
)
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Qt

from .widgets.cdfg_viewer import CDFGViewer
from .widgets.stats_dashboard import StatsDashboard
from .widgets.file_browser import FileBrowser
from .widgets.queue_monitor import QueueMonitor
from .widgets.fu_utilization import FUUtilizationWidget
from .widgets.power_area import PowerAreaWidget
from .widgets.execution_timeline import ExecutionTimeline
from .widgets.comparison import ComparisonWidget
from .widgets.simulation_panel import SimulationPanel
from .widgets.help_browser import HelpBrowser
from .data.dot_parser import parse_cdfg_dot
from .data.stats_parser import parse_stats_output
from .data.realtime_connection import SimulationConnection, LiveDataBuffer
from .dialogs.connection_dialog import ConnectionDialog, ConnectionStatusWidget


class MainWindow(QMainWindow):
    """Main application window with dockable visualization widgets."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("gem5-SALAM GUI")
        self.setMinimumSize(1200, 800)

        # Track loaded data
        self.cdfg_data = None
        self.stats_data = None
        self.current_dir: Optional[Path] = None

        # Real-time connection
        self.connection: Optional[SimulationConnection] = None
        self.live_data_buffer = LiveDataBuffer()

        self._setup_ui()
        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._create_statusbar()
        self._create_dock_widgets()

    def _setup_ui(self):
        """Set up the central widget."""
        # Central widget will be the CDFG viewer
        self.cdfg_viewer = CDFGViewer()
        self.setCentralWidget(self.cdfg_viewer)

    def _create_actions(self):
        """Create menu and toolbar actions."""
        # File actions
        self.open_dir_action = QAction("Open Directory...", self)
        self.open_dir_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_dir_action.triggered.connect(self.open_directory)

        self.open_cdfg_action = QAction("Open CDFG...", self)
        self.open_cdfg_action.setShortcut("Ctrl+G")
        self.open_cdfg_action.triggered.connect(self.open_cdfg_dialog)

        self.open_stats_action = QAction("Open Stats...", self)
        self.open_stats_action.setShortcut("Ctrl+T")
        self.open_stats_action.triggered.connect(self.open_stats_dialog)

        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.exit_action.triggered.connect(self.close)

        # View actions
        self.zoom_in_action = QAction("Zoom In", self)
        self.zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.zoom_in_action.triggered.connect(self.cdfg_viewer.zoom_in)

        self.zoom_out_action = QAction("Zoom Out", self)
        self.zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.zoom_out_action.triggered.connect(self.cdfg_viewer.zoom_out)

        self.fit_view_action = QAction("Fit to View", self)
        self.fit_view_action.setShortcut("Ctrl+0")
        self.fit_view_action.triggered.connect(self.cdfg_viewer.fit_to_view)

        # Tools actions
        self.connect_live_action = QAction("Connect Live...", self)
        self.connect_live_action.setShortcut("Ctrl+L")
        self.connect_live_action.triggered.connect(self.connect_live_dialog)

    def _create_menus(self):
        """Create menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self.open_dir_action)
        file_menu.addAction(self.open_cdfg_action)
        file_menu.addAction(self.open_stats_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.fit_view_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        tools_menu.addAction(self.connect_live_action)

        # Help menu
        help_contents_action = QAction("Help Contents...", self)
        help_contents_action.setShortcut("F1")
        help_contents_action.triggered.connect(self.show_help)

        help_menu = menubar.addMenu("&Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(help_contents_action)
        help_menu.addSeparator()
        help_menu.addAction(about_action)

    def _create_toolbar(self):
        """Create main toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addAction(self.open_dir_action)
        toolbar.addAction(self.open_cdfg_action)
        toolbar.addAction(self.open_stats_action)
        toolbar.addSeparator()
        toolbar.addAction(self.zoom_in_action)
        toolbar.addAction(self.zoom_out_action)
        toolbar.addAction(self.fit_view_action)
        toolbar.addSeparator()
        toolbar.addAction(self.connect_live_action)

    def _create_statusbar(self):
        """Create status bar."""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Ready")

        # Add connection status widget
        self.connection_status = ConnectionStatusWidget()
        self.connection_status.clicked.connect(self.connect_live_dialog)
        self.statusbar.addPermanentWidget(self.connection_status)

        # Cycle counter for live mode
        self.cycle_label = QLabel("Cycle: -")
        self.cycle_label.setStyleSheet("padding: 0 10px;")
        self.cycle_label.hide()
        self.statusbar.addPermanentWidget(self.cycle_label)

    def _create_dock_widgets(self):
        """Create dockable widget panels."""
        # File Browser (left side)
        self.file_browser = FileBrowser()
        self.file_browser.file_selected.connect(self._on_file_selected)
        browser_dock = QDockWidget("Files", self)
        browser_dock.setWidget(self.file_browser)
        browser_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea |
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, browser_dock)

        # Simulation Panel (left side, tabbed with files)
        self.simulation_panel = SimulationPanel()
        sim_dock = QDockWidget("Run Simulation", self)
        sim_dock.setWidget(self.simulation_panel)
        sim_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea |
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, sim_dock)
        self.tabifyDockWidget(browser_dock, sim_dock)

        # Raise files tab by default on left side
        browser_dock.raise_()

        # Stats Dashboard (right side)
        self.stats_dashboard = StatsDashboard()
        stats_dock = QDockWidget("Performance Summary", self)
        stats_dock.setWidget(self.stats_dashboard)
        stats_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea |
            Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, stats_dock)

        # Queue Monitor (bottom)
        self.queue_monitor = QueueMonitor()
        queue_dock = QDockWidget("Queue Monitor", self)
        queue_dock.setWidget(self.queue_monitor)
        queue_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea |
            Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, queue_dock)

        # FU Utilization (bottom, tabbed with queue)
        self.fu_utilization = FUUtilizationWidget()
        fu_dock = QDockWidget("FU Utilization", self)
        fu_dock.setWidget(self.fu_utilization)
        fu_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea |
            Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, fu_dock)
        self.tabifyDockWidget(queue_dock, fu_dock)

        # Power & Area (bottom, tabbed)
        self.power_area = PowerAreaWidget()
        power_dock = QDockWidget("Power & Area", self)
        power_dock.setWidget(self.power_area)
        power_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea |
            Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, power_dock)
        self.tabifyDockWidget(fu_dock, power_dock)

        # Execution Timeline (bottom, tabbed)
        self.timeline = ExecutionTimeline()
        timeline_dock = QDockWidget("Execution Timeline", self)
        timeline_dock.setWidget(self.timeline)
        timeline_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea |
            Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, timeline_dock)
        self.tabifyDockWidget(power_dock, timeline_dock)

        # Comparison widget (bottom, tabbed)
        self.comparison = ComparisonWidget()
        comparison_dock = QDockWidget("Compare Runs", self)
        comparison_dock.setWidget(self.comparison)
        comparison_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea |
            Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, comparison_dock)
        self.tabifyDockWidget(timeline_dock, comparison_dock)

        # Raise the queue monitor tab by default
        queue_dock.raise_()

    # --- File Operations ---

    def open_directory(self):
        """Open a simulation output directory."""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Open Simulation Directory",
            str(self.current_dir or Path.home())
        )
        if dir_path:
            self.load_simulation_output(Path(dir_path))

    def open_cdfg_dialog(self):
        """Open a CDFG dot file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open CDFG File",
            str(self.current_dir or Path.home()),
            "DOT files (*.dot);;All files (*)"
        )
        if file_path:
            self.load_cdfg(Path(file_path))

    def open_stats_dialog(self):
        """Open a statistics file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Statistics File",
            str(self.current_dir or Path.home()),
            "All files (*);;JSON files (*.json);;Text files (*.txt)"
        )
        if file_path:
            self.load_stats(Path(file_path))

    def load_simulation_output(self, dir_path: Path):
        """Load a simulation output directory."""
        if not dir_path.exists():
            QMessageBox.warning(self, "Error", f"Directory not found: {dir_path}")
            return

        self.current_dir = dir_path
        self.file_browser.set_directory(dir_path)
        self.statusbar.showMessage(f"Loaded: {dir_path}")

        # Auto-detect and load files
        cdfg_file = dir_path / "cdfg.dot"
        if cdfg_file.exists():
            self.load_cdfg(cdfg_file)

        # Look for stats in various locations
        stats_file = dir_path / "stats.txt"
        if stats_file.exists():
            self.load_stats(stats_file)

    def load_cdfg(self, file_path: Path):
        """Load and display a CDFG dot file."""
        try:
            self.cdfg_data = parse_cdfg_dot(file_path)
            self.cdfg_viewer.set_graph(self.cdfg_data)
            self.statusbar.showMessage(
                f"CDFG loaded: {len(self.cdfg_data.nodes)} nodes, "
                f"{len(self.cdfg_data.edges)} edges"
            )
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load CDFG: {e}")

    def load_stats(self, file_path: Path):
        """Load and display statistics."""
        try:
            self.stats_data = parse_stats_output(file_path)
            self.stats_dashboard.set_stats(self.stats_data)
            self.statusbar.showMessage(f"Stats loaded: {file_path.name}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load stats: {e}")

    def _on_file_selected(self, file_path: Path):
        """Handle file selection from browser."""
        if file_path.suffix == '.dot':
            self.load_cdfg(file_path)
        elif file_path.suffix in ('.txt', '.json', '.csv'):
            self.load_stats(file_path)

    # --- Live Connection ---

    def connect_live_dialog(self):
        """Show dialog to connect to live simulation."""
        dialog = ConnectionDialog(self)
        dialog.connection_established.connect(self._on_connection_established)
        dialog.exec()

    def _on_connection_established(self, connection: SimulationConnection):
        """Handle successful connection to simulation."""
        self.connection = connection

        # Connect signals for live updates
        self.connection.connected.connect(self._on_connected)
        self.connection.disconnected.connect(self._on_disconnected)
        self.connection.connection_error.connect(self._on_connection_error)
        self.connection.cycle_updated.connect(self._on_cycle_updated)
        self.connection.queue_state_updated.connect(self._on_queue_state_updated)
        self.connection.fu_state_updated.connect(self._on_fu_state_updated)
        self.connection.stats_updated.connect(self._on_stats_updated)

        # Update UI
        self.connection_status.set_connected()
        self.cycle_label.show()
        self.statusbar.showMessage("Connected to live simulation")

    def _on_connected(self):
        """Handle connection event."""
        self.connection_status.set_connected()
        self.cycle_label.show()
        self.live_data_buffer.clear()

    def _on_disconnected(self):
        """Handle disconnection event."""
        self.connection_status.set_disconnected()
        self.cycle_label.hide()
        self.statusbar.showMessage("Disconnected from simulation")
        self.connection = None

    def _on_connection_error(self, error_msg: str):
        """Handle connection error."""
        self.connection_status.set_disconnected()
        self.statusbar.showMessage(f"Connection error: {error_msg}")

    def _on_cycle_updated(self, cycle: int):
        """Handle cycle update from live simulation."""
        self.cycle_label.setText(f"Cycle: {cycle:,}")

    def _on_queue_state_updated(self, state: dict):
        """Handle queue state update from live simulation."""
        if self.connection:
            self.live_data_buffer.add_queue_state(
                self.connection.current_cycle, state
            )
        # TODO: Update queue monitor widget with live data

    def _on_fu_state_updated(self, state: dict):
        """Handle FU state update from live simulation."""
        if self.connection:
            self.live_data_buffer.add_fu_state(
                self.connection.current_cycle, state
            )
        # TODO: Update FU utilization widget with live data

    def _on_stats_updated(self, stats: dict):
        """Handle stats update from live simulation."""
        # TODO: Update stats dashboard with live data
        pass

    def disconnect_live(self):
        """Disconnect from live simulation."""
        if self.connection:
            self.connection.disconnect()
            self.connection = None

        # --- Help ---

    def show_help(self):
        """Show integrated help browser."""
        # Determine project root (parent of scripts directory)
        project_root = Path(__file__).parent.parent.parent
        self.help_browser = HelpBrowser(project_root, self)
        self.help_browser.show()

    def show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About gem5-SALAM GUI",
            """<h2>gem5-SALAM GUI</h2>
            <p>Version 1.0.0</p>
            <p>Unified visualization and simulation tool for gem5-SALAM.</p>
            <p><b>Visualization:</b></p>
            <ul>
                <li>CDFG visualization with pan/zoom</li>
                <li>Performance metrics dashboard</li>
                <li>File browser for simulation outputs</li>
            </ul>
            <p><b>Advanced Analytics:</b></p>
            <ul>
                <li>Queue monitoring with depth charts</li>
                <li>FU utilization heatmaps</li>
                <li>Power & Area treemap analysis</li>
                <li>Execution timeline (Gantt view)</li>
                <li>Run comparison mode</li>
            </ul>
            <p><b>Simulation Runner:</b></p>
            <ul>
                <li>WSL integration for Windows</li>
                <li>Benchmark selection and configuration</li>
                <li>Real-time output streaming</li>
                <li>ZeroMQ live connection</li>
            </ul>
            """
        )
