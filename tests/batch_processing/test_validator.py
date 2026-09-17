"""
Unit tests for Validator component (ISA-JSON validation).
"""

import json

import pytest

from utils.batch.validator import FileValidationResult, ISAJsonValidator, ValidationResult


@pytest.mark.unit
@pytest.mark.batch_component
@pytest.mark.isa_validation
class TestISAJsonValidator:
    """Tests for ISAJsonValidator class."""

    def test_initialization(self, isa_validator):
        """Test validator initialization."""
        assert isinstance(isa_validator, ISAJsonValidator)
        assert len(isa_validator.required_investigation_fields) > 0

    def test_validate_valid_investigation(self, isa_validator, temp_dir, valid_investigation_json):
        """Test validation of valid investigation."""
        inv_path = temp_dir / "investigation.json"
        with open(inv_path, "w") as f:
            json.dump(valid_investigation_json, f)

        result = isa_validator.validate_investigation(str(inv_path))

        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert result.validation_type == "investigation"

    def test_validate_investigation_missing_identifier(self, isa_validator, temp_dir):
        """Test validation of investigation missing identifier."""
        inv_data = {
            "investigation": {
                "@id": "https://example.org/investigations/test_inv",
                # Missing: identifier
                "title": "Test Investigation",
                "description": "Test description",
                "submissionDate": "2024-01-01",
                "studies": [],
                "ontologySourceReferences": [],
            }
        }

        inv_path = temp_dir / "investigation.json"
        with open(inv_path, "w") as f:
            json.dump(inv_data, f)

        result = isa_validator.validate_investigation(str(inv_path))

        assert result.is_valid is False
        assert any("identifier" in error.lower() for error in result.errors)

    def test_validate_investigation_missing_title(self, isa_validator, temp_dir):
        """Test validation of investigation missing title."""
        inv_data = {
            "investigation": {
                "@id": "https://example.org/investigations/test_inv",
                "identifier": "test_inv",
                # Missing: title
                "description": "Test description",
                "submissionDate": "2024-01-01",
                "studies": [],
                "ontologySourceReferences": [],
            }
        }

        inv_path = temp_dir / "investigation.json"
        with open(inv_path, "w") as f:
            json.dump(inv_data, f)

        result = isa_validator.validate_investigation(str(inv_path))

        assert result.is_valid is False
        assert any("title" in error.lower() for error in result.errors)

    def test_validate_investigation_no_studies(self, isa_validator, temp_dir):
        """Test validation of investigation with no studies (warning)."""
        inv_data = {
            "investigation": {
                "@id": "https://example.org/investigations/test_inv",
                "identifier": "test_inv",
                "title": "Test Investigation",
                "description": "Test description",
                "submissionDate": "2024-01-01",
                "publicReleaseDate": "2025-01-01",
                "studies": [],
                "ontologySourceReferences": [],
            }
        }

        inv_path = temp_dir / "investigation.json"
        with open(inv_path, "w") as f:
            json.dump(inv_data, f)

        result = isa_validator.validate_investigation(str(inv_path))

        # Should be valid but with warning
        assert any("no studies" in warning.lower() for warning in result.warnings)

    def test_validate_investigation_with_study(
        self, isa_validator, temp_dir, valid_investigation_json, valid_study_json
    ):
        """Test validation of investigation with study."""
        inv_data = valid_investigation_json.copy()
        inv_data["investigation"]["studies"] = [valid_study_json]

        inv_path = temp_dir / "investigation.json"
        with open(inv_path, "w") as f:
            json.dump(inv_data, f)

        result = isa_validator.validate_investigation(str(inv_path))

        assert result.is_valid is True
        # Check that studies were detected (info contains "studies" or "study")
        assert any("stud" in info.lower() for info in result.info)

    def test_validate_invalid_json(self, isa_validator, temp_dir):
        """Test validation of invalid JSON file."""
        inv_path = temp_dir / "investigation.json"
        inv_path.write_text("{ invalid json }")

        result = isa_validator.validate_investigation(str(inv_path))

        assert result.is_valid is False
        assert any("json" in error.lower() for error in result.errors)

    def test_validate_nonexistent_file(self, isa_validator):
        """Test validation of nonexistent file."""
        result = isa_validator.validate_investigation("/nonexistent/file.json")

        assert result.is_valid is False
        assert any("not found" in error.lower() for error in result.errors)

    def test_validate_ontology_references(self, isa_validator, temp_dir):
        """Test ontology reference validation."""
        inv_data = {
            "investigation": {
                "@id": "https://example.org/investigations/test_inv",
                "identifier": "test_inv",
                "title": "Test Investigation",
                "description": "Test description",
                "submissionDate": "2024-01-01",
                "publicReleaseDate": "2025-01-01",
                "studies": [],
                "ontologySourceReferences": [
                    {
                        "name": "OBI",
                        "description": "Ontology for Biomedical Investigations",
                        "file": "http://purl.obolibrary.org/obo/obi.owl",
                        "version": "2024-01-01",
                    }
                ],
            }
        }

        inv_path = temp_dir / "investigation.json"
        with open(inv_path, "w") as f:
            json.dump(inv_data, f)

        result = isa_validator.validate_investigation(str(inv_path))

        assert any("ontology" in info.lower() for info in result.info)

    def test_validate_incomplete_ontology_reference(self, isa_validator, temp_dir):
        """Test validation of incomplete ontology reference."""
        inv_data = {
            "investigation": {
                "@id": "https://example.org/investigations/test_inv",
                "identifier": "test_inv",
                "title": "Test Investigation",
                "description": "Test description",
                "submissionDate": "2024-01-01",
                "publicReleaseDate": "2025-01-01",
                "studies": [],
                "ontologySourceReferences": [
                    {
                        "name": "OBI"
                        # Missing: description, file, version
                    }
                ],
            }
        }

        inv_path = temp_dir / "investigation.json"
        with open(inv_path, "w") as f:
            json.dump(inv_data, f)

        result = isa_validator.validate_investigation(str(inv_path))

        assert any("ontology" in warning.lower() for warning in result.warnings)


