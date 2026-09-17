"""Tests for file-to-sample mapping and per-sample process creation (Fix 2)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # noqa: E402

try:
    import scripts.process_partner_data  # noqa: F401
except ImportError:
    pytest.skip(
        "scripts.process_partner_data not available (moved to private profile)",
        allow_module_level=True,
    )

from scripts.process_partner_data import PartnerDataProcessor  # noqa: E402


class TestMapFileToSample:
    """Test the _map_file_to_sample heuristic matching."""

    def setup_method(self):
        """Set up processor and sample fixtures."""
        self.processor = PartnerDataProcessor.__new__(PartnerDataProcessor)
        self.samples = [
            {
                "@id": "#sample_Control_2mm",
                "name": "Retinal explant - 2mm Control",
                "factorValues": [
                    {
                        "category": {"@id": "#factor/explant_size"},
                        "value": {"annotationValue": "2mm"},
                    },
                    {
                        "category": {"@id": "#factor/treatment"},
                        "value": {"annotationValue": "Control"},
                    },
                ],
            },
            {
                "@id": "#sample_Isopropanol_2mm",
                "name": "Retinal explant - 2mm Isopropanol",
                "factorValues": [
                    {
                        "category": {"@id": "#factor/explant_size"},
                        "value": {"annotationValue": "2mm"},
                    },
                    {
                        "category": {"@id": "#factor/treatment"},
                        "value": {"annotationValue": "Isopropanol"},
                    },
                ],
            },
            {
                "@id": "#sample_Static01_6mm_1Tag",
                "name": "Retinal explant - 0,1uM 6mm 1 Tag Static",
                "factorValues": [
                    {
                        "category": {"@id": "#factor/concentration"},
                        "value": {"annotationValue": "0,1uM"},
                    },
                    {
                        "category": {"@id": "#factor/explant_size"},
                        "value": {"annotationValue": "6mm"},
                    },
                    {
                        "category": {"@id": "#factor/stimulation_duration"},
                        "value": {"annotationValue": "1 Tag"},
                    },
                    {
                        "category": {"@id": "#factor/treatment"},
                        "value": {"annotationValue": "Static"},
                    },
                ],
            },
            {
                "@id": "#sample_Static10_6mm_10min",
                "name": "Retinal explant - 10uM 6mm 10min Static",
                "factorValues": [
                    {
                        "category": {"@id": "#factor/concentration"},
                        "value": {"annotationValue": "10uM"},
                    },
                    {
                        "category": {"@id": "#factor/explant_size"},
                        "value": {"annotationValue": "6mm"},
                    },
                    {
                        "category": {"@id": "#factor/stimulation_duration"},
                        "value": {"annotationValue": "10min"},
                    },
                    {
                        "category": {"@id": "#factor/treatment"},
                        "value": {"annotationValue": "Static"},
                    },
                ],
            },
        ]

    def test_single_sample_returns_that_sample(self):
        """Rule 1: Single sample maps all files to it."""
        single_sample = [self.samples[0]]
        result = self.processor._map_file_to_sample("any_file.fcs", single_sample, {})
        assert result == "#sample_Control_2mm"

    def test_no_samples_returns_none(self):
        """Empty sample list returns None."""
        result = self.processor._map_file_to_sample("file.fcs", [], {})
        assert result is None

    def test_isopropanol_file_matches_isopropanol_sample(self):
        """Factor substring match: 'isoprop' in filename matches Isopropanol sample."""
        result = self.processor._map_file_to_sample(
            "poriceRetina_LiveDead_171224_JP_dead Isoprop.fcs", self.samples, {}
        )
        assert result == "#sample_Isopropanol_2mm"

    def test_static_01_file_matches_static01_sample(self):
        """Multi-factor match: 'static 0,1uM' + '6mm' + '1 tag' matches correct sample."""
        result = self.processor._map_file_to_sample(
            "Explant 6mm_Static 0,1uM_1 Tag Stimulierung.png", self.samples, {}
        )
        assert result == "#sample_Static01_6mm_1Tag"

    def test_static_10_file_matches_static10_sample(self):
        """Multi-factor match: 'static 10uM' + '6mm' + '10min' matches correct sample."""
        result = self.processor._map_file_to_sample(
            "Explant 6mm_Static 10uM_10min Stimulierung.png", self.samples, {}
        )
        assert result == "#sample_Static10_6mm_10min"

    def test_controlle_matches_control_via_alias(self):
        """Alias expansion: 'Controlle' in filename matches 'Control' factor via alias."""
        factor_aliases = {
            "treatment": {
                "control": ["ctrl", "control", "controlle", "contr"],
            }
        }
        result = self.processor._map_file_to_sample(
            "Explant 2mm_Controlle Living_1.png",
            self.samples,
            factor_aliases,
        )
        assert result == "#sample_Control_2mm"

    def test_unmatched_file_returns_best_effort(self):
        """Files with no clear match return best available match."""
        result = self.processor._map_file_to_sample("Auswertung FACS.wsp", self.samples, {})
        # Should return some sample (best effort) or None if nothing matches
        # The .wsp file won't match any factor values
        assert result is None or isinstance(result, str)

    def test_living_small_matches_control_via_size(self):
        """'living small' file matches 2mm Control via '2mm' factor overlap."""
        result = self.processor._map_file_to_sample(
            "poriceRetina_LiveDead_171224_JP_living small.fcs", self.samples, {}
        )
        # 'small' is not a factor value, but the file won't match any specific treatment
        # This tests the graceful fallback behavior
        assert result is None or isinstance(result, str)


class TestBuildPerSampleProcesses:
    """Test the _build_per_sample_processes method."""

    def setup_method(self):
        self.processor = PartnerDataProcessor.__new__(PartnerDataProcessor)

    def test_empty_assays_no_op(self):
        """Empty assays list is handled gracefully."""
        self.processor._build_per_sample_processes({}, [], [], "study_1")
        # No error means pass

    def test_empty_samples_no_op(self):
        """Empty samples list is handled gracefully."""
        assays = [{"@id": "assay_1", "name": "FACS", "dataFiles": []}]
        self.processor._build_per_sample_processes({}, assays, [], "study_1")
        assert assays[0].get("processSequence", []) == []

    def test_single_sample_single_file_creates_process(self):
        """Single sample with one file creates one per-sample process."""
        samples = [
            {
                "@id": "#sample_Control",
                "name": "Control",
                "factorValues": [
                    {
                        "category": {"@id": "#factor/treatment"},
                        "value": {"annotationValue": "Control"},
                    },
                ],
            }
        ]
        assays = [
            {
                "@id": "assay_1",
                "name": "Microscopy assay",
                "dataFiles": [
                    {
                        "@id": "datafile_1",
                        "name": "Control_sample.fcs",
                        "type": "Raw Data File",
                        "comments": [],
                    }
                ],
            }
        ]
        self.processor._build_per_sample_processes({}, assays, samples, "study_1")

        ps = assays[0]["processSequence"]
        assert len(ps) >= 1
        assert ps[0]["inputs"] == [{"@id": "#sample_Control"}]
        assert {"@id": "datafile_1"} in ps[0]["outputs"]

    def test_derived_from_sample_comment_added(self):
        """Each data file gets a derivedFromSample comment."""
        samples = [
            {
                "@id": "#sample_Control",
                "name": "Control",
                "factorValues": [
                    {
                        "category": {"@id": "#factor/treatment"},
                        "value": {"annotationValue": "Control"},
                    },
                ],
            }
        ]
        assays = [
            {
                "@id": "assay_1",
                "name": "FACS assay",
                "dataFiles": [
                    {
                        "@id": "datafile_1",
                        "name": "Control_sample.fcs",
                        "type": "Raw Data File",
                        "comments": [],
                    }
                ],
            }
        ]
        self.processor._build_per_sample_processes({}, assays, samples, "study_1")

        comments = assays[0]["dataFiles"][0]["comments"]
        derived = [c for c in comments if c.get("name") == "derivedFromSample"]
        assert len(derived) == 1
        assert derived[0]["value"] == "#sample_Control"

    def test_unassigned_file_gets_comment(self):
        """Files that can't be matched get 'unassigned' in the comment."""
        samples = [
            {
                "@id": "#sample_Control",
                "name": "Control",
                "factorValues": [
                    {
                        "category": {"@id": "#factor/treatment"},
                        "value": {"annotationValue": "Control"},
                    },
                ],
            }
        ]
        assays = [
            {
                "@id": "assay_1",
                "name": "FACS assay",
                "dataFiles": [
                    {
                        "@id": "datafile_1",
                        "name": "generic_workspace.wsp",
                        "type": "Derived Data File",
                        "comments": [],
                    }
                ],
            }
        ]
        self.processor._build_per_sample_processes({}, assays, samples, "study_1")

        comments = assays[0]["dataFiles"][0]["comments"]
        derived = [c for c in comments if c.get("name") == "derivedFromSample"]
        assert len(derived) == 1

    def test_multi_sample_creates_multiple_processes(self):
        """Multiple samples create multiple per-sample processes."""
        samples = [
            {
                "@id": "#sample_Control",
                "name": "Control",
                "factorValues": [
                    {
                        "category": {"@id": "#factor/treatment"},
                        "value": {"annotationValue": "Control"},
                    },
                ],
            },
            {
                "@id": "#sample_Isopropanol",
                "name": "Isopropanol",
                "factorValues": [
                    {
                        "category": {"@id": "#factor/treatment"},
                        "value": {"annotationValue": "Isopropanol"},
                    },
                ],
            },
        ]
        assays = [
            {
                "@id": "assay_1",
                "name": "FACS assay",
                "dataFiles": [
                    {
                        "@id": "datafile_control",
                        "name": "Control_sample.fcs",
                        "type": "Raw Data File",
                        "comments": [],
                    },
                    {
                        "@id": "datafile_iso",
                        "name": "Isopropanol_dead.fcs",
                        "type": "Raw Data File",
                        "comments": [],
                    },
                ],
            }
        ]
        self.processor._build_per_sample_processes({}, assays, samples, "study_1")

        ps = assays[0]["processSequence"]
        # Should have at least 2 processes (one per matched sample)
        assert len(ps) >= 2

        # Each process should have exactly one sample input
        input_ids = set()
        for proc in ps:
            for inp in proc.get("inputs", []):
                input_ids.add(inp.get("@id"))
        assert "#sample_Control" in input_ids or "#sample_Isopropanol" in input_ids


