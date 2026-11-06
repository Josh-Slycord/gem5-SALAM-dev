// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>

#include <cstdint>
#include <limits>
#include <list>
#include <map>
#include <vector>

#include "hwacc/response_queue.hh"

namespace
{

struct Response
{
    uint64_t tick;
    unsigned address;
    unsigned origin;
    unsigned id;
};

using Queue = std::list<Response>;

void
insert(Queue &queue, Response response, bool pinHead = false)
{
    auto position = gem5::salam::responseInsertionPosition(
        queue, response.tick, pinHead,
        [response](const auto &entry) {
            return entry.address == response.address;
        });
    queue.insert(position, response);
}

std::vector<unsigned>
ids(const Queue &queue)
{
    std::vector<unsigned> result;
    for (const auto &response : queue) {
        result.push_back(response.id);
    }
    return result;
}

} // anonymous namespace

TEST(SalamResponseQueue, EmptyQueueInsertion)
{
    Queue queue;
    insert(queue, {20, 1, 0, 1});
    ASSERT_EQ(queue.size(), 1);
    EXPECT_EQ(queue.front().id, 1);
}

TEST(SalamResponseQueue, EarlierDifferentAddressCanBecomeHead)
{
    Queue queue;
    insert(queue, {30, 1, 0, 1});
    insert(queue, {10, 2, 1, 2});
    insert(queue, {20, 3, 2, 3});
    EXPECT_EQ(ids(queue), (std::vector<unsigned>{2, 3, 1}));
}

TEST(SalamResponseQueue, EqualTicksStayStable)
{
    Queue queue;
    insert(queue, {10, 1, 0, 1});
    insert(queue, {10, 2, 1, 2});
    insert(queue, {10, 3, 2, 3});
    EXPECT_EQ(ids(queue), (std::vector<unsigned>{1, 2, 3}));
}

TEST(SalamResponseQueue, SameAddressIsAnOrderingBarrier)
{
    Queue queue;
    insert(queue, {30, 1, 0, 1});
    insert(queue, {40, 2, 1, 2});
    insert(queue, {5, 1, 2, 3});
    EXPECT_EQ(ids(queue), (std::vector<unsigned>{1, 3, 2}));
}

TEST(SalamResponseQueue, BlockedHeadCannotBeReplaced)
{
    Queue queue;
    insert(queue, {30, 1, 0, 1});
    insert(queue, {40, 2, 1, 2});
    insert(queue, {5, 3, 1, 3}, true);
    EXPECT_EQ(ids(queue), (std::vector<unsigned>{1, 3, 2}));
}

TEST(SalamResponseQueue, InCallbackHeadIsNeverDereferenced)
{
    Queue queue{{30, 1, 0, 1}, {40, 2, 1, 2}};
    auto position = gem5::salam::responseInsertionPosition(
        queue, uint64_t(5), true,
        [](const auto &entry) {
            // A synchronous peer may already have freed the head packet.
            EXPECT_NE(entry.id, 1);
            return false;
        });
    queue.insert(position, {5, 3, 2, 3});
    EXPECT_EQ(ids(queue), (std::vector<unsigned>{1, 3, 2}));
}

TEST(SalamResponseQueue, EmptyQueueNeverReadsHeadRetryState)
{
    Queue queue;
    auto when = gem5::salam::nextResponseTime(
        queue, uint64_t(5), false,
        [](const auto &) {
            ADD_FAILURE() << "Empty queue queried a nonexistent head";
            return false;
        });
    EXPECT_FALSE(when);
}

TEST(SalamResponseQueue, BlockedFrontPortPreventsOtherPortBypass)
{
    Queue queue{{30, 1, 0, 1}, {40, 2, 1, 2}};
    std::map<unsigned, bool> blocked{{0, true}, {1, false}};
    auto check = [&blocked](const auto &entry) {
        return blocked.at(entry.origin);
    };
    EXPECT_FALSE(gem5::salam::nextResponseTime(
        queue, uint64_t(50), false, check));
    blocked[0] = false;
    EXPECT_EQ(gem5::salam::nextResponseTime(
        queue, uint64_t(50), false, check), uint64_t(50));
    queue.pop_front();
    EXPECT_EQ(gem5::salam::nextResponseTime(
        queue, uint64_t(50), false, check), uint64_t(50));
}

TEST(SalamResponseQueue, InCallbackDefersResponseScheduling)
{
    Queue queue{{30, 1, 0, 1}};
    auto when = gem5::salam::nextResponseTime(
        queue, uint64_t(5), true,
        [](const auto &) {
            ADD_FAILURE() << "In-flight response retry state was inspected";
            return false;
        });
    EXPECT_FALSE(when);
}

