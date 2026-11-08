#ifndef __HWMODEL_HW_MODEL_HH__
#define __HWMODEL_HW_MODEL_HH__

/**
 * @file
 * @brief Aggregates hardware modeling components for SALAM compute units.
 *
 * HWInterface groups cycle counts, functional unit pools, instruction configs,
 * power models, and runtime statistics into a unified SimObject container.
 */

#include "params/HWInterface.hh"
#include "sim/sim_object.hh"

#include "../../common/src/macros.hh"

#include "cycle_counts.hh"
#include "functional_units.hh"
#include "instruction_config.hh"
#include "salam_power_model.hh"
#include "cacti_wrapper.hh"
#include "hw_statistics.hh"
#include "simulator_config.hh"
#include "opcodes.hh"
#include <iostream>
#include <cstdlib>
#include <vector>

using namespace gem5;

/**
 * @brief SimObject managing hardware configuration, timing, and resources.
 */
class HWInterface : public SimObject 
{
    friend class LLVMInterface;
    private:
    protected:
    public:
        CycleCounts *cycle_counts;
        FunctionalUnits *functional_units;
        HWStatistics *hw_statistics;
        InstConfig *inst_config;
        InstOpCodes *opcodes;
        SALAMPowerModel *salam_power_model;
        SimulatorConfig *simulator_config;

        HWInterface();
        HWInterface(const HWInterfaceParams &params);

        /**
         * @brief Checks if a functional unit of the given type is available.
         *
         * @param functional_unit FU type identifier.
         * @return True if available.
         */
        bool availableFunctionalUnit(uint64_t functional_unit);

        /**
         * @brief Releases a previously allocated functional unit.
         *
         * @param functional_unit FU type identifier.
         */
        void clearFunctionalUnit(uint64_t functional_unit);
        

};

// TODO: Figure out a better way to link floating point instructions to the correct precision function unit, currently assuming everything is single precision since we are building for 32 bit

#endif //__HWMODEL_HW_MODEL_HH__
