// Standalone collector tests: no gem5, LLVM, historical agents, or simulator run.
#include "hwacc/workbench_statistics.hh"
#include <cassert>
#include <iostream>
#include <limits>

using gem5::salam::WorkbenchStatistics;

int main()
{
    WorkbenchStatistics stats;
    assert(stats.begin("system.gemm_clstr.gemm", 0, 10, 1000000000000ULL));
    stats.memoryStarted(1, false, 4, 0); // Tick zero is a real timestamp.
    stats.memoryStarted(2, true, 8, 3);
    stats.memoryCompleted(1, 10);
    stats.memoryCompleted(2, 23);
    // Reusing an opaque address after completion is another logical request.
    stats.memoryStarted(1, false, 12, 25);
    stats.memoryCompleted(1, 30);
    stats.recordCommit(WorkbenchStatistics::Commit::MemoryRead);
    stats.recordCommit(WorkbenchStatistics::Commit::MemoryRead);
    stats.recordCommit(WorkbenchStatistics::Commit::MemoryWrite);
    stats.recordCommit(WorkbenchStatistics::Commit::QueuedCompute);
    stats.sampleQueues(4, 2, 1, 3, 2);
    stats.sampleQueues(1, 0, 0, 2, 1);
    stats.sampleQueues(0, 0, 0, 0, 1);
    stats.end(35);
    assert(stats.valid());
    assert(stats.readTotals().started == 2 && stats.readTotals().completed == 2);
    assert(stats.readTotals().startedBytes == 16 && stats.readTotals().completedBytes == 16);
    assert(stats.readTotals().latencySum == 15 && stats.readTotals().latencyMin == 5);
    assert(stats.readTotals().latencyMax == 10 && stats.writeTotals().latencySum == 20);
    assert(stats.sampleCount() == 3 && stats.reservationTotals().sum == 5);
    assert(stats.reservationTotals().max == 4);
    assert(stats.outputFilename() == "system.gemm_clstr.gemm.invocation-1.json");
    const std::string first = stats.toJSON();
    assert(first.find("\"selected_commits_total\":4") != std::string::npos);

    // Every invocation resets aggregates while preserving its unique identity.
    assert(stats.begin("system.gemm_clstr.gemm", 40, 10, 1000000000000ULL));
    stats.sampleQueues(0, 0, 0, 0, 0);
    stats.end(40);
    assert(stats.valid() && stats.invocationId() == 2);
    assert(stats.readTotals().completed == 0 && stats.reservationTotals().sum == 0);
    assert(stats.toJSON().find("\"count\":0,\"sum\":0,\"min\":null,\"max\":null") != std::string::npos);

    WorkbenchStatistics pending;
    pending.begin("pending", 10, 1, 1000);
    pending.memoryStarted(3, false, 16, 11);
    pending.end(20);
    assert(!pending.valid());
    assert(pending.toJSON().find("\"pending_requests\":1") != std::string::npos);

    WorkbenchStatistics duplicate;
    duplicate.begin("duplicates", 0, 1, 1000);
    duplicate.memoryStarted(4, false, 8, 0);
    duplicate.memoryStarted(4, false, 8, 1);
    duplicate.memoryCompleted(4, 10);
    duplicate.memoryCompleted(4, 11);
    duplicate.end(12);
    assert(!duplicate.valid() && duplicate.invalidEventCount() == 2);
    assert(duplicate.readTotals().started == 1 && duplicate.readTotals().completed == 1);

    WorkbenchStatistics backwards;
    backwards.begin("backwards", 10, 1, 1000);
    backwards.memoryStarted(1, false, 4, 9);
    backwards.memoryStarted(2, true, 4, 12);
    backwards.memoryCompleted(2, 11);
    backwards.end(15);
    assert(!backwards.valid() && backwards.invalidEventCount() == 2);

    WorkbenchStatistics overlap;
    overlap.begin("overlap", 0, 1, 1000);
    assert(!overlap.begin("would-erase-evidence", 1, 1, 1000));
    overlap.end(2);
    assert(!overlap.valid() && overlap.invocationId() == 1);

    WorkbenchStatistics overflow;
    overflow.begin("overflow", 0, 1, 1000);
    overflow.sampleQueues(std::numeric_limits<uint64_t>::max(), 0, 0, 0, 1);
    overflow.sampleQueues(1, 0, 0, 0, 1);
    overflow.end(1);
    assert(!overflow.valid() && overflow.invalidEventCount() == 1);

    WorkbenchStatistics badClock;
    badClock.begin("bad-clock", 0, 0, 0);
    badClock.end(1);
    assert(!badClock.valid());
    assert(WorkbenchStatistics::jsonString("a\"b\\c\n\t\x01") == "\"a\\\"b\\\\c\\n\\t\\u0001\"");
    assert(WorkbenchStatistics::fileComponent("../unsafe/name").find('/') == std::string::npos);
    assert(WorkbenchStatistics::fileComponent("..") != "..");
    assert(WorkbenchStatistics::fileComponent("system.gemm_clstr.top") == "system.gemm_clstr.top");

    // Emit one independently parseable witness for Python JSON/schema tests.
    std::cout << first;
    return 0;
}
