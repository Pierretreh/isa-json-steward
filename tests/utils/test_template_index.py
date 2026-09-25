"""
Unit tests for utils.template_index.

These tests cover:
- pure helper functions: _extract_annotation_label, _relative_path,
  _summarise_assay, _summarise_protocol, _summarise_material_file,
  _summarise_device_file, _format_template_list
- scanner functions against a tmp_path-based mock template tree:
  scan_assay_templates, scan_protocol_templates, scan_material_templates,
  scan_device_templates
- generate_template_index and write_template_index
- edge cases: missing subdirectories, empty directories, malformed JSON,
  non-JSON files, and missing keys
"""

import json
from pathlib import Path
from typing import Any

import pytest

from utils.template_index import (
    _extract_annotation_label,
    _format_template_list,
    _relative_path,
    _summarise_assay,
    _summarise_device_file,
    _summarise_material_file,
    _summarise_protocol,
    generate_template_index,
    scan_assay_templates,
    scan_device_templates,
    scan_material_templates,
    scan_protocol_templates,
    write_template_index,
)

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def templates_root(tmp_path: Path) -> Path:
    """A mock templates/ root with all four template subdirectories."""
    (tmp_path / "assay_templates").mkdir(parents=True)
    (tmp_path / "protocol_templates").mkdir(parents=True)
    (tmp_path / "material_templates").mkdir(parents=True)
    (tmp_path / "device_templates").mkdir(parents=True)
    return tmp_path


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@pytest.fixture
def populated_root(templates_root: Path) -> Path:
    """Templates root populated with one valid file per subdirectory."""
    device = {
        "templates": [
            {"name": "Incubator", "deviceCategory": "culture"},
            {"name": "Shaking Incubator", "deviceCategory": "culture"},
        ]
    }
    _write_json(templates_root / "device_templates" / "culture_devices.json", device)
    assay = {
        "@id": "https://example.org/assays/microscopy",
        "@type": "onto:MicroscopyAssay",
        "name": "Microscopy assay",
        "description": "General microscopy assay",
        "measurementType": {"annotationValue": "microscopy assay", "termSource": "OBI"},
        "technologyType": {"annotationValue": "microscopy"},
        "technologyPlatform": "microscope",
        "parameters": [
            {"name": "magnification"},
            {"name": "exposure time"},
        ],
    }
    _write_json(templates_root / "assay_templates" / "microscopy_assay.json", assay)

    protocol = {
        "@id": "https://example.org/protocols/bacterial_culture",
        "@type": "onto:BacterialCulture",
        "name": "Bacterial culture",
        "description": "Growth of bacteria",
        "protocolType": {"annotationValue": "cell culture", "termSource": "PMDco"},
        "technologyPlatform": "shaking incubator",
        "parameters": [
            {"name": "incubation temperature"},
        ],
    }
    _write_json(templates_root / "protocol_templates" / "bacterial_culture.json", protocol)

    material = {
        "templates": [
            {"name": "Transformed Bacteria", "materialType": "sample"},
            {"name": "Unexpressed Culture", "materialType": "sample"},
        ]
    }
    _write_json(templates_root / "material_templates" / "sample_templates.json", material)

    return templates_root


# ----------------------------------------------------------------------
# _extract_annotation_label
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestExtractAnnotationLabel:
    """Tests for _extract_annotation_label."""

    def test_dict_with_annotation_value(self):
        """An annotation dict returns its annotationValue."""
        assert _extract_annotation_label({"annotationValue": "microscopy"}) == "microscopy"

    def test_dict_without_annotation_value(self):
        """A dict without annotationValue returns an empty string."""
        assert _extract_annotation_label({"termSource": "OBI"}) == ""

    def test_none_returns_empty(self):
        """None returns an empty string."""
        assert _extract_annotation_label(None) == ""

    def test_string_returns_empty(self):
        """Plain strings are not annotation dicts, so they return empty."""
        assert _extract_annotation_label("microscopy") == ""

    def test_list_returns_empty(self):
        """Lists are not annotation dicts, so they return empty."""
        assert _extract_annotation_label(["a", "b"]) == ""


