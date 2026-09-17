"""
Studies page for the ISA-JSON Data Steward GUI.
"""

import json

# Import utilities
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ..dialogs.investigation_dialog import InvestigationDialog
from ..dialogs.study_wizard import StudyWizard
from ..widgets.common import ActionButton, PrimaryButton, SectionHeader
from .base_page import ScrollablePage

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.isa_json_exporter import ISAJsonExporter  # noqa: E402
from utils.isa_json_preview_helpers import ISAJsonPreviewHelper  # noqa: E402


class StudiesPage(ScrollablePage):
    """Studies page for managing investigations and studies."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.preview_helper = None
        self._study_data_cache = {}  # Cache study data by (inv_id, study_id)
        self.setup_studies_ui()

    def setup_studies_ui(self):
        """Set up the studies UI."""
        # Header
        self.add_widget(SectionHeader("Investigations and Studies"))

        # Main splitter: tree (left) + details (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: Tree widget for investigations/studies
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Type", "ID"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setMinimumHeight(400)

        # Enable selection
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)

        # Connect double-click to open and single click to preview
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemClicked.connect(self._on_item_clicked)

        self.set_expanding(self.tree)

        # Configure header resize modes - Interactive for user-adjustable columns
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 120)
        self.tree.setColumnWidth(2, 200)

        left_layout.addWidget(self.tree)

        # Right panel: Details preview
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

        details_header = QLabel("Details")
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
            '<span style="color: #666;">Select an investigation or study to view details</span>'
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

        refresh_btn = ActionButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        buttons_layout.addWidget(refresh_btn)

        create_inv_btn = PrimaryButton("Create New Investigation")
        create_inv_btn.clicked.connect(self._on_create_investigation)
        buttons_layout.addWidget(create_inv_btn)

        create_btn = PrimaryButton("Create New Study")
        create_btn.clicked.connect(self._on_create_study)
        buttons_layout.addWidget(create_btn)

        delete_btn = ActionButton("Delete Selected")
        delete_btn.clicked.connect(self._on_delete)
        buttons_layout.addWidget(delete_btn)

        buttons_layout.addStretch()

        self.add_layout(buttons_layout)

        # Load data
        self.refresh()

    def refresh(self):
        """Refresh the investigations and studies list."""
        # Save current selection
        selected_items = self.tree.selectedItems()
        selected_data = None
        if selected_items:
            item = selected_items[0]
            selected_data = (item.text(0), item.text(1), item.text(2))

        self.tree.clear()

        dm = self.main_window.get_directory_manager()
        investigations = dm.list_investigations()

        for inv_id in investigations:
            inv_item = QTreeWidgetItem(self.tree)
            inv_item.setText(0, inv_id)
            inv_item.setText(1, "Investigation")
            inv_item.setText(2, inv_id)

            studies = dm.list_studies(inv_id)
            for study_id in studies:
                study_item = QTreeWidgetItem(inv_item)
                study_item.setText(0, study_id)
                study_item.setText(1, "Study")
                study_item.setText(2, study_id)

                # Load study metadata if available
                try:
                    study_json = dm.get_study_json_path(inv_id, study_id)
                    if study_json.exists():
                        with open(study_json, "r", encoding="utf-8") as f:
                            study_data = json.load(f)
                            # Handle both simple study structure and complete ISA-JSON structure
                            if (
                                "studies" in study_data
                                and isinstance(study_data["studies"], list)
                                and len(study_data["studies"]) > 0
                            ):
                                # Complete ISA-JSON structure: study name is in studies[0].title
                                study_name = study_data["studies"][0].get("title", "")
                            else:
                                # Simple study structure
                                study_name = study_data.get("study_name", "")
                            if study_name:
                                study_item.setText(0, f"{study_id} - {study_name}")
                except Exception as e:  # noqa: F841
                    pass  # Skip if can't load metadata

        self.tree.expandAll()

        # Restore selection
        if selected_data:
            for i in range(self.tree.topLevelItemCount()):
                inv_item = self.tree.topLevelItem(i)
                if inv_item.text(0) == selected_data[0]:
                    inv_item.setSelected(True)
                    break
                for j in range(inv_item.childCount()):
                    study_item = inv_item.child(j)
                    if study_item.text(2) == selected_data[2]:
                        study_item.setSelected(True)
                        break

    def _on_create_investigation(self):
        """Handle create investigation button click."""
        dm = self.main_window.get_directory_manager()

        dialog = InvestigationDialog(self, dm=dm)
        if dialog.exec():
            inv_data = dialog.get_investigation_data()

            try:
                inv_id = inv_data["investigation_id"]
                inv_path = dm.create_investigation_directory(inv_id)

                if inv_path is None:
                    QMessageBox.critical(
                        self, "Error", f"Failed to create investigation directory for '{inv_id}'."
                    )
                    return

                # Save investigation metadata JSON
                inv_json_path = inv_path / f"{inv_id}.json"
                with open(inv_json_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "identifier": inv_id,
                            "title": inv_data["title"],
                            "description": inv_data["description"],
                            "created_at": inv_data["created_at"],
                            "studies": [],
                        },
                        f,
                        indent=2,
                    )

                # Auto-select the new investigation
                self.main_window.set_investigation(inv_id)

                self.main_window.status_bar.show_message(
                    f"Investigation '{inv_data['title']}' created successfully!"
                )
                self.refresh()

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create investigation:\n{str(e)}")

    def _on_create_study(self):
        """Handle create study button click."""
        dm = self.main_window.get_directory_manager()

        wizard = StudyWizard(self, dm=dm)
        if wizard.exec():
            study_data = wizard.get_study_data()

            try:
                # Create study directory
                dm.create_study_directory(study_data["investigation_id"], study_data["study_id"])

                # Copy sequence file if provided
                sequence_file_path = study_data.get("sequence_file_path")
                copied_sequence_path = None
                if sequence_file_path and Path(sequence_file_path).exists():
                    copied_sequence_path = dm.copy_sequence_file_to_study(
                        Path(sequence_file_path),
                        study_data["investigation_id"],
                        study_data["study_id"],
                    )

                # Update study_data with copied path for ISA-JSON export
                if copied_sequence_path:
                    # Store relative path from study directory
                    study_path = dm.get_study_path(
                        study_data["investigation_id"], study_data["study_id"]
                    )
                    relative_path = copied_sequence_path.relative_to(study_path)
                    study_data["copied_sequence_path"] = str(relative_path)

                # Export to complete ISA-JSON format
                investigation_id = study_data.get("investigation_id", "inv_1")
                study_id = study_data.get("study_id", "study_1")

                exporter = ISAJsonExporter(study_data, investigation_id, study_id)
                isa_json = exporter.export_complete_isa_json()

                # Save study JSON
                study_json_path = dm.get_study_json_path(investigation_id, study_id)

                with open(study_json_path, "w", encoding="utf-8") as f:
                    json.dump(isa_json, f, indent=2)

                self.main_window.status_bar.show_message(
                    f"Study '{study_data['study_name']}' created successfully!"
                )
                self.refresh()

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create study:\n{str(e)}")

    def _on_delete(self):
        """Handle delete button click."""
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.information(
                self, "No Selection", "Please select an investigation or study to delete."
            )
            return

        item = selected[0]
        item_type = item.text(1)
        item_name = item.text(0)

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete the {item_type.lower()} '{item_name}'?\n\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.No:
            return

        dm = self.main_window.get_directory_manager()

        try:
            if item_type == "Study":
                # Delete study
                inv_id = item.parent().text(0)
                study_id = item.text(2)
                dm.delete_study(inv_id, study_id)

                # Clear current study if it was deleted
                if self.main_window.current_study == study_id:
                    self.main_window.set_study(None)

            elif item_type == "Investigation":
                # Delete investigation (and all studies)
                inv_id = item.text(0)
                dm.delete_investigation(inv_id)

                # Clear current context if it was deleted
                if self.main_window.current_investigation == inv_id:
                    self.main_window.set_investigation(None)
                    self.main_window.set_study(None)

            self.main_window.status_bar.show_message(f"{item_type} deleted successfully!")
            self.refresh()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete {item_type.lower()}:\n{str(e)}")

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double-click on tree item."""
        item_type = item.text(1)

        if item_type == "Investigation":
            inv_id = item.text(0)
            self.main_window.set_investigation(inv_id)
            self.main_window.status_bar.show_message(f"Selected investigation: {inv_id}")

        elif item_type == "Study":
            parent = item.parent()
            if parent is None:
                return
            inv_id = parent.text(0)
            study_id = item.text(2)
            self.main_window.set_investigation(inv_id)
            self.main_window.set_study(study_id)
            self.main_window.status_bar.show_message(f"Selected study: {study_id}")

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle single click on tree item - show details preview."""
        item_type = item.text(1)

        if item_type == "Investigation":
            inv_id = item.text(0)
            self._show_investigation_details(inv_id)
        elif item_type == "Study":
            parent = item.parent()
            if parent is None:
                return
            inv_id = parent.text(0)
            study_id = item.text(2)
            self._show_study_details(inv_id, study_id)

    def _show_investigation_details(self, inv_id: str):
        """Show investigation details in the preview panel."""
        dm = self.main_window.get_directory_manager()

        html_parts = []
        html_parts.append(
            f'<b style="font-size: 14px;">{ISAJsonPreviewHelper._escape(inv_id)}</b><br>'
        )
        html_parts.append('<span style="color: #666;">Type:</span> Investigation<br>')

        # Load investigation metadata if available
        try:
            inv_path = dm.get_investigation_path(inv_id)
            inv_json_path = inv_path / f"{inv_id}.json"
            if inv_json_path.exists():
                with open(inv_json_path, "r", encoding="utf-8") as f:
                    inv_meta = json.load(f)
                title = inv_meta.get("title", "")
                description = inv_meta.get("description", "")
                if title:
                    html_parts.append(
                        f'<span style="color: #666;">Title:</span> '
                        f"{ISAJsonPreviewHelper._escape(title)}<br>"
                    )
                if description:
                    html_parts.append(
                        f'<span style="color: #666;">Description:</span> '
                        f"{ISAJsonPreviewHelper._escape(description)}<br>"
                    )
        except Exception:
            pass

        html_parts.append("<br>")

        # List studies
        try:
            studies = dm.list_studies(inv_id)
            if studies:
                html_parts.append(f"<b>Studies ({len(studies)}):</b><br>")
                html_parts.append('<ul style="margin-top: 2px;">')
                for study_id in studies:
                    # Try to load study title
                    study_title = ""
                    try:
                        study_json = dm.get_study_json_path(inv_id, study_id)
                        if study_json.exists():
                            with open(study_json, "r", encoding="utf-8") as f:
                                study_data = json.load(f)
                            if (
                                "studies" in study_data
                                and isinstance(study_data["studies"], list)
                                and len(study_data["studies"]) > 0
                            ):
                                study_title = study_data["studies"][0].get("title", "")
                            else:
                                study_title = study_data.get("title", "")
                    except Exception:
                        pass

                    display = ISAJsonPreviewHelper._escape(study_id)
                    if study_title:
                        display += f" - {ISAJsonPreviewHelper._escape(study_title)}"
                    html_parts.append(f"<li>{display}</li>")
                html_parts.append("</ul>")
            else:
                html_parts.append('<span style="color: #999;">No studies found</span>')
        except Exception as e:
            html_parts.append(
                f'<span style="color: #dc3545;">Error: {ISAJsonPreviewHelper._escape(str(e))}</span>'  # noqa: E501
            )

        self.details_browser.setHtml("\n".join(html_parts))

    def _show_study_details(self, inv_id: str, study_id: str):
        """Show study details in the preview panel using ISA-JSON data."""
        dm = self.main_window.get_directory_manager()

        try:
            study_json_path = dm.get_study_json_path(inv_id, study_id)
            if not study_json_path.exists():
                self.details_browser.setHtml(
                    f'<span style="color: #999;">Study file not found: {ISAJsonPreviewHelper._escape(study_id)}</span>'  # noqa: E501
                )
                return

            with open(study_json_path, "r", encoding="utf-8") as f:
                study_data = json.load(f)

            preview_helper = ISAJsonPreviewHelper(study_data)
            html = preview_helper.get_study_preview_html()
            self.details_browser.setHtml(html)

        except Exception as e:
            self.details_browser.setHtml(
                f'<span style="color: #dc3545;">Error loading study: {ISAJsonPreviewHelper._escape(str(e))}</span>'  # noqa: E501
            )

    def on_enter(self):
        """Called when the page is shown."""
        self.refresh()

    def on_exit(self):
        """Called when the page is hidden."""
        pass

    def set_investigation(self, investigation_id: str):
        """Set the current investigation."""
        pass

    def set_study(self, study_id: str):
        """Set the current study."""
        pass
