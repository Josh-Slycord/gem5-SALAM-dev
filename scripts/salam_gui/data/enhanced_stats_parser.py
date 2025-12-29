# ==============================================================================
# enhanced_stats_parser.py - Enhanced Statistics Parser for New JSON Format
# ==============================================================================
"""Parser for Enhanced gem5-SALAM Statistics JSON Format.

This module extends the stats_parser to handle the new enhanced JSON
statistics format from HWStatistics, including:
- Memory access statistics (hit/miss, latency)
- Dataflow analysis (critical path, ILP, dependencies)
- FU utilization with contention tracking
- Stall root cause breakdown
- Enhanced power/area with activity factors

The new JSON format version is 3.0 and includes nested objects for
each category of statistics.

Example JSON structure::

    {
      "salam_stats": {
        "version": "3.0",
        "accelerator_name": "matmul",
        "performance": { ... },
        "memory": { ... },
        "memory_access": { ... },
        "dataflow": { ... },
        "fu_utilization": { ... },
        "stall_breakdown": { ... },
        "power": { ... },
        "area": { ... }
      }
    }

Usage:
    # From JSON string (live stats update)
    stats = parse_enhanced_json(json_string)

    # From JSON file
    stats = load_enhanced_json(Path("salam_stats.json"))

See Also:
    - stats_parser: Base statistics parsing
    - realtime_connection: Live stats signal source
    - hw_statistics.cc: C++ side JSON generation
"""

__version__ = "3.0.0"

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional


@dataclass
class MemoryAccessMetrics:
    """Enhanced memory access statistics."""
    cache_hits: int = 0
    cache_misses: int = 0
    cache_read_hits: int = 0
    cache_read_misses: int = 0
    cache_write_hits: int = 0
    cache_write_misses: int = 0
    spm_reads: int = 0
    spm_writes: int = 0
    dma_reads: int = 0
    dma_writes: int = 0
    avg_read_latency: float = 0.0
    avg_write_latency: float = 0.0
    max_read_latency: int = 0
    max_write_latency: int = 0
    read_port_contentions: int = 0
    write_port_contentions: int = 0

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0.0


@dataclass
class DataflowMetrics:
    """Dataflow analysis metrics."""
    critical_path_length: int = 0
    critical_path_instructions: int = 0
    critical_path_loads: int = 0
    critical_path_stores: int = 0
    critical_path_computes: int = 0
    avg_ready_instructions: float = 0.0
    avg_issued_per_cycle: float = 0.0
    max_parallel_ops: int = 0
    total_instructions: int = 0
    true_dependencies: int = 0
    anti_dependencies: int = 0
    output_dependencies: int = 0
    control_dependencies: int = 0
    memory_dependencies: int = 0
    avg_dependency_depth: float = 0.0
    max_dependency_depth: int = 0
    total_dependency_edges: int = 0

    @property
    def ilp(self) -> float:
        """Instruction-Level Parallelism metric."""
        if self.critical_path_length > 0:
            return self.total_instructions / self.critical_path_length
        return 0.0

    @property
    def avg_parallelism(self) -> float:
        return self.avg_ready_instructions


@dataclass
class FUTypeUtilization:
    """Per-FU-type utilization."""
    name: str
    instances_available: int = 0
    total_operations: int = 0
    total_busy_cycles: int = 0
    contention_stalls: int = 0
    avg_utilization: float = 0.0


@dataclass
class FUUtilizationMetrics:
    """FU utilization statistics."""
    total_fu_busy_cycles: int = 0
    total_contention_stalls: int = 0
    overall_utilization: float = 0.0
    by_type: Dict[str, FUTypeUtilization] = field(default_factory=dict)


@dataclass
class StallBreakdownMetrics:
    """Stall cause breakdown."""
    total_stalls: int = 0
    no_stall_cycles: int = 0
    memory_latency: int = 0
    raw_hazard: int = 0
    waw_hazard: int = 0
    war_hazard: int = 0
    fu_contention: int = 0
    port_contention: int = 0
    control_flow: int = 0
    dma_pending: int = 0
    resource_limit: int = 0

    def get_stall_percentages(self) -> Dict[str, float]:
        """Get stall causes as percentages."""
        if self.total_stalls == 0:
            return {}
        return {
            "memory_latency": self.memory_latency / self.total_stalls * 100,
            "raw_hazard": self.raw_hazard / self.total_stalls * 100,
            "waw_hazard": self.waw_hazard / self.total_stalls * 100,
            "war_hazard": self.war_hazard / self.total_stalls * 100,
            "fu_contention": self.fu_contention / self.total_stalls * 100,
            "port_contention": self.port_contention / self.total_stalls * 100,
            "control_flow": self.control_flow / self.total_stalls * 100,
            "dma_pending": self.dma_pending / self.total_stalls * 100,
            "resource_limit": self.resource_limit / self.total_stalls * 100,
        }


