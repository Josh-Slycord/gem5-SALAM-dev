# ==============================================================================
# queue_monitor.py - Instruction Queue Visualization
# ==============================================================================
"""Instruction Queue Monitor Widget for gem5-SALAM GUI.

This module provides the QueueMonitor widget, which visualizes instruction
queue depths over time and displays stall analysis. It helps identify
bottlenecks in the accelerator's execution pipeline.

Features:
    - Line chart showing queue depths over simulation cycles
    - Click-to-select specific cycles for detailed inspection
    - Snapshot panel showing queue state at selected cycle
    - Stall breakdown (load, store, compute)
    - Cycle slider for quick navigation

Widget Layout::

    +---------------------------------------------------------------+
    | Queue Monitor                                                  |
    +---------------------------------------------------------------+
    | +-----------------------------------------------+ +---------+ |
    | |  Queue Depth Chart                            | | Cycle:  | |
    | |  ^                                            | | 1,234   | |
    | |  |    /\      /\                              | +---------+ |
    | |  |   /  \  __/  \__                           | |Read:  5 | |
    | |  |  /    \/        \___                       | |Write: 2 | |
    | |  | /                   \                      | |Comp: 10 | |
    | |  +---------------------->                     | +---------+ |
    | |  0              cycles              max       | |Stalls   | |
    | +-----------------------------------------------+ |Load:  3 | |
    | Cycle: [==========|================] [1234]     | |Store: 1 | |
    +-----------------------------------------------+ +---------+ |
    +---------------------------------------------------------------+

Queue Types and Colors:
    | Queue    | Color              | Purpose              |
    |----------|--------------------|--------------------- |
    | Read     | Cornflower Blue    | Memory load ops      |
    | Write    | Tomato Red         | Memory store ops     |
    | Compute  | Light Green        | ALU/FPU operations   |

Data Structures:
    - QueueSnapshot: State of all queues at a specific cycle
    - QueueHistory: Time series of queue snapshots

Signals:
    cycle_clicked(int): Emitted when user clicks on the chart

Example:
    Loading and displaying queue history::

        from salam_gui.widgets.queue_monitor import (
            QueueMonitor, QueueHistory, parse_queue_debug_output
        )

        monitor = QueueMonitor()

        # From debug output file
        with open("m5out/debug.log") as f:
            history = parse_queue_debug_output(f.read())
        monitor.set_history(history)

        # Or programmatically
        history = QueueHistory()
        history.snapshots.append(QueueSnapshot(
            cycle=100, read_queue=5, write_queue=2, compute_queue=10
        ))
        monitor.set_history(history)

Debug Flag:
    Enable RuntimeQueues flag in gem5-SALAM to generate queue data::

        ./gem5.opt --debug-flags=RuntimeQueues configs/...

See Also:
    - stats_dashboard: Overall performance metrics including stall totals
    - execution_timeline: Gantt view of instruction execution
    - fu_utilization: Functional unit bottleneck analysis
"""


__version__ = "3.0.0.pre[1.0.0]"

from typing import Dict, List, Optional
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QGroupBox, QSplitter, QScrollArea,
    QSlider, QSpinBox
)
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PySide6.QtCore import Qt, Signal, QRect


@dataclass
class QueueSnapshot:
    """State of all queues at a specific cycle."""
    cycle: int
    read_queue: int = 0
    write_queue: int = 0
    compute_queue: int = 0
    load_stalls: int = 0
    store_stalls: int = 0
    compute_stalls: int = 0


@dataclass
class QueueHistory:
    """Time series of queue states."""
    snapshots: List[QueueSnapshot] = field(default_factory=list)

    @property
    def max_cycle(self) -> int:
        return max(s.cycle for s in self.snapshots) if self.snapshots else 0

    @property
    def max_queue_depth(self) -> int:
        if not self.snapshots:
            return 1
        return max(
            max(s.read_queue, s.write_queue, s.compute_queue)
            for s in self.snapshots
        ) or 1


