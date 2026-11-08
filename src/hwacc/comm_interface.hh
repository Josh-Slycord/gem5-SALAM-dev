#ifndef __HWACC_COMM_INTERFACE_HH__
#define __HWACC_COMM_INTERFACE_HH__

/**
 * @file comm_interface.hh
 * @brief Memory-mapped communication and control interface for gem5-SALAM
 * accelerators.
 *
 * CommInterface connects host CPUs to hardware accelerators via memory-mapped
 * I/O (MMIO).
 * It implements the accelerator control registers (start, busy, done),
 * interrupt generation
 * (via ARM GIC), memory request routing across local, global, scratchpad, and
 * register ports,
 * and computation orchestration with attached ComputeUnit instances.
 */

#include "params/CommInterface.hh"
#include "base/statistics.hh"
#include "dev/io_device.hh"
#include "dev/arm/base_gic.hh"
#include "hwacc/compute_unit.hh"
#include "hwacc/LLVMRead/src/mem_request.hh"
#include "hwacc/stream_port.hh"
#include "hwacc/scratchpad_memory.hh"
#include "hwacc/LLVMRead/src/debug_flags.hh"

#include <list>
#include <queue>
#include <vector>

class SalamLifecycleTester;

/**
 * @class CommInterface
 * @brief PIO device providing the memory-mapped register interface and memory
 * gateway.
 *
 * Acts as the primary control gateway for a SALAM accelerator cluster. The
 * host CPU initiates
 * execution by writing to the memory-mapped run register. CommInterface
 * orchestrates memory
 * traffic between the compute unit (e.g. LLVMInterface) and target memory
 * spaces (scratchpads,
 * register files, cluster-local caches, or coherent system memory), signaling
 * completion via
 * MMR status flags and hardware interrupts.
 */
class CommInterface : public BasicPioDevice
{
    friend class SalamLifecycleTester;

  protected:
    static constexpr uint8_t MmrStatusRun = 0x01;
    static constexpr uint8_t MmrStatusBusy = 0x02;
    static constexpr uint8_t MmrStatusDone = 0x04;
    static constexpr uint8_t MmrClearRunMask = 0xfe;
    static constexpr uint8_t MmrClearRunBusyMask = 0xfc;

    Addr io_addr;
    Addr io_size;
    Addr flag_size;
    Addr config_size;
    Addr FLAG_OFFSET;
    Addr CONFIG_OFFSET;
    Addr VAR_OFFSET;
    std::string devname;
    BaseGic *gic;
    int32_t int_num;
    bool use_premap_data;
    std::vector<Addr> data_base_ptrs;
    ByteOrder endian;
    bool debugEnabled;

  public:
    /**
     * @brief Check whether debug tracing is enabled.
     * @return True if debug flag is active.
     */
    bool debug() { return debugEnabled; }

  protected:
    /**
     * @class MemSidePort
     * @brief Master stream port connecting CommInterface to local, global, or
     * streaming memory.
     */
    class MemSidePort : public StreamRequestPort
    {
      friend class CommInterface;

      private:
        CommInterface *owner;
        std::queue<PacketPtr> outstandingPkts;
        MemoryRequest *readReq;
        MemoryRequest *writeReq;
        bool readActive;
        bool writeActive;

      public:
        MemSidePort(const std::string& name, CommInterface *owner, PortID id=InvalidPortID) :
          StreamRequestPort(name, owner, id), owner(owner) {
          readActive = false;
          writeActive = false;
          readReq = NULL;
          writeReq = NULL;
        }
        MemoryRequest * getReadReq() { return readReq; }
        MemoryRequest * getWriteReq() { return writeReq; }
        void setReadReq(MemoryRequest * req = nullptr) { readReq = req; }
        void setWriteReq(MemoryRequest * req = nullptr) { writeReq = req; }

      protected:
        virtual bool recvTimingResp(PacketPtr pkt);
        virtual void recvReqRetry();
        virtual void recvRangeChange() { };
        virtual Tick recvAtomic(PacketPtr pkt) {return 0;}
        virtual void recvFunctional(PacketPtr pkt) { };
        void setStalled(PacketPtr pkt)
        {
          outstandingPkts.push(pkt);
        }
        bool isStalled() { return !outstandingPkts.empty(); }
        void sendPacket(PacketPtr pkt);
        bool active() { return readActive || writeActive; }
        bool reading() { return readActive; }
        bool writing() { return writeActive; }
        bool debug() { return owner->debug(); }
    };

    /**
     * @class SPMPort
     * @brief Dedicated port connecting CommInterface directly to on-chip
     * ScratchpadMemory.
     */
    class SPMPort : public ScratchpadRequestPort
    {
      friend class CommInterface;

      private:
        CommInterface *owner;
        std::queue<PacketPtr> outstandingPkts;
        MemoryRequest *readReq;
        MemoryRequest *writeReq;
        bool readActive;
        bool writeActive;

