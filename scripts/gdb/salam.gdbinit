# =============================================================================
# gem5-SALAM GDB Initialization File
# =============================================================================
# Source this file in GDB: source scripts/gdb/salam.gdbinit
# Or use: gdb -x scripts/gdb/salam.gdbinit --args ./build/ARM/gem5.debug ...
# =============================================================================

# Set pagination off for long outputs
set pagination off

# Print array limits
set print array on
set print array-indexes on

# Don't stop on SIGPIPE (common in gem5)
handle SIGPIPE nostop noprint

# =============================================================================
# SALAM-Specific Breakpoints
# =============================================================================

# Break when compute begins
define salam-break-compute
  break gem5::LLVMInterface::compute
  echo Breakpoint set at LLVMInterface::compute\n
end
document salam-break-compute
Set breakpoint at accelerator compute entry point.
Use: salam-break-compute
end

# Break on DMA response
define salam-break-dma
  break gem5::NoncoherentDma::recvTimingResp
  echo Breakpoint set at NoncoherentDma::recvTimingResp\n
end
document salam-break-dma
Set breakpoint when DMA receives timing response.
Use: salam-break-dma
end

# Break on instruction scheduling
define salam-break-schedule
  break gem5::BasicBlock::scheduleInstructions
  echo Breakpoint set at BasicBlock::scheduleInstructions\n
end
document salam-break-schedule
Set breakpoint at basic block instruction scheduling.
Use: salam-break-schedule
end

# Break on memory requests
define salam-break-memreq
  break gem5::CommInterface::recvTimingResp
  echo Breakpoint set at CommInterface::recvTimingResp\n
end
document salam-break-memreq
Set breakpoint when CommInterface receives memory response.
Use: salam-break-memreq
end

# Break on accelerator start
define salam-break-start
  break gem5::CommInterface::start
  echo Breakpoint set at CommInterface::start\n
end
document salam-break-start
Set breakpoint at accelerator start.
Use: salam-break-start
end

# Break on accelerator finish
define salam-break-finish
  break gem5::CommInterface::finish
  echo Breakpoint set at CommInterface::finish\n
end
document salam-break-finish
Set breakpoint when accelerator finishes.
Use: salam-break-finish
end

# =============================================================================
# gem5 Utility Commands
# =============================================================================

# Dump event queue
define salam-events
  call gem5::debug::eventqDump()
end
document salam-events
Dump the current gem5 event queue.
Use: salam-events
end

# Get current tick
define salam-tick
  print gem5::curTick()
end
document salam-tick
Print the current simulation tick.
Use: salam-tick
end

# Enable a debug flag at runtime
define salam-flag-on
  call gem5::debug::setFlag($arg0)
  printf "Debug flag '%s' enabled\n", $arg0
end
document salam-flag-on
Enable a debug flag at runtime.
Use: salam-flag-on "SALAMExec"
end

# Disable a debug flag at runtime
define salam-flag-off
  call gem5::debug::clearFlag($arg0)
  printf "Debug flag '%s' disabled\n", $arg0
end
document salam-flag-off
Disable a debug flag at runtime.
Use: salam-flag-off "SALAMExec"
end

# =============================================================================
# Quick Setup Commands
# =============================================================================

# Set all common SALAM breakpoints
define salam-break-all
  salam-break-start
  salam-break-compute
  salam-break-finish
  echo All common SALAM breakpoints set\n
end
document salam-break-all
Set all common SALAM breakpoints (start, compute, finish).
Use: salam-break-all
end

# =============================================================================
# Help
# =============================================================================

define salam-help
  echo \n=== SALAM GDB Commands ===\n
  echo \nBreakpoints:\n
  echo   salam-break-compute   - Break at compute entry\n
  echo   salam-break-dma       - Break on DMA response\n
  echo   salam-break-schedule  - Break at BB scheduling\n
  echo   salam-break-memreq    - Break on memory response\n
  echo   salam-break-start     - Break at accelerator start\n
  echo   salam-break-finish    - Break at accelerator finish\n
  echo   salam-break-all       - Set all common breakpoints\n
  echo \nUtilities:\n
  echo   salam-events          - Dump event queue\n
  echo   salam-tick            - Print current tick\n
  echo   salam-flag-on "FLAG"  - Enable debug flag\n
  echo   salam-flag-off "FLAG" - Disable debug flag\n
  echo \n
end
document salam-help
Show available SALAM GDB commands.
Use: salam-help
end

# Print welcome message
echo \n
echo =============================================\n
echo   gem5-SALAM GDB Environment Loaded\n
echo   Type 'salam-help' for available commands\n
echo =============================================\n
echo \n
