"""
File Converter Utility for converting files to open scientific standards.

Supported conversions:
- Images (JPEG, PNG, BMP) → TIFF
- Data files (XLSX, XLS, ODS) → CSV
- Sequencing files (AB1, FASTQ, DNA) → GenBank
"""

import hashlib
import logging
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError as e:
    PIL_AVAILABLE = False
    logger.warning(
        f"PIL/Pillow not available for image conversion: {e}. " "Install with: pip install Pillow"
    )

try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError as e:
    PANDAS_AVAILABLE = False
    logger.warning(
        f"pandas not available for data conversion: {e}. " "Install with: pip install pandas"
    )

try:
    from Bio import SeqIO
    from Bio.Seq import Seq
    from Bio.SeqFeature import FeatureLocation, SeqFeature
    from Bio.SeqRecord import SeqRecord

    BIOPYTHON_AVAILABLE = True
except ImportError as e:
    BIOPYTHON_AVAILABLE = False
    logger.warning(
        f"Biopython not available for sequencing conversion: {e}. "
        "Install with: pip install biopython"
    )


class FileConverter:
    """Converter for transforming files to open scientific standards."""

    # File type specifications
    FILE_TYPE_MAPPINGS: Dict[str, Dict[str, Any]] = {
        "image": {
            "source_extensions": [".jpg", ".jpeg", ".png", ".bmp", ".gif"],
            "target_extension": ".tif",
            "target_format": "tiff",
            "mime_type": "image/tiff",
        },
        "data": {
            "source_extensions": [".xlsx", ".xls", ".ods"],
            "target_extension": ".csv",
            "target_format": "csv",
            "mime_type": "text/csv",
        },
        "sequencing": {
            "source_extensions": [".ab1", ".fastq", ".fasta", ".fa", ".gb", ".dna"],
            "target_extension": ".gb",
            "target_format": "genbank",
            "mime_type": "text/plain",
        },
        "report": {
            "source_extensions": [".pdf", ".docx", ".txt"],
            "target_extension": None,  # No conversion
            "target_format": None,
            "mime_type": None,
        },
    }

    def __init__(self):
        """Initialize the file converter."""
        self.conversion_log: List[Dict[str, Any]] = []

    def get_file_type(self, file_path: Path) -> Optional[str]:
        """
        Determine the file type based on extension.

        Args:
            file_path: Path to the file

        Returns:
            File type string or None if unknown
        """
        extension = file_path.suffix.lower()

        for file_type, spec in self.FILE_TYPE_MAPPINGS.items():
            if extension in spec["source_extensions"]:
                return file_type  # type: ignore[no-any-return]

        return None

    def needs_conversion(self, file_path: Path, file_type: str) -> bool:
        """
        Check if a file needs conversion.

        Args:
            file_path: Path to the file
            file_type: Type of file (image, data, sequencing, report)

        Returns:
            True if conversion is needed, False otherwise
        """
        if file_type == "report":
            return False

        spec = self.FILE_TYPE_MAPPINGS.get(file_type, {})
        target_ext = spec.get("target_extension")

        if target_ext is None:
            return False

        return file_path.suffix.lower() != target_ext  # type: ignore[no-any-return]

    def convert_image_to_tiff(self, source_path: Path, target_path: Path) -> Dict[str, Any]:
        """
        Convert image file to TIFF format.

        Args:
            source_path: Path to source image file
            target_path: Path where TIFF file should be saved

        Returns:
            Dictionary with conversion result and metadata
        """
        if not PIL_AVAILABLE:
            return {"success": False, "error": "PIL/Pillow not available for image conversion"}

        try:
            # Open source image
            with Image.open(source_path) as img:
                # Get original metadata
                metadata = {
                    "original_format": img.format,
                    "original_mode": img.mode,
                    "original_size": img.size,
                    "conversion_date": datetime.now().isoformat(),
                }

                # Convert to RGB if necessary (TIFF supports various modes)
                if img.mode not in ("RGB", "L", "CMYK"):
                    img = img.convert("RGB")  # type: ignore[assignment]

                # Save as TIFF with scientific metadata
                img.save(
                    target_path,
                    format="TIFF",
                    compression="lzw",
                    dpi=(300, 300),  # Standard scientific resolution
                )

                # Get file hashes
                metadata["original_hash"] = self._calculate_file_hash(source_path)
                metadata["converted_hash"] = self._calculate_file_hash(target_path)

                return {"success": True, "metadata": metadata}

        except (IOError, OSError) as e:
            logger.error(
                f"File I/O error during image conversion {source_path} -> {target_path}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": f"File I/O error: {e}"}
        except (ValueError, TypeError) as e:
            logger.error(
                f"Data error during image conversion {source_path} -> {target_path}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": f"Data error: {e}"}
        except Exception as e:
            logger.error(
                f"Unexpected error during image conversion {source_path} -> {target_path}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": f"Unexpected error: {e}"}

    def convert_data_to_csv(self, source_path: Path, target_path: Path) -> Dict[str, Any]:
        """
        Convert data file (Excel/ODS) to CSV format.

        Args:
            source_path: Path to source data file
            target_path: Path where CSV file should be saved

        Returns:
            Dictionary with conversion result and metadata
        """
        if not PANDAS_AVAILABLE:
            return {"success": False, "error": "pandas not available for data conversion"}

        try:
            # Read source file
            if source_path.suffix.lower() in [".xlsx", ".xls"]:
                df = pd.read_excel(source_path)
            elif source_path.suffix.lower() == ".ods":
                df = pd.read_excel(source_path, engine="odf")
            else:
                return {
                    "success": False,
                    "error": f"Unsupported data file format: {source_path.suffix}",
                }

            # Save as CSV
            df.to_csv(target_path, index=False, encoding="utf-8")

            # Get metadata
            metadata = {
                "original_format": source_path.suffix,
                "rows": len(df),
                "columns": len(df.columns),
                "column_names": list(df.columns),
                "conversion_date": datetime.now().isoformat(),
            }

            metadata["original_hash"] = self._calculate_file_hash(source_path)
            metadata["converted_hash"] = self._calculate_file_hash(target_path)

            return {"success": True, "metadata": metadata}

        except (IOError, OSError) as e:
            logger.error(
                f"File I/O error during data conversion {source_path} -> {target_path}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": f"File I/O error: {e}"}
        except ValueError as e:
            logger.error(
                f"Data validation error during data conversion {source_path} -> {target_path}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": f"Data validation error: {e}"}
        except Exception as e:
            logger.error(
                f"Unexpected error during data conversion {source_path} -> {target_path}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": f"Unexpected error: {e}"}

    def convert_sequencing_to_genbank(self, source_path: Path, target_path: Path) -> Dict[str, Any]:
        """
        Convert sequencing file to GenBank format.

        Args:
            source_path: Path to source sequencing file
            target_path: Path where GenBank file should be saved

        Returns:
            Dictionary with conversion result and metadata
        """
        if not BIOPYTHON_AVAILABLE:
            return {"success": False, "error": "Biopython not available for sequencing conversion"}

        try:
            # Read source file
            records = list(SeqIO.parse(source_path, self._get_biopython_format(source_path)))

            if not records:
                return {"success": False, "error": "No sequences found in file"}

            # Write as GenBank
            SeqIO.write(records, target_path, "genbank")

            # Get metadata
            metadata = {
                "original_format": source_path.suffix,
                "sequence_count": len(records),
                "sequence_lengths": [len(rec.seq) for rec in records],
                "sequence_ids": [rec.id for rec in records],
                "conversion_date": datetime.now().isoformat(),
            }

            metadata["original_hash"] = self._calculate_file_hash(source_path)
            metadata["converted_hash"] = self._calculate_file_hash(target_path)

            return {"success": True, "metadata": metadata}

        except (IOError, OSError) as e:
            logger.error(
                f"File I/O error during sequencing conversion {source_path} -> {target_path}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": f"File I/O error: {e}"}
        except ValueError as e:
            logger.error(
                f"Data validation error during sequencing conversion {source_path} -> {target_path}: {e}",  # noqa: E501
                exc_info=True,
            )
            return {"success": False, "error": f"Data validation error: {e}"}
        except Exception as e:
            logger.error(
                f"Unexpected error during sequencing conversion {source_path} -> {target_path}: {e}",  # noqa: E501
                exc_info=True,
            )
            return {"success": False, "error": f"Unexpected error: {e}"}

    def convert_dna_to_genbank(self, source_path: Path, target_path: Path) -> Dict[str, Any]:
        """
        Convert SnapGene .dna file to GenBank format.

        SnapGene .dna files are XML-based ZIP archives. This method extracts
        the sequence and feature data from the XML and writes a GenBank file
        using Biopython.

        Args:
            source_path: Path to source .dna file
            target_path: Path where GenBank file should be saved

        Returns:
            Dictionary with conversion result and metadata
        """
        if not BIOPYTHON_AVAILABLE:
            return {"success": False, "error": "Biopython not available for DNA conversion"}

        try:
            # Open .dna file as ZIP archive
            with zipfile.ZipFile(source_path, "r") as zf:
                # Find the XML content file (typically the first non-directory entry)
                xml_filename = None
                for name in zf.namelist():
                    if not name.endswith("/") and name.lower().endswith(".xml"):
                        xml_filename = name
                        break

                if xml_filename is None:
                    # Some .dna files store XML directly without .xml extension
                    for name in zf.namelist():
                        if not name.endswith("/"):
                            xml_filename = name
                            break

                if xml_filename is None:
                    return {"success": False, "error": "No content found in .dna ZIP archive"}

                xml_content = zf.read(xml_filename)

            # Parse XML
            root = ET.fromstring(xml_content)

            # Extract sequence from <Sequence> element
            seq_element = root.find(".//Sequence")
            if seq_element is None:
                # Try alternate paths used by some SnapGene versions
                seq_element = root.find("Sequence")

            if seq_element is None:
                return {"success": False, "error": "No <Sequence> element found in .dna XML"}

            # The sequence text may be in the text content or a 'seq' attribute
            sequence_str = seq_element.text
            if sequence_str is None:
                sequence_str = seq_element.get("seq", "")

            if not sequence_str:
                return {"success": False, "error": "Empty sequence in .dna file"}

            # Clean up sequence (remove whitespace, convert to uppercase)
            sequence_str = sequence_str.strip().upper().replace(" ", "").replace("\n", "")

            # Extract metadata
            name_element = root.find(".//Name")
            if name_element is None:
                name_element = root.find("Name")
            record_name = name_element.text if name_element is not None else source_path.stem

            # Extract molecule type and topology
            topology = "circular"  # Default for plasmids
            molecule_type = "DNA"

            # Check for circular/topology hints in the XML
            props_element = root.find(".//Properties")
            if props_element is not None:
                circular_attr = props_element.get("circular", "")
                if circular_attr.lower() in ("false", "0", "no"):
                    topology = "linear"

            # Build SeqRecord
            seq = Seq(sequence_str)
            record = SeqRecord(
                seq,
                id=record_name,
                name=str(record_name)[:16],  # GenBank name field max 16 chars
                description=f"{record_name} converted from SnapGene .dna format",
            )
            record.annotations["molecule_type"] = molecule_type
            record.annotations["topology"] = topology
            record.annotations["source"] = "SnapGene .dna"
            record.annotations["date"] = datetime.now().strftime("%d-%b-%Y").upper()

            # Extract features from <Features> element
            features_element = root.find(".//Features")
            if features_element is None:
                features_element = root.find("Features")

            feature_count = 0
            if features_element is not None:
                for feature_elem in features_element.findall(".//Feature"):
                    feature_type = feature_elem.get("type", "misc_feature")
                    directionality = feature_elem.get("directionality", "0")

                    # Get location (start, end)
                    start_elem = feature_elem.find(".//Start")
                    end_elem = feature_elem.find(".//End")

                    if start_elem is not None and end_elem is not None:
                        try:
                            start = int(start_elem.get("position", start_elem.text or "0"))
                            end = int(end_elem.get("position", end_elem.text or "0"))
                        except (ValueError, TypeError):
                            continue

                        # SnapGene uses 0-based coordinates; GenBank uses 1-based
                        strand = 1 if directionality in ("1", "true") else 0

                        location = FeatureLocation(start, end, strand=strand)
                        qualifiers = {}

                        # Extract feature label/name
                        label_elem = feature_elem.find(".//Label")
                        if label_elem is None:
                            label_elem = feature_elem.find(".//Name")
                        if label_elem is not None and label_elem.text:
                            qualifiers["label"] = [label_elem.text]

                        # Extract note
                        note_elem = feature_elem.find(".//Note")
                        if note_elem is not None and note_elem.text:
                            qualifiers["note"] = [note_elem.text]

                        feature = SeqFeature(location, type=feature_type, qualifiers=qualifiers)
                        record.features.append(feature)
                        feature_count += 1

            # Write GenBank file
            SeqIO.write([record], target_path, "genbank")

            # Get metadata
            metadata = {
                "original_format": ".dna",
                "sequence_count": 1,
                "sequence_lengths": [len(sequence_str)],
                "sequence_ids": [record_name],
                "feature_count": feature_count,
                "topology": topology,
                "conversion_date": datetime.now().isoformat(),
            }

            metadata["original_hash"] = self._calculate_file_hash(source_path)
            metadata["converted_hash"] = self._calculate_file_hash(target_path)

            return {"success": True, "metadata": metadata}

        except zipfile.BadZipFile as e:
            logger.error(f"Invalid ZIP archive in .dna file {source_path}: {e}", exc_info=True)
            return {"success": False, "error": f"Invalid ZIP archive: {e}"}
        except ET.ParseError as e:
            logger.error(f"XML parse error in .dna file {source_path}: {e}", exc_info=True)
            return {"success": False, "error": f"XML parse error: {e}"}
        except (IOError, OSError) as e:
            logger.error(
                f"File I/O error during DNA conversion {source_path} -> {target_path}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": f"File I/O error: {e}"}
        except Exception as e:
            logger.error(
                f"Unexpected error during DNA conversion {source_path} -> {target_path}: {e}",
                exc_info=True,
            )
            return {"success": False, "error": f"Unexpected error: {e}"}

    def convert_file(
        self, source_path: Path, target_path: Path, file_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Convert a file to its target open standard format.

        Args:
            source_path: Path to source file
            target_path: Path where converted file should be saved
            file_type: Type of file (auto-detected if not provided)

        Returns:
            Dictionary with conversion result and metadata
        """
        # Auto-detect file type if not provided
        if file_type is None:
            file_type = self.get_file_type(source_path)

        if file_type is None:
            return {"success": False, "error": f"Unknown file type: {source_path.suffix}"}

        # Check if conversion is needed
        if not self.needs_conversion(source_path, file_type):
            return {
                "success": True,
                "metadata": {
                    "note": "File already in target format",
                    "original_format": source_path.suffix,
                },
            }

        # Perform conversion based on file type
        result: Dict[str, Any] = {}
        if file_type == "image":
            result = self.convert_image_to_tiff(source_path, target_path)
        elif file_type == "data":
            result = self.convert_data_to_csv(source_path, target_path)
        elif file_type == "sequencing":
            if source_path.suffix.lower() == ".dna":
                result = self.convert_dna_to_genbank(source_path, target_path)
            else:
                result = self.convert_sequencing_to_genbank(source_path, target_path)
        elif file_type == "report":
            result = {
                "success": True,
                "metadata": {
                    "note": "Report files are not converted",
                    "original_format": source_path.suffix,
                },
            }

        # Log conversion
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "source_path": str(source_path),
            "target_path": str(target_path),
            "file_type": file_type,
            "success": result.get("success", False),
        }
        if "error" in result:
            log_entry["error"] = result["error"]
        self.conversion_log.append(log_entry)

        return result

    def _calculate_file_hash(self, file_path: Path) -> str:
        """
        Calculate SHA-256 hash of a file.

        Args:
            file_path: Path to file

        Returns:
            Hexadecimal hash string
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _get_biopython_format(self, file_path: Path) -> str:
        """
        Get Biopython format string for a file.

        Args:
            file_path: Path to file

        Returns:
            Biopython format string
        """
        ext = file_path.suffix.lower()
        format_map = {".ab1": "abi", ".fastq": "fastq", ".fasta": "fasta", ".fa": "fasta"}
        return format_map.get(ext, "fasta")

    def get_conversion_log(self) -> list:
        """
        Get the conversion log.

        Returns:
            List of conversion log entries
        """
        return self.conversion_log.copy()  # type: ignore[no-any-return]

    def clear_conversion_log(self):
        """Clear the conversion log."""
        self.conversion_log.clear()
