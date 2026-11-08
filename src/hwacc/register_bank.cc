#include "hwacc/register_bank.hh"
#include "hwacc/response_queue.hh"

#include <sys/mman.h>
#include <sys/types.h>
#include <sys/user.h>

#include <cstring>
#include <stdio.h>
#include <stdlib.h>
#include <iomanip>

#include "base/trace.hh"
#include "mem/packet.hh"
#include "mem/packet_access.hh"
#include "sim/system.hh"
#include "debug/Drain.hh"

using namespace std;

#include "debug/MemoryAccess.hh"

RegisterBank::RegisterBank(const RegisterBankParams &p) :
    AbstractMemory(p),
    port(name() + ".reg_port", this),
    load(name() + ".load_port", this),
    deltaTime(p.delta_time),
    retryResp(false),
    dequeueEvent([this]{ dequeue(); }, name()),
    deltaEvent([this]{ delta(); }, name())
{
    // Setup of the delta memory container
    int shm_fd = -1;
    int map_flags = MAP_ANON | MAP_PRIVATE;

    deltaAddr = (uint8_t *)mmap(NULL, range.size(),
                                PROT_READ | PROT_WRITE,
                                map_flags, shm_fd, 0);
    if (deltaAddr == (uint8_t *)MAP_FAILED) {
        perror("mmap");
        fatal("Could not mmap %d bytes for range %s!\n", range.size(),
            range.to_string());
    }
}

static inline void
tracePacket(System *sys, const char *label, PacketPtr pkt)
{
    int size = pkt->getSize();
#if THE_ISA != NULL_ISA
    if (size == 1 || size == 2 || size == 4 || size == 8) {
        DPRINTF(MemoryAccess,"%s from %s of size %i on address %#x data "
                "%#x %c\n", label, sys->getRequestorName(pkt->req->requestorId()),
                size, pkt->getAddr(), pkt->getUintX(ByteOrder::little),
                pkt->req->isUncacheable() ? 'U' : 'C');
        return;
    }
#endif
    DPRINTF(MemoryAccess, "%s from %s of size %i on address %#x %c\n",
            label, sys->getRequestorName(pkt->req->requestorId()),
            size, pkt->getAddr(), pkt->req->isUncacheable() ? 'U' : 'C');
    DDUMP(MemoryAccess, pkt->getConstPtr<uint8_t>(), pkt->getSize());
}

#if TRACING_ON
#   define TRACE_PACKET(A) tracePacket(system(), A, pkt)
#else
#   define TRACE_PACKET(A)
#endif

void
RegisterBank::registerAccess(PacketPtr pkt)
{
    assert(AddrRange(pkt->getAddr(),
                     pkt->getAddr() + (pkt->getSize() - 1)).isSubset(range));

    if (pkt->isRead()) {
        assert(!pkt->isWrite());
        uint8_t * hostAddr = pmemAddr + pkt->getAddr() - range.start();
        if (pmemAddr) {
            pkt->setData(hostAddr);
        }
        stats.numReads[pkt->req->requestorId()]++;
        stats.bytesRead[pkt->req->requestorId()] += pkt->getSize();
    } else if (pkt->isWrite()) {
        uint8_t * hostAddr = deltaAddr + pkt->getAddr() - range.start();
        if (writeOK(pkt)) {
            if (deltaAddr) {
                pkt->writeData(hostAddr);
                DPRINTF(MemoryAccess, "%s wrote %i bytes to address %x\n",
                        __func__, pkt->getSize(), pkt->getAddr());
            }
            assert(!pkt->req->isInstFetch());
            TRACE_PACKET("Write");
            stats.numWrites[pkt->req->requestorId()]++;
            stats.bytesWritten[pkt->req->requestorId()] += pkt->getSize();
            if (!deltaEvent.scheduled())
                schedule(deltaEvent, curTick()+deltaTime);
        }
    } else {
        panic("Unexpected packet %s", pkt->print());
    }

    if (pkt->needsResponse()) {
        pkt->makeResponse();
    }
}

void
RegisterBank::init()
{
    // allow unconnected memories as this is used in several ruby
    // systems at the moment
    if (port.isConnected()) {
        port.sendRangeChange();
    }
    if (load.isConnected()) {
        load.sendRangeChange();
    }
}

