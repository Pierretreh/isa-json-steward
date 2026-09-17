"""Tests for FileConverter in utils/file_converter.py.

Covers:
  - FileConverter.__init__
  - get_file_type
  - needs_conversion
  - FILE_TYPE_MAPPINGS
"""

from pathlib import Path

import pytest

from utils.file_converter import FileConverter


@pytest.fixture
def converter():
    return FileConverter()


# ---------------------------------------------------------------------------
# FileConverter.__init__
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFileConverterInit:
    """Tests for FileConverter initialization."""

    def test_init(self, converter):
        assert converter.conversion_log == []

    def test_file_type_mappings_exist(self):
        assert "image" in FileConverter.FILE_TYPE_MAPPINGS
        assert "data" in FileConverter.FILE_TYPE_MAPPINGS
        assert "sequencing" in FileConverter.FILE_TYPE_MAPPINGS
        assert "report" in FileConverter.FILE_TYPE_MAPPINGS


# ---------------------------------------------------------------------------
# get_file_type
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetFileType:
    """Tests for FileConverter.get_file_type."""

    def test_jpg_is_image(self, converter):
        assert converter.get_file_type(Path("photo.jpg")) == "image"

    def test_jpeg_is_image(self, converter):
        assert converter.get_file_type(Path("photo.jpeg")) == "image"

    def test_png_is_image(self, converter):
        assert converter.get_file_type(Path("image.png")) == "image"

    def test_bmp_is_image(self, converter):
        assert converter.get_file_type(Path("image.bmp")) == "image"

    def test_gif_is_image(self, converter):
        assert converter.get_file_type(Path("anim.gif")) == "image"

    def test_xlsx_is_data(self, converter):
        assert converter.get_file_type(Path("data.xlsx")) == "data"

    def test_xls_is_data(self, converter):
        assert converter.get_file_type(Path("data.xls")) == "data"

    def test_ods_is_data(self, converter):
        assert converter.get_file_type(Path("data.ods")) == "data"

    def test_ab1_is_sequencing(self, converter):
        assert converter.get_file_type(Path("trace.ab1")) == "sequencing"

    def test_fastq_is_sequencing(self, converter):
        assert converter.get_file_type(Path("reads.fastq")) == "sequencing"

    def test_fasta_is_sequencing(self, converter):
        assert converter.get_file_type(Path("seq.fasta")) == "sequencing"

    def test_dna_is_sequencing(self, converter):
        assert converter.get_file_type(Path("plasmid.dna")) == "sequencing"

    def test_pdf_is_report(self, converter):
        assert converter.get_file_type(Path("report.pdf")) == "report"

    def test_docx_is_report(self, converter):
        assert converter.get_file_type(Path("report.docx")) == "report"

    def test_txt_is_report(self, converter):
        assert converter.get_file_type(Path("notes.txt")) == "report"

    def test_unknown_extension(self, converter):
        assert converter.get_file_type(Path("file.xyz")) is None

    def test_case_insensitive(self, converter):
        assert converter.get_file_type(Path("FILE.JPG")) == "image"
        assert converter.get_file_type(Path("DATA.XLSX")) == "data"


# ---------------------------------------------------------------------------
# needs_conversion
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNeedsConversion:
    """Tests for FileConverter.needs_conversion."""

    def test_image_needs_conversion(self, converter):
        assert converter.needs_conversion(Path("photo.jpg"), "image") is True

    def test_image_already_tiff(self, converter):
        # Target extension is .tif (not .tiff), so .tiff still needs conversion
        assert converter.needs_conversion(Path("image.tiff"), "image") is True

    def test_image_already_tif(self, converter):
        assert converter.needs_conversion(Path("image.tif"), "image") is False

    def test_data_needs_conversion(self, converter):
        assert converter.needs_conversion(Path("data.xlsx"), "data") is True

    def test_data_already_csv(self, converter):
        assert converter.needs_conversion(Path("data.csv"), "data") is False

    def test_sequencing_needs_conversion(self, converter):
        assert converter.needs_conversion(Path("trace.ab1"), "sequencing") is True

    def test_sequencing_already_gb(self, converter):
        assert converter.needs_conversion(Path("seq.gb"), "sequencing") is False

    def test_report_needs_no_conversion(self, converter):
        assert converter.needs_conversion(Path("report.pdf"), "report") is False

    def test_unknown_file_type(self, converter):
        # Unknown file type has no target extension
        assert converter.needs_conversion(Path("file.xyz"), "unknown_type") is False
