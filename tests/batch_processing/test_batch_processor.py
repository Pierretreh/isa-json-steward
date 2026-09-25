"""
Unit tests for BatchProcessor component.
"""

import threading

import pytest

from utils.batch.batch_processor import BatchProcessingResult, BatchProcessor


@pytest.mark.unit
@pytest.mark.batch_component
class TestBatchProcessor:
    """Tests for BatchProcessor class."""

    def test_initialization(self, batch_processor):
        """Test batch processor initialization."""
        assert isinstance(batch_processor, BatchProcessor)
        assert batch_processor.investigation_id == "test_inv"

    def test_initialization_with_inv_inm(self):
        """Test batch processor initialization with inv_inm path."""
        processor = BatchProcessor(investigation_id="test_inv", inv_inm_path="/path/to/inv_inm")

        assert processor.investigation_id == "test_inv"
        assert processor.inv_inm_path == "/path/to/inv_inm"

    def test_process_batch_empty_directory(self, batch_processor, temp_dir):
        """Test processing batch with empty directory."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        result = batch_processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=True,
        )

        assert isinstance(result, BatchProcessingResult)
        assert result.total_experiments == 0
        assert result.successful_experiments == 0

    def test_process_batch_single_experiment(self, batch_processor, temp_dir):
        """Test processing batch with single experiment."""
        # Create experiment folder with E-prefix (project naming convention)
        exp_dir = temp_dir / "E1_test_experiment"
        exp_dir.mkdir()
        (exp_dir / "data.csv").write_text("col1,col2\nval1,val2\n")

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        result = batch_processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=True,
        )

        assert isinstance(result, BatchProcessingResult)
        assert result.total_experiments == 1

    def test_process_batch_multiple_experiments(self, batch_processor, temp_dir):
        """Test processing batch with multiple experiments."""
        # Create multiple experiment folders with E-prefix
        for i in range(3):
            exp_dir = temp_dir / f"E{i+1}_experiment_{i}"
            exp_dir.mkdir()
            (exp_dir / f"data_{i}.csv").write_text(f"data{i}\n")

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        result = batch_processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=True,
        )

        assert isinstance(result, BatchProcessingResult)
        assert result.total_experiments == 3

    def test_process_batch_skip_conversion(self, batch_processor, temp_dir):
        """Test processing batch with conversion skipped."""
        exp_dir = temp_dir / "test_exp"
        exp_dir.mkdir()
        (exp_dir / "data.csv").write_text("data\n")

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        result = batch_processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=True,
        )

        assert result.converted_files == 0

    def test_process_batch_skip_validation(self, batch_processor, temp_dir):
        """Test processing batch with validation skipped."""
        exp_dir = temp_dir / "test_exp"
        exp_dir.mkdir()
        (exp_dir / "data.csv").write_text("data\n")

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        result = batch_processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=True,
        )

        # When validation is skipped, validation_passed should be True by default
        assert result.validation_passed is True

    def test_process_batch_with_conversion(self, batch_processor, temp_dir):
        """Test processing batch with conversion enabled."""
        exp_dir = temp_dir / "test_exp"
        exp_dir.mkdir()
        # Create a file that might need conversion
        (exp_dir / "image.tiff").write_bytes(b"fake_tiff")

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        result = batch_processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=False,
            skip_validation=True,
        )

        assert isinstance(result, BatchProcessingResult)
        # Conversion results depend on FormatConverter implementation

    def test_process_batch_creates_investigation_file(self, batch_processor, temp_dir):
        """Test that batch processing creates investigation file."""
        exp_dir = temp_dir / "E1_test_exp"
        exp_dir.mkdir()
        (exp_dir / "data.csv").write_text("data\n")

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        batch_processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=True,
        )

        # Check if investigation file was created
        # File organizer saves as {output_dir}/{investigation_id}/{investigation_id}.json
        inv_files = list(output_dir.glob("**/*.json"))
        assert len(inv_files) > 0

    def test_process_batch_populates_classifications(self, batch_processor, temp_dir):
        """Test that per-experiment classifications are captured (D5)."""
        exp_dir = temp_dir / "E1_test_exp"
        exp_dir.mkdir()
        (exp_dir / "data.csv").write_text("data\n")

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        result = batch_processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=True,
        )

        assert result.classifications, "expected at least one classification"
        entry = result.classifications["E1"]
        assert "type" in entry
        assert "template" in entry
        assert "confidence" in entry

    def test_process_batch_cancel_event_short_circuits(self, batch_processor, temp_dir):
        """Test that a pre-set cancel_event stops the run before Step 2 (D5)."""
        exp_dir = temp_dir / "E1_test_exp"
        exp_dir.mkdir()
        (exp_dir / "data.csv").write_text("data\n")

        output_dir = temp_dir / "output"
        output_dir.mkdir()

        cancel_event = threading.Event()
        cancel_event.set()

        result = batch_processor.process_batch(
            data_root=str(temp_dir),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=True,
            cancel_event=cancel_event,
        )

        assert "Pipeline cancelled by user" in result.errors
        assert result.classifications == {}
        # The run stopped before Step 6/7, so no report or study JSON was written.
        assert not (output_dir / "processing_report.json").exists()


@pytest.mark.unit
@pytest.mark.batch_component
class TestBatchProcessingResult:
    """Tests for BatchProcessingResult dataclass."""

    def test_batch_processing_result_creation(self):
        """Test BatchProcessingResult creation."""
        result = BatchProcessingResult(
            total_experiments=5,
            successful_experiments=4,
            failed_experiments=1,
            total_files=10,
            converted_files=8,
            failed_conversions=2,
            validation_passed=True,
            processing_time_seconds=10.5,
        )

        assert result.total_experiments == 5
        assert result.successful_experiments == 4
        assert result.failed_experiments == 1
        assert result.total_files == 10
        assert result.converted_files == 8
        assert result.failed_conversions == 2
        assert result.validation_passed is True
        assert result.processing_time_seconds == 10.5

    def test_batch_processing_result_with_errors(self):
        """Test BatchProcessingResult with errors."""
        result = BatchProcessingResult(
            total_experiments=1,
            successful_experiments=0,
            failed_experiments=1,
            total_files=0,
            converted_files=0,
            failed_conversions=0,
            validation_passed=False,
            processing_time_seconds=1.0,
            errors=["File not found", "Invalid format"],
        )

        assert len(result.errors) == 2
        assert "File not found" in result.errors
        assert result.validation_passed is False

    def test_batch_processing_result_with_warnings(self):
        """Test BatchProcessingResult with warnings."""
        result = BatchProcessingResult(
            total_experiments=1,
            successful_experiments=1,
            failed_experiments=0,
            total_files=1,
            converted_files=1,
            failed_conversions=0,
            validation_passed=True,
            processing_time_seconds=1.0,
            warnings=["Low confidence classification"],
        )

        assert len(result.warnings) == 1
        assert "Low confidence classification" in result.warnings

    def test_batch_processing_result_with_info(self):
        """Test BatchProcessingResult with info messages."""
        result = BatchProcessingResult(
            total_experiments=1,
            successful_experiments=1,
            failed_experiments=0,
            total_files=1,
            converted_files=1,
            failed_conversions=0,
            validation_passed=True,
            processing_time_seconds=1.0,
            info=["Processing started", "Processing completed"],
        )

        assert len(result.info) == 2
        assert "Processing started" in result.info
