"""
Parameter Dialog for editing protocol parameters.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..agent_tools.ids import set_test_id


class ParameterDialog(QDialog):
    """Dialog for editing protocol parameters."""

    def __init__(self, parent=None, protocol_name="", parameters=None):
        super().__init__(parent)
        self.protocol_name = protocol_name
        self.parameters = parameters or []
        set_test_id(self, "dialog.parameter", accessible_name="Protocol Parameters dialog")
        self.setWindowTitle(f"Parameters: {protocol_name}")
        self.setMinimumSize(600, 400)
        self.setup_ui()

    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Description
        desc_label = QLabel(f"Protocol: {self.protocol_name}")
        desc_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(desc_label)

        # Parameters form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        form_widget = QWidget()
        self.form = QFormLayout(form_widget)

        self.param_entries = {}
        for index, param in enumerate(self.parameters):
            name = param.get("annotationValue", param.get("name", "Unknown"))
            entry = QLineEdit()
            set_test_id(
                entry,
                f"dialog.parameter.valueField_{index}",
                accessible_name=f"{name} value",
            )
            entry.setAccessibleDescription(f"Value for the {name} parameter")
            entry.setPlaceholderText("Enter value...")
            self.form.addRow(f"{name}:", entry)
            self.param_entries[name] = entry

        scroll.setWidget(form_widget)
        layout.addWidget(scroll)

        # Buttons
        btn_layout = QHBoxLayout()  # type: ignore
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        set_test_id(cancel_btn, "dialog.parameter.cancelButton", accessible_name="Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        set_test_id(save_btn, "dialog.parameter.saveButton", accessible_name="Save parameters")
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def get_parameter_values(self) -> dict:
        """Get the parameter values from the dialog."""
        values = {}
        for name, entry in self.param_entries.items():
            values[name] = entry.text()
        return values