Tick
RegisterBank::recvAtomic(PacketPtr pkt)
{
    panic_if(pkt->cacheResponding(), "Should not see packets where cache "
             "is responding");
    registerAccess(pkt);
    return deltaTime;
}

Tick
RegisterBank::recvAtomicBackdoor(PacketPtr pkt, MemBackdoorPtr &_backdoor)
{
    Tick latency = recvAtomic(pkt);

    if (backdoor.ptr())
        _backdoor = &backdoor;
    return latency;
}

void
RegisterBank::recvFunctional(PacketPtr pkt)
{
    pkt->pushLabel(name());

    functionalAccess(pkt);

    bool done = false;
    auto p = packetQueue.begin();
    // potentially update the packets in our packet queue as well
    while (!done && p != packetQueue.end()) {
        done = pkt->trySatisfyFunctional(p->pkt);
        ++p;
    }

    pkt->popLabel();
}

bool
RegisterBank::recvTimingReq(PacketPtr pkt)
{
    panic_if(pkt->cacheResponding(), "Should not see packets where cache "
             "is responding");

    panic_if(!(pkt->isRead() || pkt->isWrite()),
             "Should only see read and writes at memory controller, "
             "saw %s to %#llx\n", pkt->cmdString(), pkt->getAddr());

    bool isRead = pkt->isRead();

    bool needsResponse = pkt->needsResponse();
    Tick responseTime = curTick() + recvAtomic(pkt);
    if (needsResponse) {
        // recvAtomic() should already have turned packet into
        // atomic response
        assert(pkt->isResponse());
        // Preserve the historical zero-time response for an idle read.
        // Enqueue first so a synchronous peer callback cannot bypass a
        // rejected response or replace the head while it is being sent.
        const bool immediateRead = isRead && packetQueue.empty() &&
            !retryResp && !responseInProgress;
        auto position = gem5::salam::responseInsertionPosition(
            packetQueue, responseTime, retryResp || responseInProgress,
            [pkt](const auto &entry) { return entry.pkt->matchAddr(pkt); });
        packetQueue.emplace(position, pkt, responseTime);

        if (immediateRead) {
            dequeue();
        } else {
            scheduleNextResponse();
        }
    }
    return true;
}

void
RegisterBank::dequeue()
{
    assert(!packetQueue.empty());
    DeferredPacket deferred_pkt = packetQueue.front();

    responseInProgress = true;
    retryResp = !port.sendTimingResp(deferred_pkt.pkt);
    responseInProgress = false;
    if (!retryResp) {
        packetQueue.pop_front();

        if (!packetQueue.empty()) {
            scheduleNextResponse();
        }
    }
    tryCompleteDrain();
}

void
RegisterBank::delta()
{
    std::memcpy(pmemAddr, deltaAddr, range.size());
    tryCompleteDrain();
}

void
RegisterBank::recvRespRetry()
{
    assert(retryResp);
    retryResp = false;
    scheduleNextResponse();
}

void
RegisterBank::scheduleNextResponse()
{
    auto when = gem5::salam::nextResponseTime(
        packetQueue, curTick(), responseInProgress,
        [this](const auto &) { return retryResp; });
    if (!when) {
        if (dequeueEvent.scheduled()) {
            deschedule(dequeueEvent);
        }
        return;
    }
    if (!dequeueEvent.scheduled()) {
        schedule(dequeueEvent, *when);
    } else if (dequeueEvent.when() != *when) {
        reschedule(dequeueEvent, *when);
    }
}

Port &
RegisterBank::getPort(const std::string &if_name, PortID idx)
{
    if (if_name == "reg_port") {
        return port;
    } else if (if_name == "load_port") {
        return load;
    }
    return AbstractMemory::getPort(if_name, idx);
}

DrainState
RegisterBank::drain()
{
    if (!packetQueue.empty() || deltaEvent.scheduled() ||
        dequeueEvent.scheduled() || retryResp || responseInProgress) {
        return DrainState::Draining;
    }
    return DrainState::Drained;
}

void
RegisterBank::tryCompleteDrain()
{
    if (drainState() == DrainState::Draining &&
        drain() == DrainState::Drained)
        signalDrainDone();
}