# ----------------------------------------------------------------------
# _relative_path
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestRelativePath:
    """Tests for _relative_path."""

    def test_relative_to_templates_root_parent(self, tmp_path):
        """Paths are relative to the parent of the templates root (forward slashes)."""
        file_path = tmp_path / "templates" / "assay_templates" / "microscopy.json"
        templates_root = tmp_path / "templates"
        expected = "templates/assay_templates/microscopy.json"
        assert _relative_path(file_path, templates_root) == expected

    def test_uses_forward_slashes_on_windows(self, tmp_path):
        """The result always uses POSIX separators."""
        file_path = tmp_path / "t" / "protocol_templates" / "culture.json"
        templates_root = tmp_path / "t"
        result = _relative_path(file_path, templates_root)
        assert "\\" not in result
        assert result == "t/protocol_templates/culture.json"


# ----------------------------------------------------------------------
# _summarise_assay
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestSummariseAssay:
    """Tests for _summarise_assay."""

    def test_full_assay(self, tmp_path):
        """A complete assay template yields all summary fields."""
        data = {
            "@type": "onto:MicroscopyAssay",
            "name": "Microscopy assay",
            "description": "desc",
            "measurementType": {"annotationValue": "microscopy assay"},
            "technologyType": {"annotationValue": "microscopy"},
            "technologyPlatform": "microscope",
            "parameters": [{"name": "p1"}, {"name": "p2"}, {"name": "p3"}],
        }
        file_path = tmp_path / "assay_templates" / "microscopy_assay.json"
        result = _summarise_assay(data, file_path, tmp_path)

        assert result["name"] == "Microscopy assay"
        assert result["description"] == "desc"
        assert result["filename"] == "microscopy_assay.json"
        assert result["path"].endswith("assay_templates/microscopy_assay.json")
        assert result["type"] == "onto:MicroscopyAssay"
        assert result["measurementType"] == "microscopy assay"
        assert result["technologyType"] == "microscopy"
        assert result["technologyPlatform"] == "microscope"
        assert result["parameter_count"] == 3

    def test_dict_type_extracted_via_annotation(self, tmp_path):
        """A dict-form @type is extracted through its annotationValue."""
        data = {"@type": {"annotationValue": "onto:ELISA"}}
        file_path = tmp_path / "a.json"
        result = _summarise_assay(data, file_path, tmp_path)
        assert result["type"] == "onto:ELISA"

    def test_missing_keys_use_defaults(self, tmp_path):
        """Missing keys fall back to sensible defaults."""
        file_path = tmp_path / "assay_templates" / "bare_assay.json"
        result = _summarise_assay({}, file_path, tmp_path)

        assert result["name"] == "bare_assay"
        assert result["description"] == ""
        assert result["filename"] == "bare_assay.json"
        assert result["type"] == ""
        assert result["measurementType"] == ""
        assert result["technologyType"] == ""
        assert result["technologyPlatform"] == ""
        assert result["parameter_count"] == 0

    def test_empty_parameters(self, tmp_path):
        """An empty parameter list yields parameter_count 0."""
        data = {"name": "No params", "parameters": []}
        file_path = tmp_path / "assay_templates" / "no_params.json"
        assert _summarise_assay(data, file_path, tmp_path)["parameter_count"] == 0


