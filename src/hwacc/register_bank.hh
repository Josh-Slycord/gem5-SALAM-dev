#ifndef __HWACC_REGISTER_BANK_HH__
#define __HWACC_REGISTER_BANK_HH__

/**
 * @file register_bank.hh
 * @brief Register file storage model with delta-cycle staging for gem5-SALAM.
 *
 * RegisterBank provides high-bandwidth, cycle-isolated register storage for
 * hardware accelerators. It features delta-cycle write staging (isolating in-
 * cycle
 * updates until clock transitions) and multi-port timing response management.
 */

#include "mem/abstract_mem.hh"
#include "mem/port.hh"
#include "mem/tport.hh"

#include <vector>

using namespace gem5;
using namespace memory;

#include "params/RegisterBank.hh"

/**
 * @class RegisterBank
 * @brief Memory-backed register file SimObject with delta-cycle update
 * isolation.
 *
 * Inherits from AbstractMemory. Writes are staged to an internal buffer
 * (`deltaAddr`)
 * during an active clock cycle, preventing write-after-read hazards within the
 * same delta cycle. At cycle boundaries (`deltaEvent`), staged values commit
 * to
 * committed storage buffer (`pmemAddr`) and response packets are dispatched.
 */
class RegisterBank : public AbstractMemory
{
  public:
    PARAMS(RegisterBank);
    /**
     * @brief Construct a new RegisterBank object.
     * @param p SimObject configuration parameters.
     */
    RegisterBank(const RegisterBankParams &p);
    /**
     * @brief Direct register read/write access routine.
     * @param pkt Memory packet to process.
     */
    void registerAccess(PacketPtr pkt);

  private:
    /**
     * @class DeferredPacket
     * @brief Encapsulates a deferred response packet with its scheduled
     * delivery tick.
     */
    class DeferredPacket
    {
      public:
        const Tick tick;
        const PacketPtr pkt;

        DeferredPacket(PacketPtr _pkt, Tick _tick) : tick(_tick), pkt(_pkt)
        { }
    };

    /**
     * @class RegPort
     * @brief Primary timing/atomic ResponsePort connecting to CommInterface or
     * compute units.
     */
    class RegPort : public ResponsePort
    {
      private:
        RegisterBank * memory;
      public:
        RegPort(const std::string& _name, RegisterBank * _memory, PortID id=InvalidPortID) :
            ResponsePort(_name, id), memory(_memory) {}
      protected:
        Tick recvAtomic(PacketPtr pkt) override { return memory->recvAtomic(pkt); };
        Tick recvAtomicBackdoor(
                PacketPtr pkt, MemBackdoorPtr &_backdoor) override { return memory->recvAtomicBackdoor(pkt,_backdoor); };
        void recvFunctional(PacketPtr pkt) override { memory->recvFunctional(pkt); };
        bool recvTimingReq(PacketPtr pkt) override { return memory->recvTimingReq(pkt); };
        void recvRespRetry() override { memory->recvRespRetry(); };
        AddrRangeList getAddrRanges() const override {
            AddrRangeList ranges;
            ranges.push_back(memory->getAddrRange());
            return ranges;
        }
    };

    RegPort port;

    /**
     * @class LoadPort
     * @brief Auxiliary SimpleTimingPort for bulk loading accelerator register
     * contents.
     */
    class LoadPort : public SimpleTimingPort
    {
      private:
        RegisterBank * memory;
      protected:
        Tick recvAtomic(PacketPtr pkt) {
          memory->registerAccess(pkt);
          return memory->getDeltaTime();
        }
        AddrRangeList getAddrRanges() const override {
            AddrRangeList ranges;
            ranges.push_back(memory->getAddrRange());
            return ranges;
        }
      public:
        LoadPort(const std::string& _name, RegisterBank * _memory, PortID id=InvalidPortID) :
          SimpleTimingPort(_name, _memory), memory(_memory) {}
    };

    LoadPort load;

    /**
     * Container for register deltas. Staged writes update this buffer
     * and are committed to physical storage (`pmemAddr`) on delta events.
     */
    uint8_t* deltaAddr;
    /**
     * Latency of a delta cycle in the register bank.
     */
    const Tick deltaTime;
    /**
     * Internal FIFO of deferred packets awaiting delivery.
     */
    std::list<DeferredPacket> packetQueue;

    /**
     * Indicates whether the downstream receiver was busy and a retry is
     * awaited.
     */
    bool retryResp;

    /**
     * Dequeue a packet from the internal queue and attempt port delivery.
     */
    void dequeue();
    /**
     * Determine and schedule the next response event.
     */
    void scheduleNextResponse();
    /**
     * In-flight delivery flag preventing synchronous reentrant displacement.
     */
    bool responseInProgress = false;
    EventFunctionWrapper dequeueEvent;

    /**
     * Handle the delta cycle: commit staged delta bytes to storage and trigger
     * dequeues.
     */
    void delta();
    /**
     * @brief Signals drain completion when all register bank events and
     * response queues are quiescent.
     *
     * Verifies that deltaEvent, responseQueue, responseRetry,
     * responseInProgress, and responseEvent have all completed before
     * calling signalDrainDone().
     */
    void tryCompleteDrain();
    EventFunctionWrapper deltaEvent;

  public:
    DrainState drain() override;

    Port &getPort(const std::string &if_name,
                  PortID idx=InvalidPortID) override;
    void init() override;
    /**
     * @brief Query the configured delta-cycle time period.
     * @return Tick duration of a single delta step.
     */
    Tick getDeltaTime() { return deltaTime; }

  protected:
    Tick recvAtomic(PacketPtr pkt);
    Tick recvAtomicBackdoor(PacketPtr pkt, MemBackdoorPtr &_backdoor);
    void recvFunctional(PacketPtr pkt);
    bool recvTimingReq(PacketPtr pkt);
    void recvRespRetry();
};
#endif //__HWACC_REGISTER_BANK_HH__
