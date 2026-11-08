// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>

#include "hwacc/float_bits.hh"

using gem5::salam::floatingRemainder;
using gem5::salam::floatingResultBits;

TEST(SalamFloatBits, FloatUsesExactlyFourBytesAndZeroExtends)
{
    struct Adjacent
    {
        float value;
        uint32_t poison;
    };
    const Adjacent adjacent{1.5f, 0xdeadbeef};
    EXPECT_EQ(floatingResultBits(adjacent.value), uint64_t(0x3fc00000));
    EXPECT_EQ(floatingResultBits(adjacent.value) >> 32, uint64_t(0));
}

TEST(SalamFloatBits, DoublePreservesAllEightBytes)
{
    EXPECT_EQ(floatingResultBits(1.5), UINT64_C(0x3ff8000000000000));
}

TEST(SalamFloatBits, NegativeZeroPreservesItsSign)
{
    EXPECT_EQ(floatingResultBits(-0.0f), UINT64_C(0x80000000));
    EXPECT_EQ(floatingResultBits(-0.0), UINT64_C(0x8000000000000000));
}

TEST(SalamFloatBits, NaNPayloadsAreNotNumericallyConverted)
{
    const uint32_t floatPayload = 0xffc12345;
    const uint64_t doublePayload = UINT64_C(0xfff8123456789abc);
    float floatValue;
    double doubleValue;
    std::memcpy(&floatValue, &floatPayload, sizeof(floatValue));
    std::memcpy(&doubleValue, &doublePayload, sizeof(doubleValue));
    EXPECT_EQ(floatingResultBits(floatValue), uint64_t(floatPayload));
    EXPECT_EQ(floatingResultBits(doubleValue), doublePayload);
}

TEST(SalamFloatBits, UnsignedAndSignedIntegerToFloatWriteback)
{
    const uint64_t unsignedValue = std::numeric_limits<uint64_t>::max();
    const int64_t signedValue = std::numeric_limits<int64_t>::min();
    EXPECT_EQ(floatingResultBits(static_cast<float>(unsignedValue)),
              UINT64_C(0x5f800000));
    EXPECT_EQ(floatingResultBits(static_cast<float>(signedValue)),
              UINT64_C(0xdf000000));
    EXPECT_EQ(floatingResultBits(static_cast<double>(signedValue)),
              UINT64_C(0xc3e0000000000000));
}

TEST(SalamFloatBits, TruncatedDoubleHasNoAdjacentStackBytes)
{
    const double wideValue = 3.5;
    EXPECT_EQ(floatingResultBits(static_cast<float>(wideValue)),
              UINT64_C(0x40600000));
}

TEST(SalamFloatBits, FremTruncatesQuotientInsteadOfRoundingIt)
{
    EXPECT_EQ(floatingRemainder(7.0f, 4.0f), 3.0f);
    EXPECT_EQ(floatingRemainder(7.0, 4.0), 3.0);
    EXPECT_EQ(floatingRemainder(-7.0f, 4.0f), -3.0f);
    EXPECT_EQ(floatingRemainder(7.0f, -4.0f), 3.0f);
    EXPECT_EQ(floatingRemainder(-7.0, -4.0), -3.0);
}

TEST(SalamFloatBits, FremPreservesSignedZero)
{
    EXPECT_EQ(floatingResultBits(floatingRemainder(-0.0f, 4.0f)),
              UINT64_C(0x80000000));
    EXPECT_EQ(floatingResultBits(floatingRemainder(-0.0, 4.0)),
              UINT64_C(0x8000000000000000));
}

TEST(SalamFloatBits, FremExceptionalInputs)
{
    const double infinity = std::numeric_limits<double>::infinity();
    EXPECT_EQ(floatingRemainder(7.0, infinity), 7.0);
    EXPECT_TRUE(std::isnan(floatingRemainder(infinity, 4.0)));
    EXPECT_TRUE(std::isnan(floatingRemainder(7.0, 0.0)));
}
