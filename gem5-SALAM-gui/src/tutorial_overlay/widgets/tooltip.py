"""
Tutorial Overlay - Tooltip Widget
=================================

Styled tooltip with arrow pointer for tutorial steps.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.schema import ArrowPosition


class TooltipWidget(QWidget):
    """
    Styled tooltip with arrow pointer for tutorial steps.

    Features:
        - Title and content text with word wrap
        - Arrow pointing to target widget
        - Automatic positioning to avoid screen edges
        - Dark theme styling consistent with visual_composer dialogs

    Signals:
        next_clicked: User clicked Next/Finish button.
        back_clicked: User clicked Back button.
        skip_clicked: User clicked Skip button.
        close_clicked: User clicked close (X) button.

    Usage:
        tooltip = TooltipWidget(parent)
        tooltip.set_content("Welcome", "This is the first step.")
        tooltip.point_to(target_rect, ArrowPosition.BOTTOM)
        tooltip.show()
    """

    # Signals for navigation
    next_clicked = Signal()
    back_clicked = Signal()
    skip_clicked = Signal()
    close_clicked = Signal()

    # Style constants
    BACKGROUND_COLOR = "#2d2d2d"
    BORDER_COLOR = "#555555"
    TEXT_COLOR = "#dddddd"
    TITLE_COLOR = "#ffffff"
    BUTTON_BG = "#3d3d3d"
    BUTTON_HOVER = "#4d4d4d"
    ACCENT_COLOR = "#4a90d9"

    ARROW_SIZE = 12
    BORDER_RADIUS = 8
    MIN_WIDTH = 280
    MAX_WIDTH = 400

    def __init__(self, parent: QWidget | None = None):
        """
        Initialize the tooltip widget.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)

        # Window flags for floating tooltip
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # State
        self._arrow_position = ArrowPosition.AUTO
        self._actual_arrow_position = ArrowPosition.BOTTOM
        self._target_rect: QRect = QRect()

        # Progress state
        self._current_step = 0
        self._total_steps = 1
        self._can_skip = True
        self._show_progress = True

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        """Create the tooltip UI components."""
        # Main layout with margins for arrow space
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            self.ARROW_SIZE + 4,
            self.ARROW_SIZE + 4,
            self.ARROW_SIZE + 4,
            self.ARROW_SIZE + 4,
        )
        main_layout.setSpacing(8)

        # Content container (painted background)
        self._content_widget = QWidget()
        self._content_widget.setObjectName("tooltip_content")
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(16, 12, 16, 12)
        content_layout.setSpacing(8)

        # Close button (top-right)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        # Title label
        self._title_label = QLabel()
        self._title_label.setObjectName("tooltip_title")
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        self._title_label.setFont(title_font)
        self._title_label.setWordWrap(True)
        header_layout.addWidget(self._title_label, 1)

        # Close button
        self._close_btn = QPushButton("×")
        self._close_btn.setObjectName("tooltip_close")
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.clicked.connect(self.close_clicked.emit)
        header_layout.addWidget(self._close_btn)

        content_layout.addLayout(header_layout)

        # Content label
        self._content_label = QLabel()
        self._content_label.setObjectName("tooltip_text")
        self._content_label.setWordWrap(True)
        content_layout.addWidget(self._content_label)

        # Progress label
        self._progress_label = QLabel()
        self._progress_label.setObjectName("tooltip_progress")
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self._progress_label)

        # Navigation buttons
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(8)

        self._skip_btn = QPushButton("Skip")
        self._skip_btn.setObjectName("tooltip_skip")
        self._skip_btn.clicked.connect(self.skip_clicked.emit)
        nav_layout.addWidget(self._skip_btn)

        nav_layout.addStretch()

        self._back_btn = QPushButton("Back")
        self._back_btn.setObjectName("tooltip_back")
        self._back_btn.clicked.connect(self.back_clicked.emit)
        nav_layout.addWidget(self._back_btn)

        self._next_btn = QPushButton("Next")
        self._next_btn.setObjectName("tooltip_next")
        self._next_btn.clicked.connect(self.next_clicked.emit)
        nav_layout.addWidget(self._next_btn)

        content_layout.addLayout(nav_layout)

        main_layout.addWidget(self._content_widget)

        # Set size constraints
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setMaximumWidth(self.MAX_WIDTH)

    def _apply_style(self):
        """Apply dark theme styling."""
        self.setStyleSheet(
            f"""
            #tooltip_content {{
                background-color: {self.BACKGROUND_COLOR};
                border: 1px solid {self.BORDER_COLOR};
                border-radius: {self.BORDER_RADIUS}px;
            }}
            #tooltip_title {{
                color: {self.TITLE_COLOR};
                background: transparent;
                border: none;
            }}
            #tooltip_text {{
                color: {self.TEXT_COLOR};
                background: transparent;
                border: none;
            }}
            #tooltip_progress {{
                color: #888888;
                font-size: 10px;
                background: transparent;
                border: none;
            }}
            #tooltip_close {{
                background: transparent;
                border: none;
                color: #888888;
                font-size: 16px;
                font-weight: bold;
            }}
            #tooltip_close:hover {{
                color: {self.TITLE_COLOR};
            }}
            QPushButton {{
                background-color: {self.BUTTON_BG};
                border: 1px solid {self.BORDER_COLOR};
                border-radius: 4px;
                color: {self.TEXT_COLOR};
                padding: 6px 12px;
                min-width: 60px;
            }}
            QPushButton:hover {{
                background-color: {self.BUTTON_HOVER};
                border-color: #666666;
            }}
            #tooltip_next {{
                background-color: {self.ACCENT_COLOR};
                border-color: {self.ACCENT_COLOR};
                color: white;
            }}
            #tooltip_next:hover {{
                background-color: #5a9fe9;
            }}
            #tooltip_skip {{
                background: transparent;
                border: none;
                color: #888888;
                min-width: 40px;
            }}
            #tooltip_skip:hover {{
                color: {self.TEXT_COLOR};
            }}
        """
        )

    def set_content(self, title: str, content: str):
        """
        Set tooltip title and content text.

        Args:
            title: Step title displayed in header.
            content: Step description/instructions.
        """
        self._title_label.setText(title)
        self._content_label.setText(content)
        self.adjustSize()

    def set_progress(
        self,
        current: int,
        total: int,
        can_skip: bool = True,
        show_progress: bool = True,
    ):
        """
        Update progress and navigation state.

        Args:
            current: Current step index (0-based).
            total: Total number of steps.
            can_skip: Whether skip button is enabled.
            show_progress: Whether to show progress indicator.
        """
        self._current_step = current
        self._total_steps = total
        self._can_skip = can_skip
        self._show_progress = show_progress

        # Update progress label
        if show_progress and total > 1:
            self._progress_label.setText(f"{current + 1} / {total}")
            self._progress_label.show()
        else:
            self._progress_label.hide()

        # Update skip button
        self._skip_btn.setVisible(can_skip)

        # Update back button (disabled on first step)
        self._back_btn.setEnabled(current > 0)

        # Update next button text
        is_last = current >= total - 1
        self._next_btn.setText("Finish" if is_last else "Next")

    def point_to(
        self,
        target_rect: QRect,
        preferred_position: ArrowPosition = ArrowPosition.AUTO,
    ):
        """
        Position tooltip to point at target rectangle.

        Args:
            target_rect: Global rectangle of target widget.
            preferred_position: Preferred arrow position.
        """
        self._target_rect = target_rect
        self._arrow_position = preferred_position

        # Calculate best position
        pos, actual_position = self._calculate_position(
            target_rect, preferred_position
        )
        self._actual_arrow_position = actual_position

        self.move(pos)
        self.update()

    def show_centered(self, title: str = "", content: str = ""):
        """
        Show tooltip centered on screen (for missing widget fallback).

        Args:
            title: Optional title to set.
            content: Optional content to set.
        """
        if title or content:
            self.set_content(title, content)

        # Clear target rect (no arrow)
        self._target_rect = QRect()

        # Center on screen
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()
            self.adjustSize()
            x = screen_rect.center().x() - self.width() // 2
            y = screen_rect.center().y() - self.height() // 2
            self.move(x, y)

        self.show()

    def _calculate_position(
        self, target_rect: QRect, position: ArrowPosition
    ) -> tuple[QPoint, ArrowPosition]:
        """
        Calculate tooltip position, adjusting for screen edges.

        Args:
            target_rect: Target widget rectangle in global coordinates.
            position: Preferred arrow position.

        Returns:
            Tuple of (position point, actual arrow position used).
        """
        self.adjustSize()
        tooltip_size = self.size()

        # Get screen geometry
        screen = QApplication.primaryScreen()
        screen_rect = (
            screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        )

        # Auto-select position if needed
        if position == ArrowPosition.AUTO:
            position = self._auto_select_position(
                target_rect, tooltip_size, screen_rect
            )

        # Calculate position based on arrow direction
        margin = self.ARROW_SIZE + 4

        if position == ArrowPosition.TOP:
            # Tooltip above target, arrow points down
            x = target_rect.center().x() - tooltip_size.width() // 2
            y = target_rect.top() - tooltip_size.height() - margin
        elif position == ArrowPosition.BOTTOM:
            # Tooltip below target, arrow points up
            x = target_rect.center().x() - tooltip_size.width() // 2
            y = target_rect.bottom() + margin
        elif position == ArrowPosition.LEFT:
            # Tooltip left of target, arrow points right
            x = target_rect.left() - tooltip_size.width() - margin
            y = target_rect.center().y() - tooltip_size.height() // 2
        elif position == ArrowPosition.RIGHT:
            # Tooltip right of target, arrow points left
            x = target_rect.right() + margin
            y = target_rect.center().y() - tooltip_size.height() // 2
        else:
            x = target_rect.center().x() - tooltip_size.width() // 2
            y = target_rect.bottom() + margin

        # Clamp to screen bounds
        x = max(
            screen_rect.left(),
            min(x, screen_rect.right() - tooltip_size.width()),
        )
        y = max(
            screen_rect.top(),
            min(y, screen_rect.bottom() - tooltip_size.height()),
        )

        return QPoint(x, y), position

    def _auto_select_position(
        self, target_rect: QRect, tooltip_size, screen_rect: QRect
    ) -> ArrowPosition:
        """
        Automatically select best arrow position based on available space.

        Args:
            target_rect: Target widget rectangle.
            tooltip_size: Size of the tooltip.
            screen_rect: Available screen area.

        Returns:
            Best ArrowPosition based on available space.
        """
        margin = self.ARROW_SIZE + 8

        # Calculate available space in each direction
        space_above = target_rect.top() - screen_rect.top()
        space_below = screen_rect.bottom() - target_rect.bottom()
        space_left = target_rect.left() - screen_rect.left()
        space_right = screen_rect.right() - target_rect.right()

        # Prefer below, then above, then right, then left
        if space_below >= tooltip_size.height() + margin:
            return ArrowPosition.BOTTOM
        if space_above >= tooltip_size.height() + margin:
            return ArrowPosition.TOP
        if space_right >= tooltip_size.width() + margin:
            return ArrowPosition.RIGHT
        if space_left >= tooltip_size.width() + margin:
            return ArrowPosition.LEFT

        # Default to bottom if nothing fits well
        return ArrowPosition.BOTTOM

    def paintEvent(self, event):
        """Paint the tooltip background and arrow."""
        super().paintEvent(event)

        # Only draw arrow if we have a target
        if self._target_rect.isEmpty():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw arrow pointing to target
        self._draw_arrow(painter)

    def _draw_arrow(self, painter: QPainter):
        """Draw the arrow pointing to the target."""
        arrow_size = self.ARROW_SIZE
        content_rect = self._content_widget.geometry()

        # Arrow colors
        fill_color = QColor(self.BACKGROUND_COLOR)
        border_color = QColor(self.BORDER_COLOR)

        # Calculate arrow position based on actual position
        if self._actual_arrow_position == ArrowPosition.BOTTOM:
            # Arrow points up (tooltip is below target)
            arrow_x = content_rect.center().x()
            arrow_y = content_rect.top()
            points = [
                QPoint(arrow_x, arrow_y - arrow_size),
                QPoint(arrow_x - arrow_size, arrow_y),
                QPoint(arrow_x + arrow_size, arrow_y),
            ]
        elif self._actual_arrow_position == ArrowPosition.TOP:
            # Arrow points down (tooltip is above target)
            arrow_x = content_rect.center().x()
            arrow_y = content_rect.bottom()
            points = [
                QPoint(arrow_x, arrow_y + arrow_size),
                QPoint(arrow_x - arrow_size, arrow_y),
                QPoint(arrow_x + arrow_size, arrow_y),
            ]
        elif self._actual_arrow_position == ArrowPosition.LEFT:
            # Arrow points right (tooltip is left of target)
            arrow_x = content_rect.right()
            arrow_y = content_rect.center().y()
            points = [
                QPoint(arrow_x + arrow_size, arrow_y),
                QPoint(arrow_x, arrow_y - arrow_size),
                QPoint(arrow_x, arrow_y + arrow_size),
            ]
        elif self._actual_arrow_position == ArrowPosition.RIGHT:
            # Arrow points left (tooltip is right of target)
            arrow_x = content_rect.left()
            arrow_y = content_rect.center().y()
            points = [
                QPoint(arrow_x - arrow_size, arrow_y),
                QPoint(arrow_x, arrow_y - arrow_size),
                QPoint(arrow_x, arrow_y + arrow_size),
            ]
        else:
            return

        # Draw filled arrow
        path = QPainterPath()
        path.addPolygon(QPolygon(points))
        painter.fillPath(path, fill_color)

        # Draw arrow border (just the two outer edges)
        pen = QPen(border_color, 1)
        painter.setPen(pen)
        painter.drawLine(points[0], points[1])
        painter.drawLine(points[0], points[2])
