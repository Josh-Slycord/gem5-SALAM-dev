#include "hwacc/stream_buffer.hh"
#include "debug/StreamBuffer.hh"

#include "sim/system.hh"
#include "mem/packet_access.hh"
#include "debug/AddrRanges.hh"
#include <cstring>

using namespace std;

StreamBuffer::TransferStats::TransferStats(statistics::Group *parent)
    : statistics::Group(parent),
      ADD_STAT(reads, statistics::units::Count::get(),
               "Stream read requests completed"),
      ADD_STAT(writes, statistics::units::Count::get(),
               "Stream write requests completed"),
      ADD_STAT(bytesRead, statistics::units::Byte::get(),
               "Bytes read from the stream buffer"),
      ADD_STAT(bytesWritten, statistics::units::Byte::get(),
               "Bytes written to the stream buffer"),
      ADD_STAT(statusReads, statistics::units::Count::get(),
               "Status register reads completed")
{}

StreamBuffer::StreamBuffer(const StreamBufferParams &p) :
    ClockedObject(p),
    streamIn(this, "stream_in"),
    streamOut(this, "stream_out"),
    statusIn(this),
    statusOut(this),
    buffer(p.buffer_size),
    fifoSize(p.buffer_size),
    endian(p.system->getGuestByteOrder()),
    streamAddr(p.stream_address),
    streamSize(p.stream_size),
    statusAddr(p.status_address),
    statusSize(p.status_size),
    streamDelay(p.stream_latency),
    bandwidth(p.bandwidth),
    transferStats(this) {}

bool
StreamBuffer::canReadStream(size_t len) {
    if (buffer.size() >= len) {
        return true;
    } else {
        return false;
    }
}

bool
StreamBuffer::canWriteStream(size_t len) {
    if ((buffer.size()+len) <= fifoSize) {
        return true;
    } else {
        return false;
    }
}

bool
StreamBuffer::tryReadStream(uint8_t *dst, size_t len) {
    if (buffer.size() >= len) {
        buffer.read(dst, len);
        return true;
    } else {
        return false;
    }
}

bool
StreamBuffer::tryWriteStream(uint8_t *src, size_t len)
{
    if ((buffer.size()+len) <= fifoSize) {
        buffer.write(src, len);
        return true;
    } else {
        return false;
    }
}

void
StreamBuffer::readStream(uint8_t *dst, size_t len) {
    const bool success(tryReadStream(dst, len));
    panic_if(!success, "Buffer underrun in StreamBuffer::readStream()\n");
}

void
StreamBuffer::writeStream(uint8_t *src, size_t len) {
    const bool success(tryWriteStream(src, len));
    panic_if(!success, "Buffer overrun in StreamBuffer::writeStream()\n");
}

bool StreamBuffer::tvalid(PacketPtr pkt) {
    return tvalid(pkt->getSize(), pkt->isRead());
}

bool StreamBuffer::tvalid(size_t len, bool isRead) {
    return isRead ? canReadStream(len) : canWriteStream(len);
}

Tick
StreamBuffer::streamRead(PacketPtr pkt) {
    DPRINTF(StreamBuffer, "A read request of size %d was received by this stream buffer\n", pkt->getSize());
    transferStats.reads++;
    transferStats.bytesRead += pkt->getSize();
    uint8_t *buff = new uint8_t[pkt->getSize()];
    readStream(buff, pkt->getSize());
    uint64_t data = 0;
    std::memcpy(&data, buff, pkt->getSize());
    delete[] buff;

    switch(pkt->getSize()) {
      case 1:
        pkt->set<uint8_t>(data, endian);
        break;
      case 2:
        pkt->set<uint16_t>(data, endian);
        break;
      case 4:
        pkt->set<uint32_t>(data, endian);
        break;
      case 8:
        pkt->set<uint64_t>(data, endian);
        break;
      default:
        panic("Read size too big?\n");
        break;
    }
    Tick duration = pkt->getSize() * bandwidth;
    pkt->makeAtomicResponse();
    return duration;
}

Tick
StreamBuffer::streamWrite(PacketPtr pkt) {
    DPRINTF(StreamBuffer, "A write request of size %d was received by this stream buffer\n", pkt->getSize());
    transferStats.writes++;
    transferStats.bytesWritten += pkt->getSize();
    uint8_t * data = new uint8_t[pkt->getSize()];
    pkt->writeData(data);
    writeStream(data, pkt->getSize());
    delete[] data;
    pkt->makeAtomicResponse();
    return streamDelay;
}

Tick
StreamBuffer::status(PacketPtr pkt, bool readStatus) {
    // Provide a means of reading the current buffer capacity of the stream
    // Writes to this register do nothing
    if (pkt->isRead()) {
        transferStats.statusReads++;
        DPRINTF(StreamBuffer, "The status of the buffer has been read. Current capacity is %d of %d bytes\n",
                buffer.size(), fifoSize);
        uint64_t data = buffer.size();
        switch(pkt->getSize()) {
            case 1:
                pkt->set<uint8_t>(data, endian);
                break;
            case 2:
                pkt->set<uint16_t>(data, endian);
                break;
            case 4:
                pkt->set<uint32_t>(data, endian);
                break;
            case 8:
                pkt->set<uint64_t>(data, endian);
                break;
            default:
                panic("Read size too big?\n");
                break;
        }
    }
    Tick duration = pkt->getSize() * bandwidth;
    pkt->makeAtomicResponse();
    return duration;
}

AddrRangeList
StreamBuffer::getStreamAddrRanges() const {
    assert(streamSize != 0);
    AddrRangeList streamRanges;
    DPRINTF(AddrRanges, "registering range: %#x-%#x\n", streamAddr, streamSize);
    streamRanges.push_back(RangeSize(streamAddr, streamSize));
    return streamRanges;
}

AddrRangeList
StreamBuffer::getStatusAddrRanges() const {
    assert(statusSize != 0);
    AddrRangeList statusRanges;
    DPRINTF(AddrRanges, "registering range: %#x-%#x\n", statusAddr, statusSize);
    statusRanges.push_back(RangeSize(statusAddr, statusSize));
    return statusRanges;
}

Port &
StreamBuffer::getPort(const std::string &if_name, PortID idx)
{
    if (if_name == "stream_in") {
        return streamIn;
    } else if (if_name == "stream_out") {
        return streamOut;
    } else if (if_name == "status_in") {
        return statusIn;
    } else if (if_name == "status_out") {
        return statusOut;
    }
    return ClockedObject::getPort(if_name, idx);
}

void
StreamBuffer::serialize(CheckpointOut &cp) const {
    SERIALIZE_CONTAINER(buffer);
}

void
StreamBuffer::unserialize(CheckpointIn &cp) {
    UNSERIALIZE_CONTAINER(buffer);
}

// StreamBuffer *
// StreamBufferParams::create() {
// 	return new StreamBuffer(this);
// }