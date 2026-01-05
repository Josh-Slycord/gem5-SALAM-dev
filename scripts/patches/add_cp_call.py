import re

# Read the file
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "r"
) as f:
    content = f.read()

# Add computeCriticalPath call before dataflow stats access
old_section = """    // Summarize cycle stats if tracking was enabled
    if (hw->hw_statistics->use_cycle_tracking()) {
        hw->hw_statistics->getSummary().cycle_summary =
            hw->hw_statistics->summarizeCycleStats();
    }

    // Calculate dataflow ILP metric
    auto& df = hw->hw_statistics->getDataflowStats();"""

new_section = """    // Summarize cycle stats if tracking was enabled
    if (hw->hw_statistics->use_cycle_tracking()) {
        hw->hw_statistics->getSummary().cycle_summary =
            hw->hw_statistics->summarizeCycleStats();
    }

    // Compute critical path from collected dependency data
    hw->hw_statistics->computeCriticalPath();

    // Calculate dataflow ILP metric
    auto& df = hw->hw_statistics->getDataflowStats();"""

content = content.replace(old_section, new_section, 1)

# Write the file back
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "w"
) as f:
    f.write(content)

print("computeCriticalPath call added successfully")
