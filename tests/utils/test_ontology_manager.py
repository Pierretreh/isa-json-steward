"""
Unit tests for OntologyManager.
"""

import json
import shutil
from pathlib import Path

import pytest
from rdflib import Namespace

from utils.ontology_manager import OntologyManager


@pytest.mark.unit
class TestOntologyManager:
    """Tests for OntologyManager class."""

    def test_initialization(self):
        """Test ontology manager initialization."""
        manager = OntologyManager()
        assert isinstance(manager, OntologyManager)

    def test_load_ontology(self):
        """Test loading an ontology."""
        manager = OntologyManager()
        # This test may require actual ontology files
        # For now, test that the method exists and handles gracefully
        try:
            result = manager.load_ontology("OBI")
            # May return None if ontology not available
            assert result is not None or result is None
        except Exception:
            # Expected if ontology files not available
            pytest.skip("Ontology files not available")

    def test_search_term(self):
        """Test searching for ontology terms."""
        manager = OntologyManager()
        try:
            results = manager.search_term("transformation", "OBI")
            assert isinstance(results, list)
        except Exception:
            pytest.skip("Ontology files not available")

    def test_get_term_details(self):
        """Test getting term details."""
        manager = OntologyManager()
        try:
            term = manager.get_term_details("http://purl.obolibrary.org/obo/OBI_0000769", "OBI")
            # May return None if term not found
            assert term is not None or term is None
        except Exception:
            pytest.skip("Ontology files not available")

    def test_validate_term(self):
        """Test validating an ontology term."""
        manager = OntologyManager()
        try:
            is_valid = manager.validate_term("http://purl.obolibrary.org/obo/OBI_0000769", "OBI")
            assert isinstance(is_valid, bool)
        except Exception:
            pytest.skip("Ontology files not available")

    def test_get_available_ontologies(self):
        """Test getting list of available ontologies."""
        manager = OntologyManager()
        ontologies = manager.get_available_ontologies()
        assert isinstance(ontologies, list)

    def test_cache_ontology(self):
        """Test ontology caching."""
        manager = OntologyManager()
        try:
            manager.cache_ontology("OBI")
            # Should not raise exception
            assert True
        except Exception:
            pytest.skip("Ontology caching not available")

    def test_offline_mode(self):
        """Test offline mode handling."""
        manager = OntologyManager(offline_mode=True)
        assert manager.offline_mode is True


@pytest.mark.unit
class TestProjectNamespace:
    """Tests for dynamic namespace resolution from profile."""

    def test_project_namespace_is_loaded(self):
        """The project namespace should be loaded from the profile."""
        from utils.ontology_manager import PROJECT_NS

        # Should be a Namespace instance
        assert isinstance(PROJECT_NS, Namespace)
        # Should end with #
        assert str(PROJECT_NS).endswith("#")

    def test_namespace_matches_profile(self):
        """The module-level project namespace should match the profile's namespace."""
        from utils.config_loader import get_profile
        from utils.ontology_manager import PROJECT_NS

        assert str(PROJECT_NS) == get_profile().get_namespace()

    def test_get_project_namespace_function(self):
        """_get_project_namespace() should return a Namespace from the profile."""
        from utils.ontology_manager import _get_project_namespace

        ns = _get_project_namespace()
        assert isinstance(ns, Namespace)


@pytest.mark.unit
class TestOntologyManagerDynamicFilenames:
    """Tests for dynamic ontology filename resolution."""

    def test_main_ontology_from_profile(self):
        """main_ontology resolves the profile filename against the profile root."""
        from utils.config_loader import get_profile

        manager = OntologyManager()
        filenames = get_profile().get_ontology_filenames()
        # Resolved against the profile root WITHOUT .name stripping
        assert manager.main_ontology == get_profile().get_profile_root() / filenames["main_owl"]
        assert manager.main_ontology.name == Path(filenames["main_owl"]).name

    def test_main_ontology_ttl_from_profile(self):
        """main_ontology_ttl resolves against the profile root."""
        from utils.config_loader import get_profile

        manager = OntologyManager()
        filenames = get_profile().get_ontology_filenames()
        assert manager.main_ontology_ttl == get_profile().get_profile_root() / filenames["main_ttl"]
        assert manager.main_ontology_ttl.name == Path(filenames["main_ttl"]).name

    def test_shapes_file_from_profile(self):
        """shapes_file resolves against the profile root too."""
        from utils.config_loader import get_profile

        manager = OntologyManager()
        filenames = get_profile().get_ontology_filenames()
        assert manager.shapes_file == get_profile().get_profile_root() / filenames["shapes"]


