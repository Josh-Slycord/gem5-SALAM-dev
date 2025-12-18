# ==============================================================================
# stats_parser.py - Simulation Statistics Parser
# ==============================================================================
"""Parser for gem5-SALAM Simulation Statistics.

This module provides parsers for extracting performance metrics, power
consumption, and area data from gem5-SALAM simulation output files.
Supports multiple output formats including CSV, JSON, and plain text.

Supported File Formats:
    | Format     | Extension | Detection         | Example                |
    |------------|-----------|-------------------|------------------------|
    | JSON       | .json     | File extension    | test_results.json      |
    | CSV        | .txt      | "StatsStart:" tag | stats.txt with CSV     |
    | Plain Text | .txt      | Fallback          | key: value pairs       |

Data Classes:
    - SimulationStats: Top-level container for all statistics
    - PerformanceMetrics: Cycles, stalls, timing
    - FunctionalUnitStats: FU utilization data
    - PowerStats: Power consumption breakdown
    - AreaStats: Silicon area breakdown

Metrics Extracted::

    Performance:
        - total_cycles: Total simulation cycles
        - stalls: Total stall cycles
        - stall_percentage: Computed stall ratio
        - load_stalls, store_stalls, compute_stalls: Breakdown

    Power (mW):
        - fu_leakage, fu_dynamic, fu_total
        - register_leakage, register_dynamic, register_total
        - spm_total, cache_total, total_power

    Area (um²):
        - fu_area, register_area, spm_area
        - cache_area, total_area

Example:
    Parsing simulation statistics::

        from salam_gui.data.stats_parser import parse_stats_output
        from pathlib import Path

        # Parse stats file
        stats = parse_stats_output(Path("m5out/stats.txt"))

        # Access performance metrics
        print(f"Total cycles: {stats.performance.total_cycles}")
        print(f"Stall %: {stats.performance.stall_percentage:.1f}%")

        # Access power metrics
        print(f"Total power: {stats.power.total_power:.2f} mW")

        # Format for display
        from salam_gui.data.stats_parser import format_cycles, format_power
        print(format_cycles(stats.performance.total_cycles))  # "1.5M"
        print(format_power(stats.power.total_power))  # "45.67 mW"

Helper Functions:
    - format_cycles(): Convert cycle count to human-readable (K, M)
    - format_power(): Convert mW to appropriate units (uW, mW, W)
    - format_area(): Convert um² to mm² when appropriate

See Also:
    - stats_dashboard: Visualizes parsed statistics
    - comparison: Compares stats from multiple runs
    - hw_statistics.cc: C++ side statistics collection
"""


__version__ = "3.0.0.pre[1.0.0]"

import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class PerformanceMetrics:
    """Core performance metrics."""
    total_cycles: int = 0
    setup_time: float = 0.0
    sim_time: float = 0.0
    stalls: int = 0
    stall_percentage: float = 0.0
    nodes_executed: int = 0

    # Stall breakdown
    load_stalls: int = 0
    store_stalls: int = 0
    compute_stalls: int = 0
    combined_stalls: int = 0


@dataclass
class FunctionalUnitStats:
    """Functional unit utilization statistics."""
    name: str
    count: int = 0
    max_occupancy: int = 0
    avg_occupancy: float = 0.0
    utilization: float = 0.0


@dataclass
class PowerStats:
    """Power consumption statistics."""
    fu_leakage: float = 0.0
    fu_dynamic: float = 0.0
    fu_total: float = 0.0
    register_leakage: float = 0.0
    register_dynamic: float = 0.0
    register_total: float = 0.0
    spm_total: float = 0.0
    cache_total: float = 0.0
    total_power: float = 0.0


@dataclass
class AreaStats:
    """Area statistics in um^2."""
    fu_area: float = 0.0
    register_area: float = 0.0
    spm_area: float = 0.0
    cache_area: float = 0.0
    total_area: float = 0.0


@dataclass
class SimulationStats:
    """Container for all simulation statistics."""
    benchmark: str = ""
    performance: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    functional_units: List[FunctionalUnitStats] = field(default_factory=list)
    power: PowerStats = field(default_factory=PowerStats)
    area: AreaStats = field(default_factory=AreaStats)
    raw_data: Dict[str, Any] = field(default_factory=dict)