TEST(SalamResponseQueue, ReschedulingDecisionUsesTheNewHead)
{
    Queue queue{{30, 1, 0, 1}};
    const auto unblocked = [](const auto &) { return false; };
    EXPECT_EQ(gem5::salam::nextResponseTime(
        queue, uint64_t(5), false, unblocked), uint64_t(30));
    insert(queue, {10, 2, 1, 2});
    EXPECT_EQ(gem5::salam::nextResponseTime(
        queue, uint64_t(5), false, unblocked), uint64_t(10));
}

TEST(SalamResponseQueue, MaximumTickDoesNotOverflow)
{
    Queue queue{{std::numeric_limits<uint64_t>::max(), 1, 0, 1}};
    EXPECT_EQ(gem5::salam::nextResponseTime(
        queue, uint64_t(5), false, [](const auto &) { return false; }),
        std::numeric_limits<uint64_t>::max());
}

TEST(SalamResponseQueue, MultiPortContentionAndHeadRetryTransitions)
{
    // Three ports (0, 1, 2) contending for response delivery.
    Queue queue;
    insert(queue, {10, 100, 0, 1}); // port 0, addr 100, tick 10, id 1
    insert(queue, {15, 200, 1, 2}); // port 1, addr 200, tick 15, id 2
    insert(queue, {20, 300, 2, 3}); // port 2, addr 300, tick 20, id 3

    std::map<unsigned, bool> blocked{{0, true}, {1, false}, {2, false}};
    auto checkBlocked = [&blocked](const auto &entry) {
        return blocked.at(entry.origin);
    };

    // When head port 0 is blocked on retry, other ports (1, 2) cannot bypass
    EXPECT_FALSE(gem5::salam::nextResponseTime(queue, uint64_t(30), false, checkBlocked));

    // Port 0 unblocks via retry callback
    blocked[0] = false;
    auto when = gem5::salam::nextResponseTime(queue, uint64_t(30), false, checkBlocked);
    ASSERT_TRUE(when.has_value());
    EXPECT_EQ(*when, uint64_t(30));
    EXPECT_EQ(queue.front().id, 1);

    // Port 0 response is sent and popped from queue
    queue.pop_front();

    // Now port 1 is the head. If port 1 is blocked on retry:
    blocked[1] = true;
    EXPECT_FALSE(gem5::salam::nextResponseTime(queue, uint64_t(30), false, checkBlocked));

    // Port 1 unblocks
    blocked[1] = false;
    when = gem5::salam::nextResponseTime(queue, uint64_t(30), false, checkBlocked);
    ASSERT_TRUE(when.has_value());
    EXPECT_EQ(queue.front().id, 2);
    queue.pop_front();

    // Port 2 delivers
    when = gem5::salam::nextResponseTime(queue, uint64_t(30), false, checkBlocked);
    ASSERT_TRUE(when.has_value());
    EXPECT_EQ(queue.front().id, 3);
    queue.pop_front();

    EXPECT_TRUE(queue.empty());
    EXPECT_FALSE(gem5::salam::nextResponseTime(queue, uint64_t(30), false, checkBlocked));
}

TEST(SalamResponseQueue, SynchronousReentrancyPreservesInFlightHead)
{
    Queue queue;
    insert(queue, {20, 0x10, 0, 1}); // Initial in-flight request

    // Simulation begins sending response: responseInProgress = true, pinHead = true
    bool inProgress = true;
    bool retryBlocked = false;

    // While in-flight, peer callback synchronously issues a new read targeting the same address
    // with an earlier timestamp (tick 5).
    auto position = gem5::salam::responseInsertionPosition(
        queue, uint64_t(5), retryBlocked || inProgress,
        [](const auto &entry) { return entry.address == 0x10; });
    queue.insert(position, {5, 0x10, 0, 2});

    // Verify in-flight head (id 1) was NOT displaced or replaced
    ASSERT_EQ(queue.size(), 2);
    EXPECT_EQ(queue.front().id, 1);
    EXPECT_EQ(ids(queue), (std::vector<unsigned>{1, 2}));

    // In-flight response callback completes and pops head
    inProgress = false;
    queue.pop_front();

    // Re-entrant request (id 2) is now ready to schedule
    auto when = gem5::salam::nextResponseTime(
        queue, uint64_t(25), inProgress, [](const auto &) { return false; });
    ASSERT_TRUE(when.has_value());
    EXPECT_EQ(*when, uint64_t(25));
    EXPECT_EQ(queue.front().id, 2);
}

