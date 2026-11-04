"""
Common widgets used throughout the ISA-JSON Data Steward GUI.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..agent_tools.ids import set_test_id


def set_ui_role(widget: QWidget, role: str | None) -> None:
    """Set the ``uiRole`` dynamic property used for theme-aware QSS rules.

    ``role`` is one of the values styled in both theme stylesheets
    (``muted``, ``statValue``, ``error``, ``success``, ``warning``, ``panel``)
    or ``None`` to clear it.  The widget is re-polished so attribute-selector
    rules re-match immediately even when no stylesheet change follows.
    """
    widget.setProperty("uiRole", role)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)


class FormLabel(QLabel):
    """A styled label for form fields."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("formLabel")


class FormField(QLineEdit):
    """A styled text input field for forms."""

    def __init__(self, placeholder: str = "", parent=None, *, test_id: str | None = None):
        super().__init__(parent)
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setMinimumHeight(30)
        if test_id is not None:
            set_test_id(self, test_id)


class ActionButton(QPushButton):
    """A standard action button."""

    def __init__(self, text: str, parent=None, *, test_id: str | None = None):
        super().__init__(text, parent)
        self.setMinimumHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if test_id is not None:
            set_test_id(self, test_id)


class PrimaryButton(QPushButton):
    """A primary action button with distinct styling."""

    def __init__(self, text: str, parent=None, *, test_id: str | None = None):
        super().__init__(text, parent)
        self.setObjectName("primaryButton")
        self.setMinimumHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if test_id is not None:
            set_test_id(self, test_id)


class DangerButton(QPushButton):
    """A danger button for destructive actions."""

    def __init__(self, text: str, parent=None, *, test_id: str | None = None):
        super().__init__(text, parent)
        self.setObjectName("dangerButton")
        self.setMinimumHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if test_id is not None:
            set_test_id(self, test_id)


class CardWidget(QFrame):
    """A card widget with rounded corners and shadow effect."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)


class LoadingOverlay(QWidget):
    """An overlay widget that shows a loading indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Set semi-transparent dark background for better contrast
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 150);
                border-radius: 8px;
            }
        """)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_bar.setMaximumWidth(200)
        layout.addWidget(self.progress_bar)

        self.label = QLabel("Loading...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: #ffffff; font-size: 14px;")
        layout.addWidget(self.label)

    def set_text(self, text: str):
        """Set the loading text."""
        self.label.setText(text)

    def show_overlay(self, parent: QWidget):
        """Show the overlay over the parent widget."""
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()

    def hide_overlay(self):
        """Hide the overlay."""
        self.hide()


class SectionHeader(QLabel):
    """A section header with bold styling."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        font = QFont()
        font.setBold(True)
        font.setPointSize(14)
        self.setFont(font)
        self.setStyleSheet("padding: 8px 0;")


class InfoCard(QFrame):
    """A card displaying key information."""

    def __init__(self, title: str, value: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setup_ui(title, value)

    def setup_ui(self, title: str, value: str):
        layout = QVBoxLayout(self)

        # U-03: colors come from the theme QSS via uiRole rules; only
        # layout-only properties stay inline.
        title_label = QLabel(title)
        set_ui_role(title_label, "muted")
        title_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(title_label)

        self.value_label = QLabel(value)
        set_ui_role(self.value_label, "statValue")
        self.value_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(self.value_label)


class FormRow(QWidget):
    """A row containing a label and form field."""

    def __init__(self, label_text: str, field_widget, parent=None):
        super().__init__(parent)
        self.setup_ui(label_text, field_widget)

    def setup_ui(self, label_text: str, field_widget):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        label = FormLabel(label_text)
        # U-08: 120px (was 150) so form rows cannot force a page wider than
        # the default content viewport.
        label.setMinimumWidth(120)
        layout.addWidget(label)

        layout.addWidget(field_widget)
        layout.addStretch()

        return field_widget


class Spacer(QWidget):
    """A spacer widget for layouts."""

    def __init__(self, width: int = 0, height: int = 0, parent=None):
        super().__init__(parent)
        if width > 0:
            self.setMinimumWidth(width)
        if height > 0:
            self.setMinimumHeight(height)


class Divider(QFrame):
    """A horizontal divider line."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setStyleSheet("background-color: #e0e0e0; max-height: 1px;")
