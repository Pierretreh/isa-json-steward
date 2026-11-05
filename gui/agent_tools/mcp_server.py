"""
Stdio MCP server for the ISA-JSON Data Steward GUI (P2-1).

plans/agent-gui-observability.md section 2.7: a ``mcp`` SDK (FastMCP) stdio
server exposing seven tools against ONE long-lived
:class:`~gui.agent_tools.runtime.HeadlessGui` instance, created lazily on the
first tool call and pumped with ``processEvents`` between calls.  All tools
return small JSON strings (or the LLM text form for dumps); images are
returned as **file paths**, never base64.

Tool surface (names are normative):

===================  ==========================================================
``dump_widget_tree``  ``test_id=None, as_text=True`` -> text form or {"tree": …}
``screenshot``        ``test_id=None, annotate=True, theme=None, max_edge=2048``
``navigate``          ``page_id`` -> {"ok": true, "page": …}
``click_widget``      ``test_id`` -> {"ok": true, "clicked": …}
``set_text``          ``test_id, value`` -> {"ok": true}
``get_state``         ``test_id`` -> {"text", "checked", "enabled", …}
``run_gui_test``      ``pattern`` -> pytest summary dict
===================  ==========================================================

Errors return ``{"ok": false, "error": "...", "known_ids": [...]}`` -- never
raw tracebacks (those land in ``crash_reports/`` via the P1-1 hooks).

Run with ``python -m gui.agent_tools mcp-serve`` (``QT_QPA_PLATFORM=offscreen``
is applied when unset).  Registered for zoo code in ``.mcp.json`` at the repo
root.

Safety policy (long-lived session, see AGENTS.md section 7 hazards):

- The tool handlers NEVER ``close()`` the window; teardown goes through
  :meth:`HeadlessGui.shutdown` (hide, not close) -- defense-in-depth against
  the ``closeEvent`` modal path (the ``config/settings.json`` rewrite half of
  the old hazard is gone since U-02: ``SettingsPage.save_data()`` is a
  no-op).
- The runtime stops ``MainWindow.auto_save_timer`` so idle sessions can never
  trigger ``save_data()`` side effects (e.g. the settings page rewriting
  ``config/settings.json`` or popping a modal).  Exercise persistence
  explicitly by clicking a page's ``saveButton``.
- ``screenshot(theme=...)`` is **session-only** (delegated to
  ``gui_screenshot()`` -- U-06 centralization): the theme QSS is applied for
  the grab and the previous stylesheet is restored afterwards -- the user's
  persisted ``gui/theme`` (QSettings) is never rewritten.  ``theme=None``
  keeps the application's current theme.
- Handlers convert ``SystemExit`` from Qt slots (e.g. the settings restart
  path) into error payloads so a single tool call cannot kill the server.
- ``run_stdio()`` pre-imports the heavy GUI module chain at startup: the
  lazy ``gui.main_window`` import (pages -> dialogs -> pandas -> numpy) has
  been observed to deadlock its native init when first triggered from inside
  the running anyio/stdio runtime (Windows loader vs the runtime's pipe I/O
  threads).  Warm-up is single-threaded and happens before the event loop
  exists.  It creates no GUI objects -- the ``HeadlessGui`` window is still
  booted lazily on the first tool call (plan section 2.7).

Note on annotations: this module deliberately does NOT use
``from __future__ import annotations`` -- FastMCP builds its JSON schema from
runtime type objects.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

# FastMCP exists only on the mcp 1.x line (mcp.server.fastmcp).  mcp 2.x
# renamed it to MCPServer; a best-effort fallback keeps the server importable
# there, but the supported/pinned SDK is ``mcp>=1.2.0,<2`` (see pyproject).
try:  # pragma: no cover - trivial import shim
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    try:
        from mcp.server.mcpserver import MCPServer as FastMCP  # mcp 2.x fallback
    except ImportError:
        FastMCP = None  # type: ignore[assignment,misc]

SERVER_NAME = "isa-gui"
RUN_GUI_TEST_TIMEOUT = 600.0  # seconds; a full tests/gui subset can be slow
OUTPUT_TAIL_LINES = 50

_INSTRUCTIONS = (
    "Inspect and drive the ISA-JSON Data Steward PyQt6 GUI, which runs "
    "offscreen behind this server. Address every widget by its unique "
    "`testId` (e.g. page.materials.saveButton) -- never by coordinates. "
    "All tool responses are small JSON strings; screenshots and dumps are "
    "returned as file paths (reports/...), never base64. Pair every "
    "screenshot with a dump_widget_tree call: the dump is exact ground truth "
    "for names/enabled/geometry, the image is for layout/color review. "
    "Use run_gui_test to iterate on pytest tests."
)

# ---------------------------------------------------------------------------
# Long-lived GUI runtime (one HeadlessGui per server process)
# ---------------------------------------------------------------------------

_gui: Any = None


def _warm_up() -> None:
    """Pre-import the heavy GUI module chain (see module docstring).

    Cheap once cached; guards the lazy first-call import against the
    stdio-runtime loader deadlock and keeps first tool calls fast.
    """
    import gui.agent_tools.runtime  # noqa: F401
    import gui.main_window  # noqa: F401  (pulls pages/dialogs/widgets, pandas, numpy)

    from . import annotate, crash, dump, events, screenshot  # noqa: F401


def _get_gui() -> Any:
    """Return the shared :class:`HeadlessGui`, booting it on first use."""
    global _gui
    if _gui is None or _gui.window is None:
        _warm_up()
        # Offscreen unless the caller pinned a platform (CI already sets it);
        # ensure_offscreen_platform() also strips whitespace pollution which
        # would otherwise make Qt abort natively on plugin lookup.
        from .runtime import HeadlessGui, ensure_offscreen_platform

        ensure_offscreen_platform()

        # theme=None keeps the application's configured theme: a long-lived
        # inspection session must never rewrite the user's persisted
        # gui/theme preference (hazard 3).
        gui = HeadlessGui(theme=None)
        gui.start()
        # Stop the auto-save timer: tool calls must stay side-effect free
        # (see module docstring, "Safety policy").
        timer = getattr(gui.window, "auto_save_timer", None)
        if timer is not None:
            timer.stop()
        _gui = gui
    return _gui


def shutdown_runtime() -> None:
    """Tear down the shared runtime (hide -- never close -- the window)."""
    global _gui
    gui, _gui = _gui, None
    if gui is not None:
        try:
            gui.shutdown()
        except Exception:  # pragma: no cover - best effort teardown
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _error_payload(exc: BaseException, gui: Any = None) -> dict:
    """Standard error shape: ``{"ok": false, "error", "known_ids"}``."""
    payload: dict[str, Any] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if gui is not None:
        try:
            payload["known_ids"] = gui.known_ids()
        except Exception:  # pragma: no cover - best effort
            pass
    return payload


def _dumps(payload: dict) -> str:
    return json.dumps(payload, default=str)


def _output_tail(text: str) -> str:
    return "\n".join(text.splitlines()[-OUTPUT_TAIL_LINES:])


def _pytest_count(output: str, word: str) -> int:
    """Last ``<n> <word>`` occurrence in pytest output (the summary line)."""
    matches = re.findall(rf"(\d+)\s+{word}\b", output)
    return int(matches[-1]) if matches else 0


# ---------------------------------------------------------------------------
# Tools (plan section 2.7 -- return shapes are normative)
# ---------------------------------------------------------------------------


async def dump_widget_tree(test_id: Optional[str] = None, as_text: bool = True) -> str:
    """Dump the widget tree of ``test_id`` (or the whole window).

    Returns the LLM-friendly text form by default; pass ``as_text=False`` for
    the full JSON dump ``{"tree": ...}`` (schema ``isa-gui/widget-tree/1``).
    """
    gui = None
    try:
        gui = _get_gui()
        gui.process_events(20)
        tree = gui.dump(test_id)
        if as_text:
            from .dump import widget_tree_to_text

            return widget_tree_to_text(tree)
        return _dumps({"tree": tree})
    except SystemExit as exc:  # Qt slots may call sys.exit; never kill the server
        return _dumps(_error_payload(exc, gui))
    except Exception as exc:
        return _dumps(_error_payload(exc, gui))


async def screenshot(
    test_id: Optional[str] = None,
    annotate: bool = True,
    theme: Optional[str] = None,
    max_edge: int = 2048,
) -> str:
    """Capture a PNG screenshot (set-of-marks annotated by default).

    Returns ``{"path", "width", "height", "legend": [{index, test_id, label}],
    "legend_path"}``.  ``theme`` ("light"/"dark") is applied **session-only**
    for the capture and restored afterwards; ``None`` keeps the current theme.
    The longest image edge is downscaled to ``max_edge`` pixels.
    """
    gui = None
    try:
        gui = _get_gui()
        gui.process_events(20)
        if theme is not None and theme not in ("light", "dark"):
            raise ValueError(f"theme must be 'light' or 'dark', got {theme!r}")
        target = gui.find(test_id) if test_id else gui.window

        # Session-only theming (U-06) is centralized in gui_screenshot():
        # theme= is applied for the grab and the previous stylesheet is
        # restored in a try/finally; the persisted gui/theme (QSettings) is
        # never rewritten.
        result = gui.screenshot(widget=target, annotate=annotate, max_edge=max_edge, theme=theme)

        payload: dict[str, Any] = {
            "path": str(result.path),
            "width": result.width,
            "height": result.height,
            "legend": [
                {"index": m.index, "test_id": m.test_id, "label": m.label}
                for m in (result.marks or [])
            ],
        }
        if result.marks is not None:
            from .annotate import legend_path_for

            payload["legend_path"] = str(legend_path_for(result.path))
        return _dumps(payload)
    except SystemExit as exc:
        return _dumps(_error_payload(exc, gui))
    except Exception as exc:
        return _dumps(_error_payload(exc, gui))


async def navigate(page_id: str) -> str:
    """Switch the content stack to ``page_id`` (e.g. "materials")."""
    gui = None
    try:
        gui = _get_gui()
        gui.navigate(page_id)
        return _dumps({"ok": True, "page": page_id})
    except SystemExit as exc:
        return _dumps(_error_payload(exc, gui))
    except Exception as exc:
        return _dumps(_error_payload(exc, gui))


async def click_widget(test_id: str) -> str:
    """Click the widget with ``test_id``.

    Note: buttons that open modal dialogs block until the dialog is closed;
    prefer the pytest-qt route for dialog flows (AGENTS.md section 8).
    """
    gui = None
    try:
        gui = _get_gui()
        gui.click(test_id)
        return _dumps({"ok": True, "clicked": test_id})
    except SystemExit as exc:
        return _dumps(_error_payload(exc, gui))
    except Exception as exc:
        return _dumps(_error_payload(exc, gui))


async def set_text(test_id: str, value: str) -> str:
    """Set text/value on a line edit, text edit or combo box (``test_id``)."""
    gui = None
    try:
        gui = _get_gui()
        gui.set_text(test_id, value)
        return _dumps({"ok": True})
    except SystemExit as exc:
        return _dumps(_error_payload(exc, gui))
    except Exception as exc:
        return _dumps(_error_payload(exc, gui))


async def get_state(test_id: str) -> str:
    """Read widget state: ``{"text", "checked", "enabled", "visible", "value"}``."""
    gui = None
    try:
        gui = _get_gui()
        gui.process_events(20)
        return _dumps(gui.get_state(test_id))
    except SystemExit as exc:
        return _dumps(_error_payload(exc, gui))
    except Exception as exc:
        return _dumps(_error_payload(exc, gui))


async def run_gui_test(pattern: str) -> str:
    """Run GUI tests matching ``pattern`` and return a parsed pytest summary.

    Executes ``python -m pytest tests/gui -k <pattern> -q`` as a subprocess
    with ``QT_QPA_PLATFORM=offscreen`` and returns
    ``{"returncode", "passed", "failed", "skipped", "output_tail"}`` (the
    last ~50 lines of output).  Since E-1 the ``pytest.ini`` addopts carry
    no --cov gate, so the argv needs no ``-o addopts=`` override (works with
    or without ``pytest-cov`` installed).
    """
    try:
        repo_root = Path(__file__).resolve().parents[2]
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/gui",
            "-k",
            pattern,
            "-q",
        ]
        from .runtime import ensure_offscreen_platform

        env = dict(os.environ)
        ensure_offscreen_platform(env)
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RUN_GUI_TEST_TIMEOUT,
        )
        output = proc.stdout or ""
        if proc.stderr:
            output = f"{output}\n{proc.stderr}" if output else proc.stderr
        return _dumps(
            {
                "returncode": proc.returncode,
                "passed": _pytest_count(output, "passed"),
                "failed": _pytest_count(output, "failed"),
                "skipped": _pytest_count(output, "skipped"),
                "output_tail": _output_tail(output),
            }
        )
    except subprocess.TimeoutExpired as exc:
        tail = _output_tail((exc.stdout or "") + ("\n" + exc.stderr if exc.stderr else ""))
        return _dumps(
            {
                "ok": False,
                "error": f"TimeoutExpired: run_gui_test exceeded {RUN_GUI_TEST_TIMEOUT:.0f}s",
                "output_tail": tail,
            }
        )
    except Exception as exc:
        return _dumps(_error_payload(exc))


# ---------------------------------------------------------------------------
# Server assembly / entry points
# ---------------------------------------------------------------------------

_TOOLS = (
    dump_widget_tree,
    screenshot,
    navigate,
    click_widget,
    set_text,
    get_state,
    run_gui_test,
)

_server: Any = None


def create_server() -> Any:
    """Build a FastMCP server exposing the seven tools (plan section 2.7)."""
    if FastMCP is None:  # pragma: no cover - environment without the mcp SDK
        raise RuntimeError(
            "the 'mcp' package is required for the MCP server; "
            'install it with: pip install -e ".[agent]"'
        )
    server = FastMCP(SERVER_NAME, instructions=_INSTRUCTIONS)
    for tool_fn in _TOOLS:
        server.tool()(tool_fn)
    return server


def get_server() -> Any:
    """Return the process-wide FastMCP server (built on first use)."""
    global _server
    if _server is None:
        _server = create_server()
    return _server


def run_stdio() -> None:
    """Serve MCP over stdio until the client disconnects (then clean up)."""
    import atexit

    from .runtime import ensure_offscreen_platform

    ensure_offscreen_platform()
    # Import the GUI modules now, single-threaded, before the stdio event
    # loop and its pipe I/O threads exist (module docstring, "Safety policy").
    _warm_up()
    atexit.register(shutdown_runtime)
    get_server().run(transport="stdio")


__all__ = [
    "SERVER_NAME",
    "create_server",
    "get_server",
    "run_stdio",
    "shutdown_runtime",
    "dump_widget_tree",
    "screenshot",
    "navigate",
    "click_widget",
    "set_text",
    "get_state",
    "run_gui_test",
]
