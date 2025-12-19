; ModuleID = 'backprop.c'
source_filename = "backprop.c"
target datalayout = "e-m:e-p:32:32-p270:32:32-p271:32:32-p272:64:64-f64:32:64-f80:32-n8:16:32-S128"
target triple = "i386-pc-linux-gnu"

; Function Attrs: noinline nounwind
define dso_local void @sigmoid(double* nocapture %0, double* nocapture %1, i32 %2) local_unnamed_addr #0 {
  %4 = icmp sgt i32 %2, 0
  br i1 %4, label %5, label %19

5:                                                ; preds = %3, %5
  %6 = phi i32 [ %17, %5 ], [ 0, %3 ]
  %7 = getelementptr inbounds double, double* %0, i32 %6
  %8 = load double, double* %7, align 4, !tbaa !3
  %9 = fsub double 1.000000e+00, %8
  %10 = fmul double %8, %9
  %11 = getelementptr inbounds double, double* %1, i32 %6
  store double %10, double* %11, align 4, !tbaa !3
  %12 = load double, double* %7, align 4, !tbaa !3
  %13 = fneg double %12
  %14 = call double @exp(double %13) #4
  %15 = fadd double %14, 1.000000e+00
  %16 = fdiv double 1.000000e+00, %15
  store double %16, double* %7, align 4, !tbaa !3
  %17 = add nuw nsw i32 %6, 1
  %18 = icmp eq i32 %17, %2
  br i1 %18, label %19, label %5, !llvm.loop !7

19:                                               ; preds = %5, %3
  ret void
}

; Function Attrs: argmemonly nofree nosync nounwind willreturn
declare void @llvm.lifetime.start.p0i8(i64 immarg, i8* nocapture) #1

; Function Attrs: nounwind
declare dso_local double @exp(double) local_unnamed_addr #2

; Function Attrs: argmemonly nofree nosync nounwind willreturn
declare void @llvm.lifetime.end.p0i8(i64 immarg, i8* nocapture) #1

; Function Attrs: noinline nounwind
define dso_local void @soft_max(double* nocapture %0, double* nocapture readonly %1) local_unnamed_addr #0 {
  br label %3

3:                                                ; preds = %2, %3
  %4 = phi double [ 0.000000e+00, %2 ], [ %10, %3 ]
  %5 = phi i32 [ 0, %2 ], [ %11, %3 ]
  %6 = getelementptr inbounds double, double* %1, i32 %5
  %7 = load double, double* %6, align 4, !tbaa !3
  %8 = fneg double %7
  %9 = call double @exp(double %8) #4
  %10 = fadd double %4, %9
  %11 = add nuw nsw i32 %5, 1
  %12 = icmp eq i32 %11, 3
  br i1 %12, label %13, label %3, !llvm.loop !10

13:                                               ; preds = %3, %13
  %14 = phi i32 [ %21, %13 ], [ 0, %3 ]
  %15 = getelementptr inbounds double, double* %1, i32 %14
  %16 = load double, double* %15, align 4, !tbaa !3
  %17 = fneg double %16
  %18 = call double @exp(double %17) #4
  %19 = fdiv double %18, %10
  %20 = getelementptr inbounds double, double* %0, i32 %14
  store double %19, double* %20, align 4, !tbaa !3
  %21 = add nuw nsw i32 %14, 1
  %22 = icmp eq i32 %21, 3
  br i1 %22, label %23, label %13, !llvm.loop !11

23:                                               ; preds = %13
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @add_bias(double* nocapture readonly %0, double* nocapture %1, i32 %2) local_unnamed_addr #3 {
  %4 = icmp sgt i32 %2, 0
  br i1 %4, label %5, label %14

5:                                                ; preds = %3, %5
  %6 = phi i32 [ %12, %5 ], [ 0, %3 ]
  %7 = getelementptr inbounds double, double* %0, i32 %6
  %8 = load double, double* %7, align 4, !tbaa !3
  %9 = getelementptr inbounds double, double* %1, i32 %6
  %10 = load double, double* %9, align 4, !tbaa !3
  %11 = fadd double %8, %10
  store double %11, double* %9, align 4, !tbaa !3
  %12 = add nuw nsw i32 %6, 1
  %13 = icmp eq i32 %12, %2
  br i1 %13, label %14, label %5, !llvm.loop !12

14:                                               ; preds = %5, %3
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @mvp_input_layer(double* nocapture readonly %0, double* nocapture readonly %1, double* nocapture %2, double* nocapture readonly %3) local_unnamed_addr #3 {
  br label %5

5:                                                ; preds = %4, %21
  %6 = phi i32 [ 0, %4 ], [ %22, %21 ]
  %7 = getelementptr inbounds double, double* %2, i32 %6
  store double 0.000000e+00, double* %7, align 4, !tbaa !3
  %8 = mul nuw nsw i32 %6, 13
  br label %9

9:                                                ; preds = %5, %9
  %10 = phi i32 [ 0, %5 ], [ %19, %9 ]
  %11 = add nuw nsw i32 %10, %8
  %12 = getelementptr inbounds double, double* %1, i32 %11
  %13 = load double, double* %12, align 4, !tbaa !3
  %14 = getelementptr inbounds double, double* %3, i32 %10
  %15 = load double, double* %14, align 4, !tbaa !3
  %16 = fmul double %13, %15
  %17 = load double, double* %7, align 4, !tbaa !3
  %18 = fadd double %17, %16
  store double %18, double* %7, align 4, !tbaa !3
  %19 = add nuw nsw i32 %10, 1
  %20 = icmp eq i32 %19, 13
  br i1 %20, label %21, label %9, !llvm.loop !13

