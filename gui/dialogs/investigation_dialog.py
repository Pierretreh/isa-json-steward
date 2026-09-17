"""
Investigation Dialog for creating new investigations.
"""

from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class InvestigationDialog(QDialog):
    """Dialog for creating a new investigation."""

    def __init__(self, parent=None, dm=None):
        super().__init__(parent)
        self.dm = dm
        self.setWindowTitle("Create New Investigation")
        self.setMinimumWidth(550)
        self.setup_ui()

    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Header info
        info_label = QLabel(
            "An investigation is the top-level container in ISA-JSON. "
            "It groups related studies under a single research project."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; margin-bottom: 8px;")
        layout.addWidget(info_label)

        # Investigation details group
        details_group = QGroupBox("Investigation Details")
        form = QFormLayout(details_group)

        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("e.g., inv_my_project (letters, numbers, underscores)")
        form.addRow("Investigation ID:", self.id_edit)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("e.g., Protein Expression Study 2024")
        form.addRow("Title:", self.title_edit)

        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("Brief description of the investigation...")
        self.description_edit.setMaximumHeight(100)
        form.addRow("Description:", self.description_edit)

        layout.addWidget(details_group)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        create_btn = QPushButton("Create Investigation")
        create_btn.setDefault(True)
        create_btn.clicked.connect(self._on_create)
        btn_layout.addWidget(create_btn)

        layout.addLayout(btn_layout)

    def validate(self) -> tuple[bool, list[str]]:
        """Validate the form data.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        inv_id = self.id_edit.text().strip()
        if not inv_id:
            errors.append("Investigation ID is required")
        elif not inv_id.replace("_", "").replace("-", "").isalnum():
            errors.append(
                "Investigation ID can only contain letters, numbers, hyphens, and underscores"
            )
        elif inv_id.startswith("_") or inv_id.startswith("-"):
            errors.append("Investigation ID must start with a letter or number")

        if not self.title_edit.text().strip():
            errors.append("Title is required")

        # Check if investigation already exists
        if self.dm and inv_id:
            existing = self.dm.list_investigations()
            if inv_id in existing:
                errors.append(f"Investigation '{inv_id}' already exists")

        return len(errors) == 0, errors

    def _on_create(self):
        """Handle create button click with validation."""
        is_valid, errors = self.validate()

        if not is_valid:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please correct the following errors:\n\n" + "\n".join(f"• {e}" for e in errors),
            )
            return

        self.accept()

    def get_investigation_data(self) -> dict:
        """Get the investigation data from the form.

        Returns:
            Dictionary with investigation metadata.
        """
        return {
            "investigation_id": self.id_edit.text().strip(),
            "title": self.title_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip(),
            "created_at": datetime.now().isoformat(),
        }
