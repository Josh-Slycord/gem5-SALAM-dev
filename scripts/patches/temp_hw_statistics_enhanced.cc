#include "hw_statistics.hh"
#include "debug/SALAMResults.hh"
#include "debug/SALAMResultsCSV.hh"
#include "hwacc/gui_publisher.hh"

#include <ctime>
#include <iomanip>
#include <algorithm>
#include <cmath>

// ============================================================================
// Helper Functions
// ============================================================================

const char* getFUTypeName(FUType type) {
    switch (type) {
        case FUType::FU_TYPE_COUNTER:           return "counter";
        case FUType::FU_TYPE_INT_ADD_SUB:       return "int_addsub";
        case FUType::FU_TYPE_INT_MUL_DIV:       return "int_muldiv";
        case FUType::FU_TYPE_INT_SHIFT:         return "int_shift";
        case FUType::FU_TYPE_INT_BITWISE:       return "int_bitwise";
        case FUType::FU_TYPE_FP_FLOAT_ADD_SUB:  return "fp_float_addsub";
        case FUType::FU_TYPE_FP_FLOAT_MUL_DIV:  return "fp_float_muldiv";
        case FUType::FU_TYPE_FP_DOUBLE_ADD_SUB: return "fp_double_addsub";
        case FUType::FU_TYPE_FP_DOUBLE_MUL_DIV: return "fp_double_muldiv";
        case FUType::FU_TYPE_ZERO_CYCLE:        return "zero_cycle";
        case FUType::FU_TYPE_GEP:               return "gep";
        case FUType::FU_TYPE_CONVERSION:        return "conversion";
        case FUType::FU_TYPE_OTHER:             return "other";
        default:                                return "unknown";
    }
}

const char* getStallTypeName(StallType type) {
    switch (type) {
        case StallType::LOAD_ONLY:       return "load_only";
        case StallType::STORE_ONLY:      return "store_only";
        case StallType::COMP_ONLY:       return "comp_only";
        case StallType::LOAD_STORE:      return "load_store";
        case StallType::LOAD_COMP:       return "load_comp";
        case StallType::STORE_COMP:      return "store_comp";
        case StallType::LOAD_STORE_COMP: return "load_store_comp";
        default:                         return "unknown";
    }
}

const char* getStallCauseName(StallCause cause) {
    switch (cause) {
        case StallCause::NONE:            return "none";
        case StallCause::MEMORY_LATENCY:  return "memory_latency";
        case StallCause::RAW_HAZARD:      return "raw_hazard";
        case StallCause::WAW_HAZARD:      return "waw_hazard";
        case StallCause::WAR_HAZARD:      return "war_hazard";
        case StallCause::FU_CONTENTION:   return "fu_contention";
        case StallCause::PORT_CONTENTION: return "port_contention";
        case StallCause::CONTROL_FLOW:    return "control_flow";
        case StallCause::DMA_PENDING:     return "dma_pending";
        case StallCause::RESOURCE_LIMIT:  return "resource_limit";
        default:                          return "unknown";
    }
}

const char* getMemAccessTypeName(MemAccessType type) {
    switch (type) {
        case MemAccessType::CACHE_READ:  return "cache_read";
        case MemAccessType::CACHE_WRITE: return "cache_write";
        case MemAccessType::SPM_READ:    return "spm_read";
        case MemAccessType::SPM_WRITE:   return "spm_write";
        case MemAccessType::DMA_READ:    return "dma_read";
        case MemAccessType::DMA_WRITE:   return "dma_write";
        case MemAccessType::LOCAL_READ:  return "local_read";
        case MemAccessType::LOCAL_WRITE: return "local_write";
        default:                         return "unknown";
    }
}

// ============================================================================
// PowerAreaCoefficients Implementation
// ============================================================================

void PowerAreaCoefficients::setDefaults() {
    // Default 45nm technology coefficients
    technology_node = "45nm";
    voltage = 1.0;
    temperature_c = 25.0;

    // Integer adder
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_ADD_SUB)].area_um2 = 179.443;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_ADD_SUB)].leakage_mw = 2.380803e-03;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_ADD_SUB)].dynamic_read_mw = 8.115300e-03;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_ADD_SUB)].dynamic_write_mw = 6.162853e-03;

    // Integer multiplier
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_MUL_DIV)].area_um2 = 4595.0;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_MUL_DIV)].leakage_mw = 4.817683e-02;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_MUL_DIV)].dynamic_read_mw = 5.725752e-01;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_MUL_DIV)].dynamic_write_mw = 8.662890e-01;

    // Bitwise operations
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_BITWISE)].area_um2 = 50.36996;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_BITWISE)].leakage_mw = 6.111633e-04;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_BITWISE)].dynamic_read_mw = 1.680942e-03;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_BITWISE)].dynamic_write_mw = 1.322420e-03;

    // Shifter
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_SHIFT)].area_um2 = 100.0;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_SHIFT)].leakage_mw = 1.0e-03;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_SHIFT)].dynamic_read_mw = 2.0e-03;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_INT_SHIFT)].dynamic_write_mw = 1.5e-03;

    // FP float adder
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_FLOAT_ADD_SUB)].area_um2 = 1500.0;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_FLOAT_ADD_SUB)].leakage_mw = 1.5e-02;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_FLOAT_ADD_SUB)].dynamic_read_mw = 5.0e-02;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_FLOAT_ADD_SUB)].dynamic_write_mw = 4.0e-02;

    // FP float multiplier
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_FLOAT_MUL_DIV)].area_um2 = 3000.0;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_FLOAT_MUL_DIV)].leakage_mw = 3.0e-02;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_FLOAT_MUL_DIV)].dynamic_read_mw = 1.0e-01;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_FLOAT_MUL_DIV)].dynamic_write_mw = 8.0e-02;

    // FP double adder
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_DOUBLE_ADD_SUB)].area_um2 = 3000.0;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_DOUBLE_ADD_SUB)].leakage_mw = 3.0e-02;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_DOUBLE_ADD_SUB)].dynamic_read_mw = 1.0e-01;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_DOUBLE_ADD_SUB)].dynamic_write_mw = 8.0e-02;

    // FP double multiplier
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_DOUBLE_MUL_DIV)].area_um2 = 6000.0;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_DOUBLE_MUL_DIV)].leakage_mw = 6.0e-02;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_DOUBLE_MUL_DIV)].dynamic_read_mw = 2.0e-01;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_FP_DOUBLE_MUL_DIV)].dynamic_write_mw = 1.5e-01;

    // GEP (address calculation)
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_GEP)].area_um2 = 200.0;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_GEP)].leakage_mw = 2.0e-03;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_GEP)].dynamic_read_mw = 5.0e-03;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_GEP)].dynamic_write_mw = 4.0e-03;

    // Conversion
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_CONVERSION)].area_um2 = 150.0;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_CONVERSION)].leakage_mw = 1.5e-03;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_CONVERSION)].dynamic_read_mw = 4.0e-03;
    fu_coeffs[static_cast<int>(FUType::FU_TYPE_CONVERSION)].dynamic_write_mw = 3.0e-03;

    // Register coefficients
    reg_area_per_bit_um2 = 5.981433;
    reg_leakage_per_bit_mw = 7.395312e-05;
    reg_dynamic_read_mw = 1.322600e-03;
    reg_dynamic_write_mw = 1.792126e-04;

    // Memory coefficients
    spm_leakage_per_kb_mw = 0.5;
    spm_read_dynamic_per_access_mw = 0.1;
    spm_write_dynamic_per_access_mw = 0.15;
    spm_area_per_kb_um2 = 10000.0;

    cache_leakage_per_kb_mw = 0.8;
    cache_read_dynamic_per_access_mw = 0.2;
    cache_write_dynamic_per_access_mw = 0.25;
    cache_area_per_kb_um2 = 15000.0;
}

