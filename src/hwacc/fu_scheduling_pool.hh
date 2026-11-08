#ifndef __HWACC_FU_SCHEDULING_POOL_HH__
#define __HWACC_FU_SCHEDULING_POOL_HH__

/**
 * @file fu_scheduling_pool.hh
 * @brief Dynamic functional unit capacity accounting and lease management.
 *
 * SALAM_FU_SCHEDULER_V1: nonpipelined capacity accounting for dynamic
 * scalar instructions. This header has no gem5 dependencies so the same
 * admission logic can be tested without a simulator build.
 */
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

/**
 * @class FUSchedulingPool
 * @brief Manages runtime resource admission, capacity constraints, and lease
 * tracking for FUs.
 *
 * Implements non-pipelined issue-to-completion functional unit scheduling for
 * SALAM.
 * Instructions request FU leases prior to computation; if the unit's limit is
 * nonzero
 * and current occupancy equals the limit, admission is denied, stalling the
 * instruction.
 * A limit of zero denotes unlimited capacity.
 */
class FUSchedulingPool
{
  public:
    // SALAM_FU_TRACE_BUDGET_V1: the bounded trace budget affects logging only.
    /** @brief Default in-memory trace event capacity. */
    static constexpr uint32_t DefaultTraceEventLimit = 262144;
    /** @brief Hard upper bound on trace event capacity. */
    static constexpr uint32_t MaxTraceEventLimit = 4194304;

    /**
     * @struct Unit
     * @brief Runtime state and usage statistics for an individual functional
     * unit.
     */
    struct Unit {
        uint32_t id;
        std::string name;
        uint64_t limit;
        uint64_t attempts = 0;
        uint64_t grants = 0;
        uint64_t denials = 0;
        uint64_t releases = 0;
        uint64_t peak = 0;
        uint64_t outstanding = 0;
    };

    /**
     * @struct Event
     * @brief Individual trace observation recording a grant, deny, or release
     * event.
     */
    struct Event {
        std::string event;
        uint64_t cycle;
        uint64_t tick;
        uint64_t uid;
        uint64_t opcode;
        uint32_t fu_id;
        uint64_t lease_id;
    };
  private:
    struct Lease {
        uint64_t lease_id;
        uint64_t uid;
        uint64_t opcode;
        uint32_t fu_id;
    };
    std::map<uint32_t, Unit> units_;
    std::map<const void *, Lease> leases_;
    std::vector<Event> trace_;
    bool trace_truncated_ = false;
    uint64_t next_lease_id_ = 0;
    uint64_t attempts_ = 0;
    uint64_t grants_ = 0;
    uint64_t denials_ = 0;
    uint64_t releases_ = 0;
    uint64_t peak_ = 0;
    uint32_t trace_event_limit_;

    void record(const char *event, uint64_t cycle, uint64_t tick,
                uint64_t uid, uint64_t opcode, uint32_t fu_id,
                uint64_t lease_id)
    {
        if (trace_.size() < trace_event_limit_)
            trace_.push_back({event, cycle, tick, uid, opcode, fu_id, lease_id});
        else
            trace_truncated_ = true;
    }

    static std::string jsonString(const std::string &value)
    {
        std::ostringstream out;
        out << '"';
        const char *hex = "0123456789abcdef";
        for (const unsigned char c : value) {
            switch (c) {
              case '"': out << "\\\""; break;
              case '\\': out << "\\\\"; break;
              case '\n': out << "\\n"; break;
              case '\r': out << "\\r"; break;
              case '\t': out << "\\t"; break;
              default:
                if (c < 0x20) {
                    out << "\\u00" << hex[c >> 4] << hex[c & 15];
                } else {
                    out << c;
                }
            }
        }
        out << '"';
        return out.str();
    }

  public:
    /**
     * @brief Construct a new FUSchedulingPool object.
     * @param trace_event_limit Maximum number of trace events to buffer.
     * @throws std::invalid_argument If trace limit is outside [1, 4194304].
     */
    explicit FUSchedulingPool(uint32_t trace_event_limit = DefaultTraceEventLimit)
        : trace_event_limit_(trace_event_limit)
    {
        if (!trace_event_limit || trace_event_limit > MaxTraceEventLimit)
            throw std::invalid_argument("FU trace event limit must be from 1 to 4194304");
    }

    /**
     * @brief Register a functional unit with capacity constraints.
     * @param id Unique nonzero unit identifier.
     * @param name Descriptive functional unit name.
     * @param limit Maximum concurrent capacity (0 = unlimited).
     * @throws std::logic_error If id is 0 or already registered.
     */
    void configure(uint32_t id, const std::string &name, uint64_t limit)
    {
        if (!id || !units_.emplace(id, Unit{id, name, limit}).second)
            throw std::logic_error("FU id must be nonzero and unique");
    }

    /**
     * @brief Check whether an FU ID is registered in the pool.
     * @param id Functional unit ID.
     * @return True if registered.
     */
    bool hasUnit(uint32_t id) const { return units_.count(id) != 0; }

    /**
     * @brief Check whether an instruction pointer holds an active lease.
     * @param instruction Pointer to instruction instance.
     * @return True if lease is active.
     */
    bool hasLease(const void *instruction) const { return leases_.count(instruction) != 0; }

    /**
     * @brief Query status for a registered functional unit.
     * @param id Functional unit ID.
     * @return Const reference to Unit state descriptor.
     */
    const Unit &unit(uint32_t id) const { return units_.at(id); }

