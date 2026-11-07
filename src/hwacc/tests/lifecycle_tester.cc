// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Joshua Slycord
#include "hwacc/tests/lifecycle_tester.hh"
#include <algorithm>
#include <set>
#include <sstream>
#include "base/logging.hh"
#include "mem/packet_access.hh"
#include "sim/drain.hh"
#include "sim/sim_exit.hh"
using namespace gem5;

SalamLifecycleTester::Peer::Peer(SalamLifecycleTester &o, PortID id)
    : ResponsePort(o.name() + ".memory" + std::to_string(id), id),
      owner(o),
      rejects(
          (o.mode == "retry" || o.mode == "retry-sync" || o.mode == "lifetime")
              ? 2
              : 0),
      retryEvent([this] { sendRetryReq(); }, o.name() + ".retry"),
      responseEvent([this] { deliver(); }, o.name() + ".response")
{}
AddrRangeList
SalamLifecycleTester::Peer::getAddrRanges() const
{
    return {AddrRange(0x1000, 0x2000)};
}
bool
SalamLifecycleTester::Peer::idle() const
{
    return !blocked && responses.empty() && !retryEvent.scheduled() &&
           !responseEvent.scheduled();
}
bool
SalamLifecycleTester::Peer::recvTimingReq(PacketPtr pkt)
{
    ++attempts;
    if (blocked) {
        fatal_if(pkt != blocked || pkt->getAddr() != blockedAddr ||
                     pkt->getSize() != blockedSize,
                 "retry packet changed");
        if (pkt->isWrite()) {
            const uint8_t *data = pkt->getConstPtr<uint8_t>();
            fatal_if(!std::equal(blockedData.begin(), blockedData.end(), data),
                     "retry payload changed");
        }
    }
    if (rejects) {
        --rejects;
        ++rejected;
        blocked = pkt;
        blockedAddr = pkt->getAddr();
        blockedSize = pkt->getSize();
        if (pkt->isWrite()) {
            const uint8_t *data = pkt->getConstPtr<uint8_t>();
            blockedData.assign(data, data + pkt->getSize());
        }
        fatal_if(retryEvent.scheduled(), "duplicate retry scheduling");
        owner.schedule(retryEvent, curTick() + owner.clockPeriod() * 20);
        return false;
    }
    blocked = nullptr;
    ++accepted;
    if (owner.mode == "sync" || owner.mode == "retry-sync") {
        respond(pkt);
    } else {
        responses.push_back(pkt);
        if (!responseEvent.scheduled()) {
            owner.schedule(responseEvent, curTick() + owner.clockPeriod() * 5);
        }
    }
    return true;
}
void
SalamLifecycleTester::Peer::respond(PacketPtr pkt)
{
    if (pkt->isRead()) {
        auto *data = pkt->getPtr<uint8_t>();
        for (unsigned i = 0; i < pkt->getSize(); ++i) {
            auto it = owner.memory.find(pkt->getAddr() + i);
            data[i] = it == owner.memory.end()
                          ? uint8_t((pkt->getAddr() + i) * 17 + 3)
                          : it->second;
        }
    } else {
        const auto *data = pkt->getConstPtr<uint8_t>();
        for (unsigned i = 0; i < pkt->getSize(); ++i) {
            owner.memory[pkt->getAddr() + i] = data[i];
        }
    }
    pkt->makeResponse();
    ++replied;
    fatal_if(!sendTimingResp(pkt), "CommInterface rejected a response");
    // The production completion callback owns and deletes pkt.
}
void
SalamLifecycleTester::Peer::deliver()
{
    auto *pkt = responses.front();
    responses.pop_front();
    respond(pkt);
    if (!responses.empty() && !responseEvent.scheduled()) {
        owner.schedule(responseEvent, curTick() + owner.clockPeriod() * 5);
    }
}
void
SalamLifecycleTester::Peer::recvRespRetry()
{
    panic("fixture response unexpectedly retried");
}
Tick
SalamLifecycleTester::Peer::recvAtomic(PacketPtr)
{
    panic("fixture memory received atomic request");
}
void
SalamLifecycleTester::Peer::recvFunctional(PacketPtr)
{
    panic("fixture memory received functional request");
}
bool
SalamLifecycleTester::Pio::recvTimingResp(PacketPtr)
{
    panic("fixture PIO uses atomic operations only");
}
void
SalamLifecycleTester::Pio::recvReqRetry()
{
    panic("fixture PIO unexpectedly retried");
}
SalamLifecycleTester::SalamLifecycleTester(const SalamLifecycleTesterParams &p)
    : ComputeUnit(p),
      mode(p.mode),
      route(p.route),
      a(p.actor_a),
      b(p.actor_b),
      corruptExpected(p.corrupt_expected),
      retainGraph(p.retain_graph),
      pulseEvent([this] { pulse(); }, name() + ".pulse")
{
    fatal_if(mode != "async" && mode != "sync" && mode != "retry" &&
                 mode != "retry-sync" && mode != "lifetime",
             "unknown test mode");
    if (mode != "lifetime") {
        comm->registerCompUnit(this);
    } else {
        fatal_if(!a || !b || a == b, "two real LLVM actors required");
    }
}
Port &
SalamLifecycleTester::getPort(const std::string &name, PortID id)
{
    fatal_if(id < 0 && (name == "memory" || name == "pio"),
             "fixture vector port requires index");
    if (name == "memory") {
        while (peers.size() <= id) {
            peers.emplace_back(new Peer(*this, peers.size()));
        }
        return *peers.at(id);
    }
    if (name == "pio") {
        while (pios.size() <= id) {
            pios.emplace_back(new Pio(this->name() + ".pio", pios.size()));
        }
        return *pios.at(id);
    }
    return ComputeUnit::getPort(name, id);
}
void
SalamLifecycleTester::mmio(unsigned actor, Addr addr, uint64_t value,
                           unsigned size)
{
    auto request = std::make_shared<Request>(addr, size, Request::Flags(),
                                             Request::funcRequestorId);
    Packet pkt(request, MemCmd::WriteReq);
    pkt.allocate();
    for (unsigned i = 0; i < size; ++i) {
        pkt.getPtr<uint8_t>()[i] = value >> (8 * i);
    }
    pios.at(actor)->sendAtomic(&pkt);
    fatal_if(!pkt.isResponse(), "PIO operation did not complete");
}
void
SalamLifecycleTester::startup()
{
    schedule(pulseEvent, clockEdge(Cycles(1)));
}
void
SalamLifecycleTester::startActor(unsigned actor, unsigned iterations)
{
    fatal_if(DrainManager::instance().state() != DrainState::Running,
             "new invocation admitted while draining");
    auto *unit = actor == 0 ? a : b;
    auto &current = actor == 0 ? weakA : weakB;
    auto &previous = actor == 0 ? previousA : previousB;
    auto &launches = actor == 0 ? launchesA : launchesB;
    if (launches) {
        fatal_if(unit->running || !unit->values.empty() || live(current),
                 "finished actor retained graph values");
        previous = current;
        current.clear();
    }
    const Addr base = actor == 0 ? 0x10000000 : 0x10001000;
    const Addr outputAddr = actor == 0 ? 0x1100 : 0x1180;
    // An unchanged old result must never qualify a new invocation.
    for (unsigned i = 0; i < 4; ++i) {
        memory.erase(outputAddr + i);
    }
    mmio(actor, base + 1, outputAddr, 8);
    mmio(actor, base + 9, iterations, 4);
    mmio(actor, base, 1, 1);
    ++launches;
}
void
SalamLifecycleTester::launch()
{
    if (mode == "lifetime") {
        startActor(0, 4);
        startActor(1, 256);
    } else {
        comm->enqueueRead(new MemoryRequest(0x103d, 70));
        std::vector<uint8_t> data(70);
        for (unsigned i = 0; i < data.size(); ++i) {
            data[i] = i * 7 + 11;
        }
        comm->enqueueWrite(
            new MemoryRequest(0x123d, data.data(), data.size()));
    }
}
void
SalamLifecycleTester::capture(LLVMInterface *actor,
                              std::vector<std::weak_ptr<SALAM::Value>> &values)
{
    if (!values.empty() || actor->values.empty()) {
        return;
    }
    std::set<const SALAM::Value *> seen;
    auto keep = [&](const std::shared_ptr<SALAM::Value> &value) {
        if (value && seen.insert(value.get()).second) {
            values.emplace_back(value);
        }
    };
    for (const auto &value : actor->values) {
        keep(value);
    }
    for (const auto &function : actor->functions) {
        keep(function);
        for (const auto &block : *function->getBBList()) {
            keep(block);
            for (const auto &instruction : *block->Instructions()) {
                keep(instruction);
            }
        }
    }
}
size_t
SalamLifecycleTester::live(
    const std::vector<std::weak_ptr<SALAM::Value>> &values) const
{
    return std::count_if(values.begin(), values.end(),
                         [](const auto &v) { return !v.expired(); });
}
void
SalamLifecycleTester::pulse()
{
    if (phase == 0) {
        launch();
        phase = 1;
    } else if (mode == "lifetime") {
        capture(a, weakA);
        capture(b, weakB);
        if (!weakA.empty() && retainGraph && !retained) {
            retained = weakA.front().lock();
        }
        if (launchesA == 1 && !weakA.empty() && !a->running &&
            a->values.empty()) {
            fatal_if(live(weakA), "finished actor retained graph values");
            fatal_if(!b->running || live(weakB) == 0,
                     "actor A did not finish independently of B");
            firstOutputA = output(0x1100);
            fatal_if(firstOutputA != 23,
                     "first actor A numerical output differs");
            restartAWhileB = true;
            startActor(0, 512);
        }
        if (launchesB == 1 && !weakB.empty() && !b->running &&
            b->values.empty()) {
            fatal_if(live(weakB), "finished actor retained graph values");
            fatal_if(launchesA != 2 || !a->running || live(weakA) == 0,
                     "actor B did not finish independently of A");
            firstOutputB = output(0x1180);
            fatal_if(firstOutputB != 32640,
                     "first actor B numerical output differs");
            restartBWhileA = true;
            startActor(1, 16);
        }
        if (phase == 1 && launchesA == 2 && launchesB == 2 && !weakA.empty() &&
            !weakB.empty() && a->running && b->running) {
            phase = 2;
            schedule(pulseEvent, clockEdge(Cycles(1)));
            exitSimulationLoopClassic("salam fixture ready");
            return;
        }
        if (phase == 2) {
            fatal_if(
                (a->running && a->drainState() != DrainState::Draining) ||
                    (b->running && b->drainState() != DrainState::Draining),
                "LLVM actor drained while active");
            sawDraining = true;
            if (!b->running && !b->values.size() && a->running) {
                fatal_if(live(weakB) || live(weakA) == 0,
                         "per-instance graph lifetime check failed");
                finishedBWhileA = true;
            }
            if (!a->running && !b->running) {
                return;
            }
        }
    } else if (phase == 1 && peers.at(0)->attempts > 0) {
        phase = 2;
        schedule(pulseEvent, clockEdge(Cycles(1)));
        exitSimulationLoopClassic("salam fixture ready");
        return;
    } else if (phase == 2) {
        fatal_if(pending() && comm->drainState() != DrainState::Draining,
                 "CommInterface drained with pending work");
        sawDraining = true;
        if (reads == 1 && writes == 1) {
            return;
        }
    }
    schedule(pulseEvent, clockEdge(Cycles(1)));
}
void
SalamLifecycleTester::readCommit(MemoryRequest *req)
{
    fatal_if(req->getAddress() != 0x103d, "wrong read request");
    for (unsigned i = 0; i < 70; ++i) {
        uint8_t expected = uint8_t((0x103d + i) * 17 + 3);
        if (corruptExpected && i == 0) {
            expected ^= 1;
        }
        fatal_if(req->getBuffer()[i] != expected, "read bytes differ");
    }
    observedRead.assign(req->getBuffer(), req->getBuffer() + 70);
    ++reads;
}
void
SalamLifecycleTester::writeCommit(MemoryRequest *req)
{
    fatal_if(req->getAddress() != 0x123d, "wrong write request");
    ++writes;
}
bool
SalamLifecycleTester::pending() const
{
    return !comm->readQueue.empty() || !comm->writeQueue.empty() ||
           !comm->accRdQ.empty() || !comm->accWrQ.empty() ||
           comm->tickEvent.scheduled() || comm->computationNeeded;
}
uint32_t
SalamLifecycleTester::output(Addr address) const
{
    uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) {
        auto it = memory.find(address + i);
        fatal_if(it == memory.end(), "missing numerical output");
        value |= uint32_t(it->second) << (8 * i);
    }
    return value;
}
std::string
SalamLifecycleTester::report()
{
    if (pulseEvent.scheduled()) {
        deschedule(pulseEvent);
    }
    fatal_if(!sawDraining && mode != "sync",
             "drain manager did not wait for actual work");
    for (const auto &peer : peers) {
        fatal_if(!peer->idle(), "peer still has pending traffic");
    }
    std::ostringstream out;
    out << "{\"state\":\"passed\",\"round\":" << round;
    if (mode == "lifetime") {
        fatal_if(a->running || b->running || !a->values.empty() ||
                     !b->values.empty(),
                 "LLVM actor drained while active");
        fatal_if(!restartAWhileB || !restartBWhileA || !finishedBWhileA ||
                     live(weakA) || live(weakB) || live(previousA) ||
                     live(previousB),
                 "per-instance graph lifetime check failed");
        fatal_if(output(0x1100) != (corruptExpected ? 130834 : 130833) ||
                     output(0x1180) != 120,
                 "multi-accelerator numerical output differs");
        unsigned replies = 0;
        for (const auto &peer : peers) {
            replies += peer->replied;
        }
        fatal_if(replies != 4 ||
                     a->execStats.completedInvocations.value() != 2 ||
                     b->execStats.completedInvocations.value() != 2,
                 "fresh independent invocations did not complete");
        out << ",\"captured_a\":" << weakA.size()
            << ",\"captured_b\":" << weakB.size()
            << ",\"a_restart_while_b_active\":true"
            << ",\"b_restart_while_a_active\":true"
            << ",\"b_finished_while_a_active\":true"
            << ",\"a_completed_invocations\":"
            << a->execStats.completedInvocations.value()
            << ",\"b_completed_invocations\":"
            << b->execStats.completedInvocations.value()
            << ",\"a_first_output\":" << firstOutputA
            << ",\"b_first_output\":" << firstOutputB
            << ",\"a_output\":" << output(0x1100)
            << ",\"b_output\":" << output(0x1180)
            << ",\"fresh_write_responses\":" << replies
            << ",\"live_a_after\":" << live(weakA)
            << ",\"live_b_after\":" << live(weakB)
            << ",\"live_previous_a_after\":" << live(previousA)
            << ",\"live_previous_b_after\":" << live(previousB);
    } else {
        fatal_if(pending() || reads != 1 || writes != 1,
                 "CommInterface drained with pending work");
        fatal_if(peers.at(0)->accepted != (route == "reg" ? 2 : 6) ||
                     peers.at(0)->replied != (route == "reg" ? 2 : 6),
                 "missing or duplicate packet completion");
        const unsigned rejected =
            (mode == "retry" || mode == "retry-sync") ? 2 : 0;
        fatal_if(peers.at(0)->rejected != rejected, "missing backpressure");
        for (unsigned i = 0; i < 70; ++i) {
            fatal_if(memory.at(0x123d + i) != uint8_t(i * 7 + 11),
                     "write bytes differ");
        }
        const auto attempts = comm->commStats.attempts[0].value() +
                              comm->commStats.attempts[1].value();
        fatal_if(attempts != peers.at(0)->attempts,
                 "native send-attempt statistic differs from real peer");
        fatal_if(comm->commStats.bytes[0].value() != 70 ||
                     comm->commStats.bytes[1].value() != 70,
                 "native completed-byte counters differ");
        out << ",\"observed_read\":[";
        for (unsigned i = 0; i < observedRead.size(); ++i) {
            if (i) {
                out << ",";
            }
            out << unsigned(observedRead[i]);
        }
        out << "],\"observed_write\":[";
        for (unsigned i = 0; i < 70; ++i) {
            if (i) {
                out << ",";
            }
            out << unsigned(memory.at(0x123d + i));
        }
        out << "],\"send_attempts\":" << attempts;
        out << ",\"reads\":" << reads << ",\"writes\":" << writes
            << ",\"accepted_packets\":" << peers.at(0)->accepted
            << ",\"responses\":" << peers.at(0)->replied
            << ",\"rejections\":" << rejected;
    }
    out << "}";
    return out.str();
}
