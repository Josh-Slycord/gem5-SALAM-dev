; ModuleID = 'sort.c'
source_filename = "sort.c"
target datalayout = "e-m:e-p:32:32-p270:32:32-p271:32:32-p272:64:64-f64:32:64-f80:32-n8:16:32-S128"
target triple = "i386-pc-linux-gnu"

; Function Attrs: nofree noinline nounwind
define dso_local void @merge(i32* nocapture %0, i32 %1, i32 %2, i32 %3) local_unnamed_addr #0 {
  %5 = alloca [2048 x i32], align 4
  %6 = bitcast [2048 x i32]* %5 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8192, i8* nonnull %6) #2
  %7 = icmp sgt i32 %1, %2
  br i1 %7, label %15, label %8

8:                                                ; preds = %4, %8
  %9 = phi i32 [ %13, %8 ], [ %1, %4 ]
  %10 = getelementptr inbounds i32, i32* %0, i32 %9
  %11 = load i32, i32* %10, align 4, !tbaa !3
  %12 = getelementptr inbounds [2048 x i32], [2048 x i32]* %5, i32 0, i32 %9
  store i32 %11, i32* %12, align 4, !tbaa !3
  %13 = add i32 %9, 1
  %14 = icmp eq i32 %9, %2
  br i1 %14, label %15, label %8, !llvm.loop !7

15:                                               ; preds = %8, %4
  %16 = add nsw i32 %2, 1
  %17 = icmp slt i32 %2, %3
  br i1 %17, label %18, label %20

18:                                               ; preds = %15
  %19 = add nsw i32 %16, %3
  br label %22

20:                                               ; preds = %22, %15
  %21 = icmp sgt i32 %1, %3
  br i1 %21, label %49, label %30

22:                                               ; preds = %18, %22
  %23 = phi i32 [ %16, %18 ], [ %28, %22 ]
  %24 = getelementptr inbounds i32, i32* %0, i32 %23
  %25 = load i32, i32* %24, align 4, !tbaa !3
  %26 = sub i32 %19, %23
  %27 = getelementptr inbounds [2048 x i32], [2048 x i32]* %5, i32 0, i32 %26
  store i32 %25, i32* %27, align 4, !tbaa !3
  %28 = add i32 %23, 1
  %29 = icmp eq i32 %23, %3
  br i1 %29, label %20, label %22, !llvm.loop !10

30:                                               ; preds = %20, %44
  %31 = phi i32 [ %46, %44 ], [ %1, %20 ]
  %32 = phi i32 [ %45, %44 ], [ %3, %20 ]
  %33 = phi i32 [ %47, %44 ], [ %1, %20 ]
  %34 = getelementptr inbounds [2048 x i32], [2048 x i32]* %5, i32 0, i32 %32
  %35 = load i32, i32* %34, align 4, !tbaa !3
  %36 = getelementptr inbounds [2048 x i32], [2048 x i32]* %5, i32 0, i32 %31
  %37 = load i32, i32* %36, align 4, !tbaa !3
  %38 = icmp slt i32 %35, %37
  %39 = getelementptr inbounds i32, i32* %0, i32 %33
  br i1 %38, label %40, label %42

40:                                               ; preds = %30
  store i32 %35, i32* %39, align 4, !tbaa !3
  %41 = add nsw i32 %32, -1
  br label %44

42:                                               ; preds = %30
  store i32 %37, i32* %39, align 4, !tbaa !3
  %43 = add nsw i32 %31, 1
  br label %44

44:                                               ; preds = %42, %40
  %45 = phi i32 [ %41, %40 ], [ %32, %42 ]
  %46 = phi i32 [ %31, %40 ], [ %43, %42 ]
  %47 = add i32 %33, 1
  %48 = icmp eq i32 %33, %3
  br i1 %48, label %49, label %30, !llvm.loop !11

49:                                               ; preds = %44, %20
  call void @llvm.lifetime.end.p0i8(i64 8192, i8* nonnull %6) #2
  ret void
}

; Function Attrs: argmemonly nofree nosync nounwind willreturn
declare void @llvm.lifetime.start.p0i8(i64 immarg, i8* nocapture) #1

; Function Attrs: argmemonly nofree nosync nounwind willreturn
declare void @llvm.lifetime.end.p0i8(i64 immarg, i8* nocapture) #1

; Function Attrs: nofree noinline nounwind
define dso_local void @ms_mergesort(i32* nocapture %0) local_unnamed_addr #0 {
  br label %2

2:                                                ; preds = %1, %15
  %3 = phi i32 [ 1, %1 ], [ %16, %15 ]
  %4 = shl nsw i32 %3, 1
  br label %5

5:                                                ; preds = %2, %5
  %6 = phi i32 [ 0, %2 ], [ %13, %5 ]
  %7 = add nsw i32 %6, %3
  %8 = add nsw i32 %7, -1
  %9 = add nsw i32 %7, %3
  %10 = add nsw i32 %9, -1
  %11 = icmp sgt i32 %9, 2048
  %12 = select i1 %11, i32 2048, i32 %10
  call void @merge(i32* %0, i32 %6, i32 %8, i32 %12) #3
  %13 = add nsw i32 %6, %4
  %14 = icmp slt i32 %13, 2048
  br i1 %14, label %5, label %15, !llvm.loop !12

15:                                               ; preds = %5
  %16 = shl nsw i32 %3, 1
  %17 = icmp slt i32 %3, 1024
  br i1 %17, label %2, label %18, !llvm.loop !13

18:                                               ; preds = %15
  ret void
}

; Function Attrs: nofree noinline nounwind
define dso_local void @top() local_unnamed_addr #0 {
  call void @ms_mergesort(i32* nonnull inttoptr (i32 789577728 to i32*)) #3
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
