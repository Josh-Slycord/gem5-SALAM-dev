#ifndef __SALAM_VALUE_HH__
#define __SALAM_VALUE_HH__

/**
 * @file
 * @brief Base class for all LLVM CDFG values and SSA variables in SALAM.
 *
 * SALAM::Value is the root abstraction for all nodes in the Control-Data Flow
 * Graph (CDFG), including instructions, function arguments, basic blocks,
 * functions, and compile-time constants. It manages unique identifiers (UID),
 * bit-width and byte sizing, hardware return register bindings, IR text
 * representations, and cycle-breaking graph edge teardown.
 */

#include "debug_flags.hh"
#include "registers.hh"
#include "llvm/IR/Value.h"
#include "llvm/IR/GlobalVariable.h"
#include "llvm/IR/Constants.h"
#include "llvm/ADT/APSInt.h"
#include "llvm/ADT/APFloat.h"
#include <llvm-c/Core.h>

#include <map>
#include <memory>
#include <vector>

namespace gem5
{
    class SimObject;
}

namespace SALAM
{
/**
 * @brief Base class representing any SSA value or CDFG node in SALAM.
 *
 * Each Value corresponds to an LLVM IR entity and optionally binds to a
 * SALAM::Register for dynamic data storage and power/area tracking.
 */
class Value;
typedef std::pair<llvm::Value *, std::shared_ptr<Value>> irvmaptype;
typedef std::map<llvm::Value *, std::shared_ptr<Value>> irvmap;
typedef std::vector<std::shared_ptr<Value>> valueListTy;

/**
 * @brief Debugger helper for printing Value state.
 */
class Value
{
    public:

    protected:
        uint64_t uid = 0;
        uint64_t size = 0;
        gem5::SimObject * owner;
        std::string ir_string;
        std::string ir_stub;
        llvm::Type::TypeID valueTy;
        std::shared_ptr<SALAM::Register> returnReg;
        bool dbg = false;
        bool inst = false;

        void addRegister(llvm::Type *irtype, bool isTracked=true);
    #if USE_LLVM_AP_VALUES
        void addAPIntRegister(const llvm::APInt & val);
        void addAPIntRegister(const llvm::APSInt & val);
        void addAPFloatRegister(const llvm::APFloat & val);
    #else
        void addAPIntRegister(const uint64_t & val);
        void addAPFloatRegister(const uint64_t & val);
    #endif
        void addPointerRegister(bool isTracked=true,
                                bool isNull=false);
        void addPointerRegister(uint64_t val,
                                bool isTracked=true,
                                bool isNull=false);

        class Value_Debugger: public Debugger
        {
            public:
                Value_Debugger();
                ~Value_Debugger() = default;
                virtual void dumper(SALAM::Value * value);
        }; 

        Value_Debugger* value_dbg;
        Value(const SALAM::Value &copy_val);
        Value(std::shared_ptr<SALAM::Value> copy_val);

    public:
        /**
         * @brief Constructs a Value node with an ID, owning SimObject, and
         * debug flag.
         *
         * @param id Unique identifier for this value.
         * @param _owner Pointer to the owning gem5 SimObject.
         * @param _dbg Flag indicating whether debug logging is enabled.
         */
        Value(uint64_t id, gem5::SimObject * _owner, bool _dbg);
        /**
         * @brief Copy assignment operator.
         */
        Value& operator = (Value &copy_val);
        /**
         * @brief Equality operator comparing unique identifiers.
         */
        bool operator == (const Value &v) { return uid == v.uid; }
        /**
         * @brief Virtual destructor for Value.
         */
        ~Value();
        // Drop shared_ptr edges into the SALAM graph. Containers that own
        // the nodes call this before they release those nodes.
        /**
         * @brief Releases shared pointer cycles in the CDFG before
         * destruction.
         *
         * Containers holding graph nodes call this method prior to clearing
         * collections to avoid circular shared_ptr memory leaks.
         */
        virtual void releaseGraphEdges() {}
        /**
         * @brief Initializes the value from an LLVM IR Value and value map.
         *
         * @param irval Underlying LLVM IR Value.
         * @param irmap Map resolving LLVM Values to SALAM Values.
         */
        virtual void initialize(llvm::Value *irval,
                                SALAM::irvmap *irmap);
        /**
         * @brief Returns the bit-width of this value.
         *
         * @return Size in bits.
         */
        uint64_t getSize() { return size; }
        /**
         * @brief Returns the byte size of this value.
         *
         * @return Size rounded up to whole bytes.
         */
        uint64_t getSizeInBytes() {
            if (size==0)
                return 0;
            else
                return ((size - 1) >> 3) + 1;
        }
        /**
         * @brief Returns the unique identifier of this value.
         *
         * @return 64-bit UID.
         */
        uint64_t getUID() const { return uid; }
        /**
         * @brief Returns the hardware register bound to this value.
         *
         * @return Shared pointer to SALAM::Register.
         */
        std::shared_ptr<SALAM::Register> getReg() { return returnReg; }
        /**
         * @brief Returns the LLVM TypeID of this value.
         *
         * @return LLVM Type::TypeID enum value.
         */
        llvm::Type::TypeID getType() { return valueTy; }
        /**
         * @brief Returns the string representation of the LLVM IR.
         *
         * @return String of the IR instruction or value.
         */
        std::string getIRString() { return ir_string; }
        /**
         * @brief Returns the short stub string of the IR identifier.
         *
         * @return IR stub name.
         */
        std::string getIRStub() { return ir_stub; }
        /**
         * @brief Returns the owning gem5 SimObject.
         *
         * @return Pointer to SimObject.
         */
        gem5::SimObject * getOwner() { return owner; }
        /**
         * @brief Returns whether debug logging is active for this value.
         *
         * @return True if debug is enabled.
         */
        bool debug() { return dbg; }

