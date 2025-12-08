#include "ir_parse.hh"

#include "base/logging.hh"
#include "base/trace.hh"
#include "debug/LLVMParse.hh"
#include "instruction.hh"

namespace SALAM {
    int ir_parser(std::string file) {
        llvm::StringRef filename = file;
        llvm::LLVMContext context;
        llvm::SMDiagnostic error;

        // Load LLVM IR file
        llvm::ErrorOr<std::unique_ptr<llvm::MemoryBuffer>> fileOrErr = llvm::MemoryBuffer::getFileOrSTDIN(filename);
        if (std::error_code ec = fileOrErr.getError()) {
            panic("SALAM Error: Opening input file '%s': %s",
                  file.c_str(), ec.message().c_str());
        }

        // Load LLVM Module
        llvm::ErrorOr<std::unique_ptr<llvm::Module>> moduleOrErr = llvm::parseIRFile(filename, error, context);
        if (std::error_code ec = moduleOrErr.getError()) {
            panic("SALAM Error: Reading Module '%s': %s",
                  file.c_str(), ec.message().c_str());
        }

        std::unique_ptr<llvm::Module> m(llvm::parseIRFile(filename, error, context));
        if(!m) return 4;

        if (DTRACE(LLVMParse)) {
            std::cout << "Successfully Loaded Module:" << std::endl;
            std::cout << " Name: " << m->getName().str() << std::endl;
            std::cout << " Target: " << m->getTargetTriple() << std::endl;
        }

        std::vector<std::shared_ptr<SALAM::Instruction>> inst_List;

        for (auto &f : m->getFunctionList()) {
            if (DTRACE(LLVMParse))
                std::cout << " Function: " << f.getName().str() << std::endl;
            for (auto &bb : f.getBasicBlockList()) {
                if (DTRACE(LLVMParse))
                    std::cout << "  BB: " << bb.getName().str() << std::endl;
                for (auto &llvm_inst : bb) {
                    SALAM::register_instruction(llvm_inst.clone(), inst_List);
                }
            }
        }
        
        // Test Function Only
        for (auto inst_list_it = inst_List.begin() ; inst_list_it != inst_List.end(); inst_list_it++) {
            (*inst_list_it)->test();
        }
        
        return 0;
    }

    void register_instruction(llvm::Instruction * inst, std::vector<std::shared_ptr<SALAM::Instruction>> &inst_List) {       
        std::shared_ptr<SALAM::Instruction> newInst(new SALAM::Instruction(inst));
        inst_List.push_back(std::move(newInst));
    }


}