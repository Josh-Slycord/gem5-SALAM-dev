import re

# Read the file
with open(
    "/home/jslycord/gem5-SALAM-dev/scripts/salam_gui/main_window.py", "r"
) as f:
    content = f.read()

# Add import for LiveStatsWidget
old_import = """from .widgets.comparison import ComparisonWidget
from .widgets.simulation_panel import SimulationPanel"""

new_import = """from .widgets.comparison import ComparisonWidget
from .widgets.simulation_panel import SimulationPanel
from .widgets.live_stats_widget import LiveStatsWidget"""

content = content.replace(old_import, new_import, 1)

# Add LiveStatsWidget creation after stats_dashboard
old_stats_section = """        # Stats Dashboard (right side)
        self.stats_dashboard = StatsDashboard()
        stats_dock = QDockWidget("Performance Summary", self)
        stats_dock.setWidget(self.stats_dashboard)
        stats_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, stats_dock)"""

new_stats_section = """        # Stats Dashboard (right side)
        self.stats_dashboard = StatsDashboard()
        stats_dock = QDockWidget("Performance Summary", self)
        stats_dock.setWidget(self.stats_dashboard)
        stats_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, stats_dock)

        # Live Stats Dashboard (right side, tabbed with stats)
        self.live_stats_widget = LiveStatsWidget()
        live_stats_dock = QDockWidget("Live Statistics", self)
        live_stats_dock.setWidget(self.live_stats_widget)
        live_stats_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, live_stats_dock)
        # Tab the live stats with the performance summary
        self.tabifyDockWidget(stats_dock, live_stats_dock)"""

content = content.replace(old_stats_section, new_stats_section, 1)

# Connect live stats widget to the simulation connection
# Find the connect method and add the connection
old_connect = """        self.connection.connected.connect(self._on_connected)
        self.connection.disconnected.connect(self._on_disconnected)"""

new_connect = """        self.connection.connected.connect(self._on_connected)
        self.connection.disconnected.connect(self._on_disconnected)
        # Connect live stats widget
        self.live_stats_widget.connect_to_simulation(self.connection)"""

content = content.replace(old_connect, new_connect, 1)

# Write the file back
with open(
    "/home/jslycord/gem5-SALAM-dev/scripts/salam_gui/main_window.py", "w"
) as f:
    f.write(content)

print("main_window.py updated successfully")
