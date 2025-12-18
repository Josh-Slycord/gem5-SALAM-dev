# ==============================================================================
# fu_utilization.py - Functional Unit Utilization Analysis
# ==============================================================================
"""Functional Unit Utilization Widget for gem5-SALAM GUI.

This module provides the FUUtilizationWidget, which displays functional unit
usage patterns over time using a heatmap visualization and summary statistics
table. Helps identify over/under-provisioned FUs in accelerator designs.

Features:
    - Heatmap showing FU utilization over time (green→yellow→red)
    - Summary statistics table with peak/average utilization
    - Bottleneck detection and recommendations
    - Multiple view modes (heatmap, table, or both)

Widget Layout::

    +------------------------------------------------------------------+
    | Functional Unit Utilization                                       |
    +------------------------------------------------------------------+
    | View: [Heatmap v] [Table v] [Both v]                             |
    +------------------------------------------------------------------+
    | Heatmap                                                           |
    | +--------------------------------------------------+ +----+      |
    | | int_alu   |████████░░░░░░░░░░░░░░░░░░░░░|      | |100%|      |
    | | int_mul   |██████████████░░░░░░░░░░░░░░░|      | |    |      |
    | | fp_add    |████░░░░░░░░░░░░░░░░░░░░░░░░░|      | | 50%|      |
    | | fp_mul    |██████████████████████████░░░|      | |    |      |
    | | memory    |████████████░░░░░░░░░░░░░░░░░|      | |  0%|      |
    | +--------------------------------------------------+ +----+      |
    |              0                    cycles                          |
    +------------------------------------------------------------------+
    | Statistics Table                                                  |
    | | FU Type      | Count | Max Occ | Avg Occ | Peak % | Avg % |   |
    | |--------------|-------|---------|---------|--------|-------|   |
    | | Integer ALU  |   4   |    3    |   1.5   |  75%   |  38%  |   |
    | | FP Multiply  |   2   |    2    |   1.8   | 100%   |  90%  |   |
    +------------------------------------------------------------------+
    | ⚠ Potential Bottlenecks:                                         |
    | FP Multiply: Peak 100% (consider adding more units)              |
    +------------------------------------------------------------------+

Functional Unit Categories:
    | Key        | Display Name     | Typical Operations        |
    |------------|------------------|---------------------------|
    | int_alu    | Integer ALU      | add, sub, and, or, xor    |
    | int_mul    | Integer Multiply | mul, imul                 |
    | int_div    | Integer Divide   | div, idiv, rem            |
    | fp_add     | FP Add/Sub       | fadd, fsub                |
    | fp_mul     | FP Multiply      | fmul                      |
    | fp_div     | FP Divide        | fdiv, fsqrt               |
    | shifter    | Shifter          | shl, shr, ashr            |
    | bitwise    | Bitwise          | and, or, xor (logic)      |
    | compare    | Compare          | icmp, fcmp                |
    | gep        | GEP              | getelementptr             |
    | conversion | Type Conversion  | trunc, ext, fptoui        |
    | memory     | Memory Unit      | load, store               |

Utilization Colors:
    | Range      | Color  | Meaning                    |
    |------------|--------|----------------------------|
    | 0% - 50%   | Green  | Underutilized/headroom     |
    | 50% - 75%  | Yellow | Moderate usage             |
    | 75% - 100% | Red    | High utilization/bottleneck|

Example:
    Loading FU statistics::

        from salam_gui.widgets.fu_utilization import (
            FUUtilizationWidget, FUHistory, parse_fu_stats_output
        )

        widget = FUUtilizationWidget()

        with open("m5out/stats.txt") as f:
            history = parse_fu_stats_output(f.read())
        widget.set_history(history)

Design Recommendations:
    - Peak > 95%: Consider adding more FUs of this type
    - Avg < 10% with count > 1: May be over-provisioned
    - Consistent 100%: Critical bottleneck, highest priority

See Also:
    - queue_monitor: Queue depth visualization
    - power_area: FU power and area breakdown
    - stats_dashboard: Overall performance summary
"""


__version__ = "3.0.0.pre[1.0.0]"

from typing import Dict, List, Optional
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QGroupBox, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QComboBox
)
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient
from PySide6.QtCore import Qt, QRect


# Functional unit categories
FU_CATEGORIES = {
    'int_alu': 'Integer ALU',
    'int_mul': 'Integer Multiply',
    'int_div': 'Integer Divide',
    'fp_add': 'FP Add/Sub',
    'fp_mul': 'FP Multiply',
    'fp_div': 'FP Divide',
    'shifter': 'Shifter',
    'bitwise': 'Bitwise',
    'compare': 'Compare',
    'gep': 'GEP',
    'conversion': 'Type Conversion',
    'memory': 'Memory Unit',
}


@dataclass
class FUSnapshot:
    """FU utilization at a specific cycle."""
    cycle: int
    utilization: Dict[str, float] = field(default_factory=dict)  # FU type -> 0.0-1.0


