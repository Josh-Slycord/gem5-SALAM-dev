// SPDX-License-Identifier: BSD-3-Clause
// Bit-preserving scalar floating-point writeback without aliasing or overreads.
#ifndef __HWACC_FLOAT_BITS_HH__
#define __HWACC_FLOAT_BITS_HH__

/**
 * @file
 * @brief Bit-preserving scalar floating-point writeback and remainder
 * operations.
 *
 * Prevents aliasing or overreads by preserving exact bit patterns across float
 * (32-bit) and double (64-bit) representations.
 */

#include <cmath>
#include <cstdint>
#include <cstring>
#include <type_traits>

namespace gem5::salam
{

/**
 * @brief Converts floating-point value to exact 64-bit unsigned
 * representation.
 *
 * @tparam Float Single or double precision float.
 * @param value Floating-point value.
 * @return Bit-pattern payload as uint64_t.
 */
template <class Float>
uint64_t
floatingResultBits(Float value)
{
    static_assert(std::is_same_v<Float, float> ||
                  std::is_same_v<Float, double>);
    static_assert(sizeof(float) == sizeof(uint32_t));
    static_assert(sizeof(double) == sizeof(uint64_t));
    using Bits = std::conditional_t<
        std::is_same_v<Float, float>, uint32_t, uint64_t>;
    Bits bits = 0;
    std::memcpy(&bits, &value, sizeof(value));
    // Float results occupy the low 32 bits; no adjacent stack bytes leak into
    // the writeback value. Double results preserve the entire 64-bit payload.
    return static_cast<uint64_t>(bits);
}

// LLVM frem truncates the quotient toward zero; std::remainder instead
// chooses the nearest integral quotient and is not equivalent.
/**
 * @brief Computes floating-point remainder compatible with LLVM frem (fmod).
 *
 * @tparam Float Single or double precision float.
 * @param lhs Dividend.
 * @param rhs Divisor.
 * @return Remainder value.
 */
template <class Float>
Float
floatingRemainder(Float lhs, Float rhs)
{
    static_assert(std::is_same_v<Float, float> ||
                  std::is_same_v<Float, double>);
    return std::fmod(lhs, rhs);
}

} // namespace gem5::salam

#endif // __HWACC_FLOAT_BITS_HH__
