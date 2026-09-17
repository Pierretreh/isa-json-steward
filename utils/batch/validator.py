"""
Validator for ISA-JSON files and converted data.

This module validates ISA-JSON files against the ISA-JSON specification
and validates converted data files for completeness and integrity.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation operation."""

    is_valid: bool
    validation_type: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)


@dataclass
class FileValidationResult:
    """Result of a file validation operation."""

    file_path: str
    file_exists: bool
    file_readable: bool
    file_size: int
    checksum: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class ISAJsonValidator:
    """Validator for ISA-JSON files."""

    def __init__(self):
        """Initialize the ISA-JSON validator."""
        self.logger = logging.getLogger(__name__)

        # ISA-JSON required fields
        self.required_investigation_fields = [
            "identifier",
            "title",
            "description",
            "submissionDate",
            "studies",
            "ontologySourceReferences",
        ]

        self.required_study_fields = [
            "identifier",
            "title",
            "description",
            "submissionDate",
            "assays",
            "materials",
            "protocols",
            "processSequence",
        ]

        self.required_assay_fields = [
            "measurementType",
            "technologyType",
            "dataFiles",
            "materials",
            "processSequence",
        ]

    def validate_investigation(self, investigation_path: str) -> ValidationResult:
        """
        Validate an investigation ISA-JSON file.

        Args:
            investigation_path: Path to investigation JSON file

        Returns:
            ValidationResult object
        """
        result = ValidationResult(is_valid=True, validation_type="investigation")

        try:
            # Load investigation file
            with open(investigation_path, "r", encoding="utf-8") as f:
                investigation_data = json.load(f)

            # Support both flat (ISA-JSON spec) and wrapped formats
            if "investigation" in investigation_data:
                investigation = investigation_data["investigation"]
            else:
                investigation = investigation_data

            # Validate required fields
            for field_ in self.required_investigation_fields:
                if field_ not in investigation:
                    result.is_valid = False
                    result.errors.append(f"Missing required field: {field_}")
                elif not investigation[field_]:
                    result.warnings.append(f"Empty required field: {field_}")

            # Validate studies
            studies = investigation.get("studies", [])
            if not studies:
                result.warnings.append("No studies found in investigation")
            else:
                result.info.append(f"Found {len(studies)} studies")
                for i, study in enumerate(studies):
                    study_result = self._validate_study(study, f"study_{i}")
                    result.errors.extend(study_result.errors)
                    result.warnings.extend(study_result.warnings)
                    result.info.extend(study_result.info)
                    if not study_result.is_valid:
                        result.is_valid = False

            # Validate ontology source references
            ontologies = investigation.get("ontologySourceReferences", [])
            if not ontologies:
                result.warnings.append("No ontology source references found")
            else:
                result.info.append(f"Found {len(ontologies)} ontology references")
                for onto in ontologies:
                    if "name" not in onto or "file" not in onto:
                        result.warnings.append("Incomplete ontology reference")

            # Check for FAIR compliance
            self._check_fair_compliance(investigation, result)

        except FileNotFoundError:
            result.is_valid = False
            result.errors.append(f"Investigation file not found: {investigation_path}")
        except json.JSONDecodeError as e:
            result.is_valid = False
            result.errors.append(f"Invalid JSON format: {e}")
        except Exception as e:
            result.is_valid = False
            result.errors.append(f"Unexpected error: {e}")

        return result

    def _validate_study(self, study: Dict[str, Any], study_id: str) -> ValidationResult:
        """
        Validate a study within an investigation.

        Args:
            study: Study data
            study_id: Study identifier for error messages

        Returns:
            ValidationResult object
        """
        result = ValidationResult(is_valid=True, validation_type="study")

        # Validate required fields
        for field_ in self.required_study_fields:
            if field_ not in study:
                result.is_valid = False
                result.errors.append(f"{study_id}: Missing required field: {field_}")

        # Validate assays
        assays = study.get("assays", [])
        if not assays:
            result.warnings.append(f"{study_id}: No assays found")
        else:
            result.info.append(f"{study_id}: Found {len(assays)} assays")
            for i, assay in enumerate(assays):
                assay_result = self._validate_assay(assay, f"{study_id}_assay_{i}")
                result.errors.extend(assay_result.errors)
                result.warnings.extend(assay_result.warnings)
                result.info.extend(assay_result.info)
                if not assay_result.is_valid:
                    result.is_valid = False

        # Validate materials
        materials = study.get("materials", {})
        if not materials:
            result.warnings.append(f"{study_id}: No materials found")

        # Validate protocols
        protocols = study.get("protocols", [])
        if not protocols:
            result.warnings.append(f"{study_id}: No protocols found")

        return result

    def _validate_assay(self, assay: Dict[str, Any], assay_id: str) -> ValidationResult:
        """
        Validate an assay within a study.

        Args:
            assay: Assay data
            assay_id: Assay identifier for error messages

        Returns:
            ValidationResult object
        """
        result = ValidationResult(is_valid=True, validation_type="assay")

        # Validate required fields
        for field_ in self.required_assay_fields:
            if field_ not in assay:
                result.is_valid = False
                result.errors.append(f"{assay_id}: Missing required field: {field_}")

        # Validate measurement type
        measurement_type = assay.get("measurementType", {})
        if not measurement_type.get("annotationValue"):
            result.warnings.append(f"{assay_id}: Missing measurement type annotation value")
        if not measurement_type.get("termSource"):
            result.warnings.append(f"{assay_id}: Missing measurement type term source")

        # Validate technology type
        technology_type = assay.get("technologyType", {})
        if not technology_type.get("annotationValue"):
            result.warnings.append(f"{assay_id}: Missing technology type annotation value")
        if not technology_type.get("termSource"):
            result.warnings.append(f"{assay_id}: Missing technology type term source")

        # Validate data files
        data_files = assay.get("dataFiles", [])
        if not data_files:
            result.warnings.append(f"{assay_id}: No data files found")
        else:
            result.info.append(f"{assay_id}: Found {len(data_files)} data files")
            for data_file in data_files:
                # ISA-JSON uses 'name' for data files, not 'filename' (per BII-S-3 reference)
                if "name" not in data_file:
                    result.warnings.append(f"{assay_id}: Data file missing name")

        # Validate process sequence
        process_sequence = assay.get("processSequence", [])
        if not process_sequence:
            result.warnings.append(f"{assay_id}: No process sequence found")

        return result

    def _check_fair_compliance(self, investigation: Dict[str, Any], result: ValidationResult):
        """
        Check FAIR compliance indicators.

        Args:
            investigation: Investigation data
            result: ValidationResult to update
        """
        # Findable: Check for identifiers and metadata
        if investigation.get("identifier"):
            result.info.append("FAIR - Findable: Has identifier")
        else:
            result.warnings.append("FAIR - Findable: Missing identifier")

        if investigation.get("title"):
            result.info.append("FAIR - Findable: Has title")

        if investigation.get("description"):
            result.info.append("FAIR - Findable: Has description")

        # Accessible: Check for protocol information
        studies = investigation.get("studies", [])
        for study in studies:
            if study.get("protocols"):
                result.info.append("FAIR - Accessible: Has protocols")
                break

        # Interoperable: Check for ontology references
        ontologies = investigation.get("ontologySourceReferences", [])
        if ontologies:
            result.info.append(f"FAIR - Interoperable: Has {len(ontologies)} ontology references")
        else:
            result.warnings.append("FAIR - Interoperable: No ontology references")

        # Reusable: Check for study design descriptors
        for study in studies:
            if study.get("studyDesignDescriptors"):
                result.info.append("FAIR - Reusable: Has study design descriptors")
                break