      public:
        SPMPort(const std::string& name, CommInterface *owner, PortID id=InvalidPortID) :
          ScratchpadRequestPort(name, owner, id), owner(owner) {
          readActive = false;
          writeActive = false;
          readReq = NULL;
          writeReq = NULL;
        }
        MemoryRequest * getReadReq() { return readReq; }
        MemoryRequest * getWriteReq() { return writeReq; }
        void setReadReq(MemoryRequest * req = nullptr) { readReq = req; }
        void setWriteReq(MemoryRequest * req = nullptr) { writeReq = req; }

      protected:
        virtual bool recvTimingResp(PacketPtr pkt);
        virtual void recvReqRetry();
        virtual void recvRangeChange() { };
        virtual Tick recvAtomic(PacketPtr pkt) {return 0;}
        virtual void recvFunctional(PacketPtr pkt) { };
        void setStalled(PacketPtr pkt)
        {
          outstandingPkts.push(pkt);
        }
        bool isStalled() { return !outstandingPkts.empty(); }
        void sendPacket(PacketPtr pkt);
        bool active() { return readActive || writeActive; }
        bool reading() { return readActive; }
        bool writing() { return writeActive; }
        bool debug() { return owner->debug(); }
    };

    /**
     * @class RegPort
     * @brief RequestPort connecting CommInterface to an on-chip RegisterBank.
     */
    class RegPort : public RequestPort
    {
      friend class CommInterface;

      private:
        CommInterface *owner;
        std::queue<PacketPtr> outstandingPkts;
        MemoryRequest *readReq;
        MemoryRequest *writeReq;
      public:
        RegPort(const std::string& name, CommInterface *_owner, PortID id=InvalidPortID) :
          RequestPort(name, id), owner(_owner), readReq(nullptr), writeReq(nullptr) {}
        void setReadReq(MemoryRequest * req = nullptr) { readReq = req; }
        void setWriteReq(MemoryRequest * req = nullptr) { writeReq = req; }
      protected:
        virtual bool recvTimingResp(PacketPtr pkt);
        virtual void recvReqRetry();
        virtual void recvRangeChange() { };
        virtual Tick recvAtomic(PacketPtr pkt) {return 0;}
        virtual void recvFunctional(PacketPtr pkt) { };
        bool sendPacket(PacketPtr pkt);
        bool debug() { return owner->debug(); }
    };

    /**
     * @class TickEvent
     * @brief Event driver scheduling periodic queue processing and MMIO
     * polling.
     */
    class TickEvent : public Event
    {
      private:
        CommInterface *comm;

      public:
        TickEvent(CommInterface *_comm) :
            Event(CPU_Tick_Pri - 1), comm(_comm)
        {}
        void process() { comm->tick(); }
        virtual const char *description() const { return "CommInterface tick"; }
        bool debug() { return comm->debug(); }
    };

    /**
     * @struct CommStats
     * @brief Statistics group tracking communication requests, byte transfers,
     * and responses.
     */
    struct CommStats : public statistics::Group
    {
        CommStats(statistics::Group *parent);

        statistics::Scalar starts;
        statistics::Scalar finishes;
        statistics::Vector requests;
        statistics::Vector attempts;
        statistics::Vector accepted;
        statistics::Vector responses;
        statistics::Vector bytes;
    };
    CommStats commStats;

    std::list<MemoryRequest*> readQueue;
    std::list<MemoryRequest*> writeQueue;
    std::list<MemoryRequest*> accRdQ;
    std::list<MemoryRequest*> accWrQ;

    int requestsInQueues;

    std::vector<MemSidePort*> localPorts;
    std::vector<MemSidePort*> globalPorts;
    std::vector<MemSidePort*> streamPorts;
    std::vector<SPMPort*>     spmPorts;
    std::vector<RegPort*>     regPorts;

    bool localPortsStalled() {
        for (auto it=localPorts.begin(); it!=localPorts.end(); ++it) {
            if (!((*it)->isStalled())) return false;
        }
        return true;
    }
    bool globalPortsStalled() {
        for (auto it=globalPorts.begin(); it!=globalPorts.end(); ++it) {
            if (!((*it)->isStalled())) return false;
        }
        return true;
    }
    bool streamPortsStalled() {
        for (auto it=streamPorts.begin(); it!=streamPorts.end(); ++it) {
            if (!((*it)->isStalled())) return false;
        }
        return true;
    }
    bool spmPortsStalled() {
        for (auto port : spmPorts) {
            if (!(port->isStalled())) return false;
        }
        return true;
    }
    bool allPortsStalled() {
        return localPortsStalled() && globalPortsStalled() && streamPortsStalled() && spmPortsStalled();
    }
    bool inStreamRange(Addr add);
    bool inSPMRange(Addr add);
    bool inRegRange(Addr add);
    bool inLocalRange(Addr add);
    bool inGlobalRange(Addr add);
    MemSidePort * getValidLocalPort(Addr add, bool read);
    MemSidePort * getValidGlobalPort(Addr add, bool read);
    MemSidePort * getValidStreamPort(Addr add, size_t len, bool read);
    SPMPort *     getValidSPMPort(Addr add, size_t len, bool read);
    RegPort *     getValidRegPort(Addr add);

