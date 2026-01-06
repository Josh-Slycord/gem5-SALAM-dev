"""
Tutorial Overlay - Core Module
==============================

Core types, schema, and management classes.
"""

from .schema import (
    ArrowPosition,
    HighlightStyle,
    TutorialDefinition,
    TutorialStep,
)
from .targeting import WidgetTargeter

# TutorialManager is lazy-loaded to avoid circular imports
# Use: from tutorial_overlay.core.manager import TutorialManager

__all__ = [
    "ArrowPosition",
    "HighlightStyle",
    "TutorialStep",
    "TutorialDefinition",
    "WidgetTargeter",
]
