; SPDX-License-Identifier: BSD-3-Clause
; LLVM reference: peer PHIs read values as of block entry, simultaneously.
define i32 @main() {
entry:
  br label %loop
loop:
  %left = phi i32 [1, %entry], [%right, %loop]
  %right = phi i32 [2, %entry], [%left, %loop]
  %n = phi i32 [0, %entry], [%next, %loop]
  %next = add i32 %n, 1
  %done = icmp eq i32 %next, 2
  br i1 %done, label %exit, label %loop
exit:
  %ok_left = icmp eq i32 %left, 2
  %ok_right = icmp eq i32 %right, 1
  %ok = and i1 %ok_left, %ok_right
  %status = select i1 %ok, i32 0, i32 1
  ret i32 %status
}
