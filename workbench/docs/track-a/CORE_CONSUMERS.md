# Core configuration consumers: Track A

Pinned source `f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb`. Source-only audit in isolated Track A worktree. No new build, simulation, numerical test or GUI test. Qualified checkpoint/runtime evidence remains separate.

Companion `CORE_CONSUMERS.json` contains 59 grouped consumer records, 761 direct Param/VectorParam/port declarations, individual source lines, role-specific evidence, and 47 pinned source SHA-256 fingerprints. Inherited generic gem5 Params and ordinary topology helper arguments are not expanded.

## Important contracts

- FU limit zero means unlimited pooled occupancy. Nonzero instruction functional_unit_limit is rejected. Mapping/lease lifetime and special-path rejections are live scheduling contracts.
- Logical hw_config runtime_cycles reaches CycleCounts then scalar launch/commit. InstConfig.runtime_cycles is a distinct stored field with no production getter reader found in scope.
- Runtime integer-ns clock_period binds native domains and process_cycles sets service cadence. Profile characterization5ns is separate from default runtime10ns.
- FU stages/cycles/datatype descriptors/fu_latency are stored metadata in bounded searches. GUI acceptance and config.ini visibility alone do not establish execution effect.
- Four PPA coefficients print behind SALAMResults as uncalibrated inputs. Other coefficients/unit tags are stored; SALAMPowerModel remains scaffold. No physical power/energy/area claim follows.
- Memory/DMA/SPM/register/stream configuration has real endpoints listed below. RegisterBank has one scalar register port and one scalar preload port. StreamDma.mem_delay and devicename labels are stored-only in pair-file searches.
- HWStatistics.cycle_tracking=True is rejected. Native tick-weighted statistics and direct pre-pass invocation samples differ in reset/sampling semantics.
- Some CycleCounts fields lack current factory dispatch; memory/control/call special paths do not establish arbitrary nonzero latency support.
- SALAM_EXPORT_CDFG assigns undeclared export_cdfg with no matched C++ consumer. IOAcc is excluded from the selected build.
- Instruction.hasFunctionalUnit() returns false; LLVMInterface pooled admission is authoritative. Reviving legacy callbacks risks double accounting.

## Field classification endpoint map

| Record | Classification | Direct declarations |
| --- | --- | ---: |
| `fu_objects` | active_object_graph | 11 |
| `fu_identity` | active_scheduling_identity | 22 |
| `fu_limit` | active_scheduling_capacity | 11 |
| `fu_stages_cycles` | stored_metadata_no_production_reader_found | 22 |
| `fu_datatypes` | stored_metadata_no_production_reader_found | 99 |
| `fu_ppa_display` | coefficient_display_only | 44 |
| `fu_ppa_stored` | coefficient_stored_no_production_reader_found | 88 |
| `instruction_objects` | active_object_graph | 49 |
| `instruction_fu` | active_scheduling_mapping | 49 |
| `instruction_opcode` | active_mapping_identity | 49 |
| `instruction_limit` | rejected_when_nonzero | 49 |
| `instruction_runtime_stored` | stored_metadata_no_production_reader_found | 49 |
| `logical_runtime_transform` | active_python_transform | 0 |
| `cycle_compute` | active_instruction_latency | 34 |
| `cycle_special` | forwarded_special_path_limited_contract | 6 |
| `cycle_undispatched` | stored_without_current_dispatch | 19 |
| `opcode_bookkeeping` | observation_seed_metadata | 49 |
| `native_clock` | active_native_clock_compatibility_adapter | 3 |
| `profile_selection` | generation_selection_not_runtime_clock | 0 |
| `legacy_fu_callback` | disabled_legacy_scheduling_path | 0 |
| `compute_links` | active_object_graph | 2 |
| `hw_active_links` | active_object_graph | 4 |
| `hw_stats_link` | active_guard_for_rejected_legacy_tracking | 1 |
| `power_simulator_scaffold` | scaffold_object_links | 2 |
| `cycle_tracking` | rejected_when_true | 1 |
| `llvm_input` | active_program_selection | 2 |
| `llvm_scheduling` | active_scheduling_policy | 2 |
| `fu_trace_budget` | observation_budget | 1 |
| `process_cycles` | active_service_cadence | 2 |
| `device_name_stored` | stored_label_no_runtime_reader_found | 3 |
| `comm_mmio` | active_memory_interface | 3 |
| `comm_data_map` | active_address_mapping | 2 |
| `comm_cacheline` | active_request_partition | 1 |
| `comm_system_interrupt` | active_system_interrupt_binding | 3 |
| `comm_debug` | observation_control | 1 |
| `comm_reset_spm` | active_scratchpad_ready_state | 1 |
| `comm_ports` | active_port_routing | 5 |
| `dma_fifo` | active_dma_capacity_partition | 3 |
| `dma_mmio` | active_mmio_mapping_latency | 3 |
| `dma_interrupt` | active_interrupt_binding | 2 |
| `dma_port` | active_port_routing | 1 |
| `scratchpad_ready` | active_ready_protocol | 4 |
| `scratchpad_timing` | active_memory_timing | 3 |
| `scratchpad_ports` | active_port_routing | 2 |
| `register_bank` | active_register_timing_ports | 3 |
| `stream_buffer` | active_stream_capacity_mapping_timing | 8 |
| `stream_buffer_ports` | active_stream_ports | 4 |
| `stream_dma_fifo` | active_stream_dma_capacity | 4 |
| `stream_dma_map` | active_stream_mapping_timing | 8 |
| `stream_dma_interrupt` | active_interrupt_binding | 3 |
| `stream_dma_ports` | active_stream_ports | 4 |
| `stream_dma_memdelay` | stored_metadata_no_runtime_reader_found | 1 |
| `cluster_metadata` | declared_metadata_no_cpp_consumer_found | 7 |
| `cluster_system` | object_graph_reference_stored | 1 |
| `ioacc_legacy` | legacy_not_registered_in_selected_build | 11 |
| `native_statistics` | active_observation | 0 |
| `custom_statistics` | active_observation | 0 |
| `cdfg_stale_switch` | unimplemented_parameter_path | 0 |
| `build_selection` | active_build_gate | 0 |

