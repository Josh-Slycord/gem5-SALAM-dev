#ifndef __HWMODEL_SIMULATOR_CONFIG_HH__
#define __HWMODEL_SIMULATOR_CONFIG_HH__

/**
 * @file
 * @brief Declares the SimulatorConfig SimObject for simulation environment
 * parameters.
 */

#include "params/SimulatorConfig.hh"
#include "sim/sim_object.hh"

using namespace gem5;

/**
 * @brief SimObject managing simulator-wide runtime configuration settings.
 */
class SimulatorConfig : public SimObject
{
    private:

    protected:

    public:
        SimulatorConfig();
        SimulatorConfig(const SimulatorConfigParams &params);
};

#endif //__HWMODEL_SIMULATOR_CONFIG_HH__
