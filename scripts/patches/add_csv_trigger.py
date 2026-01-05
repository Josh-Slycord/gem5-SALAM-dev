import re

# Read the file
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "r"
) as f:
    content = f.read()

# Add SALAMResultsCSV check after SALAMResults check
old_section = """    // Verbose output if debug flag enabled
    if (debug::SALAMResults) {
        hw->hw_statistics->printDetailed(std::cout);
    }

    // Publish final stats to GUI if enabled"""

new_section = """    // Verbose output if debug flag enabled
    if (debug::SALAMResults) {
        hw->hw_statistics->printDetailed(std::cout);
    }

    // CSV output if debug flag enabled
    if (debug::SALAMResultsCSV) {
        hw->hw_statistics->printCSV(std::cout);
        hw->hw_statistics->writeCSVFile();
    }

    // Publish final stats to GUI if enabled"""

content = content.replace(old_section, new_section, 1)

# Write the file back
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "w"
) as f:
    f.write(content)

print("CSV trigger added successfully")
