# ==============================================================================
# connection_dialog.py - Live Simulation Connection Dialog
# ==============================================================================
"""Connection Dialog for Real-Time Simulation Monitoring.

This module provides the ConnectionDialog for establishing ZeroMQ
connections to running gem5-SALAM simulations, enabling live monitoring
of simulation progress and statistics.

Dialog Layout::

    +------------------------------------------+
    | Connect to Live Simulation               |
    +------------------------------------------+
    | Connection Settings                       |
    | +--------------------------------------+ |
    | | Protocol: [tcp v]                    | |
    | | Host:     [localhost         ]       | |
    | | Port:     [5555]                     | |
    | | Preset:   [Local (tcp://localhost:5555) v] |
    | +--------------------------------------+ |
    +------------------------------------------+
    | Status                                    |
    | +--------------------------------------+ |
    | |        Connecting to tcp://...       | |
    | |        [==============         ]     | |
    | +--------------------------------------+ |
    +------------------------------------------+
    | [Connect]  [Disconnect]  [Cancel]        |
    +------------------------------------------+
    | Start your gem5-SALAM simulation with    |
    | the --zmq-publish flag to enable live    |
    | monitoring.                              |
    +------------------------------------------+

Connection Presets:
    | Preset              | Address                   |
    |---------------------|---------------------------|
    | Local TCP           | tcp://localhost:5555      |
    | Local IPC           | ipc:///tmp/gem5-salam.sock|
    | Custom              | User-specified            |

Classes:
    - ConnectionDialog: Modal dialog for connection setup
    - ConnectionStatusWidget: Status bar indicator widget

Signals:
    - connection_established(SimulationConnection): When connected
    - clicked(): When status widget is clicked

Connection Workflow:
    1. User opens dialog (from menu or status widget click)
    2. Select preset or enter custom address
    3. Click Connect
    4. Progress shown while attempting connection
    5. On success: dialog closes, returns connection
    6. On failure/timeout: error message shown

Example:
    Showing the connection dialog::

        from salam_gui.dialogs.connection_dialog import ConnectionDialog

        def show_connection_dialog(self):
            dialog = ConnectionDialog(self)
            dialog.connection_established.connect(self.on_connection)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                conn = dialog.get_connection()
                # Start receiving live updates
                conn.queue_state_updated.connect(self.update_queues)

Status Widget Usage::

    # Add to status bar
    status_widget = ConnectionStatusWidget()
    status_widget.clicked.connect(show_connection_dialog)
    statusBar().addPermanentWidget(status_widget)

    # Update based on connection state
    status_widget.set_connected("localhost:5555")
    status_widget.set_disconnected()
    status_widget.set_connecting()

See Also:
    - realtime_connection: ZeroMQ connection implementation
    - main_window: Hosts the status widget
    - queue_monitor: Uses live connection data
"""


__version__ = "3.0.0.pre[1.0.0]"

from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QGroupBox, QProgressBar, QMessageBox, QSpinBox
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont

from ..data.realtime_connection import SimulationConnection, ConnectionState


