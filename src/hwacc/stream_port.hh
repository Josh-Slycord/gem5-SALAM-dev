#ifndef __HWACC_STREAM_PORT_HH__
#define __HWACC_STREAM_PORT_HH__

/**
 * @file
 * @brief Declares streaming port interfaces modeling AXI-Stream flow control
 * in
 * SALAM.
 *
 * Provides StreamRequestPort and StreamResponsePort (templated
 * StreamResponsePortT)
 * implementing valid/ready handshaking, stall accounting, retry notifications,
 * and bandwidth-modeled transfer durations.
 */

#include "base/statistics.hh"
#include "mem/port.hh"
#include "mem/tport.hh"

using namespace gem5;

/** Forward declaration **/
class StreamRequestPort;

/**
 * @brief Base response port for streaming data transfers.
 *
 * Specialization of SimpleTimingPort enabling master/slave streaming semantics
 * similar to the AXI-Stream specification. Collects timing statistics for
 * requests, payload bytes, backpressure stalls, and retries.
 */
class StreamResponsePort : public SimpleTimingPort {
  friend class StreamRequestPort;
  private:
  protected:
    /**
     * @brief Statistics group for streaming port activity.
     */
    struct StreamStats : public statistics::Group
    {
        StreamStats(statistics::Group *parent, const std::string &port_name)
            : statistics::Group(parent, port_name.c_str()),
              ADD_STAT(requests, statistics::units::Count::get(),
                       "Stream timing requests accepted"),
              ADD_STAT(bytes, statistics::units::Byte::get(),
                       "Stream payload bytes accepted"),
              ADD_STAT(tvalidStalls, statistics::units::Count::get(),
                       "Requests rejected because stream data/space was not valid"),
              ADD_STAT(busyStalls, statistics::units::Count::get(),
                       "Requests rejected while the stream port was busy"),
              ADD_STAT(retries, statistics::units::Count::get(),
                       "Retry notifications sent after stream busy periods")
        {}

        statistics::Scalar requests;
        statistics::Scalar bytes;
        statistics::Scalar tvalidStalls;
        statistics::Scalar busyStalls;
        statistics::Scalar retries;
    };
    StreamStats streamStats;

    /**
     * @brief Evaluates whether a packet transfer is valid.
     *
     * @param pkt Pointer to gem5 packet.
     * @return True if port can service the packet.
     */
    virtual bool tvalid(PacketPtr pkt) = 0;

    /**
     * @brief Evaluates whether a transfer of given length is valid.
     *
     * @param len Transfer length in bytes.
     * @param isRead True if read request, false if write.
     * @return True if port can accept transfer.
     */
    virtual bool tvalid(size_t len, bool isRead) = 0;

    Tick recvAtomic(PacketPtr pkt) override {
      Tick t = 0;
      return t;
    }
    AddrRangeList getAddrRanges() const override {
      AddrRangeList range;
      return range;
    }
  public:
    /**
     * @brief Constructs a StreamResponsePort.
     *
     * @param name Name of the port.
     * @param owner Pointer to owning SimObject.
     * @param stat_name Sub-group name for statistics.
     */
    StreamResponsePort(const std::string& name, SimObject* owner,
                       const std::string &stat_name="stream") :
      SimpleTimingPort(name, owner), streamStats(owner, stat_name) {}
};

/**
 * @brief Templated StreamResponsePort connecting a specific device.
 *
 * Implements flow control, transfer duration calculation based on device
 * bandwidth, and retry notifications.
 */
template <class Device>
class StreamResponsePortT : public StreamResponsePort
{
  friend class StreamRequestPort;

  private:
    bool isBusy;
    bool retryReq;

    EventFunctionWrapper releaseEvent;

    void
    release() {
        assert(isBusy);
        isBusy = false;
        if (retryReq) {
            retryReq = false;
            streamStats.retries++;
            sendRetryReq();
        }
    }

  protected:
    Device *device;

    virtual bool tvalid(PacketPtr pkt) { return device->tvalid(pkt); }
    virtual bool tvalid(size_t len, bool isRead) { return device->tvalid(len, isRead); }

