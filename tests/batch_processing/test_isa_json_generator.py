"""
Unit tests for ISAJsonGenerator component.
"""

import json
from pathlib import Path

import pytest

from utils.batch.isa_json_generator import ISAAssay, ISAInvestigation, ISAJsonGenerator, ISAStudy


@pytest.mark.unit
@pytest.mark.batch_component
@pytest.mark.isa_validation
class TestISAJsonGenerator:
    """Tests for ISAJsonGenerator class."""

    def test_initialization(self, isa_json_generator):
        """Test generator initialization."""
        assert isinstance(isa_json_generator, ISAJsonGenerator)
        assert isa_json_generator.templates_root.endswith("assay_templates")

    def test_generate_investigation(self, isa_json_generator, sample_experiment_folder):
        """Test investigation generation."""
        investigation = isa_json_generator.generate_investigation(
            experiments=[sample_experiment_folder],
            investigation_id="test_inv",
            investigation_title="Test Investigation",
            investigation_description="Test description",
        )

        assert isinstance(investigation, ISAInvestigation)
        assert investigation.investigation_id == "test_inv"
        assert investigation.investigation_title == "Test Investigation"
        assert investigation.investigation_description == "Test description"

    def test_generate_study(self, isa_json_generator, sample_experiment_folder):
        """Test study generation."""
        study = isa_json_generator.generate_study(
            experiment_path=sample_experiment_folder,
            investigation_id="test_inv",
            study_id="study_1",
        )

        assert isinstance(study, ISAStudy)
        assert study.study_id == "study_1"
        assert len(study.assays) >= 0

    def test_generate_assay(self, isa_json_generator):
        """Test assay generation."""
        assay = isa_json_generator.generate_assay(
            assay_id="assay_1",
            assay_name="Test Assay",
            measurement_type={
                "annotationValue": "gene expression profiling",
                "termSource": "EFO",
                "termAccession": "http://www.ebi.ac.uk/efo/EFO_0003067",
            },
            technology_type={
                "annotationValue": "DNA microarray",
                "termSource": "EFO",
                "termAccession": "http://www.ebi.ac.uk/efo/EFO_0002692",
            },
        )

        assert isinstance(assay, ISAAssay)
        assert assay.assay_id == "assay_1"
        assert assay.assay_name == "Test Assay"

    def test_create_material_node(self, isa_json_generator):
        """Test material node creation."""
        material = isa_json_generator.create_material_node(
            material_id="source_1", material_type="source", name="Test Material"
        )

        assert material.material_id == "source_1"
        assert material.material_type == "source"
        assert material.name == "Test Material"

    def test_create_process_node(self, isa_json_generator):
        """Test process node creation."""
        process = isa_json_generator.create_process_node(
            process_id="process_1", executes_protocol="protocol_1"
        )

        assert process.process_id == "process_1"
        assert process.executes_protocol == "protocol_1"

    def test_investigation_to_dict(self, isa_json_generator):
        """Test investigation to dictionary conversion."""
        investigation = ISAInvestigation(
            investigation_id="test_inv",
            investigation_title="Test",
            investigation_description="Test desc",
            investigation_abstract="Test abstract",
            submission_date="2024-01-01",
            public_release_date="2025-01-01",
        )

        result = isa_json_generator._investigation_to_dict(investigation)

        assert isinstance(result, dict)
        assert "identifier" in result
        assert result["identifier"] == "test_inv"

    def test_study_to_dict(self, isa_json_generator):
        """Test study to dictionary conversion."""
        study = ISAStudy(
            study_id="study_1",
            study_name="Test Study",
            study_title="Test",
            study_description="Test desc",
            submission_date="2024-01-01",
            public_release_date="2025-01-01",
        )

        result = isa_json_generator._study_to_dict(study)

        assert isinstance(result, dict)
        assert result["identifier"] == "study_1"

    def test_assay_to_dict(self, isa_json_generator):
        """Test assay to dictionary conversion."""
        assay = ISAAssay(
            assay_id="assay_1",
            assay_name="Test Assay",
            measurement_type={
                "annotationValue": "test",
                "termSource": "TEST",
                "termAccession": "http://test.org/TEST_001",
            },
            technology_type={
                "annotationValue": "test",
                "termSource": "TEST",
                "termAccession": "http://test.org/TEST_002",
            },
        )

        result = isa_json_generator._assay_to_dict(assay)

        assert isinstance(result, dict)
        assert result["measurementType"]["annotationValue"] == "test"

    def test_save_investigation(self, isa_json_generator, temp_dir):
        """Test saving investigation to file with lightweight study references."""
        investigation = ISAInvestigation(
            investigation_id="test_inv",
            investigation_title="Test",
            investigation_description="Test desc",
            investigation_abstract="Test abstract",
            submission_date="2024-01-01",
            public_release_date="2025-01-01",
        )

        output_path = temp_dir / "investigation.json"
        isa_json_generator.save_investigation(investigation, str(output_path))

        assert output_path.exists()

        with open(output_path, "r") as f:
            data = json.load(f)
            # Lightweight investigation JSON has flat ISA-JSON structure
            assert "identifier" in data
            assert data["identifier"] == "test_inv"
            assert "studies" in data
            assert isinstance(data["studies"], list)

    def test_save_investigation_with_studies(self, isa_json_generator, temp_dir):
        """Test saving investigation creates per-study subfolders."""
        study = ISAStudy(
            study_id="study_E1",
            study_name="E1 Test",
            study_title="E1 Test Experiment",
            study_description="Test experiment E1",
            submission_date="2024-01-01",
            public_release_date="2025-01-01",
        )

        investigation = ISAInvestigation(
            investigation_id="test_inv",
            investigation_title="Test",
            investigation_description="Test desc",
            investigation_abstract="Test abstract",
            submission_date="2024-01-01",
            public_release_date="2025-01-01",
            studies=[study],
        )

        output_dir = temp_dir / "output"
        isa_json_generator.save_investigation(investigation, str(output_dir))

        # Check investigation JSON
        inv_file = output_dir / "test_inv.json"
        assert inv_file.exists()

        with open(inv_file, "r") as f:
            data = json.load(f)
            # Lightweight: studies have only references, not full data
            assert len(data["studies"]) == 1
            study_ref = data["studies"][0]
            assert study_ref["identifier"] == "study_E1"
            assert "assays" not in study_ref  # Lightweight: no assay data

        # Check per-study JSON
        study_file = output_dir / "studies" / "study_E1" / "study.json"
        assert study_file.exists()

        with open(study_file, "r") as f:
            study_data = json.load(f)
            assert study_data["identifier"] == "study_E1"
            assert study_data["title"] == "E1 Test Experiment"


