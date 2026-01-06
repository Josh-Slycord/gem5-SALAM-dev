# gem5-SALAM Installer

A graphical installer and build tool for gem5-SALAM (System for Automated Logic Analysis Modeling).

## Requirements

- Windows 10/11 with WSL2 installed
- Python 3.8 or later (Windows)
- A WSL distribution (Ubuntu recommended)

## Quick Start

1. **Install Python dependencies:**
   ```
   pip install -r requirements.txt
   ```

2. **Run the installer:**
   ```
   python installer.py
   ```
   Or double-click `run_installer.bat`

3. **In the GUI:**
   - Verify WSL is detected and select your distribution
   - Set the path to your gem5-SALAM directory
   - Click "Install Dependencies" to install all required packages
   - Click "Build gem5-SALAM" to compile the simulator
   - Click "Build CACTI" to compile the memory modeling tool

## Features

- **WSL Detection**: Automatically detects WSL installation and available distributions
- **Dependency Management**: Installs all required packages for gem5-SALAM
- **Build Automation**: Compiles gem5-SALAM and CACTI with progress tracking
- **Live Output**: Shows real-time build output in the console
- **Interactive Tutorial**: Step-by-step onboarding via Help → Getting Started Tutorial

## Project Structure

```
gem5-SALAM-gui/
├── installer.py          # Main entry point
├── run_installer.bat     # Windows launcher
├── requirements.txt      # Python dependencies
├── configs/
│   └── default_config.yaml
├── scripts/
│   ├── install_deps.sh   # Dependency installer
│   ├── build_gem5.sh     # gem5 build script
│   └── build_cacti.sh    # CACTI build script
├── tutorials/
│   └── getting_started.yaml  # Interactive tutorial definition
└── src/
    ├── gui/
    │   └── main_window.py
    ├── tutorial_overlay/     # Tutorial/onboarding system
    │   ├── core/             # Schema, targeting, manager
    │   ├── widgets/          # Spotlight, tooltip, navigator
    │   ├── animations/       # Highlight effects
    │   └── loaders/          # YAML tutorial loader
    └── utils/
        ├── wsl.py        # WSL utilities
        └── config.py     # Configuration management
```

## Dependencies Installed

The installer sets up the following in your WSL environment:

- **Build tools**: gcc, g++, make, cmake
- **Python**: python3, pip3, scons
- **LLVM/Clang**: For LLVM IR compilation
- **ARM toolchain**: arm-none-eabi-gcc for cross-compilation
- **gem5 dependencies**: protobuf, boost, gperftools, etc.
- **32-bit libraries**: Required for CACTI

## Troubleshooting

### WSL not detected
- Ensure WSL is installed: `wsl --install`
- Restart your terminal after installation

### Build failures
- Check the output console for specific errors
- Ensure all dependencies were installed successfully
- Try running with fewer parallel jobs if you run out of memory

### Permission errors
- The installer uses `sudo` inside WSL for package installation
- You may be prompted for your WSL password

## License

This installer is part of the gem5-SALAM project.
