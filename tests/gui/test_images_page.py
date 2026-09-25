"""
Tests for the Images page registration and page contract (plan §5, T1).

These tests verify that ``ImagesPage`` is importable, is a proper
``ScrollablePage`` subclass, and exposes the base page contract.  They are
PyQt6-guarded so they skip cleanly in headless CI where PyQt6 is missing.
"""

import pytest

try:
    from PyQt6.QtWidgets import QWidget  # noqa: F401

    PYQT6_AVAILABLE = True
except (ImportError, OSError):
    PYQT6_AVAILABLE = False


@pytest.mark.gui
@pytest.mark.gui_page
class TestImagesPage:
    """Import + contract tests for the Images page."""

    @pytest.fixture(autouse=True)
    def _check_pyqt6(self):
        if not PYQT6_AVAILABLE:
            pytest.skip("PyQt6 not installed")

    def test_images_page_importable(self):
        """ImagesPage can be imported from the pages package."""
        from gui.pages.images import ImagesPage

        assert ImagesPage is not None

    def test_images_page_is_scrollable_page_subclass(self):
        """ImagesPage is a ScrollablePage (i.e. a BasePage) subclass."""
        from gui.pages.base_page import BasePage, ScrollablePage
        from gui.pages.images import ImagesPage

        assert issubclass(ImagesPage, ScrollablePage)
        assert issubclass(ImagesPage, BasePage)

    def test_images_page_exposes_page_contract(self):
        """ImagesPage exposes the required base-page methods."""
        from gui.pages.images import ImagesPage

        for attr in ("refresh", "set_study", "set_investigation", "on_enter", "on_exit"):
            assert hasattr(ImagesPage, attr), f"ImagesPage missing {attr}"

    def test_images_page_registered_in_pages_init(self):
        """ImagesPage is exported from the pages package."""
        import gui.pages as pages_pkg

        assert hasattr(pages_pkg, "ImagesPage")
        assert "ImagesPage" in pages_pkg.__all__
