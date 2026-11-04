"""Workflow-UX regression tests for Batch 3 of ``plans/gui-usability-fixes.md``.

Implements the acceptance cases for:

* **U-07** -- settings save flow: Save/Reset live in a fixed footer outside
  the scroll area and are visible at the window minimum; Save never opens a
  modal and returns promptly; restart-required settings show a non-modal
  hint + ``Restart Now`` button whose handler schedules a queued shutdown
  (no ``sys.exit()`` in ``gui/pages/settings.py``); cheap settings (theme,
  font, auto-save interval, window dims) never flag restart while startup
  settings (directories, URLs) do; the auto-save tick message is honest for
  the manual-only settings page.
* **U-11** -- selection gating: Edit/Delete/Export/Save/Remove buttons are
  disabled with nothing selected, enable when a row/item is selected, and
  re-disable when the selection clears; clicking a disabled button is a
  silent no-op (no ``QMessageBox``); Add-type buttons gate on a loaded
  study.
* **U-08** -- horizontal scrolling: none of the 10 pages reports a
  horizontal scrollbar at the default window size or at the plan's 938px
  content width; materials-table header sections fit their header text
  (no mid-word clipping).
* **U-10** -- status bar: the four ``statusBar.*`` children never overlap,
  with the progress bar hidden and after ``show_progress()``.
* **U-13** -- empty states: the Images/Templates lists show muted
  placeholders while empty and hide them once populated; the preview pane
  shows "Select a template to preview" until a template is selected.
* **U-14** -- button semantics: the six destructive buttons are
  ``DangerButton``s (``objectName: dangerButton``) and both themes style
  disabled primary/danger buttons.
* **U-15(b)** -- settings form: checkbox rows are uniform 22px tall and
  left aligned; field columns line up across the eight sections.

Reuses the ``make_settings_window`` / ``_forbid_modals`` helpers from
``tests/gui/test_settings_page.py`` (Batch 1b).
"""

import json
from pathlib import Path

import pytest

# Batch 1b helpers: isolated-config window factory and the modal watchdog.
from tests.gui.test_settings_page import (  # noqa: F401
    _forbid_modals,
    make_settings_window,
)

pytestmark = pytest.mark.gui

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PAGE_PY = REPO_ROOT / "gui" / "pages" / "settings.py"

PAGE_IDS = [
    "dashboard",
    "studies",
    "process_sequence",
    "materials",
    "assays",
    "files",
    "images",
    "ontology",
    "templates",
    "settings",
]


def _find(window, test_id):
    from gui.agent_tools.ids import find_by_test_id

    widget = find_by_test_id(window, test_id)
    assert widget is not None, f"missing testId {test_id}"
    return widget


def _process_events():
    from PyQt6.QtWidgets import QApplication

    QApplication.processEvents()


# ---------------------------------------------------------------------------
# U-11 helpers: inject one selectable item and drive the real selection
# signals (never mouse events -- deterministic in the offscreen platform).
# ---------------------------------------------------------------------------


def _materials_select(page):
    from PyQt6.QtWidgets import QTableWidgetItem

    page.table.insertRow(0)
    page.table.setItem(0, 0, QTableWidgetItem("probe"))
    page.table.selectRow(0)


def _assays_select(page):
    from PyQt6.QtWidgets import QTableWidgetItem

    page.table.insertRow(0)
    page.table.setItem(0, 0, QTableWidgetItem("probe"))
    page.table.selectRow(0)


def _files_select(page):
    from PyQt6.QtWidgets import QTreeWidgetItem

    item = QTreeWidgetItem(page.file_tree)
    item.setText(0, "probe.txt")
    item.setSelected(True)


def _studies_select(page):
    from PyQt6.QtWidgets import QTreeWidgetItem

    item = QTreeWidgetItem(page.tree)
    item.setText(0, "probe")
    item.setText(1, "Study")
    item.setText(2, "probe")
    item.setSelected(True)


def _images_select(page):
    page.raw_list.addItem("probe.png")
    page.raw_list.setCurrentRow(0)


def _templates_select(page):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QListWidgetItem

    item = QListWidgetItem("probe")
    item.setData(Qt.ItemDataRole.UserRole, {"filename": "probe.json", "data": {"name": "probe"}})
    page.template_list.addItem(item)
    page.template_list.setCurrentRow(0)


