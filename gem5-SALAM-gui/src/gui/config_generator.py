"""
Configuration Generator Dialog for gem5-SALAM

Provides GUI for creating and editing accelerator configurations.
Integrates with the salam_config module for validation and generation.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QSpinBox,
    QTextEdit, QGroupBox, QTabWidget, QWidget, QTreeWidget,
    QTreeWidgetItem, QSplitter, QMessageBox, QFileDialog,
    QDialogButtonBox, QCheckBox, QFrame, QScrollArea
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor

from pathlib import Path
import yaml
import sys
import os


class YAMLHighlighter(QSyntaxHighlighter):
    """Simple syntax highlighter for YAML content."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_formats()

    def setup_formats(self):
        """Set up text formats for different YAML elements."""
        # Keys (words followed by colon)
        self.key_format = QTextCharFormat()
        self.key_format.setForeground(QColor("#569cd6"))
        self.key_format.setFontWeight(QFont.Bold)

        # Values (strings)
        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#ce9178"))

        # Numbers
        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor("#b5cea8"))

        # Comments
        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#6a9955"))
        self.comment_format.setFontItalic(True)

        # Booleans
        self.bool_format = QTextCharFormat()
        self.bool_format.setForeground(QColor("#569cd6"))

    def highlightBlock(self, text):
        """Highlight a block of text."""
        import re

        # Comments
        comment_pattern = re.compile(r'#.*$')
        for match in comment_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.comment_format)

        # Keys (word before colon at start of line or after spaces)
        key_pattern = re.compile(r'^(\s*)(\w[\w\s]*?)(:)')
        for match in key_pattern.finditer(text):
            self.setFormat(match.start(2), match.end(2) - match.start(2), self.key_format)

        # Strings in quotes
        string_pattern = re.compile(r'["\'].*?["\']')
        for match in string_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.string_format)

        # Numbers
        number_pattern = re.compile(r'\b\d+\.?\d*\b')
        for match in number_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.number_format)

        # Booleans
        bool_pattern = re.compile(r'\b(true|false|True|False|yes|no)\b')
        for match in bool_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.bool_format)


