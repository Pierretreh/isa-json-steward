"""
Unit tests for utils.isa_json_preview_helpers.

These tests cover ISAJsonPreviewHelper:
- study dict resolution (wrapped vs. flat format)
- index building for materials, factors, categories, protocols, data files,
  assays, and processes
- @id reference resolvers (found, suffix-matched, and missing lookups)
- HTML preview generation for materials, assays, data files, and studies
- the static helpers _format_file_size and _escape
"""

import html as html_module
from typing import Any, Dict

import pytest

from utils.isa_json_preview_helpers import ISAJsonPreviewHelper

# ----------------------------------------------------------------------
# Fixture builders
# ----------------------------------------------------------------------


def _build_study() -> Dict[str, Any]:
    """Build a realistic ISA-JSON study dict covering all indexed sections."""
    return {
        "title": "ISA-JSON Expression Study",
        "description": "Protein expression in E. coli <in vivo>",
        "identifier": "STU-0001",
        "filename": "study_1.json",
        "submissionDate": "2025-01-15",
        "studyDesignDescriptors": [
            {"annotationValue": "single organism", "termSource": "EDAM"},
        ],
        "materials": {
            "sources": [
                {
                    "@id": "#source_e_coli",
                    "name": "E. coli BL21",
                    "materialType": "source",
                    "characteristics": [
                        {
                            "category": {"@id": "#char_cat_organism"},
                            "value": {
                                "annotationValue": "Escherichia coli",
                                "termSource": "NCBITaxon",
                                "termAccession": "NCBITaxon_460",
                            },
                        }
                    ],
                    "comments": [{"name": "origin", "value": "ATCC"}],
                }
            ],
            "samples": [
                {
                    "@id": "#sample_pellet",
                    "name": "Cell Pellet",
                    "materialType": "sample",
                    "factorValues": [
                        {
                            "category": {"@id": "#factor_treatment"},
                            "value": {"annotationValue": "IPTG induced"},
                        }
                    ],
                    "derivesFrom": [{"@id": "#source_e_coli"}],
                }
            ],
            "otherMaterials": [
                {
                    "@id": "#other_buffer",
                    "name": "Lysis Buffer",
                    "materialType": "other",
                }
            ],
        },
        "factors": [
            {
                "@id": "#factor_treatment",
                "factorName": "Treatment",
                "factorType": {"annotationValue": "treatment type"},
            },
            {
                "@id": "#factor_replicate",
                "factorName": "Replicate",
            },
        ],
        "characteristicCategories": [
            {
                "@id": "#char_cat_organism",
                "characteristicType": {"annotationValue": "organism"},
            },
            {
                "@id": "#char_cat_growth",
                "characteristicType": {"annotationValue": "growth condition"},
            },
        ],
        "protocols": [
            {
                "@id": "#protocol_harvest",
                "name": "Harvesting Protocol",
                "protocolType": {"annotationValue": "harvesting"},
                "description": "Harvest cells by centrifugation",
            },
            {
                "@id": "#protocol_wb",
                "name": "Western Blot Protocol",
            },
        ],
        "assays": [
            {
                "@id": "#assay_western",
                "name": "Western blot",
                "filename": "western_blot.json",
                "measurementType": {
                    "annotationValue": "protein detection",
                    "termSource": "OBI",
                    "termAccession": "OBI_0002119",
                },
                "technologyType": {"annotationValue": "western blot"},
                "comments": [
                    {"name": "original measurement type", "value": "gel electrophoresis"},
                    {"name": "original technology type", "value": "wet blot"},
                ],
                "materials": {
                    "samples": [
                        {"@id": "#sample_assay_only", "name": "Assay-Only Sample"},
                    ]
                },
                "processSequence": [
                    {
                        "@id": "#process_wb_load",
                        "name": "Load gel",
                        "date": "2025-01-10",
                        "performer": "Alice",
                        "inputs": [
                            {"@id": "#sample_pellet"},
                            {"@id": "#other_buffer"},
                        ],
                        "parameterValues": [
                            {"category": {"@id": "#parameter/voltage"}, "value": "120"},
                            {"category": "parameter/temperature", "value": {"value": "4"}},
                        ],
                    }
                ],
                "dataFiles": [
                    {
                        "@id": "#datafile_wb_raw",
                        "name": "western_raw.tif",
                        "type": "image/tiff",
                        "comments": [
                            {"name": "fileSize", "value": "10485760"},
                            {"name": "derivedFromSample", "value": "#sample_pellet"},
                            {"name": "TraceDB", "value": "files/original/western_raw.tif"},
                        ],
                    },
                    {
                        "@id": "#datafile_wb_unc",
                        "name": "western_unc.tif",
                        "type": "image/tiff",
                        "comments": [
                            {"name": "derivedFromSample", "value": "unassigned"},
                        ],
                    },
                ],
            }
        ],
    }


