# ==============================================================================
# simulation_panel.py - Simulation Runner Widget
# ==============================================================================
"""Simulation Panel Widget for gem5-SALAM GUI.

This module provides the SimulationPanel widget, which enables running
gem5-SALAM simulations directly from the GUI with WSL (Windows Subsystem
for Linux) integration.

Features:
    - WSL distribution detection and selection
    - M5_PATH environment variable discovery
    - Benchmark selection (sys_validation, legacy)
    - Build type selection (opt, debug, fast)
    - CPU type selection (DerivO3CPU, TimingSimpleCPU, etc.)
    - Debug flag presets and custom flags
    - Real-time output console with ANSI color support
    - Simulation progress monitoring

Panel Layout::

    +---------------------------------------------------------------+
    |  gem5-SALAM Simulation                                         |
    +---------------------+---------------------+--------------------+
    | WSL Environment     | Debug Options       | Simulation Options |
    | +- Distribution    | +- Preset          | +- Build Type      |
    | +- M5_PATH         | +- Custom Flags    | +- CPU Type        |
    |                    | +- Time Range      | +- Memory          |
    | Benchmark          | +- Results Output  | +- Caches          |
    | +- Type            |                    |                    |
    | +- Name            |                    | [Run] [Stop]       |
    +---------------------+---------------------+--------------------+
    | Simulation Output                                              |
    | +---------------------------------------------------------+   |
    | | ==> Starting simulation                                  |   |
    | | Distro: Ubuntu-20.04                                    |   |
    | | Benchmark: gemm                                          |   |
    | | ...                                                      |   |
    | +---------------------------------------------------------+   |
    +---------------------------------------------------------------+

Debug Flag Presets:
    | Preset          | Flags Enabled                              |
    |-----------------|-------------------------------------------|
    | SALAMQuick      | Basic execution flow                      |
    | SALAMVerbose    | Detailed execution output                 |
    | SALAMStallDebug | Stall analysis flags                      |
    | SALAMDataDebug  | Data flow tracing                         |
    | SALAMDMADebug   | DMA operation tracing                     |
    | SALAMPerfDebug  | Performance analysis                      |
    | SALAMAll        | All SALAM flags enabled                   |

Example:
    The panel is typically added to MainWindow as a dock widget::

        from salam_gui.widgets.simulation_panel import SimulationPanel

        panel = SimulationPanel()
        panel.simulation_completed.connect(self.load_simulation_output)

See Also:
    - MainWindow: Hosts this panel as a dock widget
    - WSLSelectorWidget: WSL distribution selector
    - DebugOptionsWidget: Debug flag configuration
"""


__version__ = "3.0.0.pre[1.0.0]"

import subprocess
import re
import json
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QTextEdit,
    QGroupBox, QProgressBar, QTreeWidget, QTreeWidgetItem,
    QSplitter, QCheckBox, QSpinBox, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal, QProcess
from PySide6.QtGui import QFont, QTextCursor, QColor


# ANSI color code mapping
ANSI_COLORS = {
    '30': '#000000', '31': '#cc0000', '32': '#00cc00', '33': '#cccc00',
    '34': '#5555ff', '35': '#cc00cc', '36': '#00cccc', '37': '#cccccc',
    '90': '#666666', '91': '#ff5555', '92': '#55ff55', '93': '#ffff55',
    '94': '#5555ff', '95': '#ff55ff', '96': '#55ffff', '97': '#ffffff',
}


def ansi_to_html(text: str) -> str:
    """Convert ANSI color codes to HTML spans."""
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    ansi_pattern = re.compile(r'\x1b\[([0-9;]*)m')

    result = []
    last_end = 0
    open_spans = 0

    for match in ansi_pattern.finditer(text):
        result.append(text[last_end:match.start()])
        codes = match.group(1).split(';')

        for code in codes:
            if code == '0' or code == '':
                result.append('</span>' * open_spans)
                open_spans = 0
            elif code == '1':
                result.append('<span style="font-weight:bold;">')
                open_spans += 1
            elif code in ANSI_COLORS:
                result.append(f'<span style="color:{ANSI_COLORS[code]};">')
                open_spans += 1

        last_end = match.end()

    result.append(text[last_end:])
    result.append('</span>' * open_spans)
    return ''.join(result)


