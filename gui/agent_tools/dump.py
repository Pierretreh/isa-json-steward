"""
Widget-tree dumps for agent inspection (P0-4).

``dump_widget_tree()`` renders a widget hierarchy into the JSON schema
``isa-gui/widget-tree/1`` (one node per widget, global geometry, dynamic
properties) and ``widget_tree_to_text()`` renders the same information in an
LLM-friendly indented text form.  See plans/agent-gui-observability.md
section 2.4 for the normative node schema.
"""

from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QAbstractButton, QComboBox, QLabel, QLineEdit, QWidget

from .ids import TEST_ID_PROPERTY, get_test_id

WIDGET_TREE_SCHEMA = "isa-gui/widget-tree/1"


def _widget_text(widget: QWidget) -> str:
    """Best-effort display text for a widget."""
    if isinstance(widget, QComboBox):
        return widget.currentText()
    if isinstance(widget, (QLabel, QAbstractButton, QLineEdit)):
        return widget.text()
    text_fn = getattr(widget, "text", None)
    if callable(text_fn):
        try:
            return str(text_fn())
        except TypeError:  # pragma: no cover - defensive
            return ""
    return ""


def _widget_value(widget: QWidget) -> Any:
    """Best-effort "value" for state reads (combo index, spin value, text)."""
    if isinstance(widget, QComboBox):
        return widget.currentIndex()
    value_fn = getattr(widget, "value", None)  # QAbstractSpinBox and friends
    if callable(value_fn):
        try:
            return value_fn()
        except TypeError:  # pragma: no cover - defensive
            return None
    return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _build_node(
    widget: QWidget,
    root: QWidget,
    origin: QPoint,
    *,
    include_hidden: bool,
    max_depth: Optional[int],
    depth: int,
) -> Optional[dict]:
    """Build one tree node (schema ``isa-gui/widget-tree/1``) for ``widget``."""
    if not include_hidden and depth > 0 and not widget.isVisibleTo(root):
        return None

    top_left = widget.mapToGlobal(QPoint(0, 0)) - origin
    visible = widget.isVisible()
    # N5: hidden widgets are skipped by layouts and can retain stale rects
    # from earlier layout passes -- normalize their geometry to the zero
    # rect so dump consumers never read a stale shape.  Schema-compatible:
    # same keys/types; values change for hidden nodes only.
    if visible:
        geometry = {
            "x": top_left.x(),
            "y": top_left.y(),
            "width": widget.width(),
            "height": widget.height(),
        }
    else:
        geometry = {"x": 0, "y": 0, "width": 0, "height": 0}
    node: dict[str, Any] = {
        "testId": get_test_id(widget),
        "class": type(widget).__name__,
        "objectName": widget.objectName(),
        "accessibleName": widget.accessibleName(),
        "text": _widget_text(widget),
        "toolTip": widget.toolTip(),
        "visible": visible,
        "enabled": widget.isEnabled(),
        "geometry": geometry,
        "properties": {},
        "children": [],
    }
    # Duck-typed checkbox support; hasattr() also narrows QWidget for mypy.
    if hasattr(widget, "isCheckable") and widget.isCheckable() and hasattr(widget, "isChecked"):
        node["checked"] = widget.isChecked()

    for name in widget.dynamicPropertyNames():
        key = name.data().decode("utf-8", errors="replace")
        if key == TEST_ID_PROPERTY:
            continue
        node["properties"][key] = _json_safe(widget.property(key))

    if max_depth is not None and depth + 1 >= max_depth:
        return node

    for child in widget.children():
        if not isinstance(child, QWidget):
            continue
        child_node = _build_node(
            child,
            root,
            origin,
            include_hidden=include_hidden,
            max_depth=max_depth,
            depth=depth + 1,
        )
        if child_node is not None:
            node["children"].append(child_node)
    return node


def dump_widget_tree(
    root: Optional[QWidget] = None,
    *,
    include_hidden: bool = True,
    max_depth: Optional[int] = None,
) -> dict:
    """Dump ``root`` (default: active window) as ``isa-gui/widget-tree/1`` JSON.

    Geometry is reported in global coordinates anchored at the root widget's
    top-left corner (so the root's own corner is 0,0 and children line up with
    screenshot pixels of a ``gui_screenshot(root)`` capture).

    ``include_hidden=False`` drops widgets that are not visible relative to
    ``root``; hidden nodes are always flagged via their ``visible`` field.
    ``max_depth`` caps the number of levels emitted (root counts as one).

    Hidden nodes (``visible: false``) report a **zeroed** ``geometry`` rect
    (``{"x": 0, "y": 0, "width": 0, "height": 0}``) -- stale rect
    normalization: hidden widgets are skipped by layouts and can keep
    leftover rects from earlier layout passes.  The schema key set is
    unchanged; only hidden nodes' geometry values differ.
    """
    if root is None:
        from PyQt6.QtWidgets import QApplication

        root = QApplication.activeWindow()
        if root is None:
            raise RuntimeError("dump_widget_tree: no active window; pass root explicitly")

    origin = root.mapToGlobal(QPoint(0, 0))
    tree_root = _build_node(
        root, root, origin, include_hidden=include_hidden, max_depth=max_depth, depth=0
    )
    return {"schema": WIDGET_TREE_SCHEMA, "root": tree_root}


def widget_tree_to_text(tree: dict) -> str:
    """Render a dump (or bare node dict) as indented LLM-friendly text.

    Every ``testId`` present in the JSON appears in the text output.
    """
    node = tree["root"] if isinstance(tree, dict) and "root" in tree else tree
    if node is None:
        return ""
    lines: list[str] = []

    def _walk(n: dict, depth: int) -> None:
        indent = "  " * depth
        geo = n["geometry"]
        flags = []
        if n.get("visible"):
            flags.append("visible")
        if n.get("enabled"):
            flags.append("enabled")
        if n.get("checked") is not None:
            flags.append("checked" if n["checked"] else "unchecked")
        flags_s = f" [{', '.join(flags)}]" if flags else ""
        text_s = f' "{n["text"]}"' if n.get("text") else ""
        test_id_s = n["testId"] if n.get("testId") else "-"
        obj_s = n["objectName"] or "-"
        lines.append(
            f'{indent}{n["class"]} testId={test_id_s} objectName={obj_s}'
            f'{text_s} ({geo["x"]},{geo["y"]} {geo["width"]}x{geo["height"]}){flags_s}'
        )
        for child in n.get("children", []):
            _walk(child, depth + 1)

    _walk(node, 0)
    return "\n".join(lines)
