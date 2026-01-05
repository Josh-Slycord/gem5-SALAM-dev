#ifndef __HWMODEL_HW_STATISTICS_HH__
#define __HWMODEL_HW_STATISTICS_HH__

#include "params/HWStatistics.hh"
#include "sim/sim_object.hh"
#include "hwacc/LLVMRead/src/debug_flags.hh"

#include <iostream>
#include <iomanip>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
#include <map>
#include <ctime>
#include <chrono>

using namespace gem5;

// Forward declaration
class GUIPublisher;

// ============================================================================
// Stall/Node Type Enumerations
// ============================================================================

enum class StallType {
    LOAD_ONLY = 0,
    STORE_ONLY,
    COMP_ONLY,
    LOAD_STORE,
    LOAD_COMP,
    STORE_COMP,
    LOAD_STORE_COMP,
    COUNT
};

enum class FUType {
    COUNTER = 0,
    INT_ADD_SUB,
    INT_MUL_DIV,
    INT_SHIFT,
    INT_BITWISE,
    FP_FLOAT_ADD_SUB,
    FP_FLOAT_MUL_DIV,
    FP_DOUBLE_ADD_SUB,
    FP_DOUBLE_MUL_DIV,
    ZERO_CYCLE,
    GEP,
    CONVERSION,
    OTHER,
    COUNT
};

// ============================================================================
// Summary Statistics Structs (consolidated from Results class)
// ============================================================================

struct PerformanceStats {
    double setup_time_ns = 0.0;
    double sim_time_ns = 0.0;
    int clock_period_ns = 0;
    double sys_clock_ghz = 0.0;
    int total_cycles = 0;
    int stall_cycles = 0;
    int executed_nodes = 0;

    // Stall breakdown by type
    int stall_breakdown[static_cast<int>(StallType::COUNT)] = {0};

    // Node breakdown by type
    int node_breakdown[static_cast<int>(StallType::COUNT)] = {0};

    void reset() {
        setup_time_ns = sim_time_ns = 0.0;
        clock_period_ns = total_cycles = stall_cycles = executed_nodes = 0;
        sys_clock_ghz = 0.0;
        for (int i = 0; i < static_cast<int>(StallType::COUNT); i++) {
            stall_breakdown[i] = node_breakdown[i] = 0;
        }
    }
};

struct FURuntimeStats {
    int max_concurrent = 0;
    double avg_occupancy = 0.0;
};

struct FunctionalUnitStats {
    // Runtime stats per FU type
    FURuntimeStats runtime[static_cast<int>(FUType::COUNT)];

    // Static counts per FU type
    int static_count[static_cast<int>(FUType::COUNT)] = {0};

    void reset() {
        for (int i = 0; i < static_cast<int>(FUType::COUNT); i++) {
            runtime[i].max_concurrent = 0;
            runtime[i].avg_occupancy = 0.0;
            static_count[i] = 0;
        }
    }
};

struct MemoryStats {
    int cache_size_kb = 0;
    int cache_ports = 0;
    int spm_size_kb = 0;
    int spm_read_ports = 0;
    int spm_write_ports = 0;
    int read_bus_width = 0;
    int write_bus_width = 0;
    int local_ports = 0;
    int64_t mem_reads = 0;
    int64_t mem_writes = 0;
    int64_t dma_reads = 0;
    int64_t dma_writes = 0;

    void reset() {
        cache_size_kb = cache_ports = 0;
        spm_size_kb = spm_read_ports = spm_write_ports = 0;
        read_bus_width = write_bus_width = local_ports = 0;
        mem_reads = mem_writes = dma_reads = dma_writes = 0;
    }
};

struct RegisterStats {
    int total = 0;
    int max_usage = 0;
    double avg_usage = 0.0;
    double avg_size_bytes = 0.0;
    int64_t reads = 0;
    int64_t writes = 0;

    void reset() {
        total = max_usage = 0;
        avg_usage = avg_size_bytes = 0.0;
        reads = writes = 0;
    }
};

struct PowerStats {
    double fu_leakage = 0.0;
    double fu_dynamic = 0.0;
    double fu_total = 0.0;
    double reg_leakage = 0.0;
    double reg_dynamic = 0.0;
    double reg_total = 0.0;
    double spm_leakage = 0.0;
    double spm_read_dynamic = 0.0;
    double spm_write_dynamic = 0.0;
    double spm_total = 0.0;
    double cache_leakage = 0.0;
    double cache_read_dynamic = 0.0;
    double cache_write_dynamic = 0.0;
    double cache_total = 0.0;
    double total_power = 0.0;
    double acc_spm_total = 0.0;
    double acc_cache_total = 0.0;

    void reset() {
        fu_leakage = fu_dynamic = fu_total = 0.0;
        reg_leakage = reg_dynamic = reg_total = 0.0;
        spm_leakage = spm_read_dynamic = spm_write_dynamic = spm_total = 0.0;
        cache_leakage = cache_read_dynamic = cache_write_dynamic = 0.0;
        cache_total = total_power = acc_spm_total = acc_cache_total = 0.0;
    }
};

struct AreaStats {
    double fu_area_um2 = 0.0;
    double reg_area_um2 = 0.0;
    double spm_area_um2 = 0.0;
    double cache_area_um2 = 0.0;
    double total_area_um2 = 0.0;
    double acc_spm_area_um2 = 0.0;
    double acc_cache_area_um2 = 0.0;

    void reset() {
        fu_area_um2 = reg_area_um2 = spm_area_um2 = cache_area_um2 = 0.0;
        total_area_um2 = acc_spm_area_um2 = acc_cache_area_um2 = 0.0;
    }
};

