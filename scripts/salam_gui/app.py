# ==============================================================================
# app.py - PySide6 Application Setup
# ==============================================================================
"""PySide6 Application Setup for gem5-SALAM GUI.

This module provides the SALAMGuiApp class, which is the main QApplication
subclass for the gem5-SALAM visualization tool. It handles:

- Application metadata (name, version, organization)
- Theme management (light/dark mode)
- Global style settings (Fusion style)

Theme Architecture::

    SALAMGuiApp
    +-- Light Theme (default): System palette
    +-- Dark Theme: Custom dark palette
        +-- Base colors: #2D2D2D (dark), #232323 (darker)
        +-- Text colors: #C8C8C8 (light gray)
        +-- Accent colors: #2A82DA (highlight blue)

Example:
    Basic application startup::

        from salam_gui.app import SALAMGuiApp
        from salam_gui.main_window import MainWindow

        app = SALAMGuiApp(sys.argv)
        app.set_dark_theme()  # Optional

        window = MainWindow()
        window.show()
        sys.exit(app.exec())

See Also:
    - MainWindow: Main application window
    - __main__.py: Entry point that creates SALAMGuiApp
"""


__version__ = "3.0.0.pre[1.0.0]"

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt


class SALAMGuiApp(QApplication):
    """Main application class with theming support."""

    def __init__(self, argv):
        super().__init__(argv)
        self.setApplicationName("gem5-SALAM GUI")
        self.setApplicationVersion("0.1.0")
        self.setOrganizationName("gem5-SALAM")

        # Set default style
        self.setStyle("Fusion")

    def set_dark_theme(self):
        """Apply dark theme to the application."""
        palette = QPalette()

        # Base colors
        dark = QColor(45, 45, 45)
        darker = QColor(35, 35, 35)
        light = QColor(200, 200, 200)
        highlight = QColor(42, 130, 218)

        palette.setColor(QPalette.ColorRole.Window, dark)
        palette.setColor(QPalette.ColorRole.WindowText, light)
        palette.setColor(QPalette.ColorRole.Base, darker)
        palette.setColor(QPalette.ColorRole.AlternateBase, dark)
        palette.setColor(QPalette.ColorRole.ToolTipBase, dark)
        palette.setColor(QPalette.ColorRole.ToolTipText, light)
        palette.setColor(QPalette.ColorRole.Text, light)
        palette.setColor(QPalette.ColorRole.Button, dark)
        palette.setColor(QPalette.ColorRole.ButtonText, light)
        palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorRole.Link, highlight)
        palette.setColor(QPalette.ColorRole.Highlight, highlight)
        palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)

        self.setPalette(palette)

    def set_light_theme(self):
        """Reset to default light theme."""
        self.setPalette(self.style().standardPalette())
