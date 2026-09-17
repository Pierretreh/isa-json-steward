"""
Study Wizard dialog for creating new studies.
"""

from datetime import datetime
from pathlib import Path

from Bio import SeqIO
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class StudyWizard(QDialog):
    """Wizard dialog for creating a new study."""

    def __init__(self, parent=None, dm=None):
        super().__init__(parent)
        self.dm = dm
        self.setWindowTitle("Create New Study")
        self.setMinimumWidth(500)
        self.setup_ui()

    def setup_ui(self):
        """Set up wizard UI."""
        layout = QVBoxLayout(self)

        # Investigation selection
        inv_layout = QHBoxLayout()
        inv_label = QLabel("Investigation:")
        inv_layout.addWidget(inv_label)

        self.inv_combo = QComboBox()
        investigations = self.dm.list_investigations() if self.dm else []
        self.inv_combo.addItems(investigations)
        inv_layout.addWidget(self.inv_combo)

        create_inv_btn = QPushButton("New...")
        create_inv_btn.setToolTip("Create a new investigation")
        create_inv_btn.clicked.connect(self._on_create_investigation)
        inv_layout.addWidget(create_inv_btn)

        layout.addLayout(inv_layout)

        # Warning label shown when no investigations exist
        self.no_inv_warning = QLabel(
            "⚠ No investigations found. Click 'New...' to create one before creating a study."
        )
        self.no_inv_warning.setStyleSheet("color: #d35400; font-weight: bold;")
        self.no_inv_warning.setWordWrap(True)
        self.no_inv_warning.setVisible(len(investigations) == 0)
        layout.addWidget(self.no_inv_warning)

        # Form fields
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Study name")
        form.addRow("Study Name:", self.name_edit)

        self.strain_edit = QLineEdit()
        self.strain_edit.setPlaceholderText("Bacterial strain")
        form.addRow("Strain:", self.strain_edit)

        self.plasmid_edit = QLineEdit()
        self.plasmid_edit.setPlaceholderText("Protein plasmid")
        form.addRow("Plasmid:", self.plasmid_edit)

        # Sequence file
        seq_layout = QHBoxLayout()
        self.seq_path_edit = QLineEdit()
        self.seq_path_edit.setPlaceholderText("Select sequence file...")
        self.seq_path_edit.setReadOnly(True)
        seq_layout.addWidget(self.seq_path_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse_sequence)
        seq_layout.addWidget(browse_btn)

        form.addRow("Sequence File:", seq_layout)

        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        create_btn = QPushButton("Create")
        create_btn.clicked.connect(self._on_create)
        btn_layout.addWidget(create_btn)

        layout.addLayout(btn_layout)

    def _on_browse_sequence(self):
        """Handle browse sequence file button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Sequence File",
            "",
            "Sequence Files (*.fasta *.fa *.gb *.dna);;All Files (*)",
        )
        if file_path:
            self.seq_path_edit.setText(file_path)

    def _on_create_investigation(self):
        """Handle create investigation inline from the study wizard."""
        from .investigation_dialog import InvestigationDialog

        dialog = InvestigationDialog(self, dm=self.dm)
        if dialog.exec():
            inv_data = dialog.get_investigation_data()
            try:
                inv_id = inv_data["investigation_id"]
                inv_path = self.dm.create_investigation_directory(inv_id)
                if inv_path is None:
                    QMessageBox.critical(
                        self, "Error", f"Failed to create investigation directory for '{inv_id}'."
                    )
                    return

                # Save investigation metadata JSON
                import json as _json

                inv_json_path = inv_path / f"{inv_id}.json"
                with open(inv_json_path, "w", encoding="utf-8") as f:
                    _json.dump(
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

                # Refresh the combo box and select the new investigation
                self.inv_combo.clear()
                investigations = self.dm.list_investigations() if self.dm else []
                self.inv_combo.addItems(investigations)
                idx = self.inv_combo.findText(inv_id)
                if idx >= 0:
                    self.inv_combo.setCurrentIndex(idx)

                self.no_inv_warning.setVisible(len(investigations) == 0)

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create investigation:\n{str(e)}")

    def validate_data(self) -> tuple[bool, list[str]]:
        """Validate the study data.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Check investigation
        if not self.inv_combo.currentText():
            errors.append("Please select an investigation (use 'New...' to create one)")

        # Check study name
        study_name = self.name_edit.text().strip()
        if not study_name:
            errors.append("Study name is required")
        elif not study_name.replace("_", "").replace("-", "").replace(" ", "").isalnum():
            errors.append(
                "Study name can only contain letters, numbers, hyphens, underscores, and spaces"
            )

        # Check strain
        if not self.strain_edit.text().strip():
            errors.append("Bacterial strain is required")

        # Check sequence file
        seq_file = self.seq_path_edit.text()
        if seq_file and not Path(seq_file).exists():
            errors.append("Sequence file does not exist")

        return len(errors) == 0, errors

    def _on_create(self):
        """Handle create button click with validation."""
        is_valid, errors = self.validate_data()

        if not is_valid:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please correct the following errors:\n\n" + "\n".join(f"• {e}" for e in errors),
            )
            return

        self.accept()

    def get_study_data(self) -> dict:
        """Get study data from the wizard."""
        study_name = self.name_edit.text().strip()

        # Generate study ID from name
        study_id = f"study_{study_name.lower().replace(' ', '_').replace('-', '_')}"

        # Read sequence file if provided
        sequence_data = None
        sequence_file_path = None
        seq_file = self.seq_path_edit.text()
        if seq_file and Path(seq_file).exists():
            try:
                seq_record = SeqIO.read(seq_file, "fasta")
                sequence_data = {
                    "sequence_id": seq_record.id,
                    "sequence": str(seq_record.seq),
                    "description": seq_record.description,
                    "file_path": seq_file,
                }
                sequence_file_path = seq_file  # Store for copying
            except Exception as e:
                print(f"Warning: Could not read sequence file: {e}")

        return {
            "investigation_id": self.inv_combo.currentText(),
            "study_id": study_id,
            "study_name": study_name,
            "bacterial_strain": self.strain_edit.text().strip(),
            "protein_plasmid": self.plasmid_edit.text().strip(),
            "sequence_data": sequence_data,
            "sequence_file_path": sequence_file_path,
            "created_at": datetime.now().isoformat(),
            "assays": [],
            "process_sequence": {},
        }
