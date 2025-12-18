# ==============================================================================
# execution_timeline.py - Gantt-Style Execution Timeline
# ==============================================================================
"""Gantt-Style Execution Timeline Widget for gem5-SALAM GUI.

This module provides the ExecutionTimeline widget, which visualizes instruction
execution as horizontal bars over time, showing issue/complete cycles, stall
periods, and dependency relationships. Essential for understanding pipeline
behavior and identifying performance bottlenecks.

Features:
    - Horizontal bars showing instruction execution duration
    - Stall cycle highlighting with orange overlay
    - Dependency arrows between instructions (optional)
    - Click-to-select with detailed instruction info
    - Zoom and pan controls
    - Filter by instruction type

Widget Layout::

    +------------------------------------------------------------------+
    | Execution Timeline                                                |
    +------------------------------------------------------------------+
    | Zoom: [=====|===] Filter: [All v] [x] Show Dependencies          |
    +------------------------------------------------------------------+
    | 0        100       200       300       400       500 (cycles)    |
    | |---------|---------|---------|---------|---------|              |
    +------------------------------------------------------------------+
    | Opcode  |                                                        |
    |---------|--------------------------------------------------------|
    | load    |▓▓▓▓▓▓▓▓▓▓░░░▓▓▓▓|                                     |
    | fmul    |          ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓|                            |
    | fadd    |                    ▓▓▓▓▓▓▓▓|                           |
    | store   |                           ▓▓▓▓▓▓░░▓▓|                  |
    | br      |                                     ▓▓|                |
    +------------------------------------------------------------------+
    | [▓ Memory] [▓ Compute] [▓ Control] [░ Stall]                     |
    +------------------------------------------------------------------+
    | Instructions: 245 | Cycles: 520 | Total Stalls: 45 cycles        |
    +------------------------------------------------------------------+

Legend:
    ▓▓▓▓ - Active execution
    ░░░░ - Stall cycles (orange overlay)
    ──── - Dependency arrow (when enabled)

Instruction Type Colors:
    | Opcode Pattern | Color              | Type       |
    |----------------|--------------------|------------|
    | load           | Cornflower Blue    | Memory     |
    | store          | Tomato Red         | Memory     |
    | add, sub       | Light Green        | Compute    |
    | mul            | Peach              | Compute    |
    | div            | Light Pink         | Compute    |
    | fadd, fmul     | Sky Blue           | FP Compute |
    | phi            | Plum               | SSA        |
    | br             | Light Yellow       | Control    |
    | call, ret      | Light Salmon       | Control    |
    | gep            | Rosy Brown         | Address    |

Data Structures:
    - InstructionExecution: Execution record for one instruction
    - ExecutionTrace: Complete trace of all instructions
    - InstructionState: Enum for instruction states

Example:
    Loading and displaying execution trace::

        from salam_gui.widgets.execution_timeline import (
            ExecutionTimeline, ExecutionTrace, parse_execution_trace
        )

        timeline = ExecutionTimeline()

        # From debug output
        with open("m5out/debug.log") as f:
            trace = parse_execution_trace(f.read())
        timeline.set_trace(trace)

        # Programmatic construction
        trace = ExecutionTrace()
        trace.instructions.append(InstructionExecution(
            uid=1,
            opcode="fmul",
            issue_cycle=100,
            complete_cycle=110,
            stall_cycles=[103, 104]
        ))
        timeline.set_trace(trace)

Debug Flag:
    Enable Runtime flag for execution events::

        ./gem5.opt --debug-flags=Runtime configs/...

See Also:
    - queue_monitor: Queue depth visualization
    - fu_utilization: Functional unit usage
    - cdfg_viewer: Static instruction graph
"""


__version__ = "3.0.0.pre[1.0.0]"

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QSlider, QComboBox, QCheckBox, QSplitter,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsLineItem, QGraphicsTextItem, QGraphicsItem
)
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QWheelEvent,
    QMouseEvent, QPolygonF
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal


class InstructionState(Enum):
    """Possible states for an instruction."""
    WAITING = "waiting"
    EXECUTING = "executing"
    STALLED = "stalled"
    COMPLETED = "completed"


@dataclass
class InstructionExecution:
    """Execution record for a single instruction."""
    uid: int
    opcode: str
    issue_cycle: int
    complete_cycle: int
    fu_type: str = ""
    basic_block: str = ""
    function: str = ""
    stall_cycles: List[int] = field(default_factory=list)
    dependencies: List[int] = field(default_factory=list)  # UIDs of dependent instructions