class DataFileValidator:
    """Validator for converted data files."""

    def __init__(self):
        """Initialize the data file validator."""
        self.logger = logging.getLogger(__name__)

    def validate_files(
        self, investigation_path: str
    ) -> Tuple[ValidationResult, List[FileValidationResult]]:
        """
        Validate all data files referenced in an investigation.

        Args:
            investigation_path: Path to investigation JSON file

        Returns:
            Tuple of (ValidationResult, List[FileValidationResult])
        """
        result = ValidationResult(is_valid=True, validation_type="data_files")
        file_results = []

        try:
            # Load investigation file
            with open(investigation_path, "r", encoding="utf-8") as f:
                investigation_data = json.load(f)

            investigation = investigation_data.get("investigation", investigation_data)
            investigation_dir = Path(investigation_path).parent

            # Validate files in each study and assay
            studies = investigation.get("studies", [])
            for study in studies:
                study_results = self._validate_study_files(study, investigation_dir)
                file_results.extend(study_results)

            # Check for missing files
            missing_files = [f for f in file_results if not f.file_exists]
            if missing_files:
                result.is_valid = False
                result.errors.append(f"Found {len(missing_files)} missing files")

            # Check for unreadable files
            unreadable_files = [f for f in file_results if not f.file_readable]
            if unreadable_files:
                result.warnings.append(f"Found {len(unreadable_files)} unreadable files")

            result.info.append(f"Validated {len(file_results)} files")
            result.info.append(f"  - {len([f for f in file_results if f.file_exists])} exist")
            result.info.append(f"  - {len([f for f in file_results if f.file_readable])} readable")

        except Exception as e:
            result.is_valid = False
            result.errors.append(f"Error validating files: {e}")

        return result, file_results

    def _validate_study_files(
        self, study: Dict[str, Any], investigation_dir: Path
    ) -> List[FileValidationResult]:
        """
        Validate files in a study.

        Args:
            study: Study data
            investigation_dir: Path to investigation directory

        Returns:
            List of FileValidationResult objects
        """
        results = []
        study_id = study.get("identifier", "unknown")

        # Validate assay files
        assays = study.get("assays", [])
        for assay in assays:
            assay_results = self._validate_assay_files(assay, investigation_dir, study_id)
            results.extend(assay_results)

        return results

    def _validate_assay_files(
        self, assay: Dict[str, Any], investigation_dir: Path, study_id: str
    ) -> List[FileValidationResult]:
        """
        Validate files in an assay.

        Args:
            assay: Assay data
            investigation_dir: Path to investigation directory
            study_id: Study identifier

        Returns:
            List of FileValidationResult objects
        """
        results = []
        assay_id = assay.get("assay_id", "unknown")

        data_files = assay.get("dataFiles", [])
        for data_file in data_files:
            filename = data_file.get("filename", "unknown")

            # Try to find the file
            file_path = self._find_file(filename, investigation_dir, study_id, assay_id)

            file_result = self._validate_single_file(file_path if file_path else filename)
            results.append(file_result)

        return results

    def _find_file(
        self, filename: str, investigation_dir: Path, study_id: str, assay_id: str
    ) -> Optional[str]:
        """
        Find a file in the investigation directory structure.

        Args:
            filename: Filename to find
            investigation_dir: Investigation directory
            study_id: Study identifier
            assay_id: Assay identifier

        Returns:
            Path to file if found, None otherwise
        """
        # Try common locations
        possible_paths = [
            investigation_dir / filename,
            investigation_dir / "studies" / study_id / "assays" / assay_id / filename,
            investigation_dir / "studies" / study_id / filename,
            investigation_dir / "data" / filename,
        ]

        for path in possible_paths:
            if path.exists():
                return str(path)

        # Try recursive search
        for path in investigation_dir.rglob(filename):
            return str(path)

        return None

    def _validate_single_file(self, file_path: str) -> FileValidationResult:
        """
        Validate a single file.

        Args:
            file_path: Path to file

        Returns:
            FileValidationResult object
        """
        result = FileValidationResult(
            file_path=file_path, file_exists=False, file_readable=False, file_size=0
        )

        try:
            path = Path(file_path)

            # Check if file exists
            if not path.exists():
                result.errors.append("File does not exist")
                return result

            result.file_exists = True
            result.file_size = path.stat().st_size

            # Check if file is readable
            try:
                with open(path, "rb") as f:
                    f.read(1)
                result.file_readable = True
            except PermissionError:
                result.errors.append("Permission denied")
            except Exception as e:
                result.errors.append(f"Read error: {e}")

            # Check file size
            if result.file_size == 0:
                result.warnings.append("File is empty")

            # Calculate checksum for small files
            if result.file_readable and result.file_size < 10 * 1024 * 1024:  # 10 MB
                result.checksum = self._calculate_checksum(file_path)

        except Exception as e:
            result.errors.append(f"Validation error: {e}")

        return result

    def _calculate_checksum(self, file_path: str) -> str:
        """
        Calculate MD5 checksum of a file.

        Args:
            file_path: Path to file

        Returns:
            MD5 checksum string
        """
        import hashlib

        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)

        return md5_hash.hexdigest()


