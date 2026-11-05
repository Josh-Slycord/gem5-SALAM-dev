// SPDX-License-Identifier: BSD-3-Clause
#ifndef __HWACC_NATIVE_HELPERS_HH__
#define __HWACC_NATIVE_HELPERS_HH__

#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>

namespace gem5::salam
{

// A diagnostic prefix must not overread a narrow store or rely on alignment.
inline uint64_t
debugBytePrefix(const uint8_t *data, size_t size)
{
    uint64_t value = 0;
    for (size_t index = 0; index < size && index < sizeof(value); ++index) {
        value |= uint64_t(data[index]) << (8 * index);
    }
    return value;
}

inline std::optional<uint64_t>
checkedClockDelay(uint64_t period, uint64_t cycles)
{
    if (!period || !cycles ||
        cycles > std::numeric_limits<uint64_t>::max() / period) {
        return std::nullopt;
    }
    return period * cycles;
}

// Legacy clock_period is an integer number of ns, not a raw tick count.
inline std::optional<uint64_t>
legacyClockTicks(int64_t nanoseconds, uint64_t ticks_per_ns)
{
    if (nanoseconds <= 0) {
        return std::nullopt;
    }
    return checkedClockDelay(ticks_per_ns, uint64_t(nanoseconds));
}

} // namespace gem5::salam

#endif