@pytest.fixture
def study_data() -> Dict[str, Any]:
    """Full ISA-JSON wrapper format (studies list + ontology references)."""
    return {
        "studies": [_build_study()],
        "ontologySourceReferences": [
            {
                "name": "OBI",
                "description": "Ontology for Biomedical Investigations",
                "version": "1.2",
            }
        ],
    }


@pytest.fixture
def helper(study_data) -> ISAJsonPreviewHelper:
    """Helper backed by the wrapped ISA-JSON fixture."""
    return ISAJsonPreviewHelper(study_data)


@pytest.fixture
def simple_helper() -> ISAJsonPreviewHelper:
    """Helper backed by a flat (non-wrapped) study dict."""
    return ISAJsonPreviewHelper(_build_study())


# ----------------------------------------------------------------------
# study property / initialization
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestStudyProperty:
    """Tests for the study property and index building."""

    def test_study_property_returns_first_wrapped_study(self, study_data, helper):
        """A wrapped study dict resolves to the first element of 'studies'."""
        assert helper.study is study_data["studies"][0]

    def test_study_property_accepts_flat_study_dict(self):
        """A flat study dict is used as-is when no 'studies' list is present."""
        study = _build_study()
        helper = ISAJsonPreviewHelper(study)
        assert helper.study is study

    def test_empty_studies_list_falls_back_to_wrapper(self):
        """An empty 'studies' list falls back to the wrapper dict itself."""
        wrapper = {"studies": [], "title": "Wrapper"}
        helper = ISAJsonPreviewHelper(wrapper)
        assert helper.study is wrapper

    def test_build_indexes_materials_from_all_sections(self, helper):
        """Sources, samples, other materials, and assay-level samples are indexed."""
        expected = {
            "#source_e_coli",
            "#sample_pellet",
            "#other_buffer",
            "#sample_assay_only",
        }
        assert set(helper._materials_by_id) == expected
        assert helper._materials_by_id["#sample_assay_only"]["name"] == "Assay-Only Sample"

    def test_build_indexes_factors_categories_protocols(self, helper):
        """Factors, characteristic categories, and protocols are indexed by @id."""
        assert set(helper._factors_by_id) == {"#factor_treatment", "#factor_replicate"}
        assert set(helper._characteristic_categories_by_id) == {
            "#char_cat_organism",
            "#char_cat_growth",
        }
        assert set(helper._protocols_by_id) == {"#protocol_harvest", "#protocol_wb"}

    def test_build_indexes_assays_datafiles_processes(self, helper):
        """Assays, their data files, and process sequences are indexed."""
        assert set(helper._assays_by_name) == {"#assay_western"}
        assert set(helper._datafiles_by_id) == {"#datafile_wb_raw", "#datafile_wb_unc"}
        assert set(helper._processes_by_id) == {"#process_wb_load"}

    def test_build_indexes_skips_entries_without_id(self):
        """Entries missing an @id are not added to any index."""
        study = {
            "materials": {
                "sources": [{"name": "No ID"}, {"@id": "#s1", "name": "With ID"}],
                "samples": [{"name": "Sample No ID"}],
                "otherMaterials": [{"name": "Other No ID"}],
            },
            "factors": [{"factorName": "Factor No ID"}],
            "characteristicCategories": [{"characteristicType": {"annotationValue": "x"}}],
            "protocols": [{"name": "Protocol No ID"}],
            "assays": [
                {
                    "@id": "#a1",
                    "materials": {"samples": [{"name": "Assay Sample No ID"}]},
                    "dataFiles": [{"name": "no-id-file"}],
                    "processSequence": [{"name": "No ID Process"}],
                }
            ],
        }
        helper = ISAJsonPreviewHelper(study)

        assert helper._materials_by_id == {"#s1": study["materials"]["sources"][1]}
        assert helper._factors_by_id == {}
        assert helper._characteristic_categories_by_id == {}
        assert helper._protocols_by_id == {}
        assert helper._datafiles_by_id == {}
        assert helper._processes_by_id == {}
        assert helper._assays_by_name == {"#a1": study["assays"][0]}


