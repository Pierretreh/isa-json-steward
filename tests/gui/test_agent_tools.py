"""Agent-toolkit smoke tests (P0-4) for the ISA-JSON Data Steward GUI.

Covers the acceptance criteria from plans/agent-gui-observability.md
section 5 for the dump, screenshot, and CLI halves of the toolkit:

- ``dump_widget_tree()`` returns valid JSON with the schema id, a text form
  listing every testId, root-relative global geometry (window corner 0,0),
  and honors ``include_hidden``.
- ``gui_screenshot()`` writes a PNG that opens with Pillow, capped at
  ``max_edge`` pixels, for window / page / single-widget targets.
- ``python -m gui.agent_tools ...`` exits 0 and prints JSON with artifact
  paths; ``pages`` lists all 10 page ids.

All checks run under ``QT_QPA_PLATFORM=offscreen``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QWidget

    PYQT6_AVAILABLE = True
except (ImportError, OSError):
    PYQT6_AVAILABLE = False

pytestmark = pytest.mark.gui

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def main_window(qapp):
    """Build a real MainWindow with the shared lightweight app stub."""
    from gui.main_window import MainWindow
    from tests.gui.conftest import StubApp

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


class TestDumpWidgetTree:
    """P0-4: widget-tree dump (schema isa-gui/widget-tree/1)."""

    def test_valid_json_with_schema_id(self, main_window):
        from gui.agent_tools.dump import WIDGET_TREE_SCHEMA, dump_widget_tree

        tree = dump_widget_tree(main_window)
        assert tree["schema"] == WIDGET_TREE_SCHEMA == "isa-gui/widget-tree/1"
        # Round-trips through a real JSON encoding.
        assert json.loads(json.dumps(tree, default=str))["root"]["class"]

    def test_root_geometry_is_window_corner(self, main_window):
        """Geometry is in one global space anchored at the root corner."""
        from gui.agent_tools.dump import dump_widget_tree

        root = dump_widget_tree(main_window)["root"]
        assert root["geometry"]["x"] == 0
        assert root["geometry"]["y"] == 0
        assert root["geometry"]["width"] == main_window.width()
        assert root["geometry"]["height"] == main_window.height()

    def test_hidden_widget_geometry_is_zeroed(self, main_window):
        """N5: hidden nodes dump the zero rect; visible geometry is unchanged."""
        from gui.agent_tools.dump import dump_widget_tree

        def find(node, test_id):
            if node.get("testId") == test_id:
                return node
            for child in node.get("children", []):
                found = find(child, test_id)
                if found is not None:
                    return found
            return None

        zero = {"x": 0, "y": 0, "width": 0, "height": 0}

        tree = dump_widget_tree(main_window)
        bar = find(tree["root"], "statusBar.progressBar")
        assert bar is not None
        assert bar["visible"] is False, "progress bar is hidden at rest (U-10)"
        assert bar["geometry"] == zero, "hidden widgets must dump the zeroed rect (N5)"

        # Visible widgets keep real geometry; the schema key set is unchanged.
        assert tree["schema"] == "isa-gui/widget-tree/1"
        assert tree["root"]["geometry"]["width"] == main_window.width()

        # Shown -> real rect again; hidden -> zeroed again.
        main_window.status_bar.show_progress("Working")
        QApplication.processEvents()
        bar = find(dump_widget_tree(main_window)["root"], "statusBar.progressBar")
        assert bar["visible"] is True
        assert bar["geometry"]["width"] > 0 and bar["geometry"]["height"] > 0

        main_window.status_bar._hide_progress()
        QApplication.processEvents()
        bar = find(dump_widget_tree(main_window)["root"], "statusBar.progressBar")
        assert bar["visible"] is False
        assert bar["geometry"] == zero

    def test_node_schema_fields(self, main_window):
        from gui.agent_tools.dump import dump_widget_tree

        node = dump_widget_tree(main_window)["root"]
        for key in (
            "testId",
            "class",
            "objectName",
            "accessibleName",
            "text",
            "toolTip",
            "visible",
            "enabled",
            "geometry",
            "properties",
            "children",
        ):
            assert key in node, f"schema field {key!r} missing"
        assert node["testId"] == "window.main"
        assert node["class"] == "MainWindow"
        # "checked" appears only for checkable widgets.
        assert "checked" not in node

    def test_dynamic_properties_are_reported(self, main_window):
        """Sidebar nav buttons expose their pageId dynamic property."""
        from gui.agent_tools.dump import dump_widget_tree

        def walk(node):
            yield node
            for child in node.get("children", []):
                yield from walk(child)

        nav = [
            n
            for n in walk(dump_widget_tree(main_window)["root"])
            if n.get("testId") == "sidebar.navButton.materials"
        ]
        assert len(nav) == 1
        assert nav[0]["properties"].get("pageId") == "materials"

    def test_text_form_lists_every_test_id(self, main_window):
        from gui.agent_tools.dump import dump_widget_tree, widget_tree_to_text

        tree = dump_widget_tree(main_window)
        text = widget_tree_to_text(tree)

        def walk(node):
            yield node
            for child in node.get("children", []):
                yield from walk(child)

        ids = [n["testId"] for n in walk(tree["root"]) if n.get("testId")]
        assert ids, "expected tagged widgets in the dump"
        for test_id in ids:
            assert test_id in text, f"{test_id!r} missing from the text form"

    def test_include_hidden_flag(self, main_window):
        from gui.agent_tools.dump import dump_widget_tree

        hidden = QWidget(main_window)
        hidden.setObjectName("probeHidden")
        hidden.hide()
        try:
            full = dump_widget_tree(main_window, include_hidden=True)
            pruned = dump_widget_tree(main_window, include_hidden=False)

            def has_probe(node):
                if node["objectName"] == "probeHidden":
                    return True
                return any(has_probe(c) for c in node.get("children", []))

            assert has_probe(full["root"])
            assert not has_probe(pruned["root"])
        finally:
            hidden.deleteLater()

    def test_max_depth(self, main_window):
        from gui.agent_tools.dump import dump_widget_tree

        def depth(node):
            kids = node.get("children", [])
            return 1 + max((depth(c) for c in kids), default=0)

        assert depth(dump_widget_tree(main_window, max_depth=1)["root"]) == 1
        assert depth(dump_widget_tree(main_window, max_depth=2)["root"]) == 2

    def test_text_form_of_empty_tree(self):
        from gui.agent_tools.dump import widget_tree_to_text

        assert widget_tree_to_text({"root": None}) == ""


class TestGuiScreenshot:
    """P0-4: screenshot capture (PNG to reports/, <= max_edge px)."""

    def test_window_capture(self, main_window, tmp_path):
        from gui.agent_tools.screenshot import gui_screenshot

        result = gui_screenshot(main_window, out_dir=tmp_path, name="window_shot")
        assert result.path.exists()
        assert result.path.suffix == ".png"
        assert result.marks is None  # marks are populated only with annotate=True

        from PIL import Image

        with Image.open(result.path) as img:
            assert img.format == "PNG"
            assert (img.width, img.height) == (result.width, result.height)
            assert max(img.width, img.height) <= 2048

    def test_page_and_widget_targets(self, main_window, tmp_path):
        from gui.agent_tools.screenshot import gui_screenshot

        page = main_window.pages["materials"]
        page_result = gui_screenshot(page, out_dir=tmp_path, name="page_shot")
        assert page_result.path.exists()

        button = main_window.sidebar.button_group.buttons()[0]
        widget_result = gui_screenshot(button, out_dir=tmp_path, name="widget_shot")
        assert widget_result.path.exists()
        assert widget_result.width == button.width()

    def test_max_edge_downscales(self, main_window, tmp_path):
        from gui.agent_tools.screenshot import gui_screenshot

        result = gui_screenshot(main_window, out_dir=tmp_path, name="tiny", max_edge=256)
        assert max(result.width, result.height) <= 256

    def test_default_out_dir_is_reports(self, main_window, tmp_path, monkeypatch):
        """Without out_dir, PNGs land in reports/ relative to cwd."""
        from gui.agent_tools.screenshot import gui_screenshot

        monkeypatch.chdir(tmp_path)
        result = gui_screenshot(main_window, name="default_dir")
        assert result.path.parent == (tmp_path / "reports").resolve()
        assert result.path.exists()

    def test_annotate_smoke(self, main_window, tmp_path):
        """P1-2: annotate=True draws marks and writes the .legend.json sidecar."""
        from gui.agent_tools.annotate import legend_path_for
        from gui.agent_tools.screenshot import gui_screenshot

        plain = gui_screenshot(main_window, out_dir=tmp_path, name="plain")
        assert plain.marks is None

        result = gui_screenshot(main_window, out_dir=tmp_path, name="annotated", annotate=True)
        assert result.marks is not None
        assert result.marks, "expected at least the window/main marks"
        assert max(result.width, result.height) <= 2048

        legend = legend_path_for(result.path)
        assert legend.exists()
        data = json.loads(legend.read_text(encoding="utf-8"))
        assert [m["index"] for m in data] == [m.index for m in result.marks]
        assert [m["test_id"] for m in data] == [m.test_id for m in result.marks]


class TestVisualSmoke:
    """P0-2 visual smoke: pages render with a non-default background."""

    def test_each_page_center_differs_from_palette_gray(self, main_window, tmp_path):
        """With a theme QSS applied, every page shows a non-default background.

        This is the P0-2 visual smoke: it fails if the ``QWidget#contentPage``
        selector stops matching after a rename.

        The plan's check is "pixel sample at page center differs from raw
        palette gray".  In a full-page render the center pixel is often covered
        by child widgets that paint palette colors of their own (splitter
        handles, scroll-view panes), so the smoke screenshots each page twice:
        once as-is (capture must work on every page), and once with the page's
        child widgets hidden so the center pixel shows exactly the background
        the ``#contentPage`` rule paints.
        """
        from PIL import Image

        from gui.agent_tools.screenshot import gui_screenshot

        styles = REPO_ROOT / "gui" / "resources" / "styles"
        qss = (styles / "dark.qss").read_text(encoding="utf-8")

        palette_gray = main_window.palette().window().color()
        gray = (palette_gray.red(), palette_gray.green(), palette_gray.blue())

        QApplication.instance().setStyleSheet(qss)
        try:
            for page_id, page in main_window.pages.items():
                main_window.content_stack.setCurrentWidget(page)
                QApplication.processEvents()

                # Full-page capture must work for every page.
                assert gui_screenshot(page, out_dir=tmp_path, name=f"smoke_{page_id}")

                # Isolate the page's own background by hiding child widgets,
                # remembering each widget's explicit hide state to restore.
                hidden_state = [(w, w.isHidden()) for w in page.findChildren(QWidget)]
                for w, _ in hidden_state:
                    w.hide()
                QApplication.processEvents()
                bare = gui_screenshot(page, out_dir=tmp_path, name=f"bare_{page_id}")
                for w, was_hidden in hidden_state:
                    w.setVisible(not was_hidden)
                QApplication.processEvents()

                with Image.open(bare.path) as img:
                    center = img.getpixel((img.width // 2, img.height // 2))[:3]
                assert tuple(center) != gray, (
                    f"page {page_id!r} background pixel {center} equals raw palette "
                    f"gray {gray}: the contentPage QSS rule is not applied"
                )
        finally:
            QApplication.instance().setStyleSheet("")


class TestCli:
    """P0-4: python -m gui.agent_tools ... exits 0 with JSON artifact paths."""

    @staticmethod
    def _run(*args, env_extra=None):
        env = dict(os.environ)
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, "-m", "gui.agent_tools", *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
            timeout=300,
        )

    def test_whitespace_polluted_platform_self_heals(self):
        """Regression: cmd.exe `set VAR=value && ...` stores "offscreen ".

        Qt cannot match a platform plugin named ``"offscreen "`` and aborts
        natively (0xC0000409) before any JSON is printed; the toolkit must
        strip the pollution (ensure_offscreen_platform) instead.
        """
        proc = self._run("pages", env_extra={"QT_QPA_PLATFORM": "offscreen "})
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True
        assert payload["pages"]

    def test_pages_lists_all_ten_pages(self):
        proc = self._run("pages")
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True
        assert sorted(payload["pages"]) == [
            "assays",
            "dashboard",
            "files",
            "images",
            "materials",
            "ontology",
            "process_sequence",
            "settings",
            "studies",
            "templates",
        ]
        assert payload["current"] == "dashboard"

    def test_dump_text_prints_artifact_paths(self, tmp_path):
        out_json = tmp_path / "tree.json"
        proc = self._run("dump", "--text", "--out", str(out_json))
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True
        assert payload["schema"] == "isa-gui/widget-tree/1"
        json_path = Path(payload["json_path"])
        text_path = Path(payload["text_path"])
        assert json_path == out_json.resolve()
        assert json_path.exists()
        assert text_path.exists()
        assert json.loads(json_path.read_text(encoding="utf-8"))["schema"]
        assert "window.main" in text_path.read_text(encoding="utf-8")

    def test_screenshot_page_prints_artifact_path(self, tmp_path):
        proc = self._run("screenshot", "--page", "materials", "--out", str(tmp_path))
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True
        shot = Path(payload["path"])
        assert shot.exists()
        assert shot.parent == tmp_path.resolve()
        assert shot.name.startswith("page.materials")
        assert max(payload["width"], payload["height"]) <= 2048

    def test_screenshot_annotate_prints_legend_path(self, tmp_path):
        proc = self._run("screenshot", "--page", "materials", "--annotate", "--out", str(tmp_path))
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True
        assert payload["marks"] >= 1
        legend = Path(payload["legend_path"])
        assert legend.exists()
        data = json.loads(legend.read_text(encoding="utf-8"))
        assert [m["index"] for m in data] == list(range(1, len(data) + 1))

    def test_get_state_round_trip(self):
        proc = self._run("get-state", "sidebar.navButton.materials")
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["state"]["text"] == "Materials"

    def test_unknown_widget_reports_error(self):
        proc = self._run("get-state", "page.dashboard.nope")
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert payload["ok"] is False
        assert "WidgetIdError" in payload["error"]
        assert "known_ids" in payload

    def test_theme_flag_never_rewrites_persisted_theme(self, tmp_path):
        """U-06 acceptance: ``--theme dark`` leaves QSettings ``gui/theme`` untouched.

        The subprocess boots a real ``StewardApp`` whose QSettings org comes
        from ``config/profile.json`` (``project`` field); the parent reads the
        same store before/after and asserts invariance.
        """
        from PyQt6.QtCore import QSettings

        settings = QSettings("ISA-JSON Data Steward", "DataSteward")
        before = settings.value("gui/theme")
        proc = self._run(
            "screenshot", "--page", "dashboard", "--theme", "dark", "--out", str(tmp_path)
        )
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["ok"] is True
        assert settings.value("gui/theme") == before


class TestBootProfile:
    """U-05: the agent boot path performs profile auto-discovery.

    Booting with the synthetic fixture profile must activate it BEFORE the
    application freezes the ``config_loader`` singleton (previously the
    ``profile=`` kwarg was silently dead and the Templates/Ontology pages
    rendered from the wrong profile).
    """

    @staticmethod
    def _copy_profile(tmp_path):
        """Copy the committed synthetic profile to tmp -- never boot against
        the tracked fixture.  (Pre-N6 the boot wrote the template index into
        ``templates_root``; since N6 the scan is in-memory, but the tmp copy
        is kept so no boot-side effect can ever reach the fixture tree.)"""
        import shutil

        src = REPO_ROOT / "tests" / "batch_processing" / "fixtures" / "synthetic_profile"
        dst = tmp_path / "synthetic_profile"
        shutil.copytree(src, dst)
        return dst.resolve()

    def test_env_profile_fills_templates_page(self, qapp, tmp_path, monkeypatch):
        """``ISA_STEWARD_PROFILE`` boots the profile's templates (not empty)."""
        from PyQt6.QtCore import Qt

        from gui.agent_tools.runtime import HeadlessGui
        from utils.config_loader import get_profile

        profile_dir = self._copy_profile(tmp_path)
        monkeypatch.setenv("ISA_STEWARD_PROFILE", str(profile_dir))

        gui = HeadlessGui()  # theme=None: keep the configured theme (U-06)
        gui.start()
        try:
            assert get_profile().get_profile_root() == profile_dir
            assert gui.window.get_templates_root() == profile_dir / "templates"

            gui.navigate("templates")
            page = gui.window.pages["templates"]
            gui.find("page.templates.typeCombo").setCurrentText("Protocol Templates")
            gui.process_events(50)

            filenames = []
            for i in range(page.template_list.count()):
                data = page.template_list.item(i).data(Qt.ItemDataRole.UserRole)
                filenames.append(data["filename"])
            assert "sample_dilution_protocol.json" in filenames
        finally:
            gui.shutdown()

    def test_profile_kwarg_wins_with_existing_qapp(self, qapp, tmp_path, monkeypatch):
        """HeadlessGui(profile=...) activates even when a QApplication exists."""
        from gui.agent_tools.runtime import HeadlessGui
        from utils.config_loader import get_profile

        pinned = self._copy_profile(tmp_path)
        decoy = tmp_path / "decoy-profile"
        decoy.mkdir()
        monkeypatch.setenv("ISA_STEWARD_PROFILE", str(decoy))  # pinned kwarg wins

        gui = HeadlessGui(profile=str(pinned))
        gui.start()
        try:
            assert get_profile().get_profile_root() == pinned
        finally:
            gui.shutdown()

    def test_missing_profile_kwarg_is_an_error(self, qapp, tmp_path):
        from gui.agent_tools.runtime import HeadlessGui

        gui = HeadlessGui(profile=str(tmp_path / "nope"))
        with pytest.raises(ValueError, match="profile directory not found"):
            gui.start()

    def test_no_discovery_keeps_default_config(self, qapp, monkeypatch):
        """With nothing discovered, the default core config/ profile is kept.

        (Workspace checkouts may legitimately contain a ``*-profile/`` dir --
        e.g. the gitignored ``domain-profile/`` -- so discovery is stubbed to
        ``None`` rather than assuming absence.)
        """
        import utils.config_loader as config_loader
        from gui.agent_tools.runtime import HeadlessGui
        from utils.config_loader import get_profile

        monkeypatch.delenv("ISA_STEWARD_PROFILE", raising=False)
        monkeypatch.setattr(config_loader, "discover_profile_dir", lambda root: None)
        gui = HeadlessGui()
        gui.start()
        try:
            assert get_profile().get_profile_root() == REPO_ROOT.resolve()
        finally:
            gui.shutdown()

    def test_gui_main_reexports_discover_profile_dir(self):
        """gui/main.py behavior is identical via import (pure relocation)."""
        from gui.main import discover_profile_dir as from_gui
        from utils.config_loader import discover_profile_dir as from_utils

        assert from_gui is from_utils


