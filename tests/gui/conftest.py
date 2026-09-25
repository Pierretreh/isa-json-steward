"""
Shared fixtures for GUI tests.

Provides a session-wide QApplication so that widget tests can construct
real Qt objects while staying safe in headless environments (PyQt6 import
failures are turned into skips, mirroring the guard pattern used in
``tests/gui/test_steward_app.py``).
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication  # noqa: F401

    PYQT6_AVAILABLE = True
except (ImportError, OSError):
    # OSError catches missing shared libraries (e.g. libEGL.so.1 on
    # headless CI runners where the Qt platform plugin cannot load).
    PYQT6_AVAILABLE = False


@pytest.fixture(scope="session")
def qapp():
    """Provide a shared QApplication instance for GUI widget tests."""
    if not PYQT6_AVAILABLE:
        pytest.skip("PyQt6 not installed")

    from PyQt6.QtWidgets import QApplication  # noqa: F811

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