    CommInterface *comm;
    RequestorID masterId;
    TickEvent tickEvent;
    unsigned cacheLineSize;

    virtual void checkMMR();
    virtual void processMemoryRequests();
    virtual void tick();

    bool running;
    bool computationNeeded;
    bool int_flag;

    void tryRead(MemSidePort * port);
    void tryWrite(MemSidePort * port);

    void tryRead(SPMPort * port);
    void tryWrite(SPMPort * port);

    void tryRead(RegPort * port);
    void tryWrite(RegPort * port);

    Addr dataAddr;

    uint8_t *mmreg;

    bool processingDone;
    Cycles processCycles;

    Tick serviceEdge() const { return clockEdge(processCycles); }

    bool reset_spm;

    ComputeUnit *cu;

  public:
    PARAMS(CommInterface);

    /**
     * @brief Construct a new CommInterface object.
     * @param p SimObject configuration parameters.
     */
    CommInterface(const CommInterfaceParams &p);

    void startup();

    /**
     * @brief Checks whether the communication interface is drained.
     *
     * Returns DrainState::Drained if no memory requests, port retries,
     * queued responses, or tick events are pending; otherwise returns
     * DrainState::Draining until tryCompleteDrain() signals completion.
     *
     * @return Current gem5 DrainState.
     */
    DrainState drain() override;

  private:
    /**
     * @brief Checks whether any ports, queues, or events have active
     * work.
     *
     * Inspects active read/write requests, port packet queues, stall
     * flags, memory-mapped registers, and scheduled tick events.
     *
     * @return True if any pending work remains prior to drain completion.
     */
    bool hasPendingWork() const;
    /**
     * @brief Signals drain completion if currently draining and no
     * pending work remains.
     */
    void tryCompleteDrain();

  public:

    /**
     * @brief Handle PIO read transaction from the host CPU into MMIO
     * registers.
     * @param pkt Memory request packet.
     * @return Access latency in ticks.
     */
    virtual Tick read(PacketPtr pkt);

    /**
     * @brief Handle PIO write transaction from the host CPU into MMIO
     * registers.
     * @param pkt Memory request packet.
     * @return Access latency in ticks.
     */
    virtual Tick write(PacketPtr pkt);

    Port& getPort(const std::string& if_name,
                                  PortID idk = InvalidPortID) override;

    /**
     * @brief Callback invoked by ports when a timing response packet returns.
     * @param pkt Completed response packet.
     */
    void recvPacket(PacketPtr pkt);

    // Addr value stored in gep register, length based on data type
    /**
     * @brief Enqueue a read request generated by a ComputeUnit instruction.
     * @param req Pointer to MemoryRequest descriptor.
     */
    void enqueueRead(MemoryRequest * req); 

    /**
     * @brief Enqueue a write request generated by a ComputeUnit instruction.
     * @param req Pointer to MemoryRequest descriptor.
     */
    void enqueueWrite(MemoryRequest * req);

    //uint8_t* getReadBuffer() { return readBuffer; }

    /**
     * @brief Query whether the accelerator is actively executing.
     * @return True if running.
     */
    bool isRunning() { return running; }
    /**
     * @brief Check whether computation needs to be triggered.
     * @return True if computation is pending.
     */
    bool isCompNeeded() { return computationNeeded; }

    /**
     * @brief Read a global input variable passed by the host in the MMR
     * aperture.
     * @param offset Byte offset within the variable section.
     * @param size Size in bytes (1, 2, 4, or 8).
     * @return Variable value as an unsigned 64-bit integer.
     */
    uint64_t getGlobalVar(unsigned offset, unsigned size);
    /**
     * @brief Get the configured processing delay in ticks.
     * @return Latency in ticks.
     */
    Tick getProcessDelay() const { return cyclesToTicks(processCycles); }
    virtual int getReadPorts()  { return 0; }
    virtual int getWritePorts()  { return 0; }
    virtual int getReadBusWidth()  { return 0; }
    virtual int getWriteBusWidth()  { return 0; }  
    virtual int getPmemRange() { return 0; }
    /**
     * @brief Register the attached ComputeUnit instance.
     * @param compunit Pointer to ComputeUnit.
     */
    void registerCompUnit(ComputeUnit *compunit) { cu = compunit; }
    /**
     * @brief Signal accelerator completion, assert interrupt, and set done
     * bit.
     */
    virtual void finish();

    MemoryRequest * findMemRequest(PacketPtr pkt, bool isRead);
    void clearMemRequest(MemoryRequest * req, bool isRead);
    virtual void refreshMemPorts() {}
    std::string getName() const { return name(); }

    virtual bool isBaseCommInterface() { return true; }
  protected:
};

#endif //__HWACC_COMM_INTERFACE_HH__

/*
* MM Register Layout
* | Location of Data 32bits | Compute Finished 1bit | Unused 30bits | Start
* Operation 1bit |
*/
