"""
Tests for the microscopy file linking script (scripts/link_microscopy_files.py).

These tests use synthetic file structures in temporary directories to avoid
requiring the actual microscopy data directory.
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Discover profile scripts directory
_profile_dir = None
_env = os.environ.get("ISA_STEWARD_PROFILE")
if _env and Path(_env).is_dir():
    _profile_dir = Path(_env)
else:
    _candidates = sorted(Path(__file__).parent.parent.glob("*-profile"))
    if _candidates:
        _profile_dir = _candidates[0]

if _profile_dir and (_profile_dir / "scripts").is_dir():
    sys.path.insert(0, str(_profile_dir / "scripts"))
try:
    from link_microscopy_files import (
        ISA_TYPE_MAP,
        MICROSCOPY_EXTENSIONS,
        MICROSCOPY_SD_MAP,
        _make_microscopy_file_ref,
        _resolve_folder,
        copy_microscopy_files,
        find_microscopy_assay,
        find_study_dir,
        main,
        process_mapping,
        register_microscopy_datafiles,
        scan_microscopy_files,
    )
except ImportError:
    pytest.skip(
        "link_microscopy_files not available (requires profile with scripts/)",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def microscopy_root(tmp_path: Path) -> Path:
    """Create a synthetic microscopy data directory with mapped folders."""
    root = tmp_path / "Microscopy of LLPS"
    root.mkdir()

    # Create a few mapped folders with sample files.
    folder_a = (
        root / "[ordered] Microscopy of 2.25 uM depot + Eylea" / "021225 018-024 eye buffer + eylea"
    )
    folder_a.mkdir(parents=True)
    (folder_a / "slide_01.czi").write_bytes(b"\x00CZI_FAKE")
    (folder_a / "overview.jpg").write_bytes(b"\xff\xd8\xff\xe0FAKE_JPG")
    (folder_a / "notes.docx").write_bytes(b"PK\x03\x04FAKE_DOCX")
    (folder_a / "measurements.xlsx").write_bytes(b"PK\x03\x04FAKE_XLSX")
    (folder_a / "readme.txt").write_bytes(b"not a microscopy file")  # should be skipped

    # Folder with prefix match needed.
    folder_b = root / "[ordered] pVV021" / "201125 Purified pVV021 + Eylea etc"
    folder_b.mkdir(parents=True)
    (folder_b / "image_01.png").write_bytes(b"\x89PNG_FAKE")
    (folder_b / "presentation.pptx").write_bytes(b"PK\x03\x04FAKE_PPTX")

    # pVV021 purif folder (top-level, no subfolder).
    folder_c = root / "pVV021 purif"
    folder_c.mkdir(parents=True)
    (folder_c / "purified_01.jpg").write_bytes(b"\xff\xd8\xff\xe0FAKE_JPG2")
    (folder_c / "data_01.tif").write_bytes(b"II\x2a\x00FAKE_TIF")

    return root


@pytest.fixture
def study_dir(tmp_path: Path) -> Path:
    """Create a synthetic study directory with a study.json containing a microscopy assay."""
    studies_root = tmp_path / "investigations" / "inv_inm" / "studies"
    study = studies_root / "study_SD24105_Analysis_of_018-024"
    study.mkdir(parents=True)
    (study / "files" / "original").mkdir(parents=True)
    (study / "files" / "converted").mkdir(parents=True)

    study_json = {
        "studies": [
            {
                "title": "Analysis of 018-024 (SD24105)",
                "assays": [
                    {
                        "@id": "#assay_Depot_microscopy_assay",
                        "name": "Depot microscopy assay",
                        "description": "Microscopy imaging of assembled depot",
                        "dataFiles": [],
                        "materials": {"samples": [], "otherMaterials": []},
                        "processSequence": [],
                    },
                    {
                        "@id": "#assay_Supernatant_concentration_determination_assay",
                        "name": "Supernatant concentration determination assay",
                        "dataFiles": [],
                        "materials": {"samples": [], "otherMaterials": []},
                        "processSequence": [],
                    },
                ],
            }
        ]
    }
    (study / "study.json").write_text(json.dumps(study_json, indent=2), encoding="utf-8")
    return study


@pytest.fixture
def dm(tmp_path: Path):
    """Create a DirectoryManager rooted at tmp_path."""
    from utils.directory_manager import DirectoryManager

    return DirectoryManager(base_path=str(tmp_path))


# ---------------------------------------------------------------------------
# Tests: _resolve_folder
# ---------------------------------------------------------------------------


class TestResolveFolder:
    """Tests for _resolve_folder()."""

    def test_exact_match(self, microscopy_root: Path):
        result = _resolve_folder(
            "[ordered] Microscopy of 2.25 uM depot + Eylea/021225 018-024 eye buffer + eylea",
            microscopy_root,
        )
        assert result is not None
        assert result.is_dir()
        assert result.name == "021225 018-024 eye buffer + eylea"

    def test_prefix_match(self, microscopy_root: Path):
        """'201125' should match '201125 Purified pVV021 + Eylea etc'."""
        result = _resolve_folder("[ordered] pVV021/201125", microscopy_root)
        assert result is not None
        assert result.name.startswith("201125")

    def test_top_level_folder(self, microscopy_root: Path):
        result = _resolve_folder("pVV021 purif", microscopy_root)
        assert result is not None
        assert result.name == "pVV021 purif"

    def test_not_found(self, microscopy_root: Path):
        result = _resolve_folder("nonexistent/folder", microscopy_root)
        assert result is None

    def test_parent_not_found(self, microscopy_root: Path):
        result = _resolve_folder("no_parent/999999", microscopy_root)
        assert result is None


# ---------------------------------------------------------------------------
# Tests: find_study_dir
# ---------------------------------------------------------------------------


class TestFindStudyDir:
    """Tests for find_study_dir()."""

    def test_found(self, dm, study_dir: Path):
        result = find_study_dir(dm, "SD24105")
        assert result is not None
        assert "SD24105" in result.name

    def test_not_found(self, dm):
        result = find_study_dir(dm, "SD99999")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: scan_microscopy_files
# ---------------------------------------------------------------------------


class TestScanMicroscopyFiles:
    """Tests for scan_microscopy_files()."""

    def test_finds_valid_extensions(self, microscopy_root: Path):
        folder = (
            microscopy_root
            / "[ordered] Microscopy of 2.25 uM depot + Eylea"
            / "021225 018-024 eye buffer + eylea"
        )
        files = scan_microscopy_files(folder)
        names = {f.name for f in files}
        assert "slide_01.czi" in names
        assert "overview.jpg" in names
        assert "notes.docx" in names
        assert "measurements.xlsx" in names
        # .txt should be excluded
        assert "readme.txt" not in names

    def test_empty_folder(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert scan_microscopy_files(empty) == []

    def test_nonexistent_folder(self, tmp_path: Path):
        assert scan_microscopy_files(tmp_path / "nope") == []


# ---------------------------------------------------------------------------
# Tests: copy_microscopy_files
# ---------------------------------------------------------------------------


class TestCopyMicroscopyFiles:
    """Tests for copy_microscopy_files()."""

    def test_copies_files(self, microscopy_root: Path, study_dir: Path):
        source = (
            microscopy_root
            / "[ordered] Microscopy of 2.25 uM depot + Eylea"
            / "021225 018-024 eye buffer + eylea"
        )
        refs = copy_microscopy_files(source, study_dir, "test_folder")
        assert len(refs) == 4  # czi, jpg, docx, xlsx

        # Verify files were actually copied.
        target_dir = study_dir / "files" / "original" / "microscopy" / "test_folder"
        assert target_dir.exists()
        copied_names = {p.name for p in target_dir.iterdir()}
        assert "slide_01.czi" in copied_names
        assert "overview.jpg" in copied_names

    def test_dry_run_no_copy(self, microscopy_root: Path, study_dir: Path):
        source = (
            microscopy_root
            / "[ordered] Microscopy of 2.25 uM depot + Eylea"
            / "021225 018-024 eye buffer + eylea"
        )
        refs = copy_microscopy_files(source, study_dir, "test_folder", dry_run=True)
        assert len(refs) == 4

        target_dir = study_dir / "files" / "original" / "microscopy" / "test_folder"
        assert not target_dir.exists()

    def test_relative_paths(self, microscopy_root: Path, study_dir: Path):
        source = (
            microscopy_root
            / "[ordered] Microscopy of 2.25 uM depot + Eylea"
            / "021225 018-024 eye buffer + eylea"
        )
        refs = copy_microscopy_files(source, study_dir, "test_folder")
        for ref in refs:
            assert ref["relative_path"].startswith("original/microscopy/")
            assert ref["file_name"] in ref["relative_path"]

    def test_isa_type_mapping(self, microscopy_root: Path, study_dir: Path):
        source = (
            microscopy_root
            / "[ordered] Microscopy of 2.25 uM depot + Eylea"
            / "021225 018-024 eye buffer + eylea"
        )
        refs = copy_microscopy_files(source, study_dir, "test_folder")
        by_name = {r["file_name"]: r for r in refs}
        assert by_name["slide_01.czi"]["isa_type"] == "Raw Data File"
        assert by_name["overview.jpg"]["isa_type"] == "Image File"
        assert by_name["notes.docx"]["isa_type"] == "Derived Data File"
        assert by_name["measurements.xlsx"]["isa_type"] == "Raw Data File"

    def test_empty_source(self, tmp_path: Path, study_dir: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        refs = copy_microscopy_files(empty, study_dir, "empty")
        assert refs == []

    def test_sanitises_folder_label(self, microscopy_root: Path, study_dir: Path):
        source = (
            microscopy_root
            / "[ordered] Microscopy of 2.25 uM depot + Eylea"
            / "021225 018-024 eye buffer + eylea"
        )
        copy_microscopy_files(source, study_dir, "bad:name/with*chars")
        target_dir = study_dir / "files" / "original" / "microscopy" / "bad_name_with_chars"
        assert target_dir.exists()


# ---------------------------------------------------------------------------
# Tests: find_microscopy_assay
# ---------------------------------------------------------------------------


class TestFindMicroscopyAssay:
    """Tests for find_microscopy_assay()."""

    def test_finds_microscopy_assay(self, study_dir: Path):
        with open(study_dir / "study.json", encoding="utf-8") as f:
            data = json.load(f)
        assay = find_microscopy_assay(data)
        assert assay is not None
        assert "microscopy" in assay["name"].lower()

    def test_no_microscopy_assay(self):
        data = {"studies": [{"assays": [{"name": "Some other assay"}]}]}
        assert find_microscopy_assay(data) is None

    def test_empty_assays(self):
        data = {"studies": [{"assays": []}]}
        assert find_microscopy_assay(data) is None


# ---------------------------------------------------------------------------
# Tests: register_microscopy_datafiles
# ---------------------------------------------------------------------------


class TestRegisterMicroscopyDatafiles:
    """Tests for register_microscopy_datafiles()."""

    def test_registers_files(self, study_dir: Path):
        json_path = study_dir / "study.json"
        refs = [
            {
                "file_name": "slide.czi",
                "relative_path": "original/microscopy/folder/slide.czi",
                "isa_type": "Raw Data File",
            },
            {
                "file_name": "image.jpg",
                "relative_path": "original/microscopy/folder/image.jpg",
                "isa_type": "Image File",
            },
        ]
        added = register_microscopy_datafiles(json_path, refs)
        assert added == 2

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assay = find_microscopy_assay(data)
        assert len(assay["dataFiles"]) == 2
        assert assay["dataFiles"][0]["@id"] == "#file_microscopy_1"
        assert assay["dataFiles"][1]["@id"] == "#file_microscopy_2"

    def test_skips_duplicates(self, study_dir: Path):
        json_path = study_dir / "study.json"
        refs = [
            {
                "file_name": "slide.czi",
                "relative_path": "original/microscopy/f/slide.czi",
                "isa_type": "Raw Data File",
            },
        ]
        register_microscopy_datafiles(json_path, refs)
        added_again = register_microscopy_datafiles(json_path, refs)
        assert added_again == 0

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assay = find_microscopy_assay(data)
        assert len(assay["dataFiles"]) == 1

    def test_dry_run_no_write(self, study_dir: Path):
        json_path = study_dir / "study.json"
        refs = [
            {
                "file_name": "slide.czi",
                "relative_path": "original/microscopy/f/slide.czi",
                "isa_type": "Raw Data File",
            },
        ]
        added = register_microscopy_datafiles(json_path, refs, dry_run=True)
        assert added == 1

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assay = find_microscopy_assay(data)
        assert len(assay["dataFiles"]) == 0

    def test_creates_assay_if_missing(self, tmp_path: Path):
        """If no microscopy assay exists, one should be created."""
        study = tmp_path / "study.json"
        data = {"studies": [{"assays": []}]}
        study.write_text(json.dumps(data), encoding="utf-8")

        refs = [
            {
                "file_name": "img.png",
                "relative_path": "original/microscopy/f/img.png",
                "isa_type": "Image File",
            },
        ]
        added = register_microscopy_datafiles(study, refs)
        assert added == 1

        with open(study, encoding="utf-8") as f:
            updated = json.load(f)
        assays = updated["studies"][0]["assays"]
        assert len(assays) == 1
        assert "microscopy" in assays[0]["name"].lower()
        assert len(assays[0]["dataFiles"]) == 1

    def test_empty_refs(self, study_dir: Path):
        json_path = study_dir / "study.json"
        assert register_microscopy_datafiles(json_path, []) == 0


# ---------------------------------------------------------------------------
# Tests: _make_microscopy_file_ref
# ---------------------------------------------------------------------------


class TestMakeMicroscopyFileRef:
    """Tests for _make_microscopy_file_ref()."""

    def test_basic_structure(self):
        fi = {
            "file_name": "test.czi",
            "relative_path": "original/microscopy/f/test.czi",
            "isa_type": "Raw Data File",
        }
        ref = _make_microscopy_file_ref(fi, 0)
        assert ref["@id"] == "#file_microscopy_1"
        assert ref["name"] == "test.czi"
        assert ref["type"] == "Raw Data File"
        assert ref["comments"][0]["name"] == "TraceDB"
        assert ref["comments"][0]["value"] == "original/microscopy/f/test.czi"

    def test_index_increments(self):
        fi = {
            "file_name": "a.jpg",
            "relative_path": "original/microscopy/f/a.jpg",
            "isa_type": "Image File",
        }
        ref0 = _make_microscopy_file_ref(fi, 0)
        ref1 = _make_microscopy_file_ref(fi, 1)
        assert ref0["@id"] == "#file_microscopy_1"
        assert ref1["@id"] == "#file_microscopy_2"


# ---------------------------------------------------------------------------
# Tests: process_mapping (integration)
# ---------------------------------------------------------------------------


class TestProcessMapping:
    """Integration tests for process_mapping()."""

    def test_full_pipeline(self, microscopy_root: Path, study_dir: Path, dm, monkeypatch):
        """Test the full pipeline: resolve → copy → register."""
        monkeypatch.setattr("link_microscopy_files.MICROSCOPY_ROOT", microscopy_root)
        summary = process_mapping(
            "[ordered] Microscopy of 2.25 uM depot + Eylea/021225 018-024 eye buffer + eylea",
            "SD24105",
            dm,
            dry_run=False,
        )
        assert summary["sd_number"] == "SD24105"
        assert summary["copied"] == 4
        assert summary["registered"] == 4
        assert summary["errors"] == []

    def test_dry_run(self, microscopy_root: Path, study_dir: Path, dm, monkeypatch):
        monkeypatch.setattr("link_microscopy_files.MICROSCOPY_ROOT", microscopy_root)
        summary = process_mapping(
            "[ordered] Microscopy of 2.25 uM depot + Eylea/021225 018-024 eye buffer + eylea",
            "SD24105",
            dm,
            dry_run=True,
        )
        assert summary["copied"] == 4
        assert summary["registered"] == 4
        # Verify nothing was actually written.
        target_dir = study_dir / "files" / "original" / "microscopy"
        assert not target_dir.exists()

    def test_missing_source(self, study_dir: Path, dm, tmp_path: Path, monkeypatch):
        """Missing source folder should produce an error."""
        empty_root = tmp_path / "empty_root"
        empty_root.mkdir()
        monkeypatch.setattr("link_microscopy_files.MICROSCOPY_ROOT", empty_root)
        summary = process_mapping(
            "nonexistent/path",
            "SD24105",
            dm,
        )
        assert summary["errors"]
        assert "not found" in summary["errors"][0].lower()

    def test_missing_study(self, microscopy_root: Path, dm, monkeypatch):
        """Missing study directory should produce an error."""
        monkeypatch.setattr("link_microscopy_files.MICROSCOPY_ROOT", microscopy_root)
        summary = process_mapping(
            "[ordered] Microscopy of 2.25 uM depot + Eylea/021225 018-024 eye buffer + eylea",
            "SD99999",
            dm,
        )
        assert summary["errors"]
        assert "study" in summary["errors"][0].lower()


# ---------------------------------------------------------------------------
# Tests: CLI (main)
# ---------------------------------------------------------------------------


class TestCLI:
    """Tests for the CLI entry point."""

    def test_dry_run_with_sd_filter(
        self,
        microscopy_root: Path,
        study_dir: Path,
        dm,
        monkeypatch,
        tmp_path: Path,
    ):
        """--dry-run --sd SD24105 should run without errors."""
        # Patch MICROSCOPY_ROOT and DirectoryManager.
        monkeypatch.setattr("link_microscopy_files.MICROSCOPY_ROOT", microscopy_root)
        monkeypatch.setattr(
            "link_microscopy_files.DirectoryManager",
            lambda: dm,
        )
        exit_code = main(["--dry-run", "--sd", "SD24105"])
        assert exit_code == 0

    def test_no_matching_sd(self, microscopy_root: Path, dm, monkeypatch):
        monkeypatch.setattr("link_microscopy_files.MICROSCOPY_ROOT", microscopy_root)
        monkeypatch.setattr(
            "link_microscopy_files.DirectoryManager",
            lambda: dm,
        )
        exit_code = main(["--sd", "SD99999"])
        assert exit_code == 1


# ---------------------------------------------------------------------------
# Tests: constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Sanity checks on module-level constants."""

    def test_microscopy_sd_map_not_empty(self):
        assert len(MICROSCOPY_SD_MAP) > 0

    def test_all_sd_numbers_valid(self):
        for sd in MICROSCOPY_SD_MAP.values():
            assert sd.startswith("SD"), f"Invalid SD number: {sd}"

    def test_microscopy_extensions(self):
        assert ".czi" in MICROSCOPY_EXTENSIONS
        assert ".jpg" in MICROSCOPY_EXTENSIONS
        assert ".png" in MICROSCOPY_EXTENSIONS
        assert ".tif" in MICROSCOPY_EXTENSIONS
        assert ".docx" in MICROSCOPY_EXTENSIONS
        assert ".pptx" in MICROSCOPY_EXTENSIONS
        assert ".xlsx" in MICROSCOPY_EXTENSIONS

    def test_isa_type_map_covers_extensions(self):
        for ext in MICROSCOPY_EXTENSIONS:
            assert ext in ISA_TYPE_MAP, f"Missing ISA type for {ext}"
