# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Joshua Slycord
from m5.objects.ClockedObject import ClockedObject
from m5.params import *
from m5.SimObject import PyBindMethod


class SalamRegisterBankTester(ClockedObject):
    type = "SalamRegisterBankTester"
    cxx_header = "hwacc/tests/register_bank_tester.hh"
    cxx_exports = [PyBindMethod("report")]
    port = RequestPort("Real register-bank timing requestor")
    load = RequestPort("Real atomic preload/functional observation port")
    bank = Param.RegisterBank("Production register bank under test")
    mode = Param.String("delta", "delta or response-retry")
    corrupt_expected = Param.Bool(False, "Negative numerical control")
