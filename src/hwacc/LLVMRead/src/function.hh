#ifndef __SALAM_FUNCTION_HH__
#define __SALAM_FUNCTION_HH__

/**
 * @file
 * @brief Declares the SALAM::Function CDFG container representing an LLVM
 * function.
 *
 * A Function manages the collection of basic blocks, formal arguments, and
 * active invocation instances for an accelerator kernel or subroutine.
 */

#include "value.hh"
#include "basic_block.hh"
#include "llvm/IR/Function.h"
#include "llvm/IR/DataLayout.h"

namespace SALAM {
	/**
	 * @brief CDFG container for an LLVM function.
	 *
	 * Extends SALAM::Value to represent a function graph in the accelerator.
	 * Manages basic block ordering, entry block resolution, argument registers,
	 * top-level kernel distinction, and active instance limits.
	 */
	class Function : public Value {
	private:
		std::vector<std::shared_ptr<SALAM::BasicBlock>> bbList;
		std::vector<std::shared_ptr<SALAM::Value>> arguments;
		bool top;
		unsigned activeInstances = 0;
		unsigned instanceLimit = 1;
	public:
		/**
		 * @brief Constructs a Function node.
		 *
		 * @param id Unique identifier for this function.
		 * @param owner Pointer to the owning gem5 SimObject.
		 * @param dbg Flag indicating whether debug logging is enabled.
		 */
		Function(uint64_t id, gem5::SimObject * owner, bool dbg);
		/**
		 * @brief Initializes the function from LLVM IR and builds basic blocks.
		 *
		 * @param irval Underlying LLVM IR Value representation.
		 * @param vmap Map resolving LLVM Values to SALAM Values.
		 * @param valueList Global list of values in the accelerator CDFG.
		 * @param topName Name of the top-level kernel function.
		 */
		void initialize(llvm::Value * irval, irvmap *vmap, SALAM::valueListTy *valueList, std::string topName);
		/**
		 * @brief Releases shared pointer cycles in the CDFG before destruction.
		 */
		void releaseGraphEdges() override;
		/**
		 * @brief Checks if this is the top-level kernel function.
		 *
		 * @return True if this function is top-level.
		 */
		bool isTop() { return top; }
		/**
		 * @brief Sets whether this function is the top-level kernel.
		 *
		 * @param isTop Flag indicating top-level status.
		 */
		void setTop(bool isTop) { top = isTop; }
		/**
		 * @brief Identifies whether this Value is a Function.
		 *
		 * @return Always true for Function instances.
		 */
		virtual bool isFunction() { return true; }
		/**
		 * @brief Returns a pointer to the list of basic blocks in this
		 * function.
		 *
		 * @return Pointer to vector of basic block shared pointers.
		 */
		std::vector<std::shared_ptr<SALAM::BasicBlock>> * getBBList() { return &bbList; }
		/**
		 * @brief Returns a pointer to the formal arguments list.
		 *
		 * @return Pointer to vector of argument Value shared pointers.
		 */
		std::vector<std::shared_ptr<SALAM::Value>> * getArguments() { return & arguments; }
		/**
		 * @brief Returns the entry basic block of the function.
		 *
		 * @return Shared pointer to the first basic block.
		 */
		std::shared_ptr<SALAM::BasicBlock> entry() { return bbList.front(); }
		/**
		 * @brief Increments the count of currently active function invocations.
		 */
		void addInstance() { activeInstances++; }
		/**
		 * @brief Decrements the count of active function invocations.
		 */
		void removeInstance() { if (activeInstances>0) activeInstances--; }
		/**
		 * @brief Checks whether another instance of this function can launch.
		 *
		 * @return True if activeInstances is below instanceLimit.
		 */
		bool canLaunch() { return activeInstances < instanceLimit; }
	};
}

#endif //__SALAM_FUNCTION_HH__
