#ifndef MEMORY_REQUEST_HH
#define MEMORY_REQUEST_HH

/**
 * @file
 * @brief Declares the MemoryRequest descriptor for staging accelerator memory
 * transactions.
 *
 * Tracks split read/write sub-requests, buffer storage, byte completion,
 * and port binding for multi-byte memory operations initiated by SALAM compute
 * units and communication interfaces.
 */

//------------------------------------------//
#include "mem/packet.hh"
#include "mem/port.hh"
#include "debug_flags.hh"
//------------------------------------------//

using namespace gem5;

/**
 * @brief Memory request descriptor managing multi-word transfers.
 *
 * Coordinates DMA and memory accesses across ScratchpadMemory, RegisterBank,
 * or host memory. Tracks remaining bytes to read/write, progress flags,
 * payload buffer, and carrier RequestPort.
 */
class MemoryRequest {
  friend class CommInterface;
  // friend class LLVMInterface;
  private:
    Addr address;
    size_t length;
    bool needToRead;
    bool needToWrite;
    Addr currentReadAddr;
    Addr currentWriteAddr;
    Addr beginAddr;
    Tick writeLeft;
    Tick writeDone;
    Tick readLeft;
    Tick readDone;
    Tick totalLength;

    uint8_t *buffer;
    bool *readsDone;

    PacketPtr pkt;
    RequestPort * port;
  public:
    /**
     * @brief Constructs a read memory request for the specified address and
     * length.
     *
     * @param add Base memory address.
     * @param len Total length of transfer in bytes.
     */
    MemoryRequest(Addr add, size_t len);

    /**
     * @brief Constructs a write memory request with payload data.
     *
     * @param add Base memory address.
     * @param data Pointer to source data buffer.
     * @param len Total length of transfer in bytes.
     */
    MemoryRequest(Addr add, const void *data, size_t len);

    /**
     * @brief Destructor for MemoryRequest, frees allocated buffers and status
     * arrays.
     */
    ~MemoryRequest() {
        delete[] readsDone;
        delete[] buffer;
        // if (pkt) delete pkt;
    }

    /**
     * @brief Binds the carrier RequestPort used to dispatch packets for this
     * request.
     *
     * @param _port Pointer to carrier gem5 RequestPort.
     */
    void setCarrierPort(RequestPort * _port) { port = _port; }

    /**
     * @brief Returns the carrier RequestPort for this request.
     *
     * @return Pointer to RequestPort.
     */
    RequestPort * getCarrierPort() { return port; }

    /**
     * @brief Returns the internal payload data buffer.
     *
     * @return Pointer to byte buffer.
     */
    uint8_t * getBuffer() { return buffer; }

    /**
     * @brief Returns the base memory address of the request.
     *
     * @return Base Addr.
     */
    Addr getAddress() { return address; }

    /**
     * @brief Generates a hex-formatted string of buffer contents for
     * debugging.
     *
     * @return Formatted string of buffer bytes.
     */
    std::string printBuffer();
};

#endif //__MEM_REQUEST_HH__