@dataclass
class WSLDistro:
    """Information about a WSL distribution."""
    name: str
    version: int
    is_default: bool


@dataclass
class WSLStatus:
    """WSL installation status."""
    installed: bool
    version: str
    distros: List[WSLDistro]


def is_running_in_wsl() -> bool:
    """Check if we're running inside WSL."""
    try:
        with open('/proc/version', 'r') as f:
            version_info = f.read().lower()
            return 'microsoft' in version_info or 'wsl' in version_info
    except:
        return False


def get_current_wsl_distro() -> str:
    """Get the current WSL distro name when running inside WSL."""
    import os
    # WSL_DISTRO_NAME env var has the actual distro name (e.g., "Ubuntu-20.04")
    distro_name = os.environ.get("WSL_DISTRO_NAME")
    if distro_name:
        return distro_name
    # Fallback to /etc/os-release (gives generic name like "Ubuntu")
    try:
        with open("/etc/os-release", "r") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=")[1].strip().strip('"')
    except:
        pass
    return "Linux"

def get_wsl_status() -> WSLStatus:
    """Get WSL installation status."""
    distros = []
    running_in_wsl = is_running_in_wsl()
    current_distro = get_current_wsl_distro() if running_in_wsl else None

    # Use wsl.exe when inside WSL, wsl when on Windows
    wsl_cmd = 'wsl.exe' if running_in_wsl else 'wsl'

    try:
        # Get WSL version
        result = subprocess.run(
            [wsl_cmd, '--version'],
            capture_output=True, text=True, timeout=10
        )
        version = result.stdout.strip() if result.returncode == 0 else ""
        if running_in_wsl:
            version = "Running inside WSL"

        # List distributions
        result = subprocess.run(
            [wsl_cmd, '-l', '-v'],
            capture_output=True, timeout=10
        )

        if result.returncode == 0:
            # Decode with utf-16-le (Windows default for wsl -l)
            try:
                output = result.stdout.decode('utf-16-le')
            except:
                output = result.stdout.decode('utf-8', errors='ignore')

            for line in output.strip().split(chr(10))[1:]:  # Skip header
                line = line.strip()
                if not line:
                    continue

                is_default = line.startswith('*')
                line = line.lstrip('* ')

                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    try:
                        ver = int(parts[1])
                    except ValueError:
                        ver = 2

                    # Mark current distro as default when running inside WSL
                    if running_in_wsl and name == current_distro:
                        is_default = True

                    distros.append(WSLDistro(name=name, version=ver, is_default=is_default))

        return WSLStatus(installed=True, version=version, distros=distros)

    except FileNotFoundError:
        # wsl.exe not available - fall back to just current distro
        if running_in_wsl and current_distro:
            distros.append(WSLDistro(name=current_distro, version=2, is_default=True))
            return WSLStatus(installed=True, version="Running inside WSL", distros=distros)
        return WSLStatus(installed=False, version="", distros=[])
    except Exception as e:
        print(f"Error checking WSL: {e}")
        # Fall back to current distro if inside WSL
        if running_in_wsl and current_distro:
            distros.append(WSLDistro(name=current_distro, version=2, is_default=True))
            return WSLStatus(installed=True, version="Running inside WSL", distros=distros)
        return WSLStatus(installed=False, version=str(e), distros=[])

def get_m5_path(distro: str) -> str:
    """Get M5_PATH from WSL environment."""
    cmd = "grep -h 'export M5_PATH=' ~/.bashrc ~/.profile 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '\"'"
    try:
        if is_running_in_wsl():
            result = subprocess.run(
                ['bash', '-c', cmd],
                capture_output=True, text=True, timeout=10
            )
        else:
            result = subprocess.run(
                ['wsl', '-d', distro, 'bash', '-c', cmd],
                capture_output=True, text=True, timeout=10
            )
        return result.stdout.strip()
    except Exception:
        return ""

