"""
Tutorial Overlay - Tutorial Manager
===================================

Main controller for tutorial overlays. Orchestrates spotlight,
tooltip, and navigation components.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from ..animations.pulse import HighlightPulse
from ..widgets.spotlight import SpotlightOverlay
from ..widgets.tooltip import TooltipWidget
from .schema import (
    ArrowPosition,
    HighlightStyle,
    TutorialDefinition,
    TutorialStep,
)
from .targeting import WidgetTargeter

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TutorialManager(QObject):
    """
    Main controller for tutorial overlays.

    Orchestrates the spotlight overlay, tooltip widget, and navigation
    to provide a complete tutorial experience.

    Signals:
        tutorial_started(str): Emitted when a tutorial starts (tutorial ID).
        step_changed(int, TutorialStep): Emitted when step changes (index, step).
        tutorial_completed(str): Emitted when tutorial completes (tutorial ID).
        tutorial_cancelled(str): Emitted when tutorial is skipped/cancelled.
        step_skipped(int, str): Emitted when a step is skipped (index, reason).

    Usage:
        manager = TutorialManager(main_window)
        manager.load_tutorial("tutorials/getting_started.yaml")
        manager.start()
    """

    # Signals
    tutorial_started = Signal(str)
    step_changed = Signal(int, object)  # (index, TutorialStep)
    tutorial_completed = Signal(str)
    tutorial_cancelled = Signal(str)
    step_skipped = Signal(int, str)  # (index, reason)

    def __init__(self, parent: QWidget):
        """
        Initialize the tutorial manager.

        Args:
            parent: Parent widget (usually the main window).
                   Used as root for widget lookups and overlay parenting.
        """
        super().__init__(parent)

        self._parent = parent
        self._targeter = WidgetTargeter(parent)

        # Tutorial state
        self._tutorials: dict[str, TutorialDefinition] = {}
        self._current_tutorial: TutorialDefinition | None = None
        self._current_index: int = 0
        self._running: bool = False

        # Configuration
        self._skip_missing: bool = True  # Skip steps with missing widgets

        # UI components (created on demand)
        self._spotlight: SpotlightOverlay | None = None
        self._tooltip: TooltipWidget | None = None
        self._pulse: HighlightPulse | None = None

    @property
    def is_running(self) -> bool:
        """Check if a tutorial is currently running."""
        return self._running

    @property
    def current_step(self) -> TutorialStep | None:
        """Get the current step, or None if not running."""
        if not self._running or not self._current_tutorial:
            return None
        if 0 <= self._current_index < len(self._current_tutorial.steps):
            return self._current_tutorial.steps[self._current_index]
        return None

    @property
    def current_index(self) -> int:
        """Get current step index (0-based)."""
        return self._current_index

    @property
    def total_steps(self) -> int:
        """Get total number of steps in current tutorial."""
        if self._current_tutorial:
            return len(self._current_tutorial.steps)
        return 0

    @property
    def skip_missing_widgets(self) -> bool:
        """Get whether to skip steps with missing widgets."""
        return self._skip_missing

    @skip_missing_widgets.setter
    def skip_missing_widgets(self, skip: bool):
        """Set whether to skip steps with missing widgets."""
        self._skip_missing = skip

    def load_tutorial(self, path: str | Path) -> TutorialDefinition:
        """
        Load a tutorial from a YAML or JSON file.

        Args:
            path: Path to tutorial definition file.

        Returns:
            The loaded TutorialDefinition.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file format is invalid.
        """
        from ..loaders.yaml_loader import load_tutorial

        tutorial = load_tutorial(Path(path))
        self.register_tutorial(tutorial)
        return tutorial

    def load_from_dict(self, data: dict) -> TutorialDefinition:
        """
        Load a tutorial from a dictionary.

        Args:
            data: Dictionary with tutorial definition.

        Returns:
            The created TutorialDefinition.
        """
        # Convert step dicts to TutorialStep objects
        steps = []
        for step_data in data.get("steps", []):
            step = TutorialStep(
                target=step_data["target"],
                title=step_data.get("title", ""),
                content=step_data.get("content", ""),
                arrow_position=ArrowPosition(
                    step_data.get("arrow_position", "auto")
                ),
                highlight_style=HighlightStyle(
                    step_data.get("highlight_style", "spotlight")
                ),
                padding=step_data.get("padding", 8),
                wait_for=step_data.get("wait_for"),
            )
            steps.append(step)

        tutorial = TutorialDefinition(
            id=data["id"],
            name=data.get("name", data["id"]),
            steps=steps,
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            can_skip=data.get("can_skip", True),
            show_progress=data.get("show_progress", True),
            metadata=data.get("metadata", {}),
        )

        self.register_tutorial(tutorial)
        return tutorial

    def register_tutorial(self, tutorial: TutorialDefinition):
        """
        Register a tutorial definition for later use.

        Args:
            tutorial: Tutorial definition to register.
        """
        self._tutorials[tutorial.id] = tutorial
        logger.debug(
            f"Registered tutorial: {tutorial.id} ({len(tutorial.steps)} steps)"
        )

    def add_step(self, step: TutorialStep):
        """
        Add a step to the current/default tutorial.

        Convenience method for programmatic tutorial building.

        Args:
            step: Step to add.
        """
        # Create default tutorial if none exists
        if "_default" not in self._tutorials:
            self._tutorials["_default"] = TutorialDefinition(
                id="_default",
                name="Tutorial",
                steps=[],
            )
        self._tutorials["_default"].steps.append(step)

    def start(self, tutorial_id: str | None = None):
        """
        Start a tutorial.

        Args:
            tutorial_id: ID of tutorial to start. If None, starts the
                        most recently loaded/registered tutorial.
        """
        # Get tutorial
        if tutorial_id:
            if tutorial_id not in self._tutorials:
                raise ValueError(f"Tutorial not found: {tutorial_id}")
            self._current_tutorial = self._tutorials[tutorial_id]
        elif self._tutorials:
            # Use most recently added
            self._current_tutorial = list(self._tutorials.values())[-1]
        else:
            raise ValueError("No tutorials registered")

        if not self._current_tutorial.steps:
            logger.warning(
                f"Tutorial {self._current_tutorial.id} has no steps"
            )
            return

        # Initialize state
        self._current_index = 0
        self._running = True

        # Create UI components
        self._create_ui_components()

        # Emit started signal
        self.tutorial_started.emit(self._current_tutorial.id)

        # Show first step
        self._show_current_step()

    def _create_ui_components(self):
        """Create spotlight and tooltip if not already created."""
        if self._spotlight is None:
            self._spotlight = SpotlightOverlay(self._parent)
            self._spotlight.overlay_clicked.connect(self._on_overlay_clicked)

        if self._tooltip is None:
            self._tooltip = TooltipWidget(self._parent)
            self._tooltip.next_clicked.connect(self.next_step)
            self._tooltip.back_clicked.connect(self.previous_step)
            self._tooltip.skip_clicked.connect(self.skip)
            self._tooltip.close_clicked.connect(self.stop)

    def _show_current_step(self):
        """Display the current step."""
        if not self._current_tutorial or not self._running:
            return

        step = self.current_step
        if step is None:
            self._complete()
            return

        # Resolve target widget
        widget = self._targeter.resolve(step.target)

        if widget is None:
            logger.warning(f"Target not found: {step.target}")
            if self._skip_missing:
                self.step_skipped.emit(self._current_index, "target_not_found")
                self._advance_step(1)
                return
            else:
                # Show tooltip centered with warning
                self._show_centered_tooltip(step)
                return

        # Stop any existing pulse
        if self._pulse:
            self._pulse.stop()
            self._pulse = None

        # Apply highlight style
        if step.highlight_style == HighlightStyle.SPOTLIGHT:
            self._spotlight.set_target(widget, step.padding)
            self._spotlight.show()
        elif step.highlight_style == HighlightStyle.PULSE:
            self._spotlight.clear_target()
            self._spotlight.show()
            self._pulse = HighlightPulse(widget, parent=self)
            self._pulse.start()
        elif step.highlight_style == HighlightStyle.BORDER:
            self._spotlight.clear_target()
            self._spotlight.show()
            # Border handled by spotlight with show_border
            self._spotlight.set_target(widget, step.padding)
        else:  # NONE
            self._spotlight.clear_target()
            self._spotlight.show()

        # Position tooltip
        target_rect = self._targeter.get_widget_geometry(widget)
        self._tooltip.set_content(step.title, step.content)
        self._tooltip.set_progress(
            self._current_index,
            len(self._current_tutorial.steps),
            self._current_tutorial.can_skip,
            self._current_tutorial.show_progress,
        )
        self._tooltip.point_to(target_rect, step.arrow_position)
        self._tooltip.show()
        self._tooltip.raise_()

        # Emit step changed
        self.step_changed.emit(self._current_index, step)

    def _show_centered_tooltip(self, step: TutorialStep):
        """Show tooltip centered (fallback when widget not found)."""
        self._spotlight.clear_target()
        self._spotlight.show()

        content = f"[Target not found: {step.target}]\n\n{step.content}"
        self._tooltip.set_content(step.title, content)
        self._tooltip.set_progress(
            self._current_index,
            len(self._current_tutorial.steps),
            self._current_tutorial.can_skip,
            self._current_tutorial.show_progress,
        )
        self._tooltip.show_centered()

    def next_step(self):
        """Advance to the next step."""
        self._advance_step(1)

    def previous_step(self):
        """Go back to the previous step."""
        self._advance_step(-1)

    def go_to_step(self, index: int):
        """
        Jump to a specific step.

        Args:
            index: Step index (0-based).
        """
        if not self._running or not self._current_tutorial:
            return

        if 0 <= index < len(self._current_tutorial.steps):
            self._current_index = index
            self._show_current_step()

    def _advance_step(self, delta: int):
        """Advance step by delta (positive or negative)."""
        if not self._running or not self._current_tutorial:
            return

        new_index = self._current_index + delta

        if new_index < 0:
            new_index = 0
        elif new_index >= len(self._current_tutorial.steps):
            self._complete()
            return

        self._current_index = new_index
        self._show_current_step()

    def skip(self):
        """Skip/cancel the current tutorial."""
        if not self._running:
            return

        tutorial_id = (
            self._current_tutorial.id if self._current_tutorial else ""
        )
        self._cleanup()
        self.tutorial_cancelled.emit(tutorial_id)

    def stop(self):
        """Stop the tutorial and clean up."""
        self.skip()

    def _complete(self):
        """Complete the tutorial successfully."""
        tutorial_id = (
            self._current_tutorial.id if self._current_tutorial else ""
        )
        self._cleanup()
        self.tutorial_completed.emit(tutorial_id)

    def _cleanup(self):
        """Clean up UI components."""
        self._running = False

        if self._pulse:
            self._pulse.stop()
            self._pulse = None

        if self._spotlight:
            self._spotlight.hide()

        if self._tooltip:
            self._tooltip.hide()

        self._current_tutorial = None
        self._current_index = 0

    def _on_overlay_clicked(self):
        """Handle click on dimmed overlay area."""
        # Could advance to next step or show hint
        pass

    def get_tutorial(self, tutorial_id: str) -> TutorialDefinition | None:
        """Get a registered tutorial by ID."""
        return self._tutorials.get(tutorial_id)

    def list_tutorials(self) -> list[str]:
        """Get list of registered tutorial IDs."""
        return list(self._tutorials.keys())
