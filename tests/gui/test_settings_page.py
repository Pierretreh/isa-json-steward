"""Settings-page data-safety tests (U-02 + U-12).

Implements the acceptance cases from ``plans/gui-usability-fixes.md``:

* close-with-modifications leaves the settings config byte-identical
  (no implicit Save at close and no blocking restart modal at shutdown);
* the auto-save tick never rewrites the config while the settings page is
  current (``SettingsPage.save_data()`` is a no-op);
* ``ISA_STEWARD_CONFIG_PATH`` isolates reads/writes: the explicit Save
  button persists to the injected file only, preserving unmanaged
  top-level sections such as ``application``;
* a failed/corrupt config load blocks Save (status-bar error, file left
  untouched) so a later Save can never drop the ``application`` section
  (U-12 config-loss edge), and the failure is logged via the project
  logger;
* a template-load failure emits a WARNING record through the
  ``JsonlEventHandler`` bridge into the JSONL GUI-event stream
  (U-12 acceptance criterion 2).

Every test isolates the config through ``ISA_STEWARD_CONFIG_PATH`` (pointed
at ``tmp_path``), so the repo ``config/settings.json`` is never at risk.
"""

import json
import logging
from pathlib import Path

import pytest

pytestmark = pytest.mark.gui

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_SETTINGS = REPO_ROOT / "config" / "settings.json"


@pytest.fixture
def make_settings_window(qtbot, stub_app, monkeypatch, tmp_path):
    """Factory building a ``MainWindow`` bound to an isolated settings config.

    The config content is copied to ``tmp_path/settings.json`` and
    ``ISA_STEWARD_CONFIG_PATH`` is pointed at it BEFORE the window is
    constructed (``SettingsPage`` reads the config at construction and again
    in ``on_enter()``).
    """
    from gui.main_window import MainWindow

    def _make(content=None):
        config_path = tmp_path / "settings.json"
        if content is None:
            content = REPO_SETTINGS.read_text(encoding="utf-8")
        config_path.write_text(content, encoding="utf-8")
        monkeypatch.setenv("ISA_STEWARD_CONFIG_PATH", str(config_path))
        window = MainWindow(stub_app)
        qtbot.addWidget(window)
        window.show()
        return window, config_path

    return _make


def _forbid_modals(monkeypatch):
    """Turn every ``QMessageBox`` entry point into a hard test failure.

    U-02's contract: neither the close path nor the blocked-save path may
    open a modal (they used to block forever under ``QT_QPA_PLATFORM=offscreen``).
    """
    from PyQt6.QtWidgets import QMessageBox

    def _boom(*args, **kwargs):
        raise AssertionError("unexpected modal QMessageBox")

    for name in ("question", "critical", "warning", "information"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(_boom))


class TestSettingsCloseSafety:
    """U-02: closing the window must never rewrite or lose settings."""

    def test_close_with_modifications_leaves_config_untouched(
        self, make_settings_window, monkeypatch
    ):
        """Close is not an implicit Save: the config is byte-identical."""
        window, config_path = make_settings_window()
        config_before = config_path.read_bytes()
        repo_before = REPO_SETTINGS.read_bytes()

        window._navigate_to_page("settings")
        page = window.pages["settings"]
        # Mutate fields -- including one that flags "restart required" (U-07
        # keeps the flag only on startup-read settings, e.g. directories).
        page.templates_root_edit.setText("templates_probe")
        assert page._restart_required
        page.validate_on_save_check.setChecked(not page.validate_on_save_check.isChecked())

        _forbid_modals(monkeypatch)
        window.close()  # closeEvent -> save_data() is a no-op (U-02)

        assert config_path.read_bytes() == config_before
        assert REPO_SETTINGS.read_bytes() == repo_before

    def test_auto_save_tick_never_rewrites_config(self, make_settings_window, monkeypatch):
        """A timer tick with the settings page current writes nothing."""
        window, config_path = make_settings_window()
        config_before = config_path.read_bytes()

        window._navigate_to_page("settings")
        page = window.pages["settings"]
        page.window_width_spin.setValue(page.window_width_spin.value() + 1)

        # Auto-save only runs when a study is loaded; arm that condition
        # without touching the filesystem (set_study() would load study JSON).
        window.current_study = "study_autosave_probe"
        assert window.auto_save_timer.isActive()  # timer armed

        _forbid_modals(monkeypatch)
        window._auto_save()  # the exact slot the timer tick invokes

        # U-07: the message is honest -- the settings page's save_data() is
        # a no-op (U-02), so the tick must not claim "Auto-saved".
        assert window.status_bar.status_label.text() == (
            "Auto-save skipped (this page saves manually)"
        )
        assert config_path.read_bytes() == config_before


