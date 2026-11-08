#ifndef __HWACC_SCRATCHPAD_MEMORY_HH__
#define __HWACC_SCRATCHPAD_MEMORY_HH__

/**
 * @file scratchpad_memory.hh
 * @brief Multi-ported, banked on-chip scratchpad memory model for gem5-SALAM.
 *
 * ScratchpadMemory models tightly coupled accelerator local SRAM memories
 * (SPMs).
 * It supports multiple concurrent request ports, configurable bank bandwidth
 * and
 * access latency, ready/valid synchronization bits, and rigorous timing retry
 * handling.
 */

#include "base/random.hh"
#include "mem/abstract_mem.hh"
#include "mem/port.hh"

#include <vector>

using namespace gem5;
using namespace memory;

class ScratchpadRequestPort;

/**
 * @class ScratchpadResponsePort
 * @brief ResponsePort variant with SPM ready/valid status query hooks.
 */
class ScratchpadResponsePort : public ResponsePort
{
  friend class ScratchpadRequestPort;
  private:
  public:
    ScratchpadResponsePort(const std::string& _name, SimObject* _owner,
        PortID id=InvalidPortID) : ResponsePort (_name, id) {}
  protected:
    virtual bool canAccess(Addr add, size_t len, bool read) { return true; }
    Tick recvAtomic(PacketPtr pkt) override { return 0; }
    Tick recvAtomicBackdoor(
            PacketPtr pkt, MemBackdoorPtr &_backdoor) override { return 0; }
    void recvFunctional(PacketPtr pkt) override { }
    bool recvTimingReq(PacketPtr pkt) override { return false; }
    void recvRespRetry() override { }
    AddrRangeList getAddrRanges() const override {
        AddrRangeList range;
        return range;
    }
    virtual void setReadyStatus(bool r) { }
};

/**
 * @class ScratchpadRequestPort
 * @brief RequestPort variant linking accelerator compute units to SPM ports.
 */
class ScratchpadRequestPort : public RequestPort
{
  private:
    ScratchpadResponsePort *_spmslave;
  protected:
    //
  public:
    ScratchpadRequestPort(const std::string& _name, SimObject* _owner,
        PortID id=InvalidPortID) : RequestPort(_name, id) {}
    /**
     * @brief Set the ready flag across SPM banks.
     * @param r Boolean ready state.
     */
    void setReadyStatus(bool r) { _spmslave->setReadyStatus(r); }
    /**
     * @brief Check whether an address range is ready for access.
     * @param add Target start address.
     * @param len Access length in bytes.
     * @param read True if read, false if write.
     * @return True if accessible, false if blocked.
     */
    bool canAccess(Addr add, size_t len, bool read) { return _spmslave->canAccess(add, len, read); }
    void bind(Port &peer) override {
        auto *spmslave = dynamic_cast<ScratchpadResponsePort *>(&peer);
        if (spmslave) {
            _spmslave = spmslave;
        }
        RequestPort::bind(peer);
    }
    void unbind() override {
        _spmslave = nullptr;
        RequestPort::unbind();
    }
};

#include "params/ScratchpadMemory.hh"

/**
 * @class ScratchpadMemory
 * @brief Multi-banked on-chip scratchpad memory SimObject.
 *
 * Implements an on-chip SRAM block with multiple access ports (`spm_ports`),
 * variable response latency, bandwidth regulation, and a serialized response
 * queue
 * enforcing head-of-line blocking across ports awaiting retries.
 */
class ScratchpadMemory : public AbstractMemory
{
  protected:
    bool readyMode;
    bool readOnInvalid;
    bool writeOnValid;
    bool resetOnScratchpadRead;
    bool initial;
    bool *ready;
  public:
    // typedef ScratchpadMemoryParams Params;
    // const Params *
    // params() const
    // {
    //   return dynamic_cast<const Params *>(_params);
    // }
    PARAMS(ScratchpadMemory);
    /**
     * @brief Construct a new ScratchpadMemory object.
     * @param p SimObject configuration parameters.
     */
    ScratchpadMemory(const ScratchpadMemoryParams &p);
    /**
     * @brief Check if target address range is ready.
     * @param ad Target address.
     * @param size Size in bytes.
     * @param read True if read operation.
     * @return True if access is permitted.
     */
    bool isReady(Addr ad, size_t size, bool read);
    /**
     * @brief Core scratchpad access handler executing read/write memory
     * transactions.
     * @param pkt Memory packet.
     * @param validateAccess Whether to enforce ready bit validation.
     */
    void scratchpadAccess(PacketPtr pkt, bool validateAccess=false);
    /**
     * @brief Bulk update ready status for all memory lines.
     * @param r Target ready state.
     */
    void setAllReady(bool r);

  private:

    /**
     * @class DeferredPacket
     * @brief Queued response packet awaiting transmission time on a specific
     * origin port.
     */
    class DeferredPacket
    {

      public:

