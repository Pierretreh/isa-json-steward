"""
Tests for the layered validation engine (plans/validation-layers-plan.md §4).

Covers:

* the unified result model (``LayerResult`` / ``ValidationReport``);
* the ``schema`` layer (valid + violating investigations);
* the ``semantic`` layer (prefix/namespace checks, local rdflib lookup with a
  mini ontology cache, label mismatch, unresolved-term propagation);
* the ``template`` layer (parameter presence, unit accession match);
* the ``shacl`` layer (valid + violating shapes, missing-extra skip,
  missing shapes file skip);
* the ``owl`` layer (structural checks: circular subclassOf, valid ontology,
  missing-ontology skip);
* the OPTIONAL ``ols`` layer with a **mocked** HTTP client (no real network):
  warning-on-resolution, warning-on-still-missing, skip-on-network-error,
  skip-on-OLS-down, and the default-off contract;
* the ``--validation-layers`` CLI flag parsing and layer-set resolution
  (profile config defaults, OLS gating);
* the additive ``processing_report.json`` ``validation`` block;
* the profile ``validation`` config section (additive, safe defaults).

All tests are offline: OLS uses a patched ``urllib.request.urlopen`` and the
semantic/SHACL/OWL layers read local fixture files only.
"""

import json
import sys
import urllib.error
from pathlib import Path

import pytest

from utils.batch.validation_layers import (
    DEFAULT_LAYERS,
    LAYER_NAMES,
    LayerResult,
    OlsValidator,
    OwlConsistencyValidator,
    SemanticValidator,
    ShaclValidator,
    TemplateValidator,
    ValidationEngine,
    ValidationReport,
    parse_layer_names,
)

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_ROOT = REPO_ROOT / "domain-profile" / "templates" / "assay_templates"


# ----------------------------------------------------------------------
# Helpers / fixtures
# ----------------------------------------------------------------------


