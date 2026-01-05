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
#include <algorithm>
#include <cmath>
#include <limits>

using namespace gem5;

// Forward declarations
class GUIPublisher;

// ============================================================================
// Enumerations
// ============================================================================

enum class StallType {
    LOAD_ONLY = 0,
    STORE_ONLY,
    COMP_ONLY,
    LOAD_STORE,
    LOAD_COMP,
    STORE_COMP,
    LOAD_STORE_COMP,
    STALL_TYPE_COUNT
};

enum class FUType {
    FU_TYPE_COUNTER = 0,
    FU_TYPE_INT_ADD_SUB,
    FU_TYPE_INT_MUL_DIV,
    FU_TYPE_INT_SHIFT,
    FU_TYPE_INT_BITWISE,
    FU_TYPE_FP_FLOAT_ADD_SUB,
    FU_TYPE_FP_FLOAT_MUL_DIV,
    FU_TYPE_FP_DOUBLE_ADD_SUB,
    FU_TYPE_FP_DOUBLE_MUL_DIV,
    FU_TYPE_ZERO_CYCLE,
    FU_TYPE_GEP,
    FU_TYPE_CONVERSION,
    FU_TYPE_OTHER,
    FU_TYPE_COUNT
};

// New: Stall root cause enumeration
enum class StallCause {
    NONE = 0,
    MEMORY_LATENCY,      // Waiting for memory response
    RAW_HAZARD,          // Read-after-write dependency
    WAW_HAZARD,          // Write-after-write dependency
    WAR_HAZARD,          // Write-after-read dependency
    FU_CONTENTION,       // Functional unit busy
    PORT_CONTENTION,     // Memory port unavailable
    CONTROL_FLOW,        // Branch resolution pending
    DMA_PENDING,         // DMA transfer in progress
    RESOURCE_LIMIT,      // Queue/buffer full
    STALL_CAUSE_COUNT
};

// New: Memory access type enumeration
enum class MemAccessType {
    CACHE_READ = 0,
    CACHE_WRITE,
    SPM_READ,
    SPM_WRITE,
    DMA_READ,
    DMA_WRITE,
    LOCAL_READ,
    LOCAL_WRITE,
    MEM_ACCESS_TYPE_COUNT
};

// ============================================================================
// NEW: Memory Access Statistics
// ============================================================================

struct MemoryAccessStats {
    // Cache statistics
    uint64_t cache_hits = 0;
    uint64_t cache_misses = 0;
    uint64_t cache_read_hits = 0;
    uint64_t cache_read_misses = 0;
    uint64_t cache_write_hits = 0;
    uint64_t cache_write_misses = 0;

    // SPM statistics
    uint64_t spm_reads = 0;
    uint64_t spm_writes = 0;
    uint64_t spm_read_bytes = 0;
    uint64_t spm_write_bytes = 0;

    // DMA statistics
    uint64_t dma_read_requests = 0;
    uint64_t dma_write_requests = 0;
    uint64_t dma_read_bytes = 0;
    uint64_t dma_write_bytes = 0;
    uint64_t dma_read_latency_total = 0;
    uint64_t dma_write_latency_total = 0;

    // Latency distribution (in cycles)
    uint64_t total_read_latency = 0;
    uint64_t total_write_latency = 0;
    uint64_t min_read_latency = std::numeric_limits<uint64_t>::max();
    uint64_t max_read_latency = 0;
    uint64_t min_write_latency = std::numeric_limits<uint64_t>::max();
    uint64_t max_write_latency = 0;
    uint64_t read_count = 0;
    uint64_t write_count = 0;

    // Bandwidth tracking
    uint64_t total_bytes_read = 0;
    uint64_t total_bytes_written = 0;
    uint64_t peak_read_bandwidth_cycle = 0;
    uint64_t peak_write_bandwidth_cycle = 0;
    uint64_t peak_read_bytes_per_cycle = 0;
    uint64_t peak_write_bytes_per_cycle = 0;

