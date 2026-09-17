"""
Ontology Browser page for ISA-JSON Data Steward GUI.
"""

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..widgets.common import ActionButton, SectionHeader
from ..widgets.graph_widget import GraphWidget
from .base_page import ScrollablePage


class OntologyBrowserPage(ScrollablePage):
    """Ontology Browser page for browsing and searching ontology terms."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.ontology_data = {}
        self.current_category = None
        self.ontology_graph = None
        self._is_updating_selection = False  # Flag to prevent mutual recursion
        self.setup_ontology_ui()

    def setup_ontology_ui(self):
        """Set up the ontology browser UI."""
        # Header
        self.add_widget(SectionHeader("Ontology Browser"))

        # Search
        search_layout = QHBoxLayout()

        search_label = QLabel("Search:")
        search_label.setStyleSheet("font-weight: 500;")
        search_layout.addWidget(search_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search ontology terms...")
        self.search_edit.returnPressed.connect(self._on_search)
        search_layout.addWidget(self.search_edit)

        search_btn = ActionButton("Search")
        search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(search_btn)

        clear_btn = ActionButton("Clear")
        clear_btn.clicked.connect(self._on_clear_search)
        search_layout.addWidget(clear_btn)

        self.add_layout(search_layout)

        # Tab widget for Tree View and Graph View
        self.tab_widget = QTabWidget()

        # Tree View Tab
        self._setup_tree_view_tab()

        # Graph View Tab
        self._setup_graph_view_tab()

        self.set_expanding(self.tab_widget)
        self.add_widget(self.tab_widget)

        # Buttons
        buttons_layout = QHBoxLayout()

        expand_all_btn = ActionButton("Expand All")
        expand_all_btn.clicked.connect(self.tree.expandAll)
        buttons_layout.addWidget(expand_all_btn)

        collapse_all_btn = ActionButton("Collapse All")
        collapse_all_btn.clicked.connect(self.tree.collapseAll)
        buttons_layout.addWidget(collapse_all_btn)

        buttons_layout.addStretch()

        self.add_layout(buttons_layout)

    def _setup_tree_view_tab(self):
        """Set up the tree view tab."""
        tree_tab = QWidget()
        tree_layout = QVBoxLayout(tree_tab)
        tree_layout.setContentsMargins(0, 0, 0, 0)

        # Splitter for tree and details
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Tree widget for ontology hierarchy
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Term", "Type", "URI"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setMinimumHeight(400)
        self.tree.setColumnHidden(2, True)  # Hide URI column

        # Connect selection to details display
        self.tree.itemSelectionChanged.connect(self._on_tree_term_selected)

        # Set expanding size policy
        self.set_expanding(self.tree)

        # Configure header resize modes - Interactive for user-adjustable columns
        header = self.tree.header()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            self.tree.setColumnWidth(0, 350)
            self.tree.setColumnWidth(1, 120)

        # Details panel
        details_layout = QVBoxLayout()

        details_label = QLabel("Term Details")
        details_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        details_layout.addWidget(details_label)

        self.term_name = QLabel("Select a term to view details")
        self.term_name.setWordWrap(True)
        self.term_name.setStyleSheet("color: #7f8c8d; padding: 8px; font-weight: bold;")
        details_layout.addWidget(self.term_name)

        self.term_uri = QLabel("")
        self.term_uri.setWordWrap(True)
        self.term_uri.setStyleSheet("color: #7f8c8d; padding: 8px; font-size: 10px;")
        details_layout.addWidget(self.term_uri)

        self.term_description = QTextEdit()
        self.term_description.setReadOnly(True)
        self.term_description.setPlaceholderText("Description will appear here...")
        details_layout.addWidget(self.term_description)

        details_layout.addStretch()

        details_widget = QWidget()
        details_widget.setLayout(details_layout)

        splitter.addWidget(self.tree)
        splitter.addWidget(details_widget)

        # Set stretch factors for proportional sizing
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        self.set_expanding(splitter)

        tree_layout.addWidget(splitter)

        self.tab_widget.addTab(tree_tab, "Tree View")

    def _setup_graph_view_tab(self):
        """Set up the graph view tab with compact side legend."""
        graph_tab = QWidget()
        graph_layout = QVBoxLayout(graph_tab)
        graph_layout.setContentsMargins(0, 0, 0, 0)

        # Graph widget
        self.graph_widget = GraphWidget()
        self.graph_widget.node_selected.connect(self._on_graph_node_selected)

        # Category selector
        top_bar = QHBoxLayout()
        category_label = QLabel("Category:")
        category_label.setStyleSheet("font-weight: 500; font-size: 11px;")
        top_bar.addWidget(category_label)

        self.category_combo = QComboBox()
        self.category_combo.addItems(
            ["All", "Materials", "Processes", "Assays", "DataFiles", "Parameters", "External"]
        )
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        top_bar.addWidget(self.category_combo)
        top_bar.addStretch()

        # Legend toggle
        self.legend_visible = True
        legend_btn = ActionButton("?")
        legend_btn.setFixedSize(24, 24)
        legend_btn.setToolTip("Toggle legend")
        legend_btn.setCheckable(True)
        legend_btn.setChecked(True)
        legend_btn.clicked.connect(self._toggle_legend)
        top_bar.addWidget(legend_btn)

        graph_layout.addLayout(top_bar)

        # Horizontal splitter: graph on left, legend on right
        self.graph_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.graph_splitter.addWidget(self.graph_widget)

        self.legend_widget = self._create_legend_widget()
        self.graph_splitter.addWidget(self.legend_widget)

        # Graph takes most space, legend has min/max constraints
        self.graph_splitter.setStretchFactor(0, 1)
        self.graph_splitter.setStretchFactor(1, 0)
        self.graph_splitter.setSizes([800, 140])
        self.graph_splitter.splitterMoved.connect(self._on_legend_resized)

        self.set_expanding(self.graph_splitter)
        graph_layout.addWidget(self.graph_splitter)

        self.tab_widget.addTab(graph_tab, "Graph View")

    def _create_legend_widget(self) -> QWidget:
        """Create a compact vertical legend panel that scales with width."""
        legend = QWidget()
        legend.setMinimumWidth(100)
        legend.setMaximumWidth(300)
        legend.setStyleSheet("""
            QWidget {
                background-color: palette(base);
                border-left: 1px solid palette(mid);
            }
        """)

        self._legend_layout = QVBoxLayout(legend)
        self._legend_layout.setContentsMargins(6, 4, 6, 4)
        self._legend_layout.setSpacing(2)

        # Store label refs for font scaling
        self._legend_labels = []
        self._legend_swatches = []
        self._legend_lines = []

        # Header
        self._legend_header = QLabel("<b>Legend</b>")
        self._legend_header.setStyleSheet("font-size: 10px; padding-bottom: 4px;")
        self._legend_layout.addWidget(self._legend_header)

        # Node colors
        self._legend_node_label = QLabel("Nodes")
        self._legend_node_label.setStyleSheet(
            "font-size: 9px; color: palette(mid); padding-top: 4px;"
        )
        self._legend_layout.addWidget(self._legend_node_label)

        node_colors = [
            ("#3498db", "Materials"),
            ("#2ecc71", "Processes"),
            ("#9b59b6", "Assays"),
            ("#1abc9c", "Data Files"),
            ("#e67e22", "Parameters"),
            ("#95a5a6", "External"),
        ]

        for color_hex, label in node_colors:
            row = QHBoxLayout()
            row.setSpacing(4)
            swatch = QLabel()
            swatch.setFixedSize(8, 8)
            swatch.setStyleSheet(f"background-color: {color_hex}; border-radius: 4px;")
            row.addWidget(swatch)
            self._legend_swatches.append(swatch)
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 10px;")
            row.addWidget(lbl)
            self._legend_labels.append(lbl)
            row.addStretch()
            self._legend_layout.addLayout(row)

        # Edge colors
        self._legend_edge_label = QLabel("Edges")
        self._legend_edge_label.setStyleSheet(
            "font-size: 9px; color: palette(mid); padding-top: 6px;"
        )
        self._legend_layout.addWidget(self._legend_edge_label)

        edge_colors = [
            ("#7f8c8d", "subClassOf"),
            ("#1abc9c", "closeMatch"),
            ("#3498db", "hasInput"),
            ("#e74c3c", "hasOutput"),
        ]

        for color_hex, label in edge_colors:
            row = QHBoxLayout()
            row.setSpacing(4)
            line = QLabel("━━━━━")
            line.setFixedWidth(28)
            line.setStyleSheet(f"color: {color_hex}; font-weight: bold; font-size: 12px;")
            row.addWidget(line)
            self._legend_lines.append(line)
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 10px;")
            row.addWidget(lbl)
            self._legend_labels.append(lbl)
            row.addStretch()
            self._legend_layout.addLayout(row)

        self._legend_layout.addStretch()

        return legend

    def _on_legend_resized(self):
        """Scale legend font size when user resizes the legend panel."""
        if not hasattr(self, "_legend_labels") or not self.legend_widget:
            return

        width = self.legend_widget.width()
        # Scale font: 10px at 140px width, up to 14px at 300px width
        base_font = 10
        max_font = 14
        _base_width = 140  # noqa: F841
        max_width = 300

        ratio = min(1.0, max(0.0, (width - 100) / (max_width - 100)))
        font_size = base_font + ratio * (max_font - base_font)

        for lbl in self._legend_labels:
            lbl.setStyleSheet(f"font-size: {font_size:.0f}px;")

        # Scale swatch size
        swatch_size = int(8 + ratio * 6)
        for swatch in self._legend_swatches:
            swatch.setFixedSize(swatch_size, swatch_size)
            color = swatch.styleSheet().split("background-color:")[1].split(";")[0].strip()
            swatch.setStyleSheet(f"background-color: {color}; border-radius: {swatch_size // 2}px;")

        # Scale line size
        line_width = int(28 + ratio * 16)
        line_font = int(12 + ratio * 4)
        for line in self._legend_lines:
            line.setFixedWidth(line_width)
            color = line.styleSheet().split("color:")[1].split(";")[0].strip()
            line.setStyleSheet(f"color: {color}; font-weight: bold; font-size: {line_font}px;")

    def _toggle_legend(self):
        """Toggle legend visibility."""
        self.legend_visible = not self.legend_visible
        self.legend_widget.setVisible(self.legend_visible)

    def _load_ontology(self):
        """Load ontology structure into tree and graph."""
        self.tree.clear()

        om = self.main_window.get_ontology_manager()

        try:
            # Load ontology graph
            self.ontology_graph = om.load_ontology()

            # Create category items
            categories = ["Materials", "Processes", "Assays", "DataFiles", "Parameters", "External"]
            category_items = {}
            for cat in categories:
                cat_item = QTreeWidgetItem(self.tree)
                cat_item.setText(0, cat)
                cat_item.setText(1, "Category")
                category_items[cat] = cat_item

            # Extract all ontology terms and categorize them
            from rdflib import OWL, RDF, RDFS

            from utils.config_loader import get_profile

            ns_uri = get_profile().get_namespace()
            for s in self.ontology_graph.subjects(RDF.type, OWL.Class):
                s_str = str(s)

                # Only include project ontology terms
                if not s_str.startswith(ns_uri):
                    continue

                # Determine category based on URI pattern
                category = self._get_category_for_term(s_str, categories)

                if category and category in category_items:
                    # Get label
                    labels = list(self.ontology_graph.objects(s, RDFS.label))
                    label = str(labels[0]) if labels else s_str.split("#")[-1]

                    # Get comment/description
                    comments = list(self.ontology_graph.objects(s, RDFS.comment))
                    description = str(comments[0]) if comments else ""

                    term_item = QTreeWidgetItem(category_items[category])
                    term_item.setText(0, label)
                    term_item.setText(1, "Term")
                    term_item.setText(2, s_str)
                    term_item.setData(
                        0,
                        Qt.ItemDataRole.UserRole,
                        {
                            "label": label,
                            "description": description,
                            "uri": s_str,
                            "category": category,
                        },
                    )

                    self.ontology_data[s_str] = {
                        "label": label,
                        "description": description,
                        "uri": s_str,
                        "category": category,
                    }

            self.tree.expandAll()
            self.main_window.status_bar.show_message("Ontology loaded successfully")

            # Load graph with all categories by default
            self._load_graph_data("All")

        except Exception as e:
            self.main_window.status_bar.show_message(f"Error loading ontology: {e}")
            # Load sample data as fallback
            self._load_sample_data()

    def _get_category_for_term(self, uri: str, categories: list) -> Optional[str]:
        """
        Determine the category for a term using RDF type hierarchy.

        Uses the ontology's class hierarchy to determine the category,
        falling back to name patterns only when needed.

        Args:
            uri: The URI of the ontology term
            categories: List of available categories

        Returns:
            The category name or None if no match
        """
        from rdflib import OWL, RDF, RDFS, Namespace, URIRef

        from utils.config_loader import get_profile

        _PROJECT_NS = Namespace(get_profile().get_namespace())  # noqa: F841
        uri_ref = URIRef(uri)

        # Check if it's a NamedIndividual (parameters)
        if self.ontology_graph and (uri_ref, RDF.type, OWL.NamedIndividual) in self.ontology_graph:
            return "Parameters" if "Parameters" in categories else None

        # Check rdfs:subClassOf chain
        if self.ontology_graph:
            for s, p, o in self.ontology_graph.triples((uri_ref, RDFS.subClassOf, None)):
                parent = str(o)
                parent_lower = parent.lower()
                if any(m in parent_lower for m in ["sample", "source", "othermaterial"]):
                    return "Materials" if "Materials" in categories else None
                if "manufacturingprocess" in parent_lower:
                    return "Processes" if "Processes" in categories else None
                # OBI terms start with OBI_ prefix — project assays subclass specific OBI terms
                if parent.startswith("http://purl.obolibrary.org/obo/OBI_"):
                    return "Assays" if "Assays" in categories else None
                if "pmd/co/assay" in parent_lower:
                    return "Assays" if "Assays" in categories else None
                if any(
                    d in parent_lower
                    for d in ["datafile", "obi_0000031", "obi_0000021", "obi_0000973"]
                ):
                    return "DataFiles" if "DataFiles" in categories else None

        # Check if it's an external URI
        from utils.config_loader import get_profile as _get_profile

        if not uri.startswith(_get_profile().get_namespace()):
            return "External" if "External" in categories else None

        # Fallback to name patterns
        term_name = uri.split("#")[-1].lower()

        material_patterns = [
            "cells",
            "dna",
            "bacteria",
            "culture",
            "pellet",
            "lysate",
            "supernatant",
            "solution",
            "depot",
            "collagen",
            "buffer",
            "medium",
            "inductor",
            "protease",
        ]
        if any(pattern in term_name for pattern in material_patterns):
            return "Materials" if "Materials" in categories else None

        process_patterns = [
            "transformation",
            "expression",
            "harvesting",
            "addition",
            "lysis",
            "centrifugation",
            "division",
            "digestion",
            "purification",
            "dialysis",
            "electroporation",
        ]
        if any(pattern in term_name for pattern in process_patterns):
            return "Processes" if "Processes" in categories else None

        assay_patterns = ["assay", "test", "staining", "sequencing", "monitoring", "weighing"]
        if any(pattern in term_name for pattern in assay_patterns):
            return "Assays" if "Assays" in categories else None

        return "Materials" if "Materials" in categories else "Materials"

    def _load_graph_data(self, category: str):
        """Load graph data for the specified category."""
        if self.ontology_graph is None:
            return

        from utils.graph_builder import GraphBuilder

        builder = GraphBuilder(self.ontology_graph)
        graph_data = builder.build_graph_data(category)
        self.graph_widget.set_graph_data(graph_data["nodes"], graph_data["edges"])

    def _load_sample_data(self):
        """Load sample ontology data as fallback."""
        self.ontology_data = {}

        categories = [
            (
                "Materials",
                [("Biomaterials", []), ("Chemicals", []), ("Buffers", []), ("Equipment", [])],
            ),
            (
                "Protocols",
                [
                    ("Transformation Protocols", []),
                    ("Culture Protocols", []),
                    ("Purification Protocols", []),
                    ("Assay Protocols", []),
                ],
            ),
            (
                "Parameters",
                [
                    ("Physical Parameters", []),
                    ("Chemical Parameters", []),
                    ("Biological Parameters", []),
                ],
            ),
            ("Assays", [("SDS-PAGE", []), ("Microscopy", []), ("Toxicity Tests", [])]),
        ]

        for category, subcategories in categories:
            cat_item = QTreeWidgetItem(self.tree)
            cat_item.setText(0, category)
            cat_item.setText(1, "Category")

            for subcategory, items in subcategories:
                sub_item = QTreeWidgetItem(cat_item)
                sub_item.setText(0, subcategory)
                sub_item.setText(1, "Subcategory")

                for item in items:
                    item_widget = QTreeWidgetItem(sub_item)
                    item_widget.setText(0, item)
                    item_widget.setText(1, "Term")
                    item_widget.setData(
                        0,
                        Qt.ItemDataRole.UserRole,
                        {
                            "label": item,
                            "description": f"Sample {item} description",
                            "uri": f"http://example.org/{item}",
                            "category": category,
                        },
                    )

    def _on_search(self):
        """Handle search button click."""
        search_term = self.search_edit.text().strip().lower()

        if not search_term:
            self._on_clear_search()
            return

        # Clear current selection
        self.tree.clearSelection()

        # Search through tree items
        found_items = []
        root_item = self.tree.invisibleRootItem()
        if root_item is not None:
            self._search_tree(root_item, search_term, found_items)

        if found_items:
            # Expand and select found items
            for item in found_items:
                item.setSelected(True)
                # Expand parent items
                parent = item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()

            # Highlight matching nodes in graph view
            matched_uris = []
            for item in found_items:
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and "uri" in data:
                    matched_uris.append(data["uri"])
            if matched_uris:
                self.graph_widget.highlight_nodes(matched_uris)

            self.main_window.status_bar.show_message(f"Found {len(found_items)} matching terms")
        else:
            self.graph_widget.clear_highlights()
            self.main_window.status_bar.show_message(f"No terms found for '{search_term}'")

    def _search_tree(self, item: QTreeWidgetItem, search_term: str, found_items: list):
        """Recursively search tree items."""
        text = item.text(0).lower()

        if search_term in text:
            found_items.append(item)

        # Search children
        for i in range(item.childCount()):
            child = item.child(i)
            if child is not None:
                self._search_tree(child, search_term, found_items)

    def _on_clear_search(self):
        """Handle clear search button click."""
        self.search_edit.clear()
        self.tree.clearSelection()
        self.graph_widget.clear_highlights()
        self.main_window.status_bar.show_message("Search cleared")

    def _on_tree_term_selected(self):
        """Handle term selection change in tree view."""
        # Prevent mutual recursion cycle
        if self._is_updating_selection:
            return

        selected = self.tree.selectedItems()

        if not selected:
            self.term_name.setText("Select a term to view details")
            self.term_description.setPlainText("")
            self.term_uri.setText("")
            return

        item = selected[0]
        term_data = item.data(0, Qt.ItemDataRole.UserRole)

        if term_data:
            self.term_name.setText(term_data.get("label", "Unknown"))
            self.term_description.setPlainText(
                term_data.get("description", "No description available")
            )
            self.term_uri.setText(f"URI: {term_data.get('uri', '')}")

            # Sync with graph view
            uri = term_data.get("uri", "")
            if uri:
                self._is_updating_selection = True
                try:
                    self.graph_widget.select_node_by_uri(uri)
                finally:
                    self._is_updating_selection = False
        else:
            self.term_name.setText(item.text(0))
            self.term_description.setPlainText("No detailed information available")
            self.term_uri.setText("")

    def _on_graph_node_selected(self, uri: str, label: str, node_type: str):
        """Handle node selection in graph view."""
        # Prevent mutual recursion cycle
        if self._is_updating_selection:
            return

        self.term_name.setText(label)
        self.term_uri.setText(f"URI: {uri}")

        # Get description from ontology data
        if uri in self.ontology_data:
            self.term_description.setPlainText(
                self.ontology_data[uri].get("description", "No description available")
            )
        else:
            self.term_description.setPlainText("No description available")

        # Find and select in tree view
        self._is_updating_selection = True
        try:
            self._select_tree_item_by_uri(uri)
        finally:
            self._is_updating_selection = False

    def _select_tree_item_by_uri(self, uri: str):
        """Find and select a tree item by URI."""
        from typing import Optional

        # Track visited items to prevent circular references (safety measure)
        visited_items = set()

        def find_item(item: QTreeWidgetItem, depth: int = 0) -> Optional[QTreeWidgetItem]:
            """Recursively find item with matching URI."""
            # Check for circular reference (should not happen with the fix, but kept as safety)
            item_id = id(item)
            if item_id in visited_items:
                return None
            visited_items.add(item_id)

            # Check current item
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("uri") == uri:
                return item

            # Search children
            for i in range(item.childCount()):
                child = item.child(i)
                if child is not None:
                    result = find_item(child, depth + 1)
                    if result:
                        return result
            return None

        root_item = self.tree.invisibleRootItem()
        if root_item is not None:
            item = find_item(root_item)
            if item:
                self.tree.clearSelection()
                item.setSelected(True)
                # Expand parent items
                parent = item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()

    def _on_category_changed(self, category: str):
        """Handle category selection change."""
        self._load_graph_data(category)

    def on_enter(self):
        """Called when the page is shown."""
        # Load ontology if not already loaded
        if self.tree.topLevelItemCount() == 0:
            self._load_ontology()

    def on_exit(self):
        """Called when the page is hidden."""
        pass

    def set_investigation(self, investigation_id: str):
        """Set current investigation."""
        pass

    def set_study(self, study_id: str):
        """Set current study."""
        pass
