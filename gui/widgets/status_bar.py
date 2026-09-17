"""
Status bar widget for the ISA-JSON Data Steward GUI.
"""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QStatusBar, QWidget


class StatusBar(QStatusBar):
    """Custom status bar with progress indicator and status messages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self._hide_progress)

    def setup_ui(self):
        """Set up the status bar UI."""
        self.setSizeGripEnabled(False)

        # Create container widget
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(8, 2, 8, 2)

        # Status message
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #ecf0f1;")
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setMaximumHeight(16)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # Permanent widgets
        self.investigation_label = QLabel()
        self.investigation_label.setStyleSheet("color: #bdc3c7; margin-left: 10px;")
        self.addPermanentWidget(self.investigation_label)

        self.study_label = QLabel()
        self.study_label.setStyleSheet("color: #bdc3c7; margin-left: 10px;")
        self.addPermanentWidget(self.study_label)

        self.addWidget(container)

    def show_message(self, message: str, timeout: int = 0):
        """Show a status message."""
        self.status_label.setText(message)
        if timeout > 0:
            QTimer.singleShot(timeout, lambda: self.status_label.setText("Ready"))

    def show_progress(self, message: str = ""):
        """Show the progress bar."""
        self.progress_bar.show()
        if message:
            self.status_label.setText(message)
        self.progress_timer.stop()

    def update_progress(self, value: int, maximum: int = 100):
        """Update the progress bar value."""
        self.progress_bar.setRange(0, maximum)
        self.progress_bar.setValue(value)

    def hide_progress(self, timeout: int = 500):
        """Hide the progress bar after a delay."""
        self.progress_timer.start(timeout)

    def _hide_progress(self):
        """Internal method to hide progress bar."""
        self.progress_bar.hide()
        self.progress_bar.setValue(0)
        self.progress_timer.stop()
        self.status_label.setText("Ready")

    def set_investigation(self, investigation_id: str):
        """Set the current investigation ID."""
        if investigation_id:
            self.investigation_label.setText(f"Inv: {investigation_id}")
        else:
            self.investigation_label.clear()

    def set_study(self, study_id: str):
        """Set the current study ID."""
        if study_id:
            self.study_label.setText(f"Study: {study_id}")
        else:
            self.study_label.clear()