class ConfigGeneratorDialog(QDialog):
    """Dialog for generating and editing gem5-SALAM configurations."""

    SUPPORTED_CYCLE_TIMES = ["1ns", "2ns", "3ns", "4ns", "5ns", "6ns", "10ns"]

    def __init__(self, gem5_path: Path, parent=None):
        super().__init__(parent)
        self.gem5_path = gem5_path
        self.setWindowTitle("Configuration Generator")
        self.setMinimumSize(900, 700)
        self.current_config = {}
        self.setup_ui()
        self.discover_benchmarks()

    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Create tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # Tab 1: Basic Configuration
        self.setup_basic_tab()

        # Tab 2: Accelerator Details
        self.setup_accelerator_tab()

        # Tab 3: Hardware Configuration
        self.setup_hw_config_tab()

        # Tab 4: YAML Preview
        self.setup_preview_tab()

        # Validation output
        validation_group = QGroupBox("Validation")
        validation_layout = QVBoxLayout(validation_group)

        self.validation_output = QTextEdit()
        self.validation_output.setReadOnly(True)
        self.validation_output.setMaximumHeight(100)
        self.validation_output.setFont(QFont("Consolas", 9))
        validation_layout.addWidget(self.validation_output)

        layout.addWidget(validation_group)

        # Dialog buttons
        button_layout = QHBoxLayout()

        self.validate_btn = QPushButton("Validate")
        self.validate_btn.clicked.connect(self.validate_config)
        button_layout.addWidget(self.validate_btn)

        self.generate_btn = QPushButton("Generate Files")
        self.generate_btn.clicked.connect(self.generate_files)
        button_layout.addWidget(self.generate_btn)

        button_layout.addStretch()

        self.save_btn = QPushButton("Save Configuration")
        self.save_btn.clicked.connect(self.save_config)
        button_layout.addWidget(self.save_btn)

        self.load_btn = QPushButton("Load Configuration")
        self.load_btn.clicked.connect(self.load_config)
        button_layout.addWidget(self.load_btn)

        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Initialize preview after all widgets are created
        self.update_preview()

    def setup_basic_tab(self):
        """Set up the basic configuration tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Benchmark selection
        bench_group = QGroupBox("Benchmark")
        bench_layout = QFormLayout(bench_group)

        self.benchmark_combo = QComboBox()
        self.benchmark_combo.setMinimumWidth(300)
        self.benchmark_combo.currentTextChanged.connect(self.on_benchmark_changed)
        bench_layout.addRow("Benchmark:", self.benchmark_combo)

        self.bench_dir_combo = QComboBox()
        self.bench_dir_combo.addItems([
            "benchmarks/sys_validation",
            "benchmarks/legacy",
            "benchmarks/lenet5-nounroll",
            "benchmarks/mobilenetv2"
        ])
        self.bench_dir_combo.currentTextChanged.connect(self.discover_benchmarks)
        bench_layout.addRow("Benchmark Directory:", self.bench_dir_combo)

        layout.addWidget(bench_group)

        # Cluster configuration
        cluster_group = QGroupBox("Accelerator Cluster")
        cluster_layout = QFormLayout(cluster_group)

        self.cluster_name_edit = QLineEdit()
        self.cluster_name_edit.setPlaceholderText("e.g., my_accelerator_clstr")
        self.cluster_name_edit.textChanged.connect(self.update_preview)
        cluster_layout.addRow("Cluster Name:", self.cluster_name_edit)

        layout.addWidget(cluster_group)

        # Memory configuration
        memory_group = QGroupBox("Memory Configuration")
        memory_layout = QFormLayout(memory_group)

        self.base_addr_edit = QLineEdit("0x10020000")
        self.base_addr_edit.textChanged.connect(self.update_preview)
        memory_layout.addRow("Base Address:", self.base_addr_edit)

        self.alignment_spin = QSpinBox()
        self.alignment_spin.setRange(1, 4096)
        self.alignment_spin.setValue(64)
        self.alignment_spin.valueChanged.connect(self.update_preview)
        memory_layout.addRow("Alignment:", self.alignment_spin)

        layout.addWidget(memory_group)

        # Hardware timing
        timing_group = QGroupBox("Hardware Timing")
        timing_layout = QFormLayout(timing_group)

        self.cycle_time_combo = QComboBox()
        self.cycle_time_combo.addItems(self.SUPPORTED_CYCLE_TIMES)
        self.cycle_time_combo.setCurrentText("5ns")
        self.cycle_time_combo.currentTextChanged.connect(self.update_preview)
        timing_layout.addRow("Cycle Time:", self.cycle_time_combo)

        layout.addWidget(timing_group)

        layout.addStretch()

        self.tabs.addTab(tab, "Basic")

    def setup_accelerator_tab(self):
        """Set up the accelerator details tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Splitter for tree and details
        splitter = QSplitter(Qt.Horizontal)

        # Left side - component tree
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        tree_label = QLabel("Components:")
        left_layout.addWidget(tree_label)

        self.component_tree = QTreeWidget()
        self.component_tree.setHeaderLabels(["Component", "Type"])
        self.component_tree.itemSelectionChanged.connect(self.on_component_selected)
        left_layout.addWidget(self.component_tree)

        # Tree controls
        tree_btn_layout = QHBoxLayout()
        add_dma_btn = QPushButton("Add DMA")
        add_dma_btn.clicked.connect(self.add_dma)
        tree_btn_layout.addWidget(add_dma_btn)

        add_acc_btn = QPushButton("Add Accelerator")
        add_acc_btn.clicked.connect(self.add_accelerator)
        tree_btn_layout.addWidget(add_acc_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self.remove_component)
        tree_btn_layout.addWidget(remove_btn)

        left_layout.addLayout(tree_btn_layout)

        splitter.addWidget(left_widget)

        # Right side - component details
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        details_label = QLabel("Details:")
        right_layout.addWidget(details_label)

        self.details_stack = QWidget()
        self.details_layout = QFormLayout(self.details_stack)
        right_layout.addWidget(self.details_stack)

        splitter.addWidget(right_widget)
        splitter.setSizes([300, 400])

        layout.addWidget(splitter)

        self.tabs.addTab(tab, "Accelerators")

        # Initialize with default components
        self.init_default_components()

    def setup_hw_config_tab(self):
        """Set up the hardware configuration tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Functional units section
        fu_group = QGroupBox("Functional Units")
        fu_layout = QVBoxLayout(fu_group)

        fu_info = QLabel("Configure functional unit parameters for power modeling:")
        fu_info.setWordWrap(True)
        fu_layout.addWidget(fu_info)

        self.fu_tree = QTreeWidget()
        self.fu_tree.setHeaderLabels(["Functional Unit", "Cycles", "Limit"])
        self.fu_tree.setColumnWidth(0, 200)
        fu_layout.addWidget(self.fu_tree)

        self.populate_functional_units()

        layout.addWidget(fu_group)

        # Instructions section
        inst_group = QGroupBox("Instruction Configuration")
        inst_layout = QVBoxLayout(inst_group)

        inst_info = QLabel("Configure instruction cycle counts:")
        inst_info.setWordWrap(True)
        inst_layout.addWidget(inst_info)

        self.inst_tree = QTreeWidget()
        self.inst_tree.setHeaderLabels(["Instruction", "Runtime Cycles", "Functional Unit"])
        self.inst_tree.setColumnWidth(0, 150)
        self.inst_tree.setColumnWidth(1, 100)
        inst_layout.addWidget(self.inst_tree)

        self.populate_instructions()

        layout.addWidget(inst_group)

        self.tabs.addTab(tab, "HW Config")

    def setup_preview_tab(self):
        """Set up the YAML preview tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        preview_label = QLabel("Generated YAML Configuration:")
        layout.addWidget(preview_label)

        self.preview_text = QTextEdit()
        self.preview_text.setFont(QFont("Consolas", 10))
        self.preview_text.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; }"
        )

        # Add syntax highlighting
        self.highlighter = YAMLHighlighter(self.preview_text.document())

        layout.addWidget(self.preview_text)

        # Preview controls
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh Preview")
        refresh_btn.clicked.connect(self.update_preview)
        btn_layout.addWidget(refresh_btn)

        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self.copy_preview)
        btn_layout.addWidget(copy_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.tabs.addTab(tab, "YAML Preview")

    def discover_benchmarks(self):
        """Discover benchmarks in the selected directory."""
        self.benchmark_combo.clear()

        bench_dir = self.bench_dir_combo.currentText()
        bench_path = self.gem5_path / bench_dir

        if not bench_path.exists():
            return

        for item in sorted(bench_path.iterdir()):
            if item.is_dir() and item.name != 'common':
                # Check if it has a config or hw directory
                has_config = (item / "config.yml").exists() or (item / "config.yaml").exists()
                has_hw = (item / "hw").is_dir()

                if has_config or has_hw:
                    display = item.name
                    if has_config:
                        display += " [config]"
                    self.benchmark_combo.addItem(display, item.name)

    def on_benchmark_changed(self, text):
        """Handle benchmark selection change."""
        bench_name = self.benchmark_combo.currentData()
        if bench_name:
            self.cluster_name_edit.setText(f"{bench_name}_clstr")
            self.update_preview()

    def init_default_components(self):
        """Initialize with default DMA and accelerator."""
        self.component_tree.clear()

        # Add default DMA
        dma_item = QTreeWidgetItem(["main_dma", "DMA"])
        dma_item.setData(0, Qt.UserRole, {
            'type': 'dma',
            'name': 'main_dma',
            'dma_type': 'NonCoherent',
            'max_req_size': 128,
            'buffer_size': 256
        })
        self.component_tree.addTopLevelItem(dma_item)

        # Add default accelerator
        acc_item = QTreeWidgetItem(["compute_unit", "Accelerator"])
        acc_item.setData(0, Qt.UserRole, {
            'type': 'accelerator',
            'name': 'compute_unit',
            'ir_path': 'hw/compute.ll',
            'pio_size': 32
        })
        self.component_tree.addTopLevelItem(acc_item)

        self.update_preview()

    def add_dma(self):
        """Add a new DMA component."""
        name = f"dma_{self.component_tree.topLevelItemCount()}"
        item = QTreeWidgetItem([name, "DMA"])
        item.setData(0, Qt.UserRole, {
            'type': 'dma',
            'name': name,
            'dma_type': 'NonCoherent',
            'max_req_size': 128,
            'buffer_size': 256
        })
        self.component_tree.addTopLevelItem(item)
        self.update_preview()

    def add_accelerator(self):
        """Add a new accelerator component."""
        name = f"accelerator_{self.component_tree.topLevelItemCount()}"
        item = QTreeWidgetItem([name, "Accelerator"])
        item.setData(0, Qt.UserRole, {
            'type': 'accelerator',
            'name': name,
            'ir_path': 'hw/compute.ll',
            'pio_size': 32
        })
        self.component_tree.addTopLevelItem(item)
        self.update_preview()

    def remove_component(self):
        """Remove selected component."""
        current = self.component_tree.currentItem()
        if current:
            index = self.component_tree.indexOfTopLevelItem(current)
            if index >= 0:
                self.component_tree.takeTopLevelItem(index)
                self.update_preview()

    def on_component_selected(self):
        """Handle component selection in tree."""
        current = self.component_tree.currentItem()
        if not current:
            return

        # Clear existing details
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        data = current.data(0, Qt.UserRole)
        if not data:
            return

        if data['type'] == 'dma':
            self.show_dma_details(current, data)
        elif data['type'] == 'accelerator':
            self.show_accelerator_details(current, data)

    def show_dma_details(self, item, data):
        """Show DMA component details."""
        name_edit = QLineEdit(data.get('name', ''))
        name_edit.textChanged.connect(
            lambda t: self.update_component_data(item, 'name', t))
        self.details_layout.addRow("Name:", name_edit)

        type_combo = QComboBox()
        type_combo.addItems(['NonCoherent', 'Stream', 'Coherent'])
        type_combo.setCurrentText(data.get('dma_type', 'NonCoherent'))
        type_combo.currentTextChanged.connect(
            lambda t: self.update_component_data(item, 'dma_type', t))
        self.details_layout.addRow("Type:", type_combo)

        max_req_spin = QSpinBox()
        max_req_spin.setRange(1, 4096)
        max_req_spin.setValue(data.get('max_req_size', 128))
        max_req_spin.valueChanged.connect(
            lambda v: self.update_component_data(item, 'max_req_size', v))
        self.details_layout.addRow("Max Request Size:", max_req_spin)

        buffer_spin = QSpinBox()
        buffer_spin.setRange(1, 16384)
        buffer_spin.setValue(data.get('buffer_size', 256))
        buffer_spin.valueChanged.connect(
            lambda v: self.update_component_data(item, 'buffer_size', v))
        self.details_layout.addRow("Buffer Size:", buffer_spin)

    def show_accelerator_details(self, item, data):
        """Show accelerator component details."""
        name_edit = QLineEdit(data.get('name', ''))
        name_edit.textChanged.connect(
            lambda t: self.update_component_data(item, 'name', t))
        self.details_layout.addRow("Name:", name_edit)

        ir_edit = QLineEdit(data.get('ir_path', ''))
        ir_edit.textChanged.connect(
            lambda t: self.update_component_data(item, 'ir_path', t))
        self.details_layout.addRow("IR Path:", ir_edit)

        pio_spin = QSpinBox()
        pio_spin.setRange(1, 4096)
        pio_spin.setValue(data.get('pio_size', 32))
        pio_spin.valueChanged.connect(
            lambda v: self.update_component_data(item, 'pio_size', v))
        self.details_layout.addRow("PIO Size:", pio_spin)

    def update_component_data(self, item, key, value):
        """Update component data in tree item."""
        data = item.data(0, Qt.UserRole)
        if data:
            data[key] = value
            item.setData(0, Qt.UserRole, data)
            if key == 'name':
                item.setText(0, value)
            self.update_preview()

    def populate_functional_units(self):
        """Populate functional units tree."""
        self.fu_tree.clear()

        fus = [
            ('bit_register', 1, 0),
            ('bit_shifter', 1, 0),
            ('bitwise_operations', 1, 0),
            ('integer_adder', 1, 0),
            ('integer_multiplier', 1, 0),
            ('float_adder', 5, 0),
            ('float_multiplier', 4, 0),
            ('float_divider', 16, 0),
            ('double_adder', 5, 0),
            ('double_multiplier', 5, 0),
            ('double_divider', 32, 0),
        ]

        for name, cycles, limit in fus:
            item = QTreeWidgetItem([name, str(cycles), str(limit)])
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.fu_tree.addTopLevelItem(item)

    def populate_instructions(self):
        """Populate instructions tree."""
        self.inst_tree.clear()

        # Common instructions with default cycles and FU mapping
        instructions = [
            ('add', 1, 'integer_adder'),
            ('sub', 1, 'integer_adder'),
            ('mul', 1, 'integer_multiplier'),
            ('fadd', 5, 'float_adder'),
            ('fsub', 5, 'float_adder'),
            ('fmul', 4, 'float_multiplier'),
            ('fdiv', 16, 'float_divider'),
            ('load', 1, 'bit_register'),
            ('store', 1, 'bit_register'),
            ('shl', 1, 'bit_shifter'),
            ('lshr', 1, 'bit_shifter'),
            ('and', 1, 'bitwise_operations'),
            ('or', 1, 'bitwise_operations'),
            ('xor', 1, 'bitwise_operations'),
        ]

        for name, cycles, fu in instructions:
            item = QTreeWidgetItem([name, str(cycles), fu])
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.inst_tree.addTopLevelItem(item)

    def build_config(self) -> dict:
        """Build configuration dictionary from UI state."""
        config = {}

        # Build acc_cluster
        acc_cluster = []

        # Cluster name
        cluster_name = self.cluster_name_edit.text().strip()
        if cluster_name:
            acc_cluster.append({'Name': cluster_name})

        # Collect DMAs and accelerators
        dmas = []
        accelerators = []

        for i in range(self.component_tree.topLevelItemCount()):
            item = self.component_tree.topLevelItem(i)
            data = item.data(0, Qt.UserRole)
            if not data:
                continue

            if data['type'] == 'dma':
                dmas.append({
                    'Name': data.get('name', ''),
                    'Type': data.get('dma_type', 'NonCoherent'),
                    'MaxReqSize': data.get('max_req_size', 128),
                    'BufferSize': data.get('buffer_size', 256)
                })
            elif data['type'] == 'accelerator':
                accelerators.append({
                    'Name': data.get('name', ''),
                    'IrPath': data.get('ir_path', ''),
                    'PIOSize': data.get('pio_size', 32)
                })

        if dmas:
            acc_cluster.append({'DMA': dmas})

        if accelerators:
            acc_cluster.append({'Accelerator': accelerators})

        config['acc_cluster'] = acc_cluster

        # Build global config
        config['global'] = {
            'memory': {
                'base_address': self.base_addr_edit.text().strip(),
                'alignment': self.alignment_spin.value()
            }
        }

        # Build hw_config
        bench_name = self.benchmark_combo.currentData() or 'benchmark'
        hw_config = {
            bench_name: {
                'cycle_time': self.cycle_time_combo.currentText(),
                'functional_units': {},
                'instructions': {}
            }
        }

        # Add functional units
        for i in range(self.fu_tree.topLevelItemCount()):
            item = self.fu_tree.topLevelItem(i)
            name = item.text(0)
            try:
                cycles = int(item.text(1))
                limit = int(item.text(2))
                hw_config[bench_name]['functional_units'][name] = {
                    'cycles': cycles,
                    'limit': limit
                }
            except ValueError:
                pass

        # Add instructions
        for i in range(self.inst_tree.topLevelItemCount()):
            item = self.inst_tree.topLevelItem(i)
            name = item.text(0)
            try:
                cycles = int(item.text(1))
                fu = item.text(2)
                hw_config[bench_name]['instructions'][name] = {
                    'runtime_cycles': cycles,
                    'functional_unit': fu
                }
            except ValueError:
                pass

        config['hw_config'] = hw_config

        return config

    def update_preview(self):
        """Update the YAML preview."""
        # Guard: preview_text may not exist during initial setup
        if not hasattr(self, 'preview_text'):
            return

        try:
            config = self.build_config()
            yaml_text = yaml.dump(config, default_flow_style=False, sort_keys=False)
            self.preview_text.setPlainText(yaml_text)
            self.current_config = config
        except Exception as e:
            self.preview_text.setPlainText(f"Error generating preview: {e}")

    def copy_preview(self):
        """Copy YAML preview to clipboard."""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.preview_text.toPlainText())
        self.validation_output.append("Copied to clipboard!")

    def validate_config(self):
        """Validate the current configuration."""
        self.validation_output.clear()

        try:
            config = self.build_config()

            # Try to use salam_config validator if available
            try:
                sys.path.insert(0, str(self.gem5_path))
                from salam_config.core.schema_validator import validate_config
                result = validate_config(config)

                if result.is_valid:
                    self.validation_output.append("Configuration is VALID")
                    if result.warnings:
                        self.validation_output.append("\nWarnings:")
                        for warning in result.warnings:
                            self.validation_output.append(f"  - {warning}")
                else:
                    self.validation_output.append("Configuration is INVALID")
                    self.validation_output.append("\nErrors:")
                    for error in result.errors:
                        self.validation_output.append(f"  - {error}")
                    if result.warnings:
                        self.validation_output.append("\nWarnings:")
                        for warning in result.warnings:
                            self.validation_output.append(f"  - {warning}")

            except ImportError:
                # Fallback basic validation
                self.validation_output.append("(Using basic validation - salam_config not available)")
                self.validation_output.append("")

                if 'acc_cluster' not in config:
                    self.validation_output.append("ERROR: Missing 'acc_cluster' section")
                else:
                    self.validation_output.append("OK: 'acc_cluster' section present")

                if 'hw_config' in config:
                    self.validation_output.append("OK: 'hw_config' section present")

                self.validation_output.append("\nBasic validation passed!")

        except Exception as e:
            self.validation_output.append(f"Validation error: {e}")

    def generate_files(self):
        """Generate configuration files."""
        bench_name = self.benchmark_combo.currentData()
        if not bench_name:
            QMessageBox.warning(self, "No Benchmark", "Please select a benchmark first.")
            return

        try:
            config = self.build_config()
            bench_dir = self.bench_dir_combo.currentText()

            # Save the YAML config file
            output_path = self.gem5_path / bench_dir / bench_name / "config.yml"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            generated_files = [str(output_path)]

            # Ask if user wants to run full generation via WSL
            reply = QMessageBox.question(
                self, "Run Full Generation?",
                f"Configuration saved to:\n{output_path}\n\n"
                "Do you want to run the full generation process?\n"
                "This will generate Python configs, C headers, and HW profile files.\n\n"
                "(Requires M5_PATH to be set in WSL)",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                # Run generation through WSL using the CLI
                self._run_generation_in_wsl(bench_name, bench_dir, generated_files)
            else:
                self.validation_output.clear()
                self.validation_output.append("Generated files:")
                for f in generated_files:
                    self.validation_output.append(f"  - {f}")

                QMessageBox.information(
                    self, "Configuration Saved",
                    f"Configuration saved to:\n{output_path}"
                )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Generation failed: {e}")

    def _run_generation_in_wsl(self, bench_name: str, bench_dir: str, generated_files: list):
        """Run the full generation process through WSL."""
        import subprocess

        # Get parent window's WSL distro selection
        parent = self.parent()
        distro = None
        if parent and hasattr(parent, 'wsl_status'):
            distro = parent.wsl_status.get_selected_distro()

        if not distro:
            QMessageBox.warning(
                self, "No WSL Distribution",
                "Please select a WSL distribution in the main window."
            )
            return

        # First, get M5_PATH value via grep (same approach as main_window.py)
        # This works around .bashrc early exit guard for non-interactive shells
        m5_path_cmd = (
            "grep -h 'export M5_PATH=' ~/.bashrc ~/.profile 2>/dev/null | "
            "tail -1 | sed 's/.*M5_PATH=[\"]*\\([^\"]*\\)[\"]*$/\\1/'"
        )
        try:
            m5_result = subprocess.run(
                ['wsl', '-d', distro, 'bash', '-c', m5_path_cmd],
                capture_output=True, text=True, timeout=10
            )
            m5_path = m5_result.stdout.strip()
        except Exception:
            m5_path = ""

        if not m5_path:
            QMessageBox.warning(
                self, "M5_PATH Not Set",
                "Could not determine M5_PATH from WSL environment.\n"
                "Please ensure M5_PATH is exported in ~/.bashrc or ~/.profile."
            )
            return

        cycle_time = self.cycle_time_combo.currentText()

        # Build the CLI command using the actual M5_PATH value (not shell variable)
        cli_cmd = (
            f"export M5_PATH='{m5_path}' && "
            f"export PYTHONPATH='{m5_path}':$PYTHONPATH && "
            f"cd '{m5_path}' && python3 -m salam_config.cli generate "
            f"-b '{bench_name}' "
            f"-d '{bench_dir}' "
            f"--cycle-time '{cycle_time}' "
            f"-v"
        )

        self.validation_output.clear()
        self.validation_output.append(f"Running generation in WSL ({distro})...")
        self.validation_output.append(f"Command: {cli_cmd}")
        self.validation_output.append("")

        try:
            # Run the command through WSL (no -l needed since we set env vars explicitly)
            result = subprocess.run(
                ['wsl', '-d', distro, 'bash', '-c', cli_cmd],
                capture_output=True, text=True, timeout=60
            )

            # Show output
            if result.stdout:
                self.validation_output.append("Output:")
                for line in result.stdout.strip().split('\n'):
                    self.validation_output.append(f"  {line}")

            if result.stderr:
                self.validation_output.append("\nErrors/Warnings:")
                for line in result.stderr.strip().split('\n'):
                    self.validation_output.append(f"  {line}")

            if result.returncode == 0:
                self.validation_output.append("\nGeneration completed successfully!")
                QMessageBox.information(
                    self, "Generation Complete",
                    "Full generation completed successfully!\n"
                    "Check the validation output for details."
                )
            else:
                self.validation_output.append(f"\nGeneration failed with exit code {result.returncode}")
                QMessageBox.warning(
                    self, "Generation Failed",
                    f"Generation failed with exit code {result.returncode}\n"
                    "Check the validation output for details."
                )

        except subprocess.TimeoutExpired:
            self.validation_output.append("\nGeneration timed out after 60 seconds")
            QMessageBox.warning(self, "Timeout", "Generation timed out after 60 seconds.")
        except Exception as e:
            self.validation_output.append(f"\nError: {e}")
            QMessageBox.critical(self, "Error", f"Failed to run generation: {e}")

    def save_config(self):
        """Save configuration to a file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Configuration",
            str(self.gem5_path / "config.yml"),
            "YAML Files (*.yml *.yaml);;All Files (*)"
        )

        if path:
            try:
                config = self.build_config()
                with open(path, 'w') as f:
                    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
                self.validation_output.append(f"Saved to: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def load_config(self):
        """Load configuration from a file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Configuration",
            str(self.gem5_path),
            "YAML Files (*.yml *.yaml);;All Files (*)"
        )

        if path:
            try:
                with open(path, 'r') as f:
                    config = yaml.safe_load(f)

                self.apply_config(config)
                self.validation_output.append(f"Loaded from: {path}")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load: {e}")

    def apply_config(self, config: dict):
        """Apply a loaded configuration to the UI."""
        # Apply acc_cluster
        if 'acc_cluster' in config:
            self.component_tree.clear()

            for item in config['acc_cluster']:
                if 'Name' in item:
                    self.cluster_name_edit.setText(item['Name'])
                elif 'DMA' in item:
                    for dma in item['DMA']:
                        tree_item = QTreeWidgetItem([dma.get('Name', 'dma'), "DMA"])
                        tree_item.setData(0, Qt.UserRole, {
                            'type': 'dma',
                            'name': dma.get('Name', ''),
                            'dma_type': dma.get('Type', 'NonCoherent'),
                            'max_req_size': dma.get('MaxReqSize', 128),
                            'buffer_size': dma.get('BufferSize', 256)
                        })
                        self.component_tree.addTopLevelItem(tree_item)
                elif 'Accelerator' in item:
                    for acc in item['Accelerator']:
                        if 'Name' in acc:
                            tree_item = QTreeWidgetItem([acc.get('Name', 'acc'), "Accelerator"])
                            tree_item.setData(0, Qt.UserRole, {
                                'type': 'accelerator',
                                'name': acc.get('Name', ''),
                                'ir_path': acc.get('IrPath', ''),
                                'pio_size': acc.get('PIOSize', 32)
                            })
                            self.component_tree.addTopLevelItem(tree_item)

        # Apply global settings
        if 'global' in config:
            glob = config['global']
            if 'memory' in glob:
                if 'base_address' in glob['memory']:
                    self.base_addr_edit.setText(str(glob['memory']['base_address']))
                if 'alignment' in glob['memory']:
                    self.alignment_spin.setValue(glob['memory']['alignment'])

        self.update_preview()