def _process_sequence_select(page):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTreeWidgetItem

    item = QTreeWidgetItem(page.tree)
    item.setText(0, "Probe Process")
    item.setData(
        0,
        Qt.ItemDataRole.UserRole,
        {"type": "process", "data": {"name": "Probe", "inputs": [], "outputs": [], "parameters": []}},
    )
    item.setSelected(True)


def _clear_selection(page, view_attr):
    getattr(page, view_attr).clearSelection()


SELECTION_GATED_CASES = [
    (
        "materials",
        ["page.materials.editButton", "page.materials.deleteButton"],
        _materials_select,
        "table",
    ),
    ("assays", ["page.assays.editButton", "page.assays.deleteButton"], _assays_select, "table"),
    ("files", ["page.files.exportButton", "page.files.deleteButton"], _files_select, "file_tree"),
    ("studies", ["page.studies.deleteButton"], _studies_select, "tree"),
    ("images", ["page.images.convertButton"], _images_select, "raw_list"),
    (
        "templates",
        ["page.templates.editButton", "page.templates.exportButton"],
        _templates_select,
        "template_list",
    ),
    (
        "process_sequence",
        [
            "page.process_sequence.removeProcessButton",
            "page.process_sequence.saveButton",
            "page.process_sequence.validateButton",
        ],
        _process_sequence_select,
        "tree",
    ),
]

SELECTION_GATED_IDS = [case[0] for case in SELECTION_GATED_CASES]

STUDY_GATED_CASES = [
    ("materials", "page.materials.addButton"),
    ("assays", "page.assays.addButton"),
    ("images", "page.images.importButton"),
]


class TestSelectionGating:
    """U-11: dependent buttons follow the current selection (or study)."""

    @pytest.mark.parametrize(
        "page_id,button_ids,select_fn,kind",
        SELECTION_GATED_CASES,
        ids=SELECTION_GATED_IDS,
    )
    def test_selection_gating_transitions(
        self, agent, main_window, page_id, button_ids, select_fn, kind
    ):
        """Empty selection -> disabled; selected -> enabled; cleared -> disabled."""
        agent.navigate(page_id)
        page = main_window.pages[page_id]

        for test_id in button_ids:
            state = agent.get_state(test_id)
            assert state["enabled"] is False, f"{test_id} must start disabled"

        select_fn(page)
        for test_id in button_ids:
            state = agent.get_state(test_id)
            assert state["enabled"] is True, f"{test_id} must enable on selection"

        # Model reset / cleared selection re-disables (U-11 acceptance 3).
        _clear_selection(page, kind)
        for test_id in button_ids:
            state = agent.get_state(test_id)
            assert state["enabled"] is False, f"{test_id} must disable on clear"

    @pytest.mark.parametrize(
        "page_id,button_ids,select_fn,kind",
        SELECTION_GATED_CASES,
        ids=SELECTION_GATED_IDS,
    )
    def test_click_disabled_button_is_silent_noop(
        self, main_window, monkeypatch, page_id, button_ids, select_fn, kind
    ):
        """click on a disabled button: no QMessageBox, no crash (U-11 acc. 2)."""
        main_window._navigate_to_page(page_id)
        _forbid_modals(monkeypatch)
        for test_id in button_ids:
            btn = _find(main_window, test_id)
            assert not btn.isEnabled()
            btn.click()  # QAbstractButton.click() is a no-op while disabled
            assert not btn.isEnabled()

    @pytest.mark.parametrize("page_id,test_id", STUDY_GATED_CASES)
    def test_study_gated_add_buttons(self, main_window, page_id, test_id):
        """Add buttons are disabled without a study and enable with one."""
        main_window._navigate_to_page(page_id)
        page = main_window.pages[page_id]
        btn = _find(main_window, test_id)
        assert not btn.isEnabled(), f"{test_id} must require a loaded study"

        main_window.current_investigation = "inv_probe"
        main_window.set_study("study_probe")  # real set_study() -> refresh() wiring
        assert btn.isEnabled(), f"{test_id} must enable once a study is set"

    def test_process_add_button_requires_process_manager(self, main_window):
        """process_sequence Add gates on the study-backed process manager."""
        main_window._navigate_to_page("process_sequence")
        page = main_window.pages["process_sequence"]
        btn = _find(main_window, "page.process_sequence.addProcessButton")
        assert not btn.isEnabled()
        page.process_manager = object()  # stand-in for ProcessSequenceManager
        page._update_action_states()
        assert btn.isEnabled()


