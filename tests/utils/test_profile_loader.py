"""
Tests for the ProfileLoader in utils/config_loader.py.
"""

import json
from pathlib import Path

import pytest

from utils.config_loader import ProfileLoader, get_profile, set_profile


@pytest.fixture
def profile_dir(tmp_path):
    """Create a temporary profile directory with a config/ subdirectory.

    All config files live under ``<tmp_path>/config/`` to match the real
    profile directory layout that ``ProfileLoader`` expects.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create profile.json
    profile = {
        "name": "test-profile",
        "version": "1.0.0",
        "namespace": "https://example.org/test/onto#",
        "namespace_prefix": "test",
        "ontology_main_file": "test_onto.owl",
        "ontology_main_ttl": "test_onto.ttl",
        "ontology_shapes": "test_shapes.ttl",
        "ontologies_dir": "ontologies",
        "templates_dir": "templates",
        "app_name": "Test Data Steward",
        "min_core_version": "1.0.0",
    }
    (config_dir / "profile.json").write_text(json.dumps(profile), encoding="utf-8")

    # Create protein_names.json
    proteins = {
        "protein_names": {
            "YFP": "Yellow Fluorescent Protein",
            "MBP": "Maltose Binding Protein",
        },
        "drug_names": {"DMSO": "DMSO", "Eylea": "Aflibercept"},
    }
    (config_dir / "protein_names.json").write_text(json.dumps(proteins), encoding="utf-8")

    # Create experiment_patterns.json
    patterns = {
        "type_to_template": {
            "facs": "facs_assay.json",
            "calcein": "calcein_assay.json",
        },
        "type_name_aliases": {
            "calceinassay": "calcein",
            "wb": "western_blot",
        },
        "type_keywords": {
            "facs": ["facs", "flow cytometry"],
            "calcein": ["calcein"],
        },
        "type_file_indicators": {"facs": [".fcs", ".wsp"]},
        "cell_type_map": {"Müller": "muller_cell", "HRMVEC": "hrmvec"},
        "assay_type_map": {"microscopy": ["MicroscopyAssay"]},
    }
    (config_dir / "experiment_patterns.json").write_text(json.dumps(patterns), encoding="utf-8")

    # Create fcs_markers.json
    fcs = {
        "channel_markers": {
            "FITC": {"dye": "Calcein-AM", "viability": "live"},
            "DAPI": {"dye": "DAPI"},
        },
        "known_operators": ["JP"],
        "instrument_aliases": {"lsrfortessa": "LSRFortessa"},
    }
    (config_dir / "fcs_markers.json").write_text(json.dumps(fcs), encoding="utf-8")

    # Create people.json
    people = {
        "people": [
            {
                "first_name": "Jane",
                "last_name": "Doe",
                "affiliation": "Test University",
                "roles": [],
            }
        ]
    }
    (config_dir / "people.json").write_text(json.dumps(people), encoding="utf-8")

    # Create investigation_defaults.json
    inv_defaults = {
        "investigation_id": "inv_test",
        "default_investigation_title": "Test Investigation",
        "default_investigation_description": "A test investigation",
    }
    (config_dir / "investigation_defaults.json").write_text(
        json.dumps(inv_defaults), encoding="utf-8"
    )

    # Create settings.json
    settings = {"gui": {"theme": "dark"}}
    (config_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    return tmp_path


@pytest.fixture
def loader(profile_dir):
    """Create a ProfileLoader with the temp profile directory."""
    return ProfileLoader(str(profile_dir))


@pytest.mark.unit
class TestProfileLoaderInit:
    """Tests for ProfileLoader initialization."""

    def test_init_with_profile_path(self, profile_dir):
        loader = ProfileLoader(str(profile_dir))
        assert loader._config_dir == Path(profile_dir).resolve() / "config"

    def test_init_without_profile_path(self):
        loader = ProfileLoader()
        expected = Path(__file__).resolve().parent.parent.parent / "config"
        assert loader._config_dir == expected

    def test_cache_is_empty_on_init(self, loader):
        assert loader._cache == {}
        assert loader._profile is None


@pytest.mark.unit
class TestProfileMetadata:
    """Tests for profile.json accessors."""

    def test_profile_property_loads_json(self, loader):
        result = loader.profile
        assert result["name"] == "test-profile"
        assert result["namespace"] == "https://example.org/test/onto#"

    def test_profile_is_cached(self, loader):
        result1 = loader.profile
        result2 = loader.profile
        assert result1 is result2  # Same dict object (cached)

    def test_get_namespace(self, loader):
        assert loader.get_namespace() == "https://example.org/test/onto#"

    def test_get_namespace_prefix(self, loader):
        assert loader.get_namespace_prefix() == "test"

    def test_get_templates_dir(self, loader):
        assert loader.get_templates_dir() == "templates"

    def test_get_config_dir(self, loader, profile_dir):
        assert loader.get_config_dir() == str(Path(profile_dir).resolve() / "config")

    def test_get_ontology_filenames(self, loader):
        result = loader.get_ontology_filenames()
        assert result["main_owl"].endswith("test_onto.owl")
        assert result["main_ttl"].endswith("test_onto.ttl")
        assert result["shapes"].endswith("test_shapes.ttl")


@pytest.mark.unit
class TestProteinDrugNames:
    """Tests for protein/drug name accessors."""

    def test_get_protein_name_known(self, loader):
        assert loader.get_protein_name("YFP") == "Yellow Fluorescent Protein"

    def test_get_protein_name_unknown(self, loader):
        assert loader.get_protein_name("UNKNOWN") == "UNKNOWN"

    def test_get_drug_name_known(self, loader):
        assert loader.get_drug_name("DMSO") == "DMSO"

    def test_get_drug_name_unknown(self, loader):
        assert loader.get_drug_name("UNKNOWN") == "UNKNOWN"

    def test_get_protein_name_map(self, loader):
        result = loader.get_protein_name_map()
        assert "YFP" in result
        assert result["YFP"] == "Yellow Fluorescent Protein"

    def test_get_drug_name_map(self, loader):
        result = loader.get_drug_name_map()
        assert "DMSO" in result


@pytest.mark.unit
class TestExperimentPatterns:
    """Tests for experiment pattern accessors."""

    def test_get_experiment_template_direct(self, loader):
        assert loader.get_experiment_template("facs") == "facs_assay.json"

    def test_get_experiment_template_via_alias(self, loader):
        # "calceinassay" is aliased to "calcein" which maps to "calcein_assay.json"
        assert loader.get_experiment_template("calceinassay") == "calcein_assay.json"

    def test_get_experiment_template_unknown(self, loader):
        assert loader.get_experiment_template("unknown") == ""

    def test_get_experiment_keywords(self, loader):
        result = loader.get_experiment_keywords("facs")
        assert "facs" in result
        assert "flow cytometry" in result

    def test_get_type_to_template(self, loader):
        result = loader.get_type_to_template()
        assert result["facs"] == "facs_assay.json"

    def test_get_type_name_aliases(self, loader):
        result = loader.get_type_name_aliases()
        assert result["calceinassay"] == "calcein"

    def test_get_type_keywords(self, loader):
        result = loader.get_type_keywords()
        assert "facs" in result

    def test_get_type_file_indicators(self, loader):
        result = loader.get_type_file_indicators()
        assert ".fcs" in result["facs"]

    def test_get_cell_type_map(self, loader):
        result = loader.get_cell_type_map()
        assert result["Müller"] == "muller_cell"

    def test_get_assay_type_map(self, loader):
        result = loader.get_assay_type_map()
        assert "microscopy" in result


@pytest.mark.unit
class TestFCSMarkers:
    """Tests for FCS marker accessors."""

    def test_get_fcs_markers(self, loader):
        result = loader.get_fcs_markers()
        assert "FITC" in result
        assert result["FITC"]["dye"] == "Calcein-AM"

    def test_get_known_operators(self, loader):
        result = loader.get_known_operators()
        assert "JP" in result

    def test_get_instrument_aliases(self, loader):
        result = loader.get_instrument_aliases()
        assert result["lsrfortessa"] == "LSRFortessa"


@pytest.mark.unit
class TestPeopleAndInvestigation:
    """Tests for people and investigation defaults."""

    def test_get_people(self, loader):
        result = loader.get_people()
        assert len(result) == 1
        assert result[0]["first_name"] == "Jane"

    def test_get_investigation_defaults(self, loader):
        result = loader.get_investigation_defaults()
        assert result["investigation_id"] == "inv_test"


@pytest.mark.unit
class TestSettings:
    """Tests for settings accessor."""

    def test_get_settings(self, loader):
        result = loader.get_settings()
        assert result["gui"]["theme"] == "dark"


@pytest.mark.unit
class TestMissingFiles:
    """Tests for graceful handling of missing config files.

    When a profile is missing a config file, the loader falls back to the
    project's default ``config/`` directory.  These tests verify that
    behaviour: the data comes from the project defaults rather than empty
    dicts.
    """

    def test_missing_profile_falls_back_to_default(self, tmp_path):
        """Profile without profile.json → falls back to project default."""
        loader = ProfileLoader(str(tmp_path))
        # The profile directory has no config/ at all, so _read_json
        # falls back to the project's config/profile.json which exists.
        result = loader.profile
        assert isinstance(result, dict)
        # Should contain the project's default profile data
        assert result.get("name") == "default"

    def test_missing_config_section_falls_back_to_default(self, tmp_path):
        """Profile without config files → falls back to project defaults."""
        loader = ProfileLoader(str(tmp_path))
        # protein_names, fcs_markers, people all fall back to project config
        proteins = loader.get_protein_name_map()
        assert isinstance(proteins, dict)
        assert len(proteins) > 0  # Project has default protein names

    def test_malformed_json_returns_empty(self, tmp_path):
        """A malformed JSON file in the profile's config dir returns empty.

        The file is found (it exists) but cannot be parsed, so empty is
        returned even though a valid fallback exists.
        """
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "profile.json").write_text("not valid json{{{", encoding="utf-8")
        loader = ProfileLoader(str(tmp_path))
        assert loader.profile == {}


@pytest.mark.unit
class TestSingleton:
    """Tests for module-level singleton pattern."""

    def setup_method(self):
        """Reset singleton before each test."""
        import utils.config_loader

        utils.config_loader._profile = None

    def teardown_method(self):
        """Reset singleton after each test."""
        import utils.config_loader

        utils.config_loader._profile = None

    def test_get_profile_creates_instance(self):
        result = get_profile()
        assert isinstance(result, ProfileLoader)

    def test_get_profile_returns_same_instance(self):
        r1 = get_profile()
        r2 = get_profile()
        assert r1 is r2

    def test_set_profile_replaces_instance(self, profile_dir):
        old = get_profile()
        new = set_profile(str(profile_dir))
        assert new is not old
        assert get_profile() is new

    def test_set_profile_loads_correct_dir(self, profile_dir):
        set_profile(str(profile_dir))
        p = get_profile()
        assert p.get_namespace() == "https://example.org/test/onto#"


# ---------------------------------------------------------------------------
# New behaviour: profile.json discovery order, strict mode,
# min_core_version enforcement, fallback tracking
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProfileJsonDiscovery:
    """profile.json may live at the profile root or in config/.

    The profile root location is checked first; only when it is absent in
    both profile locations does the loader fall back to the core default
    ``config/profile.json`` (loudly, when an explicit profile was given).
    """

    def test_profile_json_at_profile_root_wins(self, tmp_path):
        """profile.json at the profile root is found (E41 regression)."""
        (tmp_path / "config").mkdir()
        (tmp_path / "profile.json").write_text(
            json.dumps(
                {
                    "name": "root-layout",
                    "namespace": "https://example.org/root#",
                    "min_core_version": "1.0.0",
                }
            ),
            encoding="utf-8",
        )
        loader = ProfileLoader(str(tmp_path))
        assert loader.profile["name"] == "root-layout"
        assert loader.get_namespace() == "https://example.org/root#"
        # No core-default fallback was needed for profile.json
        assert "profile.json" not in loader.fallback_files

    def test_profile_json_in_config_dir_also_works(self, tmp_path):
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "profile.json").write_text(
            json.dumps(
                {
                    "name": "config-layout",
                    "namespace": "https://example.org/config#",
                    "min_core_version": "1.0.0",
                }
            ),
            encoding="utf-8",
        )
        loader = ProfileLoader(str(tmp_path))
        assert loader.profile["name"] == "config-layout"

    def test_profile_json_missing_falls_back_loudly(self, tmp_path, caplog):
        (tmp_path / "config").mkdir()
        loader = ProfileLoader(str(tmp_path))
        with caplog.at_level("WARNING", logger="utils.config_loader"):
            result = loader.profile
        # Falls back to the core default profile.json (name == "default")
        assert result.get("name") == "default"
        assert "profile.json" in loader.fallback_files
        assert any("CORE DEFAULT" in r.message for r in caplog.records)

    def test_candidate_order_prefers_profile_root(self, tmp_path):
        loader = ProfileLoader(str(tmp_path))
        candidates = loader._candidate_paths("profile.json")
        # Profile root before config dir, core default last
        assert candidates[0] == tmp_path.resolve() / "profile.json"
        assert candidates[1] == tmp_path.resolve() / "config" / "profile.json"
        assert candidates[-1] == loader._PROJECT_ROOT / "config" / "profile.json"

    def test_candidate_order_for_regular_files(self, tmp_path):
        loader = ProfileLoader(str(tmp_path))
        candidates = loader._candidate_paths("people.json")
        # No profile-root entry for regular config files
        assert candidates[0] == tmp_path.resolve() / "config" / "people.json"
        assert candidates[-1] == loader._PROJECT_ROOT / "config" / "people.json"


@pytest.mark.unit
class TestStrictMode:
    """Strict mode: missing profile files raise instead of falling back."""

    def test_missing_file_raises(self, tmp_path):
        (tmp_path / "config").mkdir()
        loader = ProfileLoader(str(tmp_path), strict=True)
        with pytest.raises(Exception, match="profile.json"):
            loader.profile

    def test_complete_profile_ok(self, profile_dir):
        loader = ProfileLoader(str(profile_dir), strict=True)
        # profile_dir fixture contains all files → no error
        assert loader.profile["name"] == "test-profile"
        assert loader.get_protein_name_map()  # forces section load

    def test_strict_ignores_missing_only_in_profile(self, tmp_path, profile_dir):
        """A file present in the profile is never an error."""
        loader = ProfileLoader(str(profile_dir), strict=True)
        assert "YFP" in loader.get_protein_name_map()

    def test_strict_false_for_implicit_profile(self):
        """Without an explicit profile path, strict mode is inert."""
        loader = ProfileLoader(strict=True)
        assert loader.strict is False

    def test_strict_true_for_explicit_profile(self, tmp_path):
        loader = ProfileLoader(str(tmp_path), strict=True)
        assert loader.strict is True


@pytest.mark.unit
class TestMinCoreVersion:
    """min_core_version from profile.json is enforced on first access."""

    def _profile_with(self, tmp_path, min_core_version):
        (tmp_path / "config").mkdir()
        data = {"name": "ver-test", "namespace": "https://example.org/ver#"}
        if min_core_version is not None:
            data["min_core_version"] = min_core_version
        (tmp_path / "profile.json").write_text(json.dumps(data), encoding="utf-8")
        return tmp_path

    def test_compatible_version_accepted(self, tmp_path, monkeypatch):
        import utils.config_loader as cl

        monkeypatch.setattr(cl, "_get_core_version", lambda: "2.0.0")
        profile_dir = self._profile_with(tmp_path, "1.0.0")
        loader = ProfileLoader(str(profile_dir))
        assert loader.profile["name"] == "ver-test"

    def test_incompatible_version_raises(self, tmp_path, monkeypatch):
        import utils.config_loader as cl

        monkeypatch.setattr(cl, "_get_core_version", lambda: "1.5.0")
        profile_dir = self._profile_with(tmp_path, "2.0.0")
        loader = ProfileLoader(str(profile_dir))
        with pytest.raises(cl.ProfileConfigError, match="requires core"):
            loader.profile

    def test_missing_field_skipped(self, tmp_path, monkeypatch):
        import utils.config_loader as cl

        monkeypatch.setattr(cl, "_get_core_version", lambda: "1.0.0")
        profile_dir = self._profile_with(tmp_path, None)
        loader = ProfileLoader(str(profile_dir))
        assert loader.profile["name"] == "ver-test"

    def test_unknown_core_version_skipped(self, tmp_path, monkeypatch):
        import utils.config_loader as cl

        monkeypatch.setattr(cl, "_get_core_version", lambda: None)
        profile_dir = self._profile_with(tmp_path, "99.0.0")
        loader = ProfileLoader(str(profile_dir))
        assert loader.profile["name"] == "ver-test"

    def test_error_message_includes_versions(self, tmp_path, monkeypatch):
        import utils.config_loader as cl

        monkeypatch.setattr(cl, "_get_core_version", lambda: "1.0.0")
        profile_dir = self._profile_with(tmp_path, "2.0.0")
        loader = ProfileLoader(str(profile_dir))
        with pytest.raises(cl.ProfileConfigError, match="1\\.0\\.0"):
            loader.profile


@pytest.mark.unit
class TestFallbackTracking:
    """Fallback files are tracked and summarised for logging."""

    def test_fallback_files_populated_only_for_explicit_profile(self, tmp_path):
        loader = ProfileLoader(str(tmp_path))
        loader.profile  # forces fallback for profile.json
        assert "profile.json" in loader.fallback_files

    def test_no_tracking_for_implicit_profile(self):
        loader = ProfileLoader()
        loader.profile
        assert loader.fallback_files == []

    def test_summary_logs_warning(self, tmp_path, caplog):
        import logging

        loader = ProfileLoader(str(tmp_path))
        loader.profile
        with caplog.at_level(logging.WARNING, logger="utils.config_loader"):
            loader.log_profile_load_summary()
        assert any("served from CORE" in r.message for r in caplog.records)

    def test_summary_silent_when_complete(self, profile_dir, caplog):
        import logging

        loader = ProfileLoader(str(profile_dir))
        loader.profile
        with caplog.at_level(logging.WARNING, logger="utils.config_loader"):
            loader.log_profile_load_summary()
        assert not [r for r in caplog.records if "served from CORE" in r.message]


@pytest.mark.unit
class TestSingletonStrict:
    """set_profile() propagates strict mode to the singleton."""

    def setup_method(self):
        import utils.config_loader

        utils.config_loader._profile = None

    def teardown_method(self):
        import utils.config_loader

        utils.config_loader._profile = None

    def test_set_profile_strict(self, tmp_path):
        new = set_profile(str(tmp_path), strict=True)
        assert new.strict is True
        with pytest.raises(Exception, match="profile.json"):
            new.profile
