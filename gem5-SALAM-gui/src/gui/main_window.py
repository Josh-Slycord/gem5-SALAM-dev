"""
Main installer window for gem5-SALAM.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QProgressBar,
    QGroupBox, QFormLayout, QComboBox, QLineEdit,
    QFileDialog, QCheckBox, QTabWidget, QFrame,
    QMessageBox, QSplitter, QDialog, QTreeWidget,
    QTreeWidgetItem, QDialogButtonBox
)
from PySide6.QtCore import Qt, QThread, Signal, QProcess
from PySide6.QtGui import QFont, QTextCursor, QColor

from pathlib import Path
import sys
import os
import re
import json

# Config file path for saving user preferences
CONFIG_FILE = Path(__file__).parent.parent.parent / "installer_config.json"

def load_config() -> dict:
    """Load user configuration from file."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "default_distro": "Ubuntu-20.04",
        "gem5_path": "",
    }

def save_config(config: dict):
    """Save user configuration to file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save config: {e}")

# Import config generator dialog (with graceful fallback)
try:
    from .config_generator import ConfigGeneratorDialog
    HAS_CONFIG_GENERATOR = True
except ImportError:
    HAS_CONFIG_GENERATOR = False


def ansi_to_html(text: str) -> str:
    """Convert ANSI color codes to HTML spans."""
    # ANSI color code mapping to CSS colors
    ansi_colors = {
        '30': '#000000',  # Black
        '31': '#cc0000',  # Red
        '32': '#00cc00',  # Green
        '33': '#cccc00',  # Yellow
        '34': '#5555ff',  # Blue
        '35': '#cc00cc',  # Magenta
        '36': '#00cccc',  # Cyan
        '37': '#cccccc',  # White
        '90': '#666666',  # Bright Black
        '91': '#ff5555',  # Bright Red
        '92': '#55ff55',  # Bright Green
        '93': '#ffff55',  # Bright Yellow
        '94': '#5555ff',  # Bright Blue
        '95': '#ff55ff',  # Bright Magenta
        '96': '#55ffff',  # Bright Cyan
        '97': '#ffffff',  # Bright White
    }

    # Escape HTML special characters first
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Pattern to match ANSI escape sequences
    ansi_pattern = re.compile(r'\x1b\[([0-9;]*)m')

    result = []
    last_end = 0
    open_spans = 0

    for match in ansi_pattern.finditer(text):
        # Add text before this match
        result.append(text[last_end:match.start()])

        codes = match.group(1).split(';')

        for code in codes:
            if code == '0' or code == '':
                # Reset - close all open spans
                result.append('</span>' * open_spans)
                open_spans = 0
            elif code == '1':
                # Bold
                result.append('<span style="font-weight:bold;">')
                open_spans += 1
            elif code in ansi_colors:
                # Color
                result.append(f'<span style="color:{ansi_colors[code]};">')
                open_spans += 1

        last_end = match.end()

    # Add remaining text
    result.append(text[last_end:])

    # Close any remaining open spans
    result.append('</span>' * open_spans)

    return ''.join(result)

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.wsl import (
    get_wsl_status, run_in_wsl_streaming, windows_to_wsl_path,
    check_dependencies, WSLStatus, launch_in_terminal,
    create_install_wrapper_script, is_windows_terminal_available
)


class InstallWorker(QThread):
    """Worker thread for running installation scripts."""

    output = Signal(str)
    progress = Signal(int, str)  # percentage, status message
    finished = Signal(bool, str)  # success, message

    def __init__(self, script_path: str, distro: str, gem5_path: str):
        super().__init__()
        self.script_path = script_path
        self.distro = distro
        self.gem5_path = gem5_path
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        # Write debug to file for crash analysis
        import datetime
        debug_file = Path(__file__).parent.parent.parent / "debug.log"
        def log(msg):
            with open(debug_file, "a") as f:
                f.write(f"{datetime.datetime.now()}: {msg}\n")
            print(msg)

        try:
            log("[DEBUG] InstallWorker.run() started")
            # Convert Windows path to WSL path
            wsl_script_path = windows_to_wsl_path(self.script_path)
            wsl_gem5_path = windows_to_wsl_path(self.gem5_path)

            # Strip Windows CRLF line endings and run through bash
            command = f"tr -d '\\r' < '{wsl_script_path}' | bash"

            log(f"[DEBUG] Script path: {self.script_path}")
            log(f"[DEBUG] WSL script path: {wsl_script_path}")
            log(f"[DEBUG] Distro: {self.distro}")
            log(f"[DEBUG] Command: {command}")

            self.output.emit(f"Running: {command}")
            self.progress.emit(10, "Starting installation...")

            log("[DEBUG] About to start WSL process...")
            process = run_in_wsl_streaming(command, distro=self.distro)
            log(f"[DEBUG] Process started with PID: {process.pid}")

            while True:
                if self._cancelled:
                    process.terminate()
                    self.finished.emit(False, "Installation cancelled")
                    return

                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break

                if line:
                    self.output.emit(line.rstrip())

                    # Parse progress from output
                    if "==>" in line:
                        self.progress.emit(-1, line.split("==>")[1].strip())

            exit_code = process.returncode
            log(f"[DEBUG] Process exited with code: {exit_code}")

            if exit_code == 0:
                self.progress.emit(100, "Installation complete!")
                self.finished.emit(True, "Installation completed successfully!")
            else:
                self.finished.emit(False, f"Installation failed with exit code {exit_code}")

        except Exception as e:
            import traceback
            log(f"[DEBUG] Exception in worker: {e}")
            log(traceback.format_exc())
            self.finished.emit(False, f"Installation error: {str(e)}")


class BuildWorker(QThread):
    """Worker thread for building gem5-SALAM."""

    output = Signal(str)
    progress = Signal(int, str)
    finished = Signal(bool, str)

    def __init__(self, script_path: str, distro: str, gem5_path: str,
                 build_type: str = "opt", num_jobs: int = None):
        super().__init__()
        self.script_path = script_path
        self.distro = distro
        self.gem5_path = gem5_path
        self.build_type = build_type
        self.num_jobs = num_jobs
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        # Write debug to file for crash analysis
        import datetime
        debug_file = Path(__file__).parent.parent.parent / "debug.log"
        def log(msg):
            with open(debug_file, "a") as f:
                f.write(f"{datetime.datetime.now()}: {msg}\n")

        try:
            log("[DEBUG] BuildWorker.run() started")
            wsl_script_path = windows_to_wsl_path(self.script_path)
            wsl_gem5_path = windows_to_wsl_path(self.gem5_path)

            jobs_arg = f"--jobs {self.num_jobs}" if self.num_jobs else ""
            # Strip Windows CRLF line endings and run through bash with args
            command = (
                f"tr -d '\\r' < '{wsl_script_path}' | bash -s -- "
                f"--dir '{wsl_gem5_path}' --type {self.build_type} {jobs_arg}"
            )

            log(f"[DEBUG] Command: {command}")
            log(f"[DEBUG] Distro: {self.distro}")

            self.progress.emit(5, "Starting build...")

            process = run_in_wsl_streaming(command, distro=self.distro)
            log(f"[DEBUG] Process started with PID: {process.pid}")

            while True:
                if self._cancelled:
                    process.terminate()
                    self.finished.emit(False, "Build cancelled")
                    return

                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break

                if line:
                    self.output.emit(line.rstrip())

                    # Try to parse scons progress
                    if "Compiling" in line or "Linking" in line:
                        self.progress.emit(-1, line.strip()[:60])

            exit_code = process.returncode
            log(f"[DEBUG] Process exited with code: {exit_code}")

            if exit_code == 0:
                self.progress.emit(100, "Build complete!")
                self.finished.emit(True, "Build completed successfully!")
            else:
                self.finished.emit(False, f"Build failed with exit code {exit_code}")

        except Exception as e:
            import traceback
            log(f"[DEBUG] Exception in BuildWorker: {e}")
            log(traceback.format_exc())
            self.finished.emit(False, f"Build error: {str(e)}")


class BenchmarkBuildWorker(QThread):
    """Worker thread for building a single benchmark."""

    output = Signal(str)
    progress = Signal(int, str)
    finished = Signal(bool, str)

    def __init__(self, script_path: str, distro: str, gem5_path: str,
                 benchmark: str, num_jobs: int = None):
        super().__init__()
        self.script_path = script_path
        self.distro = distro
        self.gem5_path = gem5_path
        self.benchmark = benchmark
        self.num_jobs = num_jobs
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            wsl_script_path = windows_to_wsl_path(self.script_path)
            wsl_gem5_path = windows_to_wsl_path(self.gem5_path)

            jobs_arg = f"--jobs {self.num_jobs}" if self.num_jobs else ""
            # Build specific benchmark
            command = (
                f"tr -d '\\r' < '{wsl_script_path}' | bash -s -- "
                f"--dir '{wsl_gem5_path}' --benchmark '{self.benchmark}' {jobs_arg}"
            )

            self.progress.emit(-1, f"Building {self.benchmark}...")

            process = run_in_wsl_streaming(command, distro=self.distro)

            while True:
                if self._cancelled:
                    process.terminate()
                    self.finished.emit(False, f"{self.benchmark}: Build cancelled")
                    return

                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break

                if line:
                    self.output.emit(line.rstrip())

            exit_code = process.returncode

            if exit_code == 0:
                self.finished.emit(True, f"{self.benchmark}: Build successful")
            else:
                self.finished.emit(False, f"{self.benchmark}: Build failed (exit code {exit_code})")

        except Exception as e:
            self.finished.emit(False, f"{self.benchmark}: Build error - {str(e)}")


class WSLStatusWidget(QGroupBox):
    """Widget displaying WSL status."""

    distro_changed = Signal(str)  # Emitted when distro selection changes

    def __init__(self):
        super().__init__("WSL Status")
        self.config = load_config()
        self.setup_ui()

    def setup_ui(self):
        layout = QFormLayout(self)

        self.status_label = QLabel("Checking...")
        self.version_label = QLabel("-")
        self.distro_combo = QComboBox()
        self.distro_combo.setMinimumWidth(200)
        self.distro_combo.currentIndexChanged.connect(self._on_distro_changed)

        layout.addRow("Status:", self.status_label)
        layout.addRow("Version:", self.version_label)
        layout.addRow("Distribution:", self.distro_combo)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_status)
        layout.addRow("", self.refresh_btn)

    def refresh_status(self):
        """Refresh WSL status."""
        self.status_label.setText("Checking...")
        self.status_label.repaint()

        status = get_wsl_status()
        self.update_status(status)

    def update_status(self, status: WSLStatus):
        """Update the display with WSL status."""
        if status.installed:
            self.status_label.setText("✓ Installed")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setText("✗ Not Available")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")

        if status.version:
            # Extract just the first line of version info
            version_line = status.version.split('\n')[0]
            self.version_label.setText(version_line)
        else:
            self.version_label.setText("-")

        # Block signals while populating to avoid spurious saves
        self.distro_combo.blockSignals(True)
        self.distro_combo.clear()

        saved_distro = self.config.get("default_distro", "Ubuntu-20.04")
        saved_index = 0

        for i, distro in enumerate(status.distros):
            display = f"{distro.name} (WSL{distro.version})"
            if distro.is_default:
                display += " [default]"
            self.distro_combo.addItem(display, distro.name)

            # Check if this matches the saved distro preference
            if distro.name == saved_distro:
                saved_index = i

        if not status.distros:
            self.distro_combo.addItem("No distributions found", None)
        else:
            # Select the saved distro (or first one if not found)
            self.distro_combo.setCurrentIndex(saved_index)

        self.distro_combo.blockSignals(False)

    def _on_distro_changed(self, index: int):
        """Handle distro selection change - save to config."""
        distro_name = self.distro_combo.currentData()
        if distro_name:
            self.config["default_distro"] = distro_name
            save_config(self.config)
            self.distro_changed.emit(distro_name)

    def get_selected_distro(self) -> str:
        """Get the currently selected distro name."""
        return self.distro_combo.currentData()


class DependencyStatusWidget(QGroupBox):
    """Widget showing dependency installation status."""

    def __init__(self, get_distro_callback=None):
        super().__init__("Dependencies")
        self.get_distro_callback = get_distro_callback
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        self.deps_labels = {}
        deps_layout = QFormLayout()

        dependencies = [
            ('build-essential', 'Build Tools (gcc/g++)'),
            ('python3', 'Python 3'),
            ('scons', 'SCons'),
            ('llvm', 'LLVM'),
            ('clang', 'Clang'),
            ('arm-none-eabi-gcc', 'ARM Toolchain'),
        ]

        for key, name in dependencies:
            label = QLabel("?")
            label.setMinimumWidth(80)
            self.deps_labels[key] = label
            deps_layout.addRow(f"{name}:", label)

        layout.addLayout(deps_layout)

        self.check_btn = QPushButton("Check Dependencies")
        self.check_btn.clicked.connect(self._on_check_clicked)
        layout.addWidget(self.check_btn)

    def _on_check_clicked(self):
        """Handle check button click."""
        distro = None
        if self.get_distro_callback:
            distro = self.get_distro_callback()
        self.run_check(distro)

    def run_check(self, distro: str = None):
        """Check which dependencies are installed."""
        self.check_btn.setEnabled(False)
        self.check_btn.setText("Checking...")
        self.check_btn.repaint()

        # Process events to update UI
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            print(f"Checking dependencies for distro: {distro}")
            deps = check_dependencies(distro)
            print(f"Dependencies result: {deps}")
            for key, label in self.deps_labels.items():
                if key in deps:
                    if deps[key]:
                        label.setText("✓ Installed")
                        label.setStyleSheet("color: green;")
                    else:
                        label.setText("✗ Missing")
                        label.setStyleSheet("color: red;")
        except Exception as e:
            import traceback
            print(f"Error checking dependencies: {e}")
            traceback.print_exc()
            for label in self.deps_labels.values():
                label.setText("Error")
                label.setStyleSheet("color: orange;")
        finally:
            self.check_btn.setEnabled(True)
            self.check_btn.setText("Check Dependencies")


class BenchmarkSelectionDialog(QDialog):
    """Dialog for selecting benchmarks to build."""

    def __init__(self, benchmarks_dir: Path, parent=None):
        super().__init__(parent)
        self.benchmarks_dir = benchmarks_dir
        self.setWindowTitle("Select Benchmarks to Build")
        self.setMinimumSize(500, 400)
        self.setup_ui()
        self.discover_benchmarks()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Instructions
        instructions = QLabel(
            "Select the benchmarks you want to build. "
            "Expand categories to select individual benchmarks."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Tree widget for benchmark selection
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Benchmark", "Path"])
        self.tree.setColumnWidth(0, 250)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)

        # Selection buttons
        btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self._deselect_all)
        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(deselect_all_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def discover_benchmarks(self):
        """Discover available benchmarks in the benchmarks directory."""
        self.tree.clear()

        categories = {
            'legacy': 'Legacy Benchmarks',
            'sys_validation': 'System Validation',
            'lenet5-nounroll': 'LeNet5 (No Unroll)',
            'lenet5-kernelunroll': 'LeNet5 (Kernel Unroll)',
            'lenet5-channelunroll': 'LeNet5 (Channel Unroll)',
            'mobilenetv2': 'MobileNetV2',
        }

        for category_dir, category_name in categories.items():
            category_path = self.benchmarks_dir / category_dir

            if not category_path.exists():
                continue

            # Create category item
            category_item = QTreeWidgetItem([category_name, category_dir])
            category_item.setFlags(
                category_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate
            )
            category_item.setCheckState(0, Qt.Unchecked)

            # Check if this is a single benchmark (has Makefile directly)
            if (category_path / "Makefile").exists():
                # Single benchmark like mobilenetv2
                category_item.setData(0, Qt.UserRole, category_dir)
                self.tree.addTopLevelItem(category_item)
                continue

            # Discover benchmarks in category
            bench_count = 0
            for bench_path in sorted(category_path.iterdir()):
                if not bench_path.is_dir():
                    continue

                # Skip common directories (they're shared code, not benchmarks)
                if bench_path.name == 'common':
                    continue

                # Check if it's a valid benchmark (has Makefile or hw/ directory)
                has_makefile = (bench_path / "Makefile").exists()
                has_hw = (bench_path / "hw").is_dir()

                if has_makefile or has_hw:
                    bench_name = bench_path.name
                    full_path = f"{category_dir}/{bench_name}"

                    bench_item = QTreeWidgetItem([bench_name, full_path])
                    bench_item.setFlags(
                        bench_item.flags() | Qt.ItemIsUserCheckable
                    )
                    bench_item.setCheckState(0, Qt.Unchecked)
                    bench_item.setData(0, Qt.UserRole, full_path)

                    category_item.addChild(bench_item)
                    bench_count += 1

            if bench_count > 0:
                self.tree.addTopLevelItem(category_item)

        # Expand all categories
        self.tree.expandAll()

    def _on_item_changed(self, item, column):
        """Handle item check state changes for parent-child relationships."""
        if column != 0:
            return

        # Block signals to prevent recursion
        self.tree.blockSignals(True)

        # If parent item, update all children
        if item.childCount() > 0:
            state = item.checkState(0)
            for i in range(item.childCount()):
                item.child(i).setCheckState(0, state)
        # If child item, update parent state
        elif item.parent():
            parent = item.parent()
            checked_count = 0
            for i in range(parent.childCount()):
                if parent.child(i).checkState(0) == Qt.Checked:
                    checked_count += 1

            if checked_count == 0:
                parent.setCheckState(0, Qt.Unchecked)
            elif checked_count == parent.childCount():
                parent.setCheckState(0, Qt.Checked)
            else:
                parent.setCheckState(0, Qt.PartiallyChecked)

        self.tree.blockSignals(False)

    def _select_all(self):
        """Select all benchmarks."""
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item.setCheckState(0, Qt.Checked)

    def _deselect_all(self):
        """Deselect all benchmarks."""
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item.setCheckState(0, Qt.Unchecked)

    def get_selected_benchmarks(self) -> list:
        """Get list of selected benchmark paths."""
        selected = []

        for i in range(self.tree.topLevelItemCount()):
            category_item = self.tree.topLevelItem(i)

            # Check if this is a single benchmark (leaf category)
            if category_item.childCount() == 0:
                if category_item.checkState(0) == Qt.Checked:
                    path = category_item.data(0, Qt.UserRole)
                    if path:
                        selected.append(path)
            else:
                # Check children
                for j in range(category_item.childCount()):
                    child = category_item.child(j)
                    if child.checkState(0) == Qt.Checked:
                        path = child.data(0, Qt.UserRole)
                        if path:
                            selected.append(path)

        return selected


class SimulationDialog(QDialog):
    """Dialog for configuring and running simulations."""

    def __init__(self, gem5_path: Path, parent=None):
        super().__init__(parent)
        self.gem5_path = gem5_path
        self.benchmarks_dir = gem5_path / "benchmarks"
        self.setWindowTitle("Run Simulation")
        self.setMinimumSize(600, 500)
        self.setup_ui()
        self.discover_benchmarks()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Benchmark selection
        bench_group = QGroupBox("Benchmark")
        bench_layout = QFormLayout(bench_group)

        self.benchmark_combo = QComboBox()
        self.benchmark_combo.setMinimumWidth(300)
        bench_layout.addRow("Benchmark:", self.benchmark_combo)

        layout.addWidget(bench_group)

        # Configuration options
        config_group = QGroupBox("Configuration")
        config_layout = QFormLayout(config_group)

        self.config_combo = QComboBox()
        self.config_combo.addItems([
            "configs/SALAM/sys_validation.py",
            "configs/SALAM/fs_hwacc.py",
            "configs/SALAM/validate_acc.py",
        ])
        config_layout.addRow("Config Script:", self.config_combo)

        self.build_combo = QComboBox()
        self.build_combo.addItems(["opt", "debug", "fast"])
        config_layout.addRow("Build Type:", self.build_combo)

        self.cpus_spin = QLineEdit("1")
        self.cpus_spin.setMaximumWidth(60)
        config_layout.addRow("CPUs:", self.cpus_spin)

        layout.addWidget(config_group)

        # Advanced options (collapsed by default)
        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QFormLayout(advanced_group)

        self.kernel_edit = QLineEdit()
        self.kernel_edit.setPlaceholderText("Path to kernel image (optional)")
        kernel_row = QHBoxLayout()
        kernel_row.addWidget(self.kernel_edit)
        kernel_browse = QPushButton("Browse...")
        kernel_browse.clicked.connect(self._browse_kernel)
        kernel_row.addWidget(kernel_browse)
        advanced_layout.addRow("Kernel:", kernel_row)

        self.disk_edit = QLineEdit()
        self.disk_edit.setPlaceholderText("Path to disk image (optional)")
        disk_row = QHBoxLayout()
        disk_row.addWidget(self.disk_edit)
        disk_browse = QPushButton("Browse...")
        disk_browse.clicked.connect(self._browse_disk)
        disk_row.addWidget(disk_browse)
        advanced_layout.addRow("Disk Image:", disk_row)

        self.extra_args_edit = QLineEdit()
        self.extra_args_edit.setPlaceholderText("Additional gem5 arguments")
        advanced_layout.addRow("Extra Args:", self.extra_args_edit)

        layout.addWidget(advanced_group)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def discover_benchmarks(self):
        """Discover available benchmarks."""
        self.benchmark_combo.clear()

        categories = ['sys_validation', 'legacy', 'lenet5-nounroll',
                      'lenet5-kernelunroll', 'lenet5-channelunroll', 'mobilenetv2']

        for category in categories:
            category_path = self.benchmarks_dir / category

            if not category_path.exists():
                continue

            # Check if category is a direct benchmark
            if (category_path / "Makefile").exists():
                self.benchmark_combo.addItem(f"{category}", category)
                continue

            # List benchmarks in category
            for bench_path in sorted(category_path.iterdir()):
                if not bench_path.is_dir():
                    continue

                # Check for built benchmark
                has_ll = list(bench_path.glob("**/*.ll"))
                has_makefile = (bench_path / "Makefile").exists()

                if has_ll or has_makefile:
                    full_path = f"{category}/{bench_path.name}"
                    display = f"{category}/{bench_path.name}"
                    if has_ll:
                        display += " [built]"
                    self.benchmark_combo.addItem(display, full_path)

    def _browse_kernel(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Kernel Image", "", "All Files (*)"
        )
        if path:
            self.kernel_edit.setText(path)

    def _browse_disk(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Disk Image", "", "Disk Images (*.img *.qcow2);;All Files (*)"
        )
        if path:
            self.disk_edit.setText(path)

    def get_config(self) -> dict:
        """Get simulation configuration."""
        return {
            'benchmark': self.benchmark_combo.currentData(),
            'config_script': self.config_combo.currentText(),
            'build_type': self.build_combo.currentText(),
            'cpus': self.cpus_spin.text(),
            'kernel': self.kernel_edit.text(),
            'disk': self.disk_edit.text(),
            'extra_args': self.extra_args_edit.text(),
        }


class SimulationWorker(QThread):
    """Worker thread for running gem5-SALAM simulations."""

    output = Signal(str)
    progress = Signal(int, str)
    finished = Signal(bool, str)

    def __init__(self, script_path: str, distro: str, gem5_path: str, config: dict):
        super().__init__()
        self.script_path = script_path
        self.distro = distro
        self.gem5_path = gem5_path
        self.config = config
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            wsl_script_path = windows_to_wsl_path(self.script_path)
            wsl_gem5_path = windows_to_wsl_path(self.gem5_path)

            # Build command arguments
            args = [
                f"--dir '{wsl_gem5_path}'",
                f"--benchmark '{self.config['benchmark']}'",
                f"--config '{self.config['config_script']}'",
                f"--build-type '{self.config['build_type']}'",
                f"--cpus {self.config['cpus']}",
            ]

            if self.config.get('kernel'):
                kernel_path = windows_to_wsl_path(self.config['kernel'])
                args.append(f"--kernel '{kernel_path}'")

            if self.config.get('disk'):
                disk_path = windows_to_wsl_path(self.config['disk'])
                args.append(f"--disk '{disk_path}'")

            if self.config.get('extra_args'):
                args.append(f"--extra '{self.config['extra_args']}'")

            command = f"tr -d '\\r' < '{wsl_script_path}' | bash -s -- {' '.join(args)}"

            self.output.emit(f"Starting simulation: {self.config['benchmark']}")
            self.progress.emit(5, "Starting simulation...")

            process = run_in_wsl_streaming(command, distro=self.distro)

            while True:
                if self._cancelled:
                    process.terminate()
                    self.finished.emit(False, "Simulation cancelled")
                    return

                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break

                if line:
                    self.output.emit(line.rstrip())

            exit_code = process.returncode

            if exit_code == 0:
                self.progress.emit(100, "Simulation complete!")
                self.finished.emit(True, "Simulation completed successfully!")
            else:
                self.finished.emit(False, f"Simulation failed with exit code {exit_code}")

        except Exception as e:
            self.finished.emit(False, f"Simulation error: {str(e)}")


class MainWindow(QMainWindow):
    """Main installer window."""

    def __init__(self):
        super().__init__()
        print("[DEBUG] MainWindow.__init__ started")
        self.setWindowTitle("gem5-SALAM Installer")
        self.setMinimumSize(900, 700)

        self.worker = None
        self.scripts_dir = Path(__file__).parent.parent.parent / "scripts"
        self.config = load_config()  # Load user preferences
        print("[DEBUG] About to call setup_ui")

        self.setup_ui()
        print("[DEBUG] setup_ui complete, calling refresh_wsl_status")
        self.refresh_wsl_status()
        print("[DEBUG] MainWindow.__init__ complete")

    def setup_ui(self):
        """Set up the main UI."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Header
        header = QLabel("gem5-SALAM Installer")
        header.setFont(QFont("", 16, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)

        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(splitter, 1)

        # Top panel - configuration
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        # Left column - WSL and paths
        left_column = QVBoxLayout()

        # WSL Status
        self.wsl_status = WSLStatusWidget()
        left_column.addWidget(self.wsl_status)

        # Path configuration
        paths_group = QGroupBox("Paths")
        paths_layout = QFormLayout(paths_group)

        self.gem5_path_edit = QLineEdit()
        self.gem5_path_edit.setPlaceholderText("Path to gem5-SALAM directory")

        # Load path from config, or auto-detect
        saved_path = self.config.get("gem5_path", "")
        if saved_path and Path(saved_path).exists():
            self.gem5_path_edit.setText(saved_path)
        else:
            default_path = Path(__file__).parent.parent.parent.parent / "gem5-SALAM-dev"
            if default_path.exists():
                self.gem5_path_edit.setText(str(default_path))

        # Save path when changed
        self.gem5_path_edit.textChanged.connect(self._save_gem5_path)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_gem5_path)

        path_row = QHBoxLayout()
        path_row.addWidget(self.gem5_path_edit, 1)
        path_row.addWidget(browse_btn)
        paths_layout.addRow("gem5-SALAM:", path_row)

        # M5_PATH setting
        m5_path_row = QHBoxLayout()
        self.m5_path_label = QLabel("Not set")
        self.m5_path_label.setStyleSheet("color: orange;")
        m5_path_row.addWidget(self.m5_path_label, 1)

        set_m5_btn = QPushButton("Set M5_PATH")
        set_m5_btn.clicked.connect(self.set_m5_path)
        set_m5_btn.setToolTip("Set M5_PATH environment variable in WSL")
        m5_path_row.addWidget(set_m5_btn)

        paths_layout.addRow("M5_PATH:", m5_path_row)

        # Check current M5_PATH status
        self._check_m5_path()

        left_column.addWidget(paths_group)
        left_column.addStretch()

        # Right column - Dependencies and build options
        right_column = QVBoxLayout()

        # Dependencies (pass callback to get selected distro)
        self.deps_status = DependencyStatusWidget(
            get_distro_callback=self.wsl_status.get_selected_distro
        )
        right_column.addWidget(self.deps_status)

        # Build options
        build_group = QGroupBox("Build Options")
        build_layout = QFormLayout(build_group)

        self.build_type_combo = QComboBox()
        self.build_type_combo.addItems(["opt", "debug", "fast"])
        build_layout.addRow("Build Type:", self.build_type_combo)

        self.jobs_edit = QLineEdit()
        self.jobs_edit.setPlaceholderText("auto")
        self.jobs_edit.setMaximumWidth(80)
        build_layout.addRow("Parallel Jobs:", self.jobs_edit)

        right_column.addWidget(build_group)
        right_column.addStretch()

        top_layout.addLayout(left_column, 1)
        top_layout.addLayout(right_column, 1)
        splitter.addWidget(top_widget)

        # Bottom panel - output and progress
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        # Progress
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_label = QLabel("Ready")
        progress_layout.addWidget(self.progress_bar, 1)
        progress_layout.addWidget(self.progress_label)
        bottom_layout.addLayout(progress_layout)

        # Output console
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Consolas", 9))
        self.output_text.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; }"
        )
        bottom_layout.addWidget(self.output_text, 1)

        # Output controls
        output_btn_layout = QHBoxLayout()
        output_btn_layout.addStretch()

        self.copy_output_btn = QPushButton("Copy to Clipboard")
        self.copy_output_btn.clicked.connect(self.copy_output_to_clipboard)
        output_btn_layout.addWidget(self.copy_output_btn)

        self.clear_output_btn = QPushButton("Clear")
        self.clear_output_btn.clicked.connect(self.output_text.clear)
        output_btn_layout.addWidget(self.clear_output_btn)

        bottom_layout.addLayout(output_btn_layout)

        splitter.addWidget(bottom_widget)
        splitter.setSizes([300, 400])

        # Action buttons
        button_layout = QHBoxLayout()

        self.install_deps_btn = QPushButton("Install Dependencies")
        self.install_deps_btn.clicked.connect(self.install_dependencies)
        button_layout.addWidget(self.install_deps_btn)

        self.build_gem5_btn = QPushButton("Build gem5-SALAM")
        self.build_gem5_btn.clicked.connect(self.build_gem5)
        button_layout.addWidget(self.build_gem5_btn)

        self.build_cacti_btn = QPushButton("Build CACTI")
        self.build_cacti_btn.clicked.connect(self.build_cacti)
        button_layout.addWidget(self.build_cacti_btn)

        self.build_benchmarks_btn = QPushButton("Build Benchmarks")
        self.build_benchmarks_btn.clicked.connect(self.build_benchmarks)
        button_layout.addWidget(self.build_benchmarks_btn)

        self.run_sim_btn = QPushButton("Run Simulation")
        self.run_sim_btn.clicked.connect(self.run_simulation)
        button_layout.addWidget(self.run_sim_btn)

        # Configuration generator button
        self.config_gen_btn = QPushButton("Configuration")
        self.config_gen_btn.clicked.connect(self.open_config_generator)
        self.config_gen_btn.setToolTip("Create or edit accelerator configurations")
        if not HAS_CONFIG_GENERATOR:
            self.config_gen_btn.setEnabled(False)
            self.config_gen_btn.setToolTip("Config generator not available")
        button_layout.addWidget(self.config_gen_btn)

        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_operation)
        self.cancel_btn.setEnabled(False)
        button_layout.addWidget(self.cancel_btn)

        main_layout.addLayout(button_layout)

    def refresh_wsl_status(self):
        """Refresh WSL status display."""
        self.wsl_status.refresh_status()
        # Also check M5_PATH after a short delay to ensure distro is selected
        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, self._check_m5_path)

    def browse_gem5_path(self):
        """Open file dialog to select gem5-SALAM directory."""
        path = QFileDialog.getExistingDirectory(
            self, "Select gem5-SALAM Directory",
            self.gem5_path_edit.text() or str(Path.home())
        )
        if path:
            self.gem5_path_edit.setText(path)

    def _save_gem5_path(self, path: str):
        """Save gem5 path to config when changed."""
        if path and Path(path).exists():
            self.config["gem5_path"] = path
            save_config(self.config)

    def _check_m5_path(self):
        """Check if M5_PATH is set in WSL."""
        try:
            distro = self.wsl_status.get_selected_distro()
            if not distro:
                self.m5_path_label.setText("Select WSL distro first")
                self.m5_path_label.setStyleSheet("color: gray;")
                return

            # Extract M5_PATH directly from shell config files
            # This is more reliable than sourcing because pyenv/other init scripts may fail
            import subprocess
            # Search for export M5_PATH= in both .bashrc and .profile
            cmd = (
                "grep -h 'export M5_PATH=' ~/.bashrc ~/.profile 2>/dev/null | "
                "tail -1 | sed 's/.*M5_PATH=[\"]*\\([^\"]*\\)[\"]*$/\\1/'"
            )
            result = subprocess.run(
                ['wsl', '-d', distro, 'bash', '-c', cmd],
                capture_output=True, text=True, timeout=5
            )

            m5_path = result.stdout.strip()
            if m5_path:
                # Truncate if too long
                display = m5_path if len(m5_path) < 40 else f"...{m5_path[-37:]}"
                self.m5_path_label.setText(display)
                self.m5_path_label.setStyleSheet("color: green;")
                self.m5_path_label.setToolTip(m5_path)
            else:
                self.m5_path_label.setText("Not set")
                self.m5_path_label.setStyleSheet("color: orange;")
                self.m5_path_label.setToolTip("M5_PATH environment variable is not set")

        except Exception as e:
            self.m5_path_label.setText("Error checking")
            self.m5_path_label.setStyleSheet("color: red;")
            self.m5_path_label.setToolTip(str(e))

    def set_m5_path(self):
        """Set M5_PATH environment variable in WSL."""
        gem5_path = self.gem5_path_edit.text().strip()
        if not gem5_path:
            QMessageBox.warning(
                self, "No Path",
                "Please specify the gem5-SALAM directory path first."
            )
            return

        if not Path(gem5_path).exists():
            QMessageBox.warning(
                self, "Invalid Path",
                f"The specified path does not exist:\n{gem5_path}"
            )
            return

        distro = self.wsl_status.get_selected_distro()
        if not distro:
            QMessageBox.warning(
                self, "No WSL Distribution",
                "Please select a WSL distribution first."
            )
            return

        # Convert Windows path to WSL path
        wsl_path = windows_to_wsl_path(gem5_path)

        # Ask user which shell config to modify
        msg = QMessageBox(self)
        msg.setWindowTitle("Set M5_PATH")
        msg.setText(f"Set M5_PATH to:\n{wsl_path}")
        msg.setInformativeText(
            "This will add an export line to your shell configuration.\n"
            "Which file should be modified?"
        )

        bashrc_btn = msg.addButton("~/.bashrc", QMessageBox.AcceptRole)
        profile_btn = msg.addButton("~/.profile", QMessageBox.ActionRole)
        both_btn = msg.addButton("Both", QMessageBox.ActionRole)
        cancel_btn = msg.addButton(QMessageBox.Cancel)

        msg.setDefaultButton(bashrc_btn)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == cancel_btn:
            return

        files_to_modify = []
        if clicked == bashrc_btn:
            files_to_modify = ['~/.bashrc']
        elif clicked == profile_btn:
            files_to_modify = ['~/.profile']
        elif clicked == both_btn:
            files_to_modify = ['~/.bashrc', '~/.profile']

        try:
            import subprocess
            export_line = f'export M5_PATH="{wsl_path}"'

            for config_file in files_to_modify:
                # Check if line already exists
                check_cmd = f'grep -q "export M5_PATH=" {config_file} 2>/dev/null && echo "exists" || echo "missing"'
                result = subprocess.run(
                    ['wsl', '-d', distro, 'bash', '-c', check_cmd],
                    capture_output=True, text=True, timeout=10
                )

                if result.stdout.strip() == "exists":
                    # Replace existing M5_PATH line
                    sed_cmd = f'sed -i "s|^export M5_PATH=.*|{export_line}|" {config_file}'
                    subprocess.run(
                        ['wsl', '-d', distro, 'bash', '-c', sed_cmd],
                        capture_output=True, text=True, timeout=10
                    )
                    self.append_output(f"Updated M5_PATH in {config_file}\n")
                else:
                    # Append new line
                    append_cmd = f'echo \'{export_line}\' >> {config_file}'
                    subprocess.run(
                        ['wsl', '-d', distro, 'bash', '-c', append_cmd],
                        capture_output=True, text=True, timeout=10
                    )
                    self.append_output(f"Added M5_PATH to {config_file}\n")

            # Also set it for the current session by sourcing
            source_cmd = f'export M5_PATH="{wsl_path}"'
            subprocess.run(
                ['wsl', '-d', distro, 'bash', '-c', source_cmd],
                capture_output=True, text=True, timeout=10
            )

            self.append_output(f"\nM5_PATH set to: {wsl_path}\n")
            self.append_output("Note: Open a new terminal or run 'source ~/.bashrc' for changes to take effect.\n")

            # Update the label
            self._check_m5_path()

            QMessageBox.information(
                self, "M5_PATH Set",
                f"M5_PATH has been set to:\n{wsl_path}\n\n"
                "Open a new WSL terminal or run 'source ~/.bashrc' for changes to take effect."
            )

        except Exception as e:
            QMessageBox.critical(
                self, "Error",
                f"Failed to set M5_PATH:\n{e}"
            )

    def append_output(self, text: str):
        """Append text to the output console with ANSI color support."""
        try:
            # Convert ANSI codes to HTML
            html_text = ansi_to_html(text)
            # Replace newlines with <br> for HTML
            html_text = html_text.replace('\n', '<br>')

            # Append as HTML
            cursor = self.output_text.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.output_text.setTextCursor(cursor)
            self.output_text.insertHtml(html_text + '<br>')

            # Auto-scroll to bottom
            cursor.movePosition(QTextCursor.End)
            self.output_text.setTextCursor(cursor)
        except Exception as e:
            # Fallback to plain text if HTML conversion fails
            try:
                self.output_text.append(text)
            except:
                pass  # Silently ignore if even plain append fails

    def update_progress(self, value: int, message: str):
        """Update progress bar and label."""
        if value >= 0:
            self.progress_bar.setValue(value)
        self.progress_label.setText(message)

    def copy_output_to_clipboard(self):
        """Copy the output text to clipboard."""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        # Get plain text (without HTML formatting)
        plain_text = self.output_text.toPlainText()
        clipboard.setText(plain_text)
        # Show brief feedback
        self.progress_label.setText("Copied to clipboard!")

    def set_buttons_enabled(self, enabled: bool):
        """Enable/disable action buttons."""
        self.install_deps_btn.setEnabled(enabled)
        self.build_gem5_btn.setEnabled(enabled)
        self.build_cacti_btn.setEnabled(enabled)
        self.build_benchmarks_btn.setEnabled(enabled)
        self.run_sim_btn.setEnabled(enabled)
        self.cancel_btn.setEnabled(not enabled)

    def validate_inputs(self) -> bool:
        """Validate user inputs before running operations."""
        distro = self.wsl_status.get_selected_distro()
        if not distro:
            QMessageBox.warning(
                self, "No WSL Distribution",
                "Please select a WSL distribution to use."
            )
            return False

        gem5_path = self.gem5_path_edit.text().strip()
        if not gem5_path:
            QMessageBox.warning(
                self, "No Path",
                "Please specify the gem5-SALAM directory path."
            )
            return False

        if not Path(gem5_path).exists():
            QMessageBox.warning(
                self, "Invalid Path",
                f"The specified path does not exist:\n{gem5_path}"
            )
            return False

        return True

    def install_dependencies(self):
        """Start dependency installation."""
        if not self.validate_inputs():
            return

        distro = self.wsl_status.get_selected_distro()

        # Offer choice between terminal (with sudo support) and embedded
        msg = QMessageBox(self)
        msg.setWindowTitle("Installation Method")
        msg.setText("How would you like to run the dependency installation?")
        msg.setInformativeText(
            "The installation requires sudo (administrator) access.\n\n"
            "• Terminal: Opens a new terminal window where you can enter your "
            "sudo password interactively. (Recommended)\n\n"
            "• Embedded: Runs in this window, but will fail if sudo prompts "
            "for a password. Only works if you have passwordless sudo."
        )

        terminal_btn = msg.addButton("Open in Terminal", QMessageBox.AcceptRole)
        embedded_btn = msg.addButton("Run Embedded", QMessageBox.ActionRole)
        cancel_btn = msg.addButton(QMessageBox.Cancel)

        msg.setDefaultButton(terminal_btn)
        msg.exec()

        clicked = msg.clickedButton()

        if clicked == cancel_btn:
            return
        elif clicked == terminal_btn:
            self._install_in_terminal(distro)
        else:
            self._install_embedded(distro)

    def _install_in_terminal(self, distro: str):
        """Launch dependency installation in a terminal window."""
        script_path = str(self.scripts_dir / "install_deps.sh")
        wsl_script_path = windows_to_wsl_path(script_path)

        # Create the installation command
        command = f"tr -d '\\r' < '{wsl_script_path}' | bash"

        self.output_text.clear()
        self.append_output("Launching installation in terminal...\n")
        self.append_output(f"Distribution: {distro}\n")
        self.append_output(f"Script: {script_path}\n\n")

        terminal_name = "Windows Terminal" if is_windows_terminal_available() else "Command Prompt"
        self.append_output(f"Opening {terminal_name}...\n")
        self.append_output("Please complete the installation in the terminal window.\n")
        self.append_output("Enter your sudo password when prompted.\n\n")
        self.append_output("Click 'Check Dependencies' after installation completes.\n")

        try:
            launch_in_terminal(
                command,
                distro=distro,
                title="gem5-SALAM Dependency Installation"
            )
            self.progress_label.setText("Installation running in terminal...")
            self.progress_bar.setValue(50)
            self.append_output("\n✓ Terminal launched successfully!\n")

            # Show reminder dialog
            QMessageBox.information(
                self,
                "Installation Started",
                "The installation is now running in a separate terminal window.\n\n"
                "Please:\n"
                "1. Enter your sudo password when prompted\n"
                "2. Wait for the installation to complete\n"
                "3. Press Enter to close the terminal\n"
                "4. Click 'Check Dependencies' to verify installation"
            )

        except Exception as e:
            self.append_output(f"\n✗ Failed to launch terminal: {e}\n")
            QMessageBox.critical(
                self,
                "Launch Failed",
                f"Failed to launch terminal:\n{e}\n\n"
                "Try using 'Run Embedded' option instead."
            )

    def _install_embedded(self, distro: str):
        """Run dependency installation embedded in the GUI (original method)."""
        self.output_text.clear()
        self.append_output("Starting dependency installation (embedded mode)...\n")
        self.append_output("Note: This will fail if sudo prompts for a password.\n\n")
        self.set_buttons_enabled(False)
        self.progress_bar.setValue(0)

        script_path = str(self.scripts_dir / "install_deps.sh")
        gem5_path = self.gem5_path_edit.text().strip()

        self.worker = InstallWorker(script_path, distro, gem5_path)
        self.worker.output.connect(self.append_output)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_operation_finished)
        self.worker.start()

    def build_gem5(self):
        """Start gem5-SALAM build."""
        if not self.validate_inputs():
            return

        gem5_path = self.gem5_path_edit.text().strip()
        scons_file = Path(gem5_path) / "SConstruct"
        if not scons_file.exists():
            QMessageBox.warning(
                self, "Invalid gem5 Directory",
                "The specified directory does not appear to be a gem5 directory.\n"
                "SConstruct file not found."
            )
            return

        self.output_text.clear()
        self.append_output("Starting gem5-SALAM build...\n")
        self.set_buttons_enabled(False)
        self.progress_bar.setValue(0)

        script_path = str(self.scripts_dir / "build_gem5.sh")
        distro = self.wsl_status.get_selected_distro()
        build_type = self.build_type_combo.currentText()

        jobs = None
        jobs_text = self.jobs_edit.text().strip()
        if jobs_text:
            try:
                jobs = int(jobs_text)
            except ValueError:
                pass

        self.worker = BuildWorker(
            script_path, distro, gem5_path, build_type, jobs
        )
        self.worker.output.connect(self.append_output)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_operation_finished)
        self.worker.start()

    def build_cacti(self):
        """Start CACTI build."""
        if not self.validate_inputs():
            return

        gem5_path = self.gem5_path_edit.text().strip()
        cacti_dir = Path(gem5_path) / "ext" / "mcpat" / "cacti"
        if not cacti_dir.exists():
            QMessageBox.warning(
                self, "CACTI Not Found",
                f"CACTI directory not found at:\n{cacti_dir}"
            )
            return

        self.output_text.clear()
        self.append_output("Starting CACTI build...\n")
        self.set_buttons_enabled(False)
        self.progress_bar.setValue(0)

        script_path = str(self.scripts_dir / "build_cacti.sh")
        distro = self.wsl_status.get_selected_distro()

        self.worker = BuildWorker(
            script_path, distro, gem5_path, "opt", None
        )
        self.worker.output.connect(self.append_output)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_operation_finished)
        self.worker.start()

    def build_benchmarks(self):
        """Start benchmark build."""
        if not self.validate_inputs():
            return

        gem5_path = self.gem5_path_edit.text().strip()
        benchmarks_dir = Path(gem5_path) / "benchmarks"
        if not benchmarks_dir.exists():
            QMessageBox.warning(
                self, "Benchmarks Not Found",
                f"Benchmarks directory not found at:\n{benchmarks_dir}"
            )
            return

        # Show benchmark selection dialog
        dialog = BenchmarkSelectionDialog(benchmarks_dir, self)
        if dialog.exec() != QDialog.Accepted:
            return

        selected = dialog.get_selected_benchmarks()
        if not selected:
            QMessageBox.warning(
                self, "No Selection",
                "Please select at least one benchmark to build."
            )
            return

        self.output_text.clear()
        self.append_output(f"Building {len(selected)} benchmark(s)...\n")
        for bench in selected:
            self.append_output(f"  - {bench}\n")
        self.append_output("\n")
        self.set_buttons_enabled(False)
        self.progress_bar.setValue(0)

        script_path = str(self.scripts_dir / "build_benchmarks.sh")
        distro = self.wsl_status.get_selected_distro()

        jobs = None
        jobs_text = self.jobs_edit.text().strip()
        if jobs_text:
            try:
                jobs = int(jobs_text)
            except ValueError:
                pass

        # Build each selected benchmark
        self._benchmark_queue = list(selected)
        self._benchmark_jobs = jobs
        self._benchmark_distro = distro
        self._benchmark_gem5_path = gem5_path
        self._benchmark_script = script_path
        self._benchmark_success_count = 0
        self._benchmark_fail_count = 0
        self._build_next_benchmark()

    def _build_next_benchmark(self):
        """Build the next benchmark in the queue."""
        if not self._benchmark_queue:
            # All done
            self.set_buttons_enabled(True)
            total = self._benchmark_success_count + self._benchmark_fail_count
            self.append_output(f"\n{'='*50}\n")
            self.append_output(f"Benchmark build complete!\n")
            self.append_output(f"  Success: {self._benchmark_success_count}/{total}\n")
            if self._benchmark_fail_count > 0:
                self.append_output(f"  Failed: {self._benchmark_fail_count}/{total}\n")
            self.progress_bar.setValue(100)
            self.progress_label.setText("Benchmark build complete!")
            return

        benchmark = self._benchmark_queue.pop(0)
        total = self._benchmark_success_count + self._benchmark_fail_count + len(self._benchmark_queue) + 1
        current = self._benchmark_success_count + self._benchmark_fail_count + 1

        self.append_output(f"\n[{current}/{total}] Building: {benchmark}\n")
        progress = int((current - 1) / total * 100)
        self.progress_bar.setValue(progress)
        self.progress_label.setText(f"Building {benchmark}...")

        # Create worker for this benchmark
        self.worker = BenchmarkBuildWorker(
            self._benchmark_script,
            self._benchmark_distro,
            self._benchmark_gem5_path,
            benchmark,
            self._benchmark_jobs
        )
        self.worker.output.connect(self.append_output)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self._on_benchmark_finished)
        self.worker.start()

    def _on_benchmark_finished(self, success: bool, message: str):
        """Handle single benchmark build completion."""
        if success:
            self._benchmark_success_count += 1
            self.append_output(f"✓ {message}\n")
        else:
            self._benchmark_fail_count += 1
            self.append_output(f"✗ {message}\n")

        # Properly clean up the worker thread
        if self.worker:
            self.worker.wait(5000)  # Wait up to 5 seconds for thread to finish
            self.worker.deleteLater()  # Schedule for deletion
            self.worker = None

        # Use a timer to start next benchmark to ensure thread cleanup
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self._build_next_benchmark)

    def open_config_generator(self):
        """Open the configuration generator dialog."""
        gem5_path = self.gem5_path_edit.text().strip()

        if not gem5_path:
            QMessageBox.warning(
                self, "No Path",
                "Please specify the gem5-SALAM directory path first."
            )
            return

        gem5_path = Path(gem5_path)
        if not gem5_path.exists():
            QMessageBox.warning(
                self, "Invalid Path",
                f"The specified path does not exist:\n{gem5_path}"
            )
            return

        try:
            dialog = ConfigGeneratorDialog(gem5_path, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(
                self, "Error",
                f"Failed to open configuration generator:\n{e}"
            )

    def run_simulation(self):
        """Start a gem5-SALAM simulation."""
        if not self.validate_inputs():
            return

        gem5_path = self.gem5_path_edit.text().strip()

        # Check for gem5 binary
        build_type = self.build_type_combo.currentText()
        gem5_bin = Path(gem5_path) / "build" / "ARM" / f"gem5.{build_type}"
        if not gem5_bin.exists():
            QMessageBox.warning(
                self, "gem5 Not Built",
                f"gem5 binary not found:\n{gem5_bin}\n\n"
                "Please build gem5-SALAM first."
            )
            return

        benchmarks_dir = Path(gem5_path) / "benchmarks"
        if not benchmarks_dir.exists():
            QMessageBox.warning(
                self, "Benchmarks Not Found",
                f"Benchmarks directory not found at:\n{benchmarks_dir}"
            )
            return

        # Show simulation configuration dialog
        dialog = SimulationDialog(Path(gem5_path), self)
        if dialog.exec() != QDialog.Accepted:
            return

        config = dialog.get_config()
        if not config.get('benchmark'):
            QMessageBox.warning(
                self, "No Benchmark",
                "Please select a benchmark to run."
            )
            return

        self.output_text.clear()
        self.append_output(f"Starting simulation: {config['benchmark']}\n")
        self.append_output(f"Config script: {config['config_script']}\n")
        self.append_output(f"Build type: {config['build_type']}\n")
        self.append_output("\n")
        self.set_buttons_enabled(False)
        self.progress_bar.setValue(0)

        script_path = str(self.scripts_dir / "run_simulation.sh")
        distro = self.wsl_status.get_selected_distro()

        self.worker = SimulationWorker(
            script_path, distro, gem5_path, config
        )
        self.worker.output.connect(self.append_output)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_operation_finished)
        self.worker.start()

    def cancel_operation(self):
        """Cancel the current operation."""
        # Clear benchmark queue if any
        if hasattr(self, '_benchmark_queue'):
            self._benchmark_queue = []

        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.append_output("\n--- Cancelling operation... ---\n")

    def on_operation_finished(self, success: bool, message: str):
        """Handle operation completion."""
        self.set_buttons_enabled(True)

        # Properly clean up the worker thread
        if self.worker:
            self.worker.wait(5000)  # Wait up to 5 seconds for thread to finish
            self.worker.deleteLater()  # Schedule for deletion
            self.worker = None

        if success:
            self.append_output(f"\n✓ {message}\n")
            self.progress_bar.setValue(100)
        else:
            self.append_output(f"\n✗ {message}\n")

        # Refresh dependency status
        distro = self.wsl_status.get_selected_distro()
        if distro:
            self.deps_status.run_check(distro)

    def closeEvent(self, event):
        """Handle window close."""
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "Operation in Progress",
                "An operation is still running. Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.worker.cancel()
                self.worker.wait(3000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