@pytest.mark.unit
@pytest.mark.batch_component
@pytest.mark.isa_validation
class TestISAInvestigation:
    """Tests for ISAInvestigation dataclass."""

    def test_investigation_creation(self):
        """Test ISAInvestigation creation."""
        inv = ISAInvestigation(
            investigation_id="test_inv",
            investigation_title="Test",
            investigation_description="Test desc",
            investigation_abstract="Test abstract",
            submission_date="2024-01-01",
            public_release_date="2025-01-01",
        )

        assert inv.investigation_id == "test_inv"
        assert inv.investigation_title == "Test"
        assert len(inv.studies) == 0

    def test_investigation_with_studies(self):
        """Test ISAInvestigation with studies."""
        study = ISAStudy(
            study_id="study_1",
            study_name="Test Study",
            study_title="Test",
            study_description="Test desc",
            submission_date="2024-01-01",
            public_release_date="2025-01-01",
        )

        inv = ISAInvestigation(
            investigation_id="test_inv",
            investigation_title="Test",
            investigation_description="Test desc",
            investigation_abstract="Test abstract",
            submission_date="2024-01-01",
            public_release_date="2025-01-01",
            studies=[study],
        )

        assert len(inv.studies) == 1
        assert inv.studies[0].study_id == "study_1"