class ConnectionDialog(QDialog):
    """Dialog for establishing connection to a running simulation."""

    connection_established = Signal(object)  # Emits SimulationConnection

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to Simulation")
        self.setMinimumWidth(400)
        self.setModal(True)

        self.connection: Optional[SimulationConnection] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Connect to Live Simulation")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Connection settings group
        settings_group = QGroupBox("Connection Settings")
        settings_layout = QFormLayout(settings_group)

        # Protocol selector
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["tcp", "ipc"])
        settings_layout.addRow("Protocol:", self.protocol_combo)

        # Host
        self.host_edit = QLineEdit("localhost")
        settings_layout.addRow("Host:", self.host_edit)

        # Port
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(5555)
        settings_layout.addRow("Port:", self.port_spin)

        # Quick connect presets
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Custom", None)
        self.preset_combo.addItem("Local (tcp://localhost:5555)", "tcp://localhost:5555")
        self.preset_combo.addItem("Local IPC (/tmp/gem5-salam.sock)", "ipc:///tmp/gem5-salam.sock")
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        settings_layout.addRow("Preset:", self.preset_combo)

        layout.addWidget(settings_group)

        # Connection status
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)

        self.status_label = QLabel("Not connected")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.hide()
        status_layout.addWidget(self.progress_bar)

        layout.addWidget(status_group)

        # Buttons
        button_layout = QHBoxLayout()

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        button_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self._on_disconnect_clicked)
        self.disconnect_btn.setEnabled(False)
        button_layout.addWidget(self.disconnect_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

        # Help text
        help_text = QLabel(
            "<i>Start your gem5-SALAM simulation with the --zmq-publish flag "
            "to enable live monitoring.</i>"
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(help_text)

    def _on_preset_changed(self, index: int):
        """Handle preset selection."""
        address = self.preset_combo.currentData()
        if address:
            # Parse the address and update fields
            if address.startswith("tcp://"):
                self.protocol_combo.setCurrentText("tcp")
                parts = address[6:].split(":")
                self.host_edit.setText(parts[0])
                if len(parts) > 1:
                    self.port_spin.setValue(int(parts[1]))
            elif address.startswith("ipc://"):
                self.protocol_combo.setCurrentText("ipc")
                self.host_edit.setText(address[6:])

    def _get_address(self) -> str:
        """Build address from current settings."""
        protocol = self.protocol_combo.currentText()
        if protocol == "tcp":
            return f"tcp://{self.host_edit.text()}:{self.port_spin.value()}"
        else:
            return f"ipc://{self.host_edit.text()}"

    def _on_connect_clicked(self):
        """Handle connect button click."""
        address = self._get_address()

        # Create connection
        self.connection = SimulationConnection(self)

        # Connect signals
        self.connection.connected.connect(self._on_connected)
        self.connection.disconnected.connect(self._on_disconnected)
        self.connection.connection_error.connect(self._on_error)

        # Update UI
        self.status_label.setText(f"Connecting to {address}...")
        self.progress_bar.show()
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)

        # Start connection
        self.connection.connect(address)

        # Set timeout for connection attempt
        QTimer.singleShot(10000, self._check_connection_timeout)

    def _on_disconnect_clicked(self):
        """Handle disconnect button click."""
        if self.connection:
            self.connection.disconnect()

    def _on_connected(self):
        """Handle successful connection."""
        self.progress_bar.hide()
        self.status_label.setText("Connected!")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

        # Emit signal and close
        self.connection_established.emit(self.connection)
        self.accept()

    def _on_disconnected(self):
        """Handle disconnection."""
        self.progress_bar.hide()
        self.status_label.setText("Disconnected")
        self.status_label.setStyleSheet("")
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)

    def _on_error(self, error_msg: str):
        """Handle connection error."""
        self.progress_bar.hide()
        self.status_label.setText(f"Error: {error_msg}")
        self.status_label.setStyleSheet("color: red;")
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)

    def _check_connection_timeout(self):
        """Check if connection has timed out."""
        if self.connection and self.connection.state == ConnectionState.CONNECTING:
            self.connection.disconnect()
            self._on_error("Connection timed out")

    def get_connection(self) -> Optional[SimulationConnection]:
        """Get the established connection (after dialog accepted)."""
        return self.connection


class ConnectionStatusWidget(QLabel):
    """Small widget showing connection status for use in status bar."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QLabel {
                padding: 2px 8px;
                border-radius: 3px;
            }
        """)
        self.set_disconnected()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_disconnected(self):
        """Show disconnected state."""
        self.setText("Offline")
        self.setStyleSheet("""
            QLabel {
                padding: 2px 8px;
                border-radius: 3px;
                background: #ffcccc;
                color: #cc0000;
            }
        """)

    def set_connecting(self):
        """Show connecting state."""
        self.setText("Connecting...")
        self.setStyleSheet("""
            QLabel {
                padding: 2px 8px;
                border-radius: 3px;
                background: #ffffcc;
                color: #cc9900;
            }
        """)

    def set_connected(self, address: str = ""):
        """Show connected state."""
        text = "Live" if not address else f"Live: {address}"
        self.setText(text)
        self.setStyleSheet("""
            QLabel {
                padding: 2px 8px;
                border-radius: 3px;
                background: #ccffcc;
                color: #009900;
            }
        """)

    def mousePressEvent(self, event):
        """Handle click to open connection dialog."""
        self.clicked.emit()
        super().mousePressEvent(event)
