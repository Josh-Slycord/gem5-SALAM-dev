/*
 * Copyright (c) 2024 gem5-SALAM Contributors
 * All rights reserved.
 *
 * SALAM Abstract Simulation Context Interface
 * Version: 3.0.0.pre[1.0.0]
 *
 * This interface abstracts the simulation timing and event scheduling
 * system, allowing SALAM to run on different simulation backends
 * (gem5, standalone, SystemC, etc.).
 */

#ifndef __SALAM_SIMULATION_CONTEXT_HH__
#define __SALAM_SIMULATION_CONTEXT_HH__

#include <cstdint>
#include <functional>
#include <memory>
#include <string>

namespace salam {

/**
 * Tick type for simulation time.
 * Compatible with gem5's Tick type (uint64_t).
 */
using Tick = uint64_t;

/**
 * Maximum tick value (equivalent to gem5's MaxTick).
 */
constexpr Tick MaxTick = UINT64_MAX;

/**
 * Abstract interface for simulation events.
 * Implementations can wrap gem5 Events or standalone event queue entries.
 */
class EventInterface {
  public:
    virtual ~EventInterface() = default;

    /**
     * Get the scheduled tick for this event.
     * @return Tick when event is scheduled, MaxTick if not scheduled.
     */
    virtual Tick when() const = 0;

    /**
     * Check if event is currently scheduled.
     */
    virtual bool scheduled() const = 0;

    /**
     * Get event description for debugging.
     */
    virtual std::string name() const = 0;
};

/**
 * Callback type for event handlers.
 */
using EventCallback = std::function<void()>;

/**
 * Abstract simulation context interface.
 *
 * This interface provides the core simulation timing and event scheduling
 * functionality that SALAM hardware components need. Different backends
 * implement this interface:
 *
 * - Gem5SimulationContext: Wraps gem5's curTick(), schedule(), etc.
 * - StandaloneSimulationContext: Simple priority queue based scheduler.
 * - SystemCSimulationContext: Maps to SystemC sc_time and processes.
 */
class SimulationContext {
  public:
    virtual ~SimulationContext() = default;

    /**
     * Get the current simulation tick.
     * Equivalent to gem5's curTick().
     */
    virtual Tick currentTick() const = 0;

    /**
     * Schedule an event at an absolute tick.
     * @param event The event to schedule.
     * @param when Absolute tick to schedule at.
     */
    virtual void schedule(EventInterface* event, Tick when) = 0;

    /**
     * Deschedule a previously scheduled event.
     * @param event The event to deschedule.
     */
    virtual void deschedule(EventInterface* event) = 0;

    /**
     * Reschedule an event to a new tick.
     * @param event The event to reschedule.
     * @param when New absolute tick.
     */
    virtual void reschedule(EventInterface* event, Tick when) = 0;

    /**
     * Create a new event with the given callback.
     * The returned event is owned by the context and will be destroyed
     * when the context is destroyed.
     *
     * @param callback Function to call when event fires.
     * @param name Optional name for debugging.
     * @return Pointer to the created event.
     */
    virtual EventInterface* createEvent(EventCallback callback,
                                         const std::string& name = "") = 0;

    /**
     * Get the tick frequency (ticks per second).
     * Default is 1e12 (1 THz, i.e., 1 tick = 1 ps) matching gem5.
     */
    virtual uint64_t tickFrequency() const { return 1000000000000ULL; }

    /**
     * Convert nanoseconds to ticks.
     */
    Tick nsToTicks(double ns) const {
        return static_cast<Tick>(ns * tickFrequency() / 1e9);
    }

    /**
     * Convert ticks to nanoseconds.
     */
    double ticksToNs(Tick ticks) const {
        return static_cast<double>(ticks) * 1e9 / tickFrequency();
    }
};

/**
 * Shared pointer type for simulation contexts.
 */
using SimulationContextPtr = std::shared_ptr<SimulationContext>;

} // namespace salam

#endif // __SALAM_SIMULATION_CONTEXT_HH__