@dataclass
class ExecutionTrace:
    """Complete execution trace."""
    instructions: List[InstructionExecution] = field(default_factory=list)

    @property
    def max_cycle(self) -> int:
        if not self.instructions:
            return 0
        return max(i.complete_cycle for i in self.instructions)

    @property
    def min_cycle(self) -> int:
        if not self.instructions:
            return 0
        return min(i.issue_cycle for i in self.instructions)


# Colors for different instruction types
INSTRUCTION_TYPE_COLORS = {
    'load': QColor(100, 149, 237),      # Blue
    'store': QColor(255, 99, 71),       # Red
    'add': QColor(144, 238, 144),       # Light green
    'sub': QColor(152, 251, 152),       # Pale green
    'mul': QColor(255, 218, 185),       # Peach
    'div': QColor(255, 182, 193),       # Light pink
    'fadd': QColor(135, 206, 235),      # Sky blue
    'fmul': QColor(176, 224, 230),      # Powder blue
    'phi': QColor(221, 160, 221),       # Plum
    'br': QColor(255, 255, 224),        # Light yellow
    'call': QColor(255, 160, 122),      # Light salmon
    'ret': QColor(250, 250, 210),       # Light goldenrod
    'gep': QColor(188, 143, 143),       # Rosy brown
    'default': QColor(200, 200, 200),   # Gray
}

STALL_COLOR = QColor(255, 165, 0, 150)  # Orange with transparency
CRITICAL_PATH_COLOR = QColor(255, 0, 0)  # Red for critical path


def get_instruction_color(opcode: str) -> QColor:
    """Get color based on instruction opcode."""
    opcode_lower = opcode.lower()
    for key, color in INSTRUCTION_TYPE_COLORS.items():
        if key in opcode_lower:
            return color
    return INSTRUCTION_TYPE_COLORS['default']


class TimelineBar(QGraphicsRectItem):
    """Graphics item representing an instruction execution bar."""

    def __init__(self, instruction: InstructionExecution, y_pos: float,
                 pixels_per_cycle: float, bar_height: float):
        super().__init__()
        self.instruction = instruction
        self.bar_height = bar_height

        # Calculate bar dimensions
        duration = instruction.complete_cycle - instruction.issue_cycle
        x = instruction.issue_cycle * pixels_per_cycle
        width = max(duration * pixels_per_cycle, 2)

        self.setRect(x, y_pos, width, bar_height)

        # Set color based on opcode
        color = get_instruction_color(instruction.opcode)
        self.setBrush(QBrush(color))
        self.setPen(QPen(color.darker(130), 1))

        # Make interactive
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

        # Store stall overlay rects
        self.stall_overlays: List[QGraphicsRectItem] = []

    def add_stall_overlays(self, scene: QGraphicsScene, pixels_per_cycle: float):
        """Add overlay rectangles for stall cycles."""
        for stall_cycle in self.instruction.stall_cycles:
            x = stall_cycle * pixels_per_cycle
            rect = QGraphicsRectItem(x, self.rect().y(), pixels_per_cycle, self.bar_height)
            rect.setBrush(QBrush(STALL_COLOR))
            rect.setPen(QPen(Qt.PenStyle.NoPen))
            rect.setZValue(1)  # Draw above the main bar
            scene.addItem(rect)
            self.stall_overlays.append(rect)

    def hoverEnterEvent(self, event):
        self.setPen(QPen(Qt.GlobalColor.blue, 2))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.isSelected():
            color = get_instruction_color(self.instruction.opcode)
            self.setPen(QPen(color.darker(130), 1))
        super().hoverLeaveEvent(event)


