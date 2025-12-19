; ModuleID = 'aes.c'
source_filename = "aes.c"
target datalayout = "e-m:e-p:32:32-p270:32:32-p271:32:32-p272:64:64-f64:32:64-f80:32-n8:16:32-S128"
target triple = "i386-pc-linux-gnu"

%struct.aes256_context = type { [32 x i8], [32 x i8], [32 x i8] }

@sbox = internal unnamed_addr constant [256 x i8] c"c|w{\F2ko\C50\01g+\FE\D7\ABv\CA\82\C9}\FAYG\F0\AD\D4\A2\AF\9C\A4r\C0\B7\FD\93&6?\F7\CC4\A5\E5\F1q\D81\15\04\C7#\C3\18\96\05\9A\07\12\80\E2\EB'\B2u\09\83,\1A\1BnZ\A0R;\D6\B3)\E3/\84S\D1\00\ED \FC\B1[j\CB\BE9JLX\CF\D0\EF\AA\FBCM3\85E\F9\02\7FP<\9F\A8Q\A3@\8F\92\9D8\F5\BC\B6\DA!\10\FF\F3\D2\CD\0C\13\EC_\97D\17\C4\A7~=d]\19s`\81O\DC\22*\90\88F\EE\B8\14\DE^\0B\DB\E02:\0AI\06$\\\C2\D3\ACb\91\95\E4y\E7\C87m\8D\D5N\A9lV\F4\EAez\AE\08\BAx%.\1C\A6\B4\C6\E8\DDt\1FK\BD\8B\8Ap>\B5fH\03\F6\0Ea5W\B9\86\C1\1D\9E\E1\F8\98\11i\D9\8E\94\9B\1E\87\E9\CEU(\DF\8C\A1\89\0D\BF\E6BhA\99-\0F\B0T\BB\16", align 1

; Function Attrs: nofree noinline nounwind
define dso_local void @aes256_encrypt_ecb(%struct.aes256_context* %0, i8* nocapture readonly %1, i8* nocapture %2) local_unnamed_addr #0 {
  %4 = alloca i8, align 1
  call void @llvm.lifetime.start.p0i8(i64 1, i8* nonnull %4) #5
  store i8 1, i8* %4, align 1, !tbaa !3
  br label %7

5:                                                ; preds = %7
  %6 = getelementptr inbounds %struct.aes256_context, %struct.aes256_context* %0, i32 0, i32 2, i32 0
  br label %15

7:                                                ; preds = %3, %7
  %8 = phi i32 [ 0, %3 ], [ %13, %7 ]
  %9 = getelementptr inbounds i8, i8* %1, i32 %8
  %10 = load i8, i8* %9, align 1, !tbaa !3
  %11 = getelementptr inbounds %struct.aes256_context, %struct.aes256_context* %0, i32 0, i32 2, i32 %8
  store i8 %10, i8* %11, align 1, !tbaa !3
  %12 = getelementptr inbounds %struct.aes256_context, %struct.aes256_context* %0, i32 0, i32 1, i32 %8
  store i8 %10, i8* %12, align 1, !tbaa !3
  %13 = add nuw nsw i32 %8, 1
  %14 = icmp eq i32 %13, 32
  br i1 %14, label %5, label %7, !llvm.loop !6

15:                                               ; preds = %5, %15
  %16 = phi i8 [ 7, %5 ], [ %17, %15 ]
  call fastcc void @aes_expandEncKey(i8* nonnull %6, i8* nonnull %4) #6
  %17 = add nsw i8 %16, -1
  %18 = icmp eq i8 %17, 0
  br i1 %18, label %19, label %15, !llvm.loop !9

19:                                               ; preds = %15
  store i8 1, i8* %4, align 1, !tbaa !3
  %20 = getelementptr inbounds %struct.aes256_context, %struct.aes256_context* %0, i32 0, i32 1, i32 0
  %21 = getelementptr inbounds %struct.aes256_context, %struct.aes256_context* %0, i32 0, i32 0, i32 0
  call fastcc void @aes_addRoundKey_cpy(i8* %2, i8* nonnull %20, i8* %21) #6
  %22 = getelementptr inbounds %struct.aes256_context, %struct.aes256_context* %0, i32 0, i32 0, i32 16
  br label %23

23:                                               ; preds = %19, %29
  %24 = phi i8 [ 1, %19 ], [ %30, %29 ]
  call fastcc void @aes_subBytes(i8* %2) #6
  call fastcc void @aes_shiftRows(i8* %2) #6
  call fastcc void @aes_mixColumns(i8* %2) #6
  %25 = and i8 %24, 1
  %26 = icmp eq i8 %25, 0
  br i1 %26, label %28, label %27

27:                                               ; preds = %23
  call fastcc void @aes_addRoundKey(i8* %2, i8* nonnull %22) #6
  br label %29

28:                                               ; preds = %23
  call fastcc void @aes_expandEncKey(i8* %21, i8* nonnull %4) #6
  call fastcc void @aes_addRoundKey(i8* %2, i8* %21) #6
  br label %29

29:                                               ; preds = %27, %28
  %30 = add nuw nsw i8 %24, 1
  %31 = icmp eq i8 %30, 14
  br i1 %31, label %32, label %23, !llvm.loop !10

32:                                               ; preds = %29
  call fastcc void @aes_subBytes(i8* %2) #6
  call fastcc void @aes_shiftRows(i8* %2) #6
  call fastcc void @aes_expandEncKey(i8* %21, i8* nonnull %4) #6
  call fastcc void @aes_addRoundKey(i8* %2, i8* %21) #6
  call void @llvm.lifetime.end.p0i8(i64 1, i8* nonnull %4) #5
  ret void
}

; Function Attrs: argmemonly nofree nosync nounwind willreturn
declare void @llvm.lifetime.start.p0i8(i64 immarg, i8* nocapture) #1

