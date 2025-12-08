# Test Results

**2025-12-08 13:26** 9/10 passed

| Benchmark | Status | Message | Duration |
|-----------|--------|---------|----------|
| bfs | PASS | Completed | 2.8s |
| fft | PASS | Completed | 8.5s |
| gemm | PASS | Completed | 3.1s |
| md_grid | FAIL* | Timeout 300s | 300.0s |
| md_knn | PASS | Completed | 10.7s |
| mergesort | PASS | Completed | 217.7s |
| nw | PASS | Completed | 4.3s |
| spmv | PASS | Completed | 3.3s |
| stencil2d | PASS | Completed | 36.1s |
| stencil3d | PASS | Completed | 31.3s |

*Known issue

## Known Issues
- **md_grid**: Floating-point precision issue