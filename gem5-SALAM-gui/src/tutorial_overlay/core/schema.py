"""
Tutorial Overlay - Schema Definitions
=====================================

Dataclasses and enums for defining tutorial steps and configurations.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ArrowPosition(Enum):
    """Position of tooltip arrow relative to target widget."""

    TOP = "top"  # Arrow points down, tooltip above target
    BOTTOM = "bottom"  # Arrow points up, tooltip below target
    LEFT = "left"  # Arrow points right, tooltip left of target
    RIGHT = "right"  # Arrow points left, tooltip right of target
    AUTO = "auto"  # Automatically determine best position


class HighlightStyle(Enum):
    """Style of target widget highlighting."""

    SPOTLIGHT = "spotlight"  # Dim everything except target
    BORDER = "border"  # Add glowing border around target
    PULSE = "pulse"  # Pulsing glow effect on target
    NONE = "none"  # No highlighting


@dataclass
class TutorialStep:
    """
    Definition of a single tutorial step.

    Attributes:
        target: Widget reference (QWidget) or objectName string for lookup.
        title: Step title displayed in tooltip header.
        content: Step description/instructions displayed in tooltip body.
        arrow_position: Where tooltip arrow points from (default: AUTO).
        highlight_style: How to highlight the target (default: SPOTLIGHT).
        padding: Extra padding around target in spotlight cutout (default: 8px).
        wait_for: Optional event name to wait for before allowing next step.
                  Examples: "click", "node_added", "connection_made", "any".
        on_enter: Optional callback function name when step is entered.
        on_exit: Optional callback function name when step is exited.
    """

    target: str | Any  # str (objectName) or QWidget reference
    title: str
    content: str
    arrow_position: ArrowPosition = ArrowPosition.AUTO
    highlight_style: HighlightStyle = HighlightStyle.SPOTLIGHT
    padding: int = 8
    wait_for: str | None = None
    on_enter: str | Callable | None = None
    on_exit: str | Callable | None = None


@dataclass
class TutorialDefinition:
    """
    Complete tutorial definition with metadata.

    Attributes:
        id: Unique tutorial identifier (used for tracking completion).
        name: Human-readable tutorial name.
        steps: List of TutorialStep objects defining the tutorial flow.
        description: Optional tutorial purpose/overview.
        version: Tutorial version for update tracking (default: "1.0.0").
        can_skip: Whether users can skip the tutorial (default: True).
        show_progress: Show step progress indicator like "2/5" (default: True).
        metadata: Optional dictionary for custom metadata.
    """

    id: str
    name: str
    steps: list[TutorialStep]
    description: str = ""
    version: str = "1.0.0"
    can_skip: bool = True
    show_progress: bool = True
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        """Validate tutorial definition."""
        if not self.id:
            raise ValueError("Tutorial id cannot be empty")
        if not self.name:
            raise ValueError("Tutorial name cannot be empty")
        if not self.steps:
            raise ValueError("Tutorial must have at least one step")
