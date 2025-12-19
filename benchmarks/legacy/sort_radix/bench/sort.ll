; ModuleID = 'sort.c'
source_filename = "sort.c"
target datalayout = "e-m:e-p:32:32-p270:32:32-p271:32:32-p272:64:64-f64:32:64-f80:32-n8:16:32-S128"
target triple = "i386-pc-linux-gnu"

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @local_scan(i32* nocapture %0) local_unnamed_addr #0 {
  br label %2

2:                                                ; preds = %1, %17
  %3 = phi i32 [ 0, %1 ], [ %18, %17 ]
  %4 = shl nuw nsw i32 %3, 4
  %5 = getelementptr i32, i32* %0, i32 %4
  %6 = shl nsw i32 %3, 4
  %7 = load i32, i32* %5, align 4
  br label %8

8:                                                ; preds = %2, %8
  %9 = phi i32 [ %7, %2 ], [ %14, %8 ]
  %10 = phi i32 [ 1, %2 ], [ %15, %8 ]
  %11 = add nuw nsw i32 %10, %6
  %12 = getelementptr inbounds i32, i32* %0, i32 %11
  %13 = load i32, i32* %12, align 4, !tbaa !3
  %14 = add nsw i32 %13, %9
  store i32 %14, i32* %12, align 4, !tbaa !3
  %15 = add nuw nsw i32 %10, 1
  %16 = icmp eq i32 %15, 16
  br i1 %16, label %17, label %8, !llvm.loop !7

17:                                               ; preds = %8
  %18 = add nuw nsw i32 %3, 1
  %19 = icmp eq i32 %18, 128
  br i1 %19, label %20, label %2, !llvm.loop !10

20:                                               ; preds = %17
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @sum_scan(i32* nocapture %0, i32* nocapture readonly %1) local_unnamed_addr #0 {
  store i32 0, i32* %0, align 4, !tbaa !3
  br label %3

3:                                                ; preds = %2, %3
  %4 = phi i32 [ 0, %2 ], [ %10, %3 ]
  %5 = phi i32 [ 1, %2 ], [ %12, %3 ]
  %6 = shl nsw i32 %5, 4
  %7 = add nsw i32 %6, -1
  %8 = getelementptr inbounds i32, i32* %1, i32 %7
  %9 = load i32, i32* %8, align 4, !tbaa !3
  %10 = add nsw i32 %9, %4
  %11 = getelementptr inbounds i32, i32* %0, i32 %5
  store i32 %10, i32* %11, align 4, !tbaa !3
  %12 = add nuw nsw i32 %5, 1
  %13 = icmp eq i32 %12, 128
  br i1 %13, label %14, label %3, !llvm.loop !11

14:                                               ; preds = %3
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @last_step_scan(i32* nocapture %0, i32* nocapture readonly %1) local_unnamed_addr #0 {
  br label %3

3:                                                ; preds = %2, %16
  %4 = phi i32 [ 0, %2 ], [ %17, %16 ]
  %5 = shl nsw i32 %4, 4
  %6 = getelementptr inbounds i32, i32* %1, i32 %4
  br label %7

7:                                                ; preds = %3, %7
  %8 = phi i32 [ 0, %3 ], [ %14, %7 ]
  %9 = add nuw nsw i32 %8, %5
  %10 = getelementptr inbounds i32, i32* %0, i32 %9
  %11 = load i32, i32* %10, align 4, !tbaa !3
  %12 = load i32, i32* %6, align 4, !tbaa !3
  %13 = add nsw i32 %12, %11
  store i32 %13, i32* %10, align 4, !tbaa !3
  %14 = add nuw nsw i32 %8, 1
  %15 = icmp eq i32 %14, 16
  br i1 %15, label %16, label %7, !llvm.loop !12

16:                                               ; preds = %7
  %17 = add nuw nsw i32 %4, 1
  %18 = icmp eq i32 %17, 128
  br i1 %18, label %19, label %3, !llvm.loop !13

19:                                               ; preds = %16
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind writeonly
define dso_local void @init(i32* nocapture %0) local_unnamed_addr #1 {
  br label %2

2:                                                ; preds = %1, %2
  %3 = phi i32 [ 0, %1 ], [ %5, %2 ]
  %4 = getelementptr inbounds i32, i32* %0, i32 %3
  store i32 0, i32* %4, align 4, !tbaa !3
  %5 = add nuw nsw i32 %3, 1
  %6 = icmp eq i32 %5, 2048
  br i1 %6, label %7, label %2, !llvm.loop !14

7:                                                ; preds = %2
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @hist(i32* nocapture %0, i32* nocapture readonly %1, i32 %2) local_unnamed_addr #0 {
  br label %4

4:                                                ; preds = %3, %22
  %5 = phi i32 [ 0, %3 ], [ %23, %22 ]
  %6 = shl nsw i32 %5, 2
  %7 = add nuw nsw i32 %5, 1
  br label %8

8:                                                ; preds = %4, %8
  %9 = phi i32 [ 0, %4 ], [ %20, %8 ]
  %10 = add nuw nsw i32 %9, %6
  %11 = getelementptr inbounds i32, i32* %1, i32 %10
  %12 = load i32, i32* %11, align 4, !tbaa !3
  %13 = ashr i32 %12, %2
  %14 = shl i32 %13, 9
  %15 = and i32 %14, 1536
  %16 = add nuw i32 %7, %15
  %17 = getelementptr inbounds i32, i32* %0, i32 %16
  %18 = load i32, i32* %17, align 4, !tbaa !3
  %19 = add nsw i32 %18, 1
  store i32 %19, i32* %17, align 4, !tbaa !3
  %20 = add nuw nsw i32 %9, 1
  %21 = icmp eq i32 %20, 4
  br i1 %21, label %22, label %8, !llvm.loop !15

