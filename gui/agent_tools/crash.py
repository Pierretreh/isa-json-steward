"""
Crash bundles and exception hooks (P1-1).

plans/agent-gui-observability.md section 2.5.  A crash bundle is written to
``crash_reports/<YYYYmmdd-HHMMSS-fff>/`` containing:

===============  ============================================================
``exception.txt``   formatted traceback
``exception.json``  ``{type, message, thread, fatal}``
``widget_tree.json`` / ``widget_tree.txt``  ``dump_widget_tree()`` of the active window
``screenshot.png``  ``gui_screenshot()`` of the active window (``grab()`` only --
                 the window is never closed, so no ``closeEvent`` modal
                 path can trigger)
``events.jsonl``  ring-buffer tail (last 500 GUI events)
``meta.json``     python/Qt/PyQt versions, platform, ``QT_QPA_PLATFORM``,
                 current theme, current page, ``sys.argv``, cwd, context
===============  ============================================================

Every step is failure-safe: a broken hook must never mask the original
exception (each artifact write is individually guarded, and the hooks
themselves swallow all internal errors before chaining to the original hook).

**PyQt6 dispatch reality (verified empirically):** exceptions raised in
slots, reimplemented event handlers and timer callables do NOT propagate
through ``QApplication.notify()`` -- PyQt6 routes them to ``sys.excepthook``
and aborts via ``qFatal()`` when the default excepthook is installed.  Once
:func:`install_crash_hooks` replaces ``sys.excepthook``, those exceptions are
captured here *and the process continues*.  The ``fatal`` flag distinguishes
the cases:

- ``fatal: false`` -- the exception happened while the Qt event loop was
  dispatching (slot/event/timer code) or inside ``notify()``; the GUI
  survives and this is exactly the plan's ``notify()``-path semantic
  ("swallow, matching Qt convention").  Detection: a per-thread dispatch
  depth counter maintained by :class:`StewardNotifyMixin`.
- ``fatal: true`` -- top-level interpreter exceptions and
  ``threading.excepthook`` crashes (the process or a thread is dying).

:class:`StewardNotifyMixin` provides the plan's ``notify()`` override (a
safety net for exceptions that do propagate through ``super().notify()``);
``StewardApp`` mixes it in (see ``gui/app.py``).
"""

from __future__ import annotations

import json
import os
import platform
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

CRASH_OUT_ROOT = Path("crash_reports")
BUNDLE_EVENT_TAIL = 500

_hooks_installed = False
_capture_enabled = False
_original_excepthook = None
_original_threading_excepthook = None
_out_root: Path = CRASH_OUT_ROOT

# Per-thread depth of StewardApp.notify() -> super().notify() dispatch.  When
# > 0 and an exception surfaces via sys.excepthook, it came from Qt dispatch
# (slot/event/timer) and is non-fatal (see module docstring).
_dispatch = threading.local()

__all__ = [
    "CRASH_OUT_ROOT",
    "StewardNotifyMixin",
    "hooks_active",
    "install_crash_hooks",
    "uninstall_crash_hooks",
    "write_crash_bundle",
]


# -- dispatch depth tracking ------------------------------------------


def _enter_dispatch() -> None:
    _dispatch.depth = getattr(_dispatch, "depth", 0) + 1


def _leave_dispatch() -> None:
    _dispatch.depth = max(0, getattr(_dispatch, "depth", 0) - 1)


def dispatch_depth() -> int:
    """Current Qt event-dispatch nesting depth on this thread."""
    return getattr(_dispatch, "depth", 0)


# -- bundle writing ----------------------------------------------------


