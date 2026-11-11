// SPDX-License-Identifier: BSD-3-Clause
#include <stdint.h>
#include "bench.h"
extern volatile uint8_t *top;

void isr(void)
{
    ++stage;
    *top = 0;
}
