; SPDX-License-Identifier: BSD-3-Clause
; Copyright (c) 2026 Joshua Slycord
; Each actor accepts its own runtime loop count and output address.
define void @top(i32* %out, i32 %count) {
entry:
  br label %loop
loop:
  %i = phi i32 [ 0, %entry ], [ %next, %loop ]
  %sum = phi i32 [ 0, %entry ], [ %added, %loop ]
  %added = add i32 %sum, %i
  %next = add i32 %i, 1
  %again = icmp ult i32 %next, %count
  br i1 %again, label %loop, label %exit
exit:
  %result = add i32 %added, 17
  store i32 %result, i32* %out
  ret void
}