class MetadataValidator:
    """Validator for metadata completeness."""

    def __init__(self):
        """Initialize the metadata validator."""
        self.logger = logging.getLogger(__name__)

    def validate_metadata(self, investigation_path: str) -> ValidationResult:
        """
        Validate metadata completeness in an investigation.

        Args:
            investigation_path: Path to investigation JSON file

        Returns:
            ValidationResult object
        """
        result = ValidationResult(is_valid=True, validation_type="metadata")

        try:
            # Load investigation file
            with open(investigation_path, "r", encoding="utf-8") as f:
                investigation_data = json.load(f)

            investigation = investigation_data.get("investigation", investigation_data)

            # Check investigation metadata
            self._check_investigation_metadata(investigation, result)

            # Check study metadata
            studies = investigation.get("studies", [])
            for i, study in enumerate(studies):
                self._check_study_metadata(study, f"study_{i}", result)

            # Check assay metadata
            for i, study in enumerate(studies):
                assays = study.get("assays", [])
                for j, assay in enumerate(assays):
                    self._check_assay_metadata(assay, f"study_{i}_assay_{j}", result)

        except Exception as e:
            result.is_valid = False
            result.errors.append(f"Error validating metadata: {e}")

        return result

    def _check_investigation_metadata(
        self, investigation: Dict[str, Any], result: ValidationResult
    ):
        """
        Check investigation-level metadata.

        Args:
            investigation: Investigation data
            result: ValidationResult to update
        """
        # Required fields
        required = ["identifier", "title", "description"]
        for field_ in required:
            if not investigation.get(field_):
                result.warnings.append(f"Investigation missing {field_}")

        # Optional but recommended fields
        recommended = ["submissionDate", "publicReleaseDate"]
        for field_ in recommended:
            if not investigation.get(field_):
                result.info.append(f"Investigation missing recommended field: {field_}")

    def _check_study_metadata(self, study: Dict[str, Any], study_id: str, result: ValidationResult):
        """
        Check study-level metadata.

        Args:
            study: Study data
            study_id: Study identifier
            result: ValidationResult to update
        """
        # Required fields
        required = ["identifier", "title", "description"]
        for field_ in required:
            if not study.get(field_):
                result.warnings.append(f"{study_id} missing {field_}")

        # Check for study design descriptors
        if not study.get("studyDesignDescriptors"):
            result.warnings.append(f"{study_id} missing study design descriptors")

        # Check for characteristic categories
        if not study.get("characteristicCategories"):
            result.warnings.append(f"{study_id} missing characteristic categories")

    def _check_assay_metadata(self, assay: Dict[str, Any], assay_id: str, result: ValidationResult):
        """
        Check assay-level metadata.

        Args:
            assay: Assay data
            assay_id: Assay identifier
            result: ValidationResult to update
        """
        # Check measurement type
        measurement_type = assay.get("measurementType", {})
        if not measurement_type.get("annotationValue"):
            result.warnings.append(f"{assay_id} missing measurement type")
        if not measurement_type.get("termSource"):
            result.warnings.append(f"{assay_id} missing measurement type ontology")

        # Check technology type
        technology_type = assay.get("technologyType", {})
        if not technology_type.get("annotationValue"):
            result.warnings.append(f"{assay_id} missing technology type")
        if not technology_type.get("termSource"):
            result.warnings.append(f"{assay_id} missing technology type ontology")

        # Check for data files
        if not assay.get("dataFiles"):
            result.warnings.append(f"{assay_id} missing data files")


