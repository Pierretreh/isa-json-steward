"""
Structured JSONL GUI-event logging (P1-1).

One JSON object per line, schema ``isa-gui/event/1``
(plans/agent-gui-observability.md section 2.5)::

    {"ts": "2026-11-02T20:48:50.769Z", "seq": 1234, "session": "<uuid4>",
     "kind": "gui_event", "event": "click", "test_id": "page.materials.saveButton",
     "class": "PrimaryButton", "object_name": "primaryButton", "page": "materials",
     "detail": {"text": "Save"}}

Field notes:

- ``kind``: ``gui_event`` (interaction/lifecycle), ``log`` (logging records
  forwarded via :class:`utils.logging_config.JsonlEventHandler`), ``crash``
  (crash rows written just before a crash bundle), ``state`` (reserved).
- ``event``: ``click | text_changed | toggled | navigate | page_enter |
  page_exit | data_changed | error | crash`` plus two capture-point
  extensions the plan's own event-filter spec requires: ``key_press`` and
  ``focus_in``.  ``kind="log"`` rows use ``error`` for level >= ERROR and the
  lower-cased level name otherwise.
- Every row always carries ``ts`` (ISO 8601 UTC with milliseconds), ``seq``
  (monotonic per session), ``session`` (uuid4 of the logging session),
  ``class``, ``object_name``, ``page`` (nullable) and ``detail`` (object).

Capture points (plan section 2.5):

1. An application-level :class:`GuiEventFilter` installed by
   :func:`install_event_filter` logs ``MouseButtonRelease`` / ``KeyPress`` /
   ``FocusIn`` on widgets carrying a ``testId``.
2. Explicit :func:`log_gui_event` calls in ``MainWindow._navigate_to_page()``
   (``navigate`` / ``page_enter`` / ``page_exit``) and
   ``MainWindow._on_page_data_changed()`` (``data_changed``), and in
   :class:`~gui.agent_tools.runtime.HeadlessGui` synthetic actions.

:class:`GuiEventLogger` keeps a 500-event ring buffer (tail written into
crash bundles, see :mod:`gui.agent_tools.crash`) and appends to
``reports/gui_events.jsonl`` (path overridable via env
``ISA_STEWARD_GUI_EVENTS``).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TextIO

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QWidget

# Re-exported per the plan's module layout (section 2.4); the implementation
# lives in utils/logging_config.py (section 2.5 "integration with
# utils.logging_config").
from utils.logging_config import JsonlEventHandler  # noqa: F401  (re-export)

from .ids import get_test_id

EVENT_SCHEMA = "isa-gui/event/1"
DEFAULT_EVENTS_PATH = Path("reports") / "gui_events.jsonl"
EVENTS_PATH_ENV = "ISA_STEWARD_GUI_EVENTS"
RING_BUFFER_SIZE = 500

__all__ = [
    "EVENT_SCHEMA",
    "EVENTS_PATH_ENV",
    "GuiEventFilter",
    "GuiEventLogger",
    "JsonlEventHandler",
    "install_event_filter",
    "get_event_logger",
    "log_gui_event",
]


def _iso_timestamp() -> str:
    """UTC ISO 8601 timestamp with millisecond precision, e.g. ``...T20:48:50.769Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _page_for(widget: Optional[QWidget]) -> Optional[str]:
    """Best-effort page id for ``widget`` (via ``page.*`` testIds / ``pageId``)."""
    node = widget
    while node is not None:
        test_id = get_test_id(node)
        if test_id and test_id.startswith("page."):
            parts = test_id.split(".")
            if len(parts) >= 2:
                return parts[1]
        page_id = node.property("pageId")
        if page_id is not None:
            return str(page_id)
        node = node.parentWidget()
    return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class GuiEventLogger:
    """Append-only JSONL GUI-event log with a ring buffer for crash bundles.

    The log file is opened lazily on the first event; all writes are
    failure-safe (a broken log must never break the GUI).  ``recent()``
    returns the ring-buffer tail for crash bundles.
    """

    def __init__(
        self,
        path: Optional[Path | str] = None,
        *,
        max_buffer: int = RING_BUFFER_SIZE,
    ) -> None:
        if path is not None:
            self.path = Path(path)
        else:
            env_path = os.environ.get(EVENTS_PATH_ENV)
            self.path = Path(env_path) if env_path else DEFAULT_EVENTS_PATH
        self.path = self.path.expanduser().resolve()
        self.session = str(uuid.uuid4())
        self._seq = 0
        self._ring: deque[dict] = deque(maxlen=max_buffer)
        self._lock = threading.Lock()
        self._file: Optional[TextIO] = None
        self._file_failed = False

    # -- writing -------------------------------------------------------

    def log(
        self,
        kind: str,
        event: str,
        *,
        test_id: Optional[str] = None,
        class_name: Optional[str] = None,
        object_name: Optional[str] = None,
        page: Optional[str] = None,
        detail: Optional[dict] = None,
    ) -> dict:
        """Append one event row; returns the row dict (failure-safe)."""
        with self._lock:
            self._seq += 1
            row = {
                "ts": _iso_timestamp(),
                "seq": self._seq,
                "session": self.session,
                "kind": kind,
                "event": event,
                "test_id": test_id,
                "class": class_name,
                "object_name": object_name,
                "page": page,
                "detail": {k: _json_safe(v) for k, v in (detail or {}).items()},
            }
            self._ring.append(row)
            self._append_line(row)
            return row

    def _append_line(self, row: dict) -> None:
        """Best-effort JSONL append; never raises."""
        if self._file_failed:
            return
        try:
            if self._file is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._file = open(self.path, "a", encoding="utf-8")
            self._file.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            self._file.flush()
        except Exception:
            self._file_failed = True

    # -- reading -------------------------------------------------------

    def recent(self, n: Optional[int] = None) -> list[dict]:
        """Return the last ``n`` events (all buffered events when ``n`` is None)."""
        with self._lock:
            rows = list(self._ring)
        return rows[-n:] if n is not None else rows

    def close(self) -> None:
        """Close the underlying log file (if open)."""
        with self._lock:
            if self._file is not None:
                try:
                    self._file.close()
                except Exception:
                    pass
                self._file = None


