"""
Materials page for the ISA-JSON Data Steward GUI.
"""

import json

# Import utilities
import sys
from pathlib import Path

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

from ..dialogs.material_dialog import MaterialDialog
from ..widgets.common import ActionButton, PrimaryButton, SectionHeader
from .base_page import ScrollablePage

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.isa_json_exporter import ISAJsonExporter  # noqa: E402
from utils.isa_json_preview_helpers import ISAJsonPreviewHelper  # noqa: E402
from utils.material_manager import MaterialManager  # noqa: E402


class MaterialsPage(ScrollablePage):
    """Materials page for managing material data."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.material_manager = None
        self.materials = []
        self.current_filter = "All"
        self.preview_helper = None
        self.setup_materials_ui()

    def setup_materials_ui(self):
        """Set up the materials UI."""
        # Header
        self.add_widget(SectionHeader("Materials"))

        # Filter layout
        filter_layout = QHBoxLayout()

        filter_label = QLabel("Filter by Type:")
        filter_label.setStyleSheet("font-weight: 500;")
        filter_layout.addWidget(filter_label)

        self.type_filter = QComboBox()
        self.type_filter.addItems(["All", "Sources", "Samples", "Other Materials"])
        self.type_filter.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.type_filter)

        filter_layout.addStretch()
        self.add_layout(filter_layout)

        # Main splitter: table (left) + details preview (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: Materials table
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Type", "ID", "Characteristics", "Derives From"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 250)
        self.table.setColumnWidth(4, 150)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        # Connect selection change to update preview
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        self.set_expanding(self.table)
        left_layout.addWidget(self.table)

        # Right panel: Material details preview
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Details card
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

        details_header = QLabel("Material Details")
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
            '<span style="color: #666;">Select a material to view details</span>'
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

        add_btn = PrimaryButton("Add Material")
        add_btn.clicked.connect(self._on_add_material)
        buttons_layout.addWidget(add_btn)

        edit_btn = ActionButton("Edit Selected")
        edit_btn.clicked.connect(self._on_edit_material)
        buttons_layout.addWidget(edit_btn)

        delete_btn = ActionButton("Delete Selected")
        delete_btn.clicked.connect(self._on_delete_material)
        buttons_layout.addWidget(delete_btn)

        refresh_btn = ActionButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        buttons_layout.addWidget(refresh_btn)

        buttons_layout.addStretch()

        self.add_layout(buttons_layout)

    def refresh(self):
        """Refresh the materials table."""
        self.table.setRowCount(0)
        self.materials = []
        self.preview_helper = None

        # Reset details panel
        self.details_browser.setHtml(
            '<span style="color: #666;">Select a material to view details</span>'
        )

        # Check if study is selected
        if not self.main_window.current_study:
            return

        # Load materials from study data
        study_data = self.main_window.get_study_data()

        if not study_data:
            return

        # Build preview helper for ISA-JSON resolution
        try:
            self.preview_helper = ISAJsonPreviewHelper(study_data)
        except Exception as e:
            print(f"[MaterialsPage] Error building preview helper: {e}")

        # Always reinitialize material manager to pick up the latest study data
        # (the study_data dict is replaced when a new study is selected)
        inv_id = self.main_window.current_investigation or "inv_1"
        study_id = self.main_window.current_study or "study_1"
        self.material_manager = MaterialManager(
            study_data,
            self.main_window.get_directory_manager(),
            investigation_id=inv_id,
            study_id=study_id,
        )

        # Get all materials
        self.materials = self.material_manager.get_all_materials()

        # If study-level materials are empty, try to collect from assay-level references
        if not self.materials:
            self.materials = self._collect_assay_materials(study_data)

        # Apply filter
        filtered_materials = self._apply_filter(self.materials)

        # Populate table
        for material in filtered_materials:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(material.get("name", "")))

            material_type = material.get("materialType", "")
            type_display = material_type
            if material_type == "source":
                type_display = "Source"
            elif material_type == "sample":
                type_display = "Sample"
            elif material_type == "otherMaterial":
                type_display = "Other"
            self.table.setItem(row, 1, QTableWidgetItem(type_display))

            self.table.setItem(row, 2, QTableWidgetItem(material.get("@id", "")))

            # Characteristics count
            characteristics = material.get("characteristics", [])
            char_count = len(characteristics)
            char_text = f"{char_count} characteristic(s)"
            self.table.setItem(row, 3, QTableWidgetItem(char_text))

            # Derives from
            derives_from = material.get("derivesFrom", [])
            derives_text = ", ".join(derives_from[:3])  # Show first 3
            if len(derives_from) > 3:
                derives_text += f" (+{len(derives_from) - 3} more)"
            self.table.setItem(row, 4, QTableWidgetItem(derives_text))

    def _collect_assay_materials(self, study_data: dict) -> list:
        """
        Collect materials from assay-level references when study-level materials are empty.
        This handles cases like E100 where samples only exist as @id references in assays.
        """
        materials = []
        seen_ids = set()

        # Get the study
        study = study_data
        if (
            "studies" in study_data
            and isinstance(study_data["studies"], list)
            and len(study_data["studies"]) > 0
        ):
            study = study_data["studies"][0]

        # Collect from assay-level materials section
        for assay in study.get("assays", []):
            assay_materials = assay.get("materials", {})
            for material_type, key in [
                ("sample", "samples"),
                ("source", "sources"),
                ("otherMaterial", "otherMaterials"),
            ]:
                for mat in assay_materials.get(key, []):
                    mat_id = mat.get("@id", "")
                    if mat_id and mat_id not in seen_ids:
                        seen_ids.add(mat_id)
                        # Try to resolve name from preview helper
                        name = mat.get("name", "")
                        if not name and self.preview_helper:
                            name = self.preview_helper.resolve_material_name(mat_id)
                        if name == mat_id:
                            # Extract readable name from @id
                            name = mat_id.split("#")[-1] if "#" in mat_id else mat_id
                            name = (
                                name.replace("sample_", "").replace("source_", "").replace("_", " ")
                            )
                        materials.append(
                            {
                                "@id": mat_id,
                                "name": name,
                                "materialType": material_type,
                                "characteristics": mat.get("characteristics", []),
                                "factorValues": mat.get("factorValues", []),
                                "derivesFrom": mat.get("derivesFrom", []),
                            }
                        )

        # Also collect from processSequence inputs/outputs
        for assay in study.get("assays", []):
            for proc in assay.get("processSequence", []):
                for inp in proc.get("inputs", []):
                    inp_id = inp.get("@id", "") if isinstance(inp, dict) else str(inp)
                    if inp_id and inp_id not in seen_ids:
                        seen_ids.add(inp_id)
                        name = inp_id.split("#")[-1] if "#" in inp_id else inp_id
                        name = name.replace("sample_", "").replace("source_", "").replace("_", " ")
                        materials.append(
                            {
                                "@id": inp_id,
                                "name": name,
                                "materialType": "sample",
                                "characteristics": [],
                                "factorValues": [],
                                "derivesFrom": [],
                            }
                        )

        return materials

    def _apply_filter(self, materials):
        """Apply the current filter to materials."""
        if self.current_filter == "All":
            return materials

        type_map = {"Sources": "source", "Samples": "sample", "Other Materials": "otherMaterial"}

        filter_type = type_map.get(self.current_filter, "")
        return [m for m in materials if m.get("materialType", "") == filter_type]

    def _on_filter_changed(self, filter_type):
        """Handle filter change."""
        self.current_filter = filter_type
        self.refresh()

    def _on_selection_changed(self):
        """Handle table selection change - update the details preview."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.details_browser.setHtml(
                '<span style="color: #666;">Select a material to view details</span>'
            )
            return

        row = selected_rows[0].row()
        filtered_materials = self._apply_filter(self.materials)

        if row < len(filtered_materials):
            material = filtered_materials[row]
            self._update_material_preview(material)
        else:
            self.details_browser.setHtml(
                '<span style="color: #666;">Select a material to view details</span>'
            )

    def _update_material_preview(self, material: dict):
        """
        Update the details preview for a material.

        Args:
            material: Material dict from ISA-JSON
        """
        if self.preview_helper:
            html = self.preview_helper.get_material_preview_html(material)
            self.details_browser.setHtml(html)
        else:
            # Fallback: basic display without ISA-JSON resolution
            html_parts = []
            name = material.get("name", "Unknown")
            mat_type = material.get("materialType", "")
            mat_id = material.get("@id", "")
            html_parts.append(
                f'<b style="font-size: 14px;">{ISAJsonPreviewHelper._escape(name)}</b><br>'
            )
            html_parts.append(
                f'<span style="color: #666;">Type:</span> {ISAJsonPreviewHelper._escape(mat_type)}<br>'  # noqa: E501
            )
            if mat_id:
                html_parts.append(
                    f'<span style="color: #666;">ID:</span> <code>{ISAJsonPreviewHelper._escape(mat_id)}</code>'  # noqa: E501
                )
            self.details_browser.setHtml("\n".join(html_parts))

    def _on_add_material(self):
        """Handle add material button click."""
        # Check if study is selected
        if not self.main_window.current_study:
            QMessageBox.information(
                self, "No Study Selected", "Please select a study first from the Studies page."
            )
            return

        # Get templates
        templates = self.material_manager.get_all_templates()

        # Open dialog
        dialog = MaterialDialog(
            self, dm=self.main_window.get_directory_manager(), material_data={}, templates=templates
        )
        dialog.setWindowTitle("Create Material")

        if dialog.exec():
            material_data = dialog.get_material_data()

            # Add to material manager
            material_type = material_data.get("materialType", "otherMaterial")
            self.material_manager.add_material(material_data, material_type)

            # Save to study file
            self.material_manager.save_to_study_file(
                self.main_window.current_investigation, self.main_window.current_study
            )

            self.main_window.status_bar.show_message(
                f"Material '{material_data['name']}' created successfully!"
            )
            self.refresh()

    def _on_edit_material(self):
        """Handle edit material button click."""
        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select a material to edit.")
            return

        # Get the first selected row
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()

        # Get material from filtered materials
        filtered_materials = self._apply_filter(self.materials)
        if row < len(filtered_materials):
            material_data = filtered_materials[row]
        else:
            return

        # Get templates
        templates = self.material_manager.get_all_templates()

        # Open dialog with existing data
        dialog = MaterialDialog(
            self,
            dm=self.main_window.get_directory_manager(),
            material_data=material_data,
            templates=templates,
        )
        dialog.setWindowTitle(f"Edit Material: {material_data.get('name', '')}")

        if dialog.exec():
            updated_data = dialog.get_material_data()

            # Update material
            material_id = material_data.get("@id", "")
            self.material_manager.update_material(material_id, updated_data)

            # Save to study file
            self.material_manager.save_to_study_file(
                self.main_window.current_investigation, self.main_window.current_study
            )

            self.main_window.status_bar.show_message(
                f"Material '{updated_data['name']}' updated successfully!"
            )
            self.refresh()

    def _on_delete_material(self):
        """Handle delete material button click."""
        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select a material to delete.")
            return

        # Get the first selected row
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()

        # Get material from filtered materials
        filtered_materials = self._apply_filter(self.materials)
        if row < len(filtered_materials):
            material_data = filtered_materials[row]
        else:
            return
        material_name = material_data.get("name", "")
        material_id = material_data.get("@id", "")

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete material '{material_name}'?\n\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Delete material
            self.material_manager.remove_material(material_id)

            # Save to study file
            self.material_manager.save_to_study_file(
                self.main_window.current_investigation, self.main_window.current_study
            )

            self.main_window.status_bar.show_message(
                f"Material '{material_name}' deleted successfully!"
            )
            self.refresh()

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

    def save_data(self):
        """Save current page data as complete ISA-JSON format."""
        if not self.material_manager or not self.main_window.current_study:
            return

        study_data = self.main_window.get_study_data() or {}
        if not study_data:
            return

        # Export to complete ISA-JSON format
        investigation_id = self.main_window.current_investigation or "inv_1"
        study_id = self.main_window.current_study or "study_1"

        exporter = ISAJsonExporter(study_data, investigation_id, study_id)
        isa_json = exporter.export_complete_isa_json()

        # Save to file
        dm = self.main_window.get_directory_manager()
        study_json_path = dm.get_study_json_path(investigation_id, study_id)

        try:
            with open(study_json_path, "w", encoding="utf-8") as f:
                json.dump(isa_json, f, indent=2)

            # Update main window study data with the simple structure (not complete ISA-JSON)
            self.main_window.study_data = study_data
            self.main_window.status_bar.show_message("Saved as complete ISA-JSON!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save materials:\n{str(e)}")

    def validate_data(self):
        """Validate current page data."""
        return True, []
