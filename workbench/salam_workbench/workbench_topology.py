"""Display the original hash-bound gem5 SimObject graph; never regenerate it.

Pure readers do not import Qt. Importing TopologyPanel lazily loads the desktop
widget, so safety/parser tests can run without a GUI installation.
"""
import hashlib
import re
from pathlib import Path
from xml.etree import ElementTree

from .workbench_results import _roots, _safe

MAX_SVG_BYTES = 8 * 1024 * 1024
MAX_SVG_ELEMENTS = 100000
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
SCOPE = (
    "Original gem5 SimObject and port configuration graph. This shows the "
    "configured system structure, not runtime activity, data flow, or utilization."
)
_DOCTYPE = re.compile(
    rb"<!DOCTYPE\s+svg\s+PUBLIC\s+[\"\']-//W3C//DTD SVG 1\.[01]//EN[\"\']\s+"
    rb"[\"\']https?://www\.w3\.org/Graphics/SVG/1\.[01]/DTD/svg1[01]\.dtd[\"\']\s*>",
    re.IGNORECASE,
)
_DISALLOWED = frozenset(
    (
        "script",
        "foreignobject",
        "image",
        "style",
        "metadata",
        "iframe",
        "object",
        "embed",
        "filter",
        "feimage",
        "animate",
        "animatemotion",
        "animatetransform",
        "set",
    )
)
_PANEL_CLASS = None


def _local(name):
    return name.rsplit("}", 1)[-1].lower()


def sanitize_svg(payload):
    """Return an inert SVG byte copy suitable for Qt's local SVG renderer.

    Graphviz's normal external SVG DTD declaration is stripped without fetching
    it. Entity declarations, internal DTD subsets, and non-SVG documents fail.
    Scripts, foreign content, images, CSS and external links are removed from
    the in-memory copy. The original evidence file is never changed.
    """
    if not isinstance(payload, bytes) or len(payload) > MAX_SVG_BYTES:
        raise ValueError("Topology SVG must be bytes and at most 8 MiB")
    # UTF-16 encodings could hide entity declarations from the ASCII scan.
    if b"\x00" in payload or re.search(rb"<!ENTITY", payload, re.IGNORECASE):
        raise ValueError("SVG entities and non-UTF-8 encodings are unsupported")
    payload = _DOCTYPE.sub(b"", payload)
    if re.search(rb"<!DOCTYPE", payload, re.IGNORECASE):
        raise ValueError("Unsupported SVG document type or internal subset")
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        raise ValueError("Topology SVG is not valid XML: " + str(error)) from error
    if root.tag not in ("svg", "{" + SVG_NAMESPACE + "}svg"):
        raise ValueError("Topology graph must have an SVG root")
    elements = list(root.iter())
    if len(elements) > MAX_SVG_ELEMENTS:
        raise ValueError("Topology SVG exceeds the 100000-element reader limit")
    for parent in elements:
        for child in list(parent):
            if _local(child.tag) in _DISALLOWED:
                parent.remove(child)
        for key, value in list(parent.attrib.items()):
            name = _local(key)
            if name.startswith("on") or name in ("base", "src"):
                del parent.attrib[key]
            elif name == "href" and not value.strip().startswith("#"):
                del parent.attrib[key]
            elif name == "style" and (
                "@import" in value.lower()
                or re.search(r"url\(\s*[\"']?(?!#)", value, re.IGNORECASE)
            ):
                del parent.attrib[key]
            elif "url(" in value.lower() and not re.fullmatch(
                r"\s*url\(\s*#[A-Za-z0-9_.:-]+\s*\)\s*", value
            ):
                # Graphviz uses plain colors; defs/fragment references may
                # remain, but remote paint servers cannot enter the renderer.
                del parent.attrib[key]
    ElementTree.register_namespace("", SVG_NAMESPACE)
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _verified_artifact(artifact, project, expected_name):
    if not isinstance(artifact, dict) or artifact.get("status") != "hash_verified":
        raise ValueError("Graph artifact is not verified against its run manifest")
    source = Path(artifact.get("path", ""))
    if source.name != expected_name:
        raise ValueError("Unexpected topology artifact name")
    _, roots = _roots(project)
    source = _safe(source, roots)
    if source.stat().st_size > MAX_SVG_BYTES:
        raise ValueError("Topology artifact exceeds the 8 MiB reader limit")
    payload = source.read_bytes()
    if len(payload) > MAX_SVG_BYTES:
        raise ValueError("Topology artifact changed while reading")
    expected = artifact.get("sha256")
    actual = hashlib.sha256(payload).hexdigest()
    if (
        not isinstance(expected, str)
        or re.fullmatch(r"[0-9a-fA-F]{64}", expected) is None
        or actual != expected.lower()
    ):
        raise ValueError("Topology artifact no longer matches its recorded SHA-256")
    return source, payload, actual


