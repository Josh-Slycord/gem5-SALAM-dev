import re

# Read the file
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/HWModeling/src/hw_statistics.cc",
    "r",
) as f:
    content = f.read()

# Fix the power stats field names
fixes = [
    ("summary.power.fu_leakage_mw", "summary.power.fu_leakage"),
    ("summary.power.fu_dynamic_mw", "summary.power.fu_dynamic"),
    ("summary.power.fu_total_mw", "summary.power.fu_total"),
    ("summary.power.reg_leakage_mw", "summary.power.reg_leakage"),
    ("summary.power.reg_dynamic_mw", "summary.power.reg_dynamic"),
    ("summary.power.reg_total_mw", "summary.power.reg_total"),
    (
        "summary.power.mem_leakage_mw",
        "(summary.power.spm_leakage + summary.power.cache_leakage)",
    ),
    (
        "summary.power.mem_dynamic_mw",
        "(summary.power.spm_total + summary.power.cache_total - summary.power.spm_leakage - summary.power.cache_leakage)",
    ),
    (
        "summary.power.mem_total_mw",
        "(summary.power.spm_total + summary.power.cache_total)",
    ),
    (
        "summary.power.total_leakage_mw",
        "(summary.power.fu_leakage + summary.power.reg_leakage + summary.power.spm_leakage + summary.power.cache_leakage)",
    ),
    (
        "summary.power.total_dynamic_mw",
        "(summary.power.total_power - summary.power.fu_leakage - summary.power.reg_leakage - summary.power.spm_leakage - summary.power.cache_leakage)",
    ),
    ("summary.power.total_power_mw", "summary.power.total_power"),
    (
        "summary.area.mem_area_um2",
        "(summary.area.spm_area_um2 + summary.area.cache_area_um2)",
    ),
    ("summary.area.total_area_mm2", "summary.area.getTotalAreaMm2()"),
]

for old, new in fixes:
    content = content.replace(old, new)

# Write the file back
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/HWModeling/src/hw_statistics.cc",
    "w",
) as f:
    f.write(content)

print("CSV field names fixed successfully")
