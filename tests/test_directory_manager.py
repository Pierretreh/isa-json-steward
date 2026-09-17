"""Tests for DirectoryManager in utils/directory_manager.py.

Covers:
  - _get_default_config
  - get_file_pattern
  - get_investigation_path
  - get_study_path
  - create_investigation_directory
  - create_study_directory
  - list_investigations
  - list_studies
  - ensure_structure_exists
  - get_investigations_root
  - get_studies_root
  - get_templates_root
  - get_ontologies_root
  - get_exports_root
  - get_archive_root
  - create_directory
  - copy_file_to_study
  - delete_study
  - delete_investigation
  - get_directory_manager convenience function
"""

import json

import pytest

from utils.directory_manager import DirectoryManager, get_directory_manager


@pytest.fixture
def dm(tmp_path):
    """Create a DirectoryManager with tmp_path as base."""
    return DirectoryManager(base_path=str(tmp_path))


# ---------------------------------------------------------------------------
# _get_default_config
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetDefaultConfig:
    """Tests for _get_default_config."""

    def test_returns_dict(self, dm):
        config = dm._get_default_config()
        assert isinstance(config, dict)

    def test_has_investigations_root(self, dm):
        config = dm._get_default_config()
        assert "investigations_root" in config
        assert config["investigations_root"] == "investigations"

    def test_has_study_subdirs(self, dm):
        config = dm._get_default_config()
        assert "study_subdirs" in config
        assert "raw_data" in config["study_subdirs"]

    def test_has_assay_subdirs(self, dm):
        config = dm._get_default_config()
        assert "assay_subdirs" in config


# ---------------------------------------------------------------------------
# get_file_pattern
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetFilePattern:
    """Tests for get_file_pattern."""

    def test_existing_pattern(self, dm):
        # Add a file_patterns key to config for testing
        dm._config["file_patterns"] = {
            "study_json": "{name}_study.json",
            "raw_image": "{name}_{date}.tiff",
        }
        result = dm.get_file_pattern("study_json", name="test")
        assert result == "test_study.json"

    def test_pattern_with_date(self, dm):
        dm._config["file_patterns"] = {
            "raw_image": "{name}_{date}.tiff",
        }
        result = dm.get_file_pattern("raw_image", name="sample")
        assert "sample_" in result
        assert result.endswith(".tiff")

    def test_missing_pattern_returns_default(self, dm):
        result = dm.get_file_pattern("nonexistent_pattern", name="test")
        assert result == "test"


# ---------------------------------------------------------------------------
# Path resolution methods
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPathResolution:
    """Tests for path resolution methods."""

    def test_get_investigations_root(self, dm, tmp_path):
        root = dm.get_investigations_root()
        assert root == tmp_path / "investigations"

    def test_get_investigation_path(self, dm, tmp_path):
        path = dm.get_investigation_path("inv_1")
        assert path == tmp_path / "investigations" / "inv_1"

    def test_get_investigation_path_invalid_id(self, dm):
        with pytest.raises(ValueError):
            dm.get_investigation_path("../escape")

    def test_get_studies_root(self, dm, tmp_path):
        path = dm.get_studies_root("inv_1")
        assert path == tmp_path / "investigations" / "inv_1" / "studies"

    def test_get_study_path(self, dm, tmp_path):
        path = dm.get_study_path("inv_1", "study_1")
        assert path == tmp_path / "investigations" / "inv_1" / "studies" / "study_1"

    def test_get_study_path_invalid_inv_id(self, dm):
        with pytest.raises(ValueError):
            dm.get_study_path("../escape", "study_1")

    def test_get_study_path_invalid_study_id(self, dm):
        with pytest.raises(ValueError):
            dm.get_study_path("inv_1", "../escape")

    def test_get_study_json_path(self, dm, tmp_path):
        path = dm.get_study_json_path("inv_1", "study_1")
        assert path.name == "study.json"

    def test_get_templates_root(self, dm, tmp_path):
        root = dm.get_templates_root()
        assert root == tmp_path / "templates"

    def test_get_ontologies_root(self, dm, tmp_path):
        root = dm.get_ontologies_root()
        assert root == tmp_path / "ontologies"

    def test_get_exports_root(self, dm, tmp_path):
        root = dm.get_exports_root()
        assert root == tmp_path / "exports"

    def test_get_archive_root(self, dm, tmp_path):
        root = dm.get_archive_root()
        assert root == tmp_path / "archive"