# ----------------------------------------------------------------------
# Reference resolvers
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestResolveMaterialName:
    """Tests for resolve_material_name."""

    def test_resolve_source_name(self, helper):
        """A source @id resolves to its name."""
        assert helper.resolve_material_name("#source_e_coli") == "E. coli BL21"

    def test_resolve_sample_name(self, helper):
        """A sample @id resolves to its name."""
        assert helper.resolve_material_name("#sample_pellet") == "Cell Pellet"

    def test_resolve_other_material_name(self, helper):
        """An otherMaterial @id resolves to its name."""
        assert helper.resolve_material_name("#other_buffer") == "Lysis Buffer"

    def test_resolve_assay_level_sample_name(self, helper):
        """A sample defined inside an assay is also resolvable."""
        assert helper.resolve_material_name("#sample_assay_only") == "Assay-Only Sample"

    def test_missing_id_returns_original_id(self, helper):
        """Unknown material ids are returned unchanged."""
        assert helper.resolve_material_name("#does_not_exist") == "#does_not_exist"

    def test_material_without_name_returns_id(self):
        """A material lacking a name falls back to its id."""
        helper = ISAJsonPreviewHelper({"materials": {"otherMaterials": [{"@id": "#noname"}]}})
        assert helper.resolve_material_name("#noname") == "#noname"


@pytest.mark.unit
class TestResolveFactorName:
    """Tests for resolve_factor_name."""

    def test_direct_match(self, helper):
        """An exact factor @id resolves to factorName."""
        assert helper.resolve_factor_name("#factor_treatment") == "Treatment"

    def test_suffix_match_without_hash(self, helper):
        """A fragment without the leading '#' still resolves."""
        assert helper.resolve_factor_name("factor_replicate") == "Replicate"

    def test_missing_factor_returns_input(self, helper):
        """Unknown factor ids are returned unchanged."""
        assert helper.resolve_factor_name("#unknown_factor") == "#unknown_factor"

    def test_factor_without_factor_name_returns_id(self):
        """A factor lacking factorName falls back to its id."""
        helper = ISAJsonPreviewHelper({"factors": [{"@id": "#f"}]})
        assert helper.resolve_factor_name("#f") == "#f"


@pytest.mark.unit
class TestResolveCharacteristicCategoryName:
    """Tests for resolve_characteristic_category_name."""

    def test_direct_match(self, helper):
        """An exact category @id resolves to the characteristic type label."""
        assert helper.resolve_characteristic_category_name("#char_cat_organism") == "organism"

    def test_suffix_match_without_hash(self, helper):
        """A fragment without the leading '#' still resolves."""
        assert helper.resolve_characteristic_category_name("char_cat_growth") == "growth condition"

    def test_missing_category_returns_input(self, helper):
        """Unknown category ids are returned unchanged."""
        assert (
            helper.resolve_characteristic_category_name("#no_such_category") == "#no_such_category"
        )

    def test_category_without_annotation_value_returns_id(self):
        """A category lacking an annotation value falls back to its id."""
        helper = ISAJsonPreviewHelper({"characteristicCategories": [{"@id": "#c"}]})
        assert helper.resolve_characteristic_category_name("#c") == "#c"


