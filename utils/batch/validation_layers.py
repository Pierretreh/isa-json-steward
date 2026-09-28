"""
Validation-layers engine for the batch pipeline (Stage 7).

This module makes the six validation layers claimed in the paper real and
executable, plus one **optional** network-dependent layer:

================================  ===========================================
Layer                             Validator (this module)
================================  ===========================================
``schema`` (Error, blocks)        :class:`SchemaLayer` — wraps
                                  ``ISAJsonValidator`` (``utils/batch/
                                  validator.py``) and adds data-type checks
                                  plus an offline isatools spec check.
``semantic`` (Warning)            :class:`SemanticValidator` — ontology-term
                                  verification via prefix/namespace
                                  resolution + local rdflib lookup against
                                  profile-cached ontologies (fully offline).
``data_file`` (Error blocks)      :class:`DataFileLayer` — wraps
                                  ``DataFileValidator``.
``template`` (Warning)            :class:`TemplateValidator` — generated
                                  assay vs. the profile assay template
                                  (parameters, unit accessions, required
                                  attachments).
``shacl`` (Error blocks)          :class:`ShaclValidator` — pyshacl (lazy
                                  import from the ``ontology`` extra) over
                                  the profile ontology RDF using the
                                  profile's shapes file.
``owl`` (Error blocks)            :class:`OwlConsistencyValidator` —
                                  rdflib-only structural check (subClassOf
                                  cycles, conflicting duplicate definitions,
                                  missing labels, orphans).  HermiT remains
                                  the offline/CI deep-reasoner gate; no JVM
                                  is ever launched from the pipeline.
``ols`` (Warning, **optional**,   :class:`OlsValidator` — resolves terms
default OFF, network)             that could not be verified locally against
                                  the EBI Ontology Lookup Service REST API.
                                  Skipped gracefully (never a hard failure)
                                  when the network/OLS is unavailable.
================================  ===========================================

Design constraints (see ``plans/validation-layers-plan.md``):

* The six core layers run **offline** — no validator in the default set may
  open a socket.  Only the user-enabled ``ols`` layer performs network I/O.
* A validator that raises is captured as a ``skipped`` layer with an info
  note — Stage 7 never crashes the pipeline.
* ``skipped`` layers never affect ``passed``; only *blocking* layers
  (schema, data_file, shacl, owl) can fail the run.
* The result model (:class:`LayerResult` / :class:`ValidationReport`) is
  additive and backward compatible: the flat
  ``errors``/``warnings``/``info`` lists and ``validation_passed`` on
  ``BatchProcessingResult`` keep their existing semantics.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "LAYER_NAMES",
    "DEFAULT_LAYERS",
    "OPTIONAL_LAYERS",
    "BLOCKING_LAYERS",
    "MAX_PARSE_SIZE_BYTES",
    "OLS_API_BASE",
    "LayerResult",
    "ValidationReport",
    "SchemaLayer",
    "SemanticValidator",
    "DataFileLayer",
    "TemplateValidator",
    "ShaclValidator",
    "OwlConsistencyValidator",
    "OlsValidator",
    "ValidationEngine",
    "parse_layer_names",
]

# ---------------------------------------------------------------------------
# Layer registry
# ---------------------------------------------------------------------------

#: All known layer names (canonical execution order, OLS last).
LAYER_NAMES: Tuple[str, ...] = (
    "schema",
    "semantic",
    "data_file",
    "template",
    "shacl",
    "owl",
    "ols",
)

#: Layers run by default (everything except the optional ``ols`` layer).
DEFAULT_LAYERS: Tuple[str, ...] = ("schema", "semantic", "data_file", "template", "shacl", "owl")

#: Layers that are opt-in (network-dependent) and never on by default.
OPTIONAL_LAYERS: Tuple[str, ...] = ("ols",)

#: Layers whose concrete violations block the run (``validation_passed=False``).
BLOCKING_LAYERS = frozenset({"schema", "data_file", "shacl", "owl"})

#: Per-file parse cap for cached ontologies (50 MB, ported from the
#: profile verification script).
MAX_PARSE_SIZE_BYTES = 50 * 1024 * 1024

# ---------------------------------------------------------------------------
# Ontology prefix / termSource machinery
# (ported from ``domain-profile/scripts/verify_ontology_refs.py`` — the
# reference implementation; the per-run validators here are the offline
# pipeline variant of that script)
# ---------------------------------------------------------------------------

#: Maps normalized ``termSource`` values to the expected URI prefix.
ONTOLOGY_PREFIX_MAP: Dict[str, Dict[str, str]] = {
    "obi": {
        "prefix": "http://purl.obolibrary.org/obo/OBI_",
        "description": "Ontology for Biomedical Investigations",
    },
    "uo": {
        "prefix": "http://purl.obolibrary.org/obo/UO_",
        "description": "Units of Measurement Ontology",
    },
    "chebi": {
        "prefix": "http://purl.obolibrary.org/obo/CHEBI_",
        "description": "Chemical Entities of Biological Interest",
    },
    "ncbitaxon": {
        "prefix": "http://purl.obolibrary.org/obo/NCBITaxon_",
        "description": "NCBI Taxonomy",
    },
    "pmdco": {
        "prefix": "https://w3id.org/pmd/co/",
        "description": "PMD Core Ontology",
    },
    "efo": {
        "prefix": "http://www.ebi.ac.uk/efo/",
        "description": "Experimental Factor Ontology",
    },
    "pato": {
        "prefix": "http://purl.obolibrary.org/obo/PATO_",
        "description": "Phenotypic Quality Ontology",
    },
    "cl": {
        "prefix": "http://purl.obolibrary.org/obo/CL_",
        "description": "Cell Ontology",
    },
    "uberon": {
        "prefix": "http://purl.obolibrary.org/obo/UBERON_",
        "description": "Uber-anatomy Ontology",
    },
    "go": {
        "prefix": "http://purl.obolibrary.org/obo/GO_",
        "description": "Gene Ontology",
    },
    "edam": {
        "prefix": "http://edamontology.org/",
        "description": "EDAM Ontology",
    },
}

#: Canonical form mapping (normalize variant spellings of termSource).
TERM_SOURCE_NORMALIZE: Dict[str, str] = {
    "chebi": "chebi",
    "chEBI": "chebi",
    "CHEBI": "chebi",
    "ChEBI": "chebi",
    "obi": "obi",
    "OBI": "obi",
    "uo": "uo",
    "UO": "uo",
    "ncbitaxon": "ncbitaxon",
    "NCBITaxon": "ncbitaxon",
    "pmdco": "pmdco",
    "PMDco": "pmdco",
    "PMD": "pmdco",
    "co": "pmdco",
    "efo": "efo",
    "EFO": "efo",
    "pato": "pato",
    "PATO": "pato",
    "cl": "cl",
    "CL": "cl",
    "uberon": "uberon",
    "UBERON": "uberon",
    "go": "go",
    "GO": "go",
    "edam": "edam",
    "EDAM": "edam",
}

#: Mapping from normalized termSource to the EBI OLS ontology ID (used by the
#: optional OLS layer).
OLS_ONTOLOGY_MAP: Dict[str, str] = {
    "obi": "obi",
    "uo": "uo",
    "chebi": "chebi",
    "ncbitaxon": "ncbitaxon",
    "pmdco": "pmdco",
    "pato": "pato",
    "efo": "efo",
    "edam": "edam",
    "cl": "cl",
    "uberon": "uberon",
    "go": "go",
}

#: EBI Ontology Lookup Service (OLS4) REST API base URL.
OLS_API_BASE = "https://www.ebi.ac.uk/ols4/api"

#: External namespace prefixes that are *not* the profile's own namespace —
#: used to scope OWL "missing label" warnings to profile-defined terms.
_EXTERNAL_TERM_PREFIXES: Tuple[str, ...] = (
    "http://purl.obolibrary.org/obo/",
    "http://www.ebi.ac.uk/efo/",
    "http://edamontology.org/",
    "https://w3id.org/pmd/co/",
    "http://www.w3.org/",
    "http://purl.org/",
)


def _normalize_term_source(term_source: str) -> Optional[str]:
    """Normalize a ``termSource`` string to canonical form (or ``None``)."""
    if not term_source:
        return None
    return TERM_SOURCE_NORMALIZE.get(term_source, term_source.lower())


def extract_ontology_refs(value: Any, path: str = "investigation") -> List[Dict[str, Any]]:
    """Recursively extract all ``termSource``/``termAccession`` pairs.

    Args:
        value: The JSON value to walk (usually the investigation dict).
        path: JSONPath-like string describing the current location.

    Returns:
        List of dicts with keys ``termSource``, ``termAccession``,
        ``annotationValue``, ``path``.
    """
    refs: List[Dict[str, Any]] = []

    def _walk(node: Any, where: str) -> None:
        if isinstance(node, dict):
            if node.get("termSource"):
                refs.append(
                    {
                        "termSource": node.get("termSource"),
                        "termAccession": node.get("termAccession"),
                        "annotationValue": node.get("annotationValue"),
                        "path": where,
                    }
                )
            for key, child in node.items():
                _walk(child, f"{where}.{key}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _walk(item, f"{where}[{i}]")

    _walk(value, path)
    return refs


def _uri_exists_in_graph(graph: Any, uri: str, ontology_prefix: str = "") -> bool:
    """Check whether *uri* appears in *graph* (subject, object, or trailing-
    slash variant); falls back to a namespace check for ontologies where
    rdflib's XML parser produces blank nodes."""
    from rdflib import URIRef

    uri_ref = URIRef(uri)
    if (uri_ref, None, None) in graph:
        return True
    if (None, None, uri_ref) in graph:
        return True
    if not uri.endswith("/") and (URIRef(uri + "/"), None, None) in graph:
        return True
    if uri.endswith("/") and (URIRef(uri.rstrip("/")), None, None) in graph:
        return True
    if ontology_prefix and uri.startswith(ontology_prefix) and len(graph) > 0:
        return True
    return False


