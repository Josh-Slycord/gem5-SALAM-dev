#include "hw_statistics.hh"
#include "debug/SALAMResults.hh"
#include "debug/SALAMResultsCSV.hh"
#include "hwacc/gui_publisher.hh"

#include <algorithm>
#include <cmath>

// ============================================================================
// Helper functions for type names
// ============================================================================

const char* getFUTypeName(FUType type) {
    switch (type) {
        case FUType::COUNTER:           return "counter";
        case FUType::INT_ADD_SUB:       return "int_adder";
        case FUType::INT_MUL_DIV:       return "int_multiplier";
        case FUType::INT_SHIFT:         return "int_shifter";
        case FUType::INT_BITWISE:       return "int_bitwise";
        case FUType::FP_FLOAT_ADD_SUB:  return "fp_float_adder";
        case FUType::FP_FLOAT_MUL_DIV:  return "fp_float_multiplier";
        case FUType::FP_DOUBLE_ADD_SUB: return "fp_double_adder";
        case FUType::FP_DOUBLE_MUL_DIV: return "fp_double_multiplier";
        case FUType::ZERO_CYCLE:        return "zero_cycle";
        case FUType::GEP:               return "gep";
        case FUType::CONVERSION:        return "conversion";
        case FUType::OTHER:             return "other";
        default:                        return "unknown";
    }
}

const char* getStallTypeName(StallType type) {
    switch (type) {
        case StallType::LOAD_ONLY:       return "load_only";
        case StallType::STORE_ONLY:      return "store_only";
        case StallType::COMP_ONLY:       return "compute_only";
        case StallType::LOAD_STORE:      return "load_store";
        case StallType::LOAD_COMP:       return "load_compute";
        case StallType::STORE_COMP:      return "store_compute";
        case StallType::LOAD_STORE_COMP: return "load_store_compute";
        default:                         return "unknown";
    }
}

// ============================================================================
// Constructor
// ============================================================================

HWStatistics::HWStatistics(const HWStatisticsParams &params) :
    SimObject(params),
    cycle_tracking(params.cycle_tracking),
    output_statistics(params.output_statistics),
    output_file(params.output_file),
    pretty_print(params.pretty_print),
    gui_stats_enabled(params.gui_stats_enabled),
    stat_buffer_size(params.stat_buffer_size),
    dbg(false)
{
    // Initialize cycle tracking buffers if enabled
    if (cycle_tracking) {
        int bufferPreDefine = 2;
        for (int i = 0; i < bufferPreDefine; i++) {
            std::vector<HW_Cycle_Stats> hw_cycle_buffer;
            hw_cycle_buffer.reserve(stat_buffer_size);
            hw_buffer_list.push_back(hw_cycle_buffer);
        }
        hw_buffer = hw_buffer_list.begin();
        cycle_buffer = hw_buffer->begin();
    }
    clearStats();
}

// ============================================================================
// Data Collection Methods
// ============================================================================

void HWStatistics::setAcceleratorName(const std::string& name) {
    summary.accelerator_name = name;

    // Set timestamp
    auto now = std::chrono::system_clock::now();
    auto time = std::chrono::system_clock::to_time_t(now);
    char buf[32];
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", std::localtime(&time));
    summary.timestamp = buf;
}

void HWStatistics::collectPerformanceStats(double setup_ns, double sim_ns,
                                           int clock_period, int cycles,
                                           int stalls) {
    summary.performance.setup_time_ns = setup_ns;
    summary.performance.sim_time_ns = sim_ns;
    summary.performance.clock_period_ns = clock_period;
    summary.performance.sys_clock_ghz = 1.0 / (clock_period / 1000.0);
    summary.performance.total_cycles = cycles;
    summary.performance.stall_cycles = stalls;
    summary.performance.executed_nodes = cycles - stalls - 1;
}

void HWStatistics::collectStallBreakdown(int load_only, int store_only,
                                         int comp_only, int load_store,
                                         int load_comp, int store_comp,
                                         int load_store_comp) {
    summary.performance.stall_breakdown[0] = load_only;
    summary.performance.stall_breakdown[1] = store_only;
    summary.performance.stall_breakdown[2] = comp_only;
    summary.performance.stall_breakdown[3] = load_store;
    summary.performance.stall_breakdown[4] = load_comp;
    summary.performance.stall_breakdown[5] = store_comp;
    summary.performance.stall_breakdown[6] = load_store_comp;
}