@pytest.mark.unit
@pytest.mark.batch_component
@pytest.mark.isa_validation
class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_creation(self):
        """Test ValidationResult creation."""
        result = ValidationResult(is_valid=True, validation_type="investigation")

        assert result.is_valid is True
        assert result.validation_type == "investigation"
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_validation_result_with_errors(self):
        """Test ValidationResult with errors."""
        result = ValidationResult(
            is_valid=False, validation_type="investigation", errors=["Error 1", "Error 2"]
        )

        assert result.is_valid is False
        assert len(result.errors) == 2
        assert "Error 1" in result.errors

    def test_validation_result_with_warnings(self):
        """Test ValidationResult with warnings."""
        result = ValidationResult(
            is_valid=True, validation_type="investigation", warnings=["Warning 1"]
        )

        assert result.is_valid is True
        assert len(result.warnings) == 1
        assert "Warning 1" in result.warnings


@pytest.mark.unit
@pytest.mark.batch_component
@pytest.mark.isa_validation
class TestFileValidationResult:
    """Tests for FileValidationResult dataclass."""

    def test_file_validation_result_creation(self):
        """Test FileValidationResult creation."""
        result = FileValidationResult(
            file_path="/test/file.txt", file_exists=True, file_readable=True, file_size=1024
        )

        assert result.file_path == "/test/file.txt"
        assert result.file_exists is True
        assert result.file_readable is True
        assert result.file_size == 1024

    def test_file_validation_result_nonexistent(self):
        """Test FileValidationResult for nonexistent file."""
        result = FileValidationResult(
            file_path="/nonexistent/file.txt", file_exists=False, file_readable=False, file_size=0
        )

        assert result.file_exists is False
        assert result.file_size == 0


# ----------------------------------------------------------------------
# Helpers for pure-logic validation tests
# ----------------------------------------------------------------------


