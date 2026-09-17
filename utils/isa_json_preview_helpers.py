"""
ISA-JSON Preview Helpers for the ISA-JSON Data Steward GUI.

Provides utility functions to resolve ISA-JSON @id references to human-readable
names and to extract formatted preview data for materials, assays, and files.
"""

import html
from typing import Optional


class ISAJsonPreviewHelper:
    """
    Helper class for resolving ISA-JSON references and extracting preview data.

    Given a study_data dict (complete ISA-JSON structure or simple study structure),
    provides methods to:
    - Resolve @id references to names
    - Extract formatted details for materials, assays, data files, and processes
    - Build lookup indexes for fast cross-reference resolution
    """

    def __init__(self, study_data: dict):
        """
        Initialize the helper with study data.

        Args:
            study_data: The complete ISA-JSON structure (with 'studies' key)
                        or simple study structure
        """
        self.study_data = study_data
        self._study: Optional[dict] = None
        self._materials_by_id: dict = {}
        self._factors_by_id: dict = {}
        self._characteristic_categories_by_id: dict = {}
        self._protocols_by_id: dict = {}
        self._datafiles_by_id: dict = {}
        self._assays_by_name: dict = {}
        self._processes_by_id: dict = {}
        self._build_indexes()

    @property
    def study(self) -> dict:
        """Get the study dict (handles both ISA-JSON and simple format)."""
        if self._study is not None:
            return self._study
        if "studies" in self.study_data and isinstance(self.study_data["studies"], list):
            if len(self.study_data["studies"]) > 0:
                self._study = self.study_data["studies"][0]
                return self._study
        self._study = self.study_data
        return self._study

    def _build_indexes(self):
        """Build lookup indexes for fast cross-reference resolution."""
        study = self.study

        # Index materials (sources, samples, otherMaterials)
        materials = study.get("materials", {})
        for source in materials.get("sources", []):
            mid = source.get("@id", "")
            if mid:
                self._materials_by_id[mid] = source
        for sample in materials.get("samples", []):
            mid = sample.get("@id", "")
            if mid:
                self._materials_by_id[mid] = sample
        for other in materials.get("otherMaterials", []):
            mid = other.get("@id", "")
            if mid:
                self._materials_by_id[mid] = other

        # Also index materials from within assays
        for assay in study.get("assays", []):
            assay_materials = assay.get("materials", {})
            for sample in assay_materials.get("samples", []):
                mid = sample.get("@id", "")
                if mid and mid not in self._materials_by_id:
                    self._materials_by_id[mid] = sample

        # Index factors
        for factor in study.get("factors", []):
            fid = factor.get("@id", "")
            if fid:
                self._factors_by_id[fid] = factor

        # Index characteristic categories
        for cat in study.get("characteristicCategories", []):
            cid = cat.get("@id", "")
            if cid:
                self._characteristic_categories_by_id[cid] = cat

        # Index protocols
        for protocol in study.get("protocols", []):
            pid = protocol.get("@id", "")
            if pid:
                self._protocols_by_id[pid] = protocol

        # Index data files from all assays
        for assay in study.get("assays", []):
            for df in assay.get("dataFiles", []):
                dfid = df.get("@id", "")
                if dfid:
                    self._datafiles_by_id[dfid] = df

        # Index assays
        for assay in study.get("assays", []):
            assay_id = assay.get("@id", "")
            if assay_id:
                self._assays_by_name[assay_id] = assay

        # Index processes from study-level processSequence
        for process in study.get("processSequence", []):
            pid = process.get("@id", "")
            if pid:
                self._processes_by_id[pid] = process

        # Index processes from assay-level processSequence
        for assay in study.get("assays", []):
            for process in assay.get("processSequence", []):
                pid = process.get("@id", "")
                if pid:
                    self._processes_by_id[pid] = process

    # --- Reference Resolution ---

    def resolve_material_name(self, material_id: str) -> str:
        """
        Resolve a material @id to its human-readable name.

        Args:
            material_id: The material @id (full URI or fragment)

        Returns:
            Material name or the original ID if not found
        """
        material = self._materials_by_id.get(material_id, {})
        return str(material.get("name", material_id))

    def resolve_factor_name(self, factor_id: str) -> str:
        """
        Resolve a factor @id to its human-readable factor name.

        Args:
            factor_id: The factor @id (e.g., "#factor/treatment")

        Returns:
            Factor name or the original ID if not found
        """
        # Try direct match
        factor = self._factors_by_id.get(factor_id, {})
        if factor:
            return str(factor.get("factorName", factor_id))
        # Try matching with # prefix stripped
        for fid, factor in self._factors_by_id.items():
            if fid.endswith(factor_id) or factor_id.endswith(fid):
                return str(factor.get("factorName", factor_id))
        return factor_id

    def resolve_characteristic_category_name(self, category_id: str) -> str:
        """
        Resolve a characteristic category @id to its type name.

        Args:
            category_id: The category @id (e.g., "#characteristic_category/organism")

        Returns:
            Category type name or the original ID if not found
        """
        cat = self._characteristic_categories_by_id.get(category_id, {})
        if cat:
            char_type = cat.get("characteristicType", {})
            return str(char_type.get("annotationValue", category_id))
        # Try matching with # prefix
        for cid, cat in self._characteristic_categories_by_id.items():
            if cid.endswith(category_id) or category_id.endswith(cid):
                char_type = cat.get("characteristicType", {})
                return str(char_type.get("annotationValue", category_id))
        return category_id

    def resolve_protocol_name(self, protocol_ref) -> str:
        """
        Resolve a protocol reference to its human-readable name.

        Args:
            protocol_ref: Either a string protocol @id or a dict with @id and name

        Returns:
            Protocol name
        """
        if isinstance(protocol_ref, dict):
            return str(protocol_ref.get("name", protocol_ref.get("@id", "")))
        protocol = self._protocols_by_id.get(protocol_ref, {})
        return str(protocol.get("name", protocol_ref))

    def resolve_datafile_name(self, datafile_id: str) -> str:
        """
        Resolve a data file @id to its name.

        Args:
            datafile_id: The data file @id

        Returns:
            File name or the original ID if not found
        """
        df = self._datafiles_by_id.get(datafile_id, {})
        return str(df.get("name", datafile_id))

    def resolve_assay_for_datafile(self, datafile_name: str) -> Optional[dict]:
        """
        Find which assay a data file belongs to (by name).

        Args:
            datafile_name: The data file name

        Returns:
            Assay dict or None if not found
        """
        for assay in self.study.get("assays", []):
            for df in assay.get("dataFiles", []):
                if df.get("name", "") == datafile_name:
                    return assay  # type: ignore[no-any-return]
        return None

    def get_comment_value(self, comments: list, comment_name: str) -> str:
        """
        Get a comment value from a list of ISA-JSON comments.

        Args:
            comments: List of comment dicts
            comment_name: The comment name to look up

        Returns:
            Comment value or empty string
        """
        for comment in comments:
            if comment.get("name", "") == comment_name:
                return str(comment.get("value", ""))
        return ""

    # --- Material Preview ---

    def get_material_preview_html(self, material: dict) -> str:
        """
        Generate HTML preview for a material (sample, source, or other material).

        Args:
            material: Material dict from ISA-JSON

        Returns:
            Formatted HTML string
        """
        lines = []
        name = material.get("name", "Unknown")
        mat_type = material.get("materialType", material.get("type", "Unknown"))
        mat_id = material.get("@id", "")

        lines.append('<div style="margin-bottom: 12px;">')
        lines.append(f'<b style="font-size: 14px;">{self._escape(name)}</b><br>')
        lines.append(f'<span style="color: #666;">Type:</span> {self._escape(mat_type)}<br>')
        if mat_id:
            lines.append(
                f'<span style="color: #666;">ID:</span> <code style="font-size: 11px;">{self._escape(mat_id)}</code>'  # noqa: E501
            )
        lines.append("</div>")

        # Characteristics
        characteristics = material.get("characteristics", [])
        if characteristics:
            lines.append("<b>Characteristics:</b><br>")
            lines.append('<table style="margin-left: 8px; border-collapse: collapse;">')
            for char in characteristics:
                cat_ref = char.get("category", {})
                cat_id = cat_ref.get("@id", "") if isinstance(cat_ref, dict) else str(cat_ref)
                cat_name = self.resolve_characteristic_category_name(cat_id)
                value_obj = char.get("value", {})
                if isinstance(value_obj, dict):
                    value = value_obj.get("annotationValue", str(value_obj))
                    term_source = value_obj.get("termSource", "")
                    term_accession = value_obj.get("termAccession", "")
                    value_str = self._escape(value)
                    if term_source:
                        value_str += f' <span style="color: #999; font-size: 10px;">({self._escape(term_source)})</span>'  # noqa: E501
                    if term_accession:
                        value_str += f'<br><span style="color: #aaa; font-size: 9px;">{self._escape(term_accession)}</span>'  # noqa: E501
                else:
                    value_str = self._escape(str(value_obj))
                lines.append(
                    f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">{self._escape(cat_name)}:</td>'  # noqa: E501
                )
                lines.append(f'<td style="padding: 2px 0;">{value_str}</td></tr>')
            lines.append("</table><br>")

        # Factor Values
        factor_values = material.get("factorValues", [])
        if factor_values:
            lines.append("<b>Factor Values:</b><br>")
            lines.append('<table style="margin-left: 8px; border-collapse: collapse;">')
            for fv in factor_values:
                cat_ref = fv.get("category", {})
                cat_id = cat_ref.get("@id", "") if isinstance(cat_ref, dict) else str(cat_ref)
                factor_name = self.resolve_factor_name(cat_id)
                value_obj = fv.get("value", {})
                if isinstance(value_obj, dict):
                    value = value_obj.get("annotationValue", str(value_obj))
                else:
                    value = str(value_obj)
                lines.append(
                    f'<tr><td style="padding: 2px 8px 2px 0; color: #666;">{self._escape(factor_name)}:</td>'  # noqa: E501
                )
                lines.append(
                    f'<td style="padding: 2px 0; font-weight: bold;">{self._escape(value)}</td></tr>'  # noqa: E501
                )
            lines.append("</table><br>")

        # Derives From
        derives_from = material.get("derivesFrom", [])
        if derives_from:
            lines.append("<b>Derives From:</b><br>")
            lines.append('<ul style="margin-top: 2px;">')
            for df_ref in derives_from:
                df_id = df_ref.get("@id", "") if isinstance(df_ref, dict) else str(df_ref)
                df_name = self.resolve_material_name(df_id)
                lines.append(f"<li>{self._escape(df_name)}</li>")
            lines.append("</ul>")

        # Linked Assays
        linked_assays = self._get_linked_assays_for_material(material.get("@id", ""))
        if linked_assays:
            lines.append("<b>Used in Assays:</b><br>")
            lines.append('<ul style="margin-top: 2px;">')
            for assay in linked_assays:
                assay_name = self._get_assay_display_name(assay)
                lines.append(f"<li>{self._escape(assay_name)}</li>")
            lines.append("</ul>")

        return "\n".join(lines)

    # --- Assay Preview ---

    def get_assay_preview_html(self, assay: dict) -> str:
        """
        Generate HTML preview for an assay.

        Args:
            assay: Assay dict from ISA-JSON

        Returns:
            Formatted HTML string
        """
        lines = []

        # Header
        assay_display_name = self._get_assay_display_name(assay)
        assay_id = assay.get("@id", "")
        lines.append('<div style="margin-bottom: 12px;">')
        lines.append(f'<b style="font-size: 14px;">{self._escape(assay_display_name)}</b><br>')
        if assay_id:
            lines.append(
                f'<span style="color: #666;">ID:</span> <code style="font-size: 11px;">{self._escape(assay_id)}</code>'  # noqa: E501
            )
        lines.append("</div>")

        # Measurement Type
        mt = assay.get("measurementType", {})
        if isinstance(mt, dict) and mt.get("annotationValue"):
            lines.append("<b>Measurement Type:</b><br>")
            lines.append('<table style="margin-left: 8px; border-collapse: collapse;">')
            lines.append('<tr><td style="padding: 2px 8px 2px 0; color: #666;">Value:</td>')
            lines.append(
                f'<td style="padding: 2px 0;"><b>{self._escape(mt.get("annotationValue", ""))}</b></td></tr>'  # noqa: E501
            )
            if mt.get("termSource"):
                lines.append('<tr><td style="padding: 2px 8px 2px 0; color: #666;">Source:</td>')
                lines.append(
                    f'<td style="padding: 2px 0;">{self._escape(mt.get("termSource", ""))}</td></tr>'  # noqa: E501
                )
            if mt.get("termAccession"):
                lines.append('<tr><td style="padding: 2px 8px 2px 0; color: #666;">Accession:</td>')
                lines.append(
                    f'<td style="padding: 2px 0; font-size: 10px;">{self._escape(mt.get("termAccession", ""))}</td></tr>'  # noqa: E501
                )
            lines.append("</table><br>")

        # Technology Type
        tt = assay.get("technologyType", {})
        if isinstance(tt, dict) and tt.get("annotationValue"):
            lines.append("<b>Technology Type:</b><br>")
            lines.append('<table style="margin-left: 8px; border-collapse: collapse;">')
            lines.append('<tr><td style="padding: 2px 8px 2px 0; color: #666;">Value:</td>')
            lines.append(
                f'<td style="padding: 2px 0;"><b>{self._escape(tt.get("annotationValue", ""))}</b></td></tr>'  # noqa: E501
            )
            if tt.get("termSource"):
                lines.append('<tr><td style="padding: 2px 8px 2px 0; color: #666;">Source:</td>')
                lines.append(
                    f'<td style="padding: 2px 0;">{self._escape(tt.get("termSource", ""))}</td></tr>'  # noqa: E501
                )
            if tt.get("termAccession"):
                lines.append('<tr><td style="padding: 2px 8px 2px 0; color: #666;">Accession:</td>')
                lines.append(
                    f'<td style="padding: 2px 0; font-size: 10px;">{self._escape(tt.get("termAccession", ""))}</td></tr>'  # noqa: E501
                )
            lines.append("</table><br>")

        # Original types from comments
        comments = assay.get("comments", [])
        orig_mt = self.get_comment_value(comments, "original measurement type")
        orig_tt = self.get_comment_value(comments, "original technology type")
        if orig_mt or orig_tt:
            lines.append("<b>Original Types:</b><br>")
            lines.append('<table style="margin-left: 8px; border-collapse: collapse;">')
            if orig_mt:
                lines.append(
                    '<tr><td style="padding: 2px 8px 2px 0; color: #666;">Measurement:</td>'
                )
                lines.append(f'<td style="padding: 2px 0;">{self._escape(orig_mt)}</td></tr>')
            if orig_tt:
                lines.append(
                    '<tr><td style="padding: 2px 8px 2px 0; color: #666;">Technology:</td>'
                )
                lines.append(f'<td style="padding: 2px 0;">{self._escape(orig_tt)}</td></tr>')
            lines.append("</table><br>")

        # Filename
        filename = assay.get("filename", "")
        if filename:
            lines.append(
                f'<b>Filename:</b> <code style="font-size: 11px;">{self._escape(filename)}</code><br><br>'  # noqa: E501
            )

        # Process Sequence Summary
        process_seq = assay.get("processSequence", [])
        if process_seq:
            lines.append(f"<b>Process Sequence ({len(process_seq)} steps):</b><br>")
            lines.append(
                '<table style="margin-left: 8px; border-collapse: collapse; width: 100%;">'
            )
            lines.append('<tr style="color: #666; font-size: 11px;">')
            lines.append('<td style="padding: 2px 8px 2px 0;"><b>Process</b></td>')
            lines.append('<td style="padding: 2px 8px;"><b>Date</b></td>')
            lines.append('<td style="padding: 2px 8px;"><b>Performer</b></td>')
            lines.append('<td style="padding: 2px 0;"><b>Parameters</b></td></tr>')
            for proc in process_seq:
                proc_name = proc.get("name", "")
                proc_date = proc.get("date", "")
                proc_performer = proc.get("performer", "")
                # Extract parameter values
                params = []
                for pv in proc.get("parameterValues", []):
                    cat_ref = pv.get("category", {})
                    param_id = cat_ref.get("@id", "") if isinstance(cat_ref, dict) else str(cat_ref)
                    param_name = param_id.split("/")[-1] if "/" in param_id else param_id
                    param_name = param_name.replace("#parameter/", "")
                    value = pv.get("value", "")
                    if isinstance(value, dict):
                        value = value.get("value", str(value))
                    params.append(f"{param_name}: {value}")
                params_str = ", ".join(params) if params else "-"
                lines.append("<tr>")
                lines.append(f'<td style="padding: 2px 8px 2px 0;">{self._escape(proc_name)}</td>')
                lines.append(f'<td style="padding: 2px 8px;">{self._escape(proc_date)}</td>')
                lines.append(f'<td style="padding: 2px 8px;">{self._escape(proc_performer)}</td>')
                lines.append(
                    f'<td style="padding: 2px 0; font-size: 11px;">{self._escape(params_str)}</td>'
                )
                lines.append("</tr>")
            lines.append("</table><br>")

        # Data Files
        data_files = assay.get("dataFiles", [])
        if data_files:
            lines.append(f"<b>Data Files ({len(data_files)}):</b><br>")
            lines.append('<ul style="margin-top: 2px;">')
            for df in data_files:
                df_name = df.get("name", "")
                df_type = df.get("type", "")
                df_comments = df.get("comments", [])
                file_size = self.get_comment_value(df_comments, "fileSize")
                derived_from = self.get_comment_value(df_comments, "derivedFromSample")

                size_str = self._format_file_size(int(file_size)) if file_size else ""
                type_str = (
                    f' <span style="color: #666;">({self._escape(df_type)})</span>'
                    if df_type
                    else ""
                )
                size_display = (
                    f' <span style="color: #999;">- {size_str}</span>' if size_str else ""
                )

                lines.append(f"<li>{self._escape(df_name)}{type_str}{size_display}")

                if derived_from and derived_from != "unassigned":
                    sample_name = self.resolve_material_name(derived_from)
                    lines.append(
                        f'<br><span style="color: #666; font-size: 11px;">Derived from: {self._escape(sample_name)}</span>'  # noqa: E501
                    )
                elif derived_from == "unassigned":
                    lines.append(
                        '<br><span style="color: #999; font-size: 11px;">Derived from: unassigned</span>'  # noqa: E501
                    )

                lines.append("</li>")
            lines.append("</ul>")

        # Input Materials
        inputs = []
        for proc in process_seq:
            for inp in proc.get("inputs", []):
                inp_id = inp.get("@id", "") if isinstance(inp, dict) else str(inp)
                if inp_id:
                    inputs.append(inp_id)
        if inputs:
            unique_inputs = list(dict.fromkeys(inputs))  # Deduplicate preserving order
            lines.append("<b>Input Materials:</b><br>")
            lines.append('<ul style="margin-top: 2px;">')
            for inp_id in unique_inputs:
                inp_name = self.resolve_material_name(inp_id)
                lines.append(f"<li>{self._escape(inp_name)}</li>")
            lines.append("</ul>")

        return "\n".join(lines)

    # --- File/DataFile Preview ---

    def get_datafile_preview_html(self, datafile: dict, assay: Optional[dict] = None) -> str:
        """
        Generate HTML preview for a data file (ISA-JSON dataFile object).

        Args:
            datafile: DataFile dict from ISA-JSON
            assay: Optional parent assay dict

        Returns:
            Formatted HTML string
        """
        lines = []

        name = datafile.get("name", "Unknown")
        df_type = datafile.get("type", "")
        df_id = datafile.get("@id", "")
        comments = datafile.get("comments", [])

        lines.append('<div style="margin-bottom: 12px;">')
        lines.append(f'<b style="font-size: 14px;">{self._escape(name)}</b><br>')
        if df_type:
            lines.append(f'<span style="color: #666;">Type:</span> {self._escape(df_type)}<br>')
        if df_id:
            lines.append(
                f'<span style="color: #666;">ID:</span> <code style="font-size: 10px;">{self._escape(df_id)}</code>'  # noqa: E501
            )
        lines.append("</div>")

        # Comments
        trace_db = self.get_comment_value(comments, "TraceDB")
        file_size = self.get_comment_value(comments, "fileSize")
        derived_from = self.get_comment_value(comments, "derivedFromSample")

        lines.append('<table style="border-collapse: collapse;">')
        if trace_db:
            lines.append('<tr><td style="padding: 2px 8px 2px 0; color: #666;">Path:</td>')
            lines.append(
                f'<td style="padding: 2px 0; font-size: 11px;"><code>{self._escape(trace_db)}</code></td></tr>'  # noqa: E501
            )
        if file_size:
            size_str = self._format_file_size(int(file_size))
            lines.append('<tr><td style="padding: 2px 8px 2px 0; color: #666;">Size:</td>')
            lines.append(f'<td style="padding: 2px 0;">{size_str}</td></tr>')
        if derived_from:
            if derived_from == "unassigned":
                lines.append('<tr><td style="padding: 2px 8px 2px 0; color: #666;">Sample:</td>')
                lines.append('<td style="padding: 2px 0; color: #999;">unassigned</td></tr>')
            else:
                sample_name = self.resolve_material_name(derived_from)
                lines.append('<tr><td style="padding: 2px 8px 2px 0; color: #666;">Sample:</td>')
                lines.append(f'<td style="padding: 2px 0;">{self._escape(sample_name)}</td></tr>')
                lines.append(
                    f'<tr><td></td><td style="padding: 2px 0; color: #aaa; font-size: 10px;"><code>{self._escape(derived_from)}</code></td></tr>'  # noqa: E501
                )
        lines.append("</table>")

        # Parent assay
        if assay:
            assay_name = self._get_assay_display_name(assay)
            lines.append(f"<br><b>Assay:</b> {self._escape(assay_name)}")

        return "\n".join(lines)

    # --- Study Preview ---

    def get_study_preview_html(self) -> str:
        """
        Generate HTML preview for the current study.

        Returns:
            Formatted HTML string
        """
        study = self.study
        lines = []

        # Title and description
        title = study.get("title", "")
        description = study.get("description", "")
        identifier = study.get("identifier", "")
        filename = study.get("filename", "")
        submission_date = study.get("submissionDate", "")

        lines.append('<div style="margin-bottom: 12px;">')
        if title:
            lines.append(f'<b style="font-size: 14px;">{self._escape(title)}</b><br>')
        if identifier:
            lines.append(
                f'<span style="color: #666;">Identifier:</span> <code>{self._escape(identifier)}</code><br>'  # noqa: E501
            )
        if filename:
            lines.append(
                f'<span style="color: #666;">Filename:</span> <code>{self._escape(filename)}</code><br>'  # noqa: E501
            )
        if submission_date:
            lines.append(
                f'<span style="color: #666;">Submitted:</span> {self._escape(submission_date)}'
            )
        lines.append("</div>")

        # Description
        if description:
            lines.append("<b>Description:</b><br>")
            lines.append(
                f'<p style="margin-left: 8px; color: #444;">{self._escape(description)}</p>'
            )

        # Study Design Descriptors
        design_descs = study.get("studyDesignDescriptors", [])
        if design_descs:
            lines.append("<b>Study Design:</b><br>")
            lines.append('<ul style="margin-top: 2px;">')
            for dd in design_descs:
                value = dd.get("annotationValue", "")
                source = dd.get("termSource", "")
                display = self._escape(value)
                if source:
                    display += f' <span style="color: #999;">({self._escape(source)})</span>'
                lines.append(f"<li>{display}</li>")
            lines.append("</ul>")

        # Factors
        factors = study.get("factors", [])
        if factors:
            lines.append(f"<b>Factors ({len(factors)}):</b><br>")
            lines.append('<ul style="margin-top: 2px;">')
            for factor in factors:
                fname = factor.get("factorName", "")
                ftype = factor.get("factorType", {})
                ftype_val = ftype.get("annotationValue", "") if isinstance(ftype, dict) else ""
                display = self._escape(fname)
                if ftype_val and ftype_val != fname:
                    display += f' <span style="color: #666;">({self._escape(ftype_val)})</span>'
                lines.append(f"<li>{display}</li>")
            lines.append("</ul>")

        # Protocols
        protocols = study.get("protocols", [])
        if protocols:
            lines.append(f"<b>Protocols ({len(protocols)}):</b><br>")
            lines.append('<ul style="margin-top: 2px;">')
            for protocol in protocols:
                pname = protocol.get("name", "")
                pdesc = protocol.get("description", "")
                ptype = protocol.get("protocolType", {})
                ptype_val = ptype.get("annotationValue", "") if isinstance(ptype, dict) else ""
                display = self._escape(pname)
                if ptype_val:
                    display += f' <span style="color: #666;">[{self._escape(ptype_val)}]</span>'
                if pdesc:
                    display += f'<br><span style="color: #888; font-size: 11px;">{self._escape(pdesc)}</span>'  # noqa: E501
                lines.append(f"<li>{display}</li>")
            lines.append("</ul>")

        # Characteristic Categories
        char_cats = study.get("characteristicCategories", [])
        if char_cats:
            lines.append("<b>Characteristic Categories:</b><br>")
            lines.append('<ul style="margin-top: 2px;">')
            for cat in char_cats:
                ct = cat.get("characteristicType", {})
                cat_name = ct.get("annotationValue", "")
                lines.append(f"<li>{self._escape(cat_name)}</li>")
            lines.append("</ul>")

        # Ontology Source References
        onto_refs = self.study_data.get("ontologySourceReferences", [])
        if onto_refs:
            lines.append("<b>Ontology Sources:</b><br>")
            lines.append('<table style="margin-left: 8px; border-collapse: collapse;">')
            lines.append('<tr style="color: #666; font-size: 11px;">')
            lines.append('<td style="padding: 2px 8px 2px 0;"><b>Name</b></td>')
            lines.append('<td style="padding: 2px 8px;"><b>Description</b></td>')
            lines.append('<td style="padding: 2px 0;"><b>Version</b></td></tr>')
            for onto in onto_refs:
                lines.append("<tr>")
                lines.append(
                    f'<td style="padding: 2px 8px 2px 0;"><b>{self._escape(onto.get("name", ""))}</b></td>'  # noqa: E501
                )
                lines.append(
                    f'<td style="padding: 2px 8px; font-size: 11px;">{self._escape(onto.get("description", ""))}</td>'  # noqa: E501
                )
                lines.append(
                    f'<td style="padding: 2px 0; font-size: 11px;">{self._escape(onto.get("version", ""))}</td>'  # noqa: E501
                )
                lines.append("</tr>")
            lines.append("</table>")

        return "\n".join(lines)

    # --- Internal Helpers ---

    def _get_assay_display_name(self, assay: dict) -> str:
        """Extract a display name from an assay dict."""
        assay_id = str(assay.get("@id", ""))
        if "#" in assay_id:
            return assay_id.split("#")[-1].replace("assay_", "").replace("_", " ")
        return str(assay.get("name", assay_id))

    def _get_linked_assays_for_material(self, material_id: str) -> list:
        """Find all assays that use a material as input in their processSequence."""
        if not material_id:
            return []
        linked = []
        study = self.study
        for assay in study.get("assays", []):
            for proc in assay.get("processSequence", []):
                for inp in proc.get("inputs", []):
                    inp_id = inp.get("@id", "") if isinstance(inp, dict) else str(inp)
                    if inp_id == material_id:
                        if assay not in linked:
                            linked.append(assay)
                        break
        return linked

    @staticmethod
    def _format_file_size(size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    @staticmethod
    def _escape(text: str) -> str:
        """Escape HTML special characters."""
        if not isinstance(text, str):
            text = str(text)
        return html.escape(text)
