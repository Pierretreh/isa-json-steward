"""
Assay Dialog for creating/editing assays.
"""

import json

# Import utilities
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..widgets.file_attachment_widget import FileAttachmentWidget
from .add_parameter_dialog import AddParameterDialog
from .material_selection_dialog import MaterialSelectionDialog

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.config_loader import get_profile  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.constants import TemplateConstants  # noqa: E402


class AssayDialog(QDialog):
    """Dialog for creating and editing assays."""

    # Use constants from centralized location
    NUMERIC_UNITS = TemplateConstants.NUMERIC_UNITS
    TEMPLATE_FILE_MAPPING = TemplateConstants.TEMPLATE_FILE_MAPPING

    def __init__(
        self,
        parent=None,
        dm=None,
        assay_data=None,
        parameter_definitions=None,
        expected_attachments=None,
        study_data=None,
    ):
        super().__init__(parent)
        self.dm = dm
        self.assay_data = assay_data or {}
        self.parameter_definitions = parameter_definitions or []
        self.expected_attachments = expected_attachments or []
        self.study_data = study_data or {}
        self.setWindowTitle("Edit Assay")
        self.setMinimumSize(700, 600)

        # Track parameter entries: {name: (widget, param_def)}
        self.param_entries = {}

        # Current view mode: 'form' or 'json'
        self.view_mode = "form"

        # Flag to prevent signal firing during initial setup
        self._initializing = True

        # Track linked materials
        self.linked_materials = []

        self.setup_ui()

    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Tab widget for different sections
        tabs = QTabWidget()

        # Basic info tab
        basic_tab = QWidget()
        basic_layout = QFormLayout(basic_tab)

        self.name_edit = QLineEdit()
        self.name_edit.setText(self.assay_data.get("name", ""))
        self.name_edit.setPlaceholderText("Assay name")
        basic_layout.addRow("Assay Name:", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(
            [
                "SDS-PAGE",
                "Microscopy",
                "Toxicity Test",
                "Assembly Fragment Gel",
                "Digestion Assay",
                "Sequencing Assay",
                "Culture Monitoring",
                "Expression Monitoring",
                "Pellet Weighing",
                "Resuspension Illumination",
                "Supernatant Concentration",
                "TUNEL Staining",
            ]
        )
        assay_type = self.assay_data.get("assay_type", "")
        if assay_type:
            index = self.type_combo.findText(assay_type)
            if index >= 0:
                self.type_combo.setCurrentIndex(index)
        basic_layout.addRow("Assay Type:", self.type_combo)

        # Connect type change signal to handler
        self.type_combo.currentTextChanged.connect(self._on_type_changed)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        if "date" in self.assay_data:
            date_str = self.assay_data["date"]
            if date_str:
                date_obj = QDate.fromString(date_str, Qt.DateFormat.ISODate)
                if date_obj.isValid():
                    self.date_edit.setDate(date_obj)
        basic_layout.addRow("Date:", self.date_edit)

        tabs.addTab(basic_tab, "Basic Info")

        # Description tab
        desc_tab = QWidget()
        desc_layout = QVBoxLayout(desc_tab)

        desc_label = QLabel("Description:")
        desc_layout.addWidget(desc_label)

        self.desc_edit = QTextEdit()
        self.desc_edit.setPlainText(self.assay_data.get("description", ""))
        self.desc_edit.setPlaceholderText("Enter assay description...")
        desc_layout.addWidget(self.desc_edit)

        tabs.addTab(desc_tab, "Description")

        # Parameters tab
        params_tab = QWidget()
        params_layout = QVBoxLayout(params_tab)

        # View toggle and add parameter buttons
        header_layout = QHBoxLayout()

        self.form_view_btn = QPushButton("Form View")
        self.form_view_btn.setCheckable(True)
        self.form_view_btn.setChecked(True)
        self.form_view_btn.clicked.connect(self._show_form_view)
        header_layout.addWidget(self.form_view_btn)

        self.json_view_btn = QPushButton("JSON View")
        self.json_view_btn.setCheckable(True)
        self.json_view_btn.clicked.connect(self._show_json_view)
        header_layout.addWidget(self.json_view_btn)

        header_layout.addStretch()

        add_param_btn = QPushButton("+ Add Parameter")
        add_param_btn.clicked.connect(self._on_add_parameter)
        header_layout.addWidget(add_param_btn)

        params_layout.addLayout(header_layout)

        # Use QStackedWidget for form/JSON view toggle
        self.params_stack = QStackedWidget()

        # Form view container
        self.form_container = QWidget()
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setWidget(self.form_container)

        self.form_layout = QVBoxLayout(self.form_container)
        self.params_form = QFormLayout()
        self.form_layout.addLayout(self.params_form)
        self.form_layout.addStretch()

        self.params_stack.addWidget(form_scroll)

        # JSON view container
        self.json_container = QWidget()
        json_layout = QVBoxLayout(self.json_container)

        json_label = QLabel("Parameters (JSON format):")
        json_layout.addWidget(json_label)

        self.params_edit = QTextEdit()
        self.params_edit.setFont(QFont("Courier New", 10))
        json_layout.addWidget(self.params_edit)

        self.params_stack.addWidget(self.json_container)

        params_layout.addWidget(self.params_stack)

        tabs.addTab(params_tab, "Parameters")

        # Files tab
        files_tab = QWidget()
        files_layout = QVBoxLayout(files_tab)

        # Get attached files from assay data
        attached_files = self.assay_data.get("files", [])

        # Create file attachment widget
        self.file_attachment_widget = FileAttachmentWidget(
            parent=files_tab,
            expected_attachments=self.expected_attachments,
            attached_files=attached_files,
        )

        # Connect file_attached signal to handler
        self.file_attachment_widget.file_attached.connect(self._on_file_attached)
        # Connect file_removed signal to handler
        self.file_attachment_widget.file_removed.connect(
            self.file_attachment_widget.remove_attached_file
        )
        files_layout.addWidget(self.file_attachment_widget)

        tabs.addTab(files_tab, "Files")

        # Materials tab
        materials_tab = QWidget()
        materials_layout = QVBoxLayout(materials_tab)

        # Inputs section with required indicator
        inputs_header_layout = QHBoxLayout()
        inputs_label = QLabel("<b>Input Materials:</b>")
        inputs_header_layout.addWidget(inputs_label)

        # Add required indicator
        self.materials_required_label = QLabel("<span style='color: red;'>*</span> Required")
        self.materials_required_label.setStyleSheet("color: red; font-weight: bold;")
        inputs_header_layout.addWidget(self.materials_required_label)
        inputs_header_layout.addStretch()

        materials_layout.addLayout(inputs_header_layout)

        # Status indicator
        self.materials_status_label = QLabel("<i style='color: orange;'>No materials selected</i>")
        self.materials_status_label.setWordWrap(True)
        materials_layout.addWidget(self.materials_status_label)

        self.inputs_list = QListWidget()
        self.inputs_list.setMaximumHeight(150)
        self.inputs_list.setAlternatingRowColors(True)
        materials_layout.addWidget(self.inputs_list)

        select_inputs_btn = QPushButton("Select Inputs...")
        select_inputs_btn.clicked.connect(self._on_select_inputs)
        materials_layout.addWidget(select_inputs_btn)

        materials_layout.addStretch()

        tabs.addTab(materials_tab, "Materials")

        # Performer tab
        performer_tab = self._setup_performer_tab()
        tabs.addTab(performer_tab, "Performer")

        layout.addWidget(tabs)

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

        # Initialize parameters
        self._initialize_parameters()

        # Load linked materials
        self._load_materials()

        # Clear the initializing flag
        self._initializing = False

    def _initialize_parameters(self):
        """Initialize the parameters form based on definitions or existing data."""
        # Get existing parameter values (could be a dict or a list from template)
        raw_params = self.assay_data.get("parameters", {})

        # Handle case where parameters is a list (from template)
        if isinstance(raw_params, list):
            existing_params = {}
        else:
            existing_params = raw_params

        # If we have parameter definitions from template, use those
        if self.parameter_definitions:
            for param_def in self.parameter_definitions:
                name = param_def.get("name", "")
                if name:
                    # Get default value from parameter definition
                    default_value = param_def.get("defaultValue", "")
                    # Use existing value if available, otherwise use default
                    value = existing_params.get(name, default_value)
                    self._add_parameter_field(name, param_def, value)
        # Otherwise, create fields from existing parameters
        elif existing_params:
            for name, value in existing_params.items():
                # Create a minimal parameter definition
                param_def = {"name": name, "description": "", "unit": {}}
                self._add_parameter_field(name, param_def, value)

        # Update JSON view
        self._update_json_view()

    def _on_file_attached(self, file_meta: dict):
        """
        Handle file attachment signal from file_attachment_widget.

        Args:
            file_meta: File metadata dictionary
        """
        # Add to widget's list (file copying is handled in assays.py)
        self.file_attachment_widget.add_attached_file(file_meta)

    def _get_input_type(self, param_def: dict) -> str:
        """Determine input type based on parameter definition."""
        unit = param_def.get("unit", {}).get("annotationValue", "").lower()
        _name = param_def.get("name", "").lower()  # noqa: F841

        # Numeric types based on unit
        if any(u in unit for u in self.NUMERIC_UNITS):
            # Check for integer vs float based on common patterns
            if any(u in unit for u in ["percent", "pixel", "cells"]):
                return "integer"
            return "float"

        # Text types (default)
        return "text"

    def _add_parameter_field(self, name: str, param_def: dict, value: str = ""):
        """Add a parameter field to the form."""
        description = param_def.get("description", "")
        unit_info = param_def.get("unit", {})
        unit = unit_info.get("annotationValue", "")

        # Create label with unit
        label_text = name
        if unit:
            label_text += f" ({unit})"

        # Create row layout
        row_layout = QHBoxLayout()

        # Create input widget based on type
        input_type = self._get_input_type(param_def)

        widget: Optional[QWidget] = None
        if input_type == "integer":
            spin = QSpinBox()
            spin.setRange(-999999, 999999)
            spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            if value:
                try:
                    spin.setValue(int(float(value)))
                except (ValueError, TypeError):
                    pass
            widget = spin
        elif input_type == "float":
            dspin = QDoubleSpinBox()
            dspin.setRange(-999999.0, 999999.0)
            dspin.setDecimals(2)
            dspin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            if value:
                try:
                    dspin.setValue(float(value))
                except (ValueError, TypeError):
                    pass
            widget = dspin
        else:
            line = QLineEdit()
            line.setText(str(value))
            line.setPlaceholderText("Enter value...")
            widget = line

        if widget is not None:
            widget.setToolTip(description)
            row_layout.addWidget(widget)

        # Remove button
        remove_btn = QToolButton()
        remove_btn.setText("×")
        remove_btn.setToolTip("Remove parameter")
        remove_btn.clicked.connect(lambda: self._remove_parameter(name))
        row_layout.addWidget(remove_btn)

        # Add to form
        self.params_form.addRow(label_text, row_layout)

        # Store entry
        self.param_entries[name] = {"widget": widget, "param_def": param_def}

    def _remove_parameter(self, name: str):
        """Remove a parameter field from the form."""
        if name in self.param_entries:
            # Find and remove the row
            for row in range(self.params_form.count()):
                item = self.params_form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                if item and item.widget():
                    from PyQt6.QtWidgets import QLabel

                    label_widget = item.widget()
                    if isinstance(label_widget, QLabel):
                        label_text = label_widget.text()
                        # Remove unit suffix if present
                        clean_name = label_text.split(" (")[0]
                        if clean_name == name:
                            # Remove the row
                            self.params_form.removeRow(row)
                            break

            del self.param_entries[name]
            self._update_json_view()

    def _on_add_parameter(self):
        """Handle add parameter button click."""
        existing_names = list(self.param_entries.keys())
        dialog = AddParameterDialog(self, existing_names)

        if dialog.exec():
            param_data = dialog.get_parameter_data()
            name = param_data["name"]

            # Create parameter definition
            param_def = {
                "name": name,
                "description": param_data["description"],
                "unit": {"annotationValue": param_data["unit"]} if param_data["unit"] else {},
            }

            self._add_parameter_field(name, param_def, param_data["value"])
            self._update_json_view()

    def _clear_parameters(self):
        """Clear all parameter fields from the form."""
        # Remove all rows from the form
        while self.params_form.count() > 0:
            self.params_form.removeRow(0)
        # Clear the param_entries dictionary
        self.param_entries.clear()

    def _reload_template(self, assay_type: str):
        """Reload the template based on the selected assay type."""
        # Check if dm is available
        if not self.dm:
            return [], [], ""

        # Get template file name from mapping
        template_filename = self.TEMPLATE_FILE_MAPPING.get(assay_type)
        if not template_filename:
            return [], [], ""

        template_file = (
            get_profile().get_templates_root() / "assay_templates" / f"{template_filename}.json"
        )

        new_parameter_definitions = []
        new_expected_attachments = []
        new_description = ""

        try:
            if template_file.exists():
                with open(template_file, "r", encoding="utf-8") as f:
                    template_data = json.load(f)
                    # Extract parameter definitions from template
                    new_parameter_definitions = template_data.get("parameters", [])
                    # Extract expected attachments from template
                    new_expected_attachments = template_data.get("expectedAttachments", [])
                    # Extract description from template
                    new_description = template_data.get("description", "")
        except Exception as e:
            print(f"Warning: Could not load template: {e}")

        return new_parameter_definitions, new_expected_attachments, new_description

    def _on_type_changed(self, new_type: str):
        """Handle assay type combo box change."""
        # Skip if we're still initializing (to avoid double initialization)
        if self._initializing:
            return

        # Reload the template
        new_parameter_definitions, new_expected_attachments, new_description = (
            self._reload_template(new_type)
        )

        # Update the internal state
        self.parameter_definitions = new_parameter_definitions
        self.expected_attachments = new_expected_attachments

        # Clear existing parameters
        self._clear_parameters()

        # Reinitialize parameters with new definitions
        self._initialize_parameters()

        # Update the file attachment widget with new expected attachments
        self._update_file_attachments(new_expected_attachments)

        # Update the description field with the new description from template
        if new_description:
            self.desc_edit.setPlainText(new_description)

    def _update_file_attachments(self, new_expected_attachments: list):
        """Update the file attachment widget with new expected attachments."""
        # Get currently attached files to preserve them
        current_attached_files = self.file_attachment_widget.attached_files

        # Update the widget's expected_attachments and attached_files
        self.file_attachment_widget.expected_attachments = new_expected_attachments
        self.file_attachment_widget.attached_files = current_attached_files

        # Rebuild the UI
        self.file_attachment_widget.setup_ui()

    def _show_form_view(self):
        """Show form view and hide JSON view."""
        self.view_mode = "form"
        self.form_view_btn.setChecked(True)
        self.json_view_btn.setChecked(False)
        self.params_stack.setCurrentIndex(0)  # Show form scroll area

    def _show_json_view(self):
        """Show JSON view and hide form view."""
        self.view_mode = "json"
        self.form_view_btn.setChecked(False)
        self.json_view_btn.setChecked(True)
        self.params_stack.setCurrentIndex(1)  # Show JSON container

    def _update_json_view(self):
        """Update the JSON view with current parameter values."""
        params = self._get_parameter_values()
        self.params_edit.setPlainText(json.dumps(params, indent=2))

    def _sync_json_to_form(self):
        """Sync JSON values to form fields."""
        try:
            json_text = self.params_edit.toPlainText()
            if json_text.strip():
                params = json.loads(json_text)

                # Update existing fields
                for name, value in params.items():
                    if name in self.param_entries:
                        widget = self.param_entries[name]["widget"]
                        if isinstance(widget, QLineEdit):
                            widget.setText(str(value))
                        elif isinstance(widget, QDoubleSpinBox):
                            try:
                                widget.setValue(float(value))
                            except (ValueError, TypeError):
                                pass
                        elif isinstance(widget, QSpinBox):
                            try:
                                widget.setValue(int(float(value)))
                            except (ValueError, TypeError):
                                pass
                    else:
                        # Add new field
                        param_def = {"name": name, "description": "", "unit": {}}
                        self._add_parameter_field(name, param_def, str(value))

                # Remove fields not in JSON
                names_to_remove = [name for name in self.param_entries if name not in params]
                for name in names_to_remove:
                    self._remove_parameter(name)

        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON", f"Parameters JSON is invalid:\n{e}")

    def _get_parameter_values(self) -> dict:
        """Get parameter values from the form."""
        values = {}
        for name, data in self.param_entries.items():
            widget = data["widget"]
            if isinstance(widget, QLineEdit):
                values[name] = widget.text()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                values[name] = str(widget.value())
        return values

    def _on_save(self):
        """Handle save button click."""
        # Validate name
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Assay name is required.")
            self.name_edit.setFocus()
            return

        # Validate that at least one material is selected
        if not self.linked_materials:
            QMessageBox.warning(
                self,
                "Validation Error",
                "At least one input material must be selected for the assay.\n\n"
                "Please go to the Materials tab and click 'Select Inputs...' to choose "
                "existing materials from your study.\n\n"
                "If no materials exist yet, please create them first in the Materials page.",
            )
            return

        # If in JSON view, validate and sync
        if self.view_mode == "json":
            params_text = self.params_edit.toPlainText()
            if params_text.strip():
                try:
                    json.loads(params_text)
                except json.JSONDecodeError as e:
                    QMessageBox.warning(self, "Invalid JSON", f"Parameters JSON is invalid:\n{e}")
                    return
            self._sync_json_to_form()

        self.accept()

    def get_assay_data(self) -> dict:
        """Get the assay data from the dialog."""
        # Get parameters from current view
        if self.view_mode == "json":
            params_text = self.params_edit.toPlainText()
            if params_text.strip():
                try:
                    params = json.loads(params_text)
                except json.JSONDecodeError:
                    params = {}
            else:
                params = {}
        else:
            params = self._get_parameter_values()

        # Generate assay ID if not provided
        assay_id = self.assay_data.get("assay_id")
        if not assay_id:
            name = self.name_edit.text().strip()
            assay_id = f"assay_{name.lower().replace(' ', '_')}"

        # Get protocol ID from assay type
        assay_type = self.type_combo.currentText()
        protocol_id = self._get_protocol_id(assay_type)

        # Create process node for this assay execution
        process_id = f"https://example.org/processes/process_{assay_id}"
        process_node = {
            "@id": process_id,
            "name": f"{self.name_edit.text().strip()} execution",
            "executesProtocol": protocol_id,
            "date": self.date_edit.date().toString(Qt.DateFormat.ISODate),
            "performer": self._get_performer_name(),
            "inputs": self._get_input_material_ids(),
            "outputs": [],
            "parameterValues": self._convert_params_to_isa_format(params),
        }

        # Get files from widget
        attached_files = self.file_attachment_widget.attached_files

        return {
            "assay_id": assay_id,
            "name": self.name_edit.text().strip(),
            "assay_type": assay_type,
            "description": self.desc_edit.toPlainText().strip(),
            "parameters": params,
            "inputs": self.linked_materials,
            "created_at": self.assay_data.get("created_at", datetime.now().isoformat()),
            "files": attached_files,
            "processSequence": [process_node],
        }

    def _load_materials(self):
        """Load linked materials from assay data."""
        self.inputs_list.clear()
        self.linked_materials = []

        inputs = self.assay_data.get("inputs", [])

        for input_item in inputs:
            if isinstance(input_item, dict):
                if "material_id" in input_item and input_item["material_id"]:
                    input_item_dict = input_item
                    material_name = input_item.get("name", "Unknown")
                    is_locked = input_item.get("locked", False)
                else:
                    # Template definition (from template file) - skip
                    continue
            else:
                continue

            self.linked_materials.append(input_item_dict)

            display_name = f"🔒 {material_name}" if is_locked else material_name

            list_item = QListWidgetItem(display_name)
            list_item.setData(Qt.ItemDataRole.UserRole, input_item_dict)
            self.inputs_list.addItem(list_item)

        # Update the status label
        self._update_materials_status()

    def _update_materials_status(self):
        """Update the materials status label based on current selection."""
        if not self.linked_materials:
            self.materials_status_label.setText(
                "<i style='color: orange;'>No materials selected. "
                "Please select at least one input material.</i>"
            )
        else:
            count = len(self.linked_materials)
            material_names = [m.get("name", "Unknown") for m in self.linked_materials[:3]]
            if count > 3:
                material_names.append(f"+{count - 3} more")
            materials_text = ", ".join(material_names)
            self.materials_status_label.setText(
                f"<i style='color: green;'>{count} material(s) selected: {materials_text}</i>"
            )

    def _get_material_by_id(self, material_id: str) -> dict:
        """
        Get material by ID from the study data.

        Args:
            material_id: The material ID to look up

        Returns:
            Material dictionary or empty dict if not found
        """
        if not self.study_data:
            return {}

        # Check if materials are in studies[0] (ISA-JSON format)
        if (
            "studies" in self.study_data
            and isinstance(self.study_data["studies"], list)
            and len(self.study_data["studies"]) > 0
        ):
            studies_0 = self.study_data["studies"][0]
            if "materials" in studies_0:
                materials = studies_0["materials"]
            else:
                materials = self.study_data.get("materials", {})
        else:
            materials = self.study_data.get("materials", {})

        all_materials: List[Dict[str, Any]] = []
        all_materials.extend(materials.get("sources", []))
        all_materials.extend(materials.get("samples", []))
        all_materials.extend(materials.get("otherMaterials", []))

        for material in all_materials:
            if material.get("@id", "") == material_id:
                return material

        return {}

    def _get_all_materials(self) -> list:
        """Get all materials from study data."""
        if not self.study_data:
            return []

        # Check if materials are in studies[0] (ISA-JSON format)
        if (
            "studies" in self.study_data
            and isinstance(self.study_data["studies"], list)
            and len(self.study_data["studies"]) > 0
        ):
            studies_0 = self.study_data["studies"][0]
            if "materials" in studies_0:
                materials = studies_0["materials"]
            else:
                materials = self.study_data.get("materials", {})
        else:
            materials = self.study_data.get("materials", {})

        all_materials = []
        all_materials.extend(materials.get("sources", []))
        all_materials.extend(materials.get("samples", []))
        all_materials.extend(materials.get("otherMaterials", []))

        return all_materials

    def _on_select_inputs(self):
        """Handle select inputs button click."""
        # Get available materials
        materials = self._get_all_materials()

        # Open material selection dialog
        dialog = MaterialSelectionDialog(
            self, materials=materials, title="Select Input Materials", multi_select=True
        )

        # Pre-select current inputs
        current_input_ids = [i.get("material_id", "") for i in self.linked_materials]
        dialog.set_preselected_materials(current_input_ids)

        if dialog.exec():
            selected_materials = dialog.get_selected_materials()

            # Update linked materials and mark as locked
            self.linked_materials = [
                {
                    "material_id": m.get("@id", ""),
                    "name": m.get("name", ""),
                    "materialType": m.get("materialType", ""),
                    "locked": True,  # Mark as manually assigned
                }
                for m in selected_materials
            ]

            # Sync to assay_data so _load_materials() can load them
            self.assay_data["inputs"] = self.linked_materials.copy()

            self._load_materials()

    def _setup_performer_tab(self) -> QWidget:
        """Set up the performer tab with person schema fields."""
        performer_tab = QWidget()
        performer_layout = QFormLayout(performer_tab)

        # Name fields
        name_layout = QHBoxLayout()
        self.first_name_edit = QLineEdit()
        self.first_name_edit.setPlaceholderText("First name")
        name_layout.addWidget(QLabel("First Name:"))
        name_layout.addWidget(self.first_name_edit)

        self.mid_initials_edit = QLineEdit()
        self.mid_initials_edit.setPlaceholderText("MI")
        self.mid_initials_edit.setMaximumWidth(50)
        name_layout.addWidget(QLabel("MI:"))
        name_layout.addWidget(self.mid_initials_edit)

        self.last_name_edit = QLineEdit()
        self.last_name_edit.setPlaceholderText("Last name")
        name_layout.addWidget(QLabel("Last Name:"))
        name_layout.addWidget(self.last_name_edit)

        performer_layout.addRow("Name:", name_layout)

        # Contact fields
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("email@example.com")
        performer_layout.addRow("Email:", self.email_edit)

        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("+1-234-567-8900")
        performer_layout.addRow("Phone:", self.phone_edit)

        self.fax_edit = QLineEdit()
        self.fax_edit.setPlaceholderText("+1-234-567-8901")
        performer_layout.addRow("Fax:", self.fax_edit)

        # Address
        self.address_edit = QTextEdit()
        self.address_edit.setMaximumHeight(80)
        self.address_edit.setPlaceholderText("Street address, City, State, ZIP, Country")
        performer_layout.addRow("Address:", self.address_edit)

        # Affiliation
        self.affiliation_edit = QLineEdit()
        self.affiliation_edit.setPlaceholderText("Organization name")
        performer_layout.addRow("Affiliation:", self.affiliation_edit)

        # Template buttons
        template_layout = QHBoxLayout()
        save_template_btn = QPushButton("Save as Template")
        save_template_btn.clicked.connect(self._save_performer_template)
        template_layout.addWidget(save_template_btn)

        self.performer_template_combo = QComboBox()
        self.performer_template_combo.addItem("-- Select Template --")
        load_template_btn = QPushButton("Load Template")
        load_template_btn.clicked.connect(
            lambda: self._load_performer_template(self.performer_template_combo)
        )
        template_layout.addWidget(self.performer_template_combo)
        template_layout.addWidget(load_template_btn)

        performer_layout.addRow(template_layout)

        # Load existing performer data if available
        self._load_performer_data()

        # Refresh performer templates
        self._refresh_performer_templates()

        return performer_tab

    def _load_performer_data(self):
        """Load existing performer data from assay data."""
        # Get performer from processSequence if available
        process_sequence = self.assay_data.get("processSequence", [])
        if process_sequence and len(process_sequence) > 0:
            first_process = process_sequence[0]
            performer_name = first_process.get("performer", "")
            # Try to parse name into first/last
            if performer_name:
                parts = performer_name.split(" ", 1)
                if len(parts) >= 1:
                    self.last_name_edit.setText(parts[0])
                    if len(parts) >= 2:
                        self.first_name_edit.setText(parts[1])
                else:
                    self.last_name_edit.setText(performer_name)

    def _get_performer_name(self) -> str:
        """Get performer name from performer tab."""
        first_name = self.first_name_edit.text() if hasattr(self, "first_name_edit") else ""
        last_name = self.last_name_edit.text() if hasattr(self, "last_name_edit") else ""
        if first_name and last_name:
            return f"{first_name} {last_name}"
        elif last_name:
            return last_name
        elif first_name:
            return first_name
        return ""

    def _get_performer_details(self) -> dict:
        """Get full performer details from performer tab."""
        return {
            "@id": f"https://example.org/people/{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "firstName": self.first_name_edit.text() if hasattr(self, "first_name_edit") else "",
            "lastName": self.last_name_edit.text() if hasattr(self, "last_name_edit") else "",
            "midInitials": (
                self.mid_initials_edit.text() if hasattr(self, "mid_initials_edit") else ""
            ),
            "email": self.email_edit.text() if hasattr(self, "email_edit") else "",
            "phone": self.phone_edit.text() if hasattr(self, "phone_edit") else "",
            "fax": self.fax_edit.text() if hasattr(self, "fax_edit") else "",
            "address": self.address_edit.toPlainText() if hasattr(self, "address_edit") else "",
            "affiliation": (
                self.affiliation_edit.text() if hasattr(self, "affiliation_edit") else ""
            ),
        }

    def _save_performer_template(self):
        """Save current performer details as a template."""
        performer = self._get_performer_details()
        name = f"{performer['firstName']} {performer['lastName']}".strip()

        if not name:
            QMessageBox.warning(
                self, "Warning", "Please enter at least a name to save as template."
            )
            return

        # Load existing templates
        templates = self._load_performer_templates()

        # Add new template
        template_id = f"performer_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        templates[template_id] = performer

        # Save templates
        templates_file = Path("config/performer_templates.json")
        templates_file.parent.mkdir(exist_ok=True, parents=True)
        with open(templates_file, "w", encoding="utf-8") as f:
            json.dump(templates, f, indent=2)

        QMessageBox.information(self, "Success", f"Template '{name}' saved successfully.")
        self._refresh_performer_templates()

    def _load_performer_templates(self) -> dict:
        """Load performer templates from config file."""
        templates_file = Path("config/performer_templates.json")
        if templates_file.exists():
            try:
                with open(templates_file, "r", encoding="utf-8") as f:
                    return json.load(f)  # type: ignore[no-any-return]
            except Exception:
                return {}
        return {}

    def _refresh_performer_templates(self):
        """Refresh the performer template combo box."""
        if hasattr(self, "performer_template_combo"):
            self.performer_template_combo.clear()
            self.performer_template_combo.addItem("-- Select Template --")

            templates = self._load_performer_templates()
            for template_id, template in templates.items():
                name = f"{template.get('firstName', '')} {template.get('lastName', '')}".strip()
                if name:
                    self.performer_template_combo.addItem(name, template_id)

    def _load_performer_template(self, combo_box: QComboBox):
        """Load selected performer template into form."""
        current_data = combo_box.currentData()
        if not current_data:
            return

        templates = self._load_performer_templates()
        template = templates.get(current_data, {})

        if template:
            self.first_name_edit.setText(template.get("firstName", ""))
            self.last_name_edit.setText(template.get("lastName", ""))
            self.mid_initials_edit.setText(template.get("midInitials", ""))
            self.email_edit.setText(template.get("email", ""))
            self.phone_edit.setText(template.get("phone", ""))
            self.fax_edit.setText(template.get("fax", ""))
            self.address_edit.setPlainText(template.get("address", ""))
            self.affiliation_edit.setText(template.get("affiliation", ""))

    def _get_input_material_ids(self) -> list:
        """Get list of material IDs from selected materials."""
        material_ids = []
        for material in self.linked_materials:
            if isinstance(material, dict) and "material_id" in material:
                material_ids.append(material["material_id"])
            elif isinstance(material, str):
                material_ids.append(material)
        return material_ids

    def _get_protocol_id(self, assay_type: str) -> str:
        """Get protocol ID based on assay type."""
        protocol_mapping = {
            "SDS-PAGE": "https://example.org/investigations/inv_1#prot_sds_page",
            "Microscopy": "https://example.org/investigations/inv_1#prot_depot_microscopy",
            "Toxicity Test": "https://example.org/investigations/inv_1#prot_toxicity_test",
            "Assembly Fragment Gel": "https://example.org/investigations/inv_1#prot_assembly_fragment_gel",  # noqa: E501
            "Digestion Assay": "https://example.org/investigations/inv_1#prot_digestion",
            "Sequencing Assay": "https://example.org/investigations/inv_1#prot_sequencing",
            "Culture Monitoring": "https://example.org/investigations/inv_1#prot_culture_monitoring",  # noqa: E501
            "Expression Monitoring": "https://example.org/investigations/inv_1#prot_expression_monitoring",  # noqa: E501
            "Pellet Weighing": "https://example.org/investigations/inv_1#prot_pellet_weighing",
            "Resuspension Illumination": "https://example.org/investigations/inv_1#prot_resuspension_illumination",  # noqa: E501
            "Supernatant Concentration": "https://example.org/investigations/inv_1#prot_supernatant_concentration",  # noqa: E501
            "TUNEL Staining": "https://example.org/investigations/inv_1#prot_tunel_staining",
        }
        return protocol_mapping.get(assay_type, "")

    def _convert_params_to_isa_format(self, params: dict) -> list:
        """Convert parameters dict to ISA-JSON parameterValues format."""
        param_values = []
        for name, value in params.items():
            param_values.append(
                {"parameterName": {"annotationValue": name, "termSource": "OBI"}, "value": value}
            )
        return param_values