def _make_valid_assay(assay_id="study_1_assay_0"):
    """Build a fully-populated, valid assay dict."""
    return {
        "measurementType": {
            "annotationValue": "protein expression",
            "termSource": "OBI",
            "termAccession": "http://purl.obolibrary.org/obo/OBI_0000615",
        },
        "technologyType": {
            "annotationValue": "mass spectrometry",
            "termSource": "OBI",
            "termAccession": "http://purl.obolibrary.org/obo/OBI_0000470",
        },
        "dataFiles": [{"name": "file_1.raw"}],
        "materials": {"samples": [], "otherMaterials": []},
        "processSequence": [
            {
                "name": "assay process",
                "executesProtocol": {"@id": "#protocol/assay", "name": "assay"},
                "inputs": [],
                "outputs": [],
            }
        ],
    }


def _make_valid_study(study_id="study_1"):
    """Build a fully-populated, valid study dict."""
    return {
        "identifier": "study_1",
        "title": "Test Study",
        "description": "Test study description",
        "submissionDate": "2024-01-01",
        "assays": [_make_valid_assay()],
        "materials": {
            "sources": [],
            "samples": [],
            "otherMaterials": [],
        },
        "protocols": [
            {"name": "assay", "protocolType": {"annotationValue": "assay", "termSource": "OBI"}}
        ],
        "processSequence": [],
    }


def _make_valid_investigation():
    """Build a fully-populated, valid investigation dict (flat format)."""
    return {
        "identifier": "test_inv",
        "title": "Test Investigation",
        "description": "Test description",
        "submissionDate": "2024-01-01",
        "publicReleaseDate": "2025-01-01",
        "studies": [_make_valid_study()],
        "ontologySourceReferences": [
            {
                "name": "OBI",
                "file": "http://purl.obolibrary.org/obo/obi.owl",
                "version": "latest",
            }
        ],
    }


@pytest.mark.unit
@pytest.mark.batch_component
@pytest.mark.isa_validation
class TestValidateStudy:
    """Tests for ISAJsonValidator._validate_study (pure dict -> ValidationResult)."""

    def test_valid_study(self, isa_validator):
        result = isa_validator._validate_study(_make_valid_study(), "study_1")
        assert result.is_valid is True
        assert result.validation_type == "study"
        assert result.errors == []

    def test_missing_single_required_field(self, isa_validator):
        study = _make_valid_study()
        del study["submissionDate"]
        result = isa_validator._validate_study(study, "study_1")
        assert result.is_valid is False
        assert any("submissionDate" in e and "Missing required field" in e for e in result.errors)

    def test_missing_all_required_fields(self, isa_validator):
        result = isa_validator._validate_study({}, "study_1")
        assert result.is_valid is False
        # 8 required fields: identifier, title, description, submissionDate,
        # assays, materials, protocols, processSequence
        assert len(result.errors) == 8
        for field in [
            "identifier",
            "title",
            "description",
            "submissionDate",
            "assays",
            "materials",
            "protocols",
            "processSequence",
        ]:
            assert any(field in e for e in result.errors)

    def test_study_id_in_error_messages(self, isa_validator):
        result = isa_validator._validate_study({}, "my_study")
        assert all("my_study" in e for e in result.errors)

    def test_no_assays_warning(self, isa_validator):
        study = _make_valid_study()
        study["assays"] = []
        result = isa_validator._validate_study(study, "study_1")
        assert any("No assays found" in w for w in result.warnings)

    def test_no_materials_warning(self, isa_validator):
        study = _make_valid_study()
        study["materials"] = {}
        result = isa_validator._validate_study(study, "study_1")
        assert any("No materials found" in w for w in result.warnings)

    def test_no_protocols_warning(self, isa_validator):
        study = _make_valid_study()
        study["protocols"] = []
        result = isa_validator._validate_study(study, "study_1")
        assert any("No protocols found" in w for w in result.warnings)

    def test_assays_count_info(self, isa_validator):
        study = _make_valid_study()
        study["assays"] = [_make_valid_assay(), _make_valid_assay()]
        result = isa_validator._validate_study(study, "study_1")
        assert any("Found 2 assays" in i for i in result.info)

    def test_invalid_assay_propagates(self, isa_validator):
        study = _make_valid_study()
        study["assays"] = [{"measurementType": {}}]  # missing required fields
        result = isa_validator._validate_study(study, "study_1")
        assert result.is_valid is False
        assert any("assay" in e for e in result.errors)


