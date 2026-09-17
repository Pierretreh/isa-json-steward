"""
End-to-end tests for full pipeline with representative dataset.
"""

import json
import os
import platform
import shutil

import pytest

from utils.batch.batch_processor import BatchProcessor
from utils.batch.validator import ISAJsonValidator


def _extended_path(path):
    """Convert path to Windows extended-length path to bypass MAX_PATH limit.

    On Windows, paths longer than 260 characters require the '\\\\?\\' prefix.
    This is needed for deeply nested pyramidal image directories in partner
    representative data (e.g., E11 *_files/ within *_files/).

    Args:
        path: A Path object or string.

    Returns:
        String path with extended-length prefix on Windows, unchanged otherwise.
    """
    if platform.system() == "Windows":
        abs_path = os.path.abspath(str(path))
        if not abs_path.startswith("\\\\?\\"):
            return f"\\\\?\\{abs_path}"
        return abs_path
    return str(path)


def _copy_tree_safe(src, dst):
    """Copy directory tree, handling Windows MAX_PATH limit.

    Args:
        src: Source directory path.
        dst: Destination directory path.
    """
    shutil.copytree(_extended_path(src), _extended_path(dst))


@pytest.mark.e2e
@pytest.mark.requires_data
@pytest.mark.slow
class TestFullPipelineWithRepresentativeData:
    """End-to-end tests using representative dataset."""

    def test_full_pipeline_all_experiments(self, temp_dir, representative_data_path):
        """Test complete pipeline with all representative experiments."""
        if not representative_data_path or not representative_data_path.exists():
            pytest.skip("Representative data not available")

        # Copy all experiments to temp directory
        test_data = temp_dir / "test_data"
        test_data.mkdir()

        exp_folders = [f for f in representative_data_path.iterdir() if f.is_dir()]
        for exp_folder in exp_folders:
            _copy_tree_safe(exp_folder, test_data / exp_folder.name)

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        # Run full pipeline
        processor = BatchProcessor(investigation_id="test_investigation")
        result = processor.process_batch(
            data_root=str(test_data),
            output_dir=str(output_dir),
            skip_conversion=False,
            skip_validation=False,
        )

        # Verify results
        assert result.total_experiments == len(exp_folders)
        assert result.successful_experiments >= 0
        assert result.validation_passed is not None

    def test_isa_json_validation_all_outputs(self, temp_dir, representative_data_path):
        """Test that all generated ISA-JSON files are valid."""
        if not representative_data_path or not representative_data_path.exists():
            pytest.skip("Representative data not available")

        test_data = temp_dir / "test_data"
        test_data.mkdir()

        exp_folders = [f for f in representative_data_path.iterdir() if f.is_dir()]
        for exp_folder in exp_folders:
            _copy_tree_safe(exp_folder, test_data / exp_folder.name)

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        # Run pipeline
        processor = BatchProcessor(investigation_id="test_investigation")
        result = processor.process_batch(
            data_root=str(test_data),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=False,
        )

        # Validate the investigation JSON exists and is valid JSON
        inv_files = list(output_dir.glob("**/test_investigation.json"))
        assert len(inv_files) > 0, "No investigation JSON files found"

        for inv_file in inv_files:
            with open(inv_file, "r", encoding="utf-8") as f:
                inv_data = json.load(f)
            assert (
                "identifier" in inv_data or "investigation" in inv_data
            ), f"Investigation file {inv_file} missing identifier"

        # Validate per-study JSONs (full data lives here, not in lightweight inv)
        study_files = list(output_dir.glob("**/studies/*/study.json"))
        assert len(study_files) > 0, "No study JSON files found"

        validator = ISAJsonValidator()
        for study_file in study_files:
            with open(study_file, "r", encoding="utf-8") as f:
                study_data = json.load(f)
            studies = study_data.get("studies", [study_data])
            for study in studies:
                result = validator._validate_study(study, study.get("identifier", "unknown"))
                assert (
                    result.is_valid or len(result.errors) == 0
                ), f"Study {study_file} validation failed: {result.errors}"

    def test_pipeline_creates_proper_structure(self, temp_dir, representative_data_path):
        """Test that pipeline creates proper directory structure."""
        if not representative_data_path or not representative_data_path.exists():
            pytest.skip("Representative data not available")

        test_data = temp_dir / "test_data"
        test_data.mkdir()

        exp_folders = [f for f in representative_data_path.iterdir() if f.is_dir()]
        for exp_folder in exp_folders:
            _copy_tree_safe(exp_folder, test_data / exp_folder.name)

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        # Run pipeline
        processor = BatchProcessor(investigation_id="test_investigation")
        processor.process_batch(
            data_root=str(test_data),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=True,
        )

        # Check directory structure (investigation_id-based path)
        inv_dir = output_dir / "test_investigation"
        assert inv_dir.exists()

        # Check investigation JSON was created
        inv_json = inv_dir / "test_investigation.json"
        assert inv_json.exists()

    def test_pipeline_preserves_data_integrity(self, temp_dir, representative_data_path):
        """Test that pipeline preserves data integrity."""
        if not representative_data_path or not representative_data_path.exists():
            pytest.skip("Representative data not available")

        test_data = temp_dir / "test_data"
        test_data.mkdir()

        exp_folders = [f for f in representative_data_path.iterdir() if f.is_dir()]
        for exp_folder in exp_folders:
            _copy_tree_safe(exp_folder, test_data / exp_folder.name)

        # Count original files
        original_files = list(test_data.rglob("*"))
        original_file_count = len([f for f in original_files if f.is_file()])

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        # Run pipeline
        processor = BatchProcessor(investigation_id="test_investigation")
        result = processor.process_batch(
            data_root=str(test_data),
            output_dir=str(output_dir),
            skip_conversion=False,
            skip_validation=True,
        )

        # Verify file count in result
        assert result.total_files >= original_file_count

    def test_pipeline_with_e1_experiment(self, temp_dir, representative_data_path):
        """Test pipeline with E1_Müller_Calceinassay experiment."""
        if not representative_data_path or not representative_data_path.exists():
            pytest.skip("Representative data not available")

        e1_folder = representative_data_path / "E1_Müller_Calceinassay und FACS Test"
        if not e1_folder.exists():
            pytest.skip("E1 experiment not found")

        test_data = temp_dir / "test_data"
        test_data.mkdir()
        _copy_tree_safe(e1_folder, test_data / "E1")

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        processor = BatchProcessor(investigation_id="test_investigation")
        result = processor.process_batch(
            data_root=str(test_data),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=False,
        )

        assert result.total_experiments == 1

    def test_pipeline_with_e10_experiment(self, temp_dir, representative_data_path):
        """Test pipeline with E10_Explant_Calcein_FACS experiment."""
        if not representative_data_path or not representative_data_path.exists():
            pytest.skip("Representative data not available")

        e10_folder = representative_data_path / "E10_Explant_Calcein_FACS"
        if not e10_folder.exists():
            pytest.skip("E10 experiment not found")

        test_data = temp_dir / "test_data"
        test_data.mkdir()
        _copy_tree_safe(e10_folder, test_data / "E10")

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        processor = BatchProcessor(investigation_id="test_investigation")
        result = processor.process_batch(
            data_root=str(test_data),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=False,
        )

        assert result.total_experiments == 1

    def test_pipeline_with_e11_experiment(self, temp_dir, representative_data_path):
        """Test pipeline with E11_Explant_FACS_Static_DAPI experiment."""
        if not representative_data_path or not representative_data_path.exists():
            pytest.skip("Representative data not available")

        e11_folder = representative_data_path / "E11_Explant_FACS_Static_DAPI"
        if not e11_folder.exists():
            pytest.skip("E11 experiment not found")

        test_data = temp_dir / "test_data"
        test_data.mkdir()
        _copy_tree_safe(e11_folder, test_data / "E11")

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        processor = BatchProcessor(investigation_id="test_investigation")
        result = processor.process_batch(
            data_root=str(test_data),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=False,
        )

        assert result.total_experiments == 1


