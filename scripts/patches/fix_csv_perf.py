import re

# Read the file
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/HWModeling/src/hw_statistics.cc",
    "r",
) as f:
    content = f.read()

# Find and replace the printCSV function
old_csv = """void HWStatistics::printCSV(std::ostream& os) const {
    // Print header row first
    os << "metric,value\\n";

    // Performance metrics
    os << "accelerator_name," << summary.perf.accelerator_name << "\\n";
    os << "setup_time_ns," << summary.perf.setup_time_ns << "\\n";
    os << "sim_time_ns," << summary.perf.sim_time_ns << "\\n";
    os << "total_time_ns," << summary.perf.total_time_ns << "\\n";
    os << "clock_period_ns," << summary.perf.clock_period_ns << "\\n";
    os << "total_cycles," << summary.perf.total_cycles << "\\n";
    os << "stall_cycles," << summary.perf.stall_cycles << "\\n";
    os << "active_cycles," << summary.perf.active_cycles << "\\n";
    os << "ipc," << summary.perf.ipc << "\\n";"""

new_csv = """void HWStatistics::printCSV(std::ostream& os) const {
    // Print header row first
    os << "metric,value\\n";

    // Performance metrics
    os << "accelerator_name," << summary.accelerator_name << "\\n";
    os << "setup_time_ns," << summary.performance.setup_time_ns << "\\n";
    os << "sim_time_ns," << summary.performance.sim_time_ns << "\\n";
    os << "total_time_ns," << (summary.performance.setup_time_ns + summary.performance.sim_time_ns) << "\\n";
    os << "clock_period_ns," << summary.performance.clock_period_ns << "\\n";
    os << "total_cycles," << summary.performance.total_cycles << "\\n";
    os << "stall_cycles," << summary.performance.stall_cycles << "\\n";
    os << "active_cycles," << (summary.performance.total_cycles - summary.performance.stall_cycles) << "\\n";
    double ipc = summary.performance.stall_cycles > 0 ?
                 (double)summary.performance.executed_nodes / summary.performance.total_cycles : 0.0;
    os << "ipc," << ipc << "\\n";"""

content = content.replace(old_csv, new_csv, 1)

# Write the file back
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/HWModeling/src/hw_statistics.cc",
    "w",
) as f:
    f.write(content)

print("CSV performance fields fixed successfully")
