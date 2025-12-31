# Comprehensive Test - Hardware Makefile

CLANG = clang

CFLAGS = -O1 -target arm-linux-gnueabihf -S -emit-llvm -fno-discard-value-names

SRC_C0 = source/cluster0
SRC_C1 = source/cluster1
SRC_C2 = source/cluster2
IR_C0 = ir/cluster0
IR_C1 = ir/cluster1
IR_C2 = ir/cluster2

all: dirs cluster0 cluster1 cluster2

dirs:
	mkdir -p $(IR_C0) $(IR_C1) $(IR_C2)

cluster0: $(IR_C0)/top.ll $(IR_C0)/integer_stress.ll $(IR_C0)/bitwise_stress.ll
$(IR_C0)/%.ll: $(SRC_C0)/%.c
	$(CLANG) $(CFLAGS) -o $@ $<

cluster1: $(IR_C1)/top.ll $(IR_C1)/float_stress.ll
$(IR_C1)/%.ll: $(SRC_C1)/%.c
	$(CLANG) $(CFLAGS) -o $@ $<

cluster2: $(IR_C2)/top.ll $(IR_C2)/double_stress.ll $(IR_C2)/stream_producer.ll $(IR_C2)/stream_consumer.ll
$(IR_C2)/%.ll: $(SRC_C2)/%.c
	$(CLANG) $(CFLAGS) -o $@ $<

clean:
	rm -rf ir/*/*.ll

.PHONY: all dirs cluster0 cluster1 cluster2 clean
