# ==============================================================================
# comparison.py - Simulation Run Comparison Widget
# ==============================================================================
"""Simulation Run Comparison Widget for gem5-SALAM GUI.

This module provides the ComparisonWidget, which enables side-by-side
comparison of two simulation runs with visual difference highlighting.
Essential for design space exploration, regression testing, and
optimization impact analysis.

Features:
    - Load two simulation runs for comparison
    - Visual bar chart comparing key metrics
    - Color-coded improvement/regression indicators
    - Detailed table with percentage changes
    - Automatic summary generation

Widget Layout::

    +------------------------------------------------------------------+
    | Simulation Comparison                                             |
    +------------------------------------------------------------------+
    | +---------------------------+ +---------------------------+       |
    | | Run A (Baseline)          | | Run B (Comparison)        |       |
    | | [Load...]                 | | [Load...]                 |       |
    | | stats_baseline.txt        | | stats_optimized.txt       |       |
    | | Cycles: 45,230            | | Cycles: 38,500            |       |
    | | Stalls: 23.5%             | | Stalls: 15.2%             |       |
    | +---------------------------+ +---------------------------+       |
    |                    [Compare Runs]                                 |
    +------------------------------------------------------------------+
    | [Visual Comparison] [Detailed Table]                              |
    +------------------------------------------------------------------+
    | Metric        |   Run A    |   Run B    |  Change   |            |
    |---------------|------------|------------|-----------|            |
    | Total Cycles  | ████████   | █████      |  -14.9%   | ▼ Green    |
    | Stall %       | █████      | ███        |  -35.3%   | ▼ Green    |
    | Total Power   | ██████     | ███████    |  +12.1%   | ▲ Red      |
    +------------------------------------------------------------------+
    | Summary:                                                          |
    | Improvements: Total Cycles, Stall %, Load Stalls                 |
    | Regressions: Total Power                                         |
    | Overall: 14.9% faster                                            |
    +------------------------------------------------------------------+

Comparison Metrics:
    | Metric         | Unit   | Lower is Better |
    |----------------|--------|-----------------|
    | Total Cycles   | cycles | Yes             |
    | Stall %        | %      | Yes             |
    | Load Stalls    | cycles | Yes             |
    | Store Stalls   | cycles | Yes             |
    | Compute Stalls | cycles | Yes             |
    | Total Power    | mW     | Yes             |
    | Total Area     | mm²    | Yes             |
    | IPC            | -      | No (higher)     |
    | Throughput     | -      | No (higher)     |

Color Coding:
    | Change   | Color  | Meaning                       |
    |----------|--------|-------------------------------|
    | < 0      | Green  | Improvement (for most metrics)|
    | > 0      | Red    | Regression (for most metrics) |
    | = 0      | Gray   | No change                     |

Example:
    Comparing two simulation runs::

        from salam_gui.widgets.comparison import ComparisonWidget
        from salam_gui.data.stats_parser import parse_stats_output

        widget = ComparisonWidget()

        # Load runs manually via UI or programmatically
        stats_a = parse_stats_output(Path("baseline/stats.txt"))
        stats_b = parse_stats_output(Path("optimized/stats.txt"))

        widget.set_runs(
            stats_a, stats_b,
            name_a="Baseline",
            name_b="Optimized"
        )

Use Cases:
    - Optimization impact: Compare before/after changes
    - Design exploration: Compare different FU configurations
    - Regression testing: Verify changes don't hurt performance
    - Benchmark comparison: Same design, different workloads

See Also:
    - stats_parser: Parses simulation statistics files
    - stats_dashboard: Single-run performance summary
    - simulation_panel: Run simulations to generate data
"""


__version__ = "3.0.0.pre[1.0.0]"

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QGroupBox, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QFileDialog,
    QSplitter, QTabWidget
)
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PySide6.QtCore import Qt, Signal

from ..data.stats_parser import SimulationStats, parse_stats_output