    /**
     * @brief Access map of all registered functional units.
     * @return Const reference to map of units.
     */
    const std::map<uint32_t, Unit> &units() const { return units_; }

    /**
     * @brief Get count of currently outstanding active leases.
     * @return Number of active leases.
     */
    uint64_t outstanding() const { return leases_.size(); }

    /**
     * @brief Check whether the trace buffer exceeded capacity and was
     * truncated.
     * @return True if trace was truncated.
     */
    bool traceTruncated() const { return trace_truncated_; }

    /**
     * @brief Get configured trace event capacity.
     * @return Event limit.
     */
    uint32_t traceEventLimit() const { return trace_event_limit_; }

    /**
     * @brief Access buffered execution trace events.
     * @return Const reference to event vector.
     */
    const std::vector<Event> &trace() const { return trace_; }

    /**
     * @brief Request a lease on a functional unit for an instruction.
     * @param instruction Pointer to requesting instruction.
     * @param uid Instruction unique ID.
     * @param opcode LLVM opcode.
     * @param fu_id Target functional unit ID.
     * @param cycle Current simulation cycle.
     * @param tick Current simulation tick.
     * @return True if lease is granted; false if denied due to capacity.
     * @throws std::logic_error If instruction is null or already holds a
     * lease.
     */
    bool acquire(const void *instruction, uint64_t uid, uint64_t opcode,
                 uint32_t fu_id, uint64_t cycle, uint64_t tick)
    {
        if (!instruction || leases_.count(instruction))
            throw std::logic_error("FU lease requires a unique live instruction");
        Unit &unit = units_.at(fu_id);
        ++unit.attempts;
        ++attempts_;
        if (unit.limit && unit.outstanding >= unit.limit) {
            ++unit.denials;
            ++denials_;
            record("deny", cycle, tick, uid, opcode, fu_id, 0);
            return false;
        }
        const uint64_t lease_id = ++next_lease_id_;
        leases_.emplace(instruction, Lease{lease_id, uid, opcode, fu_id});
        ++unit.grants;
        ++unit.outstanding;
        unit.peak = std::max(unit.peak, unit.outstanding);
        ++grants_;
        peak_ = std::max<uint64_t>(peak_, leases_.size());
        record("grant", cycle, tick, uid, opcode, fu_id, lease_id);
        return true;
    }

    /**
     * @brief Release a previously granted functional unit lease.
     * @param instruction Pointer to instruction holding lease.
     * @param cycle Current simulation cycle.
     * @param tick Current simulation tick.
     * @return Functional unit ID that was released.
     * @throws std::logic_error If instruction has no active lease or underflow
     * occurs.
     */
    uint32_t release(const void *instruction, uint64_t cycle, uint64_t tick)
    {
        auto it = leases_.find(instruction);
        if (it == leases_.end())
            throw std::logic_error("FU lease released without a matching grant");
        const Lease lease = it->second;
        Unit &unit = units_.at(lease.fu_id);
        if (!unit.outstanding)
            throw std::logic_error("FU occupancy underflow");
        --unit.outstanding;
        ++unit.releases;
        ++releases_;
        leases_.erase(it);
        record("release", cycle, tick, lease.uid, lease.opcode,
               lease.fu_id, lease.lease_id);
        return lease.fu_id;
    }

    /**
     * @brief Serialize pool state and trace log to JSON format.
     * @param name Benchmark or accelerator name.
     * @param elapsed_cycles Total execution cycles.
     * @param elapsed_ticks Total execution ticks.
     * @return Formatted JSON string.
     */
    std::string toJSON(const std::string &name, uint64_t elapsed_cycles,
                       uint64_t elapsed_ticks) const
    {
        std::ostringstream out;
        out << "{\"kind\":\"salam_fu_scheduling\",\"schema_version\":1,"
            << "\"invocation\":{\"name\":" << jsonString(name)
            << ",\"elapsed_cycles\":" << elapsed_cycles
            << ",\"elapsed_ticks\":" << elapsed_ticks << "},"
            << "\"units\":[";
        bool first = true;
        for (const auto &entry : units_) {
            const Unit &u = entry.second;
            if (!first) out << ',';
            first = false;
            out << "{\"id\":" << u.id << ",\"name\":" << jsonString(u.name)
                << ",\"limit\":" << u.limit << ",\"attempts\":" << u.attempts
                << ",\"grants\":" << u.grants << ",\"denials\":" << u.denials
                << ",\"releases\":" << u.releases << ",\"peak\":" << u.peak
                << ",\"outstanding\":" << u.outstanding << '}';
        }
        out << "],\"totals\":{\"attempts\":" << attempts_
            << ",\"grants\":" << grants_ << ",\"denials\":" << denials_
            << ",\"releases\":" << releases_ << ",\"peak\":" << peak_
            << ",\"outstanding\":" << leases_.size() << "},\"trace\":[";
        first = true;
        for (const Event &e : trace_) {
            if (!first) out << ',';
            first = false;
            out << "{\"event\":" << jsonString(e.event)
                << ",\"cycle\":" << e.cycle << ",\"tick\":" << e.tick
                << ",\"uid\":" << e.uid << ",\"opcode\":" << e.opcode
                << ",\"fu_id\":" << e.fu_id
                << ",\"lease_id\":" << e.lease_id << '}';
        }
        out << "],\"trace_event_limit\":" << trace_event_limit_
            << ",\"trace_truncated\":"
            << (trace_truncated_ ? "true" : "false") << '}';
        return out.str();
    }
};

#endif // __HWACC_FU_SCHEDULING_POOL_HH__