; Function Attrs: nofree noinline norecurse nounwind
define internal fastcc void @aes_expandEncKey(i8* %0, i8* nocapture %1) unnamed_addr #2 {
  %3 = getelementptr inbounds i8, i8* %0, i32 29
  %4 = load i8, i8* %3, align 1, !tbaa !3
  %5 = zext i8 %4 to i32
  %6 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %5
  %7 = load i8, i8* %6, align 1, !tbaa !3
  %8 = load i8, i8* %1, align 1, !tbaa !3
  %9 = xor i8 %8, %7
  %10 = load i8, i8* %0, align 1, !tbaa !3
  %11 = xor i8 %9, %10
  store i8 %11, i8* %0, align 1, !tbaa !3
  %12 = getelementptr inbounds i8, i8* %0, i32 30
  %13 = load i8, i8* %12, align 1, !tbaa !3
  %14 = zext i8 %13 to i32
  %15 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %14
  %16 = load i8, i8* %15, align 1, !tbaa !3
  %17 = getelementptr inbounds i8, i8* %0, i32 1
  %18 = load i8, i8* %17, align 1, !tbaa !3
  %19 = xor i8 %18, %16
  store i8 %19, i8* %17, align 1, !tbaa !3
  %20 = getelementptr inbounds i8, i8* %0, i32 31
  %21 = load i8, i8* %20, align 1, !tbaa !3
  %22 = zext i8 %21 to i32
  %23 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %22
  %24 = load i8, i8* %23, align 1, !tbaa !3
  %25 = getelementptr inbounds i8, i8* %0, i32 2
  %26 = load i8, i8* %25, align 1, !tbaa !3
  %27 = xor i8 %26, %24
  store i8 %27, i8* %25, align 1, !tbaa !3
  %28 = getelementptr inbounds i8, i8* %0, i32 28
  %29 = load i8, i8* %28, align 1, !tbaa !3
  %30 = zext i8 %29 to i32
  %31 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %30
  %32 = load i8, i8* %31, align 1, !tbaa !3
  %33 = getelementptr inbounds i8, i8* %0, i32 3
  %34 = load i8, i8* %33, align 1, !tbaa !3
  %35 = xor i8 %34, %32
  store i8 %35, i8* %33, align 1, !tbaa !3
  %36 = load i8, i8* %1, align 1, !tbaa !3
  %37 = shl i8 %36, 1
  %38 = ashr i8 %36, 7
  %39 = and i8 %38, 27
  %40 = xor i8 %39, %37
  store i8 %40, i8* %1, align 1, !tbaa !3
  br label %41

41:                                               ; preds = %2, %41
  %42 = phi i32 [ 4, %2 ], [ %71, %41 ]
  %43 = add nsw i32 %42, -4
  %44 = getelementptr inbounds i8, i8* %0, i32 %43
  %45 = load i8, i8* %44, align 1, !tbaa !3
  %46 = getelementptr inbounds i8, i8* %0, i32 %42
  %47 = load i8, i8* %46, align 1, !tbaa !3
  %48 = xor i8 %47, %45
  store i8 %48, i8* %46, align 1, !tbaa !3
  %49 = add nsw i32 %42, -3
  %50 = getelementptr inbounds i8, i8* %0, i32 %49
  %51 = load i8, i8* %50, align 1, !tbaa !3
  %52 = add nuw nsw i32 %42, 1
  %53 = getelementptr inbounds i8, i8* %0, i32 %52
  %54 = load i8, i8* %53, align 1, !tbaa !3
  %55 = xor i8 %54, %51
  store i8 %55, i8* %53, align 1, !tbaa !3
  %56 = add nsw i32 %42, -2
  %57 = getelementptr inbounds i8, i8* %0, i32 %56
  %58 = load i8, i8* %57, align 1, !tbaa !3
  %59 = add nuw nsw i32 %42, 2
  %60 = getelementptr inbounds i8, i8* %0, i32 %59
  %61 = load i8, i8* %60, align 1, !tbaa !3
  %62 = xor i8 %61, %58
  store i8 %62, i8* %60, align 1, !tbaa !3
  %63 = add nsw i32 %42, -1
  %64 = getelementptr inbounds i8, i8* %0, i32 %63
  %65 = load i8, i8* %64, align 1, !tbaa !3
  %66 = add nuw nsw i32 %42, 3
  %67 = getelementptr inbounds i8, i8* %0, i32 %66
  %68 = load i8, i8* %67, align 1, !tbaa !3
  %69 = xor i8 %68, %65
  store i8 %69, i8* %67, align 1, !tbaa !3
  %70 = add nuw nsw i32 %42, 4
  %71 = and i32 %70, 255
  %72 = icmp ult i32 %71, 16
  br i1 %72, label %41, label %73, !llvm.loop !11

73:                                               ; preds = %41
  %74 = getelementptr inbounds i8, i8* %0, i32 12
  %75 = load i8, i8* %74, align 1, !tbaa !3
  %76 = zext i8 %75 to i32
  %77 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %76
  %78 = load i8, i8* %77, align 1, !tbaa !3
  %79 = getelementptr inbounds i8, i8* %0, i32 16
  %80 = load i8, i8* %79, align 1, !tbaa !3
  %81 = xor i8 %80, %78
  store i8 %81, i8* %79, align 1, !tbaa !3
  %82 = getelementptr inbounds i8, i8* %0, i32 13
  %83 = load i8, i8* %82, align 1, !tbaa !3
  %84 = zext i8 %83 to i32
  %85 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %84
  %86 = load i8, i8* %85, align 1, !tbaa !3
  %87 = getelementptr inbounds i8, i8* %0, i32 17
  %88 = load i8, i8* %87, align 1, !tbaa !3
  %89 = xor i8 %88, %86
  store i8 %89, i8* %87, align 1, !tbaa !3
  %90 = getelementptr inbounds i8, i8* %0, i32 14
  %91 = load i8, i8* %90, align 1, !tbaa !3
  %92 = zext i8 %91 to i32
  %93 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %92
  %94 = load i8, i8* %93, align 1, !tbaa !3
  %95 = getelementptr inbounds i8, i8* %0, i32 18
  %96 = load i8, i8* %95, align 1, !tbaa !3
  %97 = xor i8 %96, %94
  store i8 %97, i8* %95, align 1, !tbaa !3
  %98 = getelementptr inbounds i8, i8* %0, i32 15
  %99 = load i8, i8* %98, align 1, !tbaa !3
  %100 = zext i8 %99 to i32
  %101 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %100
  %102 = load i8, i8* %101, align 1, !tbaa !3
  %103 = getelementptr inbounds i8, i8* %0, i32 19
  %104 = load i8, i8* %103, align 1, !tbaa !3
  %105 = xor i8 %104, %102
  store i8 %105, i8* %103, align 1, !tbaa !3
  br label %106