@pytest.mark.unit
class TestResolveProtocolName:
    """Tests for resolve_protocol_name."""

    def test_dict_with_name(self, helper):
        """A protocol dict is resolved via its name key."""
        ref = {"@id": "#x", "name": "Inline Protocol"}
        assert helper.resolve_protocol_name(ref) == "Inline Protocol"

    def test_dict_without_name_falls_back_to_id(self, helper):
        """A protocol dict without a name falls back to its @id."""
        assert helper.resolve_protocol_name({"@id": "#p1"}) == "#p1"

    def test_string_lookup_found(self, helper):
        """A known protocol @id resolves to its name."""
        assert helper.resolve_protocol_name("#protocol_harvest") == "Harvesting Protocol"

    def test_string_lookup_missing_returns_input(self, helper):
        """An unknown protocol id is returned unchanged."""
        assert helper.resolve_protocol_name("#nope") == "#nope"


@pytest.mark.unit
class TestResolveDatafile:
    """Tests for resolve_datafile_name and resolve_assay_for_datafile."""

    def test_resolve_datafile_name_found(self, helper):
        """A known data file @id resolves to its name."""
        assert helper.resolve_datafile_name("#datafile_wb_raw") == "western_raw.tif"

    def test_resolve_datafile_name_missing(self, helper):
        """Unknown data file ids are returned unchanged."""
        assert helper.resolve_datafile_name("#missing_df") == "#missing_df"

    def test_resolve_assay_for_datafile_found(self, helper):
        """A data file name resolves to the owning assay dict."""
        assay = helper.resolve_assay_for_datafile("western_raw.tif")
        assert assay is not None
        assert assay["@id"] == "#assay_western"

    def test_resolve_assay_for_datafile_missing(self, helper):
        """An unknown data file name returns None."""
        assert helper.resolve_assay_for_datafile("missing.tif") is None


@pytest.mark.unit
class TestGetCommentValue:
    """Tests for get_comment_value."""

    def test_found(self, helper):
        """A known comment name returns its value."""
        comments = [{"name": "origin", "value": "ATCC"}]
        assert helper.get_comment_value(comments, "origin") == "ATCC"

    def test_not_found_returns_empty(self, helper):
        """A missing comment name returns an empty string."""
        comments = [{"name": "origin", "value": "ATCC"}]
        assert helper.get_comment_value(comments, "other") == ""

    def test_empty_list_returns_empty(self, helper):
        """An empty comment list returns an empty string."""
        assert helper.get_comment_value([], "origin") == ""

    def test_comment_without_value_key_returns_empty(self, helper):
        """A matching comment without a value returns an empty string."""
        assert helper.get_comment_value([{"name": "origin"}], "origin") == ""


# ----------------------------------------------------------------------
# Material preview HTML
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestMaterialPreviewHtml:
    """Tests for get_material_preview_html."""

    def test_contains_name_type_and_id(self, helper):
        """The material name, type, and @id are rendered."""
        material = helper._materials_by_id["#source_e_coli"]
        html_out = helper.get_material_preview_html(material)
        assert "E. coli BL21" in html_out
        assert "source" in html_out
        assert "#source_e_coli" in html_out
        assert '<b style="font-size: 14px;">' in html_out

    def test_characteristics_table_rendered(self, helper):
        """Characteristics are rendered with resolved category and value details."""
        material = helper._materials_by_id["#source_e_coli"]
        html_out = helper.get_material_preview_html(material)
        assert "<b>Characteristics:</b>" in html_out
        assert "organism" in html_out
        assert "Escherichia coli" in html_out
        assert "NCBITaxon" in html_out
        assert "NCBITaxon_460" in html_out
        assert "<table" in html_out

    def test_factor_values_rendered(self, helper):
        """Factor values are rendered with resolved factor names."""
        material = helper._materials_by_id["#sample_pellet"]
        html_out = helper.get_material_preview_html(material)
        assert "<b>Factor Values:</b>" in html_out
        assert "Treatment" in html_out
        assert "IPTG induced" in html_out

    def test_derives_from_resolves_material_name(self, helper):
        """derivesFrom references are resolved to material names."""
        material = helper._materials_by_id["#sample_pellet"]
        html_out = helper.get_material_preview_html(material)
        assert "<b>Derives From:</b>" in html_out
        assert "E. coli BL21" in html_out

    def test_linked_assays_listed(self, helper):
        """Assays using the material as an input are listed."""
        material = helper._materials_by_id["#other_buffer"]
        html_out = helper.get_material_preview_html(material)
        assert "<b>Used in Assays:</b>" in html_out
        assert "western" in html_out

    def test_string_category_and_value(self, helper):
        """Non-dict category refs and plain values are handled."""
        material = {
            "@id": "#sample_plain",
            "name": "Plain Sample",
            "characteristics": [
                {"category": "organism", "value": "plain value"},
            ],
        }
        html_out = helper.get_material_preview_html(material)
        assert "Plain Sample" in html_out
        assert "plain value" in html_out

    def test_minimal_material(self, helper):
        """A material without optional sections still renders."""
        html_out = helper.get_material_preview_html({})
        assert isinstance(html_out, str)
        assert "Unknown" in html_out
        assert "<div" in html_out

    def test_special_characters_escaped(self, helper):
        """HTML special characters in material fields are escaped."""
        material = {"name": "<b>Bold</b>", "materialType": "A&B"}
        html_out = helper.get_material_preview_html(material)
        assert html_module.escape("<b>Bold</b>") in html_out
        assert html_module.escape("A&B") in html_out
        assert "<b>Bold</b>" not in html_out