class SimulationWorker(QThread):
    """Worker thread for running simulations."""

    output = Signal(str)
    simulation_done = Signal(bool, str)  # Renamed from 'finished' to avoid QThread conflict

    def __init__(self, distro: str, command: str):
        super().__init__()
        self.distro = distro
        self.command = command
        self._cancelled = False
        self.process: Optional[subprocess.Popen] = None

    def cancel(self):
        self._cancelled = True
        if self.process:
            self.process.terminate()

    def run(self):
        try:
            if is_running_in_wsl():
                # Running inside WSL - execute directly
                self.process = subprocess.Popen(
                    ['bash', '-c', self.command],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
            else:
                # Running on Windows - use wsl command
                self.process = subprocess.Popen(
                    ['wsl', '-d', self.distro, 'bash', '-c', self.command],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

            for line in iter(self.process.stdout.readline, ''):
                if self._cancelled:
                    break
                self.output.emit(line)

            self.process.wait()

            if self._cancelled:
                self.simulation_done.emit(False, "Cancelled by user")
            elif self.process.returncode == 0:
                self.simulation_done.emit(True, "Simulation completed successfully")
            else:
                self.simulation_done.emit(False, f"Exited with code {self.process.returncode}")

        except Exception as e:
            self.simulation_done.emit(False, str(e))


class WSLSelectorWidget(QGroupBox):
    """Widget for selecting WSL distribution."""

    distro_changed = Signal(str)

    def __init__(self):
        super().__init__("WSL Environment")
        self.m5_path = ""
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QFormLayout(self)

        # Distro selector
        self.distro_combo = QComboBox()
        self.distro_combo.currentIndexChanged.connect(self._on_distro_changed)
        layout.addRow("Distribution:", self.distro_combo)

        # M5_PATH display
        self.m5_path_label = QLabel("-")
        self.m5_path_label.setWordWrap(True)
        layout.addRow("M5_PATH:", self.m5_path_label)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        layout.addRow("", refresh_btn)

    def refresh(self):
        """Refresh WSL status."""
        self.distro_combo.blockSignals(True)
        self.distro_combo.clear()

        status = get_wsl_status()

        if not status.installed:
            self.distro_combo.addItem("WSL not installed", None)
            self.m5_path_label.setText("N/A")
        elif not status.distros:
            self.distro_combo.addItem("No distributions found", None)
            self.m5_path_label.setText("N/A")
        else:
            for distro in status.distros:
                display = f"{distro.name} (WSL{distro.version})"
                if distro.is_default:
                    display += " *"
                self.distro_combo.addItem(display, distro.name)

            # Update M5_PATH for first distro
            self._update_m5_path()

        self.distro_combo.blockSignals(False)

    def _on_distro_changed(self, index: int):
        self._update_m5_path()
        distro = self.get_selected_distro()
        if distro:
            self.distro_changed.emit(distro)

    def _update_m5_path(self):
        distro = self.get_selected_distro()
        if distro:
            self.m5_path = get_m5_path(distro)
            self.m5_path_label.setText(self.m5_path or "Not set")
        else:
            self.m5_path = ""
            self.m5_path_label.setText("N/A")

    def get_selected_distro(self) -> Optional[str]:
        return self.distro_combo.currentData()


class BenchmarkSelector(QGroupBox):
    """Widget for selecting benchmarks."""

    def __init__(self):
        super().__init__("Benchmark Selection")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Benchmark type
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["sys_validation", "legacy"])
        type_layout.addWidget(self.type_combo)
        layout.addLayout(type_layout)

        # Benchmark name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Benchmark:"))
        self.bench_combo = QComboBox()
        self.bench_combo.setEditable(True)
        self.bench_combo.addItems([
            "gemm", "stencil2d", "stencil3d", "md-knn", "nw", "fft",
            "aes", "bfs", "sort-merge", "spmv-csr", "spmv-ellpack"
        ])
        name_layout.addWidget(self.bench_combo)
        layout.addLayout(name_layout)

    def get_benchmark(self) -> str:
        return self.bench_combo.currentText()

    def get_benchmark_type(self) -> str:
        return self.type_combo.currentText()


class SimulationOptionsWidget(QGroupBox):
    """Widget for simulation options."""

    def __init__(self):
        super().__init__("Simulation Options")
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)

        # Build type
        self.build_combo = QComboBox()
        self.build_combo.addItems(["opt", "debug", "fast"])
        layout.addRow("Build Type:", self.build_combo)

        # CPU type
        self.cpu_combo = QComboBox()
        self.cpu_combo.addItems(["DerivO3CPU", "TimingSimpleCPU", "AtomicSimpleCPU"])
        layout.addRow("CPU Type:", self.cpu_combo)

        # Memory size
        self.mem_combo = QComboBox()
        self.mem_combo.addItems(["4GB", "2GB", "8GB"])
        layout.addRow("Memory:", self.mem_combo)

        # Bare metal mode
        self.baremetal_check = QCheckBox("Bare Metal Mode")
        self.baremetal_check.setChecked(True)
        layout.addRow("", self.baremetal_check)

        # Caches
        self.caches_check = QCheckBox("Enable Caches")
        self.caches_check.setChecked(True)
        layout.addRow("", self.caches_check)

        # CDFG Export
        self.export_cdfg_check = QCheckBox("Export CDFG (for visualization)")
        self.export_cdfg_check.setChecked(False)
        layout.addRow("", self.export_cdfg_check)