@pytest.mark.unit
@pytest.mark.batch_component
@pytest.mark.isa_validation
class TestValidateAssay:
    """Tests for ISAJsonValidator._validate_assay (pure dict -> ValidationResult)."""

    def test_valid_assay(self, isa_validator):
        result = isa_validator._validate_assay(_make_valid_assay(), "assay_1")
        assert result.is_valid is True
        assert result.validation_type == "assay"
        assert result.errors == []

    def test_missing_required_fields(self, isa_validator):
        result = isa_validator._validate_assay({}, "assay_1")
        assert result.is_valid is False
        # 5 required fields: measurementType, technologyType, dataFiles,
        # materials, processSequence
        assert len(result.errors) == 5
        for field in [
            "measurementType",
            "technologyType",
            "dataFiles",
            "materials",
            "processSequence",
        ]:
            assert any(field in e for e in result.errors)

    def test_missing_single_required_field(self, isa_validator):
        assay = _make_valid_assay()
        del assay["dataFiles"]
        result = isa_validator._validate_assay(assay, "assay_1")
        assert result.is_valid is False
        assert any("dataFiles" in e for e in result.errors)

    def test_measurement_type_missing_annotation(self, isa_validator):
        assay = _make_valid_assay()
        assay["measurementType"] = {"termSource": "OBI"}
        result = isa_validator._validate_assay(assay, "assay_1")
        assert any("measurement type annotation" in w.lower() for w in result.warnings)

    def test_measurement_type_missing_term_source(self, isa_validator):
        assay = _make_valid_assay()
        assay["measurementType"] = {"annotationValue": "protein expression"}
        result = isa_validator._validate_assay(assay, "assay_1")
        assert any("measurement type term source" in w.lower() for w in result.warnings)

    def test_measurement_type_missing_entirely(self, isa_validator):
        assay = _make_valid_assay()
        del assay["measurementType"]
        result = isa_validator._validate_assay(assay, "assay_1")
        assert result.is_valid is False
        assert any("measurement type annotation" in w.lower() for w in result.warnings)
        assert any("measurement type term source" in w.lower() for w in result.warnings)

    def test_technology_type_missing_annotation(self, isa_validator):
        assay = _make_valid_assay()
        assay["technologyType"] = {"termSource": "OBI"}
        result = isa_validator._validate_assay(assay, "assay_1")
        assert any("technology type annotation" in w.lower() for w in result.warnings)

    def test_technology_type_missing_term_source(self, isa_validator):
        assay = _make_valid_assay()
        assay["technologyType"] = {"annotationValue": "mass spectrometry"}
        result = isa_validator._validate_assay(assay, "assay_1")
        assert any("technology type term source" in w.lower() for w in result.warnings)

    def test_no_data_files_warning(self, isa_validator):
        assay = _make_valid_assay()
        assay["dataFiles"] = []
        result = isa_validator._validate_assay(assay, "assay_1")
        assert any("No data files found" in w for w in result.warnings)

    def test_data_file_missing_name_warning(self, isa_validator):
        assay = _make_valid_assay()
        assay["dataFiles"] = [{"@id": "#file_1"}]
        result = isa_validator._validate_assay(assay, "assay_1")
        assert any("Data file missing name" in w for w in result.warnings)

    def test_data_files_count_info(self, isa_validator):
        assay = _make_valid_assay()
        assay["dataFiles"] = [{"name": "f1"}, {"name": "f2"}]
        result = isa_validator._validate_assay(assay, "assay_1")
        assert any("Found 2 data files" in i for i in result.info)

    def test_no_process_sequence_warning(self, isa_validator):
        assay = _make_valid_assay()
        assay["processSequence"] = []
        result = isa_validator._validate_assay(assay, "assay_1")
        assert any("No process sequence found" in w for w in result.warnings)


