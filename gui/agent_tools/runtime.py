"""
Headless GUI lifecycle wrapper for agent tooling (P0-4).

``HeadlessGui`` boots the real application (``StewardApp`` + ``MainWindow``)
offscreen and exposes the small action surface the agent needs:
navigate / find / click / set_text / get_state / dump / screenshot.

It is safe to use both from the CLI (fresh process, real ``StewardApp``) and
from tests (an existing ``QApplication`` is reused; a lightweight settings
shim mirrors the ``_StubApp`` pattern used in tests/gui/test_steward_app.py).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, MutableMapping, Optional, cast

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QWidget

from .dump import _widget_text, _widget_value, dump_widget_tree
from .events import log_gui_event
from .ids import WidgetIdError, find_by_test_id, get_test_id
from .screenshot import ScreenshotResult, gui_screenshot

_WIN_FONT_DIR = "C:\\Windows\\Fonts"


def _windows_fontdir() -> Optional[str]:
    """X-2 default: ``C:\\Windows\\Fonts`` on Windows when it exists.

    Returns ``None`` off-Windows (behavior unchanged there).  Split out as a
    seam so tests can simulate either platform cheaply.
    """
    if os.name != "nt":
        return None
    fontdir = Path(_WIN_FONT_DIR)
    return str(fontdir) if fontdir.is_dir() else None


def ensure_offscreen_fontdir(env: Optional[MutableMapping[str, str]] = None) -> None:
    """X-2: give offscreen renders a usable font dir on Windows.

    When the effective platform is ``offscreen``, running on Windows, and
    ``QT_QPA_FONTDIR`` is unset/blank, fall back to ``C:\\Windows\\Fonts``
    (when that directory exists) so offscreen captures render real glyphs
    without a manual env var.  An explicit ``QT_QPA_FONTDIR`` is never
    overridden; non-Windows behavior is unchanged.  Must run BEFORE the
    ``QGuiApplication`` is created -- the offscreen font database reads the
    variable once at construction.
    """
    target = os.environ if env is None else env
    if str(target.get("QT_QPA_PLATFORM") or "").strip() != "offscreen":
        return
    if str(target.get("QT_QPA_FONTDIR") or "").strip():
        return  # explicit value wins
    fontdir = _windows_fontdir()
    if fontdir:
        target["QT_QPA_FONTDIR"] = fontdir


def ensure_offscreen_platform(env: Optional[MutableMapping[str, str]] = None) -> str:
    """Normalize ``QT_QPA_PLATFORM`` in ``env`` (default: ``os.environ``).

    Returns the normalized value.  A whitespace-polluted value (the cmd.exe
    ``set VAR=value && ...`` trailing-space pitfall) makes Qt fail to match a
    platform plugin and abort the process (``qFatal`` -> ``abort``) before any
    Python-level diagnostic runs.  Unset or blank values fall back to
    ``"offscreen"``; any other value is kept (stripped) so callers can still
    pin a platform.

    X-2: afterwards the ``QT_QPA_FONTDIR`` fallback
    (:func:`ensure_offscreen_fontdir`) is applied for offscreen runs.
    """
    target = os.environ if env is None else env
    value = str(target.get("QT_QPA_PLATFORM") or "").strip()
    target["QT_QPA_PLATFORM"] = value or "offscreen"
    ensure_offscreen_fontdir(target)
    return target["QT_QPA_PLATFORM"]


class _AgentAppShim:
    """Settings/window-state facade for an already-existing QApplication.

    Mirrors the ``_StubApp`` pattern from tests/gui/test_steward_app.py so
    ``MainWindow`` can be constructed when pytest-qt (or another harness)
    already owns the ``QApplication`` singleton.
    """

    def __init__(self, app: QApplication):
        self._app = app
        self.settings = QSettings("isa-json-steward-agent", "DataSteward")

    def get_window_geometry(self):
        return None

    def get_window_state(self):
        return None

    def set_window_geometry(self, geometry) -> None:
        pass

    def set_window_state(self, state) -> None:
        pass

    def set_current_investigation(self, investigation_id: str) -> None:
        pass

    def set_current_study(self, study_id: str) -> None:
        pass

    def apply_theme(self, theme: str, persist: bool = False) -> None:
        """Apply a theme QSS; write ``QSettings`` only when ``persist``.

        Mirrors ``StewardApp.apply_theme`` (U-06): agent contexts are
        session-only and never rewrite the user's persisted preference.
        """
        if persist:
            self.settings.setValue("gui/theme", theme)
        style_path = Path(__file__).parent.parent / "resources" / "styles" / f"{theme}.qss"
        if style_path.exists():
            self._app.setStyleSheet(style_path.read_text(encoding="utf-8"))

    def set_theme(self, theme: str) -> None:
        """Apply a theme session-only (U-06: never writes ``QSettings``)."""
        self.apply_theme(theme, persist=False)


class HeadlessGui:
    """Boot, drive, and tear down the GUI from scripts/tests/CLI."""

    def __init__(
        self,
        argv: Optional[list[str]] = None,
        *,
        theme: Optional[str] = None,
        profile: Optional[str] = None,
    ) -> None:
        """``theme`` defaults to ``None`` (keep the theme currently configured
        in the application settings); pass ``"light"``/``"dark"`` to force a
        theme for the session (never persisted -- U-06).  ``profile`` pins a
        profile directory, overriding ``ISA_STEWARD_PROFILE`` / ``*-profile/``
        auto-discovery (U-05)."""
        self._argv = list(argv) if argv is not None else ["python", "-m", "gui.agent_tools"]
        self._theme = theme
        self._profile = profile
        self.app: Any = None
        self.window: Any = None
        self._owns_app = False

    # -- lifecycle -----------------------------------------------------

    def _activate_profile(self) -> None:
        """Resolve and activate the profile (U-05).

        Priority: the ``profile=`` kwarg, then ``ISA_STEWARD_PROFILE`` env /
        ``*-profile/`` auto-discovery (same order as ``gui/main.py``).  Must
        run BEFORE the application object is created -- ``StewardApp.__init__``
        calls ``get_profile()`` and freezes the singleton.  When nothing is
        discovered the default core ``config/`` profile is kept untouched.
        """
        from utils.config_loader import (
            ProfileConfigError,
            discover_profile_dir,
            get_profile,
            set_profile,
        )

        repo_root = Path(__file__).resolve().parents[2]
        profile_dir: Optional[Path]
        if self._profile:
            profile_dir = Path(self._profile)
            if not profile_dir.is_dir():
                raise ValueError(f"profile directory not found: {profile_dir}")
            profile_dir = profile_dir.resolve()
        else:
            profile_dir = discover_profile_dir(repo_root)
        if profile_dir is None:
            return

        set_profile(str(profile_dir))
        try:
            profile = get_profile()
            profile.profile  # force resolution (triggers the min_core_version check)
            profile.log_profile_load_summary()
        except ProfileConfigError as exc:
            raise RuntimeError(f"profile activation failed for {profile_dir}: {exc}") from exc

    def _install_diagnostics(self) -> None:
        """Install the P1-1 hook trio (U-01), unless explicitly opted out.

        Mirrors ``gui/main.py``: ``setup_gui_event_log()`` ->
        ``install_event_filter()`` -> ``install_crash_hooks()``.  All three
        are idempotent, so re-installing across sessions is safe.  Set
        ``ISA_STEWARD_AGENT_DIAGNOSTICS=0`` to skip the install entirely.
        """
        if os.environ.get("ISA_STEWARD_AGENT_DIAGNOSTICS", "").strip() == "0":
            return
        from gui.agent_tools.crash import install_crash_hooks
        from gui.agent_tools.events import install_event_filter
        from utils.logging_config import setup_gui_event_log

        qapp = QApplication.instance()
        setup_gui_event_log()
        if isinstance(qapp, QApplication):
            install_event_filter(qapp)
            install_crash_hooks(qapp)

    def start(self) -> None:
        """Create the application + main window, show them, pump events."""
        if self.window is not None:
            return

        # X-2: font env BEFORE the application object exists -- the QPA font
        # database reads QT_QPA_FONTDIR once at QGuiApplication construction.
        ensure_offscreen_fontdir()

        # U-05: profile BEFORE the app object is created (it freezes the
        # profile singleton in StewardApp.__init__).
        self._activate_profile()

        existing = QApplication.instance()
        if existing is None:
            from gui.app import StewardApp

            self.app = StewardApp(self._argv)
            self._owns_app = True
        elif hasattr(existing, "settings") and hasattr(existing, "set_theme"):
            self.app = existing  # a real StewardApp already exists
            self._owns_app = False
        else:
            # QApplication.instance() is typed QCoreApplication | None in the
            # PyQt6 stubs; the singleton is always a QApplication here (the
            # shim needs QApplication.setStyleSheet()).
            self.app = _AgentAppShim(cast(QApplication, existing))
            self._owns_app = False

        if self._theme:
            # U-06: session-only theme switch (never persisted).
            from .screenshot import _apply_theme

            _apply_theme(self._theme)

        # U-01: diagnostics trio so a slot exception during an agent session
        # writes a crash bundle instead of aborting the process (0xC0000409).
        self._install_diagnostics()

        from gui.main_window import MainWindow

        self.window = MainWindow(self.app)
        self.window.show()
        self.process_events(100)

    def shutdown(self) -> None:
        """Tear down the window and release the application we own.

        Deliberately *hides* rather than ``close()``s the window: MainWindow's
        ``closeEvent`` persists window geometry and auto-saves page data, which
        must not happen as a side effect of an agent tool run.

        Idempotent (N9): a second ``shutdown()`` is a no-op -- the Qt
        teardown hazard documented in AGENTS.md section 7 ("Teardown
        hazards") is interpreter-exit behavior, not this call.
        """
        if self.window is not None:
            timer = getattr(self.window, "auto_save_timer", None)
            if timer is not None:
                timer.stop()
            self.window.hide()
            self.window.deleteLater()
            self.window = None
            self.process_events(20)
        if self._owns_app and self.app is not None:
            self.app.quit()
            self.app = None
            self._owns_app = False

    def __enter__(self) -> "HeadlessGui":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown()

    def process_events(self, ms: int = 50) -> None:
        """Pump the Qt event loop for roughly ``ms`` milliseconds."""
        app = QApplication.instance()
        if app is None:
            return
        deadline = time.monotonic() + ms / 1000.0
        while True:
            app.processEvents()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.01, remaining))

    # -- actions -------------------------------------------------------

    def navigate(self, page_id: str) -> None:
        """Switch the content stack to ``page_id``."""
        self._require_window()
        if page_id not in self.window.pages:
            raise WidgetIdError(
                f"unknown page {page_id!r}; known pages: {sorted(self.window.pages)}"
            )
        self.window._navigate_to_page(page_id)
        self.process_events(50)

    def find(self, test_id: str) -> QWidget:
        """Return the widget with ``test_id``; raise ``WidgetIdError`` if absent."""
        self._require_window()
        widget = find_by_test_id(self.window, test_id)
        if widget is None:
            raise WidgetIdError(f"unknown id {test_id!r}")
        return widget

    def click(self, test_id: str) -> None:
        """Click the widget with ``test_id``."""
        widget = self.find(test_id)
        click_fn = getattr(widget, "click", None)
        if callable(click_fn):
            click_fn()
            # Synthetic clicks do not generate mouse events, so log explicitly.
            log_gui_event("click", widget=widget, detail={"text": _widget_text(widget)})
        else:
            from PyQt6.QtCore import Qt
            from PyQt6.QtTest import QTest

            # Real mouse events -- the application event filter logs the click.
            # PyQt6's QtTest stubs declare mouseClick with a ``self: QTest``
            # parameter although it is used as a static entry point; this call
            # form is the standard PyQt idiom (runtime-verified in tests/gui).
            QTest.mouseClick(widget, Qt.MouseButton.LeftButton)  # type: ignore[call-overload]
        self.process_events(50)

    def set_text(self, test_id: str, value: str) -> None:
        """Set text/value on a line edit, text edit or combo box."""
        widget = self.find(test_id)
        if hasattr(widget, "setText"):
            widget.setText(value)
        elif hasattr(widget, "setPlainText"):
            widget.setPlainText(value)
        elif hasattr(widget, "setCurrentText"):
            widget.setCurrentText(value)
        else:
            raise WidgetIdError(
                f"widget {test_id!r} ({type(widget).__name__}) does not accept text"
            )
        log_gui_event("text_changed", widget=widget, detail={"value": value})
        self.process_events(20)

    def get_state(self, test_id: str) -> dict:
        """Return ``{"text","checked","enabled","visible","value"}`` for ``test_id``."""
        widget = self.find(test_id)
        checked: Optional[bool] = None
        if hasattr(widget, "isCheckable") and widget.isCheckable() and hasattr(widget, "isChecked"):
            checked = widget.isChecked()
        return {
            "text": _widget_text(widget),
            "checked": checked,
            "enabled": widget.isEnabled(),
            "visible": widget.isVisible(),
            "value": _widget_value(widget),
        }

    def dump(self, test_id: Optional[str] = None) -> dict:
        """Dump the widget tree of ``test_id`` (or the whole window)."""
        self._require_window()
        root = self.find(test_id) if test_id else self.window
        return dump_widget_tree(root)

    def screenshot(self, **kwargs) -> ScreenshotResult:
        """Capture the window (or ``widget=``/target passed through ``kwargs``)."""
        self._require_window()
        kwargs.setdefault("widget", self.window)
        return gui_screenshot(**kwargs)

    def known_ids(self) -> list[str]:
        """All testIds currently present in the window tree (for error hints)."""
        self._require_window()
        from .dump import dump_widget_tree

        ids: list[str] = []

        def _walk(node: dict) -> None:
            if node.get("testId"):
                ids.append(node["testId"])
            for child in node.get("children", []):
                _walk(child)

        tree = dump_widget_tree(self.window)
        if tree.get("root"):
            _walk(tree["root"])
        return sorted(ids)

    def _require_window(self) -> None:
        if self.window is None:
            raise RuntimeError("HeadlessGui.start() has not been called")


__all__ = [
    "HeadlessGui",
    "WidgetIdError",
    "ensure_offscreen_fontdir",
    "ensure_offscreen_platform",
    "get_test_id",
]
