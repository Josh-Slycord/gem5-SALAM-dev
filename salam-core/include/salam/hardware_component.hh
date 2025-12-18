/*
 * Copyright (c) 2024 gem5-SALAM Contributors
 * All rights reserved.
 *
 * SALAM Abstract Hardware Component Interface
 * Version: 3.0.0.pre[1.0.0]
 *
 * This interface abstracts hardware component lifecycle management,
 * replacing gem5's SimObject inheritance.
 */

#ifndef __SALAM_HARDWARE_COMPONENT_HH__
#define __SALAM_HARDWARE_COMPONENT_HH__

#include <memory>
#include <string>
#include <vector>

#include "salam/simulation_context.hh"

namespace salam {

/**
 * Component state enumeration.
 */
enum class ComponentState {
    Created,      // Object constructed but not initialized
    Initialized,  // init() called
    Started,      // startup() called, simulation running
    Draining,     // drain() called, flushing state
    Drained,      // Fully drained
    Resuming,     // drainResume() called
    Stopped       // Simulation ended
};

/**
 * Abstract hardware component interface.
 *
 * This interface provides the component lifecycle that SALAM hardware
 * components need. It mirrors gem5's SimObject interface but without
 * the gem5 dependencies.
 *
 * Lifecycle: Created -> Initialized -> Started -> [Draining -> Drained] ->
 * Stopped
 */
class HardwareComponent {
  public:
    /**
     * Constructor with component name and simulation context.
     */
    explicit HardwareComponent(const std::string& name,
                               SimulationContextPtr ctx = nullptr)
        : componentName(name),
          context(ctx),
          state(ComponentState::Created) {}

    virtual ~HardwareComponent() = default;

    /**
     * Get the component name.
     */
    const std::string& name() const { return componentName; }

    /**
     * Get current component state.
     */
    ComponentState getState() const { return state; }

    /**
     * Set the simulation context.
     * Must be called before init() if not provided in constructor.
     */
    void setSimulationContext(SimulationContextPtr ctx) { context = ctx; }

    /**
     * Get the simulation context.
     */
    SimulationContextPtr getSimulationContext() const { return context; }

    /**
     * Initialize the component.
     * Called after construction but before simulation starts.
     * Equivalent to gem5's init().
     */
    virtual void init() {
        state = ComponentState::Initialized;
    }

    /**
     * Start the component for simulation.
     * Called when simulation begins.
     * Equivalent to gem5's startup().
     */
    virtual void startup() {
        state = ComponentState::Started;
    }

    /**
     * Drain the component (prepare for checkpointing or stopping).
     * @return true if immediately drained, false if draining asynchronously.
     */
    virtual bool drain() {
        state = ComponentState::Drained;
        return true;
    }

    /**
     * Resume from a drained state.
     */
    virtual void drainResume() {
        state = ComponentState::Started;
    }

    /**
     * Serialize component state to a checkpoint.
     * Override for components with persistent state.
     */
    virtual void serialize(std::ostream& os) const {}

    /**
     * Unserialize component state from a checkpoint.
     */
    virtual void unserialize(std::istream& is) {}

    /**
     * Get statistics from this component.
     * Returns a map of stat_name -> value pairs.
     */
    virtual std::vector<std::pair<std::string, double>> getStats() const {
        return {};
    }

    /**
     * Reset statistics.
     */
    virtual void resetStats() {}

  protected:
    /**
     * Schedule an event at current_tick + delay.
     * Convenience wrapper around context->schedule().
     */
    void scheduleEvent(EventInterface* event, Tick delay) {
        if (context) {
            context->schedule(event, context->currentTick() + delay);
        }
    }

    /**
     * Get current simulation tick.
     */
    Tick currentTick() const {
        return context ? context->currentTick() : 0;
    }

    std::string componentName;
    SimulationContextPtr context;
    ComponentState state;
};

/**
 * Shared pointer type for hardware components.
 */
using HardwareComponentPtr = std::shared_ptr<HardwareComponent>;

/**
 * Interface for clocked components (ClockedObject equivalent).
 *
 * Adds clock-related functionality on top of HardwareComponent.
 */
class ClockedComponent : public HardwareComponent {
  public:
    ClockedComponent(const std::string& name,
                     Tick clockPeriod,
                     SimulationContextPtr ctx = nullptr)
        : HardwareComponent(name, ctx),
          period(clockPeriod) {}

    /**
     * Get the clock period in ticks.
     */
    Tick clockPeriod() const { return period; }

    /**
     * Get the clock frequency in Hz.
     */
    double clockFrequency() const {
        if (context) {
            return static_cast<double>(context->tickFrequency()) / period;
        }
        return 1e12 / period; // Assume 1 THz tick frequency
    }

    /**
     * Get the next clock edge tick.
     */
    Tick nextCycle() const {
        return nextCycle(currentTick());
    }

    /**
     * Get the next clock edge after the given tick.
     */
    Tick nextCycle(Tick after) const {
        Tick current = after;
        Tick cycles = current / period;
        return (cycles + 1) * period;
    }

    /**
     * Convert cycles to ticks.
     */
    Tick cyclesToTicks(uint64_t cycles) const {
        return cycles * period;
    }

    /**
     * Convert ticks to cycles.
     */
    uint64_t ticksToCycles(Tick ticks) const {
        return ticks / period;
    }

  protected:
    Tick period;
};

} // namespace salam

#endif // __SALAM_HARDWARE_COMPONENT_HH__
