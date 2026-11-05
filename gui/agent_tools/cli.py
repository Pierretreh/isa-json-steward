"""
Agent CLI for the ISA-JSON Data Steward GUI (P0-4).

Usage::

    python -m gui.agent_tools pages
    python -m gui.agent_tools dump [--page PAGE] [--widget TEST_ID] [--text] [--out PATH]
    python -m gui.agent_tools screenshot [--page PAGE] [--widget TEST_ID]
                                         [--annotate] [--theme light|dark] [--out DIR]
    python -m gui.agent_tools click TEST_ID
    python -m gui.agent_tools set-text TEST_ID VALUE
    python -m gui.agent_tools get-state TEST_ID
    python -m gui.agent_tools mcp-serve

Every command boots a :class:`~gui.agent_tools.runtime.HeadlessGui`
(offscreen unless ``QT_QPA_PLATFORM`` says otherwise), performs one action,
prints **JSON to stdout** (artifact *paths*, never base64), and exits 0.
Errors print ``{"ok": false, "error": ..., "known_ids": [...]}`` and exit 1.

``mcp-serve`` (P2-1) is the exception: it starts the stdio MCP server
(:mod:`gui.agent_tools.mcp_server`, requires the ``agent`` extra) against one
long-lived offscreen GUI and serves until the client disconnects.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

DEFAULT_OUT_DIR = Path("reports")


def _print_json(payload: dict) -> None:
    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m gui.agent_tools",
        description="Headless GUI observability toolkit for the ISA-JSON Data Steward.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("pages", help="list page ids and the current page")

    p_dump = sub.add_parser("dump", help="dump the widget tree (JSON + optional text)")
    p_dump.add_argument("--page", help="navigate to this page id first")
    p_dump.add_argument("--widget", dest="widget", help="dump this testId subtree only")
    p_dump.add_argument("--text", action="store_true", help="also write the LLM-friendly text form")
    p_dump.add_argument("--out", help="output JSON path (default: reports/widget_tree.json)")

    p_shot = sub.add_parser("screenshot", help="capture a PNG screenshot")
    p_shot.add_argument("--page", help="navigate to this page id first")
    p_shot.add_argument("--widget", dest="widget", help="capture this testId only")
    p_shot.add_argument(
        "--annotate",
        action="store_true",
        help="set-of-marks annotation: numbered badges + legend panel + .legend.json sidecar",
    )
    p_shot.add_argument("--theme", choices=["light", "dark"], help="theme before capture")
    p_shot.add_argument("--out", help="output directory (default: reports/)")

    p_click = sub.add_parser("click", help="click a widget by testId")
    p_click.add_argument("test_id")

    p_set = sub.add_parser("set-text", help="set text on a widget by testId")
    p_set.add_argument("test_id")
    p_set.add_argument("value")

    p_state = sub.add_parser("get-state", help="read widget state by testId")
    p_state.add_argument("test_id")

    sub.add_parser(
        "mcp-serve",
        help="serve the stdio MCP server (long-lived offscreen GUI; needs the agent extra)",
    )

    return parser


def _error_payload(exc: Exception, gui: Any = None) -> dict:
    payload: dict[str, Any] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if gui is not None:
        try:
            payload["known_ids"] = gui.known_ids()
        except Exception:  # pragma: no cover - best effort
            pass
    return payload


def _resolve_target(gui: Any, args: argparse.Namespace):
    """--widget selects a widget subtree; --page selects that page's widget;
    with neither, the whole window is the target (see plan section 2.4)."""
    if getattr(args, "widget", None):
        return gui.find(args.widget)
    if getattr(args, "page", None):
        return gui.find(f"page.{args.page}")
    return gui.window


def _run(args: argparse.Namespace) -> dict:
    """Boot the GUI, run one command, return the JSON payload (never raises)."""
    # Offscreen unless the caller pinned a platform (CI already sets it);
    # ensure_offscreen_platform() also strips whitespace pollution which
    # would otherwise make Qt abort natively on plugin lookup.
    from .runtime import HeadlessGui, ensure_offscreen_platform

    ensure_offscreen_platform()

    # theme=None keeps the app's configured theme unless --theme was given, so
    # plain inspection commands never rewrite the user's persisted preference.
    gui = HeadlessGui(theme=getattr(args, "theme", None))
    try:
        gui.start()
        if getattr(args, "page", None):
            gui.navigate(args.page)

        if args.command == "pages":
            pages = sorted(gui.window.pages)
            current = gui.window.content_stack.currentWidget()
            current_id = None
            for page_id, page in gui.window.pages.items():
                if page is current:
                    current_id = page_id
                    break
            return {"ok": True, "pages": pages, "current": current_id}

        if args.command == "dump":
            from .dump import dump_widget_tree

            tree = dump_widget_tree(_resolve_target(gui, args))
            out_json = Path(args.out) if args.out else DEFAULT_OUT_DIR / "widget_tree.json"
            out_json = out_json.resolve()
            out_json.parent.mkdir(parents=True, exist_ok=True)
            out_json.write_text(json.dumps(tree, indent=2, default=str), encoding="utf-8")
            payload: dict[str, Any] = {
                "ok": True,
                "schema": tree.get("schema"),
                "json_path": str(out_json),
            }
            if args.text:
                from .dump import widget_tree_to_text

                out_txt = out_json.with_suffix(".txt")
                out_txt.write_text(widget_tree_to_text(tree), encoding="utf-8")
                payload["text_path"] = str(out_txt)
            return payload

        if args.command == "screenshot":
            result = gui.screenshot(
                widget=_resolve_target(gui, args),
                out_dir=Path(args.out) if args.out else DEFAULT_OUT_DIR,
                annotate=bool(getattr(args, "annotate", False)),
                theme=getattr(args, "theme", None),
            )
            payload = {
                "ok": True,
                "path": str(result.path),
                "width": result.width,
                "height": result.height,
            }
            if result.marks is not None:
                from .annotate import legend_path_for

                payload["legend_path"] = str(legend_path_for(result.path))
                payload["marks"] = len(result.marks)
            return payload

        if args.command == "click":
            gui.click(args.test_id)
            return {"ok": True, "clicked": args.test_id}

        if args.command == "set-text":
            gui.set_text(args.test_id, args.value)
            return {"ok": True, "test_id": args.test_id, "value": args.value}

        if args.command == "get-state":
            return {"ok": True, "test_id": args.test_id, "state": gui.get_state(args.test_id)}

        return {"ok": False, "error": f"unhandled command {args.command!r}"}  # pragma: no cover
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, never traceback
        return _error_payload(exc, gui)
    finally:
        try:
            gui.shutdown()
        except Exception:  # pragma: no cover - best effort
            pass


def _serve_mcp() -> int:
    """Start the stdio MCP server (P2-1); long-running, no JSON on stdout."""
    from .runtime import ensure_offscreen_platform

    ensure_offscreen_platform()
    try:
        from .mcp_server import run_stdio

        run_stdio()
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, never traceback
        _print_json(
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "hint": 'install the agent extra: pip install -e ".[agent]"',
            }
        )
        return 1
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "mcp-serve":
        return _serve_mcp()
    payload = _run(args)
    _print_json(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
