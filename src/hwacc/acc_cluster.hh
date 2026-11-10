#ifndef __HWACC_ACC_CLUSTER_HH__
#define __HWACC_ACC_CLUSTER_HH__

/**
 * @file acc_cluster.hh
 * @brief Platform container representing an accelerator cluster in gem5-SALAM.
 *
 * AccCluster serves as the hierarchical SimObject container bundling
 * compute units, local scratchpad memories, register banks, and DMA
 * controllers
 * into a coherent accelerator subsystem within a full-system platform.
 */
//------------------------------------------//
#include "hwacc/LLVMRead/src/debug_flags.hh"
#include "dev/platform.hh"
#include "params/AccCluster.hh"
//------------------------------------------//
using namespace gem5;

class BaseGic;
class IdeController;
class System;

/**
 * @class AccCluster
 * @brief Platform object encapsulating an accelerator cluster.
 *
 * Implements Platform interfaces to bind the cluster to system interrupt
 * controllers (GIC) and console interfaces within full-system simulation.
 */
class AccCluster : public Platform
{
  public:
    /** Pointer to the system */
    gem5::System *system;

    BaseGic *gic;

  public:
    // typedef AccClusterParams Params;
    // const Params *
    // params() const {
    //     return dynamic_cast<const Params *>(_params);
    // }
    PARAMS(AccCluster);
    /**
     * @brief Construct a new AccCluster platform object.
     * @param p SimObject configuration parameters.
     */
    AccCluster(const AccClusterParams &p);

    /**
     * @brief Bind generic interrupt controller (GIC) to the accelerator
     * cluster.
     * @param _gic Pointer to BaseGic instance.
     */
    void setGic(BaseGic *_gic) { gic = _gic; }

  public: // Public Platform interfaces
    /**
     * @brief Post console interrupt (Platform interface stub).
     */
    void postConsoleInt() override;
    /**
     * @brief Clear console interrupt (Platform interface stub).
     */
    void clearConsoleInt() override;
};

#endif
