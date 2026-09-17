"""Extended tests for FileManager static/pure methods.

Covers:
  - FileManager._get_file_type_from_isa_type (static)
  - FileManager._get_file_type_from_name (static)
  - FileManager._ontology_to_data_type (static)
  - FileManager._get_file_type_from_ontology
  - FileManager.get_file_type (instance)
  - FileManager.generate_isa_file_reference
"""

from pathlib import Path

import pytest

from utils.file_manager import FileManager


@pytest.fixture
def fm(tmp_path):
    """Create a FileManager with a temporary investigations root."""
    return FileManager(investigations_root=str(tmp_path))


# ---------------------------------------------------------------------------
# _get_file_type_from_isa_type (static)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetFileTypeFromIsaType:
    """Tests for FileManager._get_file_type_from_isa_type."""

    def test_empty_returns_data(self):
        assert FileManager._get_file_type_from_isa_type("") == "data"

    def test_raw_data_file(self):
        assert FileManager._get_file_type_from_isa_type("Raw Data File") == "data"

    def test_derived_data_file(self):
        assert FileManager._get_file_type_from_isa_type("Derived Data File") == "data"

    def test_image_file(self):
        assert FileManager._get_file_type_from_isa_type("Image File") == "image"

    def test_image_file_lowercase(self):
        assert FileManager._get_file_type_from_isa_type("image file") == "image"

    def test_sequence_file(self):
        assert FileManager._get_file_type_from_isa_type("Sequence File") == "sequencing"

    def test_report_file(self):
        assert FileManager._get_file_type_from_isa_type("Report File") == "report"

    def test_acquisition_parameter_data_file(self):
        assert FileManager._get_file_type_from_isa_type("Acquisition Parameter Data File") == "data"

    def test_unknown_defaults_to_data(self):
        assert FileManager._get_file_type_from_isa_type("Something Unknown") == "data"


# ---------------------------------------------------------------------------
# _get_file_type_from_name (static)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetFileTypeFromName:
    """Tests for FileManager._get_file_type_from_name."""

    def test_tiff_image(self):
        assert FileManager._get_file_type_from_name("image.tiff") == "image"

    def test_tif_image(self):
        assert FileManager._get_file_type_from_name("image.tif") == "image"

    def test_png_image(self):
        assert FileManager._get_file_type_from_name("photo.png") == "image"

    def test_jpg_image(self):
        assert FileManager._get_file_type_from_name("photo.jpg") == "image"

    def test_czi_image(self):
        assert FileManager._get_file_type_from_name("microscopy.czi") == "image"

    def test_fcs_data(self):
        assert FileManager._get_file_type_from_name("sample.fcs") == "data"

    def test_xlsx_data(self):
        assert FileManager._get_file_type_from_name("data.xlsx") == "data"

    def test_csv_data(self):
        assert FileManager._get_file_type_from_name("table.csv") == "data"

    def test_wsp_data(self):
        assert FileManager._get_file_type_from_name("workspace.wsp") == "data"

    def test_fastq_sequencing(self):
        assert FileManager._get_file_type_from_name("reads.fastq") == "sequencing"

    def test_fasta_sequencing(self):
        assert FileManager._get_file_type_from_name("sequence.fasta") == "sequencing"

    def test_ab1_sequencing(self):
        assert FileManager._get_file_type_from_name("trace.ab1") == "sequencing"

    def test_unknown_extension(self):
        assert FileManager._get_file_type_from_name("file.xyz") is None

    def test_empty_filename(self):
        assert FileManager._get_file_type_from_name("") is None

    def test_no_extension(self):
        assert FileManager._get_file_type_from_name("noext") is None


# ---------------------------------------------------------------------------
# _ontology_to_data_type (static)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOntologyToDataType:
    """Tests for FileManager._ontology_to_data_type."""

    def test_image_ontology(self):
        ontology = {"annotationValue": "image", "termSource": "EDAM"}
        assert FileManager._ontology_to_data_type(ontology) == "Image File"

    def test_data_ontology(self):
        ontology = {"annotationValue": "data", "termSource": "EDAM"}
        assert FileManager._ontology_to_data_type(ontology) == "Derived Data File"

    def test_sequence_ontology(self):
        ontology = {"annotationValue": "sequence", "termSource": "EDAM"}
        assert FileManager._ontology_to_data_type(ontology) == "Raw Spectral Data File"

    def test_report_ontology(self):
        ontology = {"annotationValue": "report", "termSource": "EDAM"}
        assert FileManager._ontology_to_data_type(ontology) == "Derived Data File"

    def test_unknown_ontology_defaults_to_derived(self):
        ontology = {"annotationValue": "unknown", "termSource": "EDAM"}
        assert FileManager._ontology_to_data_type(ontology) == "Derived Data File"

    def test_empty_ontology(self):
        assert FileManager._ontology_to_data_type({}) == "Derived Data File"


