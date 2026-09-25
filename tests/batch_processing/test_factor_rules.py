"""
Unit tests for the declarative factor-extraction engine
(:class:`utils.batch.factor_rules.FactorRulesExtractor`).

Covers rule gating (contains_all / contains_any), min_factors_to_match,
value_map, suffix, default_if_absent, scan_subfolders, no-match behaviour,
both rule schemas (full ``factors`` and legacy ``pattern``/``extract``),
and the delimited-token file-to-sample mapper.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # noqa: E402

from utils.batch.factor_rules import FactorRulesExtractor  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_core_rules() -> dict:
    path = PROJECT_ROOT / "config" / "factor_extraction_rules.json"
    with open(path, "r", encoding="utf-8") as f:
        data: dict = json.load(f)
    return data


def _extractor(rules: dict, aliases=None) -> FactorRulesExtractor:
    return FactorRulesExtractor(rules, aliases)


@pytest.fixture
def core_rules() -> dict:
    return _load_core_rules()


# ---------------------------------------------------------------------------
# Rule gating
# ---------------------------------------------------------------------------


class TestRuleGating:
    @pytest.mark.unit
    def test_contains_all_requires_every_token(self, core_rules):
        ex = _extractor(core_rules)
        # E11 rule requires "explant" AND "static"; name has only "calcein".
        result = ex.extract("X1_Calcein_Control 5uM", ["Calcein_Control_1.czi"])
        assert result is None

    @pytest.mark.unit
    def test_contains_any_requires_one_token(self, core_rules):
        ex = _extractor(core_rules)
        # E100 rule fires on pvv021 or cleav.
        result = ex.extract("E100_Explant_FACS_pVV021_n=2", ["L D_161225_A_pVV021.fcs"])
        assert result is not None

    @pytest.mark.unit
    def test_no_matching_rule_returns_none(self, core_rules):
        ex = _extractor(core_rules)
        result = ex.extract("Z99_unknown", ["file_1.czi"])
        assert result is None

    @pytest.mark.unit
    def test_empty_rules_returns_none(self):
        ex = _extractor({"rules": []})
        assert ex.extract("E1_Calcein", ["x.czi"]) is None

    @pytest.mark.unit
    def test_empty_rules_dict_returns_none(self):
        ex = _extractor({})
        assert ex.extract("E1_Calcein", ["x.czi"]) is None


# ---------------------------------------------------------------------------
# min_factors_to_match
# ---------------------------------------------------------------------------


class TestMinFactorsToMatch:
    @pytest.mark.unit
    def test_rule_below_threshold_does_not_fire(self, core_rules):
        ex = _extractor(core_rules)
        # E100 rule (gated on pvv021/cleav) needs >= 2 factors; only the
        # donor matches here (the name ends right after "_A_", so no
        # treatment tail exists). Name avoids "E#" so the legacy rule
        # does not fire either.
        result = ex.extract("Explant_FACS_pVV021", ["L D_161225_A_"])
        assert result is None

    @pytest.mark.unit
    def test_rule_at_threshold_fires(self, core_rules):
        ex = _extractor(core_rules)
        result = ex.extract(
            "E100_Explant_FACS_pVV021",
            ["L D_161225_A_pVV021 5uM (21).fcs"],
        )
        assert result is not None
        factor_values, _ = result
        assert "donor" in factor_values
        assert "concentration" in factor_values


# ---------------------------------------------------------------------------
# value_map / suffix
# ---------------------------------------------------------------------------


class TestValueMapAndSuffix:
    @pytest.mark.unit
    def test_value_map_applied(self, core_rules):
        ex = _extractor(core_rules)
        # E11 rule: treatment "Controlle" -> "Control".
        result = ex.extract(
            "E11_Explant_Static_DAPI",
            ["Explant 2mm_Controlle Living_1.png"],
        )
        assert result is not None
        factor_values, _ = result
        assert "Control" in factor_values.get("treatment", set())

    @pytest.mark.unit
    def test_suffix_appended(self, core_rules):
        ex = _extractor(core_rules)
        # E11 rule: concentration group "0,1" + suffix "uM".
        result = ex.extract(
            "E11_Explant_Static",
            ["Explant 6mm_Static 0,1uM_1 Tag.png"],
        )
        assert result is not None
        factor_values, _ = result
        assert "0,1uM" in factor_values.get("concentration", set())

    @pytest.mark.unit
    def test_custom_value_map(self):
        rules = {
            "rules": [
                {
                    "name": "r1",
                    "match_experiment_name": {"contains_all": ["x"]},
                    "min_factors_to_match": 1,
                    "factors": [
                        {
                            "name": "state",
                            "regex": "(mit|ohne) FBS",
                            "group": 1,
                            "value_map": {"mit": "+FBS", "ohne": "-FBS"},
                        }
                    ],
                }
            ]
        }
        ex = _extractor(rules)
        result = ex.extract("X_mitFBS", ["sample_mit FBS_1.czi"])
        assert result is not None
        factor_values, _ = result
        assert factor_values["state"] == {"+FBS"}


# ---------------------------------------------------------------------------
# default_if_absent
# ---------------------------------------------------------------------------


class TestDefaultIfAbsent:
    @pytest.mark.unit
    def test_default_added_when_factor_not_matched(self):
        rules = {
            "rules": [
                {
                    "name": "r1",
                    "match_experiment_name": {"contains_all": ["x"]},
                    "min_factors_to_match": 1,
                    "factors": [
                        {"name": "a", "regex": "(A1)"},
                        {
                            "name": "volume",
                            "regex": "(viel|wenig)",
                            "default_if_absent": "standard",
                        },
                    ],
                }
            ]
        }
        ex = _extractor(rules)
        result = ex.extract("X_test", ["A1_sample.czi"])
        assert result is not None
        factor_values, _ = result
        assert factor_values["a"] == {"A1"}
        assert factor_values["volume"] == {"standard"}

    @pytest.mark.unit
    def test_default_not_counted_toward_min_factors(self):
        rules = {
            "rules": [
                {
                    "name": "r1",
                    "match_experiment_name": {"contains_all": ["x"]},
                    "min_factors_to_match": 2,
                    "factors": [
                        {"name": "a", "regex": "(A1)"},
                        {
                            "name": "b",
                            "regex": "(NEVER_MATCHES)",
                            "default_if_absent": "dflt",
                        },
                    ],
                }
            ]
        }
        ex = _extractor(rules)
        # Only factor 'a' matches -> below min_factors_to_match=2 -> None.
        result = ex.extract("X_test", ["A1.czi"])
        assert result is None

    @pytest.mark.unit
    def test_default_does_not_create_combos(self):
        rules = {
            "rules": [
                {
                    "name": "r1",
                    "match_experiment_name": {"contains_all": ["x"]},
                    "min_factors_to_match": 1,
                    "factors": [
                        {"name": "a", "regex": "(A1)"},
                        {
                            "name": "b",
                            "regex": "(NEVER_MATCHES)",
                            "default_if_absent": "dflt",
                        },
                    ],
                }
            ]
        }
        ex = _extractor(rules)
        result = ex.extract("X_test", ["A1.czi"])
        assert result is not None
        _factor_values, combos = result
        for combo in combos:
            assert "b" not in combo


# ---------------------------------------------------------------------------
# scan_subfolders
# ---------------------------------------------------------------------------


class TestScanSubfolders:
    @pytest.mark.unit
    def test_subfolder_names_scanned(self):
        rules = {
            "rules": [
                {
                    "name": "r1",
                    "match_experiment_name": {"contains_all": ["hrmvec"]},
                    "min_factors_to_match": 2,
                    "scan_subfolders": True,
                    "factors": [
                        {"name": "treatment", "regex": "(MBP|YFP)"},
                        {"name": "concentration", "regex": "(\\d+uM)"},
                    ],
                }
            ]
        }
        ex = _extractor(rules)
        # File names alone don't match; subfolder names do.
        result = ex.extract(
            "E41_HRMVEC_MBP",
            ["img_001.czi"],
            subfolder_names=["MBP 10uM"],
        )
        assert result is not None
        factor_values, _ = result
        assert "MBP" in factor_values.get("treatment", set())
        assert "10uM" in factor_values.get("concentration", set())

    @pytest.mark.unit
    def test_subfolders_ignored_when_not_enabled(self):
        rules = {
            "rules": [
                {
                    "name": "r1",
                    "match_experiment_name": {"contains_all": ["x"]},
                    "min_factors_to_match": 1,
                    "scan_subfolders": False,
                    "factors": [{"name": "t", "regex": "(MBP)"}],
                }
            ]
        }
        ex = _extractor(rules)
        result = ex.extract("X", ["img.czi"], subfolder_names=["MBP"])
        assert result is None


# ---------------------------------------------------------------------------
# Combinations
# ---------------------------------------------------------------------------


class TestCombinations:
    @pytest.mark.unit
    def test_one_combo_per_matched_name(self, core_rules):
        ex = _extractor(core_rules)
        result = ex.extract(
            "E100_Explant_FACS_pVV021",
            [
                "L D_161225_A_pVV021 5uM.fcs",
                "L D_161225_B_pVV021 5uM.fcs",
            ],
        )
        assert result is not None
        _factor_values, combos = result
        assert len(combos) == 2
        donors = {c.get("donor") for c in combos}
        assert donors == {"A", "B"}

    @pytest.mark.unit
    def test_duplicate_combinations_deduplicated(self, core_rules):
        ex = _extractor(core_rules)
        # Two files, same donor+treatment, only the replicate number (n)
        # differs -> one unique combination after (n)-stripping.
        result = ex.extract(
            "E100_Explant_FACS_pVV021",
            [
                "L D_161225_A_pVV021 5uM (1).fcs",
                "L D_161225_A_pVV021 5uM (2).fcs",
            ],
        )
        assert result is not None
        factor_values, combos = result
        assert len(combos) == 1
        assert combos[0]["donor"] == "A"
        assert "pVV021 5uM" in factor_values.get("treatment", set())


# ---------------------------------------------------------------------------
# Legacy schema (pattern / extract)
# ---------------------------------------------------------------------------


class TestLegacySchema:
    @pytest.mark.unit
    def test_legacy_pattern_extract_int(self):
        rules = {
            "rules": [
                {
                    "pattern": "E(?P<experiment_number>\\d+)",
                    "extract": {"experiment_number": "int"},
                }
            ]
        }
        ex = _extractor(rules)
        result = ex.extract("E42_Calcein", ["a.czi"])
        assert result is not None
        factor_values, combos = result
        assert factor_values["experiment_number"] == {"42"}
        assert combos[0]["experiment_number"] == "42"

    @pytest.mark.unit
    def test_legacy_pattern_extract_str(self):
        rules = {
            "rules": [
                {
                    "pattern": "(?P<code>[A-Z]{2,4})_(?P<num>\\d+)",
                    "extract": {"code": "str", "num": "int"},
                }
            ]
        }
        ex = _extractor(rules)
        result = ex.extract("AB_123", [])
        assert result is not None
        factor_values, _ = result
        assert factor_values["code"] == {"AB"}
        assert factor_values["num"] == {"123"}

    @pytest.mark.unit
    def test_legacy_rule_in_core_config(self, core_rules):
        # The core config ships the legacy E# rule; the engine must still
        # honour it (for names that do not match any full-schema rule).
        ex = _extractor(core_rules)
        result = ex.extract("E7_unknown_type", ["file_1.txt"])
        assert result is not None
        factor_values, _ = result
        assert "experiment_number" in factor_values

    @pytest.mark.unit
    def test_invalid_pattern_skipped(self):
        rules = {"rules": [{"pattern": "([unclosed", "extract": {}}]}
        ex = _extractor(rules)
        assert ex.extract("E1", ["a.czi"]) is None


# ---------------------------------------------------------------------------
# Aliases
# ---------------------------------------------------------------------------


class TestAliases:
    @pytest.mark.unit
    def test_aliases_from_rules(self, core_rules):
        ex = _extractor(core_rules)
        assert "treatment" in ex.aliases
        assert "control" in ex.aliases["treatment"]
        assert "controlle" in ex.aliases["treatment"]["control"]

    @pytest.mark.unit
    def test_explicit_aliases_override(self, core_rules):
        custom = {"donor": {"d1": ["donor1"]}}
        ex = _extractor(core_rules, aliases=custom)
        assert ex.aliases == custom

    @pytest.mark.unit
    def test_alias_expansion_in_mapper(self, core_rules):
        ex = _extractor(core_rules)
        samples = [
            {
                "@id": "#s1",
                "factorValues": [
                    {
                        "category": {"@id": "#factor/treatment"},
                        "value": {"annotationValue": "Control"},
                    },
                ],
            },
            {
                "@id": "#s2",
                "factorValues": [
                    {
                        "category": {"@id": "#factor/treatment"},
                        "value": {"annotationValue": "Sorafenib"},
                    },
                ],
            },
        ]
        # "Controlle" is an alias of "control" in the core config.
        result = ex.map_file_to_sample("sample_Controlle_1.fcs", samples)
        assert result == "#s1"


# ---------------------------------------------------------------------------
# File-to-sample mapper
# ---------------------------------------------------------------------------


def _sample(sample_id: str, factors: dict) -> dict:
    return {
        "@id": sample_id,
        "name": sample_id,
        "factorValues": [
            {"category": {"@id": f"#factor/{name}"}, "value": {"annotationValue": value}}
            for name, value in factors.items()
        ],
    }


class TestMapper:
    @pytest.mark.unit
    def test_no_samples_returns_none(self, core_rules):
        ex = _extractor(core_rules)
        assert ex.map_file_to_sample("a.fcs", [], {}) is None

    @pytest.mark.unit
    def test_single_sample_shortcut(self, core_rules):
        ex = _extractor(core_rules)
        assert ex.map_file_to_sample("a.fcs", [_sample("#s", {})], {}) == "#s"

    @pytest.mark.unit
    def test_exact_beats_partial(self, core_rules):
        ex = _extractor(core_rules)
        samples = [
            _sample("#control", {"treatment": "Control"}),
            _sample("#control_erneut", {"treatment": "Control erneut"}),
        ]
        assert ex.map_file_to_sample("A_Control.fcs", samples, {}) == "#control"
        assert ex.map_file_to_sample("A_Control erneut.fcs", samples, {}) == "#control_erneut"

    @pytest.mark.unit
    def test_single_letter_token_never_inside_word(self, core_rules):
        ex = _extractor(core_rules)
        samples = [
            _sample("#s_A", {"donor": "A", "treatment": "cleav"}),
            _sample("#s_B", {"donor": "B", "treatment": "cleav"}),
        ]
        # 'b' must not match inside 'cleav'
        assert ex.map_file_to_sample("L D_B_cleav.fcs", samples, {}) == "#s_B"
        assert ex.map_file_to_sample("L D_A_cleav.fcs", samples, {}) == "#s_A"

    @pytest.mark.unit
    def test_substring_match(self, core_rules):
        ex = _extractor(core_rules)
        samples = [
            _sample("#iso", {"treatment": "Isopropanol"}),
            _sample("#sora", {"treatment": "Sorafenib"}),
        ]
        # "isoprop" is a substring of "isopropanol" (not of "sorafenib").
        assert ex.map_file_to_sample("dead Isoprop.fcs", samples, {}) == "#iso"

    @pytest.mark.unit
    def test_unmatched_returns_none(self, core_rules):
        ex = _extractor(core_rules)
        samples = [
            _sample("#a", {"treatment": "Control"}),
            _sample("#b", {"treatment": "Sorafenib"}),
        ]
        assert ex.map_file_to_sample("zzz_unknown_xyz.fcs", samples, {}) is None

    @pytest.mark.unit
    def test_empty_filename_returns_none(self, core_rules):
        ex = _extractor(core_rules)
        samples = [
            _sample("#a", {"treatment": "Control"}),
            _sample("#b", {"treatment": "Sorafenib"}),
        ]
        assert ex.map_file_to_sample("", samples, {}) is None


# ---------------------------------------------------------------------------
# Config file integration
# ---------------------------------------------------------------------------


class TestConfigIntegration:
    @pytest.mark.unit
    def test_core_config_parses(self, core_rules):
        assert isinstance(core_rules["rules"], list)
        assert len(core_rules["rules"]) >= 9
        assert "factor_aliases" in core_rules

    @pytest.mark.unit
    def test_profile_loader_getter(self, core_rules):
        from utils.config_loader import get_profile

        rules = get_profile().get_factor_extraction_rules()
        assert "rules" in rules
        assert len(rules["rules"]) >= 9