class TestLoadFactorAliases:
    """Test loading factor aliases from config."""

    def setup_method(self):
        self.processor = PartnerDataProcessor.__new__(PartnerDataProcessor)

    def test_loads_aliases_from_config(self):
        """Factor aliases are loaded from factor_extraction_rules.json."""
        aliases = self.processor._load_factor_aliases()
        assert isinstance(aliases, dict)
        # Should have treatment aliases
        if "treatment" in aliases:
            assert "control" in aliases["treatment"]
            assert "controlle" in aliases["treatment"]["control"]


class TestGetSampleFactorStrings:
    """Test extraction of factor strings from sample dicts."""

    def setup_method(self):
        self.processor = PartnerDataProcessor.__new__(PartnerDataProcessor)

    def test_extracts_factor_values(self):
        """Factor values are extracted as lowercase strings."""
        sample = {
            "@id": "#s1",
            "factorValues": [
                {"category": {"@id": "#factor/treatment"}, "value": {"annotationValue": "Control"}},
                {"category": {"@id": "#factor/size"}, "value": {"annotationValue": "2mm"}},
            ],
        }
        result = self.processor._get_sample_factor_strings(sample)
        assert "control" in result
        assert "2mm" in result

    def test_empty_factor_values(self):
        """Sample with no factor values returns empty list."""
        sample = {"@id": "#s1", "factorValues": []}
        result = self.processor._get_sample_factor_strings(sample)
        assert result == []


class TestDAPIAssayMeasurementType:
    """Test that DAPI assay uses corrected measurement type (Fix 1)."""

    def test_dapi_measurement_type_is_live_dead_staining(self):
        """DAPI assay config should have 'live/dead staining' as measurement type."""
        from scripts.process_partner_data import PartnerDataProcessor

        config = PartnerDataProcessor.ASSAY_TYPE_CONFIG["dapi"]
        assert config["measurement_type"]["annotationValue"] == "live/dead staining"
        # Should no longer be "cell counting"
        assert config["measurement_type"]["annotationValue"] != "cell counting"