class TestSettingsFooterAndSaveFlow:
    """U-07: fixed footer, non-modal save, non-modal restart UX."""

    def test_save_reset_live_outside_scroll_area_and_visible_at_minimum(
        self, make_settings_window
    ):
        """Footer geometry (U-07 acceptance 1): no scrolling to reach Save."""
        window, _config_path = make_settings_window()
        window._navigate_to_page("settings")
        page = window.pages["settings"]
        window.resize(window.minimumSize())
        _process_events()

        window_rect = window.rect()
        for test_id in ("page.settings.saveButton", "page.settings.resetButton"):
            btn = _find(window, test_id)
            # Outside the scroll area (fixed footer), always visible.
            assert not page.scroll_area.isAncestorOf(btn)
            assert btn.isVisible()
            top_left = btn.mapTo(window, btn.rect().topLeft())
            bottom_right = btn.mapTo(window, btn.rect().bottomRight())
            assert window_rect.contains(top_left) and window_rect.contains(bottom_right), (
                f"{test_id} must be inside the visible window at its minimum size"
            )

    def test_save_click_is_prompt_and_modal_free(self, make_settings_window, monkeypatch):
        """click on Save returns promptly and opens no modal (U-07 acc. 4)."""
        window, config_path = make_settings_window()
        window._navigate_to_page("settings")
        page = window.pages["settings"]
        new_value = not page.validate_on_save_check.isChecked()
        page.validate_on_save_check.setChecked(new_value)

        _forbid_modals(monkeypatch)
        _find(window, "page.settings.saveButton").click()

        assert "saved" in window.status_bar.status_label.text().lower()
        assert json.loads(config_path.read_text(encoding="utf-8"))["validation"][
            "validate_on_save"
        ] is new_value
        assert page._restart_required is False
        assert _find(window, "page.settings.restartButton").isVisible() is False

    def test_restart_flag_only_for_startup_settings(self, make_settings_window, monkeypatch):
        """Restart-flag semantics per field (U-07 audit, acceptance 2)."""
        window, _config_path = make_settings_window()
        window._navigate_to_page("settings")
        page = window.pages["settings"]
        restart_hint = _find(window, "page.settings.restartHintLabel")
        restart_btn = _find(window, "page.settings.restartButton")
        assert not restart_hint.isVisible() and not restart_btn.isVisible()

        # Cheap settings apply live: no restart flag, no hint, no button.
        # The app-wide QSS application is stubbed: session-global styling is
        # out of scope here and would leak into later tests' layout metrics.
        applied_themes = []
        monkeypatch.setattr(window.app, "set_theme", lambda t: applied_themes.append(t))
        original_theme = page.theme_combo.currentText()
        page.theme_combo.setCurrentText("dark" if original_theme == "light" else "light")
        assert applied_themes, "theme combo must apply the theme live"
        page.theme_combo.setCurrentText(original_theme)
        page.font_size_spin.setValue(page.font_size_spin.value() + 1)
        page.autosave_interval_spin.setValue(page.autosave_interval_spin.value() + 10)
        page.window_width_spin.setValue(page.window_width_spin.value() + 1)

        assert page._restart_required is False
        assert not restart_hint.isVisible() and not restart_btn.isVisible()

        # Save: plain success message, still no restart prompt/hint.
        _forbid_modals(monkeypatch)
        _find(window, "page.settings.saveButton").click()
        assert window.status_bar.status_label.text() == "Settings saved!"
        assert not restart_btn.isVisible()

        # Startup-read settings flag restart: hint + Restart Now appear.
        page.templates_root_edit.setText("templates_probe")
        assert page._restart_required is True
        assert restart_hint.isVisible() and restart_btn.isVisible()

        _find(window, "page.settings.saveButton").click()
        assert window.status_bar.status_label.text() == (
            "Settings saved — restart to apply directory/URL changes"
        )
        assert restart_btn.isVisible()  # restart still pending after Save

    def test_url_fields_also_flag_restart(self, make_settings_window):
        """URL config is startup-baked into exports -- flagged like dirs."""
        window, _config_path = make_settings_window()
        window._navigate_to_page("settings")
        page = window.pages["settings"]
        assert page._restart_required is False
        page.study_url_template_edit.setText("{base_url}/{study_id}")
        assert page._restart_required is True

    def test_restart_now_queues_shutdown_and_never_sys_exits(
        self, make_settings_window, monkeypatch, qtbot
    ):
        """Restart Now schedules a queued close+quit (U-07 acceptance 3)."""
        window, _config_path = make_settings_window()
        window._navigate_to_page("settings")
        page = window.pages["settings"]
        page.templates_root_edit.setText("templates_probe")

        calls = []
        monkeypatch.setattr(window, "close", lambda: calls.append("close"))
        from PyQt6.QtWidgets import QApplication

        monkeypatch.setattr(QApplication, "quit", staticmethod(lambda: calls.append("quit")))

        _forbid_modals(monkeypatch)
        _find(window, "page.settings.restartButton").click()
        # Shutdown is queued (QTimer.singleShot(0, ...)), not inline in the slot.
        assert calls == []
        qtbot.wait(10)  # let the queued call run
        assert calls == ["close", "quit"]  # no SystemExit, no sys.exit()

        source = SETTINGS_PAGE_PY.read_text(encoding="utf-8")
        assert "sys.exit(" not in source, "settings.py must not call sys.exit()"
        assert "QMessageBox.question" not in source.split("def _on_save_settings")[1].split(
            "def _validate_settings"
        )[0], "the save path must not open a question dialog"

    def test_auto_save_message_is_honest(self, make_settings_window):
        """U-07 freebie: the tick never claims 'Auto-saved' for a no-op save."""
        window, _config_path = make_settings_window()
        window.current_study = "study_probe"  # arm auto-save without filesystem

        window._navigate_to_page("materials")
        window._auto_save()
        assert window.status_bar.status_label.text() == "Auto-saved"  # data page unchanged

        window._navigate_to_page("settings")
        window._auto_save()
        assert window.status_bar.status_label.text() == (
            "Auto-save skipped (this page saves manually)"
        )


