"""
Constants for the ISA Data Steward GUI application.

This module defines constants for UI elements, timeouts, and other
configuration values that were previously hardcoded.
"""


class UIConstants:
    """UI-related constants."""

    # Window sizes
    MIN_WINDOW_WIDTH = 1200
    MIN_WINDOW_HEIGHT = 800
    DEFAULT_WINDOW_WIDTH = 1400
    DEFAULT_WINDOW_HEIGHT = 900

    # Sidebar
    SIDEBAR_WIDTH = 250
    SIDEBAR_ITEM_HEIGHT = 40

    # Message timeouts (in milliseconds)
    AUTO_SAVE_TIMEOUT = 2000
    MESSAGE_TIMEOUT = 3000
    STATUS_MESSAGE_TIMEOUT = 5000

    # Dialogs
    DIALOG_MIN_WIDTH = 400
    DIALOG_MIN_HEIGHT = 300
    WIZARD_MIN_WIDTH = 600
    WIZARD_MIN_HEIGHT = 500

    # Tree widgets
    TREE_COLUMN_NAME = 0
    TREE_COLUMN_TYPE = 1
    TREE_COLUMN_ID = 2

    # Form elements
    LABEL_WIDTH = 150
    INPUT_MIN_WIDTH = 300
    BUTTON_MIN_WIDTH = 100
    BUTTON_HEIGHT = 32

    # Spacing
    SPACING_SMALL = 5
    SPACING_MEDIUM = 10
    SPACING_LARGE = 20
    SPACING_XLARGE = 30

    # Icons
    ICON_SIZE_SMALL = 16
    ICON_SIZE_MEDIUM = 24
    ICON_SIZE_LARGE = 32

    # Fonts
    FONT_SIZE_SMALL = 10
    FONT_SIZE_NORMAL = 12
    FONT_SIZE_LARGE = 14
    FONT_SIZE_XLARGE = 16


class FileConstants:
    """File-related constants."""

    # File size limits (in bytes)
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
    MAX_IMAGE_SIZE = 50 * 1024 * 1024  # 50 MB

    # Allowed file extensions
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".tif"}
    DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".csv"}
    DATA_EXTENSIONS = {".json", ".xml", ".yaml", ".yml"}


class OntologyConstants:
    """Ontology-related constants."""

    # Default namespace - loaded from configuration
    # DEFAULT_BASE_URL is now loaded from config/settings.json

    @staticmethod
    def get_ontology_main() -> str:
        """Return the main ontology OWL filename from the active profile."""
        from utils.config_loader import get_profile

        return str(get_profile().profile.get("ontology_main_file", "onto.owl"))

    @staticmethod
    def get_ontology_main_ttl() -> str:
        """Return the main ontology TTL filename from the active profile."""
        from utils.config_loader import get_profile

        return str(get_profile().profile.get("ontology_main_ttl", "onto.ttl"))


class ISAJsonConstants:
    """ISA-JSON related constants."""

    # Default IDs
    DEFAULT_INVESTIGATION_ID = "inv_1"
    DEFAULT_STUDY_ID = "study_1"

    # Required fields
    REQUIRED_INVESTIGATION_FIELDS = ["title", "description"]
    REQUIRED_STUDY_FIELDS = ["title", "description"]
    REQUIRED_ASSAY_FIELDS = ["measurementType", "technologyType"]


class ValidationConstants:
    """Validation-related constants."""

    # ID validation
    ID_MIN_LENGTH = 1
    ID_MAX_LENGTH = 100

    # Text validation
    TITLE_MIN_LENGTH = 1
    TITLE_MAX_LENGTH = 255
    DESCRIPTION_MAX_LENGTH = 5000

    # URL validation
    MAX_URL_LENGTH = 2048


class TemplateConstants:
    """Template-related constants for assays and protocols."""

    # Mapping from combo box display names to template file names
    TEMPLATE_FILE_MAPPING: dict[str, str] = {}

    # Numeric units for automatic type detection in parameter values
    NUMERIC_UNITS = [
        "percent",
        "volt",
        "minute",
        "hour",
        "microlitre",
        "nanometer",
        "micromolar",
        "degree celsius",
        "millisecond",
        "pixel",
        "cells per milliliter",
        "second",
        "meter",
        "gram",
        "kilogram",
        "liter",
        "milliliter",
        "lux",
        "rpm",
        "microgram per milliliter",
        "unit per milliliter",
        "nanogram",
        "milligram",
        "day",
        "micrometer",
    ]
