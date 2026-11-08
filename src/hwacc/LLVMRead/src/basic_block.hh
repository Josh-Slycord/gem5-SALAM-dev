#ifndef __SALAM_BASIC_BLOCK_HH__
#define __SALAM_BASIC_BLOCK_HH__

/**
 * @file
 * @brief Declares the SALAM::BasicBlock CDFG node representing an LLVM basic
 * block.
 *
 * A BasicBlock encapsulates a linear sequence of instructions with single-
 * entry
 * and single-exit semantics within an accelerator kernel CDFG. It tracks
 * control-flow predecessors for branch validation and PHI node resolution, and
 * manages its contained instructions.
 */
//------------------------------------------//
#include "debug_flags.hh"
#include "value.hh"
#include "instruction.hh"
#include "llvm/IR/BasicBlock.h"
#include "llvm/IR/Instruction.h"
//------------------------------------------//
#include <memory>
#include <iomanip>
#include <string>
#include <sstream>
#include <iostream>
#include <iterator>
#include <algorithm>
//------------------------------------------//

namespace SALAM {
  class Instruction; // Do not remove

  /**
   * @brief CDFG basic block container representing a sequence of instructions.
   *
   * Extends SALAM::Value to model an LLVM basic block. Manages a list of
   * instructions and predecessor basic blocks for control flow traversal.
   */
  class BasicBlock : public Value {
    private:
      std::vector<std::shared_ptr<SALAM::BasicBlock>> predecessors;
      std::vector<std::shared_ptr<SALAM::Instruction>> instructions;
    protected:
      /**
       * @brief Debug helper for printing basic block state.
       */
      class BasicBlock_Debugger: public Debugger
        {
            public:
                BasicBlock_Debugger();
                ~BasicBlock_Debugger() = default;
                virtual void dumper(SALAM::BasicBlock * bb);
        }; 

       BasicBlock_Debugger* bb_dbg;  
    public:
      /**
       * @brief Constructs a BasicBlock node with the given UID and owner.
       *
       * @param id Unique identifier for this basic block.
       * @param owner Pointer to the owning gem5 SimObject.
       * @param dbg Flag indicating whether debug logging is enabled.
       */
      BasicBlock(uint64_t id, gem5::SimObject * owner, bool dbg);
      /**
       * @brief Destructor for BasicBlock.
       */
      ~BasicBlock();
      /**
       * @brief Identifies whether this Value is a BasicBlock.
       *
       * @return Always true for BasicBlock instances.
       */
      virtual bool isBasicBlock() { return true; }
      /**
       * @brief Initializes the basic block from an LLVM IR Value.
       *
       * Populates predecessor list and contained instructions using the
       * provided value map.
       *
       * @param irval Underlying LLVM IR Value representation.
       * @param vmap Map resolving LLVM Values to SALAM Values.
       * @param valueList Global list of values in the accelerator CDFG.
       */
      void initialize(llvm::Value * irval, irvmap *vmap, SALAM::valueListTy *valueList);
      /**
       * @brief Releases shared pointer cycles in the CDFG before destruction.
       */
      void releaseGraphEdges() override;
      /**
       * @brief Returns a pointer to the list of contained instructions.
       *
       * @return Pointer to vector of instruction shared pointers.
       */
      std::vector<std::shared_ptr<SALAM::Instruction> > * Instructions() { return &instructions; }
      /**
       * @brief Dumps debug information for this basic block if debugging is
       * enabled.
       */
      void dump() { if (dbg) bb_dbg->dumper(this); }
      /**
       * @brief Checks if a given basic block is a valid control-flow
       * predecessor.
       *
       * @param bb Candidate predecessor basic block.
       * @return True if bb is in the predecessor list, false otherwise.
       */
      bool validPredecessor(std::shared_ptr<SALAM::BasicBlock> bb) {
        auto it = std::find(predecessors.begin(), predecessors.end(), bb);
        if (it == predecessors.end()) return false;
        return true;
      }
  };
}

#endif //__SALAM_BASIC_BLOCK_HH__
