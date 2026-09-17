"""
PathPicker widget for ISA-JSON Data Steward GUI.

A line edit with a browse button for selecting directories.
"""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget


class PathPicker(QWidget):
    """A line edit with a browse button for selecting directories."""

    pathChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._is_valid = True
        self._must_exist = False

        # Create widgets
        self._line_edit = QLineEdit()
        self._line_edit.setPlaceholderText("Select a directory...")
        self._line_edit.textChanged.connect(self._on_text_changed)

        self._browse_button = QPushButton("Browse...")
        self._browse_button.setFixedWidth(80)
        self._browse_button.clicked.connect(self._on_browse_clicked)

        # Set up layout
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self._line_edit)
        layout.addWidget(self._browse_button)
        self.setLayout(layout)

    def _on_text_changed(self, text: str):
        """Handle text change in line edit."""
        self._validate_path(text)
        self.pathChanged.emit(text)

    def _on_browse_clicked(self):
        """Handle browse button click."""
        current_path = self._line_edit.text() or "."
        path = QFileDialog.getExistingDirectory(self, "Select Directory", current_path)
        if path:
            self._line_edit.setText(path)

    def _validate_path(self, path: str):
        """Validate the path."""
        if not path:
            self._set_valid(True)
            return

        path_obj = Path(path)

        if self._must_exist:
            self._set_valid(path_obj.exists())
        else:
            # Check if path is valid (no invalid characters)
            try:
                path_obj.resolve()
                self._set_valid(True)
            except (OSError, RuntimeError):
                self._set_valid(False)

    def _set_valid(self, valid: bool):
        """Set the valid state of the widget."""
        self._is_valid = valid

        if valid:
            self._line_edit.setStyleSheet("")
        else:
            self._line_edit.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #ff6b6b;
                    background-color: #fff5f5;
                }
            """)

    def path(self) -> str:
        """Get the current path."""
        return str(self._line_edit.text())

    def set_path(self, path: str):
        """Set the current path."""
        self._line_edit.setText(path)

    def set_must_exist(self, must_exist: bool):
        """Set whether the path must exist."""
        self._must_exist = must_exist
        self._validate_path(self._line_edit.text())

    def is_valid(self) -> bool:
        """Check if the current path is valid."""
        return bool(self._is_valid)

    def set_placeholder_text(self, text: str):
        """Set the placeholder text."""
        self._line_edit.setPlaceholderText(text)

    def set_read_only(self, read_only: bool):
        """Set whether the path picker is read-only."""
        self._line_edit.setReadOnly(read_only)
        self._browse_button.setEnabled(not read_only)
