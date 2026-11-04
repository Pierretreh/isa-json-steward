"""
Images page for the ISA-JSON Data Steward GUI.
"""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..agent_tools.ids import set_test_id
from ..dialogs.image_converter import ImageConverterDialog
from ..widgets.common import ActionButton, PrimaryButton, SectionHeader, set_ui_role
from .base_page import ScrollablePage


class ImagesPage(ScrollablePage):
    """Images page for managing experimental images."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setup_images_ui()

    def setup_images_ui(self):
        """Set up the images UI."""
        # Header
        self.add_widget(SectionHeader("Image Management"))

        # Splitter for lists
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Raw images list
        raw_layout = QVBoxLayout()
        raw_label = QLabel("Raw Images")
        raw_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        raw_layout.addWidget(raw_label)

        self.raw_list = QListWidget()
        set_test_id(self.raw_list, "page.images.rawImagesList")
        self.raw_list.setAlternatingRowColors(True)
        self.raw_list.setMinimumHeight(400)
        self.raw_list.itemDoubleClicked.connect(self._on_raw_image_selected)
        self.set_expanding(self.raw_list)
        raw_layout.addWidget(self.raw_list)

        # U-13: empty-state placeholder (muted via the theme QSS uiRole rule),
        # shown while the list is empty and hidden once populated.
        self.raw_placeholder = QLabel("No raw images — select a study, then use Import Image")
        set_test_id(self.raw_placeholder, "page.images.rawListPlaceholder")
        set_ui_role(self.raw_placeholder, "muted")
        self.raw_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.raw_placeholder.setWordWrap(True)
        self.set_expanding(self.raw_placeholder)
        raw_layout.addWidget(self.raw_placeholder)

        raw_widget = QWidget()  # type: ignore
        raw_widget.setLayout(raw_layout)
        splitter.addWidget(raw_widget)

        # Processed images list
        processed_layout = QVBoxLayout()
        processed_label = QLabel("Processed TIFFs")
        processed_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        processed_layout.addWidget(processed_label)

        self.processed_list = QListWidget()
        set_test_id(self.processed_list, "page.images.processedImagesList")
        self.processed_list.setAlternatingRowColors(True)
        self.processed_list.setMinimumHeight(400)
        self.processed_list.itemDoubleClicked.connect(self._on_processed_image_selected)
        self.set_expanding(self.processed_list)
        processed_layout.addWidget(self.processed_list)

        # U-13: empty-state placeholder (muted via the theme QSS uiRole rule).
        self.processed_placeholder = QLabel("No processed images yet")
        set_test_id(self.processed_placeholder, "page.images.processedListPlaceholder")
        set_ui_role(self.processed_placeholder, "muted")
        self.processed_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.processed_placeholder.setWordWrap(True)
        self.set_expanding(self.processed_placeholder)
        processed_layout.addWidget(self.processed_placeholder)

        processed_widget = QWidget()  # type: ignore
        processed_widget.setLayout(processed_layout)
        splitter.addWidget(processed_widget)

        # Set stretch factors for proportional sizing
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        self.set_expanding(splitter)
        self.add_widget(splitter)

        # Buttons
        buttons_layout = QHBoxLayout()

        import_btn = ActionButton("Import Image")
        set_test_id(import_btn, "page.images.importButton")
        import_btn.clicked.connect(self._on_import_image)
        buttons_layout.addWidget(import_btn)

        convert_btn = PrimaryButton("Convert to TIFF")
        set_test_id(convert_btn, "page.images.convertButton")
        convert_btn.clicked.connect(self._on_convert)
        buttons_layout.addWidget(convert_btn)

        refresh_btn = ActionButton("Refresh")
        set_test_id(refresh_btn, "page.images.refreshButton")
        refresh_btn.clicked.connect(self._on_refresh)
        buttons_layout.addWidget(refresh_btn)

        buttons_layout.addStretch()

        self.add_layout(buttons_layout)

        # U-11: keep references for selection/study gating; Convert starts
        # disabled until a raw image is selected, Import until a study loads.
        self.import_btn = import_btn
        self.convert_btn = convert_btn
        self.raw_list.itemSelectionChanged.connect(self._update_action_states)
        self._update_action_states()
        self._update_empty_states()

    def _update_action_states(self):
        """Enable/disable action buttons per selection/study state (U-11).

        Convert requires a selected raw image; Import requires a loaded
        study.  The QMessageBox guards in the handlers stay as defensive
        fallbacks but are unreachable through the normal click path.
        """
        self.convert_btn.setEnabled(bool(self.raw_list.selectedItems()))
        self.import_btn.setEnabled(bool(self.main_window.current_study))

    def _update_empty_states(self):
        """Toggle the U-13 empty-state placeholders against the lists.

        Each placeholder is mutually exclusive with its list: the
        placeholder is shown while the list is empty and hidden once the
        list has items.
        """
        has_raw = self.raw_list.count() > 0
        self.raw_list.setVisible(has_raw)
        self.raw_placeholder.setVisible(not has_raw)

        has_processed = self.processed_list.count() > 0
        self.processed_list.setVisible(has_processed)
        self.processed_placeholder.setVisible(not has_processed)

    def refresh(self):
        """Refresh the image lists."""
        self.raw_list.clear()
        self.processed_list.clear()
        self._update_action_states()
        self._update_empty_states()  # U-13: empty lists show their placeholders

        # Load images if a study is selected
        if not self.main_window.current_study:
            self.main_window.status_bar.show_message("No study selected")
            return

        dm = self.main_window.get_directory_manager()
        study_path = dm.get_study_path(
            self.main_window.current_investigation, self.main_window.current_study
        )

        # Load raw images from the canonical files/ directory
        # (created by DirectoryManager.create_study_directory), plus the
        # legacy raw_data/images and assay subdirectory layouts.
        image_dirs = [
            study_path / "files" / "original",
            study_path / "raw_data" / "images",
            study_path / "assays",
        ]
        seen = set()
        for base_dir in image_dirs:
            if not base_dir.exists():
                continue
            for img_file in sorted(base_dir.rglob("*")):
                if not img_file.is_file() or not self._is_image_file(img_file):
                    continue
                if img_file in seen:
                    continue
                seen.add(img_file)
                item = QListWidgetItem(img_file.name)
                item.setData(Qt.ItemDataRole.UserRole, str(img_file))
                item.setToolTip(f"Path: {img_file}")
                self.raw_list.addItem(item)

        # Load processed TIFFs
        tiff_dir = study_path / "processed_data" / "tiff"
        if tiff_dir.exists():
            for tiff_file in sorted(tiff_dir.glob("*.tif")):
                if tiff_file.is_file():
                    item = QListWidgetItem(tiff_file.name)
                    item.setData(Qt.ItemDataRole.UserRole, str(tiff_file))
                    item.setToolTip(f"Path: {tiff_file}")
                    self.processed_list.addItem(item)

        self.main_window.status_bar.show_message(
            f"Loaded {self.raw_list.count()} raw images, {self.processed_list.count()} TIFFs"
        )
        self._update_action_states()
        self._update_empty_states()  # U-13: populated lists hide their placeholders

    def _is_image_file(self, path: Path) -> bool:
        """Check if a file is an image."""
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif"}
        return path.suffix.lower() in image_extensions

    def _on_import_image(self):
        """Handle import image button click."""
        # Check if a study is selected
        if not self.main_window.current_study:
            QMessageBox.information(
                self, "No Study Selected", "Please select a study first from the Studies page."
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image File",
            "",
            "Image Files (*.jpg *.jpeg *.png *.tif *.tiff *.bmp);;All Files (*)",
        )
        if file_path:
            try:
                # Copy to the canonical raw images directory
                dm = self.main_window.get_directory_manager()
                raw_dir = (
                    dm.get_study_path(
                        self.main_window.current_investigation, self.main_window.current_study
                    )
                    / "files"
                    / "original"
                )

                raw_dir.mkdir(parents=True, exist_ok=True)

                import shutil

                dest_path = raw_dir / Path(file_path).name
                shutil.copy2(file_path, dest_path)

                self.main_window.status_bar.show_message(f"Imported: {Path(file_path).name}")
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import image:\n{str(e)}")

    def _on_convert(self):
        """Handle convert button click."""
        selected = self.raw_list.selectedItems()
        if not selected:
            QMessageBox.information(self, "No Selection", "Please select a raw image to convert.")
            return

        item = selected[0]
        source_path = Path(item.data(Qt.ItemDataRole.UserRole))

        # Open converter dialog
        dialog = ImageConverterDialog(self)
        dialog.file_path_edit.setText(str(source_path))

        if dialog.exec():
            conversion_data = dialog.get_conversion_data()
            self._convert_to_tiff(source_path, conversion_data.get("description", ""))

    def _convert_to_tiff(self, source_path: Path, description: str):
        """Convert an image to TIFF format."""
        try:
            from PIL import Image

            # Open source image
            img = Image.open(source_path)

            # Determine destination path
            dm = self.main_window.get_directory_manager()
            tiff_dir = (
                dm.get_study_path(
                    self.main_window.current_investigation, self.main_window.current_study
                )
                / "processed_data"
                / "tiff"
            )

            tiff_dir.mkdir(parents=True, exist_ok=True)

            # Generate output filename
            output_name = source_path.stem + ".tif"
            output_path = tiff_dir / output_name

            # Save as TIFF
            img.save(output_path, format="TIFF")

            self.main_window.status_bar.show_message(f"Converted to TIFF: {output_name}")
            self.refresh()

        except ImportError:
            QMessageBox.critical(
                self,
                "Missing Library",
                "Pillow library is required for image conversion.\n"
                "Please install it with: pip install Pillow",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to convert image:\n{str(e)}")

    def _on_refresh(self):
        """Handle refresh button click."""
        self.refresh()

    def _on_raw_image_selected(self, item: QListWidgetItem):
        """Handle raw image double-click."""
        file_path = item.data(Qt.ItemDataRole.UserRole)
        self.main_window.status_bar.show_message(f"Selected: {Path(file_path).name}")

    def _on_processed_image_selected(self, item: QListWidgetItem):
        """Handle processed image double-click."""
        file_path = item.data(Qt.ItemDataRole.UserRole)
        self.main_window.status_bar.show_message(f"Selected: {Path(file_path).name}")

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