# ----------------------------------------------------------------------
# _summarise_protocol
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestSummariseProtocol:
    """Tests for _summarise_protocol."""

    def test_full_protocol(self, tmp_path):
        """A complete protocol template yields all summary fields."""
        data = {
            "@type": "onto:BacterialCulture",
            "name": "Bacterial culture",
            "description": "growth",
            "protocolType": {"annotationValue": "cell culture"},
            "technologyPlatform": "shaking incubator",
            "parameters": [{"name": "temperature"}],
        }
        file_path = tmp_path / "protocol_templates" / "bacterial_culture.json"
        result = _summarise_protocol(data, file_path, tmp_path)

        assert result["name"] == "Bacterial culture"
        assert result["description"] == "growth"
        assert result["filename"] == "bacterial_culture.json"
        assert result["path"].endswith("protocol_templates/bacterial_culture.json")
        assert result["type"] == "onto:BacterialCulture"
        assert result["protocolType"] == "cell culture"
        assert result["technologyPlatform"] == "shaking incubator"
        assert result["parameter_count"] == 1

    def test_dict_type_extracted_via_annotation(self, tmp_path):
        """A dict-form @type is extracted through its annotationValue."""
        data = {"@type": {"annotationValue": "onto:Harvesting"}}
        file_path = tmp_path / "p.json"
        assert _summarise_protocol(data, file_path, tmp_path)["type"] == "onto:Harvesting"

    def test_missing_keys_use_defaults(self, tmp_path):
        """Missing keys fall back to sensible defaults."""
        file_path = tmp_path / "protocol_templates" / "bare_protocol.json"
        result = _summarise_protocol({}, file_path, tmp_path)

        assert result["name"] == "bare_protocol"
        assert result["description"] == ""
        assert result["type"] == ""
        assert result["protocolType"] == ""
        assert result["technologyPlatform"] == ""
        assert result["parameter_count"] == 0


# ----------------------------------------------------------------------
# _summarise_material_file
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestSummariseMaterialFile:
    """Tests for _summarise_material_file."""

    def test_template_count(self, tmp_path):
        """The number of templates in the file is counted."""
        data = {"templates": [{"name": "A"}, {"name": "B"}, {"name": "C"}]}
        file_path = tmp_path / "material_templates" / "sample_templates.json"
        result = _summarise_material_file(data, file_path, tmp_path)

        assert result["filename"] == "sample_templates.json"
        assert result["path"].endswith("material_templates/sample_templates.json")
        assert result["template_count"] == 3

    def test_missing_templates_key(self, tmp_path):
        """A file without a templates list yields template_count 0."""
        file_path = tmp_path / "material_templates" / "empty.json"
        assert _summarise_material_file({}, file_path, tmp_path)["template_count"] == 0

    def test_non_dict_data(self, tmp_path):
        """Non-dict payload yields template_count 0."""
        file_path = tmp_path / "material_templates" / "weird.json"
        assert _summarise_material_file(None, file_path, tmp_path)["template_count"] == 0


# ----------------------------------------------------------------------
# _summarise_device_file
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestSummariseDeviceFile:
    """Tests for _summarise_device_file."""

    def test_template_count(self, tmp_path):
        """The number of templates in the file is counted."""
        data = {"templates": [{"name": "Incubator"}, {"name": "Shaker"}, {"name": "Balance"}]}
        file_path = tmp_path / "device_templates" / "culture_devices.json"
        result = _summarise_device_file(data, file_path, tmp_path)

        assert result["filename"] == "culture_devices.json"
        assert result["path"].endswith("device_templates/culture_devices.json")
        assert result["template_count"] == 3

    def test_missing_templates_key(self, tmp_path):
        """A file without a templates list yields template_count 0."""
        file_path = tmp_path / "device_templates" / "empty.json"
        assert _summarise_device_file({}, file_path, tmp_path)["template_count"] == 0

    def test_non_dict_data(self, tmp_path):
        """Non-dict payload yields template_count 0."""
        file_path = tmp_path / "device_templates" / "weird.json"
        assert _summarise_device_file(None, file_path, tmp_path)["template_count"] == 0


# ----------------------------------------------------------------------
# _format_template_list
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestFormatTemplateList:
    """Tests for _format_template_list."""

    def test_full_index(self):
        """All four sections are rendered with their entries."""
        index = {
            "assay_templates": [{"name": "Microscopy assay"}, {"name": "ELISA"}],
            "protocol_templates": [{"name": "Bacterial culture"}],
            "material_templates": [{"filename": "sample_templates.json"}],
            "device_templates": [{"filename": "culture_devices.json"}],
        }
        text = _format_template_list(index)

        assert "=== Assay Templates ===" in text
        assert "Microscopy assay" in text
        assert "ELISA" in text
        assert "=== Protocol Templates ===" in text
        assert "Bacterial culture" in text
        assert "=== Material Template Files ===" in text
        assert "sample_templates.json" in text
        assert "=== Device Template Files ===" in text
        assert "culture_devices.json" in text

    def test_missing_sections_render_headers_only(self):
        """Missing sections still render their headers."""
        text = _format_template_list({})
        assert "=== Assay Templates ===" in text
        assert "=== Protocol Templates ===" in text
        assert "=== Material Template Files ===" in text
        assert "=== Device Template Files ===" in text

    def test_entries_without_names_use_fallback(self):
        """Assay entries without a name fall back to 'Unknown'."""
        text = _format_template_list({"assay_templates": [{}]})
        assert "Unknown" in text


