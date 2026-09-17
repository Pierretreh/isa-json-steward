"""
Unit tests for MaterialManager.
"""

import pytest

from utils.material_manager import MaterialManager


@pytest.mark.unit
class TestMaterialManager:
    """Tests for MaterialManager class."""

    def test_initialization(self, sample_study_data, directory_manager):
        """Test that MaterialManager initializes correctly."""
        manager = MaterialManager(
            study_data=sample_study_data,
            directory_manager=directory_manager,
            investigation_id="inv_1",
            study_id="study_1",
        )

        assert manager.study_data == sample_study_data
        assert manager.investigation_id == "inv_1"
        assert manager.study_id == "study_1"
        assert "sources" in manager.materials
        assert "samples" in manager.materials
        assert "otherMaterials" in manager.materials

    def test_load_materials(self, sample_study_data):
        """Test that materials are loaded correctly from study data."""
        manager = MaterialManager(study_data=sample_study_data)

        assert len(manager.materials["sources"]) == 1
        assert manager.materials["sources"][0]["name"] == "E. coli ClearColi"
        assert len(manager.materials["samples"]) == 0
        assert len(manager.materials["otherMaterials"]) == 0

    def test_generate_material_id(self, material_manager):
        """Test material ID generation."""
        material_id = material_manager.generate_material_id("source", "Test Material")

        assert material_id == "#source_Test_Material"
        assert "source" in material_id
        assert "Test_Material" in material_id

    def test_add_material_source(self, material_manager):
        """Test adding a source material."""
        material_data = {"name": "New Source", "characteristics": []}

        material_manager.add_material("source", material_data)

        assert len(material_manager.materials["sources"]) == 2
        assert material_manager.materials["sources"][1]["name"] == "New Source"

    def test_add_material_sample(self, material_manager):
        """Test adding a sample material."""
        material_data = {"name": "New Sample", "characteristics": []}

        material_manager.add_material("sample", material_data)

        assert len(material_manager.materials["samples"]) == 1
        assert material_manager.materials["samples"][0]["name"] == "New Sample"

    def test_add_material_invalid_type(self, material_manager):
        """Test that adding material with invalid type raises error."""
        material_data = {"name": "Invalid Material", "characteristics": []}

        with pytest.raises(ValueError):
            material_manager.add_material("invalid_type", material_data)

    def test_get_material_by_id(self, material_manager):
        """Test retrieving material by ID."""
        material_id = "/investigations/inv_1/studies/study_1#source_bacteria"
        material = material_manager.get_material_by_id(material_id)

        assert material is not None
        assert material["name"] == "E. coli ClearColi"

    def test_get_material_by_id_not_found(self, material_manager):
        """Test retrieving non-existent material returns None."""
        material = material_manager.get_material_by_id(
            "/investigations/inv_1/studies/study_1#nonexistent"
        )

        assert material is None

    def test_delete_material(self, material_manager):
        """Test deleting a material."""
        # First add a material
        material_data = {"name": "To Delete", "characteristics": []}
        material_manager.add_material("sample", material_data)

        # Get the ID of the added material
        added_id = material_manager.materials["samples"][0]["@id"]

        # Delete it
        result = material_manager.delete_material(added_id)

        assert result is True
        assert len(material_manager.materials["samples"]) == 0

    def test_delete_material_not_found(self, material_manager):
        """Test deleting non-existent material returns False."""
        result = material_manager.delete_material(
            "/investigations/inv_1/studies/study_1#nonexistent"
        )

        assert result is False

    def test_update_material(self, material_manager):
        """Test updating a material."""
        material_id = "/investigations/inv_1/studies/study_1#source_bacteria"
        updated_data = {"name": "Updated Bacteria", "characteristics": []}

        result = material_manager.update_material(material_id, updated_data)

        assert result is True
        material = material_manager.get_material_by_id(material_id)
        assert material["name"] == "Updated Bacteria"

    def test_update_material_not_found(self, material_manager):
        """Test updating non-existent material returns False."""
        updated_data = {"name": "Non-existent", "characteristics": []}

        result = material_manager.update_material(
            "/investigations/inv_1/studies/study_1#nonexistent", updated_data
        )

        assert result is False


@pytest.mark.unit
class TestMaterialManagerTemplates:
    """Tests for MaterialManager template loading."""

    def test_load_templates(self, material_manager):
        """Test that templates are loaded correctly."""
        templates = material_manager.templates

        assert "sources" in templates
        assert "samples" in templates
        assert "otherMaterials" in templates

    def test_get_template_by_type(self, material_manager):
        """Test getting templates by type."""
        source_templates = material_manager.get_templates("source")

        assert isinstance(source_templates, list)

    def test_get_template_invalid_type(self, material_manager):
        """Test getting templates with invalid type."""
        templates = material_manager.get_templates("invalid_type")

        assert templates == []
