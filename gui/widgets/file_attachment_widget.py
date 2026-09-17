"""
File Attachment Widget for managing file attachments in assays and processes.

Provides type-specific import buttons and file management functionality.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.file_manager import FileManager  # noqa: E402


class FileAttachmentWidget(QWidget):
    """Widget for managing file attachments with type-specific import buttons."""

    file_attached = pyqtSignal(dict)  # Signal when a file is attached
    file_removed = pyqtSignal(str)  # Signal when a file is removed

    def __init__(
        self,
        parent=None,
        expected_attachments: Optional[List[Dict[str, Any]]] = None,
        attached_files: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Initialize the file attachment widget.

        Args:
            parent: Parent widget
            expected_attachments: List of expected attachment specifications from template
            attached_files: List of currently attached file metadata
        """
        super().__init__(parent)
        self.expected_attachments: List[Dict[str, Any]] = expected_attachments or []
        self.attached_files: List[Dict[str, Any]] = attached_files or []
        self.file_manager = FileManager()

        self.setup_ui()

    def setup_ui(self):
        """Set up the widget UI."""
        # Reuse existing layout if it exists, otherwise create a new one
        layout = self.layout()
        if layout is None:
            layout = QVBoxLayout(self)
        else:
            # Clear the existing layout
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header_label = QLabel("File Attachments")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header_label)

        # Scroll area for attachment sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        # Create attachment sections for each expected attachment type
        self.attachment_sections = {}

        for attachment_spec in self.expected_attachments:
            section = self._create_attachment_section(attachment_spec)
            self.attachment_sections[attachment_spec["name"]] = section
            scroll_layout.addWidget(section)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Summary label
        self.summary_label = QLabel("No files attached")
        self.summary_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.summary_label)

    def _create_attachment_section(self, attachment_spec: dict) -> QGroupBox:
        """
        Create a section widget for an attachment type.

        Args:
            attachment_spec: Attachment specification from template

        Returns:
            GroupBox widget for the attachment section
        """
        name = attachment_spec["name"]
        description = attachment_spec.get("description", "")
        required = attachment_spec.get("required", False)
        file_type = attachment_spec.get("fileType", "data")
        _multiple = attachment_spec.get("multiple", False)  # noqa: F841

        # Create group box
        group = QGroupBox(name)
        group.setStyleSheet("""
            QGroupBox {
                font-weight: 600;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)

        layout = QVBoxLayout(group)

        # Description
        if description:
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #666; font-size: 11px;")
            layout.addWidget(desc_label)

        # Required indicator
        if required:
            required_label = QLabel("* Required")
            required_label.setStyleSheet("color: #d32f2f; font-weight: bold;")
            layout.addWidget(required_label)

        # File type icon and label
        type_layout = QHBoxLayout()
        type_icon = self._get_file_type_icon(file_type)
        type_label = QLabel(f"Type: {file_type.capitalize()}")
        type_label.setStyleSheet("color: #666;")
        type_layout.addWidget(type_icon)
        type_layout.addWidget(type_label)
        type_layout.addStretch()
        layout.addLayout(type_layout)

        # Import button (type-specific)
        import_btn = self._create_import_button(attachment_spec)
        import_btn.clicked.connect(lambda: self._on_import_file(attachment_spec))
        layout.addWidget(import_btn)

        # Attached files list
        files_container = QWidget()
        files_layout = QVBoxLayout(files_container)
        files_layout.setContentsMargins(0, 0, 0, 0)

        # Add existing files for this attachment type
        self._update_attached_files_list(files_layout, attachment_spec)

        layout.addWidget(files_container)

        return group

    def _create_import_button(self, attachment_spec: dict) -> QPushButton:
        """
        Create a type-specific import button.

        Args:
            attachment_spec: Attachment specification from template

        Returns:
            QPushButton with type-specific text and icon
        """
        name = attachment_spec["name"]
        file_type = attachment_spec.get("fileType", "data")

        # Create button with type-specific text
        if file_type == "image":
            button_text = f"Import {name}"
        elif file_type == "data":
            button_text = f"Import {name}"
        elif file_type == "sequencing":
            button_text = f"Import {name}"
        elif file_type == "report":
            button_text = f"Attach {name}"
        else:
            button_text = f"Import {name}"

        button = QPushButton(button_text)
        button.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:pressed {
                background-color: #2a5f8f;
            }
        """)

        return button

    def _get_file_type_icon(self, file_type: str) -> QLabel:
        """
        Get an icon label for a file type.

        Args:
            file_type: File type string

        Returns:
            QLabel with icon
        """
        icon_label = QLabel()
        icon_label.setFixedSize(24, 24)

        # Simple text-based icons (could be replaced with actual icons)
        icons = {"image": "📷", "data": "📊", "sequencing": "🧬", "report": "📄"}

        icon_label.setText(icons.get(file_type, "📁"))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 18px;")

        return icon_label

    def _update_attached_files_list(self, layout: QVBoxLayout, attachment_spec: dict):
        """
        Update the list of attached files for an attachment type.

        Args:
            layout: Layout to add file widgets to
            attachment_spec: Attachment specification
        """
        if layout is None:
            return

        # Clear existing widgets
        while layout.count():
            child = layout.takeAt(0)
            if child is not None:
                widget = child.widget()
                if widget is not None:
                    widget.deleteLater()

        # Add attached files
        name = attachment_spec["name"]
        for file_meta in self.attached_files:
            if file_meta.get("attachment_type") == name:
                file_widget = self._create_file_widget(file_meta)
                layout.addWidget(file_widget)

        if layout.count() == 0:
            empty_label = QLabel("No files attached")
            empty_label.setStyleSheet("color: #999; font-style: italic; padding: 10px;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty_label)

    def _create_file_widget(self, file_meta: dict) -> QWidget:
        """
        Create a widget for displaying an attached file.

        Args:
            file_meta: File metadata dictionary

        Returns:
            QWidget with file information and remove button
        """
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
            }
        """)

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 4, 8, 4)

        # File type icon
        file_type = file_meta.get("file_type", "data")
        icon_label = self._get_file_type_icon(file_type)
        layout.addWidget(icon_label)

        # File info
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(8, 0, 0, 0)

        name_label = QLabel(file_meta.get("original_filename", "Unknown"))
        name_label.setStyleSheet("font-weight: 500;")
        info_layout.addWidget(name_label)

        # Conversion status
        conversion_status = file_meta.get("conversion_status", "unknown")
        status_text = ""
        status_color = "#666"

        if conversion_status == "completed":
            status_text = f"✓ Converted to {file_meta.get('converted_format', '')}"
            status_color = "#28a745"
        elif conversion_status == "failed":
            status_text = "✗ Conversion failed"
            status_color = "#dc3545"
        elif conversion_status == "not_needed":
            status_text = "No conversion needed"
            status_color = "#6c757d"

        if status_text:
            status_label = QLabel(status_text)
            status_label.setStyleSheet(f"color: {status_color}; font-size: 11px;")
            info_layout.addWidget(status_label)

        layout.addLayout(info_layout)
        layout.addStretch()

        # Remove button
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 12px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        remove_btn.clicked.connect(lambda: self._on_remove_file(file_meta))
        layout.addWidget(remove_btn)

        return widget

    def _on_import_file(self, attachment_spec: dict):
        """
        Handle file import for an attachment type.

        Args:
            attachment_spec: Attachment specification
        """
        name = attachment_spec["name"]
        file_type = attachment_spec.get("fileType", "data")
        allowed_extensions = attachment_spec.get("allowedExtensions", [])
        multiple = attachment_spec.get("multiple", False)

        # Build file filter dynamically from template's allowedExtensions
        if allowed_extensions:
            # Create filter from template's allowedExtensions
            ext_list = " ".join(f"*{ext}" for ext in allowed_extensions)
            filter_text = f"{name.capitalize()} Files ({ext_list});;All Files (*)"
        else:
            # No restrictions - allow all files
            filter_text = "All Files (*)"

        # Open file dialog
        if multiple:
            file_paths, _ = QFileDialog.getOpenFileNames(self, f"Import {name}", "", filter_text)
        else:
            file_path, _ = QFileDialog.getOpenFileName(self, f"Import {name}", "", filter_text)
            file_paths = [file_path] if file_path else []

        # Process selected files
        for file_path in file_paths:
            path = Path(file_path)

            # Validate file type
            is_valid, error_msg = self.file_manager.validate_file_attachment(path, attachment_spec)

            if not is_valid:
                QMessageBox.warning(
                    self, "Invalid File", f"Cannot import '{path.name}':\n{error_msg}"
                )
                continue

            # Create file metadata (will be processed by parent)
            file_meta = {
                "file_path": str(path),
                "attachment_type": name,
                "attachment_name": attachment_spec.get("name", name),
                "file_type": file_type,
                "original_filename": path.name,
                "file_size_bytes": path.stat().st_size,
            }

            # Emit signal for parent to handle
            self.file_attached.emit(file_meta)

    def _on_remove_file(self, file_meta: dict):
        """
        Handle file removal.

        Args:
            file_meta: File metadata dictionary
        """
        reply = QMessageBox.question(
            self,
            "Remove File",
            f"Are you sure you want to remove '{file_meta['original_filename']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.file_removed.emit(file_meta.get("file_id", ""))

    def add_attached_file(self, file_meta: dict):
        """
        Add an attached file to the widget.

        Args:
            file_meta: File metadata dictionary
        """
        self.attached_files.append(file_meta)

        # Update the appropriate section
        attachment_type = file_meta.get("attachment_type")
        if attachment_type in self.attachment_sections:
            section = self.attachment_sections[attachment_type]
            # Find the files layout in the section
            layout = section.layout()
            files_layout = None
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    # The files container is a QWidget (not a QLabel, QPushButton, etc.)
                    # and should have a layout
                    if widget.layout() is not None:
                        files_layout = widget.layout()
                        break

            if files_layout is not None:
                self._update_attached_files_list(files_layout, {"name": attachment_type})
                # Force UI update
                files_layout.activate()
                files_layout.update()

        self._update_summary()
        # Force widget update and repaint
        self.update()
        self.repaint()

    def remove_attached_file(self, file_id: str):
        """
        Remove an attached file from the widget.

        Args:
            file_id: File ID to remove
        """
        self.attached_files = [f for f in self.attached_files if f.get("file_id") != file_id]

        # Update all sections
        for attachment_spec in self.expected_attachments:
            if attachment_spec["name"] in self.attachment_sections:
                section = self.attachment_sections[attachment_spec["name"]]
                layout = section.layout()
                files_layout = None
                for i in range(layout.count()):
                    item = layout.itemAt(i)
                    if item and item.widget():
                        widget = item.widget()
                        if widget.layout() is not None:
                            files_layout = widget.layout()
                            break

                if files_layout is not None:
                    self._update_attached_files_list(files_layout, attachment_spec)

        self._update_summary()

    def _update_summary(self):
        """Update the summary label."""
        count = len(self.attached_files)
        if count == 0:
            self.summary_label.setText("No files attached")
        elif count == 1:
            self.summary_label.setText("1 file attached")
        else:
            self.summary_label.setText(f"{count} files attached")

    def get_attached_files(self) -> list:
        """
        Get list of attached files.

        Returns:
            List of file metadata dictionaries
        """
        return self.attached_files.copy()

    def set_expected_attachments(self, expected_attachments: list):
        """
        Set the expected attachments and rebuild the UI.

        Args:
            expected_attachments: List of expected attachment specifications
        """
        self.expected_attachments = expected_attachments

        # Clear and rebuild
        layout = self.layout()
        if layout is not None:
            while layout.count():
                child = layout.takeAt(0)
                if child is not None:
                    widget = child.widget()
                    if widget is not None:
                        widget.deleteLater()

        self.setup_ui()

    def set_attached_files(self, attached_files: list):
        """
        Set the attached files and update the UI.

        Args:
            attached_files: List of file metadata dictionaries
        """
        self.attached_files = attached_files.copy()

        # Update all sections
        for attachment_spec in self.expected_attachments:
            if attachment_spec["name"] in self.attachment_sections:
                section = self.attachment_sections[attachment_spec["name"]]
                layout = section.layout()
                files_layout = None
                for i in range(layout.count()):
                    item = layout.itemAt(i)
                    if item and item.widget():
                        widget = item.widget()
                        if widget.layout() is not None:
                            files_layout = widget.layout()
                            break

                if files_layout is not None:
                    self._update_attached_files_list(files_layout, attachment_spec)

        self._update_summary()
