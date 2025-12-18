# ==============================================================================
# dialogs/__init__.py - Dialog Components Package
# ==============================================================================
"""Dialog Components for gem5-SALAM GUI.

This subpackage provides modal dialog windows for user interactions
that require focused input or configuration.

Module Structure::

    salam_gui/dialogs/
    +-- __init__.py           # This file (exports)
    +-- connection_dialog.py  # Live connection setup

Available Dialogs:
    - ConnectionDialog: Configure real-time simulation connection
    - ConnectionStatusWidget: Status bar connection indicator

Example:
    Showing dialogs from the main window::

        from salam_gui.dialogs import ConnectionDialog

        dialog = ConnectionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            connection = dialog.get_connection()
"""


__version__ = "3.0.0.pre[1.0.0]"

from .connection_dialog import ConnectionDialog, ConnectionStatusWidget

__all__ = ['ConnectionDialog', 'ConnectionStatusWidget']