    // Contention tracking
    uint64_t read_port_stalls = 0;
    uint64_t write_port_stalls = 0;
    uint64_t queue_full_stalls = 0;

    // Access pattern tracking (for heatmap)
    std::map<uint64_t, uint64_t> address_read_counts;   // addr -> count
    std::map<uint64_t, uint64_t> address_write_counts;  // addr -> count
    uint64_t address_granularity = 64;  // Cache line size for bucketing

    // Computed metrics
    double getCacheHitRate() const {
        uint64_t total = cache_hits + cache_misses;
        return total > 0 ? (double)cache_hits / total : 0.0;
    }

    double getAvgReadLatency() const {
        return read_count > 0 ? (double)total_read_latency / read_count : 0.0;
    }

    double getAvgWriteLatency() const {
        return write_count > 0 ? (double)total_write_latency / write_count : 0.0;
    }

    double getReadBandwidthUtilization(uint64_t total_cycles, int bus_width) const {
        if (total_cycles == 0 || bus_width == 0) return 0.0;
        double max_bytes = (double)total_cycles * bus_width;
        return total_bytes_read / max_bytes;
    }

    double getWriteBandwidthUtilization(uint64_t total_cycles, int bus_width) const {
        if (total_cycles == 0 || bus_width == 0) return 0.0;
        double max_bytes = (double)total_cycles * bus_width;
        return total_bytes_written / max_bytes;
    }

    void recordReadLatency(uint64_t latency) {
        total_read_latency += latency;
        read_count++;
        min_read_latency = std::min(min_read_latency, latency);
        max_read_latency = std::max(max_read_latency, latency);
    }

    void recordWriteLatency(uint64_t latency) {
        total_write_latency += latency;
        write_count++;
        min_write_latency = std::min(min_write_latency, latency);
        max_write_latency = std::max(max_write_latency, latency);
    }

    void recordAddressAccess(uint64_t addr, bool is_write) {
        uint64_t bucket = (addr / address_granularity) * address_granularity;
        if (is_write) {
            address_write_counts[bucket]++;
        } else {
            address_read_counts[bucket]++;
        }
    }

    void reset() {
        cache_hits = cache_misses = 0;
        cache_read_hits = cache_read_misses = 0;
        cache_write_hits = cache_write_misses = 0;
        spm_reads = spm_writes = spm_read_bytes = spm_write_bytes = 0;
        dma_read_requests = dma_write_requests = 0;
        dma_read_bytes = dma_write_bytes = 0;
        dma_read_latency_total = dma_write_latency_total = 0;
        total_read_latency = total_write_latency = 0;
        min_read_latency = min_write_latency = std::numeric_limits<uint64_t>::max();
        max_read_latency = max_write_latency = 0;
        read_count = write_count = 0;
        total_bytes_read = total_bytes_written = 0;
        peak_read_bandwidth_cycle = peak_write_bandwidth_cycle = 0;
        peak_read_bytes_per_cycle = peak_write_bytes_per_cycle = 0;
        read_port_stalls = write_port_stalls = queue_full_stalls = 0;
        address_read_counts.clear();
        address_write_counts.clear();
    }
};

// ============================================================================
// NEW: Dataflow/Dependency Analysis Statistics
// ============================================================================

struct DataflowStats {
    // Critical path analysis
    int critical_path_length = 0;        // Longest dependency chain (cycles)
    int critical_path_instructions = 0;  // Number of instructions on critical path
    int critical_path_loads = 0;         // Loads on critical path
    int critical_path_stores = 0;        // Stores on critical path
    int critical_path_computes = 0;      // Compute ops on critical path

    // Instruction-Level Parallelism (ILP)
    double avg_ready_instructions = 0.0;  // Avg instructions ready per cycle
    double avg_issued_per_cycle = 0.0;    // Actual IPC achieved
    int max_parallel_ops = 0;             // Peak parallelism observed
    int total_instructions = 0;           // Total dynamic instructions

