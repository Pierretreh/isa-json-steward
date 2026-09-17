"""
File Type Validator with Magic Bytes Detection

This module provides secure file type validation using magic bytes (file signatures)
to detect actual file types regardless of extension. This prevents users from
uploading malicious files with disguised extensions.
"""

import logging
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple, cast

logger = logging.getLogger(__name__)


class FileType(Enum):
    """Supported file types for validation."""

    IMAGE = "image"
    DATA = "data"
    SEQUENCING = "sequencing"
    REPORT = "report"
    UNKNOWN = "unknown"


# Magic byte signatures for common file types
# Format: (magic_bytes, offset, file_type, extensions)
MAGIC_SIGNATURES: List[Tuple[bytes, int, "FileType", List[str]]] = [
    # Image files
    (b"\xff\xd8\xff", 0, FileType.IMAGE, [".jpg", ".jpeg"]),
    (b"\x89PNG\r\n\x1a\n", 0, FileType.IMAGE, [".png"]),
    (b"GIF87a", 0, FileType.IMAGE, [".gif"]),
    (b"GIF89a", 0, FileType.IMAGE, [".gif"]),
    (b"BM", 0, FileType.IMAGE, [".bmp"]),
    (b"II*\x00", 0, FileType.IMAGE, [".tiff", ".tif"]),
    (b"MM\x00*", 0, FileType.IMAGE, [".tiff", ".tif"]),
    (b"\x49\x49\x2a\x00", 0, FileType.IMAGE, [".tiff", ".tif"]),
    (b"\x4d\x4d\x00\x2a", 0, FileType.IMAGE, [".tiff", ".tif"]),
    # Data files
    (b"PK\x03\x04", 0, FileType.DATA, [".xlsx", ".xlsm", ".xlsb"]),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", 0, FileType.DATA, [".xls"]),
    (b"PK\x05\x06", 0, FileType.DATA, [".xlsx", ".xlsm"]),
    (b"\x50\x4b\x03\x04\x14\x00\x06\x00", 0, FileType.DATA, [".xlsx", ".xlsm"]),
    (b"ODS", 0, FileType.DATA, [".ods"]),
    # Sequencing files
    (b"@HD\tVN", 0, FileType.SEQUENCING, [".ab1"]),
    (b"@HD\tSN", 0, FileType.SEQUENCING, [".ab1"]),
    (b"@HD\tAN", 0, FileType.SEQUENCING, [".ab1"]),
    (b"@HD\tAP", 0, FileType.SEQUENCING, [".ab1"]),
    (b"LOCUS", 0, FileType.SEQUENCING, [".gb", ".genbank"]),
    (b">", 0, FileType.SEQUENCING, [".fasta", ".fa", ".fastq"]),
    # Report files
    (b"%PDF-", 0, FileType.REPORT, [".pdf"]),
    (b"PK\x03\x04", 0, FileType.REPORT, [".docx"]),
    (b"\xd0\xcf\x11\xe0", 0, FileType.REPORT, [".doc"]),
]


class FileTypeError(Exception):
    """Exception raised when file type validation fails."""

    pass


class FileSizeError(Exception):
    """Exception raised when file size exceeds limits."""

    pass