# ----------------------------------------------------------------------
# scan_assay_templates
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestScanAssayTemplates:
    """Tests for scan_assay_templates."""

    def test_scans_valid_templates(self, templates_root):
        """Valid assay templates are summarised and returned."""
        _write_json(
            templates_root / "assay_templates" / "microscopy_assay.json",
            {
                "name": "Microscopy assay",
                "@type": "onto:MicroscopyAssay",
                "measurementType": {"annotationValue": "microscopy assay"},
                "parameters": [{"name": "magnification"}],
            },
        )
        results = scan_assay_templates(templates_root)

        assert len(results) == 1
        assert results[0]["name"] == "Microscopy assay"
        assert results[0]["type"] == "onto:MicroscopyAssay"
        assert results[0]["measurementType"] == "microscopy assay"
        assert results[0]["parameter_count"] == 1
        assert results[0]["filename"] == "microscopy_assay.json"

    def test_missing_directory_returns_empty(self, tmp_path):
        """A missing assay_templates directory yields an empty list."""
        assert scan_assay_templates(tmp_path) == []

    def test_empty_directory_returns_empty(self, templates_root):
        """An empty assay_templates directory yields an empty list."""
        assert scan_assay_templates(templates_root) == []

    def test_malformed_json_is_skipped(self, templates_root):
        """Malformed JSON files are skipped, valid ones still returned."""
        assay_dir = templates_root / "assay_templates"
        (assay_dir / "broken.json").write_text("{not valid json", encoding="utf-8")
        _write_json(assay_dir / "good.json", {"name": "Good Assay"})

        results = scan_assay_templates(templates_root)
        assert [r["name"] for r in results] == ["Good Assay"]

    def test_non_json_files_ignored(self, templates_root):
        """Non-JSON files in the directory are ignored."""
        assay_dir = templates_root / "assay_templates"
        (assay_dir / "readme.txt").write_text("ignore me", encoding="utf-8")
        assert scan_assay_templates(templates_root) == []

    def test_results_sorted_by_filename(self, templates_root):
        """Templates are returned in sorted filename order."""
        assay_dir = templates_root / "assay_templates"
        _write_json(assay_dir / "zzz.json", {"name": "Z"})
        _write_json(assay_dir / "aaa.json", {"name": "A"})

        results = scan_assay_templates(templates_root)
        assert [r["filename"] for r in results] == ["aaa.json", "zzz.json"]


# ----------------------------------------------------------------------
# scan_protocol_templates
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestScanProtocolTemplates:
    """Tests for scan_protocol_templates."""

    def test_scans_valid_templates(self, templates_root):
        """Valid protocol templates are summarised and returned."""
        _write_json(
            templates_root / "protocol_templates" / "bacterial_culture.json",
            {
                "name": "Bacterial culture",
                "@type": "onto:BacterialCulture",
                "protocolType": {"annotationValue": "cell culture"},
                "parameters": [{"name": "temperature"}],
            },
        )
        results = scan_protocol_templates(templates_root)

        assert len(results) == 1
        assert results[0]["name"] == "Bacterial culture"
        assert results[0]["protocolType"] == "cell culture"
        assert results[0]["parameter_count"] == 1

    def test_missing_directory_returns_empty(self, tmp_path):
        """A missing protocol_templates directory yields an empty list."""
        assert scan_protocol_templates(tmp_path) == []

    def test_empty_directory_returns_empty(self, templates_root):
        """An empty protocol_templates directory yields an empty list."""
        assert scan_protocol_templates(templates_root) == []

    def test_malformed_json_is_skipped(self, templates_root):
        """Malformed JSON files are skipped, valid ones still returned."""
        protocol_dir = templates_root / "protocol_templates"
        (protocol_dir / "broken.json").write_text("not json at all", encoding="utf-8")
        _write_json(protocol_dir / "good.json", {"name": "Good Protocol"})

        results = scan_protocol_templates(templates_root)
        assert [r["name"] for r in results] == ["Good Protocol"]


