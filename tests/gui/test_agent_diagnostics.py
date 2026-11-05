"""Crash-bundle / event-log / annotated-screenshot tests (P1-1, P1-2).

Acceptance criteria from plans/agent-gui-observability.md section 5:

- P1-1 crash: a raise inside a notify()-dispatched slot writes a crash bundle
  with ``exception.json``/``widget_tree.json``/``screenshot.png``/
  ``events.jsonl``/``meta.json``; the threading.excepthook path writes a
  bundle; duplicate crashes get distinct timestamped dirs; a broken hook
  never masks the original exception.
- P1-1 events: clicking a button with a testId appends one JSONL line with
  ``event: "click"``; navigating emits ``navigate``/``page_enter``/
  ``page_exit``; every line parses as JSON and carries ``ts``/``seq``/
  ``session``; the ring buffer returns the last N events.
- P1-2 annotate: one badge per visible testId widget; legend panel text
  includes each testId; ``<name>.legend.json`` matches badge numbers;
  per-page crops <= 2048 px max edge; ``theme="light"`` and ``theme="dark"``
  both produce captures.

All checks run under ``QT_QPA_PLATFORM=offscreen``.
"""

import json
import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QWidget

    PYQT6_AVAILABLE = True
except (ImportError, OSError):
    PYQT6_AVAILABLE = False

pytestmark = pytest.mark.gui

REPO_ROOT = Path(__file__).resolve().parents[2]

# The subprocess probe boots a real StewardApp (fresh QApplication, so the
# StewardNotifyMixin is active) and raises in three dispatch paths.
_CRASH_PROBE = """
import sys

from PyQt6.QtCore import QThread, QTimer

from gui.agent_tools.crash import install_crash_hooks
from gui.agent_tools.runtime import HeadlessGui

out_root = sys.argv[1]
gui = HeadlessGui(theme=None)  # theme=None: never rewrite user settings
gui.start()
install_crash_hooks(gui.app, out_root=out_root)


def boom():
    raise RuntimeError("notify-slot boom")


class BoomThread(QThread):
    def run(self):
        raise RuntimeError("qthread boom")


QTimer.singleShot(0, boom)          # slot raise during event dispatch
QTimer.singleShot(500, gui.app.quit)
gui.app.exec()

worker = BoomThread()               # virtual-override raise on a QThread
worker.start()
worker.wait(10_000)

print("SURVIVED", flush=True)
# Bypass interpreter/Qt teardown: destroying a QThread whose run() aborted on
# a Python exception can access-violate at shutdown on this Qt build (the
# bundle is already written and output flushed at this point).
import os

os._exit(0)
"""

# U-01: the boot probe relies on HeadlessGui.start() installing the hook trio
# itself (no explicit install_crash_hooks before the injected exception).
_BOOT_PROBE = """
import json
import sys

from PyQt6.QtCore import QTimer

from gui.agent_tools import crash as crash_mod
from gui.agent_tools import events as events_mod
from gui.agent_tools.runtime import HeadlessGui, ensure_offscreen_platform

ensure_offscreen_platform()
out_root = sys.argv[1]

gui = HeadlessGui()  # theme=None: never rewrite user settings (U-06)
gui.start()

# U-01 acceptance 1: booting installed the hook trio.
installed = {
    "hooks": crash_mod._hooks_installed,
    "filter": events_mod._installed_filter is not None,
}

# Point the already-installed hooks at the test's out_root (install_crash_hooks
# is idempotent: re-installing only updates out_root).
crash_mod.install_crash_hooks(gui.app, out_root=out_root)


def boom():
    raise RuntimeError("boot-slot boom")


QTimer.singleShot(0, boom)             # slot raise during event dispatch
QTimer.singleShot(500, gui.app.quit)
gui.app.exec()

# U-01 acceptance 2: the session survives and subsequent actions still work.
gui.navigate("materials")

print(json.dumps({"installed": installed, "survived": True}), flush=True)
import os

os._exit(0)
"""

