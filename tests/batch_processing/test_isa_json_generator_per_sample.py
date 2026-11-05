"""Tests for per-sample processes and file→sample mapping in Path A (merge plan Phase 2 / D1).

Covers the new :class:`~utils.batch.isa_json_generator.ISAJsonGenerator` surface
ported from ``ExperimentProcessor`` (which remains untouched until Phase 5):

* ``_map_file_to_sample`` — shared ``FactorRulesExtractor`` mapping,
* ``_ensure_sample_comment`` — ``derivedFromSample`` comment management,
* ``_assign_files_to_assays`` — subdirectory context first, then the
  registry's ``file_extensions``, then the ``default_assay`` fallback,
* ``_build_per_sample_processes`` — one process per sample with mapped files,
  an ``unassigned`` fallback process, template ``parameter_values`` and
  FCS ``date``/``performer`` on every process,
* the serialized ``study.json`` shape (organized output layout kept).

The committed synthetic fixture folder
``E10_explant_facs_treatment_donor`` (8 FCS files across two donors and six
treatment conditions) is the ideal case: with the synthetic test profile its
donor/treatment rule fires and produces exactly 8 samples, so every file maps
to its own sample and its own process.
"""

import json
from pathlib import Path

import pytest

from utils.batch.isa_json_generator import ISAJsonGenerator  # noqa: F401

FIXTURES = Path(__file__).parent / "fixtures"
E10_FOLDER = FIXTURES / "E10_explant_facs_treatment_donor"
E10_NAME = "E10_explant_facs_treatment_donor"


def _fcs_summary() -> dict:
    """A synthetic FCS acquisition summary (instrument/operator/date)."""
    return {
        "instrument": "LSRFortessa",
        "operator": "Boneva",
        "acquisition_date": "16-DEC-2025",
        "acquisition_date_iso": "2025-12-16",
        "is_live_dead": True,
    }


def _e10_folder_metadata():
    """FolderMetadata for the E10 fixture folder (with file inventory)."""
    from utils.batch.folder_scanner import FolderScanner

    scanner = FolderScanner(str(E10_FOLDER.parent))
    metadata = scanner._extract_folder_metadata(E10_FOLDER)
    assert metadata is not None
    assert metadata.file_inventory is not None
    return metadata


def _e10_exp_meta(generator: "ISAJsonGenerator") -> dict:
    file_names, _sub = generator._list_folder_contents(str(E10_FOLDER))
    return generator._extract_experiment_metadata(E10_NAME, file_names=file_names)


def _make_facs_assay(generator: "ISAJsonGenerator", data_files) -> object:
    assay = generator.generate_assay(
        assay_id="assay_x",
        assay_name="FACS assay",
        measurement_type={"annotationValue": "flow cytometry assay", "termSource": "OBI"},
        technology_type={"annotationValue": "flow cytometry", "termSource": "OBI"},
    )
    assay.assay_type_key = "facs"
    assay.data_files = list(data_files)
    return assay


def _sample(sample_id: str, factors: dict) -> dict:
    return {
        "@id": sample_id,
        "name": sample_id,
        "factorValues": [
            {"category": {"@id": f"#factor/{name}"}, "value": {"annotationValue": value}}
            for name, value in factors.items()
        ],
    }


@pytest.mark.unit
@pytest.mark.batch_component
class TestPathAMapFileToSample:
    """The Path A wrapper delegates to the shared FactorRulesExtractor mapper."""

    def test_maps_file_to_best_sample(self, isa_json_generator):
        samples = [
            _sample("#s_A", {"donor": "A", "treatment": "Control"}),
            _sample("#s_B", {"donor": "B", "treatment": "Control"}),
        ]
        assert isa_json_generator._map_file_to_sample("L D_161225_A_Control.fcs", samples) == "#s_A"
        assert isa_json_generator._map_file_to_sample("L D_161225_B_Control.fcs", samples) == "#s_B"

    def test_single_sample_fast_path(self, isa_json_generator):
        samples = [_sample("#s_only", {"donor": "A"})]
        assert isa_json_generator._map_file_to_sample("any_file.fcs", samples) == "#s_only"

    def test_no_samples_returns_none(self, isa_json_generator):
        assert isa_json_generator._map_file_to_sample("file.fcs", []) is None


