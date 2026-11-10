// SPDX-License-Identifier: BSD-3-Clause
// Shared ordering and retry decisions for SALAM timing responses.
#ifndef __HWACC_RESPONSE_QUEUE_HH__
#define __HWACC_RESPONSE_QUEUE_HH__

/**
 * @file
 * @brief Shared response queue ordering and retry arbitration for timing
 * ports.
 */

#include <algorithm>
#include <iterator>
#include <optional>

namespace gem5::salam
{

// Search backwards without decrementing an empty container's end iterator.
// A matching address is an ordering barrier. A head whose response has been
// rejected (or is inside a send callback) must remain the next response.
/**
 * @brief Determines ordered insertion point for a timing response.
 *
 * Maintains strict address ordering and head pinning during retries.
 *
 * @param queue Response queue.
 * @param ready Ready tick.
 * @param pinHead Whether head packet is pinned in flight.
 * @param sameAddress Predicate for address ordering barrier.
 * @return Iterator insertion position.
 */
template <class Queue, class Time, class SameAddress>
typename Queue::iterator
responseInsertionPosition(Queue &queue, Time ready, bool pinHead,
                          SameAddress sameAddress)
{
    auto first = queue.begin();
    if (pinHead && first != queue.end()) {
        ++first;
    }
    auto position = queue.end();
    while (position != first) {
        const auto previous = std::prev(position);
        if (ready >= previous->tick || sameAddress(*previous)) {
            break;
        }
        position = previous;
    }
    return position;
}

// A shared response queue observes its head port's retry state, rather than
// the state of a newly arrived request on another port. Do not schedule from
// inside sendTimingResp: the peer can enqueue another request synchronously.
/**
 * @brief Calculates scheduled tick for the next eligible response packet.
 *
 * @param queue Response queue.
 * @param now Current simulation tick.
 * @param responseInProgress Flag indicating if a response is already in-
 * flight.
 * @param blocked Predicate indicating if head port is retry-blocked.
 * @return Scheduled tick, or nullopt if no packet can be sent.
 */
template <class Queue, class Time, class Blocked>
std::optional<Time>
nextResponseTime(const Queue &queue, Time now, bool responseInProgress,
                 Blocked blocked)
{
    if (queue.empty() || responseInProgress || blocked(queue.front())) {
        return std::nullopt;
    }
    return std::max<Time>(queue.front().tick, now);
}

} // namespace gem5::salam

#endif // __HWACC_RESPONSE_QUEUE_HH__