class TestTemplateIndexBootHygiene:
    """N6: boot must not write template index files into the profile dir.

    ``MainWindow._regenerate_template_index()`` builds the index in memory;
    file output (``template_index.json`` + ``template_list.txt``) is opt-in
    via ``ISA_STEWARD_TEMPLATE_INDEX_WRITE=1``.  The tracked CLI
    ``scripts/generate_template_index.py`` is the explicit write path and
    is unaffected.
    """

    @staticmethod
    def _tree_digest(root):
        """{relative path: sha256} for every file under *root* (byte truth)."""
        import hashlib

        return {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"))
            if p.is_file()
        }

    def test_boot_leaves_profile_dir_byte_identical(self, qapp, tmp_path, monkeypatch, caplog):
        """N6 acceptance 1 + N7: the boot writes nothing into the profile
        dir (before/after digest equal) and logs zero WARNING+ records from
        ``utils.template_index`` for the absent optional subdirs."""
        import logging

        import utils.config_loader as config_loader
        from gui.agent_tools.runtime import HeadlessGui

        profile_dir = TestBootProfile._copy_profile(tmp_path)
        before = self._tree_digest(profile_dir)

        monkeypatch.setenv("ISA_STEWARD_PROFILE", str(profile_dir))
        monkeypatch.delenv("ISA_STEWARD_TEMPLATE_INDEX_WRITE", raising=False)
        # U-05 isolation: snapshot the config_loader singleton so teardown
        # restores whatever profile the suite was running with.
        monkeypatch.setattr(config_loader, "_profile", config_loader._profile)

        with caplog.at_level(logging.DEBUG, logger="utils.template_index"):
            gui = HeadlessGui()  # theme=None: keep the configured theme (U-06)
            gui.start()
            try:
                templates_root = profile_dir / "templates"
                assert not (templates_root / "template_index.json").exists()
                assert not (templates_root / "template_list.txt").exists()
                assert self._tree_digest(profile_dir) == before
            finally:
                gui.shutdown()

        records = [r for r in caplog.records if r.name == "utils.template_index"]
        noisy = [r for r in records if r.levelno >= logging.WARNING]
        assert noisy == [], f"boot must not warn on absent optional subdirs: {noisy}"
        # The missing material/device subdirs were still reported -- at DEBUG.
        assert any("templates directory not found" in r.getMessage() for r in records)

    def test_optin_env_writes_index_files(self, qapp, tmp_path, monkeypatch):
        """N6 acceptance 2: ``ISA_STEWARD_TEMPLATE_INDEX_WRITE=1`` restores
        the explicit file output at boot."""
        import utils.config_loader as config_loader
        from gui.agent_tools.runtime import HeadlessGui

        profile_dir = TestBootProfile._copy_profile(tmp_path)
        monkeypatch.setenv("ISA_STEWARD_PROFILE", str(profile_dir))
        monkeypatch.setenv("ISA_STEWARD_TEMPLATE_INDEX_WRITE", "1")
        monkeypatch.setattr(config_loader, "_profile", config_loader._profile)

        gui = HeadlessGui()
        gui.start()
        try:
            templates_root = profile_dir / "templates"
            index_path = templates_root / "template_index.json"
            list_path = templates_root / "template_list.txt"
            assert index_path.exists()
            assert list_path.exists()

            index = json.loads(index_path.read_text(encoding="utf-8"))
            # Counts match the synthetic fixture: 2 assays + 1 protocol.
            assert index["counts"] == {
                "assay": 2,
                "protocol": 1,
                "material_files": 0,
                "device_files": 0,
            }
            assert "=== Assay Templates ===" in list_path.read_text(encoding="utf-8")
        finally:
            gui.shutdown()

    def test_templates_page_lists_templates_without_file_writes(self, qapp, tmp_path, monkeypatch):
        """N6: the Templates page still lists templates when the boot index
        stays in memory (the page reads the template subdirs directly)."""
        from PyQt6.QtCore import Qt

        import utils.config_loader as config_loader
        from gui.agent_tools.runtime import HeadlessGui

        profile_dir = TestBootProfile._copy_profile(tmp_path)
        monkeypatch.setenv("ISA_STEWARD_PROFILE", str(profile_dir))
        monkeypatch.delenv("ISA_STEWARD_TEMPLATE_INDEX_WRITE", raising=False)
        monkeypatch.setattr(config_loader, "_profile", config_loader._profile)

        gui = HeadlessGui()
        gui.start()
        try:
            gui.navigate("templates")
            page = gui.window.pages["templates"]

            def _filenames():
                return [
                    page.template_list.item(i).data(Qt.ItemDataRole.UserRole)["filename"]
                    for i in range(page.template_list.count())
                ]

            # Default combo selection lists the assay templates.
            assert "calcein_assay.json" in _filenames()
            assert "facs_assay.json" in _filenames()

            gui.find("page.templates.typeCombo").setCurrentText("Protocol Templates")
            gui.process_events(50)
            assert "sample_dilution_protocol.json" in _filenames()

            # The populated page must not have come from (or produced) files.
            templates_root = profile_dir / "templates"
            assert not (templates_root / "template_index.json").exists()
            assert not (templates_root / "template_list.txt").exists()
        finally:
            gui.shutdown()