21:                                               ; preds = %9
  %22 = add nuw nsw i32 %6, 1
  %23 = icmp eq i32 %22, 64
  br i1 %23, label %24, label %5, !llvm.loop !14

24:                                               ; preds = %21
  call void @add_bias(double* %0, double* %2, i32 64) #5
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @mvp_hidden_layer(double* nocapture readonly %0, double* nocapture readonly %1, double* nocapture %2, double* nocapture readonly %3) local_unnamed_addr #3 {
  br label %5

5:                                                ; preds = %4, %21
  %6 = phi i32 [ 0, %4 ], [ %22, %21 ]
  %7 = getelementptr inbounds double, double* %2, i32 %6
  store double 0.000000e+00, double* %7, align 4, !tbaa !3
  %8 = shl nsw i32 %6, 6
  br label %9

9:                                                ; preds = %5, %9
  %10 = phi i32 [ 0, %5 ], [ %19, %9 ]
  %11 = add nuw nsw i32 %10, %8
  %12 = getelementptr inbounds double, double* %1, i32 %11
  %13 = load double, double* %12, align 4, !tbaa !3
  %14 = getelementptr inbounds double, double* %3, i32 %10
  %15 = load double, double* %14, align 4, !tbaa !3
  %16 = fmul double %13, %15
  %17 = load double, double* %7, align 4, !tbaa !3
  %18 = fadd double %17, %16
  store double %18, double* %7, align 4, !tbaa !3
  %19 = add nuw nsw i32 %10, 1
  %20 = icmp eq i32 %19, 64
  br i1 %20, label %21, label %9, !llvm.loop !15

21:                                               ; preds = %9
  %22 = add nuw nsw i32 %6, 1
  %23 = icmp eq i32 %22, 64
  br i1 %23, label %24, label %5, !llvm.loop !16

24:                                               ; preds = %21
  call void @add_bias(double* %0, double* %2, i32 64) #5
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @mvp_output_layer(double* nocapture readonly %0, double* nocapture readonly %1, double* nocapture %2, double* nocapture readonly %3) local_unnamed_addr #3 {
  br label %5

5:                                                ; preds = %4, %21
  %6 = phi i32 [ 0, %4 ], [ %22, %21 ]
  %7 = getelementptr inbounds double, double* %2, i32 %6
  store double 0.000000e+00, double* %7, align 4, !tbaa !3
  %8 = shl nsw i32 %6, 6
  br label %9

9:                                                ; preds = %5, %9
  %10 = phi i32 [ 0, %5 ], [ %19, %9 ]
  %11 = add nuw nsw i32 %10, %8
  %12 = getelementptr inbounds double, double* %1, i32 %11
  %13 = load double, double* %12, align 4, !tbaa !3
  %14 = getelementptr inbounds double, double* %3, i32 %10
  %15 = load double, double* %14, align 4, !tbaa !3
  %16 = fmul double %13, %15
  %17 = load double, double* %7, align 4, !tbaa !3
  %18 = fadd double %17, %16
  store double %18, double* %7, align 4, !tbaa !3
  %19 = add nuw nsw i32 %10, 1
  %20 = icmp eq i32 %19, 64
  br i1 %20, label %21, label %9, !llvm.loop !17

21:                                               ; preds = %9
  %22 = add nuw nsw i32 %6, 1
  %23 = icmp eq i32 %22, 3
  br i1 %23, label %24, label %5, !llvm.loop !18

24:                                               ; preds = %21
  call void @add_bias(double* %0, double* %2, i32 3) #5
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @take_difference(double* nocapture readonly %0, double* nocapture readonly %1, double* nocapture %2, double* nocapture readonly %3) local_unnamed_addr #3 {
  br label %5

5:                                                ; preds = %4, %5
  %6 = phi i32 [ 0, %4 ], [ %17, %5 ]
  %7 = getelementptr inbounds double, double* %0, i32 %6
  %8 = load double, double* %7, align 4, !tbaa !3
  %9 = getelementptr inbounds double, double* %1, i32 %6
  %10 = load double, double* %9, align 4, !tbaa !3
  %11 = fsub double %8, %10
  %12 = fneg double %11
  %13 = getelementptr inbounds double, double* %3, i32 %6
  %14 = load double, double* %13, align 4, !tbaa !3
  %15 = fmul double %14, %12
  %16 = getelementptr inbounds double, double* %2, i32 %6
  store double %15, double* %16, align 4, !tbaa !3
  %17 = add nuw nsw i32 %6, 1
  %18 = icmp eq i32 %17, 3
  br i1 %18, label %19, label %5, !llvm.loop !19

19:                                               ; preds = %5
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @delta_weights3(double* nocapture %0, double* nocapture readonly %1, double* nocapture readonly %2) local_unnamed_addr #3 {
  br label %4

4:                                                ; preds = %3, %18
  %5 = phi i32 [ 0, %3 ], [ %19, %18 ]
  %6 = getelementptr inbounds double, double* %2, i32 %5
  %7 = mul nuw nsw i32 %5, 3
  br label %8

