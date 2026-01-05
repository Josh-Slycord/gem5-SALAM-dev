import re

# Read the file
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "r"
) as f:
    content = f.read()

# Add comprehensive null check at start of finalize stats section
old_code = """    hw->hw_statistics->setAcceleratorName(name());
    hw->hw_statistics->collectPerformanceStats("""

new_code = """    // Guard all statistics collection with null check
    if (!hw || !hw->hw_statistics) {
        warn("HWStatistics not available, skipping statistics collection");
        printResults();  // Legacy output
        functions.clear();
        values.clear();
        comm->finish();
        return;
    }

    hw->hw_statistics->setAcceleratorName(name());
    hw->hw_statistics->collectPerformanceStats("""

content = content.replace(old_code, new_code, 1)

# Write the file back
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "w"
) as f:
    f.write(content)

print("Finalize null check added successfully")
