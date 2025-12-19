/**
 * Viterbi Host Driver for gem5-SALAM
 * Hidden Markov Model decoding from MachSuite
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
static tok_t obs[N_OBS];
static state_t path[N_OBS];
static prob_t init[N_STATES];
static prob_t transition[N_STATES * N_STATES];
static prob_t emission[N_STATES * N_TOKENS];

/* Generate test data */
void genData(void)
{
    /* Generate random observations */
    for (int i = 0; i < N_OBS; i++) {
        obs[i] = rand() % N_TOKENS;
    }

    /* Initialize path to zeros */
    memset(path, 0, sizeof(path));

    /* Initialize probabilities (log space, so negative values) */
    for (int i = 0; i < N_STATES; i++) {
        init[i] = -log((TYPE)(i + 1) / N_STATES);
    }

    for (int i = 0; i < N_STATES * N_STATES; i++) {
        transition[i] = -log(((TYPE)(rand() % 100) + 1) / 100.0);
    }

    for (int i = 0; i < N_STATES * N_TOKENS; i++) {
        emission[i] = -log(((TYPE)(rand() % 100) + 1) / 100.0);
    }
}

int main(void)
{
    m5_reset_stats();

    /* SPM pointers */
    tok_t *spm_obs = (tok_t *)OBS_ADDR;
    state_t *spm_path = (state_t *)PATH_ADDR;
    prob_t *spm_init = (prob_t *)INIT_ADDR;
    prob_t *spm_transition = (prob_t *)TRANSITION_ADDR;
    prob_t *spm_emission = (prob_t *)EMISSION_ADDR;

    printf("Generating Viterbi test data\n");
    srand(42);
    genData();
    printf("Data generated - %d observations, %d states\n", N_OBS, N_STATES);

    /* Copy data to SPM via DMA */
    dmacpy(spm_obs, obs, sizeof(obs));
    while (!pollDma());
    resetDma();

    dmacpy(spm_path, path, sizeof(path));
    while (!pollDma());
    resetDma();

    dmacpy(spm_init, init, sizeof(init));
    while (!pollDma());
    resetDma();

    dmacpy(spm_transition, transition, sizeof(transition));
    while (!pollDma());
    resetDma();

    dmacpy(spm_emission, emission, sizeof(emission));
    while (!pollDma());
    resetDma();

    printf("Starting Viterbi accelerator\n");

    /* Start accelerator */
    *acc = 0x01;

    /* Wait for completion */
    while (*acc != 0x4) {
        /* spin */
    }

    printf("Viterbi decoding complete\n");

    /* Copy result back */
    dmacpy(path, spm_path, sizeof(path));
    while (!pollDma());

    *acc = 0x00;

    /* Verify path is valid (all states in valid range) */
    int valid = 1;
    for (int i = 0; i < N_OBS; i++) {
        if (path[i] >= N_STATES) {
            valid = 0;
            break;
        }
    }

    if (valid) {
        printf("Viterbi SUCCESS - valid path computed\n");
        printf("First 10 states: ");
        for (int i = 0; i < 10; i++) {
            printf("%d ", path[i]);
        }
        printf("...\n");
    } else {
        printf("Viterbi FAILED - invalid states in path\n");
    }

    m5_dump_stats();
    m5_exit();
    return 0;
}
