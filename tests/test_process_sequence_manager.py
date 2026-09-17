"""
Unit tests for ProcessSequenceManager.
"""

import pytest

from utils.process_sequence_manager import ProcessSequenceManager


@pytest.mark.unit
class TestProcessSequenceManager:
    """Tests for ProcessSequenceManager class."""

    def test_initialization(self, sample_study_data, material_manager):
        """Test that ProcessSequenceManager initializes correctly."""
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )

        assert manager.study_data == sample_study_data
        assert manager.material_manager == material_manager
        assert "processes" in manager.process_sequence

    def test_load_process_sequence(self, sample_study_data):
        """Test that process sequence is loaded correctly."""
        sample_study_data["process_sequence"] = {
            "processes": [{"id": "process_1", "name": "Test Process", "protocol_ref": "protocol_1"}]
        }

        manager = ProcessSequenceManager(study_data=sample_study_data)

        assert len(manager.process_sequence["processes"]) == 1
        assert manager.process_sequence["processes"][0]["name"] == "Test Process"

    def test_load_process_sequence_from_list(self, sample_study_data):
        """Test loading process sequence from list format."""
        sample_study_data["process_sequence"] = [{"id": "process_1", "name": "Test Process"}]

        manager = ProcessSequenceManager(study_data=sample_study_data)

        assert "processes" in manager.process_sequence
        assert len(manager.process_sequence["processes"]) == 1

    def test_add_process(self, sample_study_data, material_manager):
        """Test adding a process."""
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )

        process_data = {
            "id": "process_1",
            "name": "New Process",
            "protocol_ref": "protocol_1",
            "inputs": [],
            "outputs": [],
            "parameterValues": [],
        }

        result = manager.add_process(process_data)

        assert result is not None
        assert len(manager.process_sequence["processes"]) == 1

    def test_remove_process(self, sample_study_data, material_manager):
        """Test removing a process."""
        sample_study_data["process_sequence"] = {
            "processes": [{"id": "process_1", "name": "Process to Remove"}]
        }

        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )

        result = manager.remove_process("process_1")

        assert result is True
        assert len(manager.process_sequence["processes"]) == 0

    def test_remove_process_not_found(self, sample_study_data, material_manager):
        """Test removing non-existent process returns False."""
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )

        result = manager.remove_process("nonexistent")

        assert result is False

    def test_update_process(self, sample_study_data, material_manager):
        """Test updating a process."""
        sample_study_data["process_sequence"] = {
            "processes": [{"id": "process_1", "name": "Original Name"}]
        }

        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )

        updated_data = {"name": "Updated Name", "protocol_ref": "protocol_2"}

        result = manager.update_process("process_1", updated_data)

        assert result is True
        process = manager.get_process_by_id("process_1")
        assert process["name"] == "Updated Name"

    def test_get_process_by_id(self, sample_study_data, material_manager):
        """Test retrieving process by ID."""
        sample_study_data["process_sequence"] = {
            "processes": [{"id": "process_1", "name": "Test Process"}]
        }

        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )

        process = manager.get_process_by_id("process_1")

        assert process is not None
        assert process["name"] == "Test Process"

    def test_get_all_materials(self, sample_study_data, material_manager):
        """Test getting all materials."""
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )

        all_materials = manager.get_all_materials()

        assert len(all_materials) == 1  # One source from sample data
        assert all_materials[0]["name"] == "E. coli ClearColi"

    def test_get_material_by_id(self, sample_study_data, material_manager):
        """Test retrieving material by ID."""
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )

        material_id = "/investigations/inv_1/studies/study_1#source_bacteria"
        material = manager.get_material_by_id(material_id)

        assert material is not None
        assert material["name"] == "E. coli ClearColi"

    def test_reorder_processes(self, sample_study_data, material_manager):
        """Test reordering processes."""
        sample_study_data["process_sequence"] = {
            "processes": [
                {"id": "process_1", "name": "Process 1"},
                {"id": "process_2", "name": "Process 2"},
                {"id": "process_3", "name": "Process 3"},
            ]
        }

        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )

        # Move process_3 to index 0
        manager.reorder_process("process_3", 0)

        assert manager.process_sequence["processes"][0]["id"] == "process_3"
        assert manager.process_sequence["processes"][2]["id"] == "process_2"