void HWStatistics::collectNodeBreakdown(int load_only, int store_only,
                                        int comp_only, int load_store,
                                        int load_comp, int store_comp,
                                        int load_store_comp) {
    summary.performance.node_breakdown[0] = load_only;
    summary.performance.node_breakdown[1] = store_only;
    summary.performance.node_breakdown[2] = comp_only;
    summary.performance.node_breakdown[3] = load_store;
    summary.performance.node_breakdown[4] = load_comp;
    summary.performance.node_breakdown[5] = store_comp;
    summary.performance.node_breakdown[6] = load_store_comp;
}

void HWStatistics::collectFUStats(const std::map<int, int>& static_usage,
                                  const std::map<int, int>& runtime_max,
                                  const std::map<int, double>& runtime_occ) {
    // Map opcode ranges to FU types (simplified mapping)
    // This would need to be adjusted based on actual opcode definitions
    for (const auto& kv : static_usage) {
        int opcode = kv.first;
        int count = kv.second;

        FUType type = FUType::OTHER;
        // Map based on LLVM opcode numbers
        if (opcode == 13 || opcode == 15) type = FUType::INT_ADD_SUB;
        else if (opcode == 17 || opcode == 19) type = FUType::INT_MUL_DIV;
        else if (opcode >= 25 && opcode <= 27) type = FUType::INT_SHIFT;
        else if (opcode >= 28 && opcode <= 30) type = FUType::INT_BITWISE;
        else if (opcode == 11 || opcode == 12) type = FUType::FP_FLOAT_ADD_SUB;
        else if (opcode == 14 || opcode == 16) type = FUType::FP_FLOAT_MUL_DIV;
        else if (opcode == 34) type = FUType::GEP;

        int idx = static_cast<int>(type);
        summary.functional_units.static_count[idx] += count;
    }

    for (const auto& kv : runtime_max) {
        int opcode = kv.first;
        int max_val = kv.second;

        FUType type = FUType::OTHER;
        if (opcode == 13 || opcode == 15) type = FUType::INT_ADD_SUB;
        else if (opcode == 17 || opcode == 19) type = FUType::INT_MUL_DIV;

        int idx = static_cast<int>(type);
        summary.functional_units.runtime[idx].max_concurrent =
            std::max(summary.functional_units.runtime[idx].max_concurrent,
                     max_val);
    }

    for (const auto& kv : runtime_occ) {
        int opcode = kv.first;
        double occ = kv.second;

        FUType type = FUType::OTHER;
        if (opcode == 13 || opcode == 15) type = FUType::INT_ADD_SUB;
        else if (opcode == 17 || opcode == 19) type = FUType::INT_MUL_DIV;

        int idx = static_cast<int>(type);
        summary.functional_units.runtime[idx].avg_occupancy = occ;
    }
}

void HWStatistics::collectMemoryStats(int cache_kb, int cache_ports,
                                      int spm_kb, int spm_read_ports,
                                      int spm_write_ports,
                                      int64_t mem_reads, int64_t mem_writes,
                                      int64_t dma_reads, int64_t dma_writes) {
    summary.memory.cache_size_kb = cache_kb;
    summary.memory.cache_ports = cache_ports;
    summary.memory.spm_size_kb = spm_kb;
    summary.memory.spm_read_ports = spm_read_ports;
    summary.memory.spm_write_ports = spm_write_ports;
    summary.memory.mem_reads = mem_reads;
    summary.memory.mem_writes = mem_writes;
    summary.memory.dma_reads = dma_reads;
    summary.memory.dma_writes = dma_writes;
}

void HWStatistics::collectRegisterStats(int total, int max_usage,
                                        double avg_usage, double avg_size,
                                        int64_t reads, int64_t writes) {
    summary.registers.total = total;
    summary.registers.max_usage = max_usage;
    summary.registers.avg_usage = avg_usage;
    summary.registers.avg_size_bytes = avg_size;
    summary.registers.reads = reads;
    summary.registers.writes = writes;
}