class QueueDepthChart(QWidget):
    """Custom widget for drawing queue depth over time."""

    COLORS = {
        'read': QColor(100, 149, 237),    # Cornflower blue
        'write': QColor(255, 99, 71),      # Tomato
        'compute': QColor(144, 238, 144),  # Light green
    }

    cycle_clicked = Signal(int)  # Emitted when user clicks on a cycle

    def __init__(self):
        super().__init__()
        self.history: Optional[QueueHistory] = None
        self.selected_cycle: Optional[int] = None
        self.setMinimumHeight(150)
        self.setMinimumWidth(400)

    def set_history(self, history: QueueHistory):
        """Set the queue history to display."""
        self.history = history
        self.update()

    def set_selected_cycle(self, cycle: int):
        """Highlight a specific cycle."""
        self.selected_cycle = cycle
        self.update()

    def paintEvent(self, event):
        """Draw the queue depth chart."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        margin = 40
        chart_rect = QRect(
            margin, 10,
            rect.width() - margin - 10,
            rect.height() - 30
        )

        # Draw background
        painter.fillRect(rect, QColor(250, 250, 250))
        painter.setPen(QPen(QColor(200, 200, 200)))
        painter.drawRect(chart_rect)

        if not self.history or not self.history.snapshots:
            painter.setPen(QColor(128, 128, 128))
            painter.drawText(chart_rect, Qt.AlignmentFlag.AlignCenter,
                           "No queue data loaded")
            return

        # Calculate scales
        max_cycle = self.history.max_cycle
        max_depth = self.history.max_queue_depth
        x_scale = chart_rect.width() / max(max_cycle, 1)
        y_scale = chart_rect.height() / max(max_depth, 1)

        # Draw grid lines
        painter.setPen(QPen(QColor(230, 230, 230)))
        for i in range(5):
            y = chart_rect.top() + i * chart_rect.height() // 4
            painter.drawLine(chart_rect.left(), y, chart_rect.right(), y)

        # Draw Y axis labels
        painter.setPen(QColor(100, 100, 100))
        painter.setFont(QFont("Arial", 8))
        for i in range(5):
            y = chart_rect.top() + i * chart_rect.height() // 4
            value = int(max_depth * (4 - i) / 4)
            painter.drawText(5, y + 4, str(value))

        # Draw queue lines
        for queue_type, color in self.COLORS.items():
            painter.setPen(QPen(color, 2))

            prev_point = None
            for snapshot in self.history.snapshots:
                x = chart_rect.left() + int(snapshot.cycle * x_scale)

                if queue_type == 'read':
                    depth = snapshot.read_queue
                elif queue_type == 'write':
                    depth = snapshot.write_queue
                else:
                    depth = snapshot.compute_queue

                y = chart_rect.bottom() - int(depth * y_scale)

                if prev_point:
                    painter.drawLine(prev_point[0], prev_point[1], x, y)
                prev_point = (x, y)

        # Draw selected cycle marker
        if self.selected_cycle is not None:
            x = chart_rect.left() + int(self.selected_cycle * x_scale)
            painter.setPen(QPen(QColor(255, 0, 0), 1, Qt.PenStyle.DashLine))
            painter.drawLine(x, chart_rect.top(), x, chart_rect.bottom())

        # Draw legend
        legend_x = chart_rect.right() - 100
        legend_y = chart_rect.top() + 10
        for i, (queue_type, color) in enumerate(self.COLORS.items()):
            painter.setPen(QPen(color, 2))
            painter.drawLine(legend_x, legend_y + i * 15,
                           legend_x + 20, legend_y + i * 15)
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(legend_x + 25, legend_y + i * 15 + 4,
                           queue_type.capitalize())

    def mousePressEvent(self, event):
        """Handle click to select cycle."""
        if not self.history or not self.history.snapshots:
            return

        margin = 40
        chart_width = self.width() - margin - 10
        max_cycle = self.history.max_cycle

        x = event.pos().x() - margin
        if 0 <= x <= chart_width:
            cycle = int(x / chart_width * max_cycle)
            self.cycle_clicked.emit(cycle)


class QueueSnapshotPanel(QFrame):
    """Panel showing queue state at a specific cycle."""

    def __init__(self):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.title = QLabel("Cycle: -")
        self.title.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(self.title)

        # Queue depths
        grid = QGridLayout()

        self.read_label = QLabel("Read Queue: -")
        self.write_label = QLabel("Write Queue: -")
        self.compute_label = QLabel("Compute Queue: -")

        grid.addWidget(QLabel("Read Queue:"), 0, 0)
        grid.addWidget(self.read_label, 0, 1)
        grid.addWidget(QLabel("Write Queue:"), 1, 0)
        grid.addWidget(self.write_label, 1, 1)
        grid.addWidget(QLabel("Compute Queue:"), 2, 0)
        grid.addWidget(self.compute_label, 2, 1)

        layout.addLayout(grid)

        # Stall info
        stall_group = QGroupBox("Stalls")
        stall_layout = QGridLayout(stall_group)

        self.load_stall_label = QLabel("-")
        self.store_stall_label = QLabel("-")
        self.compute_stall_label = QLabel("-")

        stall_layout.addWidget(QLabel("Load:"), 0, 0)
        stall_layout.addWidget(self.load_stall_label, 0, 1)
        stall_layout.addWidget(QLabel("Store:"), 1, 0)
        stall_layout.addWidget(self.store_stall_label, 1, 1)
        stall_layout.addWidget(QLabel("Compute:"), 2, 0)
        stall_layout.addWidget(self.compute_stall_label, 2, 1)

        layout.addWidget(stall_group)
        layout.addStretch()

    def set_snapshot(self, snapshot: Optional[QueueSnapshot]):
        """Update display with snapshot data."""
        if snapshot is None:
            self.title.setText("Cycle: -")
            self.read_label.setText("-")
            self.write_label.setText("-")
            self.compute_label.setText("-")
            self.load_stall_label.setText("-")
            self.store_stall_label.setText("-")
            self.compute_stall_label.setText("-")
            return

        self.title.setText(f"Cycle: {snapshot.cycle:,}")
        self.read_label.setText(str(snapshot.read_queue))
        self.write_label.setText(str(snapshot.write_queue))
        self.compute_label.setText(str(snapshot.compute_queue))
        self.load_stall_label.setText(str(snapshot.load_stalls))
        self.store_stall_label.setText(str(snapshot.store_stalls))
        self.compute_stall_label.setText(str(snapshot.compute_stalls))


class QueueMonitor(QWidget):
    """Main queue monitoring widget."""

    def __init__(self):
        super().__init__()
        self.history: Optional[QueueHistory] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Queue Monitor")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(title)

        # Main content
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Chart on left
        chart_container = QWidget()
        chart_layout = QVBoxLayout(chart_container)
        chart_layout.setContentsMargins(0, 0, 0, 0)

        self.chart = QueueDepthChart()
        self.chart.cycle_clicked.connect(self._on_cycle_selected)
        chart_layout.addWidget(self.chart)

        # Cycle slider
        slider_layout = QHBoxLayout()
        slider_layout.addWidget(QLabel("Cycle:"))
        self.cycle_slider = QSlider(Qt.Orientation.Horizontal)
        self.cycle_slider.setMinimum(0)
        self.cycle_slider.setMaximum(100)
        self.cycle_slider.valueChanged.connect(self._on_slider_changed)
        slider_layout.addWidget(self.cycle_slider)
        self.cycle_spinbox = QSpinBox()
        self.cycle_spinbox.setMinimum(0)
        self.cycle_spinbox.setMaximum(100)
        self.cycle_spinbox.valueChanged.connect(self._on_spinbox_changed)
        slider_layout.addWidget(self.cycle_spinbox)
        chart_layout.addLayout(slider_layout)

        splitter.addWidget(chart_container)

        # Snapshot panel on right
        self.snapshot_panel = QueueSnapshotPanel()
        self.snapshot_panel.setMaximumWidth(200)
        splitter.addWidget(self.snapshot_panel)

        splitter.setSizes([600, 200])
        layout.addWidget(splitter)

    def set_history(self, history: QueueHistory):
        """Load queue history data."""
        self.history = history
        self.chart.set_history(history)

        max_cycle = history.max_cycle
        self.cycle_slider.setMaximum(max_cycle)
        self.cycle_spinbox.setMaximum(max_cycle)

        if history.snapshots:
            self._select_cycle(0)

    def _on_cycle_selected(self, cycle: int):
        """Handle cycle selection from chart."""
        self._select_cycle(cycle)

    def _on_slider_changed(self, value: int):
        """Handle slider change."""
        self.cycle_spinbox.blockSignals(True)
        self.cycle_spinbox.setValue(value)
        self.cycle_spinbox.blockSignals(False)
        self._select_cycle(value)

    def _on_spinbox_changed(self, value: int):
        """Handle spinbox change."""
        self.cycle_slider.blockSignals(True)
        self.cycle_slider.setValue(value)
        self.cycle_slider.blockSignals(False)
        self._select_cycle(value)

    def _select_cycle(self, cycle: int):
        """Select and display a specific cycle."""
        self.chart.set_selected_cycle(cycle)

        if self.history and self.history.snapshots:
            # Find nearest snapshot
            nearest = min(self.history.snapshots,
                         key=lambda s: abs(s.cycle - cycle))
            self.snapshot_panel.set_snapshot(nearest)


def parse_queue_debug_output(content: str) -> QueueHistory:
    """
    Parse RuntimeQueues debug output into QueueHistory.

    Expected format (from gem5 debug output):
    cycle: 1234 read: 5 write: 2 compute: 10 ...
    """
    import re

    history = QueueHistory()

    # Pattern for queue state lines
    pattern = re.compile(
        r'cycle[:\s]+(\d+).*?'
        r'read[:\s]+(\d+).*?'
        r'write[:\s]+(\d+).*?'
        r'compute[:\s]+(\d+)',
        re.IGNORECASE
    )

    for match in pattern.finditer(content):
        snapshot = QueueSnapshot(
            cycle=int(match.group(1)),
            read_queue=int(match.group(2)),
            write_queue=int(match.group(3)),
            compute_queue=int(match.group(4))
        )
        history.snapshots.append(snapshot)

    # Sort by cycle
    history.snapshots.sort(key=lambda s: s.cycle)

    return history