    // Dependency breakdown
    uint64_t true_dependencies = 0;       // RAW (Read-After-Write)
    uint64_t anti_dependencies = 0;       // WAR (Write-After-Read)
    uint64_t output_dependencies = 0;     // WAW (Write-After-Write)
    uint64_t control_dependencies = 0;    // Branch dependencies
    uint64_t memory_dependencies = 0;     // Memory ordering dependencies

    // Dependency chain statistics
    double avg_dependency_depth = 0.0;    // Average depth of dependency chains
    int max_dependency_depth = 0;         // Maximum depth observed
    int total_dependency_edges = 0;       // Total producer-consumer edges

    // Parallelism histogram (instructions ready per cycle)
    std::map<int, uint64_t> parallelism_histogram;  // parallel_count -> cycle_count

    // Critical path breakdown by instruction type
    std::map<int, int> critical_path_by_opcode;  // opcode -> count on critical path

    double getAvgParallelism() const {
        if (parallelism_histogram.empty()) return 0.0;
        uint64_t total_ready = 0, total_cycles = 0;
        for (const auto& p : parallelism_histogram) {
            total_ready += p.first * p.second;
            total_cycles += p.second;
        }
        return total_cycles > 0 ? (double)total_ready / total_cycles : 0.0;
    }

    double getILP() const {
        return critical_path_length > 0 ?
               (double)total_instructions / critical_path_length : 0.0;
    }

    void reset() {
        critical_path_length = critical_path_instructions = 0;
        critical_path_loads = critical_path_stores = critical_path_computes = 0;
        avg_ready_instructions = avg_issued_per_cycle = 0.0;
        max_parallel_ops = total_instructions = 0;
        true_dependencies = anti_dependencies = output_dependencies = 0;
        control_dependencies = memory_dependencies = 0;
        avg_dependency_depth = 0.0;
        max_dependency_depth = total_dependency_edges = 0;
        parallelism_histogram.clear();
        critical_path_by_opcode.clear();
    }
};

// ============================================================================
// NEW: Enhanced Functional Unit Utilization Statistics
// ============================================================================

struct FUInstanceStats {
    int instance_id = 0;
    uint64_t busy_cycles = 0;
    uint64_t idle_cycles = 0;
    uint64_t operations_executed = 0;

    double getUtilization(uint64_t total_cycles) const {
        return total_cycles > 0 ? (double)busy_cycles / total_cycles : 0.0;
    }
};

struct FUTypeUtilizationStats {
    FUType type;
    int instances_available = 0;
    int max_concurrent_used = 0;
    uint64_t total_busy_cycles = 0;      // Sum across all instances
    uint64_t total_operations = 0;
    uint64_t contention_stalls = 0;      // Cycles wanted FU but none available
    uint64_t contention_requests = 0;    // Number of times contention occurred

    // Per-instance tracking
    std::vector<FUInstanceStats> instance_stats;

    // Temporal utilization (for Gantt chart)
    std::vector<std::pair<uint64_t, uint64_t>> busy_intervals;  // (start, end) cycles

    double getOverallUtilization(uint64_t total_cycles) const {
        if (total_cycles == 0 || instances_available == 0) return 0.0;
        return (double)total_busy_cycles / (total_cycles * instances_available);
    }

    double getContentionRate() const {
        uint64_t total_requests = total_operations + contention_requests;
        return total_requests > 0 ? (double)contention_requests / total_requests : 0.0;
    }

    void reset() {
        instances_available = max_concurrent_used = 0;
        total_busy_cycles = total_operations = 0;
        contention_stalls = contention_requests = 0;
        instance_stats.clear();
        busy_intervals.clear();
    }
};

struct FUUtilizationStats {
    FUTypeUtilizationStats by_type[static_cast<int>(FUType::FU_TYPE_COUNT)];

    uint64_t total_fu_busy_cycles = 0;
    uint64_t total_fu_idle_cycles = 0;
    uint64_t total_contention_stalls = 0;