# ----------------------------------------------------------------------
# Assay preview HTML
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestAssayPreviewHtml:
    """Tests for get_assay_preview_html."""

    @pytest.fixture
    def assay(self, helper) -> Dict[str, Any]:
        return helper._assays_by_name["#assay_western"]

    @pytest.fixture
    def html_out(self, helper, assay) -> str:
        return helper.get_assay_preview_html(assay)

    def test_contains_display_name_and_id(self, html_out):
        """The assay display name (from @id) and raw id are rendered."""
        assert '<b style="font-size: 14px;">western</b>' in html_out
        assert "#assay_western" in html_out

    def test_measurement_type_rendered(self, html_out):
        """Measurement type value, term source, and accession are rendered."""
        assert "<b>Measurement Type:</b>" in html_out
        assert "protein detection" in html_out
        assert "OBI" in html_out
        assert "OBI_0002119" in html_out

    def test_technology_type_rendered(self, html_out):
        """Technology type value is rendered."""
        assert "<b>Technology Type:</b>" in html_out
        assert "western blot" in html_out

    def test_original_types_from_comments(self, html_out):
        """Original measurement/technology types come from comments."""
        assert "<b>Original Types:</b>" in html_out
        assert "gel electrophoresis" in html_out
        assert "wet blot" in html_out

    def test_filename_rendered(self, html_out):
        """The assay filename is rendered."""
        assert "<b>Filename:</b>" in html_out
        assert "western_blot.json" in html_out

    def test_process_sequence_rendered(self, html_out):
        """Process steps with date, performer, and parameters are rendered."""
        assert "Process Sequence (1 steps):" in html_out
        assert "Load gel" in html_out
        assert "Alice" in html_out
        assert "voltage: 120" in html_out
        assert "temperature: 4" in html_out

    def test_data_files_rendered(self, html_out):
        """Data files list name, type, formatted size, and origin."""
        assert "Data Files (2):" in html_out
        assert "western_raw.tif" in html_out
        assert "image/tiff" in html_out
        assert "10.0 MB" in html_out
        assert "Derived from: Cell Pellet" in html_out
        assert "Derived from: unassigned" in html_out

    def test_input_materials_rendered_deduplicated(self, html_out):
        """Input materials are resolved to names and deduplicated."""
        assert "<b>Input Materials:</b>" in html_out
        assert "Cell Pellet" in html_out
        assert "Lysis Buffer" in html_out

    def test_empty_assay(self, helper):
        """An empty assay dict still produces valid HTML."""
        html_out = helper.get_assay_preview_html({})
        assert isinstance(html_out, str)
        assert "<div" in html_out


