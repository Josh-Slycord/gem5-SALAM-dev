//------------------------------------------//
#include "hwacc/stream_dma.hh"
#include <algorithm>
#include <cstring>
//------------------------------------------//

StreamDma::DmaStats::DmaStats(statistics::Group *parent)
    : statistics::Group(parent),
      ADD_STAT(readStarts, statistics::units::Count::get(),
               "MM2S stream-DMA channels started"),
      ADD_STAT(writeStarts, statistics::units::Count::get(),
               "S2MM stream-DMA channels started"),
      ADD_STAT(framesRead, statistics::units::Count::get(),
               "MM2S frames filled from memory"),
      ADD_STAT(framesWritten, statistics::units::Count::get(),
               "S2MM frames drained to memory"),
      ADD_STAT(bytesRead, statistics::units::Byte::get(),
               "Bytes read by consumers from the MM2S FIFO"),
      ADD_STAT(bytesWritten, statistics::units::Byte::get(),
               "Bytes written by producers into the S2MM FIFO"),
      ADD_STAT(writePackets, statistics::units::Count::get(),
               "DMA write packets issued to memory"),
      ADD_STAT(statusReads, statistics::units::Count::get(),
               "Stream-DMA status register reads completed"),
      ADD_STAT(active, statistics::units::Ratio::get(),
               "Time-weighted active fraction over simulation ticks since native stats reset")
{
    active.flags(statistics::nozero);
}

StreamDma::StreamDma(const StreamDmaParams &p)
    : DmaDevice(p),
    devname(p.devicename),
    streamIn(this, "stream_in"),
    streamOut(this, "stream_out"),
    statusIn(this, false),
    statusOut(this, true),
    pioAddr(p.pio_addr),
    pioDelay(p.pio_delay),
    pioSize(p.pio_size),
    streamAddr(p.stream_addr),
    streamSize(p.stream_size),
    statusAddr(p.status_addr),
    statusSize(p.status_size),
    memDelay(p.mem_delay),
    rdBufferSize(p.read_buffer_size),
    wrBufferSize(p.write_buffer_size),
    maxPending(p.max_pending),
    maxReqSize(p.max_req_size),
    gic(p.gic),
    rdInt(p.rd_int),
    wrInt(p.wr_int),
    tickEvent(this),
    bandwidth(p.bandwidth),
    dmaStats(this) {
    readFifo = new DmaReadFifo(dmaPort, rdBufferSize, maxReqSize, maxPending);
    writeFifo = new DmaWriteFifo(
        dmaPort, wrBufferSize, maxReqSize, maxPending, 0,
        [this](size_t) { dmaStats.writePackets++; });
    const Addr mmregSize = std::max<Addr>(pioSize, BUFFER_ACCESS_OFF);
    mmreg = new uint8_t[mmregSize];
    for (Addr i = 0; i < mmregSize; i++)
        mmreg[i]=0;
    FLAGS = mmreg;
    CONFIG = (uint16_t *)(mmreg+CONFIG_OFF);
    RD_ADDR = (uint64_t *)(mmreg+RD_ADDR_OFF);
    WR_ADDR = (uint64_t *)(mmreg+WR_ADDR_OFF);
    RD_FRAME_SIZE = (uint32_t *)(mmreg+RD_FRAME_SIZE_OFF);
    NUM_RD_FRAMES = (uint8_t *)(mmreg+NUM_RD_FRAMES_OFF);
    RD_FRAME_BUFF_SIZE = (uint8_t *)(mmreg+RD_FRAME_BUFF_SIZE_OFF);
    WR_FRAME_SIZE = (uint32_t *)(mmreg+WR_FRAME_SIZE_OFF);
    NUM_WR_FRAMES = (uint8_t *)(mmreg+NUM_WR_FRAMES_OFF);
    WR_FRAME_BUFF_SIZE = (uint8_t *)(mmreg+WR_FRAME_BUFF_SIZE_OFF);

    rdRunning = false;
    wrRunning = false;
    running = false;

    endian = sys->getGuestByteOrder();
}

AddrRangeList
StreamDma::getAddrRanges() const
{
    assert(pioSize != 0);
    AddrRangeList ranges;
    DPRINTF(AddrRanges, "Valid pio range: %#x-%#x\n", pioAddr, pioAddr+pioSize);
    ranges.push_back(RangeSize(pioAddr, pioSize));
    return ranges;
}

