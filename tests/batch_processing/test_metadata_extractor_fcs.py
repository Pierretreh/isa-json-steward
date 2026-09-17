"""Tests for the corrected FCS metadata extraction in MetadataExtractor.

Covers:
  * A1 - the fixed FCS header / TEXT-segment parser (instrument, operator,
    date, channels) against the real E100 .fcs files.
  * A2 - the folder-level FCS acquisition aggregator and Live/Dead detection.
  * Pure-unit helpers (_parse_fcs_date, _infer_fcs_markers) that do not require
    the representative dataset, so they run in every environment.
"""

import sys
from pathlib import Path

import pytest

# Make the ``scripts`` package importable when running pytest from the
# repository root (matches the pattern used in the sibling test files).
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.batch.metadata_extractor import MetadataExtractor  # noqa: E402

E100_FOLDER_NAME = "E100_Explant_FACS_pVV021 und cleav 0,5 zu 4uM_n=5"


@pytest.fixture
def extractor():
    return MetadataExtractor()


# ---------------------------------------------------------------------------
# Pure unit tests (no representative data required)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFcsDateParser:
    """Cover the best-effort $DATE -> ISO conversion."""

    def test_dec_month_format(self, extractor):
        # BD/FACSJazz style: "16-DEC-2025"
        assert extractor._parse_fcs_date("16-DEC-2025") == "2025-12-16"

    def test_iso_format(self, extractor):
        assert extractor._parse_fcs_date("2025-12-16") == "2025-12-16"

    def test_dotted_european(self, extractor):
        assert extractor._parse_fcs_date("16.12.2025") == "2025-12-16"

    def test_empty_returns_empty(self, extractor):
        assert extractor._parse_fcs_date("") == ""
        assert extractor._parse_fcs_date("   ") == ""

    def test_unparseable_returns_empty(self, extractor):
        assert extractor._parse_fcs_date("not-a-date") == ""


@pytest.mark.unit
class TestFcsMarkerInference:
    """Cover the project-specific channel -> dye mapping."""

    def test_calcein_and_pi_detected(self, extractor):
        channels = ["FSC-A", "SSC-A", "FITC-A", "PI-A", "Time"]
        markers = extractor._infer_fcs_markers(channels)
        dyes = {m["dye"] for m in markers}
        assert "Calcein-AM" in dyes
        assert "Propidium Iodide" in dyes
        # Roles are assigned correctly.
        roles = {m["dye"]: m["role"] for m in markers}
        assert roles["Calcein-AM"] == "live"
        assert roles["Propidium Iodide"] == "dead"

    def test_dapi_detected(self, extractor):
        markers = extractor._infer_fcs_markers(["DAPI-A"])
        assert markers == [{"channel": "DAPI-A", "dye": "DAPI", "role": "nucleus"}]

    def test_no_relevant_channels(self, extractor):
        assert extractor._infer_fcs_markers(["FSC-A", "SSC-H", "Time"]) == []

    def test_empty_channels(self, extractor):
        assert extractor._infer_fcs_markers([]) == []


# ---------------------------------------------------------------------------
# Data-dependent tests against the real E100 .fcs files
# ---------------------------------------------------------------------------


@pytest.mark.requires_data
@pytest.mark.batch_component
class TestFcsMetadataOnE100:
    """Validate the corrected parser against the real E100 dataset.

    Expected header facts (extracted manually from the FCS TEXT segment):
      $CYT  = LSRFortessa      (BD instrument)
      $OP   = Boneva           (operator)
      $DATE = 16-DEC-2025      (-> ISO 2025-12-16)
      channels include FITC-A and PI-A  (Live/Dead viability assay)
    """

    def _e100_folder(self, representative_data_path):
        if not representative_data_path:
            pytest.skip("Representative data not available")
        folder = representative_data_path / E100_FOLDER_NAME
        if not folder.exists():
            pytest.skip(f"E100 folder not found: {folder}")
        return folder

    def test_single_file_header_fields(self, extractor, representative_data_path):
        folder = self._e100_folder(representative_data_path)
        fcs_files = sorted(folder.rglob("*.fcs"))
        assert fcs_files, "E100 should contain .fcs files"

        md = extractor.extract_fcs_metadata(str(fcs_files[0]))

        # Core, previously-missing acquisition fields are now populated.
        assert md["instrument"] == "LSRFortessa"
        assert md["operator"] == "Boneva"
        assert md["acquisition_date"] == "16-DEC-2025"
        assert md["acquisition_date_iso"] == "2025-12-16"

        # Channel list is ordered and includes the viability readout channels.
        assert "FITC-A" in md["channels"]
        assert "PI-A" in md["channels"]

        # Backward-compatible keys are still emitted (and now correct).
        assert md["file_type"] == "fcs"
        assert "$PAR" in md  # parameter count keyword echoed
        assert "$TOT" in md  # total events keyword echoed

    def test_per_file_markers_and_live_dead(self, extractor, representative_data_path):
        folder = self._e100_folder(representative_data_path)
        fcs_files = sorted(folder.rglob("*.fcs"))

        for fp in fcs_files:
            md = extractor.extract_fcs_metadata(str(fp))
            dyes = {m["dye"] for m in md["markers"]}
            assert "Calcein-AM" in dyes, f"Calcein-AM missing in {fp.name}"
            assert "Propidium Iodide" in dyes, f"PI missing in {fp.name}"

    def test_acquisition_summary_consensus(self, extractor, representative_data_path):
        folder = self._e100_folder(representative_data_path)
        fcs_files = sorted(folder.rglob("*.fcs"))

        summary = extractor.extract_fcs_acquisition_summary(str(folder))

        # Every .fcs file is accounted for.
        assert summary["file_count"] == len(fcs_files)

        # Consensus fields match the known instrument/operator/date.
        assert summary["instrument"] == "LSRFortessa"
        assert summary["operator"] == "Boneva"
        assert summary["acquisition_date_iso"] == "2025-12-16"
        assert summary["acquisition_date"] == "16-DEC-2025"

        # Aggregated channels include the viability pair and the Live/Dead
        # heuristic flags the experiment correctly.
        assert "FITC-A" in summary["channels"]
        assert "PI-A" in summary["channels"]
        assert summary["is_live_dead"] is True

        # per_file detail mirrors the number of files scanned.
        assert len(summary["per_file"]) == len(fcs_files)

    def test_summary_handles_empty_folder(self, extractor, tmp_path):
        # No .fcs files -> graceful fallback dictionary.
        summary = extractor.extract_fcs_acquisition_summary(str(tmp_path))
        assert summary == {"file_count": 0}
