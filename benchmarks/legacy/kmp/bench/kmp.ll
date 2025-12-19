; ModuleID = 'kmp.c'
source_filename = "kmp.c"
target datalayout = "e-m:e-p:32:32-p270:32:32-p271:32:32-p272:64:64-f64:32:64-f80:32-n8:16:32-S128"
target triple = "i386-pc-linux-gnu"

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @CPF(i8* nocapture readonly %0, i32* nocapture %1) local_unnamed_addr #0 {
  store i32 0, i32* %1, align 4, !tbaa !3
  br label %3

3:                                                ; preds = %2, %19
  %4 = phi i32 [ 1, %2 ], [ %29, %19 ]
  %5 = phi i32 [ 0, %2 ], [ %27, %19 ]
  %6 = icmp sgt i32 %5, 0
  br i1 %6, label %7, label %19

7:                                                ; preds = %3
  %8 = getelementptr inbounds i8, i8* %0, i32 %4
  %9 = load i8, i8* %8, align 1, !tbaa !7
  %10 = getelementptr inbounds i32, i32* %1, i32 %4
  br label %11

11:                                               ; preds = %7, %16
  %12 = phi i32 [ %5, %7 ], [ %17, %16 ]
  %13 = getelementptr inbounds i8, i8* %0, i32 %12
  %14 = load i8, i8* %13, align 1, !tbaa !7
  %15 = icmp eq i8 %14, %9
  br i1 %15, label %19, label %16

16:                                               ; preds = %11
  %17 = load i32, i32* %10, align 4, !tbaa !3
  %18 = icmp sgt i32 %17, 0
  br i1 %18, label %11, label %19, !llvm.loop !8

19:                                               ; preds = %11, %16, %3
  %20 = phi i32 [ %5, %3 ], [ %12, %11 ], [ %17, %16 ]
  %21 = getelementptr inbounds i8, i8* %0, i32 %20
  %22 = load i8, i8* %21, align 1, !tbaa !7
  %23 = getelementptr inbounds i8, i8* %0, i32 %4
  %24 = load i8, i8* %23, align 1, !tbaa !7
  %25 = icmp eq i8 %22, %24
  %26 = zext i1 %25 to i32
  %27 = add nsw i32 %20, %26
  %28 = getelementptr inbounds i32, i32* %1, i32 %4
  store i32 %27, i32* %28, align 4, !tbaa !3
  %29 = add nuw nsw i32 %4, 1
  %30 = icmp eq i32 %29, 4
  br i1 %30, label %31, label %3, !llvm.loop !11

31:                                               ; preds = %19
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local i32 @kmp(i8* nocapture readonly %0, i8* nocapture readonly %1, i32* nocapture %2, i32* nocapture %3) local_unnamed_addr #0 {
  store i32 0, i32* %3, align 4, !tbaa !3
  call void @CPF(i8* %0, i32* %2) #1
  br label %5

5:                                                ; preds = %4, %37
  %6 = phi i32 [ 0, %4 ], [ %38, %37 ]
  %7 = phi i32 [ 0, %4 ], [ %39, %37 ]
  %8 = icmp sgt i32 %6, 0
  br i1 %8, label %9, label %21

9:                                                ; preds = %5
  %10 = getelementptr inbounds i8, i8* %1, i32 %7
  %11 = load i8, i8* %10, align 1, !tbaa !7
  br label %12

12:                                               ; preds = %9, %17
  %13 = phi i32 [ %6, %9 ], [ %19, %17 ]
  %14 = getelementptr inbounds i8, i8* %0, i32 %13
  %15 = load i8, i8* %14, align 1, !tbaa !7
  %16 = icmp eq i8 %15, %11
  br i1 %16, label %21, label %17

17:                                               ; preds = %12
  %18 = getelementptr inbounds i32, i32* %2, i32 %13
  %19 = load i32, i32* %18, align 4, !tbaa !3
  %20 = icmp sgt i32 %19, 0
  br i1 %20, label %12, label %21, !llvm.loop !12

21:                                               ; preds = %12, %17, %5
  %22 = phi i32 [ %6, %5 ], [ %13, %12 ], [ %19, %17 ]
  %23 = getelementptr inbounds i8, i8* %0, i32 %22
  %24 = load i8, i8* %23, align 1, !tbaa !7
  %25 = getelementptr inbounds i8, i8* %1, i32 %7
  %26 = load i8, i8* %25, align 1, !tbaa !7
  %27 = icmp eq i8 %24, %26
  %28 = zext i1 %27 to i32
  %29 = add nsw i32 %22, %28
  %30 = icmp sgt i32 %29, 3
  br i1 %30, label %31, label %37

31:                                               ; preds = %21
  %32 = load i32, i32* %3, align 4, !tbaa !3
  %33 = add nsw i32 %32, 1
  store i32 %33, i32* %3, align 4, !tbaa !3
  %34 = add nsw i32 %29, -1
  %35 = getelementptr inbounds i32, i32* %2, i32 %34
  %36 = load i32, i32* %35, align 4, !tbaa !3
  br label %37

37:                                               ; preds = %21, %31
  %38 = phi i32 [ %36, %31 ], [ %29, %21 ]
  %39 = add nuw nsw i32 %7, 1
  %40 = icmp eq i32 %39, 32411
  br i1 %40, label %41, label %5, !llvm.loop !13

41:                                               ; preds = %37
  ret i32 0
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @top() local_unnamed_addr #0 {
  %1 = call i32 @kmp(i8* nonnull inttoptr (i32 789577728 to i8*), i8* nonnull inttoptr (i32 789577984 to i8*), i32* nonnull inttoptr (i32 789577744 to i32*), i32* nonnull inttoptr (i32 789577760 to i32*)) #1
  ret void
}

attributes #0 = { nofree noinline norecurse nounwind "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "min-legal-vector-width"="0" "no-builtins" "no-infs-fp-math"="false" "no-jump-tables"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="i686" "target-features"="+cx8,+x87" "tune-cpu"="generic" "unsafe-fp-math"="false" "use-soft-float"="false" }
attributes #1 = { nobuiltin "no-builtins" }

!llvm.module.flags = !{!0, !1}
!llvm.ident = !{!2}

!0 = !{i32 1, !"NumRegisterParameters", i32 0}
!1 = !{i32 1, !"wchar_size", i32 4}
!2 = !{!"Ubuntu clang version 12.0.0-3ubuntu1~20.04.5"}
!3 = !{!4, !4, i64 0}
!4 = !{!"int", !5, i64 0}
!5 = !{!"omnipotent char", !6, i64 0}
!6 = !{!"Simple C/C++ TBAA"}
!7 = !{!5, !5, i64 0}
!8 = distinct !{!8, !9, !10}
!9 = !{!"llvm.loop.mustprogress"}
!10 = !{!"llvm.loop.unroll.disable"}
!11 = distinct !{!11, !9, !10}
!12 = distinct !{!12, !9, !10}
!13 = distinct !{!13, !9, !10}
