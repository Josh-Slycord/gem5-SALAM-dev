#ifndef __HWACC_STREAM_BUFFER_HH__
#define __HWACC_STREAM_BUFFER_HH__

/**
 * @file
 * @brief Streaming FIFO buffer device connecting streaming producers and
 * consumers.
 */

#include "params/StreamBuffer.hh"
// #include "dev/io_device.hh"
#include "base/circlebuf.hh"
#include "sim/clocked_object.hh"
#include "hwacc/stream_port.hh"

/**
 * @brief Clocked streaming buffer implementing FIFO queuing and flow control.
 */
class StreamBuffer : public ClockedObject {
  private:
    StreamResponsePortT<StreamBuffer> streamIn;
    StreamResponsePortT<StreamBuffer> streamOut;
    StatusPort<StreamBuffer> statusIn;
    StatusPort<StreamBuffer> statusOut;
    Fifo<uint8_t> buffer;
    size_t const fifoSize;
    ByteOrder endian;
    Addr streamAddr;
    Addr streamSize;
  Addr statusAddr;
  Addr statusSize;
    Tick streamDelay;
    const double bandwidth;

    /**
     * @brief gem5 statistics group tracking streaming FIFO traffic.
     */
    struct TransferStats : public statistics::Group
    {
        TransferStats(statistics::Group *parent);

        statistics::Scalar reads;
        statistics::Scalar writes;
        statistics::Scalar bytesRead;
        statistics::Scalar bytesWritten;
        statistics::Scalar statusReads;
    };
    TransferStats transferStats;

  public:
    // typedef StreamBufferParams Params;
    // const Params *
    // params() const
    // {
    //   return dynamic_cast<const Params *>(_params);
    // }
  PARAMS(StreamBuffer);
    /**
     * @brief Constructs a StreamBuffer SimObject.
     * @param p Configuration parameters.
     */
    StreamBuffer(const StreamBufferParams &p);

    /**
     * @brief Returns the current number of bytes queued in the FIFO.
     */
    size_t size() const { return buffer.size(); }
    /**
     * @brief Clears all queued bytes from the internal FIFO buffer.
     */
    void flush() { buffer.flush(); }
    /**
     * @brief Checks if at least len bytes are available to read.
     */
    bool canReadStream(size_t len);
    /**
     * @brief Checks if at least len bytes of free space exist to write.
     */
    bool canWriteStream(size_t len);
    /**
     * @brief Reads len bytes from the stream FIFO into dst.
     */
    void readStream(uint8_t *dst, size_t len);
    /**
     * @brief Writes len bytes from src into the stream FIFO.
     */
    void writeStream(uint8_t *src, size_t len);
    /**
     * @brief Reads len bytes if available; returns false otherwise.
     */
    bool tryReadStream(uint8_t *dst, size_t len);
    /**
     * @brief Writes len bytes if capacity permits; returns false
     * otherwise.
     */
    bool tryWriteStream(uint8_t *src, size_t len);

    bool tvalid(PacketPtr pkt);
    bool tvalid(size_t len, bool isRead);

    /**
     * @brief Services a stream read packet from the output port.
     */
    virtual Tick streamRead(PacketPtr pkt);
    /**
     * @brief Services a stream write packet from the input port.
     */
    virtual Tick streamWrite(PacketPtr pkt);
  /**
   * @brief Services a stream status query packet.
   */
  Tick status(PacketPtr pkt, bool readStatus);

    AddrRangeList getStreamAddrRanges() const;
  AddrRangeList getStatusAddrRanges() const;

    /**
     * @brief Resolves stream and status port bindings by name.
     */
    Port &getPort(const std::string &if_name,
            PortID idx=InvalidPortID) override;

    /**
     * @brief Serializes FIFO state to a gem5 checkpoint.
     */
    void serialize(CheckpointOut &cp) const override;
    /**
     * @brief Restores FIFO state from a gem5 checkpoint.
     */
    void unserialize(CheckpointIn & cp) override;
    double getBandwidth(){ return bandwidth; };
};

#endif // __HWACC_STREAM_BUFFER_HH__
