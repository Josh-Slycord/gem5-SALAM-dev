# ==============================================================================
# live_stats_widget.py - Live Statistics Dashboard Widget
# ==============================================================================
"""Live Statistics Dashboard Widget for Real-Time Monitoring.

This widget provides real-time visualization of enhanced statistics
received from a running gem5-SALAM simulation via ZeroMQ.

Features:
    - Live updating performance metrics
    - Critical path and ILP visualization
    - Stall cause breakdown with color-coded bars
    - Memory access statistics with cache hit rate
    - Power and area metrics

Connection:
    Subscribes to the SimulationConnection's stats_updated signal
    to receive periodic statistics updates during simulation.

Example:
    # In main window
    from salam_gui.widgets.live_stats_widget import LiveStatsWidget
    from salam_gui.data.realtime_connection import SimulationConnection

    conn = SimulationConnection()
    widget = LiveStatsWidget()
    widget.connect_to_simulation(conn)
    conn.connect("tcp://localhost:5555")
"""

__version__ = "3.0.0"

import json
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QScrollArea, QGroupBox, QProgressBar,
    QSplitter, QTabWidget
)
from PySide6.QtGui import QFont, QColor, QPalette
from PySide6.QtCore import Qt, Signal, Slot

from ..data.enhanced_stats_parser import (
    EnhancedSimulationStats, parse_enhanced_json,
    format_metric, format_percentage, format_cycles
)
from ..data.realtime_connection import SimulationConnection


class MetricCard(QFrame):
    """A card displaying a single metric with label and value."""

    def __init__(self, label: str, value: str = "-", color: Optional[QColor] = None):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setMinimumHeight(70)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Label
        self.label_widget = QLabel(label)
        self.label_widget.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(self.label_widget)

        # Value
        self.value_widget = QLabel(value)
        self.value_widget.setStyleSheet("font-size: 14pt; font-weight: bold;")
        if color:
            self.value_widget.setStyleSheet(
                f"font-size: 14pt; font-weight: bold; color: {color.name()};"
            )
        layout.addWidget(self.value_widget)

    def set_value(self, value: str, color: Optional[QColor] = None):
        """Update the displayed value."""
        self.value_widget.setText(value)
        if color:
            self.value_widget.setStyleSheet(
                f"font-size: 14pt; font-weight: bold; color: {color.name()};"
            )


class StallBar(QFrame):
    """A horizontal bar showing a stall category percentage."""

    def __init__(self, label: str, percentage: float = 0.0):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        # Label
        self.label_widget = QLabel(label)
        self.label_widget.setFixedWidth(120)
        layout.addWidget(self.label_widget)

        # Progress bar
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(True)
        self.bar.setFormat("%.1f%%" % percentage)
        self.bar.setValue(int(percentage))
        layout.addWidget(self.bar)

    def set_percentage(self, percentage: float):
        """Update the percentage."""
        self.bar.setFormat("%.1f%%" % percentage)
        self.bar.setValue(int(min(100, percentage)))

        # Color based on severity
        if percentage > 50:
            self.bar.setStyleSheet("QProgressBar::chunk { background-color: #e74c3c; }")
        elif percentage > 20:
            self.bar.setStyleSheet("QProgressBar::chunk { background-color: #f39c12; }")
        else:
            self.bar.setStyleSheet("QProgressBar::chunk { background-color: #27ae60; }")