AddrRangeList
StreamDma::getStreamAddrRanges() const {
    assert(streamSize != 0);
    AddrRangeList streamRanges;
    DPRINTF(AddrRanges, "Valid stream range: %#x-%#x\n", streamAddr, streamAddr+streamSize);
    streamRanges.push_back(RangeSize(streamAddr, streamSize));
    return streamRanges;
}

AddrRangeList
StreamDma::getStatusAddrRanges() const {
	assert(statusSize != 0);
	AddrRangeList statusRanges;
	DPRINTF(AddrRanges, "registering range: %#x-%#x\n", statusAddr, statusSize);
    statusRanges.push_back(RangeSize(statusAddr, statusSize));
    return statusRanges;
}

void
StreamDma::tick() {

    if (!rdRunning && ((*FLAGS&RD_START_MASK)==RD_START_MASK)) {
        rdRunning = true;
        dmaStats.readStarts++;
        *FLAGS &= ~RD_START_MASK;
        *FLAGS |= RD_RUNNING_MASK;
        readAddr = *RD_ADDR;
        readPtr = readAddr;
        readFrameSize = *RD_FRAME_SIZE;
        framesToRead = *NUM_RD_FRAMES;
        readFrameBuffSize = *RD_FRAME_BUFF_SIZE;
        framesRead = 0;
        readIntFrames = *(uint8_t *)CONFIG;
        DPRINTF(StreamDma, "Initializing frame read from 0x%016x with frame size of %d Bytes\n", readPtr, readFrameSize);
        readFifo->startFill(readPtr, readFrameSize);
    }

    if (!wrRunning && ((*FLAGS&WR_START_MASK)==WR_START_MASK)) {
        wrRunning = true;
        dmaStats.writeStarts++;
        *FLAGS &= ~WR_START_MASK;
        *FLAGS |= WR_RUNNING_MASK;
        writeAddr = *WR_ADDR;
        writePtr = writeAddr;
        writeFrameSize = *WR_FRAME_SIZE;
        framesToWrite = *NUM_WR_FRAMES;
        writeFrameBuffSize = *WR_FRAME_BUFF_SIZE;
        framesWritten = 0;
        writeIntFrames = *CONFIG>>8;
        DPRINTF(StreamDma, "MMR After Write: %08x\n", *FLAGS);
        DPRINTF(StreamDma, "Initializing frame write to 0x%016x with frame size of %d Bytes\n", writePtr, writeFrameSize);
        writeFifo->startEmpty(writePtr, writeFrameSize);
    }

    if ((*FLAGS&RD_INT_MASK) != RD_INT_MASK) {
        gic->clearInt(rdInt);
    }

    if ((*FLAGS&WR_INT_MASK) != WR_INT_MASK) {
        gic->clearInt(wrInt);
    }

    if (rdRunning && !readFifo->isActive()) {
        framesRead++;
        dmaStats.framesRead++;
        DPRINTF(StreamDma, "Frame %d of %d read\n", framesRead, framesToRead);
        if (readIntFrames != 0) {
            if (framesRead % readIntFrames == 0) {
                gic->sendInt(rdInt);
                *FLAGS |= RD_INT_MASK;
            }
        }
        if ((framesToRead != 0) && (framesRead >= framesToRead)) {
            rdRunning = false;
            *FLAGS &= ~RD_RUNNING_MASK;
        } else {
            assert(readFrameBuffSize != 0);
            readPtr = readAddr + ((framesRead % readFrameBuffSize) * readFrameSize);
            DPRINTF(StreamDma, "Initializing frame read from 0x%016x with frame size of %d Bytes\n", readPtr, readFrameSize);
            readFifo->startFill(readPtr, readFrameSize);
        }
    }

    if (wrRunning && !writeFifo->isActive()) {
        framesWritten++;
        dmaStats.framesWritten++;
        DPRINTF(StreamDma, "Frame %d of %d written\n", framesWritten, framesToWrite);
        if (writeIntFrames != 0) {
            if (framesWritten % writeIntFrames == 0) {
                gic->sendInt(wrInt);
                *FLAGS |= WR_INT_MASK;
            }
        }
        if ((framesToWrite != 0) && (framesWritten >= framesToWrite)) {
            wrRunning = false;
            *FLAGS &= ~WR_RUNNING_MASK;
        } else {
            assert(writeFrameBuffSize != 0);
            writePtr = writeAddr + ((framesWritten % writeFrameBuffSize) * writeFrameSize);
            DPRINTF(StreamDma, "Initializing frame write to 0x%016x with frame size of %d Bytes\n", writePtr, writeFrameSize);
            writeFifo->startEmpty(writePtr, writeFrameSize);
        }
    }

    running = rdRunning || wrRunning;
    dmaStats.active = running ? 1 : 0;
    if (!tickEvent.scheduled() && running) {
        schedule(tickEvent, nextCycle());
    }
}

