# Legacy configuration consumer audit

Baseline: `f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb` on `codex/native-gem5-milestone`.

This is a source-only audit of retained configurator routes and Workbench adapters. It records producers, transformations, generated assignments, defaults and validation limits. It does not qualify a new run. Accepting or storing a value is not proof it affects simulated behavior. No production source, qualified checkpoint, runtime or official repository was changed for this audit.

The companion [JSON inventory](LEGACY_CONFIG_CONSUMERS.json) contains 56 grouped field records, source line references and SHA-256 snapshots of each cited file. Families stay distinct when the same spelling has a different base, stage or role. The separate YAML occurrence census contains 276 tracked files and 56,186 key occurrences (348 normalized patterns); neither figure counts working controls. Its 122 duplicate-key occurrences in seven files all repeat identically serialized values (zero different values). No conflicting-value change is demonstrated; retained duplicate syntax remains a migration ambiguity and hygiene issue.

## Findings that determine the native configuration contract

- Paths are dialect-specific. Root IrPath is engine-relative; tools IrPath is benchmark-working-directory-relative. Raw root ConfigPath is commented out; Workbench stages a contained-YAML adapter. Cluster SysPath/HWPath and accelerator HWPath are separate tools-only paths with different concatenation rules. Old .ini examples are not valid current hardware YAML.
- Defaults disagree across template, parser constructor and native SimObject. DMA sizes called optional in the template are directly indexed before constructor defaults apply. Missing noncoherent InterruptNum produces native interrupt 200; omission does not disable IRQ. Missing PIOMaster emits no PIO edge although the checked validator substitutes LocalBus for its acceptance test.
- SPM and RegisterBank are distinct memory contracts. Raw bank generation ignores port counts. The staged adapter preserves requested cardinality, but the compiled bank has one scalar private response port. A generated loop cannot create native multiport memory semantics.
- There are three cache families: CPU caches, generated per-accelerator L1Cache variables, and optional cluster cache. The generated cluster call passes no nonzero cache size, leaving its branch dormant despite an AccCluster cache_size parameter. Cache Variable source support is broader than current checked Workbench admission.
- Hardware profiles, runtime YAML overrides and offline CACTI are different channels. Raw profile generation selects 5ns despite a 10ns class default, can overwrite instruction FU mappings, and emits fractional power coefficients as UInt32. Checked staging sorts inputs, selects the profile and patches seven fields to Float. This does not establish calibrated power.
- The duplicated CACTI wrapper visits only the first object of each Var list, requires explicit Ports, clamps modeled capacity to 2048 bytes and uses fixed 45nm assumptions. CSV output is not automatically measured run energy, and its technology differs from the named 40nm FU profile.
- Unknown fields generally disappear through raw consumers. The checked schema closes many gaps but still accepts stream-only fields on SPM/RegisterBank, does not reject repeated scalar fields across accelerator list entries, and validates stripped connection syntax that raw generation does not strip. SPM connection existence/cardinality lacks an independent effective-peer expectation here.
- A stale behavioral_limits literal says FU scheduling is disabled. Use the companion core audit and actual capability evidence as authority; this literal is not a current scheduler gate.

## Migration order

1. Define one typed authored document plus explicit legacy dialect importer. Preserve original bytes and exact conversions. Reject ambiguous duplicate keys and cross-list duplicate scalar definitions.
2. Resolve paths, defaults, identifiers, connection references and allocated addresses once. Use that normalized object for factory construction and effective-state expectations.
3. Define per-memory-type allowed fields and native port cardinality. Preserve unsupported Stream/Cache routes as unresolved inventory until each has simulator witnesses.
4. Keep runtime overrides, generated model defaults and external characterization separate. Replace template patching only after equivalent native routing and rebuild identity checks are demonstrated.
5. Add source/generated/effective port witnesses and deliberate negative cases for each uncovered acceptance gap. Test omitted defaults separately from explicit values.

Legacy comprehensive-test clusterN examples retain an additional unresolved dialect. A bounded implementation search found no demonstrated reader for those producer spellings. GUI global.memory is different: current GUI metadata conversion exists, and record L056 traces it explicitly.

## Record inventory

All entries have validation state source_only. Unsupported checked route means Workbench withholds admission; it does not mean no legacy implementation exists.

### L001 - documents[*].acc_cluster[*].Name

Each YAML document is processed as a cluster. The root generator gathers Name/DMA/Accelerator entries; device generation is ordered all DMAs, then all accelerators. Names become Python attributes/function identifiers; accelerator names are lowercased.

Defaults: None in raw generator; Workbench requires exactly one Python-safe cluster name and checks case-insensitive duplicates.

Validation: Strict Workbench structure; raw generator ignores unrelated root/list keys.

Disposition: normalize_across_consumers.

