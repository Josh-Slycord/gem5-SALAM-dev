# ==============================================================================
# SALAM Research Workbench - 1-Click Windows Desktop Launcher
# Launches the Linux PySide6 GUI inside WSL2 using WSLg seamless windowing
# ==============================================================================

$Distro = "gem5-salam-prebuilt"
$AppPath = "/home/jslycord/gem5-SALAM-dev/workbench"

Write-Host "Launching SALAM Research Workbench from distro [$Distro]..." -ForegroundColor Cyan

# Execute inside WSL2 with Python and Qt environment configured
wsl.exe -d $Distro --cd $AppPath -- bash -c "export PYTHONPATH=/home/jslycord/gem5-SALAM-dev/workbench:`$PYTHONPATH; export PATH=/usr/lib/llvm-14/bin:/home/jslycord/.local/bin:`$PATH; python3 -m salam_workbench.configurator_app"
