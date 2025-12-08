#!/usr/bin/env python3
"""
gem5-SALAM Installer
Main entry point for the installation GUI.
"""

import sys
import traceback
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def main():
    """Main entry point."""
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from gui.main_window import MainWindow

        # Enable high DPI scaling
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        app = QApplication(sys.argv)
        app.setApplicationName("gem5-SALAM Installer")
        app.setOrganizationName("gem5-SALAM")

        # Set application style
        app.setStyle("Fusion")

        window = MainWindow()
        window.show()

        sys.exit(app.exec())
    except Exception as e:
        # Write error to log file
        log_path = Path(__file__).parent / "crash.log"
        with open(log_path, 'w') as f:
            f.write(f"Error: {e}\n\n")
            f.write(traceback.format_exc())
        print(f"Error: {e}")
        print(f"See {log_path} for details")
        raise


if __name__ == "__main__":
    main()
