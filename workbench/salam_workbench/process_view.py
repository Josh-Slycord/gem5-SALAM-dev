"""Interactive conceptual workflow, with optional links to recorded run files."""
import hashlib
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .workbench_results import _roots, _safe

PALETTE = {
    "ink": "#172f4a",
    "muted": "#546779",
    "blue": "#1f5fa7",
    "teal": "#087d80",
    "amber": "#b76222",
    "border": "#ccd7e0",
}
STAGES = (
    {
        "title": "Choose + configure",
        "color": "blue",
        "description": "Choose a workload and edit the system, accelerator, memory and hardware settings for a configured simulation.",
        "suffixes": ("config.yml", "config.yaml", "workbench_profile.yml"),
    },
    {
        "title": "Stage the request",
        "color": "blue",
        "description": "The Workbench validates and stages the selected configuration and its inputs. The original benchmark configuration remains an input.",
        "suffixes": ("configuration.json", "experiment.json"),
    },
    {
        "title": "Hardware build selection",
        "color": "amber",
        "description": "The configured pipeline can reuse a verified simulator, or generate a hardware variant and rebuild when the selected model requires it.",
        "suffixes": ("_hw_defines.h", "SALAMClassGenerator.py", "config.ini"),
    },
    {
        "title": "Compile workload",
        "color": "teal",
        "description": "Prepare the benchmark software and LLVM intermediate representation for the staged accelerator workload.",
        "suffixes": (".ll", "main.elf", "Makefile"),
    },
    {
        "title": "Run gem5-SALAM",
        "color": "teal",
        "description": "gem5 executes the modeled system; SALAM's accelerator models consume the workload representation within that simulated system.",
        "suffixes": ("stdout.txt", "system.terminal", "config.dot.svg"),
    },
    {
        "title": "Validate recorded evidence",
        "color": "amber",
        "description": "The Workbench checks available guest, simulator-exit, configuration and SALAM evidence. The checks performed depend on the run and workload.",
        "suffixes": ("system.terminal", "stdout.txt", "configuration.json"),
    },
    {
        "title": "Inspect + compare",
        "color": "blue",
        "description": "Explore direct SALAM outputs, gem5 system statistics, provenance and the recorded system topology. Metric scope and missing values remain explicit.",
        "suffixes": ("stats.txt", ".invocation-1.json", "config.dot.svg"),
    },
)
MAX_PREVIEW_FILE = 8 * 1024 * 1024
MAX_PREVIEW_TEXT = 512 * 1024


def related_artifacts(result, stage):
    """Return only recorded, hash-verified candidates; names imply no execution claim."""
    if not isinstance(result, dict) or not 0 <= stage < len(STAGES):
        return []
    candidates = []
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    for item in artifacts:
        if not isinstance(item, dict) or item.get("status") != "hash_verified":
            continue
        name = str(item.get("name", ""))
        if any(name.endswith(suffix) for suffix in STAGES[stage]["suffixes"]):
            candidates.append(item)
    return candidates[:20]


def preview_artifact(project, artifact):
    """Read a bounded artifact only if its current bytes still match the manifest."""
    if not isinstance(artifact, dict) or artifact.get("status") != "hash_verified":
        raise ValueError("Artifact is not hash verified")
    _, roots = _roots(project)
    path = _safe(Path(str(artifact.get("path", ""))), roots)
    if path.stat().st_size > MAX_PREVIEW_FILE:
        raise ValueError("Artifact exceeds the 8 MiB preview verification limit")
    with path.open("rb") as handle:
        data = handle.read(MAX_PREVIEW_FILE + 1)
    if len(data) > MAX_PREVIEW_FILE:
        raise ValueError("Artifact exceeds the 8 MiB preview verification limit")
    digest = hashlib.sha256(data).hexdigest()
    if digest != artifact.get("sha256"):
        raise ValueError("Artifact no longer matches its recorded SHA-256")
    if b"\x00" in data:
        return "Binary artifact · {} bytes\nSHA-256: {}".format(len(data), digest)
    tail = data[-MAX_PREVIEW_TEXT:].decode("utf-8", errors="replace")
    return ("[Showing final 512 KiB]\n" if len(data) > MAX_PREVIEW_TEXT else "") + tail


