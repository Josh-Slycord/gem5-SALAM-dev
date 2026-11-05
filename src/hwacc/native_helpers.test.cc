// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>

#include <limits>
#include <memory>

#include "hwacc/native_helpers.hh"

using namespace gem5::salam;

TEST(SalamNativeHelpers, DebugPrefixDoesNotOverreadNarrowStores)
{
    for (const size_t size : {1, 2, 4, 8, 16}) {
        auto bytes = std::make_unique<uint8_t[]>(size);
        uint64_t expected = 0;
        for (size_t index = 0; index < size; ++index) {
            bytes[index] = uint8_t(index + 1);
            if (index < 8) {
                expected |= uint64_t(index + 1) << (8 * index);
            }
        }
        EXPECT_EQ(debugBytePrefix(bytes.get(), size), expected);
    }
    EXPECT_EQ(debugBytePrefix(nullptr, 0), 0);
}

TEST(SalamNativeHelpers, DebugPrefixDoesNotRequireAlignment)
{
    const uint8_t bytes[] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
    EXPECT_EQ(debugBytePrefix(bytes + 1, 8), 0x0908070605040302ULL);
}

TEST(SalamNativeHelpers, LegacyClockConversionIsExplicitAndChecked)
{
    EXPECT_EQ(legacyClockTicks(10, 1000), 10000);
    EXPECT_EQ(legacyClockTicks(5, 1000), 5000);
    EXPECT_EQ(legacyClockTicks(10, 2), 20);
    EXPECT_FALSE(legacyClockTicks(0, 1000));
    EXPECT_FALSE(legacyClockTicks(-1, 1000));
    EXPECT_FALSE(legacyClockTicks(10, 0));
    EXPECT_FALSE(legacyClockTicks(std::numeric_limits<int64_t>::max(), 1000));
}

TEST(SalamNativeHelpers, ServiceCyclesCannotBeZeroOrOverflowTicks)
{
    EXPECT_EQ(checkedClockDelay(10000, 2), 20000);
    EXPECT_FALSE(checkedClockDelay(10000, 0));
    EXPECT_FALSE(checkedClockDelay(0, 1));
    EXPECT_FALSE(checkedClockDelay(std::numeric_limits<uint64_t>::max(), 2));
}
