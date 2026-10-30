"""Qt adapter for live SALAM GUI edits and asynchronous checked execution."""
import json
import os
import re
from copy import deepcopy
from pathlib import Path

import yaml
from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .gui_editor import (
    MODEL_FLOAT_FIELDS,
    MODEL_INT_FIELDS,
    build_gui_request,
    discover_profile_periods,
    extract_components,
    read_fu_ids,
    read_fu_registry,
    render_document,
    source_hash,
)

WORKBENCH_HOST = Path(__file__).resolve().parents[1]
MODEL_FIELDS = MODEL_FLOAT_FIELDS + MODEL_INT_FIELDS


def _editable(item):
    item.setFlags(item.flags() | Qt.ItemIsEditable)
    return item


def _selected_file(dialog):
    bench_name = dialog.benchmark_combo.currentData()
    bench_dir = dialog.bench_dir_combo.currentText()
    if not isinstance(bench_name, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]+", bench_name
    ):
        raise ValueError("Select a benchmark")
    if bench_dir not in (
        "benchmarks/sys_validation",
        "benchmarks/legacy",
        "benchmarks/lenet5-nounroll",
        "benchmarks/mobilenetv2",
    ):
        raise ValueError("Unsupported benchmark directory")
    benchmark = bench_dir + "/" + bench_name
    root = dialog.gem5_path.resolve(strict=True)
    for filename in ("config.yml", "config.yaml"):
        path = root / benchmark / filename
        if path.is_file():
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
            if resolved != path:
                raise ValueError("Symlinked GUI source YAML is unsupported")
            return benchmark, path
    raise ValueError("Selected benchmark has no configuration YAML")


def _rows(tree, *, hardware):
    rows = {}
    seen = set()
    for index in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(index)
        name = item.text(0).strip()
        if not name:
            continue
        if name in seen:
            raise ValueError("Duplicate visible " + hardware + " row: " + name)
        seen.add(name)
        if hardware == "fu":
            cycles = item.text(1).strip()
            limit = item.text(2).strip()
            if not cycles and not limit and not item.data(0, Qt.UserRole):
                continue
            if not cycles or not limit:
                raise ValueError(
                    "Incomplete visible FU row: "
                    + name
                    + " (cycles and limit, including 0, are required)"
                )
            rows[name] = {"cycles": cycles, "limit": limit}
        else:
            runtime = item.text(1).strip()
            selector = tree.itemWidget(item, 2)
            unit = (
                selector.currentData() if selector is not None else item.text(2).strip()
            )
            if not runtime or unit in (None, ""):
                raise ValueError(
                    "Incomplete visible instruction row: "
                    + name
                    + " (runtime cycles and FU ID, including 0, are required)"
                )
            rows[name] = {"runtime_cycles": runtime, "functional_unit": unit}
    return rows


def _fill_rows(dialog, target):
    doc = dialog._base_document or {}
    hardware = doc.get("hw_config", {}) if isinstance(doc, dict) else {}
    key = next(
        (
            name
            for name in hardware
            if isinstance(name, str) and name.lower() == target.lower()
        ),
        target,
    )
    source_settings = hardware.get(key) or {}
    if not isinstance(source_settings, dict):
        raise ValueError("Hardware settings are not a mapping")
    table = dialog._hardware_tables.get(target)
    fu = (table or {}).get(
        "functional_units", source_settings.get("functional_units", {})
    )
    inst = (table or {}).get("instructions", source_settings.get("instructions", {}))
    if not isinstance(fu, dict) or not isinstance(inst, dict):
        raise ValueError("Hardware tables must be mappings")
    dialog.fu_tree.clear()
    registry = read_fu_registry(dialog.gem5_path)
    for name in list(registry) + sorted(set(fu) - set(registry)):
        values = fu.get(name, {})
        if not isinstance(values, dict):
            raise ValueError("FU row is not a mapping")
        item = _editable(
            QTreeWidgetItem(
                dialog.fu_tree,
                [
                    name,
                    str(values.get("cycles", "")),
                    str(values.get("limit", "")),
                ],
            )
        )
        item.setData(0, Qt.UserRole, name in fu)
    dialog.inst_tree.clear()
    fu_ids = read_fu_ids(dialog.gem5_path)
    for name, values in inst.items():
        if not isinstance(values, dict):
            raise ValueError("Instruction row is not a mapping")
        value = values.get("functional_unit", "")
        item = _editable(
            QTreeWidgetItem(
                dialog.inst_tree,
                [name, str(values.get("runtime_cycles", "")), str(value)],
            )
        )
        selector = QComboBox()
        selector.addItem("0 — unassigned", 0)
        for fu_name, fu_id in fu_ids.items():
            selector.addItem(str(fu_id) + " — " + fu_name, fu_id)
        if value not in [selector.itemData(i) for i in range(selector.count())]:
            # Preserve a source value exactly, including an unknown numeric ID.
            selector.addItem(str(value) + " — source value", value)
        selector.setCurrentIndex(
            next(i for i in range(selector.count()) if selector.itemData(i) == value)
        )
        selector.currentIndexChanged.connect(dialog.update_preview)
        dialog.inst_tree.setItemWidget(item, 2, selector)


