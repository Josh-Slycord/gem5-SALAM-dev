; SPDX-License-Identifier: BSD-3-Clause
; LLVM reference: remainder takes the numerator sign and truncates quotient.
define i32 @main() {
entry:
  %a = frem float 7.0, 4.0
  %b = frem double -7.0, 4.0
  %ok_a = fcmp oeq float %a, 3.0
  %ok_b = fcmp oeq double %b, -3.0
  %ok = and i1 %ok_a, %ok_b
  %status = select i1 %ok, i32 0, i32 1
  ret i32 %status
}
