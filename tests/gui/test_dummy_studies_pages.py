"""Defect-fix GUI tests: representative dummy studies + honest empty states.

Covers:

* **Defect A verification** -- a generated study populates the Materials
  table and the Process Sequence tree (the historical dummy studies were
  empty everywhere and looked like a display bug).
* **Empty-state hints** (U-13 pattern) on Materials / Process Sequence:
  muted placeholders ("No materials in this study" / "No processes in this
  study") shown while the study is empty and hidden once populated.
* **Assay-level materials fallback** (``materials.py`` ``_collect_assay_materials``).
* **Honest ontology status** -- "Ontology loaded: N terms" /
  "No ontology found (searched: ...)" instead of a blanket success message.
"""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gui

REPO_ROOT = Path(__file__).resolve().parents[2]


def _find(window, test_id):
    from gui.agent_tools.ids import find_by_test_id

    widget = find_by_test_id(window, test_id)
    assert widget is not None, f"missing testId {test_id}"
    return widget


def _process_events():
    from PyQt6.QtWidgets import QApplication

    QApplication.processEvents()


def _load_generator_module():
    script = REPO_ROOT / "scripts" / "generate_dummy_studies.py"
    spec = importlib.util.spec_from_file_location("gen_dummy_gui_tests", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generated_dataset(tmp_path_factory):
    """Generate the dummy dataset once per module into a temp directory."""
    module = _load_generator_module()
    out_dir = tmp_path_factory.mktemp("gen_inv")
    module.generate_dummy_studies(
        out_dir=str(out_dir), count=8, seed=42, investigation_id="inv_dummy"
    )
    return out_dir


@pytest.fixture
def dummy_dataset(generated_dataset, tmp_path):
    """Copy the generated dataset into the per-test investigations root.

    ``tests/conftest.py::_isolate_directory_manager`` points
    ``DirectoryManager`` at ``tmp_path``, so the window discovers the copy
    under ``tmp_path/investigations/inv_dummy``.
    """
    dest = tmp_path / "investigations" / "inv_dummy"
    shutil.copytree(generated_dataset, dest)
    return dest


def _select_study(window, study_id):
    window.set_investigation("inv_dummy")
    window.set_study(study_id)
    _process_events()


class TestPopulatedStudy:
    """study_D001 (donor x treatment, calcein/facs/elisa) populates both pages."""

    def test_materials_table_populates(self, main_window, dummy_dataset, synthetic_profile):
        window = main_window
        _select_study(window, "study_D001")
        window._navigate_to_page("materials")
        _process_events()

        table = _find(window, "page.materials.materialsTable")
        placeholder = _find(window, "page.materials.emptyStateLabel")
        # 2 sources + >= 6 samples + 2 otherMaterials
        assert table.rowCount() >= 10, "materials table must show the generated materials"
        assert table.isVisible()
        assert not placeholder.isVisible(), "placeholder must hide once populated"

    def test_process_sequence_tree_populates(self, main_window, dummy_dataset, synthetic_profile):
        window = main_window
        _select_study(window, "study_D001")
        window._navigate_to_page("process_sequence")
        _process_events()

        tree = _find(window, "page.process_sequence.processTree")
        placeholder = _find(window, "page.process_sequence.emptyStateLabel")
        # 3 study-level processes + 3 merged assay-level processes
        assert tree.topLevelItemCount() >= 6, "process tree must show study + assay processes"
        assert tree.isVisible()
        assert not placeholder.isVisible(), "placeholder must hide once populated"

    def test_assay_level_materials_fallback(self, main_window, dummy_dataset, synthetic_profile):
        """study_D006 stores materials at assay level only (GUI fallback)."""
        window = main_window
        _select_study(window, "study_D006")
        window._navigate_to_page("materials")
        _process_events()

        table = _find(window, "page.materials.materialsTable")
        placeholder = _find(window, "page.materials.emptyStateLabel")
        assert table.rowCount() >= 2, "assay-level materials must surface via the fallback"
        assert not placeholder.isVisible()


class TestEmptyStates:
    """study_D007 / study_D008 are deliberately empty -> honest hints."""

    def test_materials_hint_without_study(self, main_window, dummy_dataset, synthetic_profile):
        window = main_window
        window._navigate_to_page("materials")
        _process_events()

        placeholder = _find(window, "page.materials.emptyStateLabel")
        assert placeholder.isVisible()
        assert placeholder.text() == "Select a study to view its materials"

    def test_materials_hint_for_empty_study(self, main_window, dummy_dataset, synthetic_profile):
        window = main_window
        _select_study(window, "study_D007")
        window._navigate_to_page("materials")
        _process_events()

        table = _find(window, "page.materials.materialsTable")
        placeholder = _find(window, "page.materials.emptyStateLabel")
        assert placeholder.isVisible(), "empty study must show the hint"
        assert not table.isVisible()
        assert placeholder.text() == "No materials in this study"

    def test_process_hint_for_empty_study(self, main_window, dummy_dataset, synthetic_profile):
        window = main_window
        _select_study(window, "study_D007")
        window._navigate_to_page("process_sequence")
        _process_events()

        tree = _find(window, "page.process_sequence.processTree")
        placeholder = _find(window, "page.process_sequence.emptyStateLabel")
        assert placeholder.isVisible(), "empty study must show the hint"
        assert not tree.isVisible()
        assert placeholder.text() == "No processes in this study"

    def test_hint_hides_again_after_populated_study(self, main_window, dummy_dataset, synthetic_profile):
        window = main_window
        _select_study(window, "study_D007")
        window._navigate_to_page("materials")
        _process_events()
        assert _find(window, "page.materials.emptyStateLabel").isVisible()

        _select_study(window, "study_D001")
        _process_events()
        placeholder = _find(window, "page.materials.emptyStateLabel")
        assert not placeholder.isVisible(), "hint must hide when a populated study is selected"


class TestOntologyStatusMessages:
    """The ontology page reports the real load outcome (both branches)."""

    def test_no_ontology_found_message(self, main_window, tmp_path, synthetic_profile):
        window = main_window
        window._navigate_to_page("ontology")
        _process_events()

        text = window.status_bar.status_label.text()
        assert text.startswith("No ontology found (searched:"), (
            f"expected honest empty-graph message, got: {text!r}"
        )
        assert ".ttl" in text, "message must list the searched paths"

    def test_loaded_message_reports_term_count(self, main_window, tmp_path):
        from utils.config_loader import set_profile
        from utils.ontology_manager import OntologyManager

        profile_dir = tmp_path / "onto_profile"
        config_dir = profile_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        ns = "https://example.org/guionto#"
        (config_dir / "profile.json").write_text(
            json.dumps(
                {
                    "name": "gui-onto",
                    "version": "1.0.0",
                    "namespace": ns,
                    "namespace_prefix": "guionto",
                    "ontology_main_file": "gui_onto.owl",
                    "ontology_main_ttl": "gui_onto.ttl",
                    "ontology_shapes": "gui_shapes.ttl",
                    "templates_dir": "templates",
                    "app_name": "GUI Onto",
                }
            ),
            encoding="utf-8",
        )
        ont_dir = profile_dir / "ontologies"
        ont_dir.mkdir()
        (ont_dir / "gui_onto.ttl").write_text(
            "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
            f"<{ns}TermA> a owl:Class .\n<{ns}TermB> a owl:Class .\n",
            encoding="utf-8",
        )
        set_profile(str(profile_dir))

        window = main_window
        window.om = OntologyManager()
        page = window.pages["ontology"]
        page._load_ontology()
        _process_events()

        text = window.status_bar.status_label.text()
        assert text == "Ontology loaded: 2 terms", f"expected term count in message, got: {text!r}"
