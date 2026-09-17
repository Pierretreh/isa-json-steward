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


class FormLabel(QLabel):
    """A styled label for form fields."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("formLabel")


class FormField(QLineEdit):
    """A styled text input field for forms."""

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setMinimumHeight(30)


class ActionButton(QPushButton):
    """A standard action button."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class PrimaryButton(QPushButton):
    """A primary action button with distinct styling."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("primaryButton")
        self.setMinimumHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class DangerButton(QPushButton):
    """A danger button for destructive actions."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("dangerButton")
        self.setMinimumHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


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

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        layout.addWidget(title_label)

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet("color: #2c3e50; font-size: 24px; font-weight: bold;")
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
        label.setMinimumWidth(150)
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