def _model_overrides(dialog):
    result = {}
    for index in range(dialog.model_tree.topLevelItemCount()):
        row = dialog.model_tree.topLevelItem(index)
        name = row.text(0).strip()
        if name in result:
            raise ValueError("Duplicate visible model FU row: " + name)
        fields = {
            field: row.text(offset + 1).strip()
            for offset, field in enumerate(MODEL_FIELDS)
            if row.text(offset + 1).strip()
        }
        if fields:
            result[name] = fields
        else:
            result[name] = {}
    return {name: values for name, values in result.items() if values}


def _editor_snapshot(dialog):
    if dialog._active_hardware_target:
        dialog._hardware_tables[dialog._active_hardware_target] = {
            "functional_units": _rows(dialog.fu_tree, hardware="fu"),
            "instructions": _rows(dialog.inst_tree, hardware="instruction"),
        }
    components = [
        deepcopy(dialog.component_tree.topLevelItem(i).data(0, Qt.UserRole))
        for i in range(dialog.component_tree.topLevelItemCount())
    ]
    current = dialog._hardware_tables.get(dialog._active_hardware_target, {})
    snapshot = {
        "cluster_name": dialog.cluster_name_edit.text().strip(),
        "components": components,
        "hardware_target": dialog._active_hardware_target,
        "hardware_by_accelerator": deepcopy(dialog._hardware_tables),
        "functional_units": deepcopy(current.get("functional_units", {})),
        "instructions": deepcopy(current.get("instructions", {})),
        "base_address": dialog.base_addr_edit.text().strip(),
        "alignment": dialog.alignment_spin.value(),
        "system": {
            "mem-size": dialog.mem_size_edit.text().strip(),
            "mem-type": dialog.mem_type_edit.text().strip(),
            "cpu-clock": dialog.cpu_clock_edit.text().strip(),
            "sys-clock": dialog.sys_clock_edit.text().strip(),
        },
        "hardware_profile": {
            "model": dialog.model_edit.text().strip(),
            "period": dialog.cycle_time_combo.currentText(),
            "profile": dialog.profile_edit.text().strip(),
            "fu_overrides": _model_overrides(dialog),
        },
        "source_legacy_cycle_time": deepcopy(dialog._legacy_cycle_times),
    }
    if dialog.input_case_combo.currentData() is not None:
        snapshot["benchmark_input"] = {
            "dataset": dialog.input_case_combo.currentData(),
            "seed": dialog.input_seed_spin.value(),
        }
    if dialog.trace_budget_check.isChecked():
        snapshot["trace_event_limit"] = dialog.trace_budget_spin.value()
    return snapshot


def _populate_model_tree(dialog):
    dialog.model_tree.clear()
    for name in read_fu_registry(dialog.gem5_path):
        _editable(QTreeWidgetItem(dialog.model_tree, [name] + [""] * len(MODEL_FIELDS)))


def _fu_telemetry_lines(receipt):
    """Readable counters from a verified GUI receipt; no derived power claims."""
    summary = receipt.get("fu_scheduling_summary")
    if (
        not isinstance(summary, dict)
        or summary.get("state") != "validated_direct_salam_trace"
    ):
        return []
    lines = ["FU scheduling (validated direct SALAM trace):"]
    for invocation in summary.get("invocations", []):
        accelerator = invocation.get("accelerator", "unknown accelerator")
        for unit in invocation.get("units", []):
            limit = unit["limit"]
            capacity = "unlimited" if limit == 0 else "capacity " + str(limit)
            lines.append(
                "  {} / {} ({}): issue attempts {}, grants {}, blocked {}, "
                "releases {}, peak {}, outstanding {}".format(
                    accelerator,
                    unit["name"],
                    capacity,
                    unit["attempts"],
                    unit["grants"],
                    unit["denials"],
                    unit["releases"],
                    unit["peak"],
                    unit["outstanding"],
                )
            )
    if len(lines) == 1:
        lines.append("  No active or capped functional units in this invocation.")
    return lines


def _workbench_event(dialog, name, **payload):
    """Optional desktop-shell observer; the checked backend remains the authority."""
    listener = getattr(dialog, "_workbench_listener", None)
    if listener is not None:
        listener(name, payload)


