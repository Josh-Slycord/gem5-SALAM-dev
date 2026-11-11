// SPDX-License-Identifier: BSD-3-Clause
#include "hw_defines.h"

void top(uint64_t a, uint64_t b, uint64_t c)
{
    volatile uint8_t *flags = (uint8_t *)DMA_Flags;
    volatile uint64_t *read_address = (uint64_t *)DMA_RdAddr;
    volatile uint64_t *write_address = (uint64_t *)DMA_WrAddr;
    volatile uint32_t *length = (uint32_t *)DMA_CopyLen;
    volatile uint8_t *compute = (uint8_t *)VADD;
    *read_address = a;
    *write_address = VECTOR_A;
    *length = VADD_BYTES;
    *flags = DEV_INIT;
    while ((*flags & DEV_INTR) != DEV_INTR) {}
    *read_address = b;
    *write_address = VECTOR_B;
    *length = VADD_BYTES;
    *flags = DEV_INIT;
    while ((*flags & DEV_INTR) != DEV_INTR) {}
    *compute = DEV_INIT;
    while ((*compute & DEV_INTR) != DEV_INTR) {}
    *read_address = VECTOR_C;
    *write_address = c;
    *length = VADD_BYTES;
    *flags = DEV_INIT;
    while ((*flags & DEV_INTR) != DEV_INTR) {}
}
