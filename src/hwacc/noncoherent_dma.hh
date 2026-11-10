#ifndef __HWACC_NONCOHERENT_DMA_HH__
#define __HWACC_NONCOHERENT_DMA_HH__

/**
 * @file
 * @brief Non-coherent Direct Memory Access (DMA) engine for accelerator data
 * staging.
 */
//------------------------------------------//
#include "base/statistics.hh"
#include "dev/arm/base_gic.hh"
#include "dev/dma_device.hh"
#include "hwacc/LLVMRead/src/debug_flags.hh"
#include "hwacc/dma_write_fifo.hh"
#include "mem/packet.hh"
#include "mem/packet_access.hh"
#include "params/NoncoherentDma.hh"

//------------------------------------------
//    Memory Map
//    |  Length  | Dst Addr | Src Addr | Flags  |
//    |----------|----------|----------|--------|
//    |  4 Bytes | 8 Bytes  | 8 Bytes  | 1 Byte |
//------------------------------------------//

/**
 * @brief DMA controller managing read and write FIFOs between host and
 * accelerator.
 */
class NoncoherentDma : public DmaDevice
{
  private:
    static constexpr uint8_t DmaFlagStart = 0x01;
    static constexpr uint8_t DmaFlagRunning = 0x02;
    static constexpr uint8_t DmaFlagDone = 0x04;
    static constexpr uint8_t DmaClearStartMask = 0xfe;
    static constexpr uint8_t DmaClearRunningMask = 0xfd;

    std::string devname;
    DmaReadFifo *memSideReadFifo;
    DmaReadFifo *accSideReadFifo;
    DmaReadFifo *readFifo;
    DmaWriteFifo *memSideWriteFifo;
    DmaWriteFifo *accSideWriteFifo;
    DmaWriteFifo *writeFifo;
    Addr pioAddr;
    Addr pioDelay;
    Addr pioSize;
    size_t bufferSize;
    unsigned maxPending;
    unsigned maxReqSize;
    BaseGic * gic;
    uint32_t intNum;
    Cycles processCycles;

    uint8_t * mmreg;
    uint8_t * FLAGS;
    uint64_t * SRC;
    uint64_t * DST;
    int * LEN;

    uint8_t last_flag;

    Addr activeSrc;
    Addr activeDst;
    int writesLeft;
    bool running;

    Tick start_time;

    EventFunctionWrapper tickEvent;

    /**
     * @brief gem5 statistics group tracking DMA transfers and beats.
     */
    struct DmaStats : public statistics::Group
    {
        DmaStats(statistics::Group *parent);

        statistics::Scalar transfers;
        statistics::Scalar bytes;
        statistics::Scalar beats;
        statistics::Scalar writePackets;
        statistics::Average active;
    };
    DmaStats dmaStats;

  protected:
    DmaPort accPort;
    DmaReadFifo * getActiveReadFifo();
    DmaWriteFifo * getActiveWriteFifo();
  public:
    PARAMS(NoncoherentDma);
    /**
     * @brief Constructs a NoncoherentDma engine.
     * @param p Configuration parameters.
     */
    NoncoherentDma(const NoncoherentDmaParams &p);
    ~NoncoherentDma() {}

    /**
     * @brief Returns the MMIO address range of the DMA controller.
     * @return List of PIO address ranges.
     */
    AddrRangeList getAddrRanges() const;

    /**
     * @brief Advances active DMA read and write FIFO transfers.
     */
    void tick();

    /**
     * @brief Handles MMIO status/configuration reads.
     * @param pkt Incoming read packet.
     * @return PIO access delay in ticks.
     */
    Tick read(PacketPtr pkt);
    /**
     * @brief Handles MMIO control/address writes and initiates DMA.
     * @param pkt Incoming write packet.
     * @return PIO access delay in ticks.
     */
    Tick write(PacketPtr pkt);

    /**
     * @brief Resolves DMA and PIO port bindings by name.
     * @param if_name Port interface name.
     * @param idx Port index.
     * @return Reference to bound Port.
     */
    Port &getPort(const std::string &if_name,
                  PortID idx=InvalidPortID) override;
};

#endif //_HWACC_NONCOHERENT_DMA_HH__
