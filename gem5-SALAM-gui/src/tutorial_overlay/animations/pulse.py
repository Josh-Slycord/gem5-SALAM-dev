"""
Tutorial Overlay - Highlight Pulse Animation
=============================================

Pulsing glow effect for highlighting target widgets.
Follows the PulseEffect pattern from visual_composer/animations.py.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget


class HighlightPulse(QObject):
    """
    Creates a pulsing glow effect around a target widget.

    Similar to PulseEffect in visual_composer/animations.py but adapted
    for QWidget instead of QGraphicsItem.

    Uses QGraphicsDropShadowEffect with animated blur radius to create
    a pulsing glow effect that draws attention to the target widget.

    Signals:
        pulse_updated: Emitted on each animation frame with intensity (0.0-1.0).

    Usage:
        pulse = HighlightPulse(my_button)
        pulse.start()
        # ... later
        pulse.stop()
    """

    pulse_updated = Signal(float)  # Intensity 0.0 to 1.0

    def __init__(
        self,
        target: QWidget,
        color: QColor | None = None,
        parent: QObject | None = None,
    ):
        """
        Initialize the pulse effect.

        Args:
            target: Widget to apply the glow effect to.
            color: Glow color (default: blue #6496ff).
            parent: Parent QObject for memory management.
        """
        super().__init__(parent)

        self._target = target
        self._color = color or QColor(100, 150, 255)  # Blue glow
        self._intensity = 0.0
        self._direction = 1  # 1 = increasing, -1 = decreasing
        self._running = False

        # Animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_pulse)

        # Shadow effect for glow
        self._shadow: QGraphicsDropShadowEffect | None = None
        self._original_effect: QGraphicsDropShadowEffect | None = None

        # Animation parameters
        self._min_blur = 5
        self._max_blur = 25
        self._speed = 0.08  # Intensity change per frame

    @property
    def color(self) -> QColor:
        """Get the glow color."""
        return self._color

    @color.setter
    def color(self, color: QColor):
        """Set the glow color."""
        self._color = color
        if self._shadow:
            self._shadow.setColor(color)

    @property
    def is_running(self) -> bool:
        """Check if animation is running."""
        return self._running

    @property
    def intensity(self) -> float:
        """Get current pulse intensity (0.0 to 1.0)."""
        return self._intensity

    def start(self, interval: int = 50):
        """
        Start the pulse animation.

        Args:
            interval: Timer interval in milliseconds (default: 50ms = 20fps).
        """
        if self._running:
            return

        self._running = True
        self._intensity = 0.0
        self._direction = 1

        # Store original effect if any
        self._original_effect = self._target.graphicsEffect()

        # Create and apply shadow effect
        self._shadow = QGraphicsDropShadowEffect()
        self._shadow.setBlurRadius(self._min_blur)
        self._shadow.setColor(self._color)
        self._shadow.setOffset(0, 0)
        self._target.setGraphicsEffect(self._shadow)

        self._timer.start(interval)

    def stop(self):
        """Stop the pulse animation and remove the effect."""
        if not self._running:
            return

        self._running = False
        self._timer.stop()
        self._intensity = 0.0

        # Restore original effect (or remove if none)
        if self._target:
            self._target.setGraphicsEffect(self._original_effect)

        self._shadow = None
        self._original_effect = None

    def _update_pulse(self):
        """Update pulse intensity on each timer tick."""
        # Update intensity with direction
        self._intensity += self._speed * self._direction

        # Reverse direction at bounds
        if self._intensity >= 1.0:
            self._intensity = 1.0
            self._direction = -1
        elif self._intensity <= 0.0:
            self._intensity = 0.0
            self._direction = 1

        # Update shadow blur based on intensity
        if self._shadow:
            blur = self._min_blur + (
                self._intensity * (self._max_blur - self._min_blur)
            )
            self._shadow.setBlurRadius(blur)

        # Emit signal for external tracking
        self.pulse_updated.emit(self._intensity)

    def set_speed(self, speed: float):
        """
        Set animation speed.

        Args:
            speed: Intensity change per frame (default: 0.08).
        """
        self._speed = max(0.01, min(0.5, speed))

    def set_blur_range(self, min_blur: int, max_blur: int):
        """
        Set blur radius range.

        Args:
            min_blur: Minimum blur radius in pixels.
            max_blur: Maximum blur radius in pixels.
        """
        self._min_blur = max(0, min_blur)
        self._max_blur = max(self._min_blur + 1, max_blur)


class BorderPulse(QObject):
    """
    Alternative highlight that pulses a border around the widget.

    Uses stylesheet manipulation instead of QGraphicsDropShadowEffect.
    Useful when the widget already has a graphics effect applied.
    """

    def __init__(
        self,
        target: QWidget,
        color: QColor | None = None,
        parent: QObject | None = None,
    ):
        """
        Initialize border pulse effect.

        Args:
            target: Widget to apply border to.
            color: Border color (default: blue).
            parent: Parent QObject.
        """
        super().__init__(parent)

        self._target = target
        self._color = color or QColor(100, 150, 255)
        self._intensity = 0.0
        self._direction = 1
        self._running = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_pulse)

        self._original_stylesheet = ""
        self._border_width = 2

    def start(self, interval: int = 50):
        """Start the border pulse animation."""
        if self._running:
            return

        self._running = True
        self._intensity = 0.0
        self._direction = 1

        # Store original stylesheet
        self._original_stylesheet = self._target.styleSheet()

        self._timer.start(interval)

    def stop(self):
        """Stop animation and restore original stylesheet."""
        if not self._running:
            return

        self._running = False
        self._timer.stop()

        # Restore original stylesheet
        self._target.setStyleSheet(self._original_stylesheet)

    def _update_pulse(self):
        """Update border opacity on each tick."""
        self._intensity += 0.08 * self._direction

        if self._intensity >= 1.0:
            self._intensity = 1.0
            self._direction = -1
        elif self._intensity <= 0.0:
            self._intensity = 0.0
            self._direction = 1

        # Calculate alpha based on intensity
        alpha = int(100 + (self._intensity * 155))  # 100-255 range
        color = QColor(self._color)
        color.setAlpha(alpha)

        # Apply border via stylesheet
        border_style = f"border: {self._border_width}px solid {color.name(QColor.NameFormat.HexArgb)};"
        new_style = self._original_stylesheet + border_style
        self._target.setStyleSheet(new_style)