class TestNoHorizontalScroll:
    """U-08: pages fit the viewport; no horizontal scrollbar anywhere."""

    @pytest.fixture(autouse=True)
    def _theme_qss(self):
        """Run under the shipped light QSS (the real boot state).

        Theme stylesheets change widget metrics (button padding, fonts),
        so the fit check must include them -- and must not leak the QSS
        into later tests.
        """
        from PyQt6.QtWidgets import QApplication

        styles = REPO_ROOT / "gui" / "resources" / "styles"
        app = QApplication.instance()
        previous = app.styleSheet()
        app.setStyleSheet((styles / "light.qss").read_text(encoding="utf-8"))
        yield
        app.setStyleSheet(previous)

    @pytest.mark.parametrize("page_id", PAGE_IDS)
    def test_no_horizontal_scrollbar_at_default_window_size(self, main_window, page_id):
        main_window._navigate_to_page(page_id)
        _process_events()
        page = main_window.pages[page_id]
        assert page.scroll_area.horizontalScrollBar().maximum() == 0, (
            f"{page_id} forces a horizontal scrollbar at the default window size"
        )

    @pytest.mark.parametrize("page_id", PAGE_IDS)
    def test_no_horizontal_scrollbar_at_938_content_width(self, main_window, page_id):
        """Plan acceptance 1: 938px content width (the sweep's viewport)."""
        sidebar_w = main_window.sidebar.width()
        main_window.setMinimumSize(0, 0)  # test-only: reach the plan's probe width
        main_window.resize(938 + sidebar_w, 800)
        _process_events()
        assert main_window.content_stack.width() == 938

        main_window._navigate_to_page(page_id)
        _process_events()
        page = main_window.pages[page_id]
        assert page.scroll_area.horizontalScrollBar().maximum() == 0, (
            f"{page_id} forces a horizontal scrollbar at 938px content width"
        )

    def test_materials_headers_fit_their_text(self, main_window):
        """U-08 acceptance 2: full header text (or clean ellipsis), no cuts."""
        from PyQt6.QtCore import Qt

        main_window._navigate_to_page("materials")
        _process_events()
        table = main_window.pages["materials"].table
        header = table.horizontalHeader()

        assert header.textElideMode() == Qt.TextElideMode.ElideRight
        labels = ["Name", "Type", "ID", "Characteristics", "Derives From"]
        fm = header.fontMetrics()
        # Content columns size to their content: the full header text fits.
        for col in range(4):
            assert header.sectionSize(col) >= fm.horizontalAdvance(labels[col]), (
                f"column {col} header {labels[col]!r} is cut mid-word"
            )


