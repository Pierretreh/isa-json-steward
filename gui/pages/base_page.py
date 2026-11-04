"""
Base class for all pages in the ISA-JSON Data Steward GUI.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QScrollArea, QSizePolicy, QVBoxLayout, QWidget


class BasePage(QWidget):
    """Base class for all content pages."""

    # Signal emitted when page data changes (for auto-save)
    dataChanged = pyqtSignal()

    # Whether ``save_data()`` actually persists page data.  Pages with
    # manual-only persistence (SettingsPage, U-02) set this False so the
    # auto-save tick never claims "Auto-saved" for a no-op save (U-07).
    auto_save_persists: bool = True

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentPage")
        # U-03: QWidget subclasses do not paint QSS backgrounds without this
        # attribute -- it makes the ``QWidget#contentPage`` background rule
        # real on every page (belt-and-braces alongside the scroll-viewport
        # descendant rules in the theme stylesheets).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setup_ui()

    def setup_ui(self):
        """Set up the page UI. Override in subclasses."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

    def on_enter(self):
        """Called when the page is shown. Override in subclasses."""
        pass

    def on_exit(self):
        """Called when the page is hidden. Override in subclasses."""
        pass

    def refresh(self):
        """Refresh the page data. Override in subclasses."""
        pass

    def validate_data(self) -> tuple[bool, list[str]]:
        """
        Validate page data.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        return True, []

    def save_data(self):
        """Save page data. Override in subclasses."""
        pass

    def set_investigation(self, investigation_id: str):
        """Set the current investigation ID."""
        pass

    def set_study(self, study_id: str):
        """Set the current study ID."""
        pass


class ScrollablePage(BasePage):
    """A base page with scrollable content area."""

    def setup_ui(self):
        """Set up the scrollable page UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(self.scroll_area.Shape.NoFrame)

        # Create content widget
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.content_layout.setSpacing(16)

        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area)

        # Fixed footer row BELOW the scroll area (U-07): always-visible home
        # for action buttons that must stay reachable without scrolling
        # (e.g. the Settings page's Save/Reset/Restart buttons).
        self._footer_layout = QHBoxLayout()
        self._footer_layout.setContentsMargins(20, 8, 20, 8)
        self._footer_layout.setSpacing(8)
        main_layout.addLayout(self._footer_layout)

    def add_widget(self, widget):
        """Add a widget to the content layout."""
        self.content_layout.addWidget(widget)

    def add_footer(self, widget):
        """Add a widget to the fixed footer row outside the scroll area (U-07)."""
        self._footer_layout.addWidget(widget)

    def add_layout(self, layout):
        """Add a layout to the content layout."""
        self.content_layout.addLayout(layout)

    def set_expanding(self, widget):
        """
        Set widget to expand in both directions.

        Args:
            widget: The widget to set expanding policy on
        """
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_horizontal_expanding(self, widget):
        """
        Set widget to expand horizontally only.

        Args:
            widget: The widget to set expanding policy on
        """
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
