import re

# Read hw_statistics.hh
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/HWModeling/src/hw_statistics.hh",
    "r",
) as f:
    hh_content = f.read()

# Read hw_statistics.cc
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/HWModeling/src/hw_statistics.cc",
    "r",
) as f:
    cc_content = f.read()

# Add CSV output method declaration to hw_statistics.hh
old_output_methods = """    // Output methods
    std::string toJSON(bool pretty = true) const;
    void printSummary(std::ostream& os) const;
    void printDetailed(std::ostream& os) const;"""

new_output_methods = """    // Output methods
    std::string toJSON(bool pretty = true) const;
    void printSummary(std::ostream& os) const;
    void printDetailed(std::ostream& os) const;
    void printCSV(std::ostream& os) const;  // CSV format for SALAMResultsCSV
    void writeCSVFile() const;  // Write CSV to file"""

hh_content = hh_content.replace(old_output_methods, new_output_methods, 1)

# Write hw_statistics.hh
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/HWModeling/src/hw_statistics.hh",
    "w",
) as f:
    f.write(hh_content)

# Add CSV output implementation to hw_statistics.cc
# Find the writeJSONFile implementation to add after it
csv_implementation = """

// ============================================================================
// CSV Output Implementation
// ============================================================================

void HWStatistics::printCSV(std::ostream& os) const {
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
    os << "ipc," << summary.perf.ipc << "\\n";

    // Memory stats
    os << "cache_hits," << summary.memory_access.cache_hits << "\\n";
    os << "cache_misses," << summary.memory_access.cache_misses << "\\n";
    os << "spm_reads," << summary.memory_access.spm_reads << "\\n";
    os << "spm_writes," << summary.memory_access.spm_writes << "\\n";
    os << "avg_read_latency," << summary.memory_access.getAvgReadLatency() << "\\n";
    os << "avg_write_latency," << summary.memory_access.getAvgWriteLatency() << "\\n";

    // Dataflow stats
    os << "critical_path_length," << summary.dataflow.critical_path_length << "\\n";
    os << "critical_path_instructions," << summary.dataflow.critical_path_instructions << "\\n";
    os << "total_instructions," << summary.dataflow.total_instructions << "\\n";
    os << "true_dependencies," << summary.dataflow.true_dependencies << "\\n";
    os << "anti_dependencies," << summary.dataflow.anti_dependencies << "\\n";
    os << "output_dependencies," << summary.dataflow.output_dependencies << "\\n";
    os << "avg_dependency_depth," << summary.dataflow.avg_dependency_depth << "\\n";
    os << "max_dependency_depth," << summary.dataflow.max_dependency_depth << "\\n";
    os << "ilp," << summary.dataflow.getILP() << "\\n";
    os << "avg_parallelism," << summary.dataflow.getAvgParallelism() << "\\n";
    os << "max_parallel_ops," << summary.dataflow.max_parallel_ops << "\\n";

    // Power stats
    os << "fu_leakage_mw," << summary.power.fu_leakage_mw << "\\n";
    os << "fu_dynamic_mw," << summary.power.fu_dynamic_mw << "\\n";
    os << "fu_total_mw," << summary.power.fu_total_mw << "\\n";
    os << "reg_leakage_mw," << summary.power.reg_leakage_mw << "\\n";
    os << "reg_dynamic_mw," << summary.power.reg_dynamic_mw << "\\n";
    os << "reg_total_mw," << summary.power.reg_total_mw << "\\n";
    os << "mem_leakage_mw," << summary.power.mem_leakage_mw << "\\n";
    os << "mem_dynamic_mw," << summary.power.mem_dynamic_mw << "\\n";
    os << "mem_total_mw," << summary.power.mem_total_mw << "\\n";
    os << "total_leakage_mw," << summary.power.total_leakage_mw << "\\n";
    os << "total_dynamic_mw," << summary.power.total_dynamic_mw << "\\n";
    os << "total_power_mw," << summary.power.total_power_mw << "\\n";

    // Area stats
    os << "fu_area_um2," << summary.area.fu_area_um2 << "\\n";
    os << "reg_area_um2," << summary.area.reg_area_um2 << "\\n";
    os << "mem_area_um2," << summary.area.mem_area_um2 << "\\n";
    os << "total_area_um2," << summary.area.total_area_um2 << "\\n";
    os << "total_area_mm2," << summary.area.total_area_mm2 << "\\n";

    // Stall breakdown
    auto& stalls = summary.stall_breakdown;
    os << "stall_memory_latency," << stalls.by_cause[static_cast<int>(StallCause::MEMORY_LATENCY)] << "\\n";
    os << "stall_raw_hazard," << stalls.by_cause[static_cast<int>(StallCause::RAW_HAZARD)] << "\\n";
    os << "stall_waw_hazard," << stalls.by_cause[static_cast<int>(StallCause::WAW_HAZARD)] << "\\n";
    os << "stall_war_hazard," << stalls.by_cause[static_cast<int>(StallCause::WAR_HAZARD)] << "\\n";
    os << "stall_fu_contention," << stalls.by_cause[static_cast<int>(StallCause::FU_CONTENTION)] << "\\n";
    os << "stall_port_contention," << stalls.by_cause[static_cast<int>(StallCause::PORT_CONTENTION)] << "\\n";
    os << "stall_dma_pending," << stalls.by_cause[static_cast<int>(StallCause::DMA_PENDING)] << "\\n";
    os << "stall_resource_limit," << stalls.by_cause[static_cast<int>(StallCause::RESOURCE_LIMIT)] << "\\n";
}

void HWStatistics::writeCSVFile() const {
    std::string csv_file = output_file;
    // Replace .json extension with .csv if present
    size_t pos = csv_file.rfind(".json");
    if (pos != std::string::npos) {
        csv_file.replace(pos, 5, ".csv");
    } else {
        csv_file += ".csv";
    }

    std::ofstream file(csv_file);
    if (file.is_open()) {
        printCSV(file);
        file.close();
        inform("CSV statistics written to %s", csv_file.c_str());
    } else {
        warn("Could not open %s for writing CSV statistics", csv_file.c_str());
    }
}

"""

# Find where to insert (before the last closing brace of implementations)
# Look for the writeJSONFile implementation and add after it
insert_marker = "void HWStatistics::writeJSONFile()"
insert_pos = cc_content.find(insert_marker)

if insert_pos != -1:
    # Find the end of writeJSONFile (the closing brace)
    # Look for the matching closing brace
    brace_count = 0
    in_function = False
    end_pos = insert_pos
    for i, char in enumerate(cc_content[insert_pos:], insert_pos):
        if char == "{":
            brace_count += 1
            in_function = True
        elif char == "}":
            brace_count -= 1
            if in_function and brace_count == 0:
                end_pos = i + 1
                break

    cc_content = (
        cc_content[:end_pos] + csv_implementation + cc_content[end_pos:]
    )

# Write hw_statistics.cc
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/HWModeling/src/hw_statistics.cc",
    "w",
) as f:
    f.write(cc_content)

print("CSV output implementation added successfully")