@dataclass
class FUStats:
    """Summary statistics for a functional unit type."""
    name: str
    display_name: str
    count: int = 0
    max_occupancy: int = 0
    avg_occupancy: float = 0.0
    peak_utilization: float = 0.0
    avg_utilization: float = 0.0
    total_ops: int = 0


@dataclass
class FUHistory:
    """Time series of FU utilization."""
    snapshots: List[FUSnapshot] = field(default_factory=list)
    stats: Dict[str, FUStats] = field(default_factory=dict)

    @property
    def max_cycle(self) -> int:
        return max(s.cycle for s in self.snapshots) if self.snapshots else 0

    @property
    def fu_types(self) -> List[str]:
        if not self.snapshots:
            return []
        return list(self.snapshots[0].utilization.keys())


class FUHeatmap(QWidget):
    """Heatmap showing FU utilization over time."""

    def __init__(self):
        super().__init__()
        self.history: Optional[FUHistory] = None
        self.setMinimumHeight(200)
        self.setMinimumWidth(400)

    def set_history(self, history: FUHistory):
        """Set the FU history to display."""
        self.history = history
        self.update()

    def paintEvent(self, event):
        """Draw the heatmap."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        margin_left = 100
        margin_top = 20
        margin_right = 60
        margin_bottom = 30

        chart_rect = QRect(
            margin_left, margin_top,
            rect.width() - margin_left - margin_right,
            rect.height() - margin_top - margin_bottom
        )

        # Background
        painter.fillRect(rect, QColor(255, 255, 255))

        if not self.history or not self.history.snapshots:
            painter.setPen(QColor(128, 128, 128))
            painter.drawText(chart_rect, Qt.AlignmentFlag.AlignCenter,
                           "No FU utilization data loaded")
            return

        fu_types = self.history.fu_types
        if not fu_types:
            return

        num_fus = len(fu_types)
        num_cycles = len(self.history.snapshots)

        cell_height = chart_rect.height() / num_fus
        cell_width = chart_rect.width() / max(num_cycles, 1)

        # Draw heatmap cells
        for i, snapshot in enumerate(self.history.snapshots):
            x = chart_rect.left() + i * cell_width

            for j, fu_type in enumerate(fu_types):
                y = chart_rect.top() + j * cell_height
                utilization = snapshot.utilization.get(fu_type, 0)

                # Color based on utilization (green -> yellow -> red)
                color = self._utilization_color(utilization)
                painter.fillRect(
                    int(x), int(y),
                    max(int(cell_width), 1), int(cell_height),
                    color
                )

        # Draw grid
        painter.setPen(QPen(QColor(200, 200, 200), 0.5))
        for j in range(num_fus + 1):
            y = chart_rect.top() + j * cell_height
            painter.drawLine(chart_rect.left(), int(y),
                           chart_rect.right(), int(y))

        # Draw FU labels (Y axis)
        painter.setPen(QColor(0, 0, 0))
        painter.setFont(QFont("Arial", 8))
        for j, fu_type in enumerate(fu_types):
            y = chart_rect.top() + (j + 0.5) * cell_height
            display_name = FU_CATEGORIES.get(fu_type, fu_type)
            painter.drawText(5, int(y) + 4, display_name[:12])

        # Draw color legend
        legend_x = chart_rect.right() + 10
        legend_height = chart_rect.height()
        legend_width = 20

        gradient = QLinearGradient(legend_x, chart_rect.top(),
                                   legend_x, chart_rect.bottom())
        gradient.setColorAt(0.0, QColor(255, 0, 0))      # High utilization
        gradient.setColorAt(0.5, QColor(255, 255, 0))    # Medium
        gradient.setColorAt(1.0, QColor(0, 255, 0))      # Low

        painter.fillRect(legend_x, chart_rect.top(),
                        legend_width, legend_height, gradient)

        painter.setPen(QColor(0, 0, 0))
        painter.drawText(legend_x + 25, chart_rect.top() + 10, "100%")
        painter.drawText(legend_x + 25, chart_rect.top() + legend_height // 2, "50%")
        painter.drawText(legend_x + 25, chart_rect.bottom(), "0%")

    def _utilization_color(self, utilization: float) -> QColor:
        """Map utilization (0-1) to color."""
        if utilization < 0.5:
            # Green to yellow
            r = int(255 * utilization * 2)
            g = 255
        else:
            # Yellow to red
            r = 255
            g = int(255 * (1 - utilization) * 2)
        return QColor(r, g, 0)


class FUStatsTable(QTableWidget):
    """Table showing FU summary statistics."""

    def __init__(self):
        super().__init__()

        self.setColumnCount(6)
        self.setHorizontalHeaderLabels([
            "Functional Unit", "Count", "Max Occ.", "Avg Occ.",
            "Peak Util.", "Avg Util."
        ])

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 6):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

    def set_stats(self, stats: Dict[str, FUStats]):
        """Update table with FU statistics."""
        self.setRowCount(len(stats))

        for row, (fu_type, stat) in enumerate(stats.items()):
            self.setItem(row, 0, QTableWidgetItem(stat.display_name))
            self.setItem(row, 1, QTableWidgetItem(str(stat.count)))
            self.setItem(row, 2, QTableWidgetItem(str(stat.max_occupancy)))
            self.setItem(row, 3, QTableWidgetItem(f"{stat.avg_occupancy:.1f}"))
            self.setItem(row, 4, QTableWidgetItem(f"{stat.peak_utilization:.1%}"))
            self.setItem(row, 5, QTableWidgetItem(f"{stat.avg_utilization:.1%}"))

            # Color cells based on utilization
            peak_item = self.item(row, 4)
            if stat.peak_utilization > 0.9:
                peak_item.setBackground(QColor(255, 200, 200))  # Red-ish
            elif stat.peak_utilization > 0.7:
                peak_item.setBackground(QColor(255, 255, 200))  # Yellow-ish


class FUUtilizationWidget(QWidget):
    """Main FU utilization widget combining heatmap and stats."""

    def __init__(self):
        super().__init__()
        self.history: Optional[FUHistory] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Functional Unit Utilization")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(title)

        # View selector
        view_layout = QHBoxLayout()
        view_layout.addWidget(QLabel("View:"))
        self.view_combo = QComboBox()
        self.view_combo.addItems(["Heatmap", "Table", "Both"])
        self.view_combo.setCurrentIndex(2)
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        view_layout.addWidget(self.view_combo)
        view_layout.addStretch()
        layout.addLayout(view_layout)

        # Heatmap
        self.heatmap = FUHeatmap()
        layout.addWidget(self.heatmap)

        # Stats table
        self.stats_table = FUStatsTable()
        layout.addWidget(self.stats_table)

        # Bottleneck analysis
        self.bottleneck_label = QLabel("")
        self.bottleneck_label.setWordWrap(True)
        self.bottleneck_label.setStyleSheet(
            "background: #fff3cd; padding: 10px; border-radius: 5px;"
        )
        self.bottleneck_label.hide()
        layout.addWidget(self.bottleneck_label)

    def _on_view_changed(self, index: int):
        """Handle view mode change."""
        if index == 0:  # Heatmap only
            self.heatmap.show()
            self.stats_table.hide()
        elif index == 1:  # Table only
            self.heatmap.hide()
            self.stats_table.show()
        else:  # Both
            self.heatmap.show()
            self.stats_table.show()

    def set_history(self, history: FUHistory):
        """Load FU utilization data."""
        self.history = history
        self.heatmap.set_history(history)
        self.stats_table.set_stats(history.stats)
        self._analyze_bottlenecks()

    def _analyze_bottlenecks(self):
        """Analyze and display potential bottlenecks."""
        if not self.history or not self.history.stats:
            self.bottleneck_label.hide()
            return

        bottlenecks = []
        for fu_type, stat in self.history.stats.items():
            if stat.peak_utilization > 0.95:
                bottlenecks.append(
                    f"<b>{stat.display_name}</b>: Peak {stat.peak_utilization:.0%} "
                    f"(consider adding more units)"
                )
            elif stat.avg_utilization < 0.1 and stat.count > 1:
                bottlenecks.append(
                    f"<b>{stat.display_name}</b>: Avg {stat.avg_utilization:.0%} "
                    f"(may be over-provisioned)"
                )

        if bottlenecks:
            self.bottleneck_label.setText(
                "<b>Potential Bottlenecks:</b><br>" + "<br>".join(bottlenecks)
            )
            self.bottleneck_label.show()
        else:
            self.bottleneck_label.hide()


def parse_fu_stats_output(content: str) -> FUHistory:
    """
    Parse FU statistics from gem5-SALAM output.

    Looks for patterns like:
    FU: int_alu count: 4 max_occ: 3 avg_occ: 1.5
    """
    import re

    history = FUHistory()

    # Pattern for FU stats lines
    pattern = re.compile(
        r'(\w+).*?count[:\s]+(\d+).*?'
        r'max[_\s]?occ(?:upancy)?[:\s]+(\d+).*?'
        r'avg[_\s]?occ(?:upancy)?[:\s]+([\d.]+)',
        re.IGNORECASE
    )

    for match in pattern.finditer(content):
        fu_type = match.group(1).lower()
        if fu_type in FU_CATEGORIES or 'fu' in fu_type or 'alu' in fu_type:
            stats = FUStats(
                name=fu_type,
                display_name=FU_CATEGORIES.get(fu_type, fu_type),
                count=int(match.group(2)),
                max_occupancy=int(match.group(3)),
                avg_occupancy=float(match.group(4))
            )
            # Calculate utilization
            if stats.count > 0:
                stats.peak_utilization = stats.max_occupancy / stats.count
                stats.avg_utilization = stats.avg_occupancy / stats.count

            history.stats[fu_type] = stats

    return history
