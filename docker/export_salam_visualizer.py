#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Compatibility entry point; the maintained exporter lives in workbench/."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    target = (
        Path(__file__).resolve().parents[1]
        / "workbench"
        / "visualizer"
        / "export_salam_visualizer.py"
    )
    runpy.run_path(str(target), run_name="__main__")
