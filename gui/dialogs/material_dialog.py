"""
Material Dialog for creating/editing materials.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class CharacteristicEditor(QWidget):
    """Widget for editing material characteristics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.characteristics = []
        self.setup_ui()

    def setup_ui(self):
        """Set up the characteristics editor UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Characteristics list
        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(200)
        layout.addWidget(self.list_widget)

        # Buttons
        buttons_layout = QHBoxLayout()

        add_btn = QPushButton("+ Add Characteristic")
        add_btn.clicked.connect(self._on_add_characteristic)
        buttons_layout.addWidget(add_btn)

        remove_btn = QPushButton("- Remove Selected")
        remove_btn.clicked.connect(self._on_remove_characteristic)
        buttons_layout.addWidget(remove_btn)

        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

    def _on_add_characteristic(self):
        """Handle add characteristic button click."""
        dialog = CharacteristicDialog(self)
        if dialog.exec():
            char_data = dialog.get_characteristic()
            self.characteristics.append(char_data)
            self._refresh_list()

    def _on_remove_characteristic(self):
        """Handle remove characteristic button click."""
        selected_items = self.list_widget.selectedItems()
        for item in selected_items:
            row = self.list_widget.row(item)
            if 0 <= row < len(self.characteristics):
                self.characteristics.pop(row)
        self._refresh_list()

    def _refresh_list(self):
        """Refresh the characteristics list display."""
        self.list_widget.clear()
        for char in self.characteristics:
            char_type = char.get("category", {}).get("annotationValue", "")
            value = char.get("value", "")
            display_text = f"{char_type}: {value}" if value else char_type
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, char)
            self.list_widget.addItem(item)

    def get_characteristics(self):
        """Get the current characteristics list."""
        return self.characteristics.copy()

    def set_characteristics(self, characteristics):
        """Set the characteristics list."""
        self.characteristics = characteristics.copy()
        self._refresh_list()


class CharacteristicDialog(QDialog):
    """Dialog for adding/editing a single characteristic."""

    def __init__(self, parent=None, characteristic=None):
        super().__init__(parent)
        self.characteristic = characteristic or {}
        self.setWindowTitle("Add Characteristic")
        self.setMinimumSize(500, 300)
        self.setup_ui()

    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        # Characteristic type
        self.type_edit = QLineEdit()
        self.type_edit.setPlaceholderText("e.g., organism, strain, buffer composition")
        self.type_edit.setText(self.characteristic.get("category", {}).get("annotationValue", ""))
        form_layout.addRow("Characteristic Type:", self.type_edit)

        # Term source
        self.source_combo = QComboBox()
        self.source_combo.addItems(["OBI", "NCBITaxon", "ChEBI", "UO", "PMDco"])
        current_source = self.characteristic.get("category", {}).get("termSource", "")
        if current_source:
            index = self.source_combo.findText(current_source)
            if index >= 0:
                self.source_combo.setCurrentIndex(index)
        form_layout.addRow("Term Source:", self.source_combo)

        # Term accession
        self.accession_edit = QLineEdit()
        self.accession_edit.setPlaceholderText("e.g., http://purl.obolibrary.org/obo/NCBITaxon_562")
        self.accession_edit.setText(
            self.characteristic.get("category", {}).get("termAccession", "")
        )
        form_layout.addRow("Term Accession:", self.accession_edit)

        # Value
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("Characteristic value")
        self.value_edit.setText(str(self.characteristic.get("value", "")))
        form_layout.addRow("Value:", self.value_edit)

        layout.addLayout(form_layout)

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        buttons_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        layout.addLayout(buttons_layout)

    def get_characteristic(self):
        """Get the characteristic data."""
        return {
            "category": {
                "annotationValue": self.type_edit.text().strip(),
                "termSource": self.source_combo.currentText(),
                "termAccession": self.accession_edit.text().strip(),
            },
            "value": self.value_edit.text().strip(),
        }


class MaterialDialog(QDialog):
    """Dialog for creating and editing materials."""

    def __init__(self, parent=None, dm=None, material_data=None, templates=None):
        super().__init__(parent)
        self.dm = dm
        self.material_data = material_data or {}
        self.templates = templates or []
        self.setWindowTitle("Edit Material")
        self.setMinimumSize(700, 600)
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
        self.name_edit.setText(self.material_data.get("name", ""))
        self.name_edit.setPlaceholderText("Material name")
        basic_layout.addRow("Material Name:", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["source", "sample", "otherMaterial"])
        material_type = self.material_data.get("materialType", "")
        if material_type:
            index = self.type_combo.findText(material_type)
            if index >= 0:
                self.type_combo.setCurrentIndex(index)
        basic_layout.addRow("Material Type:", self.type_combo)

        # Derives from (for samples)
        self.derives_from_edit = QLineEdit()
        self.derives_from_edit.setText(", ".join(self.material_data.get("derivesFrom", [])))
        self.derives_from_edit.setPlaceholderText("Comma-separated material IDs")
        basic_layout.addRow("Derives From:", self.derives_from_edit)

        # Description
        self.description_edit = QLineEdit()
        self.description_edit.setText(self.material_data.get("description", ""))
        self.description_edit.setPlaceholderText("Material description")
        basic_layout.addRow("Description:", self.description_edit)

        tabs.addTab(basic_tab, "Basic Info")

        # Characteristics tab
        char_tab = QWidget()
        char_layout = QVBoxLayout(char_tab)

        char_layout.addWidget(QLabel("Characteristics:"))
        self.characteristics_editor = CharacteristicEditor()
        self.characteristics_editor.set_characteristics(
            self.material_data.get("characteristics", [])
        )
        char_layout.addWidget(self.characteristics_editor)

        tabs.addTab(char_tab, "Characteristics")

        # Template tab (for new materials)
        if not self.material_data:
            template_tab = QWidget()
            template_layout = QVBoxLayout(template_tab)

            template_layout.addWidget(QLabel("Select a template to create material from:"))

            self.template_combo = QComboBox()
            self.template_combo.addItem("-- No Template --", None)
            for template in self.templates:
                template_name = template.get("name", "Unknown")
                template_type = template.get("materialType", "")
                display_name = f"{template_name} ({template_type})"
                self.template_combo.addItem(display_name, template)
            template_layout.addWidget(self.template_combo)

            use_template_btn = QPushButton("Use Template")
            use_template_btn.clicked.connect(self._on_use_template)
            template_layout.addWidget(use_template_btn)

            template_layout.addStretch()
            tabs.addTab(template_tab, "Templates")

        layout.addWidget(tabs)

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        buttons_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        layout.addLayout(buttons_layout)

    def _on_use_template(self):
        """Handle use template button click."""
        template = self.template_combo.currentData()
        if not template:
            QMessageBox.information(
                self, "No Template Selected", "Please select a template to use."
            )
            return

        # Fill in data from template
        self.name_edit.setText(template.get("name", ""))
        material_type = template.get("materialType", "")
        index = self.type_combo.findText(material_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)

        self.description_edit.setText(template.get("description", ""))
        self.characteristics_editor.set_characteristics(template.get("characteristics", []))

        QMessageBox.information(
            self,
            "Template Applied",
            f"Template '{template.get('name')}' has been applied. " "Review the data and save.",
        )

    def _on_save(self):
        """Handle save button click."""
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Material name is required.")
            return

        # Build material data
        material = {
            "name": name,
            "materialType": self.type_combo.currentText(),
            "description": self.description_edit.text().strip(),
            "characteristics": self.characteristics_editor.get_characteristics(),
        }

        # Keep existing ID if editing
        if "@id" in self.material_data:
            material["@id"] = self.material_data["@id"]

        # Handle derives from
        derives_from_text = self.derives_from_edit.text().strip()
        if derives_from_text:
            material["derivesFrom"] = [id.strip() for id in derives_from_text.split(",")]

        self.material_data = material
        self.accept()

    def get_material_data(self):
        """Get the material data."""
        return self.material_data