Tick
StreamDma::read(PacketPtr pkt) {

    Addr offset = pkt->req->getPaddr() - pioAddr;

    if (offset < BUFFER_ACCESS_OFF) {
        DPRINTF(DeviceMMR, "The MMR associated with this DMA was read from!\n");

        uint32_t data = 0;

        switch(pkt->getSize()) {
          case 1:
            data = *(uint8_t *)(mmreg+offset);
            pkt->set<uint8_t>(data, endian);
            break;
          case 2:
            data = *(uint16_t *)(mmreg+offset);
            pkt->set<uint16_t>(data, endian);
            break;
          case 4:
            data = *(uint32_t *)(mmreg+offset);
            pkt->set<uint32_t>(data, endian);
            break;
          default:
            panic("Read size too big?\n");
            break;
        }
    } else {
        DPRINTF(DeviceMMR, "The data buffer associated with this DMA was read from!\n");
        dmaStats.bytesRead += pkt->getSize();

        uint8_t *buff = new uint8_t[pkt->getSize()];
        readFifo->get(buff, pkt->getSize());
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
    }

    if (!tickEvent.scheduled()) {
        schedule(tickEvent, nextCycle());
    }
    pkt->makeAtomicResponse();
    return pioDelay;
}

Tick
StreamDma::write(PacketPtr pkt) {

    Addr offset = pkt->req->getPaddr() - pioAddr;

    if (offset < BUFFER_ACCESS_OFF) {
        DPRINTF(DeviceMMR, "The MMR associated with this DMA was written to!\n");

        pkt->writeData(mmreg + offset);
    } else {
        DPRINTF(DeviceMMR, "The data buffer associated with this DMA was written to!\n");
        dmaStats.bytesWritten += pkt->getSize();
        uint8_t * data = new uint8_t[pkt->getSize()];
        pkt->writeData(data);
        writeFifo->fill(data, pkt->getSize());
        delete[] data;
    }

    if (!tickEvent.scheduled()) {
        schedule(tickEvent, nextCycle());
    }
    pkt->makeAtomicResponse();
    return pioDelay;
}

Tick
StreamDma::streamRead(PacketPtr pkt) {
    DPRINTF(DeviceMMR, "The data buffer associated with this DMA was read from!\n");
    dmaStats.bytesRead += pkt->getSize();

    uint8_t *buff = new uint8_t[pkt->getSize()];
    readFifo->get(buff, pkt->getSize());
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
StreamDma::streamWrite(PacketPtr pkt) {
    DPRINTF(DeviceMMR, "The data buffer associated with this DMA was written to!\n");
    dmaStats.bytesWritten += pkt->getSize();
    uint8_t * data = new uint8_t[pkt->getSize()];
    pkt->writeData(data);
    writeFifo->fill(data, pkt->getSize());
    delete[] data;

    pkt->makeAtomicResponse();
    return pioDelay;
}

Tick
StreamDma::status(PacketPtr pkt, bool readStatus) {
	// Provide a means of reading the current buffer capacity of the stream
	// Writes to this register do nothing
	if (pkt->isRead()) {
        dmaStats.statusReads++;
        uint64_t data;
        if (readStatus) {
            DPRINTF(StreamDma, "The status of the MM2S buffer has been read. Current capacity is %d of %d bytes\n",
                    readFifo->size(), rdBufferSize);
            data = readFifo->size();
        } else {
            DPRINTF(StreamDma, "The status of the S2MM buffer has been read. Current capacity is %d of %d bytes\n",
                    writeFifo->size(), wrBufferSize);
            data = writeFifo->size();
        }
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

bool
StreamDma::tvalid(PacketPtr pkt) {
    return tvalid(pkt->getSize(), pkt->isRead());
}

bool
StreamDma::tvalid(size_t len, bool isRead) {
    if (isRead) {
        return (readFifo->size() >= len) ? true : false;
    } else {
        return writeFifo->canFill(len);
    }
}

Port &
StreamDma::getPort(const std::string &if_name, PortID idx) {
    if (if_name == "stream_in") {
        return streamIn;
    } else if (if_name == "stream_out") {
        return streamOut;
    } else if (if_name == "status_in") {
        return statusIn;
    } else if (if_name == "status_out") {
    	return statusOut;
	}
    return DmaDevice::getPort(if_name, idx);
}

// StreamDma *
// StreamDmaParams::create() {
//     return new StreamDma(this);
// }