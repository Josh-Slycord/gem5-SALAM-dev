import re

# Read the file
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "r"
) as f:
    content = f.read()

# Fix processQueues null checks - wrap all hw_statistics accesses
# Pattern 1: use_cycle_tracking check
old_code1 = """    if (owner->hw->hw_statistics->use_cycle_tracking()) {"""
new_code1 = """    if (owner->hw && owner->hw->hw_statistics && owner->hw->hw_statistics->use_cycle_tracking()) {"""
content = content.replace(old_code1, new_code1)

# Pattern 2: recordParallelism and other inline calls
old_code2 = (
    """        owner->hw->hw_statistics->recordParallelism(ready_count,"""
)
new_code2 = """        if (owner->hw && owner->hw->hw_statistics) owner->hw->hw_statistics->recordParallelism(ready_count,"""
content = content.replace(old_code2, new_code2)

# Pattern 3: publishPipelineSnapshot
old_code3 = """        owner->hw->hw_statistics->publishPipelineSnapshot("""
new_code3 = """        if (owner->hw && owner->hw->hw_statistics) owner->hw->hw_statistics->publishPipelineSnapshot("""
content = content.replace(old_code3, new_code3)

# Pattern 4: recordCriticalPathNode in compute commit
old_code4 = """            owner->hw->hw_statistics->recordCriticalPathNode(
                completed_inst->getUID(),
                completed_inst->getOpode(),
                false,   // not a load
                false);  // not a store"""
new_code4 = """            if (owner->hw && owner->hw->hw_statistics) {
                owner->hw->hw_statistics->recordCriticalPathNode(
                    completed_inst->getUID(),
                    completed_inst->getOpode(),
                    false,   // not a load
                    false);  // not a store
            }"""
content = content.replace(old_code4, new_code4)

# Pattern 5: recordStallCause for FU contention
old_code5 = """            owner->hw->hw_statistics->recordStallCause(StallCause::FU_CONTENTION);"""
new_code5 = """            if (owner->hw && owner->hw->hw_statistics) owner->hw->hw_statistics->recordStallCause(StallCause::FU_CONTENTION);"""
content = content.replace(old_code5, new_code5)

# Pattern 6: recordStallCause for RAW hazard
old_code6 = """                            owner->hw->hw_statistics->recordStallCause(StallCause::RAW_HAZARD);"""
new_code6 = """                            if (owner->hw && owner->hw->hw_statistics) owner->hw->hw_statistics->recordStallCause(StallCause::RAW_HAZARD);"""
content = content.replace(old_code6, new_code6)

# Pattern 7: updateHWStatsCycleStart
old_code7 = """        owner->hw->hw_statistics->updateHWStatsCycleStart();"""
new_code7 = """        if (owner->hw && owner->hw->hw_statistics) owner->hw->hw_statistics->updateHWStatsCycleStart();"""
content = content.replace(old_code7, new_code7)

# Pattern 8: updateHWStatsCycleEnd
old_code8 = """        owner->hw->hw_statistics->updateHWStatsCycleEnd(owner->cycle);"""
new_code8 = """        if (owner->hw && owner->hw->hw_statistics) owner->hw->hw_statistics->updateHWStatsCycleEnd(owner->cycle);"""
content = content.replace(old_code8, new_code8)

# Pattern 9: recordDependency calls (there are 4)
old_code9 = """                owner->hw->hw_statistics->recordDependency("""
new_code9 = """                if (owner->hw && owner->hw->hw_statistics) owner->hw->hw_statistics->recordDependency("""
content = content.replace(old_code9, new_code9)

old_code10 = """            owner->hw->hw_statistics->recordDependency("""
new_code10 = """            if (owner->hw && owner->hw->hw_statistics) owner->hw->hw_statistics->recordDependency("""
content = content.replace(old_code10, new_code10)

# Pattern 11: recordCriticalPathNode in readCommit
old_code11 = """            owner->hw->hw_statistics->recordCriticalPathNode(
                load_inst->getUID(),
                load_inst->getOpode(),
                true,    // is a load
                false);  // not a store"""
new_code11 = """            if (owner->hw && owner->hw->hw_statistics) {
                owner->hw->hw_statistics->recordCriticalPathNode(
                    load_inst->getUID(),
                    load_inst->getOpode(),
                    true,    // is a load
                    false);  // not a store
            }"""
content = content.replace(old_code11, new_code11)

# Pattern 12: recordCriticalPathNode in writeCommit
old_code12 = """            owner->hw->hw_statistics->recordCriticalPathNode(
                store_inst->getUID(),
                store_inst->getOpode(),
                false,   // not a load
                true);   // is a store"""
new_code12 = """            if (owner->hw && owner->hw->hw_statistics) {
                owner->hw->hw_statistics->recordCriticalPathNode(
                    store_inst->getUID(),
                    store_inst->getOpode(),
                    false,   // not a load
                    true);   // is a store
            }"""
content = content.replace(old_code12, new_code12)

# Write the file back
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "w"
) as f:
    f.write(content)

print("ProcessQueues null checks added successfully")