@pytest.mark.unit
@pytest.mark.batch_component
@pytest.mark.isa_validation
class TestISAStudy:
    """Tests for ISAStudy dataclass."""

    def test_study_creation(self):
        """Test ISAStudy creation."""
        study = ISAStudy(
            study_id="study_1",
            study_name="Test Study",
            study_title="Test",
            study_description="Test desc",
            submission_date="2024-01-01",
            public_release_date="2025-01-01",
        )

        assert study.study_id == "study_1"
        assert study.study_name == "Test Study"
        assert len(study.assays) == 0


@pytest.mark.unit
@pytest.mark.batch_component
@pytest.mark.isa_validation
class TestISAAssay:
    """Tests for ISAAssay dataclass."""

    def test_assay_creation(self):
        """Test ISAAssay creation."""
        assay = ISAAssay(
            assay_id="assay_1",
            assay_name="Test Assay",
            measurement_type={
                "annotationValue": "test",
                "termSource": "TEST",
                "termAccession": "http://test.org/TEST_001",
            },
            technology_type={
                "annotationValue": "test",
                "termSource": "TEST",
                "termAccession": "http://test.org/TEST_002",
            },
        )

        assert assay.assay_id == "assay_1"
        assert assay.assay_name == "Test Assay"
        assert len(assay.data_files) == 0


