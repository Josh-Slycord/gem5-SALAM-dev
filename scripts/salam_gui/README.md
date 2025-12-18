# gem5-SALAM GUI

Interactive visualization tool for gem5-SALAM hardware accelerator simulations.

## Features

- **CDFG Visualizer**: Interactive Control Data Flow Graph viewer with pan/zoom
- **Performance Dashboard**: Key metrics at a glance
- **File Browser**: Navigate simulation outputs
- **Stats Parser**: Parse gem5 statistics into structured data

## Installation

```bash
# From gem5-SALAM directory
cd scripts/salam_gui

# Install dependencies
pip install -r requirements.txt

# Or install individually
pip install PyQt6 pyqtgraph networkx pydot pandas matplotlib PyYAML pyzmq
```

## Usage

```bash
# Launch GUI
python -m salam_gui

# Load specific simulation output
python -m salam_gui --load /path/to/m5out

# Load CDFG directly
python -m salam_gui --cdfg cdfg.dot

# Use dark theme
python -m salam_gui --dark
```

## Enabling CDFG Export in gem5-SALAM

To generate CDFG files for visualization, enable the export in your gem5 config:

```python
llvm_if = LLVMInterface(
    export_cdfg=True,
    cdfg_output="cdfg.dot"
)
```

Then visualize the generated `cdfg.dot` file with this GUI.

## Project Structure

```
salam_gui/
├── __init__.py          # Package init
├── __main__.py          # Entry point
├── app.py               # QApplication setup
├── main_window.py       # Main window with docking
├── widgets/
│   ├── cdfg_viewer.py   # CDFG graph widget
│   ├── stats_dashboard.py  # Metrics cards
│   └── file_browser.py  # File tree browser
├── data/
│   ├── dot_parser.py    # Parse CDFG .dot files
│   ├── stats_parser.py  # Parse gem5 stats
│   └── config_loader.py # Load YAML configs
├── requirements.txt
└── README.md
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+O | Open directory |
| Ctrl+G | Open CDFG file |
| Ctrl+T | Open stats file |
| Ctrl++ | Zoom in |
| Ctrl+- | Zoom out |
| Ctrl+0 | Fit to view |
| Ctrl+L | Connect live |
| Ctrl+Q | Quit |

## Roadmap

- [x] Phase 1: CDFG viewer + Stats dashboard (MVP)
- [ ] Phase 2: Queue monitor, FU utilization, power/area
- [ ] Phase 3: Real-time simulation connection
- [ ] Phase 4: Config editor, PDF export
