"""
Logging configuration for the ISA Data Steward GUI application.

This module provides centralized logging configuration for the application.

Additive P1-1 integration (plans/agent-gui-observability.md section 2.5):
:class:`JsonlEventHandler` forwards log records into the structured JSONL
GUI-event stream (schema ``isa-gui/event/1``) and :func:`setup_gui_event_log`
wires that stream up.  The ``gui`` package is imported lazily inside
functions so ``utils`` keeps its dependency-light layering.
"""

import logging
import sys
from pathlib import Path
from typing import List, Optional


def setup_logging(
    log_level: str = "INFO", log_file: Optional[Path] = None, log_format: Optional[str] = None
) -> None:
    """
    Configure application logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        log_format: Optional custom log format string
    """
    if log_format is None:
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        # Ensure log directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format=log_format,
        handlers=handlers,
        force=True,  # Override any existing configuration
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


class JsonlEventHandler(logging.Handler):
    """Forward log records into the JSONL GUI-event stream (``isa-gui/event/1``).

    Records at level >= ERROR map to the ``error`` event; lower levels map to
    their lower-cased level name.  The row's ``detail`` carries ``level``,
    ``logger`` and ``message``.  Failure-safe: emit errors never propagate.
    """

    def __init__(self, event_logger=None, level: int = logging.WARNING):
        super().__init__(level)
        self._event_logger = event_logger

    def emit(self, record: logging.LogRecord) -> None:
        try:
            from gui.agent_tools.events import get_event_logger  # lazy (layering)

            event_logger = self._event_logger or get_event_logger()
            event = "error" if record.levelno >= logging.ERROR else record.levelname.lower()
            event_logger.log(
                "log",
                event,
                detail={
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                },
            )
        except Exception:
            self.handleError(record)


def setup_gui_event_log(path: Optional[Path] = None):
    """Create (or repoint) the shared GUI event log and attach a log handler.

    Attaches a :class:`JsonlEventHandler` to the root logger so WARNING+
    records land in the same JSONL stream as GUI events (plan section 2.5).
    Idempotent: at most one such handler is attached.

    Args:
        path: optional log file path (default ``reports/gui_events.jsonl``,
            overridable via env ``ISA_STEWARD_GUI_EVENTS``)

    Returns:
        The shared ``GuiEventLogger`` instance.
    """
    from gui.agent_tools.events import get_event_logger  # lazy (layering)

    event_logger = get_event_logger(path)
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not isinstance(h, JsonlEventHandler)]
    root.addHandler(JsonlEventHandler(event_logger))
    return event_logger
