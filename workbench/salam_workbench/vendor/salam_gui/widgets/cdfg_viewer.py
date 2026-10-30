# ==============================================================================
# cdfg_viewer.py - CDFG Visualization Widget
# ==============================================================================
"""Interactive CDFG (Control Data Flow Graph) Viewer Widget.

This module provides the CDFGViewer widget, which renders and allows
interactive exploration of Control Data Flow Graphs exported from
gem5-SALAM accelerator simulations.

Features:
    - Interactive pan and zoom (mouse wheel, drag)
    - Click-to-select nodes with details panel
    - Color-coded instruction types
    - Edge type visualization (data, control, sequence)
    - Auto-layout using NetworkX algorithms

Widget Architecture::

    CDFGViewer
    +-- CDFGGraphicsView (left, 75%)
    |   +-- QGraphicsScene
    |       +-- InstructionNodeItem (per instruction)
    |       +-- Edge lines with arrowheads
    +-- NodeDetailsPanel (right, 25%)
        +-- Instruction details display

Node Color Legend:
    | Color       | Instruction Type |
    |-------------|------------------|
    | Light Blue  | Memory ops       |
    | Light Green | Compute ops      |
    | Light Yellow| Control ops      |
    | Light Pink  | Phi nodes        |
    | Light Salmon| Call instructions|

Edge Types:
    | Style   | Color | Type     |
    |---------|-------|----------|
    | Solid   | Blue  | Data     |
    | Dashed  | Red   | Control  |
    | Dotted  | Gray  | Sequence |

Example:
    Loading and displaying a CDFG::

        from salam_gui.widgets.cdfg_viewer import CDFGViewer
        from salam_gui.data.dot_parser import parse_cdfg_dot

        viewer = CDFGViewer()
        graph = parse_cdfg_dot(Path("m5out/cdfg.dot"))
        viewer.set_graph(graph)

See Also:
    - dot_parser: Parses CDFG DOT files into CDFGGraph structures
    - MainWindow: Hosts this widget as the central widget
"""


__version__ = "3.0.0.pre[1.0.0]"

from typing import Dict, Optional, Tuple
import math

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsTextItem,
    QGraphicsRectItem, QFrame, QScrollArea
)
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont,
    QWheelEvent, QMouseEvent, QTransform
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal

from ..data.dot_parser import CDFGGraph, InstructionNode, get_node_positions


# Color mapping for instruction types
INSTRUCTION_COLORS = {
    'lightblue': QColor(173, 216, 230),    # Memory ops
    'lightgreen': QColor(144, 238, 144),   # Compute ops
    'lightyellow': QColor(255, 255, 224),  # Control ops
    'lightpink': QColor(255, 182, 193),    # Phi nodes
    'lightsalmon': QColor(255, 160, 122),  # Call instructions
    'white': QColor(255, 255, 255),        # Default
}

EDGE_COLORS = {
    'data': QColor(0, 0, 255),       # Blue
    'control': QColor(255, 0, 0),    # Red
    'sequence': QColor(128, 128, 128),  # Gray
}


class InstructionNodeItem(QGraphicsRectItem):
    """Graphics item representing an instruction node."""

    def __init__(self, node: InstructionNode, x: float, y: float, parent=None):
        super().__init__(parent)
        self.node = node
        self.selected = False

        # Node dimensions
        self.width = 80
        self.height = 50

        self.setRect(x - self.width/2, y - self.height/2, self.width, self.height)

        # Set appearance
        color = INSTRUCTION_COLORS.get(node.color, INSTRUCTION_COLORS['white'])
        self.setBrush(QBrush(color))
        self.setPen(QPen(Qt.GlobalColor.black, 1))

        # Make interactive
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

        # Add text label
        self.label = QGraphicsTextItem(self)
        self.label.setPlainText(f"{node.opcode}\n{node.uid}")
        self.label.setFont(QFont("Courier", 8))
        self.label.setPos(x - self.width/2 + 5, y - self.height/2 + 5)

    def hoverEnterEvent(self, event):
        self.setPen(QPen(Qt.GlobalColor.blue, 2))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.selected:
            self.setPen(QPen(Qt.GlobalColor.black, 1))
        super().hoverLeaveEvent(event)

    @property
    def center(self) -> QPointF:
        rect = self.rect()
        return QPointF(rect.x() + rect.width()/2, rect.y() + rect.height()/2)


