"""
Tutorial Overlay - Step Navigator Widget
========================================

Navigation controls for tutorial steps (Back/Next/Skip/Close).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class StepNavigator(QWidget):
    """
    Navigation controls for tutorial steps.

    Provides:
        - Back button (disabled on first step)
        - Next button (changes to "Finish" on last step)
        - Skip button (optional, based on tutorial settings)
        - Progress indicator (e.g., "2 / 5")

    Signals:
        next_clicked: User clicked Next/Finish button.
        back_clicked: User clicked Back button.
        skip_clicked: User clicked Skip button.

    Usage:
        nav = StepNavigator()
        nav.update_state(current=0, total=5, can_skip=True)
        nav.next_clicked.connect(on_next)
    """

    next_clicked = Signal()
    back_clicked = Signal()
    skip_clicked = Signal()

    # Style constants
    BUTTON_BG = "#3d3d3d"
    BUTTON_HOVER = "#4d4d4d"
    BORDER_COLOR = "#555555"
    TEXT_COLOR = "#dddddd"
    ACCENT_COLOR = "#4a90d9"

    def __init__(self, parent: QWidget | None = None):
        """
        Initialize the navigator widget.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)

        self._current_step = 0
        self._total_steps = 1
        self._can_skip = True
        self._show_progress = True

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        """Create the navigation UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Skip button (left side)
        self._skip_btn = QPushButton("Skip Tutorial")
        self._skip_btn.setObjectName("nav_skip")
        self._skip_btn.clicked.connect(self.skip_clicked.emit)
        layout.addWidget(self._skip_btn)

        layout.addStretch()

        # Progress label (center)
        self._progress_label = QLabel()
        self._progress_label.setObjectName("nav_progress")
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._progress_label)

        layout.addStretch()

        # Back button
        self._back_btn = QPushButton("Back")
        self._back_btn.setObjectName("nav_back")
        self._back_btn.clicked.connect(self.back_clicked.emit)
        layout.addWidget(self._back_btn)

        # Next button
        self._next_btn = QPushButton("Next")
        self._next_btn.setObjectName("nav_next")
        self._next_btn.clicked.connect(self.next_clicked.emit)
        layout.addWidget(self._next_btn)

    def _apply_style(self):
        """Apply dark theme styling."""
        self.setStyleSheet(
            f"""
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
            QPushButton:disabled {{
                background-color: #2d2d2d;
                color: #666666;
                border-color: #444444;
            }}
            #nav_next {{
                background-color: {self.ACCENT_COLOR};
                border-color: {self.ACCENT_COLOR};
                color: white;
            }}
            #nav_next:hover {{
                background-color: #5a9fe9;
            }}
            #nav_skip {{
                background: transparent;
                border: none;
                color: #888888;
                min-width: 80px;
            }}
            #nav_skip:hover {{
                color: {self.TEXT_COLOR};
            }}
            #nav_progress {{
                color: #888888;
                font-size: 11px;
            }}
        """
        )

    def update_state(
        self,
        current: int,
        total: int,
        can_skip: bool = True,
        show_progress: bool = True,
    ):
        """
        Update navigator state for current step.

        Args:
            current: Current step index (0-based).
            total: Total number of steps.
            can_skip: Whether skip button is visible.
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

        # Update skip button visibility
        self._skip_btn.setVisible(can_skip)

        # Update back button (disabled on first step)
        self._back_btn.setEnabled(current > 0)

        # Update next button text
        is_last = current >= total - 1
        self._next_btn.setText("Finish" if is_last else "Next")

    @property
    def current_step(self) -> int:
        """Get current step index."""
        return self._current_step

    @property
    def total_steps(self) -> int:
        """Get total number of steps."""
        return self._total_steps

    @property
    def is_first_step(self) -> bool:
        """Check if on first step."""
        return self._current_step == 0

    @property
    def is_last_step(self) -> bool:
        """Check if on last step."""
        return self._current_step >= self._total_steps - 1

    def set_next_enabled(self, enabled: bool):
        """Enable/disable next button (for wait_for conditions)."""
        self._next_btn.setEnabled(enabled)

    def set_back_enabled(self, enabled: bool):
        """Enable/disable back button."""
        self._back_btn.setEnabled(enabled)