void HWStatistics::collectPowerStats(double fu_leak, double fu_dyn,
                                     double reg_leak, double reg_dyn,
                                     double spm_leak, double spm_read,
                                     double spm_write,
                                     double cache_leak, double cache_read,
                                     double cache_write) {
    summary.power.fu_leakage = fu_leak;
    summary.power.fu_dynamic = fu_dyn;
    summary.power.fu_total = fu_leak + fu_dyn;

    summary.power.reg_leakage = reg_leak;
    summary.power.reg_dynamic = reg_dyn;
    summary.power.reg_total = reg_leak + reg_dyn;

    summary.power.spm_leakage = spm_leak;
    summary.power.spm_read_dynamic = spm_read;
    summary.power.spm_write_dynamic = spm_write;
    summary.power.spm_total = spm_leak + spm_read + spm_write;

    summary.power.cache_leakage = cache_leak;
    summary.power.cache_read_dynamic = cache_read;
    summary.power.cache_write_dynamic = cache_write;
    summary.power.cache_total = cache_leak + cache_read + cache_write;

    summary.power.total_power = summary.power.fu_total +
                                summary.power.reg_total;
    summary.power.acc_spm_total = summary.power.total_power +
                                  summary.power.spm_total;
    summary.power.acc_cache_total = summary.power.total_power +
                                    summary.power.cache_total;
}

void HWStatistics::collectAreaStats(double fu_area, double reg_area,
                                    double spm_area, double cache_area) {
    summary.area.fu_area_um2 = fu_area;
    summary.area.reg_area_um2 = reg_area;
    summary.area.spm_area_um2 = spm_area;
    summary.area.cache_area_um2 = cache_area;
    summary.area.total_area_um2 = fu_area + reg_area;
    summary.area.acc_spm_area_um2 = summary.area.total_area_um2 + spm_area;
    summary.area.acc_cache_area_um2 = summary.area.total_area_um2 + cache_area;
}

// ============================================================================
// Cycle Tracking Methods
// ============================================================================

void HWStatistics::recordCycleStats(const HW_Cycle_Stats& stats) {
    if (!cycle_tracking) return;

    current_cycle_stats = stats;
    hw_buffer_list[current_buffer_index].push_back(stats);

    // Check if buffer is full
    if (hw_buffer_list[current_buffer_index].size() >=
        static_cast<size_t>(stat_buffer_size)) {
        updateBuffer();
    }
}

CycleStatsSummary HWStatistics::summarizeCycleStats() {
    CycleStatsSummary result;

    if (!cycle_tracking) return result;

    int64_t sum_res = 0, sum_load = 0, sum_store = 0, sum_comp = 0;

    for (const auto& buffer : hw_buffer_list) {
        for (const auto& stats : buffer) {
            result.total_samples++;

            sum_res += stats.resInFlight;
            sum_load += stats.loadInFlight;
            sum_store += stats.storeInFlight;
            sum_comp += stats.compInFlight;

            result.peak_res_in_flight =
                std::max(result.peak_res_in_flight, stats.resInFlight);
            result.peak_load_in_flight =
                std::max(result.peak_load_in_flight, stats.loadInFlight);
            result.peak_store_in_flight =
                std::max(result.peak_store_in_flight, stats.storeInFlight);
            result.peak_comp_in_flight =
                std::max(result.peak_comp_in_flight, stats.compInFlight);

            result.total_load_raw_stalls += stats.loadRawStall;
            result.total_comp_fu_stalls += stats.compFUStall;
        }
    }

    if (result.total_samples > 0) {
        result.avg_res_in_flight =
            static_cast<double>(sum_res) / result.total_samples;
        result.avg_load_in_flight =
            static_cast<double>(sum_load) / result.total_samples;
        result.avg_store_in_flight =
            static_cast<double>(sum_store) / result.total_samples;
        result.avg_comp_in_flight =
            static_cast<double>(sum_comp) / result.total_samples;
    }

    return result;
}

void HWStatistics::updateHWStatsCycleStart() {
    if (dbg) DPRINTF(SALAM_Debug, "Updating Cycle Statistics Buffer\n");
    if (cycle_tracking) {
        recordCycleStats(current_cycle_stats);
    }
    clearStats();
}

