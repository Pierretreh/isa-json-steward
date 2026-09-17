"""
Process Sequence page for the ISA-JSON Data Steward GUI.
Enhanced version with material linking, default values, and process management.
"""

import json
import logging

# Import utilities
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDropEvent, QResizeEvent
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..dialogs.material_selection_dialog import MaterialSelectionDialog
from ..widgets.common import ActionButton, PrimaryButton, SectionHeader
from ..widgets.file_attachment_widget import FileAttachmentWidget
from .base_page import ScrollablePage

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.isa_json_exporter import ISAJsonExporter  # noqa: E402
from utils.material_handover_validator import MaterialHandoverValidator  # noqa: E402
from utils.material_manager import MaterialManager  # noqa: E402
from utils.process_sequence_manager import ProcessSequenceManager  # noqa: E402


class DraggableTreeWidget(QTreeWidget):
    """Tree widget with drag and drop support for reordering."""

    itemMoved = pyqtSignal(int, int)  # old_index, new_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.drag_start_index = None

    def startDrag(self, supportedActions):
        """Handle drag start."""
        item = self.currentItem()
        if item:
            self.drag_start_index = self.indexOfTopLevelItem(item)
        super().startDrag(supportedActions)

    def dropEvent(self, event: Optional[QDropEvent]):
        """Handle drop event for reordering."""
        if event is None:
            return
        if self.drag_start_index is not None:
            # Get drop position (convert QPointF to QPoint for itemAt)
            pos = event.position().toPoint()
            item = self.itemAt(pos)

            if item:
                new_index = self.indexOfTopLevelItem(item)
                self.itemMoved.emit(self.drag_start_index, new_index)

        event.accept()
        super().dropEvent(event)