# ----------------------------------------------------------------------
# Data file preview HTML
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestDatafilePreviewHtml:
    """Tests for get_datafile_preview_html."""

    @pytest.fixture
    def datafile(self, helper) -> Dict[str, Any]:
        return helper._datafiles_by_id["#datafile_wb_raw"]

    @pytest.fixture
    def assay(self, helper) -> Dict[str, Any]:
        return helper._assays_by_name["#assay_western"]

    def test_contains_name_type_and_id(self, helper, datafile):
        """The data file name, type, and @id are rendered."""
        html_out = helper.get_datafile_preview_html(datafile)
        assert "western_raw.tif" in html_out
        assert "image/tiff" in html_out
        assert "#datafile_wb_raw" in html_out

    def test_comments_rendered(self, helper, datafile):
        """TraceDB path, formatted size, and source sample are rendered."""
        html_out = helper.get_datafile_preview_html(datafile)
        assert "files/original/western_raw.tif" in html_out
        assert "10.0 MB" in html_out
        assert "Cell Pellet" in html_out
        assert "#sample_pellet" in html_out

    def test_unassigned_sample(self, helper):
        """An unassigned derived sample is rendered as a placeholder."""
        datafile = helper._datafiles_by_id["#datafile_wb_unc"]
        html_out = helper.get_datafile_preview_html(datafile)
        assert "unassigned" in html_out

    def test_parent_assay_name(self, helper, datafile, assay):
        """The parent assay name is rendered when provided."""
        html_out = helper.get_datafile_preview_html(datafile, assay)
        assert "<b>Assay:</b>" in html_out
        assert "western" in html_out

    def test_no_assay_omits_assay_section(self, helper, datafile):
        """Without an assay, the assay section is omitted."""
        html_out = helper.get_datafile_preview_html(datafile, None)
        assert "<b>Assay:</b>" not in html_out

    def test_minimal_datafile(self, helper):
        """A data file without comments still renders its name."""
        html_out = helper.get_datafile_preview_html({"name": "bare.tif"})
        assert "bare.tif" in html_out
        assert "<table" in html_out


# ----------------------------------------------------------------------
# Study preview HTML
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestStudyPreviewHtml:
    """Tests for get_study_preview_html."""

    def test_title_and_metadata(self, helper):
        """Title, identifier, filename, and submission date are rendered."""
        html_out = helper.get_study_preview_html()
        assert "ISA-JSON Expression Study" in html_out
        assert "STU-0001" in html_out
        assert "study_1.json" in html_out
        assert "2025-01-15" in html_out

    def test_description_rendered_escaped(self, helper):
        """The description is rendered with HTML characters escaped."""
        html_out = helper.get_study_preview_html()
        assert "<b>Description:</b>" in html_out
        assert html_module.escape("E. coli <in vivo>") in html_out

    def test_study_design_descriptors(self, helper):
        """Study design descriptors render value and term source."""
        html_out = helper.get_study_preview_html()
        assert "<b>Study Design:</b>" in html_out
        assert "single organism" in html_out
        assert "EDAM" in html_out

    def test_factors_listed(self, helper):
        """Factors render names, with distinct types in parentheses."""
        html_out = helper.get_study_preview_html()
        assert "Factors (2):" in html_out
        assert "Treatment" in html_out
        assert "treatment type" in html_out
        assert "Replicate" in html_out

    def test_protocols_listed(self, helper):
        """Protocols render names, types, and descriptions."""
        html_out = helper.get_study_preview_html()
        assert "Protocols (2):" in html_out
        assert "Harvesting Protocol" in html_out
        assert "[harvesting]" in html_out
        assert "Harvest cells by centrifugation" in html_out
        assert "Western Blot Protocol" in html_out

    def test_characteristic_categories_listed(self, helper):
        """Characteristic category type names are listed."""
        html_out = helper.get_study_preview_html()
        assert "<b>Characteristic Categories:</b>" in html_out
        assert "organism" in html_out
        assert "growth condition" in html_out

    def test_ontology_source_references(self, helper):
        """Top-level ontology source references are rendered."""
        html_out = helper.get_study_preview_html()
        assert "<b>Ontology Sources:</b>" in html_out
        assert "OBI" in html_out
        assert "Ontology for Biomedical Investigations" in html_out
        assert "1.2" in html_out

    def test_ontology_refs_omitted_when_absent(self, simple_helper):
        """Without top-level ontology references, the section is omitted."""
        html_out = simple_helper.get_study_preview_html()
        assert "<b>Ontology Sources:</b>" not in html_out

    def test_minimal_study(self):
        """An empty study dict still produces valid HTML."""
        helper = ISAJsonPreviewHelper({})
        html_out = helper.get_study_preview_html()
        assert isinstance(html_out, str)
        assert "<div" in html_out


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestGetAssayDisplayName:
    """Tests for the _get_assay_display_name helper."""

    def test_id_with_hash_fragment(self, helper):
        """An @id fragment after '#' is used, with assay_ prefix stripped."""
        assay = {"@id": "#assay_western"}
        assert helper._get_assay_display_name(assay) == "western"

    def test_id_with_hash_replaces_underscores(self, helper):
        """Remaining underscores become spaces in the display name."""
        assay = {"@id": "#assay_western_blot"}
        assert helper._get_assay_display_name(assay) == "western blot"

    def test_id_without_hash_uses_name(self, helper):
        """Without a '#' in the id, the name key is used."""
        assay = {"@id": "assay_plain", "name": "Plain Name"}
        assert helper._get_assay_display_name(assay) == "Plain Name"

    def test_no_id_no_name_returns_empty(self, helper):
        """An empty assay dict yields an empty display name."""
        assert helper._get_assay_display_name({}) == ""