Producer: [SALAM-Configurator/template.yml:1](../../../SALAM-Configurator/template.yml#L1), [workbench/salam_workbench/gui_editor.py:257](../../../workbench/salam_workbench/gui_editor.py#L257).

Transform: [SALAM-Configurator/systembuilder.py:265](../../../SALAM-Configurator/systembuilder.py#L265), [tools/SALAM-Configurator/systembuilder.py:105](../../../tools/SALAM-Configurator/systembuilder.py#L105).

Consumer: [SALAM-Configurator/parser.py:284](../../../SALAM-Configurator/parser.py#L284), [workbench/salam_workbench/config_contract.py:324](../../../workbench/salam_workbench/config_contract.py#L324), [workbench/salam_workbench/config_contract.py:347](../../../workbench/salam_workbench/config_contract.py#L347).

Unresolved: Raw tools parser supports SysPath/HWPath recursion, while checked Workbench accepts only Name/DMA/Accelerator cluster items.

### L002 - base_address / --base-address / implicit cluster address allocation

Root CLI permits a custom initial address. DMA MMIO consumes padded21 bytes (Stream32+status4); accelerator PIOSize and memory Size are padded using size+(64-size%64), so already aligned sizes still advance another64. Next cluster adds another alignment step.

Defaults: 0x10020000 initial; raw maximum0x13ffffff warning only.

Validation: Workbench enforces64-byte alignment in0x10020000..0x13ffffff and rejects computed end>=0x14000000.

Disposition: normalize_across_consumers.

Producer: [workbench/salam_workbench/gui_editor.py:535](../../../workbench/salam_workbench/gui_editor.py#L535).

Transform: [SALAM-Configurator/systembuilder.py:124](../../../SALAM-Configurator/systembuilder.py#L124), [SALAM-Configurator/systembuilder.py:285](../../../SALAM-Configurator/systembuilder.py#L285), [SALAM-Configurator/parser.py:54](../../../SALAM-Configurator/parser.py#L54), [SALAM-Configurator/parser.py:155](../../../SALAM-Configurator/parser.py#L155).

Consumer: [workbench/salam_workbench/config_contract.py:157](../../../workbench/salam_workbench/config_contract.py#L157), [workbench/salam_workbench/config_contract.py:847](../../../workbench/salam_workbench/config_contract.py#L847), [workbench/salam_workbench/configurator.py:117](../../../workbench/salam_workbench/configurator.py#L117).

Unresolved: Padding is historical behavior, not conventional round-up; preserve or explicitly version it.

### L003 - acc_cluster[*].DMA[*].Name / Type

Raw parser dispatches Type by substring NonCoherent or Stream and lowercases device names. An unrecognized DMA type has no explicit else rejection in the raw dispatch. Checked contract requires exact NonCoherent and safe unique names.

Defaults: No raw YAML default.

Validation: Raw accepts a wider spelling space; checked Stream path is deliberately unsupported pending a simulator witness.

Disposition: normalize_across_consumers.

Producer: [workbench/salam_workbench/gui_editor.py:274](../../../workbench/salam_workbench/gui_editor.py#L274).

Consumer: [SALAM-Configurator/parser.py:23](../../../SALAM-Configurator/parser.py#L23), [SALAM-Configurator/parser.py:56](../../../SALAM-Configurator/parser.py#L56), [SALAM-Configurator/parser.py:469](../../../SALAM-Configurator/parser.py#L469), [workbench/salam_workbench/config_contract.py:415](../../../workbench/salam_workbench/config_contract.py#L415).

Unresolved: Do not label Stream impossible: source generator support exists but checked acceptance is withheld.

### L004 - acc_cluster[*].DMA[*].BufferSize / MaxReqSize (NonCoherent)

Raw parser directly indexes both keys and generated assignments set NoncoherentDma.buffer_size and max_req_size. Constructor defaults64/4 do not rescue missing YAML because indexing occurs before construction.

Defaults: Template calls both optional; raw constructor64/4; native SimObject1024/Parent.cache_line_size; actual YAML must supply values on this route.

Validation: Workbench requires positive UInt32 values and MaxReqSize<=BufferSize.

Disposition: normalize_across_consumumers.

Producer: [SALAM-Configurator/template.yml:8](../../../SALAM-Configurator/template.yml#L8), [workbench/salam_workbench/gui_editor.py:275](../../../workbench/salam_workbench/gui_editor.py#L275).

Transform: [SALAM-Configurator/parser.py:37](../../../SALAM-Configurator/parser.py#L37), [SALAM-Configurator/parser.py:50](../../../SALAM-Configurator/parser.py#L50).

Consumer: [SALAM-Configurator/parser.py:513](../../../SALAM-Configurator/parser.py#L513), [src/hwacc/NoncoherentDma.py:13](../../../src/hwacc/NoncoherentDma.py#L13), [workbench/salam_workbench/config_contract.py:431](../../../workbench/salam_workbench/config_contract.py#L431).

Unresolved: Default family must be explicit in native factory; do not silently choose one of three conflicting layers.

### L005 - acc_cluster[*].DMA[*].InterruptNum

When YAML omits InterruptNum, generated NoncoherentDma constructor omits int_num, exposing native default200. Omission is not IRQ disabling.

Defaults: Raw Dma.int_num=None; native NoncoherentDma.int_num=200.

Validation: Workbench validates and witnesses only an explicitly supplied interrupt; omitted native200 is not inserted into expected_effective.

Disposition: normalize_across_consumers.

Producer: [SALAM-Configurator/template.yml:14](../../../SALAM-Configurator/template.yml#L14), [workbench/salam_workbench/gui_editor.py:282](../../../workbench/salam_workbench/gui_editor.py#L282).

Transform: [SALAM-Configurator/parser.py:41](../../../SALAM-Configurator/parser.py#L41), [SALAM-Configurator/parser.py:500](../../../SALAM-Configurator/parser.py#L500).

Consumer: [src/hwacc/NoncoherentDma.py:17](../../../src/hwacc/NoncoherentDma.py#L17), [workbench/salam_workbench/config_contract.py:472](../../../workbench/salam_workbench/config_contract.py#L472).

Unresolved: Record and test omitted default separately from explicit IRQ0/200; no simulator proof in this audit.

### L006 - acc_cluster[*].DMA[*].PIOMaster

Raw comma-splits without stripping whitespace; LocalBus is normalized case-insensitively by substring to local_bus for DMA, then generates named bus.mem_side_ports -> DMA.pio. Missing field leaves an empty connection list.

Defaults: Raw missing=[]; Workbench validation uses get(...,'LocalBus') when absent.

Validation: Workbench accepts only literal LocalBus, yet omitted field is accepted by its default without generating the same connection.

Disposition: normalization_gap.

Producer: [SALAM-Configurator/template.yml:10](../../../SALAM-Configurator/template.yml#L10), [workbench/salam_workbench/gui_editor.py:281](../../../workbench/salam_workbench/gui_editor.py#L281).

Transform: [SALAM-Configurator/parser.py:25](../../../SALAM-Configurator/parser.py#L25), [SALAM-Configurator/parser.py:478](../../../SALAM-Configurator/parser.py#L478).

Consumer: [SALAM-Configurator/parser.py:516](../../../SALAM-Configurator/parser.py#L516), [workbench/salam_workbench/config_contract.py:448](../../../workbench/salam_workbench/config_contract.py#L448).

Unresolved: Require explicit LocalBus or materialize canonical default before generation; compare ports, not merely config scalar values.

### L007 - acc_cluster[*].DMA[*].BufferSize (Stream)

Raw Stream DMA BufferSize is passed as StreamDma.size and emitted as stream_size (interface width), not read_buffer_size/write_buffer_size capacity. It also emits max_pending=pioSize32 and pio_delay1ns.

Defaults: Template labels BufferSize optional; raw directly indexes it. Native stream_size8, max_pending8, pio_delay100ns are replaced by generated values.

Validation: Workbench rejects Stream DMA pending independent witness.

Disposition: normalize_across_consumers.

Producer: [SALAM-Configurator/template.yml:21](../../../SALAM-Configurator/template.yml#L21).

Transform: [SALAM-Configurator/parser.py:81](../../../SALAM-Configurator/parser.py#L81), [SALAM-Configurator/parser.py:123](../../../SALAM-Configurator/parser.py#L123).

Consumer: [SALAM-Configurator/parser.py:437](../../../SALAM-Configurator/parser.py#L437), [SALAM-Configurator/parser.py:444](../../../SALAM-Configurator/parser.py#L444), [src/hwacc/StreamDma.py:15](../../../src/hwacc/StreamDma.py#L15), [src/hwacc/StreamDma.py:21](../../../src/hwacc/StreamDma.py#L21).

Unresolved: Potentially misleading name: do not interpret this field as native buffer storage size.

### L008 - acc_cluster[*].DMA[*].ReadInt / WriteInt

Raw Stream DMA separately emits rd_int/wr_int only if given. Native omitted defaults210/211 remain. Checked NonCoherent rejects these stream-only interrupt fields.

Defaults: Stream rd_int210 / wr_int211; no IRQ-disable sentinel established.

Validation: Source-supported stream route but checked unsupported as a whole; inappropriate NonCoherent fields fail explicitly.

Disposition: unsupported_checked_route.

Producer: [SALAM-Configurator/template.yml:23](../../../SALAM-Configurator/template.yml#L23).

Transform: [SALAM-Configurator/parser.py:69](../../../SALAM-Configurator/parser.py#L69).

Consumer: [SALAM-Configurator/parser.py:446](../../../SALAM-Configurator/parser.py#L446), [src/hwacc/StreamDma.py:26](../../../src/hwacc/StreamDma.py#L26), [workbench/salam_workbench/config_contract.py:424](../../../workbench/salam_workbench/config_contract.py#L424).

### L009 - acc_cluster[*].Accelerator[*].Name / IrPath

Root generator constructs literal M5_PATH+'/'+IrPath and passes it to AccConfig. Tools generator prefixes benchmark working_dir+'/'+IrPath instead, so identical relative text has different bases. Accelerator lowercasing and HW lookup by IR basename impose another identity constraint.

Defaults: irPath initializedNone; missing causes later code-generation failure rather than a semantic default.

Validation: Workbench requires safe relative .ll, no absolute/backslash/colon/dot segments; requires IR stem==lowercase accelerator name.

Disposition: normalize_across_consumers.

Producer: [SALAM-Configurator/template.yml:28](../../../SALAM-Configurator/template.yml#L28), [workbench/salam_workbench/gui_editor.py:288](../../../workbench/salam_workbench/gui_editor.py#L288).

Transform: [SALAM-Configurator/parser.py:161](../../../SALAM-Configurator/parser.py#L161), [tools/SALAM-Configurator/config_parser.py:171](../../../tools/SALAM-Configurator/config_parser.py#L171).

Consumer: [SALAM-Configurator/parser.py:303](../../../SALAM-Configurator/parser.py#L303), [tools/SALAM-Configurator/config_parser.py:313](../../../tools/SALAM-Configurator/config_parser.py#L313), [workbench/salam_workbench/config_contract.py:168](../../../workbench/salam_workbench/config_contract.py#L168), [workbench/salam_workbench/config_contract.py:577](../../../workbench/salam_workbench/config_contract.py#L577).

Unresolved: Normalize paths from declared source root; preserve originating dialect. Do not treat paths relative to YAML by assumption.

### L010 - acc_cluster[*].Accelerator[*].ConfigPath (raw root dialect)

Root parser initializes configPath to the topology configFile and its ConfigPath handling is commented out; AccConfig sees the primary YAML. Template still describes ConfigPath required and illustrates .ini.

Defaults: Primary topology configFile wins regardless of raw ConfigPath.

Validation: Raw field is ignored, not implemented. Checked route accepts it only with verified staged adapter.

Disposition: ignored_raw_field.

Producer: [SALAM-Configurator/template.yml:30](../../../SALAM-Configurator/template.yml#L30).

Transform: [SALAM-Configurator/parser.py:143](../../../SALAM-Configurator/parser.py#L143).

Consumer: [SALAM-Configurator/parser.py:163](../../../SALAM-Configurator/parser.py#L163), [SALAM-Configurator/parser.py:304](../../../SALAM-Configurator/parser.py#L304).

Unresolved: Old .ini reference is unsupported by current YAML consumer, not a path alias to adopt.

### L011 - acc_cluster[*].Accelerator[*].ConfigPath (Workbench adapter)

Source-bound staged parser patch activates ConfigPath; it resolves strictly contained portable benchmarks/... or configs/... YAML and copies/source-hashes external files. One mapping must contain nonempty hw_config keyed by IR stem. Primary same-name hardware is rejected as shadowed.

Defaults: Absent -> primary topology config; present -> explicit external YAML.

Validation: Fail-closed parser-anchor/source checks; no production parser mutation.

Disposition: normalize_across_consumers.

Producer: [workbench/salam_workbench/gui_editor.py:294](../../../workbench/salam_workbench/gui_editor.py#L294).

Transform: [workbench/salam_workbench/topology_adapter.py:24](../../../workbench/salam_workbench/topology_adapter.py#L24), [workbench/salam_workbench/topology_adapter.py:34](../../../workbench/salam_workbench/topology_adapter.py#L34), [workbench/salam_workbench/topology_adapter.py:118](../../../workbench/salam_workbench/topology_adapter.py#L118).

Consumer: [workbench/salam_workbench/config_contract.py:235](../../../workbench/salam_workbench/config_contract.py#L235), [workbench/salam_workbench/config_contract.py:871](../../../workbench/salam_workbench/config_contract.py#L871).

Unresolved: Native factory should replace staged textual patch with shared typed path contract; .ini remains rejected.

### L012 - acc_cluster[*].SysPath / HWPath (tools dialect)

Tools systembuilder recursively opens SysPath as working_dir+raw; HWPath is similarly prefixed. SysPath cannot mix device definitions, HWPath alone rejected. Inherited hw_path may default to parent YAML.

Defaults: working_dir is benchmark directory; parent_path main YAML fallback.

Validation: No shared checked Workbench support for these keys; raw string concatenation lacks containment/type schema.

Disposition: unsupported_checked_route.

Producer: [tools/SALAM-Configurator/template.yml:1](../../../tools/SALAM-Configurator/template.yml#L1).

Transform: [tools/SALAM-Configurator/systembuilder.py:72](../../../tools/SALAM-Configurator/systembuilder.py#L72), [tools/SALAM-Configurator/systembuilder.py:78](../../../tools/SALAM-Configurator/systembuilder.py#L78), [tools/SALAM-Configurator/systembuilder.py:85](../../../tools/SALAM-Configurator/systembuilder.py#L85), [tools/SALAM-Configurator/systembuilder.py:93](../../../tools/SALAM-Configurator/systembuilder.py#L93).

Consumer: [tools/SALAM-Configurator/systembuilder.py:120](../../../tools/SALAM-Configurator/systembuilder.py#L120).

Unresolved: Keep distinct from accelerator ConfigPath and HWPath; recursive cycles and exact multi-document semantics need future fixtures.

### L013 - acc_cluster[*].Accelerator[*].HWPath (tools dialect)

Tools parser allows per-accelerator HWPath override; value is assigned verbatim and emitted as hw_config. Unlike cluster HWPath, this override is not prefixed by working_dir.

Defaults: Inherited cluster hw_config_path.

Validation: Not accepted in checked root-dialect contract.

Disposition: normalize_across_consumers.

Transform: [tools/SALAM-Configurator/config_parser.py:154](../../../tools/SALAM-Configurator/config_parser.py#L154), [tools/SALAM-Configurator/config_parser.py:173](../../../tools/SALAM-Configurator/config_parser.py#L173).

Consumer: [tools/SALAM-Configurator/config_parser.py:315](../../../tools/SALAM-Configurator/config_parser.py#L315).

Unresolved: Require explicit base semantics; do not rename HWPath to ConfigPath without preserving resolution.

### L014 - acc_cluster[*].Accelerator[*].PIOSize

Required raw field allocates padded MMIO and feeds CommInterface.pio_size; generated address header follows allocation. It is not the unpadded requested size after generation.

Defaults: No usable raw default; GUI historical32 versus Workbench loaded fallback1.

Validation: Workbench positive UInt32; generated/effective checks compare padded PIO size.

Disposition: normalize_across_consumers.

Producer: [SALAM-Configurator/template.yml:33](../../../SALAM-Configurator/template.yml#L33), [workbench/salam_workbench/gui_editor.py:289](../../../workbench/salam_workbench/gui_editor.py#L289).

Transform: [SALAM-Configurator/parser.py:153](../../../SALAM-Configurator/parser.py#L153).

Consumer: [SALAM-Configurator/parser.py:313](../../../SALAM-Configurator/parser.py#L313), [workbench/salam_workbench/config_contract.py:535](../../../workbench/salam_workbench/config_contract.py#L535), [workbench/salam_workbench/config_contract.py:575](../../../workbench/salam_workbench/config_contract.py#L575).

### L015 - acc_cluster[*].Accelerator[*].PIOMaster / LocalSlaves

Raw comma-separated PIOMaster routes .pio to LocalBus.mem_side_ports or named accelerator.local; LocalSlaves routes .local to LocalBus.cpu_side_ports or named device.pio. Accelerator LocalBus matching is case-sensitive substring, unlike DMA normalization.

Defaults: Missing connection fields -> empty lists, no generated edge.

Validation: Checked allows only literal LocalBus for PIOMaster/default, LocalSlaves None/LocalBus; default PIOMaster acceptance does not materialize raw connection.

Disposition: normalization_gap.

Producer: [SALAM-Configurator/template.yml:34](../../../SALAM-Configurator/template.yml#L34), [workbench/salam_workbench/gui_editor.py:292](../../../workbench/salam_workbench/gui_editor.py#L292).

Transform: [SALAM-Configurator/parser.py:165](../../../SALAM-Configurator/parser.py#L165), [SALAM-Configurator/parser.py:171](../../../SALAM-Configurator/parser.py#L171).

Consumer: [SALAM-Configurator/parser.py:340](../../../SALAM-Configurator/parser.py#L340), [SALAM-Configurator/parser.py:354](../../../SALAM-Configurator/parser.py#L354), [workbench/salam_workbench/config_contract.py:543](../../../workbench/salam_workbench/config_contract.py#L543).

Unresolved: Resolve reference existence, whitespace, cardinality and role explicitly; do not infer that acceptance proves connectivity.

### L016 - acc_cluster[*].Accelerator[*].StreamIn / StreamOut

Comma-separated names emit accelerator.stream connections to peer.stream_in/stream_out, lowercasing peer names.

Defaults: Absent -> no stream connections.

Validation: Checked contract rejects supplied fields pending separate actual-simulator witness.

Disposition: unsupported_checked_route.

Transform: [SALAM-Configurator/parser.py:167](../../../SALAM-Configurator/parser.py#L167).

Consumer: [SALAM-Configurator/parser.py:369](../../../SALAM-Configurator/parser.py#L369), [SALAM-Configurator/parser.py:374](../../../SALAM-Configurator/parser.py#L374), [workbench/salam_workbench/config_contract.py:557](../../../workbench/salam_workbench/config_contract.py#L557).

Unresolved: Retain this producer/consumer path in migration inventory rather than deleting it as unused.

### L017 - acc_cluster[*].Accelerator[*].InterruptNum / Debug

Explicit InterruptNum enters CommInterface.int_num; absence leaves native default. Debug emitted as enable_debug_msgs, defaultFalse.

Defaults: Raw intNumNone / DebugFalse.

Validation: Workbench interrupt UInt32 and Debug strict bool; scalar effective expectations recorded.

Disposition: normalize_across_consumers.

Producer: [SALAM-Configurator/template.yml:32](../../../SALAM-Configurator/template.yml#L32), [workbench/salam_workbench/gui_editor.py:295](../../../workbench/salam_workbench/gui_editor.py#L295).

Transform: [SALAM-Configurator/parser.py:173](../../../SALAM-Configurator/parser.py#L173).

Consumer: [SALAM-Configurator/parser.py:307](../../../SALAM-Configurator/parser.py#L307), [SALAM-Configurator/parser.py:383](../../../SALAM-Configurator/parser.py#L383), [workbench/salam_workbench/config_contract.py:567](../../../workbench/salam_workbench/config_contract.py#L567), [workbench/salam_workbench/config_contract.py:617](../../../workbench/salam_workbench/config_contract.py#L617).

Unresolved: Absence must retain native default identity; this audit does not substitute interrupt-disabled semantics.

### L018 - acc_cluster[*].Accelerator[*].Var[*].Name / Type

Raw Variable constructor recognizes exact SPM, Stream, RegisterBank, Cache; allocation uses substring checks in separate branch. Name is lowercased for most generated objects; Cache path preserves Name case.

Defaults: No valid generic Type default in raw parser; Workbench editor defaults SPM.

Validation: Checked admits only SPM/RegisterBank and safe unique identifiers; Stream/Cache source routes require witnesses.

Disposition: normalize_across_consumers.

Producer: [SALAM-Configurator/template.yml:39](../../../SALAM-Configurator/template.yml#L39), [workbench/salam_workbench/gui_editor.py:306](../../../workbench/salam_workbench/gui_editor.py#L306).

Transform: [SALAM-Configurator/parser.py:184](../../../SALAM-Configurator/parser.py#L184), [SALAM-Configurator/parser.py:194](../../../SALAM-Configurator/parser.py#L194).

Consumer: [SALAM-Configurator/parser.py:539](../../../SALAM-Configurator/parser.py#L539), [SALAM-Configurator/parser.py:586](../../../SALAM-Configurator/parser.py#L586), [workbench/salam_workbench/config_contract.py:663](../../../workbench/salam_workbench/config_contract.py#L663).

Unresolved: Exact enum must replace split substring/exact matching. Normalize cache name casing intentionally.

### L019 - acc_cluster[*].Accelerator[*].Var[*].Size (SPM/RegisterBank/Cache)

SPM/RegisterBank create AddrRange(addr,addr+Size), update next address with historical64B padding; Cache Size becomes L1Cache(size='<Size>B') and consumes no local address.

Defaults: Missing Size becomesNone and later fails; no documented implicit memory size here.

Validation: Workbench positive UInt32 for checked memory types; enforces global aperture.

Disposition: normalize_across_consumers.

Producer: [SALAM-Configurator/template.yml:41](../../../SALAM-Configurator/template.yml#L41), [workbench/salam_workbench/gui_editor.py:307](../../../workbench/salam_workbench/gui_editor.py#L307).

Transform: [SALAM-Configurator/parser.py:194](../../../SALAM-Configurator/parser.py#L194), [SALAM-Configurator/parser.py:206](../../../SALAM-Configurator/parser.py#L206).

Consumer: [SALAM-Configurator/parser.py:638](../../../SALAM-Configurator/parser.py#L638), [SALAM-Configurator/parser.py:699](../../../SALAM-Configurator/parser.py#L699), [SALAM-Configurator/parser.py:727](../../../SALAM-Configurator/parser.py#L727), [workbench/salam_workbench/config_contract.py:698](../../../workbench/salam_workbench/config_contract.py#L698).

Unresolved: Preserve range end semantics exactly until fixture comparison establishes intended extent.

### L020 - acc_cluster[*].Accelerator[*].Var[*].Ports (SPM)

Default owning-accelerator PortedConnection count is Ports; generated loop repeats vector .spm -> .spm_ports bindings; public .port attaches LocalBus.

Defaults: Raw default1; offline CACTI lacks this default.

Validation: Workbench validates positive UInt32 but does not add a separate expected_effective port-count entry for SPM.

Disposition: normalization_gap.

Producer: [SALAM-Configurator/template.yml:42](../../../SALAM-Configurator/template.yml#L42), [workbench/salam_workbench/gui_editor.py:308](../../../workbench/salam_workbench/gui_editor.py#L308).

Transform: [SALAM-Configurator/parser.py:546](../../../SALAM-Configurator/parser.py#L546), [SALAM-Configurator/parser.py:553](../../../SALAM-Configurator/parser.py#L553).

Consumer: [SALAM-Configurator/parser.py:676](../../../SALAM-Configurator/parser.py#L676), [SALAM-Configurator/parser.py:683](../../../SALAM-Configurator/parser.py#L683), [workbench/salam_workbench/config_contract.py:707](../../../workbench/salam_workbench/config_contract.py#L707).

Unresolved: Port cardinality and actual peers need explicit source/generated/effective witness in future native path.

### L021 - acc_cluster[*].Accelerator[*].Var[*].Connections (SPM)

Comma-delimited name:count tokens add extra private SPM peers. Raw split does not strip whitespace; int(count) used. Repeated names and absent target names are not independently resolved by parser.

Defaults: Absent -> only owning accelerator connection.

Validation: Workbench syntax validates stripped tokens and positive counts but does not validate target existence or add SPM effective peer expectations.

Disposition: normalization_gap.

Producer: [SALAM-Configurator/template.yml:52](../../../SALAM-Configurator/template.yml#L52), [workbench/salam_workbench/gui_editor.py:312](../../../workbench/salam_workbench/gui_editor.py#L312).

Transform: [SALAM-Configurator/parser.py:555](../../../SALAM-Configurator/parser.py#L555).

Consumer: [SALAM-Configurator/parser.py:683](../../../SALAM-Configurator/parser.py#L683), [workbench/salam_workbench/config_contract.py:730](../../../workbench/salam_workbench/config_contract.py#L730).

Unresolved: Validator strips tokens for syntax while raw generation preserves leading peer whitespace; canonicalize once before both.

### L022 - acc_cluster[*].Accelerator[*].Var[*].ReadyMode / ResetOnRead / ReadOnInvalid / WriteOnValid (SPM)

SPM assignments route to ready_mode, reset_on_scratchpad_read, read_on_invalid, write_on_valid. conf_table_reported is separately hardcodedFalse.

Defaults: False / True / False / True.

Validation: Workbench strict bool and effective scalar expectations for all four; raw parser accepts any stringifiable value.

Disposition: normalize_across_consumers.

Producer: [SALAM-Configurator/template.yml:43](../../../SALAM-Configurator/template.yml#L43), [workbench/salam_workbench/gui_editor.py:313](../../../workbench/salam_workbench/gui_editor.py#L313).

Transform: [SALAM-Configurator/parser.py:548](../../../SALAM-Configurator/parser.py#L548).

Consumer: [SALAM-Configurator/parser.py:643](../../../SALAM-Configurator/parser.py#L643), [SALAM-Configurator/parser.py:651](../../../SALAM-Configurator/parser.py#L651), [workbench/salam_workbench/config_contract.py:717](../../../workbench/salam_workbench/config_contract.py#L717), [workbench/salam_workbench/config_contract.py:820](../../../workbench/salam_workbench/config_contract.py#L820).

### L023 - acc_cluster[*].Accelerator[*].Var[*].Ports / Connections (RegisterBank)

Raw bank ignores Ports, gives owner1 connection and emits one reg->reg_port binding for each Connections token regardless count. Staged Workbench adapter changes owner count/loops using exact source/AST anchors.

Defaults: Raw owner count1; staged Ports default1.

Validation: Workbench requires staged adapter when Ports present or counts!=1; native compiled bank scalar private port rejects total private connections!=1 even with adapter.

Disposition: normalize_across_consumers.

Producer: [SALAM-Configurator/template.yml:67](../../../SALAM-Configurator/template.yml#L67), [workbench/salam_workbench/gui_editor.py:308](../../../workbench/salam_workbench/gui_editor.py#L308).

Transform: [workbench/salam_workbench/registerbank_adapter.py:17](../../../workbench/salam_workbench/registerbank_adapter.py#L17), [workbench/salam_workbench/registerbank_adapter.py:37](../../../workbench/salam_workbench/registerbank_adapter.py#L37), [workbench/salam_workbench/registerbank_adapter.py:67](../../../workbench/salam_workbench/registerbank_adapter.py#L67).

Consumer: [SALAM-Configurator/parser.py:580](../../../SALAM-Configurator/parser.py#L580), [SALAM-Configurator/parser.py:712](../../../SALAM-Configurator/parser.py#L712), [workbench/salam_workbench/config_contract.py:688](../../../workbench/salam_workbench/config_contract.py#L688), [workbench/salam_workbench/config_contract.py:782](../../../workbench/salam_workbench/config_contract.py#L782), [src/hwacc/RegisterBank.py:9](../../../src/hwacc/RegisterBank.py#L9).

Unresolved: Generator multiplicity is not native multiport memory support; distinguish the load_port from private reg_port.

### L024 - acc_cluster[*].Accelerator[*].Var[*].ReadyMode / ResetOnRead / ReadOnInvalid / WriteOnValid (RegisterBank)

Raw bank never reads scratchpad ready controls; simply preserving these keys does not implement semantics.

Defaults: None.

Validation: Workbench explicitly rejects these misplaced fields as unconsumed_register_field.

Disposition: unsupported_field.

Producer: [workbench/salam_workbench/gui_editor.py:313](../../../workbench/salam_workbench/gui_editor.py#L313).

Consumer: [SALAM-Configurator/parser.py:572](../../../SALAM-Configurator/parser.py#L572), [workbench/salam_workbench/config_contract.py:672](../../../workbench/salam_workbench/config_contract.py#L672).

### L025 - acc_cluster[*].Accelerator[*].Var[*].StreamSize / BufferSize / InCon / OutCon (Stream)

Raw StreamBuffer width/capacity use StreamSize/BufferSize. InCon/OutCon lowercased; connects peer.stream to .stream_in/out. Status and stream MMIO allocations are generated.

Defaults: Template labels sizes optional; raw consumes StreamSize before construction and stringifies missing BufferSize, so optional comments are not a usable default contract.

Validation: Workbench rejects Stream memory type pending real witness.

Disposition: unsupported_checked_route.

Producer: [SALAM-Configurator/template.yml:58](../../../SALAM-Configurator/template.yml#L58).

Transform: [SALAM-Configurator/parser.py:184](../../../SALAM-Configurator/parser.py#L184), [SALAM-Configurator/parser.py:563](../../../SALAM-Configurator/parser.py#L563).

Consumer: [SALAM-Configurator/parser.py:603](../../../SALAM-Configurator/parser.py#L603), [SALAM-Configurator/parser.py:617](../../../SALAM-Configurator/parser.py#L617).

Unresolved: Stream alignment/status addresses and producer/consumer direction need distinct fixtures.

### L026 - acc_cluster[*].Accelerator[*].Var[*].Size (Cache) / accelerator_cache.*

Raw Cache Variable creates per-accelerator L1Cache, connects mem_side to coherency_bus and cpu_side to owner.local. Template L1 assoc2/latencies2/mshrs4/targets20. Workbench accelerator_cache patches these six generated class defaults only if Cache Var present.

Defaults: assoc2; tag/data/response_latency2; mshrs4; tgts_per_mshr20.

Validation: Spec validation accepts positive integers, but configuration contract rejects Cache memory type before this checked pipeline can qualify; code existence is not a tested GUI feature.

Disposition: unsupported_checked_route.

Producer: [SALAM-Configurator/template.yml:69](../../../SALAM-Configurator/template.yml#L69).

Transform: [SALAM-Configurator/systembuilder.py:79](../../../SALAM-Configurator/systembuilder.py#L79), [workbench/salam_workbench/configurator.py:855](../../../workbench/salam_workbench/configurator.py#L855).

Consumer: [SALAM-Configurator/parser.py:724](../../../SALAM-Configurator/parser.py#L724), [workbench/salam_workbench/configurator.py:870](../../../workbench/salam_workbench/configurator.py#L870), [workbench/salam_workbench/config_contract.py:664](../../../workbench/salam_workbench/config_contract.py#L664).

Unresolved: Separate this per-accelerator L1 cache from AccCluster.cluster_cache and CPU caches.

### L027 - system.acc_cache / AccCluster.cache_size / _connect_caches(cache_size,l2coherent)

Cluster cache exists only if options.acc_cache AND explicit method cache_size!=0. Generated call sets l2coherent=False and supplies no cache_size, so branch is dormant. Param cache_size32kB is not automatically passed to method; topology local/external ranges are computed but bridge helper is not invoked here.

Defaults: AccCluster.cache_size32kB; _connect_caches cache_size0; coherenceFalse in generator.

Validation: Scalar parameter existence alone does not prove topology effectiveness.

Disposition: default_literal_dormant.

Producer: [SALAM-Configurator/fs_template.py:79](../../../SALAM-Configurator/fs_template.py#L79).

Transform: [SALAM-Configurator/parser.py:251](../../../SALAM-Configurator/parser.py#L251), [SALAM-Configurator/parser.py:259](../../../SALAM-Configurator/parser.py#L259).

Consumer: [src/hwacc/AccCluster.py:29](../../../src/hwacc/AccCluster.py#L29), [src/hwacc/AccCluster.py:51](../../../src/hwacc/AccCluster.py#L51), [src/hwacc/AccCluster.py:63](../../../src/hwacc/AccCluster.py#L63).

Unresolved: Native factory must choose cache placement and constructor-time routing explicitly; post-construction scalar changes do not retroactively add cache/bridge objects.

### L028 - system.* in Workbench JSON spec

Default system dictionary merged with requested keys; sorted entries become --key forTrue, omittedFalse, or --key=value. Strict top-level spec keys but only syntax/reserved/scalar checks for system keys, not an allowlist.

Defaults: 4GB DDR4_2400_8x8; VExpress_GEM5_V1; dtb none; bare-metalTrue; DerivO3CPU; caches/l2cacheTrue.

Validation: Unknown syntactically valid system option can reach gem5 argparse and fail there; no assurance every accepted request is meaningful.

Disposition: normalization_gap.

Transform: [workbench/salam_workbench/configurator.py:41](../../../workbench/salam_workbench/configurator.py#L41), [workbench/salam_workbench/configurator.py:123](../../../workbench/salam_workbench/configurator.py#L123), [workbench/salam_workbench/configurator.py:920](../../../workbench/salam_workbench/configurator.py#L920).

Consumer: [workbench/salam_workbench/configurator.py:926](../../../workbench/salam_workbench/configurator.py#L926), [SALAM-Configurator/fs_template.py:312](../../../SALAM-Configurator/fs_template.py#L312).

Unresolved: Underscore/hyphen system keys remain distinct during default merging and CLI emission; witness later replaces underscore for comparison. Detect conflicts before CLI.

### L029 - system.cpu-type / legacy CPU aliases

On modern toolchain only, DerivO3CPU/O3CPU->ArmO3CPU; TimingSimpleCPU->ArmTimingSimpleCPU; AtomicSimpleCPU->ArmAtomicSimpleCPU; MinorCPU->ArmMinorCPU. Records requested and effective values.

Defaults: Depends on selected toolchain, not YAML model period.

Validation: Source transformation with explicit receipt, runtime still needs class witness.

Disposition: normalize_across_consumers.

Transform: [workbench/salam_workbench/toolchain_profile.py:147](../../../workbench/salam_workbench/toolchain_profile.py#L147).

Consumer: [workbench/salam_workbench/system_witness.py:250](../../../workbench/salam_workbench/system_witness.py#L250).

### L030 - system.mem-size / mem-type / machine-type / num-cpus / caches / l2cache / cacheline-size / l1i-size / l1d-size / l2-size / l1i-assoc / l1d-assoc / l2-assoc / sys-clock / cpu-clock / mem-channels / mem-ranks / dtb-file

Legacy fs template delegates native Options, CPU/Mem/CacheConfig. Host witness compares INI sizes/classes/clock/cache structure and requires live runtime capture for platform/DRAM class. Unmapped options yield partial, not passed.

Defaults: Native defaults and Workbench defaults are separate layers.

Validation: Witness mappings are present in source; no new simulation performed by this audit.

Disposition: normalize_across_consumers.

Transform: [SALAM-Configurator/fs_template.py:110](../../../SALAM-Configurator/fs_template.py#L110), [SALAM-Configurator/fs_template.py:125](../../../SALAM-Configurator/fs_template.py#L125), [SALAM-Configurator/fs_template.py:133](../../../SALAM-Configurator/fs_template.py#L133), [SALAM-Configurator/fs_template.py:230](../../../SALAM-Configurator/fs_template.py#L230).

Consumer: [workbench/salam_workbench/system_witness.py:239](../../../workbench/salam_workbench/system_witness.py#L239), [workbench/salam_workbench/system_witness.py:376](../../../workbench/salam_workbench/system_witness.py#L376), [workbench/salam_workbench/system_witness.py:404](../../../workbench/salam_workbench/system_witness.py#L404).

Unresolved: bare-metal and other accepted common/FS options currently lack explicit witness mappings and can leave system state partial.

### L031 - GUI snapshot.system

Current Workbench editor accepts only mem-size,mem-type,cpu-clock,sys-clock; broader CLI/native options remain outside these widgets.

Defaults: Blank/None widget values removed, inherited pipeline defaults remain.

Validation: Explicit GUI allowlist; not equivalent to all configurator JSON system capabilities.

Disposition: supported_source_path.

Transform: [workbench/salam_workbench/gui_editor.py:537](../../../workbench/salam_workbench/gui_editor.py#L537).

Consumer: [workbench/salam_workbench/gui_editor.py:566](../../../workbench/salam_workbench/gui_editor.py#L566).

### L032 - parameters.<system.object>.<compiled_scalar>

Spec accepts named finite scalar values. Runtime traverses live SimObjects and requires declared nonprivate scalar _params, rejects SimObject/vector replacement, asks gem5 to convert, and rejects fractional values routed to integer descriptors. Writes applied receipt before instantiate.

Defaults: No general default substitution; obj native/current value unless explicitly overridden.

Validation: Host name/type validation plus actual live descriptor conversion and later config.ini witness. Scalar acceptance is not proof C++ uses a stored parameter for desired behavior.

Disposition: supported_source_path.

Transform: [workbench/salam_workbench/configurator.py:135](../../../workbench/salam_workbench/configurator.py#L135), [workbench/salam_workbench/configurator_runtime.py:29](../../../workbench/salam_workbench/configurator_runtime.py#L29).

Consumer: [workbench/salam_workbench/configurator_runtime.py:39](../../../workbench/salam_workbench/configurator_runtime.py#L39), [workbench/salam_workbench/configurator.py:943](../../../workbench/salam_workbench/configurator.py#L943).

Unresolved: Structural changes belong in factory/topology path; late scalar overrides may miss constructor-copied state.

### L033 - parameters.*.clock_period

Integer nanoseconds legacy actor parameter1..1,000,000; dedicated native clock domains assigned after final overrides by retained HWAccConfig helper. Distinct from profile selection period.

Defaults: Actor default e.g.NoncoherentDma10ns; profile generator selection5ns.

Validation: Spec and native helper range checks. Native build/run witness still required for changes.

Disposition: normalize_across_consumers.

Transform: [workbench/salam_workbench/configurator.py:150](../../../workbench/salam_workbench/configurator.py#L150), [configs/SALAM/HWAccConfig.py:437](../../../configs/SALAM/HWAccConfig.py#L437).

Consumer: [src/hwacc/NoncoherentDma.py:18](../../../src/hwacc/NoncoherentDma.py#L18), [configs/SALAM/HWAccConfig.py:440](../../../configs/SALAM/HWAccConfig.py#L440).

Unresolved: New native factory should call equivalent actor-domain finalization without common/Simulation global hook.

### L034 - legacy GUI hw_config.*.instructions.<and|or|xor|switch> / symbolic functional_unit

Import-only canonicalization maps aliases and/or/xor/switch to *_inst via current runtime registry; symbolic functional_unit to compiled enum_value. Rejects unknown symbol and collisions, retains unrelated fields and original source hash.

Defaults: Integer mapping values retained unchanged.

Validation: Pure in-memory dialect transform; does not run generator/build/simulator.

Disposition: normalize_across_consumers.

Producer: [gem5-SALAM-gui/src/gui/config_generator.py:673](../../../gem5-SALAM-gui/src/gui/config_generator.py#L673).

Transform: [workbench/salam_workbench/configuration_import.py:14](../../../workbench/salam_workbench/configuration_import.py#L14), [workbench/salam_workbench/configuration_import.py:74](../../../workbench/salam_workbench/configuration_import.py#L74), [workbench/salam_workbench/configuration_import.py:110](../../../workbench/salam_workbench/configuration_import.py#L110).

Consumer: [workbench/salam_workbench/config_contract.py:922](../../../workbench/salam_workbench/config_contract.py#L922).

Unresolved: Keep canonical instruction alias separate from CycleCounts and/or/xor key alias route.

### L035 - root HWProfileGenerator / tools/hw_generator HWProfileGenerator selection

Both copies share behavior (only trailing whitespace differences observed): model40nm_model, HWModel latency default10ns, default_profile, benchfolder benchmarks/sys_validation. Main forcibly latency5ns; HWArgs only bench; raw os.listdir unsorted. Workbench selects root script files, staged patches sort and inject requested model/period/profile.

Defaults: HWModel10ns vs CLI actual5ns.

Validation: Profile selection must be explicit; current Workbench stage is isolated and source-hashed.

Disposition: normalize_across_consumers.

Producer: [SALAMArgs.py:3](../../../SALAMArgs.py#L3), [tools/hw_generator/SALAMArgs.py:3](../../../tools/hw_generator/SALAMArgs.py#L3).

Transform: [HWProfileGenerator.py:9](../../../HWProfileGenerator.py#L9), [tools/hw_generator/HWProfileGenerator.py:9](../../../tools/hw_generator/HWProfileGenerator.py#L9), [HWProfileGenerator.py:87](../../../HWProfileGenerator.py#L87), [tools/hw_generator/HWProfileGenerator.py:87](../../../tools/hw_generator/HWProfileGenerator.py#L87), [workbench/salam_workbench/hardware_codegen.py:178](../../../workbench/salam_workbench/hardware_codegen.py#L178).

Consumer: [workbench/salam_workbench/hardware_codegen.py:20](../../../workbench/salam_workbench/hardware_codegen.py#L20).

Unresolved: Duplicate copies remain distinct paths; tools maintenance cannot be assumed to update root pipeline.

### L036 - functional_unit.parameters.alias / stages / cycles / enum_value / limit

Both HWModel copies directly require these profile keys; generated defaults set aliasString and numeric UInt32 stages/cycles/enum/limit. Workbench verifies alias matches directory. Regeneration emits C++/SimObjects and requires simulator rebuild.

Defaults: Profile literals, no raw field fallback.

Validation: Stored/generated contract separate from scheduler activity; runtime consumption covered by core audit.

Disposition: normalize_across_consumers.

Transform: [HWProfileGenerator.py:36](../../../HWProfileGenerator.py#L36), [HWProfileGenerator.py:57](../../../HWProfileGenerator.py#L57), [tools/hw_generator/HWProfileGenerator.py:36](../../../tools/hw_generator/HWProfileGenerator.py#L36), [tools/hw_generator/HWProfileGenerator.py:57](../../../tools/hw_generator/HWProfileGenerator.py#L57), [workbench/salam_workbench/hardware_codegen.py:135](../../../workbench/salam_workbench/hardware_codegen.py#L135).

Consumer: [SALAMClassGenerator.py:355](../../../SALAMClassGenerator.py#L355), [SALAMClassGenerator.py:368](../../../SALAMClassGenerator.py#L368), [tools/hw_generator/SALAMClassGenerator.py:355](../../../tools/hw_generator/SALAMClassGenerator.py#L355).

### L037 - functional_unit.parameters.datatypes.{integer,floating_point,pointer}.{size,sign,APMode}

Raw profile reader requires all9 fields; generator emits size/sign Strings and apmode Bool. Presence in generated C++ storage is not evidence of arbitrary LLVM precision execution.

Defaults: Profile literals.

Validation: Source-required producer fields; no inference that metadata changes numerics.

Disposition: normalize_across_consumers.

Transform: [HWProfileGenerator.py:40](../../../HWProfileGenerator.py#L40), [tools/hw_generator/HWProfileGenerator.py:40](../../../tools/hw_generator/HWProfileGenerator.py#L40).

Consumer: [SALAMClassGenerator.py:359](../../../SALAMClassGenerator.py#L359), [tools/hw_generator/SALAMClassGenerator.py:359](../../../tools/hw_generator/SALAMClassGenerator.py#L359).

Unresolved: Native profile schema must preserve exact APMode capitalization versus generated lowercase field names.

### L038 - functional_unit.parameters.instructions[] / instructions.<opcode>.functional_unit

During profile generation both HWModel copies mutate inst_list.yml: each supported instruction except literal any/none gets FU enum_value. Multiple FU assignments overwrite in directory traversal order; Workbench sorts traversal but has not established semantic conflict rejection here.

Defaults: any/none skipped, original instruction mapping retained.

Validation: Mutation occurs in staged copy in checked pipeline; raw generator would modify supplied benchmark instruction file.

Disposition: normalization_gap.

Transform: [HWProfileGenerator.py:49](../../../HWProfileGenerator.py#L49), [tools/hw_generator/HWProfileGenerator.py:49](../../../tools/hw_generator/HWProfileGenerator.py#L49), [workbench/salam_workbench/hardware_codegen.py:178](../../../workbench/salam_workbench/hardware_codegen.py#L178).

Consumer: [HWProfileGenerator.py:54](../../../HWProfileGenerator.py#L54), [tools/hw_generator/HWProfileGenerator.py:54](../../../tools/hw_generator/HWProfileGenerator.py#L54).

Unresolved: Detect overlapping FU instruction membership before factory creation; deterministic last-wins is not conflict validation.

### L039 - functional_unit.power_model.units.{power,energy,time,area} / latency

Both readers require unit labels and latency. Generator emits labelsString and fu_latencyUInt32. This is profile characterization data rather than live actor period or measured run power.

Defaults: Profile literals.

Validation: No synthesis provenance/calibration proven by these consumers.

Disposition: normalize_across_consumers.

Transform: [HWProfileGenerator.py:63](../../../HWProfileGenerator.py#L63), [tools/hw_generator/HWProfileGenerator.py:63](../../../tools/hw_generator/HWProfileGenerator.py#L63).

Consumer: [SALAMClassGenerator.py:370](../../../SALAMClassGenerator.py#L370), [SALAMClassGenerator.py:374](../../../SALAMClassGenerator.py#L374), [tools/hw_generator/SALAMClassGenerator.py:370](../../../tools/hw_generator/SALAMClassGenerator.py#L370).

### L040 - functional_unit.power_model.{internal_power,switch_power,dynamic_power,dynamic_energy,leakage_power,area,path_delay}

Raw duplicated class generators emit7 fractional characterization fields asUInt32. Checked staged class patch usesFloat for exactly those7; integer fu_latency is separate. Generated-source constructor audit checks routing, not power calibration.

Defaults: Profile literals; no universally valid zero/measurement default.

Validation: Must preserve staged float fix or replace generator with typed native data.

Disposition: normalize_across_consumers.

Transform: [HWProfileGenerator.py:69](../../../HWProfileGenerator.py#L69), [tools/hw_generator/HWProfileGenerator.py:69](../../../tools/hw_generator/HWProfileGenerator.py#L69), [workbench/salam_workbench/hardware_codegen.py:194](../../../workbench/salam_workbench/hardware_codegen.py#L194).

Consumer: [SALAMClassGenerator.py:375](../../../SALAMClassGenerator.py#L375), [tools/hw_generator/SALAMClassGenerator.py:375](../../../tools/hw_generator/SALAMClassGenerator.py#L375), [workbench/salam_workbench/hardware_codegen.py:284](../../../workbench/salam_workbench/hardware_codegen.py#L284).

Unresolved: Model coefficients must not be promoted to observed run energy or calibrated estimates.

### L041 - instructions.<opcode>.functional_unit_limit / opcode_num / runtime_cycles (offline inst_list)

Raw instruction generator requires all four fields including functional_unit. Workbench staged patch defaults missing functional_unit_limit to0. Logical runtime hw_config overrides and static generated inst_list are separate input families.

Defaults: Only staged functional_unit_limit fallback0; other generated fields required.

Validation: Per-instruction nonzero limit remains unsupported by scheduler, unlike FU-level limit. Core audit contains C++ trace.

Disposition: normalize_across_consumers.

Transform: [SALAMClassGenerator.py:383](../../../SALAMClassGenerator.py#L383), [workbench/salam_workbench/hardware_codegen.py:202](../../../workbench/salam_workbench/hardware_codegen.py#L202).

Consumer: [SALAMClassGenerator.py:390](../../../SALAMClassGenerator.py#L390), [tools/hw_generator/SALAMClassGenerator.py:383](../../../tools/hw_generator/SALAMClassGenerator.py#L383).

Unresolved: Do not infer missing runtime_cycles uses FU cycles: channels differ.

### L042 - hw_config.<ir_stem>.instructions.* / functional_units.*

Checked contract selects hardware per accelerator; recognizes hw_config.name as string metadata; rejects unused accelerator hardware, unknown registries and unconsumed field names. Runtime logical instructions allow functional_unit, functional_unit_limit, opcode_num, runtime_cycles; FUs allow cycles/limit.

Defaults: Missing orNone accelerator settings leave compiled defaults.

Validation: Runtime generated profile schema is not this narrower override schema.

Disposition: normalize_across_consumers.

Producer: [gem5-SALAM-gui/src/gui/config_generator.py:647](../../../gem5-SALAM-gui/src/gui/config_generator.py#L647), [workbench/salam_workbench/gui_editor.py:447](../../../workbench/salam_workbench/gui_editor.py#L447).

Consumer: [workbench/salam_workbench/config_contract.py:857](../../../workbench/salam_workbench/config_contract.py#L857), [workbench/salam_workbench/config_contract.py:882](../../../workbench/salam_workbench/config_contract.py#L882), [workbench/salam_workbench/config_contract.py:901](../../../workbench/salam_workbench/config_contract.py#L901), [workbench/salam_workbench/config_contract.py:932](../../../workbench/salam_workbench/config_contract.py#L932), [workbench/salam_workbench/config_contract.py:1008](../../../workbench/salam_workbench/config_contract.py#L1008).

Unresolved: Do not flatten FU profile metadata/power fields into runtime override block.

### L043 - cacti-SALAM / tools/cacti-SALAM: Var[*].Type / Name / Size / Ports

Byte-identical wrappers inspect only mem_object[1][0], i.e.first Var element in each discovered list. Only exact SPM included; other first objects printed as 'Streaming Buffer'. Requires explicit Ports; clamps Size<2048 to2048 in loaded dict then invokes external cactiStats. Produces append CSV, not runtime SimObject assignments.

Defaults: Minimum modeled Size2048; unlike runtime Ports default1 there is no Ports fallback.

Validation: No duplicate-key/schema/range checks; no all-Var traversal. No CACTI run performed.

Disposition: normalize_across_consumers.

Transform: [cacti-SALAM/cactiWrapper.py:24](../../../cacti-SALAM/cactiWrapper.py#L24), [tools/cacti-SALAM/cactiWrapper.py:24](../../../tools/cacti-SALAM/cactiWrapper.py#L24).

Consumer: [cacti-SALAM/cactiWrapper.py:39](../../../cacti-SALAM/cactiWrapper.py#L39), [cacti-SALAM/cactiWrapper.py:42](../../../cacti-SALAM/cactiWrapper.py#L42), [tools/cacti-SALAM/cactiWrapper.py:44](../../../tools/cacti-SALAM/cactiWrapper.py#L44).

Unresolved: Offline result coverage incomplete for lists>1; no automatic link from CSV to runtime power established.

### L044 - cactiStats.sh fixed characterization parameters

Shell consumesSize/Ports arguments then fixes line64,assoc1,banks1,tech45,output width512,temp300, and many objective/wire choices; runs ext/mcpat/cacti under M5_PATH.

Defaults: Technology45nm versus FU profile name40nm_model; independent assumptions.

Validation: Fixed literals are offline model inputs, not mutable runtime YAML keys.

Disposition: default_literal.

Transform: [cacti-SALAM/cactiStats.sh:3](../../../cacti-SALAM/cactiStats.sh#L3), [tools/cacti-SALAM/cactiStats.sh:3](../../../tools/cacti-SALAM/cactiStats.sh#L3).

Consumer: [cacti-SALAM/cactiStats.sh:12](../../../cacti-SALAM/cactiStats.sh#L12), [cacti-SALAM/cactiStats.sh:56](../../../cacti-SALAM/cactiStats.sh#L56).

Unresolved: Record model compatibility and area/energy units before combining characterization outputs.

### L045 - unknown root / cluster / accelerator / Var keys

Raw generator only tests recognized keys and generally ignores extras; Variable kwargs reads known names without rejecting unknowns. Checked _keys rejects unknown root and individual scalar-map keys, but accepted Var set is not Type-specific.

Defaults: No generic warning in raw parser.

Validation: Strict checked validator is useful but not a universal dialect schema.

Disposition: validation_gap.

Transform: [SALAM-Configurator/systembuilder.py:271](../../../SALAM-Configurator/systembuilder.py#L271), [SALAM-Configurator/parser.py:152](../../../SALAM-Configurator/parser.py#L152).

Consumer: [SALAM-Configurator/parser.py:537](../../../SALAM-Configurator/parser.py#L537), [workbench/salam_workbench/config_contract.py:63](../../../workbench/salam_workbench/config_contract.py#L63), [workbench/salam_workbench/config_contract.py:643](../../../workbench/salam_workbench/config_contract.py#L643).

### L046 - SPM/RegisterBank with StreamSize / BufferSize / InCon / OutCon

Checked Var accepted-key set contains Stream-only fields even when accepted Type is SPM/RegisterBank; neither corresponding raw branch reads them. Current checks reject bank SPM controls but not these stream fields on nonstream types.

Defaults: Ignored raw field values.

Validation: Source-visible consumer mismatch; no runtime acceptance proof claimed.

Disposition: validation_gap.

Consumer: [workbench/salam_workbench/config_contract.py:643](../../../workbench/salam_workbench/config_contract.py#L643), [SALAM-Configurator/parser.py:540](../../../SALAM-Configurator/parser.py#L540), [SALAM-Configurator/parser.py:572](../../../SALAM-Configurator/parser.py#L572).

Unresolved: Add per-Type key partition or explicit unconsumed_field diagnostics before native route.

### L047 - repeated Accelerator field across list mappings (e.g.PIOSize twice)

YAML loader rejects duplicate mapping keys, but fields repeated across separate Accelerator list items remain legal YAML. Contract fields.update collapses repeats while raw parser processes each occurrence (PIOSize can allocate twice, PIOMaster extends).

Defaults: Last-value wins in contract vs repeated side effects in generator.

Validation: No explicit cross-list duplicate-field rejection found on these source paths.

Disposition: validation_gap.

Transform: [SALAM-Configurator/parser.py:152](../../../SALAM-Configurator/parser.py#L152).

Consumer: [workbench/salam_workbench/config_contract.py:496](../../../workbench/salam_workbench/config_contract.py#L496), [workbench/salam_workbench/config_contract.py:533](../../../workbench/salam_workbench/config_contract.py#L533).

Unresolved: Canonicalizer should reject duplicate scalar fields across Accelerator list entries before comparing generated/effective output.

### L048 - ConfigPath / IrPath portable path shape disagreement

Contract IrPath rejects unsafe segments but is less restrictive than topology adapter portable regex and benchmarks/configs base requirement. Contract external suffix is case-sensitive while adapter lowercases suffix. PyPath normalization can mask dot components in some checks; adapter split-based rejection is stricter.

Defaults: No implicit canonical path rewrite.

Validation: Different entry points can reject the same input differently; stage adapter is intentionally fail-closed.

Disposition: normalization_gap.

Transform: [workbench/salam_workbench/topology_adapter.py:61](../../../workbench/salam_workbench/topology_adapter.py#L61).

Consumer: [workbench/salam_workbench/config_contract.py:168](../../../workbench/salam_workbench/config_contract.py#L168), [workbench/salam_workbench/config_contract.py:235](../../../workbench/salam_workbench/config_contract.py#L235).

Unresolved: A shared parser must produce one normalized relative path plus provenance, with explicit legacy base.

### L049 - configuration contract behavioral_limits literal

Result initialization still states 'Current C++ hasFunctionalUnit() returns false' in behavioral_limits. That literal can disagree with dynamic source-capability inspection and current retained scheduler; it is report text, not a gate.

Defaults: Hardcoded stale legacy statement.

Validation: Flag as stale reporting rather than using it as current scheduler evidence.

Disposition: stale_literal.

Consumer: [workbench/salam_workbench/config_contract.py:1264](../../../workbench/salam_workbench/config_contract.py#L1264), [src/hwacc/llvm_interface.cc:912](../../../src/hwacc/llvm_interface.cc#L912), [src/hwacc/HWModeling/generated/functionalunits/base.hh:140](../../../src/hwacc/HWModeling/generated/functionalunits/base.hh#L140).

Unresolved: Root core audit must provide current C++ authority; no production edit in Track A.

### L050 - gem5-SALAM-gui legacy config_generator output vs checked Workbench editor

Legacy GUI emits DMA/accelerator basic keys and symbolic FU mappings but omits PIOMaster, memories, many interrupt/topology fields in its simple gather routine. Current Workbench editor preserves raw loaded fields and renders memory/PIO/config inputs; checked GUI prepare explicitly records editor_form_appliedFalse and simulation_requestedFalse.

Defaults: Legacy DMA maxreq128/buffer256 and PIO32 widget defaults are producer literals, not shared schema.

Validation: Distinguish prepare-only receipt from apply-and-run request; legacy UI validation is not simulator verification.

Disposition: normalize_across_consumers.

Producer: [gem5-SALAM-gui/src/gui/config_generator.py:594](../../../gem5-SALAM-gui/src/gui/config_generator.py#L594).

Transform: [workbench/salam_workbench/gui_editor.py:265](../../../workbench/salam_workbench/gui_editor.py#L265), [workbench/salam_workbench/gui_editor.py:550](../../../workbench/salam_workbench/gui_editor.py#L550).

Consumer: [workbench/salam_workbench/configurator_gui_bridge.py:151](../../../workbench/salam_workbench/configurator_gui_bridge.py#L151), [workbench/salam_workbench/gui_editor.py:559](../../../workbench/salam_workbench/gui_editor.py#L559).

Unresolved: Preserve raw form provenance and staged consumer checks across new native factory.

### L051 - GUI trace_event_limit -> parameters.*.llvm_interface.fu_trace_event_limit

GUI optional budget mapped to each accelerator llvm_interface compiled scalar after source-supported marker check.

Defaults: Absent->native default; range1..4194304.

Validation: Control is distinct from benchmark configuration; it changes bounded trace output, not FU capacity.

Disposition: supported_source_path.

Transform: [workbench/salam_workbench/gui_editor.py:579](../../../workbench/salam_workbench/gui_editor.py#L579).

Consumer: [workbench/salam_workbench/gui_editor.py:594](../../../workbench/salam_workbench/gui_editor.py#L594).

### L052 - system.{kernel,disk-image,accpath,accbench,outdir,command-line-file,script,restore-with-cpu,checkpoint-dir}

Workbench rejects these reserved system keys and supplies kernel,disk-image,accpath,accbench from staged benchmark and engine paths. Template declares accpath/accbench but external generation remains responsible for literal IR/config bindings.

Defaults: Staged sw/main.elf; engine baremetal/common/fake.iso; benchmark parent/name.

Validation: Reserved keys cannot override pipeline artifact paths via system spec.

Disposition: supported_source_path.

Transform: [workbench/salam_workbench/configurator.py:51](../../../workbench/salam_workbench/configurator.py#L51).

Consumer: [workbench/salam_workbench/configurator.py:123](../../../workbench/salam_workbench/configurator.py#L123), [workbench/salam_workbench/configurator.py:934](../../../workbench/salam_workbench/configurator.py#L934), [SALAM-Configurator/fs_template.py:78](../../../SALAM-Configurator/fs_template.py#L78).

### L053 - duplicate YAML mapping keys in legacy benchmark files

Companion census found 122 duplicate mapping-key occurrences across seven legacy files: 16 Debug, eight instructions containers and 98 repeated opcode members. Every repeated value node serializes identically (122 equal, zero different); no conflicting-value change is demonstrated. Retained duplicate syntax is migration ambiguity and hygiene, not 122 distinct broken controls. Workbench _Loader rejects duplicate keys; raw PyYAML loaders collapse repeated keys before consumer logic.

Defaults: Identical retained duplicate values do not establish a general overwrite/default policy.

Validation: Raw-load versus strict-load semantics diverge. Serialized equality is source comparison, not execution equivalence; no simulator was rerun.

Disposition: normalization_gap.

Consumer: [workbench/salam_workbench/config_contract.py:20](../../../workbench/salam_workbench/config_contract.py#L20), [SALAM-Configurator/systembuilder.py:215](../../../SALAM-Configurator/systembuilder.py#L215), [HWProfileGenerator.py:25](../../../HWProfileGenerator.py#L25).

Unresolved: Preserve original bytes; reject or document deliberate duplicate-syntax cleanup. Do not inflate occurrence counts into distinct broken-control counts.

### L054 - Var.Address / Var.AccName / Var.StatusAddress (generator-injected)

Parser copies each authored Var map and overwrites Address and AccName from allocation/current accelerator; Stream additionally injects StatusAddress. These kwargs are consumer inputs but not user-editable topology YAML keys in checked schema.

Defaults: Derived from sequential allocator and ownership; not authored defaults.

Validation: Checked Var allowlist does not accept these internal keys. Explicit source values are overwritten in raw parser.

Disposition: derived_internal_field.

Producer: [SALAM-Configurator/parser.py:180](../../../SALAM-Configurator/parser.py#L180), [tools/SALAM-Configurator/config_parser.py:190](../../../tools/SALAM-Configurator/config_parser.py#L190).

Consumer: [SALAM-Configurator/parser.py:547](../../../SALAM-Configurator/parser.py#L547), [SALAM-Configurator/parser.py:568](../../../SALAM-Configurator/parser.py#L568), [workbench/salam_workbench/config_contract.py:643](../../../workbench/salam_workbench/config_contract.py#L643).

Unresolved: Typed factory should keep derived allocation/ownership separate from authored fields and report the transformation.

### L055 - benchmarks/comprehensive_test/config_{full,cache,stream}.yml: M5_PATH / benchmark / clusterN.{Dma,Acc,Spm,StreamDma,StreamBuffer,ClusterCache} / gui_publisher / system / debug_flags

These examples use a different YAML shape from acc_cluster and include explicit pio_addr/pio_size, read_ports/write_ports, MaxPendingReads/MaxPendingWrites, local_range_start/end, cache/use_cache, lowercase ready_mode/reset_on_read, publisher configuration and kernel/disk/cpu_type system metadata. The audited current raw builders select acc_cluster, and checked contract rejects these root keys. Implementation-source spelling search found no reader for gui_publisher, MaxPendingReads/MaxPendingWrites or these named variant filenames. No demonstrated translator into the active topology route was located.

Defaults: YAML literals are retained authored values, not current simulator defaults.

Validation: Unsupported input shape on audited routes; no runtime launch attempted. This does not prove no historical/external consumer ever existed.

Disposition: unresolved_legacy_dialect.

Producer: [benchmarks/comprehensive_test/config_full.yml:15](../../../benchmarks/comprehensive_test/config_full.yml#L15), [benchmarks/comprehensive_test/config_full.yml:23](../../../benchmarks/comprehensive_test/config_full.yml#L23), [benchmarks/comprehensive_test/config_full.yml:396](../../../benchmarks/comprehensive_test/config_full.yml#L396), [benchmarks/comprehensive_test/config_full.yml:1054](../../../benchmarks/comprehensive_test/config_full.yml#L1054), [benchmarks/comprehensive_test/config_cache.yml:19](../../../benchmarks/comprehensive_test/config_cache.yml#L19), [benchmarks/comprehensive_test/config_stream.yml:198](../../../benchmarks/comprehensive_test/config_stream.yml#L198).

Consumer: [SALAM-Configurator/systembuilder.py:271](../../../SALAM-Configurator/systembuilder.py#L271), [tools/SALAM-Configurator/systembuilder.py:70](../../../tools/SALAM-Configurator/systembuilder.py#L70), [workbench/salam_workbench/config_contract.py:324](../../../workbench/salam_workbench/config_contract.py#L324).

Unresolved: Do not interpret descriptive 'all features enabled' comments or native-looking key names as proof of constructed objects. Keep YAML M5_PATH metadata separate from the actively consumed environment variable of the same name. Find or write an explicitly reviewed importer before admitting this dialect.

### L056 - GUI global.memory.{base_address,alignment} / hw_config.<accelerator>.cycle_time

Legacy GUI produces and reloads global.memory metadata, and the current checked editor loads its base/alignment into widgets. Checked rendering validates/removes that metadata from consumer YAML; explicit snapshot base_address becomes pipeline request and alignment must equal 64. Legacy hw_config.cycle_time is recognized and removed: it never reached generated model on the old route. Current model/period/profile selection comes from explicit live hardware_profile snapshot instead.

Defaults: Loaded base default 0x10020000; alignment 64; explicit current profile selection replaces legacy cycle_time metadata.

Validation: GUI metadata has current consumers and transformation; it is not an active raw runtime override or an unconditionally orphaned field.

Disposition: normalize_across_consumers.

Producer: [gem5-SALAM-gui/src/gui/config_generator.py:635](../../../gem5-SALAM-gui/src/gui/config_generator.py#L635), [gem5-SALAM-gui/src/gui/config_generator.py:646](../../../gem5-SALAM-gui/src/gui/config_generator.py#L646).

Transform: [workbench/salam_workbench/gui_editor_qt.py:521](../../../workbench/salam_workbench/gui_editor_qt.py#L521), [workbench/salam_workbench/gui_editor.py:373](../../../workbench/salam_workbench/gui_editor.py#L373), [workbench/salam_workbench/gui_editor.py:391](../../../workbench/salam_workbench/gui_editor.py#L391).

Consumer: [gem5-SALAM-gui/src/gui/config_generator.py:912](../../../gem5-SALAM-gui/src/gui/config_generator.py#L912), [workbench/salam_workbench/gui_editor.py:526](../../../workbench/salam_workbench/gui_editor.py#L526), [workbench/salam_workbench/gui_editor.py:568](../../../workbench/salam_workbench/gui_editor.py#L568).

Unresolved: Keep metadata-to-request conversion source-hashed; do not silently treat old cycle_time numeric labels as live clock_period controls.

## Limits

- This inventory groups related concrete fields and patterns; it is not the separate exhaustive YAML occurrence census.
- Runtime C++ scheduling/numeric/profile consumption is covered by the companion core audit; cross-references here do not replace it.
- Unmatched custom scripts and external historical archives outside this isolated worktree have not been re-executed or broadly audited.
- No newly passing simulations or recovered historical characterization provenance are claimed.
