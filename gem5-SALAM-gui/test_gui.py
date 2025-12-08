#!/usr/bin/env python3
"""Minimal GUI test."""
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel

app = QApplication(sys.argv)
window = QMainWindow()
window.setWindowTitle("Test")
window.setCentralWidget(QLabel("GUI Works!"))
window.resize(400, 200)
window.show()
print("GUI started successfully")
sys.exit(app.exec())
