#ifndef KMP_H
#define KMP_H

#include "../defines.h"

int kmp(char *pattern, char *input, int32_t *kmpNext, int32_t *n_matches);

void top();

#endif /* KMP_H */
