"""Widget-ID enforcement tests (P0-3) and a11y rollout tests (P2-3).

Implements the enforcement test from plans/agent-gui-observability.md
section 2.1: build ``MainWindow``, walk the tree, and assert that

1. every visible ``QAbstractButton``, ``QLineEdit``, ``QComboBox`` and
   ``QAbstractItemView`` carries a non-empty ``testId``,
2. all ``testId`` values are unique,
3. all ``testId`` values match the naming grammar, and
4. ``find_by_test_id()`` round-trips for every ID in the dump.

Also covers the P0-2 ``contentArea``/``contentPage`` objectName fix, and the
P2-3 accessibility rollout (plans/gui-usability-improvements.md, Batch C2):
human ``accessibleName`` coverage (never the raw ``testId``) on ``MainWindow``
plus the key dialogs, the plan's "top-20 primary actions" criterion, and
``accessibleDescription`` coverage on the multi-field forms.

The walk skips Qt-internal composite children (combo-box popups, spin-box
line edits, item-view headers, tab-bar buttons, ...) — those are created by
Qt, not by the pages/dialogs covered by the rollout set.
"""

import re

import pytest

try:
    from PyQt6.QtWidgets import (
        QAbstractButton,
        QAbstractItemView,
        QAbstractSpinBox,
        QApplication,
        QComboBox,
        QHeaderView,
        QLineEdit,
        QScrollBar,
        QTabBar,
        QWidget,
    )

    PYQT6_AVAILABLE = True
except (ImportError, OSError):
    PYQT6_AVAILABLE = False

pytestmark = pytest.mark.gui

# Classes whose instances are "interactive" per the plan's enforcement test.
if PYQT6_AVAILABLE:
    _INTERACTIVE = (QAbstractButton, QLineEdit, QComboBox, QAbstractItemView)

    # Qt composite widgets whose *children* are Qt-internal machinery
    # (combo popups, spin-box line edits, tab-bar buttons).  Item-view
    # headers/corners are handled by class checks below; QSplitter and
    # QScrollArea are deliberately NOT listed -- their children are
    # ordinary page content and must stay in scope.
    _QT_CONTAINERS = (QComboBox, QAbstractSpinBox, QTabBar, QScrollBar)

    # Qt-internal classes with no creation site in pages/dialogs.
    _QT_INTERNALS = (QHeaderView,)

    # Reusable composites from gui/widgets whose internals are outside the
    # P0-3 rollout set ("no IDs inside — callers set them", plan section 2.1).
    # The container itself is tagged by its creating page/dialog.
    from gui.widgets.collapsible_group_box import CollapsibleGroupBox
    from gui.widgets.file_attachment_widget import FileAttachmentWidget
    from gui.widgets.graph_widget import GraphWidget
    from gui.widgets.path_picker import PathPicker

    _WIDGET_CONTAINERS = (
        CollapsibleGroupBox,
        FileAttachmentWidget,
        GraphWidget,
        PathPicker,
    )


def _is_out_of_rollout(widget, root) -> bool:
    """True for widgets the P0-3 rollout does not tag.

    - Qt-internal composite parts (combo popups, spin-box line edits, item
      view headers/corners, tab-bar buttons) are created by Qt, not at a
      page's creation site.
    - Internals of reusable composites from ``gui/widgets/`` follow the
      plan's "no IDs inside — callers set them (widgets lack context)"
      rule; their container is tagged instead.
    """
    class_name = type(widget).__name__
    if isinstance(widget, _QT_INTERNALS) or class_name == "QTableCornerButton":
        return True
    if widget.objectName() == "qt_tableview_cornerbutton":
        return True
    if isinstance(widget, _WIDGET_CONTAINERS):
        return True
    parent = widget.parent()
    while parent is not None and parent is not root:
        if isinstance(parent, _QT_CONTAINERS + _WIDGET_CONTAINERS):
            return True
        parent = parent.parent()
    return False


def _interactive_widgets(root):
    """All rollout-set interactive widgets under (and including) ``root``."""
    widgets = [root] + root.findChildren(QWidget)
    return [
        w for w in widgets if isinstance(w, _INTERACTIVE) and not _is_out_of_rollout(w, root)
    ]


def _collect_test_ids(root):
    ids = {}
    for w in [root] + root.findChildren(QWidget):
        value = w.property("testId")
        if value not in (None, ""):
            ids[str(value)] = w
    return ids