@pytest.mark.unit
@pytest.mark.batch_component
@pytest.mark.isa_validation
class TestFairCompliance:
    """Tests for ISAJsonValidator._check_fair_compliance (pure dict -> result mutation)."""

    def _run(self, isa_validator, investigation):
        result = ValidationResult(is_valid=True, validation_type="investigation")
        isa_validator._check_fair_compliance(investigation, result)
        return result

    def test_fully_fair_investigation(self, isa_validator):
        investigation = _make_valid_investigation()
        investigation["studies"][0]["studyDesignDescriptors"] = [
            {"annotationValue": "experimental study", "termSource": "OBI"}
        ]
        result = self._run(isa_validator, investigation)
        assert any("Findable: Has identifier" in i for i in result.info)
        assert any("Findable: Has title" in i for i in result.info)
        assert any("Findable: Has description" in i for i in result.info)
        assert any("Accessible: Has protocols" in i for i in result.info)
        assert any("Interoperable" in i and "1 ontology references" in i for i in result.info)
        assert any("Reusable: Has study design descriptors" in i for i in result.info)
        assert not any("FAIR" in w for w in result.warnings)

    def test_missing_identifier_warning(self, isa_validator):
        investigation = _make_valid_investigation()
        del investigation["identifier"]
        result = self._run(isa_validator, investigation)
        assert any("Findable: Missing identifier" in w for w in result.warnings)

    def test_missing_title_and_description_no_info(self, isa_validator):
        investigation = _make_valid_investigation()
        del investigation["title"]
        del investigation["description"]
        result = self._run(isa_validator, investigation)
        assert not any("Has title" in i for i in result.info)
        assert not any("Has description" in i for i in result.info)

    def test_no_ontologies_warning(self, isa_validator):
        investigation = _make_valid_investigation()
        investigation["ontologySourceReferences"] = []
        result = self._run(isa_validator, investigation)
        assert any("Interoperable: No ontology references" in w for w in result.warnings)

    def test_empty_investigation(self, isa_validator):
        result = self._run(isa_validator, {})
        assert any("Findable: Missing identifier" in w for w in result.warnings)
        assert any("Interoperable: No ontology references" in w for w in result.warnings)

    def test_ontology_count_reported(self, isa_validator):
        investigation = _make_valid_investigation()
        investigation["ontologySourceReferences"] = [
            {"name": "OBI", "file": "obi.owl"},
            {"name": "UO", "file": "uo.owl"},
        ]
        result = self._run(isa_validator, investigation)
        assert any("2 ontology references" in i for i in result.info)


