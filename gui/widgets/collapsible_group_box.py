"""
CollapsibleGroupBox widget for the ISA-JSON Data Steward GUI.

A group box that can be collapsed/expanded to save screen space.
"""

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation
from PyQt6.QtWidgets import QGroupBox, QPushButton, QVBoxLayout, QWidget


class CollapsibleGroupBox(QGroupBox):
    """A group box that can be collapsed/expanded."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(title, parent)

        self._is_collapsed = False
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_widget.setLayout(self._content_layout)

        # Create collapse/expand button
        self._collapse_button = QPushButton()
        self._collapse_button.setCheckable(True)
        self._collapse_button.setChecked(False)
        self._collapse_button.setText("▼")
        self._collapse_button.setFixedWidth(24)
        self._collapse_button.setFixedHeight(24)
        self._collapse_button.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                font-size: 10px;
            }
            QPushButton:hover {
                background: rgba(200, 200, 200, 100);
            }
        """)
        self._collapse_button.toggled.connect(self._on_collapse_toggled)

        # Set up main layout
        self._main_layout = QVBoxLayout()
        self._main_layout.setContentsMargins(5, 5, 5, 5)
        self._main_layout.setSpacing(5)

        # Create header layout
        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        # Add collapse button to title
        self.setStyleSheet("""
            QGroupBox {{
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
        """)

        # Set up the group box layout
        self.setLayout(self._main_layout)
        self._main_layout.addWidget(self._content_widget)

        # Move collapse button to title bar
        self._collapse_button.setParent(self)
        self._collapse_button.move(5, 5)

        # Set maximum height for animation
        self._max_height = 1000
        self._current_height = self._max_height

    def add_widget(self, widget: QWidget):
        """Add a widget to the content area."""
        self._content_layout.addWidget(widget)

    def add_layout(self, layout):
        """Add a layout to the content area."""
        self._content_layout.addLayout(layout)

    def _on_collapse_toggled(self, checked: bool):
        """Handle collapse/expand button toggle."""
        self._is_collapsed = checked
        self._collapse_button.setText("▲" if checked else "▼")

        # Animate the content widget
        if checked:
            # Collapse
            self._animate_height(0)
        else:
            # Expand
            self._animate_height(self._max_height)

    def _animate_height(self, target_height: int):
        """Animate the height change."""
        self.animation = QPropertyAnimation(self, b"contentHeight")
        self.animation.setDuration(200)
        self.animation.setStartValue(self._current_height)
        self.animation.setEndValue(target_height)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.animation.start()
        self._current_height = target_height

    @property
    def contentHeight(self) -> int:
        """Get the content height."""
        return self._content_widget.height()

    @contentHeight.setter
    def contentHeight(self, height: int):
        """Set the content height."""
        self._content_widget.setFixedHeight(height)
        self._content_widget.setVisible(height > 0)

    def is_collapsed(self) -> bool:
        """Check if the group box is collapsed."""
        return self._is_collapsed

    def set_collapsed(self, collapsed: bool):
        """Set the collapsed state."""
        self._collapse_button.setChecked(collapsed)

    def resizeEvent(self, event):
        """Handle resize event to update max height."""
        super().resizeEvent(event)
        if not self._is_collapsed:
            self._max_height = self.height() - 30
            if self._current_height > 0:
                self._content_widget.setMaximumHeight(self._max_height)
