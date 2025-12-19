/**
 * Backpropagation neural network training kernel
 * Ported from MachSuite for gem5-SALAM
 */
#include "backprop.h"

/* Sigmoid activation and derivative */
void sigmoid(TYPE activations[NODES_PER_LAYER],
             TYPE dactivations[NODES_PER_LAYER],
             int size) {
    int i;
    for (i = 0; i < size; i++) {
        dactivations[i] = activations[i] * (1.0 - activations[i]);
        activations[i] = 1.0 / (1.0 + exp(-activations[i]));
    }
}

/* Softmax for output layer */
void soft_max(TYPE net_outputs[POSSIBLE_OUT],
              TYPE activations[POSSIBLE_OUT]) {
    int i;
    TYPE sum = 0.0;
    for (i = 0; i < POSSIBLE_OUT; i++) {
        sum += exp(-activations[i]);
    }
    for (i = 0; i < POSSIBLE_OUT; i++) {
        net_outputs[i] = exp(-activations[i]) / sum;
    }
}

void add_bias(TYPE *biases, TYPE *activations, int size) {
    int i;
    for (i = 0; i < size; i++) {
        activations[i] += biases[i];
    }
}

/* Matrix-vector product for input layer */
void mvp_input_layer(TYPE *biases,
                     TYPE *weights,
                     TYPE *activations,
                     TYPE *input_sample) {
    int i, j;
    for (j = 0; j < NODES_PER_LAYER; j++) {
        activations[j] = 0.0;
        for (i = 0; i < INPUT_DIM; i++) {
            activations[j] += weights[j * INPUT_DIM + i] * input_sample[i];
        }
    }
    add_bias(biases, activations, NODES_PER_LAYER);
}

/* Matrix-vector product for hidden layer */
void mvp_hidden_layer(TYPE *biases,
                      TYPE *weights,
                      TYPE *activations,
                      TYPE *input_activations) {
    int i, j;
    for (i = 0; i < NODES_PER_LAYER; i++) {
        activations[i] = 0.0;
        for (j = 0; j < NODES_PER_LAYER; j++) {
            activations[i] += weights[i * NODES_PER_LAYER + j] * input_activations[j];
        }
    }
    add_bias(biases, activations, NODES_PER_LAYER);
}

/* Matrix-vector product for output layer */
void mvp_output_layer(TYPE *biases,
                      TYPE *weights,
                      TYPE *activations,
                      TYPE *input_activations) {
    int i, j;
    for (j = 0; j < POSSIBLE_OUT; j++) {
        activations[j] = 0.0;
        for (i = 0; i < NODES_PER_LAYER; i++) {
            activations[j] += weights[j * NODES_PER_LAYER + i] * input_activations[i];
        }
    }
    add_bias(biases, activations, POSSIBLE_OUT);
}

/* Compute output difference */
void take_difference(TYPE *net_outputs,
                     TYPE *solutions,
                     TYPE *output_difference,
                     TYPE *dactivations) {
    int i;
    for (i = 0; i < POSSIBLE_OUT; i++) {
        output_difference[i] = ((net_outputs[i] - solutions[i]) * -1.0) * dactivations[i];
    }
}

/* Delta matrix for weights3 */
void delta_weights3(TYPE *delta_w3,
                    TYPE *output_diff,
                    TYPE *last_act) {
    int i, j;
    for (i = 0; i < NODES_PER_LAYER; i++) {
        for (j = 0; j < POSSIBLE_OUT; j++) {
            delta_w3[i * POSSIBLE_OUT + j] = last_act[i] * output_diff[j];
        }
    }
}

/* Oracle activations for layer 2 */
void oracle_act2(TYPE *weights3,
                 TYPE *output_diff,
                 TYPE *oracle_act,
                 TYPE *dactivations) {
    int i, j;
    for (i = 0; i < NODES_PER_LAYER; i++) {
        oracle_act[i] = 0.0;
        for (j = 0; j < POSSIBLE_OUT; j++) {
            oracle_act[i] += output_diff[j] * weights3[i * POSSIBLE_OUT + j];
        }
        oracle_act[i] *= dactivations[i];
    }
}

