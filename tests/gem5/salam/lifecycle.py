# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Joshua Slycord
"""Drive actual production SimObjects with an opt-in adversarial test peer."""
import argparse
import json
import sys
from pathlib import Path

import m5
from m5.objects import *

parser = argparse.ArgumentParser()
parser.add_argument(
    "--mode",
    choices=("async", "sync", "retry", "retry-sync", "lifetime"),
    required=True,
)
parser.add_argument(
    "--route", choices=("local", "acp", "reg"), default="local"
)
parser.add_argument("--corrupt-expected", action="store_true")
parser.add_argument("--retain-graph", action="store_true")
args = parser.parse_args()
repo = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo / "configs"))
from SALAM import HWAccConfig as hardware

system = System(
    mem_mode="timing", mem_ranges=[AddrRange(0x80000000, size=4096)]
)
system.voltage_domain = VoltageDomain()
system.clk_domain = SrcClockDomain(
    clock="100MHz", voltage_domain=system.voltage_domain
)
system.mem = SimpleMemory(range=system.mem_ranges[0])
system.system_port = system.mem.port


def accelerator(name, address, ir=None):
    acc = CommInterface(
        pio_addr=address, pio_size=32, gic=NULL, int_num=-1, clock_period=10
    )
    # Attach the device before assigning back-references from its children.
    setattr(system, name, acc)
    if ir:
        acc.llvm_interface = LLVMInterface(in_file=str(ir), clock_period=10)
        acc.hw_interface = HWInterface(cycle_counts=CycleCounts())
        hardware._instantiate_functional_units(acc, {})
        hardware._instantiate_instructions(acc, {})
        hardware._apply_cycle_counts(acc, {})
        acc.hw_interface.salam_power_model = SALAMPowerModel()
        acc.hw_interface.hw_statistics = HWStatistics()
        acc.hw_interface.simulator_config = SimulatorConfig()
        acc.hw_interface.opcodes = InstOpCodes()
        acc.llvm_interface.comm_int = acc
        acc.llvm_interface.hw_int = acc.hw_interface
    return acc


accelerator(
    "a",
    0x10000000,
    Path(__file__).with_name("lifetime_a.ll")
    if args.mode == "lifetime"
    else None,
)
if args.mode == "lifetime":
    accelerator("b", 0x10001000, Path(__file__).with_name("lifetime_b.ll"))
    system.tester = SalamLifecycleTester(
        comm_int=system.a,
        hw_int=NULL,
        mode=args.mode,
        actor_a=system.a.llvm_interface,
        actor_b=system.b.llvm_interface,
        retain_graph=args.retain_graph,
        corrupt_expected=args.corrupt_expected,
    )
    system.a.local = system.tester.memory
    system.b.local = system.tester.memory
    system.tester.pio = system.a.pio
    system.tester.pio = system.b.pio
else:
    system.tester = SalamLifecycleTester(
        comm_int=system.a,
        hw_int=NULL,
        mode=args.mode,
        route=args.route,
        corrupt_expected=args.corrupt_expected,
    )
    setattr(system.a, args.route, system.tester.memory)
    system.tester.pio = system.a.pio
root = Root(full_system=False, system=system)
m5.instantiate()
m5.drain()
if int(m5.curTick()) != 0:
    raise RuntimeError("idle drain advanced the event queue")
reports = []
for round_index in range(1):
    event = m5.simulate(1000000000)
    if event.getCause() != "salam fixture ready":
        raise RuntimeError(
            "fixture did not reach real pending state: " + event.getCause()
        )
    before = int(m5.curTick())
    m5.drain()
    after = int(m5.curTick())
    report = json.loads(system.tester.report())
    if after <= before and args.mode != "sync":
        raise RuntimeError(
            "drain completed without advancing pending simulation"
        )
    report.update(drain_requested_tick=before, drained_tick=after)
    reports.append(report)
path = Path(m5.options.outdir) / "lifecycle.json"
path.write_text(
    json.dumps(
        {"state": "passed", "mode": args.mode, "rounds": reports}, indent=2
    )
    + "\n"
)
print(
    json.dumps({"state": "passed", "mode": args.mode, "rounds": len(reports)})
)
