#ifndef BACKPROP_H
#define BACKPROP_H

#include <math.h>

#include "../defines.h"

void backprop(
    TYPE *weights1,
    TYPE *weights2,
    TYPE *weights3,
    TYPE *biases1,
    TYPE *biases2,
    TYPE *biases3,
    TYPE *training_data,
    TYPE *training_targets);

void top();

#endif /* BACKPROP_H */
