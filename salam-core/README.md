# SALAM Core Library

**Version**: 3.0.0.pre[1.0.0]

The SALAM Core library provides simulator-agnostic interfaces for hardware accelerator simulation. This allows SALAM to run on different simulation backends (gem5, standalone, SystemC, etc.).

## Architecture

```
salam-core/
├── include/salam/           # Public headers
│   ├── salam.hh             # Main header (includes all)
│   ├── simulation_context.hh # Event scheduling interface
│   ├── hardware_component.hh # Component lifecycle interface
│   └── memory_interface.hh   # Memory access interface
└── adapters/
    └── gem5/                # gem5 backend implementation
        ├── gem5_simulation_context.hh
        └── gem5_memory_port.hh
```

## Interfaces

### SimulationContext

Abstracts the simulation timing and event scheduling system:

```cpp
class SimulationContext {
    virtual Tick currentTick() const = 0;
    virtual void schedule(EventInterface* event, Tick when) = 0;
    virtual void deschedule(EventInterface* event) = 0;
    virtual void reschedule(EventInterface* event, Tick when) = 0;
    virtual EventInterface* createEvent(EventCallback callback,
                                         const std::string& name = "") = 0;
};
```

### HardwareComponent

Abstracts component lifecycle (replaces gem5's SimObject):

```cpp
class HardwareComponent {
    virtual void init();
    virtual void startup();
    virtual bool drain();
    virtual void drainResume();
    virtual void serialize(std::ostream& os) const;
    virtual void unserialize(std::istream& is);
};
```

### MemoryPort

Abstracts memory access (replaces gem5's ports):

```cpp
class MemoryPort {
    virtual bool sendTimingRequest(MemoryRequest& req) = 0;
    virtual void sendFunctional(MemoryRequest& req) = 0;
    virtual bool isReady() const = 0;
    virtual bool isStalled() const = 0;
    virtual void setCompletionCallback(MemoryCallback callback) = 0;
};
```

## Usage with gem5

```cpp
#include "salam/salam.hh"
#include "adapters/gem5/gem5_simulation_context.hh"
#include "adapters/gem5/gem5_memory_port.hh"

// Create gem5 simulation context
auto ctx = salam::createGem5SimulationContext(eventManager);

// Create component with context
MyAccelerator acc("my_acc", ctx);
acc.init();
acc.startup();
```

## Usage Standalone (future)

```cpp
#include "salam/salam.hh"
// Future: #include "adapters/standalone/standalone_context.hh"

// Create standalone simulation context
auto ctx = salam::createStandaloneContext();

// Create component with context
MyAccelerator acc("my_acc", ctx);
acc.init();
acc.startup();

// Run simulation
while (ctx->hasMoreEvents()) {
    ctx->processNextEvent();
}
```

## Building

The salam-core headers are header-only and require no separate compilation.

For gem5 integration, include the adapters in your SConscript:

```python
# In src/hwacc/SConscript
Source('salam-core/adapters/gem5/gem5_simulation_context.cc')  # if needed
```

## Version

This library follows the unified versioning standard:
- Format: `[MAJOR][REWORK].[REVISION].[PATCH].[STAGE]`
- Current: `3.0.0.pre[1.0.0]`
  - `3.0.0.pre` = gem5-SALAM parent version
  - `[1.0.0]` = salam-core module version