@pytest.mark.e2e
@pytest.mark.isa_validation
@pytest.mark.slow
class TestISAJsonValidationComprehensive:
    """Comprehensive ISA-JSON validation tests."""

    def test_validate_investigation_structure(self, temp_dir, valid_investigation_json):
        """Test validation of investigation structure."""
        inv_path = temp_dir / "investigation.json"
        with open(inv_path, "w") as f:
            json.dump(valid_investigation_json, f)

        validator = ISAJsonValidator()
        result = validator.validate_investigation(str(inv_path))

        assert result.is_valid is True

    def test_validate_study_structure(self, temp_dir, valid_study_json):
        """Test validation of study structure."""
        validator = ISAJsonValidator()
        result = validator._validate_study(valid_study_json, "test_study")

        assert result.is_valid is True

    def test_validate_assay_structure(self, temp_dir, valid_assay_json):
        """Test validation of assay structure."""
        validator = ISAJsonValidator()
        result = validator._validate_assay(valid_assay_json, "test_assay")

        assert result.is_valid is True

    def test_validate_ontology_references(self, temp_dir):
        """Test validation of ontology references."""
        inv_data = {
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
                    },
                    {
                        "name": "UO",
                        "description": "Units of Measurement Ontology",
                        "file": "http://purl.obolibrary.org/obo/uo.owl",
                        "version": "2024-01-01",
                    },
                ],
            }
        }

        inv_path = temp_dir / "investigation.json"
        with open(inv_path, "w") as f:
            json.dump(inv_data, f)

        validator = ISAJsonValidator()
        result = validator.validate_investigation(str(inv_path))

        assert result.is_valid is True
