"""
Add Parameter Dialog for adding custom assay parameters.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class AddParameterDialog(QDialog):
    """Dialog for adding a custom parameter to an assay."""

    def __init__(self, parent=None, existing_params=None):
        super().__init__(parent)
        self.existing_params = existing_params or []
        self.setWindowTitle("Add Parameter")
        self.setMinimumWidth(400)
        self.setup_ui()

    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Parameter name (e.g., temperature)")
        form.addRow("Parameter Name:", self.name_edit)

        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText("Description (optional)")
        form.addRow("Description:", self.description_edit)

        self.unit_edit = QLineEdit()
        self.unit_edit.setPlaceholderText("Unit (e.g., °C, minutes)")
        form.addRow("Unit:", self.unit_edit)

        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("Default value (optional)")
        form.addRow("Default Value:", self.value_edit)

        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        add_btn = QPushButton("Add Parameter")
        add_btn.clicked.connect(self._on_add)
        btn_layout.addWidget(add_btn)

        layout.addLayout(btn_layout)

    def _on_add(self):
        """Handle add button click."""
        name = self.name_edit.text().strip()

        if not name:
            QMessageBox.warning(self, "Validation Error", "Parameter name is required.")
            self.name_edit.setFocus()
            return

        # Check for duplicate names
        if name in self.existing_params:
            QMessageBox.warning(
                self, "Duplicate Parameter", f"A parameter with the name '{name}' already exists."
            )
            self.name_edit.setFocus()
            return

        self.accept()

    def get_parameter_data(self) -> dict:
        """Get the parameter data from the dialog."""
        return {
            "name": self.name_edit.text().strip(),
            "description": self.description_edit.text().strip(),
            "unit": self.unit_edit.text().strip(),
            "value": self.value_edit.text().strip(),
        }