/* Delta matrix for weights2 */
void delta_weights2(TYPE *delta_w2,
                    TYPE *output_diff,
                    TYPE *last_act) {
    int i, j;
    for (i = 0; i < NODES_PER_LAYER; i++) {
        for (j = 0; j < NODES_PER_LAYER; j++) {
            delta_w2[i * NODES_PER_LAYER + j] = last_act[i] * output_diff[j];
        }
    }
}

/* Oracle activations for layer 1 */
void oracle_act1(TYPE *weights2,
                 TYPE *output_diff,
                 TYPE *oracle_act,
                 TYPE *dactivations) {
    int i, j;
    for (i = 0; i < NODES_PER_LAYER; i++) {
        oracle_act[i] = 0.0;
        for (j = 0; j < NODES_PER_LAYER; j++) {
            oracle_act[i] += output_diff[j] * weights2[i * NODES_PER_LAYER + j];
        }
        oracle_act[i] *= dactivations[i];
    }
}

/* Delta matrix for weights1 */
void delta_weights1(TYPE *delta_w1,
                    TYPE *output_diff,
                    TYPE *last_act) {
    int i, j;
    for (i = 0; i < INPUT_DIM; i++) {
        for (j = 0; j < NODES_PER_LAYER; j++) {
            delta_w1[i * NODES_PER_LAYER + j] = last_act[i] * output_diff[j];
        }
    }
}

/* Update all weights with normalization */
void update_weights(TYPE *weights1, TYPE *weights2, TYPE *weights3,
                    TYPE *d_weights1, TYPE *d_weights2, TYPE *d_weights3,
                    TYPE *biases1, TYPE *biases2, TYPE *biases3,
                    TYPE *d_biases1, TYPE *d_biases2, TYPE *d_biases3) {
    int i, j;
    TYPE norm, bias_norm;

    /* Update weights1 */
    norm = 0.0;
    bias_norm = 0.0;
    for (i = 0; i < INPUT_DIM; i++) {
        for (j = 0; j < NODES_PER_LAYER; j++) {
            weights1[i * NODES_PER_LAYER + j] -= d_weights1[i * NODES_PER_LAYER + j] * LEARNING_RATE;
            norm += weights1[i * NODES_PER_LAYER + j] * weights1[i * NODES_PER_LAYER + j];
        }
    }
    for (i = 0; i < NODES_PER_LAYER; i++) {
        biases1[i] -= d_biases1[i] * LEARNING_RATE;
        bias_norm += biases1[i] * biases1[i];
    }
    norm = sqrt(norm);
    bias_norm = sqrt(bias_norm);
    for (i = 0; i < INPUT_DIM; i++) {
        for (j = 0; j < NODES_PER_LAYER; j++) {
            weights1[i * NODES_PER_LAYER + j] /= norm;
        }
    }
    for (i = 0; i < NODES_PER_LAYER; i++) {
        biases1[i] /= bias_norm;
    }

    /* Update weights2 */
    norm = 0.0;
    bias_norm = 0.0;
    for (i = 0; i < NODES_PER_LAYER; i++) {
        for (j = 0; j < NODES_PER_LAYER; j++) {
            weights2[i * NODES_PER_LAYER + j] -= d_weights2[i * NODES_PER_LAYER + j] * LEARNING_RATE;
            norm += weights2[i * NODES_PER_LAYER + j] * weights2[i * NODES_PER_LAYER + j];
        }
    }
    for (i = 0; i < NODES_PER_LAYER; i++) {
        biases2[i] -= d_biases2[i] * LEARNING_RATE;
        bias_norm += biases2[i] * biases2[i];
    }
    norm = sqrt(norm);
    bias_norm = sqrt(bias_norm);
    for (i = 0; i < NODES_PER_LAYER; i++) {
        for (j = 0; j < NODES_PER_LAYER; j++) {
            weights2[i * NODES_PER_LAYER + j] /= norm;
        }
    }
    for (i = 0; i < NODES_PER_LAYER; i++) {
        biases2[i] /= bias_norm;
    }

    /* Update weights3 */
    norm = 0.0;
    bias_norm = 0.0;
    for (i = 0; i < NODES_PER_LAYER; i++) {
        for (j = 0; j < POSSIBLE_OUT; j++) {
            weights3[i * POSSIBLE_OUT + j] -= d_weights3[i * POSSIBLE_OUT + j] * LEARNING_RATE;
            norm += weights3[i * POSSIBLE_OUT + j] * weights3[i * POSSIBLE_OUT + j];
        }
    }
    for (i = 0; i < POSSIBLE_OUT; i++) {
        biases3[i] -= d_biases3[i] * LEARNING_RATE;
        bias_norm += biases3[i] * biases3[i];
    }
    norm = sqrt(norm);
    bias_norm = sqrt(bias_norm);
    for (i = 0; i < NODES_PER_LAYER; i++) {
        for (j = 0; j < POSSIBLE_OUT; j++) {
            weights3[i * POSSIBLE_OUT + j] /= norm;
        }
    }
    for (i = 0; i < POSSIBLE_OUT; i++) {
        biases3[i] /= bias_norm;
    }
}

