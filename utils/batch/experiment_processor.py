"""
Experiment folder processor (batch conversion pipeline).

This module converts raw experiment folders (e.g. ``E1_...``, ``EXP_01_...``
— any layout matching the configured ``experiment_folder`` pattern) into
GUI-compatible, ISA-JSON-compliant study files.

Factor extraction is delegated to the shared, rule-driven engine
:class:`utils.batch.factor_rules.FactorRulesExtractor`, which reads its rules
from the active profile's ``factor_extraction_rules.json`` (falling back to the
core neutral default), so the batch pipeline and any profile use the same
declarative rules.

Assay configuration (measurement types, file extensions, name keywords,
optional live/dead measurement override) is read from the profile's
``assay_types.json`` via :func:`utils.config_loader.get_profile`; cell-type
detection is driven by the profile's ``cell_type_map``.  No project-specific
biology or naming is hard-coded here.

Only the *processing* logic lives here.  XLSX conversion
(``convert_excel_to_csv`` / ``extract_excel_metadata``) is intentionally not
part of this module; run it separately via :mod:`utils.batch.format_converter`.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.batch.experiment_classifier import (
    ExperimentClassification,
    ExperimentClassifier,
)
from utils.batch.factor_rules import FactorRulesExtractor
from utils.batch.folder_scanner import FolderMetadata
from utils.config_loader import get_profile
from utils.directory_manager import DirectoryManager
from utils.isa_json_exporter import ISAJsonExporter
from utils.material_manager import MaterialManager

logger = logging.getLogger(__name__)


class _AssayRegistryAccessor:
    """Descriptor exposing the active profile's assay registry.

    Supports both class-level (``ExperimentProcessor.ASSAY_TYPE_CONFIG``) and
    instance-level (``processor.ASSAY_TYPE_CONFIG``) access, always resolving
    the live registry from the active profile.
    """

    def __get__(self, obj, objtype=None) -> Dict[str, Any]:
        return get_profile().get_assay_types().get("assays") or {}


# ── Result dataclasses ─────────────────────────────────────────────────────


@dataclass
class StudyResult:
    """Result of processing a single study/experiment."""

    success: bool
    study_id: str = ""
    assay_type: str = ""
    assays_created: int = 0
    materials_created: int = 0
    files_linked: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class BatchResult:
    """Aggregated result of a full batch conversion run."""

    total_experiments: int = 0
    successful: int = 0
    failed: int = 0
    total_files: int = 0
    total_files_linked: int = 0
    validation_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    study_results: List[StudyResult] = field(default_factory=list)


# ── Processor ──────────────────────────────────────────────────────────────


class ExperimentProcessor:
    """Process experiment folders into ISA-JSON studies.

    Args:
        data_root: Root directory containing experiment folders (named per
            the configured ``experiment_folder`` pattern).
        investigation_id: Investigation identifier for the output.
        base_path: Base directory used by :class:`DirectoryManager`
            (investigations are created under ``base_path/investigations``).
        skip_conversion: When True, XLSX conversion is not attempted.
        validate: When True, run internal ISA-JSON sanity checks after export.
        verbose: Enable verbose logging.
    """

    def __init__(
        self,
        data_root: Optional[str] = None,
        investigation_id: str = "inv_001",
        base_path: Optional[str] = None,
        skip_conversion: bool = True,
        validate: bool = False,
        verbose: bool = False,
    ) -> None:
        self.investigation_id = investigation_id
        self.data_root = Path(data_root) if data_root else None
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self.skip_conversion = skip_conversion
        self.validate = validate
        self.verbose = verbose

        if verbose:
            logging.basicConfig(level=logging.INFO)

        # DirectoryManager with an explicit base path so tests can redirect
        # output to a temp directory.
        self.dm = DirectoryManager(base_path=str(self.base_path))
        self.dm.create_investigation_directory(investigation_id)

        # FCS acquisition summary (instrument/operator/date/channels/…).
        # Populated per experiment in _process_experiment when available.
        self._fcs_summary: Dict[str, Any] = {}

    # ── Assay configuration (profile-driven) ───────────────────────────────

    #: Live assay registry (assay key -> configuration), always resolved from
    #: the active profile via the descriptor.
    ASSAY_TYPE_CONFIG = _AssayRegistryAccessor()

    def _assay_registry(self) -> Dict[str, Any]:
        """Return the assay registry (``assay_key -> config``) from the profile."""
        return self.ASSAY_TYPE_CONFIG

    def _default_assay_key(self) -> str:
        """Return the catch-all assay key (``calcein`` by core default)."""
        return get_profile().get_assay_types().get("default_assay") or "calcein"

    # ── Factor rules (shared engine) ─────────────────────────────────────

    def _rules_data(self) -> Dict[str, Any]:
        """Load factor extraction rules from the active profile."""
        try:
            return get_profile().get_factor_extraction_rules() or {}
        except Exception:  # pragma: no cover - defensive
            return {}

    def _extractor(self) -> FactorRulesExtractor:
        """Build a :class:`FactorRulesExtractor` from the profile rules."""
        return FactorRulesExtractor(self._rules_data())

    def _load_factor_aliases(self) -> Dict[str, Dict[str, List[str]]]:
        """Return the ``factor_aliases`` section of the rules config."""
        return self._extractor().aliases

    def _parse_filename_factors(self, experiment) -> Optional[tuple]:
        """Extract factors from all file names of *experiment*.

        Delegates to the shared rule engine.  Returns
        ``(factor_values, combinations)`` when a rule fires, else ``None``.
        """
        folder_path = getattr(experiment, "folder_path", None)
        file_names: List[str] = []
        if folder_path and Path(folder_path).is_dir():
            file_names = sorted(p.name for p in Path(folder_path).rglob("*") if p.is_file())
        return self._extractor().extract(
            getattr(experiment, "experiment_name", "") or "", file_names
        )

    # ── Study identity ────────────────────────────────────────────────────

    def _generate_study_id(self, experiment) -> str:
        """Deterministic study id derived from the experiment id and name.

        Shape: ``study_<exp_id>_<sanitized-name>``; the experiment id token is
        matched with the profile's configured ``experiment_folder`` pattern
        (neutral default ``^E(\\d+)``).  Falls back to ``study_exp_`` when no
        name is available.
        """
        exp_id = (getattr(experiment, "experiment_id", "") or "").strip()
        name = (getattr(experiment, "experiment_name", "") or "").strip()
        if not exp_id:
            pattern, _group = get_profile().get_experiment_folder_pattern()
            m = pattern.match(name)
            exp_id = m.group(0) if m else "exp"
        exp_id = re.sub(r"[^0-9A-Za-z_]+", "_", exp_id).strip("_") or "exp"

        suffix = re.sub(r"[^0-9A-Za-z]+", "_", name).strip("_")
        suffix = re.sub(r"_+", "_", suffix)
        # Drop a leading duplicate of the experiment id in the name
        if suffix.lower().startswith(exp_id.lower()) and len(suffix) > len(exp_id):
            if suffix[len(exp_id) : len(exp_id) + 1] == "_" or not suffix[len(exp_id) :]:
                suffix = suffix[len(exp_id) :].strip("_")
        if suffix:
            return f"study_{exp_id}_{suffix}"
        return f"study_{exp_id}_"

    # ── Classification helpers ────────────────────────────────────────────

    def _determine_cell_type(self, experiment) -> str:
        """Detect the cell/tissue type from the experiment folder name.

        Driven entirely by the active profile's ``cell_type_map``
        (``{keyword: cell_type_key}``).  The first keyword (case-insensitive)
        found in the folder name is returned; when no profile keyword matches
        a neutral ``"Unknown"`` label is used.
        """
        name = getattr(experiment, "experiment_name", "") or ""
        name_l = name.lower()
        try:
            cell_type_map = get_profile().get_cell_type_map()
        except Exception:  # pragma: no cover - defensive
            cell_type_map = {}
        for keyword in cell_type_map:
            if keyword and keyword.lower() in name_l:
                return keyword
        return "Unknown"

    def _determine_assay_types(
        self, experiment, exp_type: Optional[ExperimentClassification] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Determine assay types for the experiment.

        Combines the classifier's result (when provided), folder-name
        keywords and the file inventory to select the assay configuration
        entries from the profile's ``assay_types`` registry.
        """
        assays = self._assay_registry()
        assay_types: Dict[str, Dict[str, Any]] = {}

        def _add(key: str) -> None:
            if key in assays and key not in assay_types:
                assay_types[key] = assays[key]

        # 1) Classifier-provided type (primary signal).
        if exp_type is not None:
            tname = (getattr(exp_type, "type_name", "") or "").lower()
            if tname in assays:
                _add(tname)

        # 2) Folder-name keywords (from each assay's ``name_keywords``).
        name_l = (getattr(experiment, "experiment_name", "") or "").lower()
        for key, cfg in assays.items():
            for kw in cfg.get("name_keywords") or []:
                if kw and kw.lower() in name_l:
                    _add(key)
                    break

        # 3) File inventory indicators.
        inventory = getattr(experiment, "file_inventory", None)
        if inventory is not None:
            if getattr(inventory, "fcs_files", None) or getattr(inventory, "wsp_files", None):
                _add("facs")
            if getattr(inventory, "czi_files", None) or getattr(inventory, "tiff_files", None):
                _add("dapi")

        if not assay_types:
            _add(self._default_assay_key())

        return assay_types

    # ── Conditions (treatments) ───────────────────────────────────────────

    _CONDITION_TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+")

    def _determine_conditions(self, experiment) -> List[str]:
        """Collect treatment conditions from the experiment's file names.

        Sources (in order, de-duplicated case-insensitively):
          1. the rule engine's ``treatment`` factor values (canonical form);
          2. known protein/drug names from the active profile (matched
             case-insensitively, appended in their canonical casing);
          3. as a last resort, alphabetic tokens (>= 3 chars) of the file
             stems, capitalised (e.g. ``Control``).

        Nested subdirectory files are included (rglob).
        """
        folder_path = getattr(experiment, "folder_path", None)
        file_names: List[str] = []
        if folder_path and Path(folder_path).is_dir():
            file_names = sorted(p.name for p in Path(folder_path).rglob("*") if p.is_file())

        conditions: List[str] = []

        def add(value: Optional[str]) -> None:
            if not value:
                return
            v = str(value).strip()
            if not v or any(v.lower() == c.lower() for c in conditions):
                return
            conditions.append(v)

        # 1) Rule-engine treatment values.
        result = self._parse_filename_factors(experiment)
        if result is not None:
            for t in sorted(result[0].get("treatment", set())):
                add(t)

        # 2) Known protein/drug names (canonical casing from the profile).
        try:
            known = list(get_profile().get_protein_name_map().keys())
            known += list(get_profile().get_drug_name_map().keys())
            for n in known:
                if n and any(n.lower() in fn.lower() for fn in file_names):
                    add(n)
        except Exception:
            pass

        # 3) Generic tokens from file stems (capitalised).
        for fn in file_names:
            for tok in self._CONDITION_TOKEN_RE.findall(Path(fn).stem):
                if len(tok) >= 3:
                    add(tok.capitalize())

        return conditions

    # ── Sample helpers ────────────────────────────────────────────────────

    @staticmethod
    def _get_sample_factor_strings(sample: Dict[str, Any]) -> List[str]:
        """Extract lowercase factor values from a sample dict."""
        values: List[str] = []
        for fv in sample.get("factorValues") or []:
            v = (fv.get("value") or {}).get("annotationValue", "")
            if v:
                values.append(str(v).lower())
        return values

    def _map_file_to_sample(
        self,
        filename: str,
        samples: List[Dict[str, Any]],
        aliases: Optional[Dict[str, Dict[str, List[str]]]] = None,
    ) -> Optional[str]:
        """Map a file to the best-matching sample ``@id`` (shared engine)."""
        return self._extractor().map_file_to_sample(filename, samples, aliases)

    # ── Study creation ────────────────────────────────────────────────────

    def _get_latest_modification_date(self, folder_path: str) -> str:
        """Latest file mtime in *folder_path* as ISO-8601 (…Z), else now."""
        latest: Optional[float] = None
        try:
            root = Path(folder_path)
            if root.is_dir():
                for p in root.rglob("*"):
                    if p.is_file():
                        mtime = p.stat().st_mtime
                        if latest is None or mtime > latest:
                            latest = mtime
        except OSError:
            latest = None
        if latest is None:
            latest = datetime.now().timestamp()
        return datetime.fromtimestamp(latest).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _create_study(
        self,
        experiment,
        study_id: str,
        exp_type: Optional[ExperimentClassification] = None,
    ) -> Dict[str, Any]:
        """Create the internal study dict (snake_case keys the exporter reads)."""
        cell_type = self._determine_cell_type(experiment)
        study_name = getattr(experiment, "experiment_name", "") or study_id
        study_description = (
            f"Automatically generated study for experiment {study_name}. "
            f"Cell type: {cell_type}."
        )
        submission_date = self._get_latest_modification_date(
            getattr(experiment, "folder_path", "") or str(Path(experiment).parent)
        )

        study_data: Dict[str, Any] = {
            "identifier": study_id,
            "study_name": study_name,
            "study_description": study_description,
            "submission_date": submission_date,
            "public_release_date": "",
            "materials": {"sources": [], "samples": [], "otherMaterials": []},
            "assays": [],
            "protocols": [],
            "factors": [],
            "characteristicCategories": [],
            "study_design_descriptors": [
                {
                    "annotationValue": "experimental study",
                    "termSource": "OBI",
                    "termAccession": "http://purl.obolibrary.org/obo/OBI_0000066",
                }
            ],
        }

        self.dm.create_study_directory(self.investigation_id, study_id)
        return study_data

    # ── Materials ─────────────────────────────────────────────────────────

    def _create_materials(
        self,
        study_data: Dict[str, Any],
        material_manager: MaterialManager,
        experiment,
        exp_type: Optional[ExperimentClassification] = None,
    ) -> tuple:
        """Create source + sample materials.

        One sample per rule-derived factor combination; when no rule fires,
        one sample per detected condition (treatment factor); otherwise a
        single default sample.

        Returns:
            (source_id, sample_ids)
        """
        cell_type = self._determine_cell_type(experiment)
        from utils.batch.isa_json_generator import ONTOLOGY

        source = material_manager.add_material(
            "source",
            {
                "name": cell_type,
                "characteristics": [
                    {
                        "category": {"@id": "#characteristic_category/cell_type"},
                        "value": ONTOLOGY.get("cell_type"),
                    }
                ],
            },
        )
        source_id = source.get("@id", "")

        sample_ids: List[str] = []

        result = self._parse_filename_factors(experiment)
        combinations = result[1] if result is not None else []
        if combinations:
            for combo in combinations:
                label = "_".join(str(v) for v in combo.values())
                sample = material_manager.add_material(
                    "sample",
                    {
                        "name": f"{cell_type} - {label}",
                        "derivesFrom": {"@id": source_id},
                        "factorValues": [
                            {
                                "category": {"@id": f"#factor/{name}"},
                                "value": {"annotationValue": value},
                            }
                            for name, value in combo.items()
                        ],
                    },
                )
                sample_ids.append(sample.get("@id", ""))

        conditions: List[str] = []
        if not sample_ids:
            conditions = self._determine_conditions(experiment)
            for cond in conditions:
                sample = material_manager.add_material(
                    "sample",
                    {
                        "name": f"{cell_type} - {cond}",
                        "derivesFrom": {"@id": source_id},
                        "factorValues": [
                            {
                                "category": {"@id": "#factor/treatment"},
                                "value": {"annotationValue": cond},
                            }
                        ],
                    },
                )
                sample_ids.append(sample.get("@id", ""))

        if not sample_ids:
            sample = material_manager.add_material(
                "sample",
                {
                    "name": f"{cell_type} - sample",
                    "derivesFrom": {"@id": source_id},
                },
            )
            sample_ids.append(sample.get("@id", ""))

        return source_id, sample_ids

    # ── Assays ────────────────────────────────────────────────────────────

    def _fcs(self) -> Dict[str, Any]:
        """The FCS acquisition summary (``{}`` when unset, e.g. on instances
        created via ``__new__`` in unit tests)."""
        summary = getattr(self, "_fcs_summary", None)
        return summary if isinstance(summary, dict) else {}

    def _fcs_markers(self) -> List[Dict[str, Any]]:
        """Return the FCS marker list from the active profile (may be [])."""
        try:
            markers = get_profile()._get_section("fcs_markers")
            if isinstance(markers, list):
                return markers
            if isinstance(markers, dict):
                for key in ("markers", "fcs_markers"):
                    value = markers.get(key)
                    if isinstance(value, list):
                        result: List[Dict[str, Any]] = value
                        return result
            return []
        except Exception:
            return []

    def _reagents_from_fcs(self) -> List[str]:
        """Detected reagent names from the FCS acquisition summary/markers."""
        reagents: List[str] = []
        summary = self._fcs_summary or {}
        for marker in summary.get("markers", []):
            dye = marker.get("dye") or ""
            if dye and dye not in reagents:
                reagents.append(dye)
        if not reagents:
            for marker in self._fcs_markers():
                dye = marker.get("dye") or marker.get("name") or ""
                if dye and dye not in reagents:
                    reagents.append(dye)
        return reagents

    def _create_assays(
        self,
        study_data: Dict[str, Any],
        assay_types: Dict[str, Dict[str, Any]],
        sample_ids: List[str],
        experiment,
    ) -> List[Dict[str, Any]]:
        """Create assay entries for each assay type.

        Enriches assays flagged with ``fcs_enrichment`` using the FCS-derived
        metadata when available: instrument (assay + protocol parameter),
        reagents (protocol parameters) and a live/dead measurement-type
        override (``live_dead_measurement_type``).
        """
        assays: List[Dict[str, Any]] = []
        protocols: List[Dict[str, Any]] = []
        summary = self._fcs()
        instrument = summary.get("instrument") or ""

        for key, config in assay_types.items():
            assay_name = config["name"]
            protocol_name = f"assay {assay_name.lower()}"
            protocol_id = f"#protocol/{protocol_name}"

            assay: Dict[str, Any] = {
                "@id": f"#assay_{key}",
                "name": assay_name,
                "assay_type": key,
                "measurementType": dict(config["measurement_type"]),
                "technologyType": dict(config["technology_type"]),
                "dataFiles": [],
                "materials": {"samples": [], "otherMaterials": []},
                "processSequence": [],
                "characteristicCategories": [],
                "unitCategories": [],
                "filename": f"a_{key}.txt",
                "parameters": [],
            }

            # Live/dead override: config-driven (no hard-coded assay branch).
            live_dead = config.get("live_dead_measurement_type")
            if live_dead and summary.get("is_live_dead"):
                assay["measurementType"] = dict(live_dead)

            # Instrument as an assay parameter (config-gated).
            if config.get("fcs_enrichment") and instrument:
                assay["parameters"].append({"name": "instrument", "value": instrument})

            # Protocol (declared once; parameters added below).
            if not any(p.get("@id") == protocol_id for p in protocols):
                protocols.append(
                    {
                        "@id": protocol_id,
                        "name": protocol_name,
                        "protocolType": {
                            "annotationValue": "assay",
                            "termSource": "OBI",
                            "termAccession": "http://purl.obolibrary.org/obo/OBI_0000070",
                        },
                        "description": f"Protocol: {protocol_name}",
                        "uri": "",
                        "version": "",
                        "parameters": [],
                        "components": [],
                    }
                )

            # Instrument and reagents as protocol parameters
            # (ISA-valid parameterName shape), config-gated.
            if config.get("fcs_enrichment"):
                proto = next(p for p in protocols if p["@id"] == protocol_id)
                param_names = {
                    (p.get("parameterName") or {}).get("annotationValue", "")
                    for p in proto.get("parameters", [])
                }
                if instrument and "instrument" not in param_names:
                    proto["parameters"].append(
                        {
                            "@id": f"{protocol_id}#parameter/instrument",
                            "parameterName": {"annotationValue": "instrument"},
                        }
                    )
                for reagent in self._reagents_from_fcs():
                    if reagent not in param_names:
                        proto["parameters"].append(
                            {
                                "@id": f"{protocol_id}#parameter/{reagent}",
                                "parameterName": {"annotationValue": reagent},
                            }
                        )

            # Link sample materials to the assay.
            assay["materials"]["samples"] = [{"@id": sid} for sid in sample_ids]

            assays.append(assay)

        study_data["assays"] = assays
        for p in protocols:
            if not any(
                (q.get("@id") or q.get("name")) == (p.get("@id") or p.get("name"))
                for q in study_data["protocols"]
            ):
                study_data["protocols"].append(p)
        return assays

    # ── File assignment ───────────────────────────────────────────────────

    def _assign_files_to_assays(
        self, study_data: Dict[str, Any], experiment, assay_keys: List[str]
    ) -> int:
        """Assign experiment files to assays based on subdirectory context
        and file extension.  Returns the number of linked files."""
        folder_path = getattr(experiment, "folder_path", None)
        if not folder_path or not Path(folder_path).is_dir():
            return 0
        root = Path(folder_path)
        assays_cfg = self._assay_registry()

        assays = study_data["assays"]
        linked = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            parent_dir = rel.parts[0] if len(rel.parts) > 1 else ""

            # Context-aware: a directory named after an assay wins.
            key = None
            for ak in assay_keys:
                if parent_dir.lower() == ak.lower() or (
                    parent_dir.lower().startswith(ak.lower()) and ak.lower() in parent_dir.lower()
                ):
                    key = ak
                    break
            if key is None:
                # Extension-based assignment (config-driven extensions).
                suffix = path.suffix.lower()
                for ak in assay_keys:
                    if suffix in (assays_cfg.get(ak) or {}).get("file_extensions", []):
                        key = ak
                        break
            if key is None:
                default_key = self._default_assay_key()
                key = default_key if default_key in assay_keys else assay_keys[0]

            assay = next((a for a in assays if a.get("assay_type") == key), None)
            if assay is None:
                assay = assays[0]

            # Skip duplicates (same filename already linked).
            if any(f.get("name") == path.name for f in assay["dataFiles"]):
                continue

            try:
                size = str(int(path.stat().st_size))
            except OSError:
                size = "0"
            assay["dataFiles"].append(
                {
                    "@id": f"#datafile_{key}_{path.name}",
                    "name": path.name,
                    "type": (
                        "Raw Data File"
                        if suffix in (".fcs", ".czi", ".tif", ".tiff")
                        else "Derived Data File"
                    ),
                    "comments": [
                        {"name": "TraceDB", "value": str(path)},
                        {"name": "fileSize", "value": size},
                    ],
                }
            )
            linked += 1
        return linked

    # ── Per-sample processes ──────────────────────────────────────────────

    def _build_per_sample_processes(
        self,
        study_data: Dict[str, Any],
        assays: List[Dict[str, Any]],
        samples: List[Dict[str, Any]],
        study_id: str,
    ) -> None:
        """Create per-sample processes for each assay.

        Each process takes one sample as input and the assay's data files
        as outputs.  Files are mapped to samples with the delimited-token
        mapper; unmatched files are still linked (with an "unassigned"
        derivedFromSample comment) so no data is lost.
        """
        if not assays or not samples:
            return

        aliases = self._load_factor_aliases()
        summary = self._fcs()
        fcs_date = summary.get("acquisition_date_iso") or ""
        performer = summary.get("operator") or ""

        for assay in assays:
            data_files = assay.get("dataFiles", [])
            if not data_files:
                continue

            # Reset existing process sequence for a clean rebuild.
            processes: List[Dict[str, Any]] = []
            assigned_files: List[str] = []

            for sample in samples:
                sample_id = sample.get("@id", "")
                sample_files = [
                    f
                    for f in data_files
                    if self._map_file_to_sample(f.get("name", ""), [sample], aliases) == sample_id
                ]
                if not sample_files:
                    continue

                for f in sample_files:
                    self._ensure_sample_comment(f, sample_id)
                assigned_files.extend(f.get("name", "") for f in sample_files)

                proc: Dict[str, Any] = {
                    "@id": f"#process/{study_id}_{assay.get('assay_type', 'assay')}_{sample_id}",
                    "name": f"assay {assay.get('assay_type', 'assay')} on {sample.get('name', '')}",
                    "executes_protocol": f"assay {assay.get('assay_type', 'assay')}",
                    "inputs": [{"@id": sample_id}],
                    "outputs": [{"@id": f.get("@id", "")} for f in sample_files],
                    "date": fcs_date,
                    "performer": performer,
                }
                if not fcs_date:
                    proc.pop("date")
                if not performer:
                    proc.pop("performer")
                processes.append(proc)

            # Unassigned files -> single process without sample inputs.
            unassigned = [f for f in data_files if f.get("name", "") not in assigned_files]
            for f in unassigned:
                self._ensure_sample_comment(f, "unassigned")
            if unassigned:
                processes.append(
                    {
                        "@id": f"#process/{study_id}_{assay.get('assay_type', 'assay')}_unassigned",
                        "name": f"assay {assay.get('assay_type', 'assay')} (unassigned files)",
                        "executes_protocol": f"assay {assay.get('assay_type', 'assay')}",
                        "inputs": [],
                        "outputs": [{"@id": f.get("@id", "")} for f in unassigned],
                        "date": fcs_date,
                        "performer": performer,
                    }
                )

            assay["processSequence"] = processes

    @staticmethod
    def _ensure_sample_comment(data_file: Dict[str, Any], sample_id: str) -> None:
        """Attach/replace the derivedFromSample comment on a data file."""
        comments = data_file.setdefault("comments", [])
        comments[:] = [c for c in comments if c.get("name") != "derivedFromSample"]
        comments.append({"name": "derivedFromSample", "value": sample_id})

    # ── Study-level process sequence ──────────────────────────────────────

    def _create_study_process_sequence(
        self,
        study_data: Dict[str, Any],
        process_manager,
        source_id: str,
        sample_ids: List[str],
    ) -> None:
        """Create the study-level sample-collection process."""
        summary = self._fcs()
        collection_date = summary.get("acquisition_date_iso") or datetime.now().strftime("%Y-%m-%d")
        process = {
            "@id": "#process/sample_collection",
            "name": "sample collection",
            "executes_protocol": "sample collection",
            "inputs": [{"@id": source_id}] if source_id else [],
            "outputs": [{"@id": sid} for sid in sample_ids],
            "date": collection_date,
        }
        if process_manager is not None:
            process_manager.add_process(process)
        else:
            study_data.setdefault("process_sequence", {"processes": []})["processes"].append(
                process
            )

    # ── Study description ─────────────────────────────────────────────────

    def _update_study_description(
        self,
        study_data: Dict[str, Any],
        experiment,
        cell_type: str,
        measurement_type: Dict[str, Any],
        sample_ids: List[str],
    ) -> None:
        """Append FCS-derived details (live/dead, instrument, date) to the
        study description and list the detected factors."""
        parts: List[str] = []
        summary = self._fcs()

        meas = (measurement_type or {}).get("annotationValue", "")
        if summary.get("is_live_dead") or "live" in meas.lower() or "dead" in meas.lower():
            parts.append("This experiment includes Live/Dead analysis.")
        instrument = summary.get("instrument") or ""
        if instrument:
            parts.append(f"FACS acquisition performed on {instrument}.")
        date = summary.get("acquisition_date_iso") or summary.get("acquisition_date") or ""
        if date:
            parts.append(f"Acquisition date: {date}.")

        factor_names = [f.get("name", "") for f in study_data.get("factors", [])]
        if factor_names:
            parts.append(f"Factors: {', '.join(factor_names)}.")

        if parts:
            existing = study_data.get("study_description", "")
            study_data["study_description"] = (existing + " " + " ".join(parts)).strip()

    # ── Factors ───────────────────────────────────────────────────────────

    def _register_study_factors(self, study_data: Dict[str, Any], experiment) -> None:
        """Register factor categories for the study.

        Factors from the rule engine are registered as-is; when the study
        has detected conditions but no ``treatment`` factor yet, a
        ``treatment`` factor is added so samples can carry treatment values.
        """
        factor_names: List[str] = []
        result = self._parse_filename_factors(experiment)
        if result is not None:
            factor_names = sorted(result[0].keys())

        conditions = self._determine_conditions(experiment)
        if conditions and "treatment" not in factor_names:
            factor_names.append("treatment")

        factors = study_data.setdefault("factors", [])
        for name in factor_names:
            if any(f.get("name") == name for f in factors):
                continue
            factors.append(
                {
                    "@id": f"#factor/{name}",
                    "name": name,
                    "factorName": name,
                }
            )

    # ── Export ────────────────────────────────────────────────────────────

    def _export_study_json(self, study_data: Dict[str, Any], study_id: str) -> Path:
        """Export the internal study dict to ``study.json`` (ISA-JSON)."""
        exporter = ISAJsonExporter(
            study_data=study_data,
            investigation_id=self.investigation_id,
            study_id=study_id,
        )
        data = exporter.export_complete_isa_json()
        out_path = self.dm.get_study_json_path(self.investigation_id, study_id)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return out_path

    def _internal_validate(self, study_data: Dict[str, Any]) -> List[str]:
        """Lightweight internal ISA-JSON sanity checks."""
        errors: List[str] = []
        for key in ("identifier", "study_name", "submission_date"):
            if not study_data.get(key):
                errors.append(f"Missing required field: {key}")
        for assay in study_data.get("assays", []):
            if not assay.get("name"):
                errors.append("Assay without name")
            if not assay.get("measurementType", {}).get("annotationValue"):
                errors.append(f"Assay '{assay.get('name')}' missing measurementType")
        return errors

    # ── Single experiment ─────────────────────────────────────────────────

    def _classify(self, experiment) -> ExperimentClassification:
        """Classify the experiment via the shared classifier (best effort)."""
        try:
            classifier = ExperimentClassifier()
            result = classifier.classify_from_name(getattr(experiment, "experiment_name", "") or "")
            if result and result.type_name:
                return result
        except Exception:
            pass
        # Fallback: derive from assay name keywords (config-driven).
        name_l = (getattr(experiment, "experiment_name", "") or "").lower()
        assays = self._assay_registry()
        for key, cfg in assays.items():
            for kw in cfg.get("name_keywords") or []:
                if kw and kw.lower() in name_l:
                    return ExperimentClassification(
                        type_name=key,
                        assay_template=f"{key}_assay.json",
                        confidence=0.5,
                        detected_keywords=[key],
                        detected_files=[],
                    )
        default_key = self._default_assay_key()
        return ExperimentClassification(
            type_name=default_key,
            assay_template=f"{default_key}_assay.json",
            confidence=0.3,
            detected_keywords=[],
            detected_files=[],
        )

    def _process_experiment(self, experiment) -> StudyResult:
        """Process a single experiment folder into a complete study."""
        study_id = self._generate_study_id(experiment)
        result = StudyResult(success=False, study_id=study_id)

        try:
            exp_type = self._classify(experiment)
            assay_types = self._determine_assay_types(experiment, exp_type)
            result.assay_type = "/".join(assay_types.keys())

            # FCS acquisition summary (optional enrichment).
            self._fcs_summary = self._extract_fcs_summary(experiment)

            # Study, materials, assays.
            study_data = self._create_study(experiment, study_id, exp_type)
            self._register_study_factors(study_data, experiment)

            material_manager = MaterialManager(
                study_data=study_data,
                directory_manager=self.dm,
                investigation_id=self.investigation_id,
                study_id=study_id,
            )
            source_id, sample_ids = self._create_materials(
                study_data, material_manager, experiment, exp_type
            )
            result.materials_created = 1 + len(sample_ids)

            assays = self._create_assays(study_data, assay_types, sample_ids, experiment)
            result.assays_created = len(assays)

            # Files -> assays.
            result.files_linked = self._assign_files_to_assays(
                study_data, experiment, list(assay_types.keys())
            )

            # Per-sample processes (maps files to samples).
            self._build_per_sample_processes(
                study_data, assays, study_data["materials"]["samples"], study_id
            )

            # Study-level sample-collection process.
            self._create_study_process_sequence(study_data, None, source_id, sample_ids)

            # Description enrichment.
            meas = assays[0].get("measurementType", {}) if assays else {}
            self._update_study_description(
                study_data,
                experiment,
                self._determine_cell_type(experiment),
                meas,
                sample_ids,
            )

            # Internal validation (optional).
            if self.validate:
                errors = self._internal_validate(study_data)
                if errors:
                    result.warnings.extend(errors)

            # Export.
            self._export_study_json(study_data, study_id)

            result.success = True
            result.warnings = list(result.warnings)
        except Exception as exc:  # noqa: BLE001 - report and continue
            logger.exception("Failed to process experiment %s", study_id)
            result.errors.append(str(exc))

        return result

    def _extract_fcs_summary(self, experiment) -> Dict[str, Any]:
        """Build the per-experiment FCS acquisition summary (best effort).

        Uses :class:`utils.batch.metadata_extractor.MetadataExtractor` when
        the folder contains FCS files; otherwise returns an empty dict.
        """
        folder_path = getattr(experiment, "folder_path", None)
        if not folder_path or not Path(folder_path).is_dir():
            return {}
        fcs = [p for p in Path(folder_path).rglob("*") if p.suffix.lower() == ".fcs"]
        if not fcs:
            return {}
        try:
            from utils.batch.metadata_extractor import MetadataExtractor

            return MetadataExtractor().extract_fcs_acquisition_summary(str(folder_path)) or {}
        except Exception:
            logger.debug("FCS summary extraction failed", exc_info=True)
            return {}

    # ── Batch ─────────────────────────────────────────────────────────────

    def _discover_experiments(self) -> List[FolderMetadata]:
        """Discover experiment folders under ``data_root``."""
        from utils.batch.folder_scanner import FolderScanner

        if not self.data_root or not self.data_root.is_dir():
            return []
        scanner = FolderScanner(str(self.data_root))
        experiments = scanner.scan_experiments()
        return [e for e in experiments if e.experiment_name]

    def process_all(self) -> BatchResult:
        """Process all experiment folders under ``data_root``."""
        batch = BatchResult()
        experiments = self._discover_experiments()
        batch.total_experiments = len(experiments)

        for experiment in experiments:
            try:
                files = [p.name for p in Path(experiment.folder_path).rglob("*") if p.is_file()]
            except OSError:
                files = []
            batch.total_files += len(files)

            sr = self._process_experiment(experiment)
            batch.study_results.append(sr)
            if sr.success:
                batch.successful += 1
                batch.total_files_linked += sr.files_linked
                batch.warnings.extend(sr.warnings)
            else:
                batch.failed += 1
                batch.validation_errors.extend(sr.errors)

        return batch


# ── CLI ────────────────────────────────────────────────────────────────────


def main(argv: Optional[List[str]] = None) -> int:
    """Command-line entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Batch-convert experiment folders into ISA-JSON studies."
    )
    parser.add_argument("--data-root", required=True, help="Root folder of experiments")
    parser.add_argument("--investigation-id", default="inv_001")
    parser.add_argument("--base-path", default=None, help="Base path for investigations output")
    parser.add_argument("--skip-conversion", action="store_true", default=True)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    processor = ExperimentProcessor(
        data_root=args.data_root,
        investigation_id=args.investigation_id,
        base_path=args.base_path,
        skip_conversion=args.skip_conversion,
        validate=args.validate,
        verbose=args.verbose,
    )
    result = processor.process_all()
    print(
        f"Processed {result.total_experiments} experiments: "
        f"{result.successful} ok, {result.failed} failed, "
        f"{result.total_files_linked}/{result.total_files} files linked"
    )
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
