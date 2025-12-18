# Test Results

**2025-12-08 15:46** 9/10 passed

| Benchmark | Status | Message | Duration |
|-----------|--------|---------|----------|
| bfs | PASS | Completed | 2.8s |
| fft | PASS | Completed | 9.0s |
| gemm | PASS | Completed | 3.3s |
| md_grid | FAIL* | Timeout 600s | 600.0s |
| md_knn | PASS | Completed | 11.0s |
| mergesort | PASS | Completed | 222.2s |
| nw | PASS | Completed | 4.3s |
| spmv | PASS | Completed | 3.3s |
| stencil2d | PASS | Completed | 36.4s |
| stencil3d | PASS | Completed | 31.9s |

*Known issue

## Known Issues
- **md_grid**: Floating-point precision issue