void HWStatistics::updateHWStatsCycleEnd(int curr_cycle) {
    if (dbg) DPRINTF(SALAM_Debug, "Updating Cycle Statistics\n");
    current_cycle_stats.cycle = curr_cycle;
}

void HWStatistics::updateBuffer() {
    if (dbg) DPRINTF(SALAM_Debug, "Checking Buffer[%i][%lu]\n",
                     current_buffer_index,
                     hw_buffer_list.at(current_buffer_index).size());

    current_buffer_index++;

    if (current_buffer_index >= static_cast<int>(hw_buffer_list.size())) {
        if (dbg) DPRINTF(SALAM_Debug, "Creating New Buffer Window\n");
        std::vector<HW_Cycle_Stats> hw_cycle_buffer;
        hw_cycle_buffer.reserve(stat_buffer_size);
        hw_buffer_list.push_back(hw_cycle_buffer);
    }

    hw_buffer = hw_buffer_list.begin() + current_buffer_index;
    cycle_buffer = hw_buffer->begin();
}

void HWStatistics::clearStats() {
    if (dbg) DPRINTF(SALAM_Debug, "Clearing Cycle Statistics\n");
    current_cycle_stats.reset();
}

// ============================================================================
// JSON Serialization Helpers
// ============================================================================

std::string HWStatistics::indent(int level) const {
    if (!pretty_print) return "";
    return std::string(level * 2, ' ');
}

void HWStatistics::writeJsonField(std::ostringstream& os,
                                  const std::string& key,
                                  int value, int indent_level, bool last) {
    os << indent(indent_level) << "\"" << key << "\": " << value;
    if (!last) os << ",";
    if (pretty_print) os << "\n";
}

void HWStatistics::writeJsonField(std::ostringstream& os,
                                  const std::string& key,
                                  int64_t value, int indent_level, bool last) {
    os << indent(indent_level) << "\"" << key << "\": " << value;
    if (!last) os << ",";
    if (pretty_print) os << "\n";
}

void HWStatistics::writeJsonField(std::ostringstream& os,
                                  const std::string& key,
                                  double value, int indent_level, bool last) {
    os << indent(indent_level) << "\"" << key << "\": "
       << std::fixed << std::setprecision(6) << value;
    if (!last) os << ",";
    if (pretty_print) os << "\n";
}

void HWStatistics::writeJsonField(std::ostringstream& os,
                                  const std::string& key,
                                  const std::string& value,
                                  int indent_level, bool last) {
    os << indent(indent_level) << "\"" << key << "\": \"" << value << "\"";
    if (!last) os << ",";
    if (pretty_print) os << "\n";
}

void HWStatistics::writeJsonField(std::ostringstream& os,
                                  const std::string& key,
                                  bool value, int indent_level, bool last) {
    os << indent(indent_level) << "\"" << key << "\": "
       << (value ? "true" : "false");
    if (!last) os << ",";
    if (pretty_print) os << "\n";
}

// ============================================================================
// JSON Output
// ============================================================================