    // Aggregate utilization
    double getOverallUtilization(uint64_t total_cycles) const {
        uint64_t total_capacity = 0;
        for (int i = 0; i < static_cast<int>(FUType::FU_TYPE_COUNT); i++) {
            total_capacity += total_cycles * by_type[i].instances_available;
        }
        return total_capacity > 0 ? (double)total_fu_busy_cycles / total_capacity : 0.0;
    }

    FUType getMostContentedFU() const {
        FUType most_contended = FUType::FU_TYPE_OTHER;
        uint64_t max_contention = 0;
        for (int i = 0; i < static_cast<int>(FUType::FU_TYPE_COUNT); i++) {
            if (by_type[i].contention_stalls > max_contention) {
                max_contention = by_type[i].contention_stalls;
                most_contended = static_cast<FUType>(i);
            }
        }
        return most_contended;
    }

    void reset() {
        for (int i = 0; i < static_cast<int>(FUType::FU_TYPE_COUNT); i++) {
            by_type[i].reset();
            by_type[i].type = static_cast<FUType>(i);
        }
        total_fu_busy_cycles = total_fu_idle_cycles = total_contention_stalls = 0;
    }
};

// ============================================================================
// NEW: Stall Root Cause Breakdown
// ============================================================================

struct StallBreakdown {
    // Per-cause stall counts (in cycles)
    uint64_t by_cause[static_cast<int>(StallCause::STALL_CAUSE_COUNT)] = {0};

    // Detailed memory stalls
    uint64_t memory_read_stalls = 0;
    uint64_t memory_write_stalls = 0;
    uint64_t cache_miss_stalls = 0;
    uint64_t dma_stalls = 0;

    // Detailed dependency stalls
    uint64_t raw_stalls = 0;
    uint64_t waw_stalls = 0;
    uint64_t war_stalls = 0;

    // Resource stalls
    uint64_t fu_stalls_by_type[static_cast<int>(FUType::FU_TYPE_COUNT)] = {0};
    uint64_t read_port_stalls = 0;
    uint64_t write_port_stalls = 0;
    uint64_t reservation_full_stalls = 0;
    uint64_t compute_queue_full_stalls = 0;

    // Stall duration tracking
    uint64_t total_stall_cycles = 0;
    uint64_t max_consecutive_stalls = 0;
    uint64_t current_stall_streak = 0;
    uint64_t stall_events = 0;  // Number of times we entered stall state

    double getAvgStallDuration() const {
        return stall_events > 0 ? (double)total_stall_cycles / stall_events : 0.0;
    }

    StallCause getDominantCause() const {
        StallCause dominant = StallCause::NONE;
        uint64_t max_stalls = 0;
        for (int i = 1; i < static_cast<int>(StallCause::STALL_CAUSE_COUNT); i++) {
            if (by_cause[i] > max_stalls) {
                max_stalls = by_cause[i];
                dominant = static_cast<StallCause>(i);
            }
        }
        return dominant;
    }

    std::string getDominantBottleneck() const {
        StallCause cause = getDominantCause();
        switch (cause) {
            case StallCause::MEMORY_LATENCY: return "memory_latency";
            case StallCause::RAW_HAZARD: return "data_dependency";
            case StallCause::FU_CONTENTION: return "compute_bound";
            case StallCause::PORT_CONTENTION: return "memory_bandwidth";
            case StallCause::CONTROL_FLOW: return "control_flow";
            case StallCause::DMA_PENDING: return "dma";
            case StallCause::RESOURCE_LIMIT: return "resource_limit";
            default: return "none";
        }
    }

    double getStallPercentage(StallCause cause, uint64_t total_cycles) const {
        return total_cycles > 0 ?
               100.0 * by_cause[static_cast<int>(cause)] / total_cycles : 0.0;
    }

    void recordStall(StallCause cause) {
        by_cause[static_cast<int>(cause)]++;
        total_stall_cycles++;
        current_stall_streak++;
        max_consecutive_stalls = std::max(max_consecutive_stalls, current_stall_streak);
    }