class ProcessPanel(QWidget):
    """Selectable process schematic; source-backed results are optional context."""

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = Path(project).resolve(strict=True)
        self.result = None
        self.selected_stage = 0
        layout = QVBoxLayout(self)
        title = QLabel("SALAM · from workload to evidence")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #172f4a;")
        layout.addWidget(title)
        scope = QLabel(
            "Conceptual configured-workflow overview · select a stage for details. Fixed reference and historical runs follow separate runners. The system topology tab shows the selected run's actual configured SimObjects and ports."
        )
        scope.setWordWrap(True)
        scope.setStyleSheet("color: #546779;")
        layout.addWidget(scope)
        ribbon_scroll = QScrollArea()
        ribbon_scroll.setWidgetResizable(True)
        ribbon_scroll.setMinimumHeight(125)
        ribbon_scroll.setMaximumHeight(165)
        ribbon = QWidget()
        grid = QGridLayout(ribbon)
        grid.setContentsMargins(10, 12, 10, 12)
        grid.setHorizontalSpacing(5)
        grid.setVerticalSpacing(8)
        self.buttons = []
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        locations = tuple((0, index * 2) for index in range(len(STAGES)))
        labels = (
            "Choose +\nconfigure",
            "Stage the\nrequest",
            "Hardware build\nselection",
            "Compile\nworkload",
            "Run gem5-SALAM",
            "Validate\nrecorded evidence",
            "Inspect +\ncompare",
        )
        for index, (row, col) in enumerate(locations):
            stage = STAGES[index]
            button = QPushButton("{:02d}\n{}".format(index + 1, labels[index]))
            button.setCheckable(True)
            button.setMinimumSize(126, 62)
            button.setAccessibleName(stage["title"])
            button.setStyleSheet(
                "QPushButton { background: #f4f7fa; border: 1px solid #ccd7e0; color: #172f4a; text-align: left; font-weight: 600; } QPushButton:checked { background: #edf4fc; border: 2px solid "
                + PALETTE[stage["color"]]
                + "; }"
            )
            button.clicked.connect(lambda _checked=False, n=index: self.select_stage(n))
            self.buttons.append(button)
            self.button_group.addButton(button)
            grid.addWidget(button, row, col)
        for col in (1, 3, 5, 7, 9, 11):
            arrow = QLabel("→")
            arrow.setAlignment(Qt.AlignCenter)
            arrow.setStyleSheet("font-size: 19px; color: #546779;")
            grid.addWidget(arrow, 0, col)
        ribbon_scroll.setWidget(ribbon)
        layout.addWidget(ribbon_scroll)
        self.heading = QLabel()
        self.heading.setStyleSheet("font-size: 17px; font-weight: 600; color: #172f4a;")
        layout.addWidget(self.heading)
        self.description = QLabel()
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.run_summary = QLabel(
            "Select a recorded run in Results and metrics to see related evidence here."
        )
        self.run_summary.setWordWrap(True)
        self.run_summary.setStyleSheet("color: #546779;")
        layout.addWidget(self.run_summary)
        split = QSplitter(Qt.Horizontal)
        self.artifacts = QListWidget()
        self.artifacts.setAccessibleName("Related recorded artifacts")
        self.artifacts.currentRowChanged.connect(self._preview)
        split.addWidget(self.artifacts)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText(
            "Select a related file to read its verified contents."
        )
        split.addWidget(self.preview)
        split.setSizes([260, 700])
        layout.addWidget(split, 1)
        citations = QLabel(
            'Research context: <a href="https://doi.org/10.1109/LCA.2019.2893932">Rogers et al., 2019</a> · <a href="https://doi.org/10.1109/MICRO50266.2020.00047">Rogers et al., MICRO 2020</a> · <a href="https://doi.org/10.1016/j.sysarc.2024.103211">Spencer et al., 2024</a>'
        )
        citations.setOpenExternalLinks(True)
        citations.setWordWrap(True)
        layout.addWidget(citations)
        self.select_stage(0)

    def show_run(self, result):
        self.result = result if isinstance(result, dict) else None
        self._refresh_stage()

    def select_stage(self, index):
        if not 0 <= index < len(STAGES):
            return
        self.selected_stage = index
        self.buttons[index].setChecked(True)
        self._refresh_stage()

    def _refresh_stage(self):
        stage = STAGES[self.selected_stage]
        self.heading.setText(stage["title"])
        self.description.setText(stage["description"])
        self.artifacts.clear()
        self.preview.clear()
        self._related = related_artifacts(self.result, self.selected_stage)
        if self.result is None:
            self.run_summary.setText(
                "Select a recorded run in Results and metrics to see related evidence here."
            )
        else:
            self.run_summary.setText(
                "Selected run: {} · recorded {} · related hash-verified files: {} (up to 20 shown). A filename alone does not establish that a process stage passed.".format(
                    self.result.get("benchmark", "unknown"),
                    self.result.get("state", "unknown"),
                    len(self._related),
                )
            )
            for artifact in self._related:
                self.artifacts.addItem(str(artifact.get("name", "artifact")))
        if not self._related:
            self.preview.setPlaceholderText(
                "No matching verified files are recorded for this stage."
            )
        else:
            self.preview.setPlaceholderText(
                "Select a related file to read its verified contents."
            )

    def _preview(self, index):
        if not 0 <= index < len(self._related):
            self.preview.clear()
            return
        artifact = self._related[index]
        try:
            content = preview_artifact(self.project, artifact)
            self.preview.setPlainText(
                "Source: {}\nSHA-256: {}\n\n{}".format(
                    artifact.get("path"), artifact.get("sha256"), content
                )
            )
        except (OSError, ValueError) as error:
            self.preview.setPlainText("Evidence unavailable: " + str(error))