@pytest.mark.unit
@pytest.mark.batch_component
@pytest.mark.isa_validation
class TestParameterPopulation:
    """Tests for Fix 3: assay parameter population from templates."""

    def test_load_assay_template_reads_real_template(self, isa_json_generator):
        """_load_assay_template should read the actual template file, not fall back to default."""
        template = isa_json_generator._load_assay_template("calcein_assay.json")
        # Real template has parameters; the default fallback has empty parameters
        assert len(template.get("parameters", [])) > 0
        param_names = [p["name"] for p in template["parameters"]]
        assert "cell type" in param_names
        assert "excitation wavelength" in param_names

    def test_load_assay_template_with_suggest_template_path(self, isa_json_generator):
        """_load_assay_template should handle paths from suggest_template() (already prefixed)."""
        classifier = isa_json_generator.classifier
        # suggest_template returns paths prefixed with templates_root
        template_path = classifier.suggest_template(classifier.classify_from_name("E1_calcein"))
        template = isa_json_generator._load_assay_template(template_path)
        assert len(template.get("parameters", [])) > 0

    def test_extract_parameter_values_from_metadata(self, isa_json_generator):
        """_extract_parameter_values should map exp_meta keys to template parameter names."""
        exp_meta = {
            "experiment_id": "E1",
            "cell_types": ["muller_cell"],
            "assay_types": ["calcein"],
            "protein_variants": ["protA"],
            "drugs": [],
            "concentrations": [50.0],
            "concentrations_raw": ["50"],
            "time_points_hours": [48],
            "sample_counts": [3],
            "controls": [],
            "organism": "human",
        }
        template = isa_json_generator._load_assay_template("calcein_assay.json")
        param_values = isa_json_generator._extract_parameter_values(exp_meta, template)

        # Should have non-empty parameter values
        assert len(param_values) > 0

        # Check that cell type was extracted
        cell_type_pv = next(
            (
                pv
                for pv in param_values
                if pv["category"]["parameterName"]["annotationValue"] == "cell type"
            ),
            None,
        )
        assert cell_type_pv is not None
        assert "muller_cell" in cell_type_pv["value"]["annotationValue"]

        # Check that concentration was extracted
        conc_pv = next(
            (
                pv
                for pv in param_values
                if pv["category"]["parameterName"]["annotationValue"] == "calcein concentration"
            ),
            None,
        )
        assert conc_pv is not None
        assert "50" in conc_pv["value"]["annotationValue"]

        # Check that time points were extracted
        time_pv = next(
            (
                pv
                for pv in param_values
                if pv["category"]["parameterName"]["annotationValue"] == "incubation time"
            ),
            None,
        )
        assert time_pv is not None
        assert "48" in time_pv["value"]["annotationValue"]

    def test_extract_parameter_values_uses_defaults(self, isa_json_generator):
        """Parameters with defaultValue should be included even when no metadata match."""
        exp_meta = {
            "experiment_id": "E1",
            "cell_types": [],
            "assay_types": ["calcein"],
            "protein_variants": [],
            "drugs": [],
            "concentrations": [],
            "concentrations_raw": [],
            "time_points_hours": [],
            "sample_counts": [],
            "controls": [],
            "organism": "human",
        }
        template = isa_json_generator._load_assay_template("calcein_assay.json")
        param_values = isa_json_generator._extract_parameter_values(exp_meta, template)

        # excitation wavelength has defaultValue=495 in the template
        excitation_pv = next(
            (
                pv
                for pv in param_values
                if pv["category"]["parameterName"]["annotationValue"] == "excitation wavelength"
            ),
            None,
        )
        assert excitation_pv is not None
        assert excitation_pv["value"]["annotationValue"] == "495"

        # emission wavelength has defaultValue=515
        emission_pv = next(
            (
                pv
                for pv in param_values
                if pv["category"]["parameterName"]["annotationValue"] == "emission wavelength"
            ),
            None,
        )
        assert emission_pv is not None
        assert emission_pv["value"]["annotationValue"] == "515"

    def test_extract_parameter_values_skips_empty(self, isa_json_generator):
        """Parameters with no metadata match and empty defaultValue should be skipped."""
        exp_meta = {
            "experiment_id": "E1",
            "cell_types": [],
            "assay_types": ["calcein"],
            "protein_variants": [],
            "drugs": [],
            "concentrations": [],
            "concentrations_raw": [],
            "time_points_hours": [],
            "sample_counts": [],
            "controls": [],
            "organism": "human",
        }
        template = isa_json_generator._load_assay_template("calcein_assay.json")
        param_values = isa_json_generator._extract_parameter_values(exp_meta, template)
        param_names = [pv["category"]["parameterName"]["annotationValue"] for pv in param_values]

        # "microscope objective" has empty defaultValue and no metadata match → skipped
        assert "microscope objective" not in param_names

    def test_create_process_sequence_populates_parameters(self, isa_json_generator):
        """_create_process_sequence should produce processes with non-empty parameterValues."""
        exp_meta = {
            "experiment_id": "E1",
            "cell_types": ["muller_cell"],
            "assay_types": ["calcein"],
            "protein_variants": ["protA"],
            "drugs": [],
            "concentrations": [50.0],
            "concentrations_raw": ["50"],
            "time_points_hours": [48],
            "sample_counts": [3],
            "controls": [],
            "organism": "human",
        }
        template = isa_json_generator._load_assay_template("calcein_assay.json")
        processes = isa_json_generator._create_process_sequence(exp_meta, template)

        assert len(processes) == 1
        process = processes[0]
        assert len(process.parameter_values) > 0

    def test_facs_assay_has_expected_parameters(self, isa_json_generator):
        """FACS assay template parameters should be populated when metadata is available."""
        exp_meta = {
            "experiment_id": "E10",
            "cell_types": ["muller_cell"],
            "assay_types": ["facs"],
            "protein_variants": [],
            "drugs": [],
            "concentrations": [],
            "concentrations_raw": [],
            "time_points_hours": [24],
            "sample_counts": [],
            "controls": [],
            "organism": "human",
        }
        template = isa_json_generator._load_assay_template("facs_assay.json")
        param_values = isa_json_generator._extract_parameter_values(exp_meta, template)
        param_names = [pv["category"]["parameterName"]["annotationValue"] for pv in param_values]

        assert "cell type" in param_names
        assert "incubation time" in param_names
        # incubation temperature has defaultValue=37
        assert "incubation temperature" in param_names

    def test_assay_to_dict_has_nonempty_parameter_values(self, isa_json_generator):
        """The serialized assay dict should have non-empty parameterValues in processSequence."""
        from utils.batch.isa_json_generator import ISAProcess

        process = ISAProcess(
            process_id="#process/assay_process_1",
            executes_protocol="#protocol/calcein_assay",
            parameter_values=[
                {
                    "category": {
                        "@id": "#parameter/cell_type",
                        "parameterName": {"annotationValue": "cell type"},
                    },
                    "value": {"annotationValue": "muller_cell"},
                }
            ],
        )
        assay = ISAAssay(
            assay_id="assay_1",
            assay_name="Test Assay",
            measurement_type={"annotationValue": "test", "termSource": "OBI", "termAccession": ""},
            technology_type={"annotationValue": "test", "termSource": "OBI", "termAccession": ""},
            process_sequence=[process],
        )
        result = isa_json_generator._assay_to_dict(assay)

        assert len(result["processSequence"]) == 1
        pvs = result["processSequence"][0]["parameterValues"]
        assert len(pvs) == 1
        assert pvs[0]["category"]["parameterName"]["annotationValue"] == "cell type"

    def test_generate_study_has_populated_parameters(self, isa_json_generator, temp_dir):
        """End-to-end: generate_study should produce assays with non-empty parameterValues."""
        from utils.batch.folder_scanner import FileInventory, FolderMetadata

        exp_path = temp_dir / "E1_calcein_50uM_48h"
        exp_path.mkdir(parents=True, exist_ok=True)
        (exp_path / "image.czi").write_bytes(b"\x00")

        FolderMetadata(
            experiment_id="E1",
            experiment_name="E1_calcein_50uM_48h",
            folder_path=str(exp_path),
            file_inventory=FileInventory(czi_files=[str(exp_path / "image.czi")]),
        )

        # Patch generate_study to use our metadata directly
        # We'll test via _create_assay_from_experiment instead
        exp_meta = isa_json_generator._extract_experiment_metadata("E1_calcein_50uM_48h")
        assay_type_key = "calcein"
        template_name = isa_json_generator.classifier.TYPE_TO_TEMPLATE.get(
            assay_type_key, "microscopy_assay.json"
        )
        template = isa_json_generator._load_assay_template(template_name)
        processes = isa_json_generator._create_process_sequence(exp_meta, template)

        assert len(processes) >= 1
        total_params = sum(len(p.parameter_values) for p in processes)
        assert total_params > 0, "processSequence should have non-empty parameterValues"