/* Main backpropagation kernel */
void backprop(TYPE *weights1, TYPE *weights2, TYPE *weights3,
              TYPE *biases1, TYPE *biases2, TYPE *biases3,
              TYPE *training_data, TYPE *training_targets) {
    int i, j;

    /* Local activations and derivatives */
    TYPE activations1[NODES_PER_LAYER];
    TYPE activations2[NODES_PER_LAYER];
    TYPE activations3[POSSIBLE_OUT];
    TYPE dactivations1[NODES_PER_LAYER];
    TYPE dactivations2[NODES_PER_LAYER];
    TYPE dactivations3[POSSIBLE_OUT];
    TYPE net_outputs[POSSIBLE_OUT];

    /* Training temporaries */
    TYPE output_difference[POSSIBLE_OUT];
    TYPE d_weights1[INPUT_DIM * NODES_PER_LAYER];
    TYPE d_weights2[NODES_PER_LAYER * NODES_PER_LAYER];
    TYPE d_weights3[NODES_PER_LAYER * POSSIBLE_OUT];
    TYPE oracle1[NODES_PER_LAYER];
    TYPE oracle2[NODES_PER_LAYER];

    /* Training loop */
    for (i = 0; i < TRAINING_SETS; i++) {
        /* Initialize activations */
        for (j = 0; j < NODES_PER_LAYER; j++) {
            activations1[j] = 0.0;
            activations2[j] = 0.0;
        }
        for (j = 0; j < POSSIBLE_OUT; j++) {
            activations3[j] = 0.0;
        }

        /* Forward pass */
        mvp_input_layer(biases1, weights1, activations1, &training_data[i * INPUT_DIM]);
        sigmoid(activations1, dactivations1, NODES_PER_LAYER);

        mvp_hidden_layer(biases2, weights2, activations2, activations1);
        sigmoid(activations2, dactivations2, NODES_PER_LAYER);

        mvp_output_layer(biases3, weights3, activations3, activations2);
        sigmoid(activations3, dactivations3, POSSIBLE_OUT);

        soft_max(net_outputs, activations3);

        /* Backward pass */
        take_difference(net_outputs, &training_targets[i * POSSIBLE_OUT], output_difference, dactivations3);

        delta_weights3(d_weights3, output_difference, activations2);
        oracle_act2(weights3, output_difference, oracle2, dactivations2);

        delta_weights2(d_weights2, oracle2, activations1);
        oracle_act1(weights2, oracle2, oracle1, dactivations1);

        delta_weights1(d_weights1, oracle1, &training_data[i * INPUT_DIM]);

        /* Update weights */
        update_weights(weights1, weights2, weights3,
                       d_weights1, d_weights2, d_weights3,
                       biases1, biases2, biases3,
                       oracle1, oracle2, output_difference);
    }
}

/* SALAM top entry point */
void top() {
    TYPE *weights1 = (TYPE *)WEIGHTS1_ADDR;
    TYPE *weights2 = (TYPE *)WEIGHTS2_ADDR;
    TYPE *weights3 = (TYPE *)WEIGHTS3_ADDR;
    TYPE *biases1 = (TYPE *)BIASES1_ADDR;
    TYPE *biases2 = (TYPE *)BIASES2_ADDR;
    TYPE *biases3 = (TYPE *)BIASES3_ADDR;
    TYPE *training_data = (TYPE *)TRAINING_DATA_ADDR;
    TYPE *training_targets = (TYPE *)TRAINING_TARGETS_ADDR;

    backprop(weights1, weights2, weights3,
             biases1, biases2, biases3,
             training_data, training_targets);
}
