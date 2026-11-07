// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Joshua Slycord
#ifndef __HWACC_TESTS_REGISTER_BANK_TESTER_HH__
#define __HWACC_TESTS_REGISTER_BANK_TESTER_HH__
#include <cstdint>
#include <string>
#include <vector>
#include "hwacc/register_bank.hh"
#include "params/SalamRegisterBankTester.hh"
#include "sim/clocked_object.hh"
class SalamRegisterBankTester : public gem5::ClockedObject
{
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
    gem5::PacketPtr packet(gem5::MemCmd cmd, uint64_t value = 0);
    bool response(gem5::PacketPtr pkt);
    void start();
    uint64_t readValue();

  public:
    PARAMS(SalamRegisterBankTester);
    SalamRegisterBankTester(const SalamRegisterBankTesterParams &p);
    gem5::Port &getPort(const std::string &name,
                        gem5::PortID id = gem5::InvalidPortID) override;
    void startup() override;
    std::string report();
};
#endif
