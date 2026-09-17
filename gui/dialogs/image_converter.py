"""
Image Converter dialog for JPEG to TIFF conversion.
"""

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


class ImageConverterDialog(QDialog):
    """Dialog for converting images to TIFF format."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Convert Image to TIFF")
        self.setMinimumWidth(500)
        self.setup_ui()

    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # File selection
        file_layout = QHBoxLayout()

        file_label = QLabel("Source File:")
        file_layout.addWidget(file_label)

        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("Select image file...")
        self.file_path_edit.setReadOnly(True)
        file_layout.addWidget(self.file_path_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse_file)
        file_layout.addWidget(browse_btn)

        layout.addLayout(file_layout)

        # Description
        desc_layout = QHBoxLayout()
        desc_label = QLabel("Description:")
        desc_layout.addWidget(desc_label)

        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("Enter description...")
        desc_layout.addWidget(self.desc_edit)

        layout.addLayout(desc_layout)

        # Progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        convert_btn = QPushButton("Convert")
        convert_btn.clicked.connect(self._on_convert)
        btn_layout.addWidget(convert_btn)

        layout.addLayout(btn_layout)

    def _on_browse_file(self):
        """Handle browse file button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Image File", "", "Image Files (*.jpg *.jpeg *.png);;All Files (*)"
        )
        if file_path:
            self.file_path_edit.setText(file_path)

    def _on_convert(self):
        """Handle convert button click."""
        source_path = self.file_path_edit.text()

        if not source_path:
            QMessageBox.warning(self, "No File Selected", "Please select a source image file.")
            return

        if not Path(source_path).exists():
            QMessageBox.warning(
                self, "File Not Found", f"The selected file does not exist:\n{source_path}"
            )
            return

        self.accept()

    def get_conversion_data(self) -> dict:
        """Get the conversion data from the dialog."""
        return {"source_file": self.file_path_edit.text(), "description": self.desc_edit.text()}