8:                                                ; preds = %4, %8
  %9 = phi i32 [ 0, %4 ], [ %16, %8 ]
  %10 = load double, double* %6, align 4, !tbaa !3
  %11 = getelementptr inbounds double, double* %1, i32 %9
  %12 = load double, double* %11, align 4, !tbaa !3
  %13 = fmul double %10, %12
  %14 = add nuw nsw i32 %9, %7
  %15 = getelementptr inbounds double, double* %0, i32 %14
  store double %13, double* %15, align 4, !tbaa !3
  %16 = add nuw nsw i32 %9, 1
  %17 = icmp eq i32 %16, 3
  br i1 %17, label %18, label %8, !llvm.loop !20

18:                                               ; preds = %8
  %19 = add nuw nsw i32 %5, 1
  %20 = icmp eq i32 %19, 64
  br i1 %20, label %21, label %4, !llvm.loop !21

21:                                               ; preds = %18
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @oracle_act2(double* nocapture readonly %0, double* nocapture readonly %1, double* nocapture %2, double* nocapture readonly %3) local_unnamed_addr #3 {
  br label %5

5:                                                ; preds = %4, %21
  %6 = phi i32 [ 0, %4 ], [ %26, %21 ]
  %7 = getelementptr inbounds double, double* %2, i32 %6
  store double 0.000000e+00, double* %7, align 4, !tbaa !3
  %8 = mul nuw nsw i32 %6, 3
  br label %9

9:                                                ; preds = %5, %9
  %10 = phi i32 [ 0, %5 ], [ %19, %9 ]
  %11 = getelementptr inbounds double, double* %1, i32 %10
  %12 = load double, double* %11, align 4, !tbaa !3
  %13 = add nuw nsw i32 %10, %8
  %14 = getelementptr inbounds double, double* %0, i32 %13
  %15 = load double, double* %14, align 4, !tbaa !3
  %16 = fmul double %12, %15
  %17 = load double, double* %7, align 4, !tbaa !3
  %18 = fadd double %17, %16
  store double %18, double* %7, align 4, !tbaa !3
  %19 = add nuw nsw i32 %10, 1
  %20 = icmp eq i32 %19, 3
  br i1 %20, label %21, label %9, !llvm.loop !22

21:                                               ; preds = %9
  %22 = getelementptr inbounds double, double* %3, i32 %6
  %23 = load double, double* %22, align 4, !tbaa !3
  %24 = load double, double* %7, align 4, !tbaa !3
  %25 = fmul double %23, %24
  store double %25, double* %7, align 4, !tbaa !3
  %26 = add nuw nsw i32 %6, 1
  %27 = icmp eq i32 %26, 64
  br i1 %27, label %28, label %5, !llvm.loop !23

28:                                               ; preds = %21
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @delta_weights2(double* nocapture %0, double* nocapture readonly %1, double* nocapture readonly %2) local_unnamed_addr #3 {
  br label %4

4:                                                ; preds = %3, %18
  %5 = phi i32 [ 0, %3 ], [ %19, %18 ]
  %6 = getelementptr inbounds double, double* %2, i32 %5
  %7 = shl nsw i32 %5, 6
  br label %8

8:                                                ; preds = %4, %8
  %9 = phi i32 [ 0, %4 ], [ %16, %8 ]
  %10 = load double, double* %6, align 4, !tbaa !3
  %11 = getelementptr inbounds double, double* %1, i32 %9
  %12 = load double, double* %11, align 4, !tbaa !3
  %13 = fmul double %10, %12
  %14 = add nuw nsw i32 %9, %7
  %15 = getelementptr inbounds double, double* %0, i32 %14
  store double %13, double* %15, align 4, !tbaa !3
  %16 = add nuw nsw i32 %9, 1
  %17 = icmp eq i32 %16, 64
  br i1 %17, label %18, label %8, !llvm.loop !24

18:                                               ; preds = %8
  %19 = add nuw nsw i32 %5, 1
  %20 = icmp eq i32 %19, 64
  br i1 %20, label %21, label %4, !llvm.loop !25

21:                                               ; preds = %18
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @oracle_act1(double* nocapture readonly %0, double* nocapture readonly %1, double* nocapture %2, double* nocapture readonly %3) local_unnamed_addr #3 {
  br label %5

5:                                                ; preds = %4, %21
  %6 = phi i32 [ 0, %4 ], [ %26, %21 ]
  %7 = getelementptr inbounds double, double* %2, i32 %6
  store double 0.000000e+00, double* %7, align 4, !tbaa !3
  %8 = shl nsw i32 %6, 6
  br label %9

9:                                                ; preds = %5, %9
  %10 = phi i32 [ 0, %5 ], [ %19, %9 ]
  %11 = getelementptr inbounds double, double* %1, i32 %10
  %12 = load double, double* %11, align 4, !tbaa !3
  %13 = add nuw nsw i32 %10, %8
  %14 = getelementptr inbounds double, double* %0, i32 %13
  %15 = load double, double* %14, align 4, !tbaa !3
  %16 = fmul double %12, %15
  %17 = load double, double* %7, align 4, !tbaa !3
  %18 = fadd double %17, %16
  store double %18, double* %7, align 4, !tbaa !3
  %19 = add nuw nsw i32 %10, 1
  %20 = icmp eq i32 %19, 64
  br i1 %20, label %21, label %9, !llvm.loop !26

