
#include <stdint.h>
#include <stdio.h>
#include "bench.h"
#include "../comprehensive_clstr_hw_defines.h"

volatile uint8_t * top = (uint8_t *)(CLUSTER0_TOP);

void isr(void)
{
    printf("Interrupt\n");
    stage += 1;
    *top = 0x00;
    printf("Interrupt finished\n");
}
