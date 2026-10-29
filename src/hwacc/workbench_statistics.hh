#ifndef __HWACC_WORKBENCH_STATISTICS_HH__
#define __HWACC_WORKBENCH_STATISTICS_HH__

// A deliberately small observation-only collector. This header has no gem5,
// LLVM, GUI, power-model, or recovered statistics-schema dependency.
#include <algorithm>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <map>
#include <sstream>
#include <string>

namespace gem5 {
namespace salam {

class WorkbenchStatistics
{
  public:
    enum class Commit { QueuedCompute, MemoryRead, MemoryWrite };

    struct MemoryTotals {
        uint64_t started = 0;
        uint64_t completed = 0;
        uint64_t startedBytes = 0;
        uint64_t completedBytes = 0;
        uint64_t latencySum = 0;
        uint64_t latencyMin = 0;
        uint64_t latencyMax = 0;
    };

    struct DepthTotals {
        uint64_t sum = 0;
        uint64_t max = 0;
    };

  private:
    struct PendingRequest {
        bool write;
        uint64_t bytes;
        uint64_t tick;
    };
    std::string accelerator;
    uint64_t invocation = 0;
    bool active = false;
    bool completed = false;
    uint64_t startTick = 0;
    uint64_t endTick = 0;
    uint64_t clockPeriod = 0;
    uint64_t tickFrequency = 0;
    uint64_t invalidEvents = 0;
    std::map<uintptr_t, PendingRequest> pending;
    MemoryTotals reads, writes;
    uint64_t computeCommits = 0, readCommits = 0, writeCommits = 0;
    uint64_t selectedCommits = 0;
    uint64_t samples = 0;
    DepthTotals reservationDepth, readDepth, writeDepth, computeDepth;
    DepthTotals activeFunctionCount;

    void invalid()
    {
        if (invalidEvents != std::numeric_limits<uint64_t>::max())
            ++invalidEvents;
    }

    void add(uint64_t &value, uint64_t amount)
    {
        if (amount > std::numeric_limits<uint64_t>::max() - value) {
            invalid();
            value = std::numeric_limits<uint64_t>::max();
        } else {
            value += amount;
        }
    }

    void sampleDepth(DepthTotals &depth, uint64_t value)
    {
        add(depth.sum, value);
        depth.max = std::max(depth.max, value);
    }

    static void writeMemory(std::ostream &os, const MemoryTotals &value)
    {
        os << "{\"started\":" << value.started
           << ",\"completed\":" << value.completed
           << ",\"started_bytes\":" << value.startedBytes
           << ",\"completed_bytes\":" << value.completedBytes
           << ",\"outstanding\":" << (value.started - value.completed)
           << ",\"latency_ticks\":{\"count\":" << value.completed
           << ",\"sum\":" << value.latencySum << ",\"min\":";
        if (value.completed) os << value.latencyMin;
        else os << "null";
        os << ",\"max\":";
        if (value.completed) os << value.latencyMax;
        else os << "null";
        os << "}}";
    }

    static void serializeDepth(std::ostream &os, const DepthTotals &value)
    {
        os << "{\"sum\":" << value.sum << ",\"max\":" << value.max << "}";
    }

  public:
    bool begin(const std::string &name, uint64_t tick, uint64_t period,
               uint64_t frequency)
    {
        if (active || invocation == std::numeric_limits<uint64_t>::max()) {
            invalid();
            return false;
        }
        const uint64_t nextInvocation = invocation + 1;
        *this = WorkbenchStatistics();
        invocation = nextInvocation;
        accelerator = name;
        startTick = tick;
        clockPeriod = period;
        tickFrequency = frequency;
        active = true;
        if (name.empty() || period == 0 || frequency == 0)
            invalid();
        return true;
    }

