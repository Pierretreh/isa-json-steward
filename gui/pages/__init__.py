"""
Page widgets for the ISA-JSON Data Steward GUI.
"""

from .assays import AssaysPage
from .base_page import BasePage
from .dashboard import DashboardPage
from .files import FilesPage
from .images import ImagesPage
from .ontology_browser import OntologyBrowserPage
from .process_sequence import ProcessSequencePage
from .settings import SettingsPage
from .studies import StudiesPage
from .templates import TemplatesPage

__all__ = [
    "BasePage",
    "DashboardPage",
    "StudiesPage",
    "ProcessSequencePage",
    "AssaysPage",
    "FilesPage",
    "ImagesPage",
    "OntologyBrowserPage",
    "TemplatesPage",
    "SettingsPage",
]