class DebugOptionsWidget(QGroupBox):
    """Widget for debug and tracing options."""

    # Debug flag presets
    DEBUG_PRESETS = {
        "(none)": "",
        "SALAMQuick": "SALAMQuick",
        "SALAMVerbose": "SALAMVerbose",
        "SALAMStallDebug": "SALAMStallDebug",
        "SALAMDataDebug": "SALAMDataDebug",
        "SALAMDMADebug": "SALAMDMADebug",
        "SALAMPerfDebug": "SALAMPerfDebug",
        "SALAMMemory": "SALAMMemory",
        "SALAMParseAll": "SALAMParseAll",
        "SALAMAll": "SALAMAll",
        "Custom...": "custom",
    }

    def __init__(self):
        super().__init__("Debug Options")
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)

        # Debug flag preset
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(self.DEBUG_PRESETS.keys()))
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        layout.addRow("Debug Preset:", self.preset_combo)

        # Custom flags input
        self.custom_flags = QLineEdit()
        self.custom_flags.setPlaceholderText("e.g., SALAMExec,Cache,MemCtrl")
        self.custom_flags.setEnabled(False)
        layout.addRow("Custom Flags:", self.custom_flags)

        # Debug output file
        self.debug_file_check = QCheckBox("Write to file")
        self.debug_file = QLineEdit()
        self.debug_file.setPlaceholderText("debug_trace.out")
        self.debug_file.setEnabled(False)
        self.debug_file_check.toggled.connect(self.debug_file.setEnabled)
        file_layout = QHBoxLayout()
        file_layout.addWidget(self.debug_file_check)
        file_layout.addWidget(self.debug_file)
        layout.addRow("Debug File:", file_layout)

        # Time range
        self.time_range_check = QCheckBox("Limit time range")
        self.time_range_check.toggled.connect(self._on_time_range_toggled)
        layout.addRow("", self.time_range_check)

        self.start_tick = QSpinBox()
        self.start_tick.setRange(0, 999999999)
        self.start_tick.setEnabled(False)
        layout.addRow("Start Tick:", self.start_tick)

        self.end_tick = QSpinBox()
        self.end_tick.setRange(0, 999999999)
        self.end_tick.setEnabled(False)
        layout.addRow("End Tick:", self.end_tick)

        # Results output
        self.results_check = QCheckBox("Output Results Summary")
        self.results_csv_check = QCheckBox("Output Results CSV")
        layout.addRow("", self.results_check)
        layout.addRow("", self.results_csv_check)

        # SALAM-specific debug options (passed to config script)
        layout.addRow(QLabel(""))  # Spacer
        layout.addRow(QLabel("<b>SALAM Config Options:</b>"))
        self.salam_debug_check = QCheckBox("Enable SALAM debug messages (C++)")
        self.salam_debug_check.setToolTip("Enables detailed C++ debug output (--salam-debug)")
        layout.addRow("", self.salam_debug_check)

        self.salam_log_combo = QComboBox()
        self.salam_log_combo.addItems(["INFO", "DEBUG", "WARNING", "ERROR"])
        self.salam_log_combo.setToolTip("Python logging level for SALAM configuration")
        layout.addRow("Python Log Level:", self.salam_log_combo)

    def _on_preset_changed(self, text: str):
        """Enable custom flags input when 'Custom...' is selected."""
        is_custom = (text == "Custom...")
        self.custom_flags.setEnabled(is_custom)
        if not is_custom:
            self.custom_flags.clear()

    def _on_time_range_toggled(self, checked: bool):
        """Enable/disable time range inputs."""
        self.start_tick.setEnabled(checked)
        self.end_tick.setEnabled(checked)

    def get_debug_flags(self) -> str:
        """Get the selected debug flags string."""
        preset = self.preset_combo.currentText()
        flags = self.DEBUG_PRESETS.get(preset, "")

        if preset == "Custom...":
            flags = self.custom_flags.text().strip()

        # Add results flags if checked
        extra_flags = []
        if self.results_check.isChecked():
            extra_flags.append("SALAMResults")
        if self.results_csv_check.isChecked():
            extra_flags.append("SALAMResultsCSV")

        if extra_flags:
            if flags:
                flags += "," + ",".join(extra_flags)
            else:
                flags = ",".join(extra_flags)

        return flags

    def get_debug_args(self) -> str:
        """Get all debug-related command line arguments."""
        args = []

        # Debug flags
        flags = self.get_debug_flags()
        if flags:
            args.append(f"--debug-flags={flags}")

        # Debug file
        if self.debug_file_check.isChecked() and self.debug_file.text():
            args.append(f"--debug-file={self.debug_file.text()}")

        # Time range
        if self.time_range_check.isChecked():
            if self.start_tick.value() > 0:
                args.append(f"--debug-start={self.start_tick.value()}")
            if self.end_tick.value() > 0:
                args.append(f"--debug-end={self.end_tick.value()}")

        return " ".join(args)

    def get_salam_config_args(self) -> str:
        """Get SALAM-specific config script arguments."""
        args = []

        if self.salam_debug_check.isChecked():
            args.append("--salam-debug")

        log_level = self.salam_log_combo.currentText()
        if log_level != "INFO":  # Only pass if not default
            args.append(f"--salam-log-level={log_level}")

        return " ".join(args)