# ----------------------------------------------------------------------
# scan_material_templates
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestScanMaterialTemplates:
    """Tests for scan_material_templates."""

    def test_scans_valid_templates(self, templates_root):
        """Material template files are listed with their template counts."""
        _write_json(
            templates_root / "material_templates" / "sample_templates.json",
            {"templates": [{"name": "A"}, {"name": "B"}]},
        )
        results = scan_material_templates(templates_root)

        assert len(results) == 1
        assert results[0]["filename"] == "sample_templates.json"
        assert results[0]["template_count"] == 2

    def test_missing_directory_returns_empty(self, tmp_path):
        """A missing material_templates directory yields an empty list."""
        assert scan_material_templates(tmp_path) == []

    def test_empty_directory_returns_empty(self, templates_root):
        """An empty material_templates directory yields an empty list."""
        assert scan_material_templates(templates_root) == []

    def test_malformed_json_is_skipped(self, templates_root):
        """Malformed material JSON files are skipped."""
        material_dir = templates_root / "material_templates"
        (material_dir / "broken.json").write_text("[", encoding="utf-8")
        _write_json(material_dir / "good.json", {"templates": [{"name": "A"}]})

        results = scan_material_templates(templates_root)
        assert [r["filename"] for r in results] == ["good.json"]


# ----------------------------------------------------------------------
# scan_device_templates
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestScanDeviceTemplates:
    """Tests for scan_device_templates."""

    def test_scans_valid_templates(self, templates_root):
        """Device template files are listed with their template counts."""
        _write_json(
            templates_root / "device_templates" / "culture_devices.json",
            {"templates": [{"name": "Incubator"}, {"name": "Shaker"}]},
        )
        results = scan_device_templates(templates_root)

        assert len(results) == 1
        assert results[0]["filename"] == "culture_devices.json"
        assert results[0]["template_count"] == 2

    def test_missing_directory_returns_empty(self, tmp_path):
        """A missing device_templates directory yields an empty list."""
        assert scan_device_templates(tmp_path) == []

    def test_empty_directory_returns_empty(self, templates_root):
        """An empty device_templates directory yields an empty list."""
        assert scan_device_templates(templates_root) == []

    def test_malformed_json_is_skipped(self, templates_root):
        """Malformed device JSON files are skipped."""
        device_dir = templates_root / "device_templates"
        (device_dir / "broken.json").write_text("[", encoding="utf-8")
        _write_json(device_dir / "good.json", {"templates": [{"name": "Incubator"}]})

        results = scan_device_templates(templates_root)
        assert [r["filename"] for r in results] == ["good.json"]