bool PowerAreaCoefficients::loadFromFile(const std::string& filename) {
    std::ifstream file(filename);
    if (!file.is_open()) {
        setDefaults();
        return false;
    }

    // Simple JSON-like parsing (basic implementation)
    std::string line;
    while (std::getline(file, line)) {
        // Parse key-value pairs (simplified)
        size_t colon = line.find(':');
        if (colon != std::string::npos) {
            std::string key = line.substr(0, colon);
            std::string value = line.substr(colon + 1);
            // Remove quotes and whitespace
            key.erase(std::remove(key.begin(), key.end(), '"'), key.end());
            key.erase(std::remove(key.begin(), key.end(), ' '), key.end());
            value.erase(std::remove(value.begin(), value.end(), '"'), value.end());
            value.erase(std::remove(value.begin(), value.end(), ','), value.end());

            if (key == "technology_node") technology_node = value;
            else if (key == "voltage") voltage = std::stod(value);
            else if (key == "temperature_c") temperature_c = std::stod(value);
            // Add more parsing as needed
        }
    }
    file.close();
    return true;
}

bool PowerAreaCoefficients::saveToFile(const std::string& filename) const {
    std::ofstream file(filename);
    if (!file.is_open()) return false;

    file << "{\n";
    file << "  \"technology_node\": \"" << technology_node << "\",\n";
    file << "  \"voltage\": " << voltage << ",\n";
    file << "  \"temperature_c\": " << temperature_c << ",\n";
    file << "  \"register\": {\n";
    file << "    \"area_per_bit_um2\": " << reg_area_per_bit_um2 << ",\n";
    file << "    \"leakage_per_bit_mw\": " << reg_leakage_per_bit_mw << ",\n";
    file << "    \"dynamic_read_mw\": " << reg_dynamic_read_mw << ",\n";
    file << "    \"dynamic_write_mw\": " << reg_dynamic_write_mw << "\n";
    file << "  },\n";
    file << "  \"spm\": {\n";
    file << "    \"leakage_per_kb_mw\": " << spm_leakage_per_kb_mw << ",\n";
    file << "    \"read_dynamic_per_access_mw\": " << spm_read_dynamic_per_access_mw << ",\n";
    file << "    \"write_dynamic_per_access_mw\": " << spm_write_dynamic_per_access_mw << ",\n";
    file << "    \"area_per_kb_um2\": " << spm_area_per_kb_um2 << "\n";
    file << "  },\n";
    file << "  \"cache\": {\n";
    file << "    \"leakage_per_kb_mw\": " << cache_leakage_per_kb_mw << ",\n";
    file << "    \"read_dynamic_per_access_mw\": " << cache_read_dynamic_per_access_mw << ",\n";
    file << "    \"write_dynamic_per_access_mw\": " << cache_write_dynamic_per_access_mw << ",\n";
    file << "    \"area_per_kb_um2\": " << cache_area_per_kb_um2 << "\n";
    file << "  },\n";
    file << "  \"functional_units\": {\n";
    for (int i = 0; i < static_cast<int>(FUType::FU_TYPE_COUNT); i++) {
        file << "    \"" << getFUTypeName(static_cast<FUType>(i)) << "\": {\n";
        file << "      \"area_um2\": " << fu_coeffs[i].area_um2 << ",\n";
        file << "      \"leakage_mw\": " << fu_coeffs[i].leakage_mw << ",\n";
        file << "      \"dynamic_read_mw\": " << fu_coeffs[i].dynamic_read_mw << ",\n";
        file << "      \"dynamic_write_mw\": " << fu_coeffs[i].dynamic_write_mw << "\n";
        file << "    }" << (i < static_cast<int>(FUType::FU_TYPE_COUNT) - 1 ? "," : "") << "\n";
    }
    file << "  }\n";
    file << "}\n";

    file.close();
    return true;
}

// ============================================================================
// HWStatistics Constructor
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
    hw_params.reset();
    current_cycle_stats.reset();
    summary.reset();
    power_area_config.setDefaults();

    // Initialize cycle tracking buffer if enabled
    if (cycle_tracking) {
        hw_buffer_list.resize(2);
        for (auto& buffer : hw_buffer_list) {
            buffer.resize(stat_buffer_size);
        }
        hw_buffer = hw_buffer_list.begin();
        cycle_buffer = hw_buffer->begin();
    }
}

// ============================================================================
// JSON Formatting Helpers
// ============================================================================

std::string HWStatistics::indent(int level) const {
    return pretty_print ? std::string(level * 2, ' ') : "";
}

void HWStatistics::writeJsonField(std::ostringstream& os, const std::string& key,
                                   int value, int indent_level, bool last) {
    os << indent(indent_level) << "\"" << key << "\": " << value;
    if (!last) os << ",";
    if (pretty_print) os << "\n";
}

void HWStatistics::writeJsonField(std::ostringstream& os, const std::string& key,
                                   int64_t value, int indent_level, bool last) {
    os << indent(indent_level) << "\"" << key << "\": " << value;
    if (!last) os << ",";
    if (pretty_print) os << "\n";
}

void HWStatistics::writeJsonField(std::ostringstream& os, const std::string& key,
                                   uint64_t value, int indent_level, bool last) {
    os << indent(indent_level) << "\"" << key << "\": " << value;
    if (!last) os << ",";
    if (pretty_print) os << "\n";
}

void HWStatistics::writeJsonField(std::ostringstream& os, const std::string& key,
                                   double value, int indent_level, bool last) {
    os << indent(indent_level) << "\"" << key << "\": ";
    if (std::isnan(value) || std::isinf(value)) {
        os << "null";
    } else {
        os << std::fixed << std::setprecision(6) << value;
    }
    if (!last) os << ",";
    if (pretty_print) os << "\n";
}

