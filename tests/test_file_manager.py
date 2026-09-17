"""
Unit tests for FileManager.
"""

from pathlib import Path

import pytest

from utils.file_manager import FileManager


@pytest.mark.unit
@pytest.mark.file_ops
class TestFileManager:
    """Tests for FileManager class."""

    def test_initialization(self, temp_study_dir):
        """Test that FileManager initializes correctly."""
        fm = FileManager(investigations_root=temp_study_dir.parent.parent.parent)

        assert fm.investigations_root == temp_study_dir.parent.parent.parent
        assert fm.converter is not None

    def test_get_study_files_dir(self, file_manager):
        """Test getting study files directory."""
        path = file_manager.get_study_files_dir("inv_1", "study_1")

        assert "inv_1" in str(path)
        assert "study_1" in str(path)
        assert "files" in str(path)

    def test_get_original_files_dir(self, file_manager):
        """Test getting original files directory."""
        path = file_manager.get_original_files_dir("inv_1", "study_1")

        assert "original" in str(path)

    def test_get_converted_files_dir(self, file_manager):
        """Test getting converted files directory."""
        path = file_manager.get_converted_files_dir("inv_1", "study_1")

        assert "converted" in str(path)

    def test_ensure_study_directories(self, file_manager, temp_study_dir):
        """Test that study directories are created."""
        file_manager.ensure_study_directories("inv_1", "study_1")

        assert (temp_study_dir / "files").exists()
        assert (temp_study_dir / "files" / "original").exists()
        assert (temp_study_dir / "files" / "converted").exists()

    def test_upload_file(self, file_manager, sample_text_file):
        """Test uploading a file."""
        result = file_manager.upload_file(
            investigation_id="inv_1",
            study_id="study_1",
            file_path=sample_text_file,
            file_type="data",
        )

        assert result is not None
        assert "filename" in result
        assert "original_path" in result
        assert "converted_path" in result

    def test_get_file_type(self, file_manager):
        """Test file type detection."""
        # Test image file
        assert file_manager.get_file_type(Path("test.jpg")) == "image"
        assert file_manager.get_file_type(Path("test.png")) == "image"

        # Test data file
        assert file_manager.get_file_type(Path("test.xlsx")) == "data"
        assert file_manager.get_file_type(Path("test.csv")) == "data"

        # Test sequencing file
        assert file_manager.get_file_type(Path("test.fastq")) == "sequencing"
        assert file_manager.get_file_type(Path("test.ab1")) == "sequencing"

        # Test unknown file
        assert file_manager.get_file_type(Path("test.unknown")) is None

    def test_delete_file(self, file_manager, sample_text_file):
        """Test deleting a file."""
        # First upload a file
        upload_result = file_manager.upload_file(
            investigation_id="inv_1",
            study_id="study_1",
            file_path=sample_text_file,
            file_type="data",
        )

        # Then delete it
        result = file_manager.delete_file(
            investigation_id="inv_1", study_id="study_1", file_id=upload_result["file_id"]
        )

        assert result is True

    def test_delete_file_not_found(self, file_manager):
        """Test deleting non-existent file returns False."""
        result = file_manager.delete_file(
            investigation_id="inv_1", study_id="study_1", file_id="nonexistent_file_id"
        )

        assert result is False

    def test_list_files(self, file_manager, sample_text_file):
        """Test listing files."""
        # Upload a file first
        file_manager.upload_file(
            investigation_id="inv_1",
            study_id="study_1",
            file_path=sample_text_file,
            file_type="data",
        )

        # List files
        files = file_manager.list_files("inv_1", "study_1")

        assert len(files) >= 1
        assert any(f["filename"] == "test.txt" for f in files)


@pytest.mark.unit
@pytest.mark.file_ops
class TestFileValidation:
    """Tests for file validation in FileManager."""

    def test_validate_file_size_valid(self, file_manager, sample_text_file):
        """Test that valid file size passes validation."""
        is_valid, message = file_manager.validate_file_size(sample_text_file)

        assert is_valid is True
        assert message is None

    def test_validate_file_size_too_large(self, file_manager, temp_dir):
        """Test that oversized files fail validation."""
        # Create a file larger than limit (simulated)
        large_file = temp_dir / "large.txt"
        large_file.write_text("x" * (100 * 1024 * 1024 + 1))  # > 100MB

        is_valid, message = file_manager.validate_file_size(large_file)

        assert is_valid is False
        assert "too large" in message.lower() or "exceeds" in message.lower()

    def test_validate_file_extension_valid(self, file_manager):
        """Test that valid extensions pass validation."""
        valid_extensions = [".jpg", ".png", ".pdf", ".xlsx", ".csv"]

        for ext in valid_extensions:
            is_valid, message = file_manager.validate_file_extension(Path(f"test{ext}"))
            assert is_valid is True

    def test_validate_file_extension_invalid(self, file_manager):
        """Test that invalid extensions fail validation."""
        invalid_extensions = [".exe", ".bat", ".sh", ".cmd"]

        for ext in invalid_extensions:
            is_valid, message = file_manager.validate_file_extension(Path(f"test{ext}"))
            assert is_valid is False
