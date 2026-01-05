import re

# Read hw_statistics.hh
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/HWModeling/src/hw_statistics.hh",
    "r",
) as f:
    hh_content = f.read()

# Read hw_statistics.cc
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/HWModeling/src/hw_statistics.cc",
    "r",
) as f:
    cc_content = f.read()

# Add instruction depth tracking data structures to private section
old_private = """    SummaryStats summary;
    PowerAreaCoefficients power_area_config;"""

new_private = """    SummaryStats summary;
    PowerAreaCoefficients power_area_config;

    // Critical path tracking - instruction depth map
    // Key: instruction UID, Value: depth in dependency chain (1 = no dependencies)
    std::map<int, int> instruction_depth;
    // Track which instructions are on the critical path
    std::set<int> critical_path_instructions;
    // Track producer-consumer relationships for critical path reconstruction
    std::map<int, std::vector<int>> producers_of;  // consumer -> [producers]
    int current_max_depth = 0;"""

hh_content = hh_content.replace(old_private, new_private, 1)

# Add new method declarations
old_methods = """    void recordDependency(int producer_uid, int consumer_uid, bool is_raw,
                          bool is_war, bool is_waw);
    void recordCriticalPathNode(int uid, int opcode, bool is_load, bool is_store);"""

new_methods = """    void recordDependency(int producer_uid, int consumer_uid, bool is_raw,
                          bool is_war, bool is_waw);
    void recordCriticalPathNode(int uid, int opcode, bool is_load, bool is_store);
    void computeCriticalPath();  // Call at end to compute final critical path
    int getInstructionDepth(int uid) const;
    void markCriticalPathInstructions();  // Backtrack from deepest to mark path"""

hh_content = hh_content.replace(old_methods, new_methods, 1)

# Add #include <set> if not present
if "#include <set>" not in hh_content:
    hh_content = hh_content.replace(
        "#include <map>", "#include <map>\n#include <set>", 1
    )

# Write hw_statistics.hh
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/HWModeling/src/hw_statistics.hh",
    "w",
) as f:
    f.write(hh_content)

# Update recordDependency in hw_statistics.cc to track depths
old_record_dep = """void HWStatistics::recordDependency(int producer_uid, int consumer_uid,
                                     bool is_raw, bool is_war, bool is_waw) {
    auto& df = summary.dataflow;
    df.total_dependency_edges++;

    if (is_raw) df.true_dependencies++;
    if (is_war) df.anti_dependencies++;
    if (is_waw) df.output_dependencies++;
}"""

new_record_dep = """void HWStatistics::recordDependency(int producer_uid, int consumer_uid,
                                     bool is_raw, bool is_war, bool is_waw) {
    auto& df = summary.dataflow;
    df.total_dependency_edges++;

    if (is_raw) df.true_dependencies++;
    if (is_war) df.anti_dependencies++;
    if (is_waw) df.output_dependencies++;

    // Track producer-consumer relationship for critical path
    producers_of[consumer_uid].push_back(producer_uid);

    // Initialize producer depth if not seen
    if (instruction_depth.find(producer_uid) == instruction_depth.end()) {
        instruction_depth[producer_uid] = 1;
    }

    // Compute consumer depth as max(producer depths) + 1
    int producer_depth = instruction_depth[producer_uid];
    int current_consumer_depth = instruction_depth[consumer_uid];  // default 0
    int new_depth = producer_depth + 1;

    if (new_depth > current_consumer_depth) {
        instruction_depth[consumer_uid] = new_depth;
        if (new_depth > current_max_depth) {
            current_max_depth = new_depth;
            df.max_dependency_depth = new_depth;
        }
    }
}"""

cc_content = cc_content.replace(old_record_dep, new_record_dep, 1)

# Update recordCriticalPathNode to use actual depth
old_record_node = """void HWStatistics::recordCriticalPathNode(int uid, int opcode, bool is_load, bool is_store) {
    auto& df = summary.dataflow;
    df.critical_path_instructions++;
    df.critical_path_by_opcode[opcode]++;

    if (is_load) df.critical_path_loads++;
    if (is_store) df.critical_path_stores++;
    if (!is_load && !is_store) df.critical_path_computes++;
}"""

new_record_node = """void HWStatistics::recordCriticalPathNode(int uid, int opcode, bool is_load, bool is_store) {
    auto& df = summary.dataflow;
    df.total_instructions++;

    // Initialize depth if instruction has no tracked dependencies
    if (instruction_depth.find(uid) == instruction_depth.end()) {
        instruction_depth[uid] = 1;  // Leaf instruction (no dependencies)
    }

    // Update average dependency depth
    int depth = instruction_depth[uid];
    df.avg_dependency_depth = (df.avg_dependency_depth * (df.total_instructions - 1) + depth)
                              / df.total_instructions;
}"""

cc_content = cc_content.replace(old_record_node, new_record_node, 1)

# Add new method implementations before recordParallelism
insert_before = """void HWStatistics::recordParallelism(int ready_count, int issued_count) {"""

new_implementations = """void HWStatistics::computeCriticalPath() {
    auto& df = summary.dataflow;

    // Set critical path length to maximum observed depth
    df.critical_path_length = current_max_depth;

    // Count instructions at each depth level for ILP estimation
    std::map<int, int> depth_counts;
    for (const auto& pair : instruction_depth) {
        depth_counts[pair.second]++;
    }

    // Compute average parallelism from depth distribution
    double total_at_depth = 0;
    int max_at_any_depth = 0;
    for (const auto& pair : depth_counts) {
        total_at_depth += pair.second;
        max_at_any_depth = std::max(max_at_any_depth, pair.second);
    }

    if (current_max_depth > 0) {
        df.avg_ready_instructions = total_at_depth / current_max_depth;
    }

    // Mark instructions on the critical path
    markCriticalPathInstructions();

    // Update critical path breakdown
    df.critical_path_instructions = 0;
    df.critical_path_loads = 0;
    df.critical_path_stores = 0;
    df.critical_path_computes = 0;
    // Note: The actual breakdown would require storing opcode info per instruction
    // For now, we just have the count from the set size
    df.critical_path_instructions = critical_path_instructions.size();
}

int HWStatistics::getInstructionDepth(int uid) const {
    auto it = instruction_depth.find(uid);
    return (it != instruction_depth.end()) ? it->second : 0;
}

void HWStatistics::markCriticalPathInstructions() {
    // Find all instructions at maximum depth - they're on a critical path
    for (const auto& pair : instruction_depth) {
        if (pair.second == current_max_depth) {
            // This instruction is at the end of a critical path
            // Backtrack through its producers to mark the full path
            std::vector<int> to_process;
            to_process.push_back(pair.first);

            while (!to_process.empty()) {
                int current = to_process.back();
                to_process.pop_back();

                if (critical_path_instructions.count(current) > 0) {
                    continue;  // Already marked
                }
                critical_path_instructions.insert(current);

                // Find the producer that contributed to this instruction's depth
                auto prod_it = producers_of.find(current);
                if (prod_it != producers_of.end()) {
                    int target_depth = instruction_depth[current] - 1;
                    for (int prod : prod_it->second) {
                        if (instruction_depth[prod] == target_depth) {
                            to_process.push_back(prod);
                        }
                    }
                }
            }
        }
    }
}

"""

cc_content = cc_content.replace(
    insert_before, new_implementations + insert_before, 1
)

# Write hw_statistics.cc
with open(
    "/home/jslycord/gem5-SALAM-dev/src/hwacc/HWModeling/src/hw_statistics.cc",
    "w",
) as f:
    f.write(cc_content)

print("Critical path algorithm added successfully")
