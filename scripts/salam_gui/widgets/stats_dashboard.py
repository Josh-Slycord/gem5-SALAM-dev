# ==============================================================================
# stats_dashboard.py - Performance Summary Dashboard
# ==============================================================================
"""Performance Summary Dashboard Widget.

This module provides the StatsDashboard widget, which displays key
performance metrics from gem5-SALAM simulations in a card-based layout
with visual indicators for performance health.

Features:
    - Metric cards with large, readable values
    - Color-coded stall percentage (green/orange/red)
    - Stall breakdown visualization with horizontal bars
    - Power and area metrics grouping
    - Raw data display for debugging

Dashboard Layout::

    +------------------------------------------+
    | Performance Summary                       |
    +------------------------------------------+
    | Performance                              |
    | +----------------+ +----------------+    |
    | | Total Cycles   | | Stall %        |    |
    | | 1.5M           | | 23.5%          |    |
    | +----------------+ +----------------+    |
    | +----------------+ +----------------+    |
    | | Sim Time       | | Nodes Executed |    |
    | | 12.34s         | | 45,230         |    |
    | +----------------+ +----------------+    |
    +------------------------------------------+
    | Stall Breakdown                          |
    | Load Stalls:    ========== 45.2%        |
    | Store Stalls:   =====      25.1%        |
    | Compute Stalls: ===        15.3%        |
    | Combined:       ====       14.4%        |
    +------------------------------------------+
    | Power                                    |
    | +----------------+ +----------------+    |
    | | Total Power    | | FU Power       |    |
    | +----------------+ +----------------+    |
    +------------------------------------------+

Stall Severity Colors:
    | Percentage | Color  | Meaning       |
    |------------|--------|---------------|
    | 0-20%      | Green  | Healthy       |
    | 20-50%     | Orange | Moderate      |
    | 50-100%    | Red    | Critical      |

Example:
    Displaying simulation statistics::

        from salam_gui.widgets.stats_dashboard import StatsDashboard
        from salam_gui.data.stats_parser import parse_stats_output

        dashboard = StatsDashboard()
        stats = parse_stats_output(Path("m5out/stats.txt"))
        dashboard.set_stats(stats)

See Also:
    - stats_parser: Parses statistics files into SimulationStats
    - MainWindow: Hosts this widget as a right-side dock
"""


__version__ = "3.0.0.pre[1.0.0]"

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QScrollArea, QGroupBox
)
from PySide6.QtGui import QFont, QColor, QPalette
from PySide6.QtCore import Qt

from ..data.stats_parser import SimulationStats, format_cycles, format_power, format_area


class MetricCard(QFrame):
    """A card displaying a single metric with label and value."""

    def __init__(self, label: str, value: str = "-", color: Optional[QColor] = None):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setMinimumHeight(80)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Label
        self.label_widget = QLabel(label)
        self.label_widget.setStyleSheet("color: gray; font-size: 10pt;")
        layout.addWidget(self.label_widget)

        # Value
        self.value_widget = QLabel(value)
        self.value_widget.setStyleSheet("font-size: 16pt; font-weight: bold;")
        if color:
            self.value_widget.setStyleSheet(
                f"font-size: 16pt; font-weight: bold; color: {color.name()};"
            )
        layout.addWidget(self.value_widget)

        layout.addStretch()

    def set_value(self, value: str, color: Optional[QColor] = None):
        """Update the displayed value."""
        self.value_widget.setText(value)
        if color:
            self.value_widget.setStyleSheet(
                f"font-size: 16pt; font-weight: bold; color: {color.name()};"
            )


class StallBreakdownWidget(QFrame):
    """Widget showing stall breakdown as horizontal bars."""

    def __init__(self):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)

        title = QLabel("Stall Breakdown")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        self.bars_layout = QVBoxLayout()
        layout.addLayout(self.bars_layout)

        self._add_bar("Load Stalls", 0, QColor(100, 149, 237))
        self._add_bar("Store Stalls", 0, QColor(255, 165, 0))
        self._add_bar("Compute Stalls", 0, QColor(144, 238, 144))
        self._add_bar("Combined", 0, QColor(255, 99, 71))

        layout.addStretch()

    def _add_bar(self, label: str, percentage: float, color: QColor):
        """Add a bar for a stall type."""
        bar_layout = QHBoxLayout()

        label_widget = QLabel(f"{label}:")
        label_widget.setMinimumWidth(100)
        bar_layout.addWidget(label_widget)

        # Simple bar using a styled label
        bar = QLabel()
        bar.setFixedHeight(15)
        bar.setStyleSheet(
            f"background-color: {color.name()}; border-radius: 3px;"
        )
        bar.setFixedWidth(max(int(percentage * 2), 5))
        bar_layout.addWidget(bar)

        percent_label = QLabel(f"{percentage:.1f}%")
        percent_label.setMinimumWidth(50)
        bar_layout.addWidget(percent_label)

        bar_layout.addStretch()
        self.bars_layout.addLayout(bar_layout)

    def update_values(self, load: float, store: float, compute: float, combined: float):
        """Update bar values."""
        # Clear existing bars
        while self.bars_layout.count():
            item = self.bars_layout.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

        self._add_bar("Load Stalls", load, QColor(100, 149, 237))
        self._add_bar("Store Stalls", store, QColor(255, 165, 0))
        self._add_bar("Compute Stalls", compute, QColor(144, 238, 144))
        self._add_bar("Combined", combined, QColor(255, 99, 71))