    // Called exactly once at CommInterface enqueue, before register bypass.
    // A logical request may later split into packets or retry; neither creates
    // another collector event. IDs are opaque, invocation-local identities.
    void memoryStarted(uintptr_t id, bool write, uint64_t bytes, uint64_t tick)
    {
        if (!active) return;
        if (tick < startTick || pending.count(id)) {
            invalid();
            return;
        }
        pending.emplace(id, PendingRequest{write, bytes, tick});
        auto &totals = write ? writes : reads;
        add(totals.started, 1);
        add(totals.startedBytes, bytes);
    }

    // Called only at the existing final logical-completion callback boundary,
    // immediately before cu->readCommit/writeCommit, never per packet response.
    void memoryCompleted(uintptr_t id, uint64_t tick)
    {
        if (!active) return;
        const auto found = pending.find(id);
        if (found == pending.end() || tick < found->second.tick) {
            invalid();
            return;
        }
        const PendingRequest request = found->second;
        auto &totals = request.write ? writes : reads;
        const uint64_t latency = tick - request.tick;
        if (totals.completed == 0) totals.latencyMin = latency;
        else totals.latencyMin = std::min(totals.latencyMin, latency);
        totals.latencyMax = std::max(totals.latencyMax, latency);
        add(totals.completed, 1);
        add(totals.completedBytes, request.bytes);
        add(totals.latencySum, latency);
        pending.erase(found);
    }

    // Only successful existing commit() calls at the three documented sites.
    // This is not a count of every instruction retired by the accelerator.
    void recordCommit(Commit kind)
    {
        if (!active) return;
        switch (kind) {
          case Commit::QueuedCompute: add(computeCommits, 1); break;
          case Commit::MemoryRead: add(readCommits, 1); break;
          case Commit::MemoryWrite: add(writeCommits, 1); break;
        }
        add(selectedCommits, 1);
    }

    // One sample at each LLVMInterface::tick entry, before any function runs.
    // Arguments are sums across the functions active at that instant.
    void sampleQueues(uint64_t reservation, uint64_t read, uint64_t write,
                      uint64_t compute, uint64_t functions)
    {
        if (!active) return;
        add(samples, 1);
        sampleDepth(reservationDepth, reservation);
        sampleDepth(readDepth, read);
        sampleDepth(writeDepth, write);
        sampleDepth(computeDepth, compute);
        sampleDepth(activeFunctionCount, functions);
    }

    void end(uint64_t tick)
    {
        if (!active || tick < startTick) {
            invalid();
            return;
        }
        endTick = tick;
        completed = true;
        active = false;
    }

    bool valid() const
    {
        return completed && invalidEvents == 0 && pending.empty();
    }
    uint64_t invocationId() const { return invocation; }
    const MemoryTotals &readTotals() const { return reads; }
    const MemoryTotals &writeTotals() const { return writes; }
    uint64_t sampleCount() const { return samples; }
    const DepthTotals &reservationTotals() const { return reservationDepth; }
    uint64_t invalidEventCount() const { return invalidEvents; }

    static std::string jsonString(const std::string &text)
    {
        std::ostringstream os;
        os << '"';
        const char *hex = "0123456789abcdef";
        for (const unsigned char c : text) {
            switch (c) {
              case '"': os << "\\\""; break;
              case '\\': os << "\\\\"; break;
              case '\n': os << "\\n"; break;
              case '\r': os << "\\r"; break;
              case '\t': os << "\\t"; break;
              default:
                if (c < 0x20)
                    os << "\\u00" << hex[c >> 4] << hex[c & 15];
                else
                    os << c;
            }
        }
        os << '"';
        return os.str();
    }

