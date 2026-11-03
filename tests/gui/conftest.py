"""
Shared fixtures for GUI tests.

Provides a session-wide QApplication so that widget tests can construct
real Qt objects while staying safe in headless environments (PyQt6 import
failures are turned into skips, mirroring the guard pattern used in
``tests/gui/test_steward_app.py``).

Also provides the P1-3 harness fixtures from the design plan (section 3.3):
``stub_app`` (the shared ``StubApp`` settings/window-state stub),
``main_window`` (a real ``MainWindow`` cleaned up via ``qtbot.addWidget``)
and ``agent`` (a thin ``gui.agent_tools`` wrapper bound to the window).
"""

from pathlib import Path

import pytest

try:
    from PyQt6.QtWidgets import QApplication  # noqa: F401

    PYQT6_AVAILABLE = True
except (ImportError, OSError):
    # OSError catches missing shared libraries (e.g. libEGL.so.1 on
    # headless CI runners where the Qt platform plugin cannot load).
    PYQT6_AVAILABLE = False


class StubApp:
    """Minimal stand-in for StewardApp (settings + window state).

    Formalizes the ``_StubApp`` pattern from ``tests/gui/test_steward_app.py``
    so test modules share one copy: ``MainWindow`` only needs the settings
    facade and the window geometry/state accessors exposed here.
    """

    class _Settings:
        def __init__(self):
            self._values = {}

        def value(self, key, default=None, type=None):
            return self._values.get(key, default)

        def setValue(self, key, value):
            self._values[key] = value

    def __init__(self):
        self.settings = self._Settings()

    def get_window_geometry(self):
        return None

    def get_window_state(self):
        return None

    def set_window_geometry(self, geometry):
        pass

    def set_window_state(self, state):
        pass

    def set_current_investigation(self, investigation_id):
        pass

    def set_current_study(self, study_id):
        pass

    def set_theme(self, theme: str) -> None:
        """Apply a theme QSS like ``StewardApp.set_theme`` (headless-safe)."""
        if not PYQT6_AVAILABLE:
            return
        style_path = (
            Path(__file__).resolve().parents[2] / "gui" / "resources" / "styles" / f"{theme}.qss"
        )
        app = QApplication.instance()
        if app is not None and style_path.exists():
            app.setStyleSheet(style_path.read_text(encoding="utf-8"))
        self.settings.setValue("gui/theme", theme)


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


@pytest.fixture
def stub_app():
    """Shared settings/window-state stub (design plan section 3.3)."""
    return StubApp()


@pytest.fixture
def main_window(qtbot, stub_app):
    """A real ``MainWindow``, registered with ``qtbot`` for auto close/cleanup.

    Teardown navigates back to the dashboard and stops the auto-save timer
    BEFORE ``qtbot`` closes the window: ``MainWindow.closeEvent`` auto-saves
    the current page, and the settings page would open a modal QMessageBox
    and rewrite ``config/settings.json`` (known hazard, see AGENTS.md).
    """
    from gui.main_window import MainWindow

    window = MainWindow(stub_app)
    qtbot.addWidget(window)  # auto close/cleanup after the test
    window.show()
    yield window
    window.auto_save_timer.stop()
    window._navigate_to_page("dashboard")


class AgentHarness:
    """Thin wrapper over ``gui.agent_tools`` bound to a live MainWindow (P1-3).

    The plan's ``agent`` surface: ``dump()`` -> dict, ``screenshot(name,
    annotate=True)`` -> Path, ``find(test_id)`` -> QWidget, ``page_ids()`` ->
    list[str], plus pass-throughs for the common drive actions.
    """

    def __init__(self, window, out_dir):
        from gui.agent_tools.runtime import HeadlessGui

        self.window = window
        self.out_dir = Path(out_dir)
        self._gui = HeadlessGui()
        self._gui.window = window
        self._gui.app = getattr(window, "app", None)

    def dump(self, test_id=None):
        return self._gui.dump(test_id)

    def screenshot(self, name="shot", annotate=True, **kwargs):
        result = self._gui.screenshot(
            widget=self.window, out_dir=self.out_dir, name=name, annotate=annotate, **kwargs
        )
        return result.path

    def find(self, test_id):
        return self._gui.find(test_id)

    def page_ids(self):
        return sorted(self.window.pages)

    def navigate(self, page_id):
        self._gui.navigate(page_id)

    def click(self, test_id):
        self._gui.click(test_id)

    def set_text(self, test_id, value):
        self._gui.set_text(test_id, value)

    def get_state(self, test_id):
        return self._gui.get_state(test_id)

    def known_ids(self):
        return self._gui.known_ids()


@pytest.fixture
def agent(main_window, tmp_path):
    """Agent harness fixture (design plan section 3.3) bound to ``main_window``."""
    return AgentHarness(main_window, tmp_path)