class TestThemeSessionOnly:
    """U-06: theme tooling is session-only (AGENTS.md section 8.1 contract)."""

    def test_gui_screenshot_restores_stylesheet(self, main_window, tmp_path):
        from gui.agent_tools.screenshot import gui_screenshot

        app = QApplication.instance()
        style_before = app.styleSheet()
        result = gui_screenshot(main_window, out_dir=tmp_path, name="dark", theme="dark")
        assert result.path.exists()
        assert app.styleSheet() == style_before

    def test_gui_screenshot_never_persists_theme(self, main_window, tmp_path):
        from PyQt6.QtCore import QSettings

        from gui.agent_tools.screenshot import gui_screenshot

        settings = QSettings("isa-json-steward-agent", "DataSteward")
        before = settings.value("gui/theme")
        gui_screenshot(main_window, out_dir=tmp_path, name="dark_persist", theme="dark")
        assert settings.value("gui/theme") == before

    def test_apply_theme_contract(self):
        """apply_theme() is session-only by default; set_theme() persists."""
        from gui.app import StewardApp

        class _SpySettings:
            def __init__(self):
                self.values = {}

            def value(self, key, default=None, type=None):
                return self.values.get(key, default)

            def setValue(self, key, value):
                self.values[key] = value

        class _SpyApp:
            # Bind the real implementations so set_theme()'s self.apply_theme
            # delegation resolves (duck-typed app, not a StewardApp instance).
            apply_theme = StewardApp.apply_theme
            set_theme = StewardApp.set_theme

            def __init__(self):
                self.settings = _SpySettings()
                self.style = ""

            def setStyleSheet(self, text):
                self.style = text

        spy = _SpyApp()
        StewardApp.apply_theme(spy, "dark")  # persist defaults to False (U-06)
        assert "gui/theme" not in spy.settings.values
        assert spy.style  # the QSS was applied

        StewardApp.apply_theme(spy, "light", persist=True)  # explicit persist
        assert spy.settings.values["gui/theme"] == "light"

        StewardApp.set_theme(spy, "dark")  # settings-page combo path persists
        assert spy.settings.values["gui/theme"] == "dark"

    def test_agent_shim_theme_never_writes_settings(self, qapp):
        from gui.agent_tools.runtime import _AgentAppShim

        shim = _AgentAppShim(qapp)
        before = shim.settings.value("gui/theme")
        shim.set_theme("dark")
        assert shim.settings.value("gui/theme") == before

    def test_boot_keeps_configured_theme(self, qapp):
        """HeadlessGui() boots with the configured theme (no forced light)."""
        from gui.agent_tools.runtime import HeadlessGui

        style_before = qapp.styleSheet()
        gui = HeadlessGui()
        gui.start()
        try:
            assert qapp.styleSheet() == style_before
        finally:
            gui.shutdown()


