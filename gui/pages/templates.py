"""
Templates page for the ISA-JSON Data Steward GUI.

Includes ontology reference verification indicators showing which
termSource/termAccession references have been verified against cached ontologies.
"""

import json
from pathlib import Path
from typing import Dict, List, Set

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from utils.logging_config import get_logger

from ..agent_tools.ids import set_test_id
from ..dialogs.template_editor import TemplateEditorDialog
from ..widgets.common import ActionButton, PrimaryButton, SectionHeader, set_ui_role
from .base_page import ScrollablePage

logger = get_logger(__name__)


class TemplatesPage(ScrollablePage):
    """Templates page for managing assay and protocol templates."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.current_template_data = None
        self._verified_uris: Set[str] = set()
        self._load_verification_data()
        self.setup_templates_ui()

    def _load_verification_data(self):
        """Load verification report data if available."""
        try:
            dm = self.main_window.get_directory_manager()
            report_path = dm.base_path / "ontologies" / "validation_report.json"
            if report_path.exists():
                with open(report_path, "r", encoding="utf-8") as f:
                    report = json.load(f)
                self._verified_uris = {
                    ref["termAccession"]
                    for ref in report.get("verified", [])
                    if ref.get("termAccession")
                }
        except Exception:
            self._verified_uris = set()

    def _check_refs_in_template(self, data: dict) -> Dict[str, List[dict]]:
        """
        Check all ontology references in a template and categorize them.

        Returns:
            Dict with keys 'verified', 'unverified', 'no_accession' mapping to
            lists of ref dicts.
        """
        results: Dict[str, List[dict]] = {"verified": [], "unverified": [], "no_accession": []}
        self._extract_and_check_refs(data, results)
        return results

    def _extract_and_check_refs(self, value, results: dict, path: str = ""):
        """Recursively extract and check ontology references."""
        if isinstance(value, dict):
            term_source = value.get("termSource")
            term_accession = value.get("termAccession")

            if term_source:
                if term_accession:
                    if term_accession in self._verified_uris:
                        results["verified"].append(
                            {
                                "termSource": term_source,
                                "termAccession": term_accession,
                                "label": value.get("annotationValue", ""),
                            }
                        )
                    else:
                        results["unverified"].append(
                            {
                                "termSource": term_source,
                                "termAccession": term_accession,
                                "label": value.get("annotationValue", ""),
                            }
                        )
                else:
                    results["no_accession"].append(
                        {
                            "termSource": term_source,
                            "label": value.get("annotationValue", ""),
                        }
                    )

            for key, child in value.items():
                self._extract_and_check_refs(child, results, f"{path}.{key}")

        elif isinstance(value, list):
            for i, item in enumerate(value):
                self._extract_and_check_refs(item, results, f"{path}[{i}]")

    def setup_templates_ui(self):
        """Set up the templates UI."""
        # Header
        self.add_widget(SectionHeader("Template Management"))

        # Template type selection
        type_layout = QHBoxLayout()

        type_label = QLabel("Template Type:")
        type_label.setStyleSheet("font-weight: 500;")
        type_layout.addWidget(type_label)

        self.type_combo = QComboBox()
        set_test_id(self.type_combo, "page.templates.typeCombo")
        self.type_combo.addItems(["Assay Templates", "Protocol Templates"])
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        type_layout.addWidget(self.type_combo)

        type_layout.addStretch()

        self.add_layout(type_layout)

        # Splitter for list and preview
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Template list
        list_layout = QVBoxLayout()
        list_label = QLabel("Available Templates")
        list_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        list_layout.addWidget(list_label)

        self.template_list = QListWidget()
        set_test_id(self.template_list, "page.templates.templateList")
        self.template_list.setAlternatingRowColors(True)
        self.template_list.setMinimumHeight(400)
        self.template_list.itemSelectionChanged.connect(self._on_template_selected)
        self.set_expanding(self.template_list)
        list_layout.addWidget(self.template_list)

        # U-13: empty-state placeholder (muted via the theme QSS uiRole rule),
        # shown while the list is empty and hidden once populated.
        self.list_placeholder = QLabel("No templates found — use Create Template")
        set_test_id(self.list_placeholder, "page.templates.listPlaceholder")
        set_ui_role(self.list_placeholder, "muted")
        self.list_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_placeholder.setWordWrap(True)
        self.set_expanding(self.list_placeholder)
        list_layout.addWidget(self.list_placeholder)

        list_widget = QWidget()
        list_widget.setLayout(list_layout)
        splitter.addWidget(list_widget)

        # Preview panel
        preview_layout = QVBoxLayout()

        preview_label = QLabel("Template Preview")
        preview_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        preview_layout.addWidget(preview_label)

        # Preview content label (rich text when a template is selected).
        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        set_ui_role(self.preview_label, "muted")
        self.preview_label.setStyleSheet("padding: 16px;")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        preview_layout.addWidget(self.preview_label)

        # U-13: centered empty-state placeholder for the preview pane.
        self.preview_placeholder = QLabel("Select a template to preview")
        set_test_id(self.preview_placeholder, "page.templates.previewPlaceholder")
        set_ui_role(self.preview_placeholder, "muted")
        self.preview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_placeholder.setWordWrap(True)
        self.set_expanding(self.preview_placeholder)
        preview_layout.addWidget(self.preview_placeholder)

        preview_widget = QWidget()
        preview_widget.setLayout(preview_layout)

        splitter.addWidget(preview_widget)

        # Set stretch factors for proportional sizing
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        self.set_expanding(splitter)
        self.add_widget(splitter)

        # Buttons
        # U-08: a 2-column grid keeps the row's minimum width under the
        # content viewport (a single row of four buttons forced a
        # horizontal scrollbar with the theme QSS applied).
        buttons_layout = QGridLayout()
        buttons_layout.setSpacing(12)

        create_btn = PrimaryButton("Create Template")
        set_test_id(create_btn, "page.templates.createButton")
        create_btn.clicked.connect(self._on_create_template)
        buttons_layout.addWidget(create_btn, 0, 0)

        edit_btn = ActionButton("Edit Selected")
        set_test_id(edit_btn, "page.templates.editButton")
        edit_btn.clicked.connect(self._on_edit_template)
        buttons_layout.addWidget(edit_btn, 0, 1)

        import_btn = ActionButton("Import Template")
        set_test_id(import_btn, "page.templates.importButton")
        import_btn.clicked.connect(self._on_import_template)
        buttons_layout.addWidget(import_btn, 1, 0)

        export_btn = ActionButton("Export Selected")
        set_test_id(export_btn, "page.templates.exportButton")
        export_btn.clicked.connect(self._on_export_template)
        buttons_layout.addWidget(export_btn, 1, 1)

        self.add_layout(buttons_layout)

        # U-11: Edit/Export start disabled until a template is selected.
        self.edit_btn = edit_btn
        self.export_btn = export_btn
        self._update_action_states()

        # Load initial templates after UI is fully set up
        self._load_templates("assay")

    def _update_action_states(self):
        """Enable/disable action buttons per current selection (U-11)."""
        has_selection = bool(self.template_list.selectedItems())
        self.edit_btn.setEnabled(has_selection)
        self.export_btn.setEnabled(has_selection)

    def _update_empty_state(self):
        """Toggle the U-13 empty-state placeholder against the template list.

        The placeholder and the list are mutually exclusive: the placeholder
        shows while the list is empty and hides once populated.
        """
        has_items = self.template_list.count() > 0
        self.template_list.setVisible(has_items)
        self.list_placeholder.setVisible(not has_items)

    def _set_preview_empty(self):
        """Show the preview-pane empty-state placeholder (U-13)."""
        self.current_template_data = None
        self.preview_label.clear()
        self.preview_label.setVisible(False)
        self.preview_placeholder.setVisible(True)

    def _set_preview_content(self):
        """Show the preview content label and hide the placeholder (U-13)."""
        self.preview_placeholder.setVisible(False)
        self.preview_label.setVisible(True)

    def _load_templates(self, template_type: str):
        """Load templates of the specified type."""
        self.template_list.clear()
        self._set_preview_empty()
        self._update_action_states()
        self._update_empty_state()  # U-13: empty list shows its placeholder

        base_path = self.main_window.get_templates_root()

        if template_type == "assay":
            template_dir = base_path / "assay_templates"
        else:  # protocol
            template_dir = base_path / "protocol_templates"

        if not template_dir.exists():
            self.main_window.status_bar.show_message(
                f"Template directory not found: {template_dir}"
            )
            return

        # Load template files
        for json_file in sorted(template_dir.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    template_data = json.load(f)

                name = template_data.get("name", json_file.stem)
                description = template_data.get("description", "")

                # Create list item with template data
                item = QListWidgetItem(name)
                item.setData(
                    Qt.ItemDataRole.UserRole, {"filename": json_file.name, "data": template_data}
                )
                item.setToolTip(description)
                self.template_list.addItem(item)
            except Exception as e:
                logger.warning(f"Error loading template {json_file}: {e}")

        self.main_window.status_bar.show_message(
            f"Loaded {self.template_list.count()} {template_type} templates"
        )
        self._update_empty_state()  # U-13: populated list hides its placeholder

    def _on_type_changed(self, template_type: str):
        """Handle template type change."""
        if "Assay" in template_type:
            self._load_templates("assay")
        else:
            self._load_templates("protocol")

    def _on_template_selected(self):
        """Handle template selection change."""
        self._update_action_states()
        selected_items = self.template_list.selectedItems()

        if not selected_items:
            self._set_preview_empty()
            return

        item = selected_items[0]
        template_info = item.data(Qt.ItemDataRole.UserRole)
        self.current_template_data = template_info["data"]

        # Display preview
        data = template_info["data"]
        name = data.get("name", "Unknown")
        description = data.get("description", "No description")

        preview_html = f"""
        <h3>{name}</h3>
        <p><b>Description:</b> {description}</p>
        <p><b>File:</b> {template_info.get('filename', 'Unknown')}</p>
        """

        # Add additional fields if present
        if "parameters" in data:
            params = data["parameters"]
            if isinstance(params, list):
                preview_html += f"<p><b>Parameters:</b> {len(params)} items</p>"

        if "protocol_steps" in data:
            steps = data["protocol_steps"]
            if isinstance(steps, list):
                preview_html += f"<p><b>Protocol Steps:</b> {len(steps)} steps</p>"

        # Ontology verification status
        if self._verified_uris:
            ref_status = self._check_refs_in_template(data)
            n_verified = len(ref_status["verified"])
            n_unverified = len(ref_status["unverified"])
            n_no_accession = len(ref_status["no_accession"])
            total = n_verified + n_unverified + n_no_accession

            if total > 0:
                preview_html += "<hr><p><b>Ontology References:</b></p>"

                if n_verified > 0:
                    preview_html += (
                        f"<p style='color: green;'>" f"&#10003; {n_verified} verified</p>"
                    )

                if n_unverified > 0:
                    preview_html += (
                        f"<p style='color: red;'>"
                        f"&#10007; {n_unverified} unverified "
                        f"(URI not found in source ontology)</p>"
                    )
                    for ref in ref_status["unverified"][:5]:
                        preview_html += (
                            f"<p style='color: red; margin-left: 16px; font-size: 11px;'>"
                            f"  {ref['termSource']}: {ref['termAccession']}</p>"
                        )
                    if n_unverified > 5:
                        preview_html += (
                            f"<p style='color: gray; margin-left: 16px; font-size: 11px;'>"
                            f"  ... and {n_unverified - 5} more</p>"
                        )

                if n_no_accession > 0:
                    preview_html += (
                        f"<p style='color: orange;'>"
                        f"&#9888; {n_no_accession} without termAccession "
                        f"(cannot verify)</p>"
                    )
            else:
                preview_html += (
                    "<p style='color: gray;'><i>No ontology references in this template</i></p>"
                )
        else:
            preview_html += (
                "<p style='color: gray;'><i>"
                "Run <code>python scripts/verify_ontology_refs.py</code> to enable "
                "verification indicators"
                "</i></p>"
            )

        self._set_preview_content()
        self.preview_label.setText(preview_html)

    def _on_create_template(self):
        """Handle create template button click."""
        template_type = "assay" if "Assay" in self.type_combo.currentText() else "protocol"

        dialog = TemplateEditorDialog(self, template_type=template_type)
        dialog.setWindowTitle("Create Template")
        if dialog.exec():
            template_data = dialog.get_template_data()

            # Save template to the profile-aware templates root
            base_path = self.main_window.get_templates_root()

            if template_type == "assay":
                template_dir = base_path / "assay_templates"
            else:
                template_dir = base_path / "protocol_templates"

            template_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename
            name = template_data.get("name", "new_template")
            filename = f"{name.lower().replace(' ', '_')}.json"
            file_path = template_dir / filename

            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(template_data, f, indent=2)

                self.main_window.status_bar.show_message(f"Template '{name}' created successfully!")
                self._load_templates(template_type)
            except Exception as e:
                self.main_window.status_bar.show_message(f"Error creating template: {e}")

    def _on_edit_template(self):
        """Handle edit template button click."""
        selected = self.template_list.selectedItems()
        if not selected:
            self.main_window.status_bar.show_message("Please select a template to edit")
            return

        item = selected[0]
        template_info = item.data(Qt.ItemDataRole.UserRole)
        template_type = "assay" if "Assay" in self.type_combo.currentText() else "protocol"

        dialog = TemplateEditorDialog(
            self, template_type=template_type, template_data=template_info["data"]
        )
        if dialog.exec():
            template_data = dialog.get_template_data()

            # Save template to the profile-aware templates root
            base_path = self.main_window.get_templates_root()

            if template_type == "assay":
                template_dir = base_path / "assay_templates"
            else:
                template_dir = base_path / "protocol_templates"

            # Use original filename
            file_path = template_dir / template_info["filename"]

            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(template_data, f, indent=2)

                self.main_window.status_bar.show_message(
                    f"Template '{template_data['name']}' updated successfully!"
                )
                self._load_templates(template_type)
            except Exception as e:
                self.main_window.status_bar.show_message(f"Error updating template: {e}")

    def _on_import_template(self):
        """Handle import template button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Template File", "", "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    template_data = json.load(f)

                # Determine template type from content
                template_type = "assay" if "assay_type" in template_data else "protocol"

                # Save to appropriate directory in the profile-aware templates root
                base_path = self.main_window.get_templates_root()

                if template_type == "assay":
                    template_dir = base_path / "assay_templates"
                else:
                    template_dir = base_path / "protocol_templates"

                template_dir.mkdir(parents=True, exist_ok=True)

                # Use original filename
                dest_path = template_dir / Path(file_path).name

                with open(dest_path, "w", encoding="utf-8") as f:
                    json.dump(template_data, f, indent=2)

                self.main_window.status_bar.show_message(f"Imported: {Path(file_path).name}")
                self._load_templates(template_type)
            except Exception as e:
                self.main_window.status_bar.show_message(f"Error importing template: {e}")

    def _on_export_template(self):
        """Handle export template button click."""
        selected = self.template_list.selectedItems()
        if not selected:
            self.main_window.status_bar.show_message("Please select a template to export")
            return

        item = selected[0]
        template_info = item.data(Qt.ItemDataRole.UserRole)
        template_data = template_info["data"]

        # Get save location
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Template",
            template_info.get("name", "template.json"),
            "JSON Files (*.json);;All Files (*)",
        )

        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(template_data, f, indent=2)

                self.main_window.status_bar.show_message(f"Exported: {Path(save_path).name}")
            except Exception as e:
                self.main_window.status_bar.show_message(f"Error exporting template: {e}")

    def on_enter(self):
        """Called when the page is shown."""
        self._load_verification_data()
        template_type = "assay" if "Assay" in self.type_combo.currentText() else "protocol"
        self._load_templates(template_type)

    def on_exit(self):
        """Called when the page is hidden."""
        pass

    def set_investigation(self, investigation_id: str):
        """Set the current investigation."""
        pass

    def set_study(self, study_id: str):
        """Set the current study."""
        pass
