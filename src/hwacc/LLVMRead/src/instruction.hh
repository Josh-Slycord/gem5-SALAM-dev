#ifndef __HWACC_LLVM_INSTRUCTION_HH__
#define __HWACC_LLVM_INSTRUCTION_HH__

/**
 * @file
 * @brief Declares SALAM::Instruction base class and LLVM IR instruction
 * specializations.
 *
 * In the SALAM CDFG execution model, instructions represent nodes in the
 * dynamic
 * dataflow graph. Each instruction tracks static operands, dynamic
 * dependencies
 * and consumers, hardware functional unit allocation, latency cycle counts,
 * and computation state (ready, launched, computed, committed). Specialized
 * classes model specific LLVM IR opcodes for control flow, integer/FP math,
 * memory operations, bit manipulation, and conversions.
 */

#include <cstdlib>
#include <iostream>
#include <llvm/IR/Value.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/Instructions.h>
#include "basic_block.hh"
#include "operand.hh"
#include "debug_flags.hh"
#include "value.hh"
#include "mem_request.hh"
#include "../../HWModeling/src/hw_interface.hh"

namespace SALAM {

class BasicBlock; // Required Declaration

//---------------------------------------------------------------------------//
//--------- Instruction Base Class ------------------------------------------//
//---------------------------------------------------------------------------//


/**
 * @brief Base class for all executable instructions in the SALAM CDFG.
 *
 * Extends SALAM::Value to represent an instruction node in the CDFG. Tracks
 * static operands, dynamic dependencies (predecessor instructions), dynamic
 * users (consumer instructions), latency cycle budgets, and execution states
 * (ready, launch, compute, commit).
 */
class Instruction : public Value
{
    private:
        std::map<uint64_t, std::shared_ptr<SALAM::Instruction>> dynamicDependencies;
        std::vector<std::shared_ptr<SALAM::Instruction>> dynamicUsers;
        uint64_t llvmOpCode;
        uint64_t cycleCount;
        uint64_t currentCycle;
        uint64_t functional_unit = 0;
        HWInterface* hw_interface;

    protected:
        valueListTy staticDependencies;
        // Operands
        std::vector<SALAM::Operand> operands;