class StatsDashboard(QWidget):
    """Dashboard showing performance summary with metric cards."""

    def __init__(self):
        super().__init__()
        self.stats: Optional[SimulationStats] = None
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dashboard layout."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)

        # Title
        title = QLabel("Performance Summary")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(title)

        # Performance metrics cards
        perf_group = QGroupBox("Performance")
        perf_layout = QGridLayout(perf_group)

        self.cycles_card = MetricCard("Total Cycles")
        self.stalls_card = MetricCard("Stall %")
        self.time_card = MetricCard("Sim Time")
        self.nodes_card = MetricCard("Nodes Executed")

        perf_layout.addWidget(self.cycles_card, 0, 0)
        perf_layout.addWidget(self.stalls_card, 0, 1)
        perf_layout.addWidget(self.time_card, 1, 0)
        perf_layout.addWidget(self.nodes_card, 1, 1)

        layout.addWidget(perf_group)

        # Stall breakdown
        self.stall_widget = StallBreakdownWidget()
        layout.addWidget(self.stall_widget)

        # Power metrics
        power_group = QGroupBox("Power")
        power_layout = QGridLayout(power_group)

        self.total_power_card = MetricCard("Total Power")
        self.fu_power_card = MetricCard("FU Power")
        self.mem_power_card = MetricCard("Memory Power")

        power_layout.addWidget(self.total_power_card, 0, 0)
        power_layout.addWidget(self.fu_power_card, 0, 1)
        power_layout.addWidget(self.mem_power_card, 1, 0)

        layout.addWidget(power_group)

        # Area metrics
        area_group = QGroupBox("Area")
        area_layout = QGridLayout(area_group)

        self.total_area_card = MetricCard("Total Area")
        self.fu_area_card = MetricCard("FU Area")

        area_layout.addWidget(self.total_area_card, 0, 0)
        area_layout.addWidget(self.fu_area_card, 0, 1)

        layout.addWidget(area_group)

        # Raw data section
        raw_group = QGroupBox("Raw Data")
        raw_layout = QVBoxLayout(raw_group)
        self.raw_label = QLabel("Load statistics to see raw data")
        self.raw_label.setWordWrap(True)
        self.raw_label.setStyleSheet("font-family: monospace; font-size: 9pt;")
        raw_layout.addWidget(self.raw_label)
        layout.addWidget(raw_group)

        layout.addStretch()

        scroll.setWidget(container)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def set_stats(self, stats: SimulationStats):
        """Update dashboard with new statistics."""
        self.stats = stats

        # Update performance cards
        perf = stats.performance
        self.cycles_card.set_value(format_cycles(perf.total_cycles))

        # Color stall percentage based on severity
        stall_color = None
        if perf.stall_percentage > 50:
            stall_color = QColor(255, 0, 0)  # Red
        elif perf.stall_percentage > 20:
            stall_color = QColor(255, 165, 0)  # Orange
        else:
            stall_color = QColor(0, 128, 0)  # Green

        self.stalls_card.set_value(f"{perf.stall_percentage:.1f}%", stall_color)
        self.time_card.set_value(f"{perf.sim_time:.2f}s")
        self.nodes_card.set_value(str(perf.nodes_executed))

        # Update stall breakdown
        total = perf.load_stalls + perf.store_stalls + perf.compute_stalls
        if total > 0:
            self.stall_widget.update_values(
                perf.load_stalls / total * 100,
                perf.store_stalls / total * 100,
                perf.compute_stalls / total * 100,
                perf.combined_stalls / total * 100
            )

        # Update power cards
        power = stats.power
        self.total_power_card.set_value(format_power(power.total_power))
        self.fu_power_card.set_value(format_power(power.fu_total))
        self.mem_power_card.set_value(
            format_power(power.spm_total + power.cache_total)
        )

        # Update area cards
        area = stats.area
        self.total_area_card.set_value(format_area(area.total_area))
        self.fu_area_card.set_value(format_area(area.fu_area))

        # Update raw data
        if stats.raw_data:
            raw_text = "\n".join(
                f"{k}: {v}" for k, v in list(stats.raw_data.items())[:20]
            )
            self.raw_label.setText(raw_text)
        else:
            self.raw_label.setText("No raw data available")

    def clear(self):
        """Clear all displayed statistics."""
        self.stats = None
        self.cycles_card.set_value("-")
        self.stalls_card.set_value("-")
        self.time_card.set_value("-")
        self.nodes_card.set_value("-")
        self.total_power_card.set_value("-")
        self.fu_power_card.set_value("-")
        self.mem_power_card.set_value("-")
        self.total_area_card.set_value("-")
        self.fu_area_card.set_value("-")
        self.raw_label.setText("Load statistics to see raw data")
