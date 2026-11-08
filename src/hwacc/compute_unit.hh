#ifndef __HWACC_COMPUTE_UNIT_HH__
#define __HWACC_COMPUTE_UNIT_HH__

/**
 * @file compute_unit.hh
 * @brief Base class definition for accelerator compute units in gem5-SALAM.
 *
 * ComputeUnit provides the common execution interface, clocking domain,
 * communication linkages, and performance monitoring hooks for all SALAM
 * hardware acceleration compute engines (such as LLVMInterface).
 */
//------------------------------------------//
#include "params/ComputeUnit.hh"
#include "sim/clocked_object.hh"
#include "hwacc/workbench_statistics.hh"
#include "hwacc/comm_interface.hh"
#include "hwacc/LLVMRead/src/mem_request.hh"
#include "hwacc/LLVMRead/src/debug_flags.hh"
#include "hwacc/HWModeling/src/hw_interface.hh" 
//------------------------------------------//

/**
 * @class ComputeUnit
 * @brief Abstract base class representing a computational engine in SALAM.
 *
 * Inherits from gem5::ClockedObject to anchor execution within an accelerator
 * clock domain. Subclasses implement the cycle-by-cycle tick() pipeline,
 * static graph initialization, and memory access commit callbacks.
 */
class ComputeUnit : public ClockedObject {
  private:

  protected:
    CommInterface *comm;
    HWInterface* hw;
    gem5::salam::WorkbenchStatistics workbenchStats;

    /**
     * @class TickEvent
     * @brief Dedicated Event wrapper driving the cycle-by-cycle compute
     * pipeline.
     */
    class TickEvent : public Event
    {
      private:
        ComputeUnit *comp_unit;

      public:
        TickEvent(ComputeUnit *_comp_unit) : Event(CPU_Tick_Pri), comp_unit(_comp_unit) {}
        void process() { comp_unit->tick(); }
        virtual const char *description() const { return "ComputeUnit tick"; }
    };


    TickEvent tickEvent;

  public:
    /**
     * @brief Main simulation step callback invoked every accelerator clock
     * cycle.
     */
    virtual void tick() {}
    /**
     * @brief Construct a new ComputeUnit object.
     * @param p SimObject configuration parameters.
     */
    ComputeUnit(const ComputeUnitParams &p);
    /**
     * @brief Initialize execution state and runtime data structures prior to
     * launch.
     */
    virtual void initialize() {}
    /**
     * @brief Callback invoked by CommInterface upon completion of a read
     * request.
     * @param req Pointer to completed memory read request.
     */
    virtual void readCommit(MemoryRequest * req) {}
    /**
     * @brief Callback invoked by CommInterface upon completion of a write
     * request.
     * @param req Pointer to completed memory write request.
     */
    virtual void writeCommit(MemoryRequest * req) {}
    /**
     * @brief Access the associated communication interface.
     * @return Pointer to CommInterface instance.
     */
    CommInterface * getCommInterface() { return comm; }
    /**
     * @brief Access the hardware modeling and PPA interface.
     * @return Pointer to HWInterface instance.
     */
    HWInterface * getHWInterface() { return hw; }
    /**
     * @brief Access runtime workbench statistics for GUI and execution
     * monitoring.
     * @return Reference to WorkbenchStatistics collector.
     */
    gem5::salam::WorkbenchStatistics &getWorkbenchStatistics() {
        return workbenchStats;
    }
};

#endif //__HWACC_COMPUTE_UNIT_HH__