class TestStatusBarLayout:
    """U-10: the status-bar children never geometrically overlap."""

    STATUS_IDS = [
        "statusBar.messageLabel",
        "statusBar.progressBar",
        "statusBar.investigationLabel",
        "statusBar.studyLabel",
    ]

    def _global_rects(self, main_window):
        from PyQt6.QtCore import QPoint, QRect

        rects = {}
        for test_id in self.STATUS_IDS:
            widget = _find(main_window, test_id)
            top_left = widget.mapToGlobal(QPoint(0, 0))
            rects[test_id] = QRect(top_left.x(), top_left.y(), widget.width(), widget.height())
        return rects

    def _assert_disjoint(self, rects):
        ids = list(rects)
        for i, first in enumerate(ids):
            for second in ids[i + 1 :]:
                assert not rects[first].intersects(rects[second]), (
                    f"{first} {rects[first]} overlaps {second} {rects[second]}"
                )

    def test_no_overlap_with_progress_hidden(self, main_window):
        """Hidden progress bar must not overlap any sibling (U-10 acc.)."""
        _process_events()
        self._assert_disjoint(self._global_rects(main_window))

    def test_no_overlap_with_progress_shown_and_hidden_again(self, main_window):
        """Disjointness holds while shown and after the bar hides (U-10 acc.)."""
        main_window.status_bar.show_progress("Working")
        _process_events()
        rects = self._global_rects(main_window)
        self._assert_disjoint(rects)
        bar = rects["statusBar.progressBar"]
        assert bar.width() <= 200 and bar.height() <= 16

        main_window.status_bar._hide_progress()
        _process_events()
        self._assert_disjoint(self._global_rects(main_window))


class TestEmptyStatePlaceholders:
    """U-13: Images/Templates empty lists show muted placeholders."""

    def test_images_placeholders_toggle_with_population(self, main_window):
        page = main_window.pages["images"]
        main_window._navigate_to_page("images")
        _process_events()

        raw_placeholder = _find(main_window, "page.images.rawListPlaceholder")
        processed_placeholder = _find(main_window, "page.images.processedListPlaceholder")
        assert raw_placeholder.isVisible(), "raw placeholder must show on empty list"
        assert processed_placeholder.isVisible(), "processed placeholder must show on empty list"

        # Populate via the real refresh() path against the isolated study dir.
        main_window.current_investigation = "inv_probe"
        main_window.current_study = "study_probe"
        dm = main_window.get_directory_manager()
        study_path = dm.get_study_path("inv_probe", "study_probe")
        raw_dir = study_path / "files" / "original"
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / "probe.png").write_bytes(b"probe")
        tiff_dir = study_path / "processed_data" / "tiff"
        tiff_dir.mkdir(parents=True, exist_ok=True)
        (tiff_dir / "probe.tif").write_bytes(b"probe")

        page.refresh()
        _process_events()
        assert page.raw_list.count() == 1 and page.processed_list.count() == 1
        assert not raw_placeholder.isVisible(), "placeholder must hide once populated"
        assert not processed_placeholder.isVisible(), "placeholder must hide once populated"

        # Lists empty again -> placeholders return.
        (raw_dir / "probe.png").unlink()
        (tiff_dir / "probe.tif").unlink()
        page.refresh()
        _process_events()
        assert raw_placeholder.isVisible()
        assert processed_placeholder.isVisible()

    def test_templates_placeholders_toggle_with_population(
        self, main_window, monkeypatch, tmp_path
    ):
        page = main_window.pages["templates"]
        monkeypatch.setattr(main_window, "get_templates_root", lambda: tmp_path / "tpl")
        main_window._navigate_to_page("templates")

        list_placeholder = _find(main_window, "page.templates.listPlaceholder")
        preview_placeholder = _find(main_window, "page.templates.previewPlaceholder")

        # Empty root -> both placeholders show.
        page._load_templates("assay")
        _process_events()
        assert page.template_list.count() == 0
        assert list_placeholder.isVisible(), "list placeholder must show on empty list"
        assert preview_placeholder.isVisible(), "preview placeholder must show with no selection"

        # Populate via the real _load_templates() path -> placeholder hides.
        template_dir = tmp_path / "tpl" / "assay_templates"
        template_dir.mkdir(parents=True)
        (template_dir / "probe.json").write_text('{"name": "probe"}', encoding="utf-8")
        page._load_templates("assay")
        _process_events()
        assert page.template_list.count() == 1
        assert not list_placeholder.isVisible(), "placeholder must hide once populated"

        # Selecting shows the preview content, not the placeholder.
        page.template_list.setCurrentRow(0)
        _process_events()
        assert not preview_placeholder.isVisible()
        assert page.preview_label.isVisible()

        # An empty type again -> both placeholders return.
        page._load_templates("protocol")
        _process_events()
        assert list_placeholder.isVisible()
        assert preview_placeholder.isVisible()


