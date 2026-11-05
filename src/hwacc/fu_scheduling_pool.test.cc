// Adapted from preserved Gemini commit b9c798893d53e8565943aed6678a151434d4a5f1,
// src/hwacc/fu_scheduling_pool.test.cc. Local changes add simultaneous leases
// on the same unlimited FU. The original institutional attribution is
// unverified; file provenance and licensing remain open under readiness U19.

#include <gtest/gtest.h>

#include <cstdint>
#include <stdexcept>

#include "hwacc/HWModeling/generated/functionalunits/base.hh"
#include "hwacc/HWModeling/generated/instructions/base.hh"
#include "hwacc/fu_scheduling_pool.hh"
#include "hwacc/workbench_statistics.hh"

namespace
{

struct MockInstParams
{
    uint32_t functional_unit = 3;
    uint32_t functional_unit_limit = 2;
    uint32_t opcode_num = 13;
    uint32_t runtime_cycles = 4;
};

struct MockFuParams
{
    std::string alias = "integer_adder";
    uint32_t stages = 1;
    uint32_t cycles = 1;
    uint32_t enum_value = 3;
    std::string int_size = "32";
    std::string int_sign = "signed";
    bool int_apmode = false;
    std::string fp_size = "32";
    std::string fp_sign = "signed";
    bool fp_apmode = false;
    std::string ptr_size = "32";
    std::string ptr_sign = "unsigned";
    bool ptr_apmode = false;
    uint32_t limit = 2;
    std::string power_units = "mW";
    std::string energy_units = "pJ";
    std::string time_units = "ns";
    std::string area_units = "um^2";
    uint32_t fu_latency = 1;
    double internal_power = 0.25;
    double switch_power = 0.50;
    double dynamic_power = 0.75;
    double dynamic_energy = 1.50;
    double leakage_power = 0.125;
    double area = 42.0;
    double path_delay = 1.25;
};

} // anonymous namespace

TEST(FUSchedulingPoolTest, EnforcesCapacityGrantsDenialsAndReleases)
{
    FUSchedulingPool pool(16);
    pool.configure(1, "integer_adder", 1);
    pool.configure(2, "float_multiplier", 0); // 0 = unlimited

    int inst_a = 1;
    int inst_b = 2;
    int inst_c = 3;
    int inst_d = 4;

    EXPECT_TRUE(pool.acquire(&inst_a, 10, 13, 1, 0, 0));
    EXPECT_EQ(pool.unit(1).outstanding, 1u);
    EXPECT_FALSE(pool.acquire(&inst_b, 11, 13, 1, 0, 0));
    EXPECT_EQ(pool.unit(1).denials, 1u);

    // Unlimited FU accepts concurrent leases
    EXPECT_TRUE(pool.acquire(&inst_c, 12, 16, 2, 0, 0));
    EXPECT_TRUE(pool.acquire(&inst_d, 13, 16, 2, 0, 0));
    EXPECT_EQ(pool.unit(2).outstanding, 2u);
    EXPECT_EQ(pool.outstanding(), 3u);

    EXPECT_EQ(pool.release(&inst_a, 1, 1000), 1u);
    EXPECT_EQ(pool.unit(1).outstanding, 0u);
    EXPECT_TRUE(pool.acquire(&inst_b, 11, 13, 1, 1, 1000));
    EXPECT_EQ(pool.release(&inst_b, 2, 2000), 1u);
    EXPECT_EQ(pool.release(&inst_c, 2, 2000), 2u);
    EXPECT_EQ(pool.release(&inst_d, 2, 2000), 2u);
    EXPECT_EQ(pool.outstanding(), 0u);
}

TEST(FUSchedulingPoolTest, RejectsDuplicateOrUnmatchedLeases)
{
    FUSchedulingPool pool(8);
    pool.configure(1, "integer_adder", 2);
    int inst = 1;

    EXPECT_TRUE(pool.acquire(&inst, 1, 13, 1, 0, 0));
    EXPECT_THROW(pool.acquire(&inst, 1, 13, 1, 0, 0), std::logic_error);
    EXPECT_EQ(pool.release(&inst, 1, 1000), 1u);
    EXPECT_THROW(pool.release(&inst, 2, 2000), std::logic_error);
}

TEST(HWModelingBaseTest, InitializesInstConfigAndFunctionalUnitFromParams)
{
    MockInstParams inst_params;
    InstConfigBase inst_cfg(inst_params);
    EXPECT_EQ(inst_cfg.get_functional_unit(), 3u);
    EXPECT_EQ(inst_cfg.get_functional_unit_limit(), 2u);
    EXPECT_EQ(inst_cfg.get_opcode_num(), 13u);
    EXPECT_EQ(inst_cfg.get_runtime_cycles(), 4u);

    MockFuParams fu_params;
    FunctionalUnitBase fu_cfg(fu_params);
    EXPECT_EQ(fu_cfg.get_alias(), "integer_adder");
    EXPECT_EQ(fu_cfg.get_enum_value(), 3u);
    EXPECT_EQ(fu_cfg.get_limit(), 2u);
    EXPECT_DOUBLE_EQ(fu_cfg.get_dynamic_power(), 0.75);
    EXPECT_DOUBLE_EQ(fu_cfg.get_leakage_power(), 0.125);
    EXPECT_DOUBLE_EQ(fu_cfg.get_area(), 42.0);
    EXPECT_TRUE(fu_cfg.is_available());
    fu_cfg.use_functional_unit();
    fu_cfg.use_functional_unit();
    EXPECT_FALSE(fu_cfg.is_available());
    fu_cfg.clear_functional_unit();
    EXPECT_TRUE(fu_cfg.is_available());
}

TEST(WorkbenchStatisticsGTest, TracksMemoryRequestsAndQueueSamples)
{
    gem5::salam::WorkbenchStatistics stats;
    ASSERT_TRUE(stats.begin("system.gemm_clstr.gemm", 0, 10, 1000000000000ULL));
    stats.memoryStarted(1, false, 64, 0);
    stats.memoryCompleted(1, 20);
    stats.sampleQueues(2, 1, 0, 1, 1);
    stats.end(30);
    EXPECT_TRUE(stats.valid());
    EXPECT_EQ(stats.readTotals().started, 1u);
    EXPECT_EQ(stats.readTotals().completed, 1u);
    EXPECT_EQ(stats.readTotals().completedBytes, 64u);
}
