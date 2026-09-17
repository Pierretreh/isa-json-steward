"""
Template Editor dialog for creating/editing templates.
"""

import json

# Import utilities
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.constants import TemplateConstants  # noqa: E402


class TemplateEditorDialog(QDialog):
    """Dialog for editing assay and protocol templates."""

    # Use constants from centralized location
    NUMERIC_UNITS = TemplateConstants.NUMERIC_UNITS

    def __init__(
        self,
        parent=None,
        template_type="assay",
        template_data: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(parent)
        self.template_type = template_type
        self.template_data: Dict[str, Any] = template_data or {}
        self.setWindowTitle(f"Edit {template_type.capitalize()} Template")
        self.setMinimumSize(900, 700)
        self.setup_ui()

    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Tab widget for different editing modes
        self.tabs = QTabWidget()

        # Basic Info tab
        self.basic_tab = QWidget()
        self._setup_basic_tab()
        self.tabs.addTab(self.basic_tab, "Basic Info")

        # Parameters tab (for assay templates)
        if self.template_type == "assay":
            self.params_tab = QWidget()
            self._setup_parameters_tab()
            self.tabs.addTab(self.params_tab, "Parameters")

        # JSON Editor tab
        self.json_tab = QWidget()
        self._setup_json_tab()
        self.tabs.addTab(self.json_tab, "JSON Editor")

        # Connect tab changes to sync
        self.tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self.tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

        # Initial validation and load
        self._validate_json()
        if self.template_type == "assay":
            self._load_parameters()

    def _setup_basic_tab(self):
        """Set up the basic info tab."""
        layout = QVBoxLayout(self.basic_tab)

        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setText(self.template_data.get("name", ""))
        self.name_edit.setPlaceholderText("Template name")
        form.addRow("Name:", self.name_edit)

        self.desc_edit = QTextEdit()
        self.desc_edit.setPlainText(self.template_data.get("description", ""))
        self.desc_edit.setPlaceholderText("Template description...")
        self.desc_edit.setMaximumHeight(80)
        form.addRow("Description:", self.desc_edit)

        layout.addLayout(form)
        layout.addStretch()

    def _setup_json_tab(self):
        """Set up the JSON editor tab."""
        layout = QVBoxLayout(self.json_tab)

        # JSON editor label
        json_label = QLabel("Template JSON:")
        json_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(json_label)

        # JSON editor
        self.json_edit = QTextEdit()
        self.json_edit.setPlainText(json.dumps(self.template_data, indent=2))
        self.json_edit.setPlaceholderText("Enter JSON data...")
        self.json_edit.setFont(QFont("Courier New", 10))
        layout.addWidget(self.json_edit)

        # Validation status
        self.validation_label = QLabel()
        self.validation_label.setStyleSheet("color: #7f8c8d; padding: 4px;")
        layout.addWidget(self.validation_label)

        # Format button
        format_btn = QPushButton("Format JSON")
        format_btn.clicked.connect(self._format_json)
        layout.addWidget(format_btn)

        # Connect text change to validation
        self.json_edit.textChanged.connect(self._validate_json)

    def _setup_parameters_tab(self):
        """Set up the parameters editing tab."""
        layout = QVBoxLayout(self.params_tab)

        # Header with add button
        header_layout = QHBoxLayout()

        params_label = QLabel("Parameters:")
        params_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(params_label)

        header_layout.addStretch()

        add_param_btn = QPushButton("+ Add Parameter")
        add_param_btn.clicked.connect(self._on_add_parameter)
        header_layout.addWidget(add_param_btn)

        layout.addLayout(header_layout)

        # Parameters table
        self.params_table = QTableWidget()
        self.params_table.setColumnCount(5)
        self.params_table.setHorizontalHeaderLabels(
            ["Parameter Name", "Description", "Unit", "Default Value", "Actions"]
        )
        self.params_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self.params_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Interactive
        )
        self.params_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Interactive
        )
        self.params_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Interactive
        )
        self.params_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Interactive
        )
        self.params_table.setColumnWidth(0, 200)
        self.params_table.setColumnWidth(1, 250)
        self.params_table.setColumnWidth(2, 100)
        self.params_table.setColumnWidth(3, 120)
        self.params_table.setColumnWidth(4, 80)
        self.params_table.setAlternatingRowColors(True)
        self.params_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.params_table)

        # Note
        note_label = QLabel(
            "Note: Default values are used when creating new assays from this template. "
            "You can override these values when creating individual assays."
        )
        note_label.setStyleSheet("color: #7f8c8d; padding: 8px; font-style: italic;")
        note_label.setWordWrap(True)
        layout.addWidget(note_label)

    def _load_parameters(self):
        """Load parameters from template data into the table."""
        self.params_table.setRowCount(0)

        parameters = self.template_data.get("parameters", [])
        if not parameters:
            return

        for param in parameters:
            self._add_parameter_row(param)

    def _add_parameter_row(self, param_data=None):
        """Add a parameter row to the table."""
        if param_data is None:
            param_data = {"name": "", "description": "", "unit": {}, "defaultValue": ""}

        row = self.params_table.rowCount()
        self.params_table.insertRow(row)

        # Name
        name_item = QTableWidgetItem(param_data.get("name", ""))
        name_item.setFlags(name_item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.params_table.setItem(row, 0, name_item)

        # Description
        desc_item = QTableWidgetItem(param_data.get("description", ""))
        desc_item.setFlags(desc_item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.params_table.setItem(row, 1, desc_item)

        # Unit (dropdown)
        unit_combo = QComboBox()
        unit_combo.setEditable(True)
        unit_combo.addItem("")  # Empty option
        for unit in sorted(self.NUMERIC_UNITS):
            unit_combo.addItem(unit)

        unit_info = param_data.get("unit", {})
        unit_value = unit_info.get("annotationValue", "")
        unit_combo.setCurrentText(unit_value)

        self.params_table.setCellWidget(row, 2, unit_combo)

        # Default Value (based on unit type)
        unit = unit_value.lower()
        widget = self._create_value_widget(unit, param_data.get("defaultValue", ""))
        self.params_table.setCellWidget(row, 3, widget)

        # Remove button
        remove_btn = QToolButton()
        remove_btn.setText("×")
        remove_btn.setToolTip("Remove parameter")
        remove_btn.clicked.connect(lambda checked, r=row: self._on_remove_parameter(r))
        self.params_table.setCellWidget(row, 4, remove_btn)

    def _create_value_widget(self, unit: str, value: str) -> QWidget:
        """Create appropriate widget for default value based on unit type."""
        # Determine type based on unit
        if any(u in unit for u in ["percent", "pixel", "cells"]):
            # Integer type
            spin = QSpinBox()
            spin.setRange(-999999, 999999)
            spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            try:
                spin.setValue(int(float(value)))
            except (ValueError, TypeError):
                pass
            return spin
        if unit and any(u in unit for u in self.NUMERIC_UNITS):
            # Float type
            dspin = QDoubleSpinBox()
            dspin.setRange(-999999.0, 999999.0)
            dspin.setDecimals(2)
            dspin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            try:
                dspin.setValue(float(value))
            except (ValueError, TypeError):
                pass
            return dspin
        # Text type
        line = QLineEdit()
        line.setText(value)
        return line

    def _get_value_from_widget(self, widget):
        """Get value from widget based on its type."""
        if isinstance(widget, QSpinBox):
            return str(widget.value())
        elif isinstance(widget, QDoubleSpinBox):
            return str(widget.value())
        else:
            return widget.text()

    def _on_add_parameter(self):
        """Handle add parameter button click."""
        self._add_parameter_row()

    def _on_remove_parameter(self, row: int):
        """Handle remove parameter button click."""
        self.params_table.removeRow(row)

    def _on_tab_changed(self, index: int):
        """Handle tab change to sync data."""
        # When switching away from Parameters tab, sync to JSON
        if self.template_type == "assay" and index != 1:
            self._sync_parameters_to_json()
        # When switching to Parameters tab, load from JSON
        elif self.template_type == "assay" and index == 1:
            self._load_parameters_from_json()

    def _sync_parameters_to_json(self):
        """Sync parameters from table to JSON editor."""
        parameters = []

        for row in range(self.params_table.rowCount()):
            # Get data from table
            name_item = self.params_table.item(row, 0)
            desc_item = self.params_table.item(row, 1)
            unit_combo = self.params_table.cellWidget(row, 2)
            value_widget = self.params_table.cellWidget(row, 3)

            name = name_item.text().strip()
            if not name:
                continue  # Skip rows without name

            unit_value = unit_combo.currentText().strip()
            unit_info = {"annotationValue": unit_value} if unit_value else {}

            param = {
                "name": name,
                "description": desc_item.text().strip(),
                "unit": unit_info,
                "defaultValue": self._get_value_from_widget(value_widget),
            }

            parameters.append(param)

        # Update template data
        try:
            template_json = json.loads(self.json_edit.toPlainText())
            template_json["parameters"] = parameters
            self.json_edit.setPlainText(json.dumps(template_json, indent=2))
        except json.JSONDecodeError:
            pass  # JSON is invalid, skip sync

    def _load_parameters_from_json(self):
        """Load parameters from JSON editor into table."""
        try:
            json_text = self.json_edit.toPlainText()
            template_json = json.loads(json_text)
            self.template_data = template_json
            self._load_parameters()
        except json.JSONDecodeError:
            pass  # JSON is invalid, skip load

    def _validate_json(self):
        """Validate JSON in editor."""
        json_text = self.json_edit.toPlainText()

        if not json_text.strip():
            self.validation_label.setText("JSON is empty")
            self.validation_label.setStyleSheet("color: #e74c3c; padding: 4px;")
            return False

        try:
            json.loads(json_text)
            self.validation_label.setText("✓ Valid JSON")
            self.validation_label.setStyleSheet("color: #27ae60; padding: 4px;")
            return True
        except json.JSONDecodeError as e:
            self.validation_label.setText(f"✗ JSON Error: {e}")
            self.validation_label.setStyleSheet("color: #e74c3c; padding: 4px;")
            return False

    def _format_json(self):
        """Format the JSON in editor."""
        if self._validate_json():
            try:
                json_text = self.json_edit.toPlainText()
                parsed = json.loads(json_text)
                formatted = json.dumps(parsed, indent=2)
                self.json_edit.setPlainText(formatted)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not format JSON: {e}")

    def _on_save(self):
        """Handle save button click."""
        # Sync parameters if on parameters tab
        if self.template_type == "assay" and self.tabs.currentIndex() == 1:
            self._sync_parameters_to_json()

        if not self._validate_json():
            QMessageBox.warning(self, "Invalid JSON", "Please fix JSON errors before saving.")
            return

        # Validate name
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Template name is required.")
            self.name_edit.setFocus()
            return

        self.accept()

    def get_template_data(self) -> dict:
        """Get the template data from the dialog."""
        try:
            json_text = self.json_edit.toPlainText()
            template_json: Dict[str, Any] = json.loads(json_text)

            # Override with form fields
            template_json["name"] = self.name_edit.text().strip()
            template_json["description"] = self.desc_edit.toPlainText().strip()

            return template_json
        except json.JSONDecodeError:
            # Return original data if JSON is invalid
            return self.template_data
