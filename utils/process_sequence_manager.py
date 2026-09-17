"""
Process Sequence Manager for handling process sequence data.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, cast


class ProcessSequenceManager:
    """Manager for process sequence data and operations."""

    def __init__(self, study_data: Dict[str, Any], material_manager=None, protocols=None):
        """
        Initialize the process sequence manager.

        Args:
            study_data: The study data dictionary containing materials and protocols
            material_manager: Optional MaterialManager for creating materials
            protocols: Optional list of protocol templates with inputs/outputs defined
        """
        self.study_data = study_data or {}
        self.material_manager = material_manager
        self.process_sequence = self._load_process_sequence()
        # Use provided protocols if available, otherwise load from study_data
        self.protocols = protocols if protocols is not None else self._load_protocols()

        # Use MaterialManager's materials if available, otherwise load from study_data
        if self.material_manager:
            self.materials = self.material_manager.materials
        else:
            self.materials = self._load_materials()

        # Track counters for each process name to generate unique material names
        self.process_counters: Dict[str, int] = {}

        # Restore process counters from existing process names
        self._restore_process_counters()

    def _load_process_sequence(self) -> Dict[str, Any]:
        """Load process sequence from study data."""
        # Try to load from 'process_sequence' (snake_case)
        process_sequence = self.study_data.get("process_sequence", {})

        # If not found, try 'processSequence' (camelCase) - for ISA-JSON compatibility
        if not process_sequence and "processSequence" in self.study_data:
            process_sequence = self.study_data.get("processSequence", {})

        # Handle case where process_sequence is a list (from complete ISA-JSON structure)
        # In complete ISA-JSON, processSequence is a list, not a dict with "processes" key
        if isinstance(process_sequence, list):
            return {"processes": process_sequence}

        return cast(Dict[str, Any], process_sequence)

    def _load_materials(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load materials from study data."""
        materials = self.study_data.get("materials", {})
        return {
            "sources": materials.get("sources", []),
            "samples": materials.get("samples", []),
            "otherMaterials": materials.get("otherMaterials", []),
        }

    def _load_protocols(self) -> List[Dict[str, Any]]:
        """Load protocols from study data."""
        # Handle both complete ISA-JSON structure and simple study structure
        if "studies" in self.study_data:
            # Complete ISA-JSON structure
            studies = self.study_data.get("studies", [])
            if not studies:
                return []
            # Get protocols from the first study
            study = studies[0] if isinstance(studies, list) else studies
            return cast(List[Dict[str, Any]], study.get("protocols", []))
        else:
            # Simple study structure (already extracted)
            return cast(List[Dict[str, Any]], self.study_data.get("protocols", []))

    def get_all_materials(self) -> List[Dict[str, Any]]:
        """Get all materials (sources, samples, otherMaterials)."""
        all_materials = []
        all_materials.extend(self.materials["sources"])
        all_materials.extend(self.materials["samples"])
        all_materials.extend(self.materials["otherMaterials"])
        return all_materials

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

    def get_materials_by_type(self, material_type: str) -> List[Dict[str, Any]]:
        """
        Get materials filtered by type.

        Args:
            material_type: The material type to filter by

        Returns:
            List of materials of the specified type
        """
        return [
            m
            for m in self.get_all_materials()
            if m.get("materialType", "").lower() == material_type.lower()
        ]

    def get_processes(self) -> List[Dict[str, Any]]:
        """Get the list of processes in the sequence."""
        return cast(List[Dict[str, Any]], self.process_sequence.get("processes", []))

    def _get_process_id(self, process: Dict[str, Any]) -> str:
        """
        Get the process ID, handling both 'id' and '@id' fields.

        Args:
            process: The process dictionary

        Returns:
            The process ID from 'id' or '@id' field, or empty string if neither exists
        """
        return str(process.get("id", process.get("@id", "")))

    def add_process(self, process: Dict[str, Any], index: Optional[int] = None) -> bool:
        """
        Add a process to the sequence.

        Args:
            process: The process data to add
            index: Optional index to insert at (appends if None)

        Returns:
            True if successful, False otherwise
        """
        processes = self.get_processes()

        if index is not None:
            processes.insert(index, process)
        else:
            processes.append(process)

        self.process_sequence["processes"] = processes
        return True

    def remove_process(self, process_id: str) -> bool:
        """
        Remove a process from the sequence.

        Args:
            process_id: The ID of the process to remove

        Returns:
            True if successful, False otherwise
        """
        processes = self.get_processes()
        original_count = len(processes)

        self.process_sequence["processes"] = [
            p for p in processes if self._get_process_id(p) != process_id
        ]

        return len(self.process_sequence["processes"]) < original_count

    def reorder_process(self, process_id: str, new_index: int) -> bool:
        """
        Reorder a process in the sequence.

        Args:
            process_id: The ID of the process to move
            new_index: The new index for the process

        Returns:
            True if successful, False otherwise
        """
        processes = self.get_processes()

        # Find the process
        process = None
        old_index = None
        for i, p in enumerate(processes):
            if self._get_process_id(p) == process_id:
                process = p
                old_index = i
                break

        if process is None or old_index is None:
            return False

        # Remove from old position
        processes.pop(old_index)

        # Insert at new position
        new_index = max(0, min(new_index, len(processes)))
        processes.insert(new_index, process)

        self.process_sequence["processes"] = processes
        return True

    def update_process(self, process_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update a process with new data.

        Args:
            process_id: The ID of the process to update
            updates: Dictionary of fields to update

        Returns:
            True if successful, False otherwise
        """
        processes = self.get_processes()

        for i, process in enumerate(processes):
            proc_id = self._get_process_id(process)
            if proc_id == process_id:
                processes[i].update(updates)
                self.process_sequence["processes"] = processes
                return True

        return False

    def get_process_by_id(self, process_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a process by its ID.

        Args:
            process_id: The process ID to search for

        Returns:
            The process dictionary if found, None otherwise
        """
        for process in self.get_processes():
            if self._get_process_id(process) == process_id:
                return process
        return None

    def validate_process(self, process_data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Validate a process's data.

        Args:
            process_data: The process data to validate

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Check for required fields
        if not process_data.get("name"):
            errors.append("Process name is required")

        if not process_data.get("protocol_ref"):
            errors.append("Protocol reference is required")

        return len(errors) == 0, errors

    def _get_next_process_counter(self, process_name: str) -> int:
        """
        Get the next counter for a process name.

        Args:
            process_name: The name of the process

        Returns:
            The next counter value for this process name
        """
        if process_name not in self.process_counters:
            self.process_counters[process_name] = 0
        self.process_counters[process_name] += 1
        return self.process_counters[process_name]

    def _restore_process_counters(self):
        """Restore process counters from existing process names."""
        processes = self.get_processes()
        self.process_counters = {}

        for process in processes:
            process_name = process.get("name", "")

            # Parse process name to extract base name and counter
            # Format: "{base_name} #{counter}" or just "{base_name}"
            if " #" in process_name:
                parts = process_name.split(" #")
                base_name = parts[0]
                try:
                    counter = int(parts[1].split()[0]) if len(parts) > 1 else 0
                except (ValueError, IndexError):
                    counter = 0

                # Update counter to max of existing values
                if base_name in self.process_counters:
                    self.process_counters[base_name] = max(
                        self.process_counters[base_name], counter
                    )
                else:
                    self.process_counters[base_name] = counter
            else:
                # Old format without counter - treat as #0
                self.process_counters.setdefault(process_name, 0)

    def auto_link_materials_for_process(
        self, process: Dict[str, Any], index: int
    ) -> Dict[str, Any]:
        """
        Automatically create and link materials for a process.

        Args:
            process: The process being added
            index: The index where the process is being inserted

        Returns:
            Updated process with auto-linked materials
        """
        processes = self.get_processes()
        process_name = process.get("name", "Unknown")
        protocol_ref = process.get("protocol_ref", "")

        # Get counter for this process name
        process_counter = self._get_next_process_counter(process_name)

        # Get inputs from previous process outputs (only if not manually assigned)
        if index > 0:
            previous_process = processes[index - 1]
            process["inputs"] = self._get_materials_from_outputs(previous_process, skip_locked=True)
        else:
            # First process - create from protocol template
            process["inputs"] = self._create_materials_from_protocol(
                protocol_ref, "inputs", process_name=process_name, process_counter=process_counter
            )

        # Create outputs from template (only if not manually assigned)
        process["outputs"] = self._create_materials_from_protocol(
            protocol_ref, "outputs", process_name=process_name, process_counter=process_counter
        )

        return process

    def update_material_links_after_reorder(self, old_index: int, new_index: int):
        """
        Update material links after process reordering.
        Skips materials that have been manually assigned (locked=True).

        Args:
            old_index: Original process index
            new_index: New process index
        """
        processes = self.get_processes()

        # Update links for all affected processes
        for i, process in enumerate(processes):
            if i > 0:
                previous_process = processes[i - 1]
                # Only update inputs that are not locked
                process["inputs"] = self._get_materials_from_outputs(
                    previous_process, skip_locked=True, existing_inputs=process.get("inputs", [])
                )

    def _normalize_material_reference(self, material_ref: Any) -> Dict[str, Any]:
        """
        Normalize a material reference to a standard dictionary format.

        Handles both ISA-JSON URI strings and dictionary formats.

        Args:
            material_ref: Either a URI string or a dictionary with material info

        Returns:
            Dictionary with material_id, name, and materialType
        """
        if isinstance(material_ref, dict):
            # Already in dictionary format
            return {
                "material_id": material_ref.get("material_id", material_ref.get("@id", "")),
                "name": material_ref.get("name", ""),
                "materialType": material_ref.get("materialType", "sample"),
            }
        elif isinstance(material_ref, str):
            # ISA-JSON format - URI string
            # Try to find the material in the materials list
            material_id = material_ref.split("#")[-1] if "#" in material_ref else material_ref

            # Search for the material in all material types
            for material_type in ["sources", "samples", "otherMaterials"]:
                for material in self.materials.get(material_type, []):
                    if material.get("@id") == material_id or material.get("@id") == material_ref:
                        return {
                            "material_id": material.get("@id", ""),
                            "name": material.get("name", ""),
                            "materialType": material.get("materialType", material_type.rstrip("s")),
                        }

            # If not found, create a basic reference from the URI
            name = material_id.replace("_", " ").replace("-", " ").title()
            return {
                "material_id": material_id,
                "name": name,
                "materialType": "sample",
            }
        else:
            # Unknown format, return empty reference
            return {
                "material_id": "",
                "name": "",
                "materialType": "sample",
            }

    def _get_materials_from_outputs(
        self,
        previous_process: Dict[str, Any],
        skip_locked: bool = True,
        existing_inputs: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get materials from previous process outputs.
        Preserves locked materials from existing inputs.

        Args:
            previous_process: The previous process in the sequence
            skip_locked: If True, skip materials that are locked
            existing_inputs: Current inputs to preserve locked materials from

        Returns:
            List of material references
        """
        existing_inputs = existing_inputs or []
        locked_inputs = [inp for inp in existing_inputs if inp.get("locked", False)]

        # Normalize previous outputs to handle both URI strings and dictionaries
        previous_outputs = previous_process.get("outputs", [])
        normalized_outputs = [self._normalize_material_reference(out) for out in previous_outputs]

        if skip_locked and locked_inputs:
            # Preserve locked inputs and add non-locked from previous outputs
            new_inputs = []

            # Map previous outputs by name for matching
            _output_map = {out.get("name"): out for out in normalized_outputs}  # noqa: F841

            # Add locked inputs first
            new_inputs.extend(locked_inputs)

            # Add non-locked inputs from previous outputs
            for output in normalized_outputs:
                output_name = output.get("name", "")
                if not any(inp.get("name") == output_name for inp in locked_inputs):
                    new_inputs.append(
                        {
                            "material_id": output.get("material_id", ""),
                            "name": output_name,
                            "materialType": output.get("materialType", ""),
                            "locked": False,  # Auto-linked materials are not locked
                        }
                    )

            return new_inputs
        else:
            # No locked inputs to preserve, use all previous outputs
            return [
                {
                    "material_id": out.get("material_id", ""),
                    "name": out.get("name", ""),
                    "materialType": out.get("materialType", ""),
                    "locked": False,
                }
                for out in normalized_outputs
            ]

    def _create_materials_from_protocol(
        self,
        protocol_ref: str,
        io_type: str,
        process_name: Optional[str] = None,
        process_counter: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Create materials from protocol template with unique naming.

        Args:
            protocol_ref: Reference to the protocol template
            io_type: Either "inputs" or "outputs"
            process_name: Name of the process creating these materials
            process_counter: Counter for the process instance

        Returns:
            List of material references with material_id
        """
        # Get input/output definitions from protocol
        template_ios = []
        for prot in self.protocols:
            if prot.get("name", "") == protocol_ref:
                template_ios = prot.get(io_type, [])
                break

        materials = []
        for io_def in template_ios:
            # Get base material name from template
            base_material_name = io_def.get("name", "Unknown")
            material_type = io_def.get("materialType", "sample")

            # Generate unique material name using process name (which already includes counter)
            if process_name:
                material_name = f"{process_name} - {base_material_name}"
            else:
                material_name = base_material_name

            # Determine material type for storage
            if io_type == "inputs":
                # Inputs are typically sources or otherMaterials
                if material_type in ["source", "cell culture"]:
                    storage_type = "sources"
                else:
                    storage_type = "otherMaterials"
            else:
                # Outputs are typically samples
                storage_type = "samples"

            # Create actual material if MaterialManager is available
            material_id = None
            if self.material_manager:
                # Create the material in the study data
                new_material = {
                    "@id": "",  # Will be auto-generated by MaterialManager
                    "name": material_name,
                    "materialType": material_type,
                    "characteristics": [],
                }
                # Convert storage_type from plural to singular for add_material
                material_type_for_manager = (
                    storage_type.rstrip("s")
                    if storage_type != "otherMaterials"
                    else "otherMaterial"
                )
                self.material_manager.add_material(material_type_for_manager, new_material)

                # Get the created material to retrieve its ID
                # Find the material we just added (it should be the last one)
                material_list = self.material_manager.materials.get(storage_type, [])
                if material_list:
                    material_id = material_list[-1].get("@id", "")

            # Create material reference with material_id
            materials.append(
                {
                    "material_id": material_id,
                    "name": material_name,
                    "materialType": material_type,
                    "storageType": storage_type,
                    "locked": False,  # Auto-linked materials are not locked
                }
            )

        return materials

    def mark_materials_as_locked(self, process_id: str, io_type: str, material_ids: List[str]):
        """
        Mark specific materials as locked (manually assigned).

        Args:
            process_id: The process ID
            io_type: Either "inputs" or "outputs"
            material_ids: List of material IDs to mark as locked
        """
        process = self.get_process_by_id(process_id)
        if process:
            materials = process.get(io_type, [])
            for mat in materials:
                if mat.get("material_id") in material_ids:
                    mat["locked"] = True

    def validate_material_handover(self) -> List[Dict[str, Any]]:
        """
        Validate material handover between processes.

        Returns:
            List of validation warnings/errors
        """
        warnings = []
        processes = self.get_processes()

        for i, process in enumerate(processes):
            process_name = process.get("name", f"Process {i}")
            outputs = process.get("outputs", [])

            # Check next process inputs
            if i < len(processes) - 1:
                next_process = processes[i + 1]
                next_inputs = next_process.get("inputs", [])

                # Check if outputs match next inputs
                for output in outputs:
                    output_name = output.get("name", "")
                    output_id = output.get("material_id", "")

                    # Find matching input in next process
                    matched = False
                    for next_input in next_inputs:
                        if (
                            next_input.get("name", "") == output_name
                            or next_input.get("material_id", "") == output_id
                        ):
                            matched = True
                            break

                    if not matched:
                        warnings.append(
                            {
                                "type": "warning",
                                "process": process_name,
                                "message": f"Output '{output_name}' not used by next process",
                            }
                        )

            # Check if all inputs have sources
            for input_item in process.get("inputs", []):
                # Handle both old format (strings) and new format (dicts)
                input_id = (
                    input_item if isinstance(input_item, str) else input_item.get("material_id", "")
                )
                if input_id and not self.get_material_by_id(input_id):
                    warnings.append(
                        {
                            "type": "error",
                            "process": process_name,
                            "message": f"Input material '{input_id}' not found",
                        }
                    )

        return warnings

    def get_process_sequence_data(self) -> Dict[str, Any]:
        """
        Get the complete process sequence data for saving.

        Returns:
            Dictionary containing process sequence data
        """
        return self.process_sequence

    def export_to_isa_json(self, investigation_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Export process sequence to ISA-JSON format.

        Args:
            investigation_id: Investigation ID for constructing proper @id URLs

        Returns:
            List of processes in ISA-JSON processSequence format
        """
        process_sequence = []

        # Base URL for constructing @id values
        base_url = "https://example.org/investigations"
        inv_id = investigation_id or "inv_1"

        for i, process in enumerate(self.get_processes()):
            # Use investigation_id in @id
            process_name = process.get("name", f"p{i}")
            process_id = process.get("@id", f"{base_url}/{inv_id}#{process_name}")

            # Get date with default to current date if not provided
            date_value = process.get("date", "")
            if not date_value:
                date_value = datetime.now().strftime("%Y-%m-%d")

            isa_process = {
                "@id": process_id,
                "name": process_name,
                "executesProtocol": self._get_protocol_object(
                    process.get("protocol_ref", ""), inv_id
                ),
                "date": date_value,
                # Handle both old format (strings) and new format (dicts)
                "inputs": [
                    p if isinstance(p, str) else p.get("material_id", "")
                    for p in process.get("inputs", [])
                ],
                "outputs": [
                    p if isinstance(p, str) else p.get("material_id", "")
                    for p in process.get("outputs", [])
                ],
                "parameterValues": [],
            }

            # Add parameter values with proper ISA-JSON structure
            for param in process.get("parameters", []):
                param_value = self._export_parameter_value(param, process_id, inv_id)
                isa_process["parameterValues"].append(param_value)

            # NOTE: GUI-specific data removed for ISA-JSON compliance
            # (_status, _inputNames, _outputNames should be stored separately if needed)

            process_sequence.append(isa_process)

        return process_sequence

    def _get_protocol_url(self, protocol_ref: str, investigation_id: str) -> str:
        """
        Construct full protocol URL from protocol reference.

        Args:
            protocol_ref: Protocol reference (name or URL)
            investigation_id: Current investigation ID

        Returns:
            Full protocol URL
        """
        # If already a full URL, return as-is
        if protocol_ref.startswith("http"):
            return protocol_ref

        # Otherwise construct full URL
        protocol_name = protocol_ref.replace(" ", "_").lower()
        return f"https://example.org/investigations/{investigation_id}#prot_{protocol_name}"

    def _get_protocol_object(self, protocol_ref: str, investigation_id: str) -> Dict[str, Any]:
        """
        Get a minimal Protocol object for use in executesProtocol field.

        According to ISA-JSON schema, executesProtocol must be an object,
        not a string reference.

        Args:
            protocol_ref: Protocol reference (name or URL)
            investigation_id: Current investigation ID

        Returns:
            Minimal Protocol object with @id, @type, and name
        """
        protocol_url = self._get_protocol_url(protocol_ref, investigation_id)
        # Extract protocol name from URL for the name field
        if protocol_ref.startswith("http"):
            # Extract name from full URL
            protocol_name = protocol_ref.split("#prot_")[-1].replace("_", " ")
        else:
            protocol_name = protocol_ref

        return {"@id": protocol_url, "name": protocol_name}

    def _export_parameter_value(
        self, param: Dict[str, Any], process_id: str, investigation_id: str = "inv_1"
    ) -> Dict[str, Any]:
        """
        Export a parameter value to ISA-JSON format.

        Args:
            param: Parameter data from internal format
            process_id: Parent process ID for constructing @id
            investigation_id: Investigation ID for constructing category @id

        Returns:
            ISA-JSON compliant parameter value with category as @id reference only
        """
        param_name = param.get("name", "")
        param_id = f"{process_id}#pp_{param_name.replace(' ', '_')}"

        # Category should only be an @id reference to the parameter defined in protocols
        # The format is #parameter/param_name (matching what's defined in protocol parameters)
        param_value: Dict[str, Any] = {
            "@id": param_id,
            "category": {"@id": f"#parameter/{param_name.replace(' ', '_')}"},
        }

        # Handle value - can be numeric with unit, or text value
        value = param.get("value", "")
        unit = param.get("unit", {})
        has_annotation_value = "annotationValue" in param

        # According to ISA-JSON schema, value can be:
        # 1. An ontology annotation (object with annotationValue, termSource, termAccession)
        # 2. A simple string
        # 3. A simple number (optionally with a unit)
        if value or unit or has_annotation_value:
            if has_annotation_value:
                # Ontology annotation value
                param_value["value"] = {"annotationValue": param["annotationValue"]}
                if "termSource" in param:
                    param_value["value"]["termSource"] = param["termSource"]
                if "termAccession" in param:
                    param_value["value"]["termAccession"] = param["termAccession"]
            else:
                # Simple value (string or number)
                # Check if we have a unit - if so, we need to wrap in object
                if unit and any(unit.values()):
                    # Build unit object
                    unit_obj = {}
                    if "annotationValue" in unit:
                        unit_obj["annotationValue"] = unit["annotationValue"]
                    if "termSource" in unit:
                        unit_obj["termSource"] = unit["termSource"]
                    if "termAccession" in unit:
                        unit_obj["termAccession"] = unit["termAccession"]

                    if unit_obj:
                        # Convert value to number if possible
                        numeric_value = None
                        if value:
                            try:
                                if "." in str(value):
                                    numeric_value = float(value)
                                else:
                                    numeric_value = int(value)
                            except (ValueError, TypeError):
                                pass

                        # Wrap value and unit in object
                        param_value["value"] = {}
                        if numeric_value is not None:
                            param_value["value"]["value"] = numeric_value
                        else:
                            param_value["value"]["value"] = str(value) if value else ""
                        param_value["value"]["unit"] = unit_obj
                    else:
                        # No valid unit, just assign value directly
                        if value:
                            try:
                                if "." in str(value):
                                    param_value["value"] = float(value)
                                else:
                                    param_value["value"] = int(value)
                            except (ValueError, TypeError):
                                param_value["value"] = str(value)
                else:
                    # No unit, assign value directly
                    if value:
                        try:
                            if "." in str(value):
                                param_value["value"] = float(value)
                            else:
                                param_value["value"] = int(value)
                        except (ValueError, TypeError):
                            param_value["value"] = str(value)

        return param_value
