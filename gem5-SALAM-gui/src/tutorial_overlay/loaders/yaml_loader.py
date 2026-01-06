"""
Tutorial Overlay - YAML Loader
==============================

Load tutorial definitions from YAML files.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from ..core.schema import (
    ArrowPosition,
    HighlightStyle,
    TutorialDefinition,
    TutorialStep,
)

logger = logging.getLogger(__name__)


def load_tutorial(path: Path) -> TutorialDefinition:
    """
    Load a tutorial definition from a YAML or JSON file.

    Args:
        path: Path to the tutorial file (.yaml, .yml, or .json).

    Returns:
        TutorialDefinition loaded from the file.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If file format is invalid or missing required fields.

    Example YAML format:
        ```yaml
        id: "getting_started"
        name: "Getting Started"
        description: "Learn the basics"
        version: "1.0.0"
        can_skip: true
        show_progress: true

        steps:
          - target: "tool_palette"
            title: "Tool Palette"
            content: "Drag nodes from here to the canvas."
            arrow_position: "right"
            highlight_style: "spotlight"
            padding: 10

          - target: "pipeline_canvas"
            title: "Canvas"
            content: "Build your pipeline here."
            arrow_position: "left"
            wait_for: "node_added"
        ```
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Tutorial file not found: {path}")

    # Load file content
    content = path.read_text(encoding="utf-8")

    # Parse based on extension
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        data = yaml.safe_load(content)
    elif suffix == ".json":
        data = json.loads(content)
    else:
        # Try YAML first, then JSON
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            data = json.loads(content)

    if not isinstance(data, dict):
        raise ValueError(
            f"Invalid tutorial file format: expected dict, got {type(data)}"
        )

    return _parse_tutorial(data, source_path=path)


def _parse_tutorial(
    data: dict, source_path: Path | None = None
) -> TutorialDefinition:
    """
    Parse tutorial data dictionary into TutorialDefinition.

    Args:
        data: Dictionary with tutorial data.
        source_path: Optional source path for error messages.

    Returns:
        TutorialDefinition object.
    """
    # Validate required fields
    if "id" not in data:
        raise ValueError("Tutorial missing required field: 'id'")
    if "steps" not in data or not data["steps"]:
        raise ValueError(
            "Tutorial missing required field: 'steps' or steps is empty"
        )

    # Parse steps
    steps = []
    for i, step_data in enumerate(data["steps"]):
        try:
            step = _parse_step(step_data)
            steps.append(step)
        except Exception as e:
            source = f" in {source_path}" if source_path else ""
            raise ValueError(f"Invalid step {i}{source}: {e}") from e

    return TutorialDefinition(
        id=data["id"],
        name=data.get("name", data["id"]),
        steps=steps,
        description=data.get("description", ""),
        version=data.get("version", "1.0.0"),
        can_skip=data.get("can_skip", True),
        show_progress=data.get("show_progress", True),
        metadata=data.get("metadata", {}),
    )


def _parse_step(data: dict) -> TutorialStep:
    """
    Parse a step dictionary into TutorialStep.

    Args:
        data: Dictionary with step data.

    Returns:
        TutorialStep object.
    """
    if "target" not in data:
        raise ValueError("Step missing required field: 'target'")

    # Parse arrow position
    arrow_pos_str = data.get("arrow_position", "auto")
    try:
        arrow_position = ArrowPosition(arrow_pos_str)
    except ValueError:
        valid = [e.value for e in ArrowPosition]
        raise ValueError(
            f"Invalid arrow_position: '{arrow_pos_str}'. Valid values: {valid}"
        ) from None

    # Parse highlight style
    highlight_str = data.get("highlight_style", "spotlight")
    try:
        highlight_style = HighlightStyle(highlight_str)
    except ValueError:
        valid = [e.value for e in HighlightStyle]
        raise ValueError(
            f"Invalid highlight_style: '{highlight_str}'. Valid values: {valid}"
        ) from None

    return TutorialStep(
        target=data["target"],
        title=data.get("title", ""),
        content=data.get("content", ""),
        arrow_position=arrow_position,
        highlight_style=highlight_style,
        padding=data.get("padding", 8),
        wait_for=data.get("wait_for"),
        on_enter=data.get("on_enter"),
        on_exit=data.get("on_exit"),
    )


def save_tutorial(
    tutorial: TutorialDefinition, path: Path, format: str = "yaml"
):
    """
    Save a tutorial definition to a file.

    Args:
        tutorial: Tutorial to save.
        path: Output file path.
        format: Output format ("yaml" or "json").
    """
    data = {
        "id": tutorial.id,
        "name": tutorial.name,
        "description": tutorial.description,
        "version": tutorial.version,
        "can_skip": tutorial.can_skip,
        "show_progress": tutorial.show_progress,
        "steps": [
            {
                "target": step.target
                if isinstance(step.target, str)
                else "<widget>",
                "title": step.title,
                "content": step.content,
                "arrow_position": step.arrow_position.value,
                "highlight_style": step.highlight_style.value,
                "padding": step.padding,
                **({"wait_for": step.wait_for} if step.wait_for else {}),
            }
            for step in tutorial.steps
        ],
    }

    if tutorial.metadata:
        data["metadata"] = tutorial.metadata

    path = Path(path)

    if format == "json":
        content = json.dumps(data, indent=2)
    else:
        content = yaml.dump(data, default_flow_style=False, sort_keys=False)

    path.write_text(content, encoding="utf-8")
    logger.info(f"Saved tutorial to {path}")
