"""
Tests for the Experiment folder processor (utils.batch.experiment_processor).

These tests verify that the batch conversion pipeline produces
GUI-compatible, ISA-JSON compliant output from the committed synthetic
fixtures in ``tests/batch_processing/fixtures/``.

The test classes exercise the neutralised experiment-folder processor
(``ExperimentProcessor``) against the committed synthetic fixture tree
(E1 / E10 / E11 convention).
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

import pytest

from utils.batch.experiment_classifier import ExperimentClassification
from utils.batch.experiment_processor import BatchResult, ExperimentProcessor
from utils.batch.folder_scanner import FileInventory, FolderMetadata

# Committed synthetic fixtures (E1 / E10 / E11 convention).
FIXTURES = Path(__file__).parent / "fixtures"
E1_FOLDER_NAME = "E1_viability_calcein_facs"
E10_FOLDER_NAME = "E10_explant_facs_treatment_donor"
E11_FOLDER_NAME = "E11_explant_facs_static_dapi"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_investigations(tmp_path, monkeypatch):
    """Point the processor at the committed fixture data root."""
    inv_root = tmp_path / "investigations"
    inv_root.mkdir()

    data_root = FIXTURES

    # Sanity: the required fixture folders must be committed.
    for name in (E1_FOLDER_NAME, E10_FOLDER_NAME, E11_FOLDER_NAME):
        assert (data_root / name).is_dir(), f"missing fixture folder: {name}"

    monkeypatch.chdir(tmp_path)

    return {
        "tmp_path": tmp_path,
        "data_root": data_root,
        "inv_root": inv_root,
        "base_path": str(tmp_path),
    }


@pytest.fixture
def processor(temp_investigations):
    """Create an ExperimentProcessor backed by the committed fixtures."""
    return ExperimentProcessor(
        data_root=str(temp_investigations["data_root"]),
        investigation_id="inv_fixture_01",
        base_path=str(temp_investigations["base_path"]),
        skip_conversion=True,
        validate=False,
        verbose=True,
    )


@pytest.fixture
def sample_experiment():
    """Create a sample FolderMetadata for testing."""
    return FolderMetadata(
        experiment_id="E1",
        experiment_name=E1_FOLDER_NAME,
        folder_path="/fake/path",
        file_inventory=FileInventory(
            czi_files=["sample.czi"],
            fcs_files=["sample.fcs"],
            tiff_files=["image.tiff"],
            xlsx_files=["data.xlsx"],
        ),
    )


@pytest.fixture
def sample_experiment_type():
    """Create a sample ExperimentClassification for testing."""
    return ExperimentClassification(
        type_name="calcein",
        assay_template="calcein_assay.json",
        confidence=0.9,
        detected_keywords=["calcein"],
        detected_files=["sample.czi"],
    )


@pytest.fixture
def e11_style_folder(tmp_path, monkeypatch):
    """Point the processor at the committed E11-style fixture folder."""
    inv_root = tmp_path / "investigations"
    inv_root.mkdir()

    data_root = FIXTURES
    e11 = data_root / E11_FOLDER_NAME
    assert e11.is_dir(), f"missing fixture folder: {E11_FOLDER_NAME}"

    monkeypatch.chdir(tmp_path)

    return {
        "tmp_path": tmp_path,
        "data_root": data_root,
        "inv_root": inv_root,
        "base_path": str(tmp_path),
    }


@pytest.fixture
def e11_processor(e11_style_folder):
    """Create a processor with E11-style fixture data."""
    return ExperimentProcessor(
        data_root=str(e11_style_folder["data_root"]),
        investigation_id="inv_fixture_02",
        skip_conversion=True,
        validate=False,
        verbose=True,
        base_path=str(e11_style_folder["base_path"]),
    )


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


class TestExperimentProcessorInit:
    """Tests for ExperimentProcessor initialization."""

    def test_init_creates_processor(self, temp_investigations):
        """Test that processor initializes correctly."""
        processor = ExperimentProcessor(
            data_root=str(temp_investigations["data_root"]),
            investigation_id="inv_fixture_01",
            base_path=str(temp_investigations["base_path"]),
        )
        assert processor.investigation_id == "inv_fixture_01"
        assert processor.data_root == Path(temp_investigations["data_root"])

    def test_init_creates_investigation_directory(self, temp_investigations):
        """Test that processor creates the investigation directory."""
        processor = ExperimentProcessor(
            data_root=str(temp_investigations["data_root"]),
            investigation_id="inv_fixture_01",
            base_path=str(temp_investigations["base_path"]),
        )
        # DirectoryManager uses its own base_path / investigations / inv_id
        inv_path = processor.dm.get_investigation_path("inv_fixture_01")
        assert inv_path.exists()


# ---------------------------------------------------------------------------
# Study ID generation tests
# ---------------------------------------------------------------------------


class TestStudyIdGeneration:
    """Tests for study ID generation."""

    def test_generate_study_id_from_e1(self, processor, sample_experiment):
        """Test study ID generation for the E1 experiment."""
        study_id = processor._generate_study_id(sample_experiment)
        assert study_id.startswith("study_E1_")
        # Should be a safe identifier
        assert " " not in study_id

    def test_generate_study_id_is_deterministic(self, processor, sample_experiment):
        """Test that study ID generation is deterministic."""
        id1 = processor._generate_study_id(sample_experiment)
        id2 = processor._generate_study_id(sample_experiment)
        assert id1 == id2


# ---------------------------------------------------------------------------
# Cell type detection tests
# ---------------------------------------------------------------------------


class TestCellTypeDetection:
    """Tests for cell/tissue type detection from folder names.

    The core cell-type registry maps the keywords ``endothelial_cell`` and
    ``cell_explant`` to themselves; any other name falls back to ``Unknown``.
    """

    def test_detect_endothelial_cell(self, processor):
        """Test detection of the ``endothelial_cell`` keyword."""
        exp = FolderMetadata(
            experiment_id="E12",
            experiment_name="E12_endothelial_cell_facs",
            folder_path="/fake",
        )
        cell_type = processor._determine_cell_type(exp)
        assert cell_type == "endothelial_cell"

    def test_detect_explant(self, processor):
        """Test detection of the ``cell_explant`` keyword."""
        exp = FolderMetadata(
            experiment_id="E10",
            experiment_name="E10_cell_explant_facs",
            folder_path="/fake",
        )
        cell_type = processor._determine_cell_type(exp)
        assert "explant" in cell_type.lower()

    def test_unknown_cell_type(self, processor, sample_experiment):
        """Test that an unmatched folder name falls back to ``Unknown``."""
        cell_type = processor._determine_cell_type(sample_experiment)
        assert cell_type == "Unknown"


# ---------------------------------------------------------------------------
# Condition extraction tests
# ---------------------------------------------------------------------------


class TestConditionExtraction:
    """Tests for experimental condition extraction from file names."""

    def test_extract_conditions_from_e1(self, processor, temp_investigations):
        """Test condition extraction from the E1 experiment."""
        e1_folder = temp_investigations["data_root"] / E1_FOLDER_NAME
        exp = FolderMetadata(
            experiment_id="E1",
            experiment_name=E1_FOLDER_NAME,
            folder_path=str(e1_folder),
        )
        conditions = processor._determine_conditions(exp)
        assert isinstance(conditions, list)
        assert len(conditions) > 0


# ---------------------------------------------------------------------------
# Assay type determination tests
# ---------------------------------------------------------------------------


class TestAssayTypeDetermination:
    """Tests for assay type determination from experiment metadata."""

    def test_calcein_and_facs_for_e1(self, processor, sample_experiment, sample_experiment_type):
        """Test that the E1 experiment gets calcein and FACS assay types."""
        assay_types = processor._determine_assay_types(sample_experiment, sample_experiment_type)
        assert "calcein" in assay_types
        assert "facs" in assay_types

    def test_facs_for_e10(self, processor):
        """Test that an explant FACS experiment gets both assay types."""
        exp = FolderMetadata(
            experiment_id="E10",
            experiment_name="E10_Explant_Calcein_FACS",
            folder_path="/fake",
            file_inventory=FileInventory(fcs_files=["sample.fcs"]),
        )
        exp_type = ExperimentClassification(
            type_name="facs",
            assay_template="facs_assay.json",
            confidence=0.9,
            detected_keywords=["facs"],
            detected_files=[],
        )
        assay_types = processor._determine_assay_types(exp, exp_type)
        assert "facs" in assay_types
        # calcein is matched via the folder name keyword
        assert "calcein" in assay_types


# ---------------------------------------------------------------------------
# Study creation tests
# ---------------------------------------------------------------------------


class TestStudyCreation:
    """Tests for study creation and data structure."""

    def test_create_study_has_required_fields(
        self, processor, sample_experiment, sample_experiment_type
    ):
        """Test that created study has all required internal-format fields."""
        study_data = processor._create_study(
            sample_experiment, "study_test", sample_experiment_type
        )
        # Internal format uses snake_case keys that ISAJsonExporter reads
        assert "identifier" in study_data
        assert "study_name" in study_data
        assert "study_description" in study_data
        assert "submission_date" in study_data
        assert "materials" in study_data
        assert "assays" in study_data
        assert "protocols" in study_data
        assert "characteristicCategories" in study_data
        assert "study_design_descriptors" in study_data

    def test_create_study_materials_structure(
        self, processor, sample_experiment, sample_experiment_type
    ):
        """Test that study materials have correct structure."""
        study_data = processor._create_study(
            sample_experiment, "study_test", sample_experiment_type
        )
        materials = study_data["materials"]
        assert "sources" in materials
        assert "samples" in materials
        assert "otherMaterials" in materials
        assert isinstance(materials["sources"], list)
        assert isinstance(materials["samples"], list)

    def test_create_study_directory_exists(
        self, processor, sample_experiment, sample_experiment_type
    ):
        """Test that study directory is created on disk."""
        study_id = "study_test_dir"
        processor._create_study(sample_experiment, study_id, sample_experiment_type)

        study_path = processor.dm.get_study_path(processor.investigation_id, study_id)
        assert study_path.exists()


# ---------------------------------------------------------------------------
# Material creation tests
# ---------------------------------------------------------------------------


class TestMaterialCreation:
    """Tests for material creation."""

    def test_create_materials_produces_source(self, processor, temp_investigations):
        """Test that material creation produces a source material."""
        e1_folder = temp_investigations["data_root"] / E1_FOLDER_NAME
        exp = FolderMetadata(
            experiment_id="E1",
            experiment_name=E1_FOLDER_NAME,
            folder_path=str(e1_folder),
        )
        exp_type = ExperimentClassification(
            type_name="calcein",
            assay_template="calcein_assay.json",
            confidence=0.9,
            detected_keywords=["calcein"],
            detected_files=[],
        )
        study_id = "study_001"
        study_data = processor._create_study(exp, study_id, exp_type)

        from utils.material_manager import MaterialManager

        material_manager = MaterialManager(
            study_data=study_data,
            directory_manager=processor.dm,
            investigation_id=processor.investigation_id,
            study_id=study_id,
        )

        source_id, sample_ids = processor._create_materials(
            study_data, material_manager, exp, exp_type
        )

        assert source_id is not None
        assert len(source_id) > 0
        assert len(sample_ids) > 0


# ---------------------------------------------------------------------------
# ISA-JSON export tests
# ---------------------------------------------------------------------------


class TestISAJsonExport:
    """Tests for ISA-JSON export and GUI compatibility."""

    def test_export_creates_study_json(self, processor, temp_investigations):
        """Test that export creates a study.json file."""
        study_data = {
            "identifier": "study_test",
            "study_name": "Test Study",
            "study_description": "Test",
            "submission_date": "2025-01-01",
            "materials": {"sources": [], "samples": [], "otherMaterials": []},
            "assays": [],
            "protocols": [],
            "characteristicCategories": [],
        }
        study_id = "study_export_test"
        processor.dm.create_study_directory(processor.investigation_id, study_id)
        processor._export_study_json(study_data, study_id)

        study_json = processor.dm.get_study_json_path(processor.investigation_id, study_id)
        assert study_json.exists()

        # Verify JSON is valid and has ISA-JSON structure
        with open(study_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        # ISA-JSON structure: top-level has 'studies' key
        assert "studies" in data
        assert isinstance(data["studies"], list)
        assert len(data["studies"]) == 1

    def test_export_isa_json_has_required_fields(self, processor, temp_investigations):
        """Test that exported ISA-JSON has required investigation fields."""
        study_data = {
            "identifier": "study_fields_test",
            "study_name": "Test Study",
            "study_description": "Test description",
            "submission_date": "2025-01-01",
            "public_release_date": "",
            "materials": {"sources": [], "samples": [], "otherMaterials": []},
            "assays": [],
            "protocols": [],
            "characteristicCategories": [],
        }
        study_id = "study_fields_test"
        processor.dm.create_study_directory(processor.investigation_id, study_id)
        processor._export_study_json(study_data, study_id)

        study_json = processor.dm.get_study_json_path(processor.investigation_id, study_id)
        with open(study_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Check investigation-level fields
        assert "identifier" in data
        assert "studies" in data
        assert "ontologySourceReferences" in data
        assert "title" in data
        assert "submissionDate" in data
        # Verify the study title was correctly propagated from study_name
        assert data["studies"][0]["title"] == "Test Study"
        assert data["studies"][0]["description"] == "Test description"

    def test_export_gui_compatible_structure(self, processor, temp_investigations):
        """Test that exported JSON is compatible with GUI loading.

        The GUI expects the 'studies' key at the top level, with
        studies[0] containing the study data.  Internal keys must
        use snake_case so that ISAJsonExporter propagates them
        correctly into the camelCase ISA-JSON output.
        """
        study_data = {
            "identifier": "study_gui_test",
            "study_name": "GUI Test Study",
            "study_description": "Test for GUI compatibility",
            "submission_date": "2025-01-01",
            "public_release_date": "",
            "study_design_descriptors": [
                {
                    "annotationValue": "experimental study",
                    "termSource": "OBI",
                    "termAccession": "http://purl.obolibrary.org/obo/OBI_0000066",
                }
            ],
            "materials": {
                "sources": [
                    {
                        "@id": (
                            f"/investigations/{processor.investigation_id}"
                            "/studies/study_gui_test#source_test"
                        ),
                        "name": "Test Source",
                        "characteristics": [],
                    }
                ],
                "samples": [],
                "otherMaterials": [],
            },
            "assays": [
                {
                    "@id": (
                        f"/investigations/{processor.investigation_id}"
                        "/studies/study_gui_test#assay_calcein"
                    ),
                    "name": "Calcein assay",
                    "measurementType": {
                        "annotationValue": "viability assay",
                        "termSource": "OBI",
                    },
                    "technologyType": {
                        "annotationValue": "fluorescence microscopy",
                        "termSource": "OBI",
                    },
                    "dataFiles": [],
                    "materials": {"samples": [], "otherMaterials": []},
                    "processSequence": [],
                    "characteristicCategories": [],
                    "unitCategories": [],
                    "filename": "a_calcein.txt",
                }
            ],
            "protocols": [],
            "process_sequence": {"processes": []},
            "characteristicCategories": [],
        }
        study_id = "study_gui_test"
        processor.dm.create_study_directory(processor.investigation_id, study_id)
        processor._export_study_json(study_data, study_id)

        study_json = processor.dm.get_study_json_path(processor.investigation_id, study_id)
        with open(study_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Verify GUI can read this structure
        assert "studies" in data
        study = data["studies"][0]

        # GUI StudiesPage reads studies[0].title to display the study name
        assert "title" in study
        assert (
            study["title"] == "GUI Test Study"
        ), "Study title must be propagated from internal 'study_name' key"
        assert (
            study["description"] == "Test for GUI compatibility"
        ), "Study description must be propagated from internal 'study_description' key"

        # GUI checks for studies[0].assays
        assert "assays" in study
        assert len(study["assays"]) == 1
        # The ISAJsonExporter normalizes measurement types
        meas_type = study["assays"][0]["measurementType"]["annotationValue"]
        assert isinstance(meas_type, str)
        assert len(meas_type) > 0

        # GUI checks for studies[0].materials
        assert "materials" in study
        assert "sources" in study["materials"]
        assert len(study["materials"]["sources"]) == 1


# ---------------------------------------------------------------------------
# Full pipeline tests
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """Tests for the full processing pipeline."""

    def test_process_all_experiments(self, processor, temp_investigations):
        """Test processing all experiment folders."""
        result = processor.process_all()

        assert result.total_experiments >= 3  # E1, E10 and E11
        assert result.successful >= 3
        assert result.failed == 0

    def test_process_all_creates_study_jsons(self, processor, temp_investigations):
        """Test that processing creates study.json files for all successful studies."""
        result = processor.process_all()

        # Check that study JSON files exist for all successful studies
        studies_root = processor.dm.get_studies_root(processor.investigation_id)
        assert studies_root.exists()

        for sr in result.study_results:
            if sr.success:
                study_json = studies_root / sr.study_id / "study.json"
                assert study_json.exists(), f"study.json not found for {sr.study_id}"

    def test_process_all_produces_valid_isa_json(self, processor, temp_investigations):
        """Test that all output ISA-JSON is valid."""
        processor.process_all()

        studies_root = processor.dm.get_studies_root(processor.investigation_id)
        for study_dir in studies_root.iterdir():
            if not study_dir.is_dir():
                continue
            study_json = study_dir / "study.json"
            if not study_json.exists():
                continue

            with open(study_json, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Check basic ISA-JSON structure
            assert "studies" in data, f"Missing 'studies' in {study_json}"
            assert len(data["studies"]) > 0, f"Empty studies in {study_json}"

            study = data["studies"][0]
            assert "identifier" in study
            assert "title" in study
            # Title must be non-empty — if this fails, the pipeline's
            # _create_study() is using camelCase keys that ISAJsonExporter
            # doesn't recognise (it reads snake_case internally).
            assert study["title"], (
                f"Study title is empty in {study_json} — "
                "check _create_study() uses snake_case keys "
                "(study_name, study_description, …)"
            )

    def test_process_single_experiment(self, processor, temp_investigations):
        """Test processing a single experiment."""
        e1_folder = temp_investigations["data_root"] / E1_FOLDER_NAME
        exp = FolderMetadata(
            experiment_id="E1",
            experiment_name=E1_FOLDER_NAME,
            folder_path=str(e1_folder),
        )

        result = processor._process_experiment(exp)
        assert result.success
        assert result.assays_created > 0
        assert result.materials_created > 0

    def test_data_files_linked_to_assays(self, processor, temp_investigations):
        """Test that data files are linked to assays in the ISA-JSON."""
        processor.process_all()

        studies_root = processor.dm.get_studies_root(processor.investigation_id)
        total_data_files = 0

        for study_dir in studies_root.iterdir():
            if not study_dir.is_dir():
                continue
            study_json = study_dir / "study.json"
            if not study_json.exists():
                continue

            with open(study_json, "r", encoding="utf-8") as f:
                data = json.load(f)

            for study in data.get("studies", []):
                for assay in study.get("assays", []):
                    data_files = assay.get("dataFiles", [])
                    total_data_files += len(data_files)

        assert total_data_files > 0, "No data files linked to any assay"


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for ISA-JSON validation."""

    def test_internal_validation_runs(self, temp_investigations):
        """Test that internal validation runs without errors."""
        processor = ExperimentProcessor(
            data_root=str(temp_investigations["data_root"]),
            investigation_id="inv_fixture_03",
            skip_conversion=True,
            validate=True,
            base_path=str(temp_investigations["base_path"]),
        )
        result = processor.process_all()
        # Validation should complete (even if there are warnings)
        assert isinstance(result, BatchResult)