@pytest.mark.unit
class TestProcessValidation:
    """Tests for process validation."""

    def test_validate_process_valid(self, sample_study_data, material_manager):
        """Test that valid process passes validation."""
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )

        process_data = {
            "id": "process_1",
            "name": "Valid Process",
            "protocol_ref": "protocol_1",
            "inputs": [],
            "outputs": [],
            "parameterValues": [],
        }

        is_valid, errors = manager.validate_process(process_data)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_process_missing_name(self, sample_study_data, material_manager):
        """Test that process without name fails validation."""
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )

        process_data = {"id": "process_1", "protocol_ref": "protocol_1"}

        is_valid, errors = manager.validate_process(process_data)

        assert is_valid is False
        assert any("name" in str(error).lower() for error in errors)

    def test_validate_process_missing_protocol(self, sample_study_data, material_manager):
        """Test that process without protocol fails validation."""
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )

        process_data = {"id": "process_1", "name": "Test Process"}

        is_valid, errors = manager.validate_process(process_data)

        assert is_valid is False
        assert any("protocol" in str(error).lower() for error in errors)


@pytest.mark.unit
class TestProcessSequenceManagerPureLogic:
    """Tests for pure-logic helper methods of ProcessSequenceManager."""

    # ------------------------------------------------------------------
    # _normalize_material_reference
    # ------------------------------------------------------------------

    def test_normalize_material_reference_dict(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        ref = manager._normalize_material_reference(
            {
                "material_id": "/inv#sample_1",
                "name": "Sample One",
                "materialType": "sample",
            }
        )
        assert ref == {
            "material_id": "/inv#sample_1",
            "name": "Sample One",
            "materialType": "sample",
        }

    def test_normalize_material_reference_dict_at_id_fallback(
        self, sample_study_data, material_manager
    ):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        ref = manager._normalize_material_reference(
            {
                "@id": "/inv#other_1",
                "name": "Other One",
            }
        )
        assert ref["material_id"] == "/inv#other_1"
        assert ref["name"] == "Other One"
        # materialType defaults to "sample" when absent
        assert ref["materialType"] == "sample"

    def test_normalize_material_reference_string_found(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        source_id = "/investigations/inv_1/studies/study_1#source_bacteria"
        ref = manager._normalize_material_reference(source_id)
        assert ref["material_id"] == source_id
        assert ref["name"] == "E. coli ClearColi"
        assert ref["materialType"] == "source"

    def test_normalize_material_reference_string_not_found(
        self, sample_study_data, material_manager
    ):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        ref = manager._normalize_material_reference("#unknown_material")
        assert ref["material_id"] == "unknown_material"
        assert ref["name"] == "Unknown Material"
        assert ref["materialType"] == "sample"

    def test_normalize_material_reference_invalid_type(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        ref = manager._normalize_material_reference(42)
        assert ref == {"material_id": "", "name": "", "materialType": "sample"}

    # ------------------------------------------------------------------
    # _export_parameter_value
    # ------------------------------------------------------------------

    def test_export_parameter_value_int(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        result = manager._export_parameter_value({"name": "temperature", "value": "37"}, "#proc_1")
        assert result["@id"] == "#proc_1#pp_temperature"
        assert result["category"] == {"@id": "#parameter/temperature"}
        assert result["value"] == 37

    def test_export_parameter_value_float(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        result = manager._export_parameter_value(
            {"name": "concentration", "value": "3.5"}, "#proc_1"
        )
        assert result["value"] == 3.5

    def test_export_parameter_value_non_numeric(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        result = manager._export_parameter_value({"name": "buffer", "value": "PBS"}, "#proc_1")
        assert result["value"] == "PBS"

    def test_export_parameter_value_with_unit(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        param = {
            "name": "temperature",
            "value": "37",
            "unit": {
                "annotationValue": "degree celsius",
                "termSource": "UO",
                "termAccession": "http://purl.obolibrary.org/obo/UO_0000027",
            },
        }
        result = manager._export_parameter_value(param, "#proc_1")
        assert result["value"] == {
            "value": 37,
            "unit": {
                "annotationValue": "degree celsius",
                "termSource": "UO",
                "termAccession": "http://purl.obolibrary.org/obo/UO_0000027",
            },
        }

    def test_export_parameter_value_annotation(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        param = {
            "name": "organism",
            "annotationValue": "E. coli",
            "termSource": "NCBITaxon",
            "termAccession": "http://purl.obolibrary.org/obo/NCBITaxon_562",
        }
        result = manager._export_parameter_value(param, "#proc_1")
        assert result["value"] == {
            "annotationValue": "E. coli",
            "termSource": "NCBITaxon",
            "termAccession": "http://purl.obolibrary.org/obo/NCBITaxon_562",
        }

    def test_export_parameter_value_empty_param(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        result = manager._export_parameter_value({}, "#proc_1")
        assert result["@id"] == "#proc_1#pp_"
        assert result["category"] == {"@id": "#parameter/"}
        assert "value" not in result

    # ------------------------------------------------------------------
    # _get_protocol_url / _get_protocol_object
    # ------------------------------------------------------------------

    def test_get_protocol_url_full_url_passthrough(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        url = "https://example.org/investigations/inv_1#prot_test"
        assert manager._get_protocol_url(url, "inv_1") == url

    def test_get_protocol_url_from_name(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        url = manager._get_protocol_url("My Protocol", "inv_2")
        assert url == "https://example.org/investigations/inv_2#prot_my_protocol"

    def test_get_protocol_object_from_name(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        result = manager._get_protocol_object("My Protocol", "inv_1")
        assert result == {
            "@id": "https://example.org/investigations/inv_1#prot_my_protocol",
            "name": "My Protocol",
        }

    def test_get_protocol_object_from_url(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        url = "https://example.org/investigations/inv_1#prot_sds_page"
        result = manager._get_protocol_object(url, "inv_1")
        assert result["@id"] == url
        assert result["name"] == "sds page"

    # ------------------------------------------------------------------
    # validate_material_handover
    # ------------------------------------------------------------------

    def test_validate_material_handover_no_processes(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        assert manager.validate_material_handover() == []

    def test_validate_material_handover_matched_flow(self, sample_study_data, material_manager):
        sample_study_data["process_sequence"] = {
            "processes": [
                {
                    "name": "Process A",
                    "outputs": [{"name": "Product", "material_id": "/inv#product"}],
                    "inputs": [],
                },
                {
                    "name": "Process B",
                    "outputs": [],
                    "inputs": [{"name": "Product", "material_id": "/inv#product"}],
                },
            ]
        }
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        # The only input references a material not present -> error, but no
        # "output not used by next process" warning should appear.
        warnings = manager.validate_material_handover()
        assert not any("not used by next process" in w["message"] for w in warnings)

    def test_validate_material_handover_unmatched_output(self, sample_study_data, material_manager):
        sample_study_data["process_sequence"] = {
            "processes": [
                {
                    "name": "Process A",
                    "outputs": [{"name": "Product", "material_id": "/inv#product"}],
                    "inputs": [],
                },
                {
                    "name": "Process B",
                    "outputs": [],
                    "inputs": [],
                },
            ]
        }
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        warnings = manager.validate_material_handover()
        assert any(
            w["type"] == "warning" and "not used by next process" in w["message"] for w in warnings
        )

    def test_validate_material_handover_missing_input(self, sample_study_data, material_manager):
        sample_study_data["process_sequence"] = {
            "processes": [
                {
                    "name": "Process A",
                    "outputs": [],
                    "inputs": [{"material_id": "/inv#does_not_exist"}],
                }
            ]
        }
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        warnings = manager.validate_material_handover()
        assert any(w["type"] == "error" and "not found" in w["message"] for w in warnings)

    def test_validate_material_handover_string_input(self, sample_study_data, material_manager):
        sample_study_data["process_sequence"] = {
            "processes": [
                {
                    "name": "Process A",
                    "outputs": [],
                    "inputs": ["/inv#does_not_exist"],
                }
            ]
        }
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        warnings = manager.validate_material_handover()
        assert any(w["type"] == "error" for w in warnings)

    # ------------------------------------------------------------------
    # export_to_isa_json
    # ------------------------------------------------------------------

    def test_export_to_isa_json_empty(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        assert manager.export_to_isa_json() == []

    def test_export_to_isa_json_full_process(self, sample_study_data, material_manager):
        sample_study_data["process_sequence"] = {
            "processes": [
                {
                    "name": "Transformation",
                    "protocol_ref": "my protocol",
                    "date": "2024-01-01",
                    "inputs": [{"material_id": "/inv#in_1"}],
                    "outputs": [{"material_id": "/inv#out_1"}],
                    "parameters": [{"name": "temperature", "value": "37"}],
                }
            ]
        }
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        result = manager.export_to_isa_json(investigation_id="inv_9")
        assert len(result) == 1
        proc = result[0]
        assert proc["name"] == "Transformation"
        assert proc["date"] == "2024-01-01"
        assert proc["@id"] == "https://example.org/investigations/inv_9#Transformation"
        assert proc["executesProtocol"]["name"] == "my protocol"
        assert proc["inputs"] == ["/inv#in_1"]
        assert proc["outputs"] == ["/inv#out_1"]
        assert proc["parameterValues"][0]["value"] == 37

    def test_export_to_isa_json_string_inputs(self, sample_study_data, material_manager):
        sample_study_data["process_sequence"] = {
            "processes": [
                {
                    "name": "P",
                    "protocol_ref": "p",
                    "inputs": ["/inv#str_in"],
                    "outputs": ["/inv#str_out"],
                }
            ]
        }
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        result = manager.export_to_isa_json()
        assert result[0]["inputs"] == ["/inv#str_in"]
        assert result[0]["outputs"] == ["/inv#str_out"]

    def test_export_to_isa_json_explicit_at_id(self, sample_study_data, material_manager):
        sample_study_data["process_sequence"] = {
            "processes": [{"name": "P", "protocol_ref": "p", "@id": "custom_id"}]
        }
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        result = manager.export_to_isa_json()
        assert result[0]["@id"] == "custom_id"

    # ------------------------------------------------------------------
    # _restore_process_counters / _get_next_process_counter
    # ------------------------------------------------------------------

    def test_restore_process_counters_empty(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        manager._restore_process_counters()
        assert manager.process_counters == {}

    def test_restore_process_counters_parses_counter(self, sample_study_data, material_manager):
        sample_study_data["process_sequence"] = {
            "processes": [
                {"name": "Transformation #2"},
                {"name": "Transformation #5"},
            ]
        }
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        # Max counter wins
        assert manager.process_counters.get("Transformation") == 5

    def test_restore_process_counters_old_format(self, sample_study_data, material_manager):
        sample_study_data["process_sequence"] = {
            "processes": [
                {"name": "Transformation"},
            ]
        }
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        assert manager.process_counters.get("Transformation") == 0

    def test_restore_process_counters_invalid_number(self, sample_study_data, material_manager):
        sample_study_data["process_sequence"] = {
            "processes": [
                {"name": "Transformation #abc"},
            ]
        }
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        assert manager.process_counters.get("Transformation") == 0

    def test_get_next_process_counter_increments(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        assert manager._get_next_process_counter("X") == 1
        assert manager._get_next_process_counter("X") == 2
        assert manager._get_next_process_counter("X") == 3

    def test_get_next_process_counter_independent_names(self, sample_study_data, material_manager):
        manager = ProcessSequenceManager(
            study_data=sample_study_data, material_manager=material_manager
        )
        assert manager._get_next_process_counter("A") == 1
        assert manager._get_next_process_counter("B") == 1
        assert manager._get_next_process_counter("A") == 2