21:                                               ; preds = %9
  %22 = getelementptr inbounds double, double* %3, i32 %6
  %23 = load double, double* %22, align 4, !tbaa !3
  %24 = load double, double* %7, align 4, !tbaa !3
  %25 = fmul double %23, %24
  store double %25, double* %7, align 4, !tbaa !3
  %26 = add nuw nsw i32 %6, 1
  %27 = icmp eq i32 %26, 64
  br i1 %27, label %28, label %5, !llvm.loop !27

28:                                               ; preds = %21
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define dso_local void @delta_weights1(double* nocapture %0, double* nocapture readonly %1, double* nocapture readonly %2) local_unnamed_addr #3 {
  br label %4

4:                                                ; preds = %3, %18
  %5 = phi i32 [ 0, %3 ], [ %19, %18 ]
  %6 = getelementptr inbounds double, double* %2, i32 %5
  %7 = shl nsw i32 %5, 6
  br label %8

8:                                                ; preds = %4, %8
  %9 = phi i32 [ 0, %4 ], [ %16, %8 ]
  %10 = load double, double* %6, align 4, !tbaa !3
  %11 = getelementptr inbounds double, double* %1, i32 %9
  %12 = load double, double* %11, align 4, !tbaa !3
  %13 = fmul double %10, %12
  %14 = add nuw nsw i32 %9, %7
  %15 = getelementptr inbounds double, double* %0, i32 %14
  store double %13, double* %15, align 4, !tbaa !3
  %16 = add nuw nsw i32 %9, 1
  %17 = icmp eq i32 %16, 64
  br i1 %17, label %18, label %8, !llvm.loop !28

18:                                               ; preds = %8
  %19 = add nuw nsw i32 %5, 1
  %20 = icmp eq i32 %19, 13
  br i1 %20, label %21, label %4, !llvm.loop !29

21:                                               ; preds = %18
  ret void
}

; Function Attrs: noinline nounwind
define dso_local void @update_weights(double* nocapture %0, double* nocapture %1, double* nocapture %2, double* nocapture readonly %3, double* nocapture readonly %4, double* nocapture readonly %5, double* nocapture %6, double* nocapture %7, double* nocapture %8, double* nocapture readonly %9, double* nocapture readonly %10, double* nocapture readonly %11) local_unnamed_addr #0 {
  br label %13

13:                                               ; preds = %12, %31
  %14 = phi double [ 0.000000e+00, %12 ], [ %28, %31 ]
  %15 = phi i32 [ 0, %12 ], [ %32, %31 ]
  %16 = shl nsw i32 %15, 6
  br label %17

17:                                               ; preds = %13, %17
  %18 = phi double [ %14, %13 ], [ %28, %17 ]
  %19 = phi i32 [ 0, %13 ], [ %29, %17 ]
  %20 = add nuw nsw i32 %19, %16
  %21 = getelementptr inbounds double, double* %3, i32 %20
  %22 = load double, double* %21, align 4, !tbaa !3
  %23 = fmul double %22, 1.000000e-02
  %24 = getelementptr inbounds double, double* %0, i32 %20
  %25 = load double, double* %24, align 4, !tbaa !3
  %26 = fsub double %25, %23
  store double %26, double* %24, align 4, !tbaa !3
  %27 = fmul double %26, %26
  %28 = fadd double %18, %27
  %29 = add nuw nsw i32 %19, 1
  %30 = icmp eq i32 %29, 64
  br i1 %30, label %31, label %17, !llvm.loop !30

31:                                               ; preds = %17
  %32 = add nuw nsw i32 %15, 1
  %33 = icmp eq i32 %32, 13
  br i1 %33, label %34, label %13, !llvm.loop !31

34:                                               ; preds = %31, %34
  %35 = phi double [ %44, %34 ], [ 0.000000e+00, %31 ]
  %36 = phi i32 [ %45, %34 ], [ 0, %31 ]
  %37 = getelementptr inbounds double, double* %9, i32 %36
  %38 = load double, double* %37, align 4, !tbaa !3
  %39 = fmul double %38, 1.000000e-02
  %40 = getelementptr inbounds double, double* %6, i32 %36
  %41 = load double, double* %40, align 4, !tbaa !3
  %42 = fsub double %41, %39
  store double %42, double* %40, align 4, !tbaa !3
  %43 = fmul double %42, %42
  %44 = fadd double %35, %43
  %45 = add nuw nsw i32 %36, 1
  %46 = icmp eq i32 %45, 64
  br i1 %46, label %47, label %34, !llvm.loop !32

47:                                               ; preds = %34
  %48 = call double @sqrt(double %28) #4
  %49 = call double @sqrt(double %44) #4
  br label %50

50:                                               ; preds = %47, %61
  %51 = phi i32 [ 0, %47 ], [ %62, %61 ]
  %52 = shl nsw i32 %51, 6
  br label %53

