"""MCP server smoke tests (P2-1) for the ISA-JSON Data Steward GUI.

Covers the acceptance criteria from plans/agent-gui-observability.md
section 5 ("P2-1 MCP") using in-process tool calls (the plan-prescribed
route):

- the server exposes exactly the 7 tools of section 2.7;
- ``navigate`` -> ``dump_widget_tree`` mentions the target page;
- ``click_widget`` on a real button changes state observable via
  ``get_state``; ``set_text``/``get_state`` round-trips;
- ``screenshot`` returns PNG path + legend path (never base64), capped at
  ``max_edge``; explicit ``theme`` is session-only;
- unknown testIds return the ``{"ok": false, ..., "known_ids"}`` payload;
- ``run_gui_test`` returns a parsed pytest summary;
- ``python -m gui.agent_tools mcp-serve`` serves stdio and lists the 7 tools.

All checks run under ``QT_QPA_PLATFORM=offscreen``.  The whole module skips
cleanly when the ``mcp`` SDK is not installed.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")  # the plan's guard: skip cleanly without the SDK

try:
    from PyQt6.QtWidgets import QApplication  # noqa: F401

    PYQT6_AVAILABLE = True
except (ImportError, OSError):
    PYQT6_AVAILABLE = False

pytestmark = pytest.mark.gui

REPO_ROOT = Path(__file__).resolve().parents[2]

TOOL_NAMES = {
    "dump_widget_tree",
    "screenshot",
    "navigate",
    "click_widget",
    "set_text",
    "get_state",
    "run_gui_test",
}


def _call(coro):
    """Run one async MCP tool handler in-process; return its string result."""
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def mcp(qapp):
    """The ``gui.agent_tools.mcp_server`` module with a clean shared runtime.

    Mirrors the server's real long-lived ``HeadlessGui`` (one instance per
    process, lazily booted) and tears it down after the module.
    """
    from gui.agent_tools import mcp_server

    mcp_server.shutdown_runtime()  # clean slate
    yield mcp_server
    mcp_server.shutdown_runtime()  # hide -- never close -- the window


class TestMcpToolSurface:
    """The server registers exactly the 7 plan-section-2.7 tools."""

    def test_server_lists_seven_tools(self, mcp):
        tools = asyncio.run(mcp.get_server().list_tools())
        names = {t.name for t in tools}
        assert names == TOOL_NAMES

    def test_mcp_serve_cli_subcommand_registered(self):
        from gui.agent_tools.cli import _build_parser

        args = _build_parser().parse_args(["mcp-serve"])
        assert args.command == "mcp-serve"


class TestMcpToolRoundTrips:
    """In-process round-trips for the stateful tools."""

    def test_navigate_and_dump(self, mcp):
        payload = json.loads(_call(mcp.navigate("materials")))
        assert payload == {"ok": True, "page": "materials"}

        # Text form (default) mentions the target page.
        text = _call(mcp.dump_widget_tree())
        assert "page.materials" in text

        # JSON form keeps the versioned dump schema.
        tree_payload = json.loads(_call(mcp.dump_widget_tree(as_text=False)))
        assert tree_payload["tree"]["schema"] == "isa-gui/widget-tree/1"
        assert tree_payload["tree"]["root"]["class"] == "MainWindow"

        # Subtree by test_id.
        sub = json.loads(_call(mcp.dump_widget_tree(test_id="page.materials", as_text=False)))
        assert sub["tree"]["root"]["testId"] == "page.materials"

    def test_click_widget_changes_state(self, mcp):
        _call(mcp.navigate("dashboard"))
        payload = json.loads(_call(mcp.click_widget("sidebar.navButton.materials")))
        assert payload == {"ok": True, "clicked": "sidebar.navButton.materials"}
        state = json.loads(_call(mcp.get_state("sidebar.navButton.materials")))
        assert state["checked"] is True
        assert set(state) == {"text", "checked", "enabled", "visible", "value"}

    def test_click_checkbox_toggles_state(self, mcp):
        _call(mcp.navigate("settings"))
        before = json.loads(_call(mcp.get_state("page.settings.backupOnSaveCheck")))
        _call(mcp.click_widget("page.settings.backupOnSaveCheck"))
        after = json.loads(_call(mcp.get_state("page.settings.backupOnSaveCheck")))
        assert after["checked"] != before["checked"]
        # Restore the original value.
        _call(mcp.click_widget("page.settings.backupOnSaveCheck"))

    def test_set_text_get_state_round_trip(self, mcp):
        _call(mcp.navigate("files"))
        _call(mcp.set_text("page.files.searchField", "needle-42"))
        state = json.loads(_call(mcp.get_state("page.files.searchField")))
        assert state["text"] == "needle-42"
        assert state["enabled"] is True and state["visible"] is True
        _call(mcp.set_text("page.files.searchField", ""))  # restore

    def test_screenshot_returns_paths_never_base64(self, mcp):
        _call(mcp.navigate("materials"))
        payload = json.loads(_call(mcp.screenshot(annotate=True, max_edge=512)))
        assert set(payload) >= {"path", "width", "height", "legend", "legend_path"}

        png = Path(payload["path"])
        assert png.suffix == ".png" and png.is_file() and png.stat().st_size > 0
        assert max(payload["width"], payload["height"]) <= 512

        # Set-of-marks legend: inline entries + .legend.json sidecar.
        assert payload["legend"], "annotated capture carries marks"
        assert set(payload["legend"][0]) == {"index", "test_id", "label"}
        legend_path = Path(payload["legend_path"])
        assert legend_path.is_file()
        legend = json.loads(legend_path.read_text(encoding="utf-8"))
        assert {m["test_id"] for m in legend} == {m["test_id"] for m in payload["legend"]}

        # Paths only -- never base64 image data in tool responses.
        assert "base64" not in json.dumps(payload).lower()

    def test_screenshot_theme_is_session_only(self, mcp):
        from PyQt6.QtCore import QSettings

        app = QApplication.instance()
        settings = QSettings("isa-json-steward-agent", "DataSteward")

        # DS-2: theme= is delegated to gui_screenshot() (U-06 centralization)
        # -- probe the invariance through the MCP handler path for both themes.
        for theme in ("dark", "light"):
            theme_before = settings.value("gui/theme")
            style_before = app.styleSheet()

            payload = json.loads(_call(mcp.screenshot(annotate=False, theme=theme)))
            assert Path(payload["path"]).is_file()
            assert "legend_path" not in payload  # annotate=False -> no sidecar

            # Session-only: the persisted theme is untouched and the previous
            # stylesheet is restored after the capture (hazard 3).
            assert settings.value("gui/theme") == theme_before
            assert app.styleSheet() == style_before


class TestMcpResilience:
    """U-01: a slot exception must not kill the MCP session.

    The runtime's boot installs the crash hooks, so an exception escaping a
    Qt slot writes a ``crash_reports/<ts>/`` bundle instead of aborting the
    process (0xC0000409); subsequent tool calls keep returning payloads and
    the server still lists exactly the 7 plan-section-2.7 tools.
    """

    def test_session_survives_slot_exception(self, mcp, qtbot, tmp_path):
        from PyQt6.QtCore import QTimer

        from gui.agent_tools import crash as crash_mod

        gui = mcp._get_gui()  # boot installs the hook trio (U-01)
        out_root = tmp_path / "crash_reports"

        def boom():
            raise RuntimeError("mcp slot boom")

        # The exception is expected: qtbot.captureExceptions() keeps pytest-qt
        # from failing the test on the unhandled slot exception.  NOTE:
        # capture_exceptions() *replaces* sys.excepthook with a non-chaining
        # collector on entry, so the boot-installed wrapper is removed BEFORE
        # the context and re-installed INSIDE it -- the wrapper then chains
        # into the collector, producing both the crash bundle and the captured
        # record (without leaking into pytest-qt's per-test collector).
        crash_mod.uninstall_crash_hooks()
        with qtbot.captureExceptions() as captured:
            crash_mod.install_crash_hooks(out_root=out_root)
            QTimer.singleShot(0, boom)  # slot raise during event dispatch
            gui.process_events(300)
        assert any("mcp slot boom" in repr(exc) for exc in captured)

        # Subsequent tool calls still return well-formed payloads.
        state = json.loads(_call(mcp.get_state("sidebar.navButton.materials")))
        assert state["text"] == "Materials"
        payload = json.loads(_call(mcp.navigate("dashboard")))
        assert payload == {"ok": True, "page": "dashboard"}

        # ... and the server still lists exactly the 7 tools.
        tools = asyncio.run(mcp.get_server().list_tools())
        assert {t.name for t in tools} == TOOL_NAMES

        # The exception produced a complete crash bundle (never a raw
        # traceback on the wire).  Note: in this in-process harness the app
        # is a shim over a plain QApplication (no StewardNotifyMixin), so the
        # exception surfaces via the sys.excepthook path -- ``fatal`` is not
        # pinned here (the notify-path fatal=false classification is covered
        # by tests/gui/test_agent_diagnostics.py).
        bundles = [p for p in out_root.iterdir() if p.is_dir()]
        assert len(bundles) == 1, [p.name for p in bundles]
        exc = json.loads((bundles[0] / "exception.json").read_text(encoding="utf-8"))
        assert exc["type"] == "RuntimeError"
        assert exc["message"] == "mcp slot boom"


class TestMcpErrorPayloads:
    """Errors are structured payloads -- never raw tracebacks."""

    def test_unknown_test_id(self, mcp):
        payload = json.loads(_call(mcp.get_state("page.nope.missing")))
        assert payload["ok"] is False
        assert "WidgetIdError" in payload["error"]
        assert "unknown id" in payload["error"]
        assert "window.main" in payload["known_ids"]

    def test_unknown_page(self, mcp):
        payload = json.loads(_call(mcp.navigate("nope")))
        assert payload["ok"] is False
        assert "known pages" in payload["error"]

    def test_bad_theme_argument(self, mcp):
        payload = json.loads(_call(mcp.screenshot(theme="neon")))
        assert payload["ok"] is False
        assert "theme must be" in payload["error"]


class TestRunGuiTest:
    """``run_gui_test`` runs the pytest command and parses the summary."""

    def test_no_match_is_parsed_summary(self, mcp):
        payload = json.loads(_call(mcp.run_gui_test("zzz_no_such_gui_test_zzz")))
        assert payload["returncode"] == 5  # pytest: no tests collected
        assert payload["passed"] == payload["failed"] == payload["skipped"] == 0
        assert isinstance(payload["output_tail"], str)

    def test_argv_needs_no_addopts_override(self, mcp, monkeypatch):
        """E-1: the cov gate left ``pytest.ini`` addopts, so ``run_gui_test``
        no longer passes ``-o addopts=`` -- and still parses summaries."""
        captured: dict = {}

        class _Proc:
            returncode = 0
            stdout = "1 passed in 0.01s"
            stderr = ""

        def fake_run(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            return _Proc()

        monkeypatch.setattr("gui.agent_tools.mcp_server.subprocess.run", fake_run)
        payload = json.loads(_call(mcp.run_gui_test("any_pattern")))
        assert payload["returncode"] == 0
        assert payload["passed"] == 1 and payload["failed"] == 0
        assert "-o" not in captured["cmd"]
        assert not any(arg.startswith("addopts") for arg in captured["cmd"])

    @pytest.mark.slow
    def test_matching_run_returns_counts(self, mcp):
        # One tiny pytest-qt test keeps the nested run cheap.
        payload = json.loads(_call(mcp.run_gui_test("wait_signal_catches_emission")))
        assert payload["returncode"] == 0
        assert payload["passed"] == 1
        assert payload["failed"] == 0
        assert payload["skipped"] == 0
        assert payload["output_tail"].strip()


@pytest.mark.slow
@pytest.mark.skipif(not PYQT6_AVAILABLE, reason="PyQt6 not available")
def test_mcp_serve_stdio_lists_seven_tools():
    """End-to-end: ``python -m gui.agent_tools mcp-serve`` over stdio."""
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def _run():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "gui.agent_tools", "mcp-serve"],
            cwd=str(REPO_ROOT),
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        )
        with anyio.fail_after(120):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    result = await session.call_tool("navigate", {"page_id": "materials"})
                    return {t.name for t in tools.tools}, result

    names, result = anyio.run(_run)
    assert names == TOOL_NAMES
    assert not result.isError
    assert json.loads(result.content[0].text) == {"ok": True, "page": "materials"}
