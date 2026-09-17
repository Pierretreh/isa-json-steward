"""
Unit tests for utils.material_handover_validator.

These tests cover the pure logic of MaterialHandoverValidator:
material existence checks, handover matching between processes,
type compatibility rules, summary generation, and suggestion stubs.
"""

from typing import Any, Dict, List, Optional, Tuple

import pytest

from utils.material_handover_validator import MaterialHandoverValidator

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _material(material_id: str, name: str, material_type: Optional[str] = None) -> Dict[str, Any]:
    """Build a material record keyed by @id."""
    material: Dict[str, Any] = {"@id": material_id, "name": name}
    if material_type is not None:
        material["materialType"] = material_type
    return material


def _io(material_id: str, name: str, material_type: Optional[str] = None) -> Dict[str, Any]:
    """Build a process input/output record (new dict format)."""
    io_item: Dict[str, Any] = {"material_id": material_id, "name": name}
    if material_type is not None:
        io_item["materialType"] = material_type
    return io_item


def _process(
    process_id: str,
    name: str,
    inputs: Optional[List[Any]] = None,
    outputs: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Build a process record with inputs and outputs."""
    return {
        "id": process_id,
        "name": name,
        "inputs": inputs or [],
        "outputs": outputs or [],
    }


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def validator() -> MaterialHandoverValidator:
    """Empty validator instance."""
    return MaterialHandoverValidator(materials=[], processes=[])


@pytest.fixture
def valid_flow() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """A valid three-step material flow.

    Transformation -> Lysis -> Assay. Every referenced input material
    exists; the final output ("Assay Results") is intentionally absent
    from the material list to exercise the "new sample" warning path.
    """
    materials = [
        _material("/inv_1/study_1#source_bacteria", "E. coli ClearColi", "source"),
        _material("/inv_1/study_1#buffer", "LB Medium", "buffer"),
        _material("/inv_1/study_1#sample_pellet", "Cell Pellet", "cell pellet"),
        _material("/inv_1/study_1#sample_lysate", "Cell Lysate", "lysate"),
    ]
    processes = [
        _process(
            "p1",
            "Transformation",
            inputs=[_io("/inv_1/study_1#source_bacteria", "E. coli ClearColi", "source")],
            outputs=[_io("/inv_1/study_1#sample_pellet", "Cell Pellet", "cell pellet")],
        ),
        _process(
            "p2",
            "Lysis",
            inputs=[
                _io("/inv_1/study_1#sample_pellet", "Cell Pellet", "cell pellet"),
                _io("/inv_1/study_1#buffer", "LB Medium", "buffer"),
            ],
            outputs=[_io("/inv_1/study_1#sample_lysate", "Cell Lysate", "lysate")],
        ),
        _process(
            "p3",
            "Assay",
            inputs=[_io("/inv_1/study_1#sample_lysate", "Cell Lysate", "lysate")],
            outputs=[_io("/inv_1/study_1#sample_results", "Assay Results", "sample")],
        ),
    ]
    return materials, processes


# ----------------------------------------------------------------------
# Initialization
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestMaterialHandoverValidatorInit:
    """Tests for MaterialHandoverValidator initialization."""

    def test_initialization_stores_materials_by_id(self):
        """Materials are indexed by their @id for fast lookup."""
        materials = [_material("mat_1", "Material One"), _material("mat_2", "Material Two")]
        validator = MaterialHandoverValidator(materials=materials, processes=[])

        assert set(validator.materials.keys()) == {"mat_1", "mat_2"}
        assert validator.materials["mat_1"]["name"] == "Material One"

    def test_initialization_stores_processes(self):
        """Processes are stored in the given order."""
        processes = [_process("p1", "First"), _process("p2", "Second")]
        validator = MaterialHandoverValidator(materials=[], processes=processes)

        assert validator.processes == processes

    def test_initialization_starts_with_no_warnings_or_errors(self):
        """A fresh validator has empty warning and error lists."""
        validator = MaterialHandoverValidator(materials=[], processes=[])

        assert validator.warnings == []
        assert validator.errors == []

    def test_initialization_handles_material_without_id(self):
        """Materials without an @id are stored under an empty key."""
        validator = MaterialHandoverValidator(materials=[{"name": "No ID"}], processes=[])

        assert "" in validator.materials
        assert validator.materials[""]["name"] == "No ID"


# ----------------------------------------------------------------------
# validate()
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestValidate:
    """Tests for MaterialHandoverValidator.validate()."""

    def test_valid_flow_has_no_errors(self, valid_flow):
        """A valid material flow produces no errors."""
        materials, processes = valid_flow
        result = MaterialHandoverValidator(materials=materials, processes=processes).validate()

        assert result["valid"] is True
        assert result["errors"] == []

    def test_valid_flow_flags_new_output_as_warning(self, valid_flow):
        """An output missing from the material list warns that it will be created."""
        materials, processes = valid_flow
        result = MaterialHandoverValidator(materials=materials, processes=processes).validate()

        assert len(result["warnings"]) == 1
        warning = result["warnings"][0]
        assert warning["severity"] == "info"
        assert warning["output_id"] == "/inv_1/study_1#sample_results"
        assert "will be created as new sample" in warning["message"]

    def test_recycled_material_flow_is_fully_clean(self):
        """A flow where the output is also a known input has no errors or warnings."""
        materials = [_material("sample_x", "Recycled Sample", "sample")]
        processes = [
            _process(
                "p1",
                "Recycle",
                inputs=[_io("sample_x", "Recycled Sample", "sample")],
                outputs=[_io("sample_x", "Recycled Sample", "sample")],
            )
        ]
        result = MaterialHandoverValidator(materials=materials, processes=processes).validate()

        assert result["valid"] is True
        assert result["errors"] == []
        assert result["warnings"] == []
        assert result["summary"] == "Material handover is valid."

    def test_empty_process_list_is_valid(self, validator):
        """No processes means nothing to validate."""
        result = validator.validate()

        assert result["valid"] is True
        assert result["errors"] == []
        assert result["warnings"] == []
        assert result["summary"] == "Material handover is valid."

    def test_missing_input_material_reports_critical_error(self):
        """An input material missing from the list is a critical error (string format)."""
        processes = [_process("p1", "Process", inputs=["missing_material"], outputs=[])]
        result = MaterialHandoverValidator(materials=[], processes=processes).validate()

        assert result["valid"] is False
        assert len(result["errors"]) == 1
        error = result["errors"][0]
        assert error["type"] == "error"
        assert error["severity"] == "critical"
        assert error["process"] == "Process"
        assert error["process_id"] == "p1"
        assert error["input_id"] == "missing_material"
        assert "missing_material" in error["message"]
        assert "not found in materials" in error["message"]

    def test_missing_dict_input_material_reports_critical_error(self):
        """A dict-format input material missing from the list is a critical error."""
        processes = [
            _process(
                "p1",
                "Process",
                inputs=[_io("ghost_material", "Ghost Material", "sample")],
                outputs=[],
            )
        ]
        result = MaterialHandoverValidator(materials=[], processes=processes).validate()

        assert result["valid"] is False
        error = result["errors"][0]
        assert error["severity"] == "critical"
        assert error["input_id"] == "ghost_material"
        assert "Ghost Material" in error["message"]

    def test_missing_output_material_reports_new_sample_warning(self):
        """A string-format output not in the material list produces an info warning."""
        processes = [_process("p1", "Process", inputs=[], outputs=["new_sample_id"])]
        result = MaterialHandoverValidator(materials=[], processes=processes).validate()

        assert result["valid"] is True
        assert len(result["warnings"]) == 1
        warning = result["warnings"][0]
        assert warning["type"] == "warning"
        assert warning["severity"] == "info"
        assert warning["output_id"] == "new_sample_id"
        assert "will be created as new sample" in warning["message"]

    def test_missing_dict_output_material_reports_new_sample_warning(self):
        """A dict-format output not in the material list produces an info warning."""
        processes = [
            _process(
                "p1",
                "Process",
                inputs=[],
                outputs=[_io("created_sample", "Created Sample", "sample")],
            )
        ]
        result = MaterialHandoverValidator(materials=[], processes=processes).validate()

        assert result["valid"] is True
        warning = result["warnings"][0]
        assert warning["output_id"] == "created_sample"
        assert "Created Sample" in warning["message"]

    def test_output_not_used_by_next_process_warns(self):
        """An output that the following process does not consume is flagged."""
        materials = [
            _material("source_a", "Source A", "source"),
            _material("buffer_b", "Buffer B", "buffer"),
        ]
        processes = [
            _process(
                "p1",
                "Extract",
                inputs=[_io("source_a", "Source A", "source")],
                outputs=[_io("sample_x", "Sample X", "sample")],
            ),
            _process(
                "p2",
                "Load",
                inputs=[_io("buffer_b", "Buffer B", "buffer")],
                outputs=[],
            ),
        ]
        result = MaterialHandoverValidator(materials=materials, processes=processes).validate()

        unused_warnings = [
            w for w in result["warnings"] if "not used by next process" in w["message"]
        ]
        assert len(unused_warnings) == 1
        assert unused_warnings[0]["severity"] == "warning"
        assert unused_warnings[0]["process"] == "Extract"
        assert unused_warnings[0]["output_id"] == "sample_x"
        assert "Load" in unused_warnings[0]["message"]

    def test_handover_matched_by_name_does_not_warn(self):
        """Outputs and inputs matched by name (different IDs) are considered handed over."""
        materials = [_material("in_id", "Product", "sample")]
        processes = [
            _process(
                "p1",
                "Produce",
                inputs=[],
                outputs=[_io("out_id", "Product", "sample")],
            ),
            _process(
                "p2",
                "Consume",
                inputs=[_io("in_id", "Product", "sample")],
                outputs=[],
            ),
        ]
        result = MaterialHandoverValidator(materials=materials, processes=processes).validate()

        assert result["errors"] == []
        assert not any("not used by next process" in w["message"] for w in result["warnings"])

    def test_incompatible_types_report_error(self):
        """A handover between incompatible material types is an error."""
        materials = [_material("sample_x", "Sample X", "sample")]
        processes = [
            _process(
                "p1",
                "Produce",
                inputs=[],
                outputs=[_io("sample_x", "Sample X", "source")],
            ),
            _process(
                "p2",
                "Consume",
                inputs=[_io("sample_x", "Sample X", "cell culture")],
                outputs=[],
            ),
        ]
        result = MaterialHandoverValidator(materials=materials, processes=processes).validate()

        assert result["valid"] is False
        assert len(result["errors"]) == 1
        error = result["errors"][0]
        assert error["severity"] == "error"
        assert error["process"] == "Produce"
        assert error["output_type"] == "source"
        assert error["input_type"] == "cell culture"
        assert "incompatible" in error["message"]

    def test_compatible_types_do_not_report_error(self):
        """A handover between compatible material types is clean."""
        materials = [_material("pellet", "Pellet", "cell pellet")]
        processes = [
            _process(
                "p1",
                "Harvest",
                inputs=[],
                outputs=[_io("pellet", "Pellet", "cell pellet")],
            ),
            _process(
                "p2",
                "Lysis",
                inputs=[_io("pellet", "Pellet", "cell pellet")],
                outputs=[],
            ),
        ]
        result = MaterialHandoverValidator(materials=materials, processes=processes).validate()

        assert result["errors"] == []
        assert not any("incompatible" in w.get("message", "") for w in result["warnings"])

    def test_output_type_without_rule_is_permissive(self):
        """Output types with no compatibility rule never raise a type error."""
        materials = [_material("custom", "Custom Material", "customType")]
        processes = [
            _process(
                "p1",
                "Produce",
                inputs=[],
                outputs=[_io("custom", "Custom Material", "customType")],
            ),
            _process(
                "p2",
                "Consume",
                inputs=[_io("custom", "Custom Material", "sample")],
                outputs=[],
            ),
        ]
        result = MaterialHandoverValidator(materials=materials, processes=processes).validate()

        assert result["errors"] == []

    def test_orphaned_output_material_warns(self):
        """A material that is only ever an output is flagged as orphaned."""
        materials = [
            _material("sample_a", "Sample A", "sample"),
            _material("buffer_b", "Buffer B", "buffer"),
        ]
        processes = [
            _process(
                "p1",
                "Produce",
                inputs=[],
                outputs=[_io("sample_a", "Sample A", "sample")],
            ),
            _process(
                "p2",
                "Consume",
                inputs=[_io("buffer_b", "Buffer B", "buffer")],
                outputs=[],
            ),
        ]
        result = MaterialHandoverValidator(materials=materials, processes=processes).validate()

        orphan_warnings = [w for w in result["warnings"] if "never used as input" in w["message"]]
        assert len(orphan_warnings) == 1
        assert orphan_warnings[0]["severity"] == "info"
        assert orphan_warnings[0]["material_id"] == "sample_a"
        assert "Sample A" in orphan_warnings[0]["message"]

    def test_process_without_name_uses_positional_name(self):
        """Processes lacking a name are referenced by their position in errors."""
        processes = [{"id": "p1", "inputs": ["missing_mat"], "outputs": []}]
        result = MaterialHandoverValidator(materials=[], processes=processes).validate()

        assert result["valid"] is False
        assert result["errors"][0]["process"] == "Process 0"

    def test_validate_resets_previous_results(self, valid_flow):
        """Calling validate() again starts from a clean slate."""
        materials, processes = valid_flow
        validator = MaterialHandoverValidator(materials=materials, processes=processes)

        first = validator.validate()
        assert len(first["warnings"]) == 1

        second = validator.validate()
        assert second["errors"] == []
        assert len(second["warnings"]) == 1
        assert second["valid"] is True


# ----------------------------------------------------------------------
# _are_types_compatible()
# ----------------------------------------------------------------------

COMPATIBLE_TYPE_PAIRS = [
    ("source", "sample"),
    ("sample", "sample"),
    ("otherMaterial", "sample"),
    ("cell culture", "cell culture"),
    ("cell culture", "sample"),
    ("cell pellet", "cell pellet"),
    ("cell pellet", "sample"),
    ("protein solution", "protein solution"),
    ("protein solution", "sample"),
    ("lysate", "lysate"),
    ("lysate", "sample"),
    ("protein mixture", "protein mixture"),
    ("protein depot", "protein depot"),
    ("buffer", "buffer"),
    ("medium", "medium"),
    ("chemical", "chemical"),
    ("enzyme", "enzyme"),
    ("medication", "medication"),
    ("polysaccharide solution", "polysaccharide solution"),
]

INCOMPATIBLE_TYPE_PAIRS = [
    ("source", "source"),
    ("source", "cell culture"),
    ("cell culture", "source"),
    ("cell culture", "cell pellet"),
    ("cell pellet", "cell culture"),
    ("cell pellet", "lysate"),
    ("lysate", "cell pellet"),
    ("buffer", "cell culture"),
    ("buffer", "sample"),
    ("buffer", "otherMaterial"),
    ("medium", "sample"),
    ("medium", "otherMaterial"),
    ("chemical", "sample"),
    ("chemical", "otherMaterial"),
    ("enzyme", "sample"),
    ("enzyme", "otherMaterial"),
    ("medication", "otherMaterial"),
    ("polysaccharide solution", "otherMaterial"),
    ("protein solution", "lysate"),
]


@pytest.mark.unit
class TestAreTypesCompatible:
    """Tests for MaterialHandoverValidator._are_types_compatible()."""

    @pytest.mark.parametrize(
        "output_type,input_type",
        COMPATIBLE_TYPE_PAIRS,
        ids=[f"{o}->{i}" for o, i in COMPATIBLE_TYPE_PAIRS],
    )
    def test_compatible_pairs(self, validator, output_type, input_type):
        """All rule-defined compatible type pairs return True."""
        assert validator._are_types_compatible(output_type, input_type) is True

    @pytest.mark.parametrize(
        "output_type,input_type",
        INCOMPATIBLE_TYPE_PAIRS,
        ids=[f"{o}->{i}" for o, i in INCOMPATIBLE_TYPE_PAIRS],
    )
    def test_incompatible_pairs(self, validator, output_type, input_type):
        """All rule-defined incompatible type pairs return False."""
        assert validator._are_types_compatible(output_type, input_type) is False

    def test_matching_is_case_insensitive(self, validator):
        """Type lookups are normalized to lowercase before comparison."""
        assert validator._are_types_compatible("SOURCE", "Sample") is True
        assert validator._are_types_compatible("Cell Culture", "CELL CULTURE") is True
        assert validator._are_types_compatible("CELL PELLET", "Lysate") is False

    def test_unknown_output_type_is_permissive(self, validator):
        """Output types without a rule fall through to the permissive branch."""
        assert validator._are_types_compatible("customType", "anything") is True

    def test_rule_keys_with_uppercase_are_not_matched(self, validator):
        """Rule keys are defined in mixed case, so lowercased lookups for them
        fall through to the permissive branch (documented behavior)."""
        assert validator._are_types_compatible("DNA", "otherMaterial") is True
        assert validator._are_types_compatible("DNA", "sample") is True
        assert validator._are_types_compatible("otherMaterial", "buffer") is True

    def test_rule_values_with_uppercase_are_not_matched(self, validator):
        """Rule values are defined in mixed case, but input types are lowercased
        before the membership check, so 'otherMaterial' targets never match
        (documented behavior)."""
        assert validator._are_types_compatible("buffer", "otherMaterial") is False
        assert validator._are_types_compatible("medium", "otherMaterial") is False


# ----------------------------------------------------------------------
# _get_summary()
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestGetSummary:
    """Tests for MaterialHandoverValidator._get_summary()."""

    def test_no_issues(self, validator):
        """No errors or warnings yields the clean summary."""
        assert validator._get_summary() == "Material handover is valid."

    def test_errors_only(self, validator):
        """Only errors are reflected in the summary."""
        validator.errors = [{"message": "e"} for _ in range(3)]

        assert validator._get_summary() == "Material handover has 3 error(s)."

    def test_warnings_only(self, validator):
        """Only warnings are reflected in the summary."""
        validator.warnings = [{"message": "w"} for _ in range(2)]

        assert validator._get_summary() == "Material handover has 2 warning(s)."

    def test_errors_and_warnings(self, validator):
        """Both errors and warnings are joined in the summary."""
        validator.errors = [{"message": "e"} for _ in range(3)]
        validator.warnings = [{"message": "w"} for _ in range(2)]

        assert validator._get_summary() == "Material handover has 3 error(s) and 2 warning(s)."

    def test_summary_included_in_validate_result(self, valid_flow):
        """validate() always includes the generated summary string."""
        materials, processes = valid_flow
        result = MaterialHandoverValidator(materials=materials, processes=processes).validate()

        assert "summary" in result
        assert isinstance(result["summary"], str)
        assert result["summary"] == "Material handover has 1 warning(s)."


# ----------------------------------------------------------------------
# get_suggested_materials()
# ----------------------------------------------------------------------


@pytest.mark.unit
class TestGetSuggestedMaterials:
    """Tests for MaterialHandoverValidator.get_suggested_materials()."""

    def test_input_suggestions_return_empty_list(self, validator):
        """Input suggestions are not implemented yet and return an empty list."""
        process = _process("p1", "Process")

        assert validator.get_suggested_materials(process, "input") == []

    def test_output_suggestions_return_empty_list(self, validator):
        """Output suggestions are not implemented yet and return an empty list."""
        process = _process("p1", "Process")

        assert validator.get_suggested_materials(process, "output") == []

    def test_default_io_type_returns_empty_list(self, validator):
        """The default io_type path also returns an empty list."""
        process = _process("p1", "Process")

        assert validator.get_suggested_materials(process) == []

    def test_suggestions_with_protocol_ref_return_empty_list(self, validator):
        """A protocol reference does not change the (stub) suggestion behavior."""
        process = _process("p1", "Process")
        process["protocol_ref"] = "/inv_1/study_1#protocol_1"

        assert validator.get_suggested_materials(process, "input") == []
        assert validator.get_suggested_materials(process, "output") == []

    def test_suggestions_for_unknown_io_type_return_empty_list(self, validator):
        """Unknown io_type values are ignored and return an empty list."""
        process = _process("p1", "Process")

        assert validator.get_suggested_materials(process, "neither") == []
