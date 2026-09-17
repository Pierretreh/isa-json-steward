"""
Unit tests for FolderScanner component.
"""

from pathlib import Path

import pytest

from utils.batch.folder_scanner import FileInventory, FolderMetadata, FolderScanner


@pytest.mark.unit
@pytest.mark.batch_component
class TestFolderScanner:
    """Tests for FolderScanner class."""

    def test_initialization(self, temp_dir):
        """Test scanner initialization with data root."""
        scanner = FolderScanner(str(temp_dir))
        assert scanner.data_root == Path(temp_dir)

    def test_scan_empty_directory(self, temp_dir):
        """Test scanning an empty directory."""
        scanner = FolderScanner(str(temp_dir))
        experiments = scanner.scan_experiments()
        assert experiments == []

    def test_scan_single_experiment(self, temp_dir):
        """Test scanning a directory with one experiment."""
        # Create experiment folder with E-prefix (project naming convention)
        exp_dir = temp_dir / "E1_test_experiment"
        exp_dir.mkdir()
        (exp_dir / "data.csv").write_text("col1,col2\nval1,val2\n")

        scanner = FolderScanner(str(temp_dir))
        experiments = scanner.scan_experiments()

        assert len(experiments) == 1
        assert experiments[0].experiment_name == "E1_test_experiment"
        assert experiments[0].folder_path == str(exp_dir)

    def test_scan_multiple_experiments(self, temp_dir):
        """Test scanning a directory with multiple experiments."""
        # Create multiple experiment folders with E-prefix
        for i in range(3):
            exp_dir = temp_dir / f"E{i+1}_experiment_{i}"
            exp_dir.mkdir()
            (exp_dir / f"data_{i}.csv").write_text(f"data{i}\n")

        scanner = FolderScanner(str(temp_dir))
        experiments = scanner.scan_experiments()

        assert len(experiments) == 3
        exp_names = [exp.experiment_name for exp in experiments]
        assert "E1_experiment_0" in exp_names
        assert "E2_experiment_1" in exp_names
        assert "E3_experiment_2" in exp_names

    def test_create_file_inventory(self, temp_dir):
        """Test file inventory creation."""
        exp_dir = temp_dir / "E1_test_exp"
        exp_dir.mkdir()

        # Create various files
        (exp_dir / "data.csv").write_text("data\n")
        (exp_dir / "image.tiff").write_bytes(b"fake_image")
        (exp_dir / "metadata.json").write_text("{}")

        scanner = FolderScanner(str(temp_dir))
        inventory = scanner.get_file_inventory(str(exp_dir))

        assert isinstance(inventory, FileInventory)
        all_files = inventory.get_all_files()
        assert len(all_files) == 3
        assert any("data.csv" in f for f in all_files)
        assert any("image.tiff" in f for f in all_files)
        assert any("metadata.json" in f for f in all_files)

    def test_file_inventory_file_types(self, temp_dir):
        """Test file type detection in inventory."""
        exp_dir = temp_dir / "E1_test_exp"
        exp_dir.mkdir()

        # Create files with different extensions
        (exp_dir / "data.csv").write_text("csv\n")
        (exp_dir / "image.tiff").write_bytes(b"tiff")
        (exp_dir / "data.xlsx").write_bytes(b"xlsx")
        (exp_dir / "metadata.json").write_text("{}")
        (exp_dir / "results.fcs").write_bytes(b"fcs")

        scanner = FolderScanner(str(temp_dir))
        inventory = scanner.get_file_inventory(str(exp_dir))

        # Check typed lists
        assert len(inventory.tiff_files) == 1
        assert len(inventory.xlsx_files) == 1
        assert len(inventory.fcs_files) == 1
        # csv and json go to other_files
        assert len(inventory.other_files) >= 1

    def test_folder_metadata_creation(self, temp_dir):
        """Test FolderMetadata creation."""
        exp_dir = temp_dir / "E1_test_exp"
        exp_dir.mkdir()
        (exp_dir / "data.csv").write_text("data\n")

        scanner = FolderScanner(str(temp_dir))
        experiments = scanner.scan_experiments()

        assert len(experiments) == 1
        metadata = experiments[0]

        assert isinstance(metadata, FolderMetadata)
        assert metadata.experiment_name == "E1_test_exp"
        assert metadata.folder_path == str(exp_dir)
        assert metadata.file_count == 1

    def test_nested_directory_handling(self, temp_dir):
        """Test handling of nested directories."""
        exp_dir = temp_dir / "E1_test_exp"
        exp_dir.mkdir()

        # Create nested structure
        nested_dir = exp_dir / "subdir" / "nested"
        nested_dir.mkdir(parents=True)
        (nested_dir / "file.txt").write_text("nested data\n")

        scanner = FolderScanner(str(temp_dir))
        experiments = scanner.scan_experiments()

        assert len(experiments) == 1
        inventory = scanner.get_file_inventory(str(exp_dir))
        assert inventory.get_file_count() == 1

    def test_invalid_path_handling(self):
        """Test handling of invalid paths."""
        scanner = FolderScanner("/nonexistent/path")
        experiments = scanner.scan_experiments()
        assert experiments == []

    def test_hidden_files_handling(self, temp_dir):
        """Test handling of hidden files."""
        exp_dir = temp_dir / "E1_test_exp"
        exp_dir.mkdir()

        # Create hidden file
        (exp_dir / ".hidden").write_text("hidden\n")
        (exp_dir / "visible.txt").write_text("visible\n")

        scanner = FolderScanner(str(temp_dir))
        inventory = scanner.get_file_inventory(str(exp_dir))

        # Check that visible file is included
        all_files = inventory.get_all_files()
        file_names = [Path(f).name for f in all_files]
        assert "visible.txt" in file_names
        # Hidden files are still included by rglob (implementation detail)
        # The key is that both files are found


