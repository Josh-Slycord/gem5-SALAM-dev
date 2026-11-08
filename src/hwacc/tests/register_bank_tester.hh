// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Joshua Slycord
#ifndef __HWACC_TESTS_REGISTER_BANK_TESTER_HH__
#define __HWACC_TESTS_REGISTER_BANK_TESTER_HH__

/**
 * @file
 * @brief Declares SalamRegisterBankTester for RegisterBank timing, retry,
 * and drain verification.
 *
 * Exercises RegisterBank delta-write staging, response queue backpressure
 * and retry ordering, and Drainable state transitions.
 */

#include <cstdint>
#include <string>
#include <vector>
#include "hwacc/register_bank.hh"
#include "params/SalamRegisterBankTester.hh"
#include "sim/clocked_object.hh"

/**
 * @brief Protocol verification SimObject for SALAM RegisterBank.
 *
 * Drives timing requests and response backpressure against a RegisterBank's
 * register port and load port, validating write-delta visibility, retry
 * ordering, and drain completion.
 */
class SalamRegisterBankTester : public gem5::ClockedObject
{
    /**
     * @brief Requestor port used to drive timing packets into RegisterBank.
     */
    class Port : public gem5::RequestPort
    {
        SalamRegisterBankTester &owner;

      public:
        Port(SalamRegisterBankTester &owner, const std::string &suffix);
        bool recvTimingResp(gem5::PacketPtr pkt) override;
        void recvReqRetry() override;
        void
        recvRangeChange() override
        {}
    };
    Port port, load;
    RegisterBank *bank;
    const std::string mode;
    const bool corruptExpected;
    gem5::EventFunctionWrapper startEvent, retryEvent, inspectEvent;
    gem5::PacketPtr first = nullptr;
    unsigned rejected = 0, completed = 0;
    uint64_t observedValue = 0;
    bool sawDraining = false;
    std::vector<unsigned> observedOrder;
    /**
     * @brief Allocates a 64-bit request packet targeting the register bank.
     *
     * @param cmd Memory command (ReadReq or WriteReq).
     * @param value 64-bit payload value for writes.
     * @return Newly allocated PacketPtr.
     */
    gem5::PacketPtr packet(gem5::MemCmd cmd, uint64_t value = 0);
    /**
     * @brief Handles a timing response packet from the RegisterBank.
     *
     * @param pkt Response packet.
     * @return True if accepted, false to inject response backpressure.
     */
    bool response(gem5::PacketPtr pkt);
    /**
     * @brief Initiates the configured RegisterBank test scenario.
     */
    void start();
    /**
     * @brief Performs a functional read of the target register bank address.
     *
     * @return 64-bit register value.
     */
    uint64_t readValue();

  public:
    PARAMS(SalamRegisterBankTester);
    /**
     * @brief Constructs the SalamRegisterBankTester SimObject.
     *
     * @param p Configuration parameters.
     */
    SalamRegisterBankTester(const SalamRegisterBankTesterParams &p);
    /**
     * @brief Returns the requested test port ("port" or "load").
     *
     * @param name Port interface name.
     * @param id Port index.
     * @return Reference to bound gem5::Port.
     */
    gem5::Port &getPort(const std::string &name,
                        gem5::PortID id = gem5::InvalidPortID) override;
    /**
     * @brief Schedules the test start event at simulation startup.
     */
    void startup() override;
    /**
     * @brief Evaluates scenario assertions and returns a PASS/FAIL summary.
     *
     * @return Structured verification result string.
     */
    std::string report();
};
#endif