        bool running = false;
        /**
         * @brief Debug helper for printing instruction execution state.
         */
        class Instruction_Debugger: public Debugger
        {
            public:
                Instruction_Debugger();
                ~Instruction_Debugger() = default;
                virtual void dumper(SALAM::Instruction *inst);
        };
        Instruction_Debugger* inst_dbg;
        bool launched = false;
        bool committed = false;
        bool isready = false;
    public:
        /**
         * @brief Constructs an Instruction node.
         *
         * @param id Unique identifier.
         * @param owner Pointer to the owning gem5 SimObject.
         * @param dbg Flag indicating whether debug logging is enabled.
         */
        Instruction(uint64_t id, gem5::SimObject * owner, bool dbg); //
        /**
         * @brief Constructs an Instruction node with opcode.
         *
         * @param id Unique identifier.
         * @param owner Pointer to the owning gem5 SimObject.
         * @param dbg Flag indicating whether debug logging is enabled.
         * @param OpCode LLVM opcode identifier.
         */
        Instruction(uint64_t id, gem5::SimObject * owner, bool dbg, uint64_t OpCode); //
        /**
         * @brief Constructs an Instruction node with opcode and cycle count.
         *
         * @param id Unique identifier.
         * @param owner Pointer to the owning gem5 SimObject.
         * @param dbg Flag indicating whether debug logging is enabled.
         * @param OpCode LLVM opcode identifier.
         * @param cycles Latency in compute cycles.
         */
        Instruction(uint64_t id, gem5::SimObject * owner, bool dbg, uint64_t OpCode, uint64_t cycles); //
        /**
         * @brief Constructs an Instruction node with opcode, cycles, and FU
         * type.
         *
         * @param id Unique identifier.
         * @param owner Pointer to the owning gem5 SimObject.
         * @param dbg Flag indicating whether debug logging is enabled.
         * @param OpCode LLVM opcode identifier.
         * @param cycles Latency in compute cycles.
         * @param functional_unit Functional unit type ID.
         */
        Instruction(uint64_t id, gem5::SimObject * owner, bool dbg, uint64_t OpCode, uint64_t cycles, uint64_t functional_unit); //
        /**
         * @brief Destructor for Instruction.
         */
        ~Instruction(); //
        /**
         * @brief Releases shared pointer cycles in the CDFG before
         * destruction.
         */
        void releaseGraphEdges() override;
        /**
         * @brief Equality operator comparing instruction UIDs.
         */
        bool operator == (const std::shared_ptr<SALAM::Instruction> inst) const { return this->getUID() == inst->getUID(); }
        /**
         * @brief Inequality operator comparing instruction UIDs.
         */
        bool operator != (const std::shared_ptr<SALAM::Instruction> inst) const { return !operator==(inst); }
        /**
         * @brief Initializes the instruction from an LLVM IR Value and value
         * map.
         *
         * @param irval Underlying LLVM IR Value.
         * @param irmap Map resolving LLVM Values to SALAM Values.
         * @param valueList Global list of values in the CDFG.
         */
        virtual void initialize(llvm::Value * irval, irvmap * irmap, SALAM::valueListTy * valueList); //
        /**
         * @brief Returns the target basic block for branch/control
         * instructions.
         *
         * @return Pointer to target BasicBlock, or nullptr if non-branching.
         */
        virtual std::shared_ptr<SALAM::BasicBlock> getTarget()  { return nullptr; }
        /**
         * @brief Returns the count of remaining unresolved dynamic
         * dependencies.
         *
         * @return Number of unsatisfied predecessor dependencies.
         */
        uint64_t getDependencyCount() { return dynamicDependencies.size(); }
        /**
         * @brief Returns the total cycle latency for this instruction.
         *
         * @return Latency in cycles.
         */
        virtual uint64_t getCycleCount() { return cycleCount; }
        /**
         * @brief Returns the LLVM opcode for this instruction.
         *
         * @return Opcode identifier.
         */
        virtual uint64_t getOpode() { return llvmOpCode; }
        /**
         * @brief Returns the current execution cycle progress.
         *
         * @return Elapsed cycles since launch.
         */
        uint64_t getCurrentCycle() { return currentCycle; }
        /**
         * @brief Returns the list of static CDFG dependencies.
         *
         * @return Vector of Value shared pointers.
         */
        virtual valueListTy getStaticDependencies() const { return staticDependencies; }
        /**
         * @brief Returns the map of unresolved dynamic dependencies.
         *
         * @return Map of UID to Instruction shared pointers.
         */
        std::map<uint64_t, std::shared_ptr<SALAM::Instruction>> getDynamicDependencies() const { return dynamicDependencies; }
        /**
         * @brief Returns a specific static dependency by index.
         *
         * @param i Index into static dependency vector.
         * @return Shared pointer to dependency Value.
         */
        std::shared_ptr<SALAM::Value> getStaticDependencies(int i) const { return staticDependencies.at(i); }
        /**
         * @brief Returns a specific dynamic dependency by UID.
         *
         * @param i UID key of dynamic dependency.
         * @return Shared pointer to dependency Value.
         */
        std::shared_ptr<SALAM::Value> getDynamicDependencies(int i) const { return dynamicDependencies.at(i); }
        /**
         * @brief Initializes dynamic runtime state when basic block becomes
         * active.
         *
         * @return Vector of dynamic dependency UIDs.
         */
        virtual std::vector<uint64_t> runtimeInitialize();
        /**
         * @brief Removes a resolved dynamic predecessor dependency.
         *
         * @param opuid UID of the completed predecessor instruction.
         */
        void removeDynamicDependency(uint64_t opuid);
        /**
         * @brief Registers a dynamic predecessor dependency for this
         * instruction.
         *
         * @param dep Shared pointer to dependency instruction.
         */
        void addRuntimeDependency(std::shared_ptr<SALAM::Instruction> dep) {
            dynamicDependencies.insert({dep->getUID(),dep});
        }
        /**
         * @brief Registers a downstream consumer instruction to notify on
         * commit.
         *
         * @param dep Shared pointer to user instruction.
         */
        void addRuntimeUser(std::shared_ptr<SALAM::Instruction> dep) { dynamicUsers.push_back(dep); }
        /**
         * @brief Signals all downstream dynamic users that this instruction
         * has committed.
         */
        void signalUsers();
        /**
         * @brief Returns whether this instruction has committed its result.
         *
         * @return True if committed.
         */
        bool isCommitted() { return committed; }
        //bool hasFunctionalUnit() { return (functional_unit != 0); }
        /**
         * @brief Checks if this instruction requires a functional unit lease.
         *
         * @return False under default scalar model.
         */
        bool hasFunctionalUnit() { return false; }
        /**
         * @brief Returns whether debug logging is active.
         *
         * @return True if debug enabled.
         */
        bool debug() { return dbg; }
        /**
         * @brief Appends an operand to the instruction's operand list.
         *
         * @param newOp Operand to attach.
         */
        void linkOperands(const SALAM::Operand &newOp);
        /**
         * @brief Returns a pointer to the operand list.
         *
         * @return Pointer to vector of operands.
         */
        std::vector<SALAM::Operand> * getOperands() { return &operands; }
        /**
         * @brief Returns the functional unit type ID for this instruction.
         *
         * @return FU identifier.
         */
        uint64_t getFunctionalUnit() { return functional_unit; }
        /** @brief Predicate indicating return instruction. */
        virtual bool isReturn() { return false; }
        /** @brief Predicate indicating basic block terminator instruction. */
        virtual bool isTerminator() { return false; }
        /** @brief Predicate indicating PHI node instruction. */
        virtual bool isPhi() { return false; }
        /** @brief Predicate indicating function call instruction. */
        virtual bool isCall() { return false; }
        /** @brief Predicate indicating branch instruction. */
        virtual bool isBr() { return false; }
        /** @brief Predicate indicating memory load instruction. */
        virtual bool isLoad() { return false; }
        /** @brief Predicate indicating memory store instruction. */
        virtual bool isStore() {return false; }
        /** @brief Predicate indicating getelementptr address calculation. */
        virtual bool isGEP() { return false; }
        /**
         * @brief Transitions instruction from ready to launched state.
         *
         * @return True if launch succeeded.
         */
        virtual bool launch();
        /**
         * @brief Commits the computed result to return register and signals
         * users.
         *
         * @return True if commit succeeded.
         */
        virtual bool commit();
        /**
         * @brief Evaluates whether all preconditions and dependencies are
         * satisfied.
         *
         * @return True if instruction is ready to launch.
         */
        virtual bool ready();
        /**
         * @brief Executes the functional logic of the instruction.
         */
        virtual void compute() { }
        /**
         * @brief Resets dynamic execution state for re-execution.
         */
        virtual void reset();
        /**
         * @brief Propagates computed operand values to dynamic users.
         *
         * @param uid UID of the operand.
         */
        virtual void setOperandValue(uint64_t uid);
        /**
         * @brief Dumps debug state for this instruction.
         */
        virtual void dump() { if (dbg) inst_dbg->dumper(this); }
        /** @brief Identifies whether this Value is an Instruction. */
        virtual bool isInstruction() { return true; }
        /** @brief Predicate for internal pipeline load state. */
        virtual bool isLoadingInternal() { return false; }
        /** @brief Predicate for latching loop branch exit. */
        virtual bool isLatchingBrExiting() { return false; }
        // virtual void linkFunctionalUnit(HWInterface * hw_interface);
        /**
         * @brief Clones this instruction for dynamic loop unrolling or
         * pipelining.
         *
         * @return Shared pointer to cloned instruction.
         */
        std::shared_ptr<SALAM::Instruction> clone() const { return std::static_pointer_cast<SALAM::Instruction>(createClone()); }
        /**
         * @brief Factory method for creating polymorphic instruction clones.
         *
         * @return Shared pointer to cloned Value instance.
         */
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Instruction>(new SALAM::Instruction(*this)); }
        /**
         * @brief Creates a MemoryRequest descriptor for memory-accessing
         * instructions.
         *
         * @return Pointer to MemoryRequest, or nullptr if not a memory
         * instruction.
         */
        virtual MemoryRequest * createMemoryRequest() { return nullptr; }

