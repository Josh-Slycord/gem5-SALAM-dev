import re

# Read the file
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "r"
) as f:
    content = f.read()

# Pattern to find the dependency recording locations in findDynamicDeps
# After each addRuntimeDependency call, add a recordDependency call

# Find and replace in reservation queue section
old_pattern1 = """                // If dependency found, create two way link
                inst->addRuntimeDependency(queued_inst);
                queued_inst->addRuntimeUser(inst);
                dep_it = dep_uids.erase(dep_it);"""

new_pattern1 = """                // If dependency found, create two way link
                inst->addRuntimeDependency(queued_inst);
                queued_inst->addRuntimeUser(inst);
                // Record dependency for dataflow analysis (RAW dependency)
                owner->hw->hw_statistics->recordDependency(
                    queued_inst->getUID(), inst->getUID(),
                    true, false, false);  // is_raw=true
                dep_it = dep_uids.erase(dep_it);"""

content = content.replace(
    old_pattern1, new_pattern1, 1
)  # Only first occurrence

# For compute queue - this is also RAW
old_pattern2 = """        if (queue_iter != computeQueue.end()) {
            auto queued_inst = queue_iter->second;
            inst->addRuntimeDependency(queued_inst);
            queued_inst->addRuntimeUser(inst);
            dep_it = dep_uids.erase(dep_it);"""

new_pattern2 = """        if (queue_iter != computeQueue.end()) {
            auto queued_inst = queue_iter->second;
            inst->addRuntimeDependency(queued_inst);
            queued_inst->addRuntimeUser(inst);
            // Record dependency for dataflow analysis (RAW - waiting on compute result)
            owner->hw->hw_statistics->recordDependency(
                queued_inst->getUID(), inst->getUID(),
                true, false, false);  // is_raw=true
            dep_it = dep_uids.erase(dep_it);"""

content = content.replace(old_pattern2, new_pattern2, 1)

# For read queue - memory dependency
old_pattern3 = """        if (queue_iter != readQueue.end()) {
            auto queued_inst = queue_iter->second;
            inst->addRuntimeDependency(queued_inst);
            queued_inst->addRuntimeUser(inst);
            dep_it = dep_uids.erase(dep_it);"""

new_pattern3 = """        if (queue_iter != readQueue.end()) {
            auto queued_inst = queue_iter->second;
            inst->addRuntimeDependency(queued_inst);
            queued_inst->addRuntimeUser(inst);
            // Record memory dependency (waiting on load result - RAW)
            owner->hw->hw_statistics->recordDependency(
                queued_inst->getUID(), inst->getUID(),
                true, false, false);  // is_raw=true, memory load dependency
            dep_it = dep_uids.erase(dep_it);"""

content = content.replace(old_pattern3, new_pattern3, 1)

# For write queue - memory ordering dependency
old_pattern4 = """        if (queue_iter != writeQueue.end()) {
            auto queued_inst = queue_iter->second;
            inst->addRuntimeDependency(queued_inst);
            queued_inst->addRuntimeUser(inst);
            dep_it = dep_uids.erase(dep_it);"""

new_pattern4 = """        if (queue_iter != writeQueue.end()) {
            auto queued_inst = queue_iter->second;
            inst->addRuntimeDependency(queued_inst);
            queued_inst->addRuntimeUser(inst);
            // Record memory ordering dependency (WAR or WAW possible)
            // Conservative: mark as memory dependency via anti-dependency
            owner->hw->hw_statistics->recordDependency(
                queued_inst->getUID(), inst->getUID(),
                false, true, false);  // is_war=true, memory ordering
            dep_it = dep_uids.erase(dep_it);"""

content = content.replace(old_pattern4, new_pattern4, 1)

# Write the file back
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "w"
) as f:
    f.write(content)

print("Dependency tracking hooks added successfully")
