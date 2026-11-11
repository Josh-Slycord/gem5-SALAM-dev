// SPDX-License-Identifier: BSD-3-Clause
#include "hw_defines.h"
_Static_assert(sizeof(TYPE) == VADD_ELEMENT_BYTES, "VADD width mismatch");
_Static_assert(VADD_LENGTH >= 1 && VADD_LENGTH <= 256, "VADD length range");

void vadd(void)
{
    const TYPE *a = (const TYPE *)VECTOR_A;
    const TYPE *b = (const TYPE *)VECTOR_B;
    TYPE *c = (TYPE *)VECTOR_C;
    for (int i = 0; i < VADD_LENGTH; ++i)
        c[i] = a[i] + b[i];
}
