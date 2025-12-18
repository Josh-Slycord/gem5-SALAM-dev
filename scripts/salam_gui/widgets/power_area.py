# ==============================================================================
# power_area.py - Power and Area Analysis Dashboard
# ==============================================================================
"""Power and Area Analysis Dashboard for gem5-SALAM GUI.

This module provides the PowerAreaWidget, which visualizes power consumption
and silicon area breakdown for accelerator components using treemaps, bar
charts, and detailed tables. Helps with design space exploration and
optimization decisions.

Features:
    - Area treemap showing proportional component sizes
    - Power bar chart with leakage vs dynamic breakdown
    - Summary cards for totals and power density
    - Component detail table with sorting
    - Design insights and recommendations

Widget Layout::

    +------------------------------------------------------------------+
    | Power & Area Analysis                                             |
    +------------------------------------------------------------------+
    | +-------------+ +-------------+ +-------------+ +-------------+   |
    | | Total Area  | | Total Power | | Breakdown   | | Power Dens  |  |
    | | 0.1234 mm²  | | 45.67 mW    | | 30% / 70%   | | 370 mW/mm²  |  |
    | +-------------+ +-------------+ +-------------+ +-------------+   |
    +------------------------------------------------------------------+
    | [Area] [Power] [Details]                                         |
    +------------------------------------------------------------------+
    | Area Tab (Treemap):                                              |
    | +--------------------+------------+--------+                     |
    | |                    |            |        |                     |
    | |    FU_MULT         |  FU_ADD    |  SPM   |                     |
    | |    0.045 mm²       |  0.023 mm² |        |                     |
    | |                    |            +--------+                     |
    | |                    +------------+ Cache  |                     |
    | +--------------------+   Regs     |        |                     |
    | +--------------------+------------+--------+                     |
    +------------------------------------------------------------------+
    | Power Tab (Bar Chart):                                           |
    | FU_MULT  |████████████░░░░░░░░░░| 12.3 mW                        |
    | FU_ADD   |██████░░░░░░░░░░░░░░░░|  6.5 mW                        |
    | SPM      |████████░░░░░░░░░░░░░░|  8.1 mW                        |
    | [████ Leakage] [░░░░ Dynamic]                                     |
    +------------------------------------------------------------------+
    | Design Insights:                                                  |
    | • FU_MULT dominates area (45%)                                   |
    | • Cache uses most power (38%)                                    |
    | • Register bank 12% utilized, consider downsizing                |
    +------------------------------------------------------------------+

Component Color Legend:
    | Component Type | Color              | Examples           |
    |----------------|--------------------|--------------------|
    | fu             | Cornflower Blue    | ALU, Multiplier    |
    | spm            | Light Green        | Scratchpad memory  |
    | cache          | Light Pink         | L1/L2 cache        |
    | register       | Peach              | Register bank      |
    | interconnect   | Plum               | NoC, crossbar      |
    | control        | Light Steel Blue   | FSM, scheduler     |
    | memory         | Light Yellow       | Memory controller  |

Power Sources:
    - Leakage Power: Static power consumption (always-on)
    - Dynamic Power: Activity-dependent power consumption

Example:
    Loading power/area data::

        from salam_gui.widgets.power_area import (
            PowerAreaWidget, PowerAreaData, ComponentMetrics
        )

        widget = PowerAreaWidget()

        # From CACTI/McPAT output
        data = PowerAreaData()
        data.components["FU_MULT"] = ComponentMetrics(
            name="FU_MULT",
            area_mm2=0.045,
            leakage_power_mw=2.1,
            dynamic_power_mw=10.2,
            utilization=0.85
        )
        widget.set_data(data)

Data Sources:
    - CACTI: Memory structures (SPM, cache, register bank)
    - McPAT: Processor components adapted for accelerators
    - gem5-SALAM HWModeling: Cycle-accurate utilization

See Also:
    - fu_utilization: Functional unit usage patterns
    - stats_dashboard: Overall performance metrics
    - SALAMPowerModel: Power modeling implementation (C++)
"""


