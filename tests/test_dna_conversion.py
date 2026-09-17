"""
Tests for SnapGene .dna to GenBank (.gb) conversion.

Tests the FileConverter.convert_dna_to_genbank() method using synthetic
.dna files created as ZIP archives with XML content.
"""

import io
import zipfile
from pathlib import Path
from typing import Optional

import pytest

from utils.file_converter import FileConverter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_dna_xml(
    name: str = "pTEST001",
    sequence: str = "ATGCGATCGATCGATCGATCGATCGATCGATCGATCGATCG",
    circular: bool = True,
    features: Optional[list] = None,
) -> str:
    """
    Build a minimal SnapGene-style XML document string.

    Args:
        name: Plasmid / sequence name
        sequence: DNA sequence string
        circular: Whether the molecule is circular
        features: Optional list of dicts with keys: type, start, end, label, directionality

    Returns:
        XML string
    """
    topology_attr = ' circular="true"' if circular else ' circular="false"'

    features_xml = ""
    if features:
        feature_elements = []
        for f in features:
            ftype = f.get("type", "misc_feature")
            start = f.get("start", 0)
            end = f.get("end", len(sequence))
            label = f.get("label", "")
            directionality = f.get("directionality", "1")
            note = f.get("note", "")

            note_xml = f"<Note>{note}</Note>" if note else ""
            feature_elements.append(
                f'<Feature type="{ftype}" directionality="{directionality}">'
                f'<Start position="{start}"/>'
                f'<End position="{end}"/>'
                f"<Label>{label}</Label>"
                f"{note_xml}"
                f"</Feature>"
            )
        features_xml = "<Features>" + "".join(feature_elements) + "</Features>"

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<DnaDocument>
  <Name>{name}</Name>
  <Properties{topology_attr}/>
  <Sequence>{sequence}</Sequence>
  {features_xml}
</DnaDocument>"""
    return xml


def _create_dna_zip(xml_content: str, xml_filename: str = "content.xml") -> bytes:
    """
    Create an in-memory ZIP archive containing the given XML content.

    Returns:
        Bytes of the ZIP archive
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(xml_filename, xml_content)
    return buf.getvalue()


@pytest.fixture
def converter():
    """Provide a FileConverter instance."""
    return FileConverter()


@pytest.fixture
def simple_dna_file(tmp_path: Path) -> Path:
    """Create a minimal .dna file with a simple sequence."""
    xml = _build_dna_xml(name="pTEST001", sequence="ATGCGATCGATCGATCGATCG")
    dna_path = tmp_path / "pTEST001.dna"
    dna_path.write_bytes(_create_dna_zip(xml))
    return dna_path


@pytest.fixture
def dna_file_with_features(tmp_path: Path) -> Path:
    """Create a .dna file with annotated features."""
    seq = "ATGCGATCGATCGATCGATCGATCGATCGATCGATCGATCG"
    features = [
        {
            "type": "CDS",
            "start": 0,
            "end": 12,
            "label": "geneA",
            "directionality": "1",
            "note": "Test gene A",
        },
        {
            "type": "promoter",
            "start": 15,
            "end": 30,
            "label": "pBAD",
            "directionality": "1",
        },
    ]
    xml = _build_dna_xml(name="pFEAT001", sequence=seq, features=features)
    dna_path = tmp_path / "pFEAT001.dna"
    dna_path.write_bytes(_create_dna_zip(xml))
    return dna_path


@pytest.fixture
def linear_dna_file(tmp_path: Path) -> Path:
    """Create a .dna file representing a linear molecule."""
    xml = _build_dna_xml(
        name="linSEQ01",
        sequence="ATGCGATCGATCGATCGATCGATCG",
        circular=False,
    )
    dna_path = tmp_path / "linSEQ01.dna"
    dna_path.write_bytes(_create_dna_zip(xml))
    return dna_path