## Critical sources

- `fu_limit`: [src/hwacc/llvm_interface.cc:908](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L908); [src/hwacc/llvm_interface.cc:919](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L919); [src/hwacc/llvm_interface.cc:955](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L955).
- `instruction_limit`: [src/hwacc/llvm_interface.cc:958](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L958).
- `logical_runtime_transform`: [src/hwacc/llvm_interface.cc:1339](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L1339).
- `instruction_runtime_stored`: [src/hwacc/HWModeling/generated/instructions/base.hh:20](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/HWModeling/generated/instructions/base.hh#L20); [src/hwacc/HWModeling/generated/instructions/base.hh:31](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/HWModeling/generated/instructions/base.hh#L31).
- `native_clock`: [src/hwacc/llvm_interface.cc:23](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L23); [src/hwacc/llvm_interface.cc:495](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L495); [src/hwacc/comm_interface.cc:65](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/comm_interface.cc#L65).
- `fu_stages_cycles`: [src/hwacc/HWModeling/generated/functionalunits/base.hh:54](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/HWModeling/generated/functionalunits/base.hh#L54); [src/hwacc/HWModeling/generated/functionalunits/base.hh:114](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/HWModeling/generated/functionalunits/base.hh#L114); [src/hwacc/HWModeling/generated/functionalunits/base.hh:115](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/HWModeling/generated/functionalunits/base.hh#L115).
- `fu_ppa_display`: [src/hwacc/llvm_interface.cc:1090](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L1090); [src/hwacc/llvm_interface.cc:1115](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L1115); [src/hwacc/llvm_interface.cc:1121](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L1121).
- `cycle_tracking`: [src/hwacc/HWModeling/src/hw_statistics.cc:7](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/HWModeling/src/hw_statistics.cc#L7); [src/hwacc/llvm_interface.cc:239](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L239).
- `cdfg_stale_switch`: [configs/SALAM/HWAccConfig.py:323](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/configs/SALAM/HWAccConfig.py#L323); [configs/SALAM/HWAccConfig.py:325](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/configs/SALAM/HWAccConfig.py#L325).
- `legacy_fu_callback`: [src/hwacc/LLVMRead/src/instruction.hh:81](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/LLVMRead/src/instruction.hh#L81); [src/hwacc/LLVMRead/src/instruction.cc:161](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/LLVMRead/src/instruction.cc#L161); [src/hwacc/llvm_interface.cc:908](https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb/src/hwacc/llvm_interface.cc#L908).

## Scope and next validation

Bounded getter/backing-member searches in src/hwacc C++. Device devname and StreamDma memDelay scoped to corresponding .cc/.hh pairs. Six AccCluster range identifiers scoped to src/configs. These findings do not assert absence in private/downstream code. Each record has producer/transform/Params/consumer/storage roles, semantics, units, source-only confidence and unresolved questions. Empty consumer lists avoid inventing endpoints.

- Compare effective config.ini/json, generated source hashes and native Params after extraction.
- Use numerical positive/deliberate-negative output checks and real simulation setting sensitivity, not guest PASS text.
- Preserve FU zero/unlimited, finite lease lifetime, instruction-limit and constrained-special-path rejection contracts.
- Qualify native runtime clocks independently of characterization period and CycleCounts.
- Keep load/store zero and special latency limits until separately demonstrated.
- Keep PPA labeled coefficients until calibrated activation/unit/aggregation model exists.
- Do not revive legacy FU callbacks or IOAcc during factory extraction.

All records use `validation_state=source_traced_not_new_runtime_tested`. A regenerated file, successful build or existing result is not new runtime sensitivity evidence. Prior qualified runs must be cited separately.