__version__ = "3.0.0.pre[1.0.0]"

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QGroupBox, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QComboBox, QTabWidget
)
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics
from PySide6.QtCore import Qt, QRect, QRectF


@dataclass
class ComponentMetrics:
    """Metrics for a single component."""
    name: str
    area_mm2: float = 0.0
    leakage_power_mw: float = 0.0
    dynamic_power_mw: float = 0.0
    utilization: float = 0.0  # 0.0 - 1.0

    @property
    def total_power_mw(self) -> float:
        return self.leakage_power_mw + self.dynamic_power_mw


@dataclass
class PowerAreaData:
    """Complete power and area data for the accelerator."""
    components: Dict[str, ComponentMetrics] = field(default_factory=dict)

    @property
    def total_area(self) -> float:
        return sum(c.area_mm2 for c in self.components.values())

    @property
    def total_power(self) -> float:
        return sum(c.total_power_mw for c in self.components.values())

    @property
    def total_leakage(self) -> float:
        return sum(c.leakage_power_mw for c in self.components.values())

    @property
    def total_dynamic(self) -> float:
        return sum(c.dynamic_power_mw for c in self.components.values())


# Color palette for components
COMPONENT_COLORS = {
    'fu': QColor(100, 149, 237),      # Cornflower blue
    'spm': QColor(144, 238, 144),     # Light green
    'cache': QColor(255, 182, 193),   # Light pink
    'register': QColor(255, 218, 185), # Peach
    'interconnect': QColor(221, 160, 221), # Plum
    'control': QColor(176, 196, 222), # Light steel blue
    'memory': QColor(255, 255, 224),  # Light yellow
    'default': QColor(200, 200, 200), # Gray
}


def get_component_color(name: str) -> QColor:
    """Get color for a component based on its name."""
    name_lower = name.lower()
    for key, color in COMPONENT_COLORS.items():
        if key in name_lower:
            return color
    return COMPONENT_COLORS['default']