106:                                              ; preds = %73, %106
  %107 = phi i32 [ 20, %73 ], [ %136, %106 ]
  %108 = add nsw i32 %107, -4
  %109 = getelementptr inbounds i8, i8* %0, i32 %108
  %110 = load i8, i8* %109, align 1, !tbaa !3
  %111 = getelementptr inbounds i8, i8* %0, i32 %107
  %112 = load i8, i8* %111, align 1, !tbaa !3
  %113 = xor i8 %112, %110
  store i8 %113, i8* %111, align 1, !tbaa !3
  %114 = add nsw i32 %107, -3
  %115 = getelementptr inbounds i8, i8* %0, i32 %114
  %116 = load i8, i8* %115, align 1, !tbaa !3
  %117 = add nuw nsw i32 %107, 1
  %118 = getelementptr inbounds i8, i8* %0, i32 %117
  %119 = load i8, i8* %118, align 1, !tbaa !3
  %120 = xor i8 %119, %116
  store i8 %120, i8* %118, align 1, !tbaa !3
  %121 = add nsw i32 %107, -2
  %122 = getelementptr inbounds i8, i8* %0, i32 %121
  %123 = load i8, i8* %122, align 1, !tbaa !3
  %124 = add nuw nsw i32 %107, 2
  %125 = getelementptr inbounds i8, i8* %0, i32 %124
  %126 = load i8, i8* %125, align 1, !tbaa !3
  %127 = xor i8 %126, %123
  store i8 %127, i8* %125, align 1, !tbaa !3
  %128 = add nsw i32 %107, -1
  %129 = getelementptr inbounds i8, i8* %0, i32 %128
  %130 = load i8, i8* %129, align 1, !tbaa !3
  %131 = add nuw nsw i32 %107, 3
  %132 = getelementptr inbounds i8, i8* %0, i32 %131
  %133 = load i8, i8* %132, align 1, !tbaa !3
  %134 = xor i8 %133, %130
  store i8 %134, i8* %132, align 1, !tbaa !3
  %135 = add nuw nsw i32 %107, 4
  %136 = and i32 %135, 255
  %137 = icmp ult i32 %136, 32
  br i1 %137, label %106, label %138, !llvm.loop !12

