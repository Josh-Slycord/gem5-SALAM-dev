; ModuleID = 'viterbi.c'
source_filename = "viterbi.c"
target datalayout = "e-m:e-p:32:32-p270:32:32-p271:32:32-p272:64:64-f64:32:64-f80:32-n8:16:32-S128"
target triple = "i386-pc-linux-gnu"

; Function Attrs: nofree noinline nounwind
define dso_local i32 @viterbi(i8* nocapture readonly %0, double* nocapture readonly %1, double* nocapture readonly %2, double* nocapture readonly %3, i8* nocapture %4) local_unnamed_addr #0 {
  %6 = alloca [140 x [64 x double]], align 8
  %7 = bitcast [140 x [64 x double]]* %6 to i8*
  call void @llvm.lifetime.start.p0i8(i64 71680, i8* nonnull %7) #2
  %8 = load i8, i8* %0, align 1, !tbaa !3
  %9 = zext i8 %8 to i32
  br label %10

10:                                               ; preds = %5, %10
  %11 = phi i32 [ 0, %5 ], [ %20, %10 ]
  %12 = getelementptr inbounds double, double* %1, i32 %11
  %13 = load double, double* %12, align 4, !tbaa !6
  %14 = shl nuw nsw i32 %11, 6
  %15 = add nuw nsw i32 %14, %9
  %16 = getelementptr inbounds double, double* %3, i32 %15
  %17 = load double, double* %16, align 4, !tbaa !6
  %18 = fadd double %13, %17
  %19 = getelementptr inbounds [140 x [64 x double]], [140 x [64 x double]]* %6, i32 0, i32 0, i32 %11
  store double %18, double* %19, align 8, !tbaa !6
  %20 = add nuw nsw i32 %11, 1
  %21 = icmp eq i32 %20, 64
  br i1 %21, label %22, label %10, !llvm.loop !8

22:                                               ; preds = %10, %59
  %23 = phi i32 [ %60, %59 ], [ 1, %10 ]
  %24 = add nsw i32 %23, -1
  %25 = getelementptr inbounds [140 x [64 x double]], [140 x [64 x double]]* %6, i32 0, i32 %24, i32 0
  %26 = getelementptr inbounds i8, i8* %0, i32 %23
  %27 = load i8, i8* %26, align 1, !tbaa !3
  %28 = zext i8 %27 to i32
  br label %29

29:                                               ; preds = %22, %55
  %30 = phi i32 [ 0, %22 ], [ %57, %55 ]
  %31 = load double, double* %25, align 8, !tbaa !6
  %32 = getelementptr inbounds double, double* %2, i32 %30
  %33 = load double, double* %32, align 4, !tbaa !6
  %34 = fadd double %31, %33
  %35 = shl nuw nsw i32 %30, 6
  %36 = add nuw nsw i32 %35, %28
  %37 = getelementptr inbounds double, double* %3, i32 %36
  %38 = load double, double* %37, align 4, !tbaa !6
  %39 = fadd double %34, %38
  br label %40

40:                                               ; preds = %29, %40
  %41 = phi i32 [ 1, %29 ], [ %53, %40 ]
  %42 = phi double [ %39, %29 ], [ %52, %40 ]
  %43 = getelementptr inbounds [140 x [64 x double]], [140 x [64 x double]]* %6, i32 0, i32 %24, i32 %41
  %44 = load double, double* %43, align 8, !tbaa !6
  %45 = shl nuw nsw i32 %41, 6
  %46 = add nuw nsw i32 %45, %30
  %47 = getelementptr inbounds double, double* %2, i32 %46
  %48 = load double, double* %47, align 4, !tbaa !6
  %49 = fadd double %44, %48
  %50 = fadd double %38, %49
  %51 = fcmp olt double %50, %42
  %52 = select i1 %51, double %50, double %42
  %53 = add nuw nsw i32 %41, 1
  %54 = icmp eq i32 %53, 64
  br i1 %54, label %55, label %40, !llvm.loop !11

55:                                               ; preds = %40
  %56 = getelementptr inbounds [140 x [64 x double]], [140 x [64 x double]]* %6, i32 0, i32 %23, i32 %30
  store double %52, double* %56, align 8, !tbaa !6
  %57 = add nuw nsw i32 %30, 1
  %58 = icmp eq i32 %57, 64
  br i1 %58, label %59, label %29, !llvm.loop !12

59:                                               ; preds = %55
  %60 = add nuw nsw i32 %23, 1
  %61 = icmp eq i32 %60, 140
  br i1 %61, label %62, label %22, !llvm.loop !13

62:                                               ; preds = %59
  %63 = getelementptr inbounds [140 x [64 x double]], [140 x [64 x double]]* %6, i32 0, i32 139, i32 0
  %64 = load double, double* %63, align 8, !tbaa !6
  br label %65

65:                                               ; preds = %62, %65
  %66 = phi i32 [ 1, %62 ], [ %75, %65 ]
  %67 = phi i8 [ 0, %62 ], [ %74, %65 ]
  %68 = phi double [ %64, %62 ], [ %72, %65 ]
  %69 = getelementptr inbounds [140 x [64 x double]], [140 x [64 x double]]* %6, i32 0, i32 139, i32 %66
  %70 = load double, double* %69, align 8, !tbaa !6
  %71 = fcmp olt double %70, %68
  %72 = select i1 %71, double %70, double %68
  %73 = trunc i32 %66 to i8
  %74 = select i1 %71, i8 %73, i8 %67
  %75 = add nuw nsw i32 %66, 1
  %76 = icmp eq i32 %75, 64
  br i1 %76, label %77, label %65, !llvm.loop !14

