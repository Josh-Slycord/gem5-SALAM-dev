/**
 * Backpropagation Host Driver for gem5-SALAM
 * Neural network training benchmark from MachSuite
 */

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "../../common/dma.h"
#include "../../common/m5ops.h"
#include "../defines.h"

/* Host data buffers */
static TYPE weights1[WEIGHTS1_SIZE];
static TYPE weights2[WEIGHTS2_SIZE];
static TYPE weights3[WEIGHTS3_SIZE];
static TYPE biases1[BIASES1_SIZE];
static TYPE biases2[BIASES2_SIZE];
static TYPE biases3[BIASES3_SIZE];
static TYPE training_data[TRAIN_DATA_SIZE];
static TYPE training_targets[TRAIN_TARG_SIZE];

/* Generate synthetic training data */
void genData(void)
{
    /* Initialize weights with small random values */
    for (int i = 0; i < WEIGHTS1_SIZE; i++) {
        weights1[i] = ((TYPE)rand() / RAND_MAX) * 0.1 - 0.05;
    }
    for (int i = 0; i < WEIGHTS2_SIZE; i++) {
        weights2[i] = ((TYPE)rand() / RAND_MAX) * 0.1 - 0.05;
    }
    for (int i = 0; i < WEIGHTS3_SIZE; i++) {
        weights3[i] = ((TYPE)rand() / RAND_MAX) * 0.1 - 0.05;
    }

    /* Initialize biases to zero */
    memset(biases1, 0, sizeof(biases1));
    memset(biases2, 0, sizeof(biases2));
    memset(biases3, 0, sizeof(biases3));

    /* Generate random training data */
    for (int i = 0; i < TRAIN_DATA_SIZE; i++) {
        training_data[i] = ((TYPE)rand() / RAND_MAX);
    }

    /* Generate one-hot encoded targets */
    for (int i = 0; i < TRAINING_SETS; i++) {
        int target = rand() % POSSIBLE_OUT;
        for (int j = 0; j < POSSIBLE_OUT; j++) {
            training_targets[i * POSSIBLE_OUT + j] = (j == target) ? 1.0 : 0.0;
        }
    }
}

int main(void)
{
    m5_reset_stats();

    /* SPM pointers */
    TYPE *spm_weights1 = (TYPE *)WEIGHTS1_ADDR;
    TYPE *spm_weights2 = (TYPE *)WEIGHTS2_ADDR;
    TYPE *spm_weights3 = (TYPE *)WEIGHTS3_ADDR;
    TYPE *spm_biases1 = (TYPE *)BIASES1_ADDR;
    TYPE *spm_biases2 = (TYPE *)BIASES2_ADDR;
    TYPE *spm_biases3 = (TYPE *)BIASES3_ADDR;
    TYPE *spm_train_data = (TYPE *)TRAINING_DATA_ADDR;
    TYPE *spm_train_targ = (TYPE *)TRAINING_TARGETS_ADDR;

    printf("Generating backprop training data\n");
    srand(42);
    genData();
    printf("Data generated\n");

    /* Copy data to SPM via DMA */
    printf("Copying data to SPM\n");

    dmacpy(spm_weights1, weights1, sizeof(weights1));
    while (!pollDma());
    resetDma();

    dmacpy(spm_weights2, weights2, sizeof(weights2));
    while (!pollDma());
    resetDma();

    dmacpy(spm_weights3, weights3, sizeof(weights3));
    while (!pollDma());
    resetDma();

    dmacpy(spm_biases1, biases1, sizeof(biases1));
    while (!pollDma());
    resetDma();

    dmacpy(spm_biases2, biases2, sizeof(biases2));
    while (!pollDma());
    resetDma();

    dmacpy(spm_biases3, biases3, sizeof(biases3));
    while (!pollDma());
    resetDma();

    dmacpy(spm_train_data, training_data, sizeof(training_data));
    while (!pollDma());
    resetDma();

    dmacpy(spm_train_targ, training_targets, sizeof(training_targets));
    while (!pollDma());
    resetDma();

    printf("Starting backprop accelerator\n");

    /* Start accelerator */
    *acc = 0x01;

    /* Wait for completion */
    while (*acc != 0x4) {
        /* spin */
    }

    printf("Backprop training complete\n");

    /* Copy updated weights back */
    dmacpy(weights1, spm_weights1, sizeof(weights1));
    while (!pollDma());
    resetDma();

    dmacpy(weights2, spm_weights2, sizeof(weights2));
    while (!pollDma());
    resetDma();

    dmacpy(weights3, spm_weights3, sizeof(weights3));
    while (!pollDma());

    *acc = 0x00;

    /* Verify weights were updated */
    int changed = 0;
    for (int i = 0; i < 10 && !changed; i++) {
        if (fabs(weights1[i]) > 0.05) {
            changed = 1;
        }
    }

    if (changed) {
        printf("Backprop SUCCESS - weights updated\n");
    } else {
        printf("Backprop WARNING - weights may not have changed\n");
    }

    m5_dump_stats();
    m5_exit();
    return 0;
}