class FileTypeValidator:
    """Validator for file types using magic bytes."""

    # Size limits (in bytes)
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
    MAX_IMAGE_SIZE = 50 * 1024 * 1024  # 50 MB

    def __init__(self):
        """Initialize the file type validator."""
        self.magic_signatures = MAGIC_SIGNATURES

    def validate_file(
        self, file_path: Path, expected_type: Optional[FileType] = None, check_size: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a file by checking its magic bytes and size.

        Args:
            file_path: Path to the file to validate
            expected_type: Expected file type (None to allow any type)
            check_size: Whether to check file size limits

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check if file exists
            if not file_path.exists():
                return False, f"File not found: {file_path}"

            # Check file size
            if check_size:
                is_valid, size_error = self._validate_file_size(file_path)
                if not is_valid:
                    return False, size_error

            # Detect actual file type from magic bytes
            detected_type = self.detect_file_type(file_path)

            # Check if detected type matches expected type
            if expected_type and detected_type != expected_type:
                return False, (
                    f"File type mismatch: expected {expected_type.value}, "
                    f"detected {detected_type.value}"
                )

            # Check if file type is supported
            if detected_type == FileType.UNKNOWN:
                return False, "Unsupported file type"

            return True, None

        except Exception as e:
            logger.error(f"Error validating file {file_path}: {e}", exc_info=True)
            return False, f"Validation error: {str(e)}"

    def detect_file_type(self, file_path: Path) -> FileType:
        """
        Detect file type by reading magic bytes.

        Args:
            file_path: Path to the file

        Returns:
            Detected FileType enum value
        """
        try:
            with open(file_path, "rb") as f:
                header = f.read(32)  # Read first 32 bytes for detection

            # Check against known magic signatures
            for magic_bytes, offset, file_type, extensions in self.magic_signatures:
                if header[offset : offset + len(magic_bytes)] == magic_bytes:
                    logger.debug(f"Detected file type {file_type.value} for {file_path}")
                    return cast(FileType, file_type)

            # If no signature matches, check for text-based files
            if self._is_text_file(file_path):
                # Could be FASTA/FASTQ or plain text
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if content.startswith(">"):
                    return FileType.SEQUENCING  # FASTA
                elif any(line.startswith("@") for line in content.split("\n")[:10]):
                    return FileType.SEQUENCING  # FASTQ

            logger.warning(f"Unknown file type for {file_path}")
            return FileType.UNKNOWN

        except Exception as e:
            logger.error(f"Error detecting file type for {file_path}: {e}", exc_info=True)
            return FileType.UNKNOWN

    def _validate_file_size(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Validate file size against limits.

        Args:
            file_path: Path to the file

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            file_size = file_path.stat().st_size

            # Check general file size limit
            if file_size > self.MAX_FILE_SIZE:
                return False, (
                    f"File too large: {file_size} bytes " f"(maximum {self.MAX_FILE_SIZE} bytes)"
                )

            # Check image-specific limit
            file_type = self.detect_file_type(file_path)
            if file_type == FileType.IMAGE and file_size > self.MAX_IMAGE_SIZE:
                return False, (
                    f"Image too large: {file_size} bytes " f"(maximum {self.MAX_IMAGE_SIZE} bytes)"
                )

            return True, None

        except Exception as e:
            logger.error(f"Error validating file size for {file_path}: {e}", exc_info=True)
            return False, f"Size validation error: {str(e)}"

    def _is_text_file(self, file_path: Path) -> bool:
        """
        Check if a file is a text file by reading a sample.

        Args:
            file_path: Path to the file

        Returns:
            True if file appears to be text, False otherwise
        """
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(1024)

                # Check for null bytes (indicates binary file)
                if b"\x00" in chunk:
                    return False

                # Check for high ratio of non-printable characters
                non_printable = sum(1 for byte in chunk if byte < 32 or byte > 126)
                if non_printable / len(chunk) > 0.3:
                    return False

                return True

        except Exception:
            return False

    def get_allowed_extensions(self, file_type: FileType) -> list[str]:
        """
        Get allowed extensions for a given file type.

        Args:
            file_type: The file type to get extensions for

        Returns:
            List of allowed file extensions
        """
        extensions = []
        for magic_bytes, offset, ft, exts in self.magic_signatures:
            if ft == file_type:
                extensions.extend(exts)

        # Add text-based extensions for sequencing
        if file_type == FileType.SEQUENCING:
            extensions.extend([".fasta", ".fa", ".fastq"])

        return list(set(extensions))

    def is_extension_allowed(self, file_path: Path, file_type: Optional[FileType] = None) -> bool:
        """
        Check if file extension is allowed for the detected type.

        Args:
            file_path: Path to the file
            file_type: Expected file type (None to auto-detect)

        Returns:
            True if extension is allowed, False otherwise
        """
        detected_type = file_type or self.detect_file_type(file_path)
        allowed_extensions = self.get_allowed_extensions(detected_type)

        return file_path.suffix.lower() in [ext.lower() for ext in allowed_extensions]


# Singleton instance for convenience
_validator = None


def get_validator() -> FileTypeValidator:
    """
    Get the singleton validator instance.

    Returns:
        FileTypeValidator instance
    """
    global _validator
    if _validator is None:
        _validator = FileTypeValidator()
    return _validator


def validate_file(
    file_path: Path, expected_type: Optional[FileType] = None, check_size: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Convenience function to validate a file.

    Args:
        file_path: Path to the file to validate
        expected_type: Expected file type (None to allow any type)
        check_size: Whether to check file size limits

    Returns:
        Tuple of (is_valid, error_message)
    """
    validator = get_validator()
    return validator.validate_file(file_path, expected_type, check_size)


def detect_file_type(file_path: Path) -> FileType:
    """
    Convenience function to detect file type.

    Args:
        file_path: Path to the file

    Returns:
        Detected FileType enum value
    """
    validator = get_validator()
    return validator.detect_file_type(file_path)