@pytest.mark.unit
class TestGetLinkedAssays:
    """Tests for _get_linked_assays_for_material."""

    def test_material_used_in_assay_is_found(self, helper):
        """A material appearing in an assay process input is linked."""
        linked = helper._get_linked_assays_for_material("#other_buffer")
        assert len(linked) == 1
        assert linked[0]["@id"] == "#assay_western"

    def test_material_not_used_returns_empty(self, helper):
        """A material not used by any assay yields an empty list."""
        assert helper._get_linked_assays_for_material("#source_e_coli") == []

    def test_empty_material_id_returns_empty(self, helper):
        """An empty material id yields an empty list."""
        assert helper._get_linked_assays_for_material("") == []


# ----------------------------------------------------------------------
# Static helpers
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestFormatFileSize:
    """Tests for the static _format_file_size helper."""

    @pytest.mark.parametrize(
        ("size_bytes", "expected"),
        [
            (0, "0 B"),
            (512, "512 B"),
            (1023, "1023 B"),
            (1024, "1.0 KB"),
            (1536, "1.5 KB"),
            (1024 * 1024, "1.0 MB"),
            (15 * 1024 * 1024, "15.0 MB"),
            (1024 * 1024 * 1024, "1.0 GB"),
            (5 * 1024 * 1024 * 1024, "5.0 GB"),
        ],
        ids=["zero", "bytes", "bytes_max", "kb_min", "kb", "mb_min", "mb", "gb_min", "gb"],
    )
    def test_format_file_size(self, size_bytes, expected):
        """File sizes render in the correct human-readable unit."""
        assert ISAJsonPreviewHelper._format_file_size(size_bytes) == expected


@pytest.mark.unit
class TestEscape:
    """Tests for the static _escape helper."""

    def test_escapes_angle_brackets(self):
        """Angle brackets are escaped."""
        assert ISAJsonPreviewHelper._escape("<") == "&" + "lt;"
        assert ISAJsonPreviewHelper._escape(">") == "&" + "gt;"

    def test_escapes_ampersand(self):
        """Ampersands are escaped."""
        assert ISAJsonPreviewHelper._escape("&") == "&" + "amp;"

    def test_escapes_quotes(self):
        """Double and single quotes are escaped."""
        assert ISAJsonPreviewHelper._escape('"') == "&" + "quot;"
        assert ISAJsonPreviewHelper._escape("'") == "&" + "#x27;"

    def test_plain_text_unchanged(self):
        """Text without special characters passes through."""
        assert ISAJsonPreviewHelper._escape("plain text") == "plain text"

    def test_non_string_input_converted(self):
        """Non-string input is stringified before escaping."""
        assert ISAJsonPreviewHelper._escape(123) == "123"
        assert ISAJsonPreviewHelper._escape(4.5) == "4.5"
