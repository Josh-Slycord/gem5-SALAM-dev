#include "../fu_scheduling_pool.hh"
#include <cassert>
#include <stdexcept>
#include <string>

int main()
{
    FUSchedulingPool pool;
    pool.configure(1, "integer_adder", 1);
    pool.configure(2, "integer_multiplier", 2);
    pool.configure(3, "unlimited", 0);
    int a = 0, b = 0, c = 0, d = 0;
    assert(pool.acquire(&a, 7, 13, 1, 1, 100));
    assert(!pool.acquire(&b, 7, 13, 1, 1, 100));
    assert(pool.unit(1).outstanding == 1);
    assert(pool.acquire(&c, 8, 17, 2, 1, 100));
    assert(pool.acquire(&d, 9, 17, 2, 1, 100));
    assert(pool.outstanding() == 3);
    pool.release(&a, 2, 200);
    assert(pool.acquire(&b, 7, 13, 1, 2, 200));
    pool.release(&b, 3, 300);
    pool.release(&c, 3, 300);
    pool.release(&d, 3, 300);
    assert(pool.outstanding() == 0);
    assert(pool.unit(1).attempts == 3 && pool.unit(1).denials == 1);
    assert(pool.unit(1).grants == 2 && pool.unit(1).releases == 2);
    assert(pool.unit(1).peak == 1);
    assert(pool.unit(2).peak == 2);
    assert(pool.trace().size() == 9);
    assert(pool.trace()[0].event == "grant");
    assert(pool.trace()[1].event == "deny");
    assert(pool.trace()[1].lease_id == 0);
    assert(pool.trace()[0].lease_id != pool.trace()[5].lease_id);
    assert(pool.trace()[0].uid == pool.trace()[5].uid);
    const std::string json = pool.toJSON("accel", 3, 200);
    assert(json.find("\"peak\":3") != std::string::npos);
    assert(json.find("\"outstanding\":0") != std::string::npos);
    assert(json.find("\"trace_truncated\":false") != std::string::npos);
    bool doubleRelease = false;
    try { pool.release(&a, 4, 400); }
    catch (const std::logic_error &) { doubleRelease = true; }
    assert(doubleRelease);
    FUSchedulingPool unlimited;
    unlimited.configure(3, "unlimited", 0);
    assert(unlimited.acquire(&a, 1, 1, 3, 1, 1));
    assert(unlimited.acquire(&b, 2, 1, 3, 1, 1));
    assert(unlimited.unit(3).peak == 2);
    unlimited.release(&a, 2, 2);
    unlimited.release(&b, 2, 2);

    // A trace budget never changes admission, occupancy or completion counters.
    FUSchedulingPool small(2), complete(3);
    for (FUSchedulingPool *bounded : {&small, &complete}) {
        bounded->configure(1, "bounded", 1);
        assert(bounded->acquire(&a, 1, 13, 1, 1, 1));
        assert(!bounded->acquire(&b, 2, 13, 1, 1, 1));
        bounded->release(&a, 2, 2);
        assert(bounded->outstanding() == 0);
        assert(bounded->unit(1).attempts == 2);
        assert(bounded->unit(1).grants == 1);
        assert(bounded->unit(1).denials == 1);
        assert(bounded->unit(1).releases == 1);
        assert(bounded->unit(1).peak == 1);
    }
    assert(small.trace().size() == 2 && small.traceTruncated());
    assert(complete.trace().size() == 3 && !complete.traceTruncated());
    assert(complete.toJSON("complete", 2, 2).find("\"trace_event_limit\":3")
           != std::string::npos);

    // The first event beyond a cap truncates; filling it exactly does not.
    FUSchedulingPool exact(2);
    exact.configure(1, "exact", 0);
    assert(exact.acquire(&a, 1, 13, 1, 1, 1));
    exact.release(&a, 2, 2);
    assert(exact.trace().size() == 2 && !exact.traceTruncated());
    assert(exact.acquire(&a, 2, 13, 1, 3, 3));
    exact.release(&a, 4, 4);
    assert(exact.trace().size() == 2 && exact.traceTruncated());
    assert(exact.unit(1).grants == 2 && exact.unit(1).releases == 2);

    FUSchedulingPool legacy, large(1048576);
    assert(legacy.traceEventLimit() == 262144);
    assert(large.traceEventLimit() == 1048576);
    legacy.configure(1, "legacy", 0);
    large.configure(1, "large", 0);
    for (uint64_t i = 0; i < 140000; ++i) {
        for (FUSchedulingPool *bounded : {&legacy, &large}) {
            assert(bounded->acquire(&a, i, 13, 1, 2 * i, 2 * i));
            bounded->release(&a, 2 * i + 1, 2 * i + 1);
        }
    }
    assert(legacy.trace().size() == 262144 && legacy.traceTruncated());
    assert(large.trace().size() == 280000 && !large.traceTruncated());
    assert(legacy.unit(1).grants == large.unit(1).grants);
    assert(legacy.unit(1).releases == large.unit(1).releases);
    assert(legacy.outstanding() == 0 && large.outstanding() == 0);
    large = FUSchedulingPool(large.traceEventLimit());
    assert(large.traceEventLimit() == 1048576);
    assert(large.trace().empty() && !large.traceTruncated());
    assert(large.outstanding() == 0 && large.units().empty());

    FUSchedulingPool maximum(FUSchedulingPool::MaxTraceEventLimit);
    assert(maximum.traceEventLimit() == 4194304);
    for (uint32_t invalid : {0U, 4194305U, 0xffffffffU}) {
        bool rejected = false;
        try { FUSchedulingPool invalid_pool(invalid); }
        catch (const std::invalid_argument &) { rejected = true; }
        assert(rejected);
    }
}