@pytest.mark.unit
@pytest.mark.batch_component
class TestPathAEnsureSampleComment:
    """derivedFromSample comment attach/replace semantics."""

    def test_attaches_comment(self, isa_json_generator):
        data_file = {"@id": "df1", "name": "a.fcs", "comments": []}
        ISAJsonGenerator._ensure_sample_comment(data_file, "#sample/1")
        assert data_file["comments"] == [{"name": "derivedFromSample", "value": "#sample/1"}]

    def test_replaces_existing_comment(self, isa_json_generator):
        data_file = {
            "@id": "df1",
            "name": "a.fcs",
            "comments": [
                {"name": "derivedFromSample", "value": "#sample/old"},
                {"name": "Original file", "value": "true"},
            ],
        }
        ISAJsonGenerator._ensure_sample_comment(data_file, "#sample/new")
        derived = [c for c in data_file["comments"] if c.get("name") == "derivedFromSample"]
        assert len(derived) == 1
        assert derived[0]["value"] == "#sample/new"
        # Unrelated comments are preserved.
        assert {"name": "Original file", "value": "true"} in data_file["comments"]


@pytest.mark.unit
@pytest.mark.batch_component
class TestPathAAssignFilesToAssays:
    """Subdirectory context first, then registry extensions, then default assay."""

    def test_extension_based_assignment(self, isa_json_generator):
        result = isa_json_generator._assign_files_to_assays(
            ["run.fcs", "table.xlsx"], ["facs", "calcein"]
        )
        assert result["facs"] == ["run.fcs"]
        assert result["calcein"] == ["table.xlsx"]

    def test_subdirectory_context_wins_over_extension(self, isa_json_generator, temp_dir):
        # A .xlsx inside a "facs" directory is context-assigned to facs, not
        # extension-assigned to calcein.
        (temp_dir / "facs" / "table.xlsx").parent.mkdir(parents=True, exist_ok=True)
        (temp_dir / "facs" / "table.xlsx").write_bytes(b"")
        result = isa_json_generator._assign_files_to_assays(
            ["facs/table.xlsx"], ["facs", "calcein"], folder_root=temp_dir
        )
        assert result["facs"] == ["facs/table.xlsx"]
        assert result["calcein"] == []

    def test_default_assay_fallback_for_unknown_extension(self, isa_json_generator):
        result = isa_json_generator._assign_files_to_assays(["readme.txt"], ["facs", "calcein"])
        # Core default_assay is "calcein".
        assert result["calcein"] == ["readme.txt"]
        assert result["facs"] == []

    def test_default_assay_respects_requested_keys(self, isa_json_generator):
        # "calcein" not requested: fall back to the first requested key.
        result = isa_json_generator._assign_files_to_assays(["readme.txt"], ["facs"])
        assert result["facs"] == ["readme.txt"]

    def test_empty_inputs(self, isa_json_generator):
        assert isa_json_generator._assign_files_to_assays([], ["facs"]) == {"facs": []}
        assert isa_json_generator._assign_files_to_assays(["a.fcs"], []) == {}


