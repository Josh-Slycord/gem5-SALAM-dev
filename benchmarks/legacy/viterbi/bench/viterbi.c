/**
 * Viterbi algorithm for Hidden Markov Models
 * Ported from MachSuite for gem5-SALAM
 * Based on: Lawrence Rabiner. "A Tutorial on Hidden Markov Models
 * and Selected Applications in Speech Recognition."
 * Proc. IEEE, v77, #2. 1989.
 */
#include "viterbi.h"

int viterbi(tok_t *obs, prob_t *init, prob_t *transition,
            prob_t *emission, state_t *path) {
    prob_t llike[N_OBS][N_STATES];
    step_t t;
    state_t prev, curr;
    prob_t min_p, p;
    state_t min_s, s;

    /* All probabilities are in -log space. (i.e.: P(x) => -log(P(x))) */

    /* Initialize with first observation and initial probabilities */
    for (s = 0; s < N_STATES; s++) {
        llike[0][s] = init[s] + emission[s * N_TOKENS + obs[0]];
    }

    /* Iteratively compute the probabilities over time */
    for (t = 1; t < N_OBS; t++) {
        for (curr = 0; curr < N_STATES; curr++) {
            /* Compute likelihood HMM is in current state */
            prev = 0;
            min_p = llike[t - 1][prev] +
                    transition[prev * N_STATES + curr] +
                    emission[curr * N_TOKENS + obs[t]];
            for (prev = 1; prev < N_STATES; prev++) {
                p = llike[t - 1][prev] +
                    transition[prev * N_STATES + curr] +
                    emission[curr * N_TOKENS + obs[t]];
                if (p < min_p) {
                    min_p = p;
                }
            }
            llike[t][curr] = min_p;
        }
    }

    /* Identify end state */
    min_s = 0;
    min_p = llike[N_OBS - 1][min_s];
    for (s = 1; s < N_STATES; s++) {
        p = llike[N_OBS - 1][s];
        if (p < min_p) {
            min_p = p;
            min_s = s;
        }
    }
    path[N_OBS - 1] = min_s;

    /* Backtrack to recover full path */
    for (t = N_OBS - 2; t >= 0; t--) {
        min_s = 0;
        min_p = llike[t][min_s] + transition[min_s * N_STATES + path[t + 1]];
        for (s = 1; s < N_STATES; s++) {
            p = llike[t][s] + transition[s * N_STATES + path[t + 1]];
            if (p < min_p) {
                min_p = p;
                min_s = s;
            }
        }
        path[t] = min_s;
    }

    return 0;
}

/* SALAM top entry point */
void top() {
    tok_t *obs = (tok_t *)OBS_ADDR;
    prob_t *init = (prob_t *)INIT_ADDR;
    prob_t *transition = (prob_t *)TRANSITION_ADDR;
    prob_t *emission = (prob_t *)EMISSION_ADDR;
    state_t *path = (state_t *)PATH_ADDR;

    viterbi(obs, init, transition, emission, path);
}
