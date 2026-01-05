import re

# Read the file
with open(
    "/home/jslycord/gem5-SALAM-dev/scripts/salam_gui/widgets/__init__.py", "r"
) as f:
    content = f.read()

# Add import for live_stats_widget
old_imports = """# Simulation integration
from .simulation_panel import SimulationPanel"""

new_imports = """# Simulation integration
from .simulation_panel import SimulationPanel

# Live statistics (Phase 3)
from .live_stats_widget import LiveStatsWidget"""

content = content.replace(old_imports, new_imports, 1)

# Add to __all__
old_all = """    # Simulation
    'SimulationPanel',"""

new_all = """    # Simulation
    'SimulationPanel',
    # Live Stats
    'LiveStatsWidget',"""

content = content.replace(old_all, new_all, 1)

# Write the file back
with open(
    "/home/jslycord/gem5-SALAM-dev/scripts/salam_gui/widgets/__init__.py", "w"
) as f:
    f.write(content)

print("widgets/__init__.py updated successfully")
