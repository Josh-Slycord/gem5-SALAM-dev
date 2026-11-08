#ifndef __HWACC_LLVM_INTERFACE_HH__
#define __HWACC_LLVM_INTERFACE_HH__

/**
 * @file llvm_interface.hh
 * @brief LLVM IR-driven cycle-accurate hardware accelerator execution engine
 * for gem5-SALAM.
 *
 * LLVMInterface parses LLVM bitcode into a control/data-flow graph (CDFG),
 * simulates
 * execution on a cycle-by-cycle basis with configurable functional units,
 * memory interfaces,
 * dynamic dependency resolution, and registers native gem5 statistics.
 */

// C++ Includes
#include <algorithm>
#include <chrono>
#include <ctime>
#include <deque>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <list>
#include <map>
#include <memory>
#include <queue>
#include <ratio>
#include <type_traits>
#include <typeinfo>

// LLVM Includes
#include <llvm-c/Core.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/Module.h>
#include <llvm/IRReader/IRReader.h>
#include <llvm/Support/SourceMgr.h>
#include <llvm/Transforms/Utils/Cloning.h>

// SALAM Includes
#include "base/statistics.hh"
#include "hwacc/HWModeling/src/hw_interface.hh"
#include "hwacc/fu_scheduling_pool.hh"
#include "hwacc/LLVMRead/src/basic_block.hh"
#include "hwacc/LLVMRead/src/debug_flags.hh"
#include "hwacc/LLVMRead/src/function.hh"
#include "hwacc/LLVMRead/src/operand.hh"
#include "hwacc/compute_unit.hh"
#include "params/LLVMInterface.hh"

class SalamLifecycleTester;

/**
 * @class LLVMInterface
 * @brief Primary compute engine executing LLVM IR dataflow graphs on modeled
 * hardware.
 *
 * Inherits from ComputeUnit. On initialization, it reads compiled LLVM bitcode
 * (.bc)
 * and constructs static CDFG structures (SALAM::Function, BasicBlock,
 * Instruction, Value).
 * During simulation, tick() drives dynamic instruction issue, dependency
 * tracking,
 * FU acquisition/release, memory transaction dispatch, and cycle
 * categorization.
 */
class LLVMInterface : public ComputeUnit {
    friend class SalamLifecycleTester;

  public:
    /**
     * @enum OpClass
     * @brief High-level classification of operations for accounting and issue
     * tracking.
     */
    enum OpClass
    {
        ComputeOp = 0,
        LoadOp = 1,
        StoreOp = 2,
        CallOp = 3,
        ControlOp = 4,
        NumOpClasses = 5
    };

    /**
     * @enum CycleCategory
     * @brief Detailed categorization of each accelerator execution cycle.
     */
    enum CycleCategory
    {
        IssueCycle = 0,
        FuStallCycle = 1,
        MemoryWaitCycle = 2,
        ComputeWaitCycle = 3,
        OtherCycle = 4,
        NumCycleCategories = 5
    };

  private:
    std::string filename;
    std::string topName;
    uint32_t scheduling_threshold;
    const uint32_t fuTraceEventLimit;
    int cycle;
    int stalls;

    /**
     * @struct PassEvents
     * @brief Per-cycle event flags used to classify cycle stalls.
     */
    struct PassEvents
    {
        bool issued = false;
        bool fuDenied = false;
        bool memoryOrderWait = false;
    };
    PassEvents pass;

    /**
     * @struct ExecStats
     * @brief Native gem5 statistics group for SALAM accelerator execution.
     */
    struct ExecStats : public statistics::Group
    {
        ExecStats(LLVMInterface *owner);
        void regStats() override;

        statistics::Scalar invocations;
        statistics::Scalar completedInvocations;
        statistics::Scalar invocationTicks;
        statistics::Scalar cycles;
        statistics::Vector cycleCategories;
        statistics::Vector issued;
        statistics::Vector completed;
        statistics::Vector opcodesIssued;
        statistics::Scalar fuDenials;
        statistics::Scalar memoryOrderWaits;
        statistics::Average reservedOps;
        statistics::Average computeOps;
        statistics::Average readOps;
        statistics::Average writeOps;
    };
    ExecStats execStats;

    void countIssue(OpClass cls, uint64_t opcode);
    void countCompletion(OpClass cls);
    void countFuDenial();
    void countMemoryOrderWait();
    void countCycleCategory();
    void sampleOccupancy();

    bool running = false;
    bool loadOpScheduled;
    bool storeOpScheduled;
    bool compOpScheduled;
    bool lockstep;
    bool dbg;
    std::chrono::duration<float> setupTime;
    std::chrono::duration<float> simTotal;
    std::chrono::duration<float> simTime;
    std::chrono::duration<float> schedulingTime;
    std::chrono::duration<float> queueProcessTime;
    std::chrono::duration<float> computeTime;
    std::chrono::duration<float> hwTime;
    std::chrono::high_resolution_clock::time_point simStop;
    std::chrono::high_resolution_clock::time_point setupStop;
    std::chrono::high_resolution_clock::time_point timeStart;


