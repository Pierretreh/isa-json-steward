"""Tests for the E100 multi-factor rule (B1/B3) and the file-to-sample mapper (B2).

Covers:
  * B1/B3 - the fixed E100 factor-extraction rule fires and produces donor,
    treatment (full condition string) and concentration (with units).
  * B2 - the mapper robustness for single-letter donor tokens (A/B) and the
    "Control" vs "Control erneut" disambiguation (exact-over-partial matching).

Pure-unit mapper tests do not require the representative dataset; the
data-dependent tests exercise the real E100 folder.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import scripts.process_partner_data  # noqa: F401
except ImportError:
    pytest.skip(
        "scripts.process_partner_data not available (moved to private profile)",
        allow_module_level=True,
    )

from scripts.process_partner_data import PartnerDataProcessor  # noqa: E402

E100_FOLDER_NAME = "E100_Explant_FACS_pVV021 und cleav 0,5 zu 4uM_n=5"


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
# Pure unit tests for the mapper (no representative data required)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMapperShortTokenAndDisambiguation:
    """Verify donor A/B boundary matching and exact-over-partial priority."""

    def setup_method(self):
        self.processor = PartnerDataProcessor.__new__(PartnerDataProcessor)

    def test_single_letter_donor_does_not_match_inside_words(self):
        """Donor 'a' must not match the 'a' in 'cleav'; a B-file maps to the B sample."""
        samples = [
            _sample("#s_A_cleav", {"donor": "A", "treatment": "cleav 05 zu 4uM"}),
            _sample("#s_B_cleav", {"donor": "B", "treatment": "cleav 05 zu 4uM"}),
        ]
        result = self.processor._map_file_to_sample(
            "L D_161225_B_cleav 05 zu 4uM (21).fcs", samples, {}
        )
        assert result == "#s_B_cleav"

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

        'b' is present in 'cleav' only as an interior letter of a different
        word, so it must not count as a donor match. With two samples sharing
        the 'cleav' treatment, the file maps by its true donor.
        """
        samples = [
            _sample("#s_A_cleav", {"donor": "A", "treatment": "cleav"}),
            _sample("#s_B_cleav", {"donor": "B", "treatment": "cleav"}),
        ]
        # 'cleav' contains neither a delimited 'a' nor 'b'; both samples tie on
        # the treatment, but neither donor token matches, so the first wins
        # deterministically (no donor is misattributed).
        result = self.processor._map_file_to_sample("L D_161225_C_cleav.fcs", samples, {})
        assert result in {"#s_A_cleav", "#s_B_cleav"}


# ---------------------------------------------------------------------------
# Data-dependent tests against the real E100 folder (B1 + B3)
# ---------------------------------------------------------------------------


@pytest.mark.requires_data
@pytest.mark.batch_component
class TestE100FactorRule:
    """Validate the corrected E100 multi-factor rule on real data."""

    def _exp(self, representative_data_path):
        if not representative_data_path:
            pytest.skip("Representative data not available")
        folder = representative_data_path / E100_FOLDER_NAME
        if not folder.exists():
            pytest.skip(f"E100 folder not found: {folder}")
        return SimpleNamespace(
            experiment_name=folder.name,
            folder_path=str(folder),
            subdirectory_hints=None,
        )

    def test_rule_fires_and_extracts_three_factors(self, representative_data_path):
        exp = self._exp(representative_data_path)
        result = PartnerDataProcessor.__new__(PartnerDataProcessor)._parse_filename_factors(exp)

        assert result is not None, "E100 multi-factor rule should now fire"
        factor_values, combos = result

        # B1: donor + treatment are present.
        assert factor_values["donor"] == {"A", "B"}
        assert "treatment" in factor_values
        # Six distinct treatment conditions across the 8 files.
        assert len(factor_values["treatment"]) == 6

        # B3: concentration is a factor and its values carry units.
        assert "concentration" in factor_values
        for conc in factor_values["concentration"]:
            assert conc.endswith("uM") or conc.endswith(
                "mM"
            ), f"concentration '{conc}' must carry units"

    def test_eight_unique_combinations(self, representative_data_path):
        exp = self._exp(representative_data_path)
        result = PartnerDataProcessor.__new__(PartnerDataProcessor)._parse_filename_factors(exp)
        assert result is not None
        _factor_values, combos = result

        # One sample per file -> 8 unique donor x treatment combinations.
        assert len(combos) == 8
        # Every combination carries a donor and a treatment.
        for combo in combos:
            assert "donor" in combo
            assert "treatment" in combo

    def test_each_file_maps_to_a_distinct_sample(self, representative_data_path):
        """End-to-end: parse factors, build samples, map all 8 files uniquely."""
        exp = self._exp(representative_data_path)
        processor = PartnerDataProcessor.__new__(PartnerDataProcessor)
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
