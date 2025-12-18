# ==============================================================================
# help_browser.py - Integrated Documentation Browser
# ==============================================================================
"""Integrated Help System for gem5-SALAM GUI.

This module implements a CHM-style integrated help system that provides
searchable access to all project documentation from within the GUI.

Features:
    - Table of Contents navigation (tree view)
    - Full-text search across all documentation
    - Markdown/HTML rendering with syntax highlighting
    - Hyperlink navigation between topics
    - Search history and bookmarks
    - Print support

Architecture::

    +-------------------------------------------------------------------+
    |  Help Browser Window                                     [-][o][X]|
    +-------------------------------------------------------------------+
    |  [<] [>] [Home] [Print]  | Search: [________________] [Go]        |
    +-------------------+-----------------------------------------------+
    |                   |                                               |
    |  Contents         |  Topic Content                                |
    |  +-[Getting Started] |                                            |
    |  | +-Overview    |  # Overview                                   |
    |  | +-Installation|                                               |
    |  | +-Quick Start |  The gem5-SALAM GUI provides visualization   |
    |  +-[GUI Reference]|  tools for hardware accelerator simulation.  |
    |  | +-Main Window |                                               |
    |  | +-CDFG Viewer |  ## Features                                   |
    |  | +-Widgets     |  - CDFG visualization                          |
    |  +-[Benchmarks]   |  - Statistics dashboard                       |
    |  | +-Legacy      |  - Real-time monitoring                        |
    |  | +-Neural Nets |                                               |
    |  +-[API Reference]|                                               |
    |    +-Parsers     |                                               |
    |    +-Widgets     |                                               |
    |                   |                                               |
    +-------------------+-----------------------------------------------+
    | Index | Search Results                                            |
    +-------------------------------------------------------------------+

Content Sources:
    | Source               | Content Type              |
    |----------------------|---------------------------|
    | scripts/salam_gui/   | GUI module docstrings     |
    | benchmarks/*.md      | Benchmark documentation   |
    | *.md (root)          | Project documentation     |
    | src/**/*.hh          | C++ header Doxygen        |

See Also:
    - MainWindow: Integration point for Help menu
"""


__version__ = "3.0.0.pre[1.0.0]"

import os
import re
from pathlib import Path
from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QTextBrowser, QLineEdit,
    QPushButton, QToolBar, QStatusBar, QTabWidget, QListWidget,
    QListWidgetItem, QLabel, QFrame
)
from PySide6.QtGui import QAction, QKeySequence, QFont, QTextDocument
from PySide6.QtCore import Qt, Signal, QUrl