@pytest.fixture(scope="module")
def main_window(qapp):
    """Build a real MainWindow with the shared lightweight app stub."""
    from tests.gui.conftest import StubApp

    from gui.main_window import MainWindow

    window = MainWindow(StubApp())
    window.show()
    QApplication.processEvents()
    yield window
    # Tear down WITHOUT close(): belt-and-braces retained from before U-02
    # (SettingsPage.save_data() is now a no-op, so closeEvent can no longer
    # rewrite config/settings.json nor pop the restart modal).
    window.hide()
    window.deleteLater()
    QApplication.processEvents()


class TestP02ObjectNameFix:
    """P0-2: contentArea/contentPage collision fix."""

    def test_exactly_one_content_area(self, main_window):
        """The stack is the only widget with objectName "contentArea"."""
        matches = [
            w for w in main_window.findChildren(QWidget) if w.objectName() == "contentArea"
        ]
        assert len(matches) == 1
        assert matches[0] is main_window.content_stack

    def test_every_page_is_content_page(self, main_window):
        """Each page root carries objectName "contentPage" (>=10 of them)."""
        matches = [
            w for w in main_window.findChildren(QWidget) if w.objectName() == "contentPage"
        ]
        assert len(matches) >= 10
        assert set(matches) == set(main_window.pages.values())

    def test_qss_files_keep_both_selectors(self):
        """Both theme files style the stack AND the page roots."""
        from pathlib import Path

        styles = Path(__file__).resolve().parents[2] / "gui" / "resources" / "styles"
        for theme in ("dark", "light"):
            qss = (styles / f"{theme}.qss").read_text(encoding="utf-8")
            assert "QWidget#contentArea, QWidget#contentPage" in qss, (
                f"{theme}.qss must widen the content selector to both objectNames"
            )


class TestTestIdCoverage:
    """P0-3: every visible interactive widget is addressable by testId."""

    def test_visible_interactive_widgets_have_test_ids(self, main_window):
        missing = [
            f"{type(w).__name__}(objectName={w.objectName()!r})"
            for w in _interactive_widgets(main_window)
            if w.isVisible() and not w.property("testId")
        ]
        assert missing == [], f"interactive widgets without testId: {missing}"

    def test_hidden_interactive_widgets_have_test_ids(self, main_window):
        """Coverage extends to pages hidden in the stack, not just the
        current one (the rollout set tags widgets at creation sites)."""
        missing = [
            f"{type(w).__name__}(objectName={w.objectName()!r})"
            for w in _interactive_widgets(main_window)
            if not w.property("testId")
        ]
        assert missing == [], f"interactive widgets without testId: {missing}"


class TestTestIdProperties:
    """P0-3: uniqueness and grammar for every testId in the tree."""

    def test_test_ids_are_unique(self, main_window):
        seen = {}
        duplicates = []
        for w in [main_window] + main_window.findChildren(QWidget):
            value = w.property("testId")
            if value in (None, ""):
                continue
            value = str(value)
            if value in seen:
                duplicates.append(value)
            seen[value] = w
        assert duplicates == [], f"duplicate testIds: {duplicates}"

    def test_test_ids_match_grammar(self, main_window):
        from gui.agent_tools.ids import TEST_ID_RE

        bad = []
        for w in [main_window] + main_window.findChildren(QWidget):
            value = w.property("testId")
            if value in (None, ""):
                continue
            if not TEST_ID_RE.match(str(value)):
                bad.append(str(value))
        assert bad == [], f"testIds violating the section 2.1 grammar: {bad}"

    def test_grammar_regex_shape(self):
        """Sanity-check the regex itself against plan examples."""
        from gui.agent_tools.ids import TEST_ID_RE

        for good in (
            "window.main",
            "window.main.contentStack",
            "sidebar.title",
            "sidebar.scrollArea",
            "sidebar.navButton.materials",
            "statusBar.messageLabel",
            "page.materials.saveButton",
            "page.process_sequence.runButton",
            "dialog.studyWizard.nextButton",
        ):
            assert TEST_ID_RE.match(good), f"plan example rejected: {good}"
        for bad in ("materials.saveButton", "page..saveButton", "page.a.b.c", ""):
            assert not TEST_ID_RE.match(bad), f"malformed id accepted: {bad}"


