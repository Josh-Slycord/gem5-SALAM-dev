// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Joshua Slycord
#ifndef __HWACC_TESTS_LIFECYCLE_TESTER_HH__
#define __HWACC_TESTS_LIFECYCLE_TESTER_HH__
#include <cstdint>
#include <deque>
#include <map>
#include <memory>
#include <string>
#include <vector>
#include "hwacc/compute_unit.hh"
#include "hwacc/llvm_interface.hh"
#include "params/SalamLifecycleTester.hh"
#include "sim/eventq.hh"
class SalamLifecycleTester : public ComputeUnit
{
  private:
    class Peer : public gem5::ResponsePort
    {
        SalamLifecycleTester &owner;
        unsigned rejects;
        gem5::PacketPtr blocked = nullptr;
        gem5::Addr blockedAddr = 0;
        unsigned blockedSize = 0;
        std::vector<uint8_t> blockedData;
        std::deque<gem5::PacketPtr> responses;
        gem5::EventFunctionWrapper retryEvent;
        gem5::EventFunctionWrapper responseEvent;
        void respond(gem5::PacketPtr pkt);
        void deliver();

      public:
        unsigned attempts = 0, accepted = 0, rejected = 0, replied = 0;
        Peer(SalamLifecycleTester &owner, gem5::PortID id);
        gem5::AddrRangeList getAddrRanges() const override;
        bool recvTimingReq(gem5::PacketPtr pkt) override;
        void recvRespRetry() override;
        gem5::Tick recvAtomic(gem5::PacketPtr) override;
        void recvFunctional(gem5::PacketPtr) override;
        bool idle() const;
    };
    class Pio : public gem5::RequestPort
    {
      public:
        Pio(const std::string &name, gem5::PortID id) : RequestPort(name, id)
        {}
        bool recvTimingResp(gem5::PacketPtr) override;
        void recvReqRetry() override;
        void
        recvRangeChange() override
        {}
    };
    std::vector<std::unique_ptr<Peer>> peers;
    std::vector<std::unique_ptr<Pio>> pios;
    const std::string mode, route;
    LLVMInterface *a, *b;
    const bool corruptExpected, retainGraph;
    gem5::EventFunctionWrapper pulseEvent;
    unsigned phase = 0, round = 1, reads = 0, writes = 0;
    unsigned launchesA = 0, launchesB = 0;
    uint32_t firstOutputA = 0, firstOutputB = 0;
    bool restartAWhileB = false, restartBWhileA = false;
    bool finishedBWhileA = false;
    std::vector<std::weak_ptr<SALAM::Value>> previousA, previousB;
    void startActor(unsigned actor, unsigned iterations);
    std::vector<uint8_t> observedRead;
    bool sawDraining = false;
    std::map<gem5::Addr, uint8_t> memory;
    std::vector<std::weak_ptr<SALAM::Value>> weakA, weakB;
    std::shared_ptr<SALAM::Value> retained;
    void pulse();
    void launch();
    void mmio(unsigned actor, gem5::Addr addr, uint64_t value, unsigned size);
    void capture(LLVMInterface *actor,
                 std::vector<std::weak_ptr<SALAM::Value>> &values);
    size_t live(const std::vector<std::weak_ptr<SALAM::Value>> &values) const;
    uint32_t output(gem5::Addr address) const;
    bool pending() const;

  public:
    PARAMS(SalamLifecycleTester);
    SalamLifecycleTester(const SalamLifecycleTesterParams &p);
    gem5::Port &getPort(const std::string &name,
                        gem5::PortID id = gem5::InvalidPortID) override;
    void startup() override;
    void readCommit(MemoryRequest *req) override;
    void writeCommit(MemoryRequest *req) override;
    std::string report();
};
#endif
