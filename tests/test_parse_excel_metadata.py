"""
Tests for the Excel metadata parser (scripts/parse_excel_metadata.py).

These tests use synthetic Excel workbooks created with openpyxl to avoid
requiring the actual data directory.
"""

import json
import os
import sys
from pathlib import Path

import openpyxl
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
    from parse_excel_metadata import (
        _clean_str,
        _extract_sd_number,
        _extract_yfp_timestamp,
        _normalize_plasmid_name,
        build_yfp_sd_mapping,
        enrich_study_json,
        find_study_jsons,
        find_yfp_excel_files,
        parse_invitro_dna_concentrations,
        parse_invitro_dna_description,
        parse_plasmid_description,
        parse_yfp_concentrations,
        save_study_json,
    )
except ImportError:
    pytest.skip(
        "parse_excel_metadata not available (requires profile with scripts/)",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def plasmid_xlsx(tmp_path: Path) -> Path:
    """Create a synthetic Plasmid description.xlsx."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Plasmid ", "Description", "Vector", "Concentration"])
    ws.append(["pVV001", "ZZ domain + Histag from pHB141", "modified pRSET", "52 ng/ul"])
    ws.append(["pVV002", "MBP + Histag", "modified pRSET", "167 ng/ul"])
    ws.append(["pVV019", "MBP+ PPEP1 + FUSn + ZZ + YFP", "modified pRSET", "50 ng/ul"])
    ws.append(["pVV021", "MBP+ PPEP1 + 0.4 FUSn GGG FUSn + ZZ + YFP", "modified pRSET", "67 ng/ul"])
    ws.append([None, None, None, None])  # empty row should be skipped
    path = tmp_path / "Plasmid description.xlsx"
    wb.save(str(path))
    wb.close()
    return path


@pytest.fixture
def invitro_desc_xlsx(tmp_path: Path) -> Path:
    """Create a synthetic In vitro DNA description.xlsx."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["In vitro DNA design", "Description", None])
    ws.append(["IVpVV001", "MBP + PPEP1 + FUSn + FUSn + ZZ domain + YFP", None])
    ws.append(["IVpVV007", "MBP + PPEP1 + hnRNPc + hnRNPc + ZZ domain + YFP", None])
    ws.append(["IVpVV001short", "FUSn + FUSn + ZZ domain + YFP", "Different first block"])
    path = tmp_path / "In vitro DNA description.xlsx"
    wb.save(str(path))
    wb.close()
    return path


@pytest.fixture
def invitro_conc_xlsx(tmp_path: Path) -> Path:
    """Create a synthetic In vitro DNA concentration after PCR.xlsx."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    # Header row
    ws.append(
        [
            "Construct",
            "Insert",
            "Concentration (ng/ul)",
            50,
            "ng",
            None,
            "H2O",
            "Concentration after column purification",
            "With addition of oVV118R",
            "With addition of oVV120R",
            "With addition of oVV119R = final for IV",
        ]
    )
    # IVpVV001 group
    ws.append(
        [
            "IVpVV001",
            "1 (MBP,PPEP1, FUSn)",
            129,
            None,
            None,
            None,
            None,
            "32 ng/ul",
            "160 ng/ul",
            None,
            None,
        ]
    )
    ws.append([None, "2 (FUSn)", 123, None, None, None, None, None, None, None, None])
    ws.append([None, "3 (ZZ)", 52, None, None, None, None, None, None, None, None])
    ws.append([None, "4 (YFP)", 76, None, None, None, None, None, None, None, None])
    # IVpVV007 group
    ws.append(
        [
            "IVpVV007",
            "1 (MBP, PPEP1)",
            124,
            None,
            None,
            None,
            None,
            "42 ng/ul",
            "126 ng/ul",
            None,
            None,
        ]
    )
    ws.append([None, "2 (hnRNPc)", 73, None, None, None, None, None, None, None, None])
    ws.append([None, "3 (hnRNPc)", 73, None, None, None, None, None, None, None, None])
    path = tmp_path / "In vitro DNA concentration after PCR.xlsx"
    wb.save(str(path))
    wb.close()
    return path


@pytest.fixture
def yfp_xlsx(tmp_path: Path) -> Path:
    """Create a synthetic YFP_VV (Modified)_*.xlsx TECAN file."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Result sheet"

    # Build 19-column rows (matching real file structure)
    def _row(*vals):
        """Pad to 19 columns."""
        lst = list(vals)
        while len(lst) < 19:
            lst.append(None)
        return lst

    # Metadata header
    ws.append(_row("Method name: YFP_VV (Modified)"))
    ws.append(_row("Application: SparkControl", None, None, None, "V3.2"))
    ws.append(_row("Device: Spark", None, None, None, "Serial number: 2306000759"))
    ws.append(_row("Firmware:", None, None, None, "LUM:V5.2.4"))
    ws.append(_row(""))
    ws.append(_row("Date:", None, None, None, "2025-10-13"))
    ws.append(_row("Time:", None, None, None, "11:31"))
    ws.append(_row("System", None, None, None, "MSB231120"))
    ws.append(_row("User", None, None, None, "INM-GMBH\\vetyskova"))
    ws.append(_row("Plate", None, None, None, "[COS96fb] - Costar 96 Flat Black"))

    # Padding rows
    for _ in range(40):
        ws.append(_row())

    # Plate readings section
    ws.append(_row("<>", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"))
    ws.append(_row("A", 45530, 11895, 1042, 54, 5, 0, 0, 0, 0, 0, 0, 345))
    ws.append(_row("B", 2958, 2429, 426, 195, 300, 1100, 688, 0, 0, 0, 0, -1))
    ws.append(_row("C", 2316, 876, 218, 121, 348, 303, 544, 0, 0, 0, 0, 0))
    ws.append(_row("D", 4053, 4053, 511, 1099, 937, 221, 389, 0, -1, 0, 0, 0))
    ws.append(_row("E", 477, 0, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    ws.append(_row("F"))
    ws.append(_row("G"))
    ws.append(_row("H"))

    # Padding
    for _ in range(10):
        ws.append(_row())

    # Calibration section
    ws.append(_row("YFP call."))
    ws.append(_row(100, 45530))
    ws.append(_row(10, 11895))
    ws.append(_row(1, 1042))
    ws.append(_row(0.1, 54))
    ws.append(_row(0.01, 5))
    ws.append(_row(0, 0))
    for _ in range(4):
        ws.append(_row())
    ws.append(_row("y = 1193.9x - 53.573"))
    ws.append(_row(53.573))
    ws.append(_row(1193.9))

    # Padding
    for _ in range(5):
        ws.append(_row())

    # Sample layout section
    ws.append(_row("<>", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"))
    ws.append(_row("A", "YFP 100", "YFP 10", "YFP 1", "YFP 0.1", "YFP 0.01", 0))
    ws.append(
        _row(
            "B", "Sample 1", "Sample 2", "Sample 3", "Sample 4", "Sample 5", "Sample 6", "Sample 7"
        )
    )
    ws.append(
        _row(
            "C",
            "Sample 8",
            "Sample 9",
            "Sample 10",
            "Sample 11",
            "Sample 12",
            "Sample 13",
            "Sample 14",
        )
    )
    ws.append(
        _row(
            "D",
            "Sample 15",
            "Sample 16",
            "Sample 17",
            "Sample 18",
            "Sample 19",
            "Sample 20",
            "Sample 21",
        )
    )
    ws.append(_row("E", "Sample 22"))

    path = tmp_path / "YFP_VV (Modified)_20251013_113122.xlsx"
    wb.save(str(path))
    wb.close()
    return path


@pytest.fixture
def sample_study_json(tmp_path: Path) -> Path:
    """Create a sample study JSON file."""
    study_dir = tmp_path / "study_SD25404_Analysis_of_purified_pVV021_apod"
    study_dir.mkdir(parents=True)
    data = {
        "studies": [
            {
                "identifier": "study_SD25404_Analysis_of_purified_pVV021_apod",
                "title": "Analysis of purified pVV021 apod (SD25404)",
                "description": "Test study",
                "comments": [
                    {"name": "SD Number", "value": "SD25404"},
                    {"name": "Lab Book Pages", "value": "Pages 12-13"},
                ],
                "factors": [],
                "assays": [],
                "materials": {"samples": [], "otherMaterials": [], "sources": []},
            }
        ]
    }
    path = study_dir / "study.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return path


@pytest.fixture
def sample_study_json_invitro(tmp_path: Path) -> Path:
    """Create a sample study JSON referencing an in vitro DNA construct."""
    study_dir = tmp_path / "study_SD95587_Lysate_023_and_006_w_wo_PPEP1"
    study_dir.mkdir(parents=True)
    data = {
        "studies": [
            {
                "identifier": "study_SD95587_Lysate_023_and_006_w_wo_PPEP1",
                "title": "Lysate IVpVV001 and IVpVV007 w/wo PPEP1 (SD95587)",
                "description": "Test study with in vitro DNA",
                "comments": [
                    {"name": "SD Number", "value": "SD95587"},
                ],
                "factors": [],
                "assays": [],
                "materials": {"samples": [], "otherMaterials": [], "sources": []},
            }
        ]
    }
    path = study_dir / "study.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return path


# ---------------------------------------------------------------------------
# Tests: parse_plasmid_description
# ---------------------------------------------------------------------------


class TestParsePlasmidDescription:
    """Tests for parse_plasmid_description."""

    def test_parses_all_rows(self, plasmid_xlsx: Path):
        result = parse_plasmid_description(plasmid_xlsx)
        assert len(result) == 4

    def test_first_plasmid(self, plasmid_xlsx: Path):
        result = parse_plasmid_description(plasmid_xlsx)
        assert result[0]["name"] == "pVV001"
        assert result[0]["description"] == "ZZ domain + Histag from pHB141"
        assert result[0]["vector"] == "modified pRSET"
        assert result[0]["concentration"] == "52 ng/ul"

    def test_plasmid_019(self, plasmid_xlsx: Path):
        result = parse_plasmid_description(plasmid_xlsx)
        pvv019 = [p for p in result if "pVV019" in p["name"]][0]
        assert "MBP" in pvv019["description"]
        assert pvv019["concentration"] == "50 ng/ul"

    def test_skips_empty_rows(self, plasmid_xlsx: Path):
        result = parse_plasmid_description(plasmid_xlsx)
        names = [p["name"] for p in result]
        assert all(n for n in names)

    def test_empty_file(self, tmp_path: Path):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Plasmid", "Description", "Vector", "Concentration"])
        path = tmp_path / "empty.xlsx"
        wb.save(str(path))
        wb.close()
        result = parse_plasmid_description(path)
        assert result == []

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            parse_plasmid_description(tmp_path / "nonexistent.xlsx")


# ---------------------------------------------------------------------------
# Tests: parse_yfp_concentrations
# ---------------------------------------------------------------------------


class TestParseYfpConcentrations:
    """Tests for parse_yfp_concentrations."""

    def test_metadata_extraction(self, yfp_xlsx: Path):
        result = parse_yfp_concentrations(yfp_xlsx)
        meta = result["metadata"]
        assert meta["date"] == "2025-10-13"
        assert meta["time"] == "11:31"
        assert "YFP_VV" in meta["method"]
        assert "Spark" in meta["device"]
        assert "vetyskova" in meta["user"]

    def test_plate_readings(self, yfp_xlsx: Path):
        result = parse_yfp_concentrations(yfp_xlsx)
        readings = result["plate_readings"]
        assert readings["A1"] == 45530
        assert readings["A2"] == 11895
        assert readings["B1"] == 2958
        assert readings["E1"] == 477
        # Empty wells should not be present
        assert "F1" not in readings

    def test_calibration_curve(self, yfp_xlsx: Path):
        result = parse_yfp_concentrations(yfp_xlsx)
        cal = result["calibration"]
        assert cal["equation"] == "y = 1193.9x - 53.573"
        assert cal["slope"] == 1193.9
        assert cal["intercept"] == pytest.approx(-53.573)
        assert len(cal["standards"]) == 6
        # Check first standard
        assert cal["standards"][0]["concentration"] == 100
        assert cal["standards"][0]["fluorescence"] == 45530

    def test_sample_layout(self, yfp_xlsx: Path):
        result = parse_yfp_concentrations(yfp_xlsx)
        layout = result["sample_layout"]
        assert layout["A1"] == "YFP 100"
        assert layout["B1"] == "Sample 1"
        assert layout["E1"] == "Sample 22"

    def test_returns_dict_keys(self, yfp_xlsx: Path):
        result = parse_yfp_concentrations(yfp_xlsx)
        assert "metadata" in result
        assert "plate_readings" in result
        assert "calibration" in result
        assert "sample_layout" in result


# ---------------------------------------------------------------------------
# Tests: parse_invitro_dna_description
# ---------------------------------------------------------------------------


class TestParseInvitroDnaDescription:
    """Tests for parse_invitro_dna_description."""

    def test_parses_all_constructs(self, invitro_desc_xlsx: Path):
        result = parse_invitro_dna_description(invitro_desc_xlsx)
        assert len(result) == 3

    def test_first_construct(self, invitro_desc_xlsx: Path):
        result = parse_invitro_dna_description(invitro_desc_xlsx)
        assert result[0]["name"] == "IVpVV001"
        assert "MBP" in result[0]["description"]
        assert "YFP" in result[0]["description"]

    def test_construct_with_notes(self, invitro_desc_xlsx: Path):
        result = parse_invitro_dna_description(invitro_desc_xlsx)
        short = [c for c in result if "short" in c["name"]][0]
        assert short["notes"] != ""

    def test_empty_file(self, tmp_path: Path):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["In vitro DNA design", "Description", None])
        path = tmp_path / "empty.xlsx"
        wb.save(str(path))
        wb.close()
        result = parse_invitro_dna_description(path)
        assert result == []


# ---------------------------------------------------------------------------
# Tests: parse_invitro_dna_concentrations
# ---------------------------------------------------------------------------


class TestParseInvitroDnaConcentrations:
    """Tests for parse_invitro_dna_concentrations."""

    def test_parses_constructs(self, invitro_conc_xlsx: Path):
        result = parse_invitro_dna_concentrations(invitro_conc_xlsx)
        assert "IVpVV001" in result
        assert "IVpVV007" in result

    def test_insert_count(self, invitro_conc_xlsx: Path):
        result = parse_invitro_dna_concentrations(invitro_conc_xlsx)
        assert len(result["IVpVV001"]["inserts"]) == 4
        assert len(result["IVpVV007"]["inserts"]) == 3

    def test_insert_concentrations(self, invitro_conc_xlsx: Path):
        result = parse_invitro_dna_concentrations(invitro_conc_xlsx)
        inserts = result["IVpVV001"]["inserts"]
        assert inserts[0]["name"] == "1 (MBP,PPEP1, FUSn)"
        assert inserts[0]["concentration_ng_ul"] == 129
        assert inserts[1]["concentration_ng_ul"] == 123

    def test_purification_data(self, invitro_conc_xlsx: Path):
        result = parse_invitro_dna_concentrations(invitro_conc_xlsx)
        assert result["IVpVV001"]["concentration_after_purification"] == "32 ng/ul"
        assert result["IVpVV001"]["with_oVV118R"] == "160 ng/ul"

    def test_empty_file(self, tmp_path: Path):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Construct", "Insert", "Concentration (ng/ul)"])
        path = tmp_path / "empty.xlsx"
        wb.save(str(path))
        wb.close()
        result = parse_invitro_dna_concentrations(path)
        assert result == {}


# ---------------------------------------------------------------------------
# Tests: enrich_study_json
# ---------------------------------------------------------------------------


class TestEnrichStudyJson:
    """Tests for enrich_study_json."""

    def test_enriches_with_plasmid_data(self, sample_study_json: Path, plasmid_xlsx: Path):
        plasmid_data = parse_plasmid_description(plasmid_xlsx)
        result = enrich_study_json(sample_study_json, plasmid_data=plasmid_data)
        comments = result["studies"][0]["comments"]
        # pVV021 is in the study title
        pvv021_comments = [c for c in comments if "pVV021" in c["name"]]
        assert len(pvv021_comments) == 1
        assert "0.4 FUSn" in pvv021_comments[0]["value"]

    def test_preserves_existing_comments(self, sample_study_json: Path, plasmid_xlsx: Path):
        plasmid_data = parse_plasmid_description(plasmid_xlsx)
        result = enrich_study_json(sample_study_json, plasmid_data=plasmid_data)
        comments = result["studies"][0]["comments"]
        sd_comments = [c for c in comments if c["name"] == "SD Number"]
        assert len(sd_comments) == 1
        assert sd_comments[0]["value"] == "SD25404"

    def test_no_duplicate_comments(self, sample_study_json: Path, plasmid_xlsx: Path):
        plasmid_data = parse_plasmid_description(plasmid_xlsx)
        # Enrich twice
        result = enrich_study_json(sample_study_json, plasmid_data=plasmid_data)
        save_study_json(result, sample_study_json)
        result2 = enrich_study_json(sample_study_json, plasmid_data=plasmid_data)
        comments = result2["studies"][0]["comments"]
        comment_names = [c["name"] for c in comments]
        # Each comment name should appear only once
        assert len(comment_names) == len(set(comment_names))

    def test_enriches_with_invitro_dna(
        self, sample_study_json_invitro: Path, invitro_desc_xlsx: Path
    ):
        invitro_data = parse_invitro_dna_description(invitro_desc_xlsx)
        result = enrich_study_json(sample_study_json_invitro, invitro_dna_data=invitro_data)
        comments = result["studies"][0]["comments"]
        iv_comments = [c for c in comments if "IVpVV001" in c["name"]]
        assert len(iv_comments) == 1
        assert "MBP" in iv_comments[0]["value"]

    def test_enriches_with_invitro_concentrations(
        self, sample_study_json_invitro: Path, invitro_conc_xlsx: Path
    ):
        conc_data = parse_invitro_dna_concentrations(invitro_conc_xlsx)
        result = enrich_study_json(sample_study_json_invitro, invitro_conc_data=conc_data)
        comments = result["studies"][0]["comments"]
        conc_comments = [c for c in comments if "IV DNA Concentration" in c["name"]]
        assert len(conc_comments) >= 1

    def test_enriches_with_yfp_data(self, sample_study_json: Path, yfp_xlsx: Path):
        """YFP data is added when the lab book links the file to the study's SD."""
        yfp_data = parse_yfp_concentrations(yfp_xlsx)
        yfp_data["source_path"] = str(yfp_xlsx)
        # Study SD is 25404; map the YFP file's timestamp to it.
        yfp_sd_mapping = {"20251013_113122": {"25404"}}
        result = enrich_study_json(
            sample_study_json,
            yfp_files=[yfp_data],
            yfp_sd_mapping=yfp_sd_mapping,
        )
        comments = result["studies"][0]["comments"]
        yfp_comments = [c for c in comments if "YFP Concentration" in c["name"]]
        assert len(yfp_comments) == 1
        assert "Calibration" in yfp_comments[0]["value"]

    def test_no_yfp_when_sd_not_matched(self, sample_study_json: Path, yfp_xlsx: Path):
        """YFP data is NOT added when the study's SD is not in the mapping."""
        yfp_data = parse_yfp_concentrations(yfp_xlsx)
        yfp_data["source_path"] = str(yfp_xlsx)
        # Map timestamp to a different SD (not 25404).
        yfp_sd_mapping = {"20251013_113122": {"99999"}}
        result = enrich_study_json(
            sample_study_json,
            yfp_files=[yfp_data],
            yfp_sd_mapping=yfp_sd_mapping,
        )
        comments = result["studies"][0]["comments"]
        yfp_comments = [c for c in comments if "YFP Concentration" in c["name"]]
        assert len(yfp_comments) == 0

    def test_no_yfp_when_no_mapping(self, sample_study_json: Path, yfp_xlsx: Path):
        """YFP data is NOT added when no lab-book mapping is provided."""
        yfp_data = parse_yfp_concentrations(yfp_xlsx)
        yfp_data["source_path"] = str(yfp_xlsx)
        result = enrich_study_json(sample_study_json, yfp_files=[yfp_data])
        comments = result["studies"][0]["comments"]
        yfp_comments = [c for c in comments if "YFP Concentration" in c["name"]]
        assert len(yfp_comments) == 0

    def test_no_match_no_comments(self, sample_study_json: Path):
        """When no data matches the study title, no new comments are added."""
        # pVV001 is not in the study title "Analysis of purified pVV021 apod"
        plasmid_data = [
            {"name": "pVV001", "description": "test", "vector": "", "concentration": ""}
        ]
        result = enrich_study_json(sample_study_json, plasmid_data=plasmid_data)
        comments = result["studies"][0]["comments"]
        # Only original comments should be present
        assert len(comments) == 2

    def test_missing_study_json(self, tmp_path: Path):
        result = enrich_study_json(tmp_path / "nonexistent.json")
        assert result == {}

    def test_study_without_comments(self, tmp_path: Path):
        """Study JSON without a comments key should get comments added."""
        study_dir = tmp_path / "study_test"
        study_dir.mkdir()
        data = {
            "studies": [
                {
                    "identifier": "test",
                    "title": "Analysis of pVV019",
                    "comments": [],
                    "factors": [],
                    "assays": [],
                    "materials": {"samples": [], "otherMaterials": [], "sources": []},
                }
            ]
        }
        path = study_dir / "study.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        plasmid_data = [
            {
                "name": "pVV019",
                "description": "test desc",
                "vector": "pRSET",
                "concentration": "50 ng/ul",
            }
        ]
        result = enrich_study_json(path, plasmid_data=plasmid_data)
        comments = result["studies"][0]["comments"]
        assert len(comments) == 1
        assert "pVV019" in comments[0]["name"]


# ---------------------------------------------------------------------------
# Tests: utility functions
# ---------------------------------------------------------------------------


class TestUtilityFunctions:
    """Tests for utility/helper functions."""

    def test_clean_str_none(self):
        assert _clean_str(None) == ""

    def test_clean_str_whitespace(self):
        assert _clean_str("  hello  ") == "hello"

    def test_clean_str_number(self):
        assert _clean_str(42) == "42"

    def test_normalize_plasmid_name(self):
        assert _normalize_plasmid_name("pVV019") == "pvv019"
        assert _normalize_plasmid_name(" pVV019 ") == "pvv019"
        assert _normalize_plasmid_name("pVV001 mut ") == "pvv001mut"

    def test_find_study_jsons(self, tmp_path: Path):
        # Create some study directories
        for sd in ["study_SD001_Test", "study_SD002_Test2"]:
            d = tmp_path / sd
            d.mkdir()
            (d / "study.json").write_text("{}")
        # Also create a non-matching directory
        (tmp_path / "other_dir").mkdir()

        result = find_study_jsons(tmp_path)
        assert len(result) == 2

    def test_find_yfp_excel_files(self, tmp_path: Path):
        # Create matching and non-matching files
        (tmp_path / "YFP_VV (Modified)_20251013.xlsx").touch()
        (tmp_path / "other_file.xlsx").touch()
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "YFP_VV (Modified)_20251202.xlsx").touch()

        result = find_yfp_excel_files(tmp_path)
        assert len(result) == 2

    def test_save_study_json(self, tmp_path: Path):
        data = {"studies": [{"test": True}]}
        path = tmp_path / "subdir" / "study.json"
        save_study_json(data, path)
        assert path.exists()
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["studies"][0]["test"] is True

    def test_extract_yfp_timestamp_disk_name(self):
        assert _extract_yfp_timestamp("YFP_VV (Modified)_20251013_113122.xlsx") == "20251013_113122"

    def test_extract_yfp_timestamp_sanitized_name(self):
        # Lab book sanitized name with underscores and hash suffix
        assert (
            _extract_yfp_timestamp("YFP_VV__Modified__20251013_113122_1760349203991.xlsx")
            == "20251013_113122"
        )

    def test_extract_yfp_timestamp_no_match(self):
        assert _extract_yfp_timestamp("no_timestamp.xlsx") is None

    def test_extract_sd_number(self):
        assert _extract_sd_number("study_SD25404_Analysis") == "25404"
        assert _extract_sd_number("", "Analysis ... (SD25404)") == "25404"
        assert _extract_sd_number("no sd here") is None


# ---------------------------------------------------------------------------
# Tests: build_yfp_sd_mapping
# ---------------------------------------------------------------------------

SAMPLE_LABBOOK_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<archivalDocument docId="25404">\n'
    "  <name>Test entry</name>\n"
    "  <createdBy>test.user@example.com</createdBy>\n"
    "  <creationDate>2025-11-05T16:22:42Z</creationDate>\n"
    "  <lastModifiedDate>2025-11-05T16:22:42Z</lastModifiedDate>\n"
    "  <listFields>\n"
    '    <field id="100">\n'
    "      <fieldName>Data</fieldName>\n"
    "      <fieldType>TEXT</fieldType>\n"
    "      <fieldData><![CDATA[<p>data</p>]]></fieldData>\n"
    "      <attachList>\n"
    '        <attach-info id="1">\n'
    "          <fileName>YFP_VV__Modified__20251013_113122_1760349203991.xlsx</fileName>\n"
    "          <name>YFP data</name>\n"
    "          <contentType>application/vnd.openxmlformats-officedocument"
    ".spreadsheetml.sheet</contentType>\n"
    "          <extension>xlsx</extension>\n"
    "          <creationDate>2025-10-13T11:31:22Z</creationDate>\n"
    "          <modificationDate>2025-10-13T11:31:22Z</modificationDate>\n"
    "          <createdBy>test.user@example.com</createdBy>\n"
    "        </attach-info>\n"
    '        <attach-info id="2">\n'
    "          <fileName>other_file.xlsx</fileName>\n"
    "          <name>Other</name>\n"
    "          <contentType>application/vnd.openxmlformats-officedocument"
    ".spreadsheetml.sheet</contentType>\n"
    "          <extension>xlsx</extension>\n"
    "          <creationDate>2025-10-13T11:31:22Z</creationDate>\n"
    "          <modificationDate>2025-10-13T11:31:22Z</modificationDate>\n"
    "          <createdBy>test.user@example.com</createdBy>\n"
    "        </attach-info>\n"
    "      </attachList>\n"
    "    </field>\n"
    "  </listFields>\n"
    "</archivalDocument>\n"
)


class TestBuildYfpSdMapping:
    """Tests for build_yfp_sd_mapping."""

    def test_builds_mapping(self, tmp_path: Path):
        doc_dir = tmp_path / "doc_Test-entry-25404"
        doc_dir.mkdir()
        (doc_dir / "doc.xml").write_text(SAMPLE_LABBOOK_XML, encoding="utf-8")

        mapping = build_yfp_sd_mapping(tmp_path)
        assert "20251013_113122" in mapping
        assert "25404" in mapping["20251013_113122"]
        # The non-YFP attachment (other_file.xlsx) must not be included
        assert mapping["20251013_113122"] == {"25404"}

    def test_empty_when_no_dir(self, tmp_path: Path):
        mapping = build_yfp_sd_mapping(tmp_path / "does_not_exist")
        assert mapping == {}

    def test_empty_when_no_entries(self, tmp_path: Path):
        # Lab book dir exists but has no doc folders
        mapping = build_yfp_sd_mapping(tmp_path)
        assert mapping == {}