class TestSettingsExplicitSave:
    """U-02 acceptance: the Save button is the only persistence path."""

    def test_explicit_save_persists_to_injected_path_only(self, make_settings_window):
        window, config_path = make_settings_window()
        repo_before = REPO_SETTINGS.read_bytes()

        window._navigate_to_page("settings")
        page = window.pages["settings"]
        # Mutate fields whose change does NOT flag "restart required"
        # (U-07 keeps the flag only on startup-read settings).
        new_validate_on_save = not page.validate_on_save_check.isChecked()
        page.validate_on_save_check.setChecked(new_validate_on_save)
        page.export_format_combo.setCurrentText("CSV")
        assert not page._restart_required

        from gui.agent_tools.ids import find_by_test_id

        save_btn = find_by_test_id(window, "page.settings.saveButton")
        assert save_btn is not None
        save_btn.click()

        saved = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved["validation"]["validate_on_save"] is new_validate_on_save
        assert saved["export"]["default_format"] == "CSV"
        # Unmanaged top-level sections survive the rewrite (deep-merge mindset).
        assert "application" in saved
        # The injected path only: the repo config is never touched.
        assert REPO_SETTINGS.read_bytes() == repo_before
        # Success message via the status bar (unchanged contract).
        assert "saved" in window.status_bar.status_label.text().lower()
        # Appearance settings persist through QSettings (unchanged contract).
        assert window.app.settings.value("gui/theme") == page.theme_combo.currentText()
        assert window.app.settings.value("gui/font_size") == page.font_size_spin.value()


class TestSettingsConfigLoadFailure:
    """U-12 config-loss edge: a failed load must block Save."""

    def test_load_failure_at_construction_sets_fail_flag(self, make_settings_window):
        window, _config_path = make_settings_window(content="{not valid json")
        page = window.pages["settings"]
        assert page._config_load_failed is True
        assert page._raw_config == {}

    def test_corrupt_config_blocks_save_and_logs(self, make_settings_window, monkeypatch, caplog):
        corrupt = '{"gui": '  # truncated JSON: json.load raises
        window, config_path = make_settings_window(content=corrupt)
        config_before = config_path.read_bytes()

        with caplog.at_level(logging.ERROR, logger="gui.pages.settings"):
            window._navigate_to_page("settings")  # on_enter() reloads -> fails
        page = window.pages["settings"]
        assert page._config_load_failed is True
        assert any("Error loading config" in rec.getMessage() for rec in caplog.records)

        page.window_width_spin.setValue(page.window_width_spin.value() + 1)

        _forbid_modals(monkeypatch)
        from gui.agent_tools.ids import find_by_test_id

        save_btn = find_by_test_id(window, "page.settings.saveButton")
        assert save_btn is not None
        save_btn.click()  # must refuse: writing now would drop 'application'

        # Refused with a status-bar error; the file is left untouched.
        assert "not saved" in window.status_bar.status_label.text().lower()
        assert config_path.read_bytes() == config_before


class TestTemplateLoadLogging:
    """U-12: resource-load failures log through the project logger."""

    def test_template_load_failure_flows_warning_into_event_log(
        self, make_settings_window, monkeypatch, tmp_path
    ):
        """A bad template file emits a WARNING row via the JsonlEventHandler
        bridge (U-12 acceptance: WARNING record in the JSONL GUI-event
        stream instead of a bare stdout line).
        """
        from gui.agent_tools.events import GuiEventLogger
        from utils.logging_config import JsonlEventHandler

        window, _config_path = make_settings_window()

        # Bad template file in an isolated templates root.
        templates_root = tmp_path / "templates"
        (templates_root / "assay_templates").mkdir(parents=True)
        (templates_root / "assay_templates" / "bad.json").write_text(
            "{not valid json", encoding="utf-8"
        )
        monkeypatch.setattr(window, "get_templates_root", lambda: templates_root)

        # Wire the JSONL bridge to an isolated event stream (the same wiring
        # utils.logging_config.setup_gui_event_log installs on the root).
        event_logger = GuiEventLogger(tmp_path / "events.jsonl")
        handler = JsonlEventHandler(event_logger)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        try:
            window.pages["templates"]._load_templates("assay")
        finally:
            root_logger.removeHandler(handler)
            event_logger.close()

        rows = [
            json.loads(line)
            for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        warnings = [
            row
            for row in rows
            if row["kind"] == "log" and row["detail"].get("level") == "WARNING"
        ]
        assert warnings, "expected a WARNING log row for the failed template load"
        assert "Error loading template" in warnings[0]["detail"]["message"]
        assert warnings[0]["detail"]["logger"] == "gui.pages.templates"
