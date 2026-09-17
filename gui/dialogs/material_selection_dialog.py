"""
Material Selection Dialog for linking materials to process inputs/outputs.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)


class MaterialSelectionDialog(QDialog):
    """Dialog for selecting materials for process inputs/outputs."""

    def __init__(self, parent=None, materials=None, title="Select Materials", multi_select=True):
        super().__init__(parent)
        self.materials = materials or []
        self.multi_select = multi_select
        self.selected_materials = []
        self.setWindowTitle(title)
        self.setMinimumSize(600, 500)
        self.setup_ui()
        self.load_materials()

    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Search and filter
        search_layout = QHBoxLayout()

        search_label = QLabel("Search:")
        search_layout.addWidget(search_label)

        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search materials...")
        self.search_entry.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_entry)

        layout.addLayout(search_layout)

        # Material tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Material", "Type", "ID"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 150)
        self.tree.setColumnHidden(2, True)  # Hide ID column

        if self.multi_select:
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        else:
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)

        layout.addWidget(self.tree)

        # Group by type checkbox
        self.group_by_type = QCheckBox("Group by material type")
        self.group_by_type.setChecked(True)
        self.group_by_type.toggled.connect(self.load_materials)
        layout.addWidget(self.group_by_type)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_materials(self):
        """Load materials into the tree."""
        self.tree.clear()

        # Filter by search text
        search_text = self.search_entry.text().lower()
        filtered_materials = [
            m
            for m in self.materials
            if search_text in m.get("name", "").lower() or search_text in m.get("@id", "").lower()
        ]

        if self.group_by_type.isChecked():
            # Group by material type
            groups = {}
            for material in filtered_materials:
                mat_type = material.get("materialType", "Unknown")
                if mat_type not in groups:
                    groups[mat_type] = []
                groups[mat_type].append(material)

            # Create tree items
            for mat_type, type_materials in groups.items():
                group_item = QTreeWidgetItem(self.tree)
                group_item.setText(0, mat_type)
                group_item.setText(1, "")
                group_item.setExpanded(True)

                for material in type_materials:
                    self._add_material_item(group_item, material)
        else:
            # Flat list
            for material in filtered_materials:
                self._add_material_item(self.tree, material)

    def _add_material_item(self, parent, material):
        """Add a material item to the tree."""
        item = QTreeWidgetItem(parent)
        item.setText(0, material.get("name", "Unknown"))
        item.setText(1, material.get("materialType", ""))
        item.setText(2, material.get("@id", ""))
        item.setData(0, Qt.ItemDataRole.UserRole, material)

        # Check if this material was previously selected
        mat_id = material.get("@id", "")
        if mat_id in [m.get("@id", "") for m in self.selected_materials]:
            item.setSelected(True)

    def _on_search_changed(self, text):
        """Handle search text change."""
        self.load_materials()

    def get_selected_materials(self):
        """Get the list of selected materials."""
        selected_items = self.tree.selectedItems()
        materials = []
        for item in selected_items:
            material = item.data(0, Qt.ItemDataRole.UserRole)
            if material:
                materials.append(material)
        return materials

    def set_preselected_materials(self, material_ids):
        """Set materials that should be pre-selected."""
        self.selected_materials = [m for m in self.materials if m.get("@id", "") in material_ids]
        self.load_materials()