@pytest.fixture
def empty_sequence_dna_file(tmp_path: Path) -> Path:
    """Create a .dna file with an empty sequence."""
    xml = _build_dna_xml(name="pEMPTY", sequence="")
    dna_path = tmp_path / "pEMPTY.dna"
    dna_path.write_bytes(_create_dna_zip(xml))
    return dna_path


@pytest.fixture
def invalid_zip_file(tmp_path: Path) -> Path:
    """Create a file with .dna extension that is not a valid ZIP."""
    bad_path = tmp_path / "bad.dna"
    bad_path.write_bytes(b"this is not a zip file")
    return bad_path


@pytest.fixture
def no_sequence_dna_file(tmp_path: Path) -> Path:
    """Create a .dna ZIP with XML that lacks a <Sequence> element."""
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<DnaDocument><Name>noSeq</Name></DnaDocument>'
    dna_path = tmp_path / "noSeq.dna"
    dna_path.write_bytes(_create_dna_zip(xml))
    return dna_path


# ---------------------------------------------------------------------------
# Tests: Successful conversion
# ---------------------------------------------------------------------------


class TestConvertDnaToGenBank:
    """Tests for successful .dna to .gb conversion."""

    def test_simple_conversion(self, converter, simple_dna_file, tmp_path):
        """Basic conversion produces a valid .gb file."""
        target = tmp_path / "output.gb"
        result = converter.convert_dna_to_genbank(simple_dna_file, target)

        assert result["success"] is True
        assert target.exists()
        assert result["metadata"]["original_format"] == ".dna"
        assert result["metadata"]["sequence_count"] == 1
        assert result["metadata"]["sequence_lengths"] == [21]
        assert result["metadata"]["sequence_ids"] == ["pTEST001"]

    def test_genbank_content_readable(self, converter, simple_dna_file, tmp_path):
        """The generated .gb file can be parsed back by Biopython."""
        from Bio import SeqIO

        target = tmp_path / "output.gb"
        converter.convert_dna_to_genbank(simple_dna_file, target)

        records = list(SeqIO.parse(target, "genbank"))
        assert len(records) == 1
        assert str(records[0].seq) == "ATGCGATCGATCGATCGATCG"
        assert records[0].annotations.get("molecule_type") == "DNA"

    def test_circular_topology(self, converter, simple_dna_file, tmp_path):
        """Circular plasmid gets 'circular' topology annotation."""
        from Bio import SeqIO

        target = tmp_path / "output.gb"
        converter.convert_dna_to_genbank(simple_dna_file, target)

        records = list(SeqIO.parse(target, "genbank"))
        assert records[0].annotations.get("topology") == "circular"

    def test_linear_topology(self, converter, linear_dna_file, tmp_path):
        """Linear molecule gets 'linear' topology annotation."""
        from Bio import SeqIO

        target = tmp_path / "output.gb"
        converter.convert_dna_to_genbank(linear_dna_file, target)

        records = list(SeqIO.parse(target, "genbank"))
        assert records[0].annotations.get("topology") == "linear"

    def test_features_extracted(self, converter, dna_file_with_features, tmp_path):
        """Features from the .dna XML are present in the GenBank output."""
        from Bio import SeqIO

        target = tmp_path / "output.gb"
        result = converter.convert_dna_to_genbank(dna_file_with_features, target)

        assert result["success"] is True
        assert result["metadata"]["feature_count"] == 2

        records = list(SeqIO.parse(target, "genbank"))
        feature_types = [f.type for f in records[0].features]
        assert "CDS" in feature_types
        assert "promoter" in feature_types

    def test_feature_labels_preserved(self, converter, dna_file_with_features, tmp_path):
        """Feature labels are carried through to GenBank qualifiers."""
        from Bio import SeqIO

        target = tmp_path / "output.gb"
        converter.convert_dna_to_genbank(dna_file_with_features, target)

        records = list(SeqIO.parse(target, "genbank"))
        labels = []
        for f in records[0].features:
            if "label" in f.qualifiers:
                labels.extend(f.qualifiers["label"])
        assert "geneA" in labels
        assert "pBAD" in labels

    def test_hashes_in_metadata(self, converter, simple_dna_file, tmp_path):
        """Conversion result includes SHA-256 hashes of source and target."""
        target = tmp_path / "output.gb"
        result = converter.convert_dna_to_genbank(simple_dna_file, target)

        assert "original_hash" in result["metadata"]
        assert "converted_hash" in result["metadata"]
        assert len(result["metadata"]["original_hash"]) == 64  # SHA-256 hex
        assert len(result["metadata"]["converted_hash"]) == 64

    def test_convert_file_routing(self, converter, simple_dna_file, tmp_path):
        """convert_file() correctly routes .dna files to convert_dna_to_genbank."""
        target = tmp_path / "output.gb"
        result = converter.convert_file(simple_dna_file, target)

        assert result["success"] is True
        assert target.exists()

    def test_get_file_type_dna(self, converter, simple_dna_file):
        """get_file_type() returns 'sequencing' for .dna files."""
        assert converter.get_file_type(simple_dna_file) == "sequencing"

    def test_needs_conversion_dna(self, converter, simple_dna_file):
        """needs_conversion() returns True for .dna files."""
        assert converter.needs_conversion(simple_dna_file, "sequencing") is True