53:                                               ; preds = %50, %53
  %54 = phi i32 [ 0, %50 ], [ %59, %53 ]
  %55 = add nuw nsw i32 %54, %52
  %56 = getelementptr inbounds double, double* %0, i32 %55
  %57 = load double, double* %56, align 4, !tbaa !3
  %58 = fdiv double %57, %48
  store double %58, double* %56, align 4, !tbaa !3
  %59 = add nuw nsw i32 %54, 1
  %60 = icmp eq i32 %59, 64
  br i1 %60, label %61, label %53, !llvm.loop !33

61:                                               ; preds = %53
  %62 = add nuw nsw i32 %51, 1
  %63 = icmp eq i32 %62, 13
  br i1 %63, label %64, label %50, !llvm.loop !34

64:                                               ; preds = %61, %64
  %65 = phi i32 [ %69, %64 ], [ 0, %61 ]
  %66 = getelementptr inbounds double, double* %6, i32 %65
  %67 = load double, double* %66, align 4, !tbaa !3
  %68 = fdiv double %67, %49
  store double %68, double* %66, align 4, !tbaa !3
  %69 = add nuw nsw i32 %65, 1
  %70 = icmp eq i32 %69, 64
  br i1 %70, label %71, label %64, !llvm.loop !35

71:                                               ; preds = %64, %89
  %72 = phi double [ %86, %89 ], [ 0.000000e+00, %64 ]
  %73 = phi i32 [ %90, %89 ], [ 0, %64 ]
  %74 = shl nsw i32 %73, 6
  br label %75

75:                                               ; preds = %71, %75
  %76 = phi double [ %72, %71 ], [ %86, %75 ]
  %77 = phi i32 [ 0, %71 ], [ %87, %75 ]
  %78 = add nuw nsw i32 %77, %74
  %79 = getelementptr inbounds double, double* %4, i32 %78
  %80 = load double, double* %79, align 4, !tbaa !3
  %81 = fmul double %80, 1.000000e-02
  %82 = getelementptr inbounds double, double* %1, i32 %78
  %83 = load double, double* %82, align 4, !tbaa !3
  %84 = fsub double %83, %81
  store double %84, double* %82, align 4, !tbaa !3
  %85 = fmul double %84, %84
  %86 = fadd double %76, %85
  %87 = add nuw nsw i32 %77, 1
  %88 = icmp eq i32 %87, 64
  br i1 %88, label %89, label %75, !llvm.loop !36

89:                                               ; preds = %75
  %90 = add nuw nsw i32 %73, 1
  %91 = icmp eq i32 %90, 64
  br i1 %91, label %92, label %71, !llvm.loop !37

92:                                               ; preds = %89, %92
  %93 = phi double [ %102, %92 ], [ 0.000000e+00, %89 ]
  %94 = phi i32 [ %103, %92 ], [ 0, %89 ]
  %95 = getelementptr inbounds double, double* %10, i32 %94
  %96 = load double, double* %95, align 4, !tbaa !3
  %97 = fmul double %96, 1.000000e-02
  %98 = getelementptr inbounds double, double* %7, i32 %94
  %99 = load double, double* %98, align 4, !tbaa !3
  %100 = fsub double %99, %97
  store double %100, double* %98, align 4, !tbaa !3
  %101 = fmul double %100, %100
  %102 = fadd double %93, %101
  %103 = add nuw nsw i32 %94, 1
  %104 = icmp eq i32 %103, 64
  br i1 %104, label %105, label %92, !llvm.loop !38

105:                                              ; preds = %92
  %106 = call double @sqrt(double %86) #4
  %107 = call double @sqrt(double %102) #4
  br label %108

108:                                              ; preds = %105, %119
  %109 = phi i32 [ 0, %105 ], [ %120, %119 ]
  %110 = shl nsw i32 %109, 6
  br label %111

111:                                              ; preds = %108, %111
  %112 = phi i32 [ 0, %108 ], [ %117, %111 ]
  %113 = add nuw nsw i32 %112, %110
  %114 = getelementptr inbounds double, double* %1, i32 %113
  %115 = load double, double* %114, align 4, !tbaa !3
  %116 = fdiv double %115, %106
  store double %116, double* %114, align 4, !tbaa !3
  %117 = add nuw nsw i32 %112, 1
  %118 = icmp eq i32 %117, 64
  br i1 %118, label %119, label %111, !llvm.loop !39

119:                                              ; preds = %111
  %120 = add nuw nsw i32 %109, 1
  %121 = icmp eq i32 %120, 64
  br i1 %121, label %122, label %108, !llvm.loop !40

122:                                              ; preds = %119, %122
  %123 = phi i32 [ %127, %122 ], [ 0, %119 ]
  %124 = getelementptr inbounds double, double* %7, i32 %123
  %125 = load double, double* %124, align 4, !tbaa !3
  %126 = fdiv double %125, %107
  store double %126, double* %124, align 4, !tbaa !3
  %127 = add nuw nsw i32 %123, 1
  %128 = icmp eq i32 %127, 64
  br i1 %128, label %129, label %122, !llvm.loop !41

129:                                              ; preds = %122, %147
  %130 = phi double [ %144, %147 ], [ 0.000000e+00, %122 ]
  %131 = phi i32 [ %148, %147 ], [ 0, %122 ]
  %132 = mul nuw nsw i32 %131, 3
  br label %133