@pytest.mark.unit
@pytest.mark.batch_component
@pytest.mark.isa_validation
class TestMetadataValidatorChecks:
    """Tests for MetadataValidator pure-logic check methods."""

    @pytest.fixture
    def metadata_validator(self):
        from utils.batch.validator import MetadataValidator

        return MetadataValidator()

    @pytest.fixture
    def result(self):
        return ValidationResult(is_valid=True, validation_type="metadata")

    # ---- _check_investigation_metadata --------------------------------

    def test_check_investigation_metadata_complete(self, metadata_validator, result):
        investigation = _make_valid_investigation()
        metadata_validator._check_investigation_metadata(investigation, result)
        assert result.warnings == []
        assert result.info == []

    def test_check_investigation_metadata_missing_required(self, metadata_validator, result):
        metadata_validator._check_investigation_metadata({}, result)
        assert any("missing identifier" in w for w in result.warnings)
        assert any("missing title" in w for w in result.warnings)
        assert any("missing description" in w for w in result.warnings)

    def test_check_investigation_metadata_missing_recommended(self, metadata_validator, result):
        investigation = _make_valid_investigation()
        del investigation["submissionDate"]
        del investigation["publicReleaseDate"]
        metadata_validator._check_investigation_metadata(investigation, result)
        assert any("recommended field: submissionDate" in i for i in result.info)
        assert any("recommended field: publicReleaseDate" in i for i in result.info)
        assert result.warnings == []

    def test_check_investigation_metadata_partial(self, metadata_validator, result):
        investigation = {"identifier": "inv_1"}
        metadata_validator._check_investigation_metadata(investigation, result)
        assert any("missing title" in w for w in result.warnings)
        assert any("missing description" in w for w in result.warnings)
        assert any("recommended field: submissionDate" in i for i in result.info)

    # ---- _check_study_metadata -----------------------------------------

    def test_check_study_metadata_complete(self, metadata_validator, result):
        study = _make_valid_study()
        study["studyDesignDescriptors"] = [
            {"annotationValue": "experimental study", "termSource": "OBI"}
        ]
        study["characteristicCategories"] = [{"@id": "#characteristic_category/organism"}]
        metadata_validator._check_study_metadata(study, "study_1", result)
        assert result.warnings == []

    def test_check_study_metadata_missing_required(self, metadata_validator, result):
        metadata_validator._check_study_metadata({}, "study_1", result)
        assert any("study_1 missing identifier" in w for w in result.warnings)
        assert any("study_1 missing title" in w for w in result.warnings)
        assert any("study_1 missing description" in w for w in result.warnings)

    def test_check_study_metadata_missing_design_descriptors(self, metadata_validator, result):
        study = _make_valid_study()
        metadata_validator._check_study_metadata(study, "study_1", result)
        assert any("study design descriptors" in w for w in result.warnings)

    def test_check_study_metadata_missing_characteristic_categories(
        self, metadata_validator, result
    ):
        study = _make_valid_study()
        study["studyDesignDescriptors"] = [
            {"annotationValue": "experimental study", "termSource": "OBI"}
        ]
        metadata_validator._check_study_metadata(study, "study_1", result)
        assert any("characteristic categories" in w for w in result.warnings)

    # ---- _check_assay_metadata ------------------------------------------

    def test_check_assay_metadata_complete(self, metadata_validator, result):
        metadata_validator._check_assay_metadata(_make_valid_assay(), "assay_1", result)
        assert result.warnings == []

    def test_check_assay_metadata_empty_assay(self, metadata_validator, result):
        metadata_validator._check_assay_metadata({}, "assay_1", result)
        assert any("assay_1 missing measurement type" in w for w in result.warnings)
        assert any("assay_1 missing measurement type ontology" in w for w in result.warnings)
        assert any("assay_1 missing technology type" in w for w in result.warnings)
        assert any("assay_1 missing technology type ontology" in w for w in result.warnings)
        assert any("assay_1 missing data files" in w for w in result.warnings)

    def test_check_assay_metadata_missing_measurement_annotation(self, metadata_validator, result):
        assay = _make_valid_assay()
        assay["measurementType"] = {"termSource": "OBI"}
        metadata_validator._check_assay_metadata(assay, "assay_1", result)
        assert any("assay_1 missing measurement type" in w for w in result.warnings)

    def test_check_assay_metadata_missing_measurement_ontology(self, metadata_validator, result):
        assay = _make_valid_assay()
        assay["measurementType"] = {"annotationValue": "protein expression"}
        metadata_validator._check_assay_metadata(assay, "assay_1", result)
        assert any("assay_1 missing measurement type ontology" in w for w in result.warnings)

    def test_check_assay_metadata_missing_technology_annotation(self, metadata_validator, result):
        assay = _make_valid_assay()
        assay["technologyType"] = {"termSource": "OBI"}
        metadata_validator._check_assay_metadata(assay, "assay_1", result)
        assert any("assay_1 missing technology type" in w for w in result.warnings)

    def test_check_assay_metadata_missing_data_files(self, metadata_validator, result):
        assay = _make_valid_assay()
        assay["dataFiles"] = []
        metadata_validator._check_assay_metadata(assay, "assay_1", result)
        assert any("assay_1 missing data files" in w for w in result.warnings)