class TestFindById:
    """P0-3: find_by_test_id round-trips every ID present in the tree."""

    def test_round_trip_every_id(self, main_window):
        from gui.agent_tools.ids import find_by_test_id, get_test_id

        for test_id, widget in _collect_test_ids(main_window).items():
            found = find_by_test_id(main_window, test_id)
            assert found is widget, f"round-trip failed for {test_id!r}"
            assert get_test_id(found) == test_id

    def test_unknown_id_returns_none(self, main_window):
        from gui.agent_tools.ids import find_by_test_id

        assert find_by_test_id(main_window, "page.dashboard.noSuchWidget") is None

    def test_duplicate_id_raises(self, main_window):
        from gui.agent_tools.ids import WidgetIdError, find_by_test_id, set_test_id

        probe_a = QWidget(main_window)
        probe_b = QWidget(main_window)
        set_test_id(probe_a, "widget.probe.duplicate", accessible_name="Duplicate id probe A")
        set_test_id(probe_b, "widget.probe.duplicate", accessible_name="Duplicate id probe B")
        try:
            with pytest.raises(WidgetIdError):
                find_by_test_id(main_window, "widget.probe.duplicate")
        finally:
            probe_a.deleteLater()
            probe_b.deleteLater()
            # Flush the DeferredDelete events so the probes cannot linger in the
            # shared module-scoped window and leak into later walks (P2-3).
            from PyQt6.QtCore import QEvent

            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class TestSidebarIds:
    """P0-3: sidebar nav buttons report sidebar.navButton.<page_id>."""

    def test_nav_button_ids_match_page_ids(self, main_window):
        from gui.agent_tools.ids import get_test_id

        for btn in main_window.sidebar.button_group.buttons():
            page_id = btn.property("pageId")
            assert page_id in main_window.pages
            assert get_test_id(btn) == f"sidebar.navButton.{page_id}"

    def test_every_page_has_a_nav_button(self, main_window):
        button_pages = {
            btn.property("pageId") for btn in main_window.sidebar.button_group.buttons()
        }
        assert button_pages == set(main_window.pages)


class TestShellAndRootIds:
    """Window shell and page roots carry the mandated IDs."""

    def test_window_shell_ids(self, main_window):
        from gui.agent_tools.ids import get_test_id

        assert get_test_id(main_window) == "window.main"
        assert get_test_id(main_window.content_stack) == "window.main.contentStack"

    def test_page_root_ids(self, main_window):
        from gui.agent_tools.ids import get_test_id

        for page_id, page in main_window.pages.items():
            assert get_test_id(page) == f"page.{page_id}"


class TestSetTestId:
    """Unit-level behavior of the ids helpers."""

    def test_sets_property_and_accessible_name(self, qapp):
        from gui.agent_tools.ids import TEST_ID_PROPERTY, get_test_id, set_test_id

        w = QWidget()
        try:
            set_test_id(w, "widget.unit.probe")
            assert w.property(TEST_ID_PROPERTY) == "widget.unit.probe"
            assert get_test_id(w) == "widget.unit.probe"
            assert w.accessibleName() == "widget.unit.probe"
        finally:
            w.deleteLater()

    def test_explicit_accessible_name_is_kept(self, qapp):
        from gui.agent_tools.ids import set_test_id

        w = QWidget()
        try:
            w.setAccessibleName("Human readable")
            set_test_id(w, "widget.unit.named", accessible_name="Other")
            assert w.accessibleName() == "Human readable"
        finally:
            w.deleteLater()

    def test_common_widget_test_id_kwarg(self, qapp):
        """PrimaryButton/ActionButton/DangerButton/FormField forward test_id."""
        from gui.agent_tools.ids import get_test_id
        from gui.widgets.common import ActionButton, FormField, PrimaryButton

        button = PrimaryButton("Save", test_id="widget.unit.primaryButton")
        field = FormField("placeholder", test_id="widget.unit.formField")
        action = ActionButton("Run", test_id="widget.unit.actionButton")
        try:
            assert get_test_id(button) == "widget.unit.primaryButton"
            assert get_test_id(field) == "widget.unit.formField"
            assert get_test_id(action) == "widget.unit.actionButton"
        finally:
            button.deleteLater()
            field.deleteLater()
            action.deleteLater()

    def test_common_widget_forwards_accessible_name(self, qapp):
        """P2-3: the common widgets forward ``accessible_name`` to set_test_id."""
        from gui.agent_tools.ids import get_test_id
        from gui.widgets.common import PrimaryButton

        button = PrimaryButton("Save", test_id="widget.unit.named", accessible_name="Save things")
        try:
            assert get_test_id(button) == "widget.unit.named"
            assert button.accessibleName() == "Save things"
        finally:
            button.deleteLater()


