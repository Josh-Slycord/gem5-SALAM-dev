import re

# Read the file
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "r"
) as f:
    content = f.read()

# Add null check before accessing hw->opcodes
old_code = """    // Collect FU stats from opcodes
    std::map<int, int> static_fu_usage;
    std::map<int, int> runtime_fu_max;
    std::map<int, double> runtime_fu_occ;
    for (const auto& count : hw->opcodes->usage) {
        static_fu_usage[count.first] = count.second;
    }
    hw->hw_statistics->collectFUStats(static_fu_usage, runtime_fu_max, runtime_fu_occ);"""

new_code = """    // Collect FU stats from opcodes (with null check)
    std::map<int, int> static_fu_usage;
    std::map<int, int> runtime_fu_max;
    std::map<int, double> runtime_fu_occ;
    if (hw && hw->opcodes) {
        for (const auto& count : hw->opcodes->usage) {
            static_fu_usage[count.first] = count.second;
        }
    }
    if (hw && hw->hw_statistics) {
        hw->hw_statistics->collectFUStats(static_fu_usage, runtime_fu_max, runtime_fu_occ);
    }"""

content = content.replace(old_code, new_code, 1)

# Write the file back
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "w"
) as f:
    f.write(content)

print("Null check added successfully")