    static std::string fileComponent(const std::string &name)
    {
        const auto safe = [](unsigned char c) {
            return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                   (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.';
        };
        if (!name.empty() && name != "." && name != ".." &&
            std::all_of(name.begin(), name.end(), safe)) return name;
        // '~' is outside the unencoded alphabet, so this encoding is injective.
        std::ostringstream os;
        os << '~' << std::hex << std::setfill('0');
        for (const unsigned char c : name) os << std::setw(2) << unsigned(c);
        return os.str();
    }

    std::string outputFilename() const
    {
        return fileComponent(accelerator) + ".invocation-" +
               std::to_string(invocation) + ".json";
    }

    std::string toJSON() const
    {
        std::ostringstream os;
        os << "{\n\"kind\":\"salam_observability\",\"schema_version\":1,"
           << "\"producer\":\"workbench-m3\",\"accelerator\":"
           << jsonString(accelerator) << ",\"invocation\":" << invocation
           << ",\"valid\":" << (valid() ? "true" : "false")
           << ",\n\"lifecycle\":{\"start_tick\":" << startTick
           << ",\"end_tick\":";
        if (completed) os << endTick;
        else os << "null";
        os << ",\"elapsed_ticks\":";
        if (completed) os << endTick - startTick;
        else os << "null";
        os << ",\"clock_period_ticks\":" << clockPeriod
           << ",\"tick_frequency_hz\":" << tickFrequency
           << ",\"interface_tick_calls\":" << samples
           << ",\"completed\":" << (completed ? "true" : "false") << "},"
           << "\n\"memory\":{\"availability\":\"observed\",\"scope\":"
           << jsonString("Logical requests from this accelerator's CommInterface enqueue to its final readCommit/writeCommit callback; includes register bypass, queue waiting, packet splitting and retries; excludes CPU, internal-load bypass and independent DMA-engine traffic")
           << ",\"reads\":";
        writeMemory(os, reads);
        os << ",\"writes\":";
        writeMemory(os, writes);
        os << "},\n\"execution\":{\"availability\":\"observed_selected_commits\",\"scope\":"
           << jsonString("Successful existing commit calls when removing computeQueue entries and at external load/store callbacks only; does not cover every immediate, control-flow, phi or internal-load completion; not total retired instructions")
           << ",\"queued_compute_commits\":" << computeCommits
           << ",\"memory_read_commits\":" << readCommits
           << ",\"memory_write_commits\":" << writeCommits
           << ",\"selected_commits_total\":" << selectedCommits << "},"
           << "\n\"queues\":{\"availability\":\"observed\","
           << "\"sample_unit\":\"accelerator_interface_tick_entry\",\"scope\":"
           << jsonString("Sum of queue lengths across active functions at each LLVMInterface::tick entry before processQueues; includes initial and final tick entries; sums are entry-samples, maxima are entries, active_functions counts functions")
           << ",\"aggregation\":\"complete_streaming_sums_and_maxima\","
           << "\"sample_count\":" << samples
           << ",\"aggregated_sample_count\":" << samples
           << ",\"dropped_sample_count\":0,\"raw_samples_available\":false,"
           << "\"reservation\":";
        serializeDepth(os, reservationDepth);
        os << ",\"read\":"; serializeDepth(os, readDepth);
        os << ",\"write\":"; serializeDepth(os, writeDepth);
        os << ",\"compute\":"; serializeDepth(os, computeDepth);
        os << ",\"active_functions\":"; serializeDepth(os, activeFunctionCount);
        os << "},\n\"diagnostics\":{\"invalid_events\":" << invalidEvents
           << ",\"pending_requests\":" << pending.size() << "},"
           << "\n\"unsupported\":{"
           << "\"cache_hits\":{\"availability\":\"unavailable\",\"reason\":\"not instrumented\"},"
           << "\"fu_utilization\":{\"availability\":\"unavailable\",\"reason\":\"not instrumented\"},"
           << "\"power\":{\"availability\":\"unavailable\",\"reason\":\"no characterized model\"},"
           << "\"area\":{\"availability\":\"unavailable\",\"reason\":\"no characterized model\"},"
           << "\"dma\":{\"availability\":\"unavailable\",\"reason\":\"separate engine not instrumented\"},"
           << "\"total_retired_instructions\":{\"availability\":\"unavailable\",\"reason\":\"only selected commit paths counted\"}}\n}\n";
        return os.str();
    }
};

} // namespace salam
} // namespace gem5

#endif
