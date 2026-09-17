"""
Material Handover Validator for validating material flow between processes.
"""

from typing import Any, Dict, List, Set


class MaterialHandoverValidator:
    """Validator for material handover between processes."""

    def __init__(self, materials: List[Dict[str, Any]], processes: List[Dict[str, Any]]):
        """
        Initialize the validator.

        Args:
            materials: List of all available materials
            processes: List of processes to validate
        """
        self.materials = {m.get("@id", ""): m for m in materials}
        self.processes = processes
        self.warnings: List[Dict[str, Any]] = []
        self.errors: List[Dict[str, Any]] = []

    def validate(self) -> Dict[str, Any]:
        """
        Validate material handover across all processes.

        Returns:
            Dictionary containing warnings and errors
        """
        self.warnings = []
        self.errors = []

        # Track which materials are used as outputs
        output_materials: Set[str] = set()

        # Track which materials are used as inputs
        input_materials: Set[str] = set()

        for i, process in enumerate(self.processes):
            process_name = process.get("name", f"Process {i}")
            process_id = process.get("id", f"p{i}")

            # Validate inputs
            for input_item in process.get("inputs", []):
                # Handle both old format (strings) and new format (dicts)
                input_id = (
                    input_item if isinstance(input_item, str) else input_item.get("material_id", "")
                )
                input_name = (
                    input_item if isinstance(input_item, str) else input_item.get("name", "")
                )

                input_materials.add(input_id)

                # Check if input material exists
                if input_id and input_id not in self.materials:
                    self.errors.append(
                        {
                            "type": "error",
                            "severity": "critical",
                            "process": process_name,
                            "process_id": process_id,
                            "message": f"Input material '{input_name}' (ID: {input_id}) not found in materials",  # noqa: E501
                            "input_id": input_id,
                        }
                    )

            # Validate outputs
            for output_item in process.get("outputs", []):
                # Handle both old format (strings) and new format (dicts)
                output_id = (
                    output_item
                    if isinstance(output_item, str)
                    else output_item.get("material_id", "")
                )
                output_name = (
                    output_item if isinstance(output_item, str) else output_item.get("name", "")
                )

                output_materials.add(output_id)

                # Check if output material exists (should be a sample)
                if output_id and output_id not in self.materials:
                    # This might be a new sample being created
                    self.warnings.append(
                        {
                            "type": "warning",
                            "severity": "info",
                            "process": process_name,
                            "process_id": process_id,
                            "message": f"Output material '{output_name}' (ID: {output_id}) will be created as new sample",  # noqa: E501
                            "output_id": output_id,
                        }
                    )

        # Validate handover between processes
        for i in range(len(self.processes) - 1):
            current_process = self.processes[i]
            next_process = self.processes[i + 1]

            current_name = current_process.get("name", f"Process {i}")
            next_name = next_process.get("name", f"Process {i + 1}")

            current_outputs = current_process.get("outputs", [])
            next_inputs = next_process.get("inputs", [])

            # Check if outputs are used by next process
            for output in current_outputs:
                output_id = output.get("material_id", "")
                output_name = output.get("name", "")
                output_type = output.get("materialType", "")

                # Find matching input in next process
                matched = False
                for next_input in next_inputs:
                    next_input_id = next_input.get("material_id", "")
                    next_input_name = next_input.get("name", "")
                    next_input_type = next_input.get("materialType", "")

                    # Match by ID or name
                    if next_input_id == output_id or next_input_name == output_name:
                        matched = True

                        # Validate type compatibility
                        if output_type and next_input_type:
                            if not self._are_types_compatible(output_type, next_input_type):
                                self.errors.append(
                                    {
                                        "type": "error",
                                        "severity": "error",
                                        "process": current_name,
                                        "message": f"Output type '{output_type}' incompatible with input type '{next_input_type}'",  # noqa: E501
                                        "output_type": output_type,
                                        "input_type": next_input_type,
                                    }
                                )
                        break

                if not matched and output_id:
                    self.warnings.append(
                        {
                            "type": "warning",
                            "severity": "warning",
                            "process": current_name,
                            "message": f"Output '{output_name}' (ID: {output_id}) not used by next process '{next_name}'",  # noqa: E501
                            "output_id": output_id,
                        }
                    )

        # Check for orphaned materials (not used as inputs)
        all_input_ids = input_materials
        all_output_ids = output_materials
        orphaned_outputs = all_output_ids - all_input_ids

        for output_id in orphaned_outputs:
            if output_id in self.materials:
                material = self.materials[output_id]
                self.warnings.append(
                    {
                        "type": "warning",
                        "severity": "info",
                        "message": f"Material '{material.get('name', output_id)}' is output but never used as input",  # noqa: E501
                        "material_id": output_id,
                    }
                )

        return {
            "valid": len(self.errors) == 0,
            "warnings": self.warnings,
            "errors": self.errors,
            "summary": self._get_summary(),
        }

    def _are_types_compatible(self, output_type: str, input_type: str) -> bool:
        """
        Check if material types are compatible for handover.

        Args:
            output_type: The output material type
            input_type: The input material type

        Returns:
            True if types are compatible, False otherwise
        """
        # Define compatibility rules
        compatibility_rules = {
            "source": ["sample"],
            "sample": ["sample"],
            "otherMaterial": ["sample"],
            "cell culture": ["sample", "cell culture"],
            "cell pellet": ["sample", "cell pellet"],
            "protein solution": ["sample", "protein solution"],
            "lysate": ["sample", "lysate"],
            "protein mixture": ["sample", "protein mixture"],
            "protein depot": ["sample", "protein depot"],
            "buffer": ["otherMaterial", "buffer"],
            "medium": ["otherMaterial", "medium"],
            "DNA": ["otherMaterial", "DNA"],
            "chemical": ["otherMaterial", "chemical"],
            "enzyme": ["otherMaterial", "enzyme"],
            "medication": ["otherMaterial", "medication"],
            "polysaccharide solution": ["otherMaterial", "polysaccharide solution"],
        }

        # Normalize types
        output_type_lower = output_type.lower()
        input_type_lower = input_type.lower()

        # Check if input type accepts output type
        if output_type_lower in compatibility_rules:
            return input_type_lower in compatibility_rules[output_type_lower]

        # If no rule defined, be permissive
        return True

    def _get_summary(self) -> str:
        """Get a summary of validation results."""
        error_count = len(self.errors)
        warning_count = len(self.warnings)

        if error_count == 0 and warning_count == 0:
            return "Material handover is valid."

        summary_parts = []
        if error_count > 0:
            summary_parts.append(f"{error_count} error(s)")
        if warning_count > 0:
            summary_parts.append(f"{warning_count} warning(s)")

        return "Material handover has " + " and ".join(summary_parts) + "."

    def get_suggested_materials(
        self, process: Dict[str, Any], io_type: str = "input"
    ) -> List[Dict[str, Any]]:
        """
        Get suggested materials for a process input or output.

        Args:
            process: The process to get suggestions for
            io_type: Either "input" or "output"

        Returns:
            List of suggested materials
        """
        suggestions: List[Dict[str, Any]] = []

        # Get process protocol reference
        _protocol_ref = process.get("protocol_ref", "")  # noqa: F841

        # Load protocol template to get expected material types
        # This would require loading from protocol templates
        # For now, return all materials

        if io_type == "input":
            # Suggest materials that are outputs of previous processes
            # This would require tracking process order
            pass
        elif io_type == "output":
            # Suggest creating new sample materials
            pass

        return suggestions
