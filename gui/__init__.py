"""
ISA Data Steward GUI - PyQt6 Version

A modern GUI application for managing ISA-JSON study data with
sidebar navigation, ontology browsing, and template management.

This package ``__init__`` intentionally performs **no** Qt imports: the
Qt-dependent modules (``gui.app``, ``gui.main``, ``gui.main_window``, the
pages) are exposed as lazy attributes via :func:`__getattr__` (PEP 562).
That keeps ``import gui`` — and therefore Qt-free submodules such as
``gui.batch_config`` — safe on machines where PyQt6 is absent or its
native graphics libraries (e.g. ``libEGL.so.1`` on headless CI runners)
cannot be loaded.  ``from gui.app import StewardApp`` and friends are
unaffected: they import the submodules directly.
"""

__version__ = "2.0.0"
__author__ = "ISA Data Steward Project"

# Lazy attribute map (PEP 562): public name -> (module, attribute).
# Only imported when the attribute is actually requested.
_LAZY_ATTRS = {
    "StewardApp": ("gui.app", "StewardApp"),
    "create_app": ("gui.app", "create_app"),
    "main": ("gui.main", "main"),
    "MainWindow": ("gui.main_window", "MainWindow"),
    "AssaysPage": ("gui.pages.assays", "AssaysPage"),
    "DashboardPage": ("gui.pages.dashboard", "DashboardPage"),
    "ImagesPage": ("gui.pages.images", "ImagesPage"),
    "OntologyBrowserPage": ("gui.pages.ontology_browser", "OntologyBrowserPage"),
    "ProcessSequencePage": ("gui.pages.process_sequence", "ProcessSequencePage"),
    "SettingsPage": ("gui.pages.settings", "SettingsPage"),
    "StudiesPage": ("gui.pages.studies", "StudiesPage"),
    "TemplatesPage": ("gui.pages.templates", "TemplatesPage"),
}


def __getattr__(name: str):
    """Lazily resolve Qt-dependent package attributes (PEP 562).

    The import happens only when a Qt-dependent attribute is requested, so
    ``import gui`` itself never drags in PyQt6.  Requesting a lazy
    attribute on a machine without working Qt libraries raises ``ImportError``
    (e.g. ``libEGL.so.1`` missing) at that point — never at package import.
    """
    if name in _LAZY_ATTRS:
        import importlib

        module_name, attr = _LAZY_ATTRS[name]
        return getattr(importlib.import_module(module_name), attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """List public attributes, including the lazily-imported ones."""
    public = [name for name in dir() if not name.startswith("_")]
    return public + sorted(_LAZY_ATTRS)
