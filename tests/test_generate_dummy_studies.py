"""
Smoke tests for scripts/generate_dummy_studies.py (defect A fix).

The generator replaces the historical 193 *empty* dummy studies with a
small set of representative ones.  These tests assert the generated data
carries every field the GUI page loaders read (the required-fields spec
from reports/diag_evidence) and that output is deterministic per seed.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_generator():
    """Import scripts/generate_dummy_studies.py by path."""
    script = REPO_ROOT / "scripts" / "generate_dummy_studies.py"
    spec = importlib.util.spec_from_file_location("generate_dummy_studies", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator():
    return _load_generator()


@pytest.fixture(scope="module")
def generated(tmp_path_factory, generator):
    """Generate a small dataset once per module into a temp directory."""
    out_dir = tmp_path_factory.mktemp("inv_dummy")
    summary = generator.generate_dummy_studies(
        out_dir=str(out_dir), count=8, seed=42, investigation_id="inv_dummy"
    )
    return out_dir, summary


def _load_study(out_dir: Path, study_id: str) -> dict:
    with open(out_dir / "studies" / study_id / "study.json", "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.unit
class TestGeneratorSmoke:
    """Structural checks on the generated investigation."""

    def test_investigation_json_lists_all_studies(self, generated):
        out_dir, summary = generated
        inv = json.loads((out_dir / "inv_dummy.json").read_text(encoding="utf-8"))
        assert inv["identifier"] == "inv_dummy"
        assert len(inv["studies"]) == 8
        assert [s["identifier"] for s in inv["studies"]] == [
            s["identifier"] for s in summary["studies"]
        ]

    def test_study_files_exist(self, generated):
        out_dir, _ = generated
        for i in range(1, 9):
            assert (out_dir / "studies" / f"study_D{i:03d}" / "study.json").is_file()

    def test_populated_study_has_all_required_sections(self, generated):
        out_dir, _ = generated
        study = _load_study(out_dir, "study_D001")["studies"][0]

        materials = study["materials"]
        assert len(materials["sources"]) >= 1
        assert len(materials["samples"]) >= 2
        assert len(materials["otherMaterials"]) >= 1

        assert len(study["processSequence"]) >= 1
        assert len(study["protocols"]) >= 2
        assert len(study["assays"]) >= 1
        assert study["characteristicCategories"], "characteristicCategories must be declared"
        assert study["unitCategories"], "unitCategories must be declared"
        assert study["people"], "people[] must be populated"
        assert study["publications"], "publications[] must be populated"

    def test_materials_carry_required_fields(self, generated):
        out_dir, _ = generated
        study = _load_study(out_dir, "study_D001")["studies"][0]

        for section in ("sources", "samples", "otherMaterials"):
            for material in study["materials"][section]:
                assert material.get("@id"), f"{section} entry missing @id"
                assert material.get("name"), f"{section} entry missing name"
                assert material.get("materialType"), f"{section} entry missing materialType"
                assert "derivesFrom" in material, f"{section} entry missing derivesFrom"
                for char in material.get("characteristics", []):
                    assert char.get("category", {}).get(
                        "@id"
                    ), "characteristic missing category @id"
                    assert "value" in char, "characteristic missing value"

    def test_samples_carry_factor_values(self, generated):
        out_dir, _ = generated
        study = _load_study(out_dir, "study_D001")["studies"][0]

        factor_values = []
        for sample in study["materials"]["samples"]:
            factor_values.extend(sample.get("factorValues", []))
        category_ids = {fv["category"]["@id"] for fv in factor_values}
        assert "#factor/treatment" in category_ids
        assert "#factor/donor" in category_ids

        # >= 2 declared factors (treatment x donor)
        factor_ids = {f["@id"] for f in study["factors"]}
        assert {"#factor/treatment", "#factor/donor"} <= factor_ids

        # Factor characteristics use #characteristic_category/factor* categories
        char_ids = set()
        for sample in study["materials"]["samples"]:
            for char in sample.get("characteristics", []):
                char_ids.add(char["category"]["@id"])
        assert any(c.startswith("#characteristic_category/factor") for c in char_ids)

    def test_processes_carry_required_fields(self, generated):
        out_dir, _ = generated
        study = _load_study(out_dir, "study_D001")["studies"][0]

        protocol_ids = {p["@id"] for p in study["protocols"]}
        protocol_names = {p["name"] for p in study["protocols"]}
        for process in study["processSequence"]:
            assert process.get("name")
            assert process.get("status"), "process must carry a status"
            assert process.get("date")
            assert process.get("performer") is not None
            assert process.get("comments"), "process must carry comments"
            exec_proto = process.get("executesProtocol", {})
            assert isinstance(exec_proto, dict) and exec_proto.get("@id")
            # executesProtocol resolves against studies[0].protocols[]
            assert exec_proto["@id"] in protocol_ids or exec_proto.get("name") in protocol_names
            for ref in process.get("inputs", []) + process.get("outputs", []):
                assert isinstance(ref, dict) and ref.get("@id"), "inputs/outputs are @id refs"
            for pv in process.get("parameterValues", []):
                assert pv.get("category", {}).get("@id", "").startswith("#parameter/")

    def test_assay_types_covered_and_linked(self, generated):
        out_dir, _ = generated
        study = _load_study(out_dir, "study_D001")["studies"][0]

        assays = study["assays"]
        assert len(assays) == 3
        # calcein / facs / elisa covered (measurementType normalised by the
        # exporter, so check the assay @ids / names; the exporter derives
        # @ids from the assay name, matching case-insensitively)
        names = " ".join(a.get("@id", "") + a.get("filename", "") for a in assays).lower()
        for key in ("calcein", "facs", "elisa"):
            assert key in names, f"assay type {key} missing"

        for assay in assays:
            assert assay.get("materials", {}).get("samples"), "assay needs material samples"
            assert assay.get("processSequence"), "assay needs a processSequence"
            assert assay.get("dataFiles"), "assay needs dataFiles"

    def test_data_files_reference_real_files(self, generated):
        out_dir, _ = generated
        study_dir = out_dir / "studies" / "study_D001"
        study = _load_study(out_dir, "study_D001")["studies"][0]

        for assay in study["assays"]:
            for data_file in assay["dataFiles"]:
                path_comment = next(
                    (c for c in data_file.get("comments", []) if c.get("name") == "TraceDB"), None
                )
                assert path_comment, "dataFile must carry a TraceDB path comment"
                assert (
                    study_dir / path_comment["value"]
                ).is_file(), f"referenced file missing: {path_comment['value']}"
        # Both content directories are populated
        assert any((study_dir / "files" / "original").iterdir())
        assert any((study_dir / "files" / "converted").iterdir())

    def test_empty_studies_are_empty(self, generated):
        out_dir, _ = generated
        for study_id in ("study_D007", "study_D008"):
            study = _load_study(out_dir, study_id)["studies"][0]
            assert study["materials"]["sources"] == []
            assert study["materials"]["samples"] == []
            assert study["materials"]["otherMaterials"] == []
            assert study["processSequence"] == []
            assert study["assays"] == []

    def test_assay_only_study_hides_study_level_materials(self, generated):
        """study_D006 keeps its materials at assay level only (GUI fallback)."""
        out_dir, _ = generated
        study = _load_study(out_dir, "study_D006")["studies"][0]
        assert study["materials"]["samples"] == []
        assay_samples = study["assays"][0]["materials"]["samples"]
        assert assay_samples, "assay-level samples must exist"
        assert assay_samples[0].get("name"), "assay-level samples need names for the fallback"

    def test_deterministic_output(self, generator, tmp_path):
        """Same seed -> byte-identical study.json files."""
        out_a = tmp_path / "a"
        out_b = tmp_path / "b"
        generator.generate_dummy_studies(out_dir=str(out_a), count=8, seed=42)
        generator.generate_dummy_studies(out_dir=str(out_b), count=8, seed=42)
        for i in range(1, 9):
            study_id = f"study_D{i:03d}"
            text_a = (out_a / "studies" / study_id / "study.json").read_text(encoding="utf-8")
            text_b = (out_b / "studies" / study_id / "study.json").read_text(encoding="utf-8")
            assert text_a == text_b, f"{study_id} differs between runs of the same seed"

    def test_different_seed_changes_output(self, generator, tmp_path):
        out_a = tmp_path / "a"
        out_b = tmp_path / "b"
        generator.generate_dummy_studies(out_dir=str(out_a), count=8, seed=42)
        generator.generate_dummy_studies(out_dir=str(out_b), count=8, seed=7)
        assert (out_a / "studies" / "study_D001" / "study.json").read_text(encoding="utf-8") != (
            out_b / "studies" / "study_D001" / "study.json"
        ).read_text(encoding="utf-8")

    def test_cli_main_runs(self, generator, tmp_path, capsys):
        rc = generator.main(["--out", str(tmp_path / "cli_inv"), "--count", "4", "--seed", "1"])
        assert rc == 0
        out = capsys.readouterr().out
        summary = json.loads(out)
        assert summary["count"] == 4
        assert (tmp_path / "cli_inv" / "cli_inv.json").is_file()
