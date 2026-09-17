"""
Assays page for the ISA-JSON Data Steward GUI.
"""

import json

# Import utilities
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
)

from ..dialogs.assay_dialog import AssayDialog
from ..widgets.common import ActionButton, PrimaryButton, SectionHeader
from .base_page import ScrollablePage

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.constants import TemplateConstants  # noqa: E402
from utils.file_manager import FileManager  # noqa: E402
from utils.isa_json_preview_helpers import ISAJsonPreviewHelper  # noqa: E402


class AssaysPage(ScrollablePage):
    """Assays page for managing assay data."""

    # Use constants from centralized location
    TEMPLATE_FILE_MAPPING = TemplateConstants.TEMPLATE_FILE_MAPPING

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.assays = []
        self._isa_raw_assays = []  # Store original ISA-JSON assays for preview
        self.preview_helper = None
        self.setup_assays_ui()

    def _get_material_by_id(self, study_data: dict, material_id: str) -> dict:
        """
        Get material by ID from the study data.

        Args:
            study_data: The study data dictionary containing materials
            material_id: The material ID to look up

        Returns:
            Material dictionary or empty dict if not found
        """
        if not study_data:
            return {}

        materials = study_data.get("materials", {})
        all_materials = []
        all_materials.extend(materials.get("sources", []))
        all_materials.extend(materials.get("samples", []))
        all_materials.extend(materials.get("otherMaterials", []))

        for material in all_materials:
            if material.get("@id", "") == material_id:
                return material  # type: ignore[no-any-return]

        return {}

    def _convert_isa_assay_to_simple(
        self, isa_assay: dict, study_data: Optional[dict] = None
    ) -> dict:
        """
        Convert ISA-JSON assay format to simple format expected by GUI.

        Args:
            isa_assay: Assay in ISA-JSON format
            study_data: The study data dictionary containing materials (for looking up material names)  # noqa: E501

        Returns:
            Assay in simple format with fields: assay_id, name, assay_type, date, description, performer, parameters, files, inputs  # noqa: E501
        """
        # Extract assay type from measurementType
        measurement_type = isa_assay.get("measurementType", {})
        assay_type = (
            measurement_type.get("annotationValue", "")
            if isinstance(measurement_type, dict)
            else ""
        )

        # Extract parameters from parameterValues
        parameters = {}
        for param_value in isa_assay.get("parameterValues", []):
            param_name = param_value.get("parameterName", {})
            if isinstance(param_name, dict):
                name = param_name.get("annotationValue", "")
                value = param_value.get("value", {})
                if isinstance(value, dict):
                    parameters[name] = value.get("value", "")
                else:
                    parameters[name] = str(value)

        # Extract assay_id and name from @id (ISA-JSON doesn't allow 'name' property for assays)
        assay_id = isa_assay.get("@id", "")
        assay_name = ""
        if assay_id:
            if "#" in assay_id:
                fragment = assay_id.split("#")[-1]
                # Extract name from assay_id (e.g., "assay_SDS-PAGE_assay" -> "SDS-PAGE assay")
                assay_name = fragment.replace("assay_", "").replace("_", " ").strip()
                # If name is empty (e.g., @id ends with "#assay_"), try fallbacks
                if not assay_name:
                    # Try original measurement type from comments
                    comments = isa_assay.get("comments", [])
                    for comment in comments:
                        if comment.get("name") == "original measurement type":
                            assay_name = comment.get("value", "")
                            break
                    # Try measurement type
                    if not assay_name:
                        mt = isa_assay.get("measurementType", {})
                        if isinstance(mt, dict):
                            assay_name = mt.get("annotationValue", "")
                    # Last resort: use the full fragment
                    if not assay_name:
                        assay_name = fragment if fragment else "Unnamed Assay"
            else:
                assay_name = assay_id
        else:
            # Fallback to 'name' property for internal format (not ISA-JSON)
            assay_name = isa_assay.get("name", "")

        # Get date and performer from first process in processSequence
        process_sequence = isa_assay.get("processSequence", [])
        if process_sequence:
            first_process = process_sequence[0]
            date = first_process.get("date", "")
            performer = first_process.get("performer", "")
            # Extract inputs from process
            process_inputs = first_process.get("inputs", [])
        else:
            date = ""
            performer = ""
            process_inputs = []

        # Get description from comments (if available)
        description = ""
        for comment in isa_assay.get("comments", []):
            if comment.get("name") == "description":
                description = comment.get("value", "")

        # Extract inputs - convert from material IDs to full format
        inputs = []
        for inp in process_inputs:
            if isinstance(inp, str):
                # ISA-JSON format: inp is a material ID string
                # Look up material from study data
                material = self._get_material_by_id(study_data, inp) if study_data else {}
                material_name = material.get("name", "Unknown") if material else "Unknown"
                material_type = material.get("materialType", "") if material else ""
                inputs.append(
                    {
                        "material_id": inp,
                        "name": material_name,
                        "materialType": material_type,
                        "locked": False,
                    }
                )
            else:
                # Already in dict format
                inputs.append(inp)

        # Extract dataFiles
        data_files = isa_assay.get("dataFiles", [])

        return {
            "assay_id": assay_id,
            "name": assay_name,
            "assay_type": assay_type,
            "date": date,  # Now from processSequence
            "description": description,  # From comments
            "performer": performer,  # From processSequence
            "parameters": parameters,
            "inputs": inputs,
            "files": data_files,
        }

    def setup_assays_ui(self):
        """Set up the assays UI."""
        # Header
        self.add_widget(SectionHeader("Assays"))

        # Template selection
        template_layout = QHBoxLayout()

        template_label = QLabel("Select Assay Template:")
        template_label.setStyleSheet("font-weight: 500;")
        template_layout.addWidget(template_label)

        self.template_combo = QComboBox()
        self.template_combo.addItems(
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
        template_layout.addWidget(self.template_combo)

        template_layout.addStretch()

        self.add_layout(template_layout)

        # Main splitter: table (left) + details preview (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: Assay data table
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Assay Name", "Type", "Date", "Performer", "Materials", "Files"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 120)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        # Connect selection change to update preview
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        self.set_expanding(self.table)
        left_layout.addWidget(self.table)

        # Right panel: Assay details preview
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        details_group = QFrame()
        details_group.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        details_layout = QVBoxLayout(details_group)

        details_header = QLabel("Assay Details")
        details_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        details_layout.addWidget(details_header)

        self.details_browser = QTextBrowser()
        self.details_browser.setOpenExternalLinks(False)
        self.details_browser.setStyleSheet("""
            QTextBrowser {
                background-color: transparent;
                border: none;
                color: #333;
                font-size: 12px;
            }
        """)
        self.details_browser.setHtml(
            '<span style="color: #666;">Select an assay to view details</span>'
        )
        details_layout.addWidget(self.details_browser)

        right_layout.addWidget(details_group)

        # Set stretch factors
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        self.set_expanding(splitter)
        self.add_widget(splitter)

        # Buttons
        buttons_layout = QHBoxLayout()

        add_btn = PrimaryButton("Add Assay")
        add_btn.clicked.connect(self._on_add_assay)
        buttons_layout.addWidget(add_btn)

        edit_btn = ActionButton("Edit Selected")
        edit_btn.clicked.connect(self._on_edit_assay)
        buttons_layout.addWidget(edit_btn)

        delete_btn = ActionButton("Delete Selected")
        delete_btn.clicked.connect(self._on_delete_assay)
        buttons_layout.addWidget(delete_btn)

        buttons_layout.addStretch()

        self.add_layout(buttons_layout)

    def refresh(self):
        """Refresh the assays table."""
        self.table.setRowCount(0)
        self.assays = []
        self._isa_raw_assays = []
        self.preview_helper = None

        # Reset details panel
        if hasattr(self, "details_browser"):
            self.details_browser.setHtml(
                '<span style="color: #666;">Select an assay to view details</span>'
            )

        # Load assays from study data
        study_data = self.main_window.get_study_data()

        if study_data:
            # Build preview helper for ISA-JSON resolution
            try:
                self.preview_helper = ISAJsonPreviewHelper(study_data)
            except Exception as e:
                print(f"[AssaysPage] Error building preview helper: {e}")

            # Handle both simple study structure and complete ISA-JSON structure
            if (
                "studies" in study_data
                and isinstance(study_data["studies"], list)
                and len(study_data["studies"]) > 0
            ):
                # Complete ISA-JSON structure: assays are in studies[0].assays
                raw_assays = study_data["studies"][0].get("assays", [])
                # Use the study data from studies[0] for material lookup (contains materials)
                material_lookup_data = study_data["studies"][0]
            else:
                # Simple study structure: assays are at top level
                raw_assays = study_data.get("assays", [])
                # Use the study_data directly for material lookup
                material_lookup_data = study_data

            # Store raw ISA-JSON assays for preview
            self._isa_raw_assays = raw_assays

            # Convert assays to simple format (handle both ISA-JSON and simple format)
            for assay in raw_assays:
                # Check if assay is in ISA-JSON format (has @id and measurementType)
                # ISA-JSON assays have measurementType, not @type
                if "@id" in assay and "measurementType" in assay:
                    # Convert from ISA-JSON to simple format, passing study data for material lookup
                    converted = self._convert_isa_assay_to_simple(assay, material_lookup_data)
                    self.assays.append(converted)
                else:
                    # Already in simple format
                    self.assays.append(assay)

        # Populate table
        for idx, assay in enumerate(self.assays):
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(assay.get("name", "")))
            self.table.setItem(row, 1, QTableWidgetItem(assay.get("assay_type", "")))
            self.table.setItem(row, 2, QTableWidgetItem(assay.get("date", "")))
            self.table.setItem(row, 3, QTableWidgetItem(assay.get("performer", "")))

            # Display linked materials
            inputs = assay.get("inputs", [])
            if inputs:
                material_names = [i.get("name", "Unknown") for i in inputs]
                materials_text = ", ".join(material_names)
                # Truncate if too long
                if len(materials_text) > 30:
                    materials_text = materials_text[:27] + "..."
                self.table.setItem(row, 4, QTableWidgetItem(materials_text))
            else:
                self.table.setItem(row, 4, QTableWidgetItem("-"))

            # Count files
            files = assay.get("files", [])
            file_count = len(files) if isinstance(files, list) else 0
            self.table.setItem(row, 5, QTableWidgetItem(str(file_count)))

    def _on_selection_changed(self):
        """Handle table selection change - update the details preview."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            if hasattr(self, "details_browser"):
                self.details_browser.setHtml(
                    '<span style="color: #666;">Select an assay to view details</span>'
                )
            return

        row = selected_rows[0].row()

        if row < len(self._isa_raw_assays):
            # Use the original ISA-JSON assay for rich preview
            isa_assay = self._isa_raw_assays[row]
            if self.preview_helper:
                html = self.preview_helper.get_assay_preview_html(isa_assay)
                self.details_browser.setHtml(html)
            else:
                self._show_basic_assay_preview(row)
        elif row < len(self.assays):
            self._show_basic_assay_preview(row)

    def _show_basic_assay_preview(self, row: int):
        """Show basic assay preview without ISA-JSON helper."""
        if row >= len(self.assays):
            return
        assay = self.assays[row]
        html_parts = []
        html_parts.append(
            f'<b style="font-size: 14px;">{ISAJsonPreviewHelper._escape(assay.get("name", ""))}</b><br>'  # noqa: E501
        )
        html_parts.append(
            f'<span style="color: #666;">Type:</span> {ISAJsonPreviewHelper._escape(assay.get("assay_type", ""))}<br>'  # noqa: E501
        )
        html_parts.append(
            f'<span style="color: #666;">Date:</span> {ISAJsonPreviewHelper._escape(assay.get("date", ""))}<br>'  # noqa: E501
        )
        html_parts.append(
            f'<span style="color: #666;">Performer:</span> {ISAJsonPreviewHelper._escape(assay.get("performer", ""))}<br>'  # noqa: E501
        )

        inputs = assay.get("inputs", [])
        if inputs:
            html_parts.append("<br><b>Inputs:</b><br>")
            for inp in inputs:
                html_parts.append(
                    f'&bull; {ISAJsonPreviewHelper._escape(inp.get("name", "Unknown"))}<br>'
                )

        files = assay.get("files", [])
        if files:
            html_parts.append(f"<br><b>Files ({len(files)}):</b><br>")
            for f in files:
                fname = f.get("name", "") if isinstance(f, dict) else str(f)
                html_parts.append(f"&bull; {ISAJsonPreviewHelper._escape(fname)}<br>")

        self.details_browser.setHtml("\n".join(html_parts))

    def _on_add_assay(self):
        """Handle add assay button click."""
        # Check if a study is selected
        if not self.main_window.current_study:
            QMessageBox.information(
                self, "No Study Selected", "Please select a study first from the Studies page."
            )
            return

        # Get template type
        template_type = self.template_combo.currentText()

        # Load template if available
        template_data = {}
        parameter_definitions = []
        expected_attachments = []
        try:
            # Get template file name from mapping
            template_filename = self.TEMPLATE_FILE_MAPPING.get(template_type)
            if template_filename:
                templates_root = self.main_window.get_templates_root()
                template_file = templates_root / "assay_templates" / f"{template_filename}.json"
                if template_file.exists():
                    with open(template_file, "r", encoding="utf-8") as f:
                        template_data = json.load(f)
                        # Extract parameter definitions from template
                        parameter_definitions = template_data.get("parameters", [])
                        # Extract expected attachments from template
                        expected_attachments = template_data.get("expectedAttachments", [])
            else:
                print(f"Warning: No template file mapping found for assay type: {template_type}")
        except Exception as e:
            print(f"Warning: Could not load template: {e}")

        # Add the assay_type to template_data so the dialog can set the correct type
        template_data["assay_type"] = template_type

        # Open dialog with parameter definitions and expected attachments
        dialog = AssayDialog(
            self,
            dm=self.main_window.get_directory_manager(),
            assay_data=template_data,
            parameter_definitions=parameter_definitions,
            expected_attachments=expected_attachments,
            study_data=self.main_window.get_study_data(),
        )
        dialog.setWindowTitle("Create Assay")
        if dialog.exec():
            assay_data = dialog.get_assay_data()
            # Copy files to study folder using FileManager
            investigation_id = self.main_window.current_investigation or "inv_1"
            study_id = self.main_window.current_study or "study_1"
            assay_name = assay_data.get("name", "unknown")

            # Create FileManager instance
            file_manager = FileManager(investigations_root="investigations")

            # Process attached files
            processed_files = []
            for file_meta in assay_data.get("files", []):
                # Get original file path
                original_path = file_meta.get("file_path")
                if not original_path:
                    continue

                # Call FileManager.add_file() to copy file to study folder
                result = file_manager.add_file(
                    investigation_id=investigation_id,
                    study_id=study_id,
                    entity_type="assay",
                    entity_id=assay_name,
                    source_path=Path(original_path),
                    attachment_type=file_meta.get("attachment_type", "unknown"),
                    attachment_name=file_meta.get("attachment_name"),
                )

                if result.get("success", True):  # add_file returns dict with file_metadata or error
                    # Use the returned file metadata (which has relative paths)
                    processed_files.append(result.get("file_metadata", result))
                else:
                    print(f"Failed to copy file: {result.get('error', 'Unknown error')}")
                    # Still keep original metadata if copy failed
                    processed_files.append(file_meta)

            # Update assay_data with processed file metadata
            assay_data["files"] = processed_files
            # Add to study data
            study_data = self.main_window.get_study_data() or {}

            # Handle both simple and complete ISA-JSON structure
            if (
                "studies" in study_data
                and isinstance(study_data["studies"], list)
                and len(study_data["studies"]) > 0
            ):
                # Complete ISA-JSON structure - add to studies[0].assays
                # Files are stored in assay.dataFiles per ISA-JSON standard
                assays = study_data["studies"][0].get("assays", [])
                assays.append(assay_data)
                study_data["studies"][0]["assays"] = assays
            else:
                # Simple structure - add to top level assays
                assays = study_data.get("assays", [])
                assays.append(assay_data)
                study_data["assays"] = assays

            # Save study JSON
            self._save_study_data(study_data)

            self.main_window.status_bar.show_message(
                f"Assay '{assay_data['name']}' created successfully!"
            )
            self.refresh()

    def _on_edit_assay(self):
        """Handle edit assay button click."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select an assay to edit.")
            return

        # Get the integer row index from QModelIndex
        row_index = selected_rows[0].row()
        assay_data = self.assays[row_index]

        # Try to load template for parameter definitions and expected attachments
        parameter_definitions = []
        expected_attachments = []
        assay_type = assay_data.get("assay_type", "")
        if assay_type:
            try:
                # Get template file name from mapping
                template_filename = self.TEMPLATE_FILE_MAPPING.get(assay_type)
                if template_filename:
                    templates_root = self.main_window.get_templates_root()
                    template_file = templates_root / "assay_templates" / f"{template_filename}.json"
                    if template_file.exists():
                        with open(template_file, "r", encoding="utf-8") as f:
                            template_data = json.load(f)
                            parameter_definitions = template_data.get("parameters", [])
                            expected_attachments = template_data.get("expectedAttachments", [])
                else:
                    print(f"Warning: No template file mapping found for assay type: {assay_type}")
            except Exception as e:
                print(f"Warning: Could not load template: {e}")

        # Open dialog with existing data, parameter definitions, and expected attachments
        dialog = AssayDialog(
            self,
            dm=self.main_window.get_directory_manager(),
            assay_data=assay_data,
            parameter_definitions=parameter_definitions,
            expected_attachments=expected_attachments,
            study_data=self.main_window.get_study_data(),
        )
        dialog.setWindowTitle("Edit Assay")
        if dialog.exec():
            updated_data = dialog.get_assay_data()
            # Copy new/updated files to study folder using FileManager
            investigation_id = self.main_window.current_investigation or "inv_1"
            study_id = self.main_window.current_study or "study_1"
            assay_name = updated_data.get("name", "unknown")

            # Create FileManager instance
            file_manager = FileManager(investigations_root="investigations")

            # Process attached files
            processed_files = []
            for file_meta in updated_data.get("files", []):
                # Get original file path
                original_path = file_meta.get("file_path")
                if not original_path:
                    # Keep existing file metadata if no path
                    processed_files.append(file_meta)
                    continue

                # Check if file is already in study folder (has original_path/converted_path)
                if file_meta.get("original_path") or file_meta.get("converted_path"):
                    # File already in study folder, keep existing metadata
                    processed_files.append(file_meta)
                    continue

                # Call FileManager.add_file() to copy file to study folder
                result = file_manager.add_file(
                    investigation_id=investigation_id,
                    study_id=study_id,
                    entity_type="assay",
                    entity_id=assay_name,
                    source_path=Path(original_path),
                    attachment_type=file_meta.get("attachment_type", "unknown"),
                    attachment_name=file_meta.get("attachment_name"),
                )

                if result.get("success", True):  # add_file returns dict with file_metadata or error
                    # Use the returned file metadata (which has relative paths)
                    processed_files.append(result.get("file_metadata", result))
                else:
                    print(f"Failed to copy file: {result.get('error', 'Unknown error')}")
                    # Still keep original metadata if copy failed
                    processed_files.append(file_meta)

            # Update updated_data with processed file metadata
            updated_data["files"] = processed_files
            # Update study data
            study_data = self.main_window.get_study_data() or {}
            # Handle both simple and complete ISA-JSON structure
            if (
                "studies" in study_data
                and isinstance(study_data["studies"], list)
                and len(study_data["studies"]) > 0
            ):
                # Complete ISA-JSON structure - update studies[0].assays
                # Files are stored in assay.dataFiles per ISA-JSON standard
                assays = study_data["studies"][0].get("assays", [])
                assays[row_index] = updated_data
                study_data["studies"][0]["assays"] = assays
            else:
                # Simple structure - update top level assays
                assays = study_data.get("assays", [])
                assays[row_index] = updated_data
                study_data["assays"] = assays

            # Save study JSON
            self._save_study_data(study_data)

            self.main_window.status_bar.show_message(
                f"Assay '{updated_data['name']}' updated successfully!"
            )
            self.refresh()

    def _on_delete_assay(self):
        """Handle delete assay button click."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select an assay to delete.")
            return

        # Get the integer row index from QModelIndex
        row_index = selected_rows[0].row()
        assay_data = self.assays[row_index]

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete assay '{assay_data.get('name', 'Unknown')}'?\n\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.No:
            return

        # Remove from study data
        study_data = self.main_window.get_study_data() or {}
        _assay_name = assay_data.get("name", "unknown")  # noqa: F841

        # Handle both simple and complete ISA-JSON structure
        if (
            "studies" in study_data
            and isinstance(study_data["studies"], list)
            and len(study_data["studies"]) > 0
        ):
            # Complete ISA-JSON structure - remove from studies[0].assays
            # Files are stored in assay.dataFiles per ISA-JSON standard
            assays = study_data["studies"][0].get("assays", [])
            assays.pop(row_index)
            study_data["studies"][0]["assays"] = assays
        else:
            # Simple structure - remove from top level assays
            assays = study_data.get("assays", [])
            assays.pop(row_index)
            study_data["assays"] = assays

        # Save study JSON
        self._save_study_data(study_data)

        self.main_window.status_bar.show_message("Assay deleted successfully!")
        self.refresh()

    def _save_study_data(self, study_data: dict):
        """Save study data as complete ISA-JSON format."""
        if not self.main_window.current_investigation or not self.main_window.current_study:
            QMessageBox.warning(self, "Error", "No investigation or study selected.")
            return

        investigation_id = self.main_window.current_investigation or "inv_1"
        study_id = self.main_window.current_study or "study_1"

        # Save using ISAJsonExporter to ensure ISA-JSON compliance
        dm = self.main_window.get_directory_manager()
        study_json_path = dm.get_study_json_path(investigation_id, study_id)

        try:
            # Use ISAJsonExporter to ensure only valid ISA-JSON fields are exported
            from utils.isa_json_exporter import ISAJsonExporter

            exporter = ISAJsonExporter(
                study_data=study_data, investigation_id=investigation_id, study_id=study_id
            )
            isa_json = exporter.export_complete_isa_json()

            with open(study_json_path, "w", encoding="utf-8") as f:
                json.dump(isa_json, f, indent=2)

            # Update main window study data with the saved structure
            # This preserves the full structure for proper GUI operation
            self.main_window.study_data = study_data
            self.main_window.status_bar.show_message("Saved successfully!")
        except Exception as e:
            import traceback

            error_details = (
                f"Failed to save study data:\n{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
            )
            print(f"[ERROR] {error_details}")
            QMessageBox.critical(self, "Error", error_details)

    def on_enter(self):
        """Called when the page is shown."""
        self.refresh()

    def on_exit(self):
        """Called when the page is hidden."""
        pass

    def set_investigation(self, investigation_id: str):
        """Set the current investigation."""
        self.refresh()

    def set_study(self, study_id: str):
        """Set the current study."""
        self.refresh()
