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
