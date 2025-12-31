; ModuleID = 'source/cluster0/integer_stress.c'
source_filename = "source/cluster0/integer_stress.c"
target datalayout = "e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64"
target triple = "armv7-unknown-linux-gnueabihf"

; Function Attrs: nofree norecurse nounwind
define dso_local void @compute(i32* nocapture readonly %input_a, i32* nocapture readonly %input_b, i32* nocapture %output) local_unnamed_addr #0 {
entry:
  br label %for.body

for.body:                                         ; preds = %entry, %for.body
  %i.020 = phi i32 [ 0, %entry ], [ %inc, %for.body ]
  %arrayidx = getelementptr inbounds i32, i32* %input_a, i32 %i.020
  %0 = load i32, i32* %arrayidx, align 4, !tbaa !3
  %arrayidx1 = getelementptr inbounds i32, i32* %input_b, i32 %i.020
  %1 = load i32, i32* %arrayidx1, align 4, !tbaa !3
  %mul19 = add i32 %1, 2
  %add3 = mul i32 %mul19, %0
  %arrayidx4 = getelementptr inbounds i32, i32* %output, i32 %i.020
  store i32 %add3, i32* %arrayidx4, align 4, !tbaa !3
  %inc = add nuw nsw i32 %i.020, 1
  %exitcond.not = icmp eq i32 %inc, 4
  br i1 %exitcond.not, label %for.end, label %for.body, !llvm.loop !7

for.end:                                          ; preds = %for.body
  ret void
}

; Function Attrs: nofree norecurse nounwind
define dso_local void @top() local_unnamed_addr #0 {
entry:
  call void @compute(i32* nonnull inttoptr (i32 268566848 to i32*), i32* nonnull inttoptr (i32 268571008 to i32*), i32* nonnull inttoptr (i32 268575168 to i32*))
  ret void
}

attributes #0 = { nofree norecurse nounwind "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "min-legal-vector-width"="0" "no-infs-fp-math"="false" "no-jump-tables"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="generic" "target-features"="+armv7-a,+dsp,+fp64,+vfp2,+vfp2sp,+vfp3d16,+vfp3d16sp,-thumb-mode" "unsafe-fp-math"="false" "use-soft-float"="false" }

!llvm.module.flags = !{!0, !1}
!llvm.ident = !{!2}

!0 = !{i32 1, !"wchar_size", i32 4}
!1 = !{i32 1, !"min_enum_size", i32 4}
!2 = !{!"Ubuntu clang version 12.0.0-3ubuntu1~20.04.5"}
!3 = !{!4, !4, i64 0}
!4 = !{!"int", !5, i64 0}
!5 = !{!"omnipotent char", !6, i64 0}
!6 = !{!"Simple C/C++ TBAA"}
!7 = distinct !{!7, !8, !9}
!8 = !{!"llvm.loop.mustprogress"}
!9 = !{!"llvm.loop.unroll.disable"}