class ProcessSequencePage(ScrollablePage):
    """Process Sequence page for entering experimental parameters and managing process flow."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.current_process = None
        self.protocols = {}
        self.process_manager: Optional[ProcessSequenceManager] = None
        self.material_manager = None
        self.process_tree_items = {}  # Map process_id to tree item
        self.setup_process_ui()

    def setup_process_ui(self):
        """Set up the process sequence UI."""
        # Header
        self.add_widget(SectionHeader("Process Sequence"))

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: Process sequence tree
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Process sequence buttons
        buttons_layout = QHBoxLayout()

        add_btn = PrimaryButton("Add Process")
        add_btn.clicked.connect(self._on_add_process)
        buttons_layout.addWidget(add_btn)

        remove_btn = ActionButton("Remove")
        remove_btn.clicked.connect(self._on_remove_process)
        buttons_layout.addWidget(remove_btn)

        buttons_layout.addStretch()
        left_layout.addLayout(buttons_layout)

        # Process tree with drag-drop reordering
        self.tree = DraggableTreeWidget()
        self.tree.setHeaderLabels(["Process", "Status", "Materials"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setMinimumHeight(400)
        self.tree.itemSelectionChanged.connect(self._on_process_selected)
        self.tree.itemMoved.connect(self._on_process_moved)

        # Configure header resize modes - Interactive for user-adjustable columns
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 120)
        self.tree.setColumnWidth(2, 150)

        left_layout.addWidget(self.tree)
        splitter.addWidget(left_panel)

        # Right panel: Process details
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Process info group
        info_group = QGroupBox("Process Information")
        info_layout = QFormLayout()

        self.process_name_label = QLabel("No process selected")
        self.process_name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_layout.addRow("Process:", self.process_name_label)

        self.protocol_label = QLabel("-")
        info_layout.addRow("Protocol:", self.protocol_label)

        info_group.setLayout(info_layout)
        right_layout.addWidget(info_group)

        # Parameters group
        params_group = QGroupBox("Parameters")
        params_layout = QVBoxLayout()

        self.params_scroll = QScrollArea()
        self.params_scroll.setWidgetResizable(True)
        self.params_scroll.setMinimumHeight(300)  # Initial minimum height
        self.params_widget = QWidget()
        self.params_layout = QFormLayout(self.params_widget)

        # Placeholder for parameters
        self.param_entries = {}

        self.params_scroll.setWidget(self.params_widget)
        params_layout.addWidget(self.params_scroll)
        params_group.setLayout(params_layout)
        right_layout.addWidget(params_group)

        # Materials group
        materials_group = QGroupBox("Materials")
        materials_layout = QVBoxLayout()

        # Inputs
        inputs_layout = QVBoxLayout()
        inputs_label = QLabel("<b>Inputs:</b>")
        inputs_layout.addWidget(inputs_label)

        self.inputs_list = QListWidget()
        self.inputs_list.setMaximumHeight(100)
        inputs_layout.addWidget(self.inputs_list)

        select_inputs_btn = ActionButton("Select Inputs...")
        select_inputs_btn.clicked.connect(self._on_select_inputs)
        inputs_layout.addWidget(select_inputs_btn)

        materials_layout.addLayout(inputs_layout)

        # Outputs
        outputs_layout = QVBoxLayout()
        outputs_label = QLabel("<b>Outputs:</b>")
        outputs_layout.addWidget(outputs_label)

        self.outputs_list = QListWidget()
        self.outputs_list.setMaximumHeight(100)
        outputs_layout.addWidget(self.outputs_list)

        select_outputs_btn = ActionButton("Select Outputs...")
        select_outputs_btn.clicked.connect(self._on_select_outputs)
        outputs_layout.addWidget(select_outputs_btn)

        materials_layout.addLayout(outputs_layout)
        materials_group.setLayout(materials_layout)
        right_layout.addWidget(materials_group)

        # Files group
        files_group = QGroupBox("File Attachments")
        files_layout = QVBoxLayout()

        # Create file attachment widget
        self.file_attachment_widget = FileAttachmentWidget(parent=files_group)
        files_layout.addWidget(self.file_attachment_widget)

        files_group.setLayout(files_layout)
        right_layout.addWidget(files_group)

        # Validation status
        self.validation_label = QLabel("")
        self.validation_label.setWordWrap(True)
        self.validation_label.setStyleSheet("color: orange; padding: 5px;")
        right_layout.addWidget(self.validation_label)

        splitter.addWidget(right_panel)

        # Set stretch factors
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        self.set_expanding(splitter)
        self.add_widget(splitter)

        # Bottom buttons
        bottom_layout = QHBoxLayout()

        save_btn = PrimaryButton("Save Process")
        save_btn.clicked.connect(self._on_save)
        bottom_layout.addWidget(save_btn)

        validate_btn = ActionButton("Validate Handover")
        validate_btn.clicked.connect(self._on_validate_handover)
        bottom_layout.addWidget(validate_btn)

        bottom_layout.addStretch()

        self.add_layout(bottom_layout)

    def _load_protocols(self):
        """Load protocol templates from templates directory."""
        self.tree.clear()
        self.process_tree_items = {}
        self.protocols = {}

        protocol_dir = self.main_window.get_templates_root() / "protocol_templates"

        if not protocol_dir.exists():
            self.main_window.status_bar.show_message("Protocol templates directory not found")
            self._load_sample_protocols()
            return

        # Group protocols by section (built dynamically from loaded data)
        sections: dict[str, list] = {}

        # Load protocol files
        for json_file in sorted(protocol_dir.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    protocol_data = json.load(f)

                name = protocol_data.get("name", json_file.stem)
                section = self._get_protocol_section(name, protocol_data)

                if section not in sections:
                    sections[section] = []
                sections[section].append(
                    {"name": name, "filename": json_file.name, "data": protocol_data}
                )
                self.protocols[name] = protocol_data
            except Exception as e:
                print(f"Error loading protocol {json_file}: {e}")

        # Build tree from process sequence if available
        self._load_process_sequence()

        # If no process sequence, build from templates
        if not self.process_manager and sections:
            for section_name, protocols in sections.items():
                section_item = QTreeWidgetItem(self.tree)
                section_item.setText(0, section_name)
                section_item.setText(1, "")
                section_item.setExpanded(True)

                for protocol in protocols:
                    protocol_item = QTreeWidgetItem(section_item)
                    protocol_item.setText(0, protocol["name"])
                    protocol_item.setText(1, "Template")
                    protocol_item.setData(
                        0, Qt.ItemDataRole.UserRole, {"type": "template", "data": protocol["data"]}
                    )

        self.main_window.status_bar.show_message(f"Loaded {len(self.protocols)} protocol templates")

    def _load_process_sequence(self):
        """Load existing process sequence from study data."""
        study_data = self.main_window.get_study_data()
        if not study_data:
            return

        # Extract process_sequence from studies[0]['processSequence']
        # The exported JSON has processSequence inside the studies array, not at top level
        process_sequence_data = {}

        # First, check if process_sequence exists at top level (for backward compatibility)
        if "process_sequence" in study_data:
            process_sequence_data = study_data["process_sequence"]
        # Check if processSequence is directly in study_data (when main_window already extracted
        # studies[0])
        elif "processSequence" in study_data:
            isa_process_sequence = study_data["processSequence"]
            process_sequence_data = {"processes": isa_process_sequence}
        # Otherwise, look for processSequence in studies[0] (ISA-JSON format)
        elif (
            "studies" in study_data
            and study_data["studies"]
            and "processSequence" in study_data["studies"][0]
        ):
            # Convert camelCase to snake_case for internal use
            isa_process_sequence = list(study_data["studies"][0]["processSequence"])

            # Build a name-based index of study-level processes for deduplication
            study_by_name = {}
            for p in isa_process_sequence:
                pname = p.get("name", "")
                if pname:
                    study_by_name[pname] = p

            # Collect assay-level processes, merging with study-level to
            # avoid duplicates.  When the same process exists at both levels
            # (matching by *name*), keep the version with more information
            # (more parameterValues / inputs / outputs / performer).
            for assay in study_data["studies"][0].get("assays", []):
                assay_name = (
                    assay.get("@id", "").split("#")[-1]
                    if "#" in assay.get("@id", "")
                    else assay.get("name", "assay")
                )
                for assay_proc in assay.get("processSequence", []):
                    if "assayContext" not in assay_proc:
                        assay_proc["assayContext"] = assay_name

                    proc_name = assay_proc.get("name", "")
                    if proc_name and proc_name in study_by_name:
                        # Duplicate: pick the richer version
                        existing = study_by_name[proc_name]
                        if self._process_info_count(assay_proc) > self._process_info_count(
                            existing
                        ):
                            idx = isa_process_sequence.index(existing)
                            isa_process_sequence[idx] = assay_proc
                            study_by_name[proc_name] = assay_proc
                        else:
                            # Existing study-level process is richer or equal;
                            # ensure it carries the assayContext tag
                            if "assayContext" not in existing:
                                existing["assayContext"] = assay_name
                    else:
                        # Assay-only process – add to the merged list
                        isa_process_sequence.append(assay_proc)
                        if proc_name:
                            study_by_name[proc_name] = assay_proc

            process_sequence_data = {"processes": isa_process_sequence}

        # Restore preserved data (status and material names) from ISA-JSON format
        # Note: _inputNames and _outputNames are no longer stored in ISA-JSON for compliance
        # The GUI now handles both string (material ID) and dict formats for inputs/outputs
        for process in process_sequence_data.get("processes", []):
            # Convert @id to id for internal consistency
            if "@id" in process and "id" not in process:
                process["id"] = process["@id"]

            # Restore status from comments array if available
            comments = process.get("comments", [])
            for comment in comments:
                if comment.get("name") == "status":
                    process["status"] = comment.get("value", "")

            # Extract protocol_ref from executesProtocol for protocol lookup
            # ISA-JSON stores protocol reference as URL like:
            # https://example.org/investigations/inv_1#prot_bacterial_culture
            # We need to extract the protocol name and match it to available protocol templates
            executes_protocol = process.get("executesProtocol", "")
            if executes_protocol:
                # Handle both string URL and dictionary format
                if isinstance(executes_protocol, dict):
                    # Dictionary format: extract @id or name
                    protocol_id = executes_protocol.get("@id", "")
                    protocol_name_from_dict = executes_protocol.get("name", "")
                    if "#prot_" in protocol_id:
                        protocol_id_part = protocol_id.split("#prot_")[-1]
                        # Try to match by name first
                        for proto_name in self.protocols.keys():
                            if proto_name.lower() == protocol_name_from_dict.lower():
                                process["protocol_ref"] = proto_name
                                break
                        else:
                            # Try to match by ID part
                            for proto_name in self.protocols.keys():
                                if proto_name.lower().replace(" ", "_") == protocol_id_part.lower():
                                    process["protocol_ref"] = proto_name
                                    break
                            else:
                                # No match found, use name from dict
                                process["protocol_ref"] = protocol_name_from_dict
                    else:
                        # No #prot_ in @id, use name from dict
                        process["protocol_ref"] = protocol_name_from_dict
                elif "#prot_" in executes_protocol:
                    protocol_id = executes_protocol.split("#prot_")[-1]
                    # Convert underscores to spaces for initial matching
                    protocol_name_from_url = protocol_id.replace("_", " ")
                    # Try to find matching protocol by name (case-insensitive)
                    for proto_name in self.protocols.keys():
                        if proto_name.lower().replace(" ", "_") == protocol_id.lower():
                            process["protocol_ref"] = proto_name
                            break
                    else:
                        # If no match found, try to use the extracted name as-is
                        process["protocol_ref"] = protocol_name_from_url
                else:
                    # URL doesn't have expected format, use as-is
                    process["protocol_ref"] = executes_protocol
                    logging.info(
                        f"[DEBUG] _load_process_sequence: Unexpected URL format, using '{executes_protocol}'"  # noqa: E501
                    )
            else:
                # No executesProtocol, try existing protocol_ref
                process["protocol_ref"] = process.get("protocol_ref", "")

            # Convert ISA-JSON parameterValues to internal parameters format
            # ISA-JSON format: category: {"@id": "#parameter/param_name"}, value: string/number/dict
            # Internal format: parameters[].name, parameters[].value
            if "parameterValues" in process and "parameters" not in process:
                parameters = []
                for pv in process["parameterValues"]:
                    category = pv.get("category", {})
                    if isinstance(category, dict) and "@id" in category:
                        param_id = category.get("@id", "")
                        param_name = param_id.replace("#parameter/", "").replace("_", " ")
                    else:
                        param_name = ""

                    value_data = pv.get("value", {})

                    # Handle various value formats: string, dict, or primitive (int, float, bool,
                    # None)
                    if isinstance(value_data, str):
                        value = value_data
                        unit = None
                    elif isinstance(value_data, dict):
                        # Check for nested value structure
                        if "value" in value_data:
                            value = value_data.get("value", "")
                            unit = value_data.get("unit", None)
                        else:
                            # Dict might be an ontology annotation with annotationValue
                            value = value_data.get("annotationValue", "")
                            unit = None
                    else:
                        # value_data is a primitive (int, float, bool, None) - use directly
                        value = value_data if value_data is not None else ""
                        unit = None

                    # Only add if we have a valid param name
                    if param_name:
                        parameters.append({"name": param_name, "value": value, "unit": unit})
                process["parameters"] = parameters
            elif "parameters" in process:
                pass

            # Note: _inputNames and _outputNames are no longer restored from ISA-JSON
            # The _load_materials() method handles both string and dict formats
            pass

        # Update study_data with the extracted process_sequence for the process manager
        study_data["process_sequence"] = process_sequence_data

        # Initialize material manager with investigation and study IDs for proper ID generation
        dm = self.main_window.get_directory_manager()
        self.material_manager = MaterialManager(
            study_data,
            dm,
            investigation_id=self.main_window.current_investigation,
            study_id=self.main_window.current_study,
        )

        # Initialize process manager with material manager and protocols
        self.process_manager = ProcessSequenceManager(
            study_data, self.material_manager, list(self.protocols.values())
        )

        # Clear tree and build from process sequence
        self.tree.clear()
        self.process_tree_items = {}

        processes = self.process_manager.get_processes()

        if processes:
            # Create flat list of processes
            for process in processes:
                item = QTreeWidgetItem(self.tree)
                item.setText(0, process.get("name", "Unknown"))
                status = process.get("status", "Pending")
                item.setText(1, status)

                # Show material count
                inputs_count = len(process.get("inputs", []))
                outputs_count = len(process.get("outputs", []))
                item.setText(2, f"{inputs_count}→{outputs_count}")

                item.setData(0, Qt.ItemDataRole.UserRole, {"type": "process", "data": process})

                self.process_tree_items[self.process_manager._get_process_id(process)] = item

    @staticmethod
    def _process_info_count(process: dict) -> int:
        """Return a heuristic count of information richness in *process*.

        Used during deduplication to decide which copy of a process to keep
        when the same process name appears at both study-level and
        assay-level ``processSequence``.  The version with the higher score
        wins.
        """
        count = 0
        count += len(process.get("parameterValues", []))
        count += len(process.get("parameters", []))
        count += len(process.get("inputs", []))
        count += len(process.get("outputs", []))
        if process.get("performer"):
            count += 1
        if process.get("date"):
            count += 1
        if process.get("comments"):
            count += len(process["comments"])
        return count

    def _load_sample_protocols(self):
        """Show empty state when no profile/templates are loaded."""
        empty_item = QTreeWidgetItem(self.tree)
        empty_item.setText(
            0, "No profile loaded. Please configure a profile to see available processes."
        )
        empty_item.setText(1, "")
        empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)

    def _get_protocol_section(self, protocol_name: str, protocol_data: dict | None = None) -> str:
        """Determine which section a protocol belongs to.

        If the protocol data contains a ``section`` key, that value is used.
        Otherwise, falls back to a generic ``"Protocols"`` category so that
        no profile-specific keywords leak into the core codebase.
        """
        if protocol_data and isinstance(protocol_data.get("section"), str):
            return str(protocol_data["section"])
        return "Protocols"

    def _on_process_selected(self):
        """Handle process selection change."""
        selected = self.tree.selectedItems()

        if not selected:
            self._clear_process_details()
            self.current_process = None
            return

        item = selected[0]
        item_data = item.data(0, Qt.ItemDataRole.UserRole)

        if item_data.get("type") == "template":
            # Template selected - prompt to add as process
            self._on_add_process_from_template(item_data["data"])
            return

        # Process selected
        process = item_data["data"]
        self.current_process = process
        self._load_process_details(process)

    def _load_process_details(self, process: dict):
        """Load process details into the right panel."""
        # Update info
        self.process_name_label.setText(process.get("name", "Unknown"))

        protocol_name = process.get("protocol_ref", "")
        protocol_data = self.protocols.get(protocol_name, {})

        self.protocol_label.setText(protocol_data.get("description", ""))

        # Load parameters with default values
        self._load_parameters(process, protocol_data)

        # Load materials
        self._load_materials(process)

        # Load files
        self._load_files(process, protocol_data)

    def _load_parameters(self, process: dict, protocol_data: dict):
        """Load parameters into the form with default values.

        Handles multiple parameter value sources in order of priority:
        1. Process parameter values (user-set values)
        2. Protocol template defaultValue (template-defined defaults)
        3. Protocol parameters from ISA-JSON (parameterName.annotationValue)
        4. Empty string (no default available)
        """
        self._clear_parameters()

        # Get parameters from process or protocol
        process_params = process.get("parameters", [])
        protocol_params = protocol_data.get("parameters", [])

        # Build a set of parameter names already handled via protocol template
        handled_names: set = set()

        # Merge: use process values if set, otherwise use protocol defaults
        for param_def in protocol_params:
            # Handle both template format ("name") and ISA-JSON format ("parameterName")
            param_name = param_def.get("name", "")
            if not param_name:
                pn = param_def.get("parameterName", {})
                if isinstance(pn, dict):
                    param_name = pn.get("annotationValue", "")
                elif isinstance(pn, str):
                    param_name = pn

            if not param_name:
                continue
            handled_names.add(param_name.lower())

            default_value = param_def.get("defaultValue", "")
            unit = param_def.get("unit", {})
            unit_name = unit.get("annotationValue", "") if unit else ""

            # Find process parameter value if exists
            process_param = next(
                (p for p in process_params if p.get("name", "").lower() == param_name.lower()), None
            )

            # Determine the value to display:
            # 1. If process has a value set, use it
            # 2. Otherwise, use the default from template (may be empty string)
            if process_param:
                value = process_param.get("value", default_value)
            else:
                value = default_value

            self._add_parameter_entry(
                param_name, value, unit_name, param_def.get("description", ""), unit, default_value
            )

        # Also display process parameters that are NOT in the protocol template
        # (e.g., instrument values from ISA-JSON assay processes)
        for process_param in process_params:
            pname = process_param.get("name", "")
            if pname.lower() not in handled_names:
                value = process_param.get("value", "")
                unit = process_param.get("unit", None)
                unit_name = ""
                if isinstance(unit, dict):
                    unit_name = unit.get("annotationValue", "")
                self._add_parameter_entry(pname, value, unit_name, "", unit, "")

    def _add_parameter_entry(
        self, param_name: str, value, unit_name: str, description: str, unit, default_value: str
    ):
        """Add a single parameter entry to the form."""
        entry = QLineEdit()

        if description:
            entry.setPlaceholderText(description)
        else:
            entry.setPlaceholderText("Enter value...")

        if value is not None and value != "":
            entry.setText(str(value))

        label_text = f"{param_name}:"
        if unit_name:
            label_text += f" [{unit_name}]"

        self.params_layout.addRow(label_text, entry)
        self.param_entries[param_name] = {
            "entry": entry,
            "unit": unit,
            "default": default_value,
            "description": description,
        }

    def _load_materials(self, process: dict):
        """Load materials into the lists."""
        self.inputs_list.clear()
        self.outputs_list.clear()

        # Load inputs
        for input_item in process.get("inputs", []):
            if (
                isinstance(input_item, dict)
                and "@id" in input_item
                and "material_id" not in input_item
            ):
                # ISA-JSON format: dict with @id only
                material_id = input_item.get("@id", "")
                material = self._get_material_by_id(material_id)
                material_name = material.get("name", "Unknown") if material else "Unknown"
                is_locked = False
                material_type = material.get("@type", "") if material else ""
                input_item_dict = {
                    "material_id": material_id,
                    "name": material_name,
                    "materialType": material_type,
                    "locked": is_locked,
                }
            else:
                # Internal format: dict with material_id, name, materialType, locked
                input_item_dict = input_item
                material_id = input_item.get("material_id", "")
                material_name = input_item.get("name", "Unknown")
                material_type = input_item.get("materialType", "")
                is_locked = input_item.get("locked", False)

            # Add lock icon if manually assigned
            display_name = f"🔒 {material_name}" if is_locked else material_name

            list_item = QListWidgetItem(display_name)
            list_item.setData(Qt.ItemDataRole.UserRole, input_item_dict)
            self.inputs_list.addItem(list_item)

        # Load outputs
        for output_item in process.get("outputs", []):
            if (
                isinstance(output_item, dict)
                and "@id" in output_item
                and "material_id" not in output_item
            ):
                # ISA-JSON format: dict with @id only
                material_id = output_item.get("@id", "")
                material = self._get_material_by_id(material_id)
                material_name = material.get("name", "Unknown") if material else "Unknown"
                is_locked = False
                material_type = material.get("@type", "") if material else ""
                output_item_dict = {
                    "material_id": material_id,
                    "name": material_name,
                    "materialType": material_type,
                    "locked": is_locked,
                }
            else:
                # Internal format: dict with material_id, name, materialType, locked
                output_item_dict = output_item
                material_id = output_item.get("material_id", "")
                material_name = output_item.get("name", "Unknown")
                material_type = output_item.get("materialType", "")
                is_locked = output_item.get("locked", False)

            # Add lock icon if manually assigned
            display_name = f"🔒 {material_name}" if is_locked else material_name

            list_item = QListWidgetItem(display_name)
            list_item.setData(Qt.ItemDataRole.UserRole, output_item_dict)
            self.outputs_list.addItem(list_item)

    def _get_material_by_id(self, material_id: str) -> dict:
        """
        Get material by ID from the study data.

        Also resolves data file references (``#datafile_*``) by looking up
        the name from the assay's ``dataFiles`` list.

        Args:
            material_id: The material ID to look up

        Returns:
            Material dictionary or empty dict if not found
        """
        if not self.process_manager:
            return {}

        # Try to get material from process_manager
        material = self.process_manager.get_material_by_id(material_id)
        if material:
            return material

        # Fallback: search in materials directly
        for material in self.process_manager.get_all_materials():
            material_at_id = material.get("@id", "")
            if material_at_id == material_id:
                return material

        # Fallback: resolve data file references from assay dataFiles
        study_data = self.main_window.get_study_data()
        if study_data and "studies" in study_data and study_data["studies"]:
            for assay in study_data["studies"][0].get("assays", []):
                for df in assay.get("dataFiles", []):
                    if df.get("@id", "") == material_id:
                        return {
                            "name": df.get("name", "data file"),
                            "@id": material_id,
                            "@type": "DataFile",
                        }
        return {}

    def _load_files(self, process: dict, protocol_data: dict):
        """Load file attachments into the widget."""
        # Get expected attachments from protocol
        expected_attachments = protocol_data.get("expectedAttachments", [])

        # Get attached files from process
        attached_files = process.get("files", [])

        # Update the file attachment widget
        # Re-create widget with new data
        self.file_attachment_widget.expected_attachments = expected_attachments
        self.file_attachment_widget.attached_files = attached_files
        self.file_attachment_widget.setup_ui()

    def _clear_parameters(self):
        """Clear all parameter entries."""
        while self.params_layout.count() > 0:
            self.params_layout.removeRow(0)
        self.param_entries = {}

    def _clear_process_details(self):
        """Clear process details panel."""
        self.process_name_label.setText("No process selected")
        self.protocol_label.setText("-")
        self._clear_parameters()
        self.inputs_list.clear()
        self.outputs_list.clear()
        self.validation_label.setText("")

        # Clear file attachment widget
        self.file_attachment_widget.expected_attachments = []
        self.file_attachment_widget.attached_files = []
        self.file_attachment_widget.setup_ui()

    def _on_add_process(self):
        """Handle add process button click."""
        if not self.process_manager:
            QMessageBox.information(
                self, "No Study Selected", "Please select a study first from the Studies page."
            )
            return

        # Show menu to select protocol template
        menu = QMenu(self)
        menu.setTitle("Select Protocol Template")

        for protocol_name, protocol_data in self.protocols.items():
            action = menu.addAction(protocol_name)
            action.triggered.connect(
                lambda checked, data=protocol_data: self._on_add_process_from_template(data)
            )

        menu.exec(self.mapToGlobal(self.pos()))

    def _on_add_process_from_template(self, protocol_data: dict):
        """Add a process from a template with auto-linked materials."""
        if not self.process_manager:
            QMessageBox.information(
                self, "No Study Selected", "Please select a study first from the Studies page."
            )
            return

        # Get base process name from protocol
        base_process_name = protocol_data.get("name", "New Process")

        # Get counter for this process name
        process_counter = self.process_manager._get_next_process_counter(base_process_name)

        # Create unique process name
        process_name = f"{base_process_name} #{process_counter}"

        # Create new process from template
        process_id = f"p_{len(self.process_manager.get_processes())}"
        process = {
            "id": process_id,
            "name": process_name,  # Use unique process name
            "protocol_ref": protocol_data.get("name", ""),
            "order": len(self.process_manager.get_processes()),
            "inputs": [],
            "outputs": [],
            "parameters": [],
            "status": "Pending",
        }

        # Auto-link materials (will use the same counter)
        process = self.process_manager.auto_link_materials_for_process(
            process, len(self.process_manager.get_processes())
        )

        # Add to process sequence
        self.process_manager.add_process(process)
        self._refresh_process_tree()

        # Select the newly added process to show its materials
        if self.process_manager._get_process_id(process) in self.process_tree_items:
            item = self.process_tree_items[self.process_manager._get_process_id(process)]
            self.tree.setCurrentItem(item)
            self._on_process_selected()

        self.main_window.status_bar.show_message(
            f"Added process: {process['name']} with auto-linked materials"
        )

    def _on_remove_process(self):
        """Handle remove process button click."""
        if not self.current_process:
            QMessageBox.information(self, "No Selection", "Please select a process to remove.")
            return

        process_id = self.process_manager._get_process_id(self.current_process)
        process_name = self.current_process.get("name", "")

        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Are you sure you want to remove process '{process_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.process_manager.remove_process(process_id)
            self._refresh_process_tree()
            self._clear_process_details()
            self.current_process = None

            self.main_window.status_bar.show_message(f"Removed process: {process_name}")

    def _on_process_moved(self, old_index: int, new_index: int):
        """Handle process move/reorder with material link updates."""
        if not self.process_manager:
            return

        processes = self.process_manager.get_processes()
        if 0 <= old_index < len(processes) and 0 <= new_index < len(processes):
            process = processes[old_index]
            process_id = self.process_manager._get_process_id(process)

            # Reorder process
            self.process_manager.reorder_process(process_id, new_index)

            # Update material links (preserving locked materials)
            self.process_manager.update_material_links_after_reorder(old_index, new_index)

            self._refresh_process_tree()

            self.main_window.status_bar.show_message("Moved process and updated material links")

    def _on_select_inputs(self):
        """Handle select inputs button click."""
        if not self.current_process:
            return

        # Get available materials
        materials = self.process_manager.get_all_materials()

        # Open material selection dialog
        dialog = MaterialSelectionDialog(
            self, materials=materials, title="Select Input Materials", multi_select=True
        )

        # Pre-select current inputs
        inputs = self.current_process.get("inputs", [])
        current_input_ids = []
        for i in inputs:
            if isinstance(i, str):
                # ISA-JSON format: i is a material ID string (URI)
                current_input_ids.append(i)
            elif isinstance(i, dict):
                # Dict format: extract material_id
                current_input_ids.append(i.get("material_id", ""))

        dialog.set_preselected_materials(current_input_ids)

        if dialog.exec():
            selected_materials = dialog.get_selected_materials()

            # Update process inputs and mark as locked
            self.current_process["inputs"] = [
                {
                    "material_id": m.get("@id", ""),
                    "name": m.get("name", ""),
                    "materialType": m.get("materialType", ""),
                    "locked": True,  # Mark as manually assigned
                }
                for m in selected_materials
            ]

            self._load_materials(self.current_process)
            self.main_window.status_bar.show_message(
                f"Updated inputs for {self.current_process['name']} (manual assignment)"
            )

    def _on_select_outputs(self):
        """Handle select outputs button click."""
        if not self.current_process:
            return

        # Get available materials (samples for outputs)
        materials = self.process_manager.get_materials_by_type("sample")

        # Open material selection dialog
        dialog = MaterialSelectionDialog(
            self, materials=materials, title="Select Output Materials", multi_select=True
        )

        # Pre-select current outputs
        outputs = self.current_process.get("outputs", [])
        current_output_ids = []
        for o in outputs:
            if isinstance(o, str):
                # ISA-JSON format: o is a material ID string (URI)
                current_output_ids.append(o)
            elif isinstance(o, dict):
                # Dict format: extract material_id
                current_output_ids.append(o.get("material_id", ""))

        dialog.set_preselected_materials(current_output_ids)

        if dialog.exec():
            selected_materials = dialog.get_selected_materials()

            # Update process outputs and mark as locked
            self.current_process["outputs"] = [
                {
                    "material_id": m.get("@id", ""),
                    "name": m.get("name", ""),
                    "materialType": m.get("materialType", ""),
                    "locked": True,  # Mark as manually assigned
                }
                for m in selected_materials
            ]

            self._load_materials(self.current_process)
            self.main_window.status_bar.show_message(
                f"Updated outputs for {self.current_process['name']} (manual assignment)"
            )

    def _on_save(self):
        """Handle save button click."""
        if not self.current_process:
            QMessageBox.information(self, "No Selection", "Please select a process to save.")
            return

        if not self.process_manager:
            QMessageBox.information(
                self, "No Study Selected", "Please select a study first from the Studies page."
            )
            return

        # Collect parameter values
        parameters = []
        for param_name, param_data in self.param_entries.items():
            entry = param_data["entry"]
            value = entry.text().strip()

            if value or value == param_data["default"]:
                param_obj = {"name": param_name, "value": value, "unit": param_data["unit"]}
                parameters.append(param_obj)

        # Update process - include inputs, outputs, and files
        process_id = self.process_manager._get_process_id(self.current_process)
        self.process_manager.update_process(
            process_id,
            {
                "parameters": parameters,
                "status": "Completed",
                "inputs": self.current_process.get("inputs", []),
                "outputs": self.current_process.get("outputs", []),
                "files": self.file_attachment_widget.attached_files,
            },
        )

        # Update tree status
        if process_id in self.process_tree_items:
            self.process_tree_items[process_id].setText(1, "Completed")

        # Save study JSON with ISA-JSON export
        self._save_study_with_isa_export()

        self.main_window.status_bar.show_message(f"Saved process '{self.current_process['name']}'!")

    def _save_study_with_isa_export(self):
        """
        Save study data as complete ISA-JSON format.
        """
        if not self.process_manager:
            return

        study_data = self.main_window.get_study_data() or {}
        if not study_data:
            return

        # Sync process manager's process_sequence to study_data before export
        # The process manager maintains its own state, but study_data needs to be updated
        # for the ISA-JSON exporter to include the processes
        study_data["process_sequence"] = self.process_manager.process_sequence

        # Export to complete ISA-JSON format
        investigation_id = self.main_window.current_investigation or "inv_1"
        study_id = self.main_window.current_study or "study_1"

        exporter = ISAJsonExporter(study_data, investigation_id, study_id)
        isa_json = exporter.export_complete_isa_json()

        # Save to file
        dm = self.main_window.get_directory_manager()
        study_json_path = dm.get_study_json_path(investigation_id, study_id)

        try:
            with open(study_json_path, "w", encoding="utf-8") as f:
                json.dump(isa_json, f, indent=2)

            # Update main window study data with the simple structure (not complete ISA-JSON)
            self.main_window.study_data = study_data
            self.main_window.status_bar.show_message("Saved as complete ISA-JSON!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save study:\n{str(e)}")
            raise

    def _on_validate_handover(self):
        """Validate material handover between processes."""
        if not self.process_manager:
            QMessageBox.information(
                self, "No Study Selected", "Please select a study first from the Studies page."
            )
            return

        # Get materials and processes
        materials = self.process_manager.get_all_materials()
        processes = self.process_manager.get_processes()

        # Validate
        validator = MaterialHandoverValidator(materials, processes)
        result = validator.validate()

        # Display results
        if result["valid"]:
            self.validation_label.setText("✓ Material handover is valid!")
            self.validation_label.setStyleSheet("color: green; padding: 5px;")
            QMessageBox.information(self, "Validation Successful", result["summary"])
        else:
            # Show warnings and errors
            messages = []
            for error in result["errors"]:
                messages.append(f"ERROR: {error['message']}")
            for warning in result["warnings"]:
                messages.append(f"WARNING: {warning['message']}")

            self.validation_label.setText(result["summary"])
            self.validation_label.setStyleSheet("color: orange; padding: 5px;")

            QMessageBox.warning(self, "Validation Results", "\n".join(messages))

    def _refresh_process_tree(self):
        """Refresh the process tree to reflect current state."""
        self.tree.clear()
        self.process_tree_items = {}

        processes = self.process_manager.get_processes()

        for process in processes:
            item = QTreeWidgetItem(self.tree)
            item.setText(0, process.get("name", "Unknown"))
            status = process.get("status", "Pending")
            item.setText(1, status)

            # Show material count
            inputs_count = len(process.get("inputs", []))
            outputs_count = len(process.get("outputs", []))
            item.setText(2, f"{inputs_count}→{outputs_count}")

            item.setData(0, Qt.ItemDataRole.UserRole, {"type": "process", "data": process})

            self.process_tree_items[process.get("id", "")] = item

    def on_enter(self):
        """Called when the page is shown."""
        self._load_protocols()

    def on_exit(self):
        """Called when the page is hidden."""
        pass

    def set_investigation(self, investigation_id: str):
        """Set the current investigation."""
        self._load_protocols()

    def set_study(self, study_id: str):
        """Set the current study."""
        self._load_process_sequence()

        # If process manager was initialized, ensure it has the latest data
        if self.process_manager:
            # Refresh process tree to reflect any changes
            self._refresh_process_tree()

    def resizeEvent(self, event: Optional[QResizeEvent]):
        """Handle window resize to adjust parameters scroll area height."""
        if event is None:
            return
        super().resizeEvent(event)

        # Get the window height
        window_height = self.height()

        # Calculate a reasonable height for the parameters scroll area
        # Use 45% of window height, with minimum of 250 and maximum of 600
        params_height = int(window_height * 0.45)
        params_height = max(250, min(params_height, 600))

        # Set the minimum height for the parameters scroll area
        self.params_scroll.setMinimumHeight(params_height)