    void recordNoStall() {
        if (current_stall_streak > 0) {
            stall_events++;
        }
        current_stall_streak = 0;
    }

    void reset() {
        for (int i = 0; i < static_cast<int>(StallCause::STALL_CAUSE_COUNT); i++) {
            by_cause[i] = 0;
        }
        memory_read_stalls = memory_write_stalls = cache_miss_stalls = dma_stalls = 0;
        raw_stalls = waw_stalls = war_stalls = 0;
        for (int i = 0; i < static_cast<int>(FUType::FU_TYPE_COUNT); i++) {
            fu_stalls_by_type[i] = 0;
        }
        read_port_stalls = write_port_stalls = 0;
        reservation_full_stalls = compute_queue_full_stalls = 0;
        total_stall_cycles = max_consecutive_stalls = current_stall_streak = 0;
        stall_events = 0;
    }
};

// ============================================================================
// NEW: Power/Area Configuration (externalized coefficients)
// ============================================================================

struct PowerAreaCoefficients {
    // FU power coefficients (per operation)
    struct FUCoeffs {
        double area_um2 = 0.0;
        double leakage_mw = 0.0;
        double dynamic_read_mw = 0.0;
        double dynamic_write_mw = 0.0;
    };

    FUCoeffs fu_coeffs[static_cast<int>(FUType::FU_TYPE_COUNT)];

    // Register power coefficients
    double reg_area_per_bit_um2 = 5.981433;
    double reg_leakage_per_bit_mw = 7.395312e-05;
    double reg_dynamic_read_mw = 1.322600e-03;
    double reg_dynamic_write_mw = 1.792126e-04;

    // Memory power coefficients
    double spm_leakage_per_kb_mw = 0.5;
    double spm_read_dynamic_per_access_mw = 0.1;
    double spm_write_dynamic_per_access_mw = 0.15;
    double spm_area_per_kb_um2 = 10000.0;

    double cache_leakage_per_kb_mw = 0.8;
    double cache_read_dynamic_per_access_mw = 0.2;
    double cache_write_dynamic_per_access_mw = 0.25;
    double cache_area_per_kb_um2 = 15000.0;

    // Technology node info
    std::string technology_node = "45nm";
    double voltage = 1.0;
    double temperature_c = 25.0;

    void setDefaults();
    bool loadFromFile(const std::string& filename);
    bool saveToFile(const std::string& filename) const;
};

// ============================================================================
// Existing Statistics Structs (updated)
// ============================================================================

struct PerformanceStats {
    double setup_time_ns = 0.0;
    double sim_time_ns = 0.0;
    int clock_period_ns = 0;
    double sys_clock_ghz = 0.0;
    int total_cycles = 0;
    int stall_cycles = 0;
    int executed_nodes = 0;

    // Stall breakdown by type (legacy)
    int stall_breakdown[static_cast<int>(StallType::STALL_TYPE_COUNT)] = {0};
    int node_breakdown[static_cast<int>(StallType::STALL_TYPE_COUNT)] = {0};

    void reset() {
        setup_time_ns = sim_time_ns = 0.0;
        clock_period_ns = total_cycles = stall_cycles = executed_nodes = 0;
        sys_clock_ghz = 0.0;
        for (int i = 0; i < static_cast<int>(StallType::STALL_TYPE_COUNT); i++) {
            stall_breakdown[i] = node_breakdown[i] = 0;
        }
    }
};

struct FURuntimeStats {
    int max_concurrent = 0;
    double avg_occupancy = 0.0;
};

struct FunctionalUnitStats {
    FURuntimeStats runtime[static_cast<int>(FUType::FU_TYPE_COUNT)];
    int static_count[static_cast<int>(FUType::FU_TYPE_COUNT)] = {0};