struct CycleStatsSummary {
    int total_samples = 0;
    double avg_res_in_flight = 0.0;
    double avg_load_in_flight = 0.0;
    double avg_store_in_flight = 0.0;
    double avg_comp_in_flight = 0.0;
    int peak_res_in_flight = 0;
    int peak_load_in_flight = 0;
    int peak_store_in_flight = 0;
    int peak_comp_in_flight = 0;
    int total_load_raw_stalls = 0;
    int total_comp_fu_stalls = 0;
};

struct SummaryStats {
    std::string accelerator_name;
    std::string timestamp;
    PerformanceStats performance;
    FunctionalUnitStats functional_units;
    MemoryStats memory;
    RegisterStats registers;
    PowerStats power;
    AreaStats area;
    CycleStatsSummary cycle_summary;

    void reset() {
        accelerator_name.clear();
        timestamp.clear();
        performance.reset();
        functional_units.reset();
        memory.reset();
        registers.reset();
        power.reset();
        area.reset();
        cycle_summary = CycleStatsSummary();
    }
};

// ============================================================================
// Legacy structs (for backward compatibility)
// ============================================================================

struct HW_Params {
    int run_end = 0;
    void reset() { run_end = 0; }
};

struct HW_Cycle_Stats {
    int cycle = 0;
    int resInFlight = 0;
    int loadInFlight = 0;
    int loadInternal = 0;
    int loadAcitve = 0;
    int loadRawStall = 0;
    int storeInFlight = 0;
    int storeActive = 0;
    int compInFlight = 0;
    int compLaunched = 0;
    int compActive = 0;
    int compFUStall = 0;
    int compCommited = 0;

    void reset() {
        cycle = resInFlight = loadInFlight = loadInternal = 0;
        loadAcitve = loadRawStall = storeInFlight = storeActive = 0;
        compInFlight = compLaunched = compActive = compFUStall = 0;
        compCommited = 0;
    }
};

// ============================================================================
// Main HWStatistics Class
// ============================================================================

class HWStatistics : public SimObject
{
  private:
    HW_Params hw_params;
    HW_Cycle_Stats current_cycle_stats;
    std::vector<HW_Cycle_Stats>::iterator cycle_buffer;
    std::vector<std::vector<HW_Cycle_Stats>> hw_buffer_list;
    std::vector<std::vector<HW_Cycle_Stats>>::iterator hw_buffer;
    int current_buffer_index = 0;

    bool cycle_tracking;
    bool output_statistics;
    std::string output_file;
    bool pretty_print;
    bool gui_stats_enabled;
    int stat_buffer_size;
    bool dbg;

    SummaryStats summary;

    std::string indent(int level) const;
    void writeJsonField(std::ostringstream& os, const std::string& key,
                        int value, int indent_level, bool last = false);
    void writeJsonField(std::ostringstream& os, const std::string& key,
                        int64_t value, int indent_level, bool last = false);
    void writeJsonField(std::ostringstream& os, const std::string& key,
                        double value, int indent_level, bool last = false);
    void writeJsonField(std::ostringstream& os, const std::string& key,
                        const std::string& value, int indent_level,
                        bool last = false);
    void writeJsonField(std::ostringstream& os, const std::string& key,
                        bool value, int indent_level, bool last = false);

  public:
    HWStatistics(const HWStatisticsParams &params);

    bool use_cycle_tracking() const { return cycle_tracking; }
    bool isOutputEnabled() const { return output_statistics; }
    bool isGuiEnabled() const { return gui_stats_enabled; }
    std::string getOutputFile() const { return output_file; }

    void setAcceleratorName(const std::string& name);
    void collectPerformanceStats(double setup_ns, double sim_ns,
                                 int clock_period, int cycles, int stalls);
    void collectStallBreakdown(int load_only, int store_only, int comp_only,
                               int load_store, int load_comp, int store_comp,
                               int load_store_comp);
    void collectNodeBreakdown(int load_only, int store_only, int comp_only,
                              int load_store, int load_comp, int store_comp,
                              int load_store_comp);
    void collectFUStats(const std::map<int, int>& static_usage,
                        const std::map<int, int>& runtime_max,
                        const std::map<int, double>& runtime_occ);
    void collectMemoryStats(int cache_kb, int cache_ports,
                            int spm_kb, int spm_read_ports, int spm_write_ports,
                            int64_t mem_reads, int64_t mem_writes,
                            int64_t dma_reads, int64_t dma_writes);
    void collectRegisterStats(int total, int max_usage, double avg_usage,
                              double avg_size, int64_t reads, int64_t writes);
    void collectPowerStats(double fu_leak, double fu_dyn,
                           double reg_leak, double reg_dyn,
                           double spm_leak, double spm_read, double spm_write,
                           double cache_leak, double cache_read,
                           double cache_write);
    void collectAreaStats(double fu_area, double reg_area,
                          double spm_area, double cache_area);

    void recordCycleStats(const HW_Cycle_Stats& stats);
    CycleStatsSummary summarizeCycleStats();
    void updateHWStatsCycleStart();
    void updateHWStatsCycleEnd(int curr_cycle);
    void updateBuffer();
    void clearStats();

    std::string toJSON(bool pretty = true) const;
    void printSummary(std::ostream& os) const;
    void printDetailed(std::ostream& os) const;
    void writeJSONFile();

    void print();
    void simpleStats();
    void unitCorrections();

    void publishCycleToGUI(uint64_t cycle);
    void publishFinalToGUI();
};

const char* getFUTypeName(FUType type);
const char* getStallTypeName(StallType type);

#endif //__HWMODEL_HW_STATISTICS_HH__