    /**
     * @class ActiveFunction
     * @brief Dynamic activation record managing in-flight execution of an LLVM
     * function.
     *
     * Holds the dynamic reservation queue, active read/write/compute queues,
     * instruction dynamic dependency resolution, and basic block scheduling.
     */
    class ActiveFunction {
      friend class LLVMInterface;
    private:
        LLVMInterface * owner;
        HWInterface* hw;
        std::shared_ptr<SALAM::Function> func;
        std::shared_ptr<SALAM::Instruction> caller;
        std::list<std::shared_ptr<SALAM::Instruction>> reservation;
        std::map<uint64_t, std::shared_ptr<SALAM::Instruction>> readQueue;
        std::map<MemoryRequest *, uint64_t> readQueueMap;
        std::map<uint64_t, std::shared_ptr<SALAM::Instruction>> writeQueue;
        std::map<MemoryRequest *, uint64_t> writeQueueMap;
        std::map<uint64_t, std::shared_ptr<SALAM::Instruction>> computeQueue;
        std::shared_ptr<SALAM::BasicBlock> previousBB;
        HW_Cycle_Stats hw_cycle_stats;
        uint32_t scheduling_threshold;
        bool returned = false;
        bool lockstep;
        bool dbg;

        inline bool uidActive(uint64_t id) {
          return computeUIDActive(id) || readUIDActive(id) || writeUIDActive(id);
        }

        std::map<Addr, std::shared_ptr<SALAM::Instruction>> activeWrites;
        inline void trackWrite(Addr writeAddr, std::shared_ptr<SALAM::Instruction> writeInst) {
          activeWrites.insert({writeAddr, writeInst});
        }
        inline void untrackWrite(uint64_t writeAddr) {
          auto it = activeWrites.find(writeAddr);
          if (it != activeWrites.end()) activeWrites.erase(it);
        }
        inline bool writeActive(uint64_t writeAddr) {
          return (activeWrites.find(writeAddr) != activeWrites.end());
        }

        inline std::shared_ptr<SALAM::Instruction> getActiveWrite(uint64_t writeAddr) {
          return activeWrites.find(writeAddr)->second;
        }
        // std::map<Addr, std::shared_ptr<SALAM::Instruction>> activeReads;
        // inline void trackRead(Addr readAddr, std::shared_ptr<SALAM::Instruction> readInst) {
        //   activeReads.insert({readAddr, readInst});
        // }
        // inline void untrackRead(uint64_t readAddr) {
        //   auto it = activeReads.find(readAddr);
        //   if (it != activeReads.end()) activeReads.erase(it);
        // }
        // inline bool readActive(uint64_t readAddr) {
        //   return (activeReads.find(readAddr) != activeReads.end());
        // }
        // inline std::shared_ptr<SALAM::Instruction> getActiveRead(uint64_t readAddr) {
        //   return activeReads.find(readAddr)->second;
        // }
        inline bool writeUIDActive(uint64_t uid) {
          return (writeQueue.find(uid) != writeQueue.end());
        }
        inline bool readUIDActive(uint64_t uid) {
          return (readQueue.find(uid) != readQueue.end());
        }
        inline bool computeUIDActive(uint64_t uid) {
          return (computeQueue.find(uid) != computeQueue.end());
        }
    public:
        /**
         * @brief Construct an ActiveFunction activation record.
         * @param _owner Parent LLVMInterface engine.
         * @param _func Target function to activate.
         * @param _caller Caller instruction if nested call.
         */
        ActiveFunction(LLVMInterface * _owner, std::shared_ptr<SALAM::Function> _func,
                       std::shared_ptr<SALAM::Instruction> _caller):
                       owner(_owner), hw(_owner->getHWInterface()), func(_func),
                       caller(_caller), previousBB(nullptr) {
                          scheduling_threshold = owner->getSchedulingThreshold();
                          lockstep = (owner->getLockstepStatus());
                          dbg = owner->debug();
                       }
        /**
         * @brief Commit a completed memory read transaction.
         * @param req Pointer to completed MemoryRequest.
         */
        void readCommit(MemoryRequest *req);
        /**
         * @brief Commit a completed memory write transaction.
         * @param req Pointer to completed MemoryRequest.
         */
        void writeCommit(MemoryRequest *req);
        /**
         * @brief Resolve dynamic dependencies for an instruction before issue.
         * @param inst Instruction clone to resolve.
         */
        void findDynamicDeps(std::shared_ptr<SALAM::Instruction> inst);
        /**
         * @brief Schedule all instructions within a basic block into the
         * reservation queue.
         * @param bb Target BasicBlock to schedule.
         */
        void scheduleBB(std::shared_ptr<SALAM::BasicBlock> bb);
        /**
         * @brief Process and advance active compute, read, and write queues
         * for this cycle.
         */
        void processQueues();
        /**
         * @brief Launch function execution by scheduling its entry basic
         * block.
         */
        void launch();
        /**
         * @brief Check whether all in-flight execution queues are empty.
         * @return True if read, write, and compute queues are empty.
         */
        inline bool queuesClear() {
          return readQueue.empty() && writeQueue.empty() && computeQueue.empty();
        }
        inline bool lockstepReady() {
          return !lockstep || queuesClear();
        }
        /**
         * @brief Check whether the function has reached a committable return
         * state.
         * @return True if queues are clear and head instruction is a return.
         */
        inline bool canReturn() {
            return queuesClear() && reservation.front()->isReturn();
        }
        /**
         * @brief Dispatch an in-flight read instruction to the memory system.
         * @param readInst Target read instruction.
         */
        void launchRead(std::shared_ptr<SALAM::Instruction> readInst);
        /**
         * @brief Dispatch an in-flight write instruction to the memory system.
         * @param writeInst Target write instruction.
         */
        void launchWrite(std::shared_ptr<SALAM::Instruction> writeInst);
        /**
         * @brief Check whether this active function instance has completed and
         * returned.
         * @return True if returned.
         */
        bool hasReturned() { return returned; }
    };