    bool
    recvTimingReq(PacketPtr pkt) override {
        // we should not get a new request after committing to retry the
        // current one, but unfortunately the CPU violates this rule, so
        // simply ignore it for now
        if (retryReq) {
          streamStats.busyStalls++;
          return false;
        }
        // if we are busy with a read or write, remember that we have to
        // retry
        if (isBusy) {
          retryReq = true;
          streamStats.busyStalls++;
          return false;
        }
        // Make sure that the transfer is valid
        if(!tvalid(pkt)) {
          streamStats.tvalidStalls++;
          return false;
        }
        streamStats.requests++;
        streamStats.bytes += pkt->getSize();
        // the SimpleTimingPort should not be used anywhere where there is
        // a need to deal with snoop responses and their flow control
        // requirements
        if (pkt->cacheResponding())
            panic("SimpleTimingPort should never see packets with the "
                  "cacheResponding flag set\n");

        Tick duration = pkt->getSize() * device->getBandwidth();

        if (duration != 0) {
            device->schedule(releaseEvent, curTick() + duration);
            isBusy = true;
        }

        bool needsResponse = pkt->needsResponse();

        Tick latency = recvAtomic(pkt);

        // turn packet around to go back to requester if response expected
        if (needsResponse) {
            // recvAtomic() should already have turned packet into
            // atomic response
            assert(pkt->isResponse());
            schedTimingResp(pkt, curTick() + latency);
        } else {
            // queue the packet for deletion
            pendingDelete.reset(pkt);
        }
        return true;
    }

    Tick recvAtomic(PacketPtr pkt) override {
      Tick receive_delay = pkt->headerDelay + pkt->payloadDelay;
      pkt->headerDelay = pkt->payloadDelay = 0;
      const Tick delay =
        pkt->isRead() ? device->streamRead(pkt) : device->streamWrite(pkt);
      assert(pkt->isResponse() || pkt->isError());
      return delay + receive_delay;
    }

    AddrRangeList getAddrRanges() const override {
      return device->getStreamAddrRanges();
    }

  public:
    /**
     * @brief Constructs a StreamResponsePortT for a specific device.
     *
     * @param dev Pointer to device.
     * @param port_suffix Name suffix for the port.
     */
    StreamResponsePortT(Device *dev, const std::string &port_suffix="stream") :
      StreamResponsePort(dev->name() + "." + port_suffix, dev, port_suffix),
      isBusy(false),
      retryReq(false),
      releaseEvent([this]{ release(); }, dev->name() + "." + port_suffix),
      device(dev) {}
      virtual ~StreamResponsePortT() {}
};

/**
 * @brief Specialization of RequestPort for stream masters.
 *
 * Checks the valid/ready signal on a connected StreamResponsePort before
 * initiating a transfer.
 */
class StreamRequestPort : public RequestPort {
  private:
    StreamResponsePort *_stream_slave;

  protected:
    //
  public:
    /**
     * @brief Constructs a StreamRequestPort.
     *
     * @param name Port name.
     * @param _owner Pointer to owning SimObject.
     * @param id Port identifier.
     */
    StreamRequestPort(const std::string& name, SimObject* _owner,
                 PortID id=InvalidPortID);
    virtual ~StreamRequestPort();

    /**
     * @brief Bind this master port to a slave port.
     *
     * Binds the slave port to this master port and caches the stream response
     * port reference if the peer is a StreamResponsePort.
     *
     * @param peer Reference to peer port.
     */
    void bind(Port &peer) override;

    /**
     * @brief Unbind this master port and the associated slave port.
     */
    void unbind() override;

    /**
     * @brief Checks if connected stream slave port can service the packet.
     *
     * @param pkt Packet to check.
     * @return True if stream slave is valid, true if not connected to stream.
     */
    bool streamValid(PacketPtr pkt) {
      if (_stream_slave)
        return _stream_slave->tvalid(pkt);
      return true;
    }

    /**
     * @brief Checks if connected stream slave can service a transfer of length
     * len.
     *
     * @param len Transfer length in bytes.
     * @param isRead True if read request.
     * @return True if valid.
     */
    bool streamValid(size_t len, bool isRead) {
      if (_stream_slave)
        return _stream_slave->tvalid(len, isRead);
      return true;
    }
};

/**
 * @brief Status monitoring port for stream devices.
 */
template <class Device>
class StatusPort : public SimpleTimingPort
{
  protected:
  Device * device;
  bool read; // Port reads from the stream

  Tick
    recvAtomic(PacketPtr pkt) override
    {
        // Technically the packet only reaches us after the header delay,
        // and typically we also need to deserialise any payload.
        Tick receive_delay = pkt->headerDelay + pkt->payloadDelay;
        pkt->headerDelay = pkt->payloadDelay = 0;

        const Tick delay = device->status(pkt, read);
        assert(pkt->isResponse() || pkt->isError());
        return delay + receive_delay;
    }

    AddrRangeList
    getAddrRanges() const override
    {
        return device->getStatusAddrRanges();
    }

  public:
    StatusPort(Device *dev, bool _read=true) :
        SimpleTimingPort(dev->name() + ".status", dev), device(dev), read(_read)
    {}
};

#endif //__HWACC_STREAM_PORT_HH__
