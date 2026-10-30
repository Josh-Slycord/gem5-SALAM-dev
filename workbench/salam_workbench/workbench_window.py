"""Desktop research workspace over the existing checked simulation pipeline."""
import datetime
import json
import sys
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QProcess,
    QSettings,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .gui_editor_qt import MODEL_FIELDS, _fill_rows
from .gui_execution import read_request, validate_request
from .runner import file_hash
from .workbench_catalog import discover_benchmarks
from .workbench_completion import verify_completion
from .workbench_results import discover_runs, load_run, read_artifact_text
from .workbench_topology import TopologyPanel

REFERENCE_NAMES = frozenset(("gemm", "bfs", "nw", "fft", "stencil3d"))
STYLE = """
QMainWindow, QWidget { background: #f5f7fa; color: #243247; }
QWidget { font-size: 13px; }
QWidget#library { background: #172638; color: #e4edf7; }
QWidget#library QLabel { background: transparent; color: #b9c9dc; }
QLabel#brand { font-size: 25px; font-weight: 700; color: white; }
QLabel#heading { font-size: 23px; font-weight: 600; }
QLabel#subtitle, QLabel#scope { color: #5a6c80; }
QLabel#runStatus { font-weight: 600; font-size: 17px; }
QLineEdit, QComboBox, QSpinBox { background: white; border: 1px solid #ccd6e1;
    padding: 6px; border-radius: 3px; min-height: 20px; }
QPushButton { background: white; border: 1px solid #c8d2df; border-radius: 4px;
    padding: 8px 13px; min-height: 18px; }
QPushButton:hover { background: #eaf0f8; border-color: #879bb4; }
QPushButton:disabled { color: #94a1b1; background: #edf1f5; }
QPushButton#primary { background: #245fd3; color: white; border-color: #245fd3;
    font-weight: 600; }
QPushButton#primary:hover { background: #194da9; }
QPushButton#primary:disabled { background: #a7b9d8; border-color: #a7b9d8; }
QTreeWidget { background: white; border: 0; alternate-background-color: #f6f8fb;
    selection-background-color: #e0eafd; selection-color: #163c75; }
QTreeWidget::item { min-height: 27px; padding: 2px 4px; }
QTreeWidget#benchmarkTree { background: #172638; color: #d9e4f2;
    selection-background-color: #294363; selection-color: white; }
QHeaderView::section { background: #eaf0f6; color: #455b74; border: 0;
    border-bottom: 1px solid #d8e1eb; padding: 8px; font-weight: 600; }
QTabWidget::pane { border: 0; background: white; }
QTabBar::tab { background: transparent; padding: 11px 18px; color: #61758d;
    border-bottom: 3px solid transparent; }
QTabBar::tab:selected { color: #245fd3; border-bottom-color: #245fd3; }
QPlainTextEdit, QTextEdit { background: white; border: 1px solid #dbe3ed;
    padding: 8px; selection-background-color: #d4e2fb; }
QGroupBox { border: 1px solid #dbe3ed; border-radius: 3px; margin-top: 14px;
    padding-top: 14px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
QProgressBar { background: #e1e8f0; border: 0; height: 5px; }
QProgressBar::chunk { background: #245fd3; }
QSplitter::handle { background: #e1e7ef; }
QStatusBar { background: #e9eef5; color: #526981; }
"""


class _DataTask(QThread):
    ready = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, name, function, parent):
        super().__init__(parent)
        self.name, self.function = name, function

    def run(self):
        try:
            self.ready.emit(self.name, self.function())
        except Exception as error:
            self.failed.emit(self.name, type(error).__name__ + ": " + str(error))