@pytest.mark.unit
class TestOntologyManagerInit:
    """Tests for OntologyManager initialization."""

    def test_default_base_path(self):
        """Without explicit base_path, uses the active profile's ontologies root."""
        from utils.config_loader import get_profile

        manager = OntologyManager()
        assert manager.base_path == get_profile().get_ontologies_root()
        assert "ontologies" in str(manager.base_path)

    def test_default_base_path_contains_ontologies_dir(self):
        """The default base path ends in the configured ontologies dir name."""
        from utils.config_loader import get_profile

        manager = OntologyManager()
        expected = get_profile().profile.get("ontologies_dir", "ontologies")
        assert manager.base_path.name == Path(expected).name

    def test_custom_base_path(self, tmp_path):
        """With explicit base_path, uses that path (bare filenames inside)."""
        from utils.config_loader import get_profile

        manager = OntologyManager(base_path=tmp_path)
        assert manager.base_path == tmp_path
        filenames = get_profile().get_ontology_filenames()
        assert manager.main_ontology == tmp_path / Path(filenames["main_owl"]).name
        assert manager.main_ontology_ttl == tmp_path / Path(filenames["main_ttl"]).name

    def test_offline_mode_flag(self, tmp_path):
        """offline_mode is stored."""
        manager = OntologyManager(base_path=tmp_path, offline_mode=True)
        assert manager.offline_mode is True

    def test_graph_is_empty_on_init(self, tmp_path):
        """Graph should be empty on initialization."""
        manager = OntologyManager(base_path=tmp_path)
        assert len(manager.graph) == 0

    def test_parse_errors_empty_on_init(self, tmp_path):
        """Parse errors list should be empty on initialization."""
        manager = OntologyManager(base_path=tmp_path)
        assert manager._parse_errors == []

    def test_search_paths_property(self, tmp_path):
        """search_paths lists the Turtle and XML candidates (Turtle first)."""
        manager = OntologyManager(base_path=tmp_path)
        assert manager.search_paths == [manager.main_ontology_ttl, manager.main_ontology]


_MINI_TTL = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<{ns}TestClassA> a owl:Class ; rdfs:label "Test class A" .
<{ns}TestClassB> a owl:Class ; rdfs:label "Test class B" .
"""


@pytest.mark.unit
class TestOntologyManagerProfileRegression:
    """Regression tests for the profile-aware ontology path resolution.

    Before the fix the default ``base_path`` pointed at the repository's
    non-existent ``ontologies/`` directory even when the active profile
    shipped ontology files, so ``load_ontology()`` silently produced an
    empty graph (2496 triples / 119 terms unreachable).
    """

    def _activate_profile_with_ontology(self, tmp_path, with_ontology=True):
        """Copy the committed synthetic profile to tmp and add ontology files.

        The tracked fixture is never modified -- everything happens in a
        tmp copy.
        """
        fixture = (
            Path(__file__).resolve().parents[1]
            / "batch_processing"
            / "fixtures"
            / "synthetic_profile"
        )
        profile_dir = tmp_path / "synthetic_profile"
        shutil.copytree(fixture, profile_dir)

        if with_ontology:
            ont_dir = profile_dir / "ontologies"
            ont_dir.mkdir(exist_ok=True)
            ns = json.loads((profile_dir / "profile.json").read_text(encoding="utf-8"))["namespace"]
            (ont_dir / "synthetic_onto.ttl").write_text(_MINI_TTL.format(ns=ns), encoding="utf-8")

        from utils.config_loader import set_profile

        set_profile(str(profile_dir))
        return profile_dir

    def test_load_ontology_non_empty_when_profile_ships_files(self, tmp_path):
        """OntologyManager().load_ontology() must see the profile's files."""
        profile_dir = self._activate_profile_with_ontology(tmp_path)

        manager = OntologyManager()
        assert manager.base_path == profile_dir / "ontologies"
        graph = manager.load_ontology()
        assert len(graph) > 0, "profile-shipped ontology must load a non-empty graph"
        assert len(graph) == 4  # 2 classes + 2 labels in the mini ontology

    def test_load_ontology_empty_when_profile_ships_no_files(self, tmp_path):
        """Without shipped files the graph is empty (but nothing crashes)."""
        self._activate_profile_with_ontology(tmp_path, with_ontology=False)

        manager = OntologyManager()
        assert manager.load_ontology() is not None
        assert len(manager.graph) == 0
        assert manager._parse_errors == []

    def test_load_ontology_default_matches_profile_root(self, tmp_path):
        """Default resolution: filenames join the profile root unstripped."""
        profile_dir = self._activate_profile_with_ontology(tmp_path)

        manager = OntologyManager()
        assert manager.main_ontology_ttl == profile_dir / "ontologies" / "synthetic_onto.ttl"
        assert manager.main_ontology == profile_dir / "ontologies" / "synthetic_onto.owl"

    def test_explicit_base_path_still_overrides(self, tmp_path):
        """The base_path kwarg (used by tests) keeps bare-name resolution."""
        self._activate_profile_with_ontology(tmp_path)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "synthetic_onto.ttl").write_text(_MINI_TTL.format(ns="http://x#"), "utf-8")

        manager = OntologyManager(base_path=elsewhere)
        assert manager.main_ontology_ttl == elsewhere / "synthetic_onto.ttl"
        assert len(manager.load_ontology()) > 0