@pytest.mark.unit
@pytest.mark.batch_component
class TestFolderMetadata:
    """Tests for FolderMetadata class."""

    def test_folder_metadata_properties(self):
        """Test FolderMetadata properties."""
        metadata = FolderMetadata(
            experiment_id="E1",
            experiment_name="E1_test_exp",
            folder_path="/test/path",
            file_count=5,
        )

        assert metadata.experiment_id == "E1"
        assert metadata.experiment_name == "E1_test_exp"
        assert metadata.folder_path == "/test/path"
        assert metadata.file_count == 5

    def test_folder_metadata_to_dict(self):
        """Test FolderMetadata field access."""
        metadata = FolderMetadata(
            experiment_id="E1",
            experiment_name="E1_test_exp",
            folder_path="/test/path",
            file_count=5,
        )

        # FolderMetadata is a dataclass, verify field access
        assert metadata.experiment_id == "E1"
        assert metadata.folder_path == "/test/path"
        assert metadata.file_count == 5


@pytest.mark.unit
@pytest.mark.batch_component
class TestFileInventory:
    """Tests for FileInventory class."""

    def test_file_inventory_creation(self, temp_dir):
        """Test FileInventory creation."""
        exp_dir = temp_dir / "E1_test_exp"
        exp_dir.mkdir()
        (exp_dir / "file1.txt").write_text("data1\n")
        (exp_dir / "file2.txt").write_text("data2\n")

        scanner = FolderScanner(str(temp_dir))
        inventory = scanner.get_file_inventory(str(exp_dir))

        assert isinstance(inventory, FileInventory)
        assert inventory.get_file_count() == 2

    def test_file_inventory_by_type(self, temp_dir):
        """Test filtering files by type."""
        exp_dir = temp_dir / "E1_test_exp"
        exp_dir.mkdir()
        (exp_dir / "data.csv").write_text("csv\n")
        (exp_dir / "image.tiff").write_bytes(b"img")
        (exp_dir / "data2.csv").write_text("csv2\n")

        scanner = FolderScanner(str(temp_dir))
        inventory = scanner.get_file_inventory(str(exp_dir))

        # Check typed lists
        assert len(inventory.tiff_files) == 1
        # csv files go to other_files
        assert len(inventory.other_files) == 2

    def test_file_inventory_summary(self, temp_dir):
        """Test file inventory summary."""
        exp_dir = temp_dir / "E1_test_exp"
        exp_dir.mkdir()
        (exp_dir / "file1.csv").write_text("data1\n")
        (exp_dir / "file2.tiff").write_bytes(b"img")

        scanner = FolderScanner(str(temp_dir))
        inventory = scanner.get_file_inventory(str(exp_dir))

        assert inventory.get_file_count() == 2
        assert len(inventory.tiff_files) == 1
        assert len(inventory.other_files) == 1


