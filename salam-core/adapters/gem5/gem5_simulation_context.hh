/*
 * Copyright (c) 2024 gem5-SALAM Contributors
 * All rights reserved.
 *
 * gem5 Simulation Context Adapter
 * Version: 3.0.0.pre[1.0.0]
 *
 * Implements SALAM's SimulationContext interface using gem5's
 * event system and timing APIs.
 */

#ifndef __SALAM_GEM5_SIMULATION_CONTEXT_HH__
#define __SALAM_GEM5_SIMULATION_CONTEXT_HH__

// gem5 includes
#include "sim/eventq.hh"
#include "sim/sim_object.hh"

// SALAM includes
#include "salam/simulation_context.hh"

#include <map>
#include <memory>

namespace salam {

/**
 * gem5 event wrapper implementing SALAM's EventInterface.
 */
class Gem5Event : public EventInterface, public gem5::Event {
  public:
    Gem5Event(EventCallback cb, const std::string& eventName)
        : gem5::Event(), callback(cb), eventName(eventName) {}

    // EventInterface implementation
    Tick when() const override {
        return gem5::Event::when();
    }

    bool scheduled() const override {
        return gem5::Event::scheduled();
    }

    std::string name() const override {
        return eventName;
    }

    // gem5 Event implementation
    void process() override {
        if (callback) {
            callback();
        }
    }

    const char* description() const override {
        return eventName.c_str();
    }

  private:
    EventCallback callback;
    std::string eventName;
};

/**
 * gem5 SimulationContext implementation.
 *
 * This adapter wraps gem5's global curTick() and event queue APIs
 * to implement SALAM's abstract SimulationContext interface.
 */
class Gem5SimulationContext : public SimulationContext {
  public:
    Gem5SimulationContext(gem5::EventManager* em = nullptr)
        : eventManager(em) {}

    ~Gem5SimulationContext() override {
        // Clean up owned events
        for (auto& pair : ownedEvents) {
            delete pair.second;
        }
    }

    /**
     * Set the event manager (for scheduling events).
     * If not set, uses the main event queue.
     */
    void setEventManager(gem5::EventManager* em) {
        eventManager = em;
    }

    // SimulationContext implementation

    Tick currentTick() const override {
        return gem5::curTick();
    }

    void schedule(EventInterface* event, Tick when) override {
        auto* gem5Event = dynamic_cast<Gem5Event*>(event);
        if (gem5Event) {
            if (eventManager) {
                eventManager->schedule(gem5Event, when);
            } else {
                gem5::mainEventQueue[0]->schedule(gem5Event, when);
            }
        }
    }

    void deschedule(EventInterface* event) override {
        auto* gem5Event = dynamic_cast<Gem5Event*>(event);
        if (gem5Event && gem5Event->scheduled()) {
            if (eventManager) {
                eventManager->deschedule(gem5Event);
            } else {
                gem5::mainEventQueue[0]->deschedule(gem5Event);
            }
        }
    }

    void reschedule(EventInterface* event, Tick when) override {
        auto* gem5Event = dynamic_cast<Gem5Event*>(event);
        if (gem5Event) {
            if (gem5Event->scheduled()) {
                if (eventManager) {
                    eventManager->reschedule(gem5Event, when);
                } else {
                    gem5::mainEventQueue[0]->reschedule(gem5Event, when);
                }
            } else {
                schedule(event, when);
            }
        }
    }

    EventInterface* createEvent(EventCallback callback,
                                const std::string& name = "") override {
        static uint64_t eventId = 0;
        std::string eventName = name.empty() ?
            "salam_event_" + std::to_string(eventId) : name;

        auto* event = new Gem5Event(callback, eventName);
        ownedEvents[eventId++] = event;
        return event;
    }

    uint64_t tickFrequency() const override {
        return gem5::SimClock::Frequency;
    }

  private:
    gem5::EventManager* eventManager;
    std::map<uint64_t, Gem5Event*> ownedEvents;
};

/**
 * Factory function to create gem5 simulation context.
 */
inline SimulationContextPtr createGem5SimulationContext(
    gem5::EventManager* em = nullptr) {
    return std::make_shared<Gem5SimulationContext>(em);
}

} // namespace salam

#endif // __SALAM_GEM5_SIMULATION_CONTEXT_HH__
