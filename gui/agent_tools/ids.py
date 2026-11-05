"""
Widget identity helpers for agent-facing observability (P0-3).

Canonical agent-facing ID: the Qt dynamic property ``testId`` (see
``TEST_ID_PROPERTY``).  ``objectName`` stays exclusively the QSS style key and
is NEVER renamed (QSS selectors like ``QPushButton#sidebarButton`` depend on
it).  Only ``testId`` is required to be unique.

Grammar (plans/agent-gui-observability.md section 2.1, "Naming convention")::

    testId := <scope>.<qualifier>.<name>       (exactly 2 or 3 dot-separated segments)
    scope  := window | sidebar | statusBar | page | dialog | widget
    qualifier := page_id for scope=page, dialog name for scope=dialog
    name   := lowerCamelCase role noun (saveButton, nameField, materialsTable, ...)

Examples: ``page.materials.saveButton``, ``page.process_sequence.runButton``,
``dialog.studyWizard.nextButton``, ``sidebar.navButton.materials``,
``window.main.contentStack``, ``statusBar.messageLabel``.

This module is dependency-light (PyQt6 only) so pages/dialogs can import it
without pulling in the rest of the toolkit.
"""

from __future__ import annotations

import re

from PyQt6.QtWidgets import QWidget

TEST_ID_PROPERTY = "testId"

# NOTE on the regex: the plan's enforcement-test regex restricts segment 2 to
# ``[a-z0-9_]+``, which rejects the plan's own normative examples
# (``sidebar.navButton.materials``, ``statusBar.messageLabel``,
# ``dialog.studyWizard.nextButton``, ``window.main.contentStack``,
# ``sidebar.scrollArea``).  Both extra segments are therefore matched as
# ``[a-zA-Z0-9_]+`` (lowerCamelCase / snake_case) per the normative naming
# convention (section 2.1); scope set and 2-or-3-segment shape are verbatim.
TEST_ID_RE = re.compile(
    r"^(window|sidebar|statusBar|page|dialog|widget)\.[a-zA-Z0-9_]+(\.[a-zA-Z0-9_]+)?$"
)

__all__ = [
    "TEST_ID_PROPERTY",
    "TEST_ID_RE",
    "WidgetIdError",
    "set_test_id",
    "get_test_id",
    "find_by_test_id",
]


class WidgetIdError(LookupError):
    """Raised on unknown or duplicate widget test IDs."""


def set_test_id(widget: QWidget, test_id: str, *, accessible_name: str | None = None) -> None:
    """Set the unique ``testId`` property on ``widget``.

    A11y convention (P2-3): pass ``accessible_name=`` human text ("Save
    settings", never the raw ``testId``) at the widget's creation site.  The
    name is filled into ``accessibleName`` ONLY when the widget does not have
    one yet -- deliberate names (pre-set, or an earlier ``accessible_name=``)
    are never overwritten.  Without ``accessible_name`` the raw ``test_id``
    fills the gap as a last resort (the cheap P0-3 half); the P2-3
    enforcement tests in ``tests/gui/test_agent_ids.py`` reject that fallback
    on interactive widgets.  Ambiguous form fields additionally get
    ``setAccessibleDescription(...)`` at their creation site.
    """
    widget.setProperty(TEST_ID_PROPERTY, test_id)
    name = accessible_name if accessible_name is not None else test_id
    if not widget.accessibleName():
        widget.setAccessibleName(name)


def get_test_id(widget: QWidget) -> str | None:
    """Return the widget's ``testId``, or ``None`` when unset."""
    value = widget.property(TEST_ID_PROPERTY)
    return str(value) if value is not None else None


def find_by_test_id(root: QWidget, test_id: str) -> QWidget | None:
    """Depth-first search for the widget with ``test_id`` under ``root``.

    ``root`` itself is considered first (so a root-level id such as
    ``window.main`` resolves).  Returns ``None`` when no widget carries the id
    and raises :class:`WidgetIdError` when more than one widget does
    (duplicate IDs).
    """
    if get_test_id(root) == test_id:
        return root
    matches = [w for w in root.findChildren(QWidget) if get_test_id(w) == test_id]
    if len(matches) > 1:
        raise WidgetIdError(f"duplicate testId {test_id!r} on {len(matches)} widgets")
    return matches[0] if matches else None