def _label_matches(graph: Any, uri: str, label: str) -> bool:
    """Best-effort semantic label check: does *label* overlap any
    ``rdfs:label`` of the term at *uri*?  Inconclusive (no label) → True."""
    from rdflib import RDFS, URIRef

    labels = [str(term) for term in graph.objects(URIRef(uri), RDFS.label)]
    if not labels:
        return True
    needle = str(label).strip().lower()
    if not needle:
        return True
    if any(needle in lab.lower() or lab.lower() in needle for lab in labels):
        return True
    words = {w for w in re.split(r"\W+", needle) if len(w) > 2}
    if not words:
        return True
    for lab in labels:
        lab_words = {w for w in re.split(r"\W+", lab.lower()) if len(w) > 2}
        if lab_words and len(words & lab_words) >= max(1, len(words) // 2):
            return True
    return False


def _valid_iso_date(value: Any) -> bool:
    """True when *value* is a ``YYYY-MM-DD`` date string."""
    if value is None:
        return True
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def _format_for(path: Path) -> str:
    """Pick an rdflib parse format from the file suffix."""
    suffix = path.suffix.lower()
    if suffix in (".ttl",):
        return "turtle"
    if suffix in (".owl", ".rdf", ".xml"):
        return "xml"
    if suffix in (".nt",):
        return "nt"
    if suffix in (".json",):
        return "json-ld"
    return "turtle"


def _format_isatools_message(message: Any) -> str:
    """Render an isatools report entry (string or dict) as a readable line."""
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        parts = []
        if message.get("message"):
            parts.append(str(message["message"]))
        if message.get("supplemental"):
            parts.append(str(message["supplemental"]).splitlines()[0])
        if parts:
            return " — ".join(parts)
        return json.dumps(message)
    return str(message)


def parse_layer_names(value: str) -> List[str]:
    """Parse a comma-separated layer list, validating against LAYER_NAMES.

    Args:
        value: e.g. ``"schema,semantic,ols"``.

    Returns:
        De-duplicated list of layer names in canonical order.

    Raises:
        ValueError: when the list is empty or contains unknown layer names.
    """
    names = [part.strip() for part in value.split(",") if part.strip()]
    if not names:
        raise ValueError("at least one validation layer name is required")
    unknown = [name for name in names if name not in LAYER_NAMES]
    if unknown:
        raise ValueError(
            f"unknown validation layer(s): {', '.join(unknown)}; "
            f"valid layers: {', '.join(LAYER_NAMES)}"
        )
    ordered = [name for name in LAYER_NAMES if name in names]
    return ordered


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class LayerResult:
    """Outcome of a single validation layer (one row of the report)."""

    layer: str
    validator: str
    status: str  # "passed" | "failed" | "skipped"
    blocking: bool
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    duration: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serializable form (used by ``processing_report.json``)."""
        return {
            "layer": self.layer,
            "validator": self.validator,
            "status": self.status,
            "blocking": self.blocking,
            "is_valid": self.is_valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "info": list(self.info),
            "details": dict(self.details),
            "duration": round(float(self.duration), 3),
        }


@dataclass
class ValidationReport:
    """Aggregated outcome of all enabled validation layers."""

    passed: bool
    layers: List[LayerResult] = field(default_factory=list)
    skipped_layers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serializable form (the ``validation`` block of the report)."""
        return {
            "passed": self.passed,
            "skipped": len(self.layers) == 0,
            "skipped_layers": list(self.skipped_layers),
            "layers": [layer.to_dict() for layer in self.layers],
        }

    def flat(self) -> Dict[str, Any]:
        """Flat ``passed/errors/warnings/info`` view in execution order.

        This is the backward-compatible shape that feeds the legacy flat
        ``errors``/``warnings``/``info`` lists and ``validation_passed``.
        """
        errors: List[str] = []
        warnings: List[str] = []
        info: List[str] = []
        for layer in self.layers:
            errors.extend(layer.errors)
            warnings.extend(layer.warnings)
            info.extend(layer.info)
        return {"passed": self.passed, "errors": errors, "warnings": warnings, "info": info}


def _make_result(
    layer: str,
    validator: str,
    *,
    blocking: bool,
    status: Optional[str] = None,
    errors: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    info: Optional[List[str]] = None,
    details: Optional[Dict[str, Any]] = None,
) -> LayerResult:
    """Build a :class:`LayerResult`; ``status`` defaults from ``errors``."""
    if status is None:
        status = "failed" if errors else "passed"
    is_valid = status in ("passed", "skipped")
    return LayerResult(
        layer=layer,
        validator=validator,
        status=status,
        blocking=blocking,
        is_valid=is_valid,
        errors=list(errors or []),
        warnings=list(warnings or []),
        info=list(info or []),
        details=dict(details or {}),
    )


# ---------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------


class SchemaLayer:
    """``schema`` layer — ISA-JSON structure, required fields, data types.

    Wraps :class:`utils.batch.validator.ISAJsonValidator` (unchanged API),
    adds structural data-type checks, and runs the offline isatools spec
    validation where available.  Violations are **Errors** and block the
    run.
    """

    layer = "schema"
    name = "ISAJsonValidator"

    def __init__(self, isa_validator: Optional[Any] = None):
        if isa_validator is None:
            from utils.batch.validator import ISAJsonValidator

            isa_validator = ISAJsonValidator()
        self._isa = isa_validator

    def validate(self, investigation_path: str, ctx: Dict[str, Any]) -> LayerResult:
        """Validate the investigation file (see module docstring)."""
        result = self._isa.validate_investigation(investigation_path)
        errors: List[str] = list(result.errors)
        warnings: List[str] = list(result.warnings)
        info: List[str] = list(result.info)

        investigation = ctx.get("investigation")
        if isinstance(investigation, dict):
            errors.extend(self._check_types(investigation))

        # Offline isatools spec validation (core dependency); any failure
        # degrades to the hand-rolled checks above (info note, never a crash).
        self._run_isatools(investigation_path, info, errors, warnings)

        return _make_result(
            self.layer, self.name, blocking=True, errors=errors, warnings=warnings, info=info
        )

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _check_types(investigation: Dict[str, Any]) -> List[str]:
        """Structural data-type checks (wrong type → Error)."""
        errors: List[str] = []

        def _str_field(scope: str, container: Dict[str, Any], name: str) -> None:
            if name in container and not isinstance(container[name], str):
                errors.append(
                    f"{scope}: '{name}' must be a string, got {type(container[name]).__name__}"
                )

        for name in ("identifier", "title", "description", "submissionDate"):
            _str_field("investigation", investigation, name)

        studies = investigation.get("studies")
        if studies is not None and not isinstance(studies, list):
            errors.append(f"investigation: 'studies' must be a list, got {type(studies).__name__}")
            return errors

        for i, study in enumerate(studies or []):
            scope = f"study_{i}"
            if not isinstance(study, dict):
                errors.append(f"{scope}: study must be an object, got {type(study).__name__}")
                continue
            for name in ("identifier", "title", "description", "submissionDate"):
                _str_field(scope, study, name)

            if "materials" in study and not isinstance(study["materials"], dict):
                errors.append(
                    f"{scope}: 'materials' must be an object, got "
                    f"{type(study['materials']).__name__}"
                )
            for name in ("protocols", "processSequence"):
                if name in study and not isinstance(study[name], list):
                    errors.append(
                        f"{scope}: '{name}' must be a list, got {type(study[name]).__name__}"
                    )  # noqa: E501

            assays = study.get("assays")
            if assays is not None and not isinstance(assays, list):
                errors.append(f"{scope}: 'assays' must be a list, got {type(assays).__name__}")
                continue
            for j, assay in enumerate(assays or []):
                a_scope = f"{scope}_assay_{j}"
                if not isinstance(assay, dict):
                    errors.append(
                        f"{a_scope}: assay must be an object, " f"got {type(assay).__name__}"
                    )
                    continue
                if "materials" in assay and not isinstance(assay["materials"], dict):
                    errors.append(
                        f"{a_scope}: 'materials' must be an object, "
                        f"got {type(assay['materials']).__name__}"
                    )
                data_files = assay.get("dataFiles")
                if data_files is not None and not isinstance(data_files, list):
                    errors.append(
                        f"{a_scope}: 'dataFiles' must be a list, got {type(data_files).__name__}"
                    )  # noqa: E501
                    continue
                if isinstance(data_files, list):
                    for k, data_file in enumerate(data_files):
                        if not isinstance(data_file, dict) or not (
                            data_file.get("name") or data_file.get("filename")
                        ):
                            errors.append(
                                f"{a_scope}: dataFiles[{k}] must be an object "
                                "with 'name' or 'filename'"
                            )
        return errors

    @staticmethod
    def _run_isatools(
        investigation_path: str,
        info: List[str],
        errors: List[str],
        warnings: List[str],
    ) -> None:
        """Run the isatools spec check (offline).  Failures degrade to the
        hand-rolled checks with an info note — the pipeline never crashes
        because of isatools.

        ``isajson.validate`` expects an *unwrapped* ISA-JSON file; wrapped
        files (``{"investigation": {...}}``) are unwrapped to a temp copy
        first so both file layouts validate correctly."""
        try:
            from isatools import isajson
        except ImportError:
            info.append("isatools not installed — spec check skipped (hand-rolled checks only)")
            return

        try:
            with open(investigation_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            info.append(
                f"isatools spec check failed ({exc.__class__.__name__}: {exc}) — "
                "hand-rolled checks only"
            )
            return

        target = investigation_path
        cleanup = ""
        if isinstance(raw, dict) and isinstance(raw.get("investigation"), dict):
            import tempfile

            tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
            tmp.close()
            cleanup = tmp.name
            try:
                with open(tmp.name, "w", encoding="utf-8") as out:
                    json.dump(raw["investigation"], out, ensure_ascii=False)
                target = tmp.name
            except OSError:
                cleanup = ""
                target = investigation_path

        try:
            report = isajson.validate(target)
        except Exception as exc:  # noqa: BLE001 - fallback by design
            if cleanup:
                Path(cleanup).unlink(missing_ok=True)
            info.append(
                f"isatools spec check failed ({exc.__class__.__name__}: {exc}) — "
                "hand-rolled checks only"
            )
            return
        finally:
            if cleanup:
                Path(cleanup).unlink(missing_ok=True)

        if isinstance(report, dict):
            spec_errors = list(report.get("errors") or [])
            spec_warnings = list(report.get("warnings") or [])
        else:
            spec_errors = list(getattr(report, "errors", []) or [])
            spec_warnings = list(getattr(report, "warnings", []) or [])
        for message in spec_errors:
            errors.append(f"isatools: {_format_isatools_message(message)}")
        for message in spec_warnings:
            warnings.append(f"isatools: {_format_isatools_message(message)}")
        if not spec_errors:
            info.append("isatools spec validation: no errors reported")


class SemanticValidator:
    """``semantic`` layer — offline ontology-term verification.

    Two offline tiers (port of ``domain-profile/scripts/verify_ontology_refs.py``):

    1. **Prefix/namespace resolution** — every ``termSource`` must be a
       known ontology and its ``termAccession`` must carry the expected URI
       prefix (mismatch → Warning, non-blocking per Table 5).
    2. **Local rdflib lookup** — when the profile ships a cached-ontology
       directory (``ontologies/cached/`` by default), each accession is
       checked against the cached graph; unverified terms → Warning.
       Without a cache the tier is reported as skipped info and the layer
       still passes.

    Also checks date formats (``submissionDate``/``publicReleaseDate``/
    process ``date`` must be ``YYYY-MM-DD``) and label plausibility for
    locally verified terms.  All findings are **Warnings** (never blocking).
    """

    layer = "semantic"
    name = "SemanticValidator"

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        max_parse_bytes: int = MAX_PARSE_SIZE_BYTES,
    ):
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._max_parse_bytes = int(max_parse_bytes)
        self._loaded: Optional[Dict[str, Dict[str, Any]]] = None

    def validate(self, investigation_path: str, ctx: Dict[str, Any]) -> LayerResult:
        """Verify ontology references in the investigation (offline)."""
        investigation = ctx.get("investigation")
        investigation = investigation if isinstance(investigation, dict) else {}
        refs = extract_ontology_refs(investigation)
        warnings: List[str] = []
        info: List[str] = []
        details: Dict[str, Any] = {"references": len(refs)}

        loaded = self._load_cached_ontologies()
        local_checked = 0
        local_candidates: List[str] = []
        for ref in refs:
            term_source = str(ref.get("termSource") or "")
            term_accession = ref.get("termAccession")
            label = ref.get("annotationValue")
            where = str(ref.get("path") or "investigation")

            norm = _normalize_term_source(term_source)
            if norm is None or norm not in ONTOLOGY_PREFIX_MAP:
                warnings.append(f"unknown termSource '{term_source}' at {where}")
                continue
            if not term_accession:
                warnings.append(f"termSource '{term_source}' has no termAccession at {where}")
                continue

            expected_prefix = ONTOLOGY_PREFIX_MAP[norm]["prefix"]
            if not str(term_accession).startswith(expected_prefix):
                warnings.append(
                    f"termAccession '{term_accession}' does not match the "
                    f"'{norm}' prefix '{expected_prefix}' at {where}"
                )

            accession = str(term_accession)
            entry = (loaded or {}).get(norm)
            if entry is None:
                # No local graph for this ontology: keep the accession as an
                # OLS candidate (used only if the user enables the optional OLS layer).
                local_candidates.append(accession)
                continue
            local_checked += 1
            if not _uri_exists_in_graph(entry["graph"], accession, expected_prefix):
                warnings.append(
                    f"term '{accession}' could not be verified locally "
                    f"against the cached '{norm}' ontology"
                )
                local_candidates.append(accession)
            elif label and not _label_matches(entry["graph"], accession, str(label)):
                warnings.append(
                    f"label '{label}' does not match any rdfs:label of "
                    f"'{accession}' (possible semantic mismatch)"
                )

        # Every accession we could not verify locally (no cache for its
        # ontology, or a failed lookup) is a candidate for the optional OLS
        # layer; verified ones are not re-checked.
        details["unverified"] = local_candidates
        if loaded:
            details["local_checks"] = local_checked
        else:
            details["local_checks"] = "skipped (no cached ontologies)"
            info.append(
                "no cached ontologies — local term verification skipped " "(prefix checks ran)"
            )

        # Date formats (submissionDate / publicReleaseDate / process date).
        date_warnings = self._check_dates(investigation)
        warnings.extend(date_warnings)
        details["date_warnings"] = len(date_warnings)

        return _make_result(
            self.layer, self.name, blocking=False, warnings=warnings, info=info, details=details
        )

    # -- helpers ----------------------------------------------------------

    def _load_cached_ontologies(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """Load profile-cached ontologies (50 MB per-file cap), once."""
        if self._loaded is not None:
            return self._loaded or None
        if self._cache_dir is None or not Path(self._cache_dir).is_dir():
            self._loaded = {}
            return None

        loaded: Dict[str, Dict[str, Any]] = {}
        cache_dir = Path(self._cache_dir)
        for path in sorted(cache_dir.iterdir()):
            if not path.is_file():
                continue
            try:
                if path.stat().st_size > self._max_parse_bytes:
                    continue
            except OSError:
                continue
            graph = self._parse_file(path)
            if graph is None:
                continue
            norm = self._match_ontology(path, graph)
            if norm is not None and norm not in loaded:
                loaded[norm] = {
                    "graph": graph,
                    "prefix": ONTOLOGY_PREFIX_MAP[norm]["prefix"],
                    "file": path.name,
                }
        self._loaded = loaded
        return loaded or None

    @staticmethod
    def _parse_file(path: Path) -> Optional[Any]:
        try:
            from rdflib import Graph

            graph = Graph()
            graph.parse(str(path), format=_format_for(path))
            return graph
        except Exception:  # noqa: BLE001 - unreadable cache file → skip
            return None

    @staticmethod
    def _match_ontology(path: Path, graph: Any) -> Optional[str]:
        """Identify which known ontology a cached file holds (by the OBO
        accession prefix appearing in its term URIs or the filename)."""
        name = path.name.lower()
        for norm in ("chebi", "ncbitaxon", "obi", "uo", "pato", "cl", "uberon", "go"):
            accession = ONTOLOGY_PREFIX_MAP[norm]["prefix"].rsplit("/", 1)[-1]
            if name.startswith(accession.lower()):
                return norm
        try:
            sample = next(iter(graph))
            sample_str = str(sample)
        except StopIteration:
            return None
        for norm, meta in ONTOLOGY_PREFIX_MAP.items():
            prefix = meta["prefix"]
            tail = prefix.rsplit("/", 1)[-1]
            if tail and tail in sample_str:
                return norm
        return None

    @staticmethod
    def _check_dates(investigation: Dict[str, Any]) -> List[str]:
        warnings: List[str] = []
        for name in ("submissionDate", "publicReleaseDate"):
            if investigation.get(name) is not None and not _valid_iso_date(investigation.get(name)):
                warnings.append(
                    f"invalid date '{investigation.get(name)}' "
                    f"(expected YYYY-MM-DD) at investigation.{name}"
                )
        for i, study in enumerate(investigation.get("studies") or []):
            if not isinstance(study, dict):
                continue
            for name in ("submissionDate", "publicReleaseDate"):
                if study.get(name) is not None and not _valid_iso_date(study.get(name)):
                    warnings.append(
                        f"invalid date '{study.get(name)}' "
                        f"(expected YYYY-MM-DD) at study_{i}.{name}"
                    )
            for j, assay in enumerate(study.get("assays") or []):
                if not isinstance(assay, dict):
                    continue
                for k, process in enumerate(assay.get("processSequence") or []):
                    if isinstance(process, dict) and process.get("date") is not None:
                        if not _valid_iso_date(process.get("date")):
                            warnings.append(
                                f"invalid date '{process.get('date')}' (expected YYYY-MM-DD) "
                                f"at study_{i}_assay_{j}.processSequence[{k}].date"
                            )
        return warnings


class DataFileLayer:
    """``data_file`` layer — file existence, readability, checksum integrity.

    Wraps :class:`utils.batch.validator.DataFileValidator` (unchanged API).
    Missing files are **Errors** (blocking); readability/size issues are
    Warnings.
    """

    layer = "data_file"
    name = "DataFileValidator"

    def __init__(self, file_validator: Optional[Any] = None):
        if file_validator is None:
            from utils.batch.validator import DataFileValidator

            file_validator = DataFileValidator()
        self._files = file_validator

    def validate(self, investigation_path: str, ctx: Dict[str, Any]) -> LayerResult:
        """Validate all data files referenced by the investigation."""
        result, file_results = self._files.validate_files(investigation_path)
        details = {
            "files": len(file_results),
            "missing": len([f for f in file_results if not f.file_exists]),
        }
        return _make_result(
            self.layer,
            self.name,
            blocking=True,
            errors=list(result.errors),
            warnings=list(result.warnings),
            info=list(result.info),
            details=details,
        )


class TemplateValidator:
    """``template`` layer — generated assay vs. the profile assay template.

    Uses ``result.classifications[exp]["template"]`` (study id equals the
    experiment id) to bind each assay to its template from the active
    profile's ``templates/assay_templates`` directory and checks:

    * ``measurementType``/``technologyType`` accession agreement,
    * presence of every template parameter in the assay's
      ``parameterValues`` (case-insensitive),
    * unit ``termAccession`` agreement where the template declares a unit,
    * presence of every ``required`` ``expectedAttachments`` entry among the
      assay's data files (by allowed extension).

    All findings are **Warnings** (never blocking); an unknown template
    yields an info note and a skipped check for that assay.
    """

    layer = "template"
    name = "TemplateValidator"

    def __init__(self, templates_root: Optional[str] = None):
        self._root = Path(templates_root) if templates_root else None
        self._index: Optional[Dict[str, Dict[str, Any]]] = None

    def validate(self, investigation_path: str, ctx: Dict[str, Any]) -> LayerResult:
        """Check every classified assay against its template."""
        index = self._index_templates()
        classifications = ctx.get("classifications") or {}
        investigation = ctx.get("investigation")
        investigation = investigation if isinstance(investigation, dict) else {}
        studies = [s for s in (investigation.get("studies") or []) if isinstance(s, dict)]

        warnings: List[str] = []
        info: List[str] = []
        details: Dict[str, Any] = {"templates_checked": 0}

        if not index:
            info.append("no assay templates found — template compliance check skipped")
            return _make_result(
                self.layer,
                self.name,
                blocking=False,
                warnings=warnings,
                info=info,
                details=details,
            )

        for exp_id, meta in classifications.items():
            template_name = str(meta.get("template") or "")
            study = self._find_study(studies, exp_id)
            if study is None:
                info.append(f"{exp_id}: no study found — template check skipped")
                continue
            assay = self._first_assay(study)
            if assay is None:
                info.append(f"{exp_id}: no assay found — template check skipped")
                continue
            template = index.get(template_name) or index.get(Path(template_name).stem)
            if template is None:
                info.append(
                    f"{exp_id}: template '{template_name}' not in templates root — "
                    "template check skipped"
                )
                continue

            details["templates_checked"] += 1
            for field_name in ("measurementType", "technologyType"):
                expected = (template.get(field_name) or {}).get("termAccession")
                actual = (assay.get(field_name) or {}).get("termAccession")
                if expected and actual and str(expected) != str(actual):
                    warnings.append(
                        f"{exp_id}: {field_name} termAccession '{actual}' differs "
                        f"from template '{expected}'"
                    )

            present_names = {n.lower() for n in self._assay_parameter_names(assay)}
            for param in template.get("parameters") or []:
                pname = str(param.get("name") or "").strip()
                if not pname:
                    continue
                if pname.lower() not in present_names:
                    warnings.append(f"{exp_id}: template parameter '{pname}' not present in assay")
                    continue
                unit_accession = (param.get("unit") or {}).get("termAccession")
                if not unit_accession:
                    continue
                match = self._find_parameter_value(assay, pname)
                pv_unit = ((match or {}).get("value") or {}).get("unit") or {}
                pv_accession = pv_unit.get("termAccession")
                if pv_accession and str(pv_accession) != str(unit_accession):
                    warnings.append(
                        f"{exp_id}: unit accession '{pv_accession}' for '{pname}' differs "
                        f"from template '{unit_accession}'"
                    )

            data_file_names = self._assay_data_file_names(assay)
            for attachment in template.get("expectedAttachments") or []:
                if not attachment.get("required"):
                    continue
                allowed = [str(e).lower() for e in attachment.get("allowedExtensions") or []]
                if allowed and not any(
                    name.lower().endswith(ext) for name in data_file_names for ext in allowed
                ):
                    warnings.append(
                        f"{exp_id}: required attachment '{attachment.get('name', '?')}' "
                        f"(extensions {allowed}) not found among assay data files"
                    )
        return _make_result(
            self.layer, self.name, blocking=False, warnings=warnings, info=info, details=details
        )

    # -- helpers ----------------------------------------------------------

    def _index_templates(self) -> Dict[str, Dict[str, Any]]:
        """Build the ``{template_name: template_dict}`` index (lazy)."""
        if self._index is not None:
            return self._index
        index: Dict[str, Dict[str, Any]] = {}
        if self._root is not None and Path(self._root).is_dir():
            for path in sorted(Path(self._root).glob("*.json")):
                try:
                    with open(path, "r", encoding="utf-8") as handle:
                        data = json.load(handle)
                    if isinstance(data, dict):
                        index[path.stem] = data
                except (json.JSONDecodeError, OSError):
                    continue
        self._index = index
        return index

    @staticmethod
    def _find_study(studies: List[Dict[str, Any]], exp_id: str) -> Optional[Dict[str, Any]]:
        for study in studies:
            if str(study.get("identifier") or "") == exp_id:
                return study
        for study in studies:
            for assay in study.get("assays") or []:
                for comment in assay.get("comments") or []:
                    if (
                        comment.get("name") in ("Experiment ID", "Assay type")
                        and str(comment.get("value")) == exp_id
                    ):
                        return study
        return None

    @staticmethod
    def _first_assay(study: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for assay in study.get("assays") or []:
            if isinstance(assay, dict):
                return assay
        return None

    @staticmethod
    def _assay_parameter_names(assay: Dict[str, Any]) -> List[str]:
        names: List[str] = []
        for process in assay.get("processSequence") or []:
            if not isinstance(process, dict):
                continue
            for pv in process.get("parameterValues") or []:
                if not isinstance(pv, dict):
                    continue
                category = pv.get("category") or {}
                pname = (category.get("parameterName") or {}).get("annotationValue")
                if pname:
                    names.append(str(pname))
        return names

    @staticmethod
    def _find_parameter_value(assay: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
        for process in assay.get("processSequence") or []:
            if not isinstance(process, dict):
                continue
            for pv in process.get("parameterValues") or []:
                if not isinstance(pv, dict):
                    continue
                category = pv.get("category") or {}
                pname = (category.get("parameterName") or {}).get("annotationValue")
                if str(pname or "").strip().lower() == name.strip().lower():
                    return pv
        return None

    @staticmethod
    def _assay_data_file_names(assay: Dict[str, Any]) -> List[str]:
        names: List[str] = []
        for data_file in assay.get("dataFiles") or []:
            if isinstance(data_file, dict):
                name = data_file.get("name") or data_file.get("filename")
                if name:
                    names.append(str(name))
        return names


class ShaclValidator:
    """``shacl`` layer — SHACL shape validation of the profile ontology RDF.

    Runs :func:`pyshacl.validate` (lazy import from the ``ontology`` extra)
    over the profile ontology (``main_ttl`` preferred, fallback
    ``main_owl``) using the profile's shapes file.  Concrete violations are
    **Errors** (blocking); ``sh:Warning`` severities map to warnings.

    Graceful degradation — never a hard failure:

    * ``pyshacl`` not installed → ``skipped`` + actionable info;
    * shapes or ontology file absent/unparseable → ``skipped`` + info.
    """

    layer = "shacl"
    name = "ShaclValidator"

    def __init__(
        self,
        shapes_file: Optional[str] = None,
        ontology_file: Optional[str] = None,
    ):
        self._shapes_file = shapes_file
        self._ontology_file = ontology_file

    def validate(self, investigation_path: str, ctx: Dict[str, Any]) -> LayerResult:
        """Validate the profile ontology against the profile SHACL shapes."""
        try:
            import pyshacl  # noqa: F401
        except ImportError:
            return _make_result(
                self.layer,
                self.name,
                blocking=True,
                status="skipped",
                info=["pyshacl not installed — SHACL layer skipped (pip install .[ontology])"],
            )

        shapes_path = self._resolve_file(ctx, "shapes", self._shapes_file)
        if shapes_path is None or not Path(shapes_path).exists():
            return _make_result(
                self.layer,
                self.name,
                blocking=True,
                status="skipped",
                info=[f"SHACL shapes file not found ({shapes_path or 'no profile'}) — skipped"],
            )

        ontology_path = self._resolve_file(ctx, "main_ttl", self._ontology_file)
        if ontology_path is None or not Path(ontology_path).exists():
            ontology_path = self._resolve_file(ctx, "main_owl", None)
        if ontology_path is None or not Path(ontology_path).exists():
            return _make_result(
                self.layer,
                self.name,
                blocking=True,
                status="skipped",
                info=["profile ontology file not found — SHACL layer skipped"],
            )

        try:
            from rdflib import Graph

            shapes = Graph()
            shapes.parse(shapes_path, format=_format_for(Path(shapes_path)))
            data = Graph()
            data.parse(ontology_path, format=_format_for(Path(ontology_path)))
        except Exception as exc:  # noqa: BLE001 - broken profile artifact → skip
            return _make_result(
                self.layer,
                self.name,
                blocking=True,
                status="skipped",
                info=[f"could not parse SHACL inputs ({exc.__class__.__name__}: {exc}) — skipped"],
            )

        try:
            conforms, results_graph, _results_text = pyshacl.validate(
                data, shacl_graph=shapes, meta_shacl=True, advanced=True
            )
        except Exception as exc:  # noqa: BLE001 - pyshacl version drift → skip
            return _make_result(
                self.layer,
                self.name,
                blocking=True,
                status="skipped",
                info=[f"pyshacl validation failed ({exc.__class__.__name__}: {exc}) — skipped"],
            )

        errors, warnings, info = self._split_results(results_graph)
        details = {
            "conforms": bool(conforms),
            "results": len(errors) + len(warnings),
            "violations": len(errors),
            "warnings": len(warnings),
            "shapes_file": str(shapes_path),
            "ontology_file": str(ontology_path),
        }
        if not errors and not warnings:
            info.append("SHACL: all shapes satisfied (0 violations)")
        return _make_result(
            self.layer,
            self.name,
            blocking=True,
            errors=errors,
            warnings=warnings,
            info=info,
            details=details,
        )

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _resolve_file(ctx: Dict[str, Any], key: str, explicit: Optional[str]) -> Optional[str]:
        if explicit:
            return str(explicit)
        profile = ctx.get("profile")
        if profile is None:
            return None
        try:
            candidate = profile.get_ontology_filenames().get(key) or ""
        except Exception:  # noqa: BLE001 - defensive
            return None
        if not candidate:
            return None
        path = Path(candidate)
        if path.is_absolute() or path.exists():
            return str(path)
        try:
            root_relative = Path(profile.get_profile_root()) / candidate
        except Exception:  # noqa: BLE001 - defensive
            return None
        if root_relative.exists():
            return str(root_relative)
        return str(path)

    @staticmethod
    def _split_results(results_graph: Any) -> Tuple[List[str], List[str], List[str]]:
        """Map SHACL result severities to errors/warnings/info.

        Iterates the ``sh:ValidationResult`` nodes (``rg.subjects``) and
        reads the ``sh:resultSeverity`` each carries (modern pyshacl);
        falls back to the source shape's ``sh:severity`` for older
        pyshacl variants.  Note: iterating the graph directly yields
        *triples* in rdflib >= 6, so it must not be used to find nodes.
        """
        from rdflib import RDF, Namespace

        sh = Namespace("http://www.w3.org/ns/shacl#")
        errors: List[str] = []
        warnings: List[str] = []
        info: List[str] = []
        for node in results_graph.subjects(RDF.type, sh.ValidationResult):
            messages = list(results_graph.objects(node, sh.resultMessage))
            text = str(messages[0]) if messages else "SHACL constraint violated"
            severity_terms = [str(term) for term in results_graph.objects(node, sh.resultSeverity)]
            if not severity_terms:
                source_shape = next(results_graph.objects(node, sh.sourceShape), None)
                if source_shape is not None:
                    severity_terms = [
                        str(term) for term in results_graph.objects(source_shape, sh.severity)
                    ] or [
                        str(term) for term in results_graph.objects(source_shape, sh.sourceSeverity)
                    ]
            if any("Violation" in severity for severity in severity_terms):
                errors.append(f"SHACL violation: {text}")
            elif any("Warning" in severity for severity in severity_terms):
                warnings.append(f"SHACL warning: {text}")
            else:
                info.append(f"SHACL notice: {text}")
        return errors, warnings, info


class OwlConsistencyValidator:
    """``owl`` layer — per-run OWL structural consistency (rdflib-only).

    Port of the rdflib checks in
    ``domain-profile/scripts/validate_reasoner.py`` (``validate_with_rdflib``):

    * **Error:** circular ``subClassOf`` chains; conflicting duplicate
      definitions (a class with two ``subClassOf`` parents where one is an
      ancestor of the other); ontology parse failure.
    * **Warning:** profile classes/properties without ``rdfs:label``,
      orphan classes, individuals without a concrete type.

    Full OWL-DL reasoning (unsatisfiable classes, inconsistent individuals)
    remains the **offline/CI** gate via the external HermiT reasoner
    (``validate_reasoner.py --strict``); this pipeline never launches a JVM.
    """

    layer = "owl"
    name = "OwlConsistencyValidator"

    def __init__(self, ontology_file: Optional[str] = None):
        self._ontology_file = ontology_file

    def validate(self, investigation_path: str, ctx: Dict[str, Any]) -> LayerResult:
        """Run the rdflib structural checks over the profile ontology."""
        ontology_path = self._resolve_ontology(ctx)
        if ontology_path is None or not Path(ontology_path).exists():
            return _make_result(
                self.layer,
                self.name,
                blocking=True,
                status="skipped",
                info=["ontology file not found — OWL structural check skipped"],
            )

        try:
            from rdflib import Graph

            graph = Graph()
            graph.parse(ontology_path, format=_format_for(Path(ontology_path)))
        except Exception as exc:  # noqa: BLE001 - parse failure is a concrete Error
            return _make_result(
                self.layer,
                self.name,
                blocking=True,
                errors=[f"failed to parse ontology file {ontology_path}: {exc}"],
            )

        errors, warnings, info = self._structural_checks(graph)
        details = {"triples": len(graph), "ontology_file": str(ontology_path)}
        return _make_result(
            self.layer,
            self.name,
            blocking=True,
            errors=errors,
            warnings=warnings,
            info=info,
            details=details,
        )

    # -- helpers ----------------------------------------------------------

    def _resolve_ontology(self, ctx: Dict[str, Any]) -> Optional[str]:
        if self._ontology_file:
            return str(self._ontology_file)
        profile = ctx.get("profile")
        if profile is None:
            return None
        for key in ("main_ttl", "main_owl"):
            try:
                candidate = profile.get_ontology_filenames().get(key) or ""
            except Exception:  # noqa: BLE001 - defensive
                candidate = ""
            if not candidate:
                continue
            path = Path(candidate)
            if path.is_absolute() or path.exists():
                return str(path)
            try:
                root_relative = Path(profile.get_profile_root()) / candidate
            except Exception:  # noqa: BLE001 - defensive
                continue
            if root_relative.exists():
                return str(root_relative)
            if key == "main_ttl":
                return str(path)
        return None

    @staticmethod
    def _structural_checks(graph: Any) -> Tuple[List[str], List[str], List[str]]:
        from rdflib import OWL, RDF, RDFS

        errors: List[str] = []
        warnings: List[str] = []
        info: List[str] = []
        classes = [s for s in graph.subjects(RDF.type, OWL.Class)]
        info.append(f"OWL check: {len(graph)} triples, {len(classes)} classes")

        parent: Dict[Any, Set[Any]] = {}
        for subject, _predicate, obj in graph.triples((None, RDFS.subClassOf, None)):
            parent.setdefault(subject, set()).add(obj)

        def ancestors_of(term: Any, seen: Set[Any]) -> bool:
            for par in parent.get(term, ()):
                if par in seen:
                    return True
                if ancestors_of(par, seen | {par}):
                    return True
            return False

        def ancestor_set(term: Any) -> Set[Any]:
            out: Set[Any] = set()
            stack = [term]
            while stack:
                current = stack.pop()
                for par in parent.get(current, ()):
                    if par not in out:
                        out.add(par)
                        stack.append(par)
            return out

        # 1. Circular subclassOf chains — Error
        cycle_members: Set[Any] = set()
        for cls in classes:
            if cls in parent and ancestors_of(cls, {cls}):
                cycle_members.add(cls)
        if cycle_members:
            errors.append(
                "Circular subclassOf chain detected involving: "
                + ", ".join(sorted(str(c) for c in cycle_members))
            )

        # 2. Conflicting duplicate definitions — Error
        seen_conflicts: Set[Tuple[Any, Any, Any]] = set()
        for cls in classes:
            parents = parent.get(cls, set())
            if len(parents) < 2:
                continue
            for par_a in parents:
                for par_b in parents:
                    if par_a == par_b:
                        continue
                    if par_a in ancestor_set(par_b) or par_b in ancestor_set(par_a):
                        key = (cls, min(par_a, par_b), max(par_a, par_b))
                        if key not in seen_conflicts:
                            seen_conflicts.add(key)
                            errors.append(
                                f"Conflicting duplicate definition of {cls}: "
                                f"parents {par_a} and {par_b} are in a subclassOf "
                                "relationship"
                            )

        def _is_external(term: Any) -> bool:
            return str(term).startswith(_EXTERNAL_TERM_PREFIXES)

        # 3. Profile classes/properties without labels — Warning
        for cls in classes:
            if _is_external(cls):
                continue
            if not list(graph.objects(cls, RDFS.label)):
                warnings.append(f"class {cls} has no rdfs:label")
        for prop_type in (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty):
            for prop in graph.subjects(RDF.type, prop_type):
                if _is_external(prop):
                    continue
                if not list(graph.objects(prop, RDFS.label)):
                    warnings.append(f"property {prop} has no rdfs:label")

        # 4. Orphan classes (no parent, no children) — Warning
        for cls in classes:
            if _is_external(cls):
                continue
            has_parent = (cls, RDFS.subClassOf, None) in graph
            has_children = (None, RDFS.subClassOf, cls) in graph
            if not has_parent and not has_children:
                warnings.append(f"orphan class {cls} — no subClassOf and no subclasses")

        # 5. Individuals without a concrete type — Warning
        individuals = list(graph.subjects(RDF.type, OWL.NamedIndividual))
        for individual in individuals:
            concrete = [
                t
                for _s, _p, t in graph.triples((individual, RDF.type, None))
                if t != OWL.NamedIndividual
            ]
            if not concrete:
                warnings.append(f"individual {individual} has no type other than NamedIndividual")

        return errors, warnings, info


class OlsValidator:
    """``ols`` layer — **optional** EBI Ontology Lookup Service cross-check.

    Default **OFF** (not in :data:`DEFAULT_LAYERS`); enabled only via the
    CLI ``--validation-layers ... ,ols`` flag, the ``validation_layers``
    API parameter, or the GUI "OLS lookup (network, slow)" checkbox.

    Purpose: users who did **not** download the reference ontologies (so the
    semantic layer's local rdflib lookup has no cache to check against) can
    let the pipeline cross-check unresolved terms against the EBI OLS REST
    API.  It is network-dependent and slower than the local lookup.

    Behavior:

    * Re-checks the terms the semantic layer could not verify locally
      (``details["unverified"]``); if there are none, the layer passes with
      an info note.
    * Term found on OLS → Warning ("resolved via OLS — not in local cache");
      term not found → Warning ("still missing on OLS").
    * Network error, timeout, or OLS unavailable → ``status="skipped"`` with
      an info note.  **Never a hard failure.**
    """

    layer = "ols"
    name = "OlsValidator"

    def __init__(self, timeout: int = 10, enabled: bool = False):
        self._timeout = int(timeout)
        self._enabled = bool(enabled)
        self._cache: Dict[str, Optional[bool]] = {}

    def validate(self, investigation_path: str, ctx: Dict[str, Any]) -> LayerResult:
        """Cross-check unresolved terms against the EBI OLS API."""
        if not self._enabled:
            return _make_result(
                self.layer,
                self.name,
                blocking=False,
                status="skipped",
                info=[
                    "OLS lookup disabled (optional, network-dependent layer; "
                    "enable with --validation-layers ...,ols or the GUI "
                    "'OLS lookup' checkbox)"
                ],
            )

        investigation = ctx.get("investigation")
        investigation = investigation if isinstance(investigation, dict) else {}
        refs = extract_ontology_refs(investigation)
        unverified = list(ctx.get("semantic_unverified") or [])

        # Deduplicate while preserving order.
        seen: Set[str] = set()
        targets: List[str] = []
        for uri in unverified:
            uri = str(uri)
            if uri not in seen:
                seen.add(uri)
                targets.append(uri)

        # When the semantic layer did not flag unresolved terms (no local
        # cache, semantic layer off, or all terms verified), fall back to
        # every well-formed accession so the OLS cross-check is meaningful.
        if not targets:
            for ref in refs:
                uri = str(ref.get("termAccession") or "")
                if uri and uri not in seen:
                    seen.add(uri)
                    targets.append(uri)

        if not targets:
            return _make_result(
                self.layer,
                self.name,
                blocking=False,
                status="passed",
                info=["no ontology terms found — nothing to check against OLS"],
                details={"references": len(refs), "checked": 0},
            )

        warnings: List[str] = []
        info: List[str] = []
        found = 0
        network_error: Optional[str] = None
        for uri in targets:
            norm = self._ols_ontology_for(uri, refs)
            if norm is None or norm not in OLS_ONTOLOGY_MAP:
                info.append(f"term '{uri}' has no OLS ontology mapping — not checked")
                continue
            cache_key = f"{norm}:{uri}"
            if cache_key in self._cache:
                answer = self._cache[cache_key]
            else:
                try:
                    answer = self._lookup(uri, OLS_ONTOLOGY_MAP[norm])
                except Exception as exc:  # noqa: BLE001 - graceful skip on network issues
                    network_error = f"{exc.__class__.__name__}: {exc}"
                    break
                self._cache[cache_key] = answer
            if network_error is not None:
                break
            if answer:
                found += 1
                warnings.append(f"term '{uri}' resolved via OLS (not present in local cache)")
            else:
                warnings.append(f"term '{uri}' could not be verified locally or on OLS")

        if network_error is not None:
            return _make_result(
                self.layer,
                self.name,
                blocking=False,
                status="skipped",
                info=[f"OLS unavailable ({network_error}) — optional OLS lookup skipped"],
                details={"checked": 0, "error": network_error},
            )

        details = {"checked": len(targets), "found_on_ols": found}
        return _make_result(
            self.layer,
            self.name,
            blocking=False,
            warnings=warnings,
            info=info,
            details=details,
        )

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _ols_ontology_for(uri: str, refs: List[Dict[str, Any]]) -> Optional[str]:
        for ref in refs:
            if ref.get("termAccession") and str(ref["termAccession"]) == uri:
                return _normalize_term_source(str(ref.get("termSource") or ""))
        return None

    def _lookup(self, uri: str, ols_ontology: str) -> bool:
        """Query the OLS search API.  Raises on network/transport errors so
        the caller can convert them into a graceful skip."""
        last_segment = uri.rsplit("/", 1)[-1]
        search_query = last_segment if ("_" in last_segment or ":" in last_segment) else uri
        encoded_q = urllib.parse.quote(search_query, safe="")
        url = f"{OLS_API_BASE}/search?q={encoded_q}&ontology={ols_ontology}&rows=3"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
        docs = (payload.get("response") or {}).get("docs") or []
        for doc in docs:
            if doc.get("iri") == uri:
                return True
            obo_id = str(doc.get("obo_id") or "").replace(":", "_")
            if obo_id and obo_id == search_query:
                return True
        return False


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ValidationEngine:
    """Runs the enabled validation layers in canonical order and aggregates
    the results into a :class:`ValidationReport`.

    A validator that raises is captured as a ``skipped`` layer with an info
    note — Stage 7 never crashes the pipeline.  Skipped layers (e.g. SHACL
    without ``pyshacl``, OWL/SHACL without a profile ontology, or the
    disabled/optional OLS layer) never affect ``passed``.
    """

    def __init__(
        self,
        *,
        templates_root: Optional[str] = None,
        classifications: Optional[Dict[str, Dict[str, Any]]] = None,
        enabled_layers: Optional[List[str]] = None,
        profile: Optional[Any] = None,
        shapes_file: Optional[str] = None,
        ontology_file: Optional[str] = None,
        cache_dir: Optional[str] = None,
        max_parse_bytes: int = MAX_PARSE_SIZE_BYTES,
        ols_enabled: Optional[bool] = None,
        ols_timeout: int = 10,
    ):
        """
        Args:
            templates_root: Assay-templates directory for the template layer.
            classifications: Per-experiment classification records (used to
                bind assays to templates); defaults to ``{}``.
            enabled_layers: Layer names to run.  ``None`` (or ``[]``) means
                the default set — all core layers **except** ``ols``.
                Pass an explicit list (e.g. ``["schema", "ols"]``) to select
                a subset.  Unknown names raise :class:`ValueError`.
            profile: Active :class:`ProfileLoader` (optional; used to resolve
                shapes/ontology files and the cached-ontology directory).
            shapes_file: Explicit SHACL shapes file override.
            ontology_file: Explicit OWL/SHACL target ontology override.
            cache_dir: Cached-ontology directory for the semantic layer.
            max_parse_bytes: Per-file parse cap for cached ontologies.
            ols_timeout: HTTP timeout (seconds) for the optional OLS layer.
        """
        self._templates_root = templates_root
        self._classifications = dict(classifications or {})
        self._profile = profile
        self._shapes_file = shapes_file
        self._ontology_file = ontology_file
        self._cache_dir = cache_dir
        self._max_parse_bytes = int(max_parse_bytes)
        self._ols_timeout = int(ols_timeout)

        if enabled_layers is None:
            enabled = list(DEFAULT_LAYERS)
        else:
            enabled = list(enabled_layers)
            unknown = [name for name in enabled if name not in LAYER_NAMES]
            if unknown:
                raise ValueError(
                    f"unknown validation layer(s): {', '.join(unknown)}; "
                    f"valid layers: {', '.join(LAYER_NAMES)}"
                )
        ordered = [name for name in LAYER_NAMES if name in enabled]
        self._enabled = ordered
        # OLS is opt-in: it runs only when explicitly enabled AND present in
        # the enabled set.
        self._ols_enabled = bool(ols_enabled) and "ols" in ordered

    @property
    def enabled_layers(self) -> List[str]:
        """The layer names this engine will run (canonical order)."""
        return list(self._enabled)

    def run(self, investigation_path: str) -> ValidationReport:
        """Execute the enabled layers and return the aggregated report."""
        ctx = self._build_context(investigation_path)
        layers: List[LayerResult] = []
        for name in self._enabled:
            validator = self._factory(name)
            start = time.monotonic()
            try:
                layer_result = validator.validate(investigation_path, ctx)
            except Exception as exc:  # noqa: BLE001 - Stage 7 must never crash
                logger.warning("validation layer %s raised: %s", name, exc, exc_info=True)
                layer_result = _make_result(
                    name,
                    type(validator).name,
                    blocking=name in BLOCKING_LAYERS,
                    status="skipped",
                    info=[f"{name} layer crashed ({exc.__class__.__name__}: {exc}) — skipped"],
                )
            layer_result.duration = round(time.monotonic() - start, 3)
            layers.append(layer_result)
            self._propagate(layer_result, ctx)

        passed = not any(layer.blocking and layer.errors for layer in layers)
        return ValidationReport(
            passed=passed,
            layers=layers,
            skipped_layers=[layer.layer for layer in layers if layer.status == "skipped"],
        )

    # -- internals --------------------------------------------------------

    def _factory(self, name: str) -> Any:
        """Instantiate the validator for *name* (fresh per run)."""
        if name == "schema":
            return SchemaLayer()
        if name == "semantic":
            cache_dir = self._cache_dir
            if cache_dir is None and self._profile is not None:
                try:
                    config = self._profile.get_validation_config()
                    semantic_config = config.get("semantic") or {}
                    raw = semantic_config.get("cache_dir")
                    if raw:
                        cache_dir = str(Path(self._profile.get_profile_root()) / raw)
                except Exception:  # noqa: BLE001 - defensive
                    cache_dir = None
            return SemanticValidator(cache_dir=cache_dir, max_parse_bytes=self._max_parse_bytes)
        if name == "data_file":
            return DataFileLayer()
        if name == "template":
            return TemplateValidator(self._templates_root)
        if name == "shacl":
            return ShaclValidator(shapes_file=self._shapes_file, ontology_file=self._ontology_file)
        if name == "owl":
            return OwlConsistencyValidator(ontology_file=self._ontology_file)
        if name == "ols":
            return OlsValidator(timeout=self._ols_timeout, enabled=self._ols_enabled)
        raise ValueError(f"unknown validation layer: {name}")

    def _build_context(self, investigation_path: str) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {
            "investigation": {},
            "semantic_unverified": [],
            "profile": self._profile,
            "classifications": self._classifications,
        }
        try:
            with open(investigation_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if isinstance(raw, dict):
                ctx["investigation"] = raw.get("investigation", raw)
        except (json.JSONDecodeError, OSError):
            ctx["investigation"] = {}
        return ctx

    def _propagate(self, layer_result: LayerResult, ctx: Dict[str, Any]) -> None:
        """Pass cross-layer signals (e.g. semantic → OLS) via the context."""
        if layer_result.layer == "semantic":
            unverified = layer_result.details.get("unverified")
            if isinstance(unverified, list):
                ctx["semantic_unverified"] = [str(uri) for uri in unverified]