# ---------------------------------------------------------------------------
# P2-3 accessibility rollout (plans/gui-usability-improvements.md, Batch C2)
# ---------------------------------------------------------------------------


def _human_name_ok(name: str, test_id) -> bool:
    """P2-3 quality rule: ``accessibleName`` is human-readable, not a raw id.

    Operational definition of the plan's "human-readable (not pure-testId)
    names": non-empty, not equal to the widget's ``testId``, not shaped like
    the ``testId`` grammar, and containing at least one letter.
    """
    from gui.agent_tools.ids import TEST_ID_RE

    if not name or not name.strip():
        return False
    if test_id is not None and name == str(test_id):
        return False
    if TEST_ID_RE.match(name):
        return False
    return any(c.isalpha() for c in name)


def _bad_tagged_names(root):
    """Tagged widgets under ``root`` whose ``accessibleName`` fails the rule."""
    bad = []
    for w in [root] + root.findChildren(QWidget):
        value = w.property("testId")
        if value in (None, ""):
            continue
        if not _human_name_ok(w.accessibleName(), str(value)):
            bad.append(
                f"{type(w).__name__}(testId={value!r}, accessibleName={w.accessibleName()!r})"
            )
    return bad


def _bad_interactive_names(root):
    """Rollout-set interactive widgets under ``root`` failing the name rule."""
    from gui.agent_tools.ids import get_test_id

    bad = []
    for w in _interactive_widgets(root):
        test_id = get_test_id(w)
        if not _human_name_ok(w.accessibleName(), test_id):
            bad.append(
                f"{type(w).__name__}(testId={test_id!r}, accessibleName={w.accessibleName()!r})"
            )
    return bad


def _key_dialog_factories():
    """(label, factory) pairs for the key dialogs in the P2-3 scope.

    Construction mirrors the patterns already used by tests/gui (no ``exec()``,
    no modals): default args only, plus one ``ParameterDialog`` parameter to
    exercise a dynamic-row id.
    """
    from gui.dialogs.add_parameter_dialog import AddParameterDialog
    from gui.dialogs.assay_dialog import AssayDialog
    from gui.dialogs.batch_processing import BatchProcessingDialog
    from gui.dialogs.image_converter import ImageConverterDialog
    from gui.dialogs.investigation_dialog import InvestigationDialog
    from gui.dialogs.material_dialog import CharacteristicDialog, MaterialDialog
    from gui.dialogs.material_selection_dialog import MaterialSelectionDialog
    from gui.dialogs.parameter_dialog import ParameterDialog
    from gui.dialogs.study_wizard import StudyWizard
    from gui.dialogs.template_editor import TemplateEditorDialog

    return [
        ("AddParameterDialog", lambda: AddParameterDialog(existing_params=[])),
        ("AssayDialog", lambda: AssayDialog()),
        ("BatchProcessingDialog", lambda: BatchProcessingDialog()),
        ("ImageConverterDialog", lambda: ImageConverterDialog()),
        ("InvestigationDialog", lambda: InvestigationDialog(dm=None)),
        ("CharacteristicDialog", lambda: CharacteristicDialog()),
        ("MaterialDialog", lambda: MaterialDialog(dm=None)),
        ("MaterialSelectionDialog", lambda: MaterialSelectionDialog()),
        (
            "ParameterDialog",
            lambda: ParameterDialog(
                protocol_name="probe", parameters=[{"annotationValue": "temperature"}]
            ),
        ),
        ("StudyWizard", lambda: StudyWizard(dm=None)),
        ("TemplateEditorDialog", lambda: TemplateEditorDialog()),
    ]


class TestAccessibleNameCoverage:
    """P2-3: human ``accessibleName`` coverage on MainWindow + key dialogs."""

    def test_visible_interactive_widgets_have_accessible_names(self, main_window):
        """Plan enforcement, sentence 1: non-empty names on visible widgets."""
        missing = [
            f"{type(w).__name__}(testId={w.property('testId')!r})"
            for w in _interactive_widgets(main_window)
            if w.isVisible() and not w.accessibleName().strip()
        ]
        assert missing == [], f"visible interactive widgets without accessibleName: {missing}"

    def test_tagged_widgets_have_human_names(self, main_window):
        """Every tagged widget's name is human-readable, not the raw testId."""
        assert _bad_tagged_names(main_window) == []

    def test_primary_actions_have_human_names(self, main_window):
        """Plan criterion: the top-20 primary actions read as human text.

        Subsumed by the full tagged sweep above; asserted separately (buttons,
        >= 20 of them) for traceability to the plan's wording.
        """
        buttons = [w for w in _interactive_widgets(main_window) if isinstance(w, QAbstractButton)]
        assert len(buttons) >= 20, f"expected >= 20 primary actions, found {len(buttons)}"
        assert _bad_interactive_names(main_window) == []

    def test_key_dialogs_have_human_names(self, qapp):
        """Acceptance: the enforcement is green on MainWindow + key dialogs."""
        for label, factory in _key_dialog_factories():
            dialog = factory()
            try:
                QApplication.processEvents()
                assert _bad_tagged_names(dialog) == [], label
                assert _bad_interactive_names(dialog) == [], label
            finally:
                dialog.hide()
                dialog.deleteLater()
                QApplication.processEvents()


