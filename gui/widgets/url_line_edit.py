"""
UrlLineEdit widget for ISA-JSON Data Steward GUI.

A line edit with URL validation.
"""

from typing import Optional

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QValidator
from PyQt6.QtWidgets import QLineEdit


class UrlValidator(QValidator):
    """Validator for URL input."""

    def __init__(self, parent=None):
        super().__init__(parent)

    def validate(self, input_str: Optional[str], pos: int) -> tuple:
        """
        Validate URL input.

        Returns:
            Tuple of (state, input_str, pos)
        """
        if not input_str:
            return (QValidator.State.Intermediate, input_str, pos)

        # Check if it's a template (contains placeholders)
        if "{" in input_str and "}" in input_str:
            # Templates are always valid
            return (QValidator.State.Acceptable, input_str, pos)

        # Check if it's a valid URL
        url = QUrl(input_str)
        if url.isValid() and url.scheme() in ("http", "https"):
            return (QValidator.State.Acceptable, input_str, pos)

        # Check if it could be a partial URL
        if input_str.startswith(("http://", "https://")):
            return (QValidator.State.Intermediate, input_str, pos)

        return (QValidator.State.Invalid, input_str, pos)


class UrlLineEdit(QLineEdit):
    """A line edit with URL validation."""

    urlChanged = pyqtSignal(str, bool)  # url, is_valid

    def __init__(self, parent=None):
        super().__init__(parent)

        self._validator = UrlValidator(self)
        self.setValidator(self._validator)

        self._is_valid = True
        self._allow_templates = True

        self.setPlaceholderText("https://example.com")
        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text: str):
        """Handle text change."""
        if not text:
            self._set_valid(True)
            self.urlChanged.emit(text, True)
            return

        # Check if it's a template
        if self._allow_templates and "{" in text and "}" in text:
            self._set_valid(True)
            self.urlChanged.emit(text, True)
            return

        # Validate URL
        url = QUrl(text)
        is_valid = url.isValid() and url.scheme() in ("http", "https")
        self._set_valid(is_valid)
        self.urlChanged.emit(text, is_valid)

    def _set_valid(self, valid: bool):
        """Set valid state of widget."""
        self._is_valid = valid

        if valid:
            self.setStyleSheet("")
        else:
            self.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #ff6b6b;
                    background-color: #fff5f5;
                }
            """)

    def url(self) -> str:
        """Get current URL."""
        return str(self.text())

    def set_url(self, url: str):
        """Set current URL."""
        self.setText(url)

    def is_valid(self) -> bool:
        """Check if current URL is valid."""
        return bool(self._is_valid)

    def set_allow_templates(self, allow: bool):
        """Set whether template placeholders are allowed."""
        self._allow_templates = allow
        self._on_text_changed(self.text())