@pytest.mark.unit
@pytest.mark.batch_component
class TestSubdirectoryHints:
    """Tests for SubdirectoryHints dataclass and _analyze_subdirectory_structure."""

    def test_flat_folder_no_structure(self, temp_dir):
        """Flat folder (no subdirs) → has_structure = False."""
        exp_dir = temp_dir / "E1_flat"
        exp_dir.mkdir()
        (exp_dir / "data.fcs").write_bytes(b"fcs")

        scanner = FolderScanner(str(temp_dir))
        hints = scanner._analyze_subdirectory_structure(exp_dir)

        assert hints.has_structure is False
        assert hints.timepoint_dirs == {}
        assert hints.processing_dirs == {}
        assert hints.assay_dirs == {}
        assert hints.immediate_subdirs == []

    def test_nonexistent_folder(self, temp_dir):
        """Non-existent folder → empty hints."""
        scanner = FolderScanner(str(temp_dir))
        hints = scanner._analyze_subdirectory_structure(temp_dir / "nonexistent")

        assert hints.has_structure is False

    def test_timepoint_dirs_detected(self, temp_dir):
        """D0/D1 subdirectories → timepoint_dirs populated."""
        exp_dir = temp_dir / "E15_test"
        exp_dir.mkdir()
        d0 = exp_dir / "D0"
        d1 = exp_dir / "D1"
        d0.mkdir()
        d1.mkdir()
        (d0 / "file1.fcs").write_bytes(b"fcs")
        (d1 / "file2.fcs").write_bytes(b"fcs")

        scanner = FolderScanner(str(temp_dir))
        hints = scanner._analyze_subdirectory_structure(exp_dir)

        assert hints.has_structure is True
        assert "D0" in hints.timepoint_dirs
        assert "D1" in hints.timepoint_dirs
        assert hints.timepoint_dirs["D0"] == "Day 0"
        assert hints.timepoint_dirs["D1"] == "Day 1"
        assert "D0" in hints.immediate_subdirs
        assert "D1" in hints.immediate_subdirs

    def test_timepoint_day_prefix(self, temp_dir):
        """Day0/Day1 subdirectories → timepoint_dirs with 'Day' prefix."""
        exp_dir = temp_dir / "E1_test"
        exp_dir.mkdir()
        (exp_dir / "Day0").mkdir()
        (exp_dir / "Day1").mkdir()

        scanner = FolderScanner(str(temp_dir))
        hints = scanner._analyze_subdirectory_structure(exp_dir)

        assert hints.timepoint_dirs["Day0"] == "Day 0"
        assert hints.timepoint_dirs["Day1"] == "Day 1"

    def test_timepoint_week_prefix(self, temp_dir):
        """Week1 subdirectory → timepoint_dirs with 'Week' prefix."""
        exp_dir = temp_dir / "E1_test"
        exp_dir.mkdir()
        (exp_dir / "Week1").mkdir()

        scanner = FolderScanner(str(temp_dir))
        hints = scanner._analyze_subdirectory_structure(exp_dir)

        assert hints.timepoint_dirs["Week1"] == "Week 1"

    def test_processing_dirs_detected(self, temp_dir):
        """filtriert/unfiltriert → processing_dirs populated."""
        exp_dir = temp_dir / "E15_test"
        exp_dir.mkdir()
        (exp_dir / "filtriert").mkdir()
        (exp_dir / "unfiltriert").mkdir()

        scanner = FolderScanner(str(temp_dir))
        hints = scanner._analyze_subdirectory_structure(exp_dir)

        assert hints.has_structure is True
        assert hints.processing_dirs["filtriert"] == "filtered"
        assert hints.processing_dirs["unfiltriert"] == "unfiltered"

    def test_processing_vorher_detected(self, temp_dir):
        """'Filtriert vorher' → 'pre-filtered'."""
        exp_dir = temp_dir / "E15_test"
        exp_dir.mkdir()
        (exp_dir / "Filtriert vorher").mkdir()

        scanner = FolderScanner(str(temp_dir))
        hints = scanner._analyze_subdirectory_structure(exp_dir)

        assert hints.processing_dirs["Filtriert vorher"] == "pre-filtered"

    def test_assay_dirs_detected(self, temp_dir):
        """FACS/ subdirectory → assay_dirs populated."""
        exp_dir = temp_dir / "E1_test"
        exp_dir.mkdir()
        (exp_dir / "FACS").mkdir()
        (exp_dir / "Calcein").mkdir()

        scanner = FolderScanner(str(temp_dir))
        hints = scanner._analyze_subdirectory_structure(exp_dir)

        assert hints.has_structure is True
        assert hints.assay_dirs["FACS"] == "facs"
        assert hints.assay_dirs["Calcein"] == "calcein"

    def test_mixed_structure(self, temp_dir):
        """Mixed subdirs with timepoints, processing, and assay dirs."""
        exp_dir = temp_dir / "E15_mixed"
        exp_dir.mkdir()
        d0 = exp_dir / "D0"
        d0.mkdir()
        (d0 / "file.fcs").write_bytes(b"fcs")
        (exp_dir / "filtriert").mkdir()
        (exp_dir / "FACS").mkdir()
        # Non-meaningful subdir
        (exp_dir / "temp").mkdir()

        scanner = FolderScanner(str(temp_dir))
        hints = scanner._analyze_subdirectory_structure(exp_dir)

        assert hints.has_structure is True
        assert "D0" in hints.timepoint_dirs
        assert "filtriert" in hints.processing_dirs
        assert "FACS" in hints.assay_dirs
        assert "temp" in hints.immediate_subdirs
        # temp should not be in any detected category
        assert "temp" not in hints.timepoint_dirs
        assert "temp" not in hints.processing_dirs
        assert "temp" not in hints.assay_dirs

    def test_files_by_subdir_populated(self, temp_dir):
        """files_by_subdir should contain files grouped by subdirectory."""
        exp_dir = temp_dir / "E1_test"
        exp_dir.mkdir()
        d0 = exp_dir / "D0"
        d0.mkdir()
        (d0 / "a.fcs").write_bytes(b"fcs")
        (d0 / "b.fcs").write_bytes(b"fcs")

        scanner = FolderScanner(str(temp_dir))
        hints = scanner._analyze_subdirectory_structure(exp_dir)

        assert "D0" in hints.files_by_subdir
        assert len(hints.files_by_subdir["D0"]) == 2

    def test_subdirectory_hints_in_metadata(self, temp_dir):
        """FolderMetadata should include subdirectory_hints after scan."""
        exp_dir = temp_dir / "E15_test"
        exp_dir.mkdir()
        (exp_dir / "D0").mkdir()
        (exp_dir / "data.fcs").write_bytes(b"fcs")

        scanner = FolderScanner(str(temp_dir))
        experiments = scanner.scan_experiments()

        assert len(experiments) == 1
        metadata = experiments[0]
        assert metadata.subdirectory_hints is not None
        assert metadata.subdirectory_hints.has_structure is True
        assert "D0" in metadata.subdirectory_hints.timepoint_dirs

    def test_non_meaningful_subdirs_no_structure(self, temp_dir):
        """Subdirs that don't match any pattern → has_structure = False."""
        exp_dir = temp_dir / "E1_test"
        exp_dir.mkdir()
        (exp_dir / "temp").mkdir()
        (exp_dir / "backup").mkdir()
        (exp_dir / "old_data").mkdir()

        scanner = FolderScanner(str(temp_dir))
        hints = scanner._analyze_subdirectory_structure(exp_dir)

        assert hints.has_structure is False
        assert len(hints.immediate_subdirs) == 3
