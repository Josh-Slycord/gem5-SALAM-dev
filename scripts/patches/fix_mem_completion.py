import re

# Read the file
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "r"
) as f:
    content = f.read()

# Add load completion tracking in readCommit
old_read = """            load_inst->compute();
            if (dbg) DPRINTFS(Runtime, owner,  "Local Read Commit\\n");
            load_inst->commit();
            readQueue.erase(queue_iter);
            readQueueMap.erase(map_iter);"""

new_read = """            load_inst->compute();
            if (dbg) DPRINTFS(Runtime, owner,  "Local Read Commit\\n");
            load_inst->commit();
            // Track completed load for dataflow analysis
            owner->hw->hw_statistics->recordCriticalPathNode(
                load_inst->getUID(),
                load_inst->getOpode(),
                true,    // is a load
                false);  // not a store
            readQueue.erase(queue_iter);
            readQueueMap.erase(map_iter);"""

content = content.replace(old_read, new_read, 1)

# Add store completion tracking in writeCommit
old_write = """        auto queue_iter = writeQueue.find(map_iter->second);
        if (queue_iter != writeQueue.end()) {
            queue_iter->second->commit();
            Addr addressWritten = map_iter->first->getAddress();"""

new_write = """        auto queue_iter = writeQueue.find(map_iter->second);
        if (queue_iter != writeQueue.end()) {
            auto store_inst = queue_iter->second;
            store_inst->commit();
            // Track completed store for dataflow analysis
            owner->hw->hw_statistics->recordCriticalPathNode(
                store_inst->getUID(),
                store_inst->getOpode(),
                false,   // not a load
                true);   // is a store
            Addr addressWritten = map_iter->first->getAddress();"""

content = content.replace(old_write, new_write, 1)

# Write the file back
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/llvm_interface.cc", "w"
) as f:
    f.write(content)

print("Memory completion tracking added successfully")