@pytest.mark.unit
@pytest.mark.batch_component
class TestPathABuildPerSampleProcesses:
    """_build_per_sample_processes on the merged Path A generator."""

    def test_one_process_per_sample_with_mapped_files(self, isa_json_generator):
        samples = [
            _sample("#sample/1", {"donor": "A", "treatment": "Control"}),
            _sample("#sample/2", {"donor": "B", "treatment": "Control"}),
        ]
        assay = _make_facs_assay(
            isa_json_generator,
            [
                {"@id": "df1", "name": "L D_161225_A_Control.fcs", "comments": []},
                {"@id": "df2", "name": "L D_161225_B_Control.fcs", "comments": []},
            ],
        )
        processes = isa_json_generator._build_per_sample_processes(assay, samples, _fcs_summary())
        assert len(processes) == 2
        assert [p.inputs for p in processes] == [
            [{"@id": "#sample/1"}],
            [{"@id": "#sample/2"}],
        ]
        assert {f["@id"] for f in processes[0].outputs} == {"df1"}
        assert {f["@id"] for f in processes[1].outputs} == {"df2"}
        # FCS date/performer landed on every per-sample process.
        assert all(p.date == "2025-12-16" and p.performer == "Boneva" for p in processes)
        # The assay's process_sequence is the per-sample set.
        assert assay.process_sequence == processes

    def test_unassigned_files_get_fallback_process(self, isa_json_generator):
        samples = [
            _sample("#sample/1", {"treatment": "Control"}),
            _sample("#sample/2", {"treatment": "Isopropanol"}),
        ]
        assay = _make_facs_assay(
            isa_json_generator,
            [
                {"@id": "df1", "name": "Control_stain.fcs", "comments": []},
                {"@id": "df2", "name": "Isopropanol_dead.fcs", "comments": []},
                {"@id": "df3", "name": "zzz_totally_unrelated.wsp", "comments": []},
            ],
        )
        processes = isa_json_generator._build_per_sample_processes(assay, samples, {})
        by_id = {p.process_id: p for p in processes}
        assert set(by_id) == {
            "#process/facs_#sample/1",
            "#process/facs_#sample/2",
            "#process/facs_unassigned",
        }
        unassigned = by_id["#process/facs_unassigned"]
        assert unassigned.inputs == []
        assert {f["@id"] for f in unassigned.outputs} == {"df3"}
        assert {f["@id"] for f in by_id["#process/facs_#sample/1"].outputs} == {"df1"}
        assert {f["@id"] for f in by_id["#process/facs_#sample/2"].outputs} == {"df2"}
        # The unassigned file is flagged, the mapped files are attributed.
        comments = {f["name"]: f for f in assay.data_files}
        derived = [
            c
            for c in comments["zzz_totally_unrelated.wsp"]["comments"]
            if c.get("name") == "derivedFromSample"
        ]
        assert derived and derived[0]["value"] == "unassigned"
        derived1 = [
            c
            for c in comments["Control_stain.fcs"]["comments"]
            if c.get("name") == "derivedFromSample"
        ]
        assert derived1 and derived1[0]["value"] == "#sample/1"

    def test_no_samples_still_collects_unassigned(self, isa_json_generator):
        assay = _make_facs_assay(
            isa_json_generator,
            [{"@id": "df1", "name": "something.fcs", "comments": []}],
        )
        processes = isa_json_generator._build_per_sample_processes(assay, [], {})
        assert len(processes) == 1
        assert processes[0].process_id.endswith("_unassigned")
        assert processes[0].inputs == []

    def test_template_parameter_values_preserved_on_each_process(
        self, isa_json_generator, synthetic_profile
    ):
        exp_meta = _e10_exp_meta(isa_json_generator)
        assay = isa_json_generator._create_assay_from_experiment(
            _e10_folder_metadata(), exp_meta, "facs"
        )
        assert assay.process_sequence, "expected per-sample processes"
        first = assay.process_sequence[0].parameter_values
        assert len(first) >= 1, "template parameter_values must be preserved"
        assert all(
            p.parameter_values == first for p in assay.process_sequence
        ), "every per-sample process carries the same template parameter_values"

    def test_date_performer_empty_without_fcs(self, isa_json_generator):
        assay = _make_facs_assay(
            isa_json_generator,
            [{"@id": "df1", "name": "L D_161225_A_Control.fcs", "comments": []}],
        )
        processes = isa_json_generator._build_per_sample_processes(
            assay, [_sample("#sample/1", {"treatment": "Control"})], {}
        )
        assert all(p.date == "" and p.performer == "" for p in processes)