def install_editor(dialog_class):
    """Upgrade only the independent GUI class after its source has loaded."""
    old_init = dialog_class.__init__
    old_basic = dialog_class.setup_basic_tab
    old_acc_tab = dialog_class.setup_accelerator_tab
    old_hw_tab = dialog_class.setup_hw_config_tab
    old_dma_details = dialog_class.show_dma_details
    old_acc_details = dialog_class.show_accelerator_details
    old_component_selected = dialog_class.on_component_selected
    old_add_accelerator = dialog_class.add_accelerator
    old_update_data = dialog_class.update_component_data

    def init(self, gem5_path, parent=None):
        self._base_document = None
        self._source_config_relative = None
        self._source_sha256 = None
        self._hardware_tables = {}
        self._active_hardware_target = None
        self._editor_loading = False
        self._gui_process = None
        self._gui_process_output = ""
        self._gui_summary = None
        self._backend_command_provider = None
        self._legacy_cycle_times = {}
        old_init(self, gem5_path, parent)
        self.generate_btn.setText("Apply edits, rebuild & run (checked)")
        self.generate_btn.setToolTip(
            "Exports all edited controls; generates, rebuilds as needed, runs gem5, and checks receipts"
        )
        self.validate_btn.setText("Check editor request")

    def setup_basic_tab(self):
        old_basic(self)
        self.alignment_spin.setRange(64, 64)
        self.alignment_spin.setToolTip(
            "The current generator uses fixed 64-byte address alignment"
        )
        self.cycle_time_combo.blockSignals(True)
        self.cycle_time_combo.clear()
        self.cycle_time_combo.blockSignals(False)
        tab = self.tabs.widget(0)
        layout = tab.layout()
        system_group = QGroupBox("System settings for this run")
        system = QFormLayout(system_group)
        self.mem_size_edit = QLineEdit("4GB")
        self.mem_type_edit = QLineEdit("DDR4_2400_8x8")
        self.cpu_clock_edit = QLineEdit()
        self.sys_clock_edit = QLineEdit()
        for label, widget in (
            ("Memory size:", self.mem_size_edit),
            ("DRAM type:", self.mem_type_edit),
            ("CPU clock (optional):", self.cpu_clock_edit),
            ("System clock (optional):", self.sys_clock_edit),
        ):
            widget.textChanged.connect(self.update_preview)
            system.addRow(label, widget)
        layout.insertWidget(layout.count() - 1, system_group)
        profile_group = QGroupBox("Generated hardware model")
        profile_form = QFormLayout(profile_group)
        self.model_edit = QLineEdit("40nm_model")
        self.profile_edit = QLineEdit("default_profile")
        self.model_edit.textChanged.connect(self.update_preview)
        self.profile_edit.textChanged.connect(self.update_preview)
        self.model_edit.textChanged.connect(self._refresh_periods)
        self.profile_edit.textChanged.connect(self._refresh_periods)
        profile_form.addRow("Model:", self.model_edit)
        profile_form.addRow("Profile:", self.profile_edit)
        layout.insertWidget(layout.count() - 1, profile_group)
        input_group = QGroupBox("Benchmark input and independent output check")
        input_form = QFormLayout(input_group)
        self.input_case_combo = QComboBox()
        self.input_case_combo.addItem("Original source input / guest checker", None)
        self.input_case_combo.addItem(
            "Generated input / independent full-output check", "seeded"
        )
        self.input_case_combo.addItem(
            "Zero input / independent full-output check", "zeros"
        )
        self.input_case_combo.addItem(
            "Boundary input / independent full-output check", "boundary"
        )
        self.input_seed_spin = QSpinBox()
        self.input_seed_spin.setRange(0, 2147483647)
        self.input_seed_spin.setValue(1)
        self.trace_budget_spin = QSpinBox()
        self.trace_budget_spin.setRange(1, 4194304)
        self.trace_budget_spin.setValue(262144)
        from .benchmark_validation import trace_budget_source_supported

        self.trace_budget_check = QCheckBox("Override scheduling trace event budget:")
        self.trace_budget_check.setEnabled(
            trace_budget_source_supported(self.gem5_path)
        )
        self.trace_budget_spin.setEnabled(False)
        self.trace_budget_check.toggled.connect(self.trace_budget_spin.setEnabled)
        self.trace_budget_check.toggled.connect(self.update_preview)
        self.trace_budget_spin.setToolTip(
            "Maximum recorded functional-unit events per accelerator invocation. Truncated traces fail validation. Requires the updated simulator; full-size stencil studies use 1048576."
        )
        self.input_seed_spin.setToolTip(
            "Deterministic input seed; supported for sys_validation GEMM, FFT and stencil3d at their current fixed dimensions"
        )
        self.input_case_combo.currentIndexChanged.connect(self.update_preview)
        self.input_seed_spin.valueChanged.connect(self.update_preview)
        self.trace_budget_spin.valueChanged.connect(self.update_preview)
        input_form.addRow("Input:", self.input_case_combo)
        input_form.addRow("Seed:", self.input_seed_spin)
        input_form.addRow(self.trace_budget_check, self.trace_budget_spin)
        layout.insertWidget(0, input_group)
        self._refresh_periods(preferred="5ns")

    def _refresh_periods(self, *_args, preferred=None):
        current = (
            preferred if preferred is not None else self.cycle_time_combo.currentText()
        )
        try:
            benchmark, _ = _selected_file(self)
            periods = discover_profile_periods(
                self.gem5_path,
                benchmark,
                self.model_edit.text().strip(),
                self.profile_edit.text().strip(),
            )
            message = (
                (
                    "Choose a period backed by a hardware model directory. "
                    "The full profile is validated when you apply edits."
                )
                if periods
                else "No source-backed profile periods for this selection."
            )
        except Exception as error:
            periods = []
            message = "No source-backed profile periods for this selection: " + str(
                error
            )
        self.cycle_time_combo.blockSignals(True)
        self.cycle_time_combo.clear()
        self.cycle_time_combo.addItems(periods)
        self.cycle_time_combo.setCurrentIndex(
            periods.index(current) if current in periods else -1
        )
        self.cycle_time_combo.setEnabled(bool(periods))
        legacy = getattr(self, "_legacy_cycle_times", {})
        if legacy:
            message += (
                " Legacy GUI cycle_time metadata (previously ignored): "
                + repr(legacy)
                + ". The selected period controls generation."
            )
        self.cycle_time_combo.setToolTip(message)
        self.cycle_time_combo.blockSignals(False)
        if hasattr(self, "preview_text"):
            self.update_preview()

    def setup_accelerator_tab(self):
        old_acc_tab(self)
        add_memory = QPushButton("Add Memory / Register")
        add_memory.clicked.connect(self.add_memory)
        self.tabs.widget(1).layout().addWidget(add_memory)

    def setup_hw_config_tab(self):
        old_hw_tab(self)
        tab = self.tabs.widget(2)
        layout = tab.layout()
        target_group = QGroupBox("Accelerator receiving instruction and FU settings")
        form = QFormLayout(target_group)
        self.hardware_target_combo = QComboBox()
        self.hardware_target_combo.currentTextChanged.connect(
            self._select_hardware_target
        )
        form.addRow("Accelerator:", self.hardware_target_combo)
        layout.insertWidget(0, target_group)
        add_instruction = QPushButton("Add Instruction Row")
        add_instruction.clicked.connect(self._add_instruction_row)
        layout.addWidget(add_instruction)
        model_group = QGroupBox("Compile-time FU model overrides (blank = inherit)")
        model_layout = QVBoxLayout(model_group)
        self.model_tree = QTreeWidget()
        self.model_tree.setHeaderLabels(["Functional Unit"] + list(MODEL_FIELDS))
        self.model_tree.setMinimumHeight(210)
        model_layout.addWidget(self.model_tree)
        layout.addWidget(model_group)

    def _add_instruction_row(self):
        name, ok = QInputDialog.getText(
            self, "Instruction name", "Runtime instruction registry name:"
        )
        if ok and name:
            _editable(QTreeWidgetItem(self.inst_tree, [name.strip(), "", ""]))

    def on_benchmark_changed(self, text):
        if not self.benchmark_combo.currentData():
            return
        try:
            benchmark, path = _selected_file(self)
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
            if len(documents) != 1:
                raise ValueError(
                    "GUI editor supports one YAML document; multi-document sources remain explicit"
                )
            self.apply_config(documents[0], source_path=path)
        except Exception as error:
            self._base_document = None
            if hasattr(self, "validation_output"):
                self.validation_output.append(
                    "Could not load selected YAML: " + str(error)
                )

    def apply_config(self, config, source_path=None):
        cluster, components = extract_components(config)
        self._editor_loading = True
        try:
            self._base_document = deepcopy(config)
            hardware = config.get("hw_config", {}) or {}
            self._legacy_cycle_times = {
                key: value["cycle_time"]
                for key, value in hardware.items()
                if isinstance(value, dict) and "cycle_time" in value
            }
            self._hardware_tables = {}
            self._active_hardware_target = None
            if source_path is not None:
                source_path = Path(source_path).resolve(strict=True)
                root = self.gem5_path.resolve(strict=True)
                self._source_config_relative = source_path.relative_to(root).as_posix()
                self._source_sha256 = source_hash(source_path)
            self.cluster_name_edit.setText(cluster)
            self.component_tree.clear()
            for data in components:
                title = data["name"]
                kind = data["type"]
                item = QTreeWidgetItem(self.component_tree, [title, kind.title()])
                item.setData(0, Qt.UserRole, data)
            global_config = config.get("global", {}) or {}
            memory = (
                global_config.get("memory", {})
                if isinstance(global_config, dict)
                else {}
            )
            self.base_addr_edit.setText(str(memory.get("base_address", "0x10020000")))
            self.alignment_spin.setValue(int(memory.get("alignment", 64)))
            self.mem_size_edit.setText("4GB")
            self.mem_type_edit.setText("DDR4_2400_8x8")
            self.cpu_clock_edit.clear()
            self.sys_clock_edit.clear()
            self.model_edit.setText("40nm_model")
            self.profile_edit.setText("default_profile")
            self._refresh_periods(preferred="5ns")
            self.hardware_target_combo.blockSignals(True)
            self.hardware_target_combo.clear()
            accelerators = [
                item["name"] for item in components if item["type"] == "accelerator"
            ]
            self.hardware_target_combo.addItems(accelerators)
            target = next(
                (
                    name
                    for name in accelerators
                    if isinstance(hardware.get(name.lower()), dict)
                ),
                None,
            )
            if target is None and accelerators:
                target = accelerators[0]
            if target:
                self.hardware_target_combo.setCurrentText(target)
            self.hardware_target_combo.blockSignals(False)
            _populate_model_tree(self)
            if target:
                self._active_hardware_target = target
                _fill_rows(self, target)
            else:
                self.fu_tree.clear()
                self.inst_tree.clear()
        finally:
            self._editor_loading = False
        self.update_preview()

    def _select_hardware_target(self, target):
        if self._editor_loading or not target:
            return
        if self._active_hardware_target:
            self._hardware_tables[self._active_hardware_target] = {
                "functional_units": _rows(self.fu_tree, hardware="fu"),
                "instructions": _rows(self.inst_tree, hardware="instruction"),
            }
        self._active_hardware_target = target
        _fill_rows(self, target)
        self.update_preview()

    def add_memory(self):
        accelerators = [
            self.component_tree.topLevelItem(i).data(0, Qt.UserRole)
            for i in range(self.component_tree.topLevelItemCount())
            if self.component_tree.topLevelItem(i).data(0, Qt.UserRole).get("type")
            == "accelerator"
        ]
        if not accelerators:
            QMessageBox.warning(
                self, "No Accelerator", "Add an accelerator before memory."
            )
            return
        selected = self.component_tree.currentItem()
        selected_data = selected.data(0, Qt.UserRole) if selected else {}
        owner = (
            selected_data.get("name")
            if selected_data.get("type") == "accelerator"
            else selected_data.get("owner", accelerators[-1]["name"])
        )
        name = "memory_" + str(self.component_tree.topLevelItemCount())
        data = {
            "type": "memory",
            "owner": owner,
            "fields": {},
            "name": name,
            "memory_type": "SPM",
            "size": 64,
            "ports": 1,
            "connections": "",
            "ready_mode": None,
            "reset_on_read": None,
            "read_on_invalid": None,
            "write_on_valid": None,
        }
        item = QTreeWidgetItem(self.component_tree, [name, "Memory"])
        item.setData(0, Qt.UserRole, data)
        self.update_preview()

    def add_accelerator(self):
        old_add_accelerator(self)
        item = self.component_tree.topLevelItem(
            self.component_tree.topLevelItemCount() - 1
        )
        data = item.data(0, Qt.UserRole)
        bench = self.benchmark_combo.currentData()
        if bench:
            data["ir_path"] = (
                self.bench_dir_combo.currentText() + "/" + bench + "/hw/compute.ll"
            )
            data["pio_master"] = "LocalBus"
            data["fields"] = {}
            item.setData(0, Qt.UserRole, data)
        self.hardware_target_combo.addItem(data["name"])

    def update_component_data(self, item, key, value):
        data = item.data(0, Qt.UserRole)
        old_name = data.get("name") if data else None
        if data and data.get("type") == "accelerator" and key == "name":
            for index in range(self.component_tree.topLevelItemCount()):
                other = self.component_tree.topLevelItem(index)
                contents = other.data(0, Qt.UserRole)
                if (
                    contents
                    and contents.get("type") == "memory"
                    and contents.get("owner") == old_name
                ):
                    contents["owner"] = value
                    other.setData(0, Qt.UserRole, contents)
            position = self.hardware_target_combo.findText(old_name)
            if position >= 0:
                self.hardware_target_combo.setItemText(position, value)
        old_update_data(self, item, key, value)

    def on_component_selected(self):
        current = self.component_tree.currentItem()
        if current and current.data(0, Qt.UserRole).get("type") == "memory":
            while self.details_layout.count():
                item = self.details_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            data = current.data(0, Qt.UserRole)
            self.show_memory_details(current, data)
        else:
            old_component_selected(self)

    def show_dma_details(self, item, data):
        old_dma_details(self, item, data)
        master = QLineEdit(str(data.get("pio_master", "LocalBus")))
        master.textChanged.connect(
            lambda value: self.update_component_data(item, "pio_master", value)
        )
        self.details_layout.addRow("PIO master:", master)
        interrupt = QLineEdit(
            "" if data.get("interrupt_num") is None else str(data["interrupt_num"])
        )
        interrupt.textChanged.connect(
            lambda value: self.update_component_data(item, "interrupt_num", value)
        )
        self.details_layout.addRow("Interrupt number:", interrupt)

    def show_accelerator_details(self, item, data):
        old_acc_details(self, item, data)
        for row in range(self.details_layout.rowCount()):
            label = self.details_layout.itemAt(row, QFormLayout.LabelRole)
            field = self.details_layout.itemAt(row, QFormLayout.FieldRole)
            if label and field and label.widget().text() == "Name:":
                field.widget().setReadOnly(True)
                field.widget().setToolTip(
                    "Accelerator identity is tied to the IR basename, hw_config key, "
                    "and generated C header. Rename migration is not yet supported."
                )
            elif label and field and label.widget().text() == "IR Path:":
                field.widget().setToolTip(
                    "The IR basename must match this accelerator's consumed hw_config key."
                )
        for label, key in (
            ("PIO master:", "pio_master"),
            ("Local slaves:", "local_slaves"),
            ("ConfigPath YAML:", "config_path"),
            ("Interrupt number:", "interrupt_num"),
        ):
            value = data.get(key)
            field = QLineEdit("" if value is None else str(value))
            field.textChanged.connect(
                lambda text, k=key: self.update_component_data(item, k, text)
            )
            self.details_layout.addRow(label, field)
        debug = QCheckBox()
        debug.setChecked(bool(data.get("debug", False)))
        debug.toggled.connect(
            lambda enabled: self.update_component_data(item, "debug", enabled)
        )
        self.details_layout.addRow("Debug:", debug)

    def show_memory_details(self, item, data):
        name = QLineEdit(str(data.get("name", "")))
        name.textChanged.connect(
            lambda value: self.update_component_data(item, "name", value)
        )
        self.details_layout.addRow("Name:", name)
        owner = QComboBox()
        owners = [
            self.component_tree.topLevelItem(i).data(0, Qt.UserRole)["name"]
            for i in range(self.component_tree.topLevelItemCount())
            if self.component_tree.topLevelItem(i).data(0, Qt.UserRole).get("type")
            == "accelerator"
        ]
        owner.addItems(owners)
        owner.setCurrentText(data.get("owner", ""))
        owner.currentTextChanged.connect(
            lambda value: self.update_component_data(item, "owner", value)
        )
        self.details_layout.addRow("Accelerator:", owner)
        kind = QComboBox()
        kind.addItems(["SPM", "RegisterBank"])
        kind.setCurrentText(data.get("memory_type", "SPM"))
        kind.currentTextChanged.connect(
            lambda value: self.update_component_data(item, "memory_type", value)
        )
        self.details_layout.addRow("Memory type:", kind)
        size = QSpinBox()
        size.setRange(1, 0x7FFFFFFF)
        size.setValue(int(data.get("size", 64)))
        size.valueChanged.connect(
            lambda value: self.update_component_data(item, "size", value)
        )
        self.details_layout.addRow("Size (bytes):", size)
        ports = QSpinBox()
        ports.setRange(1, 1024)
        ports.setValue(int(data.get("ports") or 1))
        ports.valueChanged.connect(
            lambda value: self.update_component_data(item, "ports", value)
        )
        self.details_layout.addRow("Ports:", ports)
        connections = QLineEdit(str(data.get("connections", "")))
        connections.textChanged.connect(
            lambda value: self.update_component_data(item, "connections", value)
        )
        self.details_layout.addRow("Connections:", connections)

    def build_config(self):
        if self._base_document is None:
            raise ValueError(
                "Load selected benchmark YAML before applying editor changes"
            )
        from .fu_capability import inspect_fu_capability

        capable = inspect_fu_capability(self.gem5_path)["supported"]
        return render_document(
            self._base_document,
            _editor_snapshot(self),
            allow_fu_capacity=capable,
        )

    def validate_config(self):
        self.validation_output.clear()
        try:
            self._make_request()
            self.validation_output.append(
                "Editor request is serializable. Apply edits, rebuild & run "
                "for generation, simulator, and effective-state verification."
            )
        except Exception as error:
            self.validation_output.append("Editor request rejected: " + str(error))

    def load_config(self):
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load configuration",
            str(self.gem5_path),
            "YAML Files (*.yml *.yaml);;All Files (*)",
        )
        if not path:
            return
        try:
            source = Path(path).resolve(strict=True)
            source.relative_to(self.gem5_path.resolve(strict=True))
            docs = list(yaml.safe_load_all(source.read_text(encoding="utf-8")))
            if len(docs) != 1:
                raise ValueError("GUI editor supports one YAML document")
            self.apply_config(docs[0], source_path=source)
            self.validation_output.append("Loaded from: " + str(source))
        except Exception as error:
            QMessageBox.warning(self, "Load Failed", str(error))

    def _make_request(self):
        actual_root = self.gem5_path.resolve(strict=True)
        gui_root = Path(self._gui_source_path).resolve(strict=True).parents[3]
        if actual_root != gui_root:
            raise ValueError("Select this independent configurator-engine checkout")
        benchmark, selected = _selected_file(self)
        if self._source_config_relative != selected.relative_to(actual_root).as_posix():
            raise ValueError("Loaded YAML does not match selected benchmark")
        if source_hash(selected) != self._source_sha256:
            raise ValueError(
                "Selected YAML changed after loading; reload before applying"
            )
        parent = self.parent()
        while parent is not None and not hasattr(parent, "wsl_status"):
            parent = parent.parent()
        distro = (
            parent.wsl_status.get_selected_distro()
            if (parent and hasattr(parent, "wsl_status"))
            else None
        )
        if not distro:
            raise ValueError("Select the WSL distribution in the main window")
        engine_wsl = (
            str(actual_root)
            if os.name != "nt"
            else self._checked_wsl_path(actual_root, distro)
        )
        snapshot = _editor_snapshot(self)
        return build_gui_request(
            self._base_document,
            snapshot,
            benchmark=benchmark,
            engine_root=engine_wsl,
            distro=distro,
            source_config_relative=self._source_config_relative,
            source_config_sha256=self._source_sha256,
            capability_source_root=actual_root,
        )

    def _backend_command(self, request):
        if self._backend_command_provider is not None:
            return self._backend_command_provider(request)
        if os.name != "nt":
            return (
                "/usr/bin/python3.8",
                [
                    "-B",
                    "-m",
                    "salam_workbench.gui_execution",
                    "--request-stdin",
                ],
            )
        workbench_wsl = self._checked_wsl_path(WORKBENCH_HOST, request["distro"])
        return (
            "wsl",
            [
                "-d",
                request["distro"],
                "--cd",
                workbench_wsl,
                "--exec",
                "/usr/bin/python3.8",
                "-B",
                "-m",
                "salam_workbench.gui_execution",
                "--request-stdin",
            ],
        )

    def generate_files(self):
        self.validation_output.clear()
        try:
            if (
                self._gui_process is not None
                and self._gui_process.state() != QProcess.NotRunning
            ):
                raise ValueError("A checked configuration run is already active")
            request = self._make_request()
            self._gui_process_output = ""
            self._gui_summary = None
            program, arguments = self._backend_command(request)
            request["provenance"]["transport_mode"] = (
                "wsl_direct_argv"
                if program.lower().endswith("wsl")
                else "native_direct_argv"
            )
            self._gui_request = deepcopy(request)
            payload = (json.dumps(request, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
            process = QProcess(self)
            # wsl.exe receives its Linux cwd through --cd; a Windows process
            # need not use a UNC workbench path as its own cwd.
            process.setWorkingDirectory(
                str(Path.home() if os.name == "nt" else WORKBENCH_HOST)
            )
            process.setProgram(program)
            process.setArguments(arguments)
            process.started.connect(
                lambda: (process.write(payload), process.closeWriteChannel())
            )
            process.readyReadStandardOutput.connect(self._read_gui_stdout)
            process.readyReadStandardError.connect(self._read_gui_stderr)
            process.errorOccurred.connect(self._gui_process_error)
            process.finished.connect(self._gui_finished)
            self._gui_process = process
            self.generate_btn.setEnabled(False)
            self.validation_output.append(
                "Applying live editor settings; generated outputs, rebuild, guest, and "
                "simulator will be checked. The GUI remains responsive."
            )
            process.start()
            _workbench_event(self, "started", request=deepcopy(request))
        except Exception as error:
            self.generate_btn.setEnabled(True)
            self.validation_output.append("Apply failed before launch: " + str(error))
            _workbench_event(self, "failed_to_start", error=str(error))
            if not getattr(self, "_workbench_embedded", False):
                QMessageBox.warning(self, "Apply Failed", str(error))

    def _process_gui_line(self, line):
        line = line.strip()
        if not line:
            return
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            self.validation_output.append(line[-1000:])
            return
        if message.get("kind") == "gui_progress":
            self.validation_output.append("Stage: " + str(message.get("stage")))
            _workbench_event(self, "progress", message=message)
        elif message.get("kind") == "gui_execution_result":
            self._gui_summary = message
            self.validation_output.append(
                "Evidence: " + str(message.get("evidence_directory"))
            )
            _workbench_event(self, "summary", message=message)
        else:
            self.validation_output.append(line[-1000:])

    def _read_gui_stdout(self):
        self._gui_process_output += bytes(
            self._gui_process.readAllStandardOutput()
        ).decode("utf-8", errors="replace")
        while "\n" in self._gui_process_output:
            line, self._gui_process_output = self._gui_process_output.split("\n", 1)
            self._process_gui_line(line)

    def _read_gui_stderr(self):
        data = bytes(self._gui_process.readAllStandardError()).decode(
            "utf-8", errors="replace"
        )
        if data.strip():
            self.validation_output.append(data.strip()[-2000:])
            _workbench_event(self, "log", text=data.strip()[-2000:])

    def _gui_process_error(self, error):
        if error == QProcess.FailedToStart:
            self.generate_btn.setEnabled(True)
            self.validation_output.append(
                "Checked backend failed to start: " + self._gui_process.errorString()
            )
            _workbench_event(
                self, "failed_to_start", error=self._gui_process.errorString()
            )
            if not getattr(self, "_workbench_embedded", False):
                QMessageBox.warning(
                    self, "Backend Failed", self._gui_process.errorString()
                )
            self._gui_process = None

    def _verify_passing_receipt(self, summary):
        path_text = summary.get("evidence_directory")
        if not isinstance(path_text, str):
            raise ValueError("Backend omitted evidence directory")
        if os.name == "nt":
            prefix = (
                self._checked_wsl_path(
                    WORKBENCH_HOST, self._gui_request["distro"]
                ).rstrip("/")
                + "/evidence/"
            )
            if not path_text.startswith(prefix):
                raise ValueError("Evidence path is outside workbench evidence")
            directory = WORKBENCH_HOST / "evidence" / path_text[len(prefix) :]
        else:
            directory = Path(path_text)
        allowed = (WORKBENCH_HOST / "evidence").resolve(strict=True)
        try:
            directory.absolute().relative_to(allowed)
        except ValueError as error:
            raise ValueError("Evidence path is outside workbench evidence") from error
        directory = directory.resolve(strict=True)
        try:
            directory.relative_to(allowed)
        except ValueError as error:
            raise ValueError(
                "Evidence path resolves outside workbench evidence"
            ) from error
        receipt = json.loads(
            (directory / "gui-execution.json").read_text(encoding="utf-8")
        )
        saved_request = json.loads(
            (directory / "request.json").read_text(encoding="utf-8")
        )
        if saved_request != self._gui_request:
            raise ValueError("Saved request differs from live GUI widget request")
        if (
            receipt.get("state") != "passed"
            or receipt.get("editor_form_applied") is not True
            or receipt.get("simulation_requested") is not True
            or receipt.get("pipeline_state") != "passed"
            or receipt.get("effective_witness", {}).get("state") != "passed"
        ):
            raise ValueError(
                "Durable GUI, simulation, or effective-state receipt did not pass"
            )
        if receipt.get("evidence_directory") != path_text:
            raise ValueError("Receipt evidence directory differs from process summary")
        # The desktop shell runs the same completion gate in its existing
        # background worker; avoid replaying a large trace on its UI thread.
        if "benchmark_input" in self._gui_request and not getattr(
            self, "_workbench_embedded", False
        ):
            from .workbench_completion import verify_completion

            assessment = verify_completion(
                directory,
                WORKBENCH_HOST,
                self._gui_request["benchmark"],
                "configured",
                expected_request=self._gui_request,
            )
            if assessment["state"] != "passed":
                raise ValueError(
                    "Current generated-input completion replay failed: "
                    + str(assessment["errors"])
                )
        return receipt

    def _gui_finished(self, exit_code, exit_status):
        if self._gui_process_output.strip():
            self._process_gui_line(self._gui_process_output)
        summary = self._gui_summary
        self.generate_btn.setEnabled(True)
        self._gui_process = None
        verified = None
        if (
            exit_code == 0
            and exit_status == QProcess.NormalExit
            and isinstance(summary, dict)
            and summary.get("state") == "passed"
        ):
            try:
                verified = self._verify_passing_receipt(summary)
            except Exception as error:
                self.validation_output.append(
                    "Receipt verification failed: " + str(error)
                )
        if verified is not None:
            for line in _fu_telemetry_lines(verified):
                self.validation_output.append(line)
            self.validation_output.append(
                "Passed: edited settings reached the checked simulation and effective-state witnesses."
            )
            if not getattr(self, "_workbench_embedded", False):
                QMessageBox.information(
                    self,
                    "Checked Run Passed",
                    "The edited configuration passed. See the evidence path.",
                )
        else:
            errors = summary.get("errors", []) if isinstance(summary, dict) else []
            message = (
                "; ".join(errors)
                if errors
                else "Backend did not return a passing receipt"
            )
            self.validation_output.append("Checked run failed: " + message)
            if not getattr(self, "_workbench_embedded", False):
                QMessageBox.warning(self, "Checked Run Failed", message)
        _workbench_event(
            self,
            "finished",
            state="passed" if verified is not None else "failed",
            receipt=verified,
            summary=summary,
            exit_code=exit_code,
        )

    dialog_class.__init__ = init
    dialog_class.setup_basic_tab = setup_basic_tab
    dialog_class._refresh_periods = _refresh_periods
    dialog_class.setup_accelerator_tab = setup_accelerator_tab
    dialog_class.setup_hw_config_tab = setup_hw_config_tab
    dialog_class._add_instruction_row = _add_instruction_row
    dialog_class.on_benchmark_changed = on_benchmark_changed
    dialog_class.apply_config = apply_config
    dialog_class._select_hardware_target = _select_hardware_target
    dialog_class.add_memory = add_memory
    dialog_class.add_accelerator = add_accelerator
    dialog_class.update_component_data = update_component_data
    dialog_class.on_component_selected = on_component_selected
    dialog_class.show_dma_details = show_dma_details
    dialog_class.show_accelerator_details = show_accelerator_details
    dialog_class.show_memory_details = show_memory_details
    dialog_class.build_config = build_config
    dialog_class.validate_config = validate_config
    dialog_class.load_config = load_config
    dialog_class._make_request = _make_request
    dialog_class._backend_command = _backend_command
    dialog_class.generate_files = generate_files
    dialog_class._process_gui_line = _process_gui_line
    dialog_class._read_gui_stdout = _read_gui_stdout
    dialog_class._read_gui_stderr = _read_gui_stderr
    dialog_class._gui_process_error = _gui_process_error
    dialog_class._verify_passing_receipt = _verify_passing_receipt
    dialog_class._gui_finished = _gui_finished
