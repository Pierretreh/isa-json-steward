"""
Tests for the lab book XML parser (scripts/lab_book_xml_parser.py).

These tests use synthetic XML content to avoid requiring the actual
data directory.  A fixture creates a minimal lab book folder structure
in a temporary directory.
"""

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
    from lab_book_xml_parser import (
        LabBookEntry,
        LabBookImage,
        LabBookXMLParser,
        classify_file_type,
        strip_html,
    )
except ImportError:
    pytest.skip(
        "lab_book_xml_parser not available (requires profile with scripts/)",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# NOTE: HTML content inside <fieldData> uses CDATA to avoid XML escaping issues.
# The real lab book XML files use entity-escaped HTML (</>), but CDATA
# is equivalent for testing purposes and avoids tool encoding issues.
SAMPLE_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<archivalDocument docId="12345">\n'
    "  <name>Test experiment with pVV019</name>\n"
    "  <type>NORMAL</type>\n"
    "  <createdBy>test.user@example.com</createdBy>\n"
    "  <creationDate>2025-11-05T16:22:42Z</creationDate>\n"
    "  <lastModifiedDate>2026-01-07T12:32:03Z</lastModifiedDate>\n"
    "  <listFields>\n"
    '    <field id="100">\n'
    "      <fieldName>Data</fieldName>\n"
    "      <fieldType>TEXT</fieldType>\n"
    "      <fieldData><![CDATA[<p>5.11.25</p>"
    "<p>pVV019 was inoculated from glycerol stocks - BL21 (DE3)"
    "<br>100 ml of LB culture</p>"
    "<p>2.25 uM depot + 1.8 uM Eylea</p>]]></fieldData>\n"
    "      <imageList>\n"
    '        <image-Info id="1">\n'
    "          <fileName>test_image.png</fileName>\n"
    "          <name>Test Image</name>\n"
    "          <contentType>image/png</contentType>\n"
    "          <extension>png</extension>\n"
    "          <creationDate>2025-11-05T16:22:42Z</creationDate>\n"
    "          <modificationDate>2025-11-05T16:22:42Z</modificationDate>\n"
    "          <createdBy>test.user@example.com</createdBy>\n"
    "        </image-Info>\n"
    "      </imageList>\n"
    "      <attachList>\n"
    '        <attach-info id="2">\n'
    "          <fileName>test_data.xlsx</fileName>\n"
    "          <name>Test Data</name>\n"
    "          <contentType>"
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    "</contentType>\n"
    "          <extension>xlsx</extension>\n"
    "          <creationDate>2025-11-05T16:22:42Z</creationDate>\n"
    "          <modificationDate>2025-11-05T16:22:42Z</modificationDate>\n"
    "          <createdBy>test.user@example.com</createdBy>\n"
    "        </attach-info>\n"
    "      </attachList>\n"
    "    </field>\n"
    "  </listFields>\n"
    "</archivalDocument>\n"
)

FORM_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<form id="5"><code>doc_test_form</code><type>NORMAL</type></form>\n'
)


