#ifndef __HWACC_LLVM_IR_PARSER_HH__
#define __HWACC_LLVM_IR_PARSER_HH__

/**
 * @file
 * @brief Declares parser functions for converting LLVM IR/bitcode into SALAM
 * CDFG models.
 */

#include <llvm/IR/Module.h>
#include <llvm/IRReader/IRReader.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/Support/SourceMgr.h>
#include <llvm/Support/MemoryBuffer.h>
#include <llvm/Support/ErrorOr.h>
#include <llvm/Bitcode/BitcodeWriter.h>
#include <llvm/Bitcode/BitcodeReader.h>
#include <llvm/Support/raw_ostream.h>
#include "instruction.hh"
#include <string>
#include <iostream>
#include <vector>
#include <memory>

namespace SALAM {
    /**
     * @brief Parses an LLVM IR or bitcode file and registers instructions.
     *
     * @param file Path to the LLVM IR or bitcode file.
     * @return Status code (0 on success).
     */
    int ir_parser(std::string file);  
    /**
     * @brief Converts an LLVM Instruction into a SALAM::Instruction and
     * appends
     * it.
     *
     * @param inst Pointer to LLVM Instruction.
     * @param inst_List Vector of SALAM::Instruction shared pointers.
     */
    void register_instruction(llvm::Instruction * inst, std::vector<std::shared_ptr<SALAM::Instruction>> &inst_List);

}

#endif //__HWACC_LLVM_IR_PARSER_HH__