# ---------------------------------------------------------------------------
# create_directory
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateDirectory:
    """Tests for create_directory."""

    def test_create_new_directory(self, dm, tmp_path):
        new_dir = tmp_path / "new_dir"
        result = dm.create_directory(new_dir)
        assert result is True
        assert new_dir.exists()

    def test_create_existing_directory(self, dm, tmp_path):
        new_dir = tmp_path / "existing"
        new_dir.mkdir()
        result = dm.create_directory(new_dir)
        assert result is True


# ---------------------------------------------------------------------------
# create_investigation_directory
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateInvestigationDirectory:
    """Tests for create_investigation_directory."""

    def test_create_investigation(self, dm, tmp_path):
        path = dm.create_investigation_directory("inv_1")
        assert path is not None
        assert path.exists()
        assert path.name == "inv_1"

    def test_create_investigation_invalid_id(self, dm):
        result = dm.create_investigation_directory("../escape")
        assert result is None


# ---------------------------------------------------------------------------
# create_study_directory
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateStudyDirectory:
    """Tests for create_study_directory."""

    def test_create_study(self, dm, tmp_path):
        path = dm.create_study_directory("inv_1", "study_1")
        assert path is not None
        assert path.exists()
        assert path.name == "study_1"
        # Check files subdirectories
        assert (path / "files").exists()
        assert (path / "files" / "original").exists()
        assert (path / "files" / "converted").exists()

    def test_create_study_invalid_ids(self, dm):
        assert dm.create_study_directory("../escape", "study_1") is None
        assert dm.create_study_directory("inv_1", "../escape") is None


# ---------------------------------------------------------------------------
# list_investigations and list_studies
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListOperations:
    """Tests for list_investigations and list_studies."""

    def test_list_investigations_empty(self, dm):
        result = dm.list_investigations()
        assert result == []

    def test_list_investigations_with_data(self, dm, tmp_path):
        inv_root = tmp_path / "investigations"
        inv_root.mkdir()
        (inv_root / "inv_1").mkdir()
        (inv_root / "inv_2").mkdir()

        result = dm.list_investigations()
        assert sorted(result) == ["inv_1", "inv_2"]

    def test_list_studies_empty(self, dm, tmp_path):
        # Create investigation but no studies
        inv_root = tmp_path / "investigations" / "inv_1" / "studies"
        inv_root.mkdir(parents=True)

        result = dm.list_studies("inv_1")
        assert result == []

    def test_list_studies_with_data(self, dm, tmp_path):
        studies_root = tmp_path / "investigations" / "inv_1" / "studies"
        studies_root.mkdir(parents=True)
        (studies_root / "study_1").mkdir()
        (studies_root / "study_2").mkdir()

        result = dm.list_studies("inv_1")
        assert sorted(result) == ["study_1", "study_2"]

    def test_list_studies_nonexistent_investigation(self, dm):
        result = dm.list_studies("nonexistent")
        assert result == []


# ---------------------------------------------------------------------------
# ensure_structure_exists
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEnsureStructureExists:
    """Tests for ensure_structure_exists."""

    def test_creates_structure(self, dm, tmp_path):
        result = dm.ensure_structure_exists()
        assert result is True
        assert (tmp_path / "investigations").exists()
        assert (tmp_path / "templates").exists()
        assert (tmp_path / "ontologies").exists()
        assert (tmp_path / "exports").exists()
        assert (tmp_path / "archive").exists()