@dataclass
class EnhancedPerformanceMetrics:
    """Enhanced performance metrics."""
    accelerator_name: str = ""
    setup_time_ns: float = 0.0
    sim_time_ns: float = 0.0
    total_time_ns: float = 0.0
    clock_period_ns: float = 0.0
    total_cycles: int = 0
    stall_cycles: int = 0
    active_cycles: int = 0
    executed_nodes: int = 0
    ipc: float = 0.0


@dataclass
class EnhancedPowerStats:
    """Enhanced power statistics."""
    fu_leakage: float = 0.0
    fu_dynamic: float = 0.0
    fu_total: float = 0.0
    reg_leakage: float = 0.0
    reg_dynamic: float = 0.0
    reg_total: float = 0.0
    spm_leakage: float = 0.0
    spm_total: float = 0.0
    cache_leakage: float = 0.0
    cache_total: float = 0.0
    total_leakage: float = 0.0
    total_dynamic: float = 0.0
    total_power: float = 0.0
    total_energy_nj: float = 0.0


@dataclass
class EnhancedAreaStats:
    """Enhanced area statistics."""
    fu_area_um2: float = 0.0
    reg_area_um2: float = 0.0
    spm_area_um2: float = 0.0
    cache_area_um2: float = 0.0
    total_area_um2: float = 0.0
    total_area_mm2: float = 0.0


@dataclass
class EnhancedSimulationStats:
    """Container for all enhanced simulation statistics."""
    version: str = "3.0"
    timestamp: str = ""
    performance: EnhancedPerformanceMetrics = field(default_factory=EnhancedPerformanceMetrics)
    memory_access: MemoryAccessMetrics = field(default_factory=MemoryAccessMetrics)
    dataflow: DataflowMetrics = field(default_factory=DataflowMetrics)
    fu_utilization: FUUtilizationMetrics = field(default_factory=FUUtilizationMetrics)
    stall_breakdown: StallBreakdownMetrics = field(default_factory=StallBreakdownMetrics)
    power: EnhancedPowerStats = field(default_factory=EnhancedPowerStats)
    area: EnhancedAreaStats = field(default_factory=EnhancedAreaStats)
    raw_data: Dict[str, Any] = field(default_factory=dict)