std::string HWStatistics::toJSON(bool pretty) const {
    std::ostringstream os;
    const std::string nl = pretty ? "\n" : "";
    const std::string sp = pretty ? "  " : "";

    os << "{" << nl;
    os << sp << "\"salam_stats\": {" << nl;

    // Metadata
    os << sp << sp << "\"version\": \"2.0\"," << nl;
    os << sp << sp << "\"accelerator_name\": \""
       << summary.accelerator_name << "\"," << nl;
    os << sp << sp << "\"timestamp\": \"" << summary.timestamp << "\"," << nl;

    // Performance
    os << sp << sp << "\"performance\": {" << nl;
    os << sp << sp << sp << "\"setup_time_ns\": "
       << std::fixed << std::setprecision(2)
       << summary.performance.setup_time_ns << "," << nl;
    os << sp << sp << sp << "\"sim_time_ns\": "
       << summary.performance.sim_time_ns << "," << nl;
    os << sp << sp << sp << "\"clock_period_ns\": "
       << summary.performance.clock_period_ns << "," << nl;
    os << sp << sp << sp << "\"sys_clock_ghz\": "
       << std::setprecision(3) << summary.performance.sys_clock_ghz << "," << nl;
    os << sp << sp << sp << "\"total_cycles\": "
       << summary.performance.total_cycles << "," << nl;
    os << sp << sp << sp << "\"stall_cycles\": "
       << summary.performance.stall_cycles << "," << nl;
    os << sp << sp << sp << "\"executed_nodes\": "
       << summary.performance.executed_nodes << "," << nl;

    // Stall breakdown
    os << sp << sp << sp << "\"stall_breakdown\": {" << nl;
    for (int i = 0; i < static_cast<int>(StallType::COUNT); i++) {
        os << sp << sp << sp << sp << "\""
           << getStallTypeName(static_cast<StallType>(i)) << "\": "
           << summary.performance.stall_breakdown[i];
        if (i < static_cast<int>(StallType::COUNT) - 1) os << ",";
        os << nl;
    }
    os << sp << sp << sp << "}," << nl;

    // Node breakdown
    os << sp << sp << sp << "\"node_breakdown\": {" << nl;
    for (int i = 0; i < static_cast<int>(StallType::COUNT); i++) {
        os << sp << sp << sp << sp << "\""
           << getStallTypeName(static_cast<StallType>(i)) << "\": "
           << summary.performance.node_breakdown[i];
        if (i < static_cast<int>(StallType::COUNT) - 1) os << ",";
        os << nl;
    }
    os << sp << sp << sp << "}" << nl;
    os << sp << sp << "}," << nl;

    // Functional Units
    os << sp << sp << "\"functional_units\": {" << nl;
    os << sp << sp << sp << "\"runtime\": {" << nl;
    for (int i = 0; i < static_cast<int>(FUType::COUNT); i++) {
        os << sp << sp << sp << sp << "\""
           << getFUTypeName(static_cast<FUType>(i)) << "\": {"
           << "\"max\": " << summary.functional_units.runtime[i].max_concurrent
           << ", \"avg_occ\": " << std::setprecision(2)
           << summary.functional_units.runtime[i].avg_occupancy << "}";
        if (i < static_cast<int>(FUType::COUNT) - 1) os << ",";
        os << nl;
    }
    os << sp << sp << sp << "}," << nl;
    os << sp << sp << sp << "\"static\": {" << nl;
    for (int i = 0; i < static_cast<int>(FUType::COUNT); i++) {
        os << sp << sp << sp << sp << "\""
           << getFUTypeName(static_cast<FUType>(i)) << "\": "
           << summary.functional_units.static_count[i];
        if (i < static_cast<int>(FUType::COUNT) - 1) os << ",";
        os << nl;
    }
    os << sp << sp << sp << "}" << nl;
    os << sp << sp << "}," << nl;

    // Memory
    os << sp << sp << "\"memory\": {" << nl;
    os << sp << sp << sp << "\"cache_size_kb\": "
       << summary.memory.cache_size_kb << "," << nl;
    os << sp << sp << sp << "\"cache_ports\": "
       << summary.memory.cache_ports << "," << nl;
    os << sp << sp << sp << "\"spm_size_kb\": "
       << summary.memory.spm_size_kb << "," << nl;
    os << sp << sp << sp << "\"spm_read_ports\": "
       << summary.memory.spm_read_ports << "," << nl;
    os << sp << sp << sp << "\"spm_write_ports\": "
       << summary.memory.spm_write_ports << "," << nl;
    os << sp << sp << sp << "\"mem_reads\": "
       << summary.memory.mem_reads << "," << nl;
    os << sp << sp << sp << "\"mem_writes\": "
       << summary.memory.mem_writes << "," << nl;
    os << sp << sp << sp << "\"dma_reads\": "
       << summary.memory.dma_reads << "," << nl;
    os << sp << sp << sp << "\"dma_writes\": "
       << summary.memory.dma_writes << nl;
    os << sp << sp << "}," << nl;

    // Registers
    os << sp << sp << "\"registers\": {" << nl;
    os << sp << sp << sp << "\"total\": " << summary.registers.total << "," << nl;
    os << sp << sp << sp << "\"max_usage\": "
       << summary.registers.max_usage << "," << nl;
    os << sp << sp << sp << "\"avg_usage\": "
       << std::setprecision(2) << summary.registers.avg_usage << "," << nl;
    os << sp << sp << sp << "\"avg_size_bytes\": "
       << summary.registers.avg_size_bytes << "," << nl;
    os << sp << sp << sp << "\"reads\": " << summary.registers.reads << "," << nl;
    os << sp << sp << sp << "\"writes\": " << summary.registers.writes << nl;
    os << sp << sp << "}," << nl;

    // Power
    os << sp << sp << "\"power\": {" << nl;
    os << sp << sp << sp << "\"fu_leakage_mw\": "
       << std::setprecision(4) << summary.power.fu_leakage << "," << nl;
    os << sp << sp << sp << "\"fu_dynamic_mw\": "
       << summary.power.fu_dynamic << "," << nl;
    os << sp << sp << sp << "\"fu_total_mw\": "
       << summary.power.fu_total << "," << nl;
    os << sp << sp << sp << "\"reg_total_mw\": "
       << summary.power.reg_total << "," << nl;
    os << sp << sp << sp << "\"spm_total_mw\": "
       << summary.power.spm_total << "," << nl;
    os << sp << sp << sp << "\"cache_total_mw\": "
       << summary.power.cache_total << "," << nl;
    os << sp << sp << sp << "\"total_mw\": "
       << summary.power.total_power << "," << nl;
    os << sp << sp << sp << "\"acc_with_spm_mw\": "
       << summary.power.acc_spm_total << "," << nl;
    os << sp << sp << sp << "\"acc_with_cache_mw\": "
       << summary.power.acc_cache_total << nl;
    os << sp << sp << "}," << nl;

    // Area
    os << sp << sp << "\"area\": {" << nl;
    os << sp << sp << sp << "\"fu_um2\": "
       << std::setprecision(2) << summary.area.fu_area_um2 << "," << nl;
    os << sp << sp << sp << "\"reg_um2\": "
       << summary.area.reg_area_um2 << "," << nl;
    os << sp << sp << sp << "\"spm_um2\": "
       << summary.area.spm_area_um2 << "," << nl;
    os << sp << sp << sp << "\"cache_um2\": "
       << summary.area.cache_area_um2 << "," << nl;
    os << sp << sp << sp << "\"total_um2\": "
       << summary.area.total_area_um2 << "," << nl;
    os << sp << sp << sp << "\"total_mm2\": "
       << std::setprecision(6) << (summary.area.total_area_um2 / 1000000.0) << nl;
    os << sp << sp << "}," << nl;

    // Cycle tracking summary
    os << sp << sp << "\"cycle_tracking\": {" << nl;
    os << sp << sp << sp << "\"enabled\": "
       << (cycle_tracking ? "true" : "false") << "," << nl;
    os << sp << sp << sp << "\"total_samples\": "
       << summary.cycle_summary.total_samples << "," << nl;
    os << sp << sp << sp << "\"avg_res_in_flight\": "
       << std::setprecision(2) << summary.cycle_summary.avg_res_in_flight
       << "," << nl;
    os << sp << sp << sp << "\"avg_load_in_flight\": "
       << summary.cycle_summary.avg_load_in_flight << "," << nl;
    os << sp << sp << sp << "\"avg_store_in_flight\": "
       << summary.cycle_summary.avg_store_in_flight << "," << nl;
    os << sp << sp << sp << "\"avg_comp_in_flight\": "
       << summary.cycle_summary.avg_comp_in_flight << "," << nl;
    os << sp << sp << sp << "\"peak_res_in_flight\": "
       << summary.cycle_summary.peak_res_in_flight << "," << nl;
    os << sp << sp << sp << "\"peak_load_in_flight\": "
       << summary.cycle_summary.peak_load_in_flight << "," << nl;
    os << sp << sp << sp << "\"peak_store_in_flight\": "
       << summary.cycle_summary.peak_store_in_flight << "," << nl;
    os << sp << sp << sp << "\"peak_comp_in_flight\": "
       << summary.cycle_summary.peak_comp_in_flight << nl;
    os << sp << sp << "}" << nl;

    os << sp << "}" << nl;
    os << "}" << nl;

    return os.str();
}