class TestButtonSemantics:
    """U-14: destructive actions are DangerButtons; disabled state is styled."""

    DANGER_BUTTON_IDS = [
        "page.studies.deleteButton",
        "page.materials.deleteButton",
        "page.assays.deleteButton",
        "page.files.deleteButton",
        "page.process_sequence.removeProcessButton",
        "page.settings.resetButton",
    ]

    @pytest.mark.parametrize("test_id", DANGER_BUTTON_IDS)
    def test_destructive_buttons_use_danger_button(self, main_window, test_id):
        btn = _find(main_window, test_id)
        assert type(btn).__name__ == "DangerButton", f"{test_id} must be a DangerButton"
        assert btn.objectName() == "dangerButton"

    @pytest.mark.parametrize("theme", ["dark", "light"])
    def test_disabled_rules_for_primary_and_danger_in_qss(self, theme):
        """Disabled styled buttons must gray out in both themes (U-14 note)."""
        qss = (REPO_ROOT / "gui" / "resources" / "styles" / f"{theme}.qss").read_text(
            encoding="utf-8"
        )
        assert "QPushButton#primaryButton:disabled" in qss, theme
        assert "QPushButton#dangerButton:disabled" in qss, theme


class TestSettingsFormPolish:
    """U-15(b): uniform checkbox rows and aligned form columns."""

    CHECKBOX_IDS = [
        "page.settings.backupOnSaveCheck",
        "page.settings.validateOnSaveCheck",
        "page.settings.validateRequiredFieldsCheck",
        "page.settings.validateOntologyTermsCheck",
        "page.settings.validateUnitsCheck",
        "page.settings.validateDateFormatsCheck",
        "page.settings.warnOnMissingMetadataCheck",
        "page.settings.includeRawDataCheck",
        "page.settings.includeProcessedDataCheck",
        "page.settings.includeAssayDataCheck",
        "page.settings.includeProtocolsCheck",
        "page.settings.enableVersionControlCheck",
        "page.settings.autoVersionOnSaveCheck",
        "page.settings.compressOldVersionsCheck",
    ]

    def test_checkbox_rows_are_uniform_and_left_aligned(self, make_settings_window):
        window, _config_path = make_settings_window()
        window._navigate_to_page("settings")
        _process_events()
        for test_id in self.CHECKBOX_IDS:
            checkbox = _find(window, test_id)
            row = checkbox.parentWidget()
            assert row is not checkbox, f"{test_id} must sit in a row wrapper"
            assert row.height() == 22, f"{test_id} row height {row.height()} != 22"
            assert checkbox.pos().x() == 0, f"{test_id} must be left-aligned in its row"

    def test_field_columns_line_up_across_sections(self, make_settings_window):
        window, _config_path = make_settings_window()
        window._navigate_to_page("settings")
        _process_events()
        # First field of each of the eight sections shares one column x.
        probe_ids = [
            "page.settings.themeCombo",
            "page.settings.windowWidthSpin",
            "page.settings.autoSaveIntervalSpin",
            "page.settings.basePathPicker",
            "page.settings.baseUrlField",
            "page.settings.validateOnSaveCheck",
            "page.settings.exportFormatCombo",
            "page.settings.versionPrefixField",
        ]
        xs = set()
        for test_id in probe_ids:
            widget = _find(window, test_id)
            field = widget.parentWidget() if test_id.endswith("Check") else widget
            xs.add(field.mapTo(window, field.rect().topLeft()).x())
        assert len(xs) == 1, f"settings field columns misaligned: x={sorted(xs)}"

    def test_form_layouts_have_pinned_polish_settings(self, make_settings_window):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QFormLayout

        window, _config_path = make_settings_window()
        page = window.pages["settings"]
        assert len(page._form_layouts) == 8
        for form in page._form_layouts:
            assert form.labelAlignment() == Qt.AlignmentFlag.AlignLeft
            assert form.formAlignment() == Qt.AlignmentFlag.AlignLeft
            assert (
                form.fieldGrowthPolicy()
                == QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            )
