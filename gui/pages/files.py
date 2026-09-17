"""
Files page for the ISA-JSON Data Steward GUI.
Unified file management for all study files organized by assay/process.
"""

# Import utilities
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ..widgets.common import ActionButton, PrimaryButton, SectionHeader
from .base_page import ScrollablePage

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.file_manager import FileManager  # noqa: E402
from utils.isa_json_preview_helpers import ISAJsonPreviewHelper  # noqa: E402


class FilesPage(ScrollablePage):
    """Unified files page for managing all study files."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.files = []
        self.file_manager = FileManager()
        self.preview_helper = None
        self._isa_datafiles_by_name = {}  # Lookup from ISA-JSON dataFiles by filename
        self.setup_files_ui()

    def setup_files_ui(self):
        """Set up the files UI."""
        # Header
        self.add_widget(SectionHeader("File Management"))

        # Filter controls
        filter_layout = QHBoxLayout()

        filter_label = QLabel("Filter by type:")
        filter_label.setStyleSheet("font-weight: 500;")
        filter_layout.addWidget(filter_label)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Files", "Images", "Data", "Sequencing", "Reports"])
        self.filter_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_combo)

        # Search
        filter_layout.addSpacing(20)

        search_label = QLabel("Search:")
        search_label.setStyleSheet("font-weight: 500;")
        filter_layout.addWidget(search_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search files...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        filter_layout.addWidget(self.search_edit)

        filter_layout.addStretch()

        self.add_layout(filter_layout)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: File tree
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # File tree
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["File", "Type", "Entity", "Size", "Status"])
        file_tree_header = self.file_tree.header()
        file_tree_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        file_tree_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        file_tree_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        file_tree_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        file_tree_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.file_tree.setColumnWidth(0, 250)
        self.file_tree.setColumnWidth(1, 80)
        self.file_tree.setColumnWidth(2, 150)
        self.file_tree.setColumnWidth(3, 80)
        self.file_tree.setColumnWidth(4, 100)
        self.file_tree.setAlternatingRowColors(True)
        self.file_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.file_tree.itemDoubleClicked.connect(self._on_file_double_clicked)
        self.file_tree.itemClicked.connect(self._on_file_clicked)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._show_context_menu)
        self.set_expanding(self.file_tree)

        left_layout.addWidget(self.file_tree)

        # Right panel: File details and preview
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # File details (using QTextBrowser for rich HTML)
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

        details_label = QLabel("File Details")
        details_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        details_layout.addWidget(details_label)

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
            '<span style="color: #666;">Select a file to view details</span>'
        )
        details_layout.addWidget(self.details_browser)

        right_layout.addWidget(details_group)

        # Preview area (image preview + ISA-JSON metadata)
        preview_group = QFrame()
        preview_group.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        preview_layout = QVBoxLayout(preview_group)

        preview_label = QLabel("Preview")
        preview_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        preview_layout.addWidget(preview_label)

        self.preview_label = QLabel("No preview available")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setStyleSheet("color: #999; border: 1px dashed #ccc;")
        preview_layout.addWidget(self.preview_label)

        # ISA-JSON metadata browser (shown below image preview)
        self.metadata_browser = QTextBrowser()
        self.metadata_browser.setOpenExternalLinks(False)
        self.metadata_browser.setStyleSheet("""
            QTextBrowser {
                background-color: transparent;
                border: none;
                color: #333;
                font-size: 12px;
            }
        """)
        self.metadata_browser.setHtml('<span style="color: #999;">No metadata available</span>')
        preview_layout.addWidget(self.metadata_browser)

        right_layout.addWidget(preview_group)

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
        refresh_btn.clicked.connect(self._on_refresh)
        buttons_layout.addWidget(refresh_btn)

        export_btn = PrimaryButton("Export File")
        export_btn.clicked.connect(self._on_export_file)
        buttons_layout.addWidget(export_btn)

        delete_btn = ActionButton("Delete Selected")
        delete_btn.clicked.connect(self._on_delete_files)
        buttons_layout.addWidget(delete_btn)

        buttons_layout.addStretch()

        self.add_layout(buttons_layout)

    def refresh(self):
        """Refresh the file list."""
        if not self.main_window.current_study:
            self.file_tree.clear()
            self.details_browser.setHtml('<span style="color: #666;">No study selected</span>')
            self.preview_label.setText("No preview available")
            self.preview_label.clear()
            self.metadata_browser.setHtml('<span style="color: #999;">No metadata available</span>')
            return

        investigation_id = self.main_window.current_investigation or "inv_1"
        study_id = self.main_window.current_study

        # Get files from study
        self.files = self.file_manager.get_files(investigation_id, study_id)

        # Build ISA-JSON data file lookup
        self._build_isa_datafile_lookup()

        # Populate tree
        self._populate_file_tree()

    def _build_isa_datafile_lookup(self):
        """Build a lookup from filename to ISA-JSON dataFile objects."""
        self._isa_datafiles_by_name = {}
        self.preview_helper = None

        study_data = self.main_window.get_study_data()
        if not study_data:
            return

        try:
            self.preview_helper = ISAJsonPreviewHelper(study_data)
            study = self.preview_helper.study

            for assay in study.get("assays", []):
                for df in assay.get("dataFiles", []):
                    df_name = df.get("name", "")
                    if df_name:
                        self._isa_datafiles_by_name[df_name] = {"datafile": df, "assay": assay}
        except Exception as e:
            print(f"[FilesPage] Error building ISA-JSON lookup: {e}")

    def _populate_file_tree(self):
        """Populate the file tree with current files."""
        self.file_tree.clear()

        # Apply filters
        filter_type = self.filter_combo.currentText()
        search_text = self.search_edit.text().lower()

        # Group files by entity (assay/process)
        entity_groups = {}

        for file_meta in self.files:
            # Apply type filter
            if filter_type != "All Files":
                file_type = file_meta.get("file_type", "").lower()
                if filter_type == "Images" and file_type != "image":
                    continue
                elif filter_type == "Data" and file_type != "data":
                    continue
                elif filter_type == "Sequencing" and file_type != "sequencing":
                    continue
                elif filter_type == "Reports" and file_type != "report":
                    continue

            # Apply search filter
            filename = file_meta.get("original_filename", "").lower()
            if search_text and search_text not in filename:
                continue

            # Group by entity
            entity_type = file_meta.get("entity_type", "unknown")
            entity_id = file_meta.get("entity_id", "unknown")
            entity_key = f"{entity_type}_{entity_id}"

            if entity_key not in entity_groups:
                entity_groups[entity_key] = []

            entity_groups[entity_key].append(file_meta)

        # Create tree items
        for entity_key, files in entity_groups.items():
            entity_type, entity_id = entity_key.split("_", 1)

            # Create entity item
            entity_item = QTreeWidgetItem(self.file_tree)
            entity_item.setText(0, f"{entity_type.capitalize()}: {entity_id}")
            entity_item.setExpanded(True)

            # Add file items
            for file_meta in files:
                file_item = QTreeWidgetItem(entity_item)
                file_item.setText(0, file_meta.get("original_filename", ""))
                file_item.setText(1, file_meta.get("file_type", "").capitalize())
                file_item.setText(2, f"{file_meta.get('attachment_name', '')}")

                # File size
                size_bytes = file_meta.get("file_size_bytes", 0)
                size_str = self._format_file_size(size_bytes)
                file_item.setText(3, size_str)

                # Conversion status
                status = file_meta.get("conversion_status", "unknown")
                if status == "completed":
                    status_str = "✓ Converted"
                    status_color = "#28a745"
                elif status == "failed":
                    status_str = "✗ Failed"
                    status_color = "#dc3545"
                elif status == "not_needed":
                    status_str = "No conversion"
                    status_color = "#6c757d"
                else:
                    status_str = status
                    status_color = "#666"

                file_item.setText(4, status_str)
                file_item.setForeground(4, QColor(status_color))

                # Store file metadata
                file_item.setData(0, Qt.ItemDataRole.UserRole, file_meta)

        # Update statistics
        self._update_statistics()

    def _format_file_size(self, size_bytes: int) -> str:
        """
        Format file size in human-readable format.

        Args:
            size_bytes: Size in bytes

        Returns:
            Formatted size string
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def _update_statistics(self):
        """Update file statistics."""
        if not self.main_window.current_study:
            return

        investigation_id = self.main_window.current_investigation or "inv_1"
        study_id = self.main_window.current_study

        stats = self.file_manager.get_file_statistics(investigation_id, study_id)

        # Update status bar or display somewhere
        # For now, just print to console
        print(f"File Statistics: {stats}")

    def _on_filter_changed(self, text: str):
        """Handle filter change."""
        self._populate_file_tree()

    def _on_search_changed(self, text: str):
        """Handle search text change."""
        self._populate_file_tree()

    def _on_file_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle single file click - show details and preview."""
        file_meta = item.data(0, Qt.ItemDataRole.UserRole)
        if file_meta:
            self._show_file_details(file_meta)
            self._show_file_preview(file_meta)

    def _on_file_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle file double click."""
        file_meta = item.data(0, Qt.ItemDataRole.UserRole)
        if file_meta:
            self._show_file_details(file_meta)
            self._show_file_preview(file_meta)

    def _show_file_details(self, file_meta: dict):
        """
        Show file details in the details panel, including ISA-JSON metadata.

        Args:
            file_meta: File metadata dictionary
        """
        html_parts = []
        html_parts.append('<table style="border-collapse: collapse; width: 100%;">')

        # FileManager metadata
        original_filename = file_meta.get("original_filename", "")
        file_type = file_meta.get("file_type", "").capitalize()
        entity_type = file_meta.get("entity_type", "").capitalize()
        entity_id = file_meta.get("entity_id", "")
        attachment = file_meta.get("attachment_name", "")
        size = self._format_file_size(file_meta.get("file_size_bytes", 0))
        upload_date = file_meta.get("upload_date", "")

        html_parts.append(
            f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">Name:</td><td style="padding: 2px 0;"><b>{ISAJsonPreviewHelper._escape(original_filename)}</b></td></tr>'  # noqa: E501
        )
        html_parts.append(
            f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">Type:</td><td style="padding: 2px 0;">{ISAJsonPreviewHelper._escape(file_type)}</td></tr>'  # noqa: E501
        )
        html_parts.append(
            f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">Entity:</td><td style="padding: 2px 0;">{ISAJsonPreviewHelper._escape(entity_type)} - {ISAJsonPreviewHelper._escape(entity_id)}</td></tr>'  # noqa: E501
        )
        if attachment:
            html_parts.append(
                f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">Attachment:</td><td style="padding: 2px 0;">{ISAJsonPreviewHelper._escape(attachment)}</td></tr>'  # noqa: E501
            )
        html_parts.append(
            f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">Size:</td><td style="padding: 2px 0;">{size}</td></tr>'  # noqa: E501
        )
        if upload_date:
            html_parts.append(
                f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">Uploaded:</td><td style="padding: 2px 0;">{ISAJsonPreviewHelper._escape(upload_date)}</td></tr>'  # noqa: E501
            )

        # Conversion details
        if file_meta.get("converted_path"):
            html_parts.append(
                f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">Original Format:</td><td style="padding: 2px 0;">{ISAJsonPreviewHelper._escape(file_meta.get("original_format", ""))}</td></tr>'  # noqa: E501
            )
            html_parts.append(
                f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">Converted Format:</td><td style="padding: 2px 0;">{ISAJsonPreviewHelper._escape(file_meta.get("converted_format", ""))}</td></tr>'  # noqa: E501
            )
            html_parts.append(
                f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">Conversion Status:</td><td style="padding: 2px 0;">{ISAJsonPreviewHelper._escape(file_meta.get("conversion_status", ""))}</td></tr>'  # noqa: E501
            )

        # ISA-JSON metadata (from dataFiles in assay)
        isa_match = self._isa_datafiles_by_name.get(original_filename)
        if isa_match:
            isa_df = isa_match["datafile"]
            isa_assay = isa_match["assay"]
            isa_comments = isa_df.get("comments", [])

            isa_type = isa_df.get("type", "")
            isa_id = isa_df.get("@id", "")
            trace_db = self.preview_helper.get_comment_value(isa_comments, "TraceDB")
            derived_from = self.preview_helper.get_comment_value(isa_comments, "derivedFromSample")

            if isa_type:
                html_parts.append(
                    f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">ISA Type:</td><td style="padding: 2px 0;">{ISAJsonPreviewHelper._escape(isa_type)}</td></tr>'  # noqa: E501
                )
            if isa_id:
                html_parts.append(
                    f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">ISA ID:</td><td style="padding: 2px 0;"><code style="font-size: 10px;">{ISAJsonPreviewHelper._escape(isa_id)}</code></td></tr>'  # noqa: E501
                )
            if trace_db:
                html_parts.append(
                    f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">TraceDB Path:</td><td style="padding: 2px 0;"><code style="font-size: 10px;">{ISAJsonPreviewHelper._escape(trace_db)}</code></td></tr>'  # noqa: E501
                )
            if derived_from:
                if derived_from == "unassigned":
                    html_parts.append(
                        '<tr><td style="padding: 2px 8px 2px 0; color: #666;">Sample:</td><td style="padding: 2px 0; color: #999;">unassigned</td></tr>'  # noqa: E501
                    )
                else:
                    sample_name = self.preview_helper.resolve_material_name(derived_from)
                    html_parts.append(
                        f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">Sample:</td><td style="padding: 2px 0;"><b>{ISAJsonPreviewHelper._escape(sample_name)}</b></td></tr>'  # noqa: E501
                    )

            # Assay info
            assay_name = self.preview_helper._get_assay_display_name(isa_assay)
            html_parts.append(
                f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">Assay:</td><td style="padding: 2px 0;">{ISAJsonPreviewHelper._escape(assay_name)}</td></tr>'  # noqa: E501
            )

        html_parts.append("</table>")
        self.details_browser.setHtml("\n".join(html_parts))

    def _show_file_preview(self, file_meta: dict):
        """
        Show file preview in the preview panel.
        Shows image preview for images, and ISA-JSON metadata for all files.

        Args:
            file_meta: File metadata dictionary
        """
        file_type = file_meta.get("file_type", "")
        original_filename = file_meta.get("original_filename", "")

        # Try image preview
        image_shown = False
        if file_type == "image":
            file_path = file_meta.get("converted_path") or file_meta.get("original_path")
            if file_path:
                investigation_id = self.main_window.current_investigation or "inv_1"
                study_id = self.main_window.current_study
                full_path = (
                    Path("investigations")
                    / investigation_id
                    / "studies"
                    / study_id
                    / "files"
                    / file_path
                )

                if full_path.exists():
                    pixmap = QPixmap(str(full_path))
                    if not pixmap.isNull():
                        scaled_pixmap = pixmap.scaled(
                            300,
                            200,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        self.preview_label.setPixmap(scaled_pixmap)
                        self.preview_label.setStyleSheet("")
                        image_shown = True

        if not image_shown:
            self.preview_label.setText("No image preview")
            self.preview_label.clear()
            self.preview_label.setStyleSheet("color: #999; border: 1px dashed #ccc;")

        # Show ISA-JSON metadata in the metadata browser
        isa_match = self._isa_datafiles_by_name.get(original_filename)
        if isa_match and self.preview_helper:
            isa_df = isa_match["datafile"]
            isa_assay = isa_match["assay"]
            metadata_html = self.preview_helper.get_datafile_preview_html(isa_df, assay=isa_assay)
            self.metadata_browser.setHtml(metadata_html)
        else:
            self.metadata_browser.setHtml(
                '<span style="color: #999;">No ISA-JSON metadata available for this file</span>'
            )

    def _show_context_menu(self, position):
        """Show context menu for file tree."""
        item = self.file_tree.itemAt(position)
        if not item:
            return

        file_meta = item.data(0, Qt.ItemDataRole.UserRole)
        if not file_meta:
            return

        menu = QMenu()

        view_action = QAction("View Details", self)
        view_action.triggered.connect(lambda: self._show_file_details(file_meta))
        menu.addAction(view_action)

        export_action = QAction("Export File", self)
        export_action.triggered.connect(lambda: self._export_single_file(file_meta))
        menu.addAction(export_action)

        delete_action = QAction("Delete File", self)
        delete_action.triggered.connect(lambda: self._delete_single_file(file_meta))
        menu.addAction(delete_action)

        menu.exec(self.file_tree.mapToGlobal(position))

    def _on_refresh(self):
        """Handle refresh button click."""
        self.refresh()

    def _on_export_file(self):
        """Handle export file button click."""
        selected_items = self.file_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a file to export.")
            return

        if len(selected_items) > 1:
            QMessageBox.warning(
                self, "Multiple Selection", "Please select only one file to export."
            )
            return

        file_meta = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        if file_meta:
            self._export_single_file(file_meta)

    def _export_single_file(self, file_meta: dict):
        """
        Export a single file.

        Args:
            file_meta: File metadata dictionary
        """
        # Get file path
        investigation_id = self.main_window.current_investigation or "inv_1"
        study_id = self.main_window.current_study

        # Prefer converted file if available
        file_path = file_meta.get("converted_path") or file_meta.get("original_path")
        full_path = (
            Path("investigations") / investigation_id / "studies" / study_id / "files" / file_path
        )

        if not full_path.exists():
            QMessageBox.warning(
                self, "File Not Found", f"The file could not be found:\n{full_path}"
            )
            return

        # Open file dialog for save location
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Export File", file_meta.get("original_filename", "")
        )

        if save_path:
            import shutil

            shutil.copy2(full_path, save_path)
            QMessageBox.information(self, "Export Complete", f"File exported to:\n{save_path}")

    def _on_delete_files(self):
        """Handle delete files button click."""
        selected_items = self.file_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select files to delete.")
            return

        reply = QMessageBox.question(
            self,
            "Delete Files",
            f"Are you sure you want to delete {len(selected_items)} file(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            for item in selected_items:
                file_meta = item.data(0, Qt.ItemDataRole.UserRole)
                if file_meta:
                    self._delete_single_file(file_meta)

            self.refresh()

    def _delete_single_file(self, file_meta: dict):
        """
        Delete a single file.

        Args:
            file_meta: File metadata dictionary
        """
        investigation_id = self.main_window.current_investigation or "inv_1"
        study_id = self.main_window.current_study
        file_id = file_meta.get("file_id", "")

        result = self.file_manager.delete_file(investigation_id, study_id, file_id)

        if not result.get("success"):
            QMessageBox.warning(self, "Delete Failed", result.get("error", "Unknown error"))

    def on_enter(self):
        """Called when the page is shown — refresh file list."""
        self.refresh()

    def set_investigation(self, investigation_id: str):
        """Set the current investigation and refresh."""
        pass

    def set_study(self, study_id: str):
        """Set the current study and refresh the file list."""
        self.refresh()
