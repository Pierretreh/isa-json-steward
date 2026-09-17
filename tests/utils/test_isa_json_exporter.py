"""
Unit tests for ISAJsonExporter.
"""

import json

import pytest

from utils.isa_json_exporter import ISAJsonExporter


@pytest.mark.unit
@pytest.mark.isa_validation
class TestISAJsonExporter:
    """Tests for ISAJsonExporter class."""

    def test_initialization(self):
        """Test exporter initialization."""
        exporter = ISAJsonExporter()
        assert isinstance(exporter, ISAJsonExporter)

    def test_export_investigation(self, temp_dir, valid_investigation_json):
        """Test exporting investigation to file."""
        exporter = ISAJsonExporter()
        output_path = temp_dir / "investigation.json"

        exporter.export_investigation(valid_investigation_json, str(output_path))

        assert output_path.exists()

        with open(output_path, "r") as f:
            data = json.load(f)
            assert "investigation" in data
            assert data["investigation"]["identifier"] == "test_inv"

    def test_export_study(self, temp_dir, valid_study_json):
        """Test exporting study to file."""
        exporter = ISAJsonExporter()
        output_path = temp_dir / "study.json"

        exporter.export_study(valid_study_json, str(output_path))

        assert output_path.exists()

        with open(output_path, "r") as f:
            data = json.load(f)
            assert data["identifier"] == "study_1"

    def test_export_assay(self, temp_dir, valid_assay_json):
        """Test exporting assay to file."""
        exporter = ISAJsonExporter()
        output_path = temp_dir / "assay.json"

        exporter.export_assay(valid_assay_json, str(output_path))

        assert output_path.exists()

        with open(output_path, "r") as f:
            data = json.load(f)
            assert "measurementType" in data

    def test_export_creates_directory(self, temp_dir, valid_investigation_json):
        """Test that export creates parent directories."""
        exporter = ISAJsonExporter()
        output_path = temp_dir / "nested" / "dir" / "investigation.json"

        exporter.export_investigation(valid_investigation_json, str(output_path))

        assert output_path.exists()
        assert output_path.parent.exists()

    def test_export_overwrites_existing(self, temp_dir, valid_investigation_json):
        """Test that export overwrites existing file."""
        exporter = ISAJsonExporter()
        output_path = temp_dir / "investigation.json"

        # Create initial file
        output_path.write_text('{"old": "data"}')

        # Export new data
        exporter.export_investigation(valid_investigation_json, str(output_path))

        # Verify file was overwritten
        with open(output_path, "r") as f:
            data = json.load(f)
            assert "old" not in data
            assert "investigation" in data

    def test_export_with_indentation(self, temp_dir, valid_investigation_json):
        """Test export with custom indentation."""
        exporter = ISAJsonExporter()
        output_path = temp_dir / "investigation.json"

        exporter.export_investigation(valid_investigation_json, str(output_path), indent=2)

        content = output_path.read_text()
        # Check that file is formatted with indentation
        assert "  " in content or "\n" in content

    def test_export_invalid_data(self, temp_dir):
        """Test export with invalid data."""
        exporter = ISAJsonExporter()
        output_path = temp_dir / "invalid.json"

        # Should handle invalid data gracefully
        with pytest.raises(Exception):
            exporter.export_investigation(None, str(output_path))


