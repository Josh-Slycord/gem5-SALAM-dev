"""Interactive, source-labeled SALAM technical reference for the process view."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

REPO = "https://github.com/Josh-Slycord/gem5-SALAM-dev/blob/0424992bab2a016591409020dc9e99ec073388d3/"
TOPICS = (
    (
        "LLVM parsing",
        "The published SALAMv2 parser reads the LLVM module, maps LLVM values to SALAM values, and initializes the SALAM representation. Static basic blocks and control/data dependencies provide the program structure; dynamic instruction instances arise as execution follows control flow. This is a conceptual model, not a graph extracted from the selected run.",
        "src/hwacc/llvm_interface.cc#L474",
        "2024 paper, Fig. 5",
    ),
    (
        "Reservation + dependencies",
        "The runtime creates dynamic instruction instances and tracks them in a reservation queue. Instructions become eligible when their dependencies are satisfied. The runtime can handle control/flow instructions, including phi/select and terminators, in place rather than dispatching every operation to a compute unit.",
        "src/hwacc/llvm_interface.cc#L136",
        "2020 paper, Fig. 3; 2024 paper, Fig. 5",
    ),
    (
        "Compute + completion",
        "Eligible modeled compute operations issue to the compute queue subject to modeled resource availability. SALAM evaluates values at issue and delays the completion/commit according to configured latency. Completion releases resources and notifies dependents. Supported resource constraints and timing depend on the simulator version and configuration.",
        "src/hwacc/llvm_interface.cc#L97",
        "2020 paper, Fig. 3",
    ),
    (
        "Read + write queues",
        "Memory operations are tracked separately in read and write queues and use the communication interface to access the gem5 memory system. Responses complete asynchronously and can release dependent work. Internal and external paths vary with the modeled instruction and memory configuration.",
        "src/hwacc/llvm_interface.cc#L589",
        "2020 paper, Figs. 3 and 6; 2024 paper, Fig. 6",
    ),
    (
        "CommInterface + PIO",
        "CommInterface is a gem5 BasicPioDevice connecting accelerator control and memory behavior to the system. Its control side includes programmed-I/O / memory-mapped registers and interrupt support; its requestor ports can connect to different memory or interconnect paths.",
        "src/hwacc/CommInterface.py",
        "2020 paper, Figs. 1 and 5",
    ),
    (
        "Memory + interconnect",
        "The SALAMv2 communication model describes optional stream, SPM, register-bank, cluster and coherence connections. DMA, private/shared scratchpads, caches and local/global interconnects are configuration-dependent. Inspect System topology for the selected run's actual instantiated SimObjects and ports.",
        "src/hwacc/CommInterface.py",
        "2024 paper, Fig. 6",
    ),
    (
        "Generator + model",
        "The Configurator consumes cluster/device YAML and generates gem5 full-system configuration, SALAM accelerator configuration, and C memory-map headers. Hardware profiles supply functional-unit, instruction and model parameters. The paper's per-accelerator runtime profiles and the Workbench's possible rebuild of compiled defaults are different mechanisms.",
        "SALAM-Configurator/systembuilder.py#L264",
        "2024 paper, Figs. 2–4",
    ),
    (
        "Telemetry + evidence",
        "Direct SALAM invocation outputs and gem5 stats.txt have different scopes. Queue/commit and FU trace fields cover the events declared by their collector, not necessarily every retired instruction. Energy, area and power require an appropriate model or measured source; absent values remain unavailable.",
        "src/hwacc/workbench_statistics.hh#L281",
        "Workbench collector contract",
    ),
)


class InternalsPanel(QWidget):
    """A navigable technical reference, not a selected-run topology claim."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_topic = 0
        layout = QVBoxLayout(self)
        scope = QLabel(
            "Select a mechanism · conceptual architecture, with paper and implementation references. Actual ports and components depend on the selected configuration."
        )
        scope.setWordWrap(True)
        layout.addWidget(scope)
        ribbon_scroll = QScrollArea()
        ribbon_scroll.setWidgetResizable(True)
        ribbon_scroll.setMinimumHeight(142)
        ribbon_scroll.setMaximumHeight(186)
        ribbon = QWidget()
        grid = QGridLayout(ribbon)
        grid.setContentsMargins(4, 4, 4, 4)
        self.buttons = []
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for index, (title, _detail, _source, _paper) in enumerate(TOPICS):
            button = QPushButton(title)
            button.setCheckable(True)
            button.setMinimumSize(145, 48)
            button.setAccessibleName(title)
            button.setStyleSheet(
                "QPushButton { text-align: left; background: #f5f8fb; border: 1px solid #ccd7e0; color: #172f4a; font-weight: 600; } QPushButton:checked { background: #e7f5f3; border: 2px solid #087d80; }"
            )
            button.clicked.connect(lambda _checked=False, n=index: self.select_topic(n))
            self.buttons.append(button)
            self.group.addButton(button)
            grid.addWidget(button, index // 4, index % 4)
        ribbon_scroll.setWidget(ribbon)
        layout.addWidget(ribbon_scroll)
        self.heading = QLabel()
        self.heading.setStyleSheet("font-size: 17px; font-weight: 600; color: #172f4a;")
        layout.addWidget(self.heading)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        layout.addWidget(self.detail, 1)
        self.references = QLabel()
        self.references.setWordWrap(True)
        self.references.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.references.setOpenExternalLinks(True)
        layout.addWidget(self.references)
        self.select_topic(0)

    def select_topic(self, index):
        if not 0 <= index < len(TOPICS):
            return
        self.selected_topic = index
        title, detail, source, paper = TOPICS[index]
        self.buttons[index].setChecked(True)
        self.heading.setText(title)
        self.detail.setPlainText(detail)
        self.references.setText(
            'Research: {} · <a href="{}{}">View implementation source</a>'.format(
                paper, REPO, source
            )
        )
