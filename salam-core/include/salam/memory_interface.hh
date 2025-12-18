/*
 * Copyright (c) 2024 gem5-SALAM Contributors
 * All rights reserved.
 *
 * SALAM Abstract Memory Interface
 * Version: 3.0.0.pre[1.0.0]
 *
 * This interface abstracts memory operations, replacing gem5's port
 * system for memory accesses.
 */

#ifndef __SALAM_MEMORY_INTERFACE_HH__
#define __SALAM_MEMORY_INTERFACE_HH__

#include <cstdint>
#include <functional>
#include <memory>
#include <vector>

#include "salam/simulation_context.hh"

namespace salam {

/**
 * Memory request types.
 */
enum class MemoryRequestType {
    Read,
    Write,
    ReadExclusive,
    WriteInvalidate,
    Invalidate,
    Prefetch,
    Flush
};

/**
 * Memory request structure.
 *
 * Encapsulates all information needed for a memory request,
 * similar to gem5's Packet but simplified.
 */
struct MemoryRequest {
    /// Unique request ID
    uint64_t id;

    /// Request type
    MemoryRequestType type;

    /// Physical address
    uint64_t addr;

    /// Size in bytes
    size_t size;

    /// Data buffer (for writes: data to write, for reads: filled on
    /// completion)
    std::vector<uint8_t> data;

    /// Request creation tick
    Tick requestTick;

    /// Response arrival tick (set on completion)
    Tick responseTick;

    /// User-defined context pointer (for tracking)
    void* context;

    /// Whether this request has completed
    bool completed;

    /// Whether the request succeeded
    bool success;

    MemoryRequest()
        : id(0), type(MemoryRequestType::Read), addr(0), size(0),
          requestTick(0), responseTick(0), context(nullptr),
          completed(false), success(false) {}

    MemoryRequest(uint64_t reqId, MemoryRequestType reqType,
                  uint64_t address, size_t reqSize)
        : id(reqId), type(reqType), addr(address), size(reqSize),
          requestTick(0), responseTick(0), context(nullptr),
          completed(false), success(false) {
        if (type == MemoryRequestType::Write) {
            data.resize(size);
        }
    }

    /// Check if this is a read request
    bool isRead() const {
        return type == MemoryRequestType::Read ||
               type == MemoryRequestType::ReadExclusive;
    }

    /// Check if this is a write request
    bool isWrite() const {
        return type == MemoryRequestType::Write ||
               type == MemoryRequestType::WriteInvalidate;
    }
};

/**
 * Callback type for memory request completion.
 */
using MemoryCallback = std::function<void(MemoryRequest&)>;

/**
 * Abstract memory port interface.
 *
 * This interface provides memory access functionality that SALAM
 * hardware components need. Different backends implement this:
 *
 * - Gem5MemoryPort: Wraps gem5's RequestPort
 * - StandaloneMemoryPort: Direct memory array access with latency
 * - SystemCMemoryPort: Maps to TLM sockets
 */
class MemoryPort {
  public:
    virtual ~MemoryPort() = default;

    /**
     * Get the port name.
     */
    virtual const std::string& name() const = 0;

    /**
     * Send a timing request.
     * @param req The memory request.
     * @return true if request was accepted, false if port is busy.
     */
    virtual bool sendTimingRequest(MemoryRequest& req) = 0;

    /**
     * Send a functional (atomic) request.
     * This bypasses timing simulation and returns immediately.
     * @param req The memory request.
     */
    virtual void sendFunctional(MemoryRequest& req) = 0;

    /**
     * Check if the port is ready to accept requests.
     */
    virtual bool isReady() const = 0;

    /**
     * Check if the port is stalled (blocked on a response).
     */
    virtual bool isStalled() const = 0;

    /**
     * Set the callback for request completion.
     */
    virtual void setCompletionCallback(MemoryCallback callback) = 0;

    /**
     * Get the address range this port can access.
     * @param start Output: start address
     * @param end Output: end address (exclusive)
     */
    virtual void getAddressRange(uint64_t& start, uint64_t& end) const {
        start = 0;
        end = UINT64_MAX;
    }
};

/**
 * Shared pointer type for memory ports.
 */
using MemoryPortPtr = std::shared_ptr<MemoryPort>;

/**
 * Abstract memory responder interface.
 *
 * Implemented by components that respond to memory requests
 * (equivalent to gem5's ResponsePort).
 */
class MemoryResponder {
  public:
    virtual ~MemoryResponder() = default;

    /**
     * Handle an incoming timing request.
     * @param req The memory request.
     * @return true if request was handled, false if busy.
     */
    virtual bool recvTimingRequest(MemoryRequest& req) = 0;

    /**
     * Handle an incoming functional request.
     */
    virtual void recvFunctional(MemoryRequest& req) = 0;

    /**
     * Get the address range this responder handles.
     */
    virtual void getAddressRange(uint64_t& start, uint64_t& end) const = 0;
};

/**
 * Simple in-memory storage.
 *
 * Can be used for standalone simulation or testing.
 */
class SimpleMemory : public MemoryResponder {
  public:
    SimpleMemory(uint64_t baseAddr, size_t size)
        : base(baseAddr), storage(size, 0) {}

    bool recvTimingRequest(MemoryRequest& req) override {
        recvFunctional(req);
        req.completed = true;
        req.success = true;
        return true;
    }

    void recvFunctional(MemoryRequest& req) override {
        if (req.addr < base || req.addr + req.size > base + storage.size()) {
            req.success = false;
            return;
        }

        size_t offset = req.addr - base;
        if (req.isRead()) {
            req.data.resize(req.size);
            std::copy(storage.begin() + offset,
                      storage.begin() + offset + req.size,
                      req.data.begin());
        } else if (req.isWrite()) {
            std::copy(req.data.begin(),
                      req.data.begin() + req.size,
                      storage.begin() + offset);
        }
        req.success = true;
    }

    void getAddressRange(uint64_t& start, uint64_t& end) const override {
        start = base;
        end = base + storage.size();
    }

    /// Direct access to memory contents (for testing/debugging)
    std::vector<uint8_t>& getStorage() { return storage; }
    const std::vector<uint8_t>& getStorage() const { return storage; }

  private:
    uint64_t base;
    std::vector<uint8_t> storage;
};

} // namespace salam

#endif // __SALAM_MEMORY_INTERFACE_HH__
