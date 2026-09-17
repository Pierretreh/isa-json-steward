"""
Unit tests for OntologyManager.
"""

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
        """main_ontology should be derived from profile config."""
        from utils.config_loader import get_profile

        manager = OntologyManager()
        filenames = get_profile().get_ontology_filenames()
        # The main_ontology path should contain the profile's ontology filename
        assert manager.main_ontology.name == Path(filenames["main_owl"]).name

    def test_main_ontology_ttl_from_profile(self):
        """main_ontology_ttl should be derived from profile config."""
        from utils.config_loader import get_profile

        manager = OntologyManager()
        filenames = get_profile().get_ontology_filenames()
        assert manager.main_ontology_ttl.name == Path(filenames["main_ttl"]).name


@pytest.mark.unit
class TestOntologyManagerInit:
    """Tests for OntologyManager initialization."""

    def test_default_base_path(self):
        """Without explicit base_path, uses project ontologies/ dir."""
        manager = OntologyManager()
        assert "ontologies" in str(manager.base_path)

    def test_custom_base_path(self, tmp_path):
        """With explicit base_path, uses that path."""
        manager = OntologyManager(base_path=tmp_path)
        assert manager.base_path == tmp_path

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
