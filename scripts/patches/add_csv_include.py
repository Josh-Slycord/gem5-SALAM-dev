import re

# Read the file
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "r"
) as f:
    content = f.read()

# Add SALAMResultsCSV include after SALAMResults include
old_include = '#include "debug/SALAMResults.hh"'
new_include = '''#include "debug/SALAMResults.hh"
#include "debug/SALAMResultsCSV.hh"'''

content = content.replace(old_include, new_include, 1)

# Write the file back
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "w"
) as f:
    f.write(content)

print("CSV include added successfully")
