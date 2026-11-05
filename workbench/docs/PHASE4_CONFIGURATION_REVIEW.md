# Configuration fixes from the final Gemini snapshot

The final reviewed Gemini source is commit `b9c798893d53e8565943aed6678a151434d4a5f1`.
This checkpoint selectively integrates configuration repairs from that immutable
snapshot. It retains the workbench's modern full-system template. Native clock
binding is applied centrally in Simulation.run after final scalar overrides;
the clock adapter has separate native-binding contract tests.

## Integrated behavior

- Both parsers retain the correct DMA buffer and maximum-request arguments when
  `InterruptNum` is omitted. They normalize every LocalBus entry, generate
  accelerator-to-accelerator PIO connections, and parse explicit connection port
  counts as integers.
- Both system builders recognize header markers despite surrounding whitespace
  and preserve custom header content. The legacy tools builder now handles
  multiple cluster headers independently, closes YAML inputs, uses the actual
  CLI argument names, and binds full-system placeholders by content.
- MobileNet profile selection uses relative path components instead of fixed
  absolute offsets and skips empty YAML documents. A local follow-up prevents an
  engine directory named `mobilenetv2` from misclassifying ordinary benchmarks.
- Generated full-system scripts retain the Simulation.run call. Its central
  final-parameter stage binds the retained SALAM periods to native clock domains.

The configuration-tier suite already includes `test_systembuilder_template`.
Its 16 tests cover both actual renderers, both actual parsers, multi-cluster
header regeneration, malformed placeholders, shifted templates, Simulation.run
call retention, and MobileNet path depth/root-name controls. Source-only CLI
regeneration also passed for all ten shipped system-validation benchmark
configurations through both builders. These checks do not establish numerical
simulator correctness.

## Deliberately deferred or unresolved

The final snapshot's new `AccCluster.cache_*` Params are deferred. Generated
callers omit the `cache_size` argument, whose zero default disables cache
creation. Even when enabled by a direct caller, copying the cluster's values
into a child Cache during construction does not propagate later `--param`
overrides. Integration needs an intentional activation path, native parent
parameter references or equivalent propagation, and a real `config.ini` check.
The existing cache implementation is preserved.

Omitting `InterruptNum` preserves the default IRQ 200 on `NoncoherentDma`. It does not
disable interrupt generation. Native DMA completion still sends/clears a GIC
interrupt; no optional-interrupt capability is claimed.

The legacy tools full-system template remains a compatibility artifact. Both
templates call Simulation.run and therefore share its final clock adapter.
Executing the older tools template end to end under gem5 26 has not been
qualified; the modern workbench uses `SALAM-Configurator/fs_template.py`.

MobileNet's `top.ll` basename and some configured `*_Top` profile keys still
differ in case. The relative-path repair does not qualify the full MobileNet
workload or resolve that older profile naming mismatch.

Local detailed evidence is saved in
`/home/jslycord/projects/salam-phase4-config-evidence-20261105/validation.json`.
