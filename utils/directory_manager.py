#!/usr/bin/env python3
"""
Directory Manager Utility Module

This module provides utilities for managing the project directory structure,
including path resolution, directory creation, and file operations.

Usage:
    from utils.directory_manager import DirectoryManager

    dm = DirectoryManager()
    study_path = dm.get_study_path("inv_1", "study_1")
    dm.create_study_directory("inv_1", "study_1")
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .validation import is_safe_id

logger = logging.getLogger(__name__)


class DirectoryManager:
    """Manager for ISA-JSON Data Steward directory structure."""

    def __init__(self, base_path: Optional[str] = None, config_path: Optional[str] = None):
        """
        Initialize the Directory Manager.

        Args:
            base_path: Base path for the project (default: script directory)
            config_path: Path to the directory structure configuration file
        """
        self.base_path = Path(base_path) if base_path else Path(__file__).parent.parent.absolute()
        self.config_path = (
            Path(config_path)
            if config_path
            else self.base_path / "config" / "directory_structure.json"
        )
        self.settings_path = self.base_path / "config" / "settings.json"

        self._config: Dict = {}
        self._settings: Dict = {}

        # Load configuration
        self._load_config()

    def _load_config(self) -> None:
        """Load directory structure configuration."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
        except FileNotFoundError:
            logger.warning(f"Configuration file not found at {self.config_path}, using defaults")
            self._config = self._get_default_config()
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in configuration file: {e}", exc_info=True)
            self._config = self._get_default_config()

    def _load_settings(self) -> None:
        """Load application settings."""
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                self._settings = json.load(f)
        except FileNotFoundError:
            logger.warning(f"Settings file not found at {self.settings_path}")
            self._settings = {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in settings file: {e}", exc_info=True)
            self._settings = {}

    def _get_default_config(self) -> Dict:
        """Return default directory structure configuration."""
        return {
            "investigations_root": "investigations",
            "study_subdirs": {
                "raw_data": ["images", "sequences", "measurements", "logs"],
                "processed_data": ["tiff", "analysis", "derived"],
                "assays": ["sds_page", "microscopy", "toxicity"],
                "protocols": [],
                "reports": [],
                "versions": [],
            },
            "assay_subdirs": {
                "sds_page": ["gel_images", "band_analysis", "metadata"],
                "microscopy": ["depot_images", "cell_images", "image_analysis", "metadata"],
                "toxicity": ["fluorescence_data", "viability_data", "metadata"],
            },
        }

    # ----------------------------------------------------------------------
    # Path Resolution Methods
    # ----------------------------------------------------------------------
    def get_investigations_root(self) -> Path:
        """Get the investigations root directory path."""
        return self.base_path / str(self._config.get("investigations_root", "investigations"))

    def get_investigation_path(self, investigation_id: str) -> Path:
        """
        Get the path to an investigation directory.

        Args:
            investigation_id: Investigation identifier (e.g., "inv_1")

        Returns:
            Path to the investigation directory
        """
        if not is_safe_id(investigation_id):
            logger.error(f"Invalid investigation ID: {investigation_id}")
            raise ValueError(f"Invalid investigation ID: {investigation_id}")
        return self.get_investigations_root() / investigation_id

    def get_studies_root(self, investigation_id: str) -> Path:
        """
        Get the path to the studies directory within an investigation.

        Args:
            investigation_id: Investigation identifier

        Returns:
            Path to the studies directory
        """
        return self.get_investigation_path(investigation_id) / "studies"

    def get_study_path(self, investigation_id: str, study_id: str) -> Path:
        """
        Get the path to a study directory.

        Args:
            investigation_id: Investigation identifier
            study_id: Study identifier (e.g., "study_1")

        Returns:
            Path to the study directory
        """
        if not is_safe_id(investigation_id):
            logger.error(f"Invalid investigation ID: {investigation_id}")
            raise ValueError(f"Invalid investigation ID: {investigation_id}")
        if not is_safe_id(study_id):
            logger.error(f"Invalid study ID: {study_id}")
            raise ValueError(f"Invalid study ID: {study_id}")
        return self.get_studies_root(investigation_id) / study_id

    def get_study_json_path(self, investigation_id: str, study_id: str) -> Path:
        """
        Get the path to a study's JSON file.

        Args:
            investigation_id: Investigation identifier
            study_id: Study identifier

        Returns:
            Path to the study.json file
        """
        return self.get_study_path(investigation_id, study_id) / "study.json"

    def get_templates_root(self) -> Path:
        """Get the templates root directory path."""
        return self.base_path / str(self._config.get("templates_root", "templates"))

    def get_template_path(self, template_name: str) -> Path:
        """
        Get the path to a template file.

        Args:
            template_name: Name of the template file

        Returns:
            Path to the template file
        """
        return self.get_templates_root() / template_name

    def get_ontologies_root(self) -> Path:
        """Get the ontologies root directory path."""
        return self.base_path / str(self._config.get("ontologies_root", "ontologies"))

    def get_exports_root(self) -> Path:
        """Get the exports root directory path."""
        return self.base_path / str(self._config.get("exports_root", "exports"))

    def get_archive_root(self) -> Path:
        """Get the archive root directory path."""
        return self.base_path / str(self._config.get("archive_root", "archive"))

    # ----------------------------------------------------------------------
    # Directory Creation Methods
    # ----------------------------------------------------------------------
    def create_directory(self, path: Path) -> bool:
        """
        Create a directory if it doesn't exist.

        Args:
            path: Path to the directory

        Returns:
            True if successful, False otherwise
        """
        try:
            path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Error creating directory {path}: {e}", exc_info=True)
            return False

    def create_study_directory(self, investigation_id: str, study_id: str) -> Optional[Path]:
        """
        Create a complete study directory structure.

        Args:
            investigation_id: Investigation identifier
            study_id: Study identifier

        Returns:
            Path to the created study directory, or None on error
        """
        # Validate IDs to prevent path traversal
        if not is_safe_id(investigation_id) or not is_safe_id(study_id):
            logger.error("Invalid investigation or study ID")
            return None

        study_path = self.get_study_path(investigation_id, study_id)

        if not self.create_directory(study_path):
            return None

        # Create only the files directory structure (original + converted).
        # Legacy subdirectories (raw_data, processed_data, assays, versions)
        # are not created by default — they were unused and only added clutter.
        files_dir = study_path / "files"
        self.create_directory(files_dir)
        self.create_directory(files_dir / "original")
        self.create_directory(files_dir / "converted")

        return study_path

    def create_investigation_directory(self, investigation_id: str) -> Optional[Path]:
        """
        Create an investigation directory structure.

        Args:
            investigation_id: Investigation identifier

        Returns:
            Path to the created investigation directory, or None on error
        """
        # Validate ID to prevent path traversal
        if not is_safe_id(investigation_id):
            logger.error(f"Invalid investigation ID: {investigation_id}")
            return None

        inv_path = self.get_investigation_path(investigation_id)

        if not self.create_directory(inv_path):
            return None

        # Create subdirectories
        inv_subdirs = self._config.get("investigation_subdirs", {})
        for dir_name, subdirs in inv_subdirs.items():
            dir_path = inv_path / dir_name
            self.create_directory(dir_path)
            for subdir in subdirs:
                self.create_directory(dir_path / subdir)

        return inv_path

    # ----------------------------------------------------------------------
    # File Operation Methods
    # ----------------------------------------------------------------------
    def list_studies(self, investigation_id: str) -> List[str]:
        """
        List all studies in an investigation.

        Args:
            investigation_id: Investigation identifier

        Returns:
            List of study identifiers
        """
        studies_root = self.get_studies_root(investigation_id)
        if not studies_root.exists():
            return []

        return [d.name for d in studies_root.iterdir() if d.is_dir()]

    def list_investigations(self) -> List[str]:
        """
        List all investigations.

        Returns:
            List of investigation identifiers
        """
        inv_root = self.get_investigations_root()
        if not inv_root.exists():
            return []

        return [d.name for d in inv_root.iterdir() if d.is_dir()]

    def copy_file_to_study(
        self,
        source_path: Path,
        investigation_id: str,
        study_id: str,
        target_category: str,
        filename: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Copy a file to a study directory.

        Args:
            source_path: Path to the source file
            investigation_id: Investigation identifier
            study_id: Study identifier
            target_category: Target category (e.g., "raw_data/images")
            filename: Optional new filename

        Returns:
            Path to the copied file, or None on error
        """
        study_path = self.get_study_path(investigation_id, study_id)
        target_path = study_path / target_category

        if not self.create_directory(target_path):
            return None

        if filename:
            dest_path = target_path / filename
        else:
            dest_path = target_path / source_path.name

        try:
            shutil.copy2(source_path, dest_path)
            return dest_path
        except (IOError, OSError) as e:
            logger.error(
                f"File I/O error copying file from {source_path} to {dest_path}: {e}", exc_info=True
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error copying file from {source_path} to {dest_path}: {e}",
                exc_info=True,
            )
            return None

    def copy_sequence_file_to_study(
        self,
        source_path: Path,
        investigation_id: str,
        study_id: str,
        filename: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Copy a sequence file to the study's raw_data/sequences directory.

        Args:
            source_path: Path to source sequence file
            investigation_id: Investigation identifier
            study_id: Study identifier
            filename: Optional new filename (default: uses source filename)

        Returns:
            Path to copied file, or None on error
        """
        study_path = self.get_study_path(investigation_id, study_id)
        target_path = study_path / "raw_data" / "sequences"

        if not self.create_directory(target_path):
            return None

        if filename:
            dest_path = target_path / filename
        else:
            dest_path = target_path / source_path.name

        try:
            shutil.copy2(source_path, dest_path)
            logger.info(f"Copied sequence file from {source_path} to {dest_path}")
            return dest_path
        except (IOError, OSError) as e:
            logger.error(
                f"File I/O error copying sequence file from {source_path} to {dest_path}: {e}",
                exc_info=True,
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error copying sequence file from {source_path} to {dest_path}: {e}",
                exc_info=True,
            )
            return None

    def delete_study(self, investigation_id: str, study_id: str) -> bool:
        """
        Delete a study directory and all its contents.

        Args:
            investigation_id: Investigation identifier
            study_id: Study identifier

        Returns:
            True if successful, False otherwise
        """
        # Validate IDs to prevent path traversal
        if not is_safe_id(investigation_id) or not is_safe_id(study_id):
            logger.error("Invalid investigation or study ID")
            return False

        study_path = self.get_study_path(investigation_id, study_id)

        if not study_path.exists():
            logger.warning(f"Study path does not exist: {study_path}")
            return False

        try:
            shutil.rmtree(study_path)
            logger.info(f"Deleted study: {study_path}")
            return True
        except (IOError, OSError) as e:
            logger.error(f"File I/O error deleting study {study_path}: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting study {study_path}: {e}", exc_info=True)
            return False

    def delete_investigation(self, investigation_id: str) -> bool:
        """
        Delete an investigation directory and all its studies.

        Args:
            investigation_id: Investigation identifier

        Returns:
            True if successful, False otherwise
        """
        # Validate ID to prevent path traversal
        if not is_safe_id(investigation_id):
            logger.error(f"Invalid investigation ID: {investigation_id}")
            return False

        inv_path = self.get_investigation_path(investigation_id)

        if not inv_path.exists():
            logger.warning(f"Investigation path does not exist: {inv_path}")
            return False

        try:
            shutil.rmtree(inv_path)
            logger.info(f"Deleted investigation: {inv_path}")
            return True
        except (IOError, OSError) as e:
            logger.error(f"File I/O error deleting investigation {inv_path}: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting investigation {inv_path}: {e}", exc_info=True)
            return False

    # ----------------------------------------------------------------------
    # Utility Methods
    # ----------------------------------------------------------------------
    def get_file_pattern(self, pattern_name: str, **kwargs) -> str:
        """
        Get a formatted file pattern.

        Args:
            pattern_name: Name of the pattern (e.g., "study_json", "raw_image")
            **kwargs: Values to substitute in the pattern

        Returns:
            Formatted file pattern
        """
        patterns = self._config.get("file_patterns", {})
        pattern = patterns.get(pattern_name, "{name}")

        # Add current date/time if needed
        now = datetime.now()
        kwargs.setdefault("date", now.strftime("%Y-%m-%d"))
        kwargs.setdefault("time", now.strftime("%H-%M-%S"))

        return str(pattern.format(**kwargs))

    def ensure_structure_exists(self) -> bool:
        """
        Ensure the root directory structure exists.

        Returns:
            True if structure exists or was created, False otherwise
        """
        # Create main directories
        main_dirs = [
            self._config.get("investigations_root", "investigations"),
            self._config.get("templates_root", "templates"),
            self._config.get("ontologies_root", "ontologies"),
            self._config.get("exports_root", "exports"),
            self._config.get("archive_root", "archive"),
        ]

        success = True
        for dir_name in main_dirs:
            if not self.create_directory(self.base_path / dir_name):
                success = False

        return success


# ----------------------------------------------------------------------
# Convenience Functions
# ----------------------------------------------------------------------
def get_directory_manager(base_path: Optional[str] = None) -> DirectoryManager:
    """
    Get a DirectoryManager instance.

    Args:
        base_path: Optional base path

    Returns:
        DirectoryManager instance
    """
    return DirectoryManager(base_path)
