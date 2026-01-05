import re

# Read the file
with open(
    "/home/jslycord/gem5-SALAM-dev/scripts/salam_gui/data/__init__.py", "r"
) as f:
    content = f.read()

# Add import for enhanced_stats_parser
old_imports = """from .stats_parser import parse_stats_output, SimulationStats
from .config_loader import load_config"""

new_imports = """from .stats_parser import parse_stats_output, SimulationStats
from .enhanced_stats_parser import (
    parse_enhanced_json,
    load_enhanced_json,
    EnhancedSimulationStats,
    MemoryAccessMetrics,
    DataflowMetrics,
    StallBreakdownMetrics
)
from .config_loader import load_config"""

content = content.replace(old_imports, new_imports, 1)

# Add to __all__
old_all = """__all__ = [
    'parse_cdfg_dot', 'CDFGGraph',
    'parse_stats_output', 'SimulationStats',
    'load_config',"""

new_all = """__all__ = [
    'parse_cdfg_dot', 'CDFGGraph',
    'parse_stats_output', 'SimulationStats',
    # Enhanced stats (v3.0)
    'parse_enhanced_json',
    'load_enhanced_json',
    'EnhancedSimulationStats',
    'MemoryAccessMetrics',
    'DataflowMetrics',
    'StallBreakdownMetrics',
    'load_config',"""

content = content.replace(old_all, new_all, 1)

# Write the file back
with open(
    "/home/jslycord/gem5-SALAM-dev/scripts/salam_gui/data/__init__.py", "w"
) as f:
    f.write(content)

print("data/__init__.py updated successfully")