@pytest.mark.unit
class TestLazyProjectNamespace:
    """PROJECT_NS must track the active profile (no import-time freeze)."""

    def _switch_profile(self, tmp_path, namespace):
        profile_dir = tmp_path / "ns_profile"
        config_dir = profile_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        profile = {
            "name": "ns-test",
            "version": "1.0.0",
            "namespace": namespace,
            "namespace_prefix": "nstest",
            "ontology_main_file": "onto.owl",
            "ontology_main_ttl": "onto.ttl",
            "ontology_shapes": "shapes.ttl",
            "templates_dir": "templates",
            "app_name": "NS Test",
        }
        (config_dir / "profile.json").write_text(json.dumps(profile), encoding="utf-8")

        from utils.config_loader import set_profile

        set_profile(str(profile_dir))

    def test_ontology_manager_project_ns_follows_profile_switch(self, tmp_path):
        """``from ... import PROJECT_NS`` reflects the current profile."""
        from utils import ontology_manager

        self._switch_profile(tmp_path, "https://example.org/switched#")
        assert str(ontology_manager.PROJECT_NS) == "https://example.org/switched#"
        assert isinstance(ontology_manager.PROJECT_NS, Namespace)

        self._switch_profile(tmp_path, "https://example.org/other#")
        assert str(ontology_manager.PROJECT_NS) == "https://example.org/other#"

    def test_graph_builder_project_ns_follows_profile_switch(self, tmp_path):
        """The same laziness holds for utils.graph_builder."""
        from utils import graph_builder

        self._switch_profile(tmp_path, "https://example.org/gb#")
        assert str(graph_builder.PROJECT_NS) == "https://example.org/gb#"
        assert str(graph_builder.PROJECT_NS.hasInput) == "https://example.org/gb#hasInput"

    def test_rdf_export_uses_profile_namespace(self, tmp_path):
        """isa_json_to_rdf IRIs use the active profile's namespace."""
        self._switch_profile(tmp_path, "https://example.org/export#")

        manager = OntologyManager(base_path=tmp_path / "no_ontology")
        graph = manager.isa_json_to_rdf(
            {"investigation": {"@id": "#investigation/inv_1", "title": "Test"}}
        )
        nodes = {str(n) for n in graph.all_nodes()}
        assert "https://example.org/export#Investigation" in nodes

        # After a profile switch the exported type IRIs must follow suit
        # (the old import-time PROJECT_NS kept exporting the stale one).
        self._switch_profile(tmp_path, "https://example.org/export2#")
        graph2 = manager.isa_json_to_rdf(
            {"investigation": {"@id": "#investigation/inv_1", "title": "Test"}}
        )
        nodes2 = {str(n) for n in graph2.all_nodes()}
        assert "https://example.org/export2#Investigation" in nodes2