def _valid_investigation() -> dict:
    """A minimal structurally-valid investigation (spec-conformant)."""
    return {
        "investigation": {
            "@id": "https://example.org/investigations/test_inv",
            "identifier": "test_inv",
            "title": "Test Investigation",
            "description": "Test description",
            "submissionDate": "2024-01-01",
            "publicReleaseDate": "2025-01-01",
            "studies": [
                {
                    "@id": "https://example.org/investigations/test_inv/studies/E1",
                    "identifier": "E1",
                    "title": "Study 1",
                    "description": "Test study",
                    "submissionDate": "2024-01-01",
                    "materials": {"sources": [], "samples": [], "otherMaterials": []},
                    "protocols": [],
                    "assays": [
                        {
                            "identifier": "A1",
                            "measurementType": {
                                "annotationValue": "cell viability assay",
                                "termSource": "OBI",
                                "termAccession": "http://purl.obolibrary.org/obo/OBI_0003583",
                            },
                            "technologyType": {
                                "annotationValue": "plate reader assay",
                                "termSource": "OBI",
                                "termAccession": "http://purl.obolibrary.org/obo/OBI_0002437",
                            },
                            "dataFiles": [{"name": "calcein.csv", "type": "Derived Data File"}],
                            "materials": {"samples": [], "otherMaterials": []},
                            "processSequence": [
                                {
                                    "executesProtocol": {"@id": "#p1"},
                                    "parameterValues": [
                                        {
                                            "category": {
                                                "parameterName": {"annotationValue": "cell density"}
                                            },
                                            "value": {"annotationValue": "1e5 cells"},
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                    "processSequence": [],
                }
            ],
            "ontologySourceReferences": [
                {"name": "OBI", "file": "http://purl.obolibrary.org/obo/obi.owl"}
            ],
        }
    }


def _write_inv(directory: Path, data: dict, name: str = "inv.json") -> Path:
    path = Path(directory) / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def inv_path(temp_dir):
    """A spec-valid investigation file on disk."""
    return _write_inv(Path(temp_dir), _valid_investigation())


class FakeOlsResponse:
    """Minimal stand-in for ``urllib.request.urlopen(...)`` responses."""

    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_ols(monkeypatch):
    """Patch ``urllib.request.urlopen`` with a controllable OLS stub.

    Returns a state dict with ``calls`` (request URLs), ``found`` (set of
    accession tails reported as found) and error controls (``raise`` /
    ``status``), so tests can assert the skip-on-error and
    warning-on-resolution contracts without any network access.
    """
    import utils.batch.validation_layers as vl

    state = {"calls": [], "found": set(), "raise": None, "status": 200}

    def fake_urlopen(request, timeout=None):
        state["calls"].append(request.full_url)
        if state["raise"] is not None:
            raise state["raise"]
        if state["status"] != 200:
            raise urllib.error.HTTPError(
                request.full_url, state["status"], "OLS unavailable", None, None
            )
        query = request.full_url.split("q=", 1)[-1]
        tail = query.split("&", 1)[0]
        if tail in state["found"]:
            payload = {
                "response": {
                    "docs": [{"iri": f"http://purl.obolibrary.org/obo/{tail}", "obo_id": tail}]
                }
            }
        else:
            payload = {"response": {"docs": []}}
        return FakeOlsResponse(payload)

    monkeypatch.setattr(vl.urllib.request, "urlopen", fake_urlopen)
    return state


@pytest.fixture
def no_pyshacl(monkeypatch):
    """Simulate the absence of the ``ontology`` extra (pyshacl missing)."""
    monkeypatch.setitem(sys.modules, "pyshacl", None)


def _mini_obi_cache(cache_dir: Path) -> Path:
    """Create a tiny 'obi' ontology cache **directory** (two terms + labels).

    Returns the *directory* path so it can be passed as ``cache_dir``.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "obi.ttl").write_text(
        """
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix obo: <http://purl.obolibrary.org/obo/> .

        obo:OBI_0003583 a owl:Class ; rdfs:label "cell viability assay" .
        obo:OBI_0002437 a owl:Class ; rdfs:label "plate reader assay" .
        """,
        encoding="utf-8",
    )
    return cache_dir


# ----------------------------------------------------------------------
# Unified result model
# ----------------------------------------------------------------------


class TestResultModel:
    def test_layer_result_fields(self):
        result = LayerResult(
            layer="schema",
            validator="SchemaLayer",
            status="passed",
            blocking=True,
            is_valid=True,
        )
        assert result.errors == []
        assert result.warnings == []
        assert result.info == []
        assert result.duration == 0.0
        assert result.details == {}

    def test_layer_result_to_dict_shape(self):
        result = LayerResult(
            layer="owl",
            validator="OwlConsistencyValidator",
            status="passed",
            blocking=True,
            is_valid=True,
            info=["ok"],
            details={"triples": 3},
        )
        data = result.to_dict()
        assert data["layer"] == "owl"
        assert data["validator"] == "OwlConsistencyValidator"
        assert data["status"] == "passed"
        assert data["errors"] == []
        assert data["details"]["triples"] == 3
        assert isinstance(data["duration"], float)

    def test_report_aggregation(self):
        report = ValidationReport(
            passed=True,
            layers=[
                LayerResult(
                    layer="schema",
                    validator="SchemaLayer",
                    status="passed",
                    blocking=True,
                    is_valid=True,
                ),
                LayerResult(
                    layer="semantic",
                    validator="SemanticValidator",
                    status="passed",
                    blocking=False,
                    is_valid=True,
                    warnings=["w"],
                ),
                LayerResult(
                    layer="ols",
                    validator="OlsValidator",
                    status="skipped",
                    blocking=False,
                    is_valid=True,
                    info=["n/a"],
                ),
            ],
            skipped_layers=["ols"],
        )
        assert report.passed is True
        assert report.skipped_layers == ["ols"]
        flat = report.flat()
        assert flat["passed"] is True
        assert flat["warnings"] == ["w"]
        assert flat["errors"] == []
        assert flat["info"] == ["n/a"]

    def test_report_failed_when_blocking_layer_fails(self):
        report = ValidationReport(
            passed=False,
            layers=[
                LayerResult(
                    layer="shacl",
                    validator="ShaclValidator",
                    status="failed",
                    blocking=True,
                    is_valid=False,
                    errors=["violation"],
                )
            ],
        )
        assert report.passed is False
        flat = report.flat()
        assert flat["passed"] is False
        assert flat["errors"] == ["violation"]

    def test_report_to_dict_block(self):
        report = ValidationReport(passed=True, layers=[])
        data = report.to_dict()
        assert data["passed"] is True
        assert data["skipped"] is True  # no layers ran at all
        assert data["layers"] == []
        assert data["skipped_layers"] == []


# ----------------------------------------------------------------------
# Layer name parsing / defaults
# ----------------------------------------------------------------------


class TestLayerNames:
    def test_default_layers_exclude_ols(self):
        assert "ols" not in DEFAULT_LAYERS
        assert set(DEFAULT_LAYERS) == {
            "schema",
            "semantic",
            "data_file",
            "template",
            "shacl",
            "owl",
        }

    def test_layernames_order(self):
        assert list(LAYER_NAMES) == [
            "schema",
            "semantic",
            "data_file",
            "template",
            "shacl",
            "owl",
            "ols",
        ]

    def test_parse_layer_names(self):
        assert parse_layer_names("schema, ols") == ["schema", "ols"]
        assert parse_layer_names("schema,schema,semantic") == ["schema", "semantic"]

    def test_parse_layer_names_rejects_unknown(self):
        with pytest.raises(ValueError, match="unknown validation layer"):
            parse_layer_names("schema,bogus")


# ----------------------------------------------------------------------
# schema layer
# ----------------------------------------------------------------------


class TestSchemaLayer:
    def test_valid_investigation_passes(self, inv_path):
        engine = ValidationEngine(enabled_layers=["schema"])
        report = engine.run(str(inv_path))
        schema = next(layer for layer in report.layers if layer.layer == "schema")
        assert schema.status == "passed"
        assert schema.is_valid is True
        assert schema.blocking is True

    def test_missing_identifier_fails_blocking(self, temp_dir):
        data = _valid_investigation()
        del data["investigation"]["identifier"]
        path = _write_inv(Path(temp_dir), data)
        engine = ValidationEngine(enabled_layers=["schema"])
        report = engine.run(str(path))
        schema = next(layer for layer in report.layers if layer.layer == "schema")
        assert schema.status == "failed"
        assert schema.blocking is True
        assert any("identifier" in error.lower() for error in schema.errors)
        assert report.passed is False  # a blocking error blocks the export

    def test_isatools_spec_validation_reported(self, inv_path):
        try:
            import isatools  # noqa: F401
        except ImportError:
            pytest.skip("isatools not installed")
        engine = ValidationEngine(enabled_layers=["schema"])
        report = engine.run(str(inv_path))
        schema = next(layer for layer in report.layers if layer.layer == "schema")
        lines = schema.errors + schema.warnings + schema.info
        assert any("isatools" in line for line in lines)


# ----------------------------------------------------------------------
# semantic layer
# ----------------------------------------------------------------------


class TestSemanticLayer:
    def test_no_cache_prefix_checks_only(self, temp_dir):
        path = _write_inv(Path(temp_dir), _valid_investigation())
        validator = SemanticValidator(cache_dir=None)
        ctx = {"investigation": _valid_investigation()["investigation"]}
        result = validator.validate(str(path), ctx)
        assert result.status == "passed"
        assert result.blocking is False
        assert any("no cached ontologies" in line for line in result.info)

    def test_unknown_term_source_is_warning(self, temp_dir):
        data = _valid_investigation()
        data["investigation"]["studies"][0]["assays"][0]["measurementType"] = {
            "annotationValue": "x",
            "termSource": "BOGUS",
            "termAccession": "http://example.org/x",
        }
        path = _write_inv(Path(temp_dir), data)
        validator = SemanticValidator(cache_dir=None)
        result = validator.validate(str(path), {"investigation": data["investigation"]})
        assert result.status == "passed"  # semantic layer is non-blocking
        assert any("BOGUS" in warning for warning in result.warnings)

    def test_prefix_mismatch_is_warning(self, temp_dir):
        data = _valid_investigation()
        data["investigation"]["studies"][0]["assays"][0]["measurementType"][
            "termAccession"
        ] = "http://purl.obolibrary.org/obo/UO_0000196"  # UO prefix, OBI source
        path = _write_inv(Path(temp_dir), data)
        validator = SemanticValidator(cache_dir=None)
        result = validator.validate(str(path), {"investigation": data["investigation"]})
        assert any("does not match the" in warning for warning in result.warnings)

    def test_local_lookup_resolves_known_terms(self, temp_dir):
        cache_dir = _mini_obi_cache(Path(temp_dir) / "cache")
        path = _write_inv(Path(temp_dir), _valid_investigation())
        validator = SemanticValidator(cache_dir=str(cache_dir))
        result = validator.validate(
            str(path), {"investigation": _valid_investigation()["investigation"]}
        )
        assert result.status == "passed"
        assert result.warnings == []
        assert result.details["local_checks"] == 2
        assert result.details["unverified"] == []

    def test_unresolved_term_propagated_for_ols(self, temp_dir):
        """A term whose ontology is not cached is flagged for the optional
        OLS layer via ``details["unverified"]`` (no local cache for CHEBI)."""
        cache_dir = _mini_obi_cache(Path(temp_dir) / "cache")
        data = _valid_investigation()
        data["investigation"]["studies"][0]["assays"][0]["measurementType"] = {
            "annotationValue": "some chemical",
            "termSource": "ChEBI",
            "termAccession": "http://purl.obolibrary.org/obo/CHEBI_15928",
        }
        path = _write_inv(Path(temp_dir), data)
        validator = SemanticValidator(cache_dir=str(cache_dir))
        result = validator.validate(str(path), {"investigation": data["investigation"]})
        assert result.status == "passed"
        assert "http://purl.obolibrary.org/obo/CHEBI_15928" in result.details["unverified"]

    def test_label_mismatch_is_warning(self, temp_dir):
        cache_dir = _mini_obi_cache(Path(temp_dir) / "cache")
        data = _valid_investigation()
        data["investigation"]["studies"][0]["assays"][0]["measurementType"][
            "annotationValue"
        ] = "completely unrelated phrase"
        path = _write_inv(Path(temp_dir), data)
        validator = SemanticValidator(cache_dir=str(cache_dir))
        result = validator.validate(str(path), {"investigation": data["investigation"]})
        assert any("does not match any rdfs:label" in warning for warning in result.warnings)


# ----------------------------------------------------------------------
# template layer
# ----------------------------------------------------------------------


def _template_ctx(assay: dict) -> dict:
    return {
        "classifications": {"E1": {"template": "calcein_assay.json"}},
        "investigation": {"studies": [{"identifier": "E1", "assays": [assay]}]},
    }


class TestTemplateLayer:
    def test_parameter_presence_checked(self):
        assay = {
            "measurementType": {
                "annotationValue": "cell viability assay",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0003583",
            },
            "processSequence": [
                {
                    "parameterValues": [
                        {"category": {"parameterName": {"annotationValue": "cell density"}}}
                    ]
                }
            ],
        }
        validator = TemplateValidator(str(TEMPLATES_ROOT))
        result = validator.validate("inv.json", _template_ctx(assay))
        assert result.status == "passed"  # template layer is non-blocking
        assert result.blocking is False
        assert any("not present in assay" in warning for warning in result.warnings)

    def test_unit_accession_mismatch_is_warning(self):
        assay = {
            "measurementType": {
                "annotationValue": "cell viability assay",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0003583",
            },
            "processSequence": [
                {
                    "parameterValues": [
                        {
                            "category": {"parameterName": {"annotationValue": "cell density"}},
                            "value": {
                                "annotationValue": "1e5",
                                "unit": {"termAccession": "http://example.org/wrong-unit"},
                            },
                        }
                    ]
                }
            ],
        }
        validator = TemplateValidator(str(TEMPLATES_ROOT))
        result = validator.validate("inv.json", _template_ctx(assay))
        assert any("unit accession" in warning for warning in result.warnings)

    def test_unclassified_experiment_skipped(self):
        ctx = {
            "classifications": {},
            "investigation": {
                "studies": [{"identifier": "E1", "assays": [{"measurementType": {}}]}]
            },
        }
        validator = TemplateValidator(str(TEMPLATES_ROOT))
        result = validator.validate("inv.json", ctx)
        assert result.status == "passed"
        assert result.warnings == []

    def test_missing_templates_root_graceful(self):
        ctx = _template_ctx({"measurementType": {}})
        validator = TemplateValidator("/nonexistent/templates")
        result = validator.validate("inv.json", ctx)
        assert result.status == "passed"  # graceful info, never a hard error
        assert result.errors == []
        assert any("no assay templates found" in line for line in result.info)


# ----------------------------------------------------------------------
# shacl layer
# ----------------------------------------------------------------------


class TestShaclLayer:
    def test_valid_ontology_passes(self, inv_path):
        validator = ShaclValidator(
            shapes_file=str(FIXTURES / "shapes_min.ttl"),
            ontology_file=str(FIXTURES / "owl_assay_ok.ttl"),
        )
        result = validator.validate(str(inv_path), {})
        assert result.status == "passed"
        assert result.blocking is True
        assert result.details["conforms"] is True

    def test_violating_ontology_fails_blocking(self, inv_path):
        validator = ShaclValidator(
            shapes_file=str(FIXTURES / "shapes_min.ttl"),
            ontology_file=str(FIXTURES / "owl_assay_violation.ttl"),
        )
        result = validator.validate(str(inv_path), {})
        assert result.status == "failed"
        assert result.blocking is True
        assert len(result.errors) >= 1

    def test_missing_pyshacl_skips(self, inv_path, no_pyshacl):
        validator = ShaclValidator(
            shapes_file=str(FIXTURES / "shapes_min.ttl"),
            ontology_file=str(FIXTURES / "owl_assay_ok.ttl"),
        )
        result = validator.validate(str(inv_path), {})
        assert result.status == "skipped"
        assert any("pyshacl" in line for line in result.info)

    def test_missing_shapes_file_skips(self, inv_path):
        validator = ShaclValidator(
            shapes_file=str(FIXTURES / "does_not_exist.ttl"),
            ontology_file=str(FIXTURES / "owl_assay_ok.ttl"),
        )
        result = validator.validate(str(inv_path), {})
        assert result.status == "skipped"
        assert result.errors == []


# ----------------------------------------------------------------------
# owl layer
# ----------------------------------------------------------------------


class TestOwlLayer:
    def test_valid_ontology_passes(self, inv_path):
        validator = OwlConsistencyValidator(ontology_file=str(FIXTURES / "owl_assay_ok.ttl"))
        result = validator.validate(str(inv_path), {})
        assert result.status == "passed"
        assert result.errors == []
        assert result.details["triples"] > 0

    def test_circular_subclass_fails_blocking(self, inv_path):
        validator = OwlConsistencyValidator(ontology_file=str(FIXTURES / "owl_circular.ttl"))
        result = validator.validate(str(inv_path), {})
        assert result.status == "failed"
        assert result.blocking is True
        assert any("Circular subclassOf" in error for error in result.errors)

    def test_missing_ontology_skips(self, inv_path):
        validator = OwlConsistencyValidator(ontology_file=None)
        result = validator.validate(str(inv_path), {})
        assert result.status == "skipped"


# ----------------------------------------------------------------------
# OLS layer (mocked HTTP — no real network)
# ----------------------------------------------------------------------


class TestOlsLayer:
    @staticmethod
    def _ctx() -> dict:
        return {
            "investigation": _valid_investigation()["investigation"],
            "semantic_unverified": [
                "http://purl.obolibrary.org/obo/OBI_0003583",
                "http://purl.obolibrary.org/obo/OBI_0002437",
            ],
        }

    def test_default_off_is_skipped(self, inv_path):
        validator = OlsValidator(enabled=False)
        result = validator.validate(str(inv_path), self._ctx())
        assert result.status == "skipped"
        assert result.blocking is False
        assert any("OLS lookup disabled" in line for line in result.info)

    def test_resolution_is_warning_not_error(self, inv_path, fake_ols):
        fake_ols["found"] = {"OBI_0003583", "OBI_0002437"}
        validator = OlsValidator(enabled=True)
        result = validator.validate(str(inv_path), self._ctx())
        assert result.status == "passed"
        assert result.blocking is False
        assert any("resolved via OLS" in warning for warning in result.warnings)
        assert len(fake_ols["calls"]) == 2  # one query per unresolved term
        assert all(url.startswith("https://www.ebi.ac.uk/ols4/api/") for url in fake_ols["calls"])

    def test_still_missing_is_warning(self, inv_path, fake_ols):
        fake_ols["found"] = set()
        validator = OlsValidator(enabled=True)
        result = validator.validate(str(inv_path), self._ctx())
        assert result.status == "passed"
        assert any(
            "could not be verified locally or on OLS" in warning for warning in result.warnings
        )

    def test_network_error_skips_never_fails(self, inv_path, fake_ols):
        fake_ols["raise"] = OSError("no network")
        validator = OlsValidator(enabled=True)
        result = validator.validate(str(inv_path), self._ctx())
        assert result.status == "skipped"
        assert result.blocking is False
        assert result.errors == []
        assert any("OLS unavailable" in line for line in result.info)

    def test_ols_down_skips_never_fails(self, inv_path, fake_ols):
        fake_ols["status"] = 503
        validator = OlsValidator(enabled=True)
        result = validator.validate(str(inv_path), self._ctx())
        assert result.status == "skipped"
        assert result.errors == []

    def test_engine_gates_ols_opt_in(self, inv_path):
        """OLS runs only when explicitly enabled AND selected."""
        engine = ValidationEngine(enabled_layers=["semantic", "ols"], ols_enabled=False)
        report = engine.run(str(inv_path))
        ols = next(layer for layer in report.layers if layer.layer == "ols")
        assert ols.status == "skipped"
        assert any("OLS lookup disabled" in line for line in ols.info)


# ----------------------------------------------------------------------
# CLI flag parsing / layer-set resolution
# ----------------------------------------------------------------------


class TestCliAndResolution:
    def test_build_arg_parser_has_flags(self):
        from utils.batch.batch_processor import build_arg_parser

        parser = build_arg_parser()
        args = parser.parse_args(
            [
                "--data-root",
                ".",
                "--output-dir",
                ".",
                "--validation-layers",
                "schema,semantic,ols",
                "--enable-ols",
            ]
        )
        assert args.validation_layers == "schema,semantic,ols"
        assert args.enable_ols is True

    def test_resolve_enabled_layers_default_excludes_ols(self):
        from utils.batch.batch_processor import BatchProcessor

        assert BatchProcessor._resolve_enabled_layers(None, False, None) == list(DEFAULT_LAYERS)
        assert BatchProcessor._resolve_enabled_layers(None, True, None) == list(LAYER_NAMES)

    def test_resolve_enabled_layers_explicit_and_string(self):
        from utils.batch.batch_processor import BatchProcessor

        assert BatchProcessor._resolve_enabled_layers(["ols"], False, None) == ["ols"]
        assert BatchProcessor._resolve_enabled_layers("schema, ols", False, None) == [
            "schema",
            "ols",
        ]

    def test_resolve_enabled_layers_rejects_unknown(self):
        from utils.batch.batch_processor import BatchProcessor

        with pytest.raises(ValueError, match="unknown validation layer"):
            BatchProcessor._resolve_enabled_layers(["bogus"], False, None)

    def test_resolve_enabled_layers_profile_default(self):
        from utils.batch.batch_processor import BatchProcessor

        class FakeProfile:
            @staticmethod
            def get_validation_config():
                return {"layers": ["schema", "data_file"]}

        assert BatchProcessor._resolve_enabled_layers(None, False, FakeProfile()) == [
            "schema",
            "data_file",
        ]
        # enable_ols still adds the optional layer on top of the profile set.
        assert BatchProcessor._resolve_enabled_layers(None, True, FakeProfile()) == [
            "schema",
            "data_file",
            "ols",
        ]


# ----------------------------------------------------------------------
# Engine integration + report block
# ----------------------------------------------------------------------


class TestEngineIntegration:
    def test_engine_runs_selected_layers_in_order(self, inv_path):
        engine = ValidationEngine(enabled_layers=["schema", "semantic", "owl"])
        report = engine.run(str(inv_path))
        assert [layer.layer for layer in report.layers] == ["schema", "semantic", "owl"]
        assert report.to_dict()["layers"][0]["layer"] == "schema"

    def test_engine_unknown_layer_raises(self):
        with pytest.raises(ValueError, match="unknown validation layer"):
            ValidationEngine(enabled_layers=["schema", "bogus"])

    def test_report_block_serializable(self, inv_path):
        engine = ValidationEngine(enabled_layers=["schema", "semantic"])
        report = engine.run(str(inv_path))
        block = report.to_dict()
        text = json.dumps(block)  # must be JSON-serializable
        assert isinstance(text, str)
        assert block["passed"] in (True, False)
        assert block["skipped"] in (True, False)
        for layer in block["layers"]:
            assert layer["layer"] in LAYER_NAMES
            assert layer["status"] in ("passed", "failed", "skipped")

    def test_processing_report_contains_validation_block(self, tmp_path, inv_path):
        """The additive ``validation`` block lands in processing_report.json
        (mirrors ``BatchProcessor._save_processing_report``)."""
        from utils.batch.batch_processor import BatchProcessingResult

        engine = ValidationEngine(enabled_layers=["semantic"])
        report = engine.run(str(inv_path))
        result = BatchProcessingResult(
            total_experiments=1,
            successful_experiments=1,
            failed_experiments=0,
            total_files=1,
            converted_files=1,
            failed_conversions=0,
            validation_passed=report.passed,
            processing_time_seconds=1.0,
            validation_report=report.to_dict(),
        )
        report_dict = {
            "processing_date": "2026-09-27T00:00:00",
            "investigation_id": "test_inv",
            "summary": {"validation_passed": result.validation_passed},
            "errors": result.errors,
            "warnings": result.warnings,
            "info": result.info,
        }
        if result.validation_report is not None:
            report_dict["validation"] = result.validation_report
        out = tmp_path / "processing_report.json"
        out.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert "validation" in loaded
        assert loaded["validation"]["layers"][0]["layer"] == "semantic"
        assert loaded["summary"]["validation_passed"] in (True, False)


# ----------------------------------------------------------------------
# Profile config wiring
# ----------------------------------------------------------------------


class TestProfileConfig:
    def test_get_validation_config_defaults(self):
        from utils.config_loader import ProfileLoader

        loader = ProfileLoader(str(REPO_ROOT / "domain-profile"))
        config = loader.get_validation_config()
        assert config["layers"] == ["schema", "semantic", "data_file", "template", "shacl", "owl"]
        assert config["enable_ols"] is False
        assert config["semantic"]["cache_dir"] == "ontologies/cached"
        assert config["semantic"]["max_parse_mb"] == 50

    def test_get_validation_config_absent_section(self, tmp_path):
        """Profiles without a ``validation`` section get safe code defaults."""
        from utils.config_loader import ProfileLoader

        profile_dir = tmp_path / "profile"
        (profile_dir / "config").mkdir(parents=True)
        (profile_dir / "profile.json").write_text(
            json.dumps({"name": "x", "templates_dir": "t", "config_dir": "c"}),
            encoding="utf-8",
        )
        (profile_dir / "config" / "settings.json").write_text("{}", encoding="utf-8")
        loader = ProfileLoader(str(profile_dir))
        config = loader.get_validation_config()
        assert config["semantic"]["cache_dir"] == "ontologies/cached"
        assert config["semantic"]["max_parse_mb"] == 50
        assert config["enable_ols"] is False  # OLS stays off by default
