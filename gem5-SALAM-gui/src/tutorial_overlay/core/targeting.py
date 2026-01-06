"""
Tutorial Overlay - Widget Targeting
===================================

Resolves widget targets from various input formats.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class WidgetTargeter:
    """
    Resolves widget targets from various input formats.

    Supports:
        - Direct QWidget reference (passthrough)
        - objectName string lookup via findChild()
        - CSS-like selector: "ClassName#objectName"

    Usage:
        targeter = WidgetTargeter(main_window)
        widget = targeter.resolve("my_button")  # Find by objectName
        widget = targeter.resolve(self.button)  # Direct reference
    """

    def __init__(self, root: QWidget):
        """
        Initialize targeter with root widget for lookups.

        Args:
            root: Root widget (usually main window) for findChild calls.
        """
        self._root = root
        self._cache: dict[str, QWidget] = {}

    @property
    def root(self) -> QWidget:
        """Get the root widget used for lookups."""
        return self._root

    def resolve(self, target: str | QWidget) -> QWidget | None:
        """
        Resolve a target to a QWidget.

        Args:
            target: Widget reference or identifier string.
                    - QWidget: returned directly
                    - str: looked up by objectName
                    - "ClassName#objectName": looked up by class and name

        Returns:
            QWidget if found, None otherwise.
        """
        # Import here to avoid module-level PySide6 dependency
        from PySide6.QtWidgets import QWidget

        # Direct widget reference - passthrough
        if isinstance(target, QWidget):
            return target

        # String-based lookup
        if isinstance(target, str):
            # Check cache first
            if target in self._cache:
                cached = self._cache[target]
                # Verify widget still exists (not deleted)
                try:
                    cached.objectName()  # Will raise if deleted
                    return cached
                except RuntimeError:
                    del self._cache[target]

            # CSS-like selector: "ClassName#objectName"
            if "#" in target:
                class_name, obj_name = target.split("#", 1)
                widget = self._find_by_class_and_name(class_name, obj_name)
            else:
                # Simple objectName lookup
                widget = self._find_by_object_name(target)

            if widget:
                self._cache[target] = widget
            return widget

        logger.warning(f"Invalid target type: {type(target)}")
        return None

    def _find_by_object_name(self, name: str) -> QWidget | None:
        """
        Find widget by objectName using findChild.

        Args:
            name: The objectName to search for.

        Returns:
            QWidget if found, None otherwise.
        """
        from PySide6.QtWidgets import QWidget

        widget = self._root.findChild(QWidget, name)
        if widget is None:
            logger.debug(f"Widget not found by objectName: {name}")
        return widget

    def _find_by_class_and_name(
        self, class_name: str, obj_name: str
    ) -> QWidget | None:
        """
        Find widget by class type and objectName.

        Args:
            class_name: The widget class name (e.g., "QPushButton").
            obj_name: The objectName to search for.

        Returns:
            QWidget if found, None otherwise.
        """
        from PySide6.QtWidgets import QWidget

        # Find all widgets with the objectName
        widget = self._root.findChild(QWidget, obj_name)
        if widget is None:
            logger.debug(f"Widget not found: {class_name}#{obj_name}")
            return None

        # Verify class name matches
        if widget.__class__.__name__ == class_name:
            return widget

        # Class name doesn't match - might be a subclass, check inheritance
        for cls in widget.__class__.__mro__:
            if cls.__name__ == class_name:
                return widget

        logger.debug(
            f"Widget found but class mismatch: expected {class_name}, "
            f"got {widget.__class__.__name__}"
        )
        return None

    def get_widget_geometry(self, widget: QWidget) -> QRect:
        """
        Get widget geometry in global (screen) coordinates.

        Args:
            widget: The widget to get geometry for.

        Returns:
            QRect in global coordinates.
        """
        from PySide6.QtCore import QRect

        # Get widget's local geometry
        local_rect = widget.rect()

        # Map top-left to global coordinates
        global_top_left = widget.mapToGlobal(local_rect.topLeft())

        return QRect(global_top_left, local_rect.size())

    def is_widget_visible(self, widget: QWidget) -> bool:
        """
        Check if widget is visible and onscreen.

        Args:
            widget: The widget to check.

        Returns:
            True if widget is visible and has nonzero size.
        """
        if not widget.isVisible():
            return False

        rect = widget.rect()
        return rect.width() > 0 and rect.height() > 0

    def clear_cache(self):
        """Clear the widget lookup cache."""
        self._cache.clear()