class HelpIndexer:
    """Indexes and searches project documentation.

    Scans the project directory for documentation files and builds
    a searchable index with table of contents structure.

    Attributes:
        project_root: Root directory of gem5-SALAM project
        toc: Hierarchical table of contents
        search_index: Full-text search index
    """

    def __init__(self, project_root: Path):
        """Initialize help indexer.

        Args:
            project_root: Path to gem5-SALAM project root
        """
        self.project_root = project_root
        self.toc: Dict = {}
        self.search_index: Dict[str, List[Dict]] = {}
        self.documents: Dict[str, str] = {}

    def build_index(self):
        """Scan project and build documentation index."""
        doc_sources = [
            ('GUI Reference', 'scripts/salam_gui/**/*.py'),
            ('GUI Reference', 'scripts/salam_gui/**/*.md'),
            ('Benchmarks', 'benchmarks/**/*.md'),
            ('Getting Started', '*.md'),
            ('API Reference', 'src/**/*.hh'),
        ]

        for category, pattern in doc_sources:
            self._scan_files(category, pattern)

    def _scan_files(self, category: str, pattern: str):
        """Scan files matching pattern and add to index."""
        from glob import glob

        full_pattern = str(self.project_root / pattern)
        for filepath in glob(full_pattern, recursive=True):
            path = Path(filepath)
            content = self._extract_content(path)
            if content:
                self._add_to_index(category, path, content)

    def _extract_content(self, path: Path) -> Optional[str]:
        """Extract documentation content from a file."""
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            suffix = path.suffix.lower()

            if suffix == '.md':
                return content
            elif suffix == '.py':
                match = re.search(r'^"""(.+?)"""', content, re.DOTALL)
                if match:
                    return match.group(1)
            elif suffix in ('.h', '.hh', '.hpp'):
                match = re.search(r'/\*\*(.+?)\*/', content, re.DOTALL)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return None

    def _add_to_index(self, category: str, path: Path, content: str):
        """Add document to search index."""
        relative_path = path.relative_to(self.project_root)
        key = str(relative_path)

        self.documents[key] = content

        words = re.findall(r'\w+', content.lower())
        for word in set(words):
            if word not in self.search_index:
                self.search_index[word] = []
            self.search_index[word].append({
                'path': key,
                'category': category,
                'title': self._extract_title(content, path)
            })

    def _extract_title(self, content: str, path: Path) -> str:
        """Extract title from document content."""
        match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if match:
            return match.group(1)
        return path.stem.replace('_', ' ').title()

    def search(self, query: str) -> List[Dict]:
        """Search documentation for query terms."""
        terms = query.lower().split()
        results: Dict[str, float] = {}

        for term in terms:
            if term in self.search_index:
                for doc in self.search_index[term]:
                    path = doc['path']
                    if path not in results:
                        results[path] = 0
                    results[path] += 1

        sorted_results = sorted(
            results.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return [
            {'path': path, 'score': score}
            for path, score in sorted_results[:20]
        ]


class HelpBrowser(QMainWindow):
    """Main help browser window.

    Provides integrated documentation browsing with tree navigation,
    content display, and full-text search.
    """

    def __init__(self, project_root: Path, parent: Optional[QWidget] = None):
        """Initialize help browser.

        Args:
            project_root: Path to gem5-SALAM project
            parent: Parent widget
        """
        super().__init__(parent)

        self.project_root = project_root
        self.indexer = HelpIndexer(project_root)
        self.history: List[str] = []
        self.history_pos = -1

        self.setWindowTitle('gem5-SALAM Help')
        self.setMinimumSize(900, 600)

        self._setup_ui()
        self._setup_toolbar()
        self._build_toc()

    def _setup_ui(self):
        """Create main UI layout."""
        central = QWidget()
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)

        # Left panel: TOC + Search
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)

        # Search box
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText('Search documentation...')
        self.search_edit.returnPressed.connect(self._do_search)
        search_btn = QPushButton('Search')
        search_btn.clicked.connect(self._do_search)
        search_layout.addWidget(self.search_edit)
        search_layout.addWidget(search_btn)
        left_layout.addLayout(search_layout)

        # Tab widget for TOC and Search Results
        self.left_tabs = QTabWidget()

        self.toc_tree = QTreeWidget()
        self.toc_tree.setHeaderLabel('Contents')
        self.toc_tree.itemClicked.connect(self._on_toc_clicked)
        self.left_tabs.addTab(self.toc_tree, 'Contents')

        self.search_list = QListWidget()
        self.search_list.itemClicked.connect(self._on_search_clicked)
        self.left_tabs.addTab(self.search_list, 'Search Results')

        left_layout.addWidget(self.left_tabs)

        # Right panel: Content browser
        self.content_browser = QTextBrowser()
        self.content_browser.setOpenExternalLinks(True)
        self.content_browser.setFont(QFont('Segoe UI', 10))
        self.content_browser.anchorClicked.connect(self._on_link_clicked)

        splitter.addWidget(left_panel)
        splitter.addWidget(self.content_browser)
        splitter.setSizes([250, 650])

        layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _setup_toolbar(self):
        """Create navigation toolbar."""
        toolbar = QToolBar('Navigation')
        self.addToolBar(toolbar)

        self.back_action = QAction('Back', self)
        self.back_action.setShortcut(QKeySequence.Back)
        self.back_action.triggered.connect(self._go_back)
        self.back_action.setEnabled(False)
        toolbar.addAction(self.back_action)

        self.forward_action = QAction('Forward', self)
        self.forward_action.setShortcut(QKeySequence.Forward)
        self.forward_action.triggered.connect(self._go_forward)
        self.forward_action.setEnabled(False)
        toolbar.addAction(self.forward_action)

        toolbar.addSeparator()

        home_action = QAction('Home', self)
        home_action.triggered.connect(self._show_home)
        toolbar.addAction(home_action)

    def _build_toc(self):
        """Build table of contents from indexed documentation."""
        self.status_bar.showMessage('Building documentation index...')
        self.indexer.build_index()

        toc_structure = {
            'Getting Started': [
                ('Overview', 'README.md'),
                ('Installation', 'INSTALL.md'),
                ('Quick Start', 'QUICKSTART.md'),
            ],
            'GUI Reference': [
                ('Main Window', 'scripts/salam_gui/main_window.py'),
                ('CDFG Viewer', 'scripts/salam_gui/widgets/cdfg_viewer.py'),
                ('Statistics Dashboard', 'scripts/salam_gui/widgets/stats_dashboard.py'),
                ('Queue Monitor', 'scripts/salam_gui/widgets/queue_monitor.py'),
                ('FU Utilization', 'scripts/salam_gui/widgets/fu_utilization.py'),
                ('Execution Timeline', 'scripts/salam_gui/widgets/execution_timeline.py'),
            ],
            'Benchmarks': [
                ('Overview', 'benchmarks/README.md'),
                ('Legacy Benchmarks', 'benchmarks/legacy/README.md'),
                ('GEMM', 'benchmarks/legacy/gemm/README.md'),
            ],
            'API Reference': [
                ('Data Parsers', 'scripts/salam_gui/data/__init__.py'),
                ('DOT Parser', 'scripts/salam_gui/data/dot_parser.py'),
                ('Stats Parser', 'scripts/salam_gui/data/stats_parser.py'),
            ],
        }

        self.toc_tree.clear()

        for category, items in toc_structure.items():
            category_item = QTreeWidgetItem([category])
            category_item.setExpanded(True)

            for title, path in items:
                item = QTreeWidgetItem([title])
                item.setData(0, Qt.UserRole, path)
                category_item.addChild(item)

            self.toc_tree.addTopLevelItem(category_item)

        self.status_bar.showMessage(
            f'Ready - {len(self.indexer.documents)} documents indexed'
        )

        self._show_home()

    def _show_home(self):
        """Display home/welcome page."""
        html = """
        <h1>gem5-SALAM Documentation</h1>
        <p>Welcome to the gem5-SALAM integrated help system.</p>

        <h2>Quick Links</h2>
        <ul>
            <li><a href="doc:README.md">Project Overview</a></li>
            <li><a href="doc:benchmarks/README.md">Benchmark Guide</a></li>
            <li><a href="doc:scripts/salam_gui/main_window.py">GUI Reference</a></li>
        </ul>

        <h2>Getting Help</h2>
        <ul>
            <li>Use the <b>Contents</b> tree to browse topics</li>
            <li>Use the <b>Search</b> box to find specific information</li>
            <li>Click links in documentation to navigate</li>
        </ul>
        """
        self.content_browser.setHtml(html)

    def _navigate_to(self, doc_path: str):
        """Navigate to a document."""
        if self.history_pos < len(self.history) - 1:
            self.history = self.history[:self.history_pos + 1]
        self.history.append(doc_path)
        self.history_pos = len(self.history) - 1
        self._update_nav_buttons()

        content = self.indexer.documents.get(doc_path, '')
        if content:
            html = self._markdown_to_html(content)
            self.content_browser.setHtml(html)
            self.status_bar.showMessage(f'Viewing: {doc_path}')
        else:
            full_path = self.project_root / doc_path
            if full_path.exists():
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    html = self._markdown_to_html(content)
                    self.content_browser.setHtml(html)
                except Exception as e:
                    self.content_browser.setHtml(f'<p>Error loading: {e}</p>')
            else:
                self.content_browser.setHtml(f'<p>Document not found: {doc_path}</p>')

    def _markdown_to_html(self, text: str) -> str:
        """Convert markdown text to HTML."""
        html = text

        # Code blocks
        html = re.sub(
            r'```(\w*)\n(.+?)```',
            r'<pre style="background:#f4f4f4;padding:10px;"><code>\2</code></pre>',
            html,
            flags=re.DOTALL
        )

        # Inline code
        html = re.sub(r'`([^`]+)`', r'<code style="background:#f4f4f4;">\1</code>', html)

        # Headers
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

        # Bold and italic
        html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
        html = re.sub(r'\*(.+?)\*', r'<i>\1</i>', html)

        # Links
        html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)

        # Lists
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)

        # Wrap in styled container
        return f'''
        <html>
        <head>
            <style>
                body {{ font-family: Segoe UI, sans-serif; margin: 20px; }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; }}
                h2 {{ color: #34495e; }}
                pre {{ background: #f4f4f4; padding: 10px; overflow-x: auto; }}
                code {{ background: #f4f4f4; padding: 2px 5px; }}
                table {{ border-collapse: collapse; }}
                a {{ color: #3498db; }}
            </style>
        </head>
        <body>
        {html}
        </body>
        </html>
        '''

    def _on_toc_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle TOC tree item click."""
        doc_path = item.data(0, Qt.UserRole)
        if doc_path:
            self._navigate_to(doc_path)

    def _on_search_clicked(self, item: QListWidgetItem):
        """Handle search result click."""
        doc_path = item.data(Qt.UserRole)
        if doc_path:
            self._navigate_to(doc_path)

    def _on_link_clicked(self, url: QUrl):
        """Handle link click in content browser."""
        url_str = url.toString()
        if url_str.startswith('doc:'):
            doc_path = url_str[4:]
            self._navigate_to(doc_path)

    def _do_search(self):
        """Execute search query."""
        query = self.search_edit.text().strip()
        if not query:
            return

        results = self.indexer.search(query)

        self.search_list.clear()
        for result in results:
            path = result['path']
            title = self.indexer._extract_title(
                self.indexer.documents.get(path, ''),
                Path(path)
            )
            item = QListWidgetItem(f'{title}\n{path}')
            item.setData(Qt.UserRole, path)
            self.search_list.addItem(item)

        self.left_tabs.setCurrentIndex(1)
        self.status_bar.showMessage(f'Found {len(results)} results for "{query}"')

    def _go_back(self):
        """Navigate back in history."""
        if self.history_pos > 0:
            self.history_pos -= 1
            doc_path = self.history[self.history_pos]
            content = self.indexer.documents.get(doc_path, '')
            if content:
                html = self._markdown_to_html(content)
                self.content_browser.setHtml(html)
            self._update_nav_buttons()

    def _go_forward(self):
        """Navigate forward in history."""
        if self.history_pos < len(self.history) - 1:
            self.history_pos += 1
            doc_path = self.history[self.history_pos]
            content = self.indexer.documents.get(doc_path, '')
            if content:
                html = self._markdown_to_html(content)
                self.content_browser.setHtml(html)
            self._update_nav_buttons()

    def _update_nav_buttons(self):
        """Update back/forward button states."""
        self.back_action.setEnabled(self.history_pos > 0)
        self.forward_action.setEnabled(self.history_pos < len(self.history) - 1)


__all__ = ['HelpBrowser', 'HelpIndexer']
