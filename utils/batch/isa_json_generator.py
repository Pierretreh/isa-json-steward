"""
ISA-JSON Generator for creating ISA-JSON files from experiment metadata.

This module generates ISA-JSON format files from extracted experiment metadata,
following the ISA-JSON specification for FAIR data representation.

Domain-specific knowledge (protein names, drug names, cell-type mappings,
people, investigation defaults) is loaded from the active profile via
:func:`utils.config_loader.get_profile`, making the generator reusable
for any project.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

from utils.batch.experiment_classifier import ExperimentClassification, ExperimentClassifier
from utils.batch.folder_scanner import FileInventory, FolderMetadata
from utils.config_loader import get_profile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Ontology term constants ──────────────────────────────────────────────────

ONTOLOGY = {
    "organism_human": {
        "annotationValue": "Homo sapiens",
        "termSource": "NCBITaxon",
        "termAccession": "http://purl.obolibrary.org/obo/NCBITaxon_9606",
    },
    "organism_rat": {
        "annotationValue": "Rattus norvegicus",
        "termSource": "NCBITaxon",
        "termAccession": "http://purl.obolibrary.org/obo/NCBITaxon_10116",
    },
    "organism_mouse": {
        "annotationValue": "Mus musculus",
        "termSource": "NCBITaxon",
        "termAccession": "http://purl.obolibrary.org/obo/NCBITaxon_10090",
    },
    "cell_type": {
        "annotationValue": "cell type",
        "termSource": "CL",
        "termAccession": "http://purl.obolibrary.org/obo/CL_0000000",
    },
    "muller_cell": {
        "annotationValue": "Muller cell",
        "termSource": "CL",
        "termAccession": "http://purl.obolibrary.org/obo/CL_0000636",
    },
    "retinal_explant": {
        "annotationValue": "retinal explant",
        "termSource": "UBERON",
        "termAccession": "http://purl.obolibrary.org/obo/UBERON_0000966",
    },
    "hrmvec": {
        "annotationValue": "human retinal microvascular endothelial cell",
        "termSource": "CL",
        "termAccession": "http://purl.obolibrary.org/obo/CL_0002542",
    },
    "organism_part": {
        "annotationValue": "organism part",
        "termSource": "OBI",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0100026",
    },
    "retina": {
        "annotationValue": "retina",
        "termSource": "UBERON",
        "termAccession": "http://purl.obolibrary.org/obo/UBERON_0000966",
    },
    "protein_variant": {
        "annotationValue": "protein variant",
        "termSource": "CHEBI",
        "termAccession": "http://purl.obolibrary.org/obo/CHEBI_36080",
    },
    "concentration": {
        "annotationValue": "concentration",
        "termSource": "PATO",
        "termAccession": "http://purl.obolibrary.org/obo/PATO_0000033",
    },
    "treatment_compound": {
        "annotationValue": "chemical substance",
        "termSource": "CHEBI",
        "termAccession": "http://purl.obolibrary.org/obo/CHEBI_59999",
    },
    "micromolar": {
        "annotationValue": "micromolar",
        "termSource": "UO",
        "termAccession": "http://purl.obolibrary.org/obo/UO_0000026",
    },
    "intervention_design": {
        "annotationValue": "intervention design",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000115",
        "termSource": "OBI",
    },
    "assay": {
        "annotationValue": "assay",
        "termSource": "OBI",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000070",
    },
    "sample_collection": {
        "annotationValue": "sample collection",
        "termSource": "OBI",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000659",
    },
    "specimen_collection": {
        "annotationValue": "specimen collection",
        "termSource": "OBI",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000659",
    },
    "data_acquisition": {
        "annotationValue": "data acquisition",
        "termSource": "OBI",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000900",
    },
    "flow_cytometry_assay": {
        "annotationValue": "flow cytometry assay",
        "termSource": "OBI",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000715",
    },
    "flow_cytometry": {
        "annotationValue": "flow cytometry",
        "termSource": "OBI",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000452",
    },
    "fluorescence_microscopy": {
        "annotationValue": "fluorescence microscopy",
        "termSource": "OBI",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000456",
    },
    "cell_viability": {
        "annotationValue": "cell viability measurement",
        "termSource": "OBI",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000916",
    },
    "histology": {
        "annotationValue": "histology assay",
        "termSource": "OBI",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0001630",
    },
    "whole_slide_imaging": {
        "annotationValue": "whole slide imaging",
        "termSource": "OBI",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0003082",
    },
    "calcein_assay": {
        "annotationValue": "calcein viability assay",
        "termSource": "OBI",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000916",
    },
    "fluorescence_measurement": {
        "annotationValue": "fluorescence measurement",
        "termSource": "OBI",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000916",
    },
    "image_analysis": {
        "annotationValue": "image analysis",
        "termSource": "OBI",
        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000752",
    },
}

# ---------------------------------------------------------------------------
# Domain-specific lookups – delegated to the active profile
# ---------------------------------------------------------------------------


def _get_cell_type_map() -> Dict[str, str]:
    """Cell/tissue type mapping from folder name keywords.

    Loaded from the active profile's ``experiment_patterns`` configuration.
    """
    return get_profile().get_cell_type_map()


def _get_assay_type_map() -> Dict[str, List[str]]:
    """Assay type info: maps folder keywords to
    [measurement_type_key, technology_type_key, protocol_name].

    Loaded from the active profile's ``experiment_patterns`` configuration.
    """
    return get_profile().get_assay_type_map()


def _get_protein_names() -> Dict[str, str]:
    """Known protein name mappings.

    Loaded from the active profile's ``protein_names`` configuration.
    """
    return get_profile().get_protein_name_map()


def _get_drug_names() -> Dict[str, str]:
    """Known drug name mappings.

    Loaded from the active profile's ``protein_names`` configuration.
    """
    return get_profile().get_drug_name_map()


@dataclass
class ISAMaterial:
    """Represents a material in ISA-JSON (source, sample, or other material)."""

    material_id: str
    material_type: str  # 'source', 'sample', 'other_material'
    name: str
    characteristics: List[Dict[str, Any]] = field(default_factory=list)
    factor_values: List[Dict[str, Any]] = field(default_factory=list)
    derives_from: Optional[str] = None


@dataclass
class ISAProcess:
    """Represents a process in ISA-JSON."""

    process_id: str
    executes_protocol: str
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    parameter_values: List[Dict[str, Any]] = field(default_factory=list)
    comments: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ISAAssay:
    """Represents an assay in ISA-JSON."""

    assay_id: str
    assay_name: str
    measurement_type: Dict[str, str]
    technology_type: Dict[str, str]
    technology_platform: str = ""
    data_files: List[Dict[str, Any]] = field(default_factory=list)
    materials: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    process_sequence: List[ISAProcess] = field(default_factory=list)
    characteristic_categories: List[Dict[str, Any]] = field(default_factory=list)
    unit_categories: List[Dict[str, Any]] = field(default_factory=list)
    comments: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ISAStudy:
    """Represents a study in ISA-JSON."""

    study_id: str
    study_name: str
    study_title: str
    study_description: str
    submission_date: str
    public_release_date: str
    assays: List[ISAAssay] = field(default_factory=list)
    materials: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    protocols: List[Dict[str, Any]] = field(default_factory=list)
    process_sequence: List[ISAProcess] = field(default_factory=list)
    characteristic_categories: List[Dict[str, Any]] = field(default_factory=list)
    study_design_descriptors: List[Dict[str, str]] = field(default_factory=list)
    factors: List[Dict[str, Any]] = field(default_factory=list)
    unit_categories: List[Dict[str, Any]] = field(default_factory=list)
    people: List[Dict[str, Any]] = field(default_factory=list)
    publications: List[Dict[str, Any]] = field(default_factory=list)
    comments: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ISAInvestigation:
    """Represents an investigation in ISA-JSON."""

    investigation_id: str
    investigation_title: str
    investigation_description: str
    investigation_abstract: str
    submission_date: str
    public_release_date: str
    studies: List[ISAStudy] = field(default_factory=list)
    ontology_source_references: List[Dict[str, str]] = field(default_factory=list)
    people: List[Dict[str, Any]] = field(default_factory=list)
    publications: List[Dict[str, Any]] = field(default_factory=list)
    comments: List[Dict[str, str]] = field(default_factory=list)


class ISAJsonGenerator:
    """Generator for ISA-JSON files from experiment metadata."""

    def __init__(self, templates_root: str = "templates/assay_templates"):
        """
        Initialize the ISA-JSON generator.

        Args:
            templates_root: Root directory for assay templates
        """
        self.templates_root = templates_root
        self.classifier = ExperimentClassifier(templates_root)
        self.logger = logging.getLogger(__name__)

        # Standard ontology sources
        self.ontology_sources = {
            "OBI": "http://purl.obolibrary.org/obo/obi.owl",
            "CHEBI": "http://purl.obolibrary.org/obo/chebi.owl",
            "UO": "http://purl.obolibrary.org/obo/uo.owl",
            "NCBITaxon": "http://purl.obolibrary.org/obo/ncbitaxon.owl",
            "EFO": "http://www.ebi.ac.uk/efo/efo.owl",
            "CL": "http://purl.obolibrary.org/obo/cl.owl",
            "UBERON": "http://purl.obolibrary.org/obo/uberon.owl",
            "PATO": "http://purl.obolibrary.org/obo/pato.owl",
        }

    # ── Parameter extraction ─────────────────────────────────────────────

    def _extract_experiment_metadata(self, folder_name: str) -> Dict[str, Any]:
        """
        Extract comprehensive metadata from an experiment folder name.

        Parses the naming convention: E{id}_{CellType}_{AssayType}_{Compounds}_{Conditions}

        Args:
            folder_name: Experiment folder name

        Returns:
            Dictionary with extracted metadata
        """
        meta: Dict[str, Any] = {
            "experiment_id": "",
            "cell_types": [],
            "assay_types": [],
            "protein_variants": [],
            "drugs": [],
            "concentrations": [],
            "concentrations_raw": [],
            "time_points_hours": [],
            "sample_counts": [],
            "controls": [],
            "organism": "human",
        }

        name_lower = folder_name.lower()

        # Extract experiment ID (E1, E10, E101, etc.)
        exp_id_match = re.match(r"^E(\d+)", folder_name)
        if exp_id_match:
            meta["experiment_id"] = f"E{exp_id_match.group(1)}"

        # Extract cell/tissue types
        for keyword, cell_key in _get_cell_type_map().items():
            if keyword in folder_name:
                meta["cell_types"].append(cell_key)

        # Extract assay types from folder name keywords
        for keyword in [
            "calceinassay",
            "calcein",
            "facs",
            "slidescanner",
            "fluoreszenzmessung",
            "dapi",
            "tunel",
            "gfap",
            "elisa",
            "wb",
            "western",
        ]:
            if keyword in name_lower:
                if keyword == "calceinassay":
                    meta["assay_types"].append("calcein")
                elif keyword == "western":
                    meta["assay_types"].append("wb")
                elif keyword not in meta["assay_types"]:
                    meta["assay_types"].append(keyword)

        # Extract protein variants (pVV019, pVV021, pVV048, etc.)
        protein_variants = re.findall(r"pVV\d+", folder_name, re.IGNORECASE)
        if protein_variants:
            meta["protein_variants"] = list(set(protein_variants))

        # Extract known drug/treatment names
        for drug_key in _get_drug_names():
            if drug_key.lower() in name_lower:
                meta["drugs"].append(drug_key)

        # Check for "cleav" / "gecleaved" keywords
        if "cleav" in name_lower or "gecleav" in name_lower:
            if "cleaved protein" not in meta["protein_variants"]:
                meta["protein_variants"].append("cleaved protein")

        # Extract concentrations (e.g., "0,5 zu 4uM", "50uM", "50,100,150uM")
        conc_patterns = re.findall(r"(\d+(?:[,.]\d+)?)\s*(?:zu\s*)?uM", folder_name, re.IGNORECASE)
        if conc_patterns:
            meta["concentrations_raw"] = conc_patterns
            meta["concentrations"] = [float(c.replace(",", ".")) for c in conc_patterns]

        # Extract sample counts (n=1, n=2, etc.)
        sample_counts = re.findall(r"n\s*=\s*(\d+)", folder_name, re.IGNORECASE)
        if sample_counts:
            meta["sample_counts"] = [int(n) for n in sample_counts]

        # Extract time points (48h, 6h, 24h, etc.)
        time_points = re.findall(r"(\d+)h", folder_name, re.IGNORECASE)
        if time_points:
            meta["time_points_hours"] = [int(t) for t in time_points]

        # Extract control references
        if "Control" in folder_name or "Ctrl" in folder_name:
            meta["controls"].append("control")
        if "negativ" in folder_name:
            meta["controls"].append("negative")
        if "positiv" in folder_name:
            meta["controls"].append("positive")

        # Default assay type if none detected
        if not meta["assay_types"]:
            meta["assay_types"].append("microscopy")

        # Default cell type if none detected
        if not meta["cell_types"]:
            meta["cell_types"].append("unknown")

        return meta

    def _build_study_description(
        self, exp_id: str, meta: Dict[str, Any], folder_name: str
    ) -> Tuple[str, str]:
        """
        Build a descriptive title and description from extracted metadata.

        Returns:
            Tuple of (title, description)
        """
        parts = []

        # Cell type
        cell_names = {
            "muller_cell": "Müller glial cells",
            "retinal_explant": "retinal explant cultures",
            "hrmvec": "human retinal microvascular endothelial cells (HRMVEC)",
            "unknown": "biological samples",
        }
        cell_str = " and ".join(cell_names.get(ct, ct) for ct in meta["cell_types"])
        parts.append(cell_str)

        # Assay types
        assay_names = {
            "calcein": "Calcein AM viability assay",
            "facs": "fluorescence-activated cell sorting (FACS) analysis",
            "slidescanner": "whole-slide scanning microscopy",
            "fluoreszenzmessung": "fluorescence measurement",
            "dapi": "DAPI staining and flow cytometry",
            "tunel": "TUNEL staining for apoptosis detection",
            "gfap": "GFAP immunohistochemistry staining",
            "elisa": "ELISA immunoassay",
            "wb": "Western blot analysis",
            "microscopy": "microscopy",
        }
        assay_strs = [assay_names.get(a, a) for a in meta["assay_types"]]

        # Treatment info
        treatments = []
        protein_names = _get_protein_names()
        drug_names = _get_drug_names()
        for pv in meta["protein_variants"]:
            label = protein_names.get(pv, pv)
            treatments.append(label)
        for drug in meta["drugs"]:
            label = drug_names.get(drug, drug)
            if label not in treatments:
                treatments.append(label)

        treatment_str = ""
        if treatments:
            treatment_str = f" with treatments: {', '.join(treatments)}"
            if meta["concentrations"]:
                conc_str = ", ".join(f"{c} µM" for c in meta["concentrations"])
                treatment_str += f" at concentrations {conc_str}"

        assay_part = assay_strs[0] if len(assay_strs) == 1 else "Multi-assay analysis"
        title = f"{exp_id}: {assay_part} on {cell_str}{treatment_str}"

        defaults = get_profile().get_investigation_defaults()
        project_name = defaults.get("project_name", "")
        desc_template = defaults.get(
            "study_description_template",
            "This study covers experiment {exp_id}.",
        )
        desc_parts = [
            desc_template.format(exp_id=exp_id, project_name=project_name),
            f"Biological material: {cell_str}.",
            f"Assays performed: {'; '.join(assay_strs)}.",
        ]
        if treatments:
            desc_parts.append(f"Treatments tested: {', '.join(treatments)}.")
        if meta["concentrations"]:
            desc_parts.append(
                f"Concentrations: {', '.join(f'{c} µM' for c in meta['concentrations'])}."
            )
        if meta["time_points_hours"]:
            desc_parts.append(
                f"Time points: {', '.join(f'{t}h' for t in meta['time_points_hours'])}."
            )
        if meta["sample_counts"]:
            desc_parts.append(
                f"Biological replicates: {', '.join(f'n={n}' for n in meta['sample_counts'])}."
            )
        if meta["controls"]:
            desc_parts.append(f"Controls included: {', '.join(meta['controls'])}.")

        description = " ".join(desc_parts)

        return title, description

    # ── Study generation ─────────────────────────────────────────────────

    def generate_study(self, experiment_path, investigation_id: str, study_id: str) -> ISAStudy:
        """
        Generate an ISA study from an experiment path.

        Args:
            experiment_path: Path to the experiment directory
            investigation_id: Investigation identifier
            study_id: Study identifier

        Returns:
            ISAStudy object
        """
        from utils.batch.folder_scanner import FolderScanner

        path = Path(experiment_path) if not isinstance(experiment_path, Path) else experiment_path

        # Create FolderMetadata from path
        scanner = FolderScanner(str(path.parent))
        metadata = scanner._extract_folder_metadata(path)
        if metadata is None:
            metadata = FolderMetadata(
                experiment_id=study_id, experiment_name=path.name, folder_path=str(path)
            )

        # Extract rich metadata from folder name
        exp_meta = self._extract_experiment_metadata(metadata.experiment_name or path.name)

        # Build title and description
        title, description = self._build_study_description(
            exp_meta["experiment_id"], exp_meta, path.name
        )

        # Build characteristic categories, units, factors
        char_categories, unit_categories, factors = self._build_study_ontology(exp_meta)

        # Build source materials with characteristics
        sources = self._build_sources(exp_meta)

        # Build sample materials
        samples = self._build_samples(exp_meta, sources)

        # Build study-level process: source → sample collection → sample
        study_processes, study_protocols = self._build_study_process_sequence(
            exp_meta, sources, samples
        )

        # Create study
        study = ISAStudy(
            study_id=study_id,
            study_name=path.name,
            study_title=title,
            study_description=description,
            submission_date=datetime.now().strftime("%Y-%m-%d"),
            public_release_date="",
            materials={
                "sources": sources,
                "samples": samples,
                "otherMaterials": [],
            },
            protocols=study_protocols,
            process_sequence=study_processes,
            characteristic_categories=char_categories,
            study_design_descriptors=[ONTOLOGY["intervention_design"]],
            factors=factors,
            unit_categories=unit_categories,
            people=self._get_study_people(),
            publications=[],
            comments=[
                {"name": "Experiment ID", "value": exp_meta["experiment_id"]},
                {"name": "Original folder name", "value": path.name},
                {"name": "Cell types detected", "value": ", ".join(exp_meta["cell_types"])},
                {"name": "Assay types detected", "value": ", ".join(exp_meta["assay_types"])},
            ],
        )

        # Create assays from experiment - one per detected assay type
        for assay_type_key in exp_meta["assay_types"]:
            assay = self._create_assay_from_experiment(metadata, exp_meta, assay_type_key)
            study.assays.append(assay)

        # If no assays were created, create a default one
        if not study.assays:
            assay = self._create_assay_from_experiment(metadata, exp_meta, "microscopy")
            study.assays.append(assay)

        return study

    def generate_assay(
        self,
        assay_id: str,
        assay_name: str,
        measurement_type: Dict[str, str],
        technology_type: Dict[str, str],
    ) -> ISAAssay:
        """
        Generate an ISA assay.

        Args:
            assay_id: Assay identifier
            assay_name: Assay name
            measurement_type: Measurement type annotation
            technology_type: Technology type annotation

        Returns:
            ISAAssay object
        """
        return ISAAssay(
            assay_id=assay_id,
            assay_name=assay_name,
            measurement_type=measurement_type,
            technology_type=technology_type,
        )

    def create_material_node(self, material_id: str, material_type: str, name: str) -> ISAMaterial:
        """
        Create a material node.

        Args:
            material_id: Material identifier
            material_type: Type of material ('source', 'sample', 'other_material')
            name: Material name

        Returns:
            ISAMaterial object
        """
        return ISAMaterial(material_id=material_id, material_type=material_type, name=name)

    def create_process_node(self, process_id: str, executes_protocol: str) -> ISAProcess:
        """
        Create a process node.

        Args:
            process_id: Process identifier
            executes_protocol: Protocol reference

        Returns:
            ISAProcess object
        """
        return ISAProcess(process_id=process_id, executes_protocol=executes_protocol)

    # ── Investigation generation ─────────────────────────────────────────

    def generate_investigation(
        self,
        experiments,
        investigation_id: str,
        investigation_title: str,
        investigation_description: str,
    ) -> ISAInvestigation:
        """
        Generate an ISA investigation from a list of experiments.

        Args:
            experiments: List of experiment metadata (FolderMetadata or Path objects)
            investigation_id: Investigation identifier
            investigation_title: Investigation title
            investigation_description: Investigation description

        Returns:
            ISAInvestigation object
        """
        # Convert Path objects to FolderMetadata if needed
        from utils.batch.folder_scanner import FolderScanner

        processed_experiments = []
        for exp in experiments:
            if isinstance(exp, Path):
                scanner = FolderScanner(str(exp.parent))
                metadata = scanner._extract_folder_metadata(exp)
                if metadata is None:
                    metadata = FolderMetadata(
                        experiment_id=exp.name, experiment_name=exp.name, folder_path=str(exp)
                    )
                processed_experiments.append(metadata)
            elif isinstance(exp, str):
                path = Path(exp)
                scanner = FolderScanner(str(path.parent))
                metadata = scanner._extract_folder_metadata(path)
                if metadata is None:
                    metadata = FolderMetadata(
                        experiment_id=path.name, experiment_name=path.name, folder_path=str(path)
                    )
                processed_experiments.append(metadata)
            else:
                processed_experiments.append(exp)

        # Group experiments by study (based on protein variant/cell type)
        studies = self._group_experiments_into_studies(processed_experiments)

        # Store studies on instance so _get_ontology_source_references can
        # scan them for actually-used termSource values.
        self._all_studies = studies

        # Create investigation
        investigation = ISAInvestigation(
            investigation_id=investigation_id,
            investigation_title=investigation_title,
            investigation_description=investigation_description,
            investigation_abstract=investigation_description,
            submission_date=datetime.now().strftime("%Y-%m-%d"),
            public_release_date="",
            studies=studies,
            ontology_source_references=self._get_ontology_source_references(),
            people=self._get_investigation_people(),
            publications=[],
            comments=self._build_investigation_comments(),
        )

        self.logger.info(f"Generated investigation {investigation_id} with {len(studies)} studies")
        return investigation

    def _group_experiments_into_studies(self, experiments: List[FolderMetadata]) -> List[ISAStudy]:
        """
        Create one study per experiment.

        Each experiment folder (E1, E2, E10, etc.) becomes its own ISA study,
        keeping all data and files for that experiment self-contained.

        Args:
            experiments: List of experiment metadata

        Returns:
            List of ISAStudy objects (one per experiment)
        """
        studies = []

        for exp_metadata in experiments:
            # Extract rich metadata from folder name
            exp_meta = self._extract_experiment_metadata(exp_metadata.experiment_name)

            # Create a unique study ID from the experiment ID
            exp_id = exp_metadata.experiment_id
            study_id = f"study_{exp_id}"

            # Build title and description
            title, description = self._build_study_description(
                exp_id, exp_meta, exp_metadata.experiment_name or exp_id
            )

            # Build characteristic categories, units, factors
            char_categories, unit_categories, factors = self._build_study_ontology(exp_meta)

            # Build source materials with characteristics
            sources = self._build_sources(exp_meta)

            # Build sample materials
            samples = self._build_samples(exp_meta, sources)

            # Build study-level process: source → sample collection → sample
            study_processes, study_protocols = self._build_study_process_sequence(
                exp_meta, sources, samples
            )

            study = ISAStudy(
                study_id=study_id,
                study_name=exp_metadata.experiment_name or exp_id,
                study_title=title,
                study_description=description,
                submission_date=datetime.now().strftime("%Y-%m-%d"),
                public_release_date="",
                materials={"sources": [], "samples": [], "otherMaterials": []},
                protocols=[],
                process_sequence=[],
                characteristic_categories=char_categories,
                study_design_descriptors=[
                    {
                        "annotationValue": "intervention design",
                        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000115",
                        "termSource": "OBI",
                    }
                ],
            )

            # Create assays - one per detected assay type
            for assay_type_key in exp_meta["assay_types"]:
                assay = self._create_assay_from_experiment(exp_metadata, exp_meta, assay_type_key)
                study.assays.append(assay)

            if not study.assays:
                assay = self._create_assay_from_experiment(exp_metadata, exp_meta, "microscopy")
                study.assays.append(assay)

            # Promote assay materials to study level (ISA-JSON requires this)
            # Sources
            for src in assay.materials.get("sources", []):
                study.materials["sources"].append(src)
            # Samples (with full definitions at study level)
            for samp in assay.materials.get("samples", []):
                study.materials["samples"].append(samp)
            # Convert assay-level samples to references only
            assay.materials["samples"] = [
                {"@id": s.get("@id", "")} for s in assay.materials.get("samples", [])
            ]

            # Promote assay processes to study-level processSequence
            for proc in assay.process_sequence:
                study.process_sequence.append(proc)

            # Ensure the assay protocol is declared at study level
            # with all parameters used in its processes
            for proc in assay.process_sequence:
                proto_name = proc.executes_protocol
                if proto_name and not any(p.get("name") == proto_name for p in study.protocols):
                    # Collect parameter declarations from process parameterValues
                    protocol_params: List[Dict[str, Any]] = []
                    for pv in proc.parameter_values:
                        cat = pv.get("category", {})
                        param_id = cat.get("@id", "")
                        param_name_obj = cat.get("parameterName", {})
                        if param_id and not any(
                            pp.get("@id") == param_id for pp in protocol_params
                        ):
                            protocol_params.append(
                                {
                                    "@id": param_id,
                                    "parameterName": param_name_obj,
                                }
                            )

                    study.protocols.append(
                        {
                            "@id": f"#protocol/{proto_name}",
                            "name": proto_name,
                            "protocolType": {
                                "annotationValue": "assay",
                                "termSource": "OBI",
                                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000070",
                            },
                            "description": f"Protocol: {proto_name}",
                            "uri": "",
                            "version": "",
                            "parameters": protocol_params,
                            "components": [],
                        }
                    )

            studies.append(study)

        return studies

    def _create_assay_from_experiment(
        self, exp_metadata: FolderMetadata, exp_meta: Dict[str, Any], assay_type_key: str
    ) -> ISAAssay:
        """
        Create an assay from experiment metadata.

        Args:
            exp_metadata: Experiment folder metadata
            exp_meta: Extracted experiment metadata from :meth:`_extract_experiment_metadata`
            assay_type_key: Assay type key (e.g. 'calcein', 'facs', 'microscopy')

        Returns:
            ISAAssay object
        """
        # Build an ExperimentClassification from the assay type key
        template_name = self.classifier.TYPE_TO_TEMPLATE.get(
            assay_type_key, "microscopy_assay.json"
        )
        exp_type = ExperimentClassification(
            type_name=assay_type_key,
            assay_template=template_name,
            confidence=1.0,
            detected_keywords=[assay_type_key],
            detected_files=[],
        )

        # Get template for this assay type
        template_path = self.classifier.suggest_template(exp_type)
        template = self._load_assay_template(template_path)

        # Create assay
        assay_id = f"assay_{exp_metadata.experiment_id}"
        assay_name = f"{assay_type_key} - {exp_metadata.experiment_id}"

        assay = ISAAssay(
            assay_id=assay_id,
            assay_name=assay_name,
            measurement_type=template.get("measurementType", {}),
            technology_type=template.get("technologyType", {}),
            data_files=self._create_data_files(
                exp_metadata.file_inventory or FileInventory(), assay_id, assay_type_key.lower()
            ),
            materials=self._create_assay_materials(exp_meta, template),
            process_sequence=self._create_process_sequence(exp_meta, template),
            comments=[
                {"name": "Experiment ID", "value": exp_metadata.experiment_id},
                {"name": "Experiment Type", "value": assay_type_key},
            ],
        )

        return assay

    def _load_assay_template(self, template_path: str) -> Dict[str, Any]:
        """
        Load an assay template from file.

        Args:
            template_path: Path to template file (may include templates_root prefix)

        Returns:
            Template dictionary
        """
        try:
            # suggest_template() already returns paths prefixed with templates_root
            # (e.g. "templates/assay_templates/calcein_assay.json"), so strip the
            # prefix to avoid double-prefixing.
            path = Path(template_path)
            if (
                path.parts[: len(Path(self.templates_root).parts)]
                == Path(self.templates_root).parts
            ):
                template_file = path
            else:
                template_file = Path(self.templates_root) / template_path
            if template_file.exists():
                with open(template_file, "r", encoding="utf-8") as f:
                    return cast(Dict[str, Any], json.load(f))
        except Exception as e:
            self.logger.warning(f"Could not load template {template_path}: {e}")

        # Return default template
        return {
            "measurementType": {
                "annotationValue": "cell counting",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000916",
                "termSource": "OBI",
            },
            "technologyType": {
                "annotationValue": "flow cytometry",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000916",
                "termSource": "OBI",
            },
            "parameters": [],
            "inputs": [],
            "outputs": [],
        }

    def _create_data_files(
        self, file_inventory: FileInventory, assay_id: str, assay_type_key: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Create data file entries from file inventory, filtered by assay type relevance.

        Args:
            file_inventory: File inventory
            assay_id: Assay ID
            assay_type_key: Assay type key for filtering relevant files (optional)

        Returns:
            List of data file dictionaries
        """
        data_files = []

        # Collect all files
        all_files = []
        for attr_name in file_inventory.__dict__:
            files = getattr(file_inventory, attr_name, [])
            if isinstance(files, list):
                all_files.extend(files)

        # File type relevance mapping
        primary_extensions = {
            "facs": {".fcs", ".wsp"},
            "calcein": {".czi", ".tiff", ".tif", ".xlsx"},
            "slidescanner": {".ndpi", ".tiff", ".tif"},
            "fluoreszenzmessung": {".xlsx", ".czi"},
            "dapi": {".fcs", ".wsp", ".czi"},
            "microscopy": {".czi", ".tiff", ".tif", ".ndpi"},
        }
        secondary_extensions = {
            "facs": {".czi", ".tiff", ".tif", ".xlsx", ".xml"},
            "calcein": {".fcs", ".xml"},
            "slidescanner": {".xlsx", ".xml"},
            "fluoreszenzmessung": {".czi", ".tiff", ".tif"},
            "dapi": {".czi", ".tiff", ".tif"},
            "microscopy": {".xlsx", ".fcs", ".xml"},
        }

        relevant_exts = primary_extensions.get(assay_type_key, set())
        secondary_exts = secondary_extensions.get(assay_type_key, set())

        # If there are files matching primary extensions, only include those + secondary
        has_primary = False
        for file_path in all_files:
            suffix = Path(file_path).suffix.lower()
            if suffix in relevant_exts:
                has_primary = True
                break

        # Include metadata XML files as comments/links, not as separate data files
        metadata_xml_files = []

        file_idx = 0
        for file_path in all_files:
            file_path_obj = Path(file_path)
            suffix = file_path_obj.suffix.lower()

            # Skip metadata XML files - they're annotations, not primary data
            if suffix == ".xml" or "_metadata.xml" in file_path_obj.name:
                metadata_xml_files.append(file_path_obj.name)
                continue

            # Skip sub-image tiff files that are pyramidal tiles
            if "_c0x0-" in file_path_obj.name or "_c1x0-" in file_path_obj.name:
                continue

            # Filter by relevance if we have a known assay type
            if has_primary and assay_type_key:
                if suffix not in relevant_exts and suffix not in secondary_exts:
                    continue

            # Determine file type according to ISA-JSON data schema
            file_type = "Raw Data File"
            if suffix in [".png", ".jpg", ".jpeg", ".tiff", ".tif"]:
                file_type = "Image File"
            elif suffix in [".csv", ".xlsx", ".xls"]:
                file_type = "Derived Data File"
            elif suffix == ".ndpi":
                file_type = "Raw Data File"
            elif suffix == ".fcs":
                file_type = "Raw Data File"
            elif suffix == ".wsp":
                file_type = "Derived Data File"
            elif suffix == ".czi":
                file_type = "Raw Data File"

            file_idx += 1
            file_id = f"#data/{assay_id}_file_{file_idx}"

            # Build comments with metadata info
            comments = [
                {"name": "Original file", "value": "true"},
                {"name": "File format", "value": suffix.lstrip(".")},
            ]

            data_file = {
                "@id": file_id,
                "name": file_path_obj.name,
                "filename": file_path_obj.name,
                "type": file_type,
                "comments": comments,
            }

            data_files.append(data_file)

        return data_files

    def _build_sources(self, exp_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Build source material entries from experiment metadata.

        Creates one source per detected cell type, annotated with organism
        and cell-type characteristics.

        Args:
            exp_meta: Extracted experiment metadata dict

        Returns:
            List of source material dictionaries
        """
        sources = []
        organism_key = f"organism_{exp_meta.get('organism', 'human')}"
        organism_term = ONTOLOGY.get(organism_key, ONTOLOGY["organism_human"])

        for idx, cell_type in enumerate(exp_meta.get("cell_types", []), start=1):
            cell_term = ONTOLOGY.get(cell_type, ONTOLOGY["cell_type"])
            source: Dict[str, Any] = {
                "@id": f"#source/{idx}",
                "name": f"Source_{cell_type}",
                "characteristics": [
                    {
                        "category": {"@id": "#characteristic_category/organism"},
                        "value": organism_term,
                    },
                    {
                        "category": {"@id": "#characteristic_category/cell_type"},
                        "value": cell_term,
                    },
                ],
            }
            sources.append(source)

        # Guarantee at least one source so downstream material chains are valid
        if not sources:
            sources.append(
                {
                    "@id": "#source/1",
                    "name": "Source_unknown",
                    "characteristics": [
                        {
                            "category": {"@id": "#characteristic_category/organism"},
                            "value": organism_term,
                        },
                    ],
                }
            )

        return sources

    def _build_samples(
        self, exp_meta: Dict[str, Any], sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Build sample material entries derived from sources.

        Replicates each source according to the detected sample counts and
        annotates samples with treatment / concentration factor values.

        Args:
            exp_meta: Extracted experiment metadata dict
            sources: Source materials built by :meth:`_build_sources`

        Returns:
            List of sample material dictionaries
        """
        samples: List[Dict[str, Any]] = []
        sample_counts = exp_meta.get("sample_counts") or [1]
        sample_count = max(sample_counts) if sample_counts else 1

        for src_idx, source in enumerate(sources):
            for rep in range(sample_count):
                sample_num = src_idx * sample_count + rep + 1
                sample: Dict[str, Any] = {
                    "@id": f"#sample/{sample_num}",
                    "name": f"Sample_{source.get('name', 'unknown')}_{rep + 1}",
                    "characteristics": [],
                    "derivesFrom": {"@id": source.get("@id", "")},
                }

                # Add protein-variant factor values
                for pv in exp_meta.get("protein_variants", []):
                    sample["factorValues"] = sample.get("factorValues", [])
                    sample["factorValues"].append(
                        {
                            "category": {"@id": "#factor/treatment_compound"},
                            "value": {"annotationValue": pv},
                        }
                    )

                # Add concentration factor values
                for conc in exp_meta.get("concentrations", []):
                    sample.setdefault("factorValues", []).append(
                        {
                            "category": {"@id": "#factor/concentration"},
                            "value": {
                                "annotationValue": str(conc),
                                "unit": ONTOLOGY["micromolar"],
                            },
                        }
                    )

                samples.append(sample)

        # Guarantee at least one sample
        if not samples and sources:
            samples.append(
                {
                    "@id": "#sample/1",
                    "name": f"Sample_{sources[0].get('name', 'unknown')}_1",
                    "characteristics": [],
                    "derivesFrom": {"@id": sources[0].get("@id", "")},
                }
            )

        return samples

    def _build_study_process_sequence(
        self,
        exp_meta: Dict[str, Any],
        sources: List[Dict[str, Any]],
        samples: List[Dict[str, Any]],
    ) -> Tuple[List[ISAProcess], List[Dict[str, Any]]]:
        """
        Build a study-level sample-collection process linking sources → samples.

        Args:
            exp_meta: Extracted experiment metadata dict
            sources: Source materials
            samples: Sample materials (derived from sources)

        Returns:
            Tuple of (process_sequence, protocols)
        """
        protocols: List[Dict[str, Any]] = [
            {
                "@id": "#protocol/sample_collection",
                "name": "sample collection",
                "protocolType": {
                    "annotationValue": "sample collection",
                    "termSource": "OBI",
                    "termAccession": "http://purl.obolibrary.org/obo/OBI_0000659",
                },
                "description": "Collection of samples from source materials",
                "uri": "",
                "version": "",
                "parameters": [],
                "components": [],
            }
        ]

        process = ISAProcess(
            process_id="#process/sample_collection_1",
            executes_protocol="sample collection",
            inputs=[{"@id": s.get("@id", "")} for s in sources],
            outputs=[{"@id": s.get("@id", "")} for s in samples],
        )

        return [process], protocols

    def _build_study_ontology(
        self, exp_meta: Dict[str, Any]
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """
        Build characteristic categories, unit categories, and factors for a study.

        Returns:
            Tuple of (characteristic_categories, unit_categories, factors)
        """
        char_categories = [
            {
                "@id": "#characteristic_category/organism",
                "characteristicType": {
                    "annotationValue": "Organism",
                    "termSource": "OBI",
                    "termAccession": "http://purl.obolibrary.org/obo/OBI_0100026",
                },
            },
            {
                "@id": "#characteristic_category/cell_type",
                "characteristicType": ONTOLOGY["cell_type"],
            },
            {
                "@id": "#characteristic_category/organism_part",
                "characteristicType": {
                    "annotationValue": "organism part",
                    "termSource": "OBI",
                    "termAccession": "http://purl.obolibrary.org/obo/OBI_0100026",
                },
            },
        ]

        unit_categories = [
            ONTOLOGY["micromolar"],
        ]

        factors = [
            {
                "@id": "#factor/treatment_compound",
                "factorName": "treatment compound",
                "factorType": ONTOLOGY["treatment_compound"],
            },
        ]

        if exp_meta.get("concentrations"):
            factors.append(
                {
                    "@id": "#factor/concentration",
                    "factorName": "concentration",
                    "factorType": ONTOLOGY["concentration"],
                }
            )

        return char_categories, unit_categories, factors

    def _create_assay_materials(
        self, params: Dict[str, Any], template: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Create an assay from experiment metadata for a specific assay type.

        Args:
            params: Extracted parameters
            template: Assay template

        Returns:
            Dictionary of materials
        """
        materials: Dict[str, List[Dict[str, Any]]] = {
            "sources": [],
            "samples": [],
            "otherMaterials": [],
        }

        # Create sample from parameters
        sample = {
            "name": params.get("sample_name", f"Sample_{params.get('protein_variant', 'unknown')}"),
            "characteristics": [],
        }

        # Add protein variant characteristic
        if "protein_variant" in params:
            sample["characteristics"].append(
                {
                    "category": {"annotationValue": "protein variant", "termSource": "CHEBI"},
                    "value": {"annotationValue": params["protein_variant"], "termSource": "CHEBI"},
                }
            )

        # Add cell type characteristic
        if "cell_type" in params:
            sample["characteristics"].append(
                {
                    "category": {"annotationValue": "cell type", "termSource": "CL"},
                    "value": {"annotationValue": params["cell_type"], "termSource": "CL"},
                }
            )

        # Add concentration characteristic
        if "concentration" in params:
            sample["characteristics"].append(
                {
                    "category": {"annotationValue": "concentration", "termSource": "UO"},
                    "value": {
                        "annotationValue": str(params["concentration"]),
                        "unit": {
                            "annotationValue": "micromolar",
                            "termAccession": "http://purl.obolibrary.org/obo/UO_0000026",
                            "termSource": "UO",
                        },
                    },
                }
            )

        materials["samples"].append(sample)

        # Add other materials from template inputs
        for input_item in template.get("inputs", []):
            materials["otherMaterials"].append(
                {"name": input_item.get("name", "unknown"), "characteristics": []}
            )

        return materials

    def _extract_parameter_values(
        self, exp_meta: Dict[str, Any], template: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract parameter values from experiment metadata, matching template parameters.

        For each parameter defined in the assay template, this method:
        1. Tries to find a matching value in the extracted experiment metadata
        2. Falls back to the template's defaultValue if available
        3. Skips the parameter if no value can be determined

        Args:
            exp_meta: Extracted experiment metadata from :meth:`_extract_experiment_metadata`
            template: Loaded assay template dictionary

        Returns:
            List of ISA-JSON parameterValue dicts
        """
        param_values: List[Dict[str, Any]] = []

        # Mapping from template parameter names to exp_meta keys
        PARAM_META_MAP = {
            "cell type": "cell_types",
            "cell line": "cell_types",
            "tissue type": "cell_types",
            "tissue source": "cell_types",
            "target protein": "protein_variants",
            "incubation time": "time_points_hours",
            "sample incubation time": "time_points_hours",
            "induction time": "time_points_hours",
            "calcein concentration": "concentrations",
            "stain concentration": "concentrations",
            "sample concentration": "concentrations",
            "coating concentration": "concentrations",
            "primary antibody concentration": "concentrations",
            "secondary antibody concentration": "concentrations",
            "DAPI concentration": "concentrations",
            "TdT enzyme concentration": "concentrations",
            "primer concentration": "concentrations",
        }

        for template_param in template.get("parameters", []):
            param_name = template_param.get("name", "")
            default_value = template_param.get("defaultValue", "")
            _unit_info = template_param.get("unit")  # noqa: F841

            value = None

            # 1. Try to match from experiment metadata
            meta_key = PARAM_META_MAP.get(param_name)
            if meta_key and exp_meta.get(meta_key):
                meta_val = exp_meta[meta_key]
                if isinstance(meta_val, list) and meta_val:
                    # Join list values; for concentrations/time use first value
                    if meta_key in ("concentrations", "time_points_hours"):
                        value = str(meta_val[0])
                        # Append unit suffix for time points
                        if meta_key == "time_points_hours":
                            value = f"{meta_val[0]} h"
                    else:
                        value = ", ".join(str(v) for v in meta_val)
                elif isinstance(meta_val, str) and meta_val:
                    value = meta_val

            # 2. Fall back to template default value (skip empty strings)
            if value is None and default_value not in ("", None):
                value = default_value

            # 3. Skip parameters with no value
            if value is None:
                continue

            param_entry: Dict[str, Any] = {
                "category": {
                    "@id": f"#parameter/{param_name.replace(' ', '_')}",
                    "parameterName": {
                        "annotationValue": param_name,
                    },
                },
                "value": {
                    "annotationValue": str(value),
                },
            }

            param_values.append(param_entry)

        return param_values

    def _create_process_sequence(
        self, params: Dict[str, Any], template: Dict[str, Any]
    ) -> List[ISAProcess]:
        """
        Create process sequence for an assay.

        Args:
            params: Extracted parameters (exp_meta)
            template: Assay template

        Returns:
            List of ISAProcess objects
        """
        processes = []

        # Build parameter values from template parameters and extracted metadata
        param_values = self._extract_parameter_values(params, template)

        # Create a process for the assay
        assay_measurement = template.get("measurementType", {}).get("annotationValue", "unknown")
        process = ISAProcess(
            process_id="#process/assay_process_1",
            executes_protocol=f"#protocol/{assay_measurement.replace(' ', '_').lower()}",
            parameter_values=param_values,
            comments=[{"name": "Assay type", "value": assay_measurement}],
        )

        processes.append(process)

        return processes

    # ── People ───────────────────────────────────────────────────────────

    @staticmethod
    def _format_people(people_raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert profile people entries to ISA-JSON person format.

        The profile stores names in ``first_name`` / ``last_name`` (snake_case);
        ISA-JSON requires ``firstName`` / ``lastName`` (camelCase) and an
        ``@id`` field.

        Args:
            people_raw: List of people dicts from the profile.

        Returns:
            List of ISA-JSON-formatted person dicts.
        """
        result: List[Dict[str, Any]] = []
        for person in people_raw:
            first = person.get("first_name", "")
            last = person.get("last_name", "")
            person_id = f"#person/{first.lower()}_{last.lower()}".replace(" ", "_")
            result.append(
                {
                    "@id": person_id,
                    "firstName": first,
                    "lastName": last,
                    "email": person.get("email", ""),
                    "phone": person.get("phone", ""),
                    "address": person.get("address", ""),
                    "affiliation": person.get("affiliation", ""),
                    "roles": person.get("roles", []),
                }
            )
        return result

    def _get_investigation_people(self) -> List[Dict[str, Any]]:
        """Get investigation-level people from the active profile."""
        return self._format_people(get_profile().get_people())

    def _get_study_people(self) -> List[Dict[str, Any]]:
        """Get study-level people from the active profile."""
        return self._format_people(get_profile().get_people())

    # ── Investigation comments ──────────────────────────────────────────

    def _build_investigation_comments(self) -> List[Dict[str, str]]:
        """Build investigation-level comments from the active profile.

        Reads ``investigation_comments`` from the profile's
        ``investigation_defaults`` configuration and appends the
        generation date.
        """
        defaults = get_profile().get_investigation_defaults()
        generator_name = defaults.get("generator_name", "ISA-JSON Generator")
        comments: List[Dict[str, str]] = [
            {"name": "Generated by", "value": generator_name},
            {"name": "Generation date", "value": datetime.now().isoformat()},
        ]
        for key, value in defaults.get("investigation_comments", {}).items():
            comments.append({"name": key, "value": value})
        return comments

    # ── Serialization ────────────────────────────────────────────────────

    def _get_ontology_source_references(self) -> List[Dict[str, str]]:
        """
        Get ontology source references.

        Scans all studies for actually-used termSource values and only
        declares ontology sources that are referenced.  This prevents
        isatools validation warning code 3007 ("ontology source declared
        but not used").

        Returns:
            List of ontology source reference dictionaries
        """
        # Collect all termSource values from all studies
        used_sources: set = set()
        for study in self._all_studies if hasattr(self, "_all_studies") else []:
            self._collect_term_sources_from_study(study, used_sources)

        # Always include OBI and UO as fundamental
        used_sources.add("OBI")
        used_sources.add("UO")

        all_sources = {
            "OBI": {
                "name": "OBI",
                "file": self.ontology_sources.get("OBI", ""),
                "version": "2024-03-01",
                "description": "Ontology for Biomedical Investigations",
            },
            "CHEBI": {
                "name": "CHEBI",
                "file": self.ontology_sources.get("CHEBI", ""),
                "version": "2024-03-01",
                "description": "Chemical Entities of Biological Interest",
            },
            "UO": {
                "name": "UO",
                "file": self.ontology_sources.get("UO", ""),
                "version": "2024-03-01",
                "description": "Units of Measurement Ontology",
            },
            "NCBITaxon": {
                "name": "NCBITaxon",
                "file": self.ontology_sources.get("NCBITaxon", ""),
                "version": "2024-03-01",
                "description": "NCBI Organismal Classification",
            },
            "CL": {
                "name": "CL",
                "file": self.ontology_sources.get("CL", ""),
                "version": "2024-03-01",
                "description": "Cell Ontology",
            },
            "UBERON": {
                "name": "UBERON",
                "file": self.ontology_sources.get("UBERON", ""),
                "version": "2024-03-01",
                "description": "Uberon Multi-Species Anatomy Ontology",
            },
            "PATO": {
                "name": "PATO",
                "file": self.ontology_sources.get("PATO", ""),
                "version": "2024-03-01",
                "description": "Phenotype And Trait Ontology",
            },
            "EFO": {
                "name": "EFO",
                "file": self.ontology_sources.get("EFO", ""),
                "version": "2024-03-01",
                "description": "Experimental Factor Ontology",
            },
        }

        return [all_sources[name] for name in sorted(used_sources) if name in all_sources]

    def _collect_term_sources_from_study(self, study, used: set) -> None:
        """Recursively collect termSource values from a study dict."""
        if isinstance(study, dict):
            # Handle ISAStudy objects
            if hasattr(study, "__dict__"):
                self._collect_term_sources_from_study(study.__dict__, used)
            else:
                ts = study.get("termSource")
                if ts and isinstance(ts, str):
                    used.add(ts)
                for v in study.values():
                    self._collect_term_sources_from_study(v, used)
        elif isinstance(study, list):
            for item in study:
                self._collect_term_sources_from_study(item, used)

    def save_investigation(self, investigation: ISAInvestigation, output_path: str):
        """
        Save investigation to ISA-JSON file with lightweight study references,
        and save each study as a separate JSON file in its own subfolder.

        Directory structure created:
            output_path/
              {investigation_id}.json    (lightweight investigation)
              studies/
                study_E1/study.json
                study_E2/study.json

        Args:
            investigation: ISAInvestigation object
            output_path: File path or directory to save the file
        """
        output = Path(output_path)

        # If output_path points to a .json file, use its parent as base
        if output.suffix == ".json":
            output.parent.mkdir(parents=True, exist_ok=True)
            output_file = output
            base_dir = output.parent
        else:
            # Use output_path directly as base directory
            base_dir = output
            base_dir.mkdir(parents=True, exist_ok=True)
            output_file = base_dir / f"{investigation.investigation_id}.json"

        # Save lightweight investigation JSON (study references only)
        investigation_dict = self._investigation_to_dict_lightweight(investigation)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(investigation_dict, f, indent=2, default=str, ensure_ascii=False)
        self.logger.info(f"Saved lightweight investigation to {output_file}")

        # Save each study as a separate JSON file
        self.save_studies_separately(investigation, base_dir)

    def save_studies_separately(self, investigation: ISAInvestigation, base_dir: Path):
        """
        Save each study as a separate JSON file in its own subfolder.

        Args:
            investigation: ISAInvestigation object
            base_dir: Base directory (investigation folder)
        """
        studies_dir = base_dir / "studies"
        studies_dir.mkdir(parents=True, exist_ok=True)

        for study in investigation.studies:
            study_dir = studies_dir / study.study_id
            study_dir.mkdir(parents=True, exist_ok=True)

            study_dict = self._study_to_dict(study)
            study_file = study_dir / "study.json"

            with open(study_file, "w", encoding="utf-8") as f:
                json.dump(study_dict, f, indent=2, default=str, ensure_ascii=False)

            self.logger.info(f"Saved study {study.study_id} to {study_file}")

    # ── Dict conversion ──────────────────────────────────────────────────

    def _investigation_to_dict(self, investigation: ISAInvestigation) -> Dict[str, Any]:
        """
        Convert investigation object to dictionary with full inline study data.
        """
        return {
            "@id": f"#investigation/{investigation.investigation_id}",
            "identifier": investigation.investigation_id,
            "title": investigation.investigation_title,
            "description": investigation.investigation_description,
            "submissionDate": investigation.submission_date,
            "publicReleaseDate": investigation.public_release_date,
            "studies": [self._study_to_dict(study) for study in investigation.studies],
            "ontologySourceReferences": investigation.ontology_source_references,
            "people": [self._person_to_dict(p) for p in investigation.people],
            "publications": [],
            "comments": investigation.comments,
        }

    def _investigation_to_dict_lightweight(self, investigation: ISAInvestigation) -> Dict[str, Any]:
        """
        Convert investigation to a lightweight dictionary with study references only.
        """
        return {
            "@id": f"#investigation/{investigation.investigation_id}",
            "identifier": investigation.investigation_id,
            "title": investigation.investigation_title,
            "description": investigation.investigation_description,
            "submissionDate": investigation.submission_date,
            "publicReleaseDate": investigation.public_release_date,
            "studies": [
                {
                    "@id": f"#study/{study.study_id}",
                    "filename": f"studies/{study.study_id}",
                    "identifier": study.study_id,
                    "title": study.study_title,
                    "description": study.study_description,
                    "submissionDate": study.submission_date,
                    "publicReleaseDate": study.public_release_date,
                }
                for study in investigation.studies
            ],
            "ontologySourceReferences": investigation.ontology_source_references,
            "people": [self._person_to_dict(p) for p in investigation.people],
            "publications": [],
            "comments": investigation.comments,
        }

    def _study_to_dict(self, study: ISAStudy) -> Dict[str, Any]:
        """
        Convert study object to dictionary.

        Args:
            study: ISAStudy object

        Returns:
            Dictionary representation
        """
        return {
            "@id": f"#study/{study.study_id}",
            "filename": f"studies/{study.study_id}",
            "identifier": study.study_id,
            "title": study.study_title,
            "description": study.study_description,
            "submissionDate": study.submission_date,
            "publicReleaseDate": study.public_release_date,
            "publications": [],
            "people": [],
            "assays": [self._assay_to_dict(assay) for assay in study.assays],
            "materials": study.materials,
            "protocols": [
                {
                    "@id": "#protocol/assay_protocol",
                    "name": "assay_protocol",
                    "protocolType": {
                        "annotationValue": "assay",
                        "termSource": "OBI",
                        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000070",
                    },
                    "description": "Assay protocol for data acquisition",
                    "uri": "",
                    "version": "",
                    "parameters": [],
                    "components": [],
                }
            ],
            "processSequence": [
                self._process_to_dict(process) for process in study.process_sequence
            ],
            "characteristicCategories": study.characteristic_categories,
            "unitCategories": study.unit_categories,
            "comments": study.comments,
        }

    def _assay_to_dict(self, assay: ISAAssay) -> Dict[str, Any]:
        """
        Convert assay object to dictionary.
        """
        return {
            "@id": f"#assay/{assay.assay_id}",
            "filename": f"assays/{assay.assay_id}",
            "measurementType": assay.measurement_type,
            "technologyType": assay.technology_type,
            "technologyPlatform": assay.technology_platform,
            "dataFiles": assay.data_files,
            "materials": assay.materials,
            "characteristicCategories": (
                assay.characteristicCategories if hasattr(assay, "characteristicCategories") else []
            ),
            "unitCategories": assay.unitCategories if hasattr(assay, "unitCategories") else [],
            "processSequence": [
                self._process_to_dict(process) for process in assay.process_sequence
            ],
            "comments": assay.comments,
        }

    def _process_to_dict(self, process: ISAProcess) -> Dict[str, Any]:
        """
        Convert process object to dictionary.
        """
        return {
            "@id": process.process_id,
            "name": process.process_id.replace("#process/", ""),
            "executesProtocol": {"@id": process.executes_protocol},
            "parameterValues": process.parameter_values,
            "performer": "",
            "date": "",
            "inputs": process.inputs,
            "outputs": process.outputs,
            "comments": process.comments,
        }

    def _person_to_dict(self, person: Dict[str, Any]) -> Dict[str, Any]:
        """Convert person dict to ISA-JSON person format."""
        return person


def main():
    """Main function for testing the ISA-JSON generator."""
    import sys

    from utils.batch.folder_scanner import FolderScanner

    # Test with representative data folder
    test_folder = "partner representative data"
    output_dir = "isa_json_output"

    if len(sys.argv) > 1:
        test_folder = sys.argv[1]
    if len(sys.argv) > 2:
        output_dir = sys.argv[2]

    # Scan experiments
    scanner = FolderScanner(test_folder)
    experiments = scanner.scan_experiments()

    # Generate investigation
    generator = ISAJsonGenerator()
    defaults = get_profile().get_investigation_defaults()
    investigation = generator.generate_investigation(
        experiments=experiments,
        investigation_id=defaults.get("investigation_id", "inv_001"),
        investigation_title=defaults.get("investigation_title", "Partner Data Investigation"),
        investigation_description=defaults.get(
            "investigation_description", "Investigation of partner data."
        ),
    )

    # Save investigation
    generator.save_investigation(investigation, output_dir)

    print("\nISA-JSON generation complete:")
    print(f"  Total experiments: {len(experiments)}")
    print(f"  Total studies: {len(investigation.studies)}")
    for study in investigation.studies:
        print(
            f"    {study.study_id}: {len(study.assays)} assays, "
            f"{len(study.materials.get('sources', []))} sources, "
            f"{len(study.materials.get('samples', []))} samples"
        )


if __name__ == "__main__":
    main()
