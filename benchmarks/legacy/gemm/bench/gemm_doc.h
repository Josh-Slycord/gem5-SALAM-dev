/**
 * @file gemm.c
 * @brief General Matrix Multiplication (GEMM) Accelerator Kernel
 *
 * Implements C = A × B matrix multiplication for hardware acceleration.
 * This kernel is compiled to LLVM IR and executed on a gem5-SALAM
 * accelerator with configurable loop unrolling strategies.
 *
 * Algorithm Complexity:
 *   - Time: O(n³) for n×n matrices
 *   - Space: O(n²) for each matrix
 *
 * Memory Access Pattern:
 * @code
 *   For each row i in A:
 *     For each column j in B:
 *       sum = 0
 *       For each k (inner product):
 *         sum += A[i,k] * B[k,j]    // k-strided access for B
 *       C[i,j] = sum
 * @endcode
 *
 * Loop Structure:
 * @code
 *   Loop Level    Index   Bounds        Pragmas
 *   ----------    -----   ------        -------
 *   Outer         i       0..row_size   Optional unroll
 *   Middle        j       0..col_size   Optional unroll  
 *   Inner         k       0..row_size   #pragma unroll(full)
 * @endcode
 *
 * The inner loop (k) is fully unrolled by default to maximize
 * parallelism in the generated hardware datapath.
 *
 * @param m1   First input matrix (row_size × col_size)
 * @param m2   Second input matrix (row_size × col_size)
 * @param prod Output product matrix (row_size × col_size)
 *
 * @note Matrices are stored in row-major order as 1D arrays
 * @see gemm.h for type definitions and matrix dimensions
 * @see config.yml for functional unit configuration
 */
