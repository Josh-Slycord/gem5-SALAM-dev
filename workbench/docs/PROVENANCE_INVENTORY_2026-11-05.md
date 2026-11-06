> **Historical Gemini inventory - unverified pin and attribution.**
>
> The original rows below are retained as evidence. Their auditor combined commit-pinned paths/history with working-tree bytes: 300 of 301 hashes match the claimed f3f437a29b pin, while syscalls.c records the later B1 bytes. Origin classifications and blanket rights notes below are unverified original assertions, not adopted ownership or licensing conclusions.
>
> The original JSON/Markdown bytes remain in Git commit 3c3f594d9bcc222e00226424d7f6c946c7746641. Use the corrected v2 auditor with an explicit accepted integration commit and newly named output files.

# Candidate Upstream Provenance & License Inventory

**Audit Snapshot Date:** 5 November 2026  
**Pinned Code Commit:** `f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb` (`gem5-26-integration-checkpoint-20261105`)  
**Candidate Scope:** Simulator core (`src/hwacc/`), configurations (`configs/SALAM/`), configurators (`SALAM-Configurator/`, `tools/`), generators, and bare-metal runtime (`benchmarks/common/`).

> [!IMPORTANT]
> This audit is an initial commit-pinned inventory of file origins, copyright headers, and license tags. It identifies provenance facts and open gaps; it does not constitute legal license clearance or assert maintainer commitments.

## Summary Metrics

- **Total candidate files audited:** 301
- **Files with explicit SPDX tags:** 10 / 301 (291 missing)
- **Files with copyright notices:** 7 / 301 (294 missing)
- **Duplicate tree copies flagged:** 6

### Provenance Classification Breakdown

| Classification | File Count | Description |
|---|---|---|
| `fork_addition` | 219 | New files authored in this fork (Josh-Slycord/gem5-SALAM-dev) |
| `gem5_core_or_derived` | 11 | Mainline gem5 SimObject bases or direct derivatives (UC Regents, AMD, ARM) |
| `third_party_cacti` | 9 | CACTI memory model tooling (HP Labs / third-party) |
| `third_party_kaiserslautern` | 1 | Bare-metal ARM runtime support (TU Kaiserslautern) |
| `uncc_salam` | 24 | Original UNC Charlotte SALAM research files (Sam Rogers et al.) |
| `unresolved_attribution` | 37 | Files with ambiguous, mixed, or missing authorship records |

## Open Licensing, Attribution & Maintainer Boundaries

- Original UNCC SALAM repository (2018-2022) had blanket or implicit BSD/MIT-style licensing across many generated and core files without per-file SPDX-License-Identifier tags.
- Files under tools/cacti-SALAM retain third-party CACTI (HP Labs) heritage with distinct licensing terms.
- Files under benchmarks/common (syscalls.c, Makefile) originate from TU Kaiserslautern bare-metal ARM test suites (Matthias Jung, Frederik Lauer).
- Duplicated configurator scripts exist in both root (SALAM-Configurator/) and tools/ (tools/SALAM-Configurator/, tools/hw_generator/).
- This inventory establishes current file provenance and identified gaps; it does not constitute legal clearance or assign maintainer commitments.

## High-Priority Candidate Files Entering Upstream Series