# ---------------------------------------------------------------------------
# _get_file_type_from_ontology (instance)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetFileTypeFromOntology:
    """Tests for FileManager._get_file_type_from_ontology."""

    def test_image_annotation(self, fm):
        ontology = {"annotationValue": "image", "termSource": "EDAM"}
        assert fm._get_file_type_from_ontology(ontology) == "image"

    def test_data_annotation(self, fm):
        ontology = {"annotationValue": "data", "termSource": "EDAM"}
        assert fm._get_file_type_from_ontology(ontology) == "data"

    def test_sequence_annotation(self, fm):
        ontology = {"annotationValue": "sequence", "termSource": "EDAM"}
        assert fm._get_file_type_from_ontology(ontology) == "sequencing"

    def test_report_annotation(self, fm):
        ontology = {"annotationValue": "report", "termSource": "EDAM"}
        assert fm._get_file_type_from_ontology(ontology) == "report"

    def test_unknown_defaults_to_data(self, fm):
        ontology = {"annotationValue": "something", "termSource": "EDAM"}
        assert fm._get_file_type_from_ontology(ontology) == "data"

    def test_empty_defaults_to_data(self, fm):
        assert fm._get_file_type_from_ontology({}) == "data"


# ---------------------------------------------------------------------------
# get_file_type (instance)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetFileType:
    """Tests for FileManager.get_file_type instance method."""

    def test_image_extensions(self, fm):
        for ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif"]:
            assert fm.get_file_type(Path(f"file{ext}")) == "image", f"Failed for {ext}"

    def test_data_extensions(self, fm):
        for ext in [".xlsx", ".xls", ".csv", ".txt", ".json", ".xml", ".pdf"]:
            assert fm.get_file_type(Path(f"file{ext}")) == "data", f"Failed for {ext}"

    def test_sequencing_extensions(self, fm):
        for ext in [".fastq", ".fq", ".ab1", ".fasta", ".fa", ".bam", ".sam"]:
            assert fm.get_file_type(Path(f"file{ext}")) == "sequencing", f"Failed for {ext}"

    def test_unknown_extension(self, fm):
        assert fm.get_file_type(Path("file.xyz")) is None

    def test_case_insensitive(self, fm):
        assert fm.get_file_type(Path("file.JPG")) == "image"
        assert fm.get_file_type(Path("file.CSV")) == "data"


# ---------------------------------------------------------------------------
# generate_isa_file_reference
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateIsaFileReference:
    """Tests for FileManager.generate_isa_file_reference."""

    def test_basic_reference(self, fm):
        file_meta = {
            "file_id": "abc12345-xxxx",
            "entity_type": "assay",
            "entity_id": "microscopy_1",
            "original_filename": "image.tiff",
            "file_type": "image",
            "original_format": ".tiff",
        }
        ref = fm.generate_isa_file_reference(file_meta, "inv_1", "study_1")
        assert "@id" in ref
        assert "inv_1" in ref["@id"]
        assert "study_1" in ref["@id"]
        assert ref["name"] == "image.tiff"
        assert ref["type"] == "Image File"

    def test_data_file_reference(self, fm):
        file_meta = {
            "file_id": "def67890-xxxx",
            "entity_type": "assay",
            "entity_id": "facs_1",
            "original_filename": "data.fcs",
            "file_type": "data",
            "original_format": ".fcs",
        }
        ref = fm.generate_isa_file_reference(file_meta, "inv_1", "study_1")
        assert ref["type"] == "Derived Data File"

    def test_reference_with_conversion(self, fm):
        file_meta = {
            "file_id": "ghi11111-xxxx",
            "entity_type": "process",
            "entity_id": "process_1",
            "original_filename": "image.jpg",
            "file_type": "image",
            "original_format": ".jpg",
            "converted_path": "converted/image.tif",
            "converted_format": ".tif",
        }
        ref = fm.generate_isa_file_reference(file_meta, "inv_1", "study_1")
        assert "comments" in ref
        assert len(ref["comments"]) > 0

    def test_reference_uses_attachment_name(self, fm):
        file_meta = {
            "file_id": "jkl22222-xxxx",
            "entity_type": "assay",
            "entity_id": "assay_1",
            "attachment_name": "Custom Name",
            "original_filename": "file.csv",
            "file_type": "data",
            "original_format": ".csv",
        }
        ref = fm.generate_isa_file_reference(file_meta, "inv_1", "study_1")
        assert ref["name"] == "Custom Name"


# ---------------------------------------------------------------------------
# FILE_TYPE_ONTOLOGY class attribute
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFileTypeOntology:
    """Tests for FileManager.FILE_TYPE_ONTOLOGY class attribute."""

    def test_image_ontology_entry(self):
        assert "image" in FileManager.FILE_TYPE_ONTOLOGY
        assert FileManager.FILE_TYPE_ONTOLOGY["image"]["termSource"] == "EDAM"

    def test_data_ontology_entry(self):
        assert "data" in FileManager.FILE_TYPE_ONTOLOGY

    def test_sequencing_ontology_entry(self):
        assert "sequencing" in FileManager.FILE_TYPE_ONTOLOGY

    def test_report_ontology_entry(self):
        assert "report" in FileManager.FILE_TYPE_ONTOLOGY


# ---------------------------------------------------------------------------
# get_expected_attachments
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetExpectedAttachments:
    """Tests for FileManager.get_expected_attachments."""

    def test_with_attachments(self, fm):
        template = {
            "expectedAttachments": [
                {"name": "image", "fileType": "image"},
                {"name": "data", "fileType": "data"},
            ]
        }
        result = fm.get_expected_attachments(template)
        assert len(result) == 2

    def test_empty_template(self, fm):
        assert fm.get_expected_attachments({}) == []
