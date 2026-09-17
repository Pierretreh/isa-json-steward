"""
Main window for the ISA Data Steward GUI.
"""

import json

# Import utilities
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from PyQt6.QtCore import QTimer, pyqtSlot
from PyQt6.QtWidgets import QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QWidget

from .pages.assays import AssaysPage
from .pages.base_page import BasePage
from .pages.dashboard import DashboardPage
from .pages.files import FilesPage
from .pages.materials import MaterialsPage
from .pages.ontology_browser import OntologyBrowserPage
from .pages.process_sequence import ProcessSequencePage
from .pages.settings import SettingsPage
from .pages.studies import StudiesPage
from .pages.templates import TemplatesPage
from .widgets.sidebar import Sidebar
from .widgets.status_bar import StatusBar

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.constants import UIConstants  # noqa: E402
from utils.directory_manager import DirectoryManager  # noqa: E402
from utils.logging_config import get_logger  # noqa: E402
from utils.ontology_manager import OntologyManager  # noqa: E402
from utils.template_index import write_template_index  # noqa: E402

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    """Main application window with sidebar navigation."""

    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        self.dm: DirectoryManager = DirectoryManager()
        self.om: OntologyManager = OntologyManager()

        # Current context
        self.current_investigation: Optional[str] = None
        self.current_study: Optional[str] = None
        self.study_data: Optional[Dict[str, Any]] = None

        # Page mapping
        self.pages: Dict[str, BasePage] = {}

        # Auto-save timer
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self._auto_save)

        # Regenerate template index before pages load
        self._regenerate_template_index()

        self.setup_ui()
        self.load_settings()
        self.initialize_pages()
        self.setup_auto_save()

    def setup_ui(self):
        """Set up the main window UI."""
        from utils.config_loader import get_profile

        self.setWindowTitle(get_profile().profile.get("app_name", "ISA-JSON Data Steward"))

        # Load from settings or use defaults
        min_width = self.app.settings.value("gui/min_width", UIConstants.MIN_WINDOW_WIDTH, int)
        min_height = self.app.settings.value("gui/min_height", UIConstants.MIN_WINDOW_HEIGHT, int)
        self.setMinimumSize(min_width, min_height)

        width = self.app.settings.value("gui/width", UIConstants.DEFAULT_WINDOW_WIDTH, int)
        height = self.app.settings.value("gui/height", UIConstants.DEFAULT_WINDOW_HEIGHT, int)
        self.resize(width, height)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar()
        self.sidebar.setFixedWidth(UIConstants.SIDEBAR_WIDTH)
        self.sidebar.navigationRequested.connect(self._navigate_to_page)
        main_layout.addWidget(self.sidebar)

        # Content area
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("contentArea")
        main_layout.addWidget(self.content_stack)

        # Status bar
        self.status_bar = StatusBar()
        self.setStatusBar(self.status_bar)

    def initialize_pages(self):
        """Initialize all pages."""
        # Create pages
        self.pages["dashboard"] = DashboardPage(self)
        self.pages["studies"] = StudiesPage(self)
        self.pages["process_sequence"] = ProcessSequencePage(self)
        self.pages["materials"] = MaterialsPage(self)
        self.pages["assays"] = AssaysPage(self)
        self.pages["files"] = FilesPage(self)
        self.pages["ontology"] = OntologyBrowserPage(self)
        self.pages["templates"] = TemplatesPage(self)
        self.pages["settings"] = SettingsPage(self)

        # Add to stack
        for page_id, page in self.pages.items():
            self.content_stack.addWidget(page)
            page.dataChanged.connect(self._on_page_data_changed)

        # Navigate to dashboard
        self._navigate_to_page("dashboard")

    def setup_auto_save(self):
        """Set up auto-save functionality."""
        interval = self.app.settings.value("gui/auto_save_interval", 300, int)
        if interval > 0:
            self.auto_save_timer.start(interval * 1000)  # Convert to milliseconds

    def _regenerate_template_index(self):
        """Regenerate the template index files on GUI startup."""
        try:
            templates_root = self.get_templates_root()
            write_template_index(templates_root)
            logger.info("Template index regenerated successfully at %s", templates_root)
        except Exception as e:
            logger.warning("Failed to regenerate template index: %s", e)

    def get_templates_root(self) -> Path:
        """Return the resolved templates root directory.

        Uses the active profile's templates directory when available,
        falling back to ``dm.base_path / "templates"`` otherwise.
        """
        from utils.config_loader import get_profile

        profile = get_profile()
        templates_root = profile.get_templates_root()
        if templates_root.is_dir():
            return templates_root
        # Fallback to core repo templates
        return self.dm.base_path / "templates"

    def _auto_save(self):
        """Auto-save current page data."""
        current_page = self.content_stack.currentWidget()
        if current_page and self.current_study:
            try:
                current_page.save_data()
                self.status_bar.show_message("Auto-saved", timeout=UIConstants.AUTO_SAVE_TIMEOUT)
            except Exception as e:
                logger.error(f"Auto-save error: {e}", exc_info=True)

    @pyqtSlot(str)
    def _navigate_to_page(self, page_id: str):
        """Navigate to the specified page."""
        if page_id not in self.pages:
            return

        # Call on_exit for current page
        current_page = self.content_stack.currentWidget()
        if current_page:
            current_page.on_exit()

        # Switch to new page
        new_page = self.pages[page_id]
        self.content_stack.setCurrentWidget(new_page)
        self.sidebar.set_current_page(page_id)

        # Call on_enter for new page
        new_page.on_enter()

        # Update status bar
        self.status_bar.show_message(f"View: {page_id.replace('_', ' ').title()}")

    @pyqtSlot()
    def _on_page_data_changed(self):
        """Handle page data changes."""
        self.status_bar.show_message("Data changed - Auto-save pending...")

    def load_settings(self):
        """Load application settings."""
        geometry = self.app.get_window_geometry()
        if geometry:
            self.restoreGeometry(geometry)

        state = self.app.get_window_state()
        if state:
            self.restoreState(state)

    def closeEvent(self, event):
        """Handle window close event."""
        # Stop auto-save timer
        self.auto_save_timer.stop()

        # Save current page data
        current_page = self.content_stack.currentWidget()
        if current_page:
            is_valid, errors = current_page.validate_data()
            if not is_valid:
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    f"There are validation errors:\n\n{chr(10).join(errors)}\n\n"
                    "Do you want to close anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.No:
                    event.ignore()
                    return
            else:
                # Save data before closing
                try:
                    current_page.save_data()
                except Exception as e:
                    logger.error(f"Error saving on close: {e}", exc_info=True)

        # Save window state
        self.app.set_window_geometry(self.saveGeometry())
        self.app.set_window_state(self.saveState())

        event.accept()

    def set_investigation(self, investigation_id: str):
        """Set the current investigation."""
        self.current_investigation = investigation_id
        self.app.set_current_investigation(investigation_id)
        self.status_bar.set_investigation(investigation_id)

        # Update all pages
        for page in self.pages.values():
            page.set_investigation(investigation_id)

    def set_study(self, study_id: str):
        """Set the current study."""
        self.current_study = study_id
        self.app.set_current_study(study_id)
        self.status_bar.set_study(study_id)

        # Load study data
        if self.current_investigation and study_id:
            try:
                study_file = self.dm.get_study_json_path(self.current_investigation, study_id)
                with open(study_file, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)

                # DEBUG: Log loaded data structure
                print(
                    f"[DEBUG] MainWindow.set_study() - loaded_data keys: {list(loaded_data.keys())}"
                )
                print(
                    f"[DEBUG] MainWindow.set_study() - has 'studies' key: {'studies' in loaded_data}"  # noqa: E501
                )
                print(
                    f"[DEBUG] MainWindow.set_study() - has 'assays' key: {'assays' in loaded_data}"
                )

                # Preserve the full ISA-JSON structure for proper assay loading
                # The AssaysPage expects the complete structure with "studies" key
                self.study_data = loaded_data
                print(
                    f"[DEBUG] MainWindow.set_study() - Preserved full structure, has 'studies' key: {'studies' in self.study_data}"  # noqa: E501
                )
            except Exception as e:
                print(f"[DEBUG] MainWindow.set_study() - Error loading study: {e}")
                self.status_bar.show_message(f"Error loading study: {e}")
                self.study_data = None
        else:
            self.study_data = None

        # Update all pages
        for page in self.pages.values():
            page.set_study(study_id)

    def get_directory_manager(self) -> DirectoryManager:
        """Get the directory manager instance."""
        return self.dm

    def get_ontology_manager(self) -> OntologyManager:
        """Get the ontology manager instance."""
        return self.om

    def get_study_data(self) -> dict:
        """Get the current study data."""
        return self.study_data or {}
