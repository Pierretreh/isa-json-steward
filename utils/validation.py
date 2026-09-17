"""
Input validation utilities for the ISA Data Steward GUI application.

This module provides validation functions for IDs, filenames, and other user input.
"""

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# Validation patterns
ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")


def validate_id(id_str: str) -> Tuple[bool, Optional[str]]:
    """
    Validate an ID string.

    Args:
        id_str: ID string to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not id_str:
        return False, "ID cannot be empty"

    if not isinstance(id_str, str):
        return False, "ID must be a string"

    if len(id_str) > 100:
        return False, "ID too long (max 100 characters)"

    if not ID_PATTERN.match(id_str):
        return False, "ID can only contain alphanumeric characters, underscores, and hyphens"

    return True, None


def validate_filename(filename: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a filename.

    Args:
        filename: Filename to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not filename:
        return False, "Filename cannot be empty"

    if not isinstance(filename, str):
        return False, "Filename must be a string"

    # Check for invalid characters
    invalid_chars = '<>:"/\\|?*\0'
    if any(char in filename for char in invalid_chars):
        return False, f"Filename contains invalid characters: {invalid_chars}"

    # Check for reserved names on Windows
    reserved_names = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
    name_without_ext = Path(filename).stem.upper()
    if name_without_ext in reserved_names:
        return False, f"'{name_without_ext}' is a reserved filename"

    return True, None


def is_safe_id(id_str: str) -> bool:
    """
    Check if ID string is safe for path operations (prevents path traversal).

    Args:
        id_str: ID string to check

    Returns:
        True if safe, False otherwise
    """
    if not id_str:
        return False

    # Prevent path traversal
    if ".." in id_str or "/" in id_str or "\\" in id_str:
        return False

    # Only allow alphanumeric, underscore, and hyphen
    return SAFE_ID_PATTERN.match(id_str) is not None


def validate_path(base_path: Path, user_path: str) -> Tuple[bool, Optional[Path]]:
    """
    Validate that a user-provided path is safe and within the base path.

    Args:
        base_path: Base directory that user paths must be within
        user_path: User-provided path (relative or absolute)

    Returns:
        Tuple of (is_valid, resolved_path)
    """
    try:
        resolved = Path(user_path).resolve()

        # If the path is absolute, check it's within base_path
        if resolved.is_absolute():
            try:
                resolved.relative_to(base_path.resolve())
            except ValueError:
                logger.warning(f"Path traversal attempt: {user_path}")
                return False, None

        return True, resolved

    except Exception as e:
        logger.error(f"Error validating path '{user_path}': {e}")
        return False, None


def validate_required_fields(data: dict, required_fields: List[str]) -> Tuple[bool, List[str]]:
    """
    Validate that required fields are present and non-empty in a dictionary.

    Args:
        data: Dictionary to validate
        required_fields: List of required field names

    Returns:
        Tuple of (is_valid, list_of_missing_fields)
    """
    missing = []
    for field in required_fields:
        if field not in data or not data[field]:
            missing.append(field)

    return len(missing) == 0, missing


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """
    Validate an email address.

    Args:
        email: Email address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not email:
        return False, "Email cannot be empty"

    # Email validation pattern - standard RFC 5322 compliant pattern
    # Requires: local-part@domain.tld
    # Local part: alphanumeric, dots, underscores, percent, plus, hyphen (no consecutive dots)
    # Domain: alphanumeric, dots, hyphens (no leading/trailing/consecutive dots)
    # TLD: 2+ letters
    email_pattern = re.compile(
        r"^[a-zA-Z0-9]+([._%+-][a-zA-Z0-9]+)*@[a-zA-Z0-9]+([.-][a-zA-Z0-9]+)*\.[a-zA-Z]{2,}$"
    )
    if not email_pattern.match(email):
        return False, "Invalid email format"

    return True, None


def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a URL.

    Args:
        url: URL to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url:
        return False, "URL cannot be empty"

    # Simple URL validation pattern
    url_pattern = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain
        r"localhost|"  # localhost
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )

    if not url_pattern.match(url):
        return False, "Invalid URL format"

    return True, None