// ============================================================================
// Output Methods
// ============================================================================

void HWStatistics::printSummary(std::ostream& os) const {
    os << "========== SALAM Statistics Summary ==========\n";
    os << "Accelerator: " << summary.accelerator_name << "\n";
    os << "Total Cycles: " << summary.performance.total_cycles << "\n";
    os << "Stall Cycles: " << summary.performance.stall_cycles
       << " (" << std::fixed << std::setprecision(1)
       << (100.0 * summary.performance.stall_cycles /
           std::max(1, summary.performance.total_cycles)) << "%)\n";
    os << "Clock: " << std::setprecision(3)
       << summary.performance.sys_clock_ghz << " GHz\n";
    os << "Total Power: " << std::setprecision(2)
       << summary.power.total_power << " mW\n";
    os << "Total Area: " << summary.area.total_area_um2 << " um^2 ("
       << std::setprecision(4) << (summary.area.total_area_um2 / 1000000.0)
       << " mm^2)\n";
    if (cycle_tracking) {
        os << "Cycle Samples: " << summary.cycle_summary.total_samples << "\n";
    }
    os << "==============================================\n";
}

void HWStatistics::printDetailed(std::ostream& os) const {
    os << toJSON(true);
}

void HWStatistics::writeJSONFile() {
    if (!output_statistics) return;

    std::ofstream file(output_file);
    if (file.is_open()) {
        file << toJSON(pretty_print);
        file.close();
        std::cout << "Statistics written to: " << output_file << std::endl;
    } else {
        std::cerr << "Failed to open stats file: " << output_file << std::endl;
    }
}

