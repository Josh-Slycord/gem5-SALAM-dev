# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Joshua Slycord
"""Opt-in adversarial peer for production SALAM SimObjects."""
from m5.objects.ComputeUnit import ComputeUnit
from m5.params import *
from m5.SimObject import PyBindMethod


class SalamLifecycleTester(ComputeUnit):
    type = "SalamLifecycleTester"
    cxx_header = "hwacc/tests/lifecycle_tester.hh"
    cxx_exports = [PyBindMethod("report")]
    memory = VectorResponsePort("Controlled timing-memory peers")
    pio = VectorRequestPort("Actual accelerator PIO connections")
    route = Param.String("local", "local, acp or reg production port")
    mode = Param.String("retry", "async, sync, retry, retry-sync or lifetime")
    actor_a = Param.LLVMInterface(NULL, "First real LLVM actor")
    actor_b = Param.LLVMInterface(NULL, "Second real LLVM actor")
    corrupt_expected = Param.Bool(False, "Negative control: wrong expected byte")
    retain_graph = Param.Bool(False, "Negative control: retain one graph value")