class OutputConsole(QTextEdit):
    """Terminal-like output console with ANSI color support."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 9))
        self.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333;
            }
        """)

    def append_output(self, text: str):
        """Append text with ANSI color support."""
        html = ansi_to_html(text)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def clear_output(self):
        self.clear()


class SimulationPanel(QWidget):
    """Main simulation panel widget."""

    simulation_completed = Signal(str)  # Emits output directory path

    def __init__(self):
        super().__init__()
        self.worker: Optional[SimulationWorker] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("gem5-SALAM Simulation")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(title)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Top: Controls
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        # Left column: WSL and benchmark
        left_col = QVBoxLayout()
        self.wsl_selector = WSLSelectorWidget()
        left_col.addWidget(self.wsl_selector)

        self.benchmark_selector = BenchmarkSelector()
        left_col.addWidget(self.benchmark_selector)

        left_col.addStretch()
        controls_layout.addLayout(left_col)

        # Middle column: Debug options
        middle_col = QVBoxLayout()
        self.debug_options = DebugOptionsWidget()
        middle_col.addWidget(self.debug_options)
        middle_col.addStretch()
        controls_layout.addLayout(middle_col)

        # Right column: Options and buttons
        right_col = QVBoxLayout()
        self.options = SimulationOptionsWidget()
        right_col.addWidget(self.options)

        # Run buttons
        btn_layout = QHBoxLayout()
        self.run_btn = QPushButton("Run Simulation")
        self.run_btn.setStyleSheet("font-weight: bold; padding: 10px;")
        self.run_btn.clicked.connect(self._on_run_clicked)
        btn_layout.addWidget(self.run_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        btn_layout.addWidget(self.stop_btn)

        right_col.addLayout(btn_layout)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate
        self.progress.hide()
        right_col.addWidget(self.progress)

        right_col.addStretch()
        controls_layout.addLayout(right_col)

        splitter.addWidget(controls_widget)

        # Bottom: Output console
        console_group = QGroupBox("Simulation Output")
        console_layout = QVBoxLayout(console_group)
        self.console = OutputConsole()
        console_layout.addWidget(self.console)

        # Console toolbar
        console_toolbar = QHBoxLayout()
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.console.clear_output)
        console_toolbar.addWidget(clear_btn)
        console_toolbar.addStretch()
        console_layout.addLayout(console_toolbar)

        splitter.addWidget(console_group)

        splitter.setSizes([300, 400])
        layout.addWidget(splitter)

    def _on_run_clicked(self):
        """Start simulation."""
        distro = self.wsl_selector.get_selected_distro()
        m5_path = self.wsl_selector.m5_path

        if not distro:
            QMessageBox.warning(self, "Error", "No WSL distribution selected")
            return

        if not m5_path:
            QMessageBox.warning(self, "Error", "M5_PATH not set in WSL environment")
            return

        benchmark = self.benchmark_selector.get_benchmark()
        bench_type = self.benchmark_selector.get_benchmark_type()
        build_type = self.options.build_combo.currentText()
        cpu_type = self.options.cpu_combo.currentText()
        mem_size = self.options.mem_combo.currentText()
        baremetal = self.options.baremetal_check.isChecked()
        caches = self.options.caches_check.isChecked()
        export_cdfg = self.options.export_cdfg_check.isChecked()
        debug_args = self.debug_options.get_debug_args()
        salam_args = self.debug_options.get_salam_config_args()

        # Build environment exports
        env_exports = f"export M5_PATH='{m5_path}'"
        if export_cdfg:
            env_exports += " && export SALAM_EXPORT_CDFG=1"

        # Build command
        gem5_binary = f"{m5_path}/build/ARM/gem5.{build_type}"

        # Add debug arguments after gem5 binary
        gem5_cmd = f"'{gem5_binary}'"
        if debug_args:
            gem5_cmd += f" {debug_args}"

        if baremetal:
            config_script = f"configs/SALAM/generated/fs_{benchmark}.py"
            kernel = f"{m5_path}/benchmarks/{bench_type}/{benchmark}/sw/main.elf"
            outdir = f"{m5_path}/BM_ARM_OUT/{bench_type}/{benchmark}"

            cmd = (
                f"cd '{m5_path}' && "
                f"{env_exports} && "
                f"{gem5_cmd} "
                f"--outdir='{outdir}' "
                f"'{m5_path}/{config_script}' "
                f"--mem-size={mem_size} "
                f"--mem-type=DDR4_2400_8x8 "
                f"--kernel={kernel} "
                f"--disk-image={m5_path}/baremetal/common/fake.iso "
                f"--machine-type=VExpress_GEM5_V1 "
                f"--dtb-file=none --bare-metal "
                f"--cpu-type={cpu_type} "
                f"--accpath='{m5_path}/benchmarks/{bench_type}' "
                f"--accbench='{benchmark}'"
            )
            if caches:
                cmd += " --caches --l2cache"
            if salam_args:
                cmd += f" {salam_args}"
        else:
            config_script = "configs/SALAM/fs_hwacc.py"
            outdir = f"{m5_path}/m5out/{benchmark}"

            cmd = (
                f"cd '{m5_path}' && "
                f"{env_exports} && "
                f"{gem5_cmd} "
                f"--outdir='{outdir}' "
                f"'{m5_path}/{config_script}' "
                f"--accpath='{m5_path}/benchmarks/{bench_type}' "
                f"--accbench='{benchmark}'"
            )
            if salam_args:
                cmd += f" {salam_args}"

        # Clear console and start
        self.console.clear_output()
        self.console.append_output(f"==> Starting simulation\n")
        self.console.append_output(f"Distro: {distro}\n")
        self.console.append_output(f"Benchmark: {benchmark}\n")
        self.console.append_output(f"Build: gem5.{build_type}\n")
        if debug_args:
            self.console.append_output(f"Debug: {debug_args}\n")
        if salam_args:
            self.console.append_output(f"SALAM: {salam_args}\n")
        self.console.append_output(f"Output: {outdir}\n\n")

        self.worker = SimulationWorker(distro, cmd)
        self.worker.output.connect(self.console.append_output)
        self.worker.simulation_done.connect(self._on_simulation_finished)

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.show()

        self.worker.start()

    def _on_stop_clicked(self):
        """Stop simulation."""
        if self.worker:
            self.worker.cancel()

    def _on_simulation_finished(self, success: bool, message: str):
        """Handle simulation completion."""
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress.hide()

        if success:
            self.console.append_output(f"\n\n[OK] {message}\n")
        else:
            self.console.append_output(f"\n\n[FAIL] {message}\n")

        self.worker = None
