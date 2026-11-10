// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Joshua Slycord
#ifndef __HWACC_TESTS_LIFECYCLE_TESTER_HH__
#define __HWACC_TESTS_LIFECYCLE_TESTER_HH__

/**
 * @file
 * @brief Declares SalamLifecycleTester for SimObject protocol and CDFG
 * lifecycle validation.
 *
 * Exercises CommInterface port retry/drain behavior, multi-round
 * LLVMInterface execution and CDFG cycle teardown (via std::weak_ptr<Value>
 * liveness checks), and overlapping independent accelerator runs.
 */

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

/**
 * @brief Protocol and lifecycle verification harness for SALAM SimObjects.
 *
 * Drives synthetic memory-route backpressure, drain state transitions,
 * repeated single-accelerator launches, and overlapping dual-accelerator
 * invocations while tracking per-instance SALAM::Value weak references.
 */
class SalamLifecycleTester : public ComputeUnit
{
  private:
    /**
     * @brief Responder port peer injecting configurable timing backpressure.
     */
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

    /**
     * @brief Requestor port issuing MMIO control writes to CommInterface.
     */
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
    /**
     * @brief Programs MMIO arguments and starts the specified accelerator.
     *
     * @param actor Index of target accelerator (0 for A, 1 for B).
     * @param iterations Loop trip count to write to MMIO configuration.
     */
    void startActor(unsigned actor, unsigned iterations);
    std::vector<uint8_t> observedRead;
    bool sawDraining = false;
    std::map<gem5::Addr, uint8_t> memory;
    std::vector<std::weak_ptr<SALAM::Value>> weakA, weakB;
    std::shared_ptr<SALAM::Value> retained;
    /**
     * @brief Periodic state-machine callback advancing the active test mode.
     */
    void pulse();
    /**
     * @brief Dispatches the initial test transaction or accelerator launch.
     */
    void launch();
    /**
     * @brief Sends a functional MMIO write packet to an accelerator's PIO
     * port.
     *
     * @param actor Target accelerator index.
     * @param addr Destination MMIO address.
     * @param value Payload value to write.
     * @param size Access width in bytes.
     */
    void mmio(unsigned actor, gem5::Addr addr, uint64_t value, unsigned size);
    /**
     * @brief Captures weak_ptr handles to all current SALAM::Value nodes in
     * an accelerator instance.
     *
     * @param actor Target LLVMInterface instance.
     * @param values Output vector populated with weak references.
     */
    void capture(LLVMInterface *actor,
                 std::vector<std::weak_ptr<SALAM::Value>> &values);
    /**
     * @brief Counts how many captured weak_ptr handles remain unexpired.
     *
     * @param values Vector of weak references to inspect.
     * @return Count of live SALAM::Value objects.
     */
    size_t live(const std::vector<std::weak_ptr<SALAM::Value>> &values) const;
    /**
     * @brief Reads a 32-bit little-endian word from the tester's backing
     * store.
     *
     * @param address Base byte address.
     * @return Reconstructed 32-bit unsigned value.
     */
    uint32_t output(gem5::Addr address) const;
    /**
     * @brief Checks whether any peer port still holds blocked or queued
     * packets.
     *
     * @return True if peer ports are not yet idle.
     */
    bool pending() const;

  public:
    PARAMS(SalamLifecycleTester);
    /**
     * @brief Constructs the SalamLifecycleTester SimObject.
     *
     * @param p Configuration parameters.
     */
    SalamLifecycleTester(const SalamLifecycleTesterParams &p);
    /**
     * @brief Resolves a named port binding for Peer or Pio connections.
     *
     * @param name Port interface name.
     * @param id Port index.
     * @return Reference to bound gem5::Port.
     */
    gem5::Port &getPort(const std::string &name,
                        gem5::PortID id = gem5::InvalidPortID) override;
    /**
     * @brief Schedules the initial test launch at simulation startup.
     */
    void startup() override;
    /**
     * @brief Callback invoked by CommInterface when a read request completes.
     *
     * @param req Completed MemoryRequest descriptor.
     */
    void readCommit(MemoryRequest *req) override;
    /**
     * @brief Callback invoked by CommInterface when a write request completes.
     *
     * @param req Completed MemoryRequest descriptor.
     */
    void writeCommit(MemoryRequest *req) override;
    /**
     * @brief Evaluates test invariants and returns a structured result string.
     *
     * @return Summary report starting with PASS or FAIL.
     */
    std::string report();
};
#endif
