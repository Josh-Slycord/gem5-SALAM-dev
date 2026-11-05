#ifndef __HWACC_STREAM_PORT_HH__
#define __HWACC_STREAM_PORT_HH__

#include "base/statistics.hh"
#include "mem/port.hh"
#include "mem/tport.hh"

using namespace gem5;

/** Forward declaration **/
class StreamRequestPort;

/**
 * A StreamResponsePort is a specialization of a SimpleTimingPort meant to enable
 * functionality similar to the master port in the AXI-Stream specification.
 * This serves only as a base class.
 */
class StreamResponsePort : public SimpleTimingPort {
  friend class StreamRequestPort;
  private:
  protected:
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

    virtual bool tvalid(PacketPtr pkt) = 0;
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
    StreamResponsePort(const std::string& name, SimObject* owner,
                       const std::string &stat_name="stream") :
      SimpleTimingPort(name, owner), streamStats(owner, stat_name) {}
};

/**
 * Templated StreamResponsePort that functions similarly to the pio port on PioDevices.
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
    StreamResponsePortT(Device *dev, const std::string &port_suffix="stream") :
      StreamResponsePort(dev->name() + "." + port_suffix, dev, port_suffix),
      isBusy(false),
      retryReq(false),
      releaseEvent([this]{ release(); }, dev->name() + "." + port_suffix),
      device(dev) {}
      virtual ~StreamResponsePortT() {}
};

/**
 * A StreamRequestPort is a specialization of a RequestPort, meant to enable
 * functionality similar to the master port in the AXI-Stream specification.
 * A StreamRequestPort is able to check the valid signal on a corresponding
 * StreamResponsePort before initiating a transfer. Otherwise it functions like
 * a standard RequestPort.
 */
class StreamRequestPort : public RequestPort {
  private:
    StreamResponsePort *_stream_slave;

  protected:
    //
  public:
    StreamRequestPort(const std::string& name, SimObject* _owner,
                 PortID id=InvalidPortID);
    virtual ~StreamRequestPort();

    /**
     * Bind this master port to a slave port. This also does the
     * mirror action and binds the slave port to the master port.
     * If the slave port is a stream slave, also binds the tvalid
     * signal.
     */
    void bind(Port &peer) override;

    /**
     * Unbind this master port and the associated slave port.
     */
    void unbind() override;

    /**
   * If the slave port is a stream slave port, then check if it can
   * service a request of size 'len'
     */
    bool streamValid(PacketPtr pkt) {
      if (_stream_slave)
        return _stream_slave->tvalid(pkt);
      return true;
    }
    bool streamValid(size_t len, bool isRead) {
      if (_stream_slave)
        return _stream_slave->tvalid(len, isRead);
      return true;
    }
};

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