| Path | Bytes | SHA-256 (Prefix) | SPDX | Provenance Class | Earliest Author | Flags |
|---|---|---|---|---|---|---|
| `HWProfileGenerator.py` | 6271 | `b639604e46d1` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright, duplicate_in_tools_hw_generator |
| `SALAM-Configurator/fs_template.py` | 14975 | `0b513a7b1e03` | **MISSING** | `uncc_salam` | Zephan Spencer | missing_spdx, duplicate_in_tools_salam_configurator |
| `SALAM-Configurator/fs_template_old.py` | 15911 | `76b511a69e39` | **MISSING** | `gem5_core_or_derived` | Samuel Rogers | missing_spdx |
| `SALAM-Configurator/parser.py` | 28231 | `62e2e67deefa` | **MISSING** | `gem5_core_or_derived` | Zephan Spencer | missing_spdx, missing_copyright |
| `SALAM-Configurator/systembuilder.py` | 20427 | `3580f2fd3328` | **MISSING** | `uncc_salam` | Zephan Spencer | missing_spdx, missing_copyright, duplicate_in_tools_salam_configurator |
| `SALAM-Configurator/validate_generation.py` | 4398 | `c03ca4d4c7c8` | **MISSING** | `fork_addition` | jslycord | missing_spdx, missing_copyright |
| `SALAMArgs.py` | 252 | `96dec93c13d4` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright, duplicate_in_tools_hw_generator |
| `SALAMClassGenerator.py` | 37902 | `15cc1d466753` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright, duplicate_in_tools_hw_generator |
| `benchmarks/common/dma.h` | 519 | `c1a98254b815` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `benchmarks/common/m5ops.h` | 1432 | `81efc26a2985` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `benchmarks/common/queue_dma.c` | 1477 | `ab194f0b7789` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `benchmarks/common/queue_dma.h` | 668 | `cd774b0ad19c` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `benchmarks/common/syscalls.c` | 2211 | `385a6d45b478` | **MISSING** | `gem5_core_or_derived` | Samuel Rogers | missing_spdx, missing_copyright |
| `configs/SALAM/HWAcc.py` | 7410 | `ec374db7f705` | **MISSING** | `uncc_salam` | Sam Rogers | missing_spdx, missing_copyright |
| `configs/SALAM/HWAccConfig.py` | 16026 | `e227eaeda609` | **MISSING** | `uncc_salam` | Sam Rogers | missing_spdx, missing_copyright |
| `configs/SALAM/fs_hwacc.py` | 16348 | `f068032f5c0a` | **MISSING** | `uncc_salam` | Sam Rogers | missing_spdx |
| `configs/SALAM/fs_hwacc_input.py` | 17521 | `384dacae5768` | **MISSING** | `uncc_salam` | Arrvindh Shriraman | missing_spdx |
| `configs/SALAM/sys_validation.py` | 16638 | `0cac61783249` | **MISSING** | `uncc_salam` | Sam Rogers | missing_spdx |
| `configs/SALAM/validate_acc.py` | 7235 | `fdc1fa31c837` | **MISSING** | `uncc_salam` | Sam Rogers | missing_spdx, missing_copyright |
| `src/hwacc/AccCluster.py` | 3733 | `37ea0e2a7524` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/CommInterface.py` | 1840 | `9718b12ebf61` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/ComputeUnit.py` | 475 | `0d480107c9ea` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/CycleCounts.py` | 4975 | `43b7c01a791b` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/FunctionalUnits.py` | 26482 | `659ddd77e7e6` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWInterface.py` | 1120 | `448d1d1193a9` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/cacti_wrapper.cc` | 5119 | `843e2e893450` | **MISSING** | `third_party_cacti` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/cacti_wrapper.hh` | 274 | `bc46e32a57b4` | **MISSING** | `third_party_cacti` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/common/defines.hh` | 101 | `58f6802e1b5e` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/cycle_counts.cc` | 1891 | `8703efc0e35b` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/cycle_counts.hh` | 2028 | `29d6b3815c2d` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/functional_units.cc` | 1354 | `0820157a5c9e` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/functional_units.hh` | 1742 | `97d40d2a1fdc` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/hw_interface.cc` | 5519 | `ffd955f290d1` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/hw_interface.hh` | 1299 | `f7605c88c820` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/hw_statistics.cc` | 17705 | `21576ba2610c` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/hw_statistics.hh` | 5226 | `754fc239d5c8` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/instruction_config.cc` | 3379 | `b68b85f202d4` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/instruction_config.hh` | 3823 | `88949b236320` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/opcodes.cc` | 4291 | `3c66e0ac8fb4` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/opcodes.hh` | 1942 | `29230006487e` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/salam_power_model.cc` | 132 | `889f77010db6` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/salam_power_model.hh` | 827 | `13255f78b88d` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/simulator_config.cc` | 130 | `c051f8affb43` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWModeling/src/simulator_config.hh` | 389 | `610aa343131f` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/HWStatistics.py` | 1867 | `e83dc87237b1` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/IOAcc.py` | 965 | `392daeaf6173` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/InstConfig.py` | 26809 | `5dc7fd3380aa` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/InstOpCodes.py` | 3497 | `a38018a6193e` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMInterface.py` | 912 | `f86c73679e37` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/basic_block.cc` | 2862 | `cb2df589bfc8` | **MISSING** | `uncc_salam` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/basic_block.hh` | 1717 | `496be10309f6` | **MISSING** | `uncc_salam` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/debug_flags.cc` | 194 | `093c1b94e4e7` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/debug_flags.hh` | 1814 | `eecaf8885d69` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/function.cc` | 2036 | `742c4a6b503b` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/function.hh` | 1206 | `44bac991d798` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/instruction.cc` | 116900 | `3603fa41623f` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/instruction.hh` | 66914 | `d7110ef9f037` | **MISSING** | `fork_addition` | Joshua Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/ir_parse.cc` | 2381 | `4133d68b6a31` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/ir_parse.hh` | 713 | `78ffaea0cefb` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/macros.hh` | 2859 | `34ec6a5936bc` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/mem_request.cc` | 1483 | `ecf267739722` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/mem_request.hh` | 1169 | `3495a8d5a8fd` | **MISSING** | `gem5_core_or_derived` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/operand.cc` | 14965 | `d4d39636c4ae` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/operand.hh` | 3808 | `17a6c46ef865` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/registers.cc` | 9340 | `b852f47eaf75` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/registers.hh` | 8101 | `0a1e1113612c` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/value.cc` | 10614 | `045c63f65710` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/LLVMRead/src/value.hh` | 5658 | `839807abb4c5` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/NoncoherentDma.py` | 959 | `402e60b9a934` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/RegisterBank.py` | 429 | `db87f57c7442` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/SALAMPowerModel.py` | 1361 | `78066b53c87f` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/ScratchpadMemory.py` | 974 | `f6e01b381f6a` | **MISSING** | `unresolved_attribution` | Sam Rogers | missing_spdx, missing_copyright |
| `src/hwacc/Scripts/createDomain.py` | 2603 | `1b8b2dc10bf9` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/Scripts/extractFunctionUnits.py` | 687 | `a4d398a3c46d` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/Scripts/resetResults.py` | 259 | `e830d468eba2` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/Scripts/statParser.py` | 678 | `29b3d7f5cd70` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/Scripts/storeResults.py` | 678 | `e26fc00abafc` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/SimulatorConfig.py` | 648 | `7dbfbaa4c9c5` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/StreamBuffer.py` | 1079 | `f8bb04466b7b` | **MISSING** | `unresolved_attribution` | Sam Rogers | missing_spdx, missing_copyright |
| `src/hwacc/StreamDma.py` | 1511 | `c387b8d1a5cf` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/acc_cluster.cc` | 613 | `c1327ca333e9` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/acc_cluster.hh` | 1124 | `d2e1b4e2de6d` | **MISSING** | `gem5_core_or_derived` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/comm_interface.cc` | 38538 | `ae252b77c1ab` | **MISSING** | `uncc_salam` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/comm_interface.hh` | 9913 | `6b1dcfbd27c9` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/common/src/debug_flags.hh` | 1783 | `2afbf3a4863e` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/common/src/macros.hh` | 710 | `2f3054e1aace` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/compute_unit.cc` | 360 | `760560a85dfa` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/compute_unit.hh` | 1433 | `aab33a5fa61c` | **MISSING** | `uncc_salam` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/data_collection.cc` | 15163 | `a550ecbebec5` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/data_collection.hh` | 11776 | `9089a5e3d738` | **MISSING** | `fork_addition` | Josh Slycord | missing_spdx, missing_copyright |
| `src/hwacc/dma_write_fifo.cc` | 6356 | `75840264a3d8` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/dma_write_fifo.hh` | 5942 | `b182dacdda63` | **MISSING** | `gem5_core_or_derived` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/float_bits.hh` | 1333 | `f40968e240b8` | `BSD-3-Clause` | `fork_addition` | Joshua Slycord | missing_copyright |
| `src/hwacc/fu_scheduling_pool.hh` | 7432 | `56e9f3cb0e6a` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/fu_scheduling_pool.test.cc` | 4598 | `e5397f816c08` | **MISSING** | `fork_addition` | Joshua Slycord | missing_spdx, missing_copyright |
| `src/hwacc/gui_publisher.cc` | 8430 | `eef852bb9d4f` | **MISSING** | `fork_addition` | jslycord | missing_spdx, missing_copyright |
| `src/hwacc/gui_publisher.hh` | 5496 | `e45b1a51002d` | **MISSING** | `fork_addition` | jslycord | missing_spdx, missing_copyright |
| `src/hwacc/io_acc.cc` | 9943 | `7802c8347904` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/io_acc.hh` | 3485 | `d7479654455b` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/llvm_interface.cc` | 69539 | `24a84054ff93` | **MISSING** | `uncc_salam` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/llvm_interface.hh` | 9743 | `181280cb12dc` | **MISSING** | `uncc_salam` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/native_helpers.hh` | 1127 | `56c0435b7f64` | `BSD-3-Clause` | `fork_addition` | Joshua Slycord | missing_copyright |
| `src/hwacc/native_helpers.test.cc` | 1628 | `a0c9c3089d5d` | `BSD-3-Clause` | `fork_addition` | Joshua Slycord | missing_copyright |
| `src/hwacc/noncoherent_dma.cc` | 7163 | `21a8ea24bb15` | **MISSING** | `uncc_salam` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/noncoherent_dma.hh` | 2443 | `ef08dcfaa850` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/register_bank.cc` | 7520 | `e675230b3741` | **MISSING** | `uncc_salam` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/register_bank.hh` | 3808 | `7a7dbdc9dda0` | **MISSING** | `gem5_core_or_derived` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/response_queue.hh` | 1700 | `22a8aedb091a` | `BSD-3-Clause` | `fork_addition` | Joshua Slycord | missing_copyright |
| `src/hwacc/scratchpad_memory.cc` | 16987 | `de503567d604` | **MISSING** | `uncc_salam` | Sam Rogers | missing_spdx, missing_copyright |
| `src/hwacc/scratchpad_memory.hh` | 7252 | `4b8d1602715e` | **MISSING** | `gem5_core_or_derived` | Sam Rogers | missing_spdx, missing_copyright |
| `src/hwacc/stream_buffer.cc` | 6253 | `2f9baef4f449` | **MISSING** | `unresolved_attribution` | Sam Rogers | missing_spdx, missing_copyright |
| `src/hwacc/stream_buffer.hh` | 2196 | `a584a8f6b21a` | **MISSING** | `unresolved_attribution` | Sam Rogers | missing_spdx, missing_copyright |
| `src/hwacc/stream_dma.cc` | 12885 | `3ecb7137e1af` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/stream_dma.hh` | 6905 | `78447dd1b980` | **MISSING** | `unresolved_attribution` | Samuel Rogers | missing_spdx, missing_copyright |
| `src/hwacc/stream_port.cc` | 518 | `4da425c12829` | **MISSING** | `unresolved_attribution` | Sam Rogers | missing_spdx, missing_copyright |
| `src/hwacc/stream_port.hh` | 7769 | `32c0fa7b9b21` | **MISSING** | `gem5_core_or_derived` | Sam Rogers | missing_spdx, missing_copyright |
| `src/hwacc/tests/float_bits.test.cc` | 3011 | `aad06a84c040` | `BSD-3-Clause` | `fork_addition` | Joshua Slycord | missing_copyright |
| `src/hwacc/tests/response_queue.test.cc` | 4485 | `9de0ee1a3da2` | `BSD-3-Clause` | `fork_addition` | Joshua Slycord | missing_copyright |
| `src/hwacc/tests/test_fu_scheduling_pool.cc` | 4771 | `3660e0645f20` | **MISSING** | `fork_addition` | Josh-Slycord | missing_spdx, missing_copyright |
| `src/hwacc/tests/test_native_stats_reader.py` | 5792 | `b3c468322676` | `BSD-3-Clause` | `fork_addition` | Joshua Slycord | missing_copyright |
| `src/hwacc/tests/test_workbench_statistics.cc` | 4355 | `590b397a554d` | **MISSING** | `uncc_salam` | Codex | missing_spdx, missing_copyright |
| `src/hwacc/tests/verify_native_stats.py` | 9066 | `18974bc70cba` | `BSD-3-Clause` | `fork_addition` | Joshua Slycord | missing_copyright |
| `src/hwacc/workbench_statistics.hh` | 12317 | `d3107ef6414e` | **MISSING** | `uncc_salam` | Codex | missing_spdx, missing_copyright |
| `tools/SALAM-Configurator/config_parser.py` | 27368 | `6ed3dc5f7b07` | **MISSING** | `gem5_core_or_derived` | Zephan Spencer | missing_spdx, missing_copyright |
| `tools/SALAM-Configurator/fs_template.py` | 16533 | `7b0f09bb1176` | **MISSING** | `uncc_salam` | Zephan Spencer | missing_spdx |
| `tools/SALAM-Configurator/systembuilder.py` | 13972 | `717dae724856` | **MISSING** | `uncc_salam` | Zephan Spencer | missing_spdx, missing_copyright |
| `tools/cacti-SALAM/cactiWrapper.py` | 2590 | `c7a2fda7e50c` | **MISSING** | `third_party_cacti` | Zephan Spencer | missing_spdx, missing_copyright |
| `tools/hw_generator/HWProfileGenerator.py` | 6261 | `6290fc7373de` | **MISSING** | `uncc_salam` | Zephan Spencer | missing_spdx, missing_copyright |
| `tools/hw_generator/SALAMArgs.py` | 252 | `96dec93c13d4` | **MISSING** | `unresolved_attribution` | Zephan Spencer | missing_spdx, missing_copyright |
| `tools/hw_generator/SALAMClassGenerator.py` | 37902 | `15cc1d466753` | **MISSING** | `uncc_salam` | Zephan Spencer | missing_spdx, missing_copyright |
| `tools/hw_generator/SALAMInstructionGenerator.py` | 229 | `c01d546bf9df` | **MISSING** | `unresolved_attribution` | Zephan Spencer | missing_spdx, missing_copyright |

## Complete Inventory Reference

The full machine-readable inventory with per-file commit hashes and copyright strings is recorded in [PROVENANCE_INVENTORY_2026-11-05.json](PROVENANCE_INVENTORY_2026-11-05.json).
