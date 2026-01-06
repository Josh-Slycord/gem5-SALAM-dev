"""
Tutorial Overlay System for PySide6
===================================

A full-featured tutorial/onboarding system for PySide6 applications providing:
- Spotlight/highlight effects to focus user attention
- Step-by-step guided tours with navigation
- Tooltips with arrow pointers
- Widget targeting by reference or objectName

Usage:
    from src.tutorial_overlay import TutorialManager, TutorialStep

    # Initialize with your main window
    manager = TutorialManager(main_window)

    # Load from YAML file
    manager.load_tutorial("tutorials/getting_started.yaml")
    manager.start()

    # Or define programmatically
    from src.tutorial_overlay import TutorialDefinition, ArrowPosition

    tutorial = TutorialDefinition(
        id="quick_tour",
        name="Quick Tour",
        steps=[
            TutorialStep(
                target="my_button",  # objectName lookup
                title="Click Here",
                content="This button does something.",
            ),
            TutorialStep(
                target=self.save_button,  # Direct widget reference
                title="Save",
                content="Save your work here.",
                arrow_position=ArrowPosition.LEFT,
            ),
        ]
    )
    manager.register_tutorial(tutorial)
    manager.start("quick_tour")
"""

from .core.schema import (
    ArrowPosition,
    HighlightStyle,
    TutorialDefinition,
    TutorialStep,
)

__version__ = "1.0.0"
__author__ = "Slycord"

__all__ = [
    # Core schema
    "ArrowPosition",
    "HighlightStyle",
    "TutorialStep",
    "TutorialDefinition",
]


def __getattr__(name: str):
    """Lazy import for heavier components to avoid import-time PySide6 dependency."""
    if name == "TutorialManager":
        from .core.manager import TutorialManager

        return TutorialManager
    if name == "WidgetTargeter":
        from .core.targeting import WidgetTargeter

        return WidgetTargeter
    if name == "SpotlightOverlay":
        from .widgets.spotlight import SpotlightOverlay

        return SpotlightOverlay
    if name == "TooltipWidget":
        from .widgets.tooltip import TooltipWidget

        return TooltipWidget
    if name == "StepNavigator":
        from .widgets.navigator import StepNavigator

        return StepNavigator
    if name == "HighlightPulse":
        from .animations.pulse import HighlightPulse

        return HighlightPulse
    if name == "load_tutorial":
        from .loaders.yaml_loader import load_tutorial

        return load_tutorial
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