class TreemapWidget(QWidget):
    """Treemap visualization for area breakdown."""

    def __init__(self):
        super().__init__()
        self.data: Optional[PowerAreaData] = None
        self.rects: List[Tuple[QRectF, str, float]] = []  # (rect, name, value)
        self.setMinimumHeight(250)
        self.setMinimumWidth(300)

    def set_data(self, data: PowerAreaData):
        """Set the power/area data to display."""
        self.data = data
        self._calculate_treemap()
        self.update()

    def _calculate_treemap(self):
        """Calculate treemap rectangles using squarified algorithm."""
        self.rects = []
        if not self.data or not self.data.components:
            return

        # Get sorted components by area (largest first)
        components = sorted(
            self.data.components.items(),
            key=lambda x: x[1].area_mm2,
            reverse=True
        )

        total_area = self.data.total_area
        if total_area <= 0:
            return

        # Simple slice-and-dice treemap
        rect = QRectF(10, 10, self.width() - 20, self.height() - 20)
        self._squarify(components, rect, total_area)

    def _squarify(self, components: List[Tuple[str, ComponentMetrics]],
                  rect: QRectF, total_area: float):
        """Simple treemap layout using slice-and-dice."""
        if not components:
            return

        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()

        if w < 2 or h < 2:
            return

        # Determine layout direction
        horizontal = w >= h

        remaining = list(components)
        offset = 0

        for name, metrics in remaining:
            if total_area <= 0:
                break

            ratio = metrics.area_mm2 / total_area

            if horizontal:
                box_w = w * ratio
                box = QRectF(x + offset, y, box_w, h)
                offset += box_w
            else:
                box_h = h * ratio
                box = QRectF(x, y + offset, w, box_h)
                offset += box_h

            self.rects.append((box, name, metrics.area_mm2))

    def paintEvent(self, event):
        """Draw the treemap."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor(255, 255, 255))

        if not self.data or not self.data.components:
            painter.setPen(QColor(128, 128, 128))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                           "No power/area data loaded")
            return

        # Recalculate if size changed
        self._calculate_treemap()

        # Draw treemap cells
        font = QFont("Arial", 9)
        painter.setFont(font)
        metrics = QFontMetrics(font)

        for rect, name, value in self.rects:
            if rect.width() < 2 or rect.height() < 2:
                continue

            color = get_component_color(name)

            # Draw cell
            painter.fillRect(rect, color)
            painter.setPen(QPen(QColor(100, 100, 100), 1))
            painter.drawRect(rect)

            # Draw label if cell is large enough
            if rect.width() > 50 and rect.height() > 30:
                painter.setPen(QColor(0, 0, 0))

                # Truncate name if needed
                display_name = name[:12] + "..." if len(name) > 15 else name

                text_rect = rect.adjusted(3, 3, -3, -3)
                painter.drawText(text_rect.toRect(),
                               Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                               display_name)

                # Show value
                if rect.height() > 45:
                    value_text = f"{value:.3f} mm²"
                    painter.drawText(text_rect.toRect(),
                                   Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
                                   value_text)

    def resizeEvent(self, event):
        """Recalculate treemap on resize."""
        self._calculate_treemap()
        super().resizeEvent(event)


class PowerBarChart(QWidget):
    """Stacked bar chart showing power breakdown."""

    def __init__(self):
        super().__init__()
        self.data: Optional[PowerAreaData] = None
        self.setMinimumHeight(200)
        self.setMinimumWidth(300)

    def set_data(self, data: PowerAreaData):
        """Set the power data to display."""
        self.data = data
        self.update()

    def paintEvent(self, event):
        """Draw the power bar chart."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        margin_left = 100
        margin_right = 20
        margin_top = 30
        margin_bottom = 40

        chart_rect = QRect(
            margin_left, margin_top,
            rect.width() - margin_left - margin_right,
            rect.height() - margin_top - margin_bottom
        )

        # Background
        painter.fillRect(rect, QColor(255, 255, 255))

        if not self.data or not self.data.components:
            painter.setPen(QColor(128, 128, 128))
            painter.drawText(chart_rect, Qt.AlignmentFlag.AlignCenter,
                           "No power data loaded")
            return

        # Sort by total power
        components = sorted(
            self.data.components.items(),
            key=lambda x: x[1].total_power_mw,
            reverse=True
        )[:10]  # Top 10 components

        if not components:
            return

        max_power = max(c.total_power_mw for _, c in components)
        if max_power <= 0:
            max_power = 1

        bar_height = chart_rect.height() / len(components) - 5

        # Draw bars
        painter.setFont(QFont("Arial", 8))

        for i, (name, metrics) in enumerate(components):
            y = chart_rect.top() + i * (bar_height + 5)

            # Draw label
            painter.setPen(QColor(0, 0, 0))
            label_rect = QRect(5, int(y), margin_left - 10, int(bar_height))
            painter.drawText(label_rect,
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           name[:15])

            # Calculate bar widths
            leakage_width = (metrics.leakage_power_mw / max_power) * chart_rect.width()
            dynamic_width = (metrics.dynamic_power_mw / max_power) * chart_rect.width()

            # Draw leakage (darker color)
            color = get_component_color(name)
            darker_color = color.darker(130)

            painter.fillRect(
                int(chart_rect.left()), int(y),
                int(leakage_width), int(bar_height),
                darker_color
            )

            # Draw dynamic (lighter color)
            painter.fillRect(
                int(chart_rect.left() + leakage_width), int(y),
                int(dynamic_width), int(bar_height),
                color
            )

            # Border
            painter.setPen(QPen(QColor(100, 100, 100), 1))
            painter.drawRect(
                int(chart_rect.left()), int(y),
                int(leakage_width + dynamic_width), int(bar_height)
            )

            # Value label
            painter.setPen(QColor(0, 0, 0))
            value_text = f"{metrics.total_power_mw:.2f} mW"
            painter.drawText(
                int(chart_rect.left() + leakage_width + dynamic_width + 5),
                int(y + bar_height/2 + 4),
                value_text
            )

        # Draw legend
        legend_y = rect.height() - 20
        painter.setPen(QColor(0, 0, 0))

        painter.fillRect(margin_left, legend_y, 15, 15, QColor(100, 100, 100))
        painter.drawText(margin_left + 20, legend_y + 12, "Leakage")

        painter.fillRect(margin_left + 100, legend_y, 15, 15, QColor(150, 180, 210))
        painter.drawText(margin_left + 120, legend_y + 12, "Dynamic")


