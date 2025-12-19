#ifndef VITERBI_H
#define VITERBI_H

#include "../defines.h"

int viterbi(tok_t *obs, prob_t *init, prob_t *transition,
            prob_t *emission, state_t *path);
void top();

#endif /* VITERBI_H */
