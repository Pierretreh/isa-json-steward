"""
Experiment Classifier for classifying experiments by type.

This module classifies experiments based on folder names, file contents,
and suggests appropriate assay templates.  Domain-specific knowledge
(keywords, templates, file indicators) is loaded from the active profile
via :func:`utils.config_loader.get_profile`, making the classifier
reusable for any project.
"""

import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, cast

from utils.batch.folder_scanner import FileInventory, FolderMetadata
from utils.config_loader import get_profile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExperimentType(Enum):
    """Experiment type classification enum."""

    UNKNOWN = "unknown"
    CALCEIN_ASSAY = "calcein"
    FACS_ASSAY = "facs"
    MICROSCOPY = "microscopy"
    ELISA = "elisa"
    WESTERN_BLOT = "western_blot"
    TUNEL_STAINING = "tunel"
    DAPI_STAINING = "dapi"
    HE_STAINING = "he_staining"
    GFAP_STAINING = "gfap"
    FLUORESCENCE = "fluorescence"
    TOXICITY_IN_VITRO = "toxicity_in_vitro"
    TOXICITY_EX_VIVO = "toxicity_ex_vivo"
    DEPOT_MICROSCOPY = "depot_microscopy"
    EXPLANT = "explant"


@dataclass
class ExperimentClassification:
    """Detailed classification result with confidence scoring."""

    type_name: str
    assay_template: str
    confidence: float
    detected_keywords: List[str]
    detected_files: List[str]


@dataclass
class ClassificationResult:
    """Result of classifying an experiment directory."""

    experiment_type: ExperimentType
    confidence: float
    template_match: Optional[str] = None