138:                                              ; preds = %106
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define internal fastcc void @aes_addRoundKey_cpy(i8* nocapture %0, i8* nocapture readonly %1, i8* nocapture %2) unnamed_addr #2 {
  %4 = load i8, i8* %1, align 1, !tbaa !3
  store i8 %4, i8* %2, align 1, !tbaa !3
  %5 = load i8, i8* %0, align 1, !tbaa !3
  %6 = xor i8 %5, %4
  store i8 %6, i8* %0, align 1, !tbaa !3
  %7 = getelementptr inbounds i8, i8* %1, i32 16
  %8 = load i8, i8* %7, align 1, !tbaa !3
  %9 = getelementptr inbounds i8, i8* %2, i32 16
  store i8 %8, i8* %9, align 1, !tbaa !3
  %10 = getelementptr inbounds i8, i8* %1, i32 1
  %11 = load i8, i8* %10, align 1, !tbaa !3
  %12 = getelementptr inbounds i8, i8* %2, i32 1
  store i8 %11, i8* %12, align 1, !tbaa !3
  %13 = getelementptr inbounds i8, i8* %0, i32 1
  %14 = load i8, i8* %13, align 1, !tbaa !3
  %15 = xor i8 %14, %11
  store i8 %15, i8* %13, align 1, !tbaa !3
  %16 = getelementptr inbounds i8, i8* %1, i32 17
  %17 = load i8, i8* %16, align 1, !tbaa !3
  %18 = getelementptr inbounds i8, i8* %2, i32 17
  store i8 %17, i8* %18, align 1, !tbaa !3
  %19 = getelementptr inbounds i8, i8* %1, i32 2
  %20 = load i8, i8* %19, align 1, !tbaa !3
  %21 = getelementptr inbounds i8, i8* %2, i32 2
  store i8 %20, i8* %21, align 1, !tbaa !3
  %22 = getelementptr inbounds i8, i8* %0, i32 2
  %23 = load i8, i8* %22, align 1, !tbaa !3
  %24 = xor i8 %23, %20
  store i8 %24, i8* %22, align 1, !tbaa !3
  %25 = getelementptr inbounds i8, i8* %1, i32 18
  %26 = load i8, i8* %25, align 1, !tbaa !3
  %27 = getelementptr inbounds i8, i8* %2, i32 18
  store i8 %26, i8* %27, align 1, !tbaa !3
  %28 = getelementptr inbounds i8, i8* %1, i32 3
  %29 = load i8, i8* %28, align 1, !tbaa !3
  %30 = getelementptr inbounds i8, i8* %2, i32 3
  store i8 %29, i8* %30, align 1, !tbaa !3
  %31 = getelementptr inbounds i8, i8* %0, i32 3
  %32 = load i8, i8* %31, align 1, !tbaa !3
  %33 = xor i8 %32, %29
  store i8 %33, i8* %31, align 1, !tbaa !3
  %34 = getelementptr inbounds i8, i8* %1, i32 19
  %35 = load i8, i8* %34, align 1, !tbaa !3
  %36 = getelementptr inbounds i8, i8* %2, i32 19
  store i8 %35, i8* %36, align 1, !tbaa !3
  %37 = getelementptr inbounds i8, i8* %1, i32 4
  %38 = load i8, i8* %37, align 1, !tbaa !3
  %39 = getelementptr inbounds i8, i8* %2, i32 4
  store i8 %38, i8* %39, align 1, !tbaa !3
  %40 = getelementptr inbounds i8, i8* %0, i32 4
  %41 = load i8, i8* %40, align 1, !tbaa !3
  %42 = xor i8 %41, %38
  store i8 %42, i8* %40, align 1, !tbaa !3
  %43 = getelementptr inbounds i8, i8* %1, i32 20
  %44 = load i8, i8* %43, align 1, !tbaa !3
  %45 = getelementptr inbounds i8, i8* %2, i32 20
  store i8 %44, i8* %45, align 1, !tbaa !3
  %46 = getelementptr inbounds i8, i8* %1, i32 5
  %47 = load i8, i8* %46, align 1, !tbaa !3
  %48 = getelementptr inbounds i8, i8* %2, i32 5
  store i8 %47, i8* %48, align 1, !tbaa !3
  %49 = getelementptr inbounds i8, i8* %0, i32 5
  %50 = load i8, i8* %49, align 1, !tbaa !3
  %51 = xor i8 %50, %47
  store i8 %51, i8* %49, align 1, !tbaa !3
  %52 = getelementptr inbounds i8, i8* %1, i32 21
  %53 = load i8, i8* %52, align 1, !tbaa !3
  %54 = getelementptr inbounds i8, i8* %2, i32 21
  store i8 %53, i8* %54, align 1, !tbaa !3
  %55 = getelementptr inbounds i8, i8* %1, i32 6
  %56 = load i8, i8* %55, align 1, !tbaa !3
  %57 = getelementptr inbounds i8, i8* %2, i32 6
  store i8 %56, i8* %57, align 1, !tbaa !3
  %58 = getelementptr inbounds i8, i8* %0, i32 6
  %59 = load i8, i8* %58, align 1, !tbaa !3
  %60 = xor i8 %59, %56
  store i8 %60, i8* %58, align 1, !tbaa !3
  %61 = getelementptr inbounds i8, i8* %1, i32 22
  %62 = load i8, i8* %61, align 1, !tbaa !3
  %63 = getelementptr inbounds i8, i8* %2, i32 22
  store i8 %62, i8* %63, align 1, !tbaa !3
  %64 = getelementptr inbounds i8, i8* %1, i32 7
  %65 = load i8, i8* %64, align 1, !tbaa !3
  %66 = getelementptr inbounds i8, i8* %2, i32 7
  store i8 %65, i8* %66, align 1, !tbaa !3
  %67 = getelementptr inbounds i8, i8* %0, i32 7
  %68 = load i8, i8* %67, align 1, !tbaa !3
  %69 = xor i8 %68, %65
  store i8 %69, i8* %67, align 1, !tbaa !3
  %70 = getelementptr inbounds i8, i8* %1, i32 23
  %71 = load i8, i8* %70, align 1, !tbaa !3
  %72 = getelementptr inbounds i8, i8* %2, i32 23
  store i8 %71, i8* %72, align 1, !tbaa !3
  %73 = getelementptr inbounds i8, i8* %1, i32 8
  %74 = load i8, i8* %73, align 1, !tbaa !3
  %75 = getelementptr inbounds i8, i8* %2, i32 8
  store i8 %74, i8* %75, align 1, !tbaa !3
  %76 = getelementptr inbounds i8, i8* %0, i32 8
  %77 = load i8, i8* %76, align 1, !tbaa !3
  %78 = xor i8 %77, %74
  store i8 %78, i8* %76, align 1, !tbaa !3
  %79 = getelementptr inbounds i8, i8* %1, i32 24
  %80 = load i8, i8* %79, align 1, !tbaa !3
  %81 = getelementptr inbounds i8, i8* %2, i32 24
  store i8 %80, i8* %81, align 1, !tbaa !3
  %82 = getelementptr inbounds i8, i8* %1, i32 9
  %83 = load i8, i8* %82, align 1, !tbaa !3
  %84 = getelementptr inbounds i8, i8* %2, i32 9
  store i8 %83, i8* %84, align 1, !tbaa !3
  %85 = getelementptr inbounds i8, i8* %0, i32 9
  %86 = load i8, i8* %85, align 1, !tbaa !3
  %87 = xor i8 %86, %83
  store i8 %87, i8* %85, align 1, !tbaa !3
  %88 = getelementptr inbounds i8, i8* %1, i32 25
  %89 = load i8, i8* %88, align 1, !tbaa !3
  %90 = getelementptr inbounds i8, i8* %2, i32 25
  store i8 %89, i8* %90, align 1, !tbaa !3
  %91 = getelementptr inbounds i8, i8* %1, i32 10
  %92 = load i8, i8* %91, align 1, !tbaa !3
  %93 = getelementptr inbounds i8, i8* %2, i32 10
  store i8 %92, i8* %93, align 1, !tbaa !3
  %94 = getelementptr inbounds i8, i8* %0, i32 10
  %95 = load i8, i8* %94, align 1, !tbaa !3
  %96 = xor i8 %95, %92
  store i8 %96, i8* %94, align 1, !tbaa !3
  %97 = getelementptr inbounds i8, i8* %1, i32 26
  %98 = load i8, i8* %97, align 1, !tbaa !3
  %99 = getelementptr inbounds i8, i8* %2, i32 26
  store i8 %98, i8* %99, align 1, !tbaa !3
  %100 = getelementptr inbounds i8, i8* %1, i32 11
  %101 = load i8, i8* %100, align 1, !tbaa !3
  %102 = getelementptr inbounds i8, i8* %2, i32 11
  store i8 %101, i8* %102, align 1, !tbaa !3
  %103 = getelementptr inbounds i8, i8* %0, i32 11
  %104 = load i8, i8* %103, align 1, !tbaa !3
  %105 = xor i8 %104, %101
  store i8 %105, i8* %103, align 1, !tbaa !3
  %106 = getelementptr inbounds i8, i8* %1, i32 27
  %107 = load i8, i8* %106, align 1, !tbaa !3
  %108 = getelementptr inbounds i8, i8* %2, i32 27
  store i8 %107, i8* %108, align 1, !tbaa !3
  %109 = getelementptr inbounds i8, i8* %1, i32 12
  %110 = load i8, i8* %109, align 1, !tbaa !3
  %111 = getelementptr inbounds i8, i8* %2, i32 12
  store i8 %110, i8* %111, align 1, !tbaa !3
  %112 = getelementptr inbounds i8, i8* %0, i32 12
  %113 = load i8, i8* %112, align 1, !tbaa !3
  %114 = xor i8 %113, %110
  store i8 %114, i8* %112, align 1, !tbaa !3
  %115 = getelementptr inbounds i8, i8* %1, i32 28
  %116 = load i8, i8* %115, align 1, !tbaa !3
  %117 = getelementptr inbounds i8, i8* %2, i32 28
  store i8 %116, i8* %117, align 1, !tbaa !3
  %118 = getelementptr inbounds i8, i8* %1, i32 13
  %119 = load i8, i8* %118, align 1, !tbaa !3
  %120 = getelementptr inbounds i8, i8* %2, i32 13
  store i8 %119, i8* %120, align 1, !tbaa !3
  %121 = getelementptr inbounds i8, i8* %0, i32 13
  %122 = load i8, i8* %121, align 1, !tbaa !3
  %123 = xor i8 %122, %119
  store i8 %123, i8* %121, align 1, !tbaa !3
  %124 = getelementptr inbounds i8, i8* %1, i32 29
  %125 = load i8, i8* %124, align 1, !tbaa !3
  %126 = getelementptr inbounds i8, i8* %2, i32 29
  store i8 %125, i8* %126, align 1, !tbaa !3
  %127 = getelementptr inbounds i8, i8* %1, i32 14
  %128 = load i8, i8* %127, align 1, !tbaa !3
  %129 = getelementptr inbounds i8, i8* %2, i32 14
  store i8 %128, i8* %129, align 1, !tbaa !3
  %130 = getelementptr inbounds i8, i8* %0, i32 14
  %131 = load i8, i8* %130, align 1, !tbaa !3
  %132 = xor i8 %131, %128
  store i8 %132, i8* %130, align 1, !tbaa !3
  %133 = getelementptr inbounds i8, i8* %1, i32 30
  %134 = load i8, i8* %133, align 1, !tbaa !3
  %135 = getelementptr inbounds i8, i8* %2, i32 30
  store i8 %134, i8* %135, align 1, !tbaa !3
  %136 = getelementptr inbounds i8, i8* %1, i32 15
  %137 = load i8, i8* %136, align 1, !tbaa !3
  %138 = getelementptr inbounds i8, i8* %2, i32 15
  store i8 %137, i8* %138, align 1, !tbaa !3
  %139 = getelementptr inbounds i8, i8* %0, i32 15
  %140 = load i8, i8* %139, align 1, !tbaa !3
  %141 = xor i8 %140, %137
  store i8 %141, i8* %139, align 1, !tbaa !3
  %142 = getelementptr inbounds i8, i8* %1, i32 31
  %143 = load i8, i8* %142, align 1, !tbaa !3
  %144 = getelementptr inbounds i8, i8* %2, i32 31
  store i8 %143, i8* %144, align 1, !tbaa !3
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define internal fastcc void @aes_subBytes(i8* nocapture %0) unnamed_addr #2 {
  %2 = load i8, i8* %0, align 1, !tbaa !3
  %3 = zext i8 %2 to i32
  %4 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %3
  %5 = load i8, i8* %4, align 1, !tbaa !3
  store i8 %5, i8* %0, align 1, !tbaa !3
  %6 = getelementptr inbounds i8, i8* %0, i32 1
  %7 = load i8, i8* %6, align 1, !tbaa !3
  %8 = zext i8 %7 to i32
  %9 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %8
  %10 = load i8, i8* %9, align 1, !tbaa !3
  store i8 %10, i8* %6, align 1, !tbaa !3
  %11 = getelementptr inbounds i8, i8* %0, i32 2
  %12 = load i8, i8* %11, align 1, !tbaa !3
  %13 = zext i8 %12 to i32
  %14 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %13
  %15 = load i8, i8* %14, align 1, !tbaa !3
  store i8 %15, i8* %11, align 1, !tbaa !3
  %16 = getelementptr inbounds i8, i8* %0, i32 3
  %17 = load i8, i8* %16, align 1, !tbaa !3
  %18 = zext i8 %17 to i32
  %19 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %18
  %20 = load i8, i8* %19, align 1, !tbaa !3
  store i8 %20, i8* %16, align 1, !tbaa !3
  %21 = getelementptr inbounds i8, i8* %0, i32 4
  %22 = load i8, i8* %21, align 1, !tbaa !3
  %23 = zext i8 %22 to i32
  %24 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %23
  %25 = load i8, i8* %24, align 1, !tbaa !3
  store i8 %25, i8* %21, align 1, !tbaa !3
  %26 = getelementptr inbounds i8, i8* %0, i32 5
  %27 = load i8, i8* %26, align 1, !tbaa !3
  %28 = zext i8 %27 to i32
  %29 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %28
  %30 = load i8, i8* %29, align 1, !tbaa !3
  store i8 %30, i8* %26, align 1, !tbaa !3
  %31 = getelementptr inbounds i8, i8* %0, i32 6
  %32 = load i8, i8* %31, align 1, !tbaa !3
  %33 = zext i8 %32 to i32
  %34 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %33
  %35 = load i8, i8* %34, align 1, !tbaa !3
  store i8 %35, i8* %31, align 1, !tbaa !3
  %36 = getelementptr inbounds i8, i8* %0, i32 7
  %37 = load i8, i8* %36, align 1, !tbaa !3
  %38 = zext i8 %37 to i32
  %39 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %38
  %40 = load i8, i8* %39, align 1, !tbaa !3
  store i8 %40, i8* %36, align 1, !tbaa !3
  %41 = getelementptr inbounds i8, i8* %0, i32 8
  %42 = load i8, i8* %41, align 1, !tbaa !3
  %43 = zext i8 %42 to i32
  %44 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %43
  %45 = load i8, i8* %44, align 1, !tbaa !3
  store i8 %45, i8* %41, align 1, !tbaa !3
  %46 = getelementptr inbounds i8, i8* %0, i32 9
  %47 = load i8, i8* %46, align 1, !tbaa !3
  %48 = zext i8 %47 to i32
  %49 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %48
  %50 = load i8, i8* %49, align 1, !tbaa !3
  store i8 %50, i8* %46, align 1, !tbaa !3
  %51 = getelementptr inbounds i8, i8* %0, i32 10
  %52 = load i8, i8* %51, align 1, !tbaa !3
  %53 = zext i8 %52 to i32
  %54 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %53
  %55 = load i8, i8* %54, align 1, !tbaa !3
  store i8 %55, i8* %51, align 1, !tbaa !3
  %56 = getelementptr inbounds i8, i8* %0, i32 11
  %57 = load i8, i8* %56, align 1, !tbaa !3
  %58 = zext i8 %57 to i32
  %59 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %58
  %60 = load i8, i8* %59, align 1, !tbaa !3
  store i8 %60, i8* %56, align 1, !tbaa !3
  %61 = getelementptr inbounds i8, i8* %0, i32 12
  %62 = load i8, i8* %61, align 1, !tbaa !3
  %63 = zext i8 %62 to i32
  %64 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %63
  %65 = load i8, i8* %64, align 1, !tbaa !3
  store i8 %65, i8* %61, align 1, !tbaa !3
  %66 = getelementptr inbounds i8, i8* %0, i32 13
  %67 = load i8, i8* %66, align 1, !tbaa !3
  %68 = zext i8 %67 to i32
  %69 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %68
  %70 = load i8, i8* %69, align 1, !tbaa !3
  store i8 %70, i8* %66, align 1, !tbaa !3
  %71 = getelementptr inbounds i8, i8* %0, i32 14
  %72 = load i8, i8* %71, align 1, !tbaa !3
  %73 = zext i8 %72 to i32
  %74 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %73
  %75 = load i8, i8* %74, align 1, !tbaa !3
  store i8 %75, i8* %71, align 1, !tbaa !3
  %76 = getelementptr inbounds i8, i8* %0, i32 15
  %77 = load i8, i8* %76, align 1, !tbaa !3
  %78 = zext i8 %77 to i32
  %79 = getelementptr inbounds [256 x i8], [256 x i8]* @sbox, i32 0, i32 %78
  %80 = load i8, i8* %79, align 1, !tbaa !3
  store i8 %80, i8* %76, align 1, !tbaa !3
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind willreturn
define internal fastcc void @aes_shiftRows(i8* nocapture %0) unnamed_addr #3 {
  %2 = getelementptr inbounds i8, i8* %0, i32 1
  %3 = load i8, i8* %2, align 1, !tbaa !3
  %4 = getelementptr inbounds i8, i8* %0, i32 5
  %5 = load i8, i8* %4, align 1, !tbaa !3
  store i8 %5, i8* %2, align 1, !tbaa !3
  %6 = getelementptr inbounds i8, i8* %0, i32 9
  %7 = load i8, i8* %6, align 1, !tbaa !3
  store i8 %7, i8* %4, align 1, !tbaa !3
  %8 = getelementptr inbounds i8, i8* %0, i32 13
  %9 = load i8, i8* %8, align 1, !tbaa !3
  store i8 %9, i8* %6, align 1, !tbaa !3
  store i8 %3, i8* %8, align 1, !tbaa !3
  %10 = getelementptr inbounds i8, i8* %0, i32 10
  %11 = load i8, i8* %10, align 1, !tbaa !3
  %12 = getelementptr inbounds i8, i8* %0, i32 2
  %13 = load i8, i8* %12, align 1, !tbaa !3
  store i8 %13, i8* %10, align 1, !tbaa !3
  store i8 %11, i8* %12, align 1, !tbaa !3
  %14 = getelementptr inbounds i8, i8* %0, i32 3
  %15 = load i8, i8* %14, align 1, !tbaa !3
  %16 = getelementptr inbounds i8, i8* %0, i32 15
  %17 = load i8, i8* %16, align 1, !tbaa !3
  store i8 %17, i8* %14, align 1, !tbaa !3
  %18 = getelementptr inbounds i8, i8* %0, i32 11
  %19 = load i8, i8* %18, align 1, !tbaa !3
  store i8 %19, i8* %16, align 1, !tbaa !3
  %20 = getelementptr inbounds i8, i8* %0, i32 7
  %21 = load i8, i8* %20, align 1, !tbaa !3
  store i8 %21, i8* %18, align 1, !tbaa !3
  store i8 %15, i8* %20, align 1, !tbaa !3
  %22 = getelementptr inbounds i8, i8* %0, i32 14
  %23 = load i8, i8* %22, align 1, !tbaa !3
  %24 = getelementptr inbounds i8, i8* %0, i32 6
  %25 = load i8, i8* %24, align 1, !tbaa !3
  store i8 %25, i8* %22, align 1, !tbaa !3
  store i8 %23, i8* %24, align 1, !tbaa !3
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define internal fastcc void @aes_mixColumns(i8* nocapture %0) unnamed_addr #2 {
  %2 = load i8, i8* %0, align 1, !tbaa !3
  %3 = getelementptr inbounds i8, i8* %0, i32 1
  %4 = load i8, i8* %3, align 1, !tbaa !3
  %5 = getelementptr inbounds i8, i8* %0, i32 2
  %6 = load i8, i8* %5, align 1, !tbaa !3
  %7 = getelementptr inbounds i8, i8* %0, i32 3
  %8 = load i8, i8* %7, align 1, !tbaa !3
  %9 = xor i8 %4, %2
  %10 = xor i8 %9, %6
  %11 = xor i8 %10, %8
  %12 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %9) #6
  %13 = xor i8 %12, %2
  %14 = xor i8 %13, %11
  store i8 %14, i8* %0, align 1, !tbaa !3
  %15 = xor i8 %6, %4
  %16 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %15) #6
  %17 = xor i8 %11, %4
  %18 = xor i8 %17, %16
  store i8 %18, i8* %3, align 1, !tbaa !3
  %19 = xor i8 %8, %6
  %20 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %19) #6
  %21 = xor i8 %9, %8
  %22 = xor i8 %21, %20
  store i8 %22, i8* %5, align 1, !tbaa !3
  %23 = xor i8 %8, %2
  %24 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %23) #6
  %25 = xor i8 %24, %10
  store i8 %25, i8* %7, align 1, !tbaa !3
  %26 = getelementptr inbounds i8, i8* %0, i32 4
  %27 = load i8, i8* %26, align 1, !tbaa !3
  %28 = getelementptr inbounds i8, i8* %0, i32 5
  %29 = load i8, i8* %28, align 1, !tbaa !3
  %30 = getelementptr inbounds i8, i8* %0, i32 6
  %31 = load i8, i8* %30, align 1, !tbaa !3
  %32 = getelementptr inbounds i8, i8* %0, i32 7
  %33 = load i8, i8* %32, align 1, !tbaa !3
  %34 = xor i8 %29, %27
  %35 = xor i8 %34, %31
  %36 = xor i8 %35, %33
  %37 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %34) #6
  %38 = xor i8 %37, %27
  %39 = xor i8 %38, %36
  store i8 %39, i8* %26, align 1, !tbaa !3
  %40 = xor i8 %31, %29
  %41 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %40) #6
  %42 = xor i8 %36, %29
  %43 = xor i8 %42, %41
  store i8 %43, i8* %28, align 1, !tbaa !3
  %44 = xor i8 %33, %31
  %45 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %44) #6
  %46 = xor i8 %34, %33
  %47 = xor i8 %46, %45
  store i8 %47, i8* %30, align 1, !tbaa !3
  %48 = xor i8 %33, %27
  %49 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %48) #6
  %50 = xor i8 %49, %35
  store i8 %50, i8* %32, align 1, !tbaa !3
  %51 = getelementptr inbounds i8, i8* %0, i32 8
  %52 = load i8, i8* %51, align 1, !tbaa !3
  %53 = getelementptr inbounds i8, i8* %0, i32 9
  %54 = load i8, i8* %53, align 1, !tbaa !3
  %55 = getelementptr inbounds i8, i8* %0, i32 10
  %56 = load i8, i8* %55, align 1, !tbaa !3
  %57 = getelementptr inbounds i8, i8* %0, i32 11
  %58 = load i8, i8* %57, align 1, !tbaa !3
  %59 = xor i8 %54, %52
  %60 = xor i8 %59, %56
  %61 = xor i8 %60, %58
  %62 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %59) #6
  %63 = xor i8 %62, %52
  %64 = xor i8 %63, %61
  store i8 %64, i8* %51, align 1, !tbaa !3
  %65 = xor i8 %56, %54
  %66 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %65) #6
  %67 = xor i8 %61, %54
  %68 = xor i8 %67, %66
  store i8 %68, i8* %53, align 1, !tbaa !3
  %69 = xor i8 %58, %56
  %70 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %69) #6
  %71 = xor i8 %59, %58
  %72 = xor i8 %71, %70
  store i8 %72, i8* %55, align 1, !tbaa !3
  %73 = xor i8 %58, %52
  %74 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %73) #6
  %75 = xor i8 %74, %60
  store i8 %75, i8* %57, align 1, !tbaa !3
  %76 = getelementptr inbounds i8, i8* %0, i32 12
  %77 = load i8, i8* %76, align 1, !tbaa !3
  %78 = getelementptr inbounds i8, i8* %0, i32 13
  %79 = load i8, i8* %78, align 1, !tbaa !3
  %80 = getelementptr inbounds i8, i8* %0, i32 14
  %81 = load i8, i8* %80, align 1, !tbaa !3
  %82 = getelementptr inbounds i8, i8* %0, i32 15
  %83 = load i8, i8* %82, align 1, !tbaa !3
  %84 = xor i8 %79, %77
  %85 = xor i8 %84, %81
  %86 = xor i8 %85, %83
  %87 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %84) #6
  %88 = xor i8 %87, %77
  %89 = xor i8 %88, %86
  store i8 %89, i8* %76, align 1, !tbaa !3
  %90 = xor i8 %81, %79
  %91 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %90) #6
  %92 = xor i8 %86, %79
  %93 = xor i8 %92, %91
  store i8 %93, i8* %78, align 1, !tbaa !3
  %94 = xor i8 %83, %81
  %95 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %94) #6
  %96 = xor i8 %84, %83
  %97 = xor i8 %96, %95
  store i8 %97, i8* %80, align 1, !tbaa !3
  %98 = xor i8 %83, %77
  %99 = call fastcc zeroext i8 @rj_xtime(i8 zeroext %98) #6
  %100 = xor i8 %99, %85
  store i8 %100, i8* %82, align 1, !tbaa !3
  ret void
}