77:                                               ; preds = %65
  %78 = getelementptr inbounds i8, i8* %4, i32 139
  store i8 %74, i8* %78, align 1, !tbaa !3
  br label %79

79:                                               ; preds = %77, %107
  %80 = phi i32 [ 138, %77 ], [ %109, %107 ]
  %81 = getelementptr inbounds [140 x [64 x double]], [140 x [64 x double]]* %6, i32 0, i32 %80, i32 0
  %82 = load double, double* %81, align 8, !tbaa !6
  %83 = add nuw nsw i32 %80, 1
  %84 = getelementptr inbounds i8, i8* %4, i32 %83
  %85 = load i8, i8* %84, align 1, !tbaa !3
  %86 = zext i8 %85 to i32
  %87 = getelementptr inbounds double, double* %2, i32 %86
  %88 = load double, double* %87, align 4, !tbaa !6
  %89 = fadd double %82, %88
  br label %90

90:                                               ; preds = %79, %90
  %91 = phi i32 [ 1, %79 ], [ %105, %90 ]
  %92 = phi i8 [ 0, %79 ], [ %104, %90 ]
  %93 = phi double [ %89, %79 ], [ %102, %90 ]
  %94 = getelementptr inbounds [140 x [64 x double]], [140 x [64 x double]]* %6, i32 0, i32 %80, i32 %91
  %95 = load double, double* %94, align 8, !tbaa !6
  %96 = shl nuw nsw i32 %91, 6
  %97 = add nuw nsw i32 %96, %86
  %98 = getelementptr inbounds double, double* %2, i32 %97
  %99 = load double, double* %98, align 4, !tbaa !6
  %100 = fadd double %95, %99
  %101 = fcmp olt double %100, %93
  %102 = select i1 %101, double %100, double %93
  %103 = trunc i32 %91 to i8
  %104 = select i1 %101, i8 %103, i8 %92
  %105 = add nuw nsw i32 %91, 1
  %106 = icmp eq i32 %105, 64
  br i1 %106, label %107, label %90, !llvm.loop !15

107:                                              ; preds = %90
  %108 = getelementptr inbounds i8, i8* %4, i32 %80
  store i8 %104, i8* %108, align 1, !tbaa !3
  %109 = add nsw i32 %80, -1
  %110 = icmp eq i32 %80, 0
  br i1 %110, label %111, label %79, !llvm.loop !16

111:                                              ; preds = %107
  call void @llvm.lifetime.end.p0i8(i64 71680, i8* nonnull %7) #2
  ret i32 0
}

; Function Attrs: argmemonly nofree nosync nounwind willreturn
declare void @llvm.lifetime.start.p0i8(i64 immarg, i8* nocapture) #1

; Function Attrs: argmemonly nofree nosync nounwind willreturn
declare void @llvm.lifetime.end.p0i8(i64 immarg, i8* nocapture) #1

; Function Attrs: nofree noinline nounwind
define dso_local void @top() local_unnamed_addr #0 {
  %1 = call i32 @viterbi(i8* nonnull inttoptr (i32 789577728 to i8*), double* nonnull inttoptr (i32 789578240 to double*), double* nonnull inttoptr (i32 789578752 to double*), double* nonnull inttoptr (i32 789611520 to double*), i8* nonnull inttoptr (i32 789577984 to i8*)) #3
  ret void
}

attributes #0 = { nofree noinline nounwind "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "min-legal-vector-width"="0" "no-builtins" "no-infs-fp-math"="false" "no-jump-tables"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="i686" "target-features"="+cx8,+x87" "tune-cpu"="generic" "unsafe-fp-math"="false" "use-soft-float"="false" }
attributes #1 = { argmemonly nofree nosync nounwind willreturn }
attributes #2 = { nounwind }
attributes #3 = { nobuiltin "no-builtins" }

!llvm.module.flags = !{!0, !1}
!llvm.ident = !{!2}

!0 = !{i32 1, !"NumRegisterParameters", i32 0}
!1 = !{i32 1, !"wchar_size", i32 4}
!2 = !{!"Ubuntu clang version 12.0.0-3ubuntu1~20.04.5"}
!3 = !{!4, !4, i64 0}
!4 = !{!"omnipotent char", !5, i64 0}
!5 = !{!"Simple C/C++ TBAA"}
!6 = !{!7, !7, i64 0}
!7 = !{!"double", !4, i64 0}
!8 = distinct !{!8, !9, !10}
!9 = !{!"llvm.loop.mustprogress"}
!10 = !{!"llvm.loop.unroll.disable"}
!11 = distinct !{!11, !9, !10}
!12 = distinct !{!12, !9, !10}
!13 = distinct !{!13, !9, !10}
!14 = distinct !{!14, !9, !10}
!15 = distinct !{!15, !9, !10}
!16 = distinct !{!16, !9, !10}
