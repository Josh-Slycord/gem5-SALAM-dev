import re

# Read the file
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "r"
) as f:
    content = f.read()

# Add instruction completion tracking in compute queue
old_compute = """        if((queue_iter->second)->commit()) {
            (queue_iter->second)->reset();
            queue_iter = computeQueue.erase(queue_iter);
            hw_cycle_stats.compCommited++;"""

new_compute = """        if((queue_iter->second)->commit()) {
            // Track completed instruction for dataflow analysis
            auto completed_inst = queue_iter->second;
            owner->hw->hw_statistics->recordCriticalPathNode(
                completed_inst->getUID(),
                completed_inst->getOpode(),
                false,   // not a load
                false);  // not a store
            (queue_iter->second)->reset();
            queue_iter = computeQueue.erase(queue_iter);
            hw_cycle_stats.compCommited++;"""

content = content.replace(old_compute, new_compute, 1)

# Write the file back
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "w"
) as f:
    f.write(content)

print("Instruction completion tracking added successfully")