; Function Attrs: nofree noinline norecurse nounwind
define internal fastcc void @aes_addRoundKey(i8* nocapture %0, i8* nocapture readonly %1) unnamed_addr #2 {
  %3 = load i8, i8* %1, align 1, !tbaa !3
  %4 = load i8, i8* %0, align 1, !tbaa !3
  %5 = xor i8 %4, %3
  store i8 %5, i8* %0, align 1, !tbaa !3
  %6 = getelementptr inbounds i8, i8* %1, i32 1
  %7 = load i8, i8* %6, align 1, !tbaa !3
  %8 = getelementptr inbounds i8, i8* %0, i32 1
  %9 = load i8, i8* %8, align 1, !tbaa !3
  %10 = xor i8 %9, %7
  store i8 %10, i8* %8, align 1, !tbaa !3
  %11 = getelementptr inbounds i8, i8* %1, i32 2
  %12 = load i8, i8* %11, align 1, !tbaa !3
  %13 = getelementptr inbounds i8, i8* %0, i32 2
  %14 = load i8, i8* %13, align 1, !tbaa !3
  %15 = xor i8 %14, %12
  store i8 %15, i8* %13, align 1, !tbaa !3
  %16 = getelementptr inbounds i8, i8* %1, i32 3
  %17 = load i8, i8* %16, align 1, !tbaa !3
  %18 = getelementptr inbounds i8, i8* %0, i32 3
  %19 = load i8, i8* %18, align 1, !tbaa !3
  %20 = xor i8 %19, %17
  store i8 %20, i8* %18, align 1, !tbaa !3
  %21 = getelementptr inbounds i8, i8* %1, i32 4
  %22 = load i8, i8* %21, align 1, !tbaa !3
  %23 = getelementptr inbounds i8, i8* %0, i32 4
  %24 = load i8, i8* %23, align 1, !tbaa !3
  %25 = xor i8 %24, %22
  store i8 %25, i8* %23, align 1, !tbaa !3
  %26 = getelementptr inbounds i8, i8* %1, i32 5
  %27 = load i8, i8* %26, align 1, !tbaa !3
  %28 = getelementptr inbounds i8, i8* %0, i32 5
  %29 = load i8, i8* %28, align 1, !tbaa !3
  %30 = xor i8 %29, %27
  store i8 %30, i8* %28, align 1, !tbaa !3
  %31 = getelementptr inbounds i8, i8* %1, i32 6
  %32 = load i8, i8* %31, align 1, !tbaa !3
  %33 = getelementptr inbounds i8, i8* %0, i32 6
  %34 = load i8, i8* %33, align 1, !tbaa !3
  %35 = xor i8 %34, %32
  store i8 %35, i8* %33, align 1, !tbaa !3
  %36 = getelementptr inbounds i8, i8* %1, i32 7
  %37 = load i8, i8* %36, align 1, !tbaa !3
  %38 = getelementptr inbounds i8, i8* %0, i32 7
  %39 = load i8, i8* %38, align 1, !tbaa !3
  %40 = xor i8 %39, %37
  store i8 %40, i8* %38, align 1, !tbaa !3
  %41 = getelementptr inbounds i8, i8* %1, i32 8
  %42 = load i8, i8* %41, align 1, !tbaa !3
  %43 = getelementptr inbounds i8, i8* %0, i32 8
  %44 = load i8, i8* %43, align 1, !tbaa !3
  %45 = xor i8 %44, %42
  store i8 %45, i8* %43, align 1, !tbaa !3
  %46 = getelementptr inbounds i8, i8* %1, i32 9
  %47 = load i8, i8* %46, align 1, !tbaa !3
  %48 = getelementptr inbounds i8, i8* %0, i32 9
  %49 = load i8, i8* %48, align 1, !tbaa !3
  %50 = xor i8 %49, %47
  store i8 %50, i8* %48, align 1, !tbaa !3
  %51 = getelementptr inbounds i8, i8* %1, i32 10
  %52 = load i8, i8* %51, align 1, !tbaa !3
  %53 = getelementptr inbounds i8, i8* %0, i32 10
  %54 = load i8, i8* %53, align 1, !tbaa !3
  %55 = xor i8 %54, %52
  store i8 %55, i8* %53, align 1, !tbaa !3
  %56 = getelementptr inbounds i8, i8* %1, i32 11
  %57 = load i8, i8* %56, align 1, !tbaa !3
  %58 = getelementptr inbounds i8, i8* %0, i32 11
  %59 = load i8, i8* %58, align 1, !tbaa !3
  %60 = xor i8 %59, %57
  store i8 %60, i8* %58, align 1, !tbaa !3
  %61 = getelementptr inbounds i8, i8* %1, i32 12
  %62 = load i8, i8* %61, align 1, !tbaa !3
  %63 = getelementptr inbounds i8, i8* %0, i32 12
  %64 = load i8, i8* %63, align 1, !tbaa !3
  %65 = xor i8 %64, %62
  store i8 %65, i8* %63, align 1, !tbaa !3
  %66 = getelementptr inbounds i8, i8* %1, i32 13
  %67 = load i8, i8* %66, align 1, !tbaa !3
  %68 = getelementptr inbounds i8, i8* %0, i32 13
  %69 = load i8, i8* %68, align 1, !tbaa !3
  %70 = xor i8 %69, %67
  store i8 %70, i8* %68, align 1, !tbaa !3
  %71 = getelementptr inbounds i8, i8* %1, i32 14
  %72 = load i8, i8* %71, align 1, !tbaa !3
  %73 = getelementptr inbounds i8, i8* %0, i32 14
  %74 = load i8, i8* %73, align 1, !tbaa !3
  %75 = xor i8 %74, %72
  store i8 %75, i8* %73, align 1, !tbaa !3
  %76 = getelementptr inbounds i8, i8* %1, i32 15
  %77 = load i8, i8* %76, align 1, !tbaa !3
  %78 = getelementptr inbounds i8, i8* %0, i32 15
  %79 = load i8, i8* %78, align 1, !tbaa !3
  %80 = xor i8 %79, %77
  store i8 %80, i8* %78, align 1, !tbaa !3
  ret void
}

