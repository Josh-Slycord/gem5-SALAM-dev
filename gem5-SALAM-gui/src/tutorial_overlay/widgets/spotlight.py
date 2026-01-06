"""
Tutorial Overlay - Spotlight Overlay Widget
===========================================

Full-screen overlay that dims everything except the target widget.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class SpotlightOverlay(QWidget):
    """
    Full-screen overlay that dims the entire screen except for a target widget.

    Creates a "spotlight" effect drawing attention to a specific widget.
    Uses QPainterPath composition to create a cutout in the dimmed overlay.

    Follows ViewToggleOverlay pattern from visual_composer:
        - WA_TranslucentBackground for transparency
        - Semi-transparent dim color: rgba(0, 0, 0, 180)

    Signals:
        overlay_clicked: Emitted when user clicks outside the spotlight.
        target_clicked: Emitted when user clicks on the target area.

    Usage:
        overlay = SpotlightOverlay(parent_window)
        overlay.set_target(button_widget, padding=10)
        overlay.show()
    """

    overlay_clicked = Signal()
    target_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        """
        Initialize the spotlight overlay.

        Args:
            parent: Parent widget (usually the main window).
        """
        super().__init__(parent)

        # Make the overlay transparent with clickable areas
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, False
        )

        # Stay on top but don't steal focus
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        # Target state
        self._target: QWidget | None = None
        self._target_rect: QRect = QRect()
        self._padding: int = 8
        self._corner_radius: int = 8

        # Visual styling
        self._dim_color = QColor(0, 0, 0, 180)
        self._border_color = QColor(100, 150, 255, 200)
        self._border_width = 2

        # Track if we should show border around spotlight
        self._show_border = True

    @property
    def dim_color(self) -> QColor:
        """Get the dim overlay color."""
        return self._dim_color

    @dim_color.setter
    def dim_color(self, color: QColor):
        """Set the dim overlay color."""
        self._dim_color = color
        self.update()

    @property
    def border_color(self) -> QColor:
        """Get the spotlight border color."""
        return self._border_color

    @border_color.setter
    def border_color(self, color: QColor):
        """Set the spotlight border color."""
        self._border_color = color
        self.update()

    @property
    def show_border(self) -> bool:
        """Get whether to show border around spotlight."""
        return self._show_border

    @show_border.setter
    def show_border(self, show: bool):
        """Set whether to show border around spotlight."""
        self._show_border = show
        self.update()

    def set_target(self, widget: QWidget | None, padding: int = 8):
        """
        Set the target widget to spotlight.

        Args:
            widget: Widget to highlight, or None to clear.
            padding: Extra space around the widget in pixels.
        """
        self._target = widget
        self._padding = padding

        if widget is not None:
            self._update_target_rect()
        else:
            self._target_rect = QRect()

        self.update()

    def clear_target(self):
        """Remove spotlight and show full dimmed overlay."""
        self._target = None
        self._target_rect = QRect()
        self.update()

    def _update_target_rect(self):
        """Update the target rectangle in overlay coordinates."""
        if self._target is None:
            self._target_rect = QRect()
            return

        # Get target's global geometry
        target_rect = self._target.rect()
        global_pos = self._target.mapToGlobal(target_rect.topLeft())

        # Convert to overlay's coordinate system
        local_pos = self.mapFromGlobal(global_pos)

        # Create rectangle with padding
        self._target_rect = QRect(
            local_pos.x() - self._padding,
            local_pos.y() - self._padding,
            target_rect.width() + (self._padding * 2),
            target_rect.height() + (self._padding * 2),
        )

    def update_geometry(self):
        """Update overlay to fill parent and recalculate target rect."""
        if self.parent():
            parent = self.parent()
            if hasattr(parent, "rect"):
                self.setGeometry(parent.rect())
        self._update_target_rect()
        self.update()

    def showEvent(self, event):
        """Handle show event - update geometry."""
        super().showEvent(event)
        self.update_geometry()

    def resizeEvent(self, event):
        """Handle resize - update target rect."""
        super().resizeEvent(event)
        self._update_target_rect()

    def paintEvent(self, event):
        """Paint the dimmed overlay with cutout for target."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Create full overlay path
        overlay_path = QPainterPath()
        overlay_path.addRect(self.rect())

        # If we have a target, create cutout
        if not self._target_rect.isEmpty():
            # Create rounded rectangle path for cutout
            cutout_path = QPainterPath()
            cutout_path.addRoundedRect(
                self._target_rect, self._corner_radius, self._corner_radius
            )

            # Subtract cutout from overlay
            overlay_path = overlay_path.subtracted(cutout_path)

        # Fill the dimmed area
        painter.fillPath(overlay_path, self._dim_color)

        # Draw border around spotlight cutout
        if self._show_border and not self._target_rect.isEmpty():
            pen = QPen(self._border_color, self._border_width)
            painter.setPen(pen)
            painter.drawRoundedRect(
                self._target_rect, self._corner_radius, self._corner_radius
            )

    def mousePressEvent(self, event):
        """Handle mouse clicks to detect target vs overlay clicks."""
        if not self._target_rect.isEmpty():
            if self._target_rect.contains(event.pos()):
                self.target_clicked.emit()
                # Pass click through to target widget
                event.ignore()
                return

        self.overlay_clicked.emit()
        event.accept()

    def get_target_center(self) -> tuple[int, int]:
        """
        Get the center point of the target rectangle.

        Returns:
            Tuple of (x, y) coordinates, or (0, 0) if no target.
        """
        if self._target_rect.isEmpty():
            return (0, 0)
        return (self._target_rect.center().x(), self._target_rect.center().y())

    def get_target_rect(self) -> QRect:
        """Get the current target rectangle (in overlay coordinates)."""
        return QRect(self._target_rect)