# U-01 acceptance 3: ISA_STEWARD_AGENT_DIAGNOSTICS=0 skips the whole trio.
_OPTOUT_PROBE = """
import json

from gui.agent_tools import crash as crash_mod
from gui.agent_tools import events as events_mod
from gui.agent_tools.runtime import HeadlessGui, ensure_offscreen_platform

ensure_offscreen_platform()
gui = HeadlessGui()
gui.start()
print(json.dumps({
    "hooks": crash_mod._hooks_installed,
    "filter": events_mod._installed_filter is not None,
}), flush=True)
import os

os._exit(0)
"""


def _bundle_dirs(out_root: Path) -> list[Path]:
    return sorted(p for p in out_root.iterdir() if p.is_dir())


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.gui_workflow
class TestCrashBundles:
    """P1-1: crash bundles in crash_reports/<timestamp>/."""

    def test_dispatched_slot_exception_writes_bundle(self, tmp_path):
        """A slot raise (via sys.excepthook, fatal=false) does not kill the GUI.

        Also covers the QThread.run raise (PyQt routes virtual-override
        exceptions through sys.excepthook; fatal=true off the dispatch path),
        matching the plan's thread-crash acceptance criterion.
        """
        import os

        out_root = tmp_path / "crash_reports"
        script = tmp_path / "crash_probe.py"
        script.write_text(_CRASH_PROBE, encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT)  # the probe lives outside the repo
        proc = subprocess.run(
            [sys.executable, str(script), str(out_root)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
            timeout=300,
        )
        assert proc.returncode == 0, proc.stderr
        assert "SURVIVED" in proc.stdout

        bundles = _bundle_dirs(out_root)
        assert len(bundles) == 2, [p.name for p in bundles]
        by_message = {_read_json(b / "exception.json")["message"]: b for b in bundles}
        assert set(by_message) == {"notify-slot boom", "qthread boom"}

        slot = _read_json(by_message["notify-slot boom"] / "exception.json")
        assert slot["type"] == "RuntimeError"
        assert slot["fatal"] is False  # event dispatch: GUI survives (plan 2.5)
        slot_meta = _read_json(by_message["notify-slot boom"] / "meta.json")
        assert slot_meta["context"]["hook"] == "notify"

        thread = _read_json(by_message["qthread boom"] / "exception.json")
        assert thread["type"] == "RuntimeError"
        assert thread["fatal"] is True

        # Full artifact set for the GUI-thread bundle; thread bundles skip the
        # widget_tree/screenshot artifacts (widget access is GUI-thread-only).
        for name in (
            "exception.txt",
            "exception.json",
            "widget_tree.json",
            "widget_tree.txt",
            "screenshot.png",
            "events.jsonl",
            "meta.json",
        ):
            assert (by_message["notify-slot boom"] / name).exists(), f"{name} missing"
        for name in ("exception.txt", "exception.json", "events.jsonl", "meta.json"):
            assert (by_message["qthread boom"] / name).exists(), f"{name} missing"

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
    def test_threading_excepthook_writes_bundle(self, main_window, tmp_path):
        """A crashing stdlib thread writes a bundle via threading.excepthook."""
        from gui.agent_tools import crash as crash_mod

        out_root = tmp_path / "crash_reports"
        crash_mod.install_crash_hooks(out_root=out_root)
        try:

            def boom():
                raise RuntimeError("thread boom")

            worker = threading.Thread(target=boom, name="boom-thread")
            worker.start()
            worker.join(10_000)
            assert not worker.is_alive()

            bundles = _bundle_dirs(out_root)
            assert len(bundles) == 1
            exc = _read_json(bundles[0] / "exception.json")
            assert exc["type"] == "RuntimeError"
            assert exc["message"] == "thread boom"
            assert exc["thread"] == "boom-thread"
            assert exc["fatal"] is True
        finally:
            crash_mod.uninstall_crash_hooks()

    def test_bundle_contents_and_duplicate_dirs(self, main_window, tmp_path):
        """write_crash_bundle emits every artifact; repeats never overwrite."""
        import sys as _sys

        from gui.agent_tools.crash import write_crash_bundle

        out_root = tmp_path / "crash_reports"
        try:
            raise ValueError("first boom")
        except ValueError:
            exc_type, exc_value, exc_tb = _sys.exc_info()

        first = write_crash_bundle(
            exc_type, exc_value, exc_tb, out_root=out_root, context={"fatal": True, "hook": "test"}
        )
        second = write_crash_bundle(
            exc_type, exc_value, exc_tb, out_root=out_root, context={"fatal": True, "hook": "test"}
        )
        assert first != second
        assert first.exists() and second.exists()

        for name in (
            "exception.txt",
            "exception.json",
            "widget_tree.json",
            "widget_tree.txt",
            "screenshot.png",
            "events.jsonl",
            "meta.json",
        ):
            assert (first / name).exists(), f"{name} missing"

        exc = _read_json(first / "exception.json")
        assert exc == {
            "type": "ValueError",
            "message": "first boom",
            "thread": threading.current_thread().name,
            "fatal": True,
        }
        assert "ValueError: first boom" in (first / "exception.txt").read_text(encoding="utf-8")

        tree = _read_json(first / "widget_tree.json")
        assert tree["schema"] == "isa-gui/widget-tree/1"
        assert tree["root"]["testId"] == "window.main"

        meta = _read_json(first / "meta.json")
        for key in (
            "python",
            "qt",
            "pyqt",
            "platform",
            "qt_qpa_platform",
            "theme",
            "page",
            "argv",
            "cwd",
            "context",
            "errors",
        ):
            assert key in meta, f"meta.json missing {key!r}"
        assert meta["page"] == "page.dashboard"
        assert meta["context"]["hook"] == "test"

        rows = [
            json.loads(line)
            for line in (first / "events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert rows, "events.jsonl must contain the ring-buffer tail"
        assert rows[-1]["kind"] == "crash"
        assert rows[-1]["event"] == "crash"

    def test_notify_mixin_swallows_and_marks_non_fatal(self, tmp_path, monkeypatch):
        """The plan's notify() override: bundle with fatal=false, returns True."""
        from gui.agent_tools import crash as crash_mod

        written = {}

        class _FailingBase:
            def notify(self, receiver, event):
                raise RuntimeError("slot boom")

        class _App(crash_mod.StewardNotifyMixin, _FailingBase):
            pass

        def _record(*args, **kwargs):
            written["args"] = (args, kwargs)
            return tmp_path

        monkeypatch.setattr(crash_mod, "write_crash_bundle", _record)

        # Without hooks installed the mixin is inert (delegates unchanged).
        app = _App()
        with pytest.raises(RuntimeError):
            app.notify(None, None)
        assert not written

        crash_mod.install_crash_hooks(out_root=tmp_path)
        try:
            assert app.notify(None, None) is True
        finally:
            crash_mod.uninstall_crash_hooks()
        assert written, "write_crash_bundle was not called"
        kwargs = written["args"][1]
        assert kwargs["context"]["fatal"] is False
        assert kwargs["context"]["hook"] == "notify"

    def test_broken_hook_never_masks_original(self, monkeypatch, tmp_path):
        """A failing bundle writer must not swallow the original excepthook."""
        import sys as _sys

        from gui.agent_tools import crash as crash_mod

        chained = []
        monkeypatch.setattr(_sys, "excepthook", lambda *a: chained.append(a))

        def _broken(*args, **kwargs):
            raise RuntimeError("bundle writer broken")

        crash_mod.install_crash_hooks(out_root=tmp_path)
        monkeypatch.setattr(crash_mod, "write_crash_bundle", _broken)
        try:
            _sys.excepthook(ValueError, ValueError("orig"), None)
        finally:
            crash_mod.uninstall_crash_hooks()
        assert chained, "the previously installed excepthook must still be called"


@pytest.mark.gui_workflow
class TestBootDiagnostics:
    """U-01: HeadlessGui.start() installs the P1-1 hook trio (CLI/MCP inherit).

    Both probes run in a fresh subprocess: the hook state is process-global and
    the opt-out assertion requires a process that never saw an install.
    """

    @staticmethod
    def _run_probe(tmp_path, script_body, env_extra=None):
        import os

        script = tmp_path / "probe.py"
        script.write_text(script_body, encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT)  # the probe lives outside the repo
        if env_extra:
            env.update(env_extra)
        proc = subprocess.run(
            [sys.executable, str(script), str(tmp_path / "crash_reports")],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
            timeout=300,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_boot_installs_hooks_and_session_survives_slot_exception(self, tmp_path):
        """Boot installs the trio; a slot exception writes a bundle and the
        session continues (subsequent actions still work)."""
        out_root = tmp_path / "crash_reports"
        result = self._run_probe(tmp_path, _BOOT_PROBE)

        assert result["installed"] == {"hooks": True, "filter": True}
        assert result["survived"] is True

        bundles = _bundle_dirs(out_root)
        assert len(bundles) == 1, [p.name for p in bundles]
        bundle = bundles[0]
        exc = _read_json(bundle / "exception.json")
        assert exc["type"] == "RuntimeError"
        assert exc["message"] == "boot-slot boom"
        assert exc["fatal"] is False  # event dispatch: the session survives
        for name in (
            "exception.txt",
            "exception.json",
            "widget_tree.json",
            "widget_tree.txt",
            "screenshot.png",
            "events.jsonl",
            "meta.json",
        ):
            assert (bundle / name).exists(), f"{name} missing"

    def test_diagnostics_opt_out_env_skips_install(self, tmp_path):
        """ISA_STEWARD_AGENT_DIAGNOSTICS=0: no hooks, no event filter."""
        result = self._run_probe(
            tmp_path, _OPTOUT_PROBE, env_extra={"ISA_STEWARD_AGENT_DIAGNOSTICS": "0"}
        )
        assert result == {"hooks": False, "filter": False}


@pytest.mark.gui_widget
class TestGuiEventLog:
    """P1-1: JSONL GUI-event stream (schema isa-gui/event/1)."""

    @pytest.fixture
    def event_log(self, qapp, monkeypatch, tmp_path):
        """Redirect the shared event log to a tmp file + install the filter."""
        from gui.agent_tools import events as events_mod

        logger = events_mod.GuiEventLogger(tmp_path / "gui_events.jsonl")
        monkeypatch.setattr(events_mod, "_shared_logger", logger)
        events_mod.install_event_filter(qapp)
        yield logger
        events_mod.remove_event_filter(qapp)
        logger.close()

    @staticmethod
    def _rows(logger):
        if not logger.path.exists():
            return []
        lines = logger.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def test_click_emits_one_click_event(self, main_window, event_log, qtbot):
        """Clicking a button with a testId appends one ``click`` row."""
        from PyQt6.QtCore import Qt

        button = next(
            b
            for b in main_window.sidebar.button_group.buttons()
            if b.property("pageId") == "materials"
        )
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: any(r["event"] == "click" for r in self._rows(event_log)))

        clicks = [r for r in self._rows(event_log) if r["event"] == "click"]
        assert len(clicks) == 1
        row = clicks[0]
        assert row["test_id"] == "sidebar.navButton.materials"
        assert row["class"] == "QPushButton"
        assert row["object_name"] == "sidebarButton"
        assert row["detail"]["text"] == "Materials"

    def test_navigation_emits_page_events(self, main_window, event_log):
        """Navigating emits page_exit / navigate / page_enter in order."""
        main_window._navigate_to_page("materials")
        rows = [r for r in self._rows(event_log) if r["kind"] == "gui_event"]
        tail = rows[-3:]
        assert [r["event"] for r in tail] == ["page_exit", "navigate", "page_enter"]
        assert tail[0]["test_id"] == "page.dashboard"
        assert tail[1]["detail"]["page"] == "materials"
        assert tail[2]["test_id"] == "page.materials"
        assert tail[2]["page"] == "materials"

    def test_data_changed_event(self, main_window, event_log):
        """The auto-save path logs ``data_changed`` with the page context."""
        main_window.pages["materials"].dataChanged.emit()
        rows = [r for r in self._rows(event_log) if r["event"] == "data_changed"]
        assert rows, "expected a data_changed row"
        assert rows[-1]["test_id"] == "page.materials"

    def test_key_press_event(self, main_window, event_log, qtbot):
        """Key presses on tagged widgets are logged (capture point 1).

        Key events propagate to parents when unhandled, so the filter logs one
        row per delivery level; assert on the row for the target widget.
        """
        from PyQt6.QtCore import Qt

        from gui.agent_tools.ids import find_by_test_id

        main_window._navigate_to_page("materials")
        field = find_by_test_id(main_window, "page.materials.typeFilter")
        qtbot.keyClick(field, Qt.Key.Key_A)
        qtbot.waitUntil(lambda: any(r["event"] == "key_press" for r in self._rows(event_log)))
        rows = [
            r
            for r in self._rows(event_log)
            if r["event"] == "key_press" and r["test_id"] == "page.materials.typeFilter"
        ]
        assert rows, "expected a key_press row for the target widget"
        assert rows[-1]["detail"]["key"] == int(Qt.Key.Key_A)

    def test_focus_in_event(self, main_window, event_log):
        """Focus changes on tagged widgets are logged (capture point 1)."""
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QFocusEvent

        from gui.agent_tools.events import GuiEventFilter
        from gui.agent_tools.ids import find_by_test_id

        field = find_by_test_id(main_window, "page.materials.typeFilter")
        GuiEventFilter().eventFilter(field, QFocusEvent(QEvent.Type.FocusIn))
        rows = [
            r
            for r in self._rows(event_log)
            if r["event"] == "focus_in" and r["test_id"] == "page.materials.typeFilter"
        ]
        assert rows, "expected a focus_in row for the target widget"

    def test_every_line_has_ts_seq_session(self, main_window, event_log):
        """Every row parses as JSON and carries ts/seq/session (schema fields)."""
        main_window._navigate_to_page("materials")
        rows = self._rows(event_log)
        assert rows
        sessions = set()
        seqs = []
        for row in rows:
            for key in ("ts", "seq", "session", "kind", "event", "detail"):
                assert key in row, f"row missing {key!r}: {row}"
            assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", row["ts"])
            sessions.add(row["session"])
            seqs.append(row["seq"])
        assert len(sessions) == 1
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)

    def test_ring_buffer_returns_last_n(self, tmp_path):
        from gui.agent_tools.events import GuiEventLogger

        logger = GuiEventLogger(tmp_path / "ring.jsonl", max_buffer=3)
        for i in range(5):
            logger.log("gui_event", "click", detail={"i": i})
        assert [r["detail"]["i"] for r in logger.recent()] == [2, 3, 4]
        assert [r["detail"]["i"] for r in logger.recent(2)] == [3, 4]
        logger.close()

    def test_env_var_overrides_path(self, tmp_path, monkeypatch):
        from gui.agent_tools.events import EVENTS_PATH_ENV, GuiEventLogger

        target = tmp_path / "from_env.jsonl"
        monkeypatch.setenv(EVENTS_PATH_ENV, str(target))
        logger = GuiEventLogger()
        assert logger.path == target.resolve()
        logger.log("gui_event", "navigate", detail={"page": "x"})
        logger.close()
        assert target.exists()

    def test_setup_gui_event_log_attaches_log_handler(self, tmp_path):
        """utils.logging_config integration: WARNING+ records flow in as kind=log."""
        import logging

        from gui.agent_tools.events import get_event_logger
        from utils.logging_config import JsonlEventHandler, setup_gui_event_log

        setup_gui_event_log(tmp_path / "stream.jsonl")  # side effect: attaches the handler
        try:
            logging.getLogger("probe.logger").error("probe failure %d", 7)
            rows = [
                json.loads(line)
                for line in (tmp_path / "stream.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            assert rows
            row = rows[-1]
            assert row["kind"] == "log"
            assert row["event"] == "error"
            assert row["detail"]["message"] == "probe failure 7"
            assert row["detail"]["logger"] == "probe.logger"
            root = logging.getLogger()
            assert sum(isinstance(h, JsonlEventHandler) for h in root.handlers) == 1
        finally:
            root = logging.getLogger()
            root.handlers = [h for h in root.handlers if not isinstance(h, JsonlEventHandler)]
            # repoint the shared logger back at the repo default for later tests
            get_event_logger(REPO_ROOT / "reports" / "gui_events.jsonl")


@pytest.mark.gui_widget
class TestAnnotate:
    """P1-2: set-of-marks annotated screenshots."""

    def test_collect_marks_filters_and_orders(self, qtbot):
        from gui.agent_tools.annotate import collect_marks
        from gui.agent_tools.ids import set_test_id

        root = QWidget()
        qtbot.addWidget(root)
        root.resize(200, 100)
        set_test_id(root, "widget.test.root")

        child = QWidget(root)
        set_test_id(child, "widget.test.a")
        child.setGeometry(10, 10, 50, 30)

        hidden = QWidget(root)
        set_test_id(hidden, "widget.test.hidden")
        hidden.setGeometry(0, 0, 20, 20)
        hidden.hide()

        untagged = QWidget(root)
        untagged.setGeometry(60, 10, 10, 10)

        grandchild = QWidget(child)
        set_test_id(grandchild, "widget.test.b")
        grandchild.setGeometry(5, 5, 10, 10)

        root.show()
        marks = collect_marks(root)

        # DFS order, root first; hidden and untagged widgets excluded
        assert [m.test_id for m in marks] == ["widget.test.root", "widget.test.a", "widget.test.b"]
        assert [m.index for m in marks] == [1, 2, 3]
        # root-anchored global geometry (matches dump geometry space)
        assert marks[0].rect == (0, 0, 200, 100)
        assert marks[1].rect == (10, 10, 50, 30)
        assert marks[2].rect == (15, 15, 10, 10)
        assert all(m.label for m in marks)

    def test_collect_marks_drops_scroll_clipped_widgets(self, qtbot):
        """U-15: widgets clipped by a scroll viewport produce no mark."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QScrollArea, QWidget

        from gui.agent_tools.annotate import collect_marks
        from gui.agent_tools.ids import set_test_id

        root = QWidget()
        qtbot.addWidget(root)
        root.resize(200, 100)
        set_test_id(root, "widget.test.root")

        scroll = QScrollArea(root)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setGeometry(0, 0, 180, 80)
        scroll.setWidgetResizable(False)
        content = QWidget()
        content.resize(180, 400)  # extends far below the 80px viewport
        scroll.setWidget(content)

        visible_child = QWidget(content)
        set_test_id(visible_child, "widget.test.visible")
        visible_child.setGeometry(10, 10, 50, 30)  # fully inside the viewport

        clipped_child = QWidget(content)
        set_test_id(clipped_child, "widget.test.clipped")
        clipped_child.setGeometry(10, 300, 50, 30)  # fully below the fold

        partial_child = QWidget(content)
        set_test_id(partial_child, "widget.test.partial")
        partial_child.setGeometry(10, 60, 50, 40)  # straddles the fold

        root.show()
        marks = collect_marks(root)

        # U-15: fully AND partially clipped marks are dropped (prefer drop
        # over shrinking); indices renumber over the surviving DFS order.
        assert [m.test_id for m in marks] == ["widget.test.root", "widget.test.visible"]
        assert [m.index for m in marks] == [1, 2]
        # every surviving rect lies fully inside the captured root rect
        for mark in marks:
            x, y, w, h = mark.rect
            assert x >= 0 and y >= 0 and x + w <= 200 and y + h <= 100, mark

    def test_annotated_canvas_matches_grab_when_content_is_clipped(self, qtbot, tmp_path):
        """U-15: with every tagged widget clipped, the canvas equals the grab."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QScrollArea, QWidget

        from gui.agent_tools.ids import set_test_id
        from gui.agent_tools.screenshot import grab_widget, gui_screenshot

        root = QWidget()
        qtbot.addWidget(root)
        root.resize(200, 100)
        # root stays untagged; the only tagged widget is fully below the fold.
        scroll = QScrollArea(root)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setGeometry(0, 0, 180, 80)
        scroll.setWidgetResizable(False)
        content = QWidget()
        content.resize(180, 400)
        scroll.setWidget(content)
        clipped = QWidget(content)
        set_test_id(clipped, "widget.test.clipped")
        clipped.setGeometry(10, 300, 50, 30)

        root.show()
        pixmap = grab_widget(root)
        result = gui_screenshot(root, out_dir=tmp_path, name="clipped", annotate=True)

        assert result.marks == []
        # annotated canvas == grab size (no legend, no grown legend panel)
        assert (result.width, result.height) == (pixmap.width(), pixmap.height())

    def test_annotate_draws_badges_and_legend(self):
        from PyQt6.QtGui import QColor, QPixmap

        from gui.agent_tools.annotate import LEGEND_MIN_WIDTH, Mark, annotate, legend_line

        pixmap = QPixmap(200, 100)
        pixmap.fill(QColor("#ffffff"))
        marks = [
            Mark(1, "widget.test.a", (50, 50, 40, 20), "Save"),
            Mark(2, "widget.test.b", (10, 10, 20, 10), "Cancel"),
        ]

        out, drawn = annotate(pixmap, marks)

        assert drawn == marks
        # legend panel appended on the right
        assert out.width() >= pixmap.width() + LEGEND_MIN_WIDTH
        assert out.height() >= pixmap.height()
        # legend line format: "#1  widget.test.a  —  Save", full testIds included
        assert legend_line(marks[0]) == "#1  widget.test.a  —  Save"
        for mark in marks:
            assert mark.test_id in legend_line(mark)
        # a badge pixel was painted (differs from the white content background)
        badge_pixel = out.toImage().pixelColor(50, 50)
        assert (badge_pixel.red(), badge_pixel.green(), badge_pixel.blue()) != (255, 255, 255)

        # empty marks: no legend, content preserved
        plain, nothing = annotate(pixmap, [])
        assert nothing == []
        assert (plain.width(), plain.height()) == (pixmap.width(), pixmap.height())

    def test_annotated_capture_writes_legend_sidecar(self, main_window, tmp_path):
        from gui.agent_tools.annotate import collect_marks, legend_path_for
        from gui.agent_tools.screenshot import gui_screenshot

        result = gui_screenshot(main_window, out_dir=tmp_path, name="annotated", annotate=True)
        assert result.marks == collect_marks(main_window)
        assert result.marks, "window/main and page widgets carry testIds"

        legend = legend_path_for(result.path)
        assert legend.exists()
        data = json.loads(legend.read_text(encoding="utf-8"))
        assert [m["index"] for m in data] == list(range(1, len(data) + 1))
        assert [m["test_id"] for m in data] == [m.test_id for m in result.marks]
        for entry in data:
            assert set(entry) == {"index", "test_id", "rect", "label"}
            assert len(entry["rect"]) == 4

    def test_per_page_crops_capped_at_max_edge(self, main_window, tmp_path):
        from gui.agent_tools.annotate import legend_path_for
        from gui.agent_tools.screenshot import gui_screenshot

        for page_id, page in main_window.pages.items():
            result = gui_screenshot(
                page, out_dir=tmp_path, name=f"crop_{page_id}", annotate=True, max_edge=2048
            )
            assert max(result.width, result.height) <= 2048, page_id
            assert legend_path_for(result.path).exists(), page_id
            assert result.marks, f"expected marks on {page_id}"

    def test_theme_light_and_dark_both_capture(self, main_window, tmp_path):
        from gui.agent_tools.screenshot import gui_screenshot

        try:
            light = gui_screenshot(main_window, out_dir=tmp_path, name="light", theme="light")
            dark = gui_screenshot(main_window, out_dir=tmp_path, name="dark", theme="dark")
            assert light.path.exists() and dark.path.exists()
            assert (
                light.path.read_bytes() != dark.path.read_bytes()
            ), "light and dark captures should render differently"
        finally:
            if PYQT6_AVAILABLE:
                QApplication.instance().setStyleSheet("")