133:                                              ; preds = %129, %133
  %134 = phi double [ %130, %129 ], [ %144, %133 ]
  %135 = phi i32 [ 0, %129 ], [ %145, %133 ]
  %136 = add nuw nsw i32 %135, %132
  %137 = getelementptr inbounds double, double* %5, i32 %136
  %138 = load double, double* %137, align 4, !tbaa !3
  %139 = fmul double %138, 1.000000e-02
  %140 = getelementptr inbounds double, double* %2, i32 %136
  %141 = load double, double* %140, align 4, !tbaa !3
  %142 = fsub double %141, %139
  store double %142, double* %140, align 4, !tbaa !3
  %143 = fmul double %142, %142
  %144 = fadd double %134, %143
  %145 = add nuw nsw i32 %135, 1
  %146 = icmp eq i32 %145, 3
  br i1 %146, label %147, label %133, !llvm.loop !42

147:                                              ; preds = %133
  %148 = add nuw nsw i32 %131, 1
  %149 = icmp eq i32 %148, 64
  br i1 %149, label %150, label %129, !llvm.loop !43

150:                                              ; preds = %147, %150
  %151 = phi double [ %160, %150 ], [ 0.000000e+00, %147 ]
  %152 = phi i32 [ %161, %150 ], [ 0, %147 ]
  %153 = getelementptr inbounds double, double* %11, i32 %152
  %154 = load double, double* %153, align 4, !tbaa !3
  %155 = fmul double %154, 1.000000e-02
  %156 = getelementptr inbounds double, double* %8, i32 %152
  %157 = load double, double* %156, align 4, !tbaa !3
  %158 = fsub double %157, %155
  store double %158, double* %156, align 4, !tbaa !3
  %159 = fmul double %158, %158
  %160 = fadd double %151, %159
  %161 = add nuw nsw i32 %152, 1
  %162 = icmp eq i32 %161, 3
  br i1 %162, label %163, label %150, !llvm.loop !44

163:                                              ; preds = %150
  %164 = call double @sqrt(double %144) #4
  %165 = call double @sqrt(double %160) #4
  br label %166

166:                                              ; preds = %163, %177
  %167 = phi i32 [ 0, %163 ], [ %178, %177 ]
  %168 = mul nuw nsw i32 %167, 3
  br label %169

169:                                              ; preds = %166, %169
  %170 = phi i32 [ 0, %166 ], [ %175, %169 ]
  %171 = add nuw nsw i32 %170, %168
  %172 = getelementptr inbounds double, double* %2, i32 %171
  %173 = load double, double* %172, align 4, !tbaa !3
  %174 = fdiv double %173, %164
  store double %174, double* %172, align 4, !tbaa !3
  %175 = add nuw nsw i32 %170, 1
  %176 = icmp eq i32 %175, 3
  br i1 %176, label %177, label %169, !llvm.loop !45

177:                                              ; preds = %169
  %178 = add nuw nsw i32 %167, 1
  %179 = icmp eq i32 %178, 64
  br i1 %179, label %180, label %166, !llvm.loop !46

180:                                              ; preds = %177, %180
  %181 = phi i32 [ %185, %180 ], [ 0, %177 ]
  %182 = getelementptr inbounds double, double* %8, i32 %181
  %183 = load double, double* %182, align 4, !tbaa !3
  %184 = fdiv double %183, %165
  store double %184, double* %182, align 4, !tbaa !3
  %185 = add nuw nsw i32 %181, 1
  %186 = icmp eq i32 %185, 3
  br i1 %186, label %187, label %180, !llvm.loop !47

187:                                              ; preds = %180
  ret void
}

; Function Attrs: nounwind
declare dso_local double @sqrt(double) local_unnamed_addr #2