// ============================================================================
// Legacy Methods (for backward compatibility)
// ============================================================================

void HWStatistics::print() {
    if (!DTRACE(SALAMResults)) return;
    printDetailed(std::cout);
}

void HWStatistics::simpleStats() {
    if (!DTRACE(SALAMResultsCSV)) return;
    // Output CSV format
    std::cout << "StatsStart:\n";
    std::cout << summary.performance.setup_time_ns << ",\n";
    std::cout << summary.performance.sim_time_ns << ",\n";
    std::cout << summary.performance.total_cycles << ",\n";
    std::cout << summary.performance.stall_cycles << ",\n";
    std::cout << summary.power.total_power << ",\n";
    std::cout << summary.area.total_area_um2 << "\n";
    std::cout << "StatsEnd:\n";
}

void HWStatistics::unitCorrections() {
    // Recalculate derived values
    summary.power.fu_total = summary.power.fu_leakage + summary.power.fu_dynamic;
    summary.power.reg_total = summary.power.reg_leakage + summary.power.reg_dynamic;
    summary.power.spm_total = summary.power.spm_leakage +
                              summary.power.spm_read_dynamic +
                              summary.power.spm_write_dynamic;
    summary.power.cache_total = summary.power.cache_leakage +
                                summary.power.cache_read_dynamic +
                                summary.power.cache_write_dynamic;
    summary.power.total_power = summary.power.fu_total + summary.power.reg_total;
    summary.power.acc_spm_total = summary.power.total_power + summary.power.spm_total;
    summary.power.acc_cache_total = summary.power.total_power +
                                    summary.power.cache_total;

    summary.area.total_area_um2 = summary.area.fu_area_um2 +
                                  summary.area.reg_area_um2;
    summary.area.acc_spm_area_um2 = summary.area.total_area_um2 +
                                    summary.area.spm_area_um2;
    summary.area.acc_cache_area_um2 = summary.area.total_area_um2 +
                                      summary.area.cache_area_um2;
}

// ============================================================================
// GUI Integration
// ============================================================================

void HWStatistics::publishCycleToGUI(uint64_t cycle) {
    if (!gui_stats_enabled) return;

    gem5::getGUIPublisher().publishQueueState(
        cycle,
        current_cycle_stats.loadInFlight,
        current_cycle_stats.storeInFlight,
        current_cycle_stats.compInFlight
    );
}

void HWStatistics::publishFinalToGUI() {
    if (!gui_stats_enabled) return;

    // Finalize cycle summary before publishing
    summary.cycle_summary = summarizeCycleStats();

    gem5::getGUIPublisher().publishStatsUpdate(
        summary.performance.total_cycles,
        toJSON(false)
    );
}