; Function Attrs: argmemonly nofree nosync nounwind willreturn
declare void @llvm.lifetime.end.p0i8(i64 immarg, i8* nocapture) #1

; Function Attrs: nofree noinline nounwind
define dso_local void @top() local_unnamed_addr #0 {
  call void @aes256_encrypt_ecb(%struct.aes256_context* nonnull inttoptr (i32 789578240 to %struct.aes256_context*), i8* nonnull inttoptr (i32 789577728 to i8*), i8* nonnull inttoptr (i32 789577984 to i8*)) #6
  ret void
}

; Function Attrs: noinline norecurse nounwind readnone willreturn
define internal fastcc zeroext i8 @rj_xtime(i8 zeroext %0) unnamed_addr #4 {
  %2 = icmp sgt i8 %0, -1
  %3 = shl i8 %0, 1
  %4 = xor i8 %3, 27
  %5 = select i1 %2, i8 %3, i8 %4
  ret i8 %5
}

attributes #0 = { nofree noinline nounwind "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "min-legal-vector-width"="0" "no-builtins" "no-infs-fp-math"="false" "no-jump-tables"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="i686" "target-features"="+cx8,+x87" "tune-cpu"="generic" "unsafe-fp-math"="false" "use-soft-float"="false" }
attributes #1 = { argmemonly nofree nosync nounwind willreturn }
attributes #2 = { nofree noinline norecurse nounwind "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "min-legal-vector-width"="0" "no-builtins" "no-infs-fp-math"="false" "no-jump-tables"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="i686" "target-features"="+cx8,+x87" "tune-cpu"="generic" "unsafe-fp-math"="false" "use-soft-float"="false" }
attributes #3 = { nofree noinline norecurse nounwind willreturn "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "min-legal-vector-width"="0" "no-builtins" "no-infs-fp-math"="false" "no-jump-tables"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="i686" "target-features"="+cx8,+x87" "tune-cpu"="generic" "unsafe-fp-math"="false" "use-soft-float"="false" }
attributes #4 = { noinline norecurse nounwind readnone willreturn "disable-tail-calls"="false" "frame-pointer"="none" "less-precise-fpmad"="false" "min-legal-vector-width"="0" "no-builtins" "no-infs-fp-math"="false" "no-jump-tables"="false" "no-nans-fp-math"="false" "no-signed-zeros-fp-math"="false" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="i686" "target-features"="+cx8,+x87" "tune-cpu"="generic" "unsafe-fp-math"="false" "use-soft-float"="false" }
attributes #5 = { nounwind }
attributes #6 = { nobuiltin "no-builtins" }

!llvm.module.flags = !{!0, !1}
!llvm.ident = !{!2}

!0 = !{i32 1, !"NumRegisterParameters", i32 0}
!1 = !{i32 1, !"wchar_size", i32 4}
!2 = !{!"Ubuntu clang version 12.0.0-3ubuntu1~20.04.5"}
!3 = !{!4, !4, i64 0}
!4 = !{!"omnipotent char", !5, i64 0}
!5 = !{!"Simple C/C++ TBAA"}
!6 = distinct !{!6, !7, !8}
!7 = !{!"llvm.loop.mustprogress"}
!8 = !{!"llvm.loop.unroll.disable"}
!9 = distinct !{!9, !7, !8}
!10 = distinct !{!10, !7, !8}
!11 = distinct !{!11, !7, !8}
!12 = distinct !{!12, !7, !8}
