#ifndef BACKPROP_DEFINES_H
#define BACKPROP_DEFINES_H

/* Neural network parameters - matching MachSuite */
#define INPUT_DIM       13
#define POSSIBLE_OUT    3
#define TRAINING_SETS   163
#define NODES_PER_LAYER 64
#define LAYERS          2
#define LEARNING_RATE   0.01
#define EPOCHS          1

/* Data type */
#define TYPE double

/* SPM Base Address */
#define SPM_BASE     0x2f100000

/* Memory layout (doubles = 8 bytes each):
 * weights1: 13*64 = 832 doubles = 6656 bytes
 * weights2: 64*64 = 4096 doubles = 32768 bytes
 * weights3: 64*3 = 192 doubles = 1536 bytes
 * biases1: 64 doubles = 512 bytes
 * biases2: 64 doubles = 512 bytes
 * biases3: 3 doubles = 24 bytes
 * training_data: 163*13 = 2119 doubles = 16952 bytes
 * training_targets: 163*3 = 489 doubles = 3912 bytes
 */
#define WEIGHTS1_ADDR        (SPM_BASE + 0x00000)
#define WEIGHTS2_ADDR        (SPM_BASE + 0x01A00)
#define WEIGHTS3_ADDR        (SPM_BASE + 0x09A00)
#define BIASES1_ADDR         (SPM_BASE + 0x0A000)
#define BIASES2_ADDR         (SPM_BASE + 0x0A200)
#define BIASES3_ADDR         (SPM_BASE + 0x0A400)
#define TRAINING_DATA_ADDR   (SPM_BASE + 0x0A420)
#define TRAINING_TARGETS_ADDR (SPM_BASE + 0x0E640)

/* Array sizes */
#define WEIGHTS1_SIZE   (INPUT_DIM * NODES_PER_LAYER)
#define WEIGHTS2_SIZE   (NODES_PER_LAYER * NODES_PER_LAYER)
#define WEIGHTS3_SIZE   (NODES_PER_LAYER * POSSIBLE_OUT)
#define BIASES1_SIZE    NODES_PER_LAYER
#define BIASES2_SIZE    NODES_PER_LAYER
#define BIASES3_SIZE    POSSIBLE_OUT
#define TRAIN_DATA_SIZE (TRAINING_SETS * INPUT_DIM)
#define TRAIN_TARG_SIZE (TRAINING_SETS * POSSIBLE_OUT)

#endif /* BACKPROP_DEFINES_H */