class TestAccessibleDescriptions:
    """P2-3: ``accessibleDescription`` on the plan's multi-field forms."""

    def test_settings_form_fields_have_descriptions(self, main_window):
        """Plan suggested test: description coverage for the settings form."""
        from PyQt6.QtWidgets import QAbstractSpinBox, QCheckBox, QPlainTextEdit, QTextEdit

        from gui.widgets.path_picker import PathPicker

        field_classes = (
            QLineEdit,
            QComboBox,
            QAbstractSpinBox,
            QCheckBox,
            QTextEdit,
            QPlainTextEdit,
            PathPicker,
        )
        fields = [
            w
            for w in main_window.findChildren(QWidget)
            if str(w.property("testId") or "").startswith("page.settings.")
            and isinstance(w, field_classes)
        ]
        assert len(fields) >= 30, f"expected the settings form fields, found {len(fields)}"
        missing = [
            str(w.property("testId")) for w in fields if not w.accessibleDescription().strip()
        ]
        assert missing == [], f"settings form fields without accessibleDescription: {missing}"

    def test_assay_dialog_fields_have_descriptions(self, qapp):
        """The dialog.assay multi-field form carries field descriptions too."""
        from gui.dialogs.assay_dialog import AssayDialog

        dialog = AssayDialog()
        try:
            QApplication.processEvents()
            fields = [
                w
                for w in dialog.findChildren(QWidget)
                if str(w.property("testId") or "").startswith("dialog.assay.")
                and isinstance(w, (QLineEdit, QComboBox))
            ]
            assert fields
            missing = [
                str(w.property("testId")) for w in fields if not w.accessibleDescription().strip()
            ]
            assert missing == [], f"assay dialog fields without accessibleDescription: {missing}"
        finally:
            dialog.hide()
            dialog.deleteLater()
            QApplication.processEvents()


class TestDumpAccessibleNames:
    """P2-3 acceptance: dump_widget_tree() reports populated accessibleName."""

    def test_dump_reports_human_names_for_primary_actions(self, main_window):
        from gui.agent_tools.dump import dump_widget_tree

        tree = dump_widget_tree(main_window)
        wanted = {
            "page.settings.saveButton",
            "page.materials.addButton",
            "page.studies.deleteButton",
            "page.dashboard.runBatchButton",
            "page.process_sequence.saveButton",
        }
        found = {}

        def _walk(node):
            if node.get("testId") in wanted:
                found[node["testId"]] = node.get("accessibleName", "")
            for child in node.get("children", []):
                _walk(child)

        _walk(tree["root"])
        assert set(found) == wanted, f"missing nodes in dump: {wanted - set(found)}"
        for test_id, name in found.items():
            assert _human_name_ok(name, test_id), f"{test_id}: accessibleName={name!r}"


class TestNoBarePrint:
    """U-12 regression guard: GUI code logs, it never prints.

    Source scan over ``gui/pages/`` and ``gui/dialogs/`` (the acceptance
    scope of ``plans/gui-usability-fixes.md`` U-12; ``gui/agent_tools``
    CLI JSON-on-stdout helpers are intentionally exempt).
    """

    def test_no_bare_print_in_pages_and_dialogs(self):
        import re
        from pathlib import Path

        gui_root = Path(__file__).resolve().parents[2] / "gui"
        offenders = []
        for sub in ("pages", "dialogs"):
            for py_file in sorted((gui_root / sub).rglob("*.py")):
                for lineno, line in enumerate(
                    py_file.read_text(encoding="utf-8").splitlines(), 1
                ):
                    if re.match(r"\s*print\(", line):
                        rel = py_file.relative_to(gui_root).as_posix()
                        offenders.append(f"{rel}:{lineno}")
        assert offenders == [], f"bare print() in GUI code: {offenders}"
