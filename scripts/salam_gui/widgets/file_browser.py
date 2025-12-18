# ==============================================================================
# file_browser.py - Simulation Output File Browser
# ==============================================================================
"""File Browser Widget for Simulation Outputs.

This module provides the FileBrowser widget, which allows users to
navigate and select files from gem5-SALAM simulation output directories.

Features:
    - Directory tree navigation
    - File type filtering (shows relevant extensions)
    - Double-click to open files
    - Legend showing file type meanings
    - Detection of CDFG and stats files

Widget Layout::

    +------------------------------------------+
    | /path/to/m5out                           |
    +------------------------------------------+
    | [v] m5out/                               |
    |   |- cdfg.dot                            |
    |   |- stats.txt                           |
    |   |- config.ini                          |
    |   |- config.json                         |
    |   |+ system/                             |
    +------------------------------------------+
    | .dot CDFG | .txt/.json Stats | .yml Conf |
    +------------------------------------------+

Supported File Types:
    | Extension | Purpose                    |
    |-----------|----------------------------|
    | .dot      | CDFG visualization         |
    | .txt      | Statistics output          |
    | .json     | Configuration/results      |
    | .csv      | Tabular data               |
    | .yml/.yaml| Configuration files        |

Signals:
    file_selected(Path): Emitted when a file is double-clicked

Example:
    Setting up the file browser::

        from salam_gui.widgets.file_browser import FileBrowser

        browser = FileBrowser()
        browser.file_selected.connect(self.on_file_selected)
        browser.set_directory(Path("/path/to/m5out"))

        # Check for specific files
        if browser.has_cdfg():
            print("CDFG file found!")

See Also:
    - MainWindow: Hosts this widget as a left-side dock
    - CDFGViewer: Opens .dot files from this browser
    - StatsDashboard: Opens stats files from this browser
"""


__version__ = "3.0.0.pre[1.0.0]"

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeView, QLabel,
    QFileSystemModel, QHeaderView
)
from PySide6.QtCore import Qt, Signal, QModelIndex


class FileBrowser(QWidget):
    """File browser for simulation output directories."""

    file_selected = Signal(Path)  # Emitted when a file is selected

    # File types we care about
    INTERESTING_EXTENSIONS = {'.dot', '.txt', '.json', '.csv', '.yml', '.yaml'}

    def __init__(self):
        super().__init__()
        self.current_dir: Optional[Path] = None
        self._setup_ui()

    def _setup_ui(self):
        """Set up the file browser UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Current directory label
        self.path_label = QLabel("No directory selected")
        self.path_label.setStyleSheet("padding: 5px; background: #f0f0f0;")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        # File system model and tree view
        self.model = QFileSystemModel()
        self.model.setReadOnly(True)

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setAnimated(True)
        self.tree.setIndentation(15)
        self.tree.setSortingEnabled(True)

        # Hide unnecessary columns (size, type, date modified)
        self.tree.setColumnHidden(1, True)  # Size
        self.tree.setColumnHidden(2, True)  # Type
        self.tree.setColumnHidden(3, True)  # Date

        # Adjust header
        header = self.tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        # Connect signals
        self.tree.clicked.connect(self._on_item_clicked)
        self.tree.doubleClicked.connect(self._on_item_double_clicked)

        layout.addWidget(self.tree)

        # Legend
        legend = QLabel(
            "<small>"
            "<b>.dot</b> CDFG | "
            "<b>.txt/.json</b> Stats | "
            "<b>.yml</b> Config"
            "</small>"
        )
        legend.setStyleSheet("color: gray; padding: 3px;")
        layout.addWidget(legend)

    def set_directory(self, dir_path: Path):
        """Set the root directory to browse."""
        if not dir_path.exists():
            return

        self.current_dir = dir_path
        self.path_label.setText(str(dir_path))

        # Set root path
        self.model.setRootPath(str(dir_path))
        self.tree.setRootIndex(self.model.index(str(dir_path)))

        # Expand to show files
        self.tree.expandAll()

    def _on_item_clicked(self, index: QModelIndex):
        """Handle single click on item."""
        file_path = Path(self.model.filePath(index))

        # Highlight interesting files
        if file_path.is_file() and file_path.suffix in self.INTERESTING_EXTENSIONS:
            # Emit signal for preview
            pass

    def _on_item_double_clicked(self, index: QModelIndex):
        """Handle double click on item."""
        file_path = Path(self.model.filePath(index))

        if file_path.is_file():
            self.file_selected.emit(file_path)
        elif file_path.is_dir():
            # Expand/collapse directory
            if self.tree.isExpanded(index):
                self.tree.collapse(index)
            else:
                self.tree.expand(index)

    def get_interesting_files(self):
        """Get list of interesting files in current directory."""
        if not self.current_dir:
            return []

        files = []
        for ext in self.INTERESTING_EXTENSIONS:
            files.extend(self.current_dir.rglob(f"*{ext}"))

        return sorted(files)

    def has_cdfg(self) -> bool:
        """Check if current directory has a CDFG file."""
        if not self.current_dir:
            return False
        return (self.current_dir / "cdfg.dot").exists()

    def has_stats(self) -> bool:
        """Check if current directory has stats files."""
        if not self.current_dir:
            return False
        return (
            (self.current_dir / "stats.txt").exists() or
            (self.current_dir / "test_results.json").exists()
        )