22:                                               ; preds = %8
  %23 = add nuw nsw i32 %5, 1
  %24 = icmp eq i32 %23, 512
  br i1 %24, label %25, label %4, !llvm.loop !16

25:                                               ; preds = %22
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @update(i32* nocapture %0, i32* nocapture %1, i32* nocapture readonly %2, i32 %3) local_unnamed_addr #0 {
  br label %5

5:                                                ; preds = %4, %24
  %6 = phi i32 [ 0, %4 ], [ %25, %24 ]
  %7 = shl nsw i32 %6, 2
  br label %8

8:                                                ; preds = %5, %8
  %9 = phi i32 [ 0, %5 ], [ %22, %8 ]
  %10 = add nuw nsw i32 %9, %7
  %11 = getelementptr inbounds i32, i32* %2, i32 %10
  %12 = load i32, i32* %11, align 4, !tbaa !3
  %13 = ashr i32 %12, %3
  %14 = shl i32 %13, 9
  %15 = and i32 %14, 1536
  %16 = add nuw nsw i32 %15, %6
  %17 = getelementptr inbounds i32, i32* %1, i32 %16
  %18 = load i32, i32* %17, align 4, !tbaa !3
  %19 = getelementptr inbounds i32, i32* %0, i32 %18
  store i32 %12, i32* %19, align 4, !tbaa !3
  %20 = load i32, i32* %17, align 4, !tbaa !3
  %21 = add nsw i32 %20, 1
  store i32 %21, i32* %17, align 4, !tbaa !3
  %22 = add nuw nsw i32 %9, 1
  %23 = icmp eq i32 %22, 4
  br i1 %23, label %24, label %8, !llvm.loop !17

24:                                               ; preds = %8
  %25 = add nuw nsw i32 %6, 1
  %26 = icmp eq i32 %25, 512
  br i1 %26, label %27, label %5, !llvm.loop !18

27:                                               ; preds = %24
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @ss_sort(i32* nocapture %0, i32* nocapture %1, i32* nocapture %2, i32* nocapture %3) local_unnamed_addr #0 {
  br label %5

5:                                                ; preds = %4, %12
  %6 = phi i32 [ 0, %4 ], [ %13, %12 ]
  %7 = phi i32 [ 0, %4 ], [ %14, %12 ]
  call void @init(i32* %2) #2
  %8 = icmp eq i32 %6, 0
  %9 = select i1 %8, i32* %0, i32* %1
  call void @hist(i32* %2, i32* %9, i32 %7) #2
  call void @local_scan(i32* %2) #2
  call void @sum_scan(i32* %3, i32* %2) #2
  call void @last_step_scan(i32* %2, i32* %3) #2
  br i1 %8, label %10, label %11

10:                                               ; preds = %5
  call void @update(i32* %1, i32* %2, i32* %0, i32 %7) #2
  br label %12

11:                                               ; preds = %5
  call void @update(i32* %0, i32* %2, i32* %1, i32 %7) #2
  br label %12

12:                                               ; preds = %10, %11
  %13 = phi i32 [ 1, %10 ], [ 0, %11 ]
  %14 = add nuw nsw i32 %7, 2
  %15 = icmp ult i32 %7, 30
  br i1 %15, label %5, label %16, !llvm.loop !19

16:                                               ; preds = %12
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @top() local_unnamed_addr #0 {
  call void @ss_sort(i32* nonnull inttoptr (i32 789577728 to i32*), i32* nonnull inttoptr (i32 789585920 to i32*), i32* nonnull inttoptr (i32 789594112 to i32*), i32* nonnull inttoptr (i32 789602304 to i32*)) #2
  ret void
}

attributes #0 = { nofree noinline norecurse nounwind "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "min-legal-vector-width"="0" "no-builtins" "no-infs-fp-math"="false" "no-jump-tables"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="i686" "target-features"="+cx8,+x87" "tune-cpu"="generic" "unsafe-fp-math"="false" "use-soft-float"="false" }
attributes #1 = { nofree noinline norecurse nounwind writeonly "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "min-legal-vector-width"="0" "no-builtins" "no-infs-fp-math"="false" "no-jump-tables"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="i686" "target-features"="+cx8,+x87" "tune-cpu"="generic" "unsafe-fp-math"="false" "use-soft-float"="false" }
attributes #2 = { nobuiltin "no-builtins" }

!llvm.module.flags = !{!0, !1}
!llvm.ident = !{!2}

!0 = !{i32 1, !"NumRegisterParameters", i32 0}
!1 = !{i32 1, !"wchar_size", i32 4}
!2 = !{!"Ubuntu clang version 12.0.0-3ubuntu1~20.04.5"}
!3 = !{!4, !4, i64 0}
!4 = !{!"int", !5, i64 0}
!5 = !{!"omnipotent char", !6, i64 0}
!6 = !{!"Simple C/C++ TBAA"}
!7 = distinct !{!7, !8, !9}
!8 = !{!"llvm.loop.mustprogress"}
!9 = !{!"llvm.loop.unroll.disable"}
!10 = distinct !{!10, !8, !9}
!11 = distinct !{!11, !8, !9}
!12 = distinct !{!12, !8, !9}
!13 = distinct !{!13, !8, !9}
!14 = distinct !{!14, !8, !9}
!15 = distinct !{!15, !8, !9}
!16 = distinct !{!16, !8, !9}
!17 = distinct !{!17, !8, !9}
!18 = distinct !{!18, !8, !9}
!19 = distinct !{!19, !8, !9}
