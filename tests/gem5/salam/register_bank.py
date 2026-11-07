# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Joshua Slycord
import argparse
import json
from pathlib import Path

import m5
from m5.objects import *

p = argparse.ArgumentParser()
p.add_argument("--mode", choices=("delta", "response-retry"), required=True)
p.add_argument("--corrupt-expected", action="store_true")
a = p.parse_args()
system = System(
    mem_mode="timing", mem_ranges=[AddrRange(0x80000000, size=4096)]
)
system.voltage_domain = VoltageDomain()
system.clk_domain = SrcClockDomain(
    clock="100MHz", voltage_domain=system.voltage_domain
)
system.mem = SimpleMemory(range=system.mem_ranges[0])
system.system_port = system.mem.port
system.bank = RegisterBank(
    range=AddrRange(0x4000, size=4096), delta_time="17ns"
)
system.tester = SalamRegisterBankTester(
    bank=system.bank, mode=a.mode, corrupt_expected=a.corrupt_expected
)
system.tester.port = system.bank.reg_port
system.tester.load = system.bank.load_port
root = Root(full_system=False, system=system)
m5.instantiate()
m5.drain()
if int(m5.curTick()) != 0:
    raise RuntimeError("idle drain advanced the event queue")
event = m5.simulate(1000000)
if event.getCause() != "salam bank fixture ready":
    raise RuntimeError(event.getCause())
before = int(m5.curTick())
m5.drain()
after = int(m5.curTick())
result = json.loads(system.tester.report())
if after <= before:
    raise RuntimeError("RegisterBank drain did not wait for pending work")
result.update(drain_requested_tick=before, drained_tick=after)
(Path(m5.options.outdir) / "register-bank.json").write_text(
    json.dumps(result, indent=2) + "\n"
)
print(json.dumps(result))