class TimelineGraphicsView(QGraphicsView):
    """Custom graphics view for the timeline with zoom and pan."""

    instruction_clicked = Signal(int)  # Emits instruction UID
    cycle_clicked = Signal(int)  # Emits cycle number

    def __init__(self, scene: QGraphicsScene):
        super().__init__(scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        # Zoom settings
        self.zoom_factor = 1.2
        self.min_zoom = 0.1
        self.max_zoom = 20.0
        self.current_zoom = 1.0

    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel for zooming."""
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            # Ctrl+wheel = zoom
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
        else:
            # Regular wheel = scroll
            super().wheelEvent(event)

    def zoom_in(self):
        if self.current_zoom < self.max_zoom:
            self.scale(self.zoom_factor, 1.0)  # Only scale horizontally
            self.current_zoom *= self.zoom_factor

    def zoom_out(self):
        if self.current_zoom > self.min_zoom:
            factor = 1.0 / self.zoom_factor
            self.scale(factor, 1.0)
            self.current_zoom *= factor

    def mousePressEvent(self, event: QMouseEvent):
        item = self.itemAt(event.pos())
        if isinstance(item, TimelineBar):
            self.instruction_clicked.emit(item.instruction.uid)
        else:
            # Calculate cycle from click position
            scene_pos = self.mapToScene(event.pos())
            # This would need pixels_per_cycle passed in
        super().mousePressEvent(event)


class InstructionDetailsPanel(QFrame):
    """Panel showing details of selected instruction."""

    def __init__(self):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(220)

        layout = QVBoxLayout(self)

        self.title = QLabel("Instruction Details")
        self.title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        layout.addWidget(self.title)

        self.details = QLabel("Click an instruction bar to see details")
        self.details.setWordWrap(True)
        layout.addWidget(self.details)

        layout.addStretch()

    def set_instruction(self, instr: Optional[InstructionExecution]):
        """Update panel with instruction information."""
        if instr is None:
            self.details.setText("Click an instruction bar to see details")
            return

        duration = instr.complete_cycle - instr.issue_cycle
        stall_count = len(instr.stall_cycles)

        details = f"""
<b>Opcode:</b> {instr.opcode}<br>
<b>UID:</b> {instr.uid}<br>
<b>Issue Cycle:</b> {instr.issue_cycle}<br>
<b>Complete Cycle:</b> {instr.complete_cycle}<br>
<b>Duration:</b> {duration} cycles<br>
<b>Stalls:</b> {stall_count} cycles<br>
<b>FU Type:</b> {instr.fu_type or 'N/A'}<br>
"""
        if instr.basic_block:
            details += f"<b>Basic Block:</b> {instr.basic_block}<br>"
        if instr.function:
            details += f"<b>Function:</b> {instr.function}<br>"
        if instr.dependencies:
            deps = ", ".join(str(d) for d in instr.dependencies[:5])
            if len(instr.dependencies) > 5:
                deps += f"... (+{len(instr.dependencies)-5} more)"
            details += f"<b>Depends on:</b> {deps}<br>"

        self.details.setText(details)


class CycleRuler(QWidget):
    """Ruler showing cycle numbers above the timeline."""

    def __init__(self):
        super().__init__()
        self.min_cycle = 0
        self.max_cycle = 100
        self.pixels_per_cycle = 5.0
        self.offset = 0
        self.setFixedHeight(25)

    def set_range(self, min_cycle: int, max_cycle: int, ppc: float):
        self.min_cycle = min_cycle
        self.max_cycle = max_cycle
        self.pixels_per_cycle = ppc
        self.update()

    def set_offset(self, offset: float):
        self.offset = offset
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), QColor(240, 240, 240))
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.setFont(QFont("Arial", 8))

        # Draw tick marks and labels
        step = max(1, int(50 / self.pixels_per_cycle))  # Tick every ~50 pixels

        for cycle in range(self.min_cycle, self.max_cycle + 1, step):
            x = int((cycle - self.min_cycle) * self.pixels_per_cycle - self.offset)
            if 0 <= x <= self.width():
                painter.drawLine(x, 15, x, 25)
                painter.drawText(x - 20, 12, str(cycle))


class ExecutionTimeline(QWidget):
    """Main execution timeline widget."""

    def __init__(self):
        super().__init__()
        self.trace: Optional[ExecutionTrace] = None
        self.instruction_bars: Dict[int, TimelineBar] = {}
        self.pixels_per_cycle = 5.0
        self.bar_height = 20
        self.bar_spacing = 5

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Title and controls
        header_layout = QHBoxLayout()

        title = QLabel("Execution Timeline")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Zoom controls
        header_layout.addWidget(QLabel("Zoom:"))
        zoom_slider = QSlider(Qt.Orientation.Horizontal)
        zoom_slider.setMinimum(1)
        zoom_slider.setMaximum(100)
        zoom_slider.setValue(20)
        zoom_slider.setFixedWidth(100)
        zoom_slider.valueChanged.connect(self._on_zoom_changed)
        header_layout.addWidget(zoom_slider)

        # Filter by type
        header_layout.addWidget(QLabel("Filter:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Memory", "Compute", "Control"])
        self.filter_combo.currentTextChanged.connect(self._on_filter_changed)
        header_layout.addWidget(self.filter_combo)

        # Show dependencies
        self.show_deps_check = QCheckBox("Show Dependencies")
        self.show_deps_check.stateChanged.connect(self._on_show_deps_changed)
        header_layout.addWidget(self.show_deps_check)

        layout.addLayout(header_layout)

        # Cycle ruler
        self.ruler = CycleRuler()
        layout.addWidget(self.ruler)

        # Main content splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Timeline view
        self.scene = QGraphicsScene()
        self.view = TimelineGraphicsView(self.scene)
        self.view.instruction_clicked.connect(self._on_instruction_clicked)
        splitter.addWidget(self.view)

        # Details panel
        self.details_panel = InstructionDetailsPanel()
        splitter.addWidget(self.details_panel)

        splitter.setSizes([700, 250])
        layout.addWidget(splitter)

        # Legend
        legend_layout = QHBoxLayout()
        self._add_legend_item(legend_layout, "Memory", INSTRUCTION_TYPE_COLORS['load'])
        self._add_legend_item(legend_layout, "Compute", INSTRUCTION_TYPE_COLORS['add'])
        self._add_legend_item(legend_layout, "Control", INSTRUCTION_TYPE_COLORS['br'])
        self._add_legend_item(legend_layout, "Stall", STALL_COLOR)
        legend_layout.addStretch()
        layout.addLayout(legend_layout)

        # Stats bar
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(self.stats_label)

    def _add_legend_item(self, layout: QHBoxLayout, label: str, color: QColor):
        """Add a legend item."""
        color_box = QLabel()
        color_box.setFixedSize(15, 15)
        color_box.setStyleSheet(f"background-color: {color.name()}; border: 1px solid gray;")
        layout.addWidget(color_box)
        layout.addWidget(QLabel(label))
        layout.addSpacing(15)

    def set_trace(self, trace: ExecutionTrace):
        """Load and display execution trace."""
        self.trace = trace
        self._build_timeline()

    def _build_timeline(self):
        """Build the timeline visualization."""
        self.scene.clear()
        self.instruction_bars.clear()

        if not self.trace or not self.trace.instructions:
            text = self.scene.addText("No execution trace loaded")
            text.setDefaultTextColor(QColor(128, 128, 128))
            return

        min_cycle = self.trace.min_cycle
        max_cycle = self.trace.max_cycle

        # Update ruler
        self.ruler.set_range(min_cycle, max_cycle, self.pixels_per_cycle)

        # Sort instructions by issue cycle
        sorted_instructions = sorted(self.trace.instructions, key=lambda x: x.issue_cycle)

        # Draw instruction bars
        for i, instr in enumerate(sorted_instructions):
            y_pos = i * (self.bar_height + self.bar_spacing)

            bar = TimelineBar(instr, y_pos, self.pixels_per_cycle, self.bar_height)
            self.scene.addItem(bar)
            bar.add_stall_overlays(self.scene, self.pixels_per_cycle)
            self.instruction_bars[instr.uid] = bar

            # Add label on left side
            label = QGraphicsTextItem(f"{instr.opcode[:8]}")
            label.setFont(QFont("Arial", 7))
            label.setPos(-60, y_pos)
            self.scene.addItem(label)

        # Draw time grid
        self._draw_grid(min_cycle, max_cycle, len(sorted_instructions))

        # Update stats
        total_cycles = max_cycle - min_cycle
        total_stalls = sum(len(i.stall_cycles) for i in self.trace.instructions)
        self.stats_label.setText(
            f"Instructions: {len(self.trace.instructions)} | "
            f"Cycles: {total_cycles} | "
            f"Total Stalls: {total_stalls} cycles"
        )

        # Fit view
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-70, -10, 10, 10))

    def _draw_grid(self, min_cycle: int, max_cycle: int, num_rows: int):
        """Draw vertical grid lines for cycle markers."""
        step = max(1, int(100 / self.pixels_per_cycle))
        pen = QPen(QColor(220, 220, 220), 1, Qt.PenStyle.DotLine)

        total_height = num_rows * (self.bar_height + self.bar_spacing)

        for cycle in range(min_cycle, max_cycle + 1, step):
            x = (cycle - min_cycle) * self.pixels_per_cycle
            line = self.scene.addLine(x, -5, x, total_height, pen)
            line.setZValue(-1)

    def _on_zoom_changed(self, value: int):
        """Handle zoom slider change."""
        self.pixels_per_cycle = value / 4.0
        self._build_timeline()

    def _on_filter_changed(self, filter_text: str):
        """Handle filter combo change."""
        # TODO: Implement filtering
        pass

    def _on_show_deps_changed(self, state: int):
        """Toggle dependency arrows."""
        if state == Qt.CheckState.Checked.value:
            self._draw_dependencies()
        else:
            self._build_timeline()  # Rebuild without deps

    def _draw_dependencies(self):
        """Draw arrows for instruction dependencies."""
        if not self.trace:
            return

        pen = QPen(QColor(150, 150, 150, 100), 1)

        for instr in self.trace.instructions:
            if instr.uid not in self.instruction_bars:
                continue

            target_bar = self.instruction_bars[instr.uid]
            target_rect = target_bar.rect()

            for dep_uid in instr.dependencies:
                if dep_uid in self.instruction_bars:
                    source_bar = self.instruction_bars[dep_uid]
                    source_rect = source_bar.rect()

                    # Draw line from source end to target start
                    line = self.scene.addLine(
                        source_rect.right(), source_rect.center().y(),
                        target_rect.left(), target_rect.center().y(),
                        pen
                    )
                    line.setZValue(-0.5)

    def _on_instruction_clicked(self, uid: int):
        """Handle instruction click."""
        if not self.trace:
            return

        # Find instruction by UID
        for instr in self.trace.instructions:
            if instr.uid == uid:
                self.details_panel.set_instruction(instr)

                # Highlight the bar
                for bar_uid, bar in self.instruction_bars.items():
                    if bar_uid == uid:
                        bar.setPen(QPen(Qt.GlobalColor.blue, 3))
                        bar.setSelected(True)
                    else:
                        color = get_instruction_color(bar.instruction.opcode)
                        bar.setPen(QPen(color.darker(130), 1))
                        bar.setSelected(False)
                break


def parse_execution_trace(content: str) -> ExecutionTrace:
    """
    Parse execution trace from gem5-SALAM output.

    Looks for patterns like:
    [Cycle 100] Issue: UID=42 OP=fmul
    [Cycle 103] Complete: UID=42
    """
    import re

    trace = ExecutionTrace()

    # Track instruction state
    instructions: Dict[int, InstructionExecution] = {}

    # Pattern for issue events
    issue_pattern = re.compile(
        r'\[?(?:Cycle|cycle)[:\s]+(\d+)\]?\s*'
        r'(?:Issue|ISSUE)[:\s]+(?:UID[=:\s]+)?(\d+)\s*'
        r'(?:OP[=:\s]+)?(\w+)?',
        re.IGNORECASE
    )

    # Pattern for complete events
    complete_pattern = re.compile(
        r'\[?(?:Cycle|cycle)[:\s]+(\d+)\]?\s*'
        r'(?:Complete|COMPLETE|Done)[:\s]+(?:UID[=:\s]+)?(\d+)',
        re.IGNORECASE
    )

    # Pattern for stall events
    stall_pattern = re.compile(
        r'\[?(?:Cycle|cycle)[:\s]+(\d+)\]?\s*'
        r'(?:Stall|STALL)[:\s]+(?:UID[=:\s]+)?(\d+)',
        re.IGNORECASE
    )

    for match in issue_pattern.finditer(content):
        cycle = int(match.group(1))
        uid = int(match.group(2))
        opcode = match.group(3) or "unknown"

        instructions[uid] = InstructionExecution(
            uid=uid,
            opcode=opcode,
            issue_cycle=cycle,
            complete_cycle=cycle  # Will be updated
        )

    for match in complete_pattern.finditer(content):
        cycle = int(match.group(1))
        uid = int(match.group(2))

        if uid in instructions:
            instructions[uid].complete_cycle = cycle

    for match in stall_pattern.finditer(content):
        cycle = int(match.group(1))
        uid = int(match.group(2))

        if uid in instructions:
            instructions[uid].stall_cycles.append(cycle)

    trace.instructions = list(instructions.values())
    return trace