void HWStatistics::writeJsonField(std::ostringstream& os, const std::string& key,
                                   const std::string& value, int indent_level, bool last) {
    os << indent(indent_level) << "\"" << key << "\": \"" << value << "\"";
    if (!last) os << ",";
    if (pretty_print) os << "\n";
}

void HWStatistics::writeJsonField(std::ostringstream& os, const std::string& key,
                                   bool value, int indent_level, bool last) {
    os << indent(indent_level) << "\"" << key << "\": " << (value ? "true" : "false");
    if (!last) os << ",";
    if (pretty_print) os << "\n";
}

// ============================================================================
// Basic Collection Methods
// ============================================================================

void HWStatistics::setAcceleratorName(const std::string& name) {
    summary.accelerator_name = name;

    // Set timestamp
    auto now = std::chrono::system_clock::now();
    auto time_t_now = std::chrono::system_clock::to_time_t(now);
    std::stringstream ss;
    ss << std::put_time(std::localtime(&time_t_now), "%Y-%m-%dT%H:%M:%S");
    summary.timestamp = ss.str();
}

void HWStatistics::collectPerformanceStats(double setup_ns, double sim_ns,
                                            int clock_period, int cycles, int stalls) {
    summary.performance.setup_time_ns = setup_ns;
    summary.performance.sim_time_ns = sim_ns;
    summary.performance.clock_period_ns = clock_period;
    summary.performance.sys_clock_ghz = clock_period > 0 ? 1.0 / clock_period : 0.0;
    summary.performance.total_cycles = cycles;
    summary.performance.stall_cycles = stalls;
    summary.performance.executed_nodes = cycles - stalls - 1;
}

void HWStatistics::collectStallBreakdown(int load_only, int store_only, int comp_only,
                                          int load_store, int load_comp, int store_comp,
                                          int load_store_comp) {
    summary.performance.stall_breakdown[static_cast<int>(StallType::LOAD_ONLY)] = load_only;
    summary.performance.stall_breakdown[static_cast<int>(StallType::STORE_ONLY)] = store_only;
    summary.performance.stall_breakdown[static_cast<int>(StallType::COMP_ONLY)] = comp_only;
    summary.performance.stall_breakdown[static_cast<int>(StallType::LOAD_STORE)] = load_store;
    summary.performance.stall_breakdown[static_cast<int>(StallType::LOAD_COMP)] = load_comp;
    summary.performance.stall_breakdown[static_cast<int>(StallType::STORE_COMP)] = store_comp;
    summary.performance.stall_breakdown[static_cast<int>(StallType::LOAD_STORE_COMP)] = load_store_comp;
}

void HWStatistics::collectNodeBreakdown(int load_only, int store_only, int comp_only,
                                         int load_store, int load_comp, int store_comp,
                                         int load_store_comp) {
    summary.performance.node_breakdown[static_cast<int>(StallType::LOAD_ONLY)] = load_only;
    summary.performance.node_breakdown[static_cast<int>(StallType::STORE_ONLY)] = store_only;
    summary.performance.node_breakdown[static_cast<int>(StallType::COMP_ONLY)] = comp_only;
    summary.performance.node_breakdown[static_cast<int>(StallType::LOAD_STORE)] = load_store;
    summary.performance.node_breakdown[static_cast<int>(StallType::LOAD_COMP)] = load_comp;
    summary.performance.node_breakdown[static_cast<int>(StallType::STORE_COMP)] = store_comp;
    summary.performance.node_breakdown[static_cast<int>(StallType::LOAD_STORE_COMP)] = load_store_comp;
}

void HWStatistics::collectFUStats(const std::map<int, int>& static_usage,
                                   const std::map<int, int>& runtime_max,
                                   const std::map<int, double>& runtime_occ) {
    for (const auto& p : static_usage) {
        if (p.first < static_cast<int>(FUType::FU_TYPE_COUNT)) {
            summary.functional_units.static_count[p.first] = p.second;
        }
    }
    for (const auto& p : runtime_max) {
        if (p.first < static_cast<int>(FUType::FU_TYPE_COUNT)) {
            summary.functional_units.runtime[p.first].max_concurrent = p.second;
        }
    }
    for (const auto& p : runtime_occ) {
        if (p.first < static_cast<int>(FUType::FU_TYPE_COUNT)) {
            summary.functional_units.runtime[p.first].avg_occupancy = p.second;
        }
    }
}