class ComponentTable(QTableWidget):
    """Table showing all component metrics."""

    def __init__(self):
        super().__init__()

        self.setColumnCount(6)
        self.setHorizontalHeaderLabels([
            "Component", "Area (mm²)", "Leakage (mW)",
            "Dynamic (mW)", "Total (mW)", "Util %"
        ])

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 6):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)

    def set_data(self, data: PowerAreaData):
        """Update table with component data."""
        self.setRowCount(len(data.components))

        for row, (name, metrics) in enumerate(data.components.items()):
            self.setItem(row, 0, QTableWidgetItem(name))
            self.setItem(row, 1, QTableWidgetItem(f"{metrics.area_mm2:.4f}"))
            self.setItem(row, 2, QTableWidgetItem(f"{metrics.leakage_power_mw:.3f}"))
            self.setItem(row, 3, QTableWidgetItem(f"{metrics.dynamic_power_mw:.3f}"))
            self.setItem(row, 4, QTableWidgetItem(f"{metrics.total_power_mw:.3f}"))
            self.setItem(row, 5, QTableWidgetItem(f"{metrics.utilization:.1%}"))

            # Color row based on component type
            color = get_component_color(name)
            color.setAlpha(50)
            for col in range(6):
                item = self.item(row, col)
                if item:
                    item.setBackground(color)


class SummaryCards(QWidget):
    """Summary cards showing totals."""

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Total Area card
        self.area_card = self._create_card("Total Area", "-")
        layout.addWidget(self.area_card)

        # Total Power card
        self.power_card = self._create_card("Total Power", "-")
        layout.addWidget(self.power_card)

        # Power breakdown card
        self.breakdown_card = self._create_card("Power Breakdown", "-")
        layout.addWidget(self.breakdown_card)

        # Efficiency card
        self.efficiency_card = self._create_card("Power Density", "-")
        layout.addWidget(self.efficiency_card)

    def _create_card(self, title: str, value: str) -> QFrame:
        """Create a metric card."""
        card = QFrame()
        card.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)

        layout = QVBoxLayout(card)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: gray; font-size: 10pt;")
        layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        value_label.setObjectName("value")
        layout.addWidget(value_label)

        return card

    def set_data(self, data: PowerAreaData):
        """Update summary cards."""
        # Total area
        area_label = self.area_card.findChild(QLabel, "value")
        if area_label:
            area_label.setText(f"{data.total_area:.4f} mm²")

        # Total power
        power_label = self.power_card.findChild(QLabel, "value")
        if power_label:
            power_label.setText(f"{data.total_power:.2f} mW")

        # Power breakdown
        breakdown_label = self.breakdown_card.findChild(QLabel, "value")
        if breakdown_label:
            leakage_pct = (data.total_leakage / data.total_power * 100) if data.total_power > 0 else 0
            breakdown_label.setText(f"{leakage_pct:.0f}% Leak / {100-leakage_pct:.0f}% Dyn")

        # Power density
        density_label = self.efficiency_card.findChild(QLabel, "value")
        if density_label:
            density = data.total_power / data.total_area if data.total_area > 0 else 0
            density_label.setText(f"{density:.2f} mW/mm²")