# ---------------------------------------------------------------------------
# copy_file_to_study
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCopyFileToStudy:
    """Tests for copy_file_to_study."""

    def test_copy_file(self, dm, tmp_path):
        # Create source file
        source = tmp_path / "source.txt"
        source.write_text("test content", encoding="utf-8")

        # Create study directory first
        dm.create_study_directory("inv_1", "study_1")

        result = dm.copy_file_to_study(source, "inv_1", "study_1", "raw_data")
        assert result is not None
        assert result.exists()
        assert result.read_text(encoding="utf-8") == "test content"

    def test_copy_file_with_custom_name(self, dm, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("data", encoding="utf-8")

        dm.create_study_directory("inv_1", "study_1")

        result = dm.copy_file_to_study(
            source, "inv_1", "study_1", "raw_data", filename="custom.txt"
        )
        assert result is not None
        assert result.name == "custom.txt"


# ---------------------------------------------------------------------------
# delete_study and delete_investigation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeleteOperations:
    """Tests for delete_study and delete_investigation."""

    def test_delete_study(self, dm, tmp_path):
        dm.create_study_directory("inv_1", "study_1")
        study_path = dm.get_study_path("inv_1", "study_1")
        assert study_path.exists()

        result = dm.delete_study("inv_1", "study_1")
        assert result is True
        assert not study_path.exists()

    def test_delete_study_nonexistent(self, dm):
        result = dm.delete_study("inv_1", "nonexistent")
        assert result is False

    def test_delete_study_invalid_ids(self, dm):
        assert dm.delete_study("../escape", "study_1") is False
        assert dm.delete_study("inv_1", "../escape") is False

    def test_delete_investigation(self, dm, tmp_path):
        dm.create_investigation_directory("inv_1")
        inv_path = dm.get_investigation_path("inv_1")
        assert inv_path.exists()

        result = dm.delete_investigation("inv_1")
        assert result is True
        assert not inv_path.exists()

    def test_delete_investigation_nonexistent(self, dm):
        result = dm.delete_investigation("nonexistent")
        assert result is False

    def test_delete_investigation_invalid_id(self, dm):
        assert dm.delete_investigation("../escape") is False


# ---------------------------------------------------------------------------
# get_directory_manager convenience function
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetDirectoryManager:
    """Tests for get_directory_manager convenience function."""

    def test_returns_directory_manager(self, tmp_path):
        dm = get_directory_manager(str(tmp_path))
        assert isinstance(dm, DirectoryManager)

    def test_default_base_path(self):
        dm = get_directory_manager()
        assert isinstance(dm, DirectoryManager)


# ---------------------------------------------------------------------------
# _load_config with missing config file
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadConfig:
    """Tests for _load_config fallback behavior."""

    def test_missing_config_uses_defaults(self, tmp_path):
        dm = DirectoryManager(base_path=str(tmp_path))
        # Config file doesn't exist, should use defaults
        assert dm._config is not None
        assert "investigations_root" in dm._config

    def test_with_custom_config(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = {
            "investigations_root": "my_investigations",
            "study_subdirs": {},
        }
        (config_dir / "directory_structure.json").write_text(json.dumps(config), encoding="utf-8")
        dm = DirectoryManager(base_path=str(tmp_path))
        assert dm._config["investigations_root"] == "my_investigations"

    def test_invalid_json_uses_defaults(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "directory_structure.json").write_text("not valid json{{{", encoding="utf-8")
        dm = DirectoryManager(base_path=str(tmp_path))
        assert dm._config is not None
        assert "investigations_root" in dm._config


# ---------------------------------------------------------------------------
# _load_settings
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadSettings:
    """Tests for _load_settings."""

    def test_missing_settings(self, tmp_path):
        dm = DirectoryManager(base_path=str(tmp_path))
        dm._load_settings()
        assert dm._settings == {}

    def test_with_settings_file(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        settings = {"key": "value"}
        (config_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        dm = DirectoryManager(base_path=str(tmp_path))
        dm._load_settings()
        assert dm._settings == {"key": "value"}