; Function Attrs: noinline nounwind
define dso_local void @backprop(double* nocapture %0, double* nocapture %1, double* nocapture %2, double* nocapture %3, double* nocapture %4, double* nocapture %5, double* nocapture readonly %6, double* nocapture readonly %7) local_unnamed_addr #0 {
  %9 = alloca [64 x double], align 8
  %10 = alloca [64 x double], align 8
  %11 = alloca [3 x double], align 8
  %12 = alloca [64 x double], align 8
  %13 = alloca [64 x double], align 8
  %14 = alloca [3 x double], align 8
  %15 = alloca [3 x double], align 8
  %16 = alloca [3 x double], align 8
  %17 = alloca [832 x double], align 8
  %18 = alloca [4096 x double], align 8
  %19 = alloca [192 x double], align 8
  %20 = alloca [64 x double], align 8
  %21 = alloca [64 x double], align 8
  %22 = bitcast [64 x double]* %9 to i8*
  call void @llvm.lifetime.start.p0i8(i64 512, i8* nonnull %22) #6
  %23 = bitcast [64 x double]* %10 to i8*
  call void @llvm.lifetime.start.p0i8(i64 512, i8* nonnull %23) #6
  %24 = bitcast [3 x double]* %11 to i8*
  call void @llvm.lifetime.start.p0i8(i64 24, i8* nonnull %24) #6
  %25 = bitcast [64 x double]* %12 to i8*
  call void @llvm.lifetime.start.p0i8(i64 512, i8* nonnull %25) #6
  %26 = bitcast [64 x double]* %13 to i8*
  call void @llvm.lifetime.start.p0i8(i64 512, i8* nonnull %26) #6
  %27 = bitcast [3 x double]* %14 to i8*
  call void @llvm.lifetime.start.p0i8(i64 24, i8* nonnull %27) #6
  %28 = bitcast [3 x double]* %15 to i8*
  call void @llvm.lifetime.start.p0i8(i64 24, i8* nonnull %28) #6
  %29 = bitcast [3 x double]* %16 to i8*
  call void @llvm.lifetime.start.p0i8(i64 24, i8* nonnull %29) #6
  %30 = bitcast [832 x double]* %17 to i8*
  call void @llvm.lifetime.start.p0i8(i64 6656, i8* nonnull %30) #6
  %31 = bitcast [4096 x double]* %18 to i8*
  call void @llvm.lifetime.start.p0i8(i64 32768, i8* nonnull %31) #6
  %32 = bitcast [192 x double]* %19 to i8*
  call void @llvm.lifetime.start.p0i8(i64 1536, i8* nonnull %32) #6
  %33 = bitcast [64 x double]* %20 to i8*
  call void @llvm.lifetime.start.p0i8(i64 512, i8* nonnull %33) #6
  %34 = bitcast [64 x double]* %21 to i8*
  call void @llvm.lifetime.start.p0i8(i64 512, i8* nonnull %34) #6
  %35 = getelementptr inbounds [64 x double], [64 x double]* %9, i32 0, i32 0
  %36 = getelementptr inbounds [64 x double], [64 x double]* %12, i32 0, i32 0
  %37 = getelementptr inbounds [64 x double], [64 x double]* %10, i32 0, i32 0
  %38 = getelementptr inbounds [64 x double], [64 x double]* %13, i32 0, i32 0
  %39 = getelementptr inbounds [3 x double], [3 x double]* %11, i32 0, i32 0
  %40 = getelementptr inbounds [3 x double], [3 x double]* %14, i32 0, i32 0
  %41 = getelementptr inbounds [3 x double], [3 x double]* %15, i32 0, i32 0
  %42 = getelementptr inbounds [3 x double], [3 x double]* %16, i32 0, i32 0
  %43 = getelementptr inbounds [192 x double], [192 x double]* %19, i32 0, i32 0
  %44 = getelementptr inbounds [64 x double], [64 x double]* %21, i32 0, i32 0
  %45 = getelementptr inbounds [4096 x double], [4096 x double]* %18, i32 0, i32 0
  %46 = getelementptr inbounds [64 x double], [64 x double]* %20, i32 0, i32 0
  %47 = getelementptr inbounds [832 x double], [832 x double]* %17, i32 0, i32 0
  br label %48

48:                                               ; preds = %8, %61
  %49 = phi i32 [ 0, %8 ], [ %66, %61 ]
  br label %50

50:                                               ; preds = %48, %50
  %51 = phi i32 [ 0, %48 ], [ %54, %50 ]
  %52 = getelementptr inbounds [64 x double], [64 x double]* %9, i32 0, i32 %51
  store double 0.000000e+00, double* %52, align 8, !tbaa !3
  %53 = getelementptr inbounds [64 x double], [64 x double]* %10, i32 0, i32 %51
  store double 0.000000e+00, double* %53, align 8, !tbaa !3
  %54 = add nuw nsw i32 %51, 1
  %55 = icmp eq i32 %54, 64
  br i1 %55, label %56, label %50, !llvm.loop !48

56:                                               ; preds = %50, %56
  %57 = phi i32 [ %59, %56 ], [ 0, %50 ]
  %58 = getelementptr inbounds [3 x double], [3 x double]* %11, i32 0, i32 %57
  store double 0.000000e+00, double* %58, align 8, !tbaa !3
  %59 = add nuw nsw i32 %57, 1
  %60 = icmp eq i32 %59, 3
  br i1 %60, label %61, label %56, !llvm.loop !49

61:                                               ; preds = %56
  %62 = mul nuw nsw i32 %49, 13
  %63 = getelementptr inbounds double, double* %6, i32 %62
  call void @mvp_input_layer(double* %3, double* %0, double* nonnull %35, double* %63) #5
  call void @sigmoid(double* nonnull %35, double* nonnull %36, i32 64) #5
  call void @mvp_hidden_layer(double* %4, double* %1, double* nonnull %37, double* nonnull %35) #5
  call void @sigmoid(double* nonnull %37, double* nonnull %38, i32 64) #5
  call void @mvp_output_layer(double* %5, double* %2, double* nonnull %39, double* nonnull %37) #5
  call void @sigmoid(double* nonnull %39, double* nonnull %40, i32 3) #5
  call void @soft_max(double* nonnull %41, double* nonnull %39) #5
  %64 = mul nuw nsw i32 %49, 3
  %65 = getelementptr inbounds double, double* %7, i32 %64
  call void @take_difference(double* nonnull %41, double* %65, double* nonnull %42, double* nonnull %40) #5
  call void @delta_weights3(double* nonnull %43, double* nonnull %42, double* nonnull %37) #5
  call void @oracle_act2(double* %2, double* nonnull %42, double* nonnull %44, double* nonnull %38) #5
  call void @delta_weights2(double* nonnull %45, double* nonnull %44, double* nonnull %35) #5
  call void @oracle_act1(double* %1, double* nonnull %44, double* nonnull %46, double* nonnull %36) #5
  call void @delta_weights1(double* nonnull %47, double* nonnull %46, double* %63) #5
  call void @update_weights(double* %0, double* %1, double* %2, double* nonnull %47, double* nonnull %45, double* nonnull %43, double* %3, double* %4, double* %5, double* nonnull %46, double* nonnull %44, double* nonnull %42) #5
  %66 = add nuw nsw i32 %49, 1
  %67 = icmp eq i32 %66, 163
  br i1 %67, label %68, label %48, !llvm.loop !50