class PowerAreaWidget(QWidget):
    """Main power and area dashboard widget."""

    def __init__(self):
        super().__init__()
        self.data: Optional[PowerAreaData] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Power & Area Analysis")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(title)

        # Summary cards
        self.summary = SummaryCards()
        layout.addWidget(self.summary)

        # Tabs for different views
        tabs = QTabWidget()

        # Area treemap tab
        treemap_widget = QWidget()
        treemap_layout = QVBoxLayout(treemap_widget)
        treemap_layout.addWidget(QLabel("Area Distribution (Treemap)"))
        self.treemap = TreemapWidget()
        treemap_layout.addWidget(self.treemap)
        tabs.addTab(treemap_widget, "Area")

        # Power chart tab
        power_widget = QWidget()
        power_layout = QVBoxLayout(power_widget)
        power_layout.addWidget(QLabel("Power Breakdown by Component"))
        self.power_chart = PowerBarChart()
        power_layout.addWidget(self.power_chart)
        tabs.addTab(power_widget, "Power")

        # Table tab
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        table_layout.addWidget(QLabel("Component Details"))
        self.table = ComponentTable()
        table_layout.addWidget(self.table)
        tabs.addTab(table_widget, "Details")

        layout.addWidget(tabs)

        # Insights panel
        self.insights_label = QLabel("")
        self.insights_label.setWordWrap(True)
        self.insights_label.setStyleSheet(
            "background: #e7f3ff; padding: 10px; border-radius: 5px;"
        )
        self.insights_label.hide()
        layout.addWidget(self.insights_label)

    def set_data(self, data: PowerAreaData):
        """Load power and area data."""
        self.data = data
        self.summary.set_data(data)
        self.treemap.set_data(data)
        self.power_chart.set_data(data)
        self.table.set_data(data)
        self._analyze_insights()

    def _analyze_insights(self):
        """Generate insights about the design."""
        if not self.data or not self.data.components:
            self.insights_label.hide()
            return

        insights = []

        # Find largest area consumers
        sorted_by_area = sorted(
            self.data.components.items(),
            key=lambda x: x[1].area_mm2,
            reverse=True
        )
        if sorted_by_area:
            name, metrics = sorted_by_area[0]
            pct = metrics.area_mm2 / self.data.total_area * 100
            insights.append(f"<b>{name}</b> dominates area ({pct:.0f}%)")

        # Find largest power consumers
        sorted_by_power = sorted(
            self.data.components.items(),
            key=lambda x: x[1].total_power_mw,
            reverse=True
        )
        if sorted_by_power:
            name, metrics = sorted_by_power[0]
            pct = metrics.total_power_mw / self.data.total_power * 100
            insights.append(f"<b>{name}</b> uses most power ({pct:.0f}%)")

        # Check for underutilized components
        underutilized = [
            (name, m) for name, m in self.data.components.items()
            if m.utilization < 0.2 and m.area_mm2 > self.data.total_area * 0.05
        ]
        for name, metrics in underutilized[:2]:
            insights.append(
                f"<b>{name}</b>: {metrics.utilization:.0%} utilized, "
                f"consider downsizing"
            )

        if insights:
            self.insights_label.setText(
                "<b>Design Insights:</b><br>" + "<br>".join(insights)
            )
            self.insights_label.show()
        else:
            self.insights_label.hide()

    def clear(self):
        """Clear all data."""
        self.data = None
        self.insights_label.hide()


def parse_power_area_output(content: str) -> PowerAreaData:
    """
    Parse power and area data from gem5-SALAM output.

    Looks for patterns like:
    Component: FU_MULT Area: 0.123 mm2 Leakage: 0.5 mW Dynamic: 2.3 mW
    """
    import re

    data = PowerAreaData()

    # Pattern for component power/area lines
    # Flexible pattern to match various output formats
    patterns = [
        # Format: Component Area Power
        re.compile(
            r'(\w+).*?area[:\s]+([0-9.]+).*?'
            r'(?:leakage|static)[:\s]+([0-9.]+).*?'
            r'(?:dynamic)[:\s]+([0-9.]+)',
            re.IGNORECASE
        ),
        # Format: Just area
        re.compile(
            r'(\w+).*?area[:\s]+([0-9.]+)\s*(?:mm|um)',
            re.IGNORECASE
        ),
    ]

    for pattern in patterns:
        for match in pattern.finditer(content):
            name = match.group(1)

            if len(match.groups()) >= 4:
                # Full metrics
                metrics = ComponentMetrics(
                    name=name,
                    area_mm2=float(match.group(2)),
                    leakage_power_mw=float(match.group(3)),
                    dynamic_power_mw=float(match.group(4))
                )
            else:
                # Just area
                metrics = ComponentMetrics(
                    name=name,
                    area_mm2=float(match.group(2))
                )

            data.components[name] = metrics

    return data