def parse_enhanced_json(json_str: str) -> EnhancedSimulationStats:
    """
    Parse enhanced statistics from JSON string.

    Args:
        json_str: JSON string from stats_update message or file

    Returns:
        EnhancedSimulationStats object with parsed data
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        return EnhancedSimulationStats()

    # Handle both direct data and wrapped format
    if "salam_stats" in data:
        data = data["salam_stats"]

    return _parse_stats_dict(data)


def load_enhanced_json(file_path: Path) -> EnhancedSimulationStats:
    """
    Load enhanced statistics from JSON file.

    Args:
        file_path: Path to JSON statistics file

    Returns:
        EnhancedSimulationStats object with parsed data
    """
    try:
        with open(file_path, "r") as f:
            content = f.read()
        return parse_enhanced_json(content)
    except Exception as e:
        print(f"Error loading stats file: {e}")
        return EnhancedSimulationStats()


def _parse_stats_dict(data: Dict[str, Any]) -> EnhancedSimulationStats:
    """Parse statistics from dictionary."""
    stats = EnhancedSimulationStats()
    stats.raw_data = data
    stats.version = data.get("version", "3.0")
    stats.timestamp = data.get("timestamp", "")

    # Parse performance
    if "performance" in data:
        perf = data["performance"]
        stats.performance = EnhancedPerformanceMetrics(
            accelerator_name=data.get("accelerator_name", ""),
            setup_time_ns=perf.get("setup_time_ns", 0.0),
            sim_time_ns=perf.get("sim_time_ns", 0.0),
            total_time_ns=perf.get("setup_time_ns", 0) + perf.get("sim_time_ns", 0),
            clock_period_ns=perf.get("clock_period_ns", 0),
            total_cycles=perf.get("total_cycles", 0),
            stall_cycles=perf.get("stall_cycles", 0),
            active_cycles=perf.get("total_cycles", 0) - perf.get("stall_cycles", 0),
            executed_nodes=perf.get("executed_nodes", 0),
        )

    # Parse memory access
    if "memory_access" in data:
        mem = data["memory_access"]
        stats.memory_access = MemoryAccessMetrics(
            cache_hits=mem.get("cache_hits", 0),
            cache_misses=mem.get("cache_misses", 0),
            cache_read_hits=mem.get("cache_read_hits", 0),
            cache_read_misses=mem.get("cache_read_misses", 0),
            cache_write_hits=mem.get("cache_write_hits", 0),
            cache_write_misses=mem.get("cache_write_misses", 0),
            spm_reads=mem.get("spm_reads", 0),
            spm_writes=mem.get("spm_writes", 0),
            dma_reads=mem.get("dma_reads", 0),
            dma_writes=mem.get("dma_writes", 0),
            avg_read_latency=mem.get("avg_read_latency", 0.0),
            avg_write_latency=mem.get("avg_write_latency", 0.0),
            max_read_latency=mem.get("max_read_latency", 0),
            max_write_latency=mem.get("max_write_latency", 0),
            read_port_contentions=mem.get("read_port_contentions", 0),
            write_port_contentions=mem.get("write_port_contentions", 0),
        )

    # Parse dataflow
    if "dataflow" in data:
        df = data["dataflow"]
        stats.dataflow = DataflowMetrics(
            critical_path_length=df.get("critical_path_length", 0),
            critical_path_instructions=df.get("critical_path_instructions", 0),
            critical_path_loads=df.get("critical_path_loads", 0),
            critical_path_stores=df.get("critical_path_stores", 0),
            critical_path_computes=df.get("critical_path_computes", 0),
            avg_ready_instructions=df.get("avg_ready_instructions", 0.0),
            avg_issued_per_cycle=df.get("avg_issued_per_cycle", 0.0),
            max_parallel_ops=df.get("max_parallel_ops", 0),
            total_instructions=df.get("total_instructions", 0),
            true_dependencies=df.get("true_dependencies", 0),
            anti_dependencies=df.get("anti_dependencies", 0),
            output_dependencies=df.get("output_dependencies", 0),
            control_dependencies=df.get("control_dependencies", 0),
            memory_dependencies=df.get("memory_dependencies", 0),
            avg_dependency_depth=df.get("avg_dependency_depth", 0.0),
            max_dependency_depth=df.get("max_dependency_depth", 0),
            total_dependency_edges=df.get("total_dependency_edges", 0),
        )

    # Parse stall breakdown
    if "stall_breakdown" in data:
        sb = data["stall_breakdown"]
        stats.stall_breakdown = StallBreakdownMetrics(
            total_stalls=sb.get("total_stalls", 0),
            no_stall_cycles=sb.get("no_stall_cycles", 0),
            memory_latency=sb.get("memory_latency", 0),
            raw_hazard=sb.get("raw_hazard", 0),
            waw_hazard=sb.get("waw_hazard", 0),
            war_hazard=sb.get("war_hazard", 0),
            fu_contention=sb.get("fu_contention", 0),
            port_contention=sb.get("port_contention", 0),
            control_flow=sb.get("control_flow", 0),
            dma_pending=sb.get("dma_pending", 0),
            resource_limit=sb.get("resource_limit", 0),
        )

    # Parse power
    if "power" in data:
        pwr = data["power"]
        stats.power = EnhancedPowerStats(
            fu_leakage=pwr.get("fu_leakage", 0.0),
            fu_dynamic=pwr.get("fu_dynamic", 0.0),
            fu_total=pwr.get("fu_total", 0.0),
            reg_leakage=pwr.get("reg_leakage", 0.0),
            reg_dynamic=pwr.get("reg_dynamic", 0.0),
            reg_total=pwr.get("reg_total", 0.0),
            spm_leakage=pwr.get("spm_leakage", 0.0),
            spm_total=pwr.get("spm_total", 0.0),
            cache_leakage=pwr.get("cache_leakage", 0.0),
            cache_total=pwr.get("cache_total", 0.0),
            total_leakage=pwr.get("total_leakage", 0.0),
            total_dynamic=pwr.get("total_dynamic", 0.0),
            total_power=pwr.get("total_power", 0.0),
            total_energy_nj=pwr.get("total_energy_nj", 0.0),
        )

    # Parse area
    if "area" in data:
        ar = data["area"]
        stats.area = EnhancedAreaStats(
            fu_area_um2=ar.get("fu_area_um2", 0.0),
            reg_area_um2=ar.get("reg_area_um2", 0.0),
            spm_area_um2=ar.get("spm_area_um2", 0.0),
            cache_area_um2=ar.get("cache_area_um2", 0.0),
            total_area_um2=ar.get("total_area_um2", 0.0),
            total_area_mm2=ar.get("total_area_mm2", 0.0),
        )

    return stats


def format_metric(value: float, unit: str = "", precision: int = 2) -> str:
    """Format a metric value with appropriate scaling."""
    if abs(value) >= 1e9:
        return f"{value/1e9:.{precision}f}G{unit}"
    elif abs(value) >= 1e6:
        return f"{value/1e6:.{precision}f}M{unit}"
    elif abs(value) >= 1e3:
        return f"{value/1e3:.{precision}f}K{unit}"
    elif abs(value) >= 1:
        return f"{value:.{precision}f}{unit}"
    elif abs(value) >= 1e-3:
        return f"{value*1e3:.{precision}f}m{unit}"
    elif abs(value) >= 1e-6:
        return f"{value*1e6:.{precision}f}u{unit}"
    else:
        return f"{value:.{precision}e}{unit}"


def format_percentage(value: float) -> str:
    """Format a percentage value."""
    return f"{value:.1f}%"


def format_cycles(cycles: int) -> str:
    """Format cycle count with K/M suffix."""
    if cycles >= 1e6:
        return f"{cycles/1e6:.2f}M"
    elif cycles >= 1e3:
        return f"{cycles/1e3:.1f}K"
    return str(cycles)