class ExperimentClassifier:
    """Classifier for experiment types.

    Domain-specific mappings (type → template, type → keywords, etc.)
    are loaded from the active profile via :func:`utils.config_loader.get_profile`.
    """

    # ------------------------------------------------------------------
    # Domain-mapping properties – delegated to ProfileLoader
    # ------------------------------------------------------------------

    @property
    def TYPE_TO_TEMPLATE(self) -> Dict[str, str]:
        """Mapping of experiment type keys to assay template filenames.

        Data is loaded from the active profile's ``experiment_patterns``
        configuration.  Falls back to an empty dict if the profile is
        unavailable.
        """
        return get_profile().get_type_to_template()

    @property
    def TYPE_NAME_TO_ENUM(self) -> Dict[str, "ExperimentType"]:
        """Mapping from string type names to :class:`ExperimentType` values.

        The canonical-name → enum mapping is derived from the profile's
        ``type_name_aliases`` section.  Enum values are the code-side
        constants and are not profile-dependent.
        """
        aliases = get_profile().get_type_name_aliases()
        enum_by_value = {e.value: e for e in ExperimentType}
        result: Dict[str, ExperimentType] = {}
        for alias, canonical in aliases.items():
            if canonical in enum_by_value:
                result[alias] = enum_by_value[canonical]
        return result

    @property
    def TYPE_KEYWORDS(self) -> Dict[str, List[str]]:
        """Keywords for each experiment type.

        Data is loaded from the active profile's ``experiment_patterns``
        configuration.
        """
        return get_profile().get_type_keywords()

    @property
    def TYPE_FILE_INDICATORS(self) -> Dict[str, List[str]]:
        """File-type indicators for each experiment type.

        Data is loaded from the active profile's ``experiment_patterns``
        configuration.
        """
        return get_profile().get_type_file_indicators()

    def __init__(self, templates_root: str = "templates/assay_templates"):
        """
        Initialize the experiment classifier.

        Args:
            templates_root: Root directory for assay templates
        """
        self.templates_root = templates_root
        self.logger = logging.getLogger(__name__)

    def classify(self, experiment_path) -> ClassificationResult:
        """
        Classify an experiment directory.

        Unified entry point that combines name-based and file-based
        classification.

        Args:
            experiment_path: Path to the experiment directory (Path or str)

        Returns:
            ClassificationResult with experiment_type, confidence, and template_match
        """
        from pathlib import Path

        path = Path(experiment_path) if not isinstance(experiment_path, Path) else experiment_path

        # Classify from folder name
        name_classification = self.classify_from_name(path.name)

        # Check if name classification found any real keyword matches
        name_has_match = len(name_classification.detected_keywords) > 0

        # Classify from files
        file_classification = None
        file_has_match = False
        if path.exists() and path.is_dir():
            from utils.batch.folder_scanner import FolderScanner

            scanner = FolderScanner(str(path.parent))
            file_inventory = scanner.get_file_inventory(str(path))
            if file_inventory and file_inventory.get_file_count() > 0:
                file_classification = self.classify_from_files(file_inventory)
                file_has_match = len(file_classification.detected_files) > 0

        # Determine best classification
        type_name = None
        confidence = 0.0

        if name_has_match and file_has_match:
            assert file_classification is not None  # guaranteed by file_has_match above
            if name_classification.type_name == file_classification.type_name:
                # Both agree - boost confidence
                confidence = min(name_classification.confidence + 0.2, 1.0)
                type_name = name_classification.type_name
            else:
                # Disagreement - use higher confidence
                if name_classification.confidence >= file_classification.confidence:
                    type_name = name_classification.type_name
                    confidence = name_classification.confidence
                else:
                    type_name = file_classification.type_name
                    confidence = file_classification.confidence
        elif name_has_match:
            type_name = name_classification.type_name
            confidence = name_classification.confidence
        elif file_has_match:
            assert file_classification is not None  # guaranteed by file_has_match
            type_name = file_classification.type_name
            confidence = file_classification.confidence
        else:
            # No matches found - return UNKNOWN
            return ClassificationResult(
                experiment_type=ExperimentType.UNKNOWN, confidence=0.0, template_match=None
            )

        # Map to enum
        experiment_type = self.TYPE_NAME_TO_ENUM.get(type_name, ExperimentType.UNKNOWN)

        # Get template match
        template_match = self.TYPE_TO_TEMPLATE.get(type_name)

        return ClassificationResult(
            experiment_type=experiment_type, confidence=confidence, template_match=template_match
        )

    def classify_from_name(self, folder_name: str) -> ExperimentClassification:
        """
        Classify experiment based on folder name.

        Args:
            folder_name: Name of the experiment folder

        Returns:
            ExperimentClassification classification
        """
        folder_name_lower = folder_name.lower()

        # Check each type for keyword matches
        best_match = None
        best_confidence = 0.0
        detected_keywords = []

        for exp_type, keywords in self.TYPE_KEYWORDS.items():
            matches = 0
            type_keywords = []

            for keyword in keywords:
                if keyword.lower() in folder_name_lower:
                    matches += 1
                    type_keywords.append(keyword)

            if matches > 0:
                confidence = min(matches / len(keywords), 1.0)

                # Boost confidence for exact matches
                if folder_name_lower.startswith(keyword.lower()):
                    confidence += 0.2

                confidence = min(confidence, 1.0)

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = exp_type
                    detected_keywords = type_keywords

        if best_match:
            assay_template = self.TYPE_TO_TEMPLATE.get(best_match, "microscopy_assay.json")
            return ExperimentClassification(
                type_name=best_match,
                assay_template=assay_template,
                confidence=best_confidence,
                detected_keywords=detected_keywords,
                detected_files=[],
            )
        else:
            # Default to microscopy if no match
            return ExperimentClassification(
                type_name="microscopy",
                assay_template="microscopy_assay.json",
                confidence=0.5,
                detected_keywords=[],
                detected_files=[],
            )

    def classify_from_files(self, file_inventory: FileInventory) -> ExperimentClassification:
        """
        Classify experiment based on file contents.

        Args:
            file_inventory: File inventory for the experiment

        Returns:
            ExperimentClassification classification
        """
        best_match = None
        best_confidence = 0.0
        detected_files = []

        for exp_type, file_indicators in self.TYPE_FILE_INDICATORS.items():
            matches = 0
            type_files = []

            for indicator in file_indicators:
                if indicator == ".fcs" and file_inventory.fcs_files:
                    matches += len(file_inventory.fcs_files)
                    type_files.extend(file_inventory.fcs_files)
                elif indicator == ".wsp" and file_inventory.wsp_files:
                    matches += len(file_inventory.wsp_files)
                    type_files.extend(file_inventory.wsp_files)
                elif indicator == ".czi" and file_inventory.czi_files:
                    matches += len(file_inventory.czi_files)
                    type_files.extend(file_inventory.czi_files)
                elif indicator in [".tiff", ".tif"] and file_inventory.tiff_files:
                    matches += len(file_inventory.tiff_files)
                    type_files.extend(file_inventory.tiff_files)
                elif indicator in [".xlsx", ".xls"] and file_inventory.xlsx_files:
                    matches += len(file_inventory.xlsx_files)
                    type_files.extend(file_inventory.xlsx_files)

            if matches > 0:
                # Normalize confidence based on total files
                total_files = file_inventory.get_file_count()
                confidence = min(matches / max(total_files, 1), 1.0)

                # Boost confidence for strong indicators
                if exp_type == "facs" and file_inventory.fcs_files:
                    confidence += 0.3

                confidence = min(confidence, 1.0)

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = exp_type
                    detected_files = type_files

        if best_match:
            assay_template = self.TYPE_TO_TEMPLATE.get(best_match, "microscopy_assay.json")
            return ExperimentClassification(
                type_name=best_match,
                assay_template=assay_template,
                confidence=best_confidence,
                detected_keywords=[],
                detected_files=detected_files,
            )
        else:
            # Default to microscopy if no match
            return ExperimentClassification(
                type_name="microscopy",
                assay_template="microscopy_assay.json",
                confidence=0.3,
                detected_keywords=[],
                detected_files=[],
            )

    def classify_experiment(self, metadata: FolderMetadata) -> ExperimentClassification:
        """
        Classify experiment using both name and file analysis.

        Args:
            metadata: Folder metadata for the experiment

        Returns:
            ExperimentClassification classification
        """
        # Classify from name
        name_classification = self.classify_from_name(metadata.experiment_name)

        # Classify from files if available
        if metadata.file_inventory:
            file_classification = self.classify_from_files(metadata.file_inventory)

            # Combine classifications
            if name_classification.type_name == file_classification.type_name:
                # Both agree - boost confidence
                combined_confidence = min(name_classification.confidence + 0.2, 1.0)
                return ExperimentClassification(
                    type_name=name_classification.type_name,
                    assay_template=name_classification.assay_template,
                    confidence=combined_confidence,
                    detected_keywords=name_classification.detected_keywords,
                    detected_files=file_classification.detected_files,
                )
            else:
                # Disagreement - use higher confidence
                if name_classification.confidence >= file_classification.confidence:
                    return name_classification
                else:
                    return file_classification
        else:
            return name_classification

    def suggest_template(self, experiment_type) -> str:
        """
        Suggest assay template for an experiment type.

        Args:
            experiment_type: ExperimentClassification or ExperimentType enum

        Returns:
            Path to assay template
        """
        if isinstance(experiment_type, ExperimentType):
            type_name = experiment_type.value
            template = self.TYPE_TO_TEMPLATE.get(type_name, "microscopy_assay.json")
        else:
            template = experiment_type.assay_template
        return f"{self.templates_root}/{template}"

    def get_available_templates(self) -> List[Dict[str, Any]]:
        """
        Get list of available assay templates.

        Returns:
            List of template info dictionaries
        """
        templates = []
        templates_dir = self.templates_root

        if os.path.isdir(templates_dir):
            for filename in sorted(os.listdir(templates_dir)):
                if filename.endswith(".json"):
                    templates.append(
                        {
                            "filename": filename,
                            "path": os.path.join(templates_dir, filename),
                            "type": filename.replace("_assay.json", "").replace(".json", ""),
                        }
                    )

        return templates

    def get_template_by_type(self, exp_type: ExperimentType) -> Optional[Dict[str, Any]]:
        """
        Get template by experiment type.

        Args:
            exp_type: ExperimentType enum value

        Returns:
            Template dictionary or None
        """
        import json

        type_name = exp_type.value
        template_filename = self.TYPE_TO_TEMPLATE.get(type_name)

        if template_filename:
            template_path = os.path.join(self.templates_root, template_filename)
            if os.path.exists(template_path):
                try:
                    with open(template_path, "r", encoding="utf-8") as f:
                        return cast(Dict[str, Any], json.load(f))
                except Exception as e:
                    self.logger.warning(f"Could not load template {template_path}: {e}")

        return None

    def extract_parameters_from_name(self, folder_name: str) -> Dict[str, Any]:
        """
        Extract experimental parameters from folder name.

        Args:
            folder_name: Name of the experiment folder

        Returns:
            Dictionary of extracted parameters
        """
        parameters = {}

        # Extract protein variants (pVV019, pVV021, etc.)
        protein_variants = re.findall(r"pVV\d+", folder_name, re.IGNORECASE)
        if protein_variants:
            parameters["protein_variants"] = protein_variants

        # Extract concentrations (e.g., "0,5 zu 4uM", "50uM")
        concentrations = re.findall(r"(\d+(?:,\d+)?)\s*(?:zu\s*)?uM", folder_name, re.IGNORECASE)
        if concentrations:
            parameters["concentrations_uM"] = [c.replace(",", ".") for c in concentrations]

        # Extract sample counts (n=1, n=2, etc.)
        sample_counts = re.findall(r"n\s*=\s*(\d+)", folder_name, re.IGNORECASE)
        if sample_counts:
            parameters["sample_count"] = [int(n) for n in sample_counts]

        # Extract cell types
        cell_types = []
        if "HRMVEC" in folder_name:
            cell_types.append("HRMVEC")
        if "Explant" in folder_name:
            cell_types.append("Explant")
        if "Müllerzellen" in folder_name or "Müller" in folder_name:
            cell_types.append("Müllerzellen")
        if cell_types:
            parameters["cell_types"] = cell_types

        # Extract time points (48h, 6h, 24h, etc.)
        time_points = re.findall(r"(\d+)h", folder_name, re.IGNORECASE)
        if time_points:
            parameters["time_points_hours"] = [int(t) for t in time_points]

        # Extract control references
        controls = []
        if "Control" in folder_name or "Ctrl" in folder_name:
            controls.append("control")
        if "negativ" in folder_name:
            controls.append("negative")
        if "positiv" in folder_name:
            controls.append("positive")
        if controls:
            parameters["controls"] = controls

        return parameters

    def classify_batch(self, experiments: List[FolderMetadata]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Classify a batch of experiments.

        Args:
            experiments: List of experiment metadata

        Returns:
            Dictionary mapping experiment types to lists of classified experiments
        """
        results: Dict[str, List[Dict[str, Any]]] = {}

        for exp in experiments:
            classification = self.classify_experiment(exp)
            parameters = self.extract_parameters_from_name(exp.experiment_name)

            result = {
                "experiment_id": exp.experiment_id,
                "experiment_name": exp.experiment_name,
                "folder_path": exp.folder_path,
                "type": classification.type_name,
                "assay_template": classification.assay_template,
                "confidence": classification.confidence,
                "detected_keywords": classification.detected_keywords,
                "detected_files": classification.detected_files,
                "parameters": parameters,
            }

            if classification.type_name not in results:
                results[classification.type_name] = []

            results[classification.type_name].append(result)
            self.logger.info(
                f"Classified {exp.experiment_id} as {classification.type_name} (confidence: {classification.confidence:.2f})"  # noqa: E501
            )

        # Log summary
        self.logger.info("\nClassification summary:")
        for exp_type, exp_list in results.items():
            self.logger.info(f"  {exp_type}: {len(exp_list)} experiments")

        return results


# Backward compatibility alias
# Code that imported ExperimentType as a dataclass will get ExperimentClassification instead
ExperimentTypeData = ExperimentClassification


def main():
    """Main function for testing the experiment classifier."""
    import json

    # Test with sample folder names
    test_folders = [
        "E1_Müller_Calceinassay und FACS Test",
        "E10_Explant_Calcein_FACS",
        "E100_Explant_FACS_pVV021 und cleav 0,5 zu 4uM_n=5",
        "E113_WB_HRMVEC_NFkB",
        "E19_TUNEL und H und E Staining",
        "E74_HRMVEC_ELISA IL6",
        "E70_Explant_GFAP_Bucher_1 zu 600 verdünnt",
    ]

    classifier = ExperimentClassifier()

    print("Testing experiment classifier:")
    print("-" * 80)

    for folder_name in test_folders:
        classification = classifier.classify_from_name(folder_name)
        parameters = classifier.extract_parameters_from_name(folder_name)

        print(f"\nFolder: {folder_name}")
        print(f"  Type: {classification.type_name}")
        print(f"  Template: {classification.assay_template}")
        print(f"  Confidence: {classification.confidence:.2f}")
        print(f"  Keywords: {classification.detected_keywords}")
        print(f"  Parameters: {json.dumps(parameters, indent=4)}")


if __name__ == "__main__":
    main()