        // Helper functions for setting the value of the return register directly from the value
        // Using these functions will increment the write counters on tracked registers
        // If you'd like to avoid incrementing write counters, directly pull the register and
        // use its appropriate write function
    #if USE_LLVM_AP_VALUES
        void setRegisterValue(const llvm::APInt &data);
        void setRegisterValue(const llvm::APFloat &data);
    #endif
        void setRegisterValue(const uint64_t data);
        void setRegisterValue(uint8_t * data);
        void setRegisterValue(bool data);
        void setRegisterValue(std::shared_ptr<SALAM::Register> reg);

        // Helper functions for getting the value of the return register directly from the value
        // Using these functions will increment the read counters on tracked registers
        // If you'd like to avoid incrementing read counters, directly pull the register and
        // use its appropriate read function
        virtual uint64_t getPtrRegValue() { return returnReg->getPtrData(); }
    #if USE_LLVM_AP_VALUES
        virtual llvm::APFloat getFloatRegValue() { return returnReg->getFloatData(); }
        virtual llvm::APSInt getIntRegValue() { return returnReg->getIntData(); }
    #else
        virtual uint64_t getFloatRegValue() { return returnReg->getFloatData(); }
        virtual float getFloatFromReg() { return returnReg->getFloat(); }
        virtual double getDoubleFromReg() { return returnReg->getDouble(); }
        virtual uint64_t getIntRegValue() { return returnReg->getIntData(); }
        virtual uint64_t getUIntRegValue() { return returnReg->getUnsignedInt(); }
        virtual int64_t getSIntRegValue() { return returnReg->getSignedInt(size); }
    #endif

        /**
         * @brief Identifies whether this Value is a compile-time constant.
         *
         * @return True if constant, false otherwise.
         */
        virtual bool isConstant() { return false; }
        /**
         * @brief Identifies whether this Value is a global constant.
         *
         * @return True if global constant, false otherwise.
         */
        virtual bool isGlobalConstant() { return false; }
        /**
         * @brief Identifies whether this Value is a function argument.
         *
         * @return True if argument, false otherwise.
         */
        virtual bool isArgument() { return false; }
        /**
         * @brief Identifies whether this Value is a Function.
         *
         * @return True if function, false otherwise.
         */
        virtual bool isFunction() { return false; }
        /**
         * @brief Identifies whether this Value is a BasicBlock.
         *
         * @return True if basic block, false otherwise.
         */
        virtual bool isBasicBlock() { return false; }
        /**
         * @brief Identifies whether this Value is an Instruction.
         *
         * @return True if instruction, false otherwise.
         */
        virtual bool isInstruction() { return false; }
        /**
         * @brief Returns the opcode if this Value is an Instruction.
         *
         * @return Opcode identifier, or -1 if not an instruction.
         */
        virtual uint64_t getOpode() { return -1; }

        /**
         * @brief Dumps debug representation of this value.
         */
        void value_dump() { if (dbg) value_dbg->dumper(this); }
        /**
         * @brief Formats the contents of the return register as a string.
         *
         * @return Formatted register data string.
         */
        std::string registerDataString() { return returnReg->dataString(); }
        /**
         * @brief Creates a polymorphic clone of this Value.
         *
         * @return Shared pointer to cloned Value.
         */
        std::shared_ptr<SALAM::Value> clone() const { return createClone(); }
        /**
         * @brief Factory method for creating polymorphic clones.
         *
         * @return Shared pointer to cloned Value instance.
         */
        virtual std::shared_ptr<SALAM::Value> createClone() const { return std::shared_ptr<SALAM::Value>(new SALAM::Value(*this)); }

};
} // End SALAM Namespace


#endif //__SALAM_VALUE_HH__