def load_topology(result, project):
    """Select only the original run's hash-verified config.dot.svg artifact."""
    loaded = {
        "state": "unavailable",
        "svg_bytes": None,
        "source": None,
        "sha256": None,
        "dot": None,
        "pdf": None,
        "issues": [],
        "scope": SCOPE,
        "sanitized_for_display": True,
    }
    artifacts = result.get("artifacts", []) if isinstance(result, dict) else []
    if not isinstance(artifacts, list):
        loaded["issues"].append("Run has no artifact manifest")
        return loaded
    matches = [
        entry
        for entry in artifacts
        if isinstance(entry, dict)
        and Path(str(entry.get("path", ""))).name == "config.dot.svg"
    ]
    if len(matches) != 1:
        loaded["issues"].append(
            "No unique original config.dot.svg was recorded for this run"
        )
        return loaded
    try:
        source, payload, digest = _verified_artifact(
            matches[0], project, "config.dot.svg"
        )
        loaded.update(
            state="ready",
            svg_bytes=sanitize_svg(payload),
            source=str(source),
            sha256=digest,
        )
        for key, name in (("dot", "config.dot"), ("pdf", "config.dot.pdf")):
            companions = [
                entry
                for entry in artifacts
                if isinstance(entry, dict)
                and Path(str(entry.get("path", ""))).name == name
            ]
            if len(companions) == 1:
                try:
                    companion, unused, unused_digest = _verified_artifact(
                        companions[0], project, name
                    )
                    if companion.parent != source.parent:
                        raise ValueError(
                            "Graph companion does not belong to the SVG's run directory"
                        )
                    loaded[key] = dict(companions[0])
                except (OSError, ValueError) as error:
                    loaded["issues"].append(name + ": " + str(error))
    except (OSError, ValueError, TypeError) as error:
        loaded.update(state="unavailable", svg_bytes=None, source=None, sha256=None)
        loaded["issues"].append(str(error))
    return loaded