    FUSchedulingPool fuSchedulingPool;
    std::map<uint32_t, FunctionalUnitBase *> fuModelById;
    uint64_t fuStartTick = 0;
    std::list<ActiveFunction> activeFunctions;
    std::map<MemoryRequest *, ActiveFunction *> globalReadQueue;
    std::map<MemoryRequest *, ActiveFunction *> globalWriteQueue;

    std::vector<std::shared_ptr<SALAM::Function>> functions;
    std::vector<std::shared_ptr<SALAM::Value>> values;
  protected:
    // const std::string name() const { return comm->getName() + ".compute"; }
    virtual bool debug() { return comm->debug(); }
    // virtual bool debug() { return true; }
  public:
    PARAMS(LLVMInterface);
    /**
     * @brief Construct a new LLVMInterface object.
     * @param p SimObject configuration parameters.
     */
    LLVMInterface(const LLVMInterfaceParams &p);
    /**
     * @brief Advance simulation state by one clock cycle.
     */
    void tick();
    /**
     * @brief Parse LLVM bitcode file and construct static CDFG structures.
     */
    void constructStaticGraph();
    void startup();
    /**
     * @brief Initialize accelerator state, reset counters, and prepare queues.
     */
    void initialize();
    /**
     * @brief Teardown accelerator execution, emit statistics, and release
     * graph nodes.
     */
    void finalize();
    /**
     * @brief Evaluates whether the LLVM execution engine has drained.
     *
     * Returns DrainState::Drained when not running and no tick event is
     * scheduled; otherwise returns DrainState::Draining until
     * finalize() completes the active invocation and calls
     * signalDrainDone().
     *
     * @return Current gem5 DrainState.
     */
    DrainState drain() override;
    void debug(uint64_t flags);
    bool getLockstepStatus() { return lockstep; }
    void readCommit(MemoryRequest *req);
    void writeCommit(MemoryRequest *req);
    /**
     * @brief Debug helper dumping LLVM module details to stdout.
     * @param m Pointer to llvm::Module.
     */
    void dumpModule(llvm::Module *m);
    /**
     * @brief Print simulation results, cycle breakdown, and PPA estimates.
     */
    void printResults();
    /**
     * @brief Instantiate and launch an activation record for a function.
     * @param callee Target function to launch.
     * @param caller Caller instruction if nested call.
     */
    void launchFunction(std::shared_ptr<SALAM::Function> callee,
                        std::shared_ptr<SALAM::Instruction> caller);
    /**
     * @brief Launch the top-level entry function of the accelerator.
     */
    void launchTopFunction();
    /**
     * @brief Attempt to acquire an FU lease for an instruction.
     * @param inst Requesting instruction.
     * @return True if granted; false if denied.
     */
    bool tryAcquireFU(SALAM::Instruction *inst);
    /**
     * @brief Release an FU lease held by an instruction.
     * @param inst Instruction releasing lease.
     */
    void releaseFU(SALAM::Instruction *inst);
    void endFunction(ActiveFunction * afunc);
    void launchRead(MemoryRequest * memReq, ActiveFunction * func);
    void launchWrite(MemoryRequest * memReq, ActiveFunction * func);
    /**
     * @brief Factory method mapping an llvm::Instruction to a
     * SALAM::Instruction subclass.
     * @param inst Pointer to LLVM IR instruction.
     * @param id Unique value ID.
     * @return Shared pointer to newly constructed SALAM::Instruction.
     */
    std::shared_ptr<SALAM::Instruction> createInstruction(llvm::Instruction *inst,
                                                          uint64_t id);
    void dumpQueues();
    uint32_t getSchedulingThreshold() { return scheduling_threshold; }
    void addSchedulingTime(std::chrono::duration<float> timeDelta) { schedulingTime = schedulingTime + timeDelta; }
    void addQueueTime(std::chrono::duration<float> timeDelta) { queueProcessTime = queueProcessTime + timeDelta; }
    void addComputeTime(std::chrono::duration<float> timeDelta) { computeTime = computeTime + timeDelta; }
    void addHWTime(std::chrono::duration<float> timeDelta) { hwTime = hwTime + timeDelta; }
};

#endif //__HWACC_LLVM_INTERFACE_HH__
