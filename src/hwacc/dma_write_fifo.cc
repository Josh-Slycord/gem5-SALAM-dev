//------------------------------------------//
#include "hwacc/dma_write_fifo.hh"
//------------------------------------------//

DmaWriteFifo::DmaWriteFifo(DmaPort &_port, size_t size,
                         unsigned max_req_size,
                         unsigned max_pending,
                         Request::Flags flags,
                         WriteIssuedCallback on_write)
    : maxReqSize(max_req_size), fifoSize(size),
      reqFlags(flags), port(_port), onWriteIssued(std::move(on_write)),
      buffer(size),
      nextAddr(0), endAddr(0)
{
    freeRequests.resize(max_pending);
    for (auto &e : freeRequests)
        e.reset(new DmaDoneEvent(this, max_req_size));

}

DmaWriteFifo::~DmaWriteFifo()
{
    for (auto &p : pendingRequests) {
        DmaDoneEvent *e(p.release());

        if (e->done()) {
            delete e;
        } else {
            // We can't kill in-flight DMAs, so we'll just transfer
            // ownership to the event queue so that they get freed
            // when they are done.
            e->kill();
        }
    }
}

void
DmaWriteFifo::serialize(CheckpointOut &cp) const
{
    assert(pendingRequests.empty());

    SERIALIZE_CONTAINER(buffer);
    SERIALIZE_SCALAR(endAddr);
    SERIALIZE_SCALAR(nextAddr);
}

void
DmaWriteFifo::unserialize(CheckpointIn &cp)
{
    UNSERIALIZE_CONTAINER(buffer);
    UNSERIALIZE_SCALAR(endAddr);
    UNSERIALIZE_SCALAR(nextAddr);
}

bool
DmaWriteFifo::canFill(size_t len)
{
    if ((buffer.size()+len) <= fifoSize) {
        return true;
    } else {
        return false;
    }
}

bool
DmaWriteFifo::tryFill(uint8_t *src, size_t len)
{
    if ((buffer.size()+len) <= fifoSize) {
        buffer.write(src, len);
        resumeEmpty();
        return true;
    } else {
        return false;
    }
}

void
DmaWriteFifo::fill(uint8_t *src, size_t len)
{
    const bool success(tryFill(src, len));
    panic_if(!success, "Buffer overrun in DmaWriteFifo::fill()\n");
}

void
DmaWriteFifo::startEmpty(Addr start, size_t size)
{
    assert(atEndOfBlock());

    nextAddr = start;
    endAddr = start + size;
    resumeEmpty();
}

void
DmaWriteFifo::stopEmpty()
{
    // Prevent new DMA requests by setting the next address to the end
    // address. Pending requests will still complete.
    nextAddr = endAddr;

    // Flag in-flight accesses as canceled. This prevents their data
    // from being written to the FIFO.
    for (auto &p : pendingRequests)
        p->cancel();
}

void
DmaWriteFifo::resumeEmpty()
{
    // Don't try to fetch more data if we are draining. This ensures
    // that the DMA engine settles down before we checkpoint it.
    if (drainState() == DrainState::Draining)
        return;

    const bool old_eob(atEndOfBlock());

    if (port.sys->bypassCaches())
        resumeEmptyFunctional();
    else
        resumeEmptyTiming();

    if (!old_eob && atEndOfBlock())
        onEndOfBlock();
}

void
DmaWriteFifo::resumeEmptyFunctional()
{
    // atomic_noncaching completes dmaAction before return, so the
    // chunk buffer is live for the whole write. Fifo::read consumes.
    assert(pendingRequests.empty());

    while (!atEndOfBlock() && buffer.size() > 0) {
        const Addr block_remaining = endAddr - nextAddr;
        const Addr available = static_cast<Addr>(buffer.size());
        const Addr req_size =
            std::min(maxReqSize, std::min(block_remaining, available));
        if (req_size == 0) {
            break;
        }

        std::vector<uint8_t> chunk(req_size);
        buffer.read(chunk.data(), req_size);
        DPRINTF(DMA,
                "KVM bypass write startAddr=%#x req_size=%#x "
                "fifo_size=%#x block_remaining=%#x\n",
                nextAddr, req_size, buffer.size(), block_remaining);

        port.dmaAction(MemCmd::WriteReq, nextAddr, req_size, nullptr,
                       chunk.data(), 0, reqFlags);
        if (onWriteIssued)
            onWriteIssued(req_size);
        nextAddr += req_size;
    }
}

void
DmaWriteFifo::resumeEmptyTiming()
{
    size_t size_pending(0);
    for (auto &e : pendingRequests)
        size_pending += e->requestSize();

    while (!freeRequests.empty() && !atEndOfBlock()) {
        const size_t req_size(std::min(maxReqSize, endAddr - nextAddr));
        if ((int64_t)(buffer.size() - size_pending - req_size) < 0)
            break;

        DmaDoneEventUPtr event(std::move(freeRequests.front()));
        freeRequests.pop_front();
        assert(event);

        event->reset(req_size);
        buffer.read(event->data(), req_size);
        port.dmaAction(MemCmd::WriteReq, nextAddr, req_size, event.get(),
                       event->data(), 0, reqFlags);
        if (onWriteIssued)
            onWriteIssued(req_size);
        nextAddr += req_size;
        size_pending += req_size;

        pendingRequests.emplace_back(std::move(event));
    }
}

void
DmaWriteFifo::dmaDone()
{
    const bool old_active(isActive());

    handlePending();
    resumeEmpty();

    if (old_active && !isActive())
        onIdle();
}

void
DmaWriteFifo::handlePending()
{
    while (!pendingRequests.empty() && pendingRequests.front()->done()) {
        // Get the first finished pending request
        DmaDoneEventUPtr event(std::move(pendingRequests.front()));
        pendingRequests.pop_front();

        if (event->canceled())
            buffer.write(event->data(), event->requestSize());

        // Move the event to the list of free requests
        freeRequests.emplace_back(std::move(event));
    }

    if (pendingRequests.empty())
        signalDrainDone();
}

DrainState
DmaWriteFifo::drain()
{
    return pendingRequests.empty() ? DrainState::Drained : DrainState::Draining;
}


DmaWriteFifo::DmaDoneEvent::DmaDoneEvent(DmaWriteFifo *_parent,
                                        size_t max_size)
    : parent(_parent), _done(false), _canceled(false), _data(max_size, 0)
{
}

void
DmaWriteFifo::DmaDoneEvent::kill()
{
    parent = nullptr;
    setFlags(AutoDelete);
}

void
DmaWriteFifo::DmaDoneEvent::cancel()
{
    _canceled = true;
}

void
DmaWriteFifo::DmaDoneEvent::reset(size_t size)
{
    assert(size <= _data.size());
    _done = false;
    _canceled = false;
    _requestSize = size;
}

void
DmaWriteFifo::DmaDoneEvent::process()
{
    if (!parent)
        return;

    assert(!_done);
    _done = true;
    parent->dmaDone();
}