@pytest.fixture
def lab_book_dir(tmp_path: Path) -> Path:
    """Create a minimal lab book directory with one entry."""
    entry_dir = tmp_path / "doc_Test-experiment-12345"
    entry_dir.mkdir()

    (entry_dir / "doc_Test-experiment-12345.xml").write_text(SAMPLE_XML, encoding="utf-8")
    (entry_dir / "doc_Test-experiment-12345_form.xml").write_text(FORM_XML, encoding="utf-8")
    # Create dummy image and attachment files
    (entry_dir / "test_image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (entry_dir / "test_data.xlsx").write_bytes(b"PK\x03\x04")

    return tmp_path


# ---------------------------------------------------------------------------
# classify_file_type
# ---------------------------------------------------------------------------


class TestClassifyFileType:
    def test_png_is_image(self):
        assert classify_file_type(".png") == "image"

    def test_jpg_is_image(self):
        assert classify_file_type("jpg") == "image"

    def test_xlsx_is_data(self):
        assert classify_file_type(".xlsx") == "data"

    def test_csv_is_data(self):
        assert classify_file_type("csv") == "data"

    def test_pptx_is_report(self):
        assert classify_file_type(".pptx") == "report"

    def test_docx_is_report(self):
        assert classify_file_type(".docx") == "report"

    def test_empty_is_report(self):
        assert classify_file_type("") == "report"

    def test_unknown_is_report(self):
        assert classify_file_type(".xyz") == "report"


# ---------------------------------------------------------------------------
# strip_html
# ---------------------------------------------------------------------------


class TestStripHtml:
    def test_empty_string(self):
        assert strip_html("") == ""

    def test_none_returns_empty(self):
        assert strip_html(None) == ""

    def test_plain_text_unchanged(self):
        assert strip_html("hello world") == "hello world"

    def test_paragraphs_become_newlines(self):
        result = strip_html("<p>line1</p><p>line2</p>")
        assert "line1" in result
        assert "line2" in result

    def test_br_becomes_newline(self):
        result = strip_html("line1<br>line2")
        assert "line1" in result
        assert "line2" in result

    def test_entities_decoded(self):
        result = strip_html("& '")
        assert "&" in result
        assert "'" in result

    def test_nbsp_decoded(self):
        result = strip_html("a&nbsp;b")
        assert "a b" in result

    def test_nested_tags_stripped(self):
        result = strip_html("<p><strong>bold</strong> text</p>")
        assert "bold" in result
        assert "text" in result
        assert "<" not in result


# ---------------------------------------------------------------------------
# LabBookXMLParser
# ---------------------------------------------------------------------------


class TestLabBookXMLParser:
    def test_list_entries(self, lab_book_dir: Path):
        parser = LabBookXMLParser(lab_book_dir)
        entries = parser.list_entries()
        assert len(entries) == 1
        assert entries[0].name.endswith(".xml")
        assert "_form.xml" not in entries[0].name

    def test_list_entries_empty_dir(self, tmp_path: Path):
        parser = LabBookXMLParser(tmp_path)
        assert parser.list_entries() == []

    def test_list_entries_nonexistent_dir(self, tmp_path: Path):
        parser = LabBookXMLParser(tmp_path / "nonexistent")
        assert parser.list_entries() == []

    def test_parse_entry_metadata(self, lab_book_dir: Path):
        parser = LabBookXMLParser(lab_book_dir)
        entries = parser.list_entries()
        entry = parser.parse_entry(entries[0])

        assert entry.doc_id == "12345"
        assert entry.name == "Test experiment with pVV019"
        assert entry.created_by == "test.user@example.com"
        assert entry.creation_date == "2025-11-05T16:22:42Z"
        assert entry.last_modified_date == "2026-01-07T12:32:03Z"

    def test_parse_entry_html_stripped(self, lab_book_dir: Path):
        parser = LabBookXMLParser(lab_book_dir)
        entries = parser.list_entries()
        entry = parser.parse_entry(entries[0])

        assert "<p>" not in entry.plain_text
        assert "pVV019" in entry.plain_text
        assert "BL21" in entry.plain_text
        assert "2.25 uM" in entry.plain_text

    def test_parse_entry_raw_html_preserved(self, lab_book_dir: Path):
        parser = LabBookXMLParser(lab_book_dir)
        entries = parser.list_entries()
        entry = parser.parse_entry(entries[0])

        # raw_html should contain the HTML content (either entity-escaped or CDATA-decoded)
        assert "pVV019" in entry.raw_html
        assert "5.11.25" in entry.raw_html

    def test_parse_entry_images(self, lab_book_dir: Path):
        parser = LabBookXMLParser(lab_book_dir)
        entries = parser.list_entries()
        entry = parser.parse_entry(entries[0])

        assert len(entry.images) == 1
        img = entry.images[0]
        assert img.file_name == "test_image.png"
        assert img.display_name == "Test Image"
        assert img.extension == "png"
        assert img.content_type == "image/png"

    def test_parse_entry_attachments(self, lab_book_dir: Path):
        parser = LabBookXMLParser(lab_book_dir)
        entries = parser.list_entries()
        entry = parser.parse_entry(entries[0])

        assert len(entry.attachments) == 1
        att = entry.attachments[0]
        assert att.file_name == "test_data.xlsx"
        assert att.display_name == "Test Data"
        assert att.extension == "xlsx"

    def test_parse_entry_source_paths(self, lab_book_dir: Path):
        parser = LabBookXMLParser(lab_book_dir)
        entries = parser.list_entries()
        entry = parser.parse_entry(entries[0])

        assert entry.source_xml_path is not None
        assert entry.source_xml_path.exists()
        assert entry.source_folder is not None
        assert entry.source_folder.exists()

    def test_parse_all(self, lab_book_dir: Path):
        parser = LabBookXMLParser(lab_book_dir)
        all_entries = parser.parse_all()
        assert len(all_entries) == 1
        assert isinstance(all_entries[0], LabBookEntry)

    def test_parse_all_skips_malformed(self, lab_book_dir: Path):
        # Add a malformed XML file
        bad_dir = lab_book_dir / "doc_Bad-entry-99999"
        bad_dir.mkdir()
        (bad_dir / "doc_Bad-entry-99999.xml").write_text("not valid xml", encoding="utf-8")

        parser = LabBookXMLParser(lab_book_dir)
        all_entries = parser.parse_all()
        # Should still parse the good one, skip the bad one
        assert len(all_entries) == 1
        assert all_entries[0].doc_id == "12345"


# ---------------------------------------------------------------------------
# Dataclass construction
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_lab_book_image_defaults(self):
        img = LabBookImage(
            id="1",
            file_name="test.png",
            display_name="Test",
            content_type="image/png",
            extension="png",
            creation_date="2025-01-01",
            modification_date="2025-01-01",
            created_by="user",
        )
        assert img.file_name == "test.png"

    def test_lab_book_entry_defaults(self):
        entry = LabBookEntry(
            doc_id="123",
            name="Test",
            created_by="user",
            creation_date="2025-01-01",
            last_modified_date="2025-01-01",
            folder_id="1",
            folder_name="Test",
            raw_html="<p>test</p>",
            plain_text="test",
        )
        assert entry.images == []
        assert entry.attachments == []
        assert entry.source_xml_path is None
