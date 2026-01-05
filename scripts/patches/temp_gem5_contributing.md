# Contributing to gem5-SALAM

## Development Setup

### Prerequisites
- Ubuntu 20.04 (WSL or native)
- Python 3.8+
- GCC/G++ toolchain
- SCons build system
- ARM cross-compiler (for benchmarks)

### Clone and Build
```bash
cd ~/gem5-SALAM-dev
scons build/ARM/gem5.opt -j$(nproc)
```

### GUI Setup
```bash
pip install PySide6 pyqtgraph networkx pydot pandas matplotlib PyYAML pyzmq
python -m scripts.salam_gui
```

---

## Code Style

### C++ (src/)
- Follow gem5 coding style
- Use Doxygen comments for documentation
- Header guards: `#ifndef __MODULE_NAME_HH__`

```cpp
/**
 * @file MyClass.hh
 * @brief Brief description of the class
 */
class MyClass : public BaseClass {
  public:
    /** @brief Constructor description */
    MyClass();

    /**
     * @brief Method description
     * @param arg Argument description
     * @return Return value description
     */
    int myMethod(int arg);
};
```

### Python (scripts/, configs/)
- Use Google-style docstrings
- Type hints for function signatures
- 4-space indentation

```python
def process_data(input_path: Path, output_dir: Path) -> bool:
    """Process simulation data.

    Args:
        input_path: Path to input file
        output_dir: Output directory

    Returns:
        True if successful
    """
    pass
```

---

## Project Structure

```
gem5-SALAM-dev/
├── src/                    # C++ source (gem5 + SALAM extensions)
│   └── hwacc/              # Hardware accelerator models
├── configs/                # Python simulation configurations
│   └── SALAM/              # SALAM-specific configs
├── scripts/
│   ├── salam_gui/          # Visualization GUI (PySide6)
│   └── generate_docs.py    # Documentation generator
├── benchmarks/             # Benchmark applications
│   ├── common/             # Shared utilities (DMA, m5ops)
│   └── legacy/             # Classic benchmarks (GEMM, FFT, etc.)
├── SALAM-Configurator/     # Config generator tool
├── gem5-SALAM-gui/         # CLI/installer tools
├── salam_config/           # Configuration utilities
└── docs/                   # Generated documentation
```

---

## Building

### gem5 Simulator
```bash
# Optimized build
scons build/ARM/gem5.opt -j$(nproc)

# Debug build
scons build/ARM/gem5.debug -j$(nproc)

# Fast build (no debug info)
scons build/ARM/gem5.fast -j$(nproc)
```

### Benchmarks
```bash
cd benchmarks
make all        # Build all benchmarks
make clean      # Clean build artifacts
```

### Documentation
```bash
python scripts/generate_docs.py           # Generate all docs
python scripts/generate_docs.py --serve   # Generate and serve locally
```

---

## Running Simulations

### Using Shell Scripts
```bash
# Run GEMM benchmark
./run_gemm.sh

# Run system validation
./systemValidation.sh

# Run LeNet-5
./runLeNet5.sh
```

### Using GUI
```bash
python -m scripts.salam_gui
# File → Open Directory → Select m5out folder
```

### Using CLI (gem5-SALAM-gui)
```bash
cd gem5-SALAM-gui
python cli.py status                           # Check WSL status
python cli.py list -d Ubuntu-20.04             # List benchmarks
python cli.py simulate -d Ubuntu-20.04 -b gemm # Run simulation
```

---

## Testing

### Run Benchmarks
```bash
# System validation suite
./systemValidation.sh

# Individual benchmark
cd benchmarks/legacy/gemm
make
```

### Verify Build
```bash
./build/ARM/gem5.opt --help
```

---

## Commit Messages

Use conventional commit format:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `refactor:` Code refactoring
- `test:` Adding tests
- `build:` Build system changes

Example:
```
feat: Add streaming DMA support for neural network benchmarks

- Implemented StreamDMA class in src/hwacc/
- Added benchmark configs for streaming mode
- Updated documentation

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Adding New Components

### New Benchmark
1. Create directory: `benchmarks/legacy/mybench/`
2. Add source files: `bench/mybench.c`, `bench/mybench.h`
3. Create `config.yml` with accelerator configuration
4. Add host code in `host/main.cpp`
5. Create `Makefile`
6. Add to `benchmarks/Makefile` if needed

### New GUI Widget
1. Create widget in `scripts/salam_gui/widgets/mywidget.py`
2. Add to `widgets/__init__.py`
3. Import in `main_window.py`
4. Create dock widget and add to layout

### New Accelerator Model
1. Add C++ files in `src/hwacc/`
2. Create SimObject in `src/hwacc/MyAccel.py`
3. Update SConscript
4. Rebuild: `scons build/ARM/gem5.opt`

---

## Output Directories

Simulation outputs go to designated directories:
- `BM_ARM_OUT/` - Benchmark outputs (in .gitignore)
- `m5out/` - Default gem5 output (in .gitignore)

**Do NOT** create test/debug folders at project root. Use:
```bash
./build/ARM/gem5.opt --outdir=BM_ARM_OUT/mytest configs/...
```

---

## Documentation

### Generate All Docs
```bash
python scripts/generate_docs.py
```

### View Documentation
```bash
python scripts/generate_docs.py --serve
# Open http://localhost:8000
```

### In-App Help
Press **F1** in the GUI or use **Help → Help Contents**

---

## Coordination (Multi-Instance)

When multiple Claude instances work on this project:

### Plan File Location
```
C:\Users\Local_Only_Slycord\.claude\plans\
```

### Protocol
1. Check for existing plan files before starting
2. Create plan file with unique ID
3. List files being modified
4. Update status periodically
5. Clean up when done

See `C:\Users\Local_Only_Slycord\CONTRIBUTING.md` for full protocol.

---

## Questions?

Open an issue or check existing documentation in `docs/`.
