"""
Shared fixtures and configuration for pytest tests.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from utils.directory_manager import DirectoryManager
from utils.file_manager import FileManager
from utils.material_manager import MaterialManager
from utils.process_sequence_manager import ProcessSequenceManager


def _discover_profile_dir() -> Optional[Path]:
    """Discover the profile directory for testing.

    Priority:
    1. ISA_STEWARD_PROFILE environment variable
    2. Any *-profile/ directory in the project root
    3. None (profile-dependent tests will skip)
    """
    # 1. Environment variable
    env = os.environ.get("ISA_STEWARD_PROFILE")
    if env and Path(env).is_dir():
        return Path(env)

    # 2. Auto-discover *-profile/ directories
    project_root = Path(__file__).parent.parent
    profile_dirs = sorted(project_root.glob("*-profile"))
    if profile_dirs:
        return profile_dirs[0]

    return None


# ----------------------------------------------------------------------
# Fixtures for temporary directories
# ----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_directory_manager(tmp_path, monkeypatch):
    """Safety net: ensure DirectoryManager never writes to the real project root during tests.

    This monkeypatches DirectoryManager.__init__ so that when no explicit base_path
    is given, it uses a per-test temp directory instead of resolving via __file__
    to the real project root. This prevents tests from creating investigation
    directories that pollute the user's GUI.
    """
    from utils.directory_manager import DirectoryManager

    original_init = DirectoryManager.__init__

    def _patched_init(self, base_path=None, config_path=None):
        if base_path is None:
            base_path = str(tmp_path)
        original_init(self, base_path=base_path, config_path=config_path)

    monkeypatch.setattr(DirectoryManager, "__init__", _patched_init)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_study_dir(temp_dir):
    """Create a temporary study directory structure."""
    study_dir = temp_dir / "investigations" / "inv_1" / "studies" / "study_1"
    study_dir.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    (study_dir / "files").mkdir(exist_ok=True)
    (study_dir / "files" / "original").mkdir(exist_ok=True)
    (study_dir / "files" / "converted").mkdir(exist_ok=True)

    return study_dir


# ----------------------------------------------------------------------
# Fixtures for test data
# ----------------------------------------------------------------------


@pytest.fixture
def sample_study_data() -> Dict[str, Any]:
    """Sample study data for testing."""
    return {
        "title": "Test Study",
        "description": "A test study for unit testing",
        "investigation_name": "Test Investigation",
        "investigation_description": "Test investigation description",
        "materials": {
            "sources": [
                {
                    "@id": "/investigations/inv_1/studies/study_1#source_bacteria",
                    "name": "E. coli ClearColi",
                    "characteristics": [
                        {
                            "category": {
                                "annotationValue": "Organism",
                                "termSource": "NCBITaxon",
                                "termAccession": "http://purl.obolibrary.org/obo/NCBITaxon_562",
                            },
                            "value": "Escherichia coli",
                        }
                    ],
                }
            ],
            "samples": [],
            "otherMaterials": [],
        },
        "protocols": [
            {
                "@id": "/investigations/inv_1/studies/study_1#protocol_transformation",
                "name": "Transformation",
                "protocolType": {
                    "annotationValue": "transformation",
                    "termSource": "OBI",
                    "termAccession": "http://purl.obolibrary.org/obo/OBI_0000769",
                },
                "description": "Bacterial transformation protocol",
            }
        ],
        "process_sequence": {"processes": []},
    }


@pytest.fixture
def sample_material_data() -> Dict[str, Any]:
    """Sample material data for testing."""
    return {
        "@id": "/investigations/inv_1/studies/study_1#source_test",
        "name": "Test Material",
        "characteristics": [
            {
                "category": {
                    "annotationValue": "Test Category",
                    "termSource": "TEST",
                    "termAccession": "http://test.org/TEST_001",
                },
                "value": "Test Value",
            }
        ],
    }


@pytest.fixture
def sample_process_data() -> Dict[str, Any]:
    """Sample process data for testing."""
    return {
        "id": "process_1",
        "name": "Test Process",
        "protocol_ref": "/investigations/inv_1/studies/study_1#protocol_transformation",
        "inputs": [
            {
                "material_id": "/investigations/inv_1/studies/study_1#source_bacteria",
                "name": "E. coli ClearColi",
                "materialType": "source",
            }
        ],
        "outputs": [
            {
                "material_id": "/investigations/inv_1/studies/study_1#sample_transformed",
                "name": "Transformed Cells",
                "materialType": "sample",
            }
        ],
        "parameterValues": [
            {
                "parameterName": {
                    "annotationValue": "temperature",
                    "termSource": "UO",
                    "termAccession": "http://purl.obolibrary.org/obo/UO_0000002",
                },
                "value": {
                    "value": "37",
                    "unit": {
                        "annotationValue": "degree celsius",
                        "termSource": "UO",
                        "termAccession": "http://purl.obolibrary.org/obo/UO_0000027",
                    },
                },
            }
        ],
    }


# ----------------------------------------------------------------------
# Fixtures for manager instances
# ----------------------------------------------------------------------


@pytest.fixture
def directory_manager(temp_dir):
    """Create a DirectoryManager instance with temporary directory."""
    return DirectoryManager(base_path=str(temp_dir))


@pytest.fixture
def file_manager(temp_study_dir):
    """Create a FileManager instance with temporary study directory."""
    return FileManager(investigations_root=temp_study_dir.parent.parent.parent)


@pytest.fixture
def material_manager(sample_study_data, directory_manager):
    """Create a MaterialManager instance with sample data."""
    return MaterialManager(
        study_data=sample_study_data,
        directory_manager=directory_manager,
        investigation_id="inv_1",
        study_id="study_1",
    )


@pytest.fixture
def process_sequence_manager(sample_study_data, material_manager):
    """Create a ProcessSequenceManager instance with sample data."""
    return ProcessSequenceManager(study_data=sample_study_data, material_manager=material_manager)


# ----------------------------------------------------------------------
# Fixtures for file operations
# ----------------------------------------------------------------------


@pytest.fixture
def sample_text_file(temp_dir):
    """Create a sample text file for testing."""
    file_path = temp_dir / "test.txt"
    file_path.write_text("Test content", encoding="utf-8")
    return file_path


@pytest.fixture
def sample_json_file(temp_dir):
    """Create a sample JSON file for testing."""
    file_path = temp_dir / "test.json"
    data = {"key": "value", "number": 42}
    file_path.write_text(json.dumps(data), encoding="utf-8")
    return file_path


# ----------------------------------------------------------------------
# Fixtures for batch processing tests
# ----------------------------------------------------------------------


@pytest.fixture
def representative_data_path():
    """Path to representative dataset."""
    path = Path("references/partner representative data")
    return path if path.exists() else None


@pytest.fixture
def sample_experiment_folder(temp_dir):
    """Create a sample experiment folder for testing."""
    exp_path = temp_dir / "test_experiment"
    exp_path.mkdir(parents=True, exist_ok=True)

    # Create sample files
    (exp_path / "sample_data.csv").write_text("col1,col2\nval1,val2\n", encoding="utf-8")
    (exp_path / "metadata.json").write_text(
        json.dumps({"experiment_type": "test", "date": "2024-01-01"}), encoding="utf-8"
    )

    return exp_path


@pytest.fixture
def batch_processor():
    """Batch processor fixture."""
    from utils.batch.batch_processor import BatchProcessor

    return BatchProcessor(investigation_id="test_inv")


@pytest.fixture
def folder_scanner(temp_dir):
    """Folder scanner fixture."""
    from utils.batch.folder_scanner import FolderScanner

    return FolderScanner(str(temp_dir))


@pytest.fixture
def experiment_classifier():
    """Experiment classifier fixture."""
    from utils.batch.experiment_classifier import ExperimentClassifier

    return ExperimentClassifier()


@pytest.fixture
def metadata_extractor():
    """Metadata extractor fixture."""
    from utils.batch.metadata_extractor import MetadataExtractor

    return MetadataExtractor()


@pytest.fixture
def format_converter():
    """Format converter fixture."""
    from utils.batch.format_converter import FormatConverter

    return FormatConverter()


@pytest.fixture
def isa_json_generator():
    """ISA-JSON generator fixture with template access."""
    from utils.batch.isa_json_generator import ISAJsonGenerator

    profile_dir = _discover_profile_dir()
    templates_root = None

    # Try profile directory first
    if profile_dir:
        candidate = profile_dir / "templates" / "assay_templates"
        if candidate.is_dir():
            templates_root = str(candidate)

    # Fall back to local templates/
    if templates_root is None:
        local = Path(__file__).parent.parent / "templates" / "assay_templates"
        if local.is_dir():
            templates_root = str(local)

    if templates_root is None:
        pytest.skip("No templates directory found (no profile or local templates)")

    return ISAJsonGenerator(templates_root=templates_root)


@pytest.fixture
def templates_dir():
    """Return the path to templates directory, checking profile first."""
    profile_dir = _discover_profile_dir()

    # Check profile templates/ first
    if profile_dir:
        profile = profile_dir / "templates"
        if profile.is_dir():
            return str(profile)

    # Check local templates/
    local = Path(__file__).parent.parent / "templates"
    if local.is_dir():
        return str(local)

    pytest.skip("No templates directory found")


@pytest.fixture
def profile_scripts_dir():
    """Path to scripts directory in the profile, if available."""
    profile_dir = _discover_profile_dir()
    if profile_dir is None:
        return None
    scripts_dir = profile_dir / "scripts"
    if scripts_dir.is_dir():
        return scripts_dir
    return None


@pytest.fixture
def file_organizer():
    """File organizer fixture."""
    from utils.batch.file_organizer import FileOrganizer

    return FileOrganizer(investigation_id="test_inv")


@pytest.fixture
def isa_validator():
    """ISA-JSON validator fixture."""
    from utils.batch.validator import ISAJsonValidator

    return ISAJsonValidator()


# ----------------------------------------------------------------------
# Fixtures for ISA-JSON validation tests
# ----------------------------------------------------------------------


@pytest.fixture
def valid_investigation_json():
    """Valid investigation JSON for testing."""
    return {
        "investigation": {
            "@id": "https://example.org/investigations/test_inv",
            "identifier": "test_inv",
            "title": "Test Investigation",
            "description": "Test description",
            "submissionDate": "2024-01-01",
            "publicReleaseDate": "2025-01-01",
            "studies": [],
            "ontologySourceReferences": [
                {
                    "name": "OBI",
                    "description": "Ontology for Biomedical Investigations",
                    "file": "http://purl.obolibrary.org/obo/obi.owl",
                    "version": "2024-01-01",
                }
            ],
        }
    }


@pytest.fixture
def valid_study_json():
    """Valid study JSON for testing."""
    return {
        "@id": "https://example.org/investigations/test_inv/studies/study_1",
        "identifier": "study_1",
        "title": "Test Study",
        "description": "Test study description",
        "submissionDate": "2024-01-01",
        "publicReleaseDate": "2025-01-01",
        "designDescriptors": [
            {
                "annotationValue": "intervention design",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000115",
            }
        ],
        "materials": {"sources": [], "samples": [], "otherMaterials": []},
        "protocols": [],
        "assays": [],
        "processSequence": [],
    }


@pytest.fixture
def valid_assay_json():
    """Valid assay JSON for testing."""
    return {
        "@id": "https://example.org/investigations/test_inv/studies/study_1/assays/assay_1",
        "measurementType": {
            "annotationValue": "gene expression profiling",
            "termSource": "EFO",
            "termAccession": "http://www.ebi.ac.uk/efo/EFO_0003067",
        },
        "technologyType": {
            "annotationValue": "DNA microarray",
            "termSource": "EFO",
            "termAccession": "http://www.ebi.ac.uk/efo/EFO_0002692",
        },
        "technologyPlatform": "Affymetrix",
        "dataFiles": [],
        "materials": {"samples": [], "otherMaterials": []},
        "processSequence": [],
    }


@pytest.fixture
def invalid_investigation_json():
    """Invalid investigation JSON for testing (missing required fields)."""
    return {
        "investigation": {
            "@id": "https://example.org/investigations/invalid_inv",
            # Missing: identifier, title, description, submissionDate
            "studies": [],
            "ontologySourceReferences": [],
        }
    }


# ----------------------------------------------------------------------
# Fixtures for GUI tests
# ----------------------------------------------------------------------


@pytest.fixture
def qtbot(qtbot):
    """QtBot fixture for GUI testing."""
    return qtbot


@pytest.fixture
def main_window(qtbot):
    """Main window fixture for GUI testing."""
    try:
        import sys

        from gui.app import StewardApp
        from gui.main_window import MainWindow

        app = StewardApp(sys.argv)
        window = MainWindow(app)
        qtbot.addWidget(window)
        return window
    except (ImportError, OSError):
        pytest.skip("PyQt6 not installed or GUI components not available")


@pytest.fixture
def sample_investigation_data():
    """Sample investigation data for GUI testing."""
    return {
        "@id": "https://example.org/investigations/inv_1",
        "identifier": "inv_1",
        "title": "Test Investigation",
        "description": "Test investigation for GUI testing",
        "submissionDate": "2024-01-01",
        "publicReleaseDate": "2025-01-01",
        "studies": [],
        "ontologySourceReferences": [
            {
                "name": "OBI",
                "description": "Ontology for Biomedical Investigations",
                "file": "http://purl.obolibrary.org/obo/obi.owl",
                "version": "2024-01-01",
            }
        ],
    }


# ----------------------------------------------------------------------
# Pytest configuration
# ----------------------------------------------------------------------
# Note: Markers are configured in pytest.ini at the project root
# to avoid duplication and ensure consistency across the test suite.
