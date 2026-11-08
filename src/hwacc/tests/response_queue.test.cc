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