@pytest.mark.unit
@pytest.mark.batch_component
class TestPathAE10PerSampleProcesses:
    """The E10 donor×treatment fixture: 8 files → 8 samples → 8 processes."""

    def test_e10_eight_processes_eight_files(self, isa_json_generator, synthetic_profile):
        exp_meta = _e10_exp_meta(isa_json_generator)
        assay = isa_json_generator._create_assay_from_experiment(
            _e10_folder_metadata(), exp_meta, "facs"
        )
        assert len(assay.data_files) == 8
        processes = assay.process_sequence
        assert len(processes) == 8, "one process per sample (8 donor×treatment samples)"

        # Each process references exactly one sample and at least one file.
        input_ids = sorted(p.inputs[0]["@id"] for p in processes)
        assert len(set(input_ids)) == 8, "every process has a distinct sample input"
        all_outputs = [o["@id"] for p in processes for o in p.outputs]
        assert sorted(all_outputs) == sorted(f["@id"] for f in assay.data_files)

        # FCS date/performer from the Phase 1 summary on every process.
        assert all(p.date == "2025-12-16" for p in processes)
        assert all(p.performer == "Boneva" for p in processes)

        # Every data file carries a derivedFromSample comment.
        for f in assay.data_files:
            derived = [c for c in f.get("comments", []) if c.get("name") == "derivedFromSample"]
            assert derived, f"missing derivedFromSample comment on {f['name']}"
            assert derived[0]["value"].startswith("#sample/")

    def test_e10_generate_study_keeps_study_level_process(
        self, isa_json_generator, synthetic_profile
    ):
        study = isa_json_generator.generate_study(
            experiment_path=E10_FOLDER,
            investigation_id="test_inv",
            study_id="study_E10",
        )
        facs = next(a for a in study.assays if a.assay_type_key == "facs")
        assert len(facs.process_sequence) == 8

        # The study-level sample-collection process is kept (D1).
        assert study.process_sequence, "study-level process sequence must be kept"
        assert any(
            "sample_collection" in p.process_id or "sample collection" in p.executes_protocol
            for p in study.process_sequence
        )
        # Rule-derived samples (8 combinations) exist at study level.
        assert len(study.materials.get("samples", [])) == 8

    def test_e10_core_profile_single_sample_fallback(self, isa_json_generator):
        """Without the donor rule (core profile) all files map to the single sample."""
        study = isa_json_generator.generate_study(
            experiment_path=E10_FOLDER,
            investigation_id="test_inv",
            study_id="study_E10",
        )
        facs = next(a for a in study.assays if a.assay_type_key == "facs")
        assert len(facs.data_files) == 8
        assert len(facs.process_sequence) == 1
        assert facs.process_sequence[0].inputs == [{"@id": "#sample/1"}]
        assert len(facs.process_sequence[0].outputs) == 8


@pytest.mark.unit
@pytest.mark.batch_component
@pytest.mark.isa_validation
class TestPathASerializedStudyShape:
    """The saved study.json carries the per-sample process model (D1)."""

    def test_study_json_per_sample_shape(self, isa_json_generator, synthetic_profile, temp_dir):
        investigation = isa_json_generator.generate_investigation(
            experiments=[str(E10_FOLDER)],
            investigation_id="inv_p2",
            investigation_title="Phase 2 study",
            investigation_description="Per-sample process model",
        )
        isa_json_generator.save_investigation(investigation, str(temp_dir))

        inv_file = temp_dir / "inv_p2.json"
        assert inv_file.exists()
        with open(inv_file, "r", encoding="utf-8") as f:
            inv_data = json.load(f)
        assert inv_data["identifier"] == "inv_p2"
        assert len(inv_data["studies"]) == 1
        assert "assays" not in inv_data["studies"][0]  # lightweight study reference

        study_file = temp_dir / "studies" / "study_E10" / "study.json"
        assert study_file.exists()
        with open(study_file, "r", encoding="utf-8") as f:
            study = json.load(f)

        assert study["identifier"] == "study_E10"
        # Select the FACS assay via the protocol its per-sample processes execute.
        facs = next(
            a
            for a in study["assays"]
            if a.get("processSequence")
            and a["processSequence"][0]["executesProtocol"]["@id"] == "assay flow cytometry assay"
        )
        assert len(facs["dataFiles"]) == 8

        ps = facs["processSequence"]
        assert len(ps) == 8, "8 per-sample processes in the serialized study"
        for p in ps:
            assert p["inputs"] and p["inputs"][0]["@id"].startswith("#sample/")
            assert len(p["outputs"]) >= 1
            assert p["date"] == "2025-12-16"
            assert p["performer"] == "Boneva"
            assert len(p["parameterValues"]) >= 1

        # Study-level sample-collection process is serialized as well.
        assert study["processSequence"], "study-level processSequence must be present"

        # In-memory model: the study-level assay protocol carries the Phase 1
        # FCS enrichment (instrument + reagents).
        study_obj = investigation.studies[0]
        protocols = {p.get("name"): p for p in study_obj.protocols}
        assert "assay flow cytometry assay" in protocols
        param_names = {
            prm.get("parameterName", {}).get("annotationValue", "")
            for prm in protocols["assay flow cytometry assay"].get("parameters", [])
        }
        assert "instrument" in param_names
