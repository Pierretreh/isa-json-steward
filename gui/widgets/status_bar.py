"""
Status bar widget for the ISA-JSON Data Steward GUI.
"""

from PyQt6.QtCore import QRect, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QStatusBar, QWidget

from ..agent_tools.ids import set_test_id


class StatusBar(QStatusBar):
    """Custom status bar with progress indicator and status messages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self._hide_progress)

    def setup_ui(self):
        """Set up the status bar UI.

        U-10: every child lives in ONE container with a single
        ``QHBoxLayout`` -- message label (stretch), progress bar,
        investigation label, study label -- and the container is added once
        with ``addWidget(container, 1)``.  The old mix of
        ``addPermanentWidget`` with a separate container left hidden or
        never-laid-out widgets at stale ``(0, 0)`` rects that overlapped the
        message label in widget-tree dumps (sweep evidence:
        ``statusBar.progressBar`` (0,0,200x16) over ``statusBar.messageLabel``
        (8,2,80x17)).
        """
        self.setSizeGripEnabled(False)

        # One container holding every status-bar child (U-10).
        self._container = QWidget()
        layout = QHBoxLayout(self._container)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)

        # Status message (stretches into the free space)
        self.status_label = QLabel("Ready")
        set_test_id(self.status_label, "statusBar.messageLabel")
        self.status_label.setStyleSheet("color: #ecf0f1;")
        self.status_label.setMinimumWidth(120)
        layout.addWidget(self.status_label, 1)

        # Progress bar (hidden by default; footprint capped at 200x16)
        self.progress_bar = QProgressBar()
        set_test_id(self.progress_bar, "statusBar.progressBar")
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setMaximumHeight(16)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        # U-10: a hidden widget is skipped by layouts and keeps its birth
        # rect (0,0,200x16), overlapping the message label in dumps -- clear
        # it so the hidden bar can never intersect a sibling.
        self.progress_bar.setGeometry(QRect())
        layout.addWidget(self.progress_bar)

        # Investigation / study labels (right end of the same row)
        self.investigation_label = QLabel()
        set_test_id(self.investigation_label, "statusBar.investigationLabel")
        self.investigation_label.setStyleSheet("color: #bdc3c7; margin-left: 10px;")
        layout.addWidget(self.investigation_label)

        self.study_label = QLabel()
        set_test_id(self.study_label, "statusBar.studyLabel")
        self.study_label.setStyleSheet("color: #bdc3c7; margin-left: 10px;")
        layout.addWidget(self.study_label)

        self.addWidget(self._container, 1)

    def _relayout(self):
        """Force an immediate layout pass so widget geometry is dump-fresh.

        Layouts only assign positions on activation; without this, a dump
        taken right after ``show_progress()`` / ``_hide_progress()`` can see
        stale rects (U-10).
        """
        bar_layout = self.layout()
        if bar_layout is not None:
            bar_layout.activate()
        container_layout = self._container.layout()
        if container_layout is not None:
            container_layout.activate()

    def show_message(self, message: str, timeout: int = 0):
        """Show a status message."""
        self.status_label.setText(message)
        if timeout > 0:
            QTimer.singleShot(timeout, self._reset_status_message)

    def _reset_status_message(self):
        """Reset to "Ready"; safe when the bar was destroyed meanwhile.

        A pending timeout can fire after the window was closed (e.g. Save
        then close within the message timeout); touching the deleted label
        would raise inside the Qt event loop and kill the session.
        """
        try:
            self.status_label.setText("Ready")
        except RuntimeError:
            pass

    def show_progress(self, message: str = ""):
        """Show the progress bar."""
        self.progress_bar.show()
        if message:
            self.status_label.setText(message)
        self.progress_timer.stop()
        self._relayout()

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
        # U-10: clear the hidden bar's stale rect so the message label (which
        # grows into the freed space) cannot geometrically overlap it.
        self.progress_bar.setGeometry(QRect())
        self._relayout()

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
