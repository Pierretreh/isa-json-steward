"""
ISA Data Steward GUI - PyQt6 Version

A modern GUI application for managing ISA-JSON study data with
sidebar navigation, ontology browsing, and template management.
"""

__version__ = "2.0.0"
__author__ = "ISA Data Steward Project"

# Export modules for proper import
from .app import StewardApp, create_app  # noqa: F401

# Import main entry point
from .main import main  # noqa: F401
from .main_window import MainWindow  # noqa: F401
from .pages.assays import AssaysPage  # noqa: F401
from .pages.dashboard import DashboardPage  # noqa: F401
from .pages.images import ImagesPage  # noqa: F401
from .pages.ontology_browser import OntologyBrowserPage  # noqa: F401
from .pages.process_sequence import ProcessSequencePage  # noqa: F401
from .pages.settings import SettingsPage  # noqa: F401
from .pages.studies import StudiesPage  # noqa: F401
from .pages.templates import TemplatesPage  # noqa: F401
