"""
File Manager Utility for centralized file operations in studies.

Handles file upload, conversion, retrieval, and ISA-JSON compliant file references.
"""

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

logger = logging.getLogger(__name__)

from .file_converter import FileConverter  # noqa: E402
from .file_type_validator import FileType, FileTypeValidator  # noqa: E402


class FileManager:
    """Manager for file operations in ISA-JSON Data Steward studies."""

    # Cache of file metadata per (investigation_id, study_id), set lazily
    _file_metadata_cache: Dict[str, List[Dict[str, Any]]] = {}

    # ISA-JSON ontology mappings
    FILE_TYPE_ONTOLOGY = {
        "image": {
            "annotationValue": "image",
            "termSource": "EDAM",
            "termAccession": "http://edamontology.org/data_3567",
        },
        "data": {
            "annotationValue": "data",
            "termSource": "EDAM",
            "termAccession": "http://edamontology.org/data_0006",
        },
        "sequencing": {
            "annotationValue": "sequence",
            "termSource": "EDAM",
            "termAccession": "http://edamontology.org/data_2044",
        },
        "report": {
            "annotationValue": "report",
            "termSource": "EDAM",
            "termAccession": "http://edamontology.org/data_2531",
        },
    }

    def __init__(self, investigations_root: str = "investigations"):
        """
        Initialize the file manager.

        Args:
            investigations_root: Root directory for investigations
        """
        self.investigations_root = Path(investigations_root)
        self.converter = FileConverter()
        self.file_validator = FileTypeValidator()

    def get_study_files_dir(self, investigation_id: str, study_id: str) -> Path:
        """
        Get the files directory for a study.

        Args:
            investigation_id: Investigation ID
            study_id: Study ID

        Returns:
            Path to study files directory
        """
        return self.investigations_root / investigation_id / "studies" / study_id / "files"

    def get_original_files_dir(self, investigation_id: str, study_id: str) -> Path:
        """
        Get the original files directory for a study.

        Args:
            investigation_id: Investigation ID
            study_id: Study ID

        Returns:
            Path to original files directory
        """
        return self.get_study_files_dir(investigation_id, study_id) / "original"

    def get_converted_files_dir(self, investigation_id: str, study_id: str) -> Path:
        """
        Get the converted files directory for a study.

        Args:
            investigation_id: Investigation ID
            study_id: Study ID

        Returns:
            Path to converted files directory
        """
        return self.get_study_files_dir(investigation_id, study_id) / "converted"

    def ensure_study_directories(self, investigation_id: str, study_id: str):
        """
        Ensure all necessary directories exist for a study.

        Args:
            investigation_id: Investigation ID
            study_id: Study ID
        """
        self.get_study_files_dir(investigation_id, study_id).mkdir(parents=True, exist_ok=True)
        self.get_original_files_dir(investigation_id, study_id).mkdir(parents=True, exist_ok=True)
        self.get_converted_files_dir(investigation_id, study_id).mkdir(parents=True, exist_ok=True)

    def validate_file_size(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Validate file size against limits.

        Args:
            file_path: Path to the file to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            file_size = file_path.stat().st_size

            # Check general file size limit
            if file_size > self.file_validator.MAX_FILE_SIZE:
                return False, (
                    f"File too large: {file_size} bytes "
                    f"(maximum {self.file_validator.MAX_FILE_SIZE} bytes)"
                )

            # Check image-specific limit
            detected_type = self.file_validator.detect_file_type(file_path)
            if detected_type == FileType.IMAGE and file_size > self.file_validator.MAX_IMAGE_SIZE:
                return False, (
                    f"Image too large: {file_size} bytes "
                    f"(maximum {self.file_validator.MAX_IMAGE_SIZE} bytes)"
                )

            return True, None

        except Exception as e:
            return False, f"Size validation error: {str(e)}"

    def validate_file_extension(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Validate file extension against allowed types.

        Args:
            file_path: Path to the file to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # If file exists, validate using magic bytes
            if file_path.exists():
                detected_type = self.file_validator.detect_file_type(file_path)

                if detected_type == FileType.UNKNOWN:
                    return False, "Unsupported file type"

                # Check if extension matches detected type
                if not self.file_validator.is_extension_allowed(file_path, detected_type):
                    return False, (
                        f"File extension {file_path.suffix} does not match "
                        f"detected file type {detected_type.value}"
                    )
            else:
                # For non-existent files, just check if extension is in allowed list
                extension = file_path.suffix.lower()
                allowed_extensions = []
                for magic_bytes, offset, file_type, exts in self.file_validator.magic_signatures:
                    allowed_extensions.extend(exts)

                # Add text-based extensions for sequencing and other common formats
                allowed_extensions.extend([".fasta", ".fa", ".fastq", ".csv"])

                if extension not in [ext.lower() for ext in allowed_extensions]:
                    return False, f"File extension {extension} is not allowed"

            return True, None

        except (ValueError, TypeError) as e:
            logger.error(f"Extension validation error for {file_path}: {e}", exc_info=True)
            return False, f"Extension validation error: {str(e)}"
        except Exception as e:
            logger.error(
                f"Unexpected error during extension validation for {file_path}: {e}", exc_info=True
            )
            return False, f"Unexpected error: {str(e)}"

    def add_file(
        self,
        investigation_id: str,
        study_id: str,
        entity_type: str,
        entity_id: str,
        source_path: Path,
        attachment_type: str,
        attachment_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a file to a study entity (assay or process).

        Args:
            investigation_id: Investigation ID
            study_id: Study ID
            entity_type: Type of entity ('assay' or 'process')
            entity_id: ID of the entity
            source_path: Path to source file
            attachment_type: Type of attachment (from template)
            attachment_name: Optional custom name for the attachment

        Returns:
            Dictionary with file metadata and conversion result
        """
        # Ensure directories exist
        self.ensure_study_directories(investigation_id, study_id)

        # Generate unique file ID
        file_id = str(uuid.uuid4())

        # Determine file type
        file_type = self.converter.get_file_type(source_path)
        if file_type is None:
            return {"success": False, "error": f"Unsupported file type: {source_path.suffix}"}

        # Create entity-specific directory
        entity_dir_name = f"{entity_type}_{entity_id}"
        original_dir = self.get_original_files_dir(investigation_id, study_id) / entity_dir_name
        original_dir.mkdir(parents=True, exist_ok=True)

        # Generate file names
        original_filename = f"{file_id}{source_path.suffix}"
        original_path = original_dir / original_filename

        # Copy original file
        shutil.copy2(source_path, original_path)

        # Determine target format and path
        spec = self.converter.FILE_TYPE_MAPPINGS[file_type]
        target_ext = spec.get("target_extension")

        converted_path = None
        conversion_result = None

        if target_ext and self.converter.needs_conversion(source_path, file_type):
            # Create converted directory
            converted_dir = (
                self.get_converted_files_dir(investigation_id, study_id) / entity_dir_name
            )
            converted_dir.mkdir(parents=True, exist_ok=True)

            converted_filename = f"{file_id}{target_ext}"
            converted_path = converted_dir / converted_filename

            # Perform conversion
            conversion_result = self.converter.convert_file(
                original_path, converted_path, file_type
            )
        else:
            conversion_result = {"success": True, "metadata": {"note": "No conversion needed"}}

        # Build file metadata
        file_metadata = {
            "file_id": file_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "attachment_type": attachment_type,
            "attachment_name": attachment_name or attachment_type,
            "file_type": file_type,
            "original_filename": source_path.name,
            "original_path": str(
                original_path.relative_to(self.get_study_files_dir(investigation_id, study_id))
            ),
            "original_format": source_path.suffix,
            "converted_path": (
                str(
                    converted_path.relative_to(self.get_study_files_dir(investigation_id, study_id))
                )
                if converted_path
                else None
            ),
            "converted_format": target_ext,
            "conversion_status": "completed" if conversion_result["success"] else "failed",
            "conversion_metadata": conversion_result.get("metadata", {}),
            "upload_date": datetime.now().isoformat(),
            "file_size_bytes": source_path.stat().st_size,
        }

        if not conversion_result["success"]:
            file_metadata["conversion_error"] = conversion_result.get("error", "")

        return {"success": True, "file_metadata": file_metadata}

    def get_files(
        self,
        investigation_id: str,
        study_id: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get files for a study, optionally filtered by entity.

        Args:
            investigation_id: Investigation ID
            study_id: Study ID
            entity_type: Optional entity type filter ('assay' or 'process')
            entity_id: Optional entity ID filter

        Returns:
            List of file metadata dictionaries
        """
        files = []

        # Check cache first for files added via add_file
        cache_key = f"{investigation_id}_{study_id}"
        if hasattr(self, "_file_metadata_cache") and cache_key in self._file_metadata_cache:
            files.extend(self._file_metadata_cache[cache_key])

        # Also read from study.json if it exists (for existing files)
        study_json_path = (
            self.investigations_root / investigation_id / "studies" / study_id / "study.json"
        )

        study_data = None  # Initialize study_data outside the if block

        if study_json_path.exists():
            try:
                with open(study_json_path, "r", encoding="utf-8") as f:
                    study_data = json.load(f)
                files.extend(study_data.get("files", []))
            except Exception as e:
                logger.error(f"get_files: Error loading study.json: {e}", exc_info=True)
                pass

        # Also collect files from assays
        # Handle both ISA-JSON format (studies[0].assays) and simple format (assays)
        logger.debug(f"get_files: study_data is None: {study_data is None}")
        if (
            study_data
            and "studies" in study_data
            and isinstance(study_data["studies"], list)
            and len(study_data["studies"]) > 0
        ):
            # ISA-JSON format: files are in studies[0].assays[i].dataFiles
            raw_assays = study_data["studies"][0].get("assays", [])
            for assay in raw_assays:
                # Extract assay name from @id since ISA-JSON doesn't allow 'name' property
                assay_id = assay.get("@id", "")
                if "#" in assay_id:
                    assay_name = assay_id.split("#")[-1].replace("assay_", "").replace("_", " ")
                else:
                    assay_name = assay.get("name", "")  # Fallback for internal format
                # Files are stored as dataFiles in ISA-JSON format
                data_files = assay.get("dataFiles", [])
                for data_file in data_files:
                    # Convert ISA-JSON file reference to file metadata format
                    file_meta = self._convert_isa_file_to_meta(
                        data_file, assay_name, investigation_id, study_id
                    )
                    files.append(file_meta)
        elif study_data:
            # Simple format: files are in assays[i].files
            assays = study_data.get("assays", [])
            for assay in assays:
                assay_name = assay.get("name", "")
                assay_files = assay.get("files", [])
                for file_meta in assay_files:
                    # Ensure entity_type and entity_id are set
                    if "entity_type" not in file_meta:
                        file_meta["entity_type"] = "assay"
                    if "entity_id" not in file_meta:
                        file_meta["entity_id"] = assay_name
                    files.append(file_meta)

        # Apply filters
        if entity_type:
            files = [f for f in files if f.get("entity_type") == entity_type]
        if entity_id:
            files = [f for f in files if f.get("entity_id") == entity_id]

        return files

    def upload_file(
        self, investigation_id: str, study_id: str, file_path: Path, file_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Upload a file to a study (simplified version for testing).

        Args:
            investigation_id: Investigation ID
            study_id: Study ID
            file_path: Path to file to upload
            file_type: Type of file ('image', 'data', 'sequencing')

        Returns:
            Dictionary with file metadata or None if failed
        """
        # Ensure directories exist
        self.ensure_study_directories(investigation_id, study_id)

        # Validate file exists
        if not file_path.exists():
            return None

        # Generate unique file ID
        file_id = str(uuid.uuid4())

        # Determine original directory
        original_dir = self.get_original_files_dir(investigation_id, study_id)
        original_dir.mkdir(parents=True, exist_ok=True)

        # Copy original file
        original_filename = f"{file_id}{file_path.suffix}"
        original_path = original_dir / original_filename
        shutil.copy2(file_path, original_path)

        # Determine converted path (simplified - no conversion for now)
        converted_path = None
        if file_type == "image":
            converted_dir = self.get_converted_files_dir(investigation_id, study_id)
            converted_dir.mkdir(parents=True, exist_ok=True)
            converted_filename = f"{file_id}.png"
            converted_path = converted_dir / converted_filename
            # Simple copy for now (would use converter in production)
            shutil.copy2(file_path, converted_path)

        # Build file metadata
        file_metadata = {
            "file_id": file_id,
            "filename": file_path.name,
            "file_type": file_type,
            "original_path": str(
                original_path.relative_to(self.get_study_files_dir(investigation_id, study_id))
            ),
            "converted_path": (
                str(
                    converted_path.relative_to(self.get_study_files_dir(investigation_id, study_id))
                )
                if converted_path
                else None
            ),
            "upload_date": datetime.now().isoformat(),
            "file_size_bytes": file_path.stat().st_size,
        }

        # Store file metadata in internal study_data structure
        # Note: Files are NOT saved directly to study.json to avoid adding
        # internal application fields that violate ISA-JSON schema.
        # The files will be exported via ISAJsonExporter when save_study_json is called.
        # Store files in a way that ISAJsonExporter can access them
        if not hasattr(self, "_file_metadata_cache"):
            self._file_metadata_cache = {}

        cache_key = f"{investigation_id}_{study_id}"
        if cache_key not in self._file_metadata_cache:
            self._file_metadata_cache[cache_key] = []
        self._file_metadata_cache[cache_key].append(file_metadata)

        return file_metadata

    def list_files(
        self, investigation_id: str, study_id: str, file_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List files in a study, optionally filtered by type.

        Args:
            investigation_id: Investigation ID
            study_id: Study ID
            file_type: Optional file type filter ('image', 'data', 'sequencing')

        Returns:
            List of file metadata dictionaries
        """
        files = self.get_files(investigation_id, study_id)

        if file_type:
            files = [f for f in files if f.get("file_type") == file_type]

        return files

    def get_file_type(self, file_path: Path) -> Optional[str]:
        """
        Get file type from file extension.

        Args:
            file_path: Path to file

        Returns:
            File type string ('image', 'data', 'sequencing') or None
        """
        # Image extensions
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif"}
        # Data file extensions
        data_extensions = {".xlsx", ".xls", ".csv", ".txt", ".json", ".xml", ".pdf"}
        # Sequencing file extensions
        sequencing_extensions = {".fastq", ".fq", ".ab1", ".fasta", ".fa", ".bam", ".sam"}

        ext = file_path.suffix.lower()

        if ext in image_extensions:
            return "image"
        elif ext in data_extensions:
            return "data"
        elif ext in sequencing_extensions:
            return "sequencing"
        else:
            return None

    def _convert_isa_file_to_meta(
        self, data_file: dict, assay_name: str, investigation_id: str, study_id: str
    ) -> dict:
        """
        Convert ISA-JSON dataFile format to file metadata format.

        Args:
            data_file: ISA-JSON dataFile dictionary
            assay_name: Name of the assay
            investigation_id: Investigation ID
            study_id: Study ID

        Returns:
            File metadata dictionary
        """
        # Get file path from dataFile
        # First try to get path from "path" property (for backward compatibility)
        file_path = data_file.get("path", "")

        # If path is empty, try to get it from comments (following BII-S-3.json pattern)
        if not file_path:
            comments = data_file.get("comments", [])
            for comment in comments:
                if comment.get("name") == "TraceDB":
                    file_path = comment.get("value", "")
                    break

        # Normalize the file path: strip leading "files/" prefix so the path is
        # relative to the study "files/" directory (consistent with upload_file).
        # ISA-JSON TraceDB comments store paths like "files/original/foo.fcs" but
        # FileManager expects paths relative to the files/ dir: "original/foo.fcs".
        if file_path.startswith("files/") or file_path.startswith("files\\"):
            file_path = file_path[6:]

        # Determine file_type from ISA-JSON "type" field (e.g. "Raw Data File")
        # as well as from ontology annotation "fileType".
        isa_type = data_file.get("type", "")
        file_type = self._get_file_type_from_isa_type(isa_type)
        if file_type == "data":
            # Fallback: try ontology-based detection
            file_type = self._get_file_type_from_ontology(data_file.get("fileType", {}))
        if file_type == "data":
            # Fallback: detect from filename extension
            file_type = self._get_file_type_from_name(data_file.get("name", "")) or "data"

        # Try to get actual file size from filesystem if path exists
        file_size = 0
        if file_path:
            try:
                study_files_dir = self.get_study_files_dir(investigation_id, study_id)
                full_path = study_files_dir / file_path
                if full_path.exists():
                    file_size = full_path.stat().st_size
            except Exception:
                pass

        # Extract file size from ISA-JSON comment if present
        if file_size == 0:
            for comment in data_file.get("comments", []):
                if comment.get("name") == "fileSize":
                    try:
                        file_size = int(comment.get("value", 0))
                    except (ValueError, TypeError):
                        pass
                    break

        # Extract key fields from data_file
        data_file_name = data_file.get("name", "")
        data_file_id = data_file.get("@id", "")

        file_meta = {
            "file_id": (
                data_file_id.split("_")[-1]
                if "_" in data_file_id
                else data_file_id.split("/")[-1].split("#")[-1] if data_file_id else ""
            ),
            "entity_type": "assay",
            "entity_id": assay_name,
            "attachment_name": data_file_name,
            "original_filename": data_file_name,
            "file_type": file_type,
            "original_path": file_path,
            "converted_path": file_path,
            "conversion_status": "completed",
            "upload_date": datetime.now().isoformat(),
            "file_size_bytes": file_size,
            "isa_type": isa_type,
        }

        return file_meta

    def _get_file_type_from_ontology(self, file_type_ontology: dict) -> str:
        """
        Get file type from ontology annotation.

        Args:
            file_type_ontology: File type ontology dictionary

        Returns:
            File type string (image, data, sequencing, report)
        """
        annotation_value = file_type_ontology.get("annotationValue", "").lower()
        if annotation_value in ["image", "data", "sequence", "report"]:
            if annotation_value == "sequence":
                return "sequencing"
            return str(annotation_value)
        return "data"

    @staticmethod
    def _get_file_type_from_isa_type(isa_type: str) -> str:
        """
        Map ISA-JSON data file type strings to internal file type categories.

        Args:
            isa_type: ISA-JSON type string (e.g. "Raw Data File", "Image File")

        Returns:
            Internal file type string (image, data, sequencing, report)
        """
        if not isa_type:
            return "data"
        t = isa_type.lower()
        if "image" in t:
            return "image"
        if "derived" in t:
            return "data"
        if "raw data" in t or "acquisition parameter" in t:
            return "data"
        if "sequence" in t:
            return "sequencing"
        if "report" in t:
            return "report"
        return "data"

    @staticmethod
    def _get_file_type_from_name(filename: str) -> Optional[str]:
        """
        Detect file type from file extension.

        Args:
            filename: File name (e.g. "image.tiff")

        Returns:
            File type string or None if unknown
        """
        if not filename:
            return None
        ext = Path(filename).suffix.lower()
        image_extensions = {".tiff", ".tif", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".czi"}
        data_extensions = {".fcs", ".xlsx", ".xls", ".csv", ".wsp"}
        sequencing_extensions = {".ab1", ".fastq", ".fasta", ".fa", ".gb"}
        if ext in image_extensions:
            return "image"
        elif ext in data_extensions:
            return "data"
        elif ext in sequencing_extensions:
            return "sequencing"
        return None

    def get_file_by_id(
        self, investigation_id: str, study_id: str, file_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get file metadata by file ID.

        Args:
            investigation_id: Investigation ID
            study_id: Study ID
            file_id: File ID

        Returns:
            File metadata dictionary or None if not found
        """
        files = self.get_files(investigation_id, study_id)
        for file_meta in files:
            if file_meta.get("file_id") == file_id:
                return file_meta
        return None

    def delete_file(self, investigation_id: str, study_id: str, file_id: str) -> bool:
        """
        Delete a file from the study.

        Args:
            investigation_id: Investigation ID
            study_id: Study ID
            file_id: File ID

        Returns:
            True if file was deleted, False if not found
        """
        # Get file metadata
        file_meta = self.get_file_by_id(investigation_id, study_id, file_id)
        if file_meta is None:
            return False

        # Get study files directory
        files_dir = self.get_study_files_dir(investigation_id, study_id)

        # Delete original file
        original_path = files_dir / file_meta["original_path"]
        if original_path.exists():
            original_path.unlink()

        # Delete converted file if exists
        if file_meta.get("converted_path"):
            converted_path = files_dir / file_meta["converted_path"]
            if converted_path.exists():
                converted_path.unlink()

        # Remove from cache instead of directly modifying study.json
        # to avoid adding internal application fields that violate ISA-JSON schema
        cache_key = f"{investigation_id}_{study_id}"
        if hasattr(self, "_file_metadata_cache") and cache_key in self._file_metadata_cache:
            self._file_metadata_cache[cache_key] = [
                f for f in self._file_metadata_cache[cache_key] if f.get("file_id") != file_id
            ]

        return True

    def generate_isa_file_reference(
        self, file_metadata: Dict[str, Any], investigation_id: str, study_id: str
    ) -> Dict[str, Any]:
        """
        Generate an ISA-JSON compliant file reference.

        Args:
            file_metadata: File metadata dictionary
            investigation_id: Investigation ID
            study_id: Study ID

        Returns:
            ISA-JSON compliant file reference dictionary
        """
        # Generate ISA-JSON ID
        entity_ref = f"{file_metadata['entity_type']}_{file_metadata['entity_id']}"
        isa_id = (
            f"https://example.org/investigations/{investigation_id}/"
            f"studies/{study_id}#file_{entity_ref}_{file_metadata['file_id'][:8]}"
        )

        # Get file type ontology and convert to ISA-JSON type enum
        file_type = file_metadata.get("file_type", "data")
        file_type_ontology = self.FILE_TYPE_ONTOLOGY.get(
            file_type, {"annotationValue": file_type, "termSource": "EDAM"}
        )
        isa_type = self._ontology_to_data_type(file_type_ontology)

        # Build reference - only include properties allowed by ISA-JSON schema
        reference = {
            "@id": isa_id,
            "name": file_metadata.get("attachment_name", file_metadata["original_filename"]),
            "type": isa_type,
        }

        # Add comments if conversion happened (must be an array of comment objects)
        if file_metadata.get("converted_path"):
            reference["comments"] = [
                {
                    "name": "description",
                    "value": f"Converted from {file_metadata['original_format']} to {file_metadata['converted_format']}",  # noqa: E501
                }
            ]

        return reference

    @staticmethod
    def _ontology_to_data_type(ontology: Dict[str, str]) -> str:
        """
        Convert ontology annotation to ISA-JSON Data type enum value.

        The ISA-JSON schema allows these values for the 'type' field:
        - "Raw Data File"
        - "Derived Data File"
        - "Image File"
        - "Acquisition Parameter Data File"
        - "Derived Spectral Data File"
        - "Protein Assignment File"
        - "Raw Spectral Data File"
        - "Peptide Assignment File"
        - "Array Data File"
        - "Derived Array Data File"
        - "Post Translational Modification Assignment File"
        - "Derived Array Data Matrix File"
        - "Free Induction Decay Data File"
        - "Metabolite Assignment File"
        - "Array Data Matrix File"

        Args:
            ontology: Ontology dictionary with annotationValue field

        Returns:
            ISA-JSON compliant type string
        """
        annotation_value = ontology.get("annotationValue", "").lower()

        # Map ontology annotation values to ISA-JSON type enums
        type_map = {
            "image": "Image File",
            "data": "Derived Data File",
            "sequence": "Raw Spectral Data File",
            "report": "Derived Data File",
        }

        return type_map.get(annotation_value, "Derived Data File")

    def get_expected_attachments(self, template_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get expected attachments from a template.

        Args:
            template_data: Template data dictionary

        Returns:
            List of expected attachment specifications
        """
        return cast(List[Dict[str, Any]], template_data.get("expectedAttachments", []))

    def validate_file_attachment(
        self, file_path: Path, attachment_spec: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that a file matches an attachment specification.

        Args:
            file_path: Path to file
            attachment_spec: Attachment specification from template

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check file type
        expected_type = attachment_spec.get("fileType")
        actual_type = self.converter.get_file_type(file_path)

        if expected_type and actual_type != expected_type:
            return False, f"Expected file type '{expected_type}', got '{actual_type}'"

        # Check extension
        allowed_extensions = attachment_spec.get("allowedExtensions", [])
        if allowed_extensions:
            ext = file_path.suffix.lower()
            if ext not in allowed_extensions:
                return (
                    False,
                    f"File extension '{ext}' not allowed. Allowed: {', '.join(allowed_extensions)}",
                )

        return True, None

    def get_file_statistics(self, investigation_id: str, study_id: str) -> Dict[str, Any]:
        """
        Get statistics about files in a study.

        Args:
            investigation_id: Investigation ID
            study_id: Study ID

        Returns:
            Dictionary with file statistics
        """
        files = self.get_files(investigation_id, study_id)

        stats: Dict[str, Any] = {
            "total_files": len(files),
            "by_type": {},
            "by_entity_type": {},
            "conversion_status": {"completed": 0, "failed": 0, "not_needed": 0},
            "total_size_bytes": 0,
        }

        for file_meta in files:
            # Count by type
            file_type = file_meta.get("file_type", "unknown")
            stats["by_type"][file_type] = stats["by_type"].get(file_type, 0) + 1

            # Count by entity type
            entity_type = file_meta.get("entity_type", "unknown")
            stats["by_entity_type"][entity_type] = stats["by_entity_type"].get(entity_type, 0) + 1

            # Count conversion status
            status = file_meta.get("conversion_status", "unknown")
            if status in stats["conversion_status"]:
                stats["conversion_status"][status] += 1

            # Sum file sizes
            stats["total_size_bytes"] += file_meta.get("file_size_bytes", 0)

        return stats
