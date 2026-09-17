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


class ParameterDialog(QDialog):
    """Dialog for editing protocol parameters."""

    def __init__(self, parent=None, protocol_name="", parameters=None):
        super().__init__(parent)
        self.protocol_name = protocol_name
        self.parameters = parameters or []
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
        for param in self.parameters:
            name = param.get("annotationValue", param.get("name", "Unknown"))
            entry = QLineEdit()
            entry.setPlaceholderText("Enter value...")
            self.form.addRow(f"{name}:", entry)
            self.param_entries[name] = entry

        scroll.setWidget(form_widget)
        layout.addWidget(scroll)

        # Buttons
        btn_layout = QHBoxLayout()  # type: ignore
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def get_parameter_values(self) -> dict:
        """Get the parameter values from the dialog."""
        values = {}
        for name, entry in self.param_entries.items():
            values[name] = entry.text()
        return values