_shared_logger: Optional[GuiEventLogger] = None


def get_event_logger(path: Optional[Path | str] = None) -> GuiEventLogger:
    """Return the shared :class:`GuiEventLogger`.

    The shared instance is created on first use.  Passing ``path`` points the
    shared logger at a different file (used by ``setup_gui_event_log`` and
    tests); without ``path`` the existing instance is reused unchanged.
    """
    global _shared_logger
    if _shared_logger is None:
        _shared_logger = GuiEventLogger(path)
    elif path is not None and Path(path).expanduser().resolve() != _shared_logger.path:
        _shared_logger.close()
        _shared_logger = GuiEventLogger(path)
    return _shared_logger


def log_gui_event(
    event: str,
    *,
    widget: Optional[QWidget] = None,
    test_id: Optional[str] = None,
    detail: Optional[dict] = None,
    kind: str = "gui_event",
) -> Optional[dict]:
    """Log one GUI event, deriving identity fields from ``widget`` when given.

    Failure-safe: returns ``None`` if the event could not be logged.
    """
    try:
        class_name = object_name = page = None
        if widget is not None:
            class_name = type(widget).__name__
            object_name = widget.objectName()
            page = _page_for(widget)
            if test_id is None:
                test_id = get_test_id(widget)
        return get_event_logger().log(
            kind,
            event,
            test_id=test_id,
            class_name=class_name,
            object_name=object_name,
            page=page,
            detail=detail,
        )
    except Exception:
        return None


class GuiEventFilter(QObject):
    """Application-level event filter logging interactions on tagged widgets.

    Logs ``MouseButtonRelease`` -> ``click``, ``KeyPress`` -> ``key_press`` and
    ``FocusIn`` -> ``focus_in``, but only for widgets carrying a ``testId``.
    Never consumes events and never raises.
    """

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        try:
            etype = event.type()
            if not isinstance(obj, QWidget):
                return False
            if etype == QEvent.Type.MouseButtonRelease:
                if get_test_id(obj):
                    from .dump import _widget_text

                    button = event.button()
                    log_gui_event(
                        "click",
                        widget=obj,
                        detail={
                            "text": _widget_text(obj),
                            # PyQt6 flag enums reject int(); use .value when present.
                            "button": _json_safe(getattr(button, "value", button)),
                        },
                    )
            elif etype == QEvent.Type.KeyPress:
                if get_test_id(obj):
                    log_gui_event(
                        "key_press",
                        widget=obj,
                        detail={"key": event.key(), "text": event.text()},
                    )
            elif etype == QEvent.Type.FocusIn:
                if get_test_id(obj):
                    log_gui_event("focus_in", widget=obj)
        except Exception:
            pass
        return False


_installed_filter: Optional[GuiEventFilter] = None


def install_event_filter(app: QObject) -> GuiEventFilter:
    """Install (or return the already-installed) application-level event filter.

    ``app`` is normally the ``QApplication`` instance; installing an event
    filter on the application object makes it an application-wide filter.
    The returned filter is kept alive by this module and by ``app``.
    """
    global _installed_filter
    if _installed_filter is not None and _installed_filter.parent() is app:
        return _installed_filter
    filt = GuiEventFilter(app)
    app.installEventFilter(filt)
    _installed_filter = filt
    return filt


def remove_event_filter(app: QObject) -> None:
    """Remove the filter installed by :func:`install_event_filter` (test hygiene)."""
    global _installed_filter
    if _installed_filter is not None:
        app.removeEventFilter(_installed_filter)
        _installed_filter = None