        // Functions for getting data from operands
        /**
         * @brief Reads a pointer/address value from a specific operand
         * register.
         *
         * @param op_num Index of the operand.
         * @return 64-bit pointer address.
         */
        uint64_t getPtrOperandValue(uint64_t op_num) { return (operands.at(op_num).getPtrRegValue()); }
};

//---------------------------------------------------------------------------//
//--------- Bad Instruction -------------------------------------------------//
//---------------------------------------------------------------------------//

// SALAM-BadInstruction // --------------------------------------------------//
/**
 * @brief Placeholder instruction used to establish dependency barriers.
 */
class BadInstruction : public Instruction {
    // Used to draw hard dependencies, ie: ret
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;

    protected:
    public:
        BadInstruction(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~BadInstruction() = default;
        void initialize (llvm::Value * irval,
                irvmap * irmap,
                SALAM::valueListTy * valueList);
        std::shared_ptr<SALAM::BadInstruction> clone() const { return std::static_pointer_cast<SALAM::BadInstruction>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::BadInstruction>(new SALAM::BadInstruction(*this)); }
};


std::shared_ptr<SALAM::Instruction>
createBadInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);


//---------------------------------------------------------------------------//
//--------- Terminator Instructions -----------------------------------------//
//---------------------------------------------------------------------------//