def _make_bundle_dir(out_root: Path) -> Path:
    """Create ``<YYYYmmdd-HHMMSS-fff>`` under ``out_root`` (collision-safe)."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    candidate = out_root / stamp
    counter = 1
    while candidate.exists():
        candidate = out_root / f"{stamp}-{counter}"
        counter += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _active_window():
    """Best-effort active (or first visible top-level) window, else None."""
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return None
        win = app.activeWindow()
        if win is not None:
            return win
        for widget in app.topLevelWidgets():
            if widget.isVisible():
                return widget
        return None
    except Exception:
        return None


def _on_gui_thread() -> bool:
    """Whether the calling thread owns the QApplication (widget access is safe)."""
    try:
        from PyQt6.QtCore import QThread
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return True
        return QThread.currentThread() is app.thread()
    except Exception:
        return True


def _write_text(path: Path, text: str, errors: list[str]) -> None:
    try:
        path.write_text(text, encoding="utf-8")
    except Exception as exc:
        errors.append(f"{path.name}: {exc}")


def _write_json(path: Path, payload: Any, errors: list[str]) -> None:
    try:
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except Exception as exc:
        errors.append(f"{path.name}: {exc}")


def _collect_meta(context: dict, errors: list[str]) -> dict:
    """Meta info per plan section 2.5 (best-effort on every field)."""
    meta: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "qt": None,
        "pyqt": None,
        "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM"),
        "theme": None,
        "page": None,
        "argv": list(sys.argv),
        "cwd": os.getcwd(),
        "context": context,
    }
    try:
        from PyQt6.QtCore import PYQT_VERSION_STR, qVersion

        meta["qt"] = qVersion()
        meta["pyqt"] = PYQT_VERSION_STR
    except Exception as exc:
        errors.append(f"meta.version: {exc}")

    if _on_gui_thread():
        try:
            from PyQt6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                settings = getattr(app, "settings", None)
                if settings is not None:
                    meta["theme"] = settings.value("gui/theme", None)
        except Exception as exc:
            errors.append(f"meta.theme: {exc}")

        try:
            window = _active_window()
            stack = getattr(window, "content_stack", None)
            if stack is not None:
                from .ids import get_test_id

                meta["page"] = get_test_id(stack.currentWidget())
        except Exception as exc:
            errors.append(f"meta.page: {exc}")

    return meta


def write_crash_bundle(
    exc_type,
    exc_value,
    exc_tb,
    *,
    out_root: Path = CRASH_OUT_ROOT,
    context: Optional[dict] = None,
) -> Path:
    """Write a full crash bundle for one exception; returns the bundle dir.

    Failure-safe per artifact: individual write errors are recorded in
    ``meta.json`` under ``errors``.  Only a failure to create the bundle
    directory itself propagates (and the hooks swallow that too).
    """
    from .events import get_event_logger

    context = dict(context or {})
    fatal = bool(context.get("fatal", True))
    bundle_dir = _make_bundle_dir(Path(out_root))
    errors: list[str] = []

    # Log the crash first so the bundle's events.jsonl tail includes it.
    try:
        get_event_logger().log(
            "crash",
            "crash",
            detail={
                "type": getattr(exc_type, "__name__", str(exc_type)),
                "message": str(exc_value) if exc_value is not None else "",
                "fatal": fatal,
            },
        )
    except Exception:
        pass

    try:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    except Exception:
        text = f"{exc_type}: {exc_value}\n<traceback unavailable>"
    _write_text(bundle_dir / "exception.txt", text, errors)

    thread_name = context.get("thread") or threading.current_thread().name
    _write_json(
        bundle_dir / "exception.json",
        {
            "type": getattr(exc_type, "__name__", str(exc_type)),
            "message": str(exc_value) if exc_value is not None else "",
            "thread": thread_name,
            "fatal": fatal,
        },
        errors,
    )

    if _on_gui_thread():
        # Widget access (tree walk / grab) is only safe on the GUI thread;
        # thread-crash bundles skip these artifacts (documented in AGENTS.md).
        try:
            from .dump import WIDGET_TREE_SCHEMA, dump_widget_tree, widget_tree_to_text

            window = _active_window()
            tree = (
                dump_widget_tree(window)
                if window is not None
                else {"schema": WIDGET_TREE_SCHEMA, "root": None}
            )
            _write_json(bundle_dir / "widget_tree.json", tree, errors)
            _write_text(bundle_dir / "widget_tree.txt", widget_tree_to_text(tree), errors)
        except Exception as exc:
            errors.append(f"widget_tree: {exc}")

        try:
            window = _active_window()
            if window is not None:
                from .screenshot import gui_screenshot

                gui_screenshot(window, out_dir=bundle_dir, name="screenshot")
        except Exception as exc:
            errors.append(f"screenshot: {exc}")
    else:
        errors.append("widget_tree/screenshot skipped (bundle written off the GUI thread)")

    try:
        tail = get_event_logger().recent(BUNDLE_EVENT_TAIL)
        lines = "\n".join(json.dumps(row, default=str) for row in tail)
        _write_text(bundle_dir / "events.jsonl", lines + ("\n" if lines else ""), errors)
    except Exception as exc:
        errors.append(f"events: {exc}")

    meta = _collect_meta(context, errors)
    meta["errors"] = errors
    _write_json(bundle_dir / "meta.json", meta, errors)

    return bundle_dir


# -- exception hooks ----------------------------------------------------


def _resolve_original(hook):
    return hook if hook is not None else sys.__excepthook__


def _sys_excepthook(exc_type, exc_value, exc_tb) -> None:
    """sys.excepthook wrapper: write a bundle, then chain (never mask)."""
    try:
        in_dispatch = dispatch_depth() > 0
        write_crash_bundle(
            exc_type,
            exc_value,
            exc_tb,
            out_root=_out_root,
            context={
                "fatal": not in_dispatch,
                "hook": "notify" if in_dispatch else "sys.excepthook",
            },
        )
    except Exception:
        pass
    try:
        _resolve_original(_original_excepthook)(exc_type, exc_value, exc_tb)
    except Exception:
        pass


def _threading_excepthook(args) -> None:
    """threading.excepthook wrapper (receives an ExceptHookArgs namedtuple)."""
    try:
        # threading._ExceptHookArgs names the traceback field ``exc_traceback``;
        # accept ``exc_tb`` too so hand-built arg objects also work.
        exc_tb = getattr(args, "exc_tb", None)
        if exc_tb is None:
            exc_tb = getattr(args, "exc_traceback", None)
        write_crash_bundle(
            args.exc_type,
            args.exc_value,
            exc_tb,
            out_root=_out_root,
            context={
                "fatal": True,
                "hook": "threading.excepthook",
                "thread": getattr(args.thread, "name", None),
            },
        )
    except Exception:
        pass
    try:
        original = (
            _original_threading_excepthook
            if _original_threading_excepthook is not None
            else threading.__excepthook__
        )
        original(args)
    except Exception:
        pass


def install_crash_hooks(
    app: Optional[Any] = None,
    *,
    out_root: Path = CRASH_OUT_ROOT,
) -> None:
    """Install ``sys.excepthook`` + ``threading.excepthook`` wrappers.

    Chaining to the previously installed hooks (plan section 2.5).  Idempotent:
    re-installing only updates ``out_root``.  When ``app`` is a ``StewardApp``
    (i.e. mixes in :class:`StewardNotifyMixin`) its ``notify()`` override is
    activated via :func:`hooks_active`; with no app, the excepthooks still
    capture crashes.

    Installing the ``sys.excepthook`` wrapper also stops PyQt6 from aborting
    the process (``qFatal``) on exceptions escaping slots/event handlers --
    they are captured as ``fatal: false`` bundles and the GUI continues.
    """
    global _hooks_installed, _capture_enabled, _original_excepthook
    global _original_threading_excepthook, _out_root

    _out_root = Path(out_root)
    if not _hooks_installed:
        _original_excepthook = sys.excepthook
        sys.excepthook = _sys_excepthook
        _original_threading_excepthook = threading.excepthook
        threading.excepthook = _threading_excepthook
        _hooks_installed = True
    _capture_enabled = True


def uninstall_crash_hooks() -> None:
    """Restore the original ``sys``/``threading`` excepthooks (test hygiene)."""
    global _hooks_installed, _capture_enabled
    if _hooks_installed:
        if _original_excepthook is not None:
            sys.excepthook = _original_excepthook
        if _original_threading_excepthook is not None:
            threading.excepthook = _original_threading_excepthook
        _hooks_installed = False
    _capture_enabled = False


def hooks_active() -> bool:
    """Whether crash capture is enabled (set by :func:`install_crash_hooks`)."""
    return _capture_enabled


class StewardNotifyMixin:
    """QApplication mixin providing the plan's ``notify()`` override (§2.5).

    Calls ``super().notify()`` in try/except; on exception it writes a crash
    bundle with ``fatal: false`` and returns ``True`` (swallow, matching Qt
    convention) while logging to the event stream.  Also maintains the
    per-thread dispatch-depth counter used to classify exceptions that PyQt6
    routes through ``sys.excepthook`` during event dispatch.  Inert unless
    :func:`install_crash_hooks` has been called.
    """

    def notify(self, receiver, event) -> bool:  # noqa: N802 (Qt API)
        if not hooks_active():
            return super().notify(receiver, event)
        _enter_dispatch()
        try:
            return super().notify(receiver, event)
        except Exception as exc:
            try:
                write_crash_bundle(
                    type(exc),
                    exc,
                    exc.__traceback__,
                    out_root=_out_root,
                    context={"fatal": False, "hook": "notify"},
                )
            except Exception:
                pass
            return True
        finally:
            _leave_dispatch()