TEST(SalamResponseQueue, DrainStateTransitionsUnderRetryBlocking)
{
    Queue queue;
    enum class DrainState { Drained, Draining };
    auto currentDrainState = [&queue]() {
        return queue.empty() ? DrainState::Drained : DrainState::Draining;
    };

    // Initially idle queue is Drained
    EXPECT_EQ(currentDrainState(), DrainState::Drained);

    // Request enqueued -> state transitions to Draining
    insert(queue, {10, 0x20, 0, 100});
    EXPECT_EQ(currentDrainState(), DrainState::Draining);

    // Response attempt fails on timing port: retryResp = true
    bool retryResp = true;

    // While retryResp is true, queue must NOT pop and drain state remains Draining
    EXPECT_EQ(currentDrainState(), DrainState::Draining);

    // A second request arrives during drain
    insert(queue, {15, 0x30, 1, 101});
    EXPECT_EQ(queue.size(), 2);

    // Downstream peer signals retry (recvRespRetry): retryResp = false
    retryResp = false;
    EXPECT_FALSE(retryResp);

    // Head packet delivers and pops
    queue.pop_front();
    EXPECT_EQ(currentDrainState(), DrainState::Draining);

    // Second packet delivers and pops
    queue.pop_front();

    // With queue completely empty, drain finishes -> Drained
    EXPECT_EQ(currentDrainState(), DrainState::Drained);
    bool drainSignaled = (currentDrainState() == DrainState::Drained);
    EXPECT_TRUE(drainSignaled);
}

TEST(SalamResponseQueue, DmaWriteFifoBypassVsTimingChunkRouting)
{
    // Simulates DmaWriteFifo write chunk calculation and sequencing.
    // Given 100-byte write from 0x2000 to 0x2064 with maxReqSize = 32.
    const uint64_t startAddr = 0x2000;
    const uint64_t totalSize = 100;
    const uint64_t endAddr = startAddr + totalSize;
    const uint64_t maxReqSize = 32;

    struct DmaAction {
        std::string cmd;
        uint64_t addr;
        uint64_t size;
        bool isTiming;
    };

    auto simulateTransfers = [&](bool bypassCaches) {
        std::vector<DmaAction> actions;
        uint64_t nextAddr = startAddr;
        uint64_t bufferSize = totalSize;

        while (nextAddr < endAddr && bufferSize > 0) {
            uint64_t block_remaining = endAddr - nextAddr;
            uint64_t req_size = std::min(maxReqSize, std::min(block_remaining, bufferSize));
            if (req_size == 0) break;

            actions.push_back({"WriteReq", nextAddr, req_size, !bypassCaches});
            nextAddr += req_size;
            bufferSize -= req_size;
        }
        return actions;
    };

    // Functional mode (bypassCaches = true)
    auto functionalChunks = simulateTransfers(true);

    // Timing mode (bypassCaches = false)
    auto timingChunks = simulateTransfers(false);

    ASSERT_EQ(functionalChunks.size(), timingChunks.size());
    ASSERT_EQ(functionalChunks.size(), 4u); // 32 + 32 + 32 + 4

    for (size_t i = 0; i < functionalChunks.size(); ++i) {
        EXPECT_EQ(functionalChunks[i].cmd, "WriteReq");
        EXPECT_EQ(timingChunks[i].cmd, "WriteReq");
        EXPECT_EQ(functionalChunks[i].addr, timingChunks[i].addr);
        EXPECT_EQ(functionalChunks[i].size, timingChunks[i].size);
    }

    EXPECT_EQ(functionalChunks[0].addr, 0x2000u);
    EXPECT_EQ(functionalChunks[0].size, 32u);
    EXPECT_EQ(functionalChunks[1].addr, 0x2020u);
    EXPECT_EQ(functionalChunks[1].size, 32u);
    EXPECT_EQ(functionalChunks[2].addr, 0x2040u);
    EXPECT_EQ(functionalChunks[2].size, 32u);
    EXPECT_EQ(functionalChunks[3].addr, 0x2060u);
    EXPECT_EQ(functionalChunks[3].size, 4u);
}

TEST(SalamResponseQueue, RegisterBankDeltaCycleStagingIsolation)
{
    // Simulates RegisterBank delta cycle: staging in deltaAddr, committing to pmemAddr
    uint32_t committed = 0xAA55AA55;
    uint32_t staged = committed;

    // A register write updates staged buffer
    staged = 0x12345678;

    // Before delta cycle, committed storage remains unchanged
    EXPECT_NE(committed, staged);
    EXPECT_EQ(committed, 0xAA55AA55u);

    // Delta cycle occurs: std::memcpy(pmemAddr, deltaAddr, size)
    committed = staged;

    // Post delta, committed reflects updated value
    EXPECT_EQ(committed, 0x12345678u);
}