class CDFGGraphicsView(QGraphicsView):
    """Custom graphics view with pan and zoom support."""

    node_clicked = Signal(int)  # Emits node UID

    def __init__(self, scene: QGraphicsScene):
        super().__init__(scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        # Zoom settings
        self.zoom_factor = 1.15
        self.min_zoom = 0.1
        self.max_zoom = 10.0
        self.current_zoom = 1.0

    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel for zooming."""
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def zoom_in(self):
        """Zoom in by factor."""
        if self.current_zoom < self.max_zoom:
            self.scale(self.zoom_factor, self.zoom_factor)
            self.current_zoom *= self.zoom_factor

    def zoom_out(self):
        """Zoom out by factor."""
        if self.current_zoom > self.min_zoom:
            factor = 1.0 / self.zoom_factor
            self.scale(factor, factor)
            self.current_zoom *= factor

    def fit_to_view(self):
        """Fit entire graph in view."""
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.current_zoom = 1.0

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse clicks on nodes."""
        item = self.itemAt(event.pos())
        if isinstance(item, InstructionNodeItem):
            self.node_clicked.emit(item.node.uid)
        super().mousePressEvent(event)


class NodeDetailsPanel(QFrame):
    """Panel showing details of selected node."""

    def __init__(self):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(200)

        layout = QVBoxLayout(self)

        self.title = QLabel("Node Details")
        self.title.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(self.title)

        self.details = QLabel("Click a node to see details")
        self.details.setWordWrap(True)
        layout.addWidget(self.details)

        layout.addStretch()

    def set_node(self, node: Optional[InstructionNode]):
        """Update panel with node information."""
        if node is None:
            self.details.setText("Click a node to see details")
            return

        details = f"""
<b>Instruction:</b> {node.opcode}<br>
<b>UID:</b> {node.uid}<br>
<b>Cycles:</b> {node.cycles}<br>
<b>Type:</b> {self._get_type_name(node.color)}<br>
"""
        if node.basic_block:
            details += f"<b>Basic Block:</b> {node.basic_block}<br>"
        if node.function:
            details += f"<b>Function:</b> {node.function}<br>"

        self.details.setText(details)

    def _get_type_name(self, color: str) -> str:
        """Map color to instruction type name."""
        mapping = {
            'lightblue': 'Memory',
            'lightgreen': 'Compute',
            'lightyellow': 'Control',
            'lightpink': 'Phi',
            'lightsalmon': 'Call',
        }
        return mapping.get(color, 'Unknown')


class CDFGViewer(QWidget):
    """Main CDFG viewer widget combining graph view and details panel."""

    def __init__(self):
        super().__init__()
        self.graph: Optional[CDFGGraph] = None
        self.node_items: Dict[int, InstructionNodeItem] = {}

        self._setup_ui()

    def _setup_ui(self):
        """Set up the viewer UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Graphics scene and view
        self.scene = QGraphicsScene()
        self.view = CDFGGraphicsView(self.scene)
        self.view.node_clicked.connect(self._on_node_clicked)

        # Details panel
        self.details_panel = NodeDetailsPanel()

        layout.addWidget(self.view, stretch=3)
        layout.addWidget(self.details_panel, stretch=1)

        # Show placeholder
        self._show_placeholder()

    def _show_placeholder(self):
        """Show placeholder when no graph is loaded."""
        text = self.scene.addText("Load a CDFG file to visualize")
        text.setDefaultTextColor(QColor(128, 128, 128))
        text.setFont(QFont("Arial", 14))

    def set_graph(self, graph: CDFGGraph):
        """Load and display a CDFG graph."""
        self.graph = graph
        self.scene.clear()
        self.node_items.clear()

        if not graph.nodes:
            self._show_placeholder()
            return

        # Calculate positions
        positions = get_node_positions(graph)

        # Scale positions for display
        scale = 100
        for uid in positions:
            x, y = positions[uid]
            positions[uid] = (x * scale, y * scale)

        # Add nodes
        for uid, node in graph.nodes.items():
            if uid in positions:
                x, y = positions[uid]
            else:
                # Fallback position
                x, y = uid * 100, 0

            item = InstructionNodeItem(node, x, y)
            self.scene.addItem(item)
            self.node_items[uid] = item

        # Add edges
        for edge in graph.edges:
            if edge.source in self.node_items and edge.target in self.node_items:
                self._add_edge(edge.source, edge.target, edge.edge_type)

        # Fit view
        self.view.fit_to_view()

    def _add_edge(self, source_uid: int, target_uid: int, edge_type: str):
        """Add an edge between two nodes."""
        source_item = self.node_items[source_uid]
        target_item = self.node_items[target_uid]

        p1 = source_item.center
        p2 = target_item.center

        pen = QPen(EDGE_COLORS.get(edge_type, QColor(0, 0, 0)), 1)

        if edge_type == 'control':
            pen.setStyle(Qt.PenStyle.DashLine)
        elif edge_type == 'sequence':
            pen.setStyle(Qt.PenStyle.DotLine)

        line = self.scene.addLine(p1.x(), p1.y(), p2.x(), p2.y(), pen)
        line.setZValue(-1)  # Draw behind nodes

        # Add arrowhead
        self._add_arrowhead(p1, p2, pen)

    def _add_arrowhead(self, p1: QPointF, p2: QPointF, pen: QPen):
        """Add arrowhead to edge."""
        angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
        arrow_size = 8

        # Calculate arrow points
        arrow_p1 = QPointF(
            p2.x() - arrow_size * math.cos(angle - math.pi/6),
            p2.y() - arrow_size * math.sin(angle - math.pi/6)
        )
        arrow_p2 = QPointF(
            p2.x() - arrow_size * math.cos(angle + math.pi/6),
            p2.y() - arrow_size * math.sin(angle + math.pi/6)
        )

        self.scene.addLine(p2.x(), p2.y(), arrow_p1.x(), arrow_p1.y(), pen)
        self.scene.addLine(p2.x(), p2.y(), arrow_p2.x(), arrow_p2.y(), pen)

    def _on_node_clicked(self, uid: int):
        """Handle node click event."""
        if self.graph and uid in self.graph.nodes:
            node = self.graph.nodes[uid]
            self.details_panel.set_node(node)

            # Highlight selected node
            for item_uid, item in self.node_items.items():
                if item_uid == uid:
                    item.setPen(QPen(Qt.GlobalColor.blue, 3))
                    item.selected = True
                else:
                    item.setPen(QPen(Qt.GlobalColor.black, 1))
                    item.selected = False

    def zoom_in(self):
        """Zoom in on the graph."""
        self.view.zoom_in()

    def zoom_out(self):
        """Zoom out on the graph."""
        self.view.zoom_out()

    def fit_to_view(self):
        """Fit the graph to the view."""
        self.view.fit_to_view()
