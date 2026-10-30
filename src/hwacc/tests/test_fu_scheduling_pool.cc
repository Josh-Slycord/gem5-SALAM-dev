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
}
