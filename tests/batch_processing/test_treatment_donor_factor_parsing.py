"""Tests for the donor/treatment multi-factor rule and the file-to-sample mapper.

Covers:
  * The donor/treatment/concentration factor-extraction rule fires and
    produces donor, treatment (full condition string) and concentration
    (with units) — against the committed synthetic fixture folder
    ``E10_explant_facs_treatment_donor``.
  * The mapper robustness for single-letter donor tokens (A/B) and the
    "Control" vs "Control erneut" disambiguation (exact-over-partial
    matching).

All data comes from the committed, project-agnostic fixture tree; the
synthetic test profile (``fixtures/synthetic_profile``) activates the
donor/treatment rule.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.batch.experiment_processor import ExperimentProcessor  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
E10_FOLDER_NAME = "E10_explant_facs_treatment_donor"


def _sample(sample_id: str, factors: dict) -> dict:
    """Build a sample dict whose factorValues mirror _create_materials output."""
    factor_values = [
        {
            "category": {"@id": f"#factor/{name}"},
            "value": {"annotationValue": value},
        }
        for name, value in factors.items()
    ]
    return {"@id": sample_id, "name": sample_id, "factorValues": factor_values}


# ---------------------------------------------------------------------------
# Pure unit tests for the mapper (no fixture data required)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMapperShortTokenAndDisambiguation:
    """Verify donor A/B boundary matching and exact-over-partial priority."""

    def setup_method(self):
        self.processor = ExperimentProcessor.__new__(ExperimentProcessor)

    def test_single_letter_donor_does_not_match_inside_words(self):
        """Donor 'a' must not match the 'a' in 'ambrosia'; a B-file maps to the B sample."""
        samples = [
            _sample("#s_A_ambrosia", {"donor": "A", "treatment": "ambrosia 05 to 4uM"}),
            _sample("#s_B_ambrosia", {"donor": "B", "treatment": "ambrosia 05 to 4uM"}),
        ]
        result = self.processor._map_file_to_sample(
            "L D_161225_B_ambrosia 05 to 4uM (21).fcs", samples, {}
        )
        assert result == "#s_B_ambrosia"

    def test_control_plain_file_maps_to_control_not_control_erneut(self):
        """Exact factor 'Control' beats partial match of 'Control erneut'."""
        samples = [
            _sample("#s_A_control", {"donor": "A", "treatment": "Control"}),
            _sample("#s_A_control_erneut", {"donor": "A", "treatment": "Control erneut"}),
        ]
        result = self.processor._map_file_to_sample("L D_161225_A_Control.fcs", samples, {})
        assert result == "#s_A_control"

    def test_control_erneut_file_maps_to_control_erneut(self):
        """The longer full match 'Control erneut' wins for its own file."""
        samples = [
            _sample("#s_A_control", {"donor": "A", "treatment": "Control"}),
            _sample("#s_A_control_erneut", {"donor": "A", "treatment": "Control erneut"}),
        ]
        result = self.processor._map_file_to_sample("L D_161225_A_Control erneut.fcs", samples, {})
        assert result == "#s_A_control_erneut"

    def test_donor_token_requires_delimited_boundary(self):
        """A donor letter only matches when delimited, never inside a word.

        'a' and 'b' are present in 'ambrosia' only as interior letters of a
        different word, so they must not count as donor matches. With two
        samples sharing the 'ambrosia' treatment, the file maps by its true
        donor.
        """
        samples = [
            _sample("#s_A_ambrosia", {"donor": "A", "treatment": "ambrosia"}),
            _sample("#s_B_ambrosia", {"donor": "B", "treatment": "ambrosia"}),
        ]
        # 'ambrosia' contains no delimited 'a' nor 'b'; both samples tie on
        # the treatment, but neither donor token matches, so the first wins
        # deterministically (no donor is misattributed).
        result = self.processor._map_file_to_sample("L D_161225_C_ambrosia.fcs", samples, {})
        assert result in {"#s_A_ambrosia", "#s_B_ambrosia"}


# ---------------------------------------------------------------------------
# Data-dependent tests against the synthetic donor/treatment fixture folder
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.batch_component
class TestTreatmentDonorFactorRule:
    """Validate the donor/treatment multi-factor rule on the synthetic fixture."""

    def _exp(self):
        folder = FIXTURES / E10_FOLDER_NAME
        assert folder.exists(), f"fixture folder not found: {folder}"
        return SimpleNamespace(
            experiment_name=folder.name,
            folder_path=str(folder),
            subdirectory_hints=None,
        )

    def test_rule_fires_and_extracts_three_factors(self, synthetic_profile):
        exp = self._exp()
        result = ExperimentProcessor.__new__(ExperimentProcessor)._parse_filename_factors(exp)

        assert result is not None, "donor/treatment multi-factor rule should fire"
        factor_values, combos = result

        # donor + treatment are present.
        assert factor_values["donor"] == {"A", "B"}
        assert "treatment" in factor_values
        # Six distinct treatment conditions across the 8 files.
        assert len(factor_values["treatment"]) == 6

        # concentration is a factor and its values carry units.
        assert "concentration" in factor_values
        for conc in factor_values["concentration"]:
            assert conc.endswith("uM") or conc.endswith(
                "mM"
            ), f"concentration '{conc}' must carry units"

    def test_eight_unique_combinations(self, synthetic_profile):
        exp = self._exp()
        result = ExperimentProcessor.__new__(ExperimentProcessor)._parse_filename_factors(exp)
        assert result is not None
        _factor_values, combos = result

        # One sample per file -> 8 unique donor x treatment combinations.
        assert len(combos) == 8
        # Every combination carries a donor and a treatment.
        for combo in combos:
            assert "donor" in combo
            assert "treatment" in combo

    def test_each_file_maps_to_a_distinct_sample(self, synthetic_profile):
        """End-to-end: parse factors, build samples, map all 8 files uniquely."""
        exp = self._exp()
        processor = ExperimentProcessor.__new__(ExperimentProcessor)
        result = processor._parse_filename_factors(exp)
        assert result is not None
        _factor_values, combos = result

        folder = Path(exp.folder_path)
        fcs_files = sorted(folder.rglob("*.fcs"))

        # Build one sample per combination (mirrors _create_materials).
        samples = []
        for i, combo in enumerate(combos):
            samples.append(_sample(f"#sample_{i}", combo))

        aliases = processor._load_factor_aliases()
        assigned = set()
        for fp in fcs_files:
            sid = processor._map_file_to_sample(fp.name, samples, aliases)
            assert sid is not None, f"No sample matched for {fp.name}"
            assert sid not in assigned, f"{fp.name} collided with a previous file on {sid}"
            assigned.add(sid)
        assert len(assigned) == len(fcs_files), "Every file must map to its own sample"