class LiveStatsWidget(QWidget):
    """
    Live statistics dashboard widget.

    Displays real-time statistics from a running simulation.
    """

    stats_updated = Signal(object)  # EnhancedSimulationStats

    def __init__(self, parent=None):
        super().__init__(parent)
        self.connection: Optional[SimulationConnection] = None
        self.current_stats: Optional[EnhancedSimulationStats] = None

        self._setup_ui()

    def _setup_ui(self):
        """Set up the widget UI."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("Live Statistics Dashboard")
        header.setStyleSheet("font-size: 12pt; font-weight: bold; padding: 5px;")
        layout.addWidget(header)

        # Status indicator
        self.status_label = QLabel("Status: Disconnected")
        self.status_label.setStyleSheet("color: gray; padding: 2px;")
        layout.addWidget(self.status_label)

        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)

        # Tab widget for organization
        tabs = QTabWidget()

        # Performance tab
        perf_tab = self._create_performance_tab()
        tabs.addTab(perf_tab, "Performance")

        # Dataflow tab
        dataflow_tab = self._create_dataflow_tab()
        tabs.addTab(dataflow_tab, "Dataflow")

        # Memory tab
        memory_tab = self._create_memory_tab()
        tabs.addTab(memory_tab, "Memory")

        # Stalls tab
        stalls_tab = self._create_stalls_tab()
        tabs.addTab(stalls_tab, "Stalls")

        # Power/Area tab
        power_tab = self._create_power_area_tab()
        tabs.addTab(power_tab, "Power/Area")

        content_layout.addWidget(tabs)
        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _create_performance_tab(self) -> QWidget:
        """Create performance metrics tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grid = QGridLayout()

        self.cycles_card = MetricCard("Total Cycles", "-")
        grid.addWidget(self.cycles_card, 0, 0)

        self.stall_pct_card = MetricCard("Stall %", "-")
        grid.addWidget(self.stall_pct_card, 0, 1)

        self.sim_time_card = MetricCard("Sim Time", "-")
        grid.addWidget(self.sim_time_card, 1, 0)

        self.nodes_card = MetricCard("Nodes Executed", "-")
        grid.addWidget(self.nodes_card, 1, 1)

        self.ipc_card = MetricCard("IPC", "-")
        grid.addWidget(self.ipc_card, 2, 0)

        self.active_cycles_card = MetricCard("Active Cycles", "-")
        grid.addWidget(self.active_cycles_card, 2, 1)

        layout.addLayout(grid)
        layout.addStretch()
        return tab

    def _create_dataflow_tab(self) -> QWidget:
        """Create dataflow analysis tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Critical path section
        cp_group = QGroupBox("Critical Path Analysis")
        cp_layout = QGridLayout(cp_group)

        self.cp_length_card = MetricCard("CP Length (cycles)", "-")
        cp_layout.addWidget(self.cp_length_card, 0, 0)

        self.cp_insts_card = MetricCard("CP Instructions", "-")
        cp_layout.addWidget(self.cp_insts_card, 0, 1)

        self.ilp_card = MetricCard("ILP", "-")
        cp_layout.addWidget(self.ilp_card, 1, 0)

        self.max_parallel_card = MetricCard("Max Parallelism", "-")
        cp_layout.addWidget(self.max_parallel_card, 1, 1)

        layout.addWidget(cp_group)

        # Dependencies section
        dep_group = QGroupBox("Dependencies")
        dep_layout = QGridLayout(dep_group)

        self.true_deps_card = MetricCard("RAW (True)", "-")
        dep_layout.addWidget(self.true_deps_card, 0, 0)

        self.anti_deps_card = MetricCard("WAR (Anti)", "-")
        dep_layout.addWidget(self.anti_deps_card, 0, 1)

        self.output_deps_card = MetricCard("WAW (Output)", "-")
        dep_layout.addWidget(self.output_deps_card, 1, 0)

        self.avg_depth_card = MetricCard("Avg Depth", "-")
        dep_layout.addWidget(self.avg_depth_card, 1, 1)

        layout.addWidget(dep_group)
        layout.addStretch()
        return tab

    def _create_memory_tab(self) -> QWidget:
        """Create memory access tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Cache section
        cache_group = QGroupBox("Cache Statistics")
        cache_layout = QGridLayout(cache_group)

        self.cache_hits_card = MetricCard("Cache Hits", "-")
        cache_layout.addWidget(self.cache_hits_card, 0, 0)

        self.cache_misses_card = MetricCard("Cache Misses", "-")
        cache_layout.addWidget(self.cache_misses_card, 0, 1)

        self.hit_rate_card = MetricCard("Hit Rate", "-")
        cache_layout.addWidget(self.hit_rate_card, 1, 0)

        self.avg_latency_card = MetricCard("Avg Read Latency", "-")
        cache_layout.addWidget(self.avg_latency_card, 1, 1)

        layout.addWidget(cache_group)

        # SPM section
        spm_group = QGroupBox("Scratchpad Memory")
        spm_layout = QGridLayout(spm_group)

        self.spm_reads_card = MetricCard("SPM Reads", "-")
        spm_layout.addWidget(self.spm_reads_card, 0, 0)

        self.spm_writes_card = MetricCard("SPM Writes", "-")
        spm_layout.addWidget(self.spm_writes_card, 0, 1)

        layout.addWidget(spm_group)
        layout.addStretch()
        return tab

    def _create_stalls_tab(self) -> QWidget:
        """Create stall breakdown tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Stall Root Cause Breakdown")
        group_layout = QVBoxLayout(group)

        self.stall_bars = {}
        stall_types = [
            ("Memory Latency", "memory_latency"),
            ("RAW Hazard", "raw_hazard"),
            ("WAR Hazard", "war_hazard"),
            ("WAW Hazard", "waw_hazard"),
            ("FU Contention", "fu_contention"),
            ("Port Contention", "port_contention"),
            ("DMA Pending", "dma_pending"),
            ("Resource Limit", "resource_limit"),
        ]

        for label, key in stall_types:
            bar = StallBar(label, 0.0)
            self.stall_bars[key] = bar
            group_layout.addWidget(bar)

        layout.addWidget(group)
        layout.addStretch()
        return tab

    def _create_power_area_tab(self) -> QWidget:
        """Create power and area tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Power section
        power_group = QGroupBox("Power Consumption")
        power_layout = QGridLayout(power_group)

        self.total_power_card = MetricCard("Total Power", "-")
        power_layout.addWidget(self.total_power_card, 0, 0)

        self.fu_power_card = MetricCard("FU Power", "-")
        power_layout.addWidget(self.fu_power_card, 0, 1)

        self.reg_power_card = MetricCard("Register Power", "-")
        power_layout.addWidget(self.reg_power_card, 1, 0)

        self.mem_power_card = MetricCard("Memory Power", "-")
        power_layout.addWidget(self.mem_power_card, 1, 1)

        layout.addWidget(power_group)

        # Area section
        area_group = QGroupBox("Silicon Area")
        area_layout = QGridLayout(area_group)

        self.total_area_card = MetricCard("Total Area", "-")
        area_layout.addWidget(self.total_area_card, 0, 0)

        self.fu_area_card = MetricCard("FU Area", "-")
        area_layout.addWidget(self.fu_area_card, 0, 1)

        layout.addWidget(area_group)
        layout.addStretch()
        return tab

    def connect_to_simulation(self, connection: SimulationConnection):
        """Connect to a simulation connection for live updates."""
        self.connection = connection
        connection.stats_updated.connect(self._on_stats_updated)
        connection.connected.connect(self._on_connected)
        connection.disconnected.connect(self._on_disconnected)

    def disconnect_from_simulation(self):
        """Disconnect from simulation connection."""
        if self.connection:
            try:
                self.connection.stats_updated.disconnect(self._on_stats_updated)
                self.connection.connected.disconnect(self._on_connected)
                self.connection.disconnected.disconnect(self._on_disconnected)
            except:
                pass
            self.connection = None
        self._on_disconnected()

    @Slot()
    def _on_connected(self):
        """Handle connection established."""
        self.status_label.setText("Status: Connected (receiving data...)")
        self.status_label.setStyleSheet("color: green; padding: 2px;")

    @Slot()
    def _on_disconnected(self):
        """Handle disconnection."""
        self.status_label.setText("Status: Disconnected")
        self.status_label.setStyleSheet("color: gray; padding: 2px;")

    @Slot(dict)
    def _on_stats_updated(self, data: Dict[str, Any]):
        """Handle incoming stats update."""
        try:
            # Parse the stats data
            json_str = json.dumps(data)
            stats = parse_enhanced_json(json_str)
            self.current_stats = stats
            self._update_display(stats)
            self.stats_updated.emit(stats)
        except Exception as e:
            print(f"Error updating stats: {e}")

    def set_stats(self, stats: EnhancedSimulationStats):
        """Manually set statistics (for file-based display)."""
        self.current_stats = stats
        self._update_display(stats)

    def _update_display(self, stats: EnhancedSimulationStats):
        """Update all display elements with new stats."""
        perf = stats.performance
        df = stats.dataflow
        mem = stats.memory_access
        sb = stats.stall_breakdown
        pwr = stats.power
        area = stats.area

        # Performance tab
        self.cycles_card.set_value(format_cycles(perf.total_cycles))
        stall_pct = (perf.stall_cycles / perf.total_cycles * 100) if perf.total_cycles > 0 else 0
        color = QColor("#27ae60") if stall_pct < 20 else (
            QColor("#f39c12") if stall_pct < 50 else QColor("#e74c3c")
        )
        self.stall_pct_card.set_value(format_percentage(stall_pct), color)
        self.sim_time_card.set_value(format_metric(perf.sim_time_ns, "ns"))
        self.nodes_card.set_value(format_cycles(perf.executed_nodes))
        self.active_cycles_card.set_value(format_cycles(perf.active_cycles))
        ipc = perf.executed_nodes / perf.total_cycles if perf.total_cycles > 0 else 0
        self.ipc_card.set_value(f"{ipc:.2f}")

        # Dataflow tab
        self.cp_length_card.set_value(str(df.critical_path_length))
        self.cp_insts_card.set_value(str(df.critical_path_instructions))
        self.ilp_card.set_value(f"{df.ilp:.2f}")
        self.max_parallel_card.set_value(str(df.max_parallel_ops))
        self.true_deps_card.set_value(str(df.true_dependencies))
        self.anti_deps_card.set_value(str(df.anti_dependencies))
        self.output_deps_card.set_value(str(df.output_dependencies))
        self.avg_depth_card.set_value(f"{df.avg_dependency_depth:.1f}")

        # Memory tab
        self.cache_hits_card.set_value(str(mem.cache_hits))
        self.cache_misses_card.set_value(str(mem.cache_misses))
        self.hit_rate_card.set_value(format_percentage(mem.cache_hit_rate))
        self.avg_latency_card.set_value(f"{mem.avg_read_latency:.1f} ticks")
        self.spm_reads_card.set_value(str(mem.spm_reads))
        self.spm_writes_card.set_value(str(mem.spm_writes))

        # Stalls tab
        pcts = sb.get_stall_percentages()
        for key, bar in self.stall_bars.items():
            bar.set_percentage(pcts.get(key, 0.0))

        # Power/Area tab
        self.total_power_card.set_value(format_metric(pwr.total_power, "W", 3))
        self.fu_power_card.set_value(format_metric(pwr.fu_total, "W", 3))
        self.reg_power_card.set_value(format_metric(pwr.reg_total, "W", 3))
        mem_power = pwr.spm_total + pwr.cache_total
        self.mem_power_card.set_value(format_metric(mem_power, "W", 3))
        self.total_area_card.set_value(format_metric(area.total_area_um2, "um2"))
        self.fu_area_card.set_value(format_metric(area.fu_area_um2, "um2"))
