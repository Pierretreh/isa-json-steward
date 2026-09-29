"""Tests for FCS-derived study enrichment.

These verify that the per-experiment FCS acquisition summary (instrument,
operator, date, channels, markers, is_live_dead) is correctly threaded into:
  * per-sample process date/performer
  * sample-collection process date
  * instrument as an assay parameter + protocol parameter
  * FACS measurementType specialized to "toxicity test" (-> "cell
    viability" on export) when Calcein+PI are detected
  * FACS protocol components populated with detected reagents
  * study description mentioning Live/Dead nature and instrument

The data-dependent test exercises the committed synthetic fixture FCS files
(``E10_explant_facs_treatment_donor``); all other tests use a synthetic
summary mirroring those headers.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.batch.experiment_processor import ExperimentProcessor  # noqa: E402
from utils.batch.metadata_extractor import MetadataExtractor  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
E10_FOLDER_NAME = "E10_explant_facs_treatment_donor"


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


def _new_processor(summary=None):
    p = ExperimentProcessor.__new__(ExperimentProcessor)
    p.investigation_id = "inv_001"
    p._fcs_summary = summary if summary is not None else _fcs_summary()
    return p


def _empty_study_data():
    return {"identifier": "study_E10", "assays": [], "protocols": [], "factors": []}


# ---------------------------------------------------------------------------
# Assay and protocol enrichment (_create_assays)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateAssaysEnrichment:
    def setup_method(self):
        self.processor = _new_processor()

    def test_live_dead_facets_measurement_type(self):
        study_data = _empty_study_data()
        assay_types = {"facs": ExperimentProcessor.ASSAY_TYPE_CONFIG["facs"]}
        assays = self.processor._create_assays(
            study_data, assay_types, ["#sample_1"], SimpleNamespace()
        )
        # measurementType set to "toxicity test" which the exporter maps to
        # the allowed "cell viability".
        assert assays[0]["measurementType"]["annotationValue"] == "toxicity test"

    def test_instrument_added_as_assay_parameter(self):
        study_data = _empty_study_data()
        assay_types = {"facs": ExperimentProcessor.ASSAY_TYPE_CONFIG["facs"]}
        assays = self.processor._create_assays(
            study_data, assay_types, ["#sample_1"], SimpleNamespace()
        )
        # instrument exposed as an assay parameter (-> parameterValue).
        params = assays[0].get("parameters", [])
        assert any(
            p.get("name") == "instrument" and p.get("value") == "LSRFortessa" for p in params
        )

    def test_facets_protocol_gets_instrument_and_reagent_parameters(self):
        study_data = _empty_study_data()
        assay_types = {"facs": ExperimentProcessor.ASSAY_TYPE_CONFIG["facs"]}
        self.processor._create_assays(study_data, assay_types, ["#sample_1"], SimpleNamespace())
        facs_protocol = next(
            p for p in study_data["protocols"] if p["name"].lower() == "assay facs assay"
        )
        # Parameters are declared in the ISA-valid parameterName shape.
        param_names = {
            (p.get("parameterName", {}) or {}).get("annotationValue", "")
            for p in facs_protocol.get("parameters", [])
        }
        # instrument declared as a protocol parameter.
        assert "instrument" in param_names
        # detected reagents declared as protocol parameters.
        assert "Calcein-AM" in param_names
        assert "Propidium Iodide" in param_names

    def test_non_live_dead_facs_keeps_default_measurement_type(self):
        summary = _fcs_summary()
        summary["is_live_dead"] = False
        processor = _new_processor(summary)
        study_data = _empty_study_data()
        assay_types = {"facs": ExperimentProcessor.ASSAY_TYPE_CONFIG["facs"]}
        assays = processor._create_assays(study_data, assay_types, ["#sample_1"], SimpleNamespace())
        # No override -> default "flow cytometry assay".
        assert assays[0]["measurementType"]["annotationValue"] == "flow cytometry assay"


# ---------------------------------------------------------------------------
# Per-sample process date/performer (_build_per_sample_processes)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPerSampleProcessDatePerformer:
    def test_processes_carry_fcs_date_and_operator(self):
        processor = _new_processor()
        study_data = _empty_study_data()
        assay = {
            "@id": "#assay_facs",
            "name": "FACS assay",
            "assay_type": "facs",
            "dataFiles": [
                {
                    "@id": "df_1",
                    "name": "L D_161225_B_Control.fcs",
                    "type": "Raw Data File",
                    "comments": [],
                }
            ],
        }
        samples = [
            {
                "@id": "#sample_Control",
                "name": "Explant - B Control",
                "factorValues": [
                    {"category": {"@id": "#factor/donor"}, "value": {"annotationValue": "B"}},
                    {
                        "category": {"@id": "#factor/treatment"},
                        "value": {"annotationValue": "Control"},
                    },
                ],
            }
        ]
        processor._build_per_sample_processes(study_data, [assay], samples, "study_E10")

        ps = assay["processSequence"]
        assert ps, "expected at least one per-sample process"
        assert ps[0]["date"] == "2025-12-16"
        assert ps[0]["performer"] == "Boneva"


# ---------------------------------------------------------------------------
# Sample-collection process date (_create_study_process_sequence)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSampleCollectionDate:
    def test_collection_date_uses_fcs_acquisition_date(self):
        processor = _new_processor()
        process_manager = MagicMock()
        study_data = _empty_study_data()
        processor._create_study_process_sequence(
            study_data, process_manager, "#source", ["#sample_1"]
        )
        added = process_manager.add_process.call_args[0][0]
        assert added["date"] == "2025-12-16"

    def test_collection_date_falls_back_to_today_without_fcs(self):
        processor = _new_processor(summary={})
        process_manager = MagicMock()
        study_data = _empty_study_data()
        processor._create_study_process_sequence(
            study_data, process_manager, "#source", ["#sample_1"]
        )
        added = process_manager.add_process.call_args[0][0]
        # Falls back to a YYYY-MM-DD today's date (non-empty).
        assert added["date"]
        assert len(added["date"]) == 10


# ---------------------------------------------------------------------------
# Study description (_update_study_description)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStudyDescriptionEnrichment:
    def test_description_mentions_live_dead_and_instrument(self):
        processor = _new_processor()
        study_data = {
            "identifier": "study_E10",
            "factors": [
                {"name": "donor"},
                {"name": "treatment"},
                {"name": "concentration"},
            ],
        }
        processor._update_study_description(
            study_data,
            SimpleNamespace(experiment_name="E10"),
            "Explant",
            {"annotationValue": "unknown"},
            ["#s1"],
        )
        desc = study_data["study_description"]
        assert "Live/Dead" in desc
        assert "LSRFortessa" in desc
        # Operator is intentionally excluded from study-level description
        # because it may only apply to the FACS assay, not other assays.
        assert "2025-12-16" in desc
        assert "donor" in desc and "concentration" in desc


# ---------------------------------------------------------------------------
# Fixture-driven: the real (synthetic) FCS summary drives the enrichment
# ---------------------------------------------------------------------------


@pytest.mark.batch_component
class TestFixtureFcsEnrichment:
    def test_fixture_summary_enriches_assay(self):
        folder = FIXTURES / E10_FOLDER_NAME
        assert folder.exists(), f"fixture folder not found: {folder}"

        summary = MetadataExtractor().extract_fcs_acquisition_summary(str(folder))
        assert summary.get("is_live_dead") is True
        assert summary.get("instrument") == "LSRFortessa"

        processor = _new_processor(summary)
        study_data = _empty_study_data()
        assay_types = {"facs": ExperimentProcessor.ASSAY_TYPE_CONFIG["facs"]}
        assays = processor._create_assays(study_data, assay_types, ["#sample_1"], SimpleNamespace())
        assert assays[0]["measurementType"]["annotationValue"] == "toxicity test"