def main():
    """Main function for testing the validator."""
    import sys

    # Test parameters
    investigation_path = "organized_output/inv_ukf/inv_ukf.json"

    if len(sys.argv) > 1:
        investigation_path = sys.argv[1]

    print("Validating ISA-JSON investigation...")

    # Validate investigation structure
    print("\n1. Validating investigation structure...")
    isa_validator = ISAJsonValidator()
    isa_result = isa_validator.validate_investigation(investigation_path)

    print(f"  Valid: {isa_result.is_valid}")
    print(f"  Errors: {len(isa_result.errors)}")
    print(f"  Warnings: {len(isa_result.warnings)}")
    print(f"  Info: {len(isa_result.info)}")

    if isa_result.errors:
        print("\n  Errors:")
        for error in isa_result.errors:
            print(f"    - {error}")

    if isa_result.warnings:
        print("\n  Warnings:")
        for warning in isa_result.warnings:
            print(f"    - {warning}")

    if isa_result.info:
        print("\n  Info:")
        for info in isa_result.info:
            print(f"    - {info}")

    # Validate data files
    print("\n2. Validating data files...")
    file_validator = DataFileValidator()
    file_result, file_results = file_validator.validate_files(investigation_path)

    print(f"  Valid: {file_result.is_valid}")
    print(f"  Files validated: {len(file_results)}")
    print(f"  Missing files: {len([f for f in file_results if not f.file_exists])}")
    print(f"  Unreadable files: {len([f for f in file_results if not f.file_readable])}")

    # Validate metadata
    print("\n3. Validating metadata...")
    metadata_validator = MetadataValidator()
    metadata_result = metadata_validator.validate_metadata(investigation_path)

    print(f"  Valid: {metadata_result.is_valid}")
    print(f"  Errors: {len(metadata_result.errors)}")
    print(f"  Warnings: {len(metadata_result.warnings)}")

    # Overall result
    print("\n" + "=" * 50)
    overall_valid = isa_result.is_valid and file_result.is_valid and metadata_result.is_valid
    print(f"Overall validation: {'PASSED' if overall_valid else 'FAILED'}")
    print("=" * 50)


if __name__ == "__main__":
    main()
