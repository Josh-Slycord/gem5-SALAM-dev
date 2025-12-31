---
dir_type: config
domain: hardware-simulation
tags:
  - dir/type/compiled
  - dir/domain/hardware-simulation
  - dir/tech/llvm-ir
  - dir/purpose/streaming
---

# Cluster 2 IR

Compiled LLVM IR for double-precision and streaming accelerators.

## Files

| File | Description |
|------|-------------|
| top.ll | Top-level cluster IR |
| double_stress.ll | Double-precision FP accelerator IR |
| stream_producer.ll | Streaming producer accelerator IR |
| stream_consumer.ll | Streaming consumer accelerator IR |