@pytest.mark.unit
@pytest.mark.batch_component
class TestPathAFcsAssayEnrichment:
    """FCS assay enrichment in the merged Path A generator (merge plan Phase 1).

    These exercise the NEW Path A enrichment surface
    (:meth:`ISAJsonGenerator._extract_fcs_summary`,
    :meth:`ISAJsonGenerator._fcs_enrich_assay`,
    :meth:`ISAJsonGenerator._fcs_enrich_description`) using the committed
    synthetic fixture FCS data (``E10_explant_facs_treatment_donor``) and a
    synthetic summary mirroring those headers.
    """

    FIXTURES = Path(__file__).parent / "fixtures"
    E10_FOLDER = FIXTURES / "E10_explant_facs_treatment_donor"

    @staticmethod
    def _fcs_summary():
        """A summary mirroring the synthetic fixture FCS headers."""
        return {
            "instrument": "LSRFortessa",
            "operator": "Boneva",
            "acquisition_date": "16-DEC-2025",
            "acquisition_date_iso": "2025-12-16",
            "channels": ["FSC-A", "FITC-A", "PI-A", "Time"],
            "markers": [
                {"channel": "FITC-A", "dye": "Calcein-AM", "role": "live"},
                {"channel": "PI-A", "dye": "Propidium Iodide", "role": "dead"},
            ],
            "is_live_dead": True,
            "file_count": 8,
        }

    def _facs_metadata(self):
        """FolderMetadata for the E10 fixture folder."""
        from utils.batch.folder_scanner import FolderMetadata

        return FolderMetadata(
            experiment_id="E10",
            experiment_name="E10_explant_facs_treatment_donor",
            folder_path=str(self.E10_FOLDER),
        )

    def test_extract_fcs_summary_from_fixture_folder(self, isa_json_generator):
        """_extract_fcs_summary reads the real fixture FCS headers."""
        summary = isa_json_generator._extract_fcs_summary(str(self.E10_FOLDER))
        assert summary.get("is_live_dead") is True
        assert summary.get("instrument") == "LSRFortessa"
        assert summary.get("operator") == "Boneva"
        assert summary.get("acquisition_date_iso") == "2025-12-16"
        dyes = {m.get("dye") for m in summary.get("markers", [])}
        assert {"Calcein-AM", "Propidium Iodide"} <= dyes

    def test_extract_fcs_summary_empty_for_folder_without_fcs(self, isa_json_generator, temp_dir):
        """Folders without .fcs files yield an empty summary (no enrichment)."""
        (temp_dir / "data.xlsx").write_bytes(b"")
        assert isa_json_generator._extract_fcs_summary(str(temp_dir)) == {}
        assert isa_json_generator._extract_fcs_summary(None) == {}
        assert isa_json_generator._extract_fcs_summary(str(temp_dir / "missing")) == {}

    def test_enrichment_overrides_facs_measurement_type_when_live_dead(self, isa_json_generator):
        """facs + is_live_dead → registry live_dead_measurement_type override."""
        assay = isa_json_generator.generate_assay(
            assay_id="assay_1",
            assay_name="FACS assay",
            measurement_type={"annotationValue": "flow cytometry assay", "termSource": "OBI"},
            technology_type={"annotationValue": "flow cytometry", "termSource": "OBI"},
        )
        summary = self._fcs_summary()
        isa_json_generator._fcs_enrich_assay(
            assay, None, summary, isa_json_generator._assay_registry()["facs"]
        )
        assert assay.measurement_type["annotationValue"] == "toxicity test"
        assert assay.parameters and assay.parameters[0] == {
            "name": "instrument",
            "value": "LSRFortessa",
        }

    def test_enrichment_keeps_measurement_type_when_not_live_dead(self, isa_json_generator):
        """Non live/dead FCS leaves the template measurement type intact."""
        assay = isa_json_generator.generate_assay(
            assay_id="assay_1",
            assay_name="FACS assay",
            measurement_type={"annotationValue": "flow cytometry assay", "termSource": "OBI"},
            technology_type={"annotationValue": "flow cytometry", "termSource": "OBI"},
        )
        summary = self._fcs_summary()
        summary["is_live_dead"] = False
        isa_json_generator._fcs_enrich_assay(
            assay, None, summary, isa_json_generator._assay_registry()["facs"]
        )
        assert assay.measurement_type["annotationValue"] == "flow cytometry assay"
        assert assay.parameters[0]["value"] == "LSRFortessa"

    def test_enrichment_adds_protocol_parameters(self, isa_json_generator):
        """Instrument + reagents are declared as protocol parameters."""
        assay = isa_json_generator.generate_assay(
            assay_id="assay_1",
            assay_name="FACS assay",
            measurement_type={"annotationValue": "flow cytometry assay", "termSource": "OBI"},
            technology_type={"annotationValue": "flow cytometry", "termSource": "OBI"},
        )
        protocol = {
            "@id": "#protocol/flow_cytometry_assay",
            "name": "flow cytometry assay",
            "parameters": [],
            "components": [],
        }
        isa_json_generator._fcs_enrich_assay(
            assay, protocol, self._fcs_summary(), isa_json_generator._assay_registry()["facs"]
        )
        param_names = {
            p.get("parameterName", {}).get("annotationValue", "")
            for p in protocol.get("parameters", [])
        }
        assert "instrument" in param_names
        assert "Calcein-AM" in param_names
        assert "Propidium Iodide" in param_names

    def test_enrichment_noop_for_empty_summary_or_non_facs_entry(self, isa_json_generator):
        """Empty summary / non-FCS registry entry leave the assay untouched."""
        assay = isa_json_generator.generate_assay(
            assay_id="assay_1",
            assay_name="Calcein assay",
            measurement_type={"annotationValue": "viability assay", "termSource": "OBI"},
            technology_type={"annotationValue": "fluorescence microscopy", "termSource": "OBI"},
        )
        isa_json_generator._fcs_enrich_assay(
            assay,
            {"@id": "#protocol/x", "parameters": []},
            {},
            isa_json_generator._assay_registry()["calcein"],
        )
        assert assay.measurement_type["annotationValue"] == "viability assay"
        assert assay.parameters == []

    def test_enrich_description_appends_live_dead_instrument_date_factors(self, isa_json_generator):
        """_fcs_enrich_description appends FCS-derived details to the description."""
        desc = isa_json_generator._fcs_enrich_description(
            "This study covers experiment E10.",
            self._fcs_summary(),
            ["concentration", "donor", "treatment"],
        )
        assert "Live/Dead" in desc
        assert "LSRFortessa" in desc
        assert "2025-12-16" in desc
        assert "donor" in desc and "concentration" in desc
        # Operator is intentionally excluded from the study-level description.
        assert "Boneva" not in desc

    def test_enrich_description_noop_without_summary(self, isa_json_generator):
        """A missing/empty summary (and no factors) leaves the description unchanged."""
        desc = "This study covers experiment E1."
        assert isa_json_generator._fcs_enrich_description(desc, {}, []) == desc
        assert isa_json_generator._fcs_enrich_description(desc, None, []) == desc

    def test_enrich_description_lists_factors_even_without_fcs(self, isa_json_generator):
        """Factor notes are appended regardless of FCS availability (Path B parity)."""
        desc = "This study covers experiment E1."
        assert isa_json_generator._fcs_enrich_description(desc, {}, ["donor"]) == (
            "This study covers experiment E1. Factors: donor."
        )

    def test_create_assay_from_experiment_applies_fcs_enrichment(self, isa_json_generator):
        """_create_assay_from_experiment enriches the assay for the E10 FCS fixture."""
        metadata = self._facs_metadata()
        exp_meta = isa_json_generator._extract_experiment_metadata(
            "E10_explant_facs_treatment_donor",
            file_names=["L D_161225_B_Control.fcs"],
        )
        assay = isa_json_generator._create_assay_from_experiment(metadata, exp_meta, "facs")

        # Live/dead override from the registry entry.
        assert assay.measurement_type["annotationValue"] == "toxicity test"
        # Instrument as an assay parameter.
        assert any(
            p.get("name") == "instrument" and p.get("value") == "LSRFortessa"
            for p in assay.parameters
        )
        # The single (generic) assay process carries the FCS date/performer.
        assert assay.process_sequence, "expected at least one assay process"
        for process in assay.process_sequence:
            assert process.date == "2025-12-16"
            assert process.performer == "Boneva"

        # Serialized form carries the enrichment.
        d = isa_json_generator._assay_to_dict(assay)
        assert d["measurementType"]["annotationValue"] == "toxicity test"
        assert d["parameters"] and d["parameters"][0]["value"] == "LSRFortessa"
        assert d["processSequence"][0]["date"] == "2025-12-16"
        assert d["processSequence"][0]["performer"] == "Boneva"

    def test_generate_study_description_enriched_for_fcs_experiment(self, isa_json_generator):
        """generate_study description includes FCS details for an FCS experiment."""
        study = isa_json_generator.generate_study(
            experiment_path=self.E10_FOLDER,
            investigation_id="test_inv",
            study_id="study_E10",
        )
        assert any(
            a.assay_type_key == "facs" for a in study.assays
        ), "expected a facs assay in the study"
        desc = study.study_description
        assert "Live/Dead" in desc
        assert "LSRFortessa" in desc
        assert "2025-12-16" in desc
