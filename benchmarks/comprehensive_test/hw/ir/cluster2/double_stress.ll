; ModuleID = 'source/cluster2/double_stress.c'
source_filename = "source/cluster2/double_stress.c"
target datalayout = "e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64"
target triple = "armv7-unknown-linux-gnueabihf"

; Function Attrs: nofree norecurse nounwind
define dso_local void @compute(double* nocapture readonly %input_a, double* nocapture readonly %input_b, double* nocapture %output) local_unnamed_addr #0 {
entry:
  br label %for.body

for.body:                                         ; preds = %entry, %for.body
  %i.019 = phi i32 [ 0, %entry ], [ %inc, %for.body ]
  %arrayidx = getelementptr inbounds double, double* %input_a, i32 %i.019
  %0 = load double, double* %arrayidx, align 8, !tbaa !3
  %arrayidx1 = getelementptr inbounds double, double* %input_b, i32 %i.019
  %1 = load double, double* %arrayidx1, align 8, !tbaa !3
  %add = fadd double %0, %1
  %sub = fsub double %0, %1
  %mul = fmul double %0, %1
  %add2 = fadd double %add, %sub
  %add3 = fadd double %mul, %add2
  %arrayidx4 = getelementptr inbounds double, double* %output, i32 %i.019
  store double %add3, double* %arrayidx4, align 8, !tbaa !3
  %inc = add nuw nsw i32 %i.019, 1
  %exitcond.not = icmp eq i32 %inc, 4
  br i1 %exitcond.not, label %for.end, label %for.body, !llvm.loop !7

for.end:                                          ; preds = %for.body
  ret void
}

; Function Attrs: nofree norecurse nounwind
define dso_local void @top() local_unnamed_addr #0 {
entry:
  call void @compute(double* nonnull inttoptr (i32 268600768 to double*), double* nonnull inttoptr (i32 268609024 to double*), double* nonnull inttoptr (i32 268617280 to double*))
  ret void
}

attributes #0 = { nofree norecurse nounwind "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "min-legal-vector-width"="0" "no-infs-fp-math"="false" "no-jump-tables"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="generic" "target-features"="+armv7-a,+dsp,+fp64,+vfp2,+vfp2sp,+vfp3d16,+vfp3d16sp,-thumb-mode" "unsafe-fp-math"="false" "use-soft-float"="false" }

!llvm.module.flags = !{!0, !1}
!llvm.ident = !{!2}

!0 = !{i32 1, !"wchar_size", i32 4}
!1 = !{i32 1, !"min_enum_size", i32 4}
!2 = !{!"Ubuntu clang version 12.0.0-3ubuntu1~20.04.5"}
!3 = !{!4, !4, i64 0}
!4 = !{!"double", !5, i64 0}
!5 = !{!"omnipotent char", !6, i64 0}
!6 = !{!"Simple C/C++ TBAA"}
!7 = distinct !{!7, !8, !9}
!8 = !{!"llvm.loop.mustprogress"}
!9 = !{!"llvm.loop.unroll.disable"}
