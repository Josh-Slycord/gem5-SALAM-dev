// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Joshua Slycord
#include "hwacc/tests/register_bank_tester.hh"
#include <sstream>
#include "base/logging.hh"
#include "mem/packet_access.hh"
#include "sim/drain.hh"
#include "sim/sim_exit.hh"
using namespace gem5;
SalamRegisterBankTester::Port::Port(SalamRegisterBankTester &o,
                                    const std::string &suffix)
    : RequestPort(o.name() + suffix), owner(o)
{}
bool
SalamRegisterBankTester::Port::recvTimingResp(PacketPtr pkt)
{
    return owner.response(pkt);
}
void
SalamRegisterBankTester::Port::recvReqRetry()
{
    panic("RegisterBank unexpectedly rejected a request");
}
SalamRegisterBankTester::SalamRegisterBankTester(
    const SalamRegisterBankTesterParams &p)
    : ClockedObject(p),
      port(*this, ".port"),
      load(*this, ".load"),
      bank(p.bank),
      mode(p.mode),
      corruptExpected(p.corrupt_expected),
      startEvent([this] { start(); }, name() + ".start"),
      retryEvent([this] { port.sendRetryResp(); }, name() + ".retry"),
      inspectEvent(
          [this] {
              fatal_if(bank->drainState() != DrainState::Draining,
                       "RegisterBank reported drained before pending work");
              sawDraining = true;
          },
          name() + ".inspect")
{
    fatal_if(mode != "delta" && mode != "response-retry", "unknown bank mode");
}
Port &
SalamRegisterBankTester::getPort(const std::string &name, PortID id)
{
    if (name == "port") {
        return port;
    }
    if (name == "load") {
        return load;
    }
    return ClockedObject::getPort(name, id);
}
PacketPtr
SalamRegisterBankTester::packet(MemCmd cmd, uint64_t value)
{
    auto request = std::make_shared<Request>(0x4000, 8, Request::Flags(),
                                             Request::funcRequestorId);
    auto *pkt = new Packet(request, cmd);
    pkt->allocate();
    if (pkt->isWrite()) {
        pkt->setLE<uint64_t>(value);
    }
    return pkt;
}
void
SalamRegisterBankTester::startup()
{
    schedule(startEvent, clockEdge(Cycles(1)));
}
uint64_t
SalamRegisterBankTester::readValue()
{
    auto *pkt = packet(MemCmd::ReadReq);
    load.sendFunctional(pkt);
    const uint64_t value = pkt->getLE<uint64_t>();
    delete pkt;
    return value;
}
void
SalamRegisterBankTester::start()
{
    if (mode == "delta") {
        auto *pkt = packet(MemCmd::WriteReq, 0x0807060504030201ULL);
        load.sendAtomic(pkt);
        fatal_if(!pkt->isResponse(), "preload failed");
        delete pkt;
        fatal_if(readValue() != 0,
                 "register write committed before delta event");
    } else {
        auto *preload = packet(MemCmd::WriteReq, 0x0807060504030201ULL);
        port.sendFunctional(preload);
        delete preload;
        first = packet(MemCmd::ReadReq);
        fatal_if(!port.sendTimingReq(first), "first bank request rejected");
    }
    schedule(inspectEvent, curTick() + 1);
    exitSimulationLoopClassic("salam bank fixture ready");
}
bool
SalamRegisterBankTester::response(PacketPtr pkt)
{
    const unsigned id = pkt == first ? 0 : 1;
    observedOrder.push_back(id);
    observedValue = pkt->getLE<uint64_t>();
    const uint64_t expected =
        corruptExpected ? 0x0807060504030200ULL : 0x0807060504030201ULL;
    fatal_if(pkt->getLE<uint64_t>() != expected,
             "bank response value differs");
    if (id == 0 && rejected < 2) {
        ++rejected;
        if (rejected == 1) {
            // Reenter the actual device while its head response is being sent.
            auto *next = packet(MemCmd::ReadReq);
            fatal_if(!port.sendTimingReq(next),
                     "nested bank request rejected");
        }
        schedule(retryEvent, curTick() + clockPeriod() * 2);
        return false;
    }
    ++completed;
    delete pkt;
    return true;
}
std::string
SalamRegisterBankTester::report()
{
    fatal_if(!sawDraining || bank->drainState() != DrainState::Drained,
             "RegisterBank reported drained before pending work");
    std::ostringstream out;
    out << "{\"state\":\"passed\",\"mode\":\"" << mode << "\"";
    if (mode == "delta") {
        const uint64_t value = readValue();
        const uint64_t expected = corruptExpected ? 0 : 0x0807060504030201ULL;
        fatal_if(value != expected, "register delta value differs");
        out << ",\"value\":" << value;
    } else {
        fatal_if(rejected != 2 || completed != 2 ||
                     observedOrder != std::vector<unsigned>({0, 0, 0, 1}),
                 "RegisterBank response bypass/retry order differs");
        out << ",\"response_value\":" << observedValue;
        out << ",\"rejected_responses\":" << rejected
            << ",\"completed_responses\":" << completed
            << ",\"response_order\":[0,0,0,1]";
    }
    out << "}";
    return out.str();
}