@pytest.mark.unit
@pytest.mark.isa_validation
class TestISAJsonExporterPureLogic:
    """Tests for pure-logic helper methods of ISAJsonExporter (dict -> dict/str)."""

    @pytest.fixture
    def exporter(self):
        """Minimal exporter with empty study data."""
        return ISAJsonExporter(study_data={})

    # ------------------------------------------------------------------
    # _get_measurement_type
    # ------------------------------------------------------------------

    def test_get_measurement_type_empty_assay_defaults(self, exporter):
        result = exporter._get_measurement_type({})
        assert result["annotationValue"] == "protein expression"
        assert result["termSource"] == "OBI"
        assert result["termAccession"] == "http://purl.obolibrary.org/obo/OBI_0000615"

    def test_get_measurement_type_sds_page(self, exporter):
        result = exporter._get_measurement_type({"assay_type": "sds-page"})
        assert result["annotationValue"] == "protein identification"
        assert result["termAccession"] == "http://purl.obolibrary.org/obo/OBI_0001148"

    def test_get_measurement_type_microscopy(self, exporter):
        result = exporter._get_measurement_type({"assay_type": "microscopy"})
        assert result["annotationValue"] == "histology"
        assert result["termAccession"] == "http://purl.obolibrary.org/obo/OBI_0000112"

    def test_get_measurement_type_sequencing(self, exporter):
        result = exporter._get_measurement_type({"assay_type": "sequencing"})
        assert result["annotationValue"] == "transcription profiling"

    def test_get_measurement_type_toxicity_test(self, exporter):
        result = exporter._get_measurement_type({"assay_type": "toxicity test"})
        assert result["annotationValue"] == "cell counting"

    def test_get_measurement_type_mass_spectrometry(self, exporter):
        result = exporter._get_measurement_type({"assay_type": "mass spectrometry"})
        assert result["annotationValue"] == "metabolite profiling"

    def test_get_measurement_type_nmr(self, exporter):
        result = exporter._get_measurement_type({"assay_type": "nmr"})
        assert result["annotationValue"] == "metabolite profiling"

    def test_get_measurement_type_flow_cytometry(self, exporter):
        result = exporter._get_measurement_type({"assay_type": "flow cytometry"})
        assert result["annotationValue"] == "cell counting"

    def test_get_measurement_type_facs(self, exporter):
        result = exporter._get_measurement_type({"assay_type": "facs"})
        assert result["annotationValue"] == "cell counting"

    def test_get_measurement_type_calcein(self, exporter):
        result = exporter._get_measurement_type({"assay_type": "calcein"})
        assert result["annotationValue"] == "histology"

    def test_get_measurement_type_dapi(self, exporter):
        result = exporter._get_measurement_type({"assay_type": "dapi"})
        assert result["annotationValue"] == "histology"

    def test_get_measurement_type_fluorescence(self, exporter):
        result = exporter._get_measurement_type({"assay_type": "fluorescence"})
        assert result["annotationValue"] == "histology"

    def test_get_measurement_type_viability_assay(self, exporter):
        result = exporter._get_measurement_type({"assay_type": "viability assay"})
        assert result["annotationValue"] == "histology"

    def test_get_measurement_type_nuclear_staining(self, exporter):
        result = exporter._get_measurement_type({"assay_type": "nuclear staining"})
        assert result["annotationValue"] == "histology"

    def test_get_measurement_type_from_assay_name(self, exporter):
        result = exporter._get_measurement_type({"name": "SDS-PAGE analysis"})
        assert result["annotationValue"] == "protein identification"

    def test_get_measurement_type_provided_with_obi_accession_passthrough(self, exporter):
        provided = {
            "annotationValue": "cell death assay",
            "termSource": "OBI",
            "termAccession": "http://purl.obolibrary.org/obo/OBI_0000001",
        }
        result = exporter._get_measurement_type({"measurementType": provided})
        assert result == provided

    def test_get_measurement_type_provided_non_obi_not_passthrough(self, exporter):
        result = exporter._get_measurement_type(
            {
                "measurementType": {
                    "annotationValue": "cell death assay",
                    "termSource": "EFO",
                    "termAccession": "http://www.ebi.ac.uk/efo/EFO_1234",
                }
            }
        )
        assert result["annotationValue"] == "protein expression"

    def test_get_measurement_type_provided_normalized_via_map(self, exporter):
        result = exporter._get_measurement_type(
            {"measurementType": {"annotationValue": "cell counting", "termSource": "OBI"}}
        )
        assert result["annotationValue"] == "histology"

    # ------------------------------------------------------------------
    # _get_technology_type
    # ------------------------------------------------------------------

    def test_get_technology_type_empty_assay_defaults(self, exporter):
        result = exporter._get_technology_type({})
        assert result["annotationValue"] == "bioassay"
        assert result["termSource"] == "OBI"
        assert result["termAccession"] == "http://purl.obolibrary.org/obo/OBI_0000070"

    def test_get_technology_type_sds_page(self, exporter):
        result = exporter._get_technology_type({"assay_type": "sds-page"})
        assert result["annotationValue"] == "mass spectrometry"
        assert result["termAccession"] == "http://purl.obolibrary.org/obo/OBI_0000470"

    def test_get_technology_type_gel_electrophoresis(self, exporter):
        result = exporter._get_technology_type({"assay_type": "gel electrophoresis"})
        assert result["annotationValue"] == "mass spectrometry"

    def test_get_technology_type_microscopy(self, exporter):
        result = exporter._get_technology_type({"assay_type": "microscopy"})
        assert result["annotationValue"] == "histology"

    def test_get_technology_type_light_microscopy(self, exporter):
        result = exporter._get_technology_type({"assay_type": "light microscopy"})
        assert result["annotationValue"] == "histology"

    def test_get_technology_type_fluorescence_microscopy(self, exporter):
        result = exporter._get_technology_type({"assay_type": "fluorescence microscopy"})
        assert result["annotationValue"] == "fluorescence microscopy"
        assert result["termAccession"] == "http://purl.obolibrary.org/obo/OBI_0000257"

    def test_get_technology_type_fluorometry_is_empty(self, exporter):
        result = exporter._get_technology_type({"assay_type": "fluorometry"})
        assert result == {"annotationValue": "", "termSource": "", "termAccession": ""}

    def test_get_technology_type_toxicity_test(self, exporter):
        result = exporter._get_technology_type({"assay_type": "toxicity test"})
        assert result["annotationValue"] == "bioassay"
        assert result["termAccession"] == "http://purl.obolibrary.org/obo/OBI_0000415"

    def test_get_technology_type_sequencing(self, exporter):
        result = exporter._get_technology_type({"assay_type": "sequencing"})
        assert result["annotationValue"] == "nucleotide sequencing"

    def test_get_technology_type_nmr(self, exporter):
        result = exporter._get_technology_type({"assay_type": "nmr"})
        assert result["annotationValue"] == "NMR spectroscopy"

    def test_get_technology_type_flow_cytometry(self, exporter):
        result = exporter._get_technology_type({"assay_type": "flow cytometry"})
        assert result["annotationValue"] == "flow cytometry"

    def test_get_technology_type_protein_microarray(self, exporter):
        result = exporter._get_technology_type({"assay_type": "protein microarray"})
        assert result["annotationValue"] == "protein microarray"

    def test_get_technology_type_dna_microarray(self, exporter):
        result = exporter._get_technology_type({"assay_type": "dna microarray"})
        assert result["annotationValue"] == "DNA microarray"

    def test_get_technology_type_clinical_chemistry(self, exporter):
        result = exporter._get_technology_type({"assay_type": "clinical chemistry"})
        assert result["annotationValue"] == "clinical chemistry analysis"

    def test_get_technology_type_from_assay_name(self, exporter):
        result = exporter._get_technology_type({"name": "Light Microscopy Image Analysis"})
        assert result["annotationValue"] == "histology"

    def test_get_technology_type_provided_obi_passthrough(self, exporter):
        provided = {
            "annotationValue": "custom technology",
            "termSource": "OBI",
            "termAccession": "http://purl.obolibrary.org/obo/OBI_0000001",
        }
        result = exporter._get_technology_type({"technologyType": provided})
        assert result == provided

    def test_get_technology_type_provided_normalized_via_map(self, exporter):
        result = exporter._get_technology_type(
            {"technologyType": {"annotationValue": "nmr", "termSource": "OBI"}}
        )
        assert result["annotationValue"] == "NMR spectroscopy"

    # ------------------------------------------------------------------
    # _ontology_to_data_type
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "annotation_value,expected",
        [
            ("image", "Image File"),
            ("data", "Derived Data File"),
            ("sequence", "Raw Spectral Data File"),
            ("report", "Derived Data File"),
            ("unknown-term", "Derived Data File"),
        ],
    )
    def test_ontology_to_data_type(self, exporter, annotation_value, expected):
        result = exporter._ontology_to_data_type({"annotationValue": annotation_value})
        assert result == expected

    def test_ontology_to_data_type_case_insensitive(self, exporter):
        assert exporter._ontology_to_data_type({"annotationValue": "IMAGE"}) == "Image File"

    def test_ontology_to_data_type_empty_dict(self, exporter):
        assert exporter._ontology_to_data_type({}) == "Derived Data File"

    # ------------------------------------------------------------------
    # _export_parameter_value
    # ------------------------------------------------------------------

    def test_export_parameter_value_preformatted_isa_json(self, exporter):
        param = {"category": {"@id": "#parameter/temperature"}, "value": {"annotationValue": "37"}}
        result = exporter._export_parameter_value(param, "#process_1")
        assert result == {
            "category": {"@id": "#parameter/temperature"},
            "value": {"annotationValue": "37"},
        }

    def test_export_parameter_value_gui_int(self, exporter):
        result = exporter._export_parameter_value(
            {"name": "temperature", "value": "37"}, "#process_1"
        )
        assert result["category"] == {"@id": "#parameter/temperature"}
        assert result["value"] == 37

    def test_export_parameter_value_gui_float(self, exporter):
        result = exporter._export_parameter_value(
            {"name": "concentration", "value": "3.5"}, "#process_1"
        )
        assert result["value"] == 3.5

    def test_export_parameter_value_non_numeric(self, exporter):
        result = exporter._export_parameter_value({"name": "buffer", "value": "PBS"}, "#process_1")
        assert result["value"] == "PBS"

    def test_export_parameter_value_annotation(self, exporter):
        param = {
            "name": "organism",
            "annotationValue": "E. coli",
            "termSource": "NCBITaxon",
            "termAccession": "http://purl.obolibrary.org/obo/NCBITaxon_562",
        }
        result = exporter._export_parameter_value(param, "#process_1")
        assert result["value"] == {
            "annotationValue": "E. coli",
            "termSource": "NCBITaxon",
            "termAccession": "http://purl.obolibrary.org/obo/NCBITaxon_562",
        }

    def test_export_parameter_value_annotation_minimal(self, exporter):
        result = exporter._export_parameter_value(
            {"name": "x", "annotationValue": "v"}, "#process_1"
        )
        assert result["value"] == {"annotationValue": "v"}

    def test_export_parameter_value_empty_param(self, exporter):
        result = exporter._export_parameter_value({}, "#process_1")
        assert result == {"category": {"@id": "#parameter/"}}

    # ------------------------------------------------------------------
    # _export_material_references
    # ------------------------------------------------------------------

    def test_export_material_references_empty(self, exporter):
        assert exporter._export_material_references([]) == []

    def test_export_material_references_strings(self, exporter):
        refs = ["/inv/study#sample_1", "/inv/study#sample_2"]
        assert exporter._export_material_references(refs) == [
            {"@id": "/inv/study#sample_1"},
            {"@id": "/inv/study#sample_2"},
        ]

    def test_export_material_references_dicts(self, exporter):
        refs = [{"@id": "#sample_1"}, {"material_id": "#sample_2"}]
        assert exporter._export_material_references(refs) == [
            {"@id": "#sample_1"},
            {"@id": "#sample_2"},
        ]

    def test_export_material_references_skips_empty_and_invalid(self, exporter):
        refs = ["", {"@id": ""}, {"name": "no-id"}, 42, None]
        assert exporter._export_material_references(refs) == []

    # ------------------------------------------------------------------
    # _collect_term_sources
    # ------------------------------------------------------------------

    def test_collect_term_sources_flat(self, exporter):
        used = set()
        exporter._collect_term_sources({"termSource": "OBI"}, used)
        assert used == {"OBI"}

    def test_collect_term_sources_nested(self, exporter):
        used = set()
        data = {
            "a": [
                {"termSource": "EFO"},
                {"b": {"termSource": "UO"}},
            ]
        }
        exporter._collect_term_sources(data, used)
        assert used == {"EFO", "UO"}

    def test_collect_term_sources_empty_and_scalar(self, exporter):
        used = set()
        exporter._collect_term_sources({}, used)
        exporter._collect_term_sources([], used)
        exporter._collect_term_sources("plain string", used)
        exporter._collect_term_sources(42, used)
        assert used == set()

    def test_collect_term_sources_ignores_non_string_values(self, exporter):
        used = set()
        exporter._collect_term_sources({"termSource": {"weird": "obj"}}, used)
        exporter._collect_term_sources({"termSource": ""}, used)
        assert used == set()

    def test_collect_term_sources_accumulates(self, exporter):
        used = {"CHEBI"}
        exporter._collect_term_sources({"termSource": "OBI"}, used)
        assert used == {"CHEBI", "OBI"}

    # ------------------------------------------------------------------
    # _export_characteristic_categories
    # ------------------------------------------------------------------

    def test_export_characteristic_categories_none_used(self, exporter):
        assert exporter._export_characteristic_categories() == []

    def test_export_characteristic_categories_organism(self):
        exporter = ISAJsonExporter(
            study_data={
                "materials": {
                    "sources": [
                        {
                            "name": "E. coli",
                            "characteristics": [
                                {"category": {"@id": "#characteristic_category/organism"}}
                            ],
                        }
                    ],
                    "samples": [],
                    "otherMaterials": [],
                }
            }
        )
        result = exporter._export_characteristic_categories()
        assert [c["@id"] for c in result] == ["#characteristic_category/organism"]
        assert result[0]["characteristicType"]["termSource"] == "OBI"

    def test_export_characteristic_categories_material_type(self):
        exporter = ISAJsonExporter(
            study_data={
                "materials": {
                    "samples": [
                        {
                            "name": "Sample A",
                            "characteristics": [
                                {"category": {"@id": "#characteristic_category/material_type"}}
                            ],
                        }
                    ]
                }
            }
        )
        result = exporter._export_characteristic_categories()
        assert [c["@id"] for c in result] == ["#characteristic_category/material_type"]

    def test_export_characteristic_categories_extract_type(self):
        exporter = ISAJsonExporter(
            study_data={
                "materials": {
                    "otherMaterials": [
                        {
                            "name": "Extract A",
                            "characteristics": [
                                {"category": {"@id": "#characteristic_category/extract_type"}}
                            ],
                        }
                    ]
                }
            }
        )
        result = exporter._export_characteristic_categories()
        assert [c["@id"] for c in result] == ["#characteristic_category/extract_type"]

    def test_export_characteristic_categories_all_used(self):
        exporter = ISAJsonExporter(
            study_data={
                "materials": {
                    "sources": [
                        {
                            "name": "S",
                            "characteristics": [
                                {"category": {"@id": "#characteristic_category/organism"}}
                            ],
                        }
                    ],
                    "samples": [
                        {
                            "name": "A",
                            "characteristics": [
                                {"category": {"@id": "#characteristic_category/material_type"}}
                            ],
                        }
                    ],
                    "otherMaterials": [
                        {
                            "name": "E",
                            "characteristics": [
                                {"category": {"@id": "#characteristic_category/extract_type"}}
                            ],
                        }
                    ],
                }
            }
        )
        result = exporter._export_characteristic_categories()
        assert len(result) == 3

    def test_export_characteristic_categories_ignores_unknown_ids(self):
        exporter = ISAJsonExporter(
            study_data={
                "materials": {
                    "sources": [
                        {
                            "name": "S",
                            "characteristics": [
                                {"category": {"@id": "#characteristic_category/custom"}}
                            ],
                        }
                    ]
                }
            }
        )
        assert exporter._export_characteristic_categories() == []

    # ------------------------------------------------------------------
    # _export_factors
    # ------------------------------------------------------------------

    def test_export_factors_empty(self, exporter):
        assert exporter._export_factors() == []

    def test_export_factors_full(self):
        exporter = ISAJsonExporter(
            study_data={
                "factors": [
                    {
                        "name": "Dose",
                        "type": "compound",
                        "term_source": "EFO",
                        "term_accession": "http://www.ebi.ac.uk/efo/EFO_0000001",
                    }
                ]
            }
        )
        result = exporter._export_factors()
        assert result == [
            {
                "@id": "#factor/dose",
                "factorName": "Dose",
                "factorType": {
                    "annotationValue": "compound",
                    "termSource": "EFO",
                    "termAccession": "http://www.ebi.ac.uk/efo/EFO_0000001",
                },
            }
        ]

    def test_export_factors_defaults(self):
        exporter = ISAJsonExporter(study_data={"factors": [{"name": "Incubation Time"}]})
        result = exporter._export_factors()
        assert result[0]["@id"] == "#factor/incubation_time"
        assert result[0]["factorName"] == "Incubation Time"
        assert result[0]["factorType"]["annotationValue"] == "Incubation Time"
        assert result[0]["factorType"]["termSource"] == "EFO"
        assert result[0]["factorType"]["termAccession"] == ""

    def test_export_factors_explicit_id(self):
        exporter = ISAJsonExporter(
            study_data={"factors": [{"name": "Dose", "@id": "#factor/custom"}]}
        )
        result = exporter._export_factors()
        assert result[0]["@id"] == "#factor/custom"

    # ------------------------------------------------------------------
    # _export_study_design_descriptors
    # ------------------------------------------------------------------

    def test_export_study_design_descriptors_empty(self, exporter):
        assert exporter._export_study_design_descriptors() == []

    def test_export_study_design_descriptors_full(self):
        exporter = ISAJsonExporter(
            study_data={
                "study_design_descriptors": [
                    {
                        "name": "experimental study",
                        "term_source": "OBI",
                        "term_accession": "http://purl.obolibrary.org/obo/OBI_0000066",
                    }
                ]
            }
        )
        result = exporter._export_study_design_descriptors()
        assert result == [
            {
                "annotationValue": "experimental study",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000066",
            }
        ]

    def test_export_study_design_descriptors_defaults(self):
        exporter = ISAJsonExporter(
            study_data={"study_design_descriptors": [{"name": "case control"}]}
        )
        result = exporter._export_study_design_descriptors()
        assert result == [
            {"annotationValue": "case control", "termSource": "EFO", "termAccession": ""}
        ]

    # ------------------------------------------------------------------
    # _export_people
    # ------------------------------------------------------------------

    def test_export_people_empty(self, exporter):
        assert exporter._export_people() == []

    def test_export_people_full(self):
        exporter = ISAJsonExporter(
            study_data={
                "people": [
                    {
                        "first_name": "Max",
                        "last_name": "Mustermann",
                        "middle_initials": "A.",
                        "email": "max@example.org",
                        "phone": "+49 30 123456",
                        "address": "Berlin",
                        "affiliation": "Institute",
                        "roles": ["Principal Investigator", "Contact"],
                    }
                ]
            }
        )
        result = exporter._export_people()
        assert result[0]["firstName"] == "Max"
        assert result[0]["lastName"] == "Mustermann"
        assert result[0]["midInitials"] == "A."
        assert result[0]["email"] == "max@example.org"
        assert result[0]["phone"] == "+49 30 123456"
        assert result[0]["address"] == "Berlin"
        assert result[0]["affiliation"] == "Institute"
        assert result[0]["roles"] == [
            {"annotationValue": "Principal Investigator", "termSource": "EFO"},
            {"annotationValue": "Contact", "termSource": "EFO"},
        ]

    def test_export_people_without_roles(self):
        exporter = ISAJsonExporter(study_data={"people": [{"first_name": "Min", "last_name": "N"}]})
        result = exporter._export_people()
        assert result[0]["firstName"] == "Min"
        assert result[0]["lastName"] == "N"
        assert "roles" not in result[0]

    # ------------------------------------------------------------------
    # _export_publications
    # ------------------------------------------------------------------

    def test_export_publications_empty(self, exporter):
        assert exporter._export_publications() == []

    def test_export_publications_full(self):
        exporter = ISAJsonExporter(
            study_data={
                "publications": [
                    {
                        "title": "Paper",
                        "pubmed_id": "12345",
                        "doi": "10.1000/xyz",
                        "authors": "A; B",
                        "status": "published",
                    }
                ]
            }
        )
        result = exporter._export_publications()
        assert result == [
            {
                "title": "Paper",
                "pubMedID": "12345",
                "doi": "10.1000/xyz",
                "authorList": "A; B",
                "status": {"annotationValue": "published", "termSource": "EFO"},
            }
        ]

    def test_export_publications_default_status(self):
        exporter = ISAJsonExporter(study_data={"publications": [{"title": "Paper"}]})
        result = exporter._export_publications()
        assert result[0]["status"]["annotationValue"] == "published"
        assert result[0]["pubMedID"] == ""
        assert result[0]["doi"] == ""

    # ------------------------------------------------------------------
    # _get_study_filename / _get_study_id
    # ------------------------------------------------------------------

    def test_get_study_filename(self, exporter):
        assert exporter._get_study_filename() == "s_study_1.txt"

    def test_get_study_filename_custom(self):
        exporter = ISAJsonExporter(study_data={}, study_id="my_study")
        assert exporter._get_study_filename() == "s_my_study.txt"

    def test_get_study_id(self, exporter):
        assert exporter._get_study_id() == "#study_1"

    def test_get_study_id_custom(self):
        exporter = ISAJsonExporter(study_data={}, study_id="my_study")
        assert exporter._get_study_id() == "#my_study"

    # ------------------------------------------------------------------
    # _get_protocol_id / _get_protocol_object
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("SDS-Page", "#protocol/sds_page"),
            ("Gel Electrophoresis", "#protocol/gel_electrophoresis"),
            ("my protocol", "#protocol/my_protocol"),
            ("", "#protocol/"),
        ],
    )
    def test_get_protocol_id(self, exporter, name, expected):
        assert exporter._get_protocol_id(name) == expected

    def test_get_protocol_object(self, exporter):
        result = exporter._get_protocol_object("SDS-Page")
        assert result == {"@id": "#protocol/sds_page", "name": "SDS-Page"}

    # ------------------------------------------------------------------
    # _get_file_type_ontology
    # ------------------------------------------------------------------

    def test_get_file_type_ontology_image(self, exporter):
        result = exporter._get_file_type_ontology("image")
        assert result["annotationValue"] == "image"
        assert result["termSource"] == "EDAM"
        assert result["termAccession"] == "http://edamontology.org/data_3567"

    def test_get_file_type_ontology_data(self, exporter):
        result = exporter._get_file_type_ontology("data")
        assert result["annotationValue"] == "data"
        assert result["termAccession"] == "http://edamontology.org/data_0006"

    def test_get_file_type_ontology_sequencing(self, exporter):
        result = exporter._get_file_type_ontology("sequencing")
        assert result["annotationValue"] == "sequence"
        assert result["termAccession"] == "http://edamontology.org/data_2044"

    def test_get_file_type_ontology_report(self, exporter):
        result = exporter._get_file_type_ontology("report")
        assert result["annotationValue"] == "report"
        assert result["termAccession"] == "http://edamontology.org/data_2531"

    def test_get_file_type_ontology_unknown(self, exporter):
        result = exporter._get_file_type_ontology("video")
        assert result == {"annotationValue": "video", "termSource": "EDAM"}