        const Tick tick;
        const PacketPtr pkt;
        const PortID origin;

        DeferredPacket(PacketPtr _pkt, Tick _tick, PortID _origin) : tick(_tick), pkt(_pkt), origin(_origin)
        { }
    };

    /**
     * @class MemoryPort
     * @brief ResponsePort connecting scratchpad to system memory crossbar.
     */
    class MemoryPort : public ResponsePort
    {
      private:
        ScratchpadMemory& memory;

      public:
        MemoryPort(const std::string& _name, ScratchpadMemory& _memory);

      protected:
        Tick recvAtomic(PacketPtr pkt) override;
        Tick recvAtomicBackdoor(
                PacketPtr pkt, MemBackdoorPtr &_backdoor) override;
        void recvFunctional(PacketPtr pkt) override;
        bool recvTimingReq(PacketPtr pkt) override;
        void recvRespRetry() override;
        AddrRangeList getAddrRanges() const override;
    };

    MemoryPort port;

    /**
     * @class SPMPort
     * @brief Dedicated accelerator access port supporting ready/valid
     * handshaking.
     */
    class SPMPort : public ScratchpadResponsePort
    {
      private:
        ScratchpadMemory * memory;
      public:
        SPMPort(const std::string& _name, ScratchpadMemory * _memory, PortID id=InvalidPortID) :
            ScratchpadResponsePort(_name, _memory, id), memory(_memory) {}
      protected:
        bool canAccess(Addr add, size_t len, bool read) override { return memory->isReady(add, len, read); }
        Tick recvAtomic(PacketPtr pkt) override { return memory->recvAtomic(pkt, true); };
        Tick recvAtomicBackdoor(
                PacketPtr pkt, MemBackdoorPtr &_backdoor) override { return memory->recvAtomicBackdoor(pkt,_backdoor); };
        void recvFunctional(PacketPtr pkt) override { memory->recvFunctional(pkt); };
        bool recvTimingReq(PacketPtr pkt) override { return memory->recvTimingReq(pkt, id, true); };
        void recvRespRetry() override { memory->recvRespRetry(id); };
        AddrRangeList getAddrRanges() const override {
            AddrRangeList ranges;
            ranges.push_back(memory->getAddrRange());
            return ranges;
        }
        void setReadyStatus(bool r) override { memory->setAllReady(r); }
    };

    std::vector<SPMPort *> spm_ports;

    /**
     * Latency from that a request is accepted until the response is
     * ready to be sent.
     */
    const Tick latency;

    /**
     * Fudge factor added to the latency.
     */
    const Tick latency_var;

    mutable Random::RandomPtr rng = Random::genRandom();

    /**
     * Internal (unbounded) storage to mimic the delay caused by the
     * actual memory access. Note that this is where the packet spends
     * the memory latency.
     */
    std::list<DeferredPacket> packetQueue;

    /**
     * Bandwidth in ticks per byte. The regulation affects the
     * acceptance rate of requests and the queueing takes place after
     * the regulation.
     */
    const double bandwidth;

    /**
     * Track the state of the memory as either idle or busy, no need
     * for an enum with only two states.
     */
    std::vector<bool> isBusy;

    /**
     * Remember if we have to retry an outstanding request that
     * arrived while we were busy.
     */
    std::vector<bool> retryReq;

    /**
     * Remember if we failed to send a response and are awaiting a
     * retry. This is only used as a check.
     */
    std::vector<bool> retryResp;

    /**
     * Release the memory after being busy and send a retry if a
     * request was rejected in the meanwhile.
     */
    void release();

    std::vector<EventFunctionWrapper> releaseEvent;
    std::vector<Tick> releaseTick;

    /**
     * Dequeue a packet from our internal packet queue and move it to
     * the port where it will be sent as soon as possible.
     */
    void dequeue();
    void scheduleNextResponse();
    bool responseInProgress = false;

    // std::vector<EventFunctionWrapper> dequeueEvent;
    EventFunctionWrapper dequeueEvent;
    // std::vector<Tick> dequeueTick;

    /**
     * @brief Compute the total response latency for a packet access.
     * @return Computed latency in ticks.
     */
    Tick getLatency() const;

    /**
     * Upstream caches need this packet until true is returned, so
     * hold it for deletion until a subsequent call
     */
    std::unique_ptr<Packet> pendingDelete;

  public:
    DrainState drain() override;

    Port &getPort(const std::string &if_name,
                  PortID idx=InvalidPortID) override;
    void init() override;

  protected:
    Tick recvAtomic(PacketPtr pkt, bool validateAccess=false);
    Tick recvAtomicBackdoor(PacketPtr pkt, MemBackdoorPtr &_backdoor);
    void recvFunctional(PacketPtr pkt);
    bool recvTimingReq(PacketPtr pkt, PortID recvPort, bool validateAccess=false);
    void recvRespRetry(PortID id);
};

#endif //__HWACC_SCRATCHPAD_MEMORY_HH__