@dataclass
class ComparisonMetric:
    """A single metric comparison."""
    name: str
    value_a: float
    value_b: float
    unit: str = ""

    @property
    def difference(self) -> float:
        return self.value_b - self.value_a

    @property
    def percent_change(self) -> float:
        if self.value_a == 0:
            return 0 if self.value_b == 0 else float('inf')
        return ((self.value_b - self.value_a) / self.value_a) * 100

    @property
    def improved(self) -> Optional[bool]:
        """Return True if improved, False if regressed, None if no change."""
        # For cycles, stalls, power - lower is better
        if self.name in ['Total Cycles', 'Stall %', 'Total Power', 'Stall Cycles']:
            if self.difference < 0:
                return True
            elif self.difference > 0:
                return False
        # For others, higher might be better (e.g., IPC)
        elif self.name in ['IPC', 'Throughput', 'Utilization']:
            if self.difference > 0:
                return True
            elif self.difference < 0:
                return False
        return None


@dataclass
class ComparisonResult:
    """Complete comparison between two runs."""
    run_a_name: str
    run_b_name: str
    metrics: List[ComparisonMetric] = field(default_factory=list)

    def add_metric(self, name: str, value_a: float, value_b: float, unit: str = ""):
        self.metrics.append(ComparisonMetric(name, value_a, value_b, unit))


class ComparisonBarChart(QWidget):
    """Bar chart comparing metrics between two runs."""

    def __init__(self):
        super().__init__()
        self.result: Optional[ComparisonResult] = None
        self.setMinimumHeight(300)
        self.setMinimumWidth(400)

    def set_result(self, result: ComparisonResult):
        """Set comparison result to display."""
        self.result = result
        self.update()

    def paintEvent(self, event):
        """Draw the comparison bar chart."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        margin_left = 120
        margin_right = 80
        margin_top = 40
        margin_bottom = 30

        chart_rect = rect.adjusted(margin_left, margin_top, -margin_right, -margin_bottom)

        # Background
        painter.fillRect(rect, QColor(255, 255, 255))

        if not self.result or not self.result.metrics:
            painter.setPen(QColor(128, 128, 128))
            painter.drawText(chart_rect, Qt.AlignmentFlag.AlignCenter,
                           "Load two runs to compare")
            return

        # Filter to numeric comparable metrics
        metrics = [m for m in self.result.metrics
                   if abs(m.value_a) + abs(m.value_b) > 0][:8]

        if not metrics:
            return

        num_metrics = len(metrics)
        bar_height = chart_rect.height() / num_metrics / 2 - 5
        max_value = max(max(abs(m.value_a), abs(m.value_b)) for m in metrics)
        if max_value == 0:
            max_value = 1

        painter.setFont(QFont("Arial", 9))

        for i, metric in enumerate(metrics):
            y_center = chart_rect.top() + (i + 0.5) * chart_rect.height() / num_metrics

            # Draw metric name
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(5, int(y_center) + 4, metric.name[:15])

            # Bar positions
            y_a = y_center - bar_height - 2
            y_b = y_center + 2

            # Calculate widths (normalized)
            width_a = (metric.value_a / max_value) * chart_rect.width()
            width_b = (metric.value_b / max_value) * chart_rect.width()

            # Draw Run A bar (blue)
            painter.fillRect(
                int(chart_rect.left()), int(y_a),
                int(width_a), int(bar_height),
                QColor(100, 149, 237)
            )

            # Draw Run B bar (green/red based on improvement)
            if metric.improved is True:
                bar_b_color = QColor(144, 238, 144)  # Green
            elif metric.improved is False:
                bar_b_color = QColor(255, 99, 71)    # Red
            else:
                bar_b_color = QColor(200, 200, 200)  # Gray

            painter.fillRect(
                int(chart_rect.left()), int(y_b),
                int(width_b), int(bar_height),
                bar_b_color
            )

            # Draw percentage change
            pct = metric.percent_change
            if abs(pct) < 1000:
                pct_text = f"{pct:+.1f}%"
            else:
                pct_text = ">>>"

            if metric.improved is True:
                painter.setPen(QColor(0, 128, 0))
            elif metric.improved is False:
                painter.setPen(QColor(255, 0, 0))
            else:
                painter.setPen(QColor(128, 128, 128))

            painter.drawText(int(chart_rect.right() + 5), int(y_center) + 4, pct_text)

        # Draw legend
        legend_y = 10
        painter.fillRect(margin_left, legend_y, 15, 15, QColor(100, 149, 237))
        painter.setPen(QColor(0, 0, 0))
        painter.drawText(margin_left + 20, legend_y + 12, self.result.run_a_name[:20])

        painter.fillRect(margin_left + 150, legend_y, 15, 15, QColor(144, 238, 144))
        painter.drawText(margin_left + 170, legend_y + 12, self.result.run_b_name[:20])


class ComparisonTable(QTableWidget):
    """Table showing detailed metric comparison."""

    def __init__(self):
        super().__init__()

        self.setColumnCount(5)
        self.setHorizontalHeaderLabels([
            "Metric", "Run A", "Run B", "Difference", "Change %"
        ])

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 5):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)

    def set_result(self, result: ComparisonResult):
        """Update table with comparison result."""
        self.setRowCount(len(result.metrics))

        for row, metric in enumerate(result.metrics):
            self.setItem(row, 0, QTableWidgetItem(metric.name))
            self.setItem(row, 1, QTableWidgetItem(f"{metric.value_a:.2f} {metric.unit}"))
            self.setItem(row, 2, QTableWidgetItem(f"{metric.value_b:.2f} {metric.unit}"))

            diff_item = QTableWidgetItem(f"{metric.difference:+.2f}")
            pct_item = QTableWidgetItem(f"{metric.percent_change:+.1f}%")

            # Color based on improvement
            if metric.improved is True:
                diff_item.setBackground(QColor(200, 255, 200))
                pct_item.setBackground(QColor(200, 255, 200))
            elif metric.improved is False:
                diff_item.setBackground(QColor(255, 200, 200))
                pct_item.setBackground(QColor(255, 200, 200))

            self.setItem(row, 3, diff_item)
            self.setItem(row, 4, pct_item)


class RunSelector(QFrame):
    """Widget for selecting a simulation run."""

    run_selected = Signal(Path)

    def __init__(self, label: str):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.stats: Optional[SimulationStats] = None
        self.run_path: Optional[Path] = None

        layout = QVBoxLayout(self)

        # Header
        header = QHBoxLayout()
        self.label = QLabel(label)
        self.label.setStyleSheet("font-weight: bold;")
        header.addWidget(self.label)

        self.load_btn = QPushButton("Load...")
        self.load_btn.clicked.connect(self._on_load_clicked)
        header.addWidget(self.load_btn)

        layout.addLayout(header)

        # Path display
        self.path_label = QLabel("No run loaded")
        self.path_label.setStyleSheet("color: gray; font-size: 9pt;")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        # Summary metrics
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

    def _on_load_clicked(self):
        """Handle load button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Statistics File",
            str(Path.home()),
            "All files (*);;JSON files (*.json);;Text files (*.txt)"
        )
        if file_path:
            self.load_stats(Path(file_path))

    def load_stats(self, file_path: Path):
        """Load statistics from file."""
        try:
            self.stats = parse_stats_output(file_path)
            self.run_path = file_path
            self.path_label.setText(str(file_path.name))

            # Update summary
            perf = self.stats.performance
            summary = f"""
<b>Cycles:</b> {perf.total_cycles:,}<br>
<b>Stalls:</b> {perf.stall_percentage:.1f}%<br>
"""
            if self.stats.power.total_power > 0:
                summary += f"<b>Power:</b> {self.stats.power.total_power:.2f} mW<br>"

            self.summary.setText(summary)
            self.run_selected.emit(file_path)

        except Exception as e:
            self.path_label.setText(f"Error: {e}")
            self.summary.setText("")


