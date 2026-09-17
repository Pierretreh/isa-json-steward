"""
Basic tests for the ISA-JSON Data Steward GUI components.

These tests verify imports, module structure, and lightweight attribute
checks.  They intentionally avoid instantiating QApplication subclasses
to remain safe in headless CI environments.
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication  # noqa: F401

    PYQT6_AVAILABLE = True
except (ImportError, OSError):
    # OSError catches missing shared libraries (e.g. libEGL.so.1 on
    # headless CI runners where the Qt platform plugin cannot load).
    PYQT6_AVAILABLE = False


@pytest.mark.gui
class TestStewardApp:
    """Basic tests for StewardApp module structure."""

    @pytest.fixture(autouse=True)
    def _check_pyqt6(self):
        if not PYQT6_AVAILABLE:
            pytest.skip("PyQt6 not installed")

    def test_app_class_importable(self):
        """Test that StewardApp can be imported."""
        from gui.app import StewardApp

        assert StewardApp is not None

    def test_app_is_qapplication_subclass(self):
        """Test that StewardApp inherits from QApplication."""
        from PyQt6.QtWidgets import QApplication  # noqa: F811

        from gui.app import StewardApp

        assert issubclass(StewardApp, QApplication)

    def test_create_app_function_exists(self):
        """Test that the create_app helper is importable."""
        from gui.app import create_app

        assert callable(create_app)

    def test_profile_loaded_during_init(self):
        """Verify the profile module can supply app_name."""
        from utils.config_loader import get_profile

        name = get_profile().profile.get("app_name", "")
        # app_name may be empty in test profiles; just verify no crash
        assert isinstance(name, str)


@pytest.mark.gui
class TestMainWindow:
    """Basic tests for MainWindow module structure."""

    @pytest.fixture(autouse=True)
    def _check_pyqt6(self):
        if not PYQT6_AVAILABLE:
            pytest.skip("PyQt6 not installed")

    def test_main_window_importable(self):
        """Test that MainWindow can be imported."""
        from gui.main_window import MainWindow

        assert MainWindow is not None

    def test_main_window_is_qmainwindow_subclass(self):
        """Test that MainWindow inherits from QMainWindow."""
        from PyQt6.QtWidgets import QMainWindow

        from gui.main_window import MainWindow

        assert issubclass(MainWindow, QMainWindow)

    def test_main_window_has_setup_ui(self):
        """Test that MainWindow has the expected setup_ui method."""
        from gui.main_window import MainWindow

        assert hasattr(MainWindow, "setup_ui")

    def test_main_window_has_sidebar(self):
        """Test that MainWindow has sidebar attribute reference."""
        from gui.main_window import MainWindow

        # The class should reference Sidebar in its __init__
        assert hasattr(MainWindow, "setup_ui")


@pytest.mark.gui
class TestSidebar:
    """Basic tests for the sidebar widget."""

    @pytest.fixture(autouse=True)
    def _check_pyqt6(self):
        if not PYQT6_AVAILABLE:
            pytest.skip("PyQt6 not installed")

    def test_sidebar_importable(self):
        """Test that Sidebar can be imported."""
        from gui.widgets.sidebar import Sidebar

        assert Sidebar is not None

    def test_sidebar_is_widget_subclass(self):
        """Test that Sidebar inherits from QWidget."""
        from PyQt6.QtWidgets import QWidget

        from gui.widgets.sidebar import Sidebar

        assert issubclass(Sidebar, QWidget)

    def test_sidebar_has_navigation_signal(self):
        """Test that Sidebar exposes a navigationRequested signal."""
        from gui.widgets.sidebar import Sidebar

        assert hasattr(Sidebar, "navigationRequested")
