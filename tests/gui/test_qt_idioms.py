"""pytest-qt idiom tests (P1-3) and the ``agent`` harness demo.

plans/agent-gui-observability.md section 3.3: exercises ``qtbot.waitSignal``,
``qtbot.waitUntil``, ``qtbot.captureExceptions``, ``qtbot.mouseClick`` and
``qtbot.screenshot`` (pytest-qt >= 4.4) as the reference idioms for GUI
tests, and demonstrates the shared ``agent`` fixture from
``tests/gui/conftest.py``.  All checks run under ``QT_QPA_PLATFORM=offscreen``.
"""

import json

import pytest

try:
    from PyQt6.QtWidgets import QWidget  # noqa: F401

    PYQT6_AVAILABLE = True
except (ImportError, OSError):
    PYQT6_AVAILABLE = False

pytestmark = pytest.mark.gui


@pytest.mark.gui_widget
class TestQtIdioms:
    """Reference pytest-qt idioms (plan section 3.3)."""

    def test_wait_signal_catches_emission(self, qtbot):
        from PyQt6.QtCore import QObject, QTimer, pyqtSignal

        class Emitter(QObject):
            fired = pyqtSignal(int)

        emitter = Emitter()
        with qtbot.waitSignal(emitter.fired, timeout=5_000) as blocker:
            QTimer.singleShot(0, lambda: emitter.fired.emit(42))
        assert blocker.args == [42]

    def test_wait_until_polls_condition(self, qtbot):
        from PyQt6.QtCore import QTimer

        state = {"done": False}
        QTimer.singleShot(0, lambda: state.update(done=True))
        qtbot.waitUntil(lambda: state["done"], timeout=5_000)

    def test_mouse_click_drives_widget(self, main_window, qtbot):
        """qtbot.mouseClick navigates via the sidebar button."""
        from PyQt6.QtCore import Qt

        button = next(
            b
            for b in main_window.sidebar.button_group.buttons()
            if b.property("pageId") == "materials"
        )
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        assert main_window.content_stack.currentWidget() is main_window.pages["materials"]

    def test_capture_exceptions_clean_workflow(self, agent, qtbot):
        """qtbot.captureExceptions() stays empty across a GUI workflow."""
        with qtbot.captureExceptions() as captured:
            agent.navigate("materials")
            agent.get_state("sidebar.navButton.materials")
            agent.set_text("page.materials.typeFilter", "Samples")
            agent.navigate("dashboard")
        assert captured == [], f"unexpected Qt exceptions: {captured}"

    def test_qtbot_screenshot(self, main_window, qtbot):
        """qtbot.screenshot (pytest-qt >= 4.4) writes a PNG."""
        path = qtbot.screenshot(main_window, "main_window")
        assert path.exists()
        assert path.suffix == ".png"


@pytest.mark.gui_workflow
class TestAgentFixture:
    """Demo of the shared ``agent`` harness fixture (plan section 3.3)."""

    def test_agent_surface(self, agent):
        assert agent.page_ids() == [
            "assays",
            "dashboard",
            "files",
            "images",
            "materials",
            "ontology",
            "process_sequence",
            "settings",
            "studies",
            "templates",
        ]

        widget = agent.find("sidebar.navButton.materials")
        assert widget.text() == "Materials"

        tree = agent.dump()
        assert tree["schema"] == "isa-gui/widget-tree/1"
        assert tree["root"]["testId"] == "window.main"

    def test_agent_screenshot_annotate(self, agent):
        from gui.agent_tools.annotate import legend_path_for

        path = agent.screenshot("agent_demo", annotate=True)
        assert path.exists()
        legend = legend_path_for(path)
        assert legend.exists()
        data = json.loads(legend.read_text(encoding="utf-8"))
        assert data, "expected at least one mark in the legend sidecar"
        assert {m["test_id"] for m in data} <= set(agent.known_ids())
