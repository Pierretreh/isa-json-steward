"""
Integration tests for single experiment batch processing pipeline.
"""

import json

import pytest

from utils.batch.batch_processor import BatchProcessor


@pytest.mark.integration
@pytest.mark.batch_pipeline
@pytest.mark.requires_data
class TestSingleExperimentPipeline:
    """Integration tests for processing a single experiment."""

    def test_full_pipeline_single_experiment(self, temp_dir, representative_data_path):
        """Test complete pipeline with single experiment."""
        if not representative_data_path or not representative_data_path.exists():
            pytest.skip("Representative data not available")

        # Find first experiment folder
        exp_folders = [f for f in representative_data_path.iterdir() if f.is_dir()]
        if not exp_folders:
            pytest.skip("No experiment folders found")

        # Copy experiment to temp directory
        import shutil

        test_exp = temp_dir / exp_folders[0].name
        shutil.copytree(exp_folders[0], test_exp)

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        # Run batch processor
        processor = BatchProcessor(investigation_id="test_inv")
        result = processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=False,
        )

        # Verify results
        assert result.total_experiments == 1
        assert result.successful_experiments >= 0

        # Check investigation file was created (named {investigation_id}.json)
        inv_files = list(output_dir.glob("**/test_inv.json"))
        assert len(inv_files) > 0

    def test_pipeline_generates_valid_isa_json(self, temp_dir, representative_data_path):
        """Test that pipeline generates valid ISA-JSON."""
        if not representative_data_path or not representative_data_path.exists():
            pytest.skip("Representative data not available")

        exp_folders = [f for f in representative_data_path.iterdir() if f.is_dir()]
        if not exp_folders:
            pytest.skip("No experiment folders found")

        import shutil

        test_exp = temp_dir / exp_folders[0].name
        shutil.copytree(exp_folders[0], test_exp)

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        processor = BatchProcessor(investigation_id="test_inv")
        processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=False,
        )

        # Find investigation file (named {investigation_id}.json)
        inv_files = list(output_dir.glob("**/test_inv.json"))
        assert len(inv_files) > 0

        # Validate ISA-JSON structure (flat format, not wrapped)
        with open(inv_files[0], "r") as f:
            data = json.load(f)
            assert "identifier" in data
            assert data["identifier"] == "test_inv"
            assert "title" in data
            assert "studies" in data
            assert isinstance(data["studies"], list)

    def test_pipeline_with_validation(self, temp_dir, representative_data_path):
        """Test pipeline with validation enabled."""
        if not representative_data_path or not representative_data_path.exists():
            pytest.skip("Representative data not available")

        exp_folders = [f for f in representative_data_path.iterdir() if f.is_dir()]
        if not exp_folders:
            pytest.skip("No experiment folders found")

        import shutil

        test_exp = temp_dir / exp_folders[0].name
        shutil.copytree(exp_folders[0], test_exp)

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        processor = BatchProcessor(investigation_id="test_inv")
        result = processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=False,
        )

        # Validation should have been performed
        assert result.validation_passed is not None

    def test_pipeline_creates_directory_structure(self, temp_dir, representative_data_path):
        """Test that pipeline creates proper directory structure."""
        if not representative_data_path or not representative_data_path.exists():
            pytest.skip("Representative data not available")

        exp_folders = [f for f in representative_data_path.iterdir() if f.is_dir()]
        if not exp_folders:
            pytest.skip("No experiment folders found")

        import shutil

        test_exp = temp_dir / exp_folders[0].name
        shutil.copytree(exp_folders[0], test_exp)

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        processor = BatchProcessor(investigation_id="test_inv")
        processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=True,
        )

        # Check for expected directories (investigation_id-based path)
        inv_dir = output_dir / "test_inv"
        assert inv_dir.exists()

        # Check studies subdirectory exists
        studies_dir = inv_dir / "studies"
        assert studies_dir.exists()


@pytest.mark.integration
@pytest.mark.batch_pipeline
class TestPipelineErrorHandling:
    """Integration tests for pipeline error handling."""

    def test_pipeline_with_missing_files(self, temp_dir):
        """Test pipeline handling of missing files."""
        # Create experiment with missing referenced files
        exp_dir = temp_dir / "broken_exp"
        exp_dir.mkdir()
        (exp_dir / "metadata.json").write_text('{"files": ["missing.txt"]}')

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        processor = BatchProcessor(investigation_id="test_inv")
        result = processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=True,
        )

        # Should handle gracefully
        assert result is not None

    def test_pipeline_with_corrupted_files(self, temp_dir):
        """Test pipeline handling of corrupted files."""
        exp_dir = temp_dir / "corrupted_exp"
        exp_dir.mkdir()
        (exp_dir / "corrupted.json").write_text("{invalid json")

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        processor = BatchProcessor(investigation_id="test_inv")
        result = processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=True,
        )

        # Should handle gracefully
        assert result is not None