# ----------------------------------------------------------------------
# generate_template_index
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateTemplateIndex:
    """Tests for generate_template_index."""

    def test_full_index_structure(self, populated_root):
        """The index contains counts and all four template sections."""
        index = generate_template_index(populated_root)

        assert set(index) == {
            "generated_at",
            "counts",
            "assay_templates",
            "protocol_templates",
            "material_templates",
            "device_templates",
        }
        assert index["counts"] == {
            "assay": 1,
            "protocol": 1,
            "material_files": 1,
            "device_files": 1,
        }
        assert index["assay_templates"][0]["name"] == "Microscopy assay"
        assert index["protocol_templates"][0]["name"] == "Bacterial culture"
        assert index["material_templates"][0]["filename"] == "sample_templates.json"
        assert index["device_templates"][0]["filename"] == "culture_devices.json"
        assert index["device_templates"][0]["template_count"] == 2

    def test_generated_at_is_iso8601(self, populated_root):
        """generated_at is a parseable ISO-8601 timestamp."""
        index = generate_template_index(populated_root)
        from datetime import datetime

        parsed = datetime.fromisoformat(index["generated_at"])
        assert parsed.tzinfo is not None

    def test_empty_root(self, tmp_path):
        """A root without template subdirectories yields zero counts."""
        index = generate_template_index(tmp_path)
        assert index["counts"] == {
            "assay": 0,
            "protocol": 0,
            "material_files": 0,
            "device_files": 0,
        }
        assert index["assay_templates"] == []
        assert index["protocol_templates"] == []
        assert index["material_templates"] == []
        assert index["device_templates"] == []

    def test_requires_path_object(self, populated_root):
        """generate_template_index expects a Path (strings are not converted)."""
        with pytest.raises(TypeError):
            generate_template_index(str(populated_root))

    def test_path_object_works(self, populated_root):
        """A Path object is processed normally."""
        index = generate_template_index(Path(str(populated_root)))
        assert index["counts"]["assay"] == 1

    def test_multiple_templates_aggregated(self, templates_root):
        """Multiple files per section are all aggregated."""
        assay_dir = templates_root / "assay_templates"
        _write_json(assay_dir / "a.json", {"name": "Assay A"})
        _write_json(assay_dir / "b.json", {"name": "Assay B"})
        _write_json(assay_dir / "c.json", {"name": "Assay C"})

        index = generate_template_index(templates_root)
        assert index["counts"]["assay"] == 3
        assert [t["name"] for t in index["assay_templates"]] == ["Assay A", "Assay B", "Assay C"]


# ----------------------------------------------------------------------
# write_template_index
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestWriteTemplateIndex:
    """Tests for write_template_index."""

    def test_writes_valid_json_index(self, populated_root):
        """template_index.json is written and contains the full index."""
        index = write_template_index(populated_root)
        index_path = populated_root / "template_index.json"

        assert index_path.exists()
        loaded = json.loads(index_path.read_text(encoding="utf-8"))
        assert loaded == index
        assert loaded["counts"] == {
            "assay": 1,
            "protocol": 1,
            "material_files": 1,
            "device_files": 1,
        }

    def test_writes_text_list(self, populated_root):
        """template_list.txt is written and lists the templates."""
        write_template_index(populated_root)
        list_path = populated_root / "template_list.txt"

        assert list_path.exists()
        text = list_path.read_text(encoding="utf-8")
        assert "=== Assay Templates ===" in text
        assert "Microscopy assay" in text
        assert "=== Protocol Templates ===" in text
        assert "Bacterial culture" in text
        assert "=== Material Template Files ===" in text
        assert "sample_templates.json" in text
        assert "=== Device Template Files ===" in text
        assert "culture_devices.json" in text

    def test_returns_index_dict(self, populated_root):
        """The returned value is the generated index dict."""
        index = write_template_index(populated_root)
        assert isinstance(index, dict)
        assert "generated_at" in index
        assert "counts" in index

    def test_accepts_string_path(self, populated_root):
        """A string path is accepted and converted to Path."""
        index = write_template_index(str(populated_root))
        assert (populated_root / "template_index.json").exists()
        assert index["counts"]["assay"] == 1

    def test_writes_files_for_empty_root(self, tmp_path):
        """Even an empty root produces both index files."""
        write_template_index(tmp_path)

        json_path = tmp_path / "template_index.json"
        list_path = tmp_path / "template_list.txt"
        assert json_path.exists()
        assert list_path.exists()

        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        assert loaded["counts"]["assay"] == 0
        assert "=== Assay Templates ===" in list_path.read_text(encoding="utf-8")

    def test_overwrites_previous_index(self, populated_root):
        """A second run overwrites the previous index files with fresh data."""
        index_path = populated_root / "template_index.json"
        index_path.write_text("stale content", encoding="utf-8")
        (populated_root / "template_list.txt").write_text("stale content", encoding="utf-8")

        write_template_index(populated_root)

        loaded = json.loads(index_path.read_text(encoding="utf-8"))
        assert loaded["counts"]["assay"] == 1
        list_text = (populated_root / "template_list.txt").read_text(encoding="utf-8")
        assert "stale content" not in list_text