class _EditorScroll(QScrollArea):
    """Keep entire form controls visible, including their styled padding."""

    def ensureWidgetVisible(self, child, xmargin=8, ymargin=8):
        super().ensureWidgetVisible(child, xmargin, ymargin)
        # Qt's implementation can target a QLineEdit's cursor rectangle and
        # leave its outer border clipped. Use the actual control bounds too.
        position = child.mapTo(self.widget(), QPoint(0, 0))
        self.ensureVisible(
            position.x() + child.width() // 2,
            position.y() + child.height() // 2,
            min(child.width() // 2 + xmargin, self.viewport().width() // 2),
            child.height() // 2 + ymargin,
        )

    def eventFilter(self, watched, event):
        if event.type() == QEvent.FocusIn:
            QTimer.singleShot(0, self._show_focused_control)
        return super().eventFilter(watched, event)

    def _show_focused_control(self):
        child = QApplication.focusWidget()
        if child is not None and self.isAncestorOf(child):
            self.ensureWidgetVisible(child)


def _tree(headers):
    widget = QTreeWidget()
    widget.setHeaderLabels(headers)
    widget.setRootIsDecorated(False)
    widget.setAlternatingRowColors(True)
    widget.setUniformRowHeights(True)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.header().setStretchLastSection(True)
    return widget


def _plain():
    widget = QPlainTextEdit()
    widget.setReadOnly(True)
    widget.setFont(QFont("DejaVu Sans Mono", 10))
    widget.setMaximumBlockCount(5000)
    return widget


def _label(text, name=None):
    widget = QLabel(text)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


def _value(value):
    if value is None:
        return "Unavailable"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


class WorkbenchWindow(QMainWindow):
    """One active job, source-backed configuration, and durable result inspection."""

    def __init__(
        self,
        project,
        engine,
        distribution,
        dialog_class,
        benchmark=None,
        *,
        settings=None,
        auto_discover=True,
    ):
        super().__init__()
        self.project = Path(project).resolve(strict=True)
        self.engine = Path(engine).resolve(strict=True)
        self.distribution = distribution
        self.wsl_status = type(
            "SelectedDistribution",
            (),
            {"get_selected_distro": lambda _self: distribution},
        )()
        self.settings = settings or QSettings("SALAM", "Research Workbench")
        self.catalog = []
        self.selected_benchmark = None
        self.selected_run = None
        self._tasks = []
        self._task_queue = OrderedDict()
        self._busy = False
        self._reference_process = None
        self._reference_buffer = ""
        self._reference_summary = None
        self._run_target = None
        self._load_generation = 0
        self._completion_generation = 0
        self._last_completed_state = None
        self._selection_error = None
        self.setWindowTitle("SALAM Research Workbench")
        self.resize(1520, 1000)
        self.setMinimumSize(1060, 720)
        self.setStyleSheet(STYLE)
        self._build_ui(dialog_class)
        self._populate_environment()
        self._preferred_benchmark = benchmark or str(
            self.settings.value("benchmark", "benchmarks/sys_validation/gemm")
        )
        self.poll = QTimer(self)
        self.poll.setInterval(1000)
        self.poll.timeout.connect(self._poll_active_evidence)
        if auto_discover:
            self.refresh_catalog()
            self.refresh_history()

    def _build_ui(self, dialog_class):
        main = QSplitter(Qt.Horizontal)
        self.setCentralWidget(main)
        library = QWidget()
        library.setObjectName("library")
        rail = QVBoxLayout(library)
        rail.setContentsMargins(20, 24, 16, 18)
        rail.setSpacing(14)
        rail.addWidget(_label("SALAM", "brand"))
        rail.addWidget(_label("RESEARCH WORKBENCH"))
        rail.addSpacing(12)
        rail.addWidget(_label("BENCHMARK LIBRARY"))
        self.benchmark_search = QLineEdit()
        self.benchmark_search.setPlaceholderText("Find a benchmark…")
        self.benchmark_search.textChanged.connect(self._filter_catalog)
        rail.addWidget(self.benchmark_search)
        self.benchmark_tree = QTreeWidget()
        self.benchmark_tree.setObjectName("benchmarkTree")
        self.benchmark_tree.setHeaderHidden(True)
        self.benchmark_tree.setUniformRowHeights(True)
        self.benchmark_tree.currentItemChanged.connect(self._benchmark_changed)
        rail.addWidget(self.benchmark_tree, 1)
        self.catalog_note = _label("Reading installed benchmark sources…")
        rail.addWidget(self.catalog_note)
        self.refresh_library_btn = QPushButton("Refresh library")
        self.refresh_library_btn.clicked.connect(self.refresh_catalog)
        rail.addWidget(self.refresh_library_btn)
        main.addWidget(library)

        workspace = QWidget()
        body = QVBoxLayout(workspace)
        body.setContentsMargins(24, 22, 24, 16)
        body.setSpacing(14)
        top = QHBoxLayout()
        title = QVBoxLayout()
        self.heading = _label("Select a benchmark", "heading")
        self.subtitle = _label(
            "Configure, execute, and inspect the evidence.", "subtitle"
        )
        title.addWidget(self.heading)
        title.addWidget(self.subtitle)
        top.addLayout(title, 1)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Configured simulation", "configured")
        self.mode_combo.addItem("Verified reference workload", "reference")
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        top.addWidget(self.mode_combo)
        self.run_btn = QPushButton("Run benchmark")
        self.run_btn.setObjectName("primary")
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self.start_run)
        top.addWidget(self.run_btn)
        body.addLayout(top)
        self.mode_note = _label("", "scope")
        body.addWidget(self.mode_note)
        self.pages = QTabWidget()
        body.addWidget(self.pages, 1)

        config_page = QWidget()
        config_layout = QVBoxLayout(config_page)
        config_layout.setContentsMargins(0, 4, 0, 0)
        tools = QHBoxLayout()
        self._config_action_buttons = {}
        for text, callback in (
            ("Check settings", self.check_settings),
            ("Save preset…", self.save_preset),
            ("Load preset…", self.load_preset),
            ("Reload source", self.reload_source),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            tools.addWidget(button)
            self._config_action_buttons[text] = button
        tools.addStretch()
        config_layout.addLayout(tools)
        self.editor = dialog_class(self.engine, self)
        self.editor.setWindowFlags(Qt.Widget)
        self.editor.setMinimumSize(0, 0)
        self.editor._workbench_embedded = True
        self.editor._workbench_listener = self._editor_event
        self.editor.validation_output.parentWidget().hide()
        for button in self.editor.findChildren(QPushButton):
            if (
                button
                in (
                    self.editor.validate_btn,
                    self.editor.generate_btn,
                    self.editor.save_btn,
                    self.editor.load_btn,
                )
                or button.text() == "Close"
            ):
                button.hide()
        # The library owns selection; the recovered controls retain exact data
        # for request validation but cannot drift away from the visible workload.
        self.editor.benchmark_combo.setEnabled(False)
        self.editor.bench_dir_combo.setEnabled(False)
        self._prepare_editor_layout()
        if hasattr(self.editor, "cycle_time_combo"):
            self.editor.cycle_time_combo.currentIndexChanged.connect(self._mode_changed)
            self.editor.model_edit.textChanged.connect(self._mode_changed)
            self.editor.profile_edit.textChanged.connect(self._mode_changed)
        config_layout.addWidget(self.editor, 1)
        self.pages.addTab(config_page, "Configuration")

        monitor = QWidget()
        monitor_layout = QVBoxLayout(monitor)
        self.run_status = _label("Ready", "runStatus")
        monitor_layout.addWidget(self.run_status)
        self.run_detail = _label(
            "Runs preserve their configuration, outputs, and check receipts."
        )
        monitor_layout.addWidget(self.run_detail)
        self.run_progress = QProgressBar()
        self.run_progress.setRange(0, 1)
        self.run_progress.setValue(0)
        self.run_progress.setTextVisible(False)
        monitor_layout.addWidget(self.run_progress)
        self.run_log = _plain()
        monitor_layout.addWidget(self.run_log, 1)
        self.pages.addTab(monitor, "Run monitor")

        results = QWidget()
        results_layout = QVBoxLayout(results)
        filters = QHBoxLayout()
        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText(
            "Filter runs by benchmark, status, or ID…"
        )
        self.history_search.textChanged.connect(self._filter_history)
        filters.addWidget(self.history_search, 1)
        self.refresh_runs_btn = QPushButton("Refresh runs")
        self.refresh_runs_btn.clicked.connect(self.refresh_history)
        filters.addWidget(self.refresh_runs_btn)
        self.compare_btn = QPushButton("Compare two selected runs")
        self.compare_btn.clicked.connect(self.compare_selected)
        filters.addWidget(self.compare_btn)
        results_layout.addLayout(filters)
        self.results_split = QSplitter(Qt.Vertical)
        self.history = _tree(
            ["Benchmark", "Recorded status", "Started", "Run / session"]
        )
        self.history.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.history.currentItemChanged.connect(self._history_changed)
        self.results_split.addWidget(self.history)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 8, 0, 0)
        self.result_heading = _label("Select a recorded run", "runStatus")
        detail_layout.addWidget(self.result_heading)
        self.result_scope = _label(
            "Recorded status and independently checked evidence are shown separately.",
            "scope",
        )
        detail_layout.addWidget(self.result_scope)
        self.result_overview = _label("", "runStatus")
        self.result_overview.hide()
        detail_layout.addWidget(self.result_overview)
        self.result_tabs = QTabWidget()
        detail_layout.addWidget(self.result_tabs, 1)
        metric_page = QWidget()
        metric_layout = QVBoxLayout(metric_page)
        self.metric_search = QLineEdit()
        self.metric_search.setPlaceholderText(
            "Filter SALAM, cycles, bytes, power, or any metric…"
        )
        self.metric_search.textChanged.connect(self._filter_metrics)
        metric_filters = QHBoxLayout()
        metric_filters.addWidget(self.metric_search, 1)
        self.metric_scope_combo = QComboBox()
        self.metric_scope_combo.addItem("All metric scopes", "all")
        self.metric_scope_combo.addItem("Direct SALAM output", "salam")
        self.metric_scope_combo.addItem("gem5 system statistics", "gem5")
        self.metric_scope_combo.currentIndexChanged.connect(self._filter_metrics)
        metric_filters.addWidget(self.metric_scope_combo)
        metric_layout.addLayout(metric_filters)
        self.metrics = _tree(
            ["Metric", "Value", "Unit", "Scope", "Evidence status", "Source"]
        )
        metric_layout.addWidget(self.metrics, 1)
        self.result_tabs.addTab(metric_page, "Metrics")
        self.topology = TopologyPanel(self.project)
        self.result_tabs.addTab(self.topology, "System topology")
        self.checks = _tree(["Check", "Status", "Detail", "Source"])
        self.result_tabs.addTab(self.checks, "Validation")
        artifacts_page = QWidget()
        artifacts_layout = QVBoxLayout(artifacts_page)
        self.artifacts = _tree(["Artifact", "Status", "Path"])
        self.artifacts.currentItemChanged.connect(self._artifact_changed)
        artifacts_layout.addWidget(self.artifacts, 1)
        self.artifact_preview = _plain()
        self.artifact_preview.setPlaceholderText(
            "Select an artifact to read its text here."
        )
        artifacts_layout.addWidget(self.artifact_preview, 1)
        self.result_tabs.addTab(artifacts_page, "Files and logs")
        self.provenance_text = _plain()
        self.result_tabs.addTab(self.provenance_text, "Provenance")
        self.comparison = _tree(["Metric", "Run A", "Run B", "Unit", "Scope"])
        self.result_tabs.addTab(self.comparison, "Comparison")
        self.results_split.addWidget(detail)
        self.results_split.setSizes([200, 430])
        results_layout.addWidget(self.results_split, 1)
        self.pages.addTab(results, "Results and metrics")

        environment = QWidget()
        environment_layout = QVBoxLayout(environment)
        environment_layout.addWidget(_label("Installation & evidence", "heading"))
        environment_layout.addWidget(
            _label(
                "Configured simulations use the selected configuration engine. Reference workloads "
                "use their recorded baseline engine and fixed datasets.",
                "scope",
            )
        )
        self.environment = _plain()
        environment_layout.addWidget(self.environment, 1)
        environment_tools = QHBoxLayout()
        for title, relative in (
            ("Open evidence folder", "evidence"),
            ("Workbench guide", "README.md"),
            ("Scheduling coverage", "docs/FU_SCHEDULING_RESULTS.md"),
        ):
            button = QPushButton(title)
            button.clicked.connect(
                lambda _checked=False, rel=relative: self._open_local(rel)
            )
            environment_tools.addWidget(button)
        environment_tools.addStretch()
        environment_layout.addLayout(environment_tools)
        self.pages.addTab(environment, "Environment")
        main.addWidget(workspace)
        main.setSizes([250, 1270])
        main.setStretchFactor(0, 0)
        main.setStretchFactor(1, 1)
        self.statusBar().showMessage("Local workspace · " + self.distribution)

    def _prepare_editor_layout(self):
        if not hasattr(self.editor, "tabs"):
            return
        basic = self.editor.tabs.widget(0)
        benchmark_group = self.editor.benchmark_combo.parentWidget()
        if isinstance(benchmark_group, QGroupBox):
            benchmark_group.hide()
        basic.layout().setSizeConstraint(QLayout.SetMinimumSize)
        basic.layout().setSpacing(12)
        for form in basic.findChildren(QFormLayout):
            form.setVerticalSpacing(8)
        self.editor.tabs.removeTab(0)
        self._basic_scroll = _EditorScroll()
        self._basic_scroll.setWidgetResizable(True)
        self._basic_scroll.setWidget(basic)
        for child in basic.findChildren(QWidget):
            child.installEventFilter(self._basic_scroll)
        self._basic_scroll.setStyleSheet("QScrollArea { border: 0; }")
        self.editor.tabs.insertTab(0, self._basic_scroll, "System")
        self.editor.tabs.setCurrentIndex(0)

    def _task(self, name, function):
        category = name.split(":", 1)[0]
        if len(self._tasks) >= 2 or any(
            t.name.split(":", 1)[0] == category for t in self._tasks
        ):
            # Keep the latest selection, rather than replaying every large trace
            # while the user moves through history. At most two readers run.
            self._task_queue[category] = (name, function)
            return
        self._start_task(name, function)

    def _start_task(self, name, function):
        task = _DataTask(name, function, self)
        self._tasks.append(task)
        task.ready.connect(self._data_ready)
        task.failed.connect(self._data_failed)
        task.finished.connect(lambda: self._task_finished(task))
        task.finished.connect(task.deleteLater)
        task.start()

    def _task_finished(self, task):
        if task in self._tasks:
            self._tasks.remove(task)
        for category in list(self._task_queue):
            if len(self._tasks) >= 2:
                break
            if any(t.name.split(":", 1)[0] == category for t in self._tasks):
                continue
            name, function = self._task_queue.pop(category)
            self._start_task(name, function)

    def refresh_catalog(self):
        if self._busy:
            return
        self.refresh_library_btn.setEnabled(False)
        self._task("catalog", lambda: discover_benchmarks(self.engine))

    def refresh_history(self):
        self.refresh_runs_btn.setEnabled(False)
        self._task("history", lambda: discover_runs(self.project))

    def _data_ready(self, name, value):
        if name == "catalog":
            self.catalog = value
            self._show_catalog()
            self.refresh_library_btn.setEnabled(not self._busy)
        elif name == "history":
            self._show_history(value)
            self.refresh_runs_btn.setEnabled(True)
        elif name.startswith("run:"):
            if name == "run:" + str(self._load_generation):
                self._show_run(value)
        elif name == "comparison":
            self._show_comparison(*value)
        elif name == "artifact":
            if value[0] == getattr(self, "_artifact_path", None):
                self.artifact_preview.setPlainText(value[1])
        elif name == "completion:" + str(self._completion_generation):
            if value.get("result"):
                self._show_run(value["result"])
            self._finish_run(value["state"], self._run_target, value.get("errors", []))

    def _data_failed(self, name, error):
        self.statusBar().showMessage(name + ": " + error)
        if name == "catalog":
            self.catalog_note.setText(error)
            self.refresh_library_btn.setEnabled(True)
        elif name == "history":
            self.refresh_runs_btn.setEnabled(True)
        elif name.startswith("run:"):
            if name == "run:" + str(self._load_generation):
                self.result_heading.setText("Could not inspect this run")
                self.result_scope.setText(error)
        elif name == "artifact":
            self.artifact_preview.setPlainText("Could not preview artifact: " + error)
        elif name == "completion:" + str(self._completion_generation):
            self._finish_run(
                "failed", self._run_target, ["Completion verification failed: " + error]
            )

    def _show_catalog(self):
        self.benchmark_tree.clear()
        groups = {}
        preferred = None
        for entry in self.catalog:
            suite = entry["suite"]
            if suite not in groups:
                group = QTreeWidgetItem(
                    self.benchmark_tree, [suite.replace("benchmarks/", "")]
                )
                group.setFlags(group.flags() & ~Qt.ItemIsSelectable)
                group.setExpanded(True)
                groups[suite] = group
            label = entry.get("title") or entry["name"]
            if not entry.get("can_configure"):
                label += "  · unavailable"
            item = QTreeWidgetItem(groups[suite], [label])
            item.setData(0, Qt.UserRole, entry)
            item.setToolTip(
                0,
                entry.get("description", "")
                + "\n"
                + "\n".join(entry.get("warnings", [])),
            )
            if (
                entry["key"] == self._preferred_benchmark
                or entry["name"] == self._preferred_benchmark
            ):
                preferred = item
        self.catalog_note.setText(
            str(sum(bool(e.get("can_configure")) for e in self.catalog))
            + " source configurations · readiness is checked before execution"
        )
        if preferred is not None:
            self.benchmark_tree.setCurrentItem(preferred)
        elif self.catalog:
            first = self.benchmark_tree.topLevelItem(0)
            if first.childCount():
                self.benchmark_tree.setCurrentItem(first.child(0))
        self._filter_catalog()

    def _filter_catalog(self):
        query = self.benchmark_search.text().lower().strip()
        for group_index in range(self.benchmark_tree.topLevelItemCount()):
            group = self.benchmark_tree.topLevelItem(group_index)
            visible = 0
            for index in range(group.childCount()):
                item = group.child(index)
                entry = item.data(0, Qt.UserRole)
                match = query in (entry["key"] + " " + item.text(0)).lower()
                item.setHidden(not match)
                visible += int(match)
            group.setHidden(not visible)

    def _benchmark_changed(self, item, _previous):
        if item is None or self._busy:
            return
        entry = item.data(0, Qt.UserRole)
        if not isinstance(entry, dict):
            return
        self.selected_benchmark = entry
        self._selection_error = None
        self._preferred_benchmark = entry["key"]
        self.heading.setText(entry.get("title") or entry["name"])
        self.subtitle.setText(entry["key"])
        if entry.get("can_configure"):
            suite = entry["key"].rsplit("/", 1)[0]
            self.editor.bench_dir_combo.setCurrentText(suite)
            index = self.editor.benchmark_combo.findData(entry["name"])
            if index < 0 and hasattr(self.editor, "discover_benchmarks"):
                self.editor.discover_benchmarks()
                index = self.editor.benchmark_combo.findData(entry["name"])
            if index >= 0:
                self.editor.benchmark_combo.setCurrentIndex(index)
                self.editor.on_benchmark_changed(
                    self.editor.benchmark_combo.currentText()
                )
                if (
                    hasattr(self.editor, "_base_document")
                    and self.editor._base_document is None
                ):
                    self._selection_error = "The selected source could not be loaded into the configuration editor."
            else:
                self._selection_error = "The selected benchmark is unavailable in the checked editor. Refresh or reload its source."
        self._mode_changed()

    def _mode_changed(self):
        entry = self.selected_benchmark or {}
        reference = self.mode_combo.currentData() == "reference"
        supported_reference = (
            entry.get("key") == "benchmarks/sys_validation/" + entry.get("name", "")
            and entry.get("name") in REFERENCE_NAMES
        )
        configured_ready = bool(entry.get("can_run"))
        if entry.get("run_readiness") == "hardware_profile_required":
            configured_ready = bool(entry.get("can_configure"))
        if hasattr(self.editor, "cycle_time_combo"):
            configured_ready = configured_ready and bool(
                self.editor.cycle_time_combo.currentText().strip()
            )
        ready = bool(
            supported_reference
            if reference
            else configured_ready and not self._selection_error
        )
        self.editor.setEnabled(
            not self._busy and not reference and bool(entry.get("can_configure"))
        )
        self.editor.benchmark_combo.setEnabled(False)
        self.editor.bench_dir_combo.setEnabled(False)
        self.run_btn.setEnabled(not self._busy and ready)
        self.run_btn.setText(
            "Run reference workload" if reference else "Apply settings and run"
        )
        for title, button in self._config_action_buttons.items():
            button.setEnabled(
                not self._busy
                and (
                    title == "Load preset…"
                    or (
                        not reference
                        and bool(entry.get("can_configure"))
                        and not self._selection_error
                    )
                )
            )
        if reference:
            self.mode_note.setText(
                "Fixed reference dataset · editor settings are not applied. Uses the baseline engine, "
                "independent workload checks, and direct SALAM observability."
                if supported_reference
                else "No verified reference adapter for this benchmark. Choose a configured simulation."
            )
        else:
            self.mode_note.setText(
                "Applies the visible settings, regenerates configuration and guest code, and rebuilds "
                "the simulator when required. Guest correctness and effective configuration are checked separately."
                if ready
                else self._selection_error
                or "\n".join(entry.get("warnings", []))
                or "Select an available benchmark configuration."
            )

    def _current_request(self):
        if self._busy or self.mode_combo.currentData() != "configured":
            raise ValueError(
                "Choose an idle configured simulation before editing or saving settings"
            )
        entry = self.selected_benchmark or {}
        if not entry.get("can_configure") or self._selection_error:
            raise ValueError(
                self._selection_error
                or "Selected benchmark has no editable configuration"
            )
        request = self.editor._make_request()
        if request.get("benchmark") != entry.get("key"):
            raise ValueError(
                "Visible benchmark and editor request differ; reload the selected source"
            )
        return request

    def reload_source(self):
        if not self._busy and self.selected_benchmark:
            self.editor.on_benchmark_changed(self.editor.benchmark_combo.currentText())
            self.statusBar().showMessage("Reloaded original source configuration")

    def check_settings(self):
        if self._busy or self.mode_combo.currentData() == "reference":
            return
        try:
            request = self._current_request()
            validate_request(request, self.project)
            self.run_log.setPlainText(
                "Editor request is valid. No simulation was started.\n"
                + json.dumps(request, indent=2)
            )
            self.statusBar().showMessage(
                "Settings passed request validation; simulation has not run"
            )
        except Exception as error:
            self.run_log.setPlainText("Settings rejected: " + str(error))
            self.pages.setCurrentIndex(1)

    def start_run(self):
        if self._busy or not self.run_btn.isEnabled():
            return
        self.run_log.clear()
        self._last_completed_state = None
        self._run_target = None
        self._active_benchmark = self.selected_benchmark["key"]
        self._active_mode = self.mode_combo.currentData()
        self.pages.setCurrentIndex(1)
        if self.mode_combo.currentData() == "reference":
            self._start_reference()
        else:
            try:
                self._current_request()
                self.editor.generate_files()
            except Exception as error:
                self._finish_run("failed", None, [str(error)])

    def _set_busy(self, busy):
        self._busy = busy
        self.benchmark_tree.setEnabled(not busy)
        self.mode_combo.setEnabled(not busy)
        self.refresh_library_btn.setEnabled(not busy)
        self.run_progress.setRange(0, 0 if busy else 1)
        self.run_progress.setValue(0)
        self._mode_changed()
        if busy:
            self.poll.start()
        else:
            self.poll.stop()

    def _editor_event(self, name, payload):
        if name == "started":
            self._set_busy(True)
            self.run_status.setText("Running · configured simulation")
            self.run_detail.setText(
                "The visible request is locked for this run. Preparation and simulation may take several minutes."
            )
        elif name == "progress":
            message = payload["message"]
            self._run_target = message.get("evidence_directory") or self._run_target
            self.run_status.setText(
                "Running · " + str(message.get("stage", "working")).replace("_", " ")
            )
        elif name == "summary":
            self._run_target = (
                payload["message"].get("evidence_directory") or self._run_target
            )
        elif name == "failed_to_start":
            self._finish_run(
                "failed", None, [payload.get("error", "Backend did not start")]
            )
        elif name == "finished":
            summary = payload.get("summary") or {}
            self._candidate_finish(
                payload["state"],
                summary.get("evidence_directory"),
                summary.get("errors", []),
            )
        self.run_log.setPlainText(self.editor.validation_output.toPlainText())

    def _start_reference(self):
        self._reference_buffer, self._reference_summary = "", None
        process = QProcess(self)
        process.setWorkingDirectory(str(self.project))
        process.setProgram(sys.executable)
        process.setArguments(
            [
                "-B",
                "-m",
                "salam_workbench.workbench_jobs",
                "--benchmark",
                self.selected_benchmark["key"],
            ]
        )
        process.readyReadStandardOutput.connect(self._reference_stdout)
        process.readyReadStandardError.connect(self._reference_stderr)
        process.errorOccurred.connect(self._reference_error)
        process.finished.connect(self._reference_finished)
        self._reference_process = process
        self._set_busy(True)
        self.run_status.setText("Running · reference workload")
        self.run_detail.setText(
            "Fixed dataset and baseline engine. Edited configuration is not used in this mode."
        )
        process.start()

    def _reference_line(self, line):
        try:
            message = json.loads(line)
        except (ValueError, TypeError):
            self.run_log.appendPlainText(line[-4000:])
            return
        if not isinstance(message, dict):
            self.run_log.appendPlainText(line[-4000:])
            return
        if message.get("kind") == "gui_execution_result":
            self._reference_summary = message
        if message.get("evidence_directory"):
            self._run_target = message["evidence_directory"]
        if message.get("kind") == "gui_progress":
            self.run_status.setText(
                "Running · " + str(message.get("stage", "working")).replace("_", " ")
            )
        self.run_log.appendPlainText(line[-4000:])

    def _reference_stdout(self):
        self._reference_buffer += bytes(
            self._reference_process.readAllStandardOutput()
        ).decode("utf-8", errors="replace")
        while "\n" in self._reference_buffer:
            line, self._reference_buffer = self._reference_buffer.split("\n", 1)
            self._reference_line(line)
        if len(self._reference_buffer) > 65536:
            self.run_log.appendPlainText(self._reference_buffer[:65536])
            self._reference_buffer = ""

    def _reference_stderr(self):
        self.run_log.appendPlainText(
            bytes(self._reference_process.readAllStandardError()).decode(
                "utf-8", errors="replace"
            )[-16000:]
        )

    def _reference_error(self, error):
        if error == QProcess.FailedToStart:
            self._finish_run("failed", None, [self._reference_process.errorString()])
            self._reference_process = None

    def _reference_finished(self, code, status):
        self._reference_stdout()
        self._reference_stderr()
        if self._reference_buffer.strip():
            self._reference_line(self._reference_buffer)
        summary = self._reference_summary or {}
        state = "failed"
        errors = list(summary.get("errors", []))
        path = summary.get("evidence_directory")
        try:
            directory = Path(path).resolve(strict=True)
            directory.relative_to((self.project / "evidence").resolve(strict=True))
            record = json.loads((directory / "reference-session.json").read_text())
            if (
                code == 0
                and status == QProcess.NormalExit
                and summary.get("state") == record.get("state") == "passed"
                and record.get("benchmark") == self.selected_benchmark["key"]
            ):
                state = "passed"
            else:
                errors.append("Reference backend or durable receipt did not pass")
        except Exception as error:
            errors.append("Reference receipt could not be verified: " + str(error))
        self._reference_process = None
        self._candidate_finish(state, path, errors)

    def _candidate_finish(self, state, evidence, errors):
        if state != "passed" or not evidence:
            self._finish_run("failed", evidence, errors)
            return
        self._run_target = evidence
        self._set_busy(True)
        self.run_status.setText("Verifying raw results and effective settings…")
        self._completion_generation += 1
        benchmark = getattr(
            self, "_active_benchmark", (self.selected_benchmark or {}).get("key")
        )
        mode = getattr(self, "_active_mode", self.mode_combo.currentData())
        request = (
            deepcopy(getattr(self.editor, "_gui_request", None))
            if mode == "configured"
            else None
        )
        self._task(
            "completion:" + str(self._completion_generation),
            lambda: verify_completion(
                evidence, self.project, benchmark, mode, expected_request=request
            ),
        )

    def _finish_run(self, state, evidence, errors):
        self._set_busy(False)
        self._last_completed_state = state
        self.run_status.setText("Completed · " + state)
        self.run_detail.setText(str(evidence or "No durable result directory returned"))
        if errors:
            self.run_log.appendPlainText("\n" + "\n".join(str(e) for e in errors))
        self.statusBar().showMessage(
            "Run " + state + " · " + str(evidence or "inspect run monitor")
        )
        self._run_target = evidence
        self.refresh_history()
        if evidence:
            self._inspect_run(evidence)
            self.pages.setCurrentIndex(2)

    def _poll_active_evidence(self):
        # The backend publishes coarse stages durably. No invented completion
        # percentages, no simulation process polling, and no writes to receipts.
        if self._busy and self._run_target:
            self.run_detail.setText(str(self._run_target))

    def _show_history(self, rows):
        selected = self._run_target or (self.selected_run or {}).get("path")
        self.history.blockSignals(True)
        self.history.clear()
        found = None
        for row in rows:
            item = QTreeWidgetItem(
                self.history,
                [
                    _value(row.get("benchmark")),
                    row.get("state", "unknown"),
                    row.get("started_at") or "Unknown",
                    row.get("run_id") or "Unknown",
                ],
            )
            item.setData(0, Qt.UserRole, row["path"])
            item.setToolTip(3, str(row["path"]))
            if str(row["path"]) == str(selected):
                found = item
        self.history.blockSignals(False)
        if found is not None:
            self.history.setCurrentItem(found)
        self._filter_history()

    def _filter_history(self):
        query = self.history_search.text().lower().strip()
        for index in range(self.history.topLevelItemCount()):
            item = self.history.topLevelItem(index)
            item.setHidden(
                query not in " ".join(item.text(c) for c in range(4)).lower()
            )

    def _history_changed(self, item, _previous):
        if item is not None:
            self._inspect_run(item.data(0, Qt.UserRole))

    def _inspect_run(self, path):
        self._load_generation += 1
        self.result_heading.setText("Reading run evidence…")
        self.result_scope.setText("")
        self.result_overview.clear()
        self.result_overview.hide()
        self.metrics.clear()
        self.checks.clear()
        self.artifacts.clear()
        self.artifact_preview.clear()
        self.provenance_text.clear()
        self.topology.show_run({"artifacts": []})
        generation = self._load_generation
        self._task("run:" + str(generation), lambda: load_run(path, self.project))

    def _show_run(self, result):
        self.selected_run = result
        self.topology.show_run(result)
        self.result_heading.setText(
            _value(result.get("benchmark"))
            + " · recorded "
            + str(result.get("state", "unknown"))
        )
        warnings = result.get("warnings", []) + result.get("errors", [])
        self.result_scope.setText(
            "Evidence assessment: "
            + str(result.get("validation_state", "unknown")).replace("_", " ")
            + ". "
            + (
                "\n".join(str(w) for w in warnings)[:1400]
                or "Inspect Validation for the checks behind this recorded result. Missing metrics remain unavailable."
            )
        )
        cycles = []
        for metric in result.get("metrics", []):
            name = metric.get("name", "")
            if (
                not name.endswith(".elapsed_cycles")
                or not str(metric.get("scope", "")).startswith("Direct SALAM")
                or metric.get("value") is None
            ):
                continue
            if metric.get("status") in (
                "invalid_trace",
                "invalid_contract",
                "unverified_artifact",
                "unavailable",
            ):
                continue
            prefix = name[: -len(".elapsed_cycles")]
            if prefix.endswith(".lifecycle"):
                prefix = prefix[: -len(".lifecycle")]
            label = ".".join(prefix.split(".")[-2:]).replace(
                ".invocation-", " / invocation "
            )
            value = metric["value"]
            cycles.append(
                label
                + ": "
                + (format(value, ",") if isinstance(value, int) else str(value))
            )
        self.result_overview.setText(
            "Recorded direct accelerator cycles · " + "  ·  ".join(cycles[:4])
        )
        self.result_overview.setVisible(bool(cycles))
        self.metrics.clear()
        for metric in result.get("metrics", []):
            item = QTreeWidgetItem(
                self.metrics,
                [
                    metric.get("name", ""),
                    _value(metric.get("value")),
                    metric.get("unit") or "—",
                    metric.get("scope") or "Unspecified",
                    metric.get("status") or "unknown",
                    str(metric.get("source") or ""),
                ],
            )
            for column in range(6):
                item.setToolTip(column, item.text(column))
        self._filter_metrics()
        self.checks.clear()
        for check in result.get("checks", []):
            QTreeWidgetItem(
                self.checks,
                [
                    check.get("name", ""),
                    check.get("status", "unknown"),
                    _value(check.get("detail")),
                    str(check.get("source") or ""),
                ],
            )
        self.artifacts.clear()
        self.artifact_preview.clear()
        for artifact in result.get("artifacts", []):
            item = QTreeWidgetItem(
                self.artifacts,
                [
                    artifact.get("name", ""),
                    artifact.get("status", "unknown"),
                    str(artifact.get("path") or ""),
                ],
            )
            item.setData(0, Qt.UserRole, artifact)
        self.provenance_text.setPlainText(
            json.dumps(
                {
                    "path": result.get("path"),
                    "kind": result.get("kind"),
                    "provenance": result.get("provenance", {}),
                    "warnings": warnings,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        for table in (self.history, self.metrics, self.checks, self.artifacts):
            for column in range(min(3, table.columnCount() - 1)):
                table.resizeColumnToContents(column)
                table.setColumnWidth(column, min(table.columnWidth(column), 430))
        for column, width in enumerate((350, 140, 130, 200, 180)):
            self.metrics.setColumnWidth(column, width)

    def _filter_metrics(self):
        query = self.metric_search.text().lower().strip()
        scope = self.metric_scope_combo.currentData()
        for index in range(self.metrics.topLevelItemCount()):
            item = self.metrics.topLevelItem(index)
            system = item.text(3).lower().startswith("gem5")
            matches_scope = scope == "all" or (
                system if scope == "gem5" else not system
            )
            item.setHidden(
                not matches_scope
                or query not in " ".join(item.text(c) for c in range(6)).lower()
            )

    def _artifact_changed(self, item, _previous):
        if item is None:
            return
        artifact = item.data(0, Qt.UserRole)
        path_text = artifact.get("path")
        self._artifact_path = path_text
        if not path_text or artifact.get("status") in (
            "missing",
            "unavailable",
            "outside_allowed_roots",
            "unsafe",
        ):
            self.artifact_preview.setPlainText(
                "Artifact is unavailable or outside the evidence boundary."
            )
            return

        def read():
            return path_text, read_artifact_text(path_text, self.project)

        self._task("artifact", read)

    def compare_selected(self):
        items = self.history.selectedItems()
        if len(items) != 2:
            self.statusBar().showMessage(
                "Select exactly two runs in Results with Ctrl-click, then compare"
            )
            return
        paths = [item.data(0, Qt.UserRole) for item in items]
        self._task(
            "comparison", lambda: [load_run(path, self.project) for path in paths]
        )

    def _show_comparison(self, left, right):
        self.comparison.clear()

        def metrics(result):
            return {
                (m["name"], m.get("unit"), m.get("scope")): m
                for m in result.get("metrics", [])
            }

        a, b = metrics(left), metrics(right)
        for key in sorted(set(a) | set(b), key=str):
            name, unit, scope = key
            QTreeWidgetItem(
                self.comparison,
                [
                    name,
                    _value(a.get(key, {}).get("value")),
                    _value(b.get(key, {}).get("value")),
                    unit or "—",
                    scope or "Unspecified",
                ],
            )
        self.comparison.setHeaderLabels(
            [
                "Metric",
                "A: " + left.get("run_id", "A"),
                "B: " + right.get("run_id", "B"),
                "Unit",
                "Scope",
            ]
        )
        self.result_scope.setText(
            "Side-by-side recorded values. Different inputs, configurations, engines, or scopes do not establish repeatability or speedup."
        )
        self.result_tabs.setCurrentWidget(self.comparison)

    def save_preset(self):
        if self._busy:
            return
        try:
            request = self._current_request()
            validate_request(request, self.project)
            directory = self.project / "evidence/workbench-presets"
            directory.mkdir(parents=True, exist_ok=True)
            name = (
                self.selected_benchmark["name"]
                + "-"
                + datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
                + ".json"
            )
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save configuration preset",
                str(directory / name),
                "Workbench preset (*.json)",
            )
            if path:
                Path(path).write_text(
                    json.dumps(request, indent=2) + "\n", encoding="utf-8"
                )
                self.statusBar().showMessage("Saved preset · " + path)
        except Exception as error:
            QMessageBox.warning(self, "Preset could not be saved", str(error))

    def load_preset(self):
        if self._busy:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load configuration preset",
            str(self.project / "evidence"),
            "Workbench preset (*.json)",
        )
        if path:
            try:
                source = Path(path)
                if source.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError("Preset exceeds 2 MiB")
                self.restore_preset(
                    read_request(source.read_text(encoding="utf-8-sig"))
                )
                self.statusBar().showMessage("Loaded preset · " + path)
            except Exception as error:
                QMessageBox.warning(self, "Preset could not be loaded", str(error))

    def restore_preset(self, request):
        """Restore controls only after validating source identity and exact request."""
        if self._busy:
            raise ValueError("Cannot change presets during an active run")
        validate_request(request, self.project)
        found = None
        for group in range(self.benchmark_tree.topLevelItemCount()):
            parent = self.benchmark_tree.topLevelItem(group)
            for index in range(parent.childCount()):
                item = parent.child(index)
                if item.data(0, Qt.UserRole)["key"] == request["benchmark"]:
                    found = item
        if found is None:
            raise ValueError("Preset benchmark is not in the installed catalog")
        self.mode_combo.setCurrentIndex(0)
        self.benchmark_tree.setCurrentItem(found)
        self.reload_source()
        editor = self.editor
        snapshot = request["provenance"]["editor_snapshot"]
        editor._editor_loading = True
        try:
            editor.cluster_name_edit.setText(snapshot["cluster_name"])
            editor.component_tree.clear()
            for component in snapshot["components"]:
                item = QTreeWidgetItem(
                    editor.component_tree,
                    [component["name"], component["type"].title()],
                )
                item.setData(0, Qt.UserRole, deepcopy(component))
            editor.base_addr_edit.setText(snapshot["base_address"])
            editor.alignment_spin.setValue(snapshot["alignment"])
            for field, key in (
                ("mem_size_edit", "mem-size"),
                ("mem_type_edit", "mem-type"),
                ("cpu_clock_edit", "cpu-clock"),
                ("sys_clock_edit", "sys-clock"),
            ):
                getattr(editor, field).setText(snapshot["system"].get(key, ""))
            profile = snapshot["hardware_profile"]
            editor.model_edit.setText(profile["model"])
            editor.profile_edit.setText(profile["profile"])
            editor._refresh_periods(preferred=profile["period"])
            editor._hardware_tables = deepcopy(snapshot["hardware_by_accelerator"])
            editor.hardware_target_combo.blockSignals(True)
            editor.hardware_target_combo.clear()
            editor.hardware_target_combo.addItems(
                [
                    c["name"]
                    for c in snapshot["components"]
                    if c["type"] == "accelerator"
                ]
            )
            editor.hardware_target_combo.setCurrentText(snapshot["hardware_target"])
            editor.hardware_target_combo.blockSignals(False)
            editor._active_hardware_target = snapshot["hardware_target"]
            _fill_rows(editor, snapshot["hardware_target"])
            for index in range(editor.model_tree.topLevelItemCount()):
                item = editor.model_tree.topLevelItem(index)
                values = profile.get("fu_overrides", {}).get(item.text(0), {})
                for column, key in enumerate(MODEL_FIELDS, 1):
                    item.setText(column, str(values[key]) if key in values else "")
        finally:
            editor._editor_loading = False
        editor.update_preview()
        restored = editor._make_request()
        for key in (
            "configuration_documents",
            "system",
            "parameters",
            "hardware_profile",
            "base_address",
        ):
            if restored.get(key) != request.get(key):
                raise ValueError("Preset could not be restored exactly: " + key)

    def _populate_environment(self):
        manifest = self.project / "workspace.json"
        data = (
            json.loads(manifest.read_text(encoding="utf-8-sig"))
            if manifest.is_file()
            else {}
        )
        text = {
            "workbench": str(self.project),
            "distribution": self.distribution,
            "configuration_engine": str(self.engine),
            "workspace_manifest_sha256": file_hash(manifest)
            if manifest.is_file()
            else None,
            "binding": data,
            "metric_scope": {
                "direct_salam": "Accelerator invocation output with its recorded validation status.",
                "gem5_stats": "Whole-guest system totals unless the metric itself specifies another scope.",
                "power_and_area": "Model estimates only when actually present; absent values remain unavailable.",
            },
        }
        self.environment.setPlainText(json.dumps(text, indent=2, ensure_ascii=False))

    def _open_local(self, relative):
        try:
            path = (self.project / relative).resolve(strict=True)
            path.relative_to(self.project)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except (OSError, ValueError) as error:
            self.statusBar().showMessage("Could not open local resource: " + str(error))

    def closeEvent(self, event):
        if self._busy:
            self.statusBar().showMessage(
                "A run is active. Leave Workbench open until its checked backend finishes."
            )
            event.ignore()
            return
        if self._task_queue or any(task.isRunning() for task in self._tasks):
            self.statusBar().showMessage(
                "Finishing evidence reads; close again in a moment"
            )
            event.ignore()
            return
        if self.selected_benchmark:
            self.settings.setValue("benchmark", self.selected_benchmark["key"])
        super().closeEvent(event)