class ComparisonWidget(QWidget):
    """Main comparison widget for comparing two simulation runs."""

    def __init__(self):
        super().__init__()
        self.result: Optional[ComparisonResult] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Simulation Comparison")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(title)

        # Run selectors
        selectors_layout = QHBoxLayout()

        self.run_a_selector = RunSelector("Run A (Baseline)")
        self.run_a_selector.run_selected.connect(self._on_run_selected)
        selectors_layout.addWidget(self.run_a_selector)

        self.run_b_selector = RunSelector("Run B (Comparison)")
        self.run_b_selector.run_selected.connect(self._on_run_selected)
        selectors_layout.addWidget(self.run_b_selector)

        layout.addLayout(selectors_layout)

        # Compare button
        self.compare_btn = QPushButton("Compare Runs")
        self.compare_btn.setEnabled(False)
        self.compare_btn.clicked.connect(self._perform_comparison)
        layout.addWidget(self.compare_btn)

        # Results tabs
        self.results_tabs = QTabWidget()

        # Chart view
        self.chart = ComparisonBarChart()
        self.results_tabs.addTab(self.chart, "Visual Comparison")

        # Table view
        self.table = ComparisonTable()
        self.results_tabs.addTab(self.table, "Detailed Table")

        layout.addWidget(self.results_tabs)

        # Summary panel
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "background: #f0f0f0; padding: 10px; border-radius: 5px;"
        )
        self.summary_label.hide()
        layout.addWidget(self.summary_label)

    def _on_run_selected(self, path: Path):
        """Handle run selection."""
        # Enable compare button if both runs loaded
        self.compare_btn.setEnabled(
            self.run_a_selector.stats is not None and
            self.run_b_selector.stats is not None
        )

    def _perform_comparison(self):
        """Perform comparison between the two runs."""
        stats_a = self.run_a_selector.stats
        stats_b = self.run_b_selector.stats

        if not stats_a or not stats_b:
            return

        # Create comparison result
        name_a = self.run_a_selector.run_path.stem if self.run_a_selector.run_path else "Run A"
        name_b = self.run_b_selector.run_path.stem if self.run_b_selector.run_path else "Run B"

        self.result = ComparisonResult(name_a, name_b)

        # Add performance metrics
        self.result.add_metric(
            "Total Cycles",
            stats_a.performance.total_cycles,
            stats_b.performance.total_cycles,
            "cycles"
        )

        self.result.add_metric(
            "Stall %",
            stats_a.performance.stall_percentage,
            stats_b.performance.stall_percentage,
            "%"
        )

        self.result.add_metric(
            "Load Stalls",
            stats_a.performance.load_stalls,
            stats_b.performance.load_stalls,
            "cycles"
        )

        self.result.add_metric(
            "Store Stalls",
            stats_a.performance.store_stalls,
            stats_b.performance.store_stalls,
            "cycles"
        )

        self.result.add_metric(
            "Compute Stalls",
            stats_a.performance.compute_stalls,
            stats_b.performance.compute_stalls,
            "cycles"
        )

        self.result.add_metric(
            "Nodes Executed",
            stats_a.performance.nodes_executed,
            stats_b.performance.nodes_executed,
            ""
        )

        # Add power metrics
        self.result.add_metric(
            "Total Power",
            stats_a.power.total_power,
            stats_b.power.total_power,
            "mW"
        )

        self.result.add_metric(
            "FU Power",
            stats_a.power.fu_total,
            stats_b.power.fu_total,
            "mW"
        )

        # Add area metrics
        self.result.add_metric(
            "Total Area",
            stats_a.area.total_area,
            stats_b.area.total_area,
            "mm²"
        )

        # Update views
        self.chart.set_result(self.result)
        self.table.set_result(self.result)

        # Generate summary
        self._generate_summary()

    def _generate_summary(self):
        """Generate a text summary of the comparison."""
        if not self.result:
            return

        improved = [m for m in self.result.metrics if m.improved is True]
        regressed = [m for m in self.result.metrics if m.improved is False]

        summary_parts = []

        if improved:
            summary_parts.append(
                f"<b>Improvements:</b> {', '.join(m.name for m in improved[:3])}"
            )

        if regressed:
            summary_parts.append(
                f"<b>Regressions:</b> {', '.join(m.name for m in regressed[:3])}"
            )

        # Overall assessment
        cycle_metric = next((m for m in self.result.metrics if m.name == "Total Cycles"), None)
        if cycle_metric:
            if cycle_metric.percent_change < -5:
                summary_parts.append(
                    f"<span style='color: green;'>Overall: {abs(cycle_metric.percent_change):.1f}% faster</span>"
                )
            elif cycle_metric.percent_change > 5:
                summary_parts.append(
                    f"<span style='color: red;'>Overall: {cycle_metric.percent_change:.1f}% slower</span>"
                )
            else:
                summary_parts.append("Overall: Similar performance")

        if summary_parts:
            self.summary_label.setText("<br>".join(summary_parts))
            self.summary_label.show()
        else:
            self.summary_label.hide()

    def set_runs(self, stats_a: SimulationStats, stats_b: SimulationStats,
                 name_a: str = "Run A", name_b: str = "Run B"):
        """Set both runs programmatically."""
        self.run_a_selector.stats = stats_a
        self.run_a_selector.path_label.setText(name_a)

        self.run_b_selector.stats = stats_b
        self.run_b_selector.path_label.setText(name_b)

        self.compare_btn.setEnabled(True)
        self._perform_comparison()