class TestOffscreenFontdir:
    """X-2: ``QT_QPA_FONTDIR`` fallback for offscreen boots on Windows."""

    def test_sets_windows_fontdir_when_unset(self, monkeypatch):
        from gui.agent_tools import runtime

        monkeypatch.setattr(runtime, "_windows_fontdir", lambda: runtime._WIN_FONT_DIR)
        env: dict = {}
        runtime.ensure_offscreen_platform(env)
        assert env["QT_QPA_FONTDIR"] == runtime._WIN_FONT_DIR

    def test_never_overrides_explicit_fontdir(self, monkeypatch):
        from gui.agent_tools import runtime

        monkeypatch.setattr(runtime, "_windows_fontdir", lambda: runtime._WIN_FONT_DIR)
        env = {"QT_QPA_FONTDIR": "/custom/fonts"}
        runtime.ensure_offscreen_platform(env)
        assert env["QT_QPA_FONTDIR"] == "/custom/fonts"

    def test_blank_fontdir_is_treated_as_unset(self, monkeypatch):
        """The cmd.exe whitespace-pollution mirror: blank counts as unset."""
        from gui.agent_tools import runtime

        monkeypatch.setattr(runtime, "_windows_fontdir", lambda: runtime._WIN_FONT_DIR)
        env = {"QT_QPA_FONTDIR": "  "}
        runtime.ensure_offscreen_platform(env)
        assert env["QT_QPA_FONTDIR"] == runtime._WIN_FONT_DIR

    def test_non_windows_leaves_fontdir_unset(self, monkeypatch):
        from gui.agent_tools import runtime

        monkeypatch.setattr(runtime, "_windows_fontdir", lambda: None)
        env: dict = {}
        runtime.ensure_offscreen_platform(env)
        assert "QT_QPA_FONTDIR" not in env

    def test_no_fallback_when_platform_pinned_away(self, monkeypatch):
        """Only the offscreen platform gets the fallback (X-2 spec)."""
        from gui.agent_tools import runtime

        monkeypatch.setattr(runtime, "_windows_fontdir", lambda: runtime._WIN_FONT_DIR)
        env = {"QT_QPA_PLATFORM": "windows"}
        runtime.ensure_offscreen_platform(env)
        assert "QT_QPA_FONTDIR" not in env

    def test_windows_fontdir_tracks_the_real_platform(self):
        """On Windows the helper returns the existing system font dir."""
        from gui.agent_tools import runtime

        if os.name == "nt":
            assert runtime._windows_fontdir() == runtime._WIN_FONT_DIR
        else:
            assert runtime._windows_fontdir() is None


class TestShutdownIdempotent:
    """N9 code half: ``HeadlessGui.shutdown()`` is idempotent."""

    def test_double_shutdown_is_a_noop(self, qapp):
        from gui.agent_tools.runtime import HeadlessGui

        gui = HeadlessGui()
        gui.start()
        gui.shutdown()
        gui.shutdown()  # N9: must be a silent no-op, never raise
        assert gui.window is None
        assert not gui._owns_app


class TestPytestIniHygiene:
    """E-1: the coverage gate lives in CI, not in ``pytest.ini`` addopts."""

    def test_addopts_carry_no_coverage_flags(self):
        """Bare ``pytest tests/gui -m gui`` must not need ``-o addopts=``."""
        lines = (REPO_ROOT / "pytest.ini").read_text(encoding="utf-8").splitlines()
        start = next(i for i, ln in enumerate(lines) if ln.strip().startswith("addopts"))
        flags = []
        for ln in lines[start + 1 :]:
            if ln.strip() and not ln[:1].isspace():
                break
            stripped = ln.strip()
            if stripped.startswith("--cov"):
                flags.append(stripped)
        assert not flags, f"pytest.ini addopts must not gate coverage (E-1): {flags}"