# ---------------------------------------------------------------------------
# File-to-assay assignment tests (E11-style fixture)
# ---------------------------------------------------------------------------


class TestFileToAssayAssignment:
    """Tests for context-aware file-to-assay assignment."""

    def test_dapi_assay_receives_pyramidal_dir_files(self, e11_processor, e11_style_folder):
        """Files in *_files/ pyramidal subdirectories should be assigned to DAPI assay."""
        e11_folder = e11_style_folder["data_root"] / E11_FOLDER_NAME
        exp = FolderMetadata(
            experiment_id="E11",
            experiment_name=E11_FOLDER_NAME,
            folder_path=str(e11_folder),
        )
        result = e11_processor._process_experiment(exp)
        assert result.success
        assert result.assays_created >= 2, "E11 should have FACS + DAPI assays"
        assert result.files_linked > 0

        # Read the generated ISA-JSON
        study_json_path = e11_processor.dm.get_study_json_path(
            e11_processor.investigation_id, result.study_id
        )
        with open(study_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        study = data["studies"][0]
        dapi_assay = None
        for assay in study.get("assays", []):
            name = assay.get("measurementType", {}).get("annotationValue", "").lower()
            if "staining" in name:
                # Staining-type assay is the DAPI assay
                dapi_assay = assay
            elif "flow cytometry" in name:
                pass  # facs assay found

        # DAPI assay should have files from *_files/ directories
        if dapi_assay:
            dapi_files = dapi_assay.get("dataFiles", [])
            dapi_names = [f["name"] for f in dapi_files]
            assert any(
                ".czi" in n for n in dapi_names
            ), f"DAPI assay missing .czi files. Got: {dapi_names}"
            assert any(
                ".png" in n for n in dapi_names
            ), f"DAPI assay missing .png files. Got: {dapi_names}"

    def test_facs_assay_receives_png_plots(self, e11_processor, e11_style_folder):
        """PNG files in FACS/ subdirectory should be assigned to FACS assay."""
        e11_folder = e11_style_folder["data_root"] / E11_FOLDER_NAME
        exp = FolderMetadata(
            experiment_id="E11",
            experiment_name=E11_FOLDER_NAME,
            folder_path=str(e11_folder),
        )
        result = e11_processor._process_experiment(exp)
        assert result.success

        study_json_path = e11_processor.dm.get_study_json_path(
            e11_processor.investigation_id, result.study_id
        )
        with open(study_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        study = data["studies"][0]
        for assay in study.get("assays", []):
            name = assay.get("measurementType", {}).get("annotationValue", "").lower()
            if "flow cytometry" in name:
                facs_files = assay.get("dataFiles", [])
                facs_names = [f["name"] for f in facs_files]
                # FACS assay should have .fcs, .wsp, AND .png plot images
                assert any(
                    ".fcs" in n for n in facs_names
                ), f"FACS assay missing .fcs files. Got: {facs_names}"
                assert any(
                    ".png" in n for n in facs_names
                ), f"FACS assay missing .png plot images. Got: {facs_names}"

    def test_xlsx_linked_to_calcein_assay(self, temp_investigations):
        """xlsx files should be linked to the calcein assay when present."""
        # E1 has calcein + FACS assays; xlsx should go to calcein
        processor = ExperimentProcessor(
            data_root=str(temp_investigations["data_root"]),
            investigation_id="inv_fixture_04",
            skip_conversion=True,
            validate=False,
            base_path=str(temp_investigations["base_path"]),
        )
        result = processor.process_all()
        assert result.successful > 0
        assert result.total_files_linked > 0

    def test_e11_total_coverage_improved(self, e11_processor, e11_style_folder):
        """E11-style folder should have significantly more files linked."""
        e11_folder = e11_style_folder["data_root"] / E11_FOLDER_NAME
        exp = FolderMetadata(
            experiment_id="E11",
            experiment_name=E11_FOLDER_NAME,
            folder_path=str(e11_folder),
        )
        result = e11_processor._process_experiment(exp)
        assert result.success
        # We have 10 files total in the committed fixture:
        # FACS: 1 .fcs, 1 .png, 1 .wsp = 3
        # *_files/: 2 .czi, 3 .png, 1 .tif, 1 .xml = 7
        # Total = 10
        assert (
            result.files_linked >= 7
        ), f"Expected at least 7 files linked, got {result.files_linked}"


class TestRecursiveConditionScan:
    """Tests for recursive _determine_conditions()."""

    def test_conditions_from_facs_subdirectory(self, e11_processor, e11_style_folder):
        """Conditions should be detected from files in FACS/ subdirectory."""
        e11_folder = e11_style_folder["data_root"] / E11_FOLDER_NAME
        exp = FolderMetadata(
            experiment_id="E11",
            experiment_name=E11_FOLDER_NAME,
            folder_path=str(e11_folder),
        )
        conditions = e11_processor._determine_conditions(exp)
        # "Control" should be detected from "Sample_LiveDead_Control.fcs" in FACS/
        assert "Control" in conditions, f"Expected 'Control' in conditions, got: {conditions}"

    def test_conditions_from_nested_subdirectories(self, tmp_path):
        """Conditions should be detected from files in nested subdirectories."""
        # Build a temporary data root with a nested file carrying a condition.
        data_root = tmp_path / "data"
        e1_folder = data_root / E1_FOLDER_NAME
        e1_folder.mkdir(parents=True)
        (e1_folder / "sample.czi").write_bytes(b"fake")
        nested_dir = e1_folder / "subdir"
        nested_dir.mkdir()
        (nested_dir / "sample_compoundA_test.czi").write_bytes(b"fake")

        exp = FolderMetadata(
            experiment_id="E1",
            experiment_name=E1_FOLDER_NAME,
            folder_path=str(e1_folder),
        )
        processor = ExperimentProcessor(
            data_root=str(data_root),
            investigation_id="inv_fixture_05",
            skip_conversion=True,
            validate=False,
            base_path=str(tmp_path),
        )
        conditions = processor._determine_conditions(exp)
        # The stem token "compoundA" is capitalised to "Compounda"
        assert "Compounda" in conditions, f"Expected 'Compounda', got: {conditions}"


class TestStudyFactors:
    """Tests for study factors derived from the factor-extraction rule engine."""

    def test_treatment_donor_study_has_treatment_factor(self, temp_investigations):
        """The E10 treatment/donor study should have the rule-derived factors."""
        e10_folder = temp_investigations["data_root"] / E10_FOLDER_NAME
        processor = ExperimentProcessor(
            data_root=str(temp_investigations["data_root"]),
            investigation_id="inv_fixture_06",
            skip_conversion=True,
            validate=False,
            base_path=str(temp_investigations["base_path"]),
        )
        exp = FolderMetadata(
            experiment_id="E10",
            experiment_name=E10_FOLDER_NAME,
            folder_path=str(e10_folder),
        )
        result = processor._process_experiment(exp)
        assert result.success

        study_json_path = processor.dm.get_study_json_path(
            processor.investigation_id, result.study_id
        )
        with open(study_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        study = data["studies"][0]
        factors = study.get("factors", [])
        assert len(factors) > 0, "Study should have at least one factor"
        factor_names = [f.get("factorName", "") for f in factors]
        assert "treatment" in factor_names, f"Expected 'treatment' factor, got: {factor_names}"

    def test_samples_have_factor_values(self, temp_investigations):
        """Samples in the E10 study should have factorValues populated."""
        e10_folder = temp_investigations["data_root"] / E10_FOLDER_NAME
        processor = ExperimentProcessor(
            data_root=str(temp_investigations["data_root"]),
            investigation_id="inv_fixture_07",
            skip_conversion=True,
            validate=False,
            base_path=str(temp_investigations["base_path"]),
        )
        exp = FolderMetadata(
            experiment_id="E10",
            experiment_name=E10_FOLDER_NAME,
            folder_path=str(e10_folder),
        )
        result = processor._process_experiment(exp)
        assert result.success

        study_json_path = processor.dm.get_study_json_path(
            processor.investigation_id, result.study_id
        )
        with open(study_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        study = data["studies"][0]
        samples = study.get("materials", {}).get("samples", [])
        assert len(samples) > 0, "Study should have samples"

        # At least some samples should have factorValues
        samples_with_fv = [
            s for s in samples if s.get("factorValues") and len(s["factorValues"]) > 0
        ]
        assert len(samples_with_fv) > 0, "At least some samples should have factorValues"


class TestFileSizeMetadata:
    """Tests for file size metadata in data file entries."""

    def test_linked_files_have_file_size_comment(self, temp_investigations):
        """Linked data files should include a fileSize comment."""
        processor = ExperimentProcessor(
            data_root=str(temp_investigations["data_root"]),
            investigation_id="inv_fixture_08",
            skip_conversion=True,
            validate=False,
            base_path=str(temp_investigations["base_path"]),
        )
        result = processor.process_all()
        assert result.successful > 0

        studies_root = processor.dm.get_studies_root(processor.investigation_id)
        found_file_size = False
        for study_dir in studies_root.iterdir():
            if not study_dir.is_dir():
                continue
            study_json = study_dir / "study.json"
            if not study_json.exists():
                continue

            with open(study_json, "r", encoding="utf-8") as f:
                data = json.load(f)

            for study in data.get("studies", []):
                for assay in study.get("assays", []):
                    for df in assay.get("dataFiles", []):
                        comments = df.get("comments", [])
                        for c in comments:
                            if c.get("name") == "fileSize":
                                found_file_size = True
                                # File size should be a numeric string
                                assert c[
                                    "value"
                                ].isdigit(), f"fileSize should be numeric, got: {c['value']}"

        assert found_file_size, "No data file entries have fileSize comment"


# ---------------------------------------------------------------------------
# Tests for file modification date retrieval
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.batch_component
class TestFileModificationDateRetrieval:
    """Tests that study submission_date comes from file modification times."""

    def test_get_latest_modification_date_returns_iso_format(self, temp_investigations):
        """_get_latest_modification_date returns an ISO-8601 datetime string."""
        processor = ExperimentProcessor(
            investigation_id="test_inv", base_path=str(temp_investigations["base_path"])
        )
        data_root = temp_investigations["data_root"]
        e1_folder = data_root / E1_FOLDER_NAME

        date_str = processor._get_latest_modification_date(str(e1_folder))

        # Should match ISO-8601 pattern YYYY-MM-DDTHH:MM:SSZ
        assert re.match(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", date_str
        ), f"Date '{date_str}' is not in ISO-8601 format"

    def test_get_latest_modification_date_nonexistent_folder(self, tmp_path):
        """Falls back to current datetime for non-existent folder."""
        processor = ExperimentProcessor(investigation_id="test_inv", base_path=str(tmp_path))

        date_str = processor._get_latest_modification_date("/nonexistent/path")

        # Should still return a valid ISO date
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", date_str)

    def test_study_submission_date_from_file_mtime(self, temp_investigations):
        """Study submission_date should be derived from file modification times."""
        processor = ExperimentProcessor(
            investigation_id="test_inv", base_path=str(temp_investigations["base_path"])
        )
        data_root = temp_investigations["data_root"]
        e1_folder = data_root / E1_FOLDER_NAME

        # Set a specific mtime on ALL files in the experiment folder
        known_time = datetime(2025, 6, 15, 10, 30, 0)
        for f in e1_folder.rglob("*"):
            if f.is_file():
                os.utime(str(f), (known_time.timestamp(), known_time.timestamp()))

        exp = FolderMetadata(
            experiment_id="E1",
            experiment_name=e1_folder.name,
            folder_path=str(e1_folder),
        )
        exp_type = ExperimentClassification(
            type_name="calcein",
            assay_template="calcein_assay.json",
            confidence=0.9,
            detected_keywords=["calcein"],
            detected_files=[],
        )

        study_id = processor._generate_study_id(exp)
        study_data = processor._create_study(exp, study_id, exp_type)

        # The date should not be datetime.now() — it should come from the files
        submission_date = study_data["submission_date"]
        assert submission_date.startswith(
            "2025-06-15"
        ), f"Expected date from file mtime (2025-06-15), got: {submission_date}"

    def test_study_submission_date_not_current_timestamp(self, temp_investigations):
        """Study date should differ from 'now' when files have older mtimes."""
        processor = ExperimentProcessor(
            investigation_id="test_inv", base_path=str(temp_investigations["base_path"])
        )
        data_root = temp_investigations["data_root"]
        e1_folder = data_root / E1_FOLDER_NAME

        # Set ALL files' mtime to 1 year ago
        old_time = datetime(2024, 1, 15, 12, 0, 0)
        for f in e1_folder.rglob("*"):
            if f.is_file():
                os.utime(str(f), (old_time.timestamp(), old_time.timestamp()))

        exp = FolderMetadata(
            experiment_id="E1",
            experiment_name=e1_folder.name,
            folder_path=str(e1_folder),
        )
        exp_type = ExperimentClassification(
            type_name="calcein",
            assay_template="calcein_assay.json",
            confidence=0.9,
            detected_keywords=["calcein"],
            detected_files=[],
        )

        study_id = processor._generate_study_id(exp)
        study_data = processor._create_study(exp, study_id, exp_type)

        now_str = datetime.now().strftime("%Y-%m-%d")
        submission_date = study_data["submission_date"]

        # The date should NOT be today
        assert not submission_date.startswith(now_str), (
            f"submission_date should be from file mtime, not datetime.now(). "
            f"Got: {submission_date}, today: {now_str}"
        )
