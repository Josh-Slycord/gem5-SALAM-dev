/*
 * Copyright (c) 2024 gem5-SALAM Contributors
 * All rights reserved.
 *
 * gem5 Memory Port Adapter
 * Version: 3.0.0.pre[1.0.0]
 *
 * Implements SALAM's MemoryPort interface using gem5's port system.
 */

#ifndef __SALAM_GEM5_MEMORY_PORT_HH__
#define __SALAM_GEM5_MEMORY_PORT_HH__

// gem5 includes
#include "mem/port.hh"
#include "mem/packet.hh"
#include "mem/request.hh"

// SALAM includes
#include "salam/memory_interface.hh"

#include <queue>

namespace salam {

/**
 * gem5 MemoryPort implementation.
 *
 * This adapter wraps gem5's RequestPort to implement SALAM's
 * abstract MemoryPort interface.
 */
class Gem5MemoryPort : public MemoryPort {
  public:
    /**
     * Inner class implementing gem5's RequestPort.
     */
    class Gem5RequestPort : public gem5::RequestPort {
      public:
        Gem5RequestPort(const std::string& name, Gem5MemoryPort* owner)
            : gem5::RequestPort(name), owner(owner) {}

      protected:
        bool recvTimingResp(gem5::PacketPtr pkt) override {
            return owner->handleTimingResponse(pkt);
        }

        void recvReqRetry() override {
            owner->handleRetry();
        }

      private:
        Gem5MemoryPort* owner;
    };

    Gem5MemoryPort(const std::string& portName,
                   gem5::SimObject* parent,
                   gem5::RequestorID requestorId)
        : portName(portName),
          port(portName, this),
          parent(parent),
          reqId(requestorId),
          stalled(false),
          nextRequestId(0) {}

    // MemoryPort interface implementation

    const std::string& name() const override {
        return portName;
    }

    bool sendTimingRequest(MemoryRequest& req) override {
        if (stalled) {
            return false;
        }

        // Create gem5 packet
        gem5::PacketPtr pkt = createPacket(req);
        if (!pkt) {
            return false;
        }

        // Store mapping for response handling
        pendingRequests[pkt] = &req;
        req.requestTick = gem5::curTick();

        // Send request
        if (!port.sendTimingReq(pkt)) {
            pendingRequests.erase(pkt);
            delete pkt;
            stalled = true;
            retryQueue.push(&req);
            return false;
        }

        return true;
    }

    void sendFunctional(MemoryRequest& req) override {
        gem5::PacketPtr pkt = createPacket(req);
        if (pkt) {
            port.sendFunctional(pkt);
            copyResponseData(pkt, req);
            req.completed = true;
            req.success = true;
            delete pkt;
        }
    }

    bool isReady() const override {
        return !stalled;
    }

    bool isStalled() const override {
        return stalled;
    }

    void setCompletionCallback(MemoryCallback callback) override {
        completionCallback = callback;
    }

    /**
     * Get the underlying gem5 port for connection.
     */
    gem5::RequestPort& getGem5Port() {
        return port;
    }

  private:
    gem5::PacketPtr createPacket(MemoryRequest& req) {
        gem5::MemCmd cmd;
        switch (req.type) {
            case MemoryRequestType::Read:
                cmd = gem5::MemCmd::ReadReq;
                break;
            case MemoryRequestType::Write:
                cmd = gem5::MemCmd::WriteReq;
                break;
            case MemoryRequestType::ReadExclusive:
                cmd = gem5::MemCmd::ReadExReq;
                break;
            default:
                cmd = gem5::MemCmd::ReadReq;
        }

        auto request = std::make_shared<gem5::Request>(
            req.addr, req.size, 0, reqId);

        gem5::PacketPtr pkt = new gem5::Packet(request, cmd);

        if (req.isWrite()) {
            pkt->allocate();
            std::copy(req.data.begin(), req.data.end(),
                      pkt->getPtr<uint8_t>());
        } else {
            pkt->allocate();
        }

        return pkt;
    }

    void copyResponseData(gem5::PacketPtr pkt, MemoryRequest& req) {
        if (req.isRead() && pkt->hasData()) {
            req.data.resize(pkt->getSize());
            std::copy(pkt->getConstPtr<uint8_t>(),
                      pkt->getConstPtr<uint8_t>() + pkt->getSize(),
                      req.data.begin());
        }
    }

    bool handleTimingResponse(gem5::PacketPtr pkt) {
        auto it = pendingRequests.find(pkt);
        if (it != pendingRequests.end()) {
            MemoryRequest* req = it->second;
            copyResponseData(pkt, *req);
            req->responseTick = gem5::curTick();
            req->completed = true;
            req->success = !pkt->isError();
            pendingRequests.erase(it);

            if (completionCallback) {
                completionCallback(*req);
            }
        }
        delete pkt;
        return true;
    }

    void handleRetry() {
        stalled = false;
        while (!retryQueue.empty()) {
            MemoryRequest* req = retryQueue.front();
            retryQueue.pop();
            if (!sendTimingRequest(*req)) {
                break;
            }
        }
    }

    std::string portName;
    Gem5RequestPort port;
    gem5::SimObject* parent;
    gem5::RequestorID reqId;
    bool stalled;
    uint64_t nextRequestId;

    std::map<gem5::PacketPtr, MemoryRequest*> pendingRequests;
    std::queue<MemoryRequest*> retryQueue;
    MemoryCallback completionCallback;
};

} // namespace salam

#endif // __SALAM_GEM5_MEMORY_PORT_HH__