# ---------------------------------------------------------------------------
# Tests: Error handling
# ---------------------------------------------------------------------------


class TestConvertDnaToGenBankErrors:
    """Tests for error handling in .dna conversion."""

    def test_invalid_zip(self, converter, invalid_zip_file, tmp_path):
        """Invalid ZIP archive returns an error."""
        target = tmp_path / "output.gb"
        result = converter.convert_dna_to_genbank(invalid_zip_file, target)

        assert result["success"] is False
        assert "Invalid ZIP archive" in result["error"]

    def test_no_sequence_element(self, converter, no_sequence_dna_file, tmp_path):
        """XML without <Sequence> element returns an error."""
        target = tmp_path / "output.gb"
        result = converter.convert_dna_to_genbank(no_sequence_dna_file, target)

        assert result["success"] is False
        assert "No <Sequence> element" in result["error"]

    def test_empty_sequence(self, converter, empty_sequence_dna_file, tmp_path):
        """Empty sequence returns an error."""
        target = tmp_path / "output.gb"
        result = converter.convert_dna_to_genbank(empty_sequence_dna_file, target)

        assert result["success"] is False
        assert "Empty sequence" in result["error"]

    def test_nonexistent_source(self, converter, tmp_path):
        """Non-existent source file returns an error."""
        source = tmp_path / "nonexistent.dna"
        target = tmp_path / "output.gb"
        result = converter.convert_dna_to_genbank(source, target)

        assert result["success"] is False
        assert result["error"]  # Should have some error message


# ---------------------------------------------------------------------------
# Tests: Conversion log integration
# ---------------------------------------------------------------------------


class TestConversionLogIntegration:
    """Tests that .dna conversions are properly logged."""

    def test_conversion_logged(self, converter, simple_dna_file, tmp_path):
        """Successful .dna conversion is recorded in the conversion log."""
        converter.clear_conversion_log()
        target = tmp_path / "output.gb"
        converter.convert_file(simple_dna_file, target)

        log = converter.get_conversion_log()
        assert len(log) == 1
        assert log[0]["success"] is True
        assert log[0]["file_type"] == "sequencing"
        assert ".dna" in log[0]["source_path"]

    def test_failed_conversion_logged(self, converter, invalid_zip_file, tmp_path):
        """Failed .dna conversion is recorded with error in the log."""
        converter.clear_conversion_log()
        target = tmp_path / "output.gb"
        converter.convert_file(invalid_zip_file, target)

        log = converter.get_conversion_log()
        assert len(log) == 1
        assert log[0]["success"] is False
        assert "error" in log[0]