def _panel_class():
    global _PANEL_CLASS
    if _PANEL_CLASS is not None:
        return _PANEL_CLASS
    from PySide6.QtCore import QByteArray, QRectF, Qt, QTimer, QUrl
    from PySide6.QtGui import QDesktopServices, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtSvgWidgets import QGraphicsSvgItem
    from PySide6.QtWidgets import (
        QGraphicsScene,
        QGraphicsView,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    class _GraphView(QGraphicsView):
        def __init__(self, parent):
            super().__init__(parent)
            self.setRenderHint(QPainter.Antialiasing)
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
            self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
            self.setBackgroundBrush(Qt.white)

        def zoom(self, factor):
            current = self.transform().m11()
            target = current * factor
            if 0.01 <= target <= 20:
                self.scale(factor, factor)

        def wheelEvent(self, event):
            self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
            event.accept()

    class TopologyPanel(QWidget):
        def __init__(self, project, parent=None):
            super().__init__(parent)
            self.project = Path(project).resolve(strict=True)
            self.loaded = None
            self.renderer = None
            self.graph_item = None
            layout = QVBoxLayout(self)
            self.scope = QLabel(SCOPE)
            self.scope.setWordWrap(True)
            layout.addWidget(self.scope)
            toolbar = QHBoxLayout()
            self.fit_btn = QPushButton("Fit system")
            self.zoom_out_btn = QPushButton("−")
            self.zoom_in_btn = QPushButton("+")
            self.actual_btn = QPushButton("100%")
            self.dot_btn = QPushButton("Open original DOT")
            self.pdf_btn = QPushButton("Open original PDF")
            for button in (
                self.fit_btn,
                self.zoom_out_btn,
                self.zoom_in_btn,
                self.actual_btn,
                self.dot_btn,
                self.pdf_btn,
            ):
                toolbar.addWidget(button)
            toolbar.addStretch()
            layout.addLayout(toolbar)
            self.status = QLabel("Select a run to view its original system topology.")
            self.status.setWordWrap(True)
            layout.addWidget(self.status)
            self.scene = QGraphicsScene(self)
            self.view = _GraphView(self)
            self.view.setScene(self.scene)
            layout.addWidget(self.view, 1)
            self.caption = QLabel("")
            self.caption.setWordWrap(True)
            self.caption.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(self.caption)
            self.fit_btn.clicked.connect(self.fit_graph)
            self.zoom_out_btn.clicked.connect(lambda: self.view.zoom(1 / 1.2))
            self.zoom_in_btn.clicked.connect(lambda: self.view.zoom(1.2))
            self.actual_btn.clicked.connect(self.view.resetTransform)
            self.dot_btn.clicked.connect(lambda: self._open_companion("dot"))
            self.pdf_btn.clicked.connect(lambda: self._open_companion("pdf"))
            self._buttons(False)

        def _buttons(self, ready):
            for button in (
                self.fit_btn,
                self.zoom_out_btn,
                self.zoom_in_btn,
                self.actual_btn,
            ):
                button.setEnabled(ready)
            self.dot_btn.setEnabled(
                bool(ready and self.loaded and self.loaded.get("dot"))
            )
            self.pdf_btn.setEnabled(
                bool(ready and self.loaded and self.loaded.get("pdf"))
            )

        def _clear(self):
            self.scene.clear()
            self.graph_item = None
            if self.renderer is not None:
                self.renderer.deleteLater()
            self.renderer = None
            self.view.resetTransform()
            self.caption.clear()
            self._buttons(False)

        def show_run(self, result):
            self._clear()
            self.loaded = load_topology(result, self.project)
            if self.loaded["state"] != "ready":
                self.status.setText(
                    "Topology unavailable · " + "; ".join(self.loaded["issues"])
                )
                return
            self.renderer = QSvgRenderer(QByteArray(self.loaded["svg_bytes"]), self)
            if not self.renderer.isValid():
                self._clear()
                self.loaded.update(state="unavailable", svg_bytes=None)
                self.loaded["issues"].append("Qt could not render this recorded SVG")
                self.status.setText(
                    "Topology unavailable · Qt could not render this recorded SVG."
                )
                return
            self.graph_item = QGraphicsSvgItem()
            self.graph_item.setSharedRenderer(self.renderer)
            self.scene.addItem(self.graph_item)
            self.scene.setSceneRect(QRectF(self.graph_item.boundingRect()))
            self.status.setText("Drag to pan · scroll or use + / − to zoom")
            self.caption.setText(
                "Original: "
                + self.loaded["source"]
                + "\nSHA-256: "
                + self.loaded["sha256"]
                + "\nA sanitized local copy is rendered; original DOT, SVG and PDF evidence is preserved."
            )
            self._buttons(True)
            self.fit_graph()
            QTimer.singleShot(0, self.fit_graph)

        def fit_graph(self):
            if self.graph_item is not None:
                self.view.fitInView(self.graph_item.boundingRect(), Qt.KeepAspectRatio)

        def _open_companion(self, key):
            try:
                if not self.loaded or not self.loaded.get(key):
                    raise ValueError("Original graph companion is unavailable")
                name = "config.dot" if key == "dot" else "config.dot.pdf"
                source, unused, unused_digest = _verified_artifact(
                    self.loaded[key], self.project, name
                )
                if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(source))):
                    raise ValueError("No local viewer accepted this file")
            except (OSError, ValueError) as error:
                self.status.setText("Could not open original graph · " + str(error))

    _PANEL_CLASS = TopologyPanel
    return _PANEL_CLASS


def __getattr__(name):
    if name == "TopologyPanel":
        return _panel_class()
    raise AttributeError(name)