def parse_stats_output(file_path: Path) -> SimulationStats:
    """
    Parse gem5-SALAM statistics from output file.

    Handles multiple formats:
    - StatsStart: CSV format
    - JSON format
    - Plain text with key: value pairs

    Args:
        file_path: Path to statistics file

    Returns:
        SimulationStats containing parsed data
    """
    content = file_path.read_text()
    stats = SimulationStats()

    # Try JSON format first
    if file_path.suffix == '.json':
        return _parse_json_stats(content, stats)

    # Try to find CSV section
    if 'StatsStart:' in content:
        return _parse_csv_stats(content, stats)

    # Fall back to text parsing
    return _parse_text_stats(content, stats)


def _parse_json_stats(content: str, stats: SimulationStats) -> SimulationStats:
    """Parse JSON format statistics."""
    try:
        data = json.loads(content)
        stats.raw_data = data

        # Extract known fields
        if 'benchmark' in data:
            stats.benchmark = data['benchmark']

        if 'summary' in data:
            summary = data['summary']
            stats.performance.total_cycles = summary.get('total_cycles', 0)
            stats.performance.stalls = summary.get('stalls', 0)

        if 'results' in data:
            # Handle test results format
            for bench, result in data['results'].items():
                if result.get('passed'):
                    stats.benchmark = bench

    except json.JSONDecodeError:
        pass

    return stats


def _parse_csv_stats(content: str, stats: SimulationStats) -> SimulationStats:
    """Parse StatsStart: CSV format."""
    # Find the CSV section
    csv_match = re.search(r'StatsStart:(.+?)(?:StatsEnd|$)', content, re.DOTALL)
    if not csv_match:
        return stats

    csv_content = csv_match.group(1).strip()
    lines = csv_content.split('\n')

    for line in lines:
        parts = line.strip().split(',')
        if len(parts) >= 2:
            key = parts[0].strip()
            value = parts[1].strip()

            stats.raw_data[key] = value

            # Map known fields
            if 'cycle' in key.lower():
                try:
                    stats.performance.total_cycles = int(value)
                except ValueError:
                    pass
            elif 'stall' in key.lower():
                try:
                    stats.performance.stalls = int(value)
                except ValueError:
                    pass

    return stats


def _parse_text_stats(content: str, stats: SimulationStats) -> SimulationStats:
    """Parse plain text statistics with key: value format."""
    # Common patterns in gem5 output
    patterns = {
        'cycles': r'(?:total\s*)?cycles?\s*[=:]\s*(\d+)',
        'stalls': r'stalls?\s*[=:]\s*(\d+)',
        'sim_time': r'sim(?:ulation)?\s*time\s*[=:]\s*([\d.]+)',
        'setup_time': r'setup\s*time\s*[=:]\s*([\d.]+)',
        'power': r'total\s*power\s*[=:]\s*([\d.]+)',
        'area': r'total\s*area\s*[=:]\s*([\d.]+)',
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            value = match.group(1)
            stats.raw_data[key] = value

            if key == 'cycles':
                stats.performance.total_cycles = int(value)
            elif key == 'stalls':
                stats.performance.stalls = int(value)
            elif key == 'sim_time':
                stats.performance.sim_time = float(value)
            elif key == 'setup_time':
                stats.performance.setup_time = float(value)
            elif key == 'power':
                stats.power.total_power = float(value)
            elif key == 'area':
                stats.area.total_area = float(value)

    # Calculate stall percentage
    if stats.performance.total_cycles > 0:
        stats.performance.stall_percentage = (
            stats.performance.stalls / stats.performance.total_cycles * 100
        )

    return stats


def format_cycles(cycles: int) -> str:
    """Format cycle count for display."""
    if cycles >= 1_000_000:
        return f"{cycles / 1_000_000:.2f}M"
    elif cycles >= 1_000:
        return f"{cycles / 1_000:.1f}K"
    return str(cycles)


def format_power(mw: float) -> str:
    """Format power in appropriate units."""
    if mw >= 1000:
        return f"{mw / 1000:.2f} W"
    elif mw >= 1:
        return f"{mw:.2f} mW"
    else:
        return f"{mw * 1000:.1f} uW"


def format_area(um2: float) -> str:
    """Format area in appropriate units."""
    mm2 = um2 / 1_000_000
    if mm2 >= 1:
        return f"{mm2:.3f} mm²"
    else:
        return f"{um2:.0f} um²"
