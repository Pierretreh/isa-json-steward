"""
Dashboard page for the ISA-JSON Data Steward GUI.
"""

from pathlib import Path

from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..widgets.common import ActionButton, CardWidget, InfoCard, PrimaryButton, SectionHeader
from .base_page import ScrollablePage


class DashboardPage(ScrollablePage):
    """Dashboard page showing overview and quick actions."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setup_dashboard_ui()

    def setup_dashboard_ui(self):
        """Set up the dashboard UI."""
        # Welcome section
        welcome_label = QLabel("Dashboard")
        welcome_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #2c3e50;
                padding: 10px 0;
            }
        """)
        self.add_widget(welcome_label)

        # Stats cards
        stats_layout = QGridLayout()
        stats_layout.setSpacing(16)

        self.investigations_card = InfoCard("Investigations", "0")
        self.studies_card = InfoCard("Studies", "0")
        self.assays_card = InfoCard("Assays", "0")
        self.images_card = InfoCard("Images", "0")

        stats_layout.addWidget(self.investigations_card, 0, 0)
        stats_layout.addWidget(self.studies_card, 0, 1)
        stats_layout.addWidget(self.assays_card, 0, 2)
        stats_layout.addWidget(self.images_card, 0, 3)

        stats_widget = QWidget()
        stats_widget.setLayout(stats_layout)
        self.add_widget(stats_widget)

        # Quick actions
        self.add_widget(SectionHeader("Quick Actions"))

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(12)

        create_inv_btn = PrimaryButton("Create New Investigation")
        create_inv_btn.clicked.connect(self._on_create_investigation)
        actions_layout.addWidget(create_inv_btn)

        create_study_btn = PrimaryButton("Create New Study")
        create_study_btn.clicked.connect(self._on_create_study)
        actions_layout.addWidget(create_study_btn)

        open_study_btn = ActionButton("Open Recent Study")
        open_study_btn.clicked.connect(self._on_open_recent)
        actions_layout.addWidget(open_study_btn)

        browse_ontology_btn = ActionButton("Browse Ontology")
        browse_ontology_btn.clicked.connect(self._on_browse_ontology)
        actions_layout.addWidget(browse_ontology_btn)

        actions_widget = QWidget()
        actions_widget.setLayout(actions_layout)
        self.add_widget(actions_widget)

        # Current context
        self.add_widget(SectionHeader("Current Context"))

        context_card = CardWidget()
        context_layout = QVBoxLayout(context_card)

        self.investigation_label = QLabel("No investigation selected")
        self.investigation_label.setStyleSheet("color: #7f8c8d; padding: 4px;")
        context_layout.addWidget(self.investigation_label)

        self.study_label = QLabel("No study selected")
        self.study_label.setStyleSheet("color: #7f8c8d; padding: 4px;")
        context_layout.addWidget(self.study_label)

        self.add_widget(context_card)

    def refresh(self):
        """Refresh the dashboard data."""
        dm = self.main_window.get_directory_manager()

        # Update investigations
        investigations = dm.list_investigations()
        self.investigations_card.value_label.setText(str(len(investigations)))

        # Update studies
        total_studies = 0
        for inv_id in investigations:
            studies = dm.list_studies(inv_id)
            total_studies += len(studies)

        self.studies_card.value_label.setText(str(total_studies))

        # Update assays
        total_assays = 0
        total_images = 0

        if self.main_window.current_study:
            study_data = self.main_window.get_study_data()
            if study_data:
                assays = study_data.get("assays", [])
                total_assays = len(assays) if isinstance(assays, list) else 0

                # Count images in study directories
                study_path = dm.get_study_path(
                    self.main_window.current_investigation, self.main_window.current_study
                )

                # Count raw images
                raw_images_dir = study_path / "raw_data" / "images"
                if raw_images_dir.exists():
                    total_images += sum(
                        1
                        for f in raw_images_dir.iterdir()
                        if f.is_file() and self._is_image_file(f)
                    )

                # Count processed TIFFs
                tiff_dir = study_path / "processed_data" / "tiff"
                if tiff_dir.exists():
                    total_images += sum(1 for f in tiff_dir.glob("*.tif") if f.is_file())

                # Count assay images
                assays_dir = study_path / "assays"
                if assays_dir.exists():
                    for assay_type_dir in assays_dir.iterdir():
                        if assay_type_dir.is_dir():
                            for subdir in assay_type_dir.iterdir():
                                if subdir.is_dir():
                                    for img_file in subdir.iterdir():
                                        if img_file.is_file() and self._is_image_file(img_file):
                                            total_images += 1

        self.assays_card.value_label.setText(str(total_assays))
        self.images_card.value_label.setText(str(total_images))

        # Update context
        inv_id = self.main_window.current_investigation
        study_id = self.main_window.current_study

        if inv_id:
            self.investigation_label.setText(f"Investigation: {inv_id}")
            self.investigation_label.setStyleSheet(
                "color: #2c3e50; padding: 4px; font-weight: bold;"
            )
        else:
            self.investigation_label.setText("No investigation selected")
            self.investigation_label.setStyleSheet("color: #7f8c8d; padding: 4px;")

        if study_id:
            study_name = study_id
            # Try to get study name from data
            if self.main_window.study_data:
                study_name = self.main_window.study_data.get("study_name", study_id)

            self.study_label.setText(f"Study: {study_name}")
            self.study_label.setStyleSheet("color: #2c3e50; padding: 4px; font-weight: bold;")
        else:
            self.study_label.setText("No study selected")
            self.study_label.setStyleSheet("color: #7f8c8d; padding: 4px;")

    def _is_image_file(self, path: Path) -> bool:
        """Check if a file is an image."""
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif"}
        return path.suffix.lower() in image_extensions

    def _on_create_investigation(self):
        """Handle create investigation button click."""
        self.main_window._navigate_to_page("studies")
        # Trigger investigation creation on the studies page
        studies_page = self.main_window.pages.get("studies")
        if studies_page:
            studies_page._on_create_investigation()

    def _on_create_study(self):
        """Handle create study button click."""
        self.main_window._navigate_to_page("studies")

    def _on_open_recent(self):
        """Handle open recent study button click."""
        self.main_window._navigate_to_page("studies")

    def _on_browse_ontology(self):
        """Handle browse ontology button click."""
        self.main_window._navigate_to_page("ontology")

    def on_enter(self):
        """Called when the page is shown."""
        self.refresh()

    def on_exit(self):
        """Called when the page is hidden."""
        pass

    def set_investigation(self, investigation_id: str):
        """Set the current investigation."""
        pass  # Handled by refresh()

    def set_study(self, study_id: str):
        """Set the current study."""
        pass  # Handled by refresh()
