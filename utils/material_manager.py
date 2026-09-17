"""
Material Manager for handling material data and operations.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Import configuration
try:
    from .config_loader import get_base_url, get_url_template
except ImportError:
    # Fallback to hardcoded URL if config loader not available
    def get_base_url() -> str:
        return "https://example.org/investigations"

    def get_url_template(template_name: str, config_path: Optional[Path] = None) -> str:
        return ""


class MaterialManager:
    """Manager for material data and operations."""

    def __init__(
        self,
        study_data: Dict[str, Any],
        directory_manager=None,
        investigation_id: Optional[str] = None,
        study_id: Optional[str] = None,
    ):
        """
        Initialize material manager.

        Args:
            study_data: The study data dictionary containing materials
            directory_manager: Optional DirectoryManager for file operations
            investigation_id: Optional investigation ID for generating material IDs
            study_id: Optional study ID for generating material IDs
        """
        self.study_data = study_data or {}
        self.dm = directory_manager
        self.investigation_id = investigation_id or "inv_1"
        self.study_id = study_id or "study_1"
        self.base_url = get_base_url()
        self.materials = self._load_materials()
        self.templates = self._load_templates()

    def _load_materials(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Load materials from study data.

        Returns:
            Dictionary with sources, samples, and otherMaterials lists
        """
        # Check if materials are in studies[0] (ISA-JSON format)
        if (
            "studies" in self.study_data
            and isinstance(self.study_data["studies"], list)
            and len(self.study_data["studies"]) > 0
        ):
            studies_0 = self.study_data["studies"][0]
            if "materials" in studies_0:
                materials = studies_0["materials"]
            else:
                materials = self.study_data.get("materials", {})
        else:
            materials = self.study_data.get("materials", {})

        result = {
            "sources": materials.get("sources", []),
            "samples": materials.get("samples", []),
            "otherMaterials": materials.get("otherMaterials", []),
        }

        return result

    def _load_templates(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Load material templates from template files.

        Returns:
            Dictionary with sources, samples, and otherMaterials template lists
        """
        templates: Dict[str, List[Dict[str, Any]]] = {
            "sources": [],
            "samples": [],
            "otherMaterials": [],
        }
        # Load from templates/material_templates/ directory
        template_files = {
            "sources": "source_templates.json",
            "samples": "sample_templates.json",
            "otherMaterials": "other_material_templates.json",
        }
        for material_type, filename in template_files.items():
            template_path = Path("templates/material_templates") / filename
            if template_path.exists():
                try:
                    with open(template_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        # Handle both direct array and wrapped with 'templates' key
                        if isinstance(data, dict) and "templates" in data:
                            templates[material_type] = data["templates"]
                        elif isinstance(data, list):
                            templates[material_type] = data
                        else:
                            logger.warning(f"Invalid template format in {filename}")
                            templates[material_type] = []
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Failed to load template file {filename}: {e}")
        return templates

    def refresh_from_study_data(self) -> None:
        """
        Refresh materials from the current study_data.

        This method reloads materials from self.study_data, which is useful
        when the investigation or study has changed and the materials need
        to be refreshed with the latest data.
        """
        self.materials = self._load_materials()
        logger.info("Refreshed materials from study data")

    def get_templates(self, material_type: str) -> List[Dict[str, Any]]:
        """
        Get templates for a specific material type.

        Args:
            material_type: Type of material (source, sample, otherMaterial)

        Returns:
            List of template dictionaries for the specified type, or empty list if invalid type
        """
        # Map common type names to template keys
        type_mapping = {
            "source": "sources",
            "sample": "samples",
            "otherMaterial": "otherMaterials",
            "other_material": "otherMaterials",
            "other": "otherMaterials",
        }

        # Get the template key
        template_key = type_mapping.get(material_type)

        if template_key is None:
            return []

        return self.templates.get(template_key, [])

    def generate_material_id(self, material_type: str, name: str) -> str:
        """
        Generate a unique material ID in ISA-JSON format.

        Args:
            material_type: Type of material (source, sample, otherMaterial)
            name: Name of the material

        Returns:
            Material ID string in format: /investigations/{inv_id}/studies/{study_id}#{type}_{sanitized_name}  # noqa: E501
        """
        # Sanitize name for URL safety
        sanitized_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        sanitized_name = sanitized_name.strip("_")

        # Generate unique ID using relative fragment format per ISA-JSON spec
        material_id = f"#{material_type}_{sanitized_name}"

        # Check if ID already exists and append counter if needed
        counter = 1
        base_id = material_id
        while self.get_material_by_id(material_id) is not None:
            material_id = f"{base_id}_{counter}"
            counter += 1

        return material_id

    def add_material(self, material_type: str, material_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a material to the study.

        Args:
            material_type: Type of material (source, sample, otherMaterial)
            material_data: Material data dictionary

        Returns:
            True if successful, False otherwise

        Raises:
            ValueError: If material_type is invalid
        """
        # Validate material type
        valid_types = ["source", "sample", "otherMaterial"]
        if material_type not in valid_types:
            raise ValueError(
                f"Invalid material type: {material_type}. Must be one of {valid_types}"
            )

        # Get the list key (plural form)
        list_key = f"{material_type}s" if material_type != "otherMaterial" else "otherMaterials"

        # Generate material ID if not provided or if it's empty
        if "@id" not in material_data or not material_data.get("@id"):
            name = material_data.get("name", "unnamed")
            material_data["@id"] = self.generate_material_id(material_type, name)

        # Add timestamp
        material_data["created_at"] = datetime.now().isoformat()

        # Add to materials list
        self.materials[list_key].append(material_data)

        # Update study_data
        if "materials" not in self.study_data:
            self.study_data["materials"] = {}
        self.study_data["materials"][list_key] = self.materials[list_key]

        logger.info(f"Added material {material_data['@id']} of type {material_type}")

        return material_data

    def get_material_by_id(self, material_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a material by its ID.

        Args:
            material_id: The material ID to search for

        Returns:
            The material dictionary if found, None otherwise
        """
        for material in self.get_all_materials():
            if material.get("@id", "") == material_id:
                return material
        return None

    def get_all_materials(self) -> List[Dict[str, Any]]:
        """
        Get all materials (sources, samples, otherMaterials).

        Each material dict is annotated with ``materialType`` so callers
        can distinguish source / sample / otherMaterial without knowing
        which list it came from.

        Returns:
            List of all material dictionaries
        """
        all_materials: List[Dict[str, Any]] = []
        for mat_type, key in [
            ("source", "sources"),
            ("sample", "samples"),
            ("otherMaterial", "otherMaterials"),
        ]:
            for m in self.materials.get(key, []):
                if "materialType" not in m:
                    m["materialType"] = mat_type
                all_materials.append(m)
        return all_materials

    def delete_material(self, material_id: str) -> bool:
        """
        Delete a material by its ID.

        Args:
            material_id: The material ID to delete

        Returns:
            True if material was deleted, False if not found
        """
        for list_key in ["sources", "samples", "otherMaterials"]:
            for i, material in enumerate(self.materials[list_key]):
                if material.get("@id", "") == material_id:
                    # Remove from materials list
                    _deleted = self.materials[list_key].pop(i)  # noqa: F841
                    # Update study_data
                    if "materials" in self.study_data:
                        self.study_data["materials"][list_key] = self.materials[list_key]
                    logger.info(f"Deleted material {material_id}")
                    return True
        return False

    def update_material(self, material_id: str, material_data: Dict[str, Any]) -> bool:
        """
        Update a material by its ID.

        Args:
            material_id: The material ID to update
            material_data: Updated material data

        Returns:
            True if material was updated, False if not found
        """
        material = self.get_material_by_id(material_id)
        if material is None:
            return False

        # Update material data
        material.update(material_data)
        material["updated_at"] = datetime.now().isoformat()

        # Update study_data
        for list_key in ["sources", "samples", "otherMaterials"]:
            for i, mat in enumerate(self.materials[list_key]):
                if mat.get("@id", "") == material_id:
                    self.materials[list_key][i] = material
                    if "materials" in self.study_data:
                        self.study_data["materials"][list_key] = self.materials[list_key]
                    break

        logger.info(f"Updated material {material_id}")
        return True

    def get_template_by_type(self, material_type: str) -> List[Dict[str, Any]]:
        """
        Get templates for a specific material type.

        Args:
            material_type: Type of material (source, sample, otherMaterial)

        Returns:
            List of template dictionaries for the specified type

        Raises:
            ValueError: If material_type is invalid
        """
        valid_types = ["source", "sample", "otherMaterial"]
        if material_type not in valid_types:
            raise ValueError(
                f"Invalid material type: {material_type}. Must be one of {valid_types}"
            )

        list_key = f"{material_type}s" if material_type != "otherMaterial" else "otherMaterials"
        return self.templates.get(list_key, [])