68:                                               ; preds = %61
  call void @llvm.lifetime.end.p0i8(i64 512, i8* nonnull %34) #6
  call void @llvm.lifetime.end.p0i8(i64 512, i8* nonnull %33) #6
  call void @llvm.lifetime.end.p0i8(i64 1536, i8* nonnull %32) #6
  call void @llvm.lifetime.end.p0i8(i64 32768, i8* nonnull %31) #6
  call void @llvm.lifetime.end.p0i8(i64 6656, i8* nonnull %30) #6
  call void @llvm.lifetime.end.p0i8(i64 24, i8* nonnull %29) #6
  call void @llvm.lifetime.end.p0i8(i64 24, i8* nonnull %28) #6
  call void @llvm.lifetime.end.p0i8(i64 24, i8* nonnull %27) #6
  call void @llvm.lifetime.end.p0i8(i64 512, i8* nonnull %26) #6
  call void @llvm.lifetime.end.p0i8(i64 512, i8* nonnull %25) #6
  call void @llvm.lifetime.end.p0i8(i64 24, i8* nonnull %24) #6
  call void @llvm.lifetime.end.p0i8(i64 512, i8* nonnull %23) #6
  call void @llvm.lifetime.end.p0i8(i64 512, i8* nonnull %22) #6
  ret void
}

; Function Attrs: noinline nounwind
define dso_local void @top() local_unnamed_addr #0 {
  call void @backprop(double* nonnull inttoptr (i32 789577728 to double*), double* nonnull inttoptr (i32 789584384 to double*), double* nonnull inttoptr (i32 789617152 to double*), double* nonnull inttoptr (i32 789618688 to double*), double* nonnull inttoptr (i32 789619200 to double*), double* nonnull inttoptr (i32 789619712 to double*), double* nonnull inttoptr (i32 789619744 to double*), double* nonnull inttoptr (i32 789636672 to double*)) #5
  ret void
}

attributes #0 = { noinline nounwind "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "min-legal-vector-width"="0" "no-builtins" "no-infs-fp-math"="false" "no-jump-tables"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="i686" "target-features"="+cx8,+x87" "tune-cpu"="generic" "unsafe-fp-math"="false" "use-soft-float"="false" }
attributes #1 = { argmemonly nofree nosync nounwind willreturn }
attributes #2 = { nounwind "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "no-builtins" "no-infs-fp-math"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="i686" "target-features"="+cx8,+x87" "tune-cpu"="generic" "unsafe-fp-math"="false" "use-soft-float"="false" }
attributes #3 = { nofree noinline norecurse nounwind "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "min-legal-vector-width"="0" "no-builtins" "no-infs-fp-math"="false" "no-jump-tables"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="i686" "target-features"="+cx8,+x87" "tune-cpu"="generic" "unsafe-fp-math"="false" "use-soft-float"="false" }
attributes #4 = { nobuiltin nounwind "no-builtins" }
attributes #5 = { nobuiltin "no-builtins" }
attributes #6 = { nounwind }

!llvm.module.flags = !{!0, !1}
!llvm.ident = !{!2}

!0 = !{i32 1, !"NumRegisterParameters", i32 0}
!1 = !{i32 1, !"wchar_size", i32 4}
!2 = !{!"Ubuntu clang version 12.0.0-3ubuntu1~20.04.5"}
!3 = !{!4, !4, i64 0}
!4 = !{!"double", !5, i64 0}
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
!20 = distinct !{!20, !8, !9}
!21 = distinct !{!21, !8, !9}
!22 = distinct !{!22, !8, !9}
!23 = distinct !{!23, !8, !9}
!24 = distinct !{!24, !8, !9}
!25 = distinct !{!25, !8, !9}
!26 = distinct !{!26, !8, !9}
!27 = distinct !{!27, !8, !9}
!28 = distinct !{!28, !8, !9}
!29 = distinct !{!29, !8, !9}
!30 = distinct !{!30, !8, !9}
!31 = distinct !{!31, !8, !9}
!32 = distinct !{!32, !8, !9}
!33 = distinct !{!33, !8, !9}
!34 = distinct !{!34, !8, !9}
!35 = distinct !{!35, !8, !9}
!36 = distinct !{!36, !8, !9}
!37 = distinct !{!37, !8, !9}
!38 = distinct !{!38, !8, !9}
!39 = distinct !{!39, !8, !9}
!40 = distinct !{!40, !8, !9}
!41 = distinct !{!41, !8, !9}
!42 = distinct !{!42, !8, !9}
!43 = distinct !{!43, !8, !9}
!44 = distinct !{!44, !8, !9}
!45 = distinct !{!45, !8, !9}
!46 = distinct !{!46, !8, !9}
!47 = distinct !{!47, !8, !9}
!48 = distinct !{!48, !8, !9}
!49 = distinct !{!49, !8, !9}
!50 = distinct !{!50, !8, !9}