void HWStatistics::collectMemoryStats(int cache_kb, int cache_ports,
                                       int spm_kb, int spm_read_ports, int spm_write_ports,
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

void HWStatistics::collectRegisterStats(int total, int max_usage, double avg_usage,
                                         double avg_size, int64_t reads, int64_t writes) {
    summary.registers.total = total;
    summary.registers.max_usage = max_usage;
    summary.registers.avg_usage = avg_usage;
    summary.registers.avg_size_bytes = avg_size;
    summary.registers.reads = reads;
    summary.registers.writes = writes;
}

void HWStatistics::collectPowerStats(double fu_leak, double fu_dyn,
                                      double reg_leak, double reg_dyn,
                                      double spm_leak, double spm_read, double spm_write,
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
    summary.power.total_power = summary.power.fu_total + summary.power.reg_total +
                                 summary.power.spm_total + summary.power.cache_total;
}

void HWStatistics::collectAreaStats(double fu_area, double reg_area,
                                     double spm_area, double cache_area) {
    summary.area.fu_area_um2 = fu_area;
    summary.area.reg_area_um2 = reg_area;
    summary.area.spm_area_um2 = spm_area;
    summary.area.cache_area_um2 = cache_area;
    summary.area.total_area_um2 = fu_area + reg_area + spm_area + cache_area;
}

// ============================================================================
// NEW: Enhanced Memory Access Collection
// ============================================================================

void HWStatistics::recordMemoryRead(uint64_t addr, size_t bytes, uint64_t latency,
                                     bool cache_hit, MemAccessType type) {
    auto& mem = summary.memory_access;

    mem.total_bytes_read += bytes;
    mem.recordReadLatency(latency);
    mem.recordAddressAccess(addr, false);

    switch (type) {
        case MemAccessType::CACHE_READ:
            if (cache_hit) {
                mem.cache_hits++;
                mem.cache_read_hits++;
            } else {
                mem.cache_misses++;
                mem.cache_read_misses++;
            }
            break;
        case MemAccessType::SPM_READ:
            mem.spm_reads++;
            mem.spm_read_bytes += bytes;
            break;
        case MemAccessType::DMA_READ:
            mem.dma_read_requests++;
            mem.dma_read_bytes += bytes;
            mem.dma_read_latency_total += latency;
            break;
        default:
            break;
    }
}

void HWStatistics::recordMemoryWrite(uint64_t addr, size_t bytes, uint64_t latency,
                                      bool cache_hit, MemAccessType type) {
    auto& mem = summary.memory_access;

    mem.total_bytes_written += bytes;
    mem.recordWriteLatency(latency);
    mem.recordAddressAccess(addr, true);

    switch (type) {
        case MemAccessType::CACHE_WRITE:
            if (cache_hit) {
                mem.cache_hits++;
                mem.cache_write_hits++;
            } else {
                mem.cache_misses++;
                mem.cache_write_misses++;
            }
            break;
        case MemAccessType::SPM_WRITE:
            mem.spm_writes++;
            mem.spm_write_bytes += bytes;
            break;
        case MemAccessType::DMA_WRITE:
            mem.dma_write_requests++;
            mem.dma_write_bytes += bytes;
            mem.dma_write_latency_total += latency;
            break;
        default:
            break;
    }
}

void HWStatistics::recordPortContention(bool is_read) {
    if (is_read) {
        summary.memory_access.read_port_stalls++;
        summary.stall_breakdown.read_port_stalls++;
    } else {
        summary.memory_access.write_port_stalls++;
        summary.stall_breakdown.write_port_stalls++;
    }
    summary.stall_breakdown.by_cause[static_cast<int>(StallCause::PORT_CONTENTION)]++;
}

void HWStatistics::recordDMATransfer(bool is_read, size_t bytes, uint64_t latency) {
    if (is_read) {
        summary.memory_access.dma_read_requests++;
        summary.memory_access.dma_read_bytes += bytes;
        summary.memory_access.dma_read_latency_total += latency;
    } else {
        summary.memory_access.dma_write_requests++;
        summary.memory_access.dma_write_bytes += bytes;
        summary.memory_access.dma_write_latency_total += latency;
    }
}

// ============================================================================
// NEW: Dataflow/Dependency Collection
// ============================================================================

void HWStatistics::recordDependency(int producer_uid, int consumer_uid,
                                     bool is_raw, bool is_war, bool is_waw) {
    auto& df = summary.dataflow;
    df.total_dependency_edges++;

    if (is_raw) df.true_dependencies++;
    if (is_war) df.anti_dependencies++;
    if (is_waw) df.output_dependencies++;
}

void HWStatistics::recordCriticalPathNode(int uid, int opcode, bool is_load, bool is_store) {
    auto& df = summary.dataflow;
    df.critical_path_instructions++;
    df.critical_path_by_opcode[opcode]++;

    if (is_load) df.critical_path_loads++;
    if (is_store) df.critical_path_stores++;
    if (!is_load && !is_store) df.critical_path_computes++;
}

void HWStatistics::recordParallelism(int ready_count, int issued_count) {
    auto& df = summary.dataflow;
    df.parallelism_histogram[ready_count]++;
    df.total_instructions += issued_count;
    df.max_parallel_ops = std::max(df.max_parallel_ops, ready_count);
}

void HWStatistics::setCriticalPathLength(int length) {
    summary.dataflow.critical_path_length = length;
}

// ============================================================================
// NEW: FU Utilization Collection
// ============================================================================

void HWStatistics::recordFUBusy(FUType type, int instance_id,
                                 uint64_t start_cycle, uint64_t end_cycle) {
    int idx = static_cast<int>(type);
    auto& fu = summary.fu_utilization.by_type[idx];

    uint64_t duration = end_cycle - start_cycle;
    fu.total_busy_cycles += duration;
    fu.total_operations++;
    fu.busy_intervals.push_back({start_cycle, end_cycle});

    summary.fu_utilization.total_fu_busy_cycles += duration;
}

void HWStatistics::recordFUContention(FUType type) {
    int idx = static_cast<int>(type);
    summary.fu_utilization.by_type[idx].contention_stalls++;
    summary.fu_utilization.by_type[idx].contention_requests++;
    summary.fu_utilization.total_contention_stalls++;
    summary.stall_breakdown.fu_stalls_by_type[idx]++;
    summary.stall_breakdown.by_cause[static_cast<int>(StallCause::FU_CONTENTION)]++;
}

void HWStatistics::setFUInstances(FUType type, int count) {
    int idx = static_cast<int>(type);
    summary.fu_utilization.by_type[idx].instances_available = count;
    summary.fu_utilization.by_type[idx].instance_stats.resize(count);
    for (int i = 0; i < count; i++) {
        summary.fu_utilization.by_type[idx].instance_stats[i].instance_id = i;
    }
}

// ============================================================================
// NEW: Stall Tracking
// ============================================================================

void HWStatistics::recordStallCause(StallCause cause) {
    summary.stall_breakdown.recordStall(cause);
}

void HWStatistics::recordNoStall() {
    summary.stall_breakdown.recordNoStall();
}

void HWStatistics::recordFUStall(FUType type) {
    recordFUContention(type);
    recordStallCause(StallCause::FU_CONTENTION);
}

// ============================================================================
// NEW: Power/Area with Activity Factors
// ============================================================================

void HWStatistics::calculatePowerWithActivity() {
    auto& pwr = summary.power;
    auto& cfg = power_area_config;

    // Reset power values
    pwr.fu_leakage = pwr.fu_dynamic = 0.0;

    // Calculate FU power based on actual usage
    for (int i = 0; i < static_cast<int>(FUType::FU_TYPE_COUNT); i++) {
        int count = summary.functional_units.static_count[i];
        double ops = summary.fu_utilization.by_type[i].total_operations;

        pwr.fu_leakage += count * cfg.fu_coeffs[i].leakage_mw;
        pwr.fu_dynamic += ops * (cfg.fu_coeffs[i].dynamic_read_mw +
                                  cfg.fu_coeffs[i].dynamic_write_mw);
    }
    pwr.fu_total = pwr.fu_leakage + pwr.fu_dynamic;

    // Calculate register power
    pwr.reg_leakage = summary.registers.total * 32 * cfg.reg_leakage_per_bit_mw;
    pwr.reg_dynamic = summary.registers.reads * cfg.reg_dynamic_read_mw +
                       summary.registers.writes * cfg.reg_dynamic_write_mw;
    pwr.reg_total = pwr.reg_leakage + pwr.reg_dynamic;

    // Calculate SPM power
    pwr.spm_leakage = summary.memory.spm_size_kb * cfg.spm_leakage_per_kb_mw;
    pwr.spm_read_dynamic = summary.memory_access.spm_reads * cfg.spm_read_dynamic_per_access_mw;
    pwr.spm_write_dynamic = summary.memory_access.spm_writes * cfg.spm_write_dynamic_per_access_mw;
    pwr.spm_total = pwr.spm_leakage + pwr.spm_read_dynamic + pwr.spm_write_dynamic;

    // Calculate cache power
    uint64_t cache_reads = summary.memory_access.cache_read_hits + summary.memory_access.cache_read_misses;
    uint64_t cache_writes = summary.memory_access.cache_write_hits + summary.memory_access.cache_write_misses;
    pwr.cache_leakage = summary.memory.cache_size_kb * cfg.cache_leakage_per_kb_mw;
    pwr.cache_read_dynamic = cache_reads * cfg.cache_read_dynamic_per_access_mw;
    pwr.cache_write_dynamic = cache_writes * cfg.cache_write_dynamic_per_access_mw;
    pwr.cache_total = pwr.cache_leakage + pwr.cache_read_dynamic + pwr.cache_write_dynamic;

    // Total power
    pwr.total_power = pwr.fu_total + pwr.reg_total + pwr.spm_total + pwr.cache_total;

    // Calculate energy (power * time in ns, result in nJ)
    double runtime_ns = summary.performance.total_cycles * summary.performance.clock_period_ns;
    pwr.total_energy_nj = pwr.total_power * runtime_ns / 1e6;  // mW * ns = pJ, /1e6 = nJ
    pwr.fu_energy_nj = pwr.fu_total * runtime_ns / 1e6;
    pwr.mem_energy_nj = (pwr.spm_total + pwr.cache_total) * runtime_ns / 1e6;
    pwr.reg_energy_nj = pwr.reg_total * runtime_ns / 1e6;
}

void HWStatistics::calculateAreaFromConfig() {
    auto& ar = summary.area;
    auto& cfg = power_area_config;

    ar.fu_area_um2 = 0.0;
    for (int i = 0; i < static_cast<int>(FUType::FU_TYPE_COUNT); i++) {
        int count = summary.functional_units.static_count[i];
        double area = count * cfg.fu_coeffs[i].area_um2;
        ar.fu_area_by_type[i] = area;
        ar.fu_area_um2 += area;
    }

    ar.reg_area_um2 = summary.registers.total * 32 * cfg.reg_area_per_bit_um2;
    ar.spm_area_um2 = summary.memory.spm_size_kb * cfg.spm_area_per_kb_um2;
    ar.cache_area_um2 = summary.memory.cache_size_kb * cfg.cache_area_per_kb_um2;
    ar.total_area_um2 = ar.fu_area_um2 + ar.reg_area_um2 + ar.spm_area_um2 + ar.cache_area_um2;
}

bool HWStatistics::loadPowerAreaConfig(const std::string& filename) {
    return power_area_config.loadFromFile(filename);
}

bool HWStatistics::savePowerAreaConfig(const std::string& filename) {
    return power_area_config.saveToFile(filename);
}

// ============================================================================
// Cycle Tracking Methods
// ============================================================================

void HWStatistics::recordCycleStats(const HW_Cycle_Stats& stats) {
    if (!cycle_tracking) return;

    *cycle_buffer = stats;
    ++cycle_buffer;

    if (cycle_buffer == hw_buffer->end()) {
        updateBuffer();
    }
}

CycleStatsSummary HWStatistics::summarizeCycleStats() {
    CycleStatsSummary sum;
    if (!cycle_tracking) return sum;

    uint64_t total_res = 0, total_load = 0, total_store = 0, total_comp = 0;
    int count = 0;

    for (auto& buffer : hw_buffer_list) {
        for (auto& stats : buffer) {
            if (stats.cycle == 0 && count > 0) break;

            total_res += stats.resInFlight;
            total_load += stats.loadInFlight;
            total_store += stats.storeInFlight;
            total_comp += stats.compInFlight;

            sum.peak_res_in_flight = std::max(sum.peak_res_in_flight, stats.resInFlight);
            sum.peak_load_in_flight = std::max(sum.peak_load_in_flight, stats.loadInFlight);
            sum.peak_store_in_flight = std::max(sum.peak_store_in_flight, stats.storeInFlight);
            sum.peak_comp_in_flight = std::max(sum.peak_comp_in_flight, stats.compInFlight);

            sum.total_load_raw_stalls += stats.loadRawStall;
            sum.total_comp_fu_stalls += stats.compFUStall;

            count++;
        }
    }

    sum.total_samples = count;
    if (count > 0) {
        sum.avg_res_in_flight = (double)total_res / count;
        sum.avg_load_in_flight = (double)total_load / count;
        sum.avg_store_in_flight = (double)total_store / count;
        sum.avg_comp_in_flight = (double)total_comp / count;
    }

    return sum;
}

void HWStatistics::updateHWStatsCycleStart() {
    current_cycle_stats.reset();
}

void HWStatistics::updateHWStatsCycleEnd(int curr_cycle) {
    current_cycle_stats.cycle = curr_cycle;
    recordCycleStats(current_cycle_stats);
}

void HWStatistics::updateBuffer() {
    ++hw_buffer;
    if (hw_buffer == hw_buffer_list.end()) {
        hw_buffer = hw_buffer_list.begin();
    }
    cycle_buffer = hw_buffer->begin();
    current_buffer_index = (current_buffer_index + 1) % hw_buffer_list.size();
}

void HWStatistics::clearStats() {
    summary.reset();
    hw_params.reset();
    current_cycle_stats.reset();

    if (cycle_tracking) {
        for (auto& buffer : hw_buffer_list) {
            for (auto& stats : buffer) {
                stats.reset();
            }
        }
        hw_buffer = hw_buffer_list.begin();
        cycle_buffer = hw_buffer->begin();
        current_buffer_index = 0;
    }
}

// ============================================================================
// JSON Serialization for New Stats
// ============================================================================

void HWStatistics::writeMemoryAccessStatsJSON(std::ostringstream& os, int indent_level) const {
    const auto& mem = summary.memory_access;
    std::string nl = pretty_print ? "\n" : "";
    std::string ind = indent(indent_level);
    std::string ind1 = indent(indent_level + 1);
    std::string ind2 = indent(indent_level + 2);

    os << ind << "\"memory_access\": {" << nl;

    // Cache stats
    os << ind1 << "\"cache\": {" << nl;
    writeJsonField(os, "hits", mem.cache_hits, indent_level + 2);
    writeJsonField(os, "misses", mem.cache_misses, indent_level + 2);
    writeJsonField(os, "hit_rate", mem.getCacheHitRate(), indent_level + 2);
    writeJsonField(os, "read_hits", mem.cache_read_hits, indent_level + 2);
    writeJsonField(os, "read_misses", mem.cache_read_misses, indent_level + 2);
    writeJsonField(os, "write_hits", mem.cache_write_hits, indent_level + 2);
    writeJsonField(os, "write_misses", mem.cache_write_misses, indent_level + 2, true);
    os << ind1 << "}," << nl;

    // SPM stats
    os << ind1 << "\"spm\": {" << nl;
    writeJsonField(os, "reads", mem.spm_reads, indent_level + 2);
    writeJsonField(os, "writes", mem.spm_writes, indent_level + 2);
    writeJsonField(os, "read_bytes", mem.spm_read_bytes, indent_level + 2);
    writeJsonField(os, "write_bytes", mem.spm_write_bytes, indent_level + 2, true);
    os << ind1 << "}," << nl;

    // DMA stats
    os << ind1 << "\"dma\": {" << nl;
    writeJsonField(os, "read_requests", mem.dma_read_requests, indent_level + 2);
    writeJsonField(os, "write_requests", mem.dma_write_requests, indent_level + 2);
    writeJsonField(os, "read_bytes", mem.dma_read_bytes, indent_level + 2);
    writeJsonField(os, "write_bytes", mem.dma_write_bytes, indent_level + 2);
    writeJsonField(os, "read_latency_total", mem.dma_read_latency_total, indent_level + 2);
    writeJsonField(os, "write_latency_total", mem.dma_write_latency_total, indent_level + 2, true);
    os << ind1 << "}," << nl;

    // Latency stats
    os << ind1 << "\"latency\": {" << nl;
    writeJsonField(os, "avg_read", mem.getAvgReadLatency(), indent_level + 2);
    writeJsonField(os, "avg_write", mem.getAvgWriteLatency(), indent_level + 2);
    writeJsonField(os, "min_read", mem.min_read_latency == std::numeric_limits<uint64_t>::max() ?
                   0 : (int64_t)mem.min_read_latency, indent_level + 2);
    writeJsonField(os, "max_read", mem.max_read_latency, indent_level + 2);
    writeJsonField(os, "min_write", mem.min_write_latency == std::numeric_limits<uint64_t>::max() ?
                   0 : (int64_t)mem.min_write_latency, indent_level + 2);
    writeJsonField(os, "max_write", mem.max_write_latency, indent_level + 2, true);
    os << ind1 << "}," << nl;

    // Bandwidth stats
    os << ind1 << "\"bandwidth\": {" << nl;
    writeJsonField(os, "total_bytes_read", mem.total_bytes_read, indent_level + 2);
    writeJsonField(os, "total_bytes_written", mem.total_bytes_written, indent_level + 2);
    writeJsonField(os, "peak_read_bytes_per_cycle", mem.peak_read_bytes_per_cycle, indent_level + 2);
    writeJsonField(os, "peak_write_bytes_per_cycle", mem.peak_write_bytes_per_cycle, indent_level + 2, true);
    os << ind1 << "}," << nl;

    // Contention stats
    os << ind1 << "\"contention\": {" << nl;
    writeJsonField(os, "read_port_stalls", mem.read_port_stalls, indent_level + 2);
    writeJsonField(os, "write_port_stalls", mem.write_port_stalls, indent_level + 2);
    writeJsonField(os, "queue_full_stalls", mem.queue_full_stalls, indent_level + 2, true);
    os << ind1 << "}" << nl;

    os << ind << "}";
}

void HWStatistics::writeDataflowStatsJSON(std::ostringstream& os, int indent_level) const {
    const auto& df = summary.dataflow;
    std::string nl = pretty_print ? "\n" : "";
    std::string ind = indent(indent_level);
    std::string ind1 = indent(indent_level + 1);

    os << ind << "\"dataflow\": {" << nl;

    // Critical path
    os << ind1 << "\"critical_path\": {" << nl;
    writeJsonField(os, "length_cycles", df.critical_path_length, indent_level + 2);
    writeJsonField(os, "instructions", df.critical_path_instructions, indent_level + 2);
    writeJsonField(os, "loads", df.critical_path_loads, indent_level + 2);
    writeJsonField(os, "stores", df.critical_path_stores, indent_level + 2);
    writeJsonField(os, "computes", df.critical_path_computes, indent_level + 2, true);
    os << ind1 << "}," << nl;

    // Parallelism
    os << ind1 << "\"parallelism\": {" << nl;
    writeJsonField(os, "ilp", df.getILP(), indent_level + 2);
    writeJsonField(os, "avg_parallelism", df.getAvgParallelism(), indent_level + 2);
    writeJsonField(os, "max_parallel_ops", df.max_parallel_ops, indent_level + 2);
    writeJsonField(os, "total_instructions", df.total_instructions, indent_level + 2, true);
    os << ind1 << "}," << nl;

    // Dependencies
    os << ind1 << "\"dependencies\": {" << nl;
    writeJsonField(os, "raw_true", df.true_dependencies, indent_level + 2);
    writeJsonField(os, "war_anti", df.anti_dependencies, indent_level + 2);
    writeJsonField(os, "waw_output", df.output_dependencies, indent_level + 2);
    writeJsonField(os, "control", df.control_dependencies, indent_level + 2);
    writeJsonField(os, "memory", df.memory_dependencies, indent_level + 2);
    writeJsonField(os, "total_edges", df.total_dependency_edges, indent_level + 2, true);
    os << ind1 << "}" << nl;

    os << ind << "}";
}

void HWStatistics::writeFUUtilizationStatsJSON(std::ostringstream& os, int indent_level) const {
    const auto& fu = summary.fu_utilization;
    std::string nl = pretty_print ? "\n" : "";
    std::string ind = indent(indent_level);
    std::string ind1 = indent(indent_level + 1);
    std::string ind2 = indent(indent_level + 2);

    os << ind << "\"fu_utilization\": {" << nl;

    writeJsonField(os, "total_busy_cycles", fu.total_fu_busy_cycles, indent_level + 1);
    writeJsonField(os, "total_contention_stalls", fu.total_contention_stalls, indent_level + 1);

    os << ind1 << "\"by_type\": {" << nl;
    for (int i = 0; i < static_cast<int>(FUType::FU_TYPE_COUNT); i++) {
        const auto& t = fu.by_type[i];
        bool last_type = (i == static_cast<int>(FUType::FU_TYPE_COUNT) - 1);

        os << ind2 << "\"" << getFUTypeName(static_cast<FUType>(i)) << "\": {" << nl;
        writeJsonField(os, "instances", t.instances_available, indent_level + 3);
        writeJsonField(os, "max_concurrent", t.max_concurrent_used, indent_level + 3);
        writeJsonField(os, "busy_cycles", t.total_busy_cycles, indent_level + 3);
        writeJsonField(os, "operations", t.total_operations, indent_level + 3);
        writeJsonField(os, "contention_stalls", t.contention_stalls, indent_level + 3);
        writeJsonField(os, "contention_rate", t.getContentionRate(), indent_level + 3, true);
        os << ind2 << "}" << (last_type ? "" : ",") << nl;
    }
    os << ind1 << "}," << nl;

    os << ind1 << "\"most_contended\": \"" << getFUTypeName(fu.getMostContentedFU()) << "\"" << nl;

    os << ind << "}";
}

void HWStatistics::writeStallBreakdownJSON(std::ostringstream& os, int indent_level) const {
    const auto& stall = summary.stall_breakdown;
    std::string nl = pretty_print ? "\n" : "";
    std::string ind = indent(indent_level);
    std::string ind1 = indent(indent_level + 1);

    os << ind << "\"stall_breakdown\": {" << nl;

    // By cause
    os << ind1 << "\"by_cause\": {" << nl;
    for (int i = 0; i < static_cast<int>(StallCause::STALL_CAUSE_COUNT); i++) {
        bool last = (i == static_cast<int>(StallCause::STALL_CAUSE_COUNT) - 1);
        writeJsonField(os, getStallCauseName(static_cast<StallCause>(i)),
                       stall.by_cause[i], indent_level + 2, last);
    }
    os << ind1 << "}," << nl;

    // Memory stalls detail
    os << ind1 << "\"memory_detail\": {" << nl;
    writeJsonField(os, "read_stalls", stall.memory_read_stalls, indent_level + 2);
    writeJsonField(os, "write_stalls", stall.memory_write_stalls, indent_level + 2);
    writeJsonField(os, "cache_miss_stalls", stall.cache_miss_stalls, indent_level + 2);
    writeJsonField(os, "dma_stalls", stall.dma_stalls, indent_level + 2, true);
    os << ind1 << "}," << nl;

    // Dependency stalls detail
    os << ind1 << "\"dependency_detail\": {" << nl;
    writeJsonField(os, "raw_stalls", stall.raw_stalls, indent_level + 2);
    writeJsonField(os, "waw_stalls", stall.waw_stalls, indent_level + 2);
    writeJsonField(os, "war_stalls", stall.war_stalls, indent_level + 2, true);
    os << ind1 << "}," << nl;

    // Resource stalls
    os << ind1 << "\"resource_detail\": {" << nl;
    writeJsonField(os, "read_port_stalls", stall.read_port_stalls, indent_level + 2);
    writeJsonField(os, "write_port_stalls", stall.write_port_stalls, indent_level + 2);
    writeJsonField(os, "reservation_full", stall.reservation_full_stalls, indent_level + 2);
    writeJsonField(os, "compute_queue_full", stall.compute_queue_full_stalls, indent_level + 2, true);
    os << ind1 << "}," << nl;

    // Summary
    writeJsonField(os, "total_stall_cycles", stall.total_stall_cycles, indent_level + 1);
    writeJsonField(os, "max_consecutive_stalls", stall.max_consecutive_stalls, indent_level + 1);
    writeJsonField(os, "stall_events", stall.stall_events, indent_level + 1);
    writeJsonField(os, "avg_stall_duration", stall.getAvgStallDuration(), indent_level + 1);
    os << ind1 << "\"dominant_bottleneck\": \"" << stall.getDominantBottleneck() << "\"" << nl;

    os << ind << "}";
}

// ============================================================================
// Main JSON Output
// ============================================================================

std::string HWStatistics::toJSON(bool pretty) const {
    std::ostringstream os;
    std::string nl = pretty ? "\n" : "";
    int ind = 0;

    os << "{" << nl;
    os << indent(1) << "\"salam_stats\": {" << nl;

    // Version and metadata
    writeJsonField(os, "version", summary.version, 2);
    writeJsonField(os, "accelerator_name", summary.accelerator_name, 2);
    writeJsonField(os, "timestamp", summary.timestamp, 2);

    // Performance section
    os << indent(2) << "\"performance\": {" << nl;
    writeJsonField(os, "setup_time_ns", summary.performance.setup_time_ns, 3);
    writeJsonField(os, "sim_time_ns", summary.performance.sim_time_ns, 3);
    writeJsonField(os, "clock_period_ns", summary.performance.clock_period_ns, 3);
    writeJsonField(os, "sys_clock_ghz", summary.performance.sys_clock_ghz, 3);
    writeJsonField(os, "total_cycles", summary.performance.total_cycles, 3);
    writeJsonField(os, "stall_cycles", summary.performance.stall_cycles, 3);
    writeJsonField(os, "executed_nodes", summary.performance.executed_nodes, 3, true);
    os << indent(2) << "}," << nl;

    // Functional units section
    os << indent(2) << "\"functional_units\": {" << nl;
    os << indent(3) << "\"static_count\": {" << nl;
    for (int i = 0; i < static_cast<int>(FUType::FU_TYPE_COUNT); i++) {
        bool last = (i == static_cast<int>(FUType::FU_TYPE_COUNT) - 1);
        writeJsonField(os, getFUTypeName(static_cast<FUType>(i)),
                       summary.functional_units.static_count[i], 4, last);
    }
    os << indent(3) << "}" << nl;
    os << indent(2) << "}," << nl;

    // Memory section
    os << indent(2) << "\"memory\": {" << nl;
    writeJsonField(os, "cache_size_kb", summary.memory.cache_size_kb, 3);
    writeJsonField(os, "spm_size_kb", summary.memory.spm_size_kb, 3);
    writeJsonField(os, "mem_reads", summary.memory.mem_reads, 3);
    writeJsonField(os, "mem_writes", summary.memory.mem_writes, 3);
    writeJsonField(os, "dma_reads", summary.memory.dma_reads, 3);
    writeJsonField(os, "dma_writes", summary.memory.dma_writes, 3, true);
    os << indent(2) << "}," << nl;

    // Power section
    os << indent(2) << "\"power\": {" << nl;
    writeJsonField(os, "fu_total_mw", summary.power.fu_total, 3);
    writeJsonField(os, "reg_total_mw", summary.power.reg_total, 3);
    writeJsonField(os, "spm_total_mw", summary.power.spm_total, 3);
    writeJsonField(os, "cache_total_mw", summary.power.cache_total, 3);
    writeJsonField(os, "total_power_mw", summary.power.total_power, 3);
    writeJsonField(os, "total_energy_nj", summary.power.total_energy_nj, 3, true);
    os << indent(2) << "}," << nl;

    // Area section
    os << indent(2) << "\"area\": {" << nl;
    writeJsonField(os, "fu_area_um2", summary.area.fu_area_um2, 3);
    writeJsonField(os, "reg_area_um2", summary.area.reg_area_um2, 3);
    writeJsonField(os, "spm_area_um2", summary.area.spm_area_um2, 3);
    writeJsonField(os, "cache_area_um2", summary.area.cache_area_um2, 3);
    writeJsonField(os, "total_area_um2", summary.area.total_area_um2, 3);
    writeJsonField(os, "total_area_mm2", summary.area.getTotalAreaMm2(), 3, true);
    os << indent(2) << "}," << nl;

    // NEW: Memory access detailed stats
    writeMemoryAccessStatsJSON(os, 2);
    os << "," << nl;

    // NEW: Dataflow stats
    writeDataflowStatsJSON(os, 2);
    os << "," << nl;

    // NEW: FU utilization stats
    writeFUUtilizationStatsJSON(os, 2);
    os << "," << nl;

    // NEW: Stall breakdown
    writeStallBreakdownJSON(os, 2);
    os << nl;

    os << indent(1) << "}" << nl;
    os << "}" << nl;

    return os.str();
}

// ============================================================================
// Output Methods
// ============================================================================

void HWStatistics::printSummary(std::ostream& os) const {
    os << "================================================================================\n";
    os << "SALAM Statistics Summary: " << summary.accelerator_name << "\n";
    os << "================================================================================\n";
    os << "Performance:\n";
    os << "  Total Cycles:    " << summary.performance.total_cycles << "\n";
    os << "  Stall Cycles:    " << summary.performance.stall_cycles
       << " (" << std::fixed << std::setprecision(1)
       << (100.0 * summary.performance.stall_cycles / std::max(1, summary.performance.total_cycles))
       << "%)\n";
    os << "  Clock:           " << summary.performance.sys_clock_ghz << " GHz\n";

    os << "Bottleneck:        " << summary.stall_breakdown.getDominantBottleneck() << "\n";

    os << "Memory:\n";
    os << "  Cache Hit Rate:  " << std::fixed << std::setprecision(1)
       << (100.0 * summary.memory_access.getCacheHitRate()) << "%\n";
    os << "  Avg Read Latency:" << std::fixed << std::setprecision(1)
       << summary.memory_access.getAvgReadLatency() << " cycles\n";

    os << "Parallelism:\n";
    os << "  ILP:             " << std::fixed << std::setprecision(2)
       << summary.dataflow.getILP() << "\n";
    os << "  Critical Path:   " << summary.dataflow.critical_path_length << " cycles\n";

    os << "Power/Area:\n";
    os << "  Total Power:     " << std::fixed << std::setprecision(3)
       << summary.power.total_power << " mW\n";
    os << "  Total Area:      " << std::fixed << std::setprecision(3)
       << summary.area.getTotalAreaMm2() << " mm²\n";
    os << "================================================================================\n";
}

void HWStatistics::printDetailed(std::ostream& os) const {
    os << toJSON(true);
}

void HWStatistics::writeJSONFile() {
    if (output_file.empty()) return;

    std::ofstream file(output_file);
    if (file.is_open()) {
        file << toJSON(pretty_print);
        file.close();
        std::cout << "Statistics written to: " << output_file << "\n";
    } else {
        std::cerr << "Error: Could not open " << output_file << " for writing\n";
    }
}

// ============================================================================
// Legacy Methods
// ============================================================================

void HWStatistics::print() {
    if (!debug::SALAMResults) return;
    printDetailed(std::cout);
}

void HWStatistics::simpleStats() {
    if (!debug::SALAMResults) return;
    if (!debug::SALAMResultsCSV) return;
    // CSV output could go here
}

void HWStatistics::unitCorrections() {
    // Unit conversion if needed
}

// ============================================================================
// GUI Publishing Methods
// ============================================================================

void HWStatistics::publishCycleToGUI(uint64_t cycle) {
    if (!gui_stats_enabled) return;

    auto& pub = gem5::getGUIPublisher();
    if (!pub.isEnabled()) return;

    pub.publishQueueState(cycle,
                          current_cycle_stats.loadInFlight,
                          current_cycle_stats.storeInFlight,
                          current_cycle_stats.compInFlight);
}

void HWStatistics::publishFinalToGUI() {
    if (!gui_stats_enabled) return;

    auto& pub = gem5::getGUIPublisher();
    if (!pub.isEnabled()) return;

    pub.publishStatsUpdate(summary.performance.total_cycles, toJSON(false));
    pub.publishSimulationEnd(summary.performance.total_cycles);
}

void HWStatistics::publishMemoryAccess(uint64_t cycle, uint64_t addr, size_t bytes,
                                        bool is_write, const std::string& source) {
    if (!gui_stats_enabled) return;

    auto& pub = gem5::getGUIPublisher();
    if (!pub.isEnabled()) return;

    // Build JSON message
    std::ostringstream json;
    json << "{\"type\":\"memory_access\","
         << "\"cycle\":" << cycle << ","
         << "\"address\":" << addr << ","
         << "\"bytes\":" << bytes << ","
         << "\"is_write\":" << (is_write ? "true" : "false") << ","
         << "\"source\":\"" << source << "\"}";

    pub.publishStatsUpdate(cycle, json.str());
}

void HWStatistics::publishFUActivity(uint64_t start_cycle, uint64_t end_cycle,
                                      FUType type, int instance, int uid) {
    if (!gui_stats_enabled) return;

    auto& pub = gem5::getGUIPublisher();
    if (!pub.isEnabled()) return;

    std::ostringstream json;
    json << "{\"type\":\"fu_activity\","
         << "\"start_cycle\":" << start_cycle << ","
         << "\"end_cycle\":" << end_cycle << ","
         << "\"fu_type\":\"" << getFUTypeName(type) << "\","
         << "\"instance\":" << instance << ","
         << "\"uid\":" << uid << "}";

    pub.publishStatsUpdate(start_cycle, json.str());
}

void HWStatistics::publishDataflowNode(uint64_t cycle, int uid, const std::string& opcode,
                                        int queue_id, const std::vector<int>& deps) {
    if (!gui_stats_enabled) return;

    auto& pub = gem5::getGUIPublisher();
    if (!pub.isEnabled()) return;

    std::ostringstream json;
    json << "{\"type\":\"dataflow_node\","
         << "\"cycle\":" << cycle << ","
         << "\"uid\":" << uid << ","
         << "\"opcode\":\"" << opcode << "\","
         << "\"queue\":" << queue_id << ","
         << "\"dependencies\":[";
    for (size_t i = 0; i < deps.size(); i++) {
        if (i > 0) json << ",";
        json << deps[i];
    }
    json << "]}";

    pub.publishStatsUpdate(cycle, json.str());
}

void HWStatistics::publishDataflowEdge(uint64_t cycle, int producer, int consumer,
                                        bool on_critical_path) {
    if (!gui_stats_enabled) return;

    auto& pub = gem5::getGUIPublisher();
    if (!pub.isEnabled()) return;

    std::ostringstream json;
    json << "{\"type\":\"dataflow_edge\","
         << "\"cycle\":" << cycle << ","
         << "\"producer\":" << producer << ","
         << "\"consumer\":" << consumer << ","
         << "\"critical\":" << (on_critical_path ? "true" : "false") << "}";

    pub.publishStatsUpdate(cycle, json.str());
}

void HWStatistics::publishStallEvent(uint64_t cycle, StallCause cause, int uid) {
    if (!gui_stats_enabled) return;

    auto& pub = gem5::getGUIPublisher();
    if (!pub.isEnabled()) return;

    pub.publishStallEvent(cycle, uid, getStallCauseName(cause));
}

void HWStatistics::publishPipelineSnapshot(uint64_t cycle, int res_depth, int comp_depth,
                                            int read_depth, int write_depth) {
    if (!gui_stats_enabled) return;

    auto& pub = gem5::getGUIPublisher();
    if (!pub.isEnabled()) return;

    pub.publishQueueState(cycle, read_depth, write_depth, comp_depth);
}
