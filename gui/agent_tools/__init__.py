"""
Agent-facing observability toolkit for the ISA-JSON Data Steward GUI.

Makes the PyQt6 GUI inspectable and controllable by an AI coding agent:
unique widget IDs, widget-tree dumps, screenshots (with set-of-marks
annotation), crash/event diagnostics, and a headless runtime plus CLI
(``python -m gui.agent_tools ...``).

Public API (design: plans/agent-gui-observability.md):

- :mod:`gui.agent_tools.ids`        -- ``set_test_id`` / ``get_test_id`` /
  ``find_by_test_id`` / ``WidgetIdError`` (dependency-light, safe to import
  from pages/dialogs).
- :mod:`gui.agent_tools.dump`       -- ``dump_widget_tree`` /
  ``widget_tree_to_text`` (schema ``isa-gui/widget-tree/1``).
- :mod:`gui.agent_tools.screenshot` -- ``gui_screenshot`` / ``grab_widget`` /
  ``ScreenshotResult``.
- :mod:`gui.agent_tools.annotate`   -- ``collect_marks`` / ``annotate`` /
  ``Mark`` (set-of-marks, P1-2).
- :mod:`gui.agent_tools.events`     -- ``GuiEventLogger`` / ``log_gui_event`` /
  ``install_event_filter`` (JSONL event stream, P1-1).
- :mod:`gui.agent_tools.crash`      -- ``install_crash_hooks`` /
  ``write_crash_bundle`` / ``StewardNotifyMixin`` (crash bundles, P1-1).
- :mod:`gui.agent_tools.runtime`    -- ``HeadlessGui`` lifecycle wrapper.
- :mod:`gui.agent_tools.mcp_server` -- stdio MCP server (P2-1); not
  re-exported here (importing it requires the ``agent`` extra).

The public names above are re-exported lazily (PEP 562) so that importing
``gui.agent_tools.ids`` from pages/dialogs does not drag in Qt app bootstrap
code (avoids circular imports with ``gui.main_window``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .ids import (
    TEST_ID_PROPERTY,
    TEST_ID_RE,
    WidgetIdError,
    find_by_test_id,
    get_test_id,
    set_test_id,
)

if TYPE_CHECKING:  # pragma: no cover
    from .annotate import Mark, annotate, collect_marks
    from .crash import StewardNotifyMixin, install_crash_hooks, write_crash_bundle
    from .dump import dump_widget_tree, widget_tree_to_text
    from .events import GuiEventLogger, install_event_filter, log_gui_event
    from .runtime import HeadlessGui
    from .screenshot import ScreenshotResult, grab_widget, gui_screenshot

_LAZY_EXPORTS = {
    "dump_widget_tree": ("gui.agent_tools.dump", "dump_widget_tree"),
    "widget_tree_to_text": ("gui.agent_tools.dump", "widget_tree_to_text"),
    "gui_screenshot": ("gui.agent_tools.screenshot", "gui_screenshot"),
    "grab_widget": ("gui.agent_tools.screenshot", "grab_widget"),
    "ScreenshotResult": ("gui.agent_tools.screenshot", "ScreenshotResult"),
    "Mark": ("gui.agent_tools.annotate", "Mark"),
    "collect_marks": ("gui.agent_tools.annotate", "collect_marks"),
    "annotate": ("gui.agent_tools.annotate", "annotate"),
    "GuiEventLogger": ("gui.agent_tools.events", "GuiEventLogger"),
    "log_gui_event": ("gui.agent_tools.events", "log_gui_event"),
    "install_event_filter": ("gui.agent_tools.events", "install_event_filter"),
    "install_crash_hooks": ("gui.agent_tools.crash", "install_crash_hooks"),
    "uninstall_crash_hooks": ("gui.agent_tools.crash", "uninstall_crash_hooks"),
    "write_crash_bundle": ("gui.agent_tools.crash", "write_crash_bundle"),
    "StewardNotifyMixin": ("gui.agent_tools.crash", "StewardNotifyMixin"),
    "HeadlessGui": ("gui.agent_tools.runtime", "HeadlessGui"),
}

__all__ = [
    "TEST_ID_PROPERTY",
    "TEST_ID_RE",
    "WidgetIdError",
    "set_test_id",
    "get_test_id",
    "find_by_test_id",
    "dump_widget_tree",
    "widget_tree_to_text",
    "gui_screenshot",
    "grab_widget",
    "ScreenshotResult",
    "Mark",
    "collect_marks",
    "annotate",
    "GuiEventLogger",
    "log_gui_event",
    "install_event_filter",
    "install_crash_hooks",
    "uninstall_crash_hooks",
    "write_crash_bundle",
    "StewardNotifyMixin",
    "HeadlessGui",
]


def __getattr__(name: str):
    """Lazily import heavier toolkit members on first attribute access."""
    if name in _LAZY_EXPORTS:
        import importlib

        module_name, attr = _LAZY_EXPORTS[name]
        return getattr(importlib.import_module(module_name), attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