// SALAM-Ret // -------------------------------------------------------------//

/**
 * @brief Models the LLVM 'ret' return instruction.
 */
class Ret : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        Ret(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Ret() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        bool isReturn() override { return true; }
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::Ret> clone() const { return std::static_pointer_cast<SALAM::Ret>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Ret>(new SALAM::Ret(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createRetInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);

// SALAM-Br // --------------------------------------------------------------//

/**
 * @brief Models unconditional and conditional branch instructions ('br').
 */
class Br : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        std::shared_ptr<SALAM::Value> condition;
        std::shared_ptr<SALAM::BasicBlock> defaultDestination;
        std::shared_ptr<SALAM::BasicBlock> trueDestination;
        std::shared_ptr<SALAM::BasicBlock> falseDestination;
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;
        bool conditional = false;
        bool isLatching = false;

    protected:
    public:
        // Branch Constructor
        Br(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Br() = default;
        void initialize(llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        void releaseGraphEdges() override;
        Br &isConditional(bool isConditional) { conditional = isConditional; return *this; }
        bool isConditional() { return conditional; }
        std::shared_ptr<SALAM::BasicBlock> getTarget() override;
        bool isTerminator() override { return true; }
        bool isBr() override { return true; }
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void setLatching(bool latch) { isLatching = latch; }
        virtual bool isLatchingBrExiting() override { return isLatching && (getTarget()==trueDestination); }
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::Br> clone() const { return std::static_pointer_cast<SALAM::Br>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Br>(new SALAM::Br(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createBrInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);

// SALAM-Switch // ----------------------------------------------------------//
typedef std::pair<std::shared_ptr<SALAM::Value>, std::shared_ptr<SALAM::BasicBlock>> caseArgs;
typedef std::vector< caseArgs> switchArgs;

/**
 * @brief Models the LLVM multi-way conditional 'switch' instruction.
 */
class Switch : public Instruction {
    public:
        static constexpr size_t kSwitchConditionOperandIndex = 0;
        static constexpr size_t kSwitchDefaultDestOperandIndex = 1;
        static constexpr size_t kSwitchFirstCaseOperandIndex = 2;

    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        // [0] [Switch Var, Default Dest]
        // [1] [ Case Var, Case Dest ] .... [n]
        switchArgs cases;
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;
        std::shared_ptr<SALAM::BasicBlock> defaultDestination;
    protected:
    public:
        Switch(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Switch() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        void releaseGraphEdges() override;
        // std::shared_ptr<SALAM::Value> defaultDest() { return arguments[0].second; }
        // std::shared_ptr<SALAM::Value> destination(int switchVar);
        std::shared_ptr<SALAM::BasicBlock> getTarget() override;
        bool isTerminator() override { return true; }
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::Switch> clone() const { return std::static_pointer_cast<SALAM::Switch>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Switch>(new SALAM::Switch(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createSwitchInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
//---------------------------------------------------------------------------//
//--------- Binary Operator Instructions ------------------------------------//
//---------------------------------------------------------------------------//

// SALAM-Add // -------------------------------------------------------------//

/**
 * @brief Models 2's complement integer addition ('add') instruction.
 */
class Add : public Instruction
{
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        Add(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Add() = default;
        void initialize(llvm::Value *irval,
                        SALAM::irvmap *irmap,
                        SALAM::valueListTy *valueList) override;
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::Add> clone() const { return std::static_pointer_cast<SALAM::Add>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Add>(new SALAM::Add(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createAddInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);

// SALAM-FAdd // ------------------------------------------------------------//

/**
 * @brief Models floating-point addition ('fadd') instruction.
 */
class FAdd : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        FAdd(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~FAdd() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::FAdd> clone() const { return std::static_pointer_cast<SALAM::FAdd>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::FAdd>(new SALAM::FAdd(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createFAddInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-Sub // -------------------------------------------------------------//

/**
 * @brief Models 2's complement integer subtraction ('sub') instruction.
 */
class Sub : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        Sub(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Sub() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::Sub> clone() const { return std::static_pointer_cast<SALAM::Sub>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Sub>(new SALAM::Sub(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createSubInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-FSub // -------------------------------------------------------------//

/**
 * @brief Models floating-point subtraction ('fsub') instruction.
 */
class FSub : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        FSub(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~FSub() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::FSub> clone() const { return std::static_pointer_cast<SALAM::FSub>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::FSub>(new SALAM::FSub(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createFSubInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-Mul // -------------------------------------------------------------//

/**
 * @brief Models integer multiplication ('mul') instruction.
 */
class Mul : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::APIntRegister *op1, *op2;
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        Mul(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Mul() = default;
        void initialize (llvm::Value * irval,
                        SALAM::irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::Mul> clone() const { return std::static_pointer_cast<SALAM::Mul>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Mul>(new SALAM::Mul(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createMulInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-FMul // ------------------------------------------------------------//

/**
 * @brief Models floating-point multiplication ('fmul') instruction.
 */
class FMul : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        FMul(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~FMul() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::FMul> clone() const { return std::static_pointer_cast<SALAM::FMul>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::FMul>(new SALAM::FMul(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createFMulInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-UDiv // ------------------------------------------------------------//

/**
 * @brief Models unsigned integer division ('udiv') instruction.
 */
class UDiv : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        UDiv(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~UDiv() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::UDiv> clone() const { return std::static_pointer_cast<SALAM::UDiv>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::UDiv>(new SALAM::UDiv(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createUDivInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-SDiv // ------------------------------------------------------------//

/**
 * @brief Models signed integer division ('sdiv') instruction.
 */
class SDiv : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        SDiv(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~SDiv() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::SDiv> clone() const { return std::static_pointer_cast<SALAM::SDiv>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::SDiv>(new SALAM::SDiv(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createSDivInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-FDiv // ------------------------------------------------------------//

/**
 * @brief Models floating-point division ('fdiv') instruction.
 */
class FDiv : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        FDiv(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~FDiv() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::FDiv> clone() const { return std::static_pointer_cast<SALAM::FDiv>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::FDiv>(new SALAM::FDiv(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createFDivInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-URem // ------------------------------------------------------------//

/**
 * @brief Models unsigned integer remainder ('urem') instruction.
 */
class URem : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        URem(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~URem() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::URem> clone() const { return std::static_pointer_cast<SALAM::URem>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::URem>(new SALAM::URem(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createURemInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-SRem // ------------------------------------------------------------//

/**
 * @brief Models signed integer remainder ('srem') instruction.
 */
class SRem : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        SRem(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~SRem() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::SRem> clone() const { return std::static_pointer_cast<SALAM::SRem>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::SRem>(new SALAM::SRem(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createSRemInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-FRem // ------------------------------------------------------------//

/**
 * @brief Models floating-point remainder ('frem') instruction.
 */
class FRem : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        FRem(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~FRem() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::FRem> clone() const { return std::static_pointer_cast<SALAM::FRem>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::FRem>(new SALAM::FRem(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createFRemInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
//---------------------------------------------------------------------------//
//--------- Bitwise Binary Operator Instructions ----------------------------//
//---------------------------------------------------------------------------//

// SALAM-Shl // -------------------------------------------------------------//

/**
 * @brief Models bitwise shift left ('shl') instruction.
 */
class Shl : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        Shl(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Shl() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::Shl> clone() const { return std::static_pointer_cast<SALAM::Shl>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Shl>(new SALAM::Shl(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createShlInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-LShr // ------------------------------------------------------------//

/**
 * @brief Models logical (zero-fill) shift right ('lshr') instruction.
 */
class LShr : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        LShr(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~LShr() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::LShr> clone() const { return std::static_pointer_cast<SALAM::LShr>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::LShr>(new SALAM::LShr(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createLShrInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-AShr // ------------------------------------------------------------//

/**
 * @brief Models arithmetic (sign-extended) shift right ('ashr') instruction.
 */
class AShr : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        AShr(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~AShr() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::AShr> clone() const { return std::static_pointer_cast<SALAM::AShr>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::AShr>(new SALAM::AShr(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createAShrInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-And // -------------------------------------------------------------//

/**
 * @brief Models bitwise AND ('and') instruction.
 */
class And : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        And(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~And() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::And> clone() const { return std::static_pointer_cast<SALAM::And>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::And>(new SALAM::And(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createAndInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-Or // --------------------------------------------------------------//

/**
 * @brief Models bitwise OR ('or') instruction.
 */
class Or : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;
    protected:

    public:
        Or(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Or() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::Or> clone() const { return std::static_pointer_cast<SALAM::Or>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Or>(new SALAM::Or(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createOrInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-Xor // -------------------------------------------------------------//

/**
 * @brief Models bitwise XOR ('xor') instruction.
 */
class Xor : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        Xor(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Xor() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::Xor> clone() const { return std::static_pointer_cast<SALAM::Xor>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Xor>(new SALAM::Xor(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createXorInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
//---------------------------------------------------------------------------//
//--------- Memory Instructions ---------------------------------------------//
//---------------------------------------------------------------------------//

// SALAM-Load // ------------------------------------------------------------//

/**
 * @brief Models memory read ('load') instruction.
 */
class Load : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        uint64_t align;
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;
        bool loadingInternal = false;

    protected:
    public:
        Load(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Load() = default;
        void initialize(llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        bool isLoad() override { return true; }
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void loadInternal();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        bool isLoadingInternal() { return loadingInternal; }
        std::shared_ptr<SALAM::Load> clone() const { return std::static_pointer_cast<SALAM::Load>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Load>(new SALAM::Load(*this)); }

        MemoryRequest * createMemoryRequest() override;
};

std::shared_ptr<SALAM::Instruction>
createLoadInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-Store // -----------------------------------------------------------//

/**
 * @brief Models memory write ('store') instruction.
 */
class Store : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        uint64_t align;
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        Store (uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Store() = default;
        void initialize(llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        bool isStore() override { return true; }
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::Store> clone() const { return std::static_pointer_cast<SALAM::Store>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Store>(new SALAM::Store(*this)); }

        MemoryRequest * createMemoryRequest() override;
};

std::shared_ptr<SALAM::Instruction>
createStoreInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-GEP // -------------------------------------------------------------//

/*

In our storage, pointers are standard uint64_t, for comm interface convience
The GEP indecies will by APSInts, so cast to int64_t for calculating offset inside GEP, then recast to APSInt

*/

/**
 * @brief Models pointer address arithmetic ('getelementptr' / GEP)
 * instruction.
 */
class GetElementPtr : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        std::vector<int64_t> offsets;
        std::vector<bool> offsetOfStruct;
        SALAM::Debugger *dbgr;
        llvm::Type * resultElementType;
        uint64_t resultElementSize;
        uint64_t resultElementSizeInBytes;
    protected:

    public:
        GetElementPtr(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~GetElementPtr() = default;
        void initialize(llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        GetElementPtr &setA() { return *this; }
        GetElementPtr &setB() { return *this; }
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        virtual bool isGEP() override { return true; }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::GetElementPtr> clone() const { return std::static_pointer_cast<SALAM::GetElementPtr>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::GetElementPtr>(new SALAM::GetElementPtr(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createGetElementPtrInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
//---------------------------------------------------------------------------//
//--------- Other / Cast Instructions ---------------------------------------//
//---------------------------------------------------------------------------//

// SALAM-Trunc // -----------------------------------------------------------//

/**
 * @brief Models integer bit-width truncation ('trunc') instruction.
 */
class Trunc : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        Trunc(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Trunc() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::Trunc> clone() const { return std::static_pointer_cast<SALAM::Trunc>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Trunc>(new SALAM::Trunc(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createTruncInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-ZExt // ------------------------------------------------------------//

/**
 * @brief Models zero extension ('zext') instruction.
 */
class ZExt : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        ZExt(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~ZExt() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::ZExt> clone() const { return std::static_pointer_cast<SALAM::ZExt>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::ZExt>(new SALAM::ZExt(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createZExtInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-SExt // ------------------------------------------------------------//

/**
 * @brief Models sign extension ('sext') instruction.
 */
class SExt : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        SExt(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~SExt() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::SExt> clone() const { return std::static_pointer_cast<SALAM::SExt>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::SExt>(new SALAM::SExt(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createSExtInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-FPToUI // ----------------------------------------------------------//
class FPToUI;
void initializeFPToUIInst(SALAM::FPToUI &salamInstruction);

/**
 * @brief Models floating-point to unsigned integer conversion ('fptoui').
 */
class FPToUI : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        FPToUI(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~FPToUI() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::FPToUI> clone() const { return std::static_pointer_cast<SALAM::FPToUI>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::FPToUI>(new SALAM::FPToUI(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createFPToUIInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-FPToSI // ----------------------------------------------------------//

/**
 * @brief Models floating-point to signed integer conversion ('fptosi').
 */
class FPToSI : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:

    public:
        FPToSI(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~FPToSI() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::FPToSI> clone() const { return std::static_pointer_cast<SALAM::FPToSI>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::FPToSI>(new SALAM::FPToSI(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createFPToSIInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-UIToFP // ----------------------------------------------------------//

/**
 * @brief Models unsigned integer to floating-point conversion ('uitofp').
 */
class UIToFP : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        UIToFP(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~UIToFP() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::UIToFP> clone() const { return std::static_pointer_cast<SALAM::UIToFP>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::UIToFP>(new SALAM::UIToFP(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createUIToFPInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-SIToFP // ----------------------------------------------------------//

/**
 * @brief Models signed integer to floating-point conversion ('sitofp').
 */
class SIToFP : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        SIToFP(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~SIToFP() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::SIToFP> clone() const { return std::static_pointer_cast<SALAM::SIToFP>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::SIToFP>(new SALAM::SIToFP(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createSIToFPInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-FPTrunc // ---------------------------------------------------------//

/**
 * @brief Models floating-point precision truncation ('fptrunc').
 */
class FPTrunc : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        FPTrunc(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~FPTrunc() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::FPTrunc> clone() const { return std::static_pointer_cast<SALAM::FPTrunc>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::FPTrunc>(new SALAM::FPTrunc(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createFPTruncInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-FPExt // -----------------------------------------------------------//

/**
 * @brief Models floating-point precision extension ('fpext').
 */
class FPExt : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        FPExt(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~FPExt() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::FPExt> clone() const { return std::static_pointer_cast<SALAM::FPExt>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::FPExt>(new SALAM::FPExt(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createFPExtInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-PtrToInt // --------------------------------------------------------//

/**
 * @brief Models pointer-to-integer cast ('ptrtoint') instruction.
 */
class PtrToInt : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:

    public:
        PtrToInt (uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~PtrToInt() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::PtrToInt> clone() const { return std::static_pointer_cast<SALAM::PtrToInt>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::PtrToInt>(new SALAM::PtrToInt(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createPtrToIntInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-IntToPtr // --------------------------------------------------------//

/**
 * @brief Models integer-to-pointer cast ('inttoptr') instruction.
 */
class IntToPtr : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        IntToPtr(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~IntToPtr() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::IntToPtr> clone() const { return std::static_pointer_cast<SALAM::IntToPtr>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::IntToPtr>(new SALAM::IntToPtr(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createIntToPtrInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);

/**
 * @brief Models bit-level type reinterpretation ('bitcast') instruction.
 */
class BitCast : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        BitCast(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~BitCast() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::BitCast> clone() const { return std::static_pointer_cast<SALAM::BitCast>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::BitCast>(new SALAM::BitCast(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createBitCastInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);

//---------------------------------------------------------------------------//
//--------- Other / Comparison Instructions ---------------------------------//
//---------------------------------------------------------------------------//

// SALAM-ICmp // ------------------------------------------------------------//

/**
 * @brief Models integer comparison ('icmp') instruction.
 */
class ICmp : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        uint64_t predicate;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:

    public:
        ICmp(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~ICmp() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::ICmp> clone() const { return std::static_pointer_cast<SALAM::ICmp>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::ICmp>(new SALAM::ICmp(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createICmpInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-FCmp // ------------------------------------------------------------//

/**
 * @brief Models floating-point comparison ('fcmp') instruction.
 */
class FCmp : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        uint64_t predicate;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:

    public:
        FCmp(uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~FCmp() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::FCmp> clone() const { return std::static_pointer_cast<SALAM::FCmp>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::FCmp>(new SALAM::FCmp(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createFCmpInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
//---------------------------------------------------------------------------//
//--------- Other / Edge Instructions ---------------------------------------//
//---------------------------------------------------------------------------//

// SALAM-Phi // -------------------------------------------------------------//

typedef std::pair<std::shared_ptr<SALAM::BasicBlock>, std::shared_ptr<SALAM::Value>> phiArgTy;

//typedef std::pair<std::shared_ptr<SALAM::Value>, std::shared_ptr<SALAM::Value> > phiNode;
typedef std::map<std::shared_ptr<SALAM::BasicBlock>, std::shared_ptr<SALAM::Value>> phiArgsTy;

/**
 * @brief Models SSA PHI node ('phi') selecting values based on active basic
 * block.
 */
class Phi : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        std::shared_ptr<SALAM::BasicBlock> previousBB;
        phiArgsTy phiArgs; // [BasicBlock, Value]
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:

    public:
        Phi (uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Phi() = default;
        void initialize(llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        void releaseGraphEdges() override;
        //virtual std::deque<uint64_t> runtimeInitialize() override;
        virtual std::vector<uint64_t> runtimeInitialize() override;
        bool isPhi() override { return true; }
        void setPrevBB(std::shared_ptr<SALAM::BasicBlock> prevBB);
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        virtual valueListTy getStaticDependencies() const override;
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::Phi> clone() const { return std::static_pointer_cast<SALAM::Phi>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Phi>(new SALAM::Phi(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createPHIInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-Call // ------------------------------------------------------------//

/**
 * @brief Models subroutine/kernel invocation ('call') instruction.
 */
class Call : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;
        std::shared_ptr<SALAM::Value> callee;
    protected:
    public:
        Call (uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Call() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        void releaseGraphEdges() override;
        bool isCall() override { return true; }
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::Value> getCalleeValue() { return callee; }
        std::shared_ptr<SALAM::Call> clone() const { return std::static_pointer_cast<SALAM::Call>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Call>(new SALAM::Call(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createCallInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
// SALAM-Select // ----------------------------------------------------------//

/**
 * @brief Models ternary conditional value selection ('select') instruction.
 */
class Select : public Instruction {
    private:
        std::vector< std::vector<uint64_t> > conditions;
        // conditions.at[0] == base params
        std::shared_ptr<SALAM::Value> condition;
        std::shared_ptr<SALAM::Value> trueValue;
        std::shared_ptr<SALAM::Value> falseValue;
        SALAM::Debugger *dbgr;
        uint64_t currentCycle;

    protected:
    public:
        // ---- Constructor
        Select (uint64_t id, gem5::SimObject * owner, bool dbg,
            uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
        ~Select() = default;
        void initialize (llvm::Value * irval,
                        irvmap * irmap,
                        SALAM::valueListTy * valueList);
        // std::shared_ptr<SALAM::Value> evaluate();
        // bool isTerminator() override { return true; }
        uint64_t getCycleCount() { return conditions.at(0).at(2); }
        void compute();
        void dump() { if (dbgr->enabled()) { dumper(); inst_dbg->dumper(static_cast<SALAM::Instruction*>(this));}}
        void dumper();
        std::shared_ptr<SALAM::Select> clone() const { return std::static_pointer_cast<SALAM::Select>(createClone()); }
        virtual std::shared_ptr<SALAM::Value> createClone() const override { return std::shared_ptr<SALAM::Select>(new SALAM::Select(*this)); }
};

std::shared_ptr<SALAM::Instruction>
createSelectInst(uint64_t id, gem5::SimObject * owner, bool dbg,
              uint64_t OpCode,
              uint64_t cycles,
              uint64_t fu);
//---------------------------------------------------------------------------//
//--------- End Instruction Classes -----------------------------------------//
//---------------------------------------------------------------------------//

}

#endif // __HWACC_LLVM_INSTRUCTION_HH__
