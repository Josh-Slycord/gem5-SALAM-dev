# SALAM SimObject lifecycle regression

This suite drives the production `CommInterface`, `LLVMInterface` and
`RegisterBank` through real gem5 ports and the global drain manager. Its C++
SimObjects are adversarial peers, enabled only by an explicit build option.
They do not replace the SALAM scheduling, request queues or graph ownership.
Run them with the explicit host runner below; default gem5 TestLib discovery
does not execute these fixtures.

## Build and run

Use Python 3.12 and the supported gem5 26 / LLVM 14 workbench environment.
From an isolated checkout, with the selected Python environment on `PATH`:

```sh
CXX=/usr/bin/g++ PYTHON_CONFIG=/usr/bin/python3.12-config \
  scons build/ARM/gem5.opt -j8 --with-salam \
  LLVM_CONFIG=/usr/bin/llvm-config-14 SALAM_PROTOCOL_TESTS=1
python workbench/scripts/verify_simobject_lifecycle.py \
  --gem5 build/ARM/gem5.opt \
  --output workbench/evidence/simobject-lifecycle
```

The output directory must be new. The runner records actual child PIDs,
commands, return codes, raw outputs, effective configuration, source hashes
and binary hashes before and after execution. It stops on unexpected failure.
Timeouts kill and reap only the child it launched. Deliberate fatal controls
have core dumps disabled in the test process, without changing system settings.

The normal suite has **15 successful simulator cases and five expected
rejections**. Expected rejections require their specific diagnostic and a
nonzero exit. They are not counted as successful simulations. The host checks
`config.ini` to establish the production types, connections, clocks and
negative-control parameters; it independently recomputes the observed results.

## Protocol coverage

| Production path | Conditions | Independent observations |
| --- | --- | --- |
| CommInterface local and ACP | Delayed response, inline response, two rejected request attempts, rejected-then-inline completion | A 70-byte unaligned read and write crossing three cache lines; raw bytes; six accepted packets/responses; actual send attempts including retries |
| CommInterface register port | The same four conditions | Unsplit 70-byte read/write; raw bytes; two accepted packets/responses; actual retry count |
| RegisterBank delta event | Atomic preload while response queue is empty; drain immediately | Value remains old before the 17 ns commit and becomes the expected eight-byte value after drain |
| RegisterBank timing response | Two rejected responses; a second request issued reentrantly during response delivery | Head packet retained; response order `0,0,0,1`; exactly two completions; nonzero payload preserved |

Each driver first drains an idle system at tick zero, then resumes simulation.
Busy cases require drain to advance the real event queue before completion.
The inline-only case may already be quiescent when drain is requested.

## Independent accelerator lifetimes

Two actual LLVM interfaces, each with its own communication and hardware
objects, execute different loop kernels. Starts use actual accelerator MMIO.

1. A1 executes four iterations and produces `17 + sum(range(4)) = 23`.
   B1 is still running its 256 iterations.
2. A1's captured graph handles must expire while B1's remain live. A2 starts
   512 iterations while B1 is active; its old output bytes are removed first.
3. B1 produces `sum(range(256)) = 32640`. Its graph must expire while A2
   remains live. B2 starts 16 iterations while A2 is active, with fresh output.
4. The global drain begins with both second invocations active. B2 finishes
   with `120` while A2 remains active; A2 eventually finishes with `130833`.
5. Both interfaces report exactly two completed invocations and four fresh
   output responses in total. Current and previous captured weak references
   must all expire. The host recomputes every sum independently.

No global "all objects must be dead" counter is used: finishing one actor
must not invalidate another actor's graph. The negative controls deliberately
retain an A1 graph value, corrupt the expected read, corrupt the expected
lifetime result, and corrupt each RegisterBank expectation. Every control must
be rejected for its intended cause.

## Production fixes

- Publish active logical requests and update their remaining-byte/address
  state before `sendTimingReq`. A synchronous completion can delete the
  logical request inside that call; code after it must not dereference it.
- Count native send attempts at actual port sends, including retries, rather
  than counting packets merely appended behind a stalled request.
- Keep CommInterface draining while queued/active requests, blocked packets,
  carrier requests, an invocation or a scheduled service event remain. Check
  for drain completion after service and computation finish.
- Initialize LLVM running state and drain its active invocation, graph,
  outstanding queues, scheduled tick and FU leases. Signal completion only
  after normal per-instance finalization has released that state.
- Include RegisterBank's pending delta commit, response delivery, response
  retry and queue in drain. Check completion after both commit and dequeue.

The suite also caught two fixture defects: parenting an accelerator before
assigning child back-references prevents recursive SimObject adoption; wiring
the lifetime corruption flag makes its numerical negative control effective.

## Preserved failure controls and scope

A binary compiled with the pre-fix production code and the corrected fixtures
is retained separately in local evidence. Run its regression mode with:

```sh
python workbench/scripts/verify_simobject_lifecycle.py \
  --gem5 /path/to/preserved/pre-fix/gem5.opt \
  --output workbench/evidence/pre-fix-controls --baseline
```

That mode requires four specific pre-fix failures: synchronous callback order,
communication drain, concurrent LLVM drain, and RegisterBank's pending delta.
It also requires the already-healthy bank response-retry case to succeed.
It is a reproduction tool for that preserved baseline, not a pass criterion
for new implementations or unrelated historical versions.

Drain proves quiescence for these scenarios. It does **not** establish full
checkpoint serialization/restore support. Captured weak-reference expiration
checks these per-instance graphs, not whole-engine leak freedom under LSan.
The separate sanitized helper suite covers helper code, not an instrumented
full simulator. DMA, stream and scratchpad-specific protocols still need
real end-to-end coverage; source changes shared with SPM are not treated as
SPM runtime proof. Physical power/area calibration and licensing gates remain
separate upstream-readiness work.

The ordinary production build excludes both tester SimObjects when
`SALAM_PROTOCOL_TESTS` is omitted. Generated binaries, raw results and build
caches stay in ignored evidence/build locations. A dated validation record
links the exact source-bound runs without placing large outputs in Git.