    void reset() {
        for (int i = 0; i < static_cast<int>(FUType::FU_TYPE_COUNT); i++) {
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

    // New: Energy metrics (time-integrated power)
    double total_energy_nj = 0.0;
    double fu_energy_nj = 0.0;
    double mem_energy_nj = 0.0;
    double reg_energy_nj = 0.0;

    void reset() {
        fu_leakage = fu_dynamic = fu_total = 0.0;
        reg_leakage = reg_dynamic = reg_total = 0.0;
        spm_leakage = spm_read_dynamic = spm_write_dynamic = spm_total = 0.0;
        cache_leakage = cache_read_dynamic = cache_write_dynamic = 0.0;
        cache_total = total_power = acc_spm_total = acc_cache_total = 0.0;
        total_energy_nj = fu_energy_nj = mem_energy_nj = reg_energy_nj = 0.0;
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

    // New: Area breakdown by FU type
    double fu_area_by_type[static_cast<int>(FUType::FU_TYPE_COUNT)] = {0};

    double getTotalAreaMm2() const { return total_area_um2 / 1e6; }

    void reset() {
        fu_area_um2 = reg_area_um2 = spm_area_um2 = cache_area_um2 = 0.0;
        total_area_um2 = acc_spm_area_um2 = acc_cache_area_um2 = 0.0;
        for (int i = 0; i < static_cast<int>(FUType::FU_TYPE_COUNT); i++) {
            fu_area_by_type[i] = 0.0;
        }
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

// ============================================================================
// Enhanced Summary Statistics (includes all new stats)
// ============================================================================

struct SummaryStats {
    std::string accelerator_name;
    std::string timestamp;
    std::string version = "3.0";  // Updated version

    // Existing stats
    PerformanceStats performance;
    FunctionalUnitStats functional_units;
    MemoryStats memory;
    RegisterStats registers;
    PowerStats power;
    AreaStats area;
    CycleStatsSummary cycle_summary;

    // NEW: Enhanced statistics
    MemoryAccessStats memory_access;
    DataflowStats dataflow;
    FUUtilizationStats fu_utilization;
    StallBreakdown stall_breakdown;

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
        memory_access.reset();
        dataflow.reset();
        fu_utilization.reset();
        stall_breakdown.reset();
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

    // NEW: Extended per-cycle stats
    StallCause stall_cause = StallCause::NONE;
    int bytes_read_this_cycle = 0;
    int bytes_written_this_cycle = 0;
    int fu_utilization_mask = 0;  // Bitmask of which FU types are busy

    void reset() {
        cycle = resInFlight = loadInFlight = loadInternal = 0;
        loadAcitve = loadRawStall = storeInFlight = storeActive = 0;
        compInFlight = compLaunched = compActive = compFUStall = 0;
        compCommited = 0;
        stall_cause = StallCause::NONE;
        bytes_read_this_cycle = bytes_written_this_cycle = 0;
        fu_utilization_mask = 0;
    }
};

// ============================================================================
// Main HWStatistics Class (Enhanced)
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
    PowerAreaCoefficients power_area_config;

    std::string indent(int level) const;
    void writeJsonField(std::ostringstream& os, const std::string& key,
                        int value, int indent_level, bool last = false);
    void writeJsonField(std::ostringstream& os, const std::string& key,
                        int64_t value, int indent_level, bool last = false);
    void writeJsonField(std::ostringstream& os, const std::string& key,
                        uint64_t value, int indent_level, bool last = false);
    void writeJsonField(std::ostringstream& os, const std::string& key,
                        double value, int indent_level, bool last = false);
    void writeJsonField(std::ostringstream& os, const std::string& key,
                        const std::string& value, int indent_level,
                        bool last = false);
    void writeJsonField(std::ostringstream& os, const std::string& key,
                        bool value, int indent_level, bool last = false);

    // NEW: JSON serialization helpers for new stats
    void writeMemoryAccessStatsJSON(std::ostringstream& os, int indent_level) const;
    void writeDataflowStatsJSON(std::ostringstream& os, int indent_level) const;
    void writeFUUtilizationStatsJSON(std::ostringstream& os, int indent_level) const;
    void writeStallBreakdownJSON(std::ostringstream& os, int indent_level) const;

  public:
    HWStatistics(const HWStatisticsParams &params);

    // Configuration accessors
    bool use_cycle_tracking() const { return cycle_tracking; }
    bool isOutputEnabled() const { return output_statistics; }
    bool isGuiEnabled() const { return gui_stats_enabled; }
    std::string getOutputFile() const { return output_file; }

    // Direct access to stats (for collection from other modules)
    SummaryStats& getSummary() { return summary; }
    MemoryAccessStats& getMemoryAccessStats() { return summary.memory_access; }
    DataflowStats& getDataflowStats() { return summary.dataflow; }
    FUUtilizationStats& getFUUtilizationStats() { return summary.fu_utilization; }
    StallBreakdown& getStallBreakdown() { return summary.stall_breakdown; }
    PowerAreaCoefficients& getPowerAreaConfig() { return power_area_config; }

    // Existing collection methods
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

    // NEW: Enhanced memory access collection
    void recordMemoryRead(uint64_t addr, size_t bytes, uint64_t latency,
                          bool cache_hit, MemAccessType type);
    void recordMemoryWrite(uint64_t addr, size_t bytes, uint64_t latency,
                           bool cache_hit, MemAccessType type);
    void recordPortContention(bool is_read);
    void recordDMATransfer(bool is_read, size_t bytes, uint64_t latency);

    // NEW: Dataflow/dependency collection
    void recordDependency(int producer_uid, int consumer_uid, bool is_raw,
                          bool is_war, bool is_waw);
    void recordCriticalPathNode(int uid, int opcode, bool is_load, bool is_store);
    void recordParallelism(int ready_count, int issued_count);
    void setCriticalPathLength(int length);

    // NEW: FU utilization collection
    void recordFUBusy(FUType type, int instance_id, uint64_t start_cycle,
                      uint64_t end_cycle);
    void recordFUContention(FUType type);
    void setFUInstances(FUType type, int count);

    // NEW: Stall tracking
    void recordStallCause(StallCause cause);
    void recordNoStall();
    void recordFUStall(FUType type);

    // NEW: Power/Area with activity factors
    void calculatePowerWithActivity();
    void calculateAreaFromConfig();
    bool loadPowerAreaConfig(const std::string& filename);
    bool savePowerAreaConfig(const std::string& filename);

    // Cycle tracking methods
    void recordCycleStats(const HW_Cycle_Stats& stats);
    CycleStatsSummary summarizeCycleStats();
    void updateHWStatsCycleStart();
    void updateHWStatsCycleEnd(int curr_cycle);
    void updateBuffer();
    void clearStats();

    // Output methods
    std::string toJSON(bool pretty = true) const;
    void printSummary(std::ostream& os) const;
    void printDetailed(std::ostream& os) const;
    void writeJSONFile();

    // Legacy methods
    void print();
    void simpleStats();
    void unitCorrections();

    // GUI publishing
    void publishCycleToGUI(uint64_t cycle);
    void publishFinalToGUI();

    // NEW: Enhanced GUI publishing for live visualization
    void publishMemoryAccess(uint64_t cycle, uint64_t addr, size_t bytes,
                             bool is_write, const std::string& source);
    void publishFUActivity(uint64_t start_cycle, uint64_t end_cycle,
                           FUType type, int instance, int uid);
    void publishDataflowNode(uint64_t cycle, int uid, const std::string& opcode,
                             int queue_id, const std::vector<int>& deps);
    void publishDataflowEdge(uint64_t cycle, int producer, int consumer,
                             bool on_critical_path);
    void publishStallEvent(uint64_t cycle, StallCause cause, int uid);
    void publishPipelineSnapshot(uint64_t cycle, int res_depth, int comp_depth,
                                 int read_depth, int write_depth);
};

// Helper function declarations
const char* getFUTypeName(FUType type);
const char* getStallTypeName(StallType type);
const char* getStallCauseName(StallCause cause);
const char* getMemAccessTypeName(MemAccessType type);

#endif //__HWMODEL_HW_STATISTICS_HH__
