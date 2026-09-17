"""
ISA-JSON Exporter for exporting study data to complete ISA-JSON format.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class ISAJsonExporter:
    """Export study data to complete ISA-JSON format."""

    def __init__(
        self,
        study_data: Optional[Dict[str, Any]] = None,
        investigation_id: Optional[str] = None,
        study_id: Optional[str] = None,
    ):
        """
        Initialize the ISA-JSON exporter.

        Args:
            study_data: The study data dictionary (optional)
            investigation_id: The investigation ID (optional)
            study_id: The study ID (optional)
        """
        self.study_data = study_data or {}
        self.investigation_id = investigation_id or "inv_1"
        self.study_id = study_id or "study_1"
        self.base_url = "https://example.org/investigations"

        # Cache for protocol templates
        self._protocol_templates: Optional[List[Dict[str, Any]]] = None
        self._used_unit_categories: List[Dict[str, Any]] = []

    @staticmethod
    def export_investigation(data: Dict[str, Any], output_path: str, indent: int = 2):
        """
        Export investigation JSON to a file.

        Args:
            data: Investigation data dictionary
            output_path: Path to output file
            indent: JSON indentation level
        """
        if data is None:
            raise ValueError("Data cannot be None")

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)

    @staticmethod
    def export_study(data: Dict[str, Any], output_path: str, indent: int = 2):
        """
        Export study JSON to a file.

        Args:
            data: Study data dictionary
            output_path: Path to output file
            indent: JSON indentation level
        """
        if data is None:
            raise ValueError("Data cannot be None")

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)

    @staticmethod
    def export_assay(data: Dict[str, Any], output_path: str, indent: int = 2):
        """
        Export assay JSON to a file.

        Args:
            data: Assay data dictionary
            output_path: Path to output file
            indent: JSON indentation level
        """
        if data is None:
            raise ValueError("Data cannot be None")

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)

    def export_complete_isa_json(self) -> Dict[str, Any]:
        """
        Export complete ISA-JSON structure.

        Returns:
            Complete ISA-JSON dictionary with investigation and study

        Note: Field order follows ISA-JSON schema as per BII-S-3.json example:
        publicReleaseDate, comments, identifier, submissionDate, description,
        people, studies, ontologySourceReferences, title, publications
        """
        # Build investigation-level JSON with correct field order matching BII-S-3.json
        result = {
            "publicReleaseDate": self.study_data.get("public_release_date", ""),
            "comments": self._get_investigation_comments(),
            "identifier": self.investigation_id,
            "submissionDate": self.study_data.get("submission_date", ""),
            "description": self._get_investigation_description(),
            "people": self._export_people() if self.study_data.get("people") else [],
            "studies": [self._export_study()],
            "ontologySourceReferences": self._get_ontology_source_references(),
            "title": self._get_investigation_title(),
            "publications": (
                self._export_publications() if self.study_data.get("publications") else []
            ),
        }

        return result

    def _get_investigation_comments(self) -> List[Dict[str, str]]:
        """
        Get investigation-level comments.

        Returns:
            List of comment dictionaries
        """
        # Default comments matching BII-S-3.json structure
        return [
            {"name": "Created With Configuration", "value": ""},
            {"name": "Last Opened With Configuration", "value": ""},
        ]

    def _get_investigation_id(self) -> str:
        """Get investigation ID."""
        return f"{self.base_url}/{self.investigation_id}"

    def _get_investigation_title(self) -> str:
        """Get investigation title."""
        return str(
            self.study_data.get("investigation_name", f"Investigation {self.investigation_id}")
        )

    def _get_investigation_description(self) -> str:
        """Get investigation description."""
        return str(self.study_data.get("investigation_description", "Project Investigation"))

    def _get_ontology_source_references(self) -> List[Dict[str, str]]:
        """
        Get ontology source references for investigation.

        Scans the study data for actually-used termSource values and only
        declares ontology sources that are referenced.  This prevents
        isatools validation warning code 3007 ("ontology source declared
        but not used").

        Returns:
            List of ontology source reference dictionaries
        """
        # All known ontology sources
        all_sources = {
            "OBI": {
                "name": "OBI",
                "description": "Ontology for Biomedical Investigations",
                "file": "http://purl.obolibrary.org/obo/obi.owl",
                "version": "latest",
            },
            "NCBITaxon": {
                "name": "NCBITaxon",
                "description": "NCBI Taxonomy Ontology",
                "file": "http://purl.obolibrary.org/obo/ncbitaxon.owl",
                "version": "latest",
            },
            "UO": {
                "name": "UO",
                "description": "Units of Measurement Ontology",
                "file": "http://purl.obolibrary.org/obo/uo.owl",
                "version": "latest",
            },
            "CHEBI": {
                "name": "CHEBI",
                "description": "Chemical Entities of Biological Interest",
                "file": "http://purl.obolibrary.org/obo/chebi.owl",
                "version": "latest",
            },
            "CL": {
                "name": "CL",
                "description": "Cell Ontology",
                "file": "http://purl.obolibrary.org/obo/cl.owl",
                "version": "latest",
            },
            "UBERON": {
                "name": "UBERON",
                "description": "Uber-anatomy Ontology",
                "file": "http://purl.obolibrary.org/obo/uberon.owl",
                "version": "latest",
            },
            "EFO": {
                "name": "EFO",
                "description": "Experimental Factor Ontology",
                "file": "http://www.ebi.ac.uk/efo/efo.owl",
                "version": "latest",
            },
            "PATO": {
                "name": "PATO",
                "description": "Phenotypic Quality Ontology",
                "file": "http://purl.obolibrary.org/obo/pato.owl",
                "version": "latest",
            },
        }

        # Collect all termSource values referenced in the study data
        used_sources: set = set()
        self._collect_term_sources(self.study_data, used_sources)

        # Always include OBI and UO as they are fundamental
        used_sources.add("OBI")
        used_sources.add("UO")

        return [all_sources[name] for name in sorted(used_sources) if name in all_sources]

    def _collect_term_sources(self, obj, used: set) -> None:
        """Recursively collect termSource values from a nested dict/list."""
        if isinstance(obj, dict):
            ts = obj.get("termSource")
            if ts and isinstance(ts, str):
                used.add(ts)
            for v in obj.values():
                self._collect_term_sources(v, used)
        elif isinstance(obj, list):
            for item in obj:
                self._collect_term_sources(item, used)

    def _export_publications(self) -> List[Dict[str, Any]]:
        """
        Export publications to ISA-JSON format.

        Returns:
            List of publication dictionaries
        """
        publications = []
        for pub in self.study_data.get("publications", []):
            publications.append(
                {
                    "title": pub.get("title", ""),
                    "pubMedID": pub.get("pubmed_id", ""),
                    "doi": pub.get("doi", ""),
                    "authorList": pub.get("authors", ""),
                    "status": {
                        "annotationValue": pub.get("status", "published"),
                        "termSource": "EFO",
                    },
                }
            )
        return publications

    def _get_used_category_ids(self) -> set:
        """
        Get IDs of characteristic categories actually used in materials.

        Returns:
            Set of category @id values that are referenced in material characteristics
        """
        used_categories = set()

        # Handle both simple format and ISA-JSON format
        # Simple format: study_data["materials"]["samples"]
        # ISA-JSON format: study_data["studies"][0]["materials"]["samples"]
        materials = None
        if "materials" in self.study_data:
            materials = self.study_data.get("materials", {})
        elif "studies" in self.study_data and isinstance(self.study_data["studies"], list):
            if len(self.study_data["studies"]) > 0:
                materials = self.study_data["studies"][0].get("materials", {})

        # Also check assay-level materials when loading from ISA-JSON format
        if "studies" in self.study_data and isinstance(self.study_data["studies"], list):
            if len(self.study_data["studies"]) > 0:
                study = self.study_data["studies"][0]
                # Check assay materials
                for assay in study.get("assays", []):
                    assay_materials = assay.get("materials", {})
                    # Check samples in assay materials
                    for sample in assay_materials.get("samples", []):
                        for char in sample.get("characteristics", []):
                            category = char.get("category", {})
                            if isinstance(category, dict):
                                cat_id = category.get("@id", "")
                                if cat_id:
                                    used_categories.add(cat_id)

        if not materials:
            return used_categories

        # Check sources
        for source in materials.get("sources", []):
            for char in source.get("characteristics", []):
                category = char.get("category", {})
                if isinstance(category, dict):
                    cat_id = category.get("@id", "")
                    if cat_id:
                        used_categories.add(cat_id)

        # Check samples
        for sample in materials.get("samples", []):
            for char in sample.get("characteristics", []):
                category = char.get("category", {})
                if isinstance(category, dict):
                    cat_id = category.get("@id", "")
                    if cat_id:
                        used_categories.add(cat_id)

        # Check otherMaterials
        for material in materials.get("otherMaterials", []):
            for char in material.get("characteristics", []):
                category = char.get("category", {})
                if isinstance(category, dict):
                    cat_id = category.get("@id", "")
                    if cat_id:
                        used_categories.add(cat_id)

        # Also check assay-level materials
        # Get assays from study_data
        raw_assays = self.study_data.get("assays", [])
        if not raw_assays and "studies" in self.study_data:
            # Try to get assays from ISA-JSON format
            if isinstance(self.study_data["studies"], list) and len(self.study_data["studies"]) > 0:
                raw_assays = self.study_data["studies"][0].get("assays", [])

        for assay in raw_assays:
            # Check assay samples
            for sample in assay.get("materials", {}).get("samples", []):
                for char in sample.get("characteristics", []):
                    category = char.get("category", {})
                    if isinstance(category, dict):
                        cat_id = category.get("@id", "")
                        if cat_id:
                            used_categories.add(cat_id)

            # Check assay otherMaterials
            for material in assay.get("materials", {}).get("otherMaterials", []):
                for char in material.get("characteristics", []):
                    category = char.get("category", {})
                    if isinstance(category, dict):
                        cat_id = category.get("@id", "")
                        if cat_id:
                            used_categories.add(cat_id)

            # Also check samples referenced in assay processSequence inputs
            for process in assay.get("processSequence", []):
                for input_ref in process.get("inputs", []):
                    input_id = (
                        input_ref.get("@id", "") if isinstance(input_ref, dict) else input_ref
                    )
                    if isinstance(input_id, str) and "/sample/" in input_id:
                        # Find the sample in study materials and check its characteristics
                        for sample in materials.get("samples", []):
                            if sample.get("@id", "") == input_id:
                                for char in sample.get("characteristics", []):
                                    category = char.get("category", {})
                                    if isinstance(category, dict):
                                        cat_id = category.get("@id", "")
                                        if cat_id:
                                            used_categories.add(cat_id)

        return used_categories

    def _export_characteristic_categories(self) -> List[Dict[str, Any]]:
        """
        Export characteristic categories to ISA-JSON format.

        Only exports categories that are actually used in material characteristics
        to avoid validation warnings about unused categories.

        Returns:
            List of characteristic category dictionaries
        """
        # Get categories actually used in materials
        used_category_ids = self._get_used_category_ids()

        categories = []

        # Define all possible characteristic categories
        all_categories = {
            "#characteristic_category/organism": {
                "@id": "#characteristic_category/organism",
                "characteristicType": {
                    "annotationValue": "organism",
                    "termSource": "OBI",
                    "termAccession": "http://purl.obolibrary.org/obo/OBI_0100026",
                },
            },
            "#characteristic_category/material_type": {
                "@id": "#characteristic_category/material_type",
                "characteristicType": {
                    "annotationValue": "material type",
                    "termSource": "OBI",
                    "termAccession": "http://purl.obolibrary.org/obo/OBI_0000100",
                },
            },
            "#characteristic_category/extract_type": {
                "@id": "#characteristic_category/extract_type",
                "characteristicType": {
                    "annotationValue": "extract type",
                    "termSource": "OBI",
                    "termAccession": "http://purl.obolibrary.org/obo/OBI_0000125",
                },
            },
        }

        # Only add categories that are actually used
        for cat_id, cat_data in all_categories.items():
            if cat_id in used_category_ids:
                categories.append(cat_data)

        return categories

    def _export_people(self) -> List[Dict[str, Any]]:
        """
        Export people/contacts to ISA-JSON format.

        Returns:
            List of person dictionaries
        """
        people = []
        for person in self.study_data.get("people", []):
            person_dict = {
                "firstName": person.get("first_name", ""),
                "lastName": person.get("last_name", ""),
                "midInitials": person.get("middle_initials", ""),
                "email": person.get("email", ""),
                "phone": person.get("phone", ""),
                "address": person.get("address", ""),
                "affiliation": person.get("affiliation", ""),
            }

            # Add roles if present
            if person.get("roles"):
                person_dict["roles"] = [
                    {"annotationValue": role, "termSource": "EFO"}
                    for role in person.get("roles", [])
                ]

            people.append(person_dict)
        return people

    def _export_study_design_descriptors(self) -> List[Dict[str, Any]]:
        """
        Export study design descriptors to ISA-JSON format.

        Returns:
            List of ontology annotation dictionaries
        """
        descriptors = []
        for descriptor in self.study_data.get("study_design_descriptors", []):
            descriptors.append(
                {
                    "annotationValue": descriptor.get("name", ""),
                    "termSource": descriptor.get("term_source", "EFO"),
                    "termAccession": descriptor.get("term_accession", ""),
                }
            )
        return descriptors

    def _export_factors(self) -> List[Dict[str, Any]]:
        """
        Export study factors to ISA-JSON format.

        Study factors represent independent variables (experimental conditions)
        that are manipulated in a study. Examples: dose, time, temperature, compound.

        Returns:
            List of factor dictionaries with @id, factorName, and factorType
        """
        factors = []
        for factor in self.study_data.get("factors", []):
            factor_name = factor.get("name", "")
            factor_id = factor.get("@id", f"#factor/{factor_name.lower().replace(' ', '_')}")

            factor_dict = {
                "@id": factor_id,
                "factorName": factor_name,
                "factorType": {
                    "annotationValue": factor.get("type", factor_name),
                    "termSource": factor.get("term_source", "EFO"),
                    "termAccession": factor.get("term_accession", ""),
                },
            }
            factors.append(factor_dict)
        return factors

    def _export_study(self) -> Dict[str, Any]:
        """
        Export study with all components.

        Returns:
            Study dictionary with materials (containing sources, samples, and otherMaterials),
            protocols, processSequence, and assays.

        Note: otherMaterials are included at study level when referenced in study-level
        processSequence, and also at assay level for assay-specific materials.
        """
        materials = self._export_materials()

        # Collect otherMaterials referenced in study-level processSequence
        study_other_materials = self._get_study_process_other_materials()

        # Build study object with field order matching BII-S-3.json structure
        # Note: technologyPlatform is NOT allowed at study level per ISA-JSON schema
        result = {
            "factors": self._export_factors(),  # factors first as in BII-S-3.json
            "assays": self._export_assays(materials["otherMaterials"]),
            "materials": {
                "sources": materials["sources"],
                "samples": materials["samples"],
                # Include otherMaterials referenced in study-level processes
                "otherMaterials": (
                    study_other_materials if study_other_materials else materials["otherMaterials"]
                ),
            },
            "unitCategories": getattr(
                self, "_used_unit_categories", []
            ),  # Populated from parameterValues with units
            "protocols": self._export_protocols(),
            "processSequence": self._export_process_sequence(),
            "@id": self._get_study_id(),
            "identifier": self.study_data.get("identifier", self.study_id),
            "filename": self._get_study_filename(),  # Required by ISA-JSON spec
            "title": self.study_data.get("study_name", ""),
            "description": self.study_data.get("study_description", ""),
            "submissionDate": self.study_data.get(
                "submission_date", datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            ),
            "studyDesignDescriptors": self.study_data.get(
                "study_design_descriptors",
                [
                    {
                        "annotationValue": "experimental study",
                        "termSource": "OBI",
                        "termAccession": "http://purl.obolibrary.org/obo/OBI_0000066",
                    }
                ],
            ),
            "characteristicCategories": self._export_characteristic_categories(),
            "people": self._export_people() if self.study_data.get("people") else [],
            "publications": (
                self._export_publications() if self.study_data.get("publications") else []
            ),
            "comments": self._get_study_comments(),
        }

        # Add optional fields if available
        if self.study_data.get("public_release_date"):
            result["publicReleaseDate"] = self.study_data["public_release_date"]

        return result

    def _get_study_comments(self) -> List[Dict[str, str]]:
        """
        Get study-level comments including sequence file reference.

        Returns:
            List of comment dictionaries
        """
        comments = []

        # Add sequence file comment if present
        sequence_file_path = self.study_data.get("copied_sequence_path")
        if sequence_file_path:
            comments.append({"name": "Sequence File", "value": sequence_file_path})

        # Add sequence ID if present
        sequence_data = self.study_data.get("sequence_data")
        if sequence_data and sequence_data.get("sequence_id"):
            comments.append({"name": "Sequence ID", "value": sequence_data["sequence_id"]})

        return comments

    def _get_study_id(self) -> str:
        """Get study ID — use relative fragment per ISA-JSON spec."""
        return f"#{self.study_id}"

    def _get_study_filename(self) -> str:
        """
        Get study filename in ISA-JSON format.

        The filename follows the pattern: s_{study_id}.txt
        This is required by the ISA-JSON specification.

        Returns:
            Study filename string
        """
        return f"s_{self.study_id}.txt"

    def _get_study_process_other_materials(self) -> List[Dict[str, Any]]:
        """
        Get otherMaterials referenced in study-level processSequence.

        These materials need to be declared at study level for validation to pass,
        as the validator expects all materials referenced in processSequence to be
        declared in the materials section.

        Returns:
            List of otherMaterial dictionaries referenced in study processes
        """
        other_materials = []
        materials = self.study_data.get("materials", {})
        all_other_materials = materials.get("otherMaterials", [])

        # Get all material IDs referenced in study-level processSequence
        process_sequence = self.study_data.get("process_sequence", {})
        if not process_sequence and "processSequence" in self.study_data:
            process_sequence = self.study_data.get("processSequence", {})

        processes = process_sequence.get("processes", [])
        referenced_ids = set()

        for process in processes:
            for input_ref in process.get("inputs", []):
                # Handle both string format and dict format
                if isinstance(input_ref, str):
                    material_id = input_ref
                else:
                    material_id = input_ref.get("material_id", "") or input_ref.get("@id", "")
                if material_id and "othermaterial" in material_id.lower():
                    referenced_ids.add(material_id)
            for output_ref in process.get("outputs", []):
                # Handle both string format and dict format
                if isinstance(output_ref, str):
                    material_id = output_ref
                else:
                    material_id = output_ref.get("material_id", "") or output_ref.get("@id", "")
                if material_id and "othermaterial" in material_id.lower():
                    referenced_ids.add(material_id)

        # Find matching materials from all_other_materials
        for material in all_other_materials:
            material_id = material.get("@id", "")
            if material_id in referenced_ids:
                other_materials.append(
                    {
                        "@id": material_id,
                        "type": "Extract Name",
                        "name": material.get("name", ""),
                        "characteristics": material.get("characteristics", []),
                    }
                )

        return other_materials

    def _export_materials(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Export materials to ISA-JSON format.

        Returns:
            Dictionary with sources, samples, and otherMaterials arrays
        """
        materials = self.study_data.get("materials", {})
        factors = self.study_data.get("factors", [])

        # Helper function to add default characteristics
        def get_characteristics(
            material: Dict[str, Any], material_type: str
        ) -> List[Dict[str, Any]]:
            chars: List[Dict[str, Any]] = material.get("characteristics", [])
            if not chars:
                # Add default characteristic based on material type
                # Use category references instead of inline characteristicType
                if material_type == "source":
                    chars = [
                        {
                            "@id": f"material_attribute_{material.get('name', '').replace(' ', '_').lower()}",  # noqa: E501
                            "category": {"@id": "#characteristic_category/organism"},
                            "value": {
                                "annotationValue": "Escherichia coli",
                                "termSource": "NCBITaxon",
                                "termAccession": "http://purl.obolibrary.org/obo/NCBITaxon_562",
                            },
                        }
                    ]
                elif material_type == "sample":
                    chars = [
                        {
                            "@id": f"material_attribute_{material.get('name', '').replace(' ', '_').lower()}",  # noqa: E501
                            "category": {"@id": "#characteristic_category/material_type"},
                            "value": {
                                "annotationValue": "biological sample",
                                "termSource": "OBI",
                                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000952",
                            },
                        }
                    ]
            return chars

        # Helper function to get factor values for a sample
        def get_factor_values(sample: Dict[str, Any]) -> List[Dict[str, Any]]:
            """
            Get factor values for a sample.

            Factor values link samples to study factors, indicating the
            experimental conditions applied to that sample.
            """
            factor_values: List[Dict[str, Any]] = sample.get("factorValues", [])

            # If no factor values provided but factors exist, add empty factor values
            if not factor_values and factors:
                for factor in factors:
                    factor_id = factor.get(
                        "@id", f"#factor/{factor.get('name', '').lower().replace(' ', '_')}"
                    )
                    factor_values.append(
                        {
                            "category": {"@id": factor_id},
                            "value": {"annotationValue": "", "termSource": "", "termAccession": ""},
                        }
                    )

            return factor_values

        return {
            "sources": [
                {
                    "@id": m.get("@id", ""),
                    "name": m.get("name", ""),
                    "characteristics": get_characteristics(m, "source"),
                }
                for m in materials.get("sources", [])
            ],
            "samples": [
                {
                    "@id": m.get("@id", ""),
                    "name": m.get("name", ""),
                    "characteristics": get_characteristics(m, "sample"),
                    "factorValues": get_factor_values(m),
                }
                for m in materials.get("samples", [])
            ],
            "otherMaterials": [
                {
                    "@id": m.get("@id", ""),
                    "type": "Extract Name",
                    "name": m.get("name", ""),
                    "characteristics": get_characteristics(m, "material"),
                }
                for m in materials.get("otherMaterials", [])
            ],
        }

    def _load_protocol_templates(self) -> List[Dict[str, Any]]:
        """
        Load protocol templates from templates directory.

        Returns:
            List of protocol template dictionaries
        """
        if self._protocol_templates is not None:
            return self._protocol_templates

        protocols = []
        protocol_dir = Path(__file__).parent.parent / "templates" / "protocol_templates"

        if protocol_dir.exists():
            for json_file in sorted(protocol_dir.glob("*.json")):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        protocol_data = json.load(f)
                        protocols.append(protocol_data)
                except Exception as e:
                    print(f"Error loading protocol {json_file}: {e}")

        self._protocol_templates = protocols
        return protocols

    def _get_used_protocol_names(self) -> set:
        """
        Get names of protocols actually used in process sequences.

        Also includes protocols that will be dynamically created by _export_assays
        for assays with dataFiles but no explicit processSequence.

        Returns:
            Set of protocol names that are referenced in processes
        """
        used_protocols = set()

        # Check study-level process sequence
        process_sequence = self.study_data.get("process_sequence", {})
        if not process_sequence and "processSequence" in self.study_data:
            process_sequence = self.study_data.get("processSequence", {})

        for process in process_sequence.get("processes", []):
            protocol_ref = process.get("protocol_ref", "")
            if protocol_ref:
                used_protocols.add(protocol_ref.lower())

        # Check assay-level process sequences
        for assay in self.study_data.get("assays", []):
            has_process_sequence = False
            for process in assay.get("processSequence", []):
                has_process_sequence = True
                executes_protocol = process.get("executesProtocol", "")
                if isinstance(executes_protocol, str):
                    # Extract protocol name from URL if needed
                    if executes_protocol.startswith("http"):
                        if "#prot_" in executes_protocol:
                            protocol_name = executes_protocol.split("#prot_")[-1].replace("_", " ")
                            used_protocols.add(protocol_name.lower())
                    else:
                        used_protocols.add(executes_protocol.lower())
                elif isinstance(executes_protocol, dict):
                    protocol_name = executes_protocol.get("name", "")
                    if protocol_name:
                        used_protocols.add(protocol_name.lower())

            # If assay has no processSequence but has dataFiles, _export_assays will
            # create a dynamic process with protocol name "assay {assay_name}"
            # We need to include this protocol name so it gets declared
            if not has_process_sequence:
                assay_name = assay.get("name", "")
                has_data_files = bool(assay.get("dataFiles", []))
                has_inputs = bool(assay.get("inputs", []))
                if (has_data_files or has_inputs) and assay_name:
                    dynamic_protocol_name = f"assay {assay_name}"
                    used_protocols.add(dynamic_protocol_name.lower())

        return used_protocols

    def _get_used_parameter_names(self) -> set:
        """
        Get names of parameters actually used in process sequences.

        Returns:
            Set of parameter names that are referenced in parameterValues
        """
        used_parameters = set()

        # Check study-level process sequence
        process_sequence = self.study_data.get("process_sequence", {})
        if not process_sequence and "processSequence" in self.study_data:
            process_sequence = self.study_data.get("processSequence", {})

        for process in process_sequence.get("processes", []):
            for param in process.get("parameters", []):
                param_name = param.get("name", "")
                if param_name:
                    used_parameters.add(param_name.lower())

        # Check assay-level process sequences
        # Handle both simple format (study_data["assays"]) and ISA-JSON format
        # (study_data["studies"][0]["assays"])
        raw_assays = self.study_data.get("assays", [])
        if not raw_assays and "studies" in self.study_data:
            if isinstance(self.study_data["studies"], list) and len(self.study_data["studies"]) > 0:
                raw_assays = self.study_data["studies"][0].get("assays", [])

        for assay in raw_assays:
            # Check process sequence parameters
            for process in assay.get("processSequence", []):
                for param in process.get("parameterValues", []):
                    category = param.get("category", {})
                    if isinstance(category, dict):
                        param_id = category.get("@id", "")
                        # Extract parameter name from #parameter/param_name format
                        if param_id.startswith("#parameter/"):
                            param_name = param_id.replace("#parameter/", "").replace("_", " ")
                            used_parameters.add(param_name.lower())

            # Check assay-level parameters
            assay_params = assay.get("parameters", [])

            # Handle both dict format ({"param_name": "value"}) and list format ([{"name": "param_name", "value": "value"}])  # noqa: E501
            if isinstance(assay_params, dict):
                # Dict format: keys are parameter names
                for param_name in assay_params.keys():
                    if param_name:
                        used_parameters.add(param_name.lower())
            else:
                # List format: each item is a dict with "name" key
                for param in assay_params:
                    param_name = param.get("name", "")
                    if param_name:
                        used_parameters.add(param_name.lower())

        return used_parameters

    def _export_protocols(self) -> List[Dict[str, Any]]:
        """
        Export protocols to ISA-JSON format.

        Only exports protocols that are actually used in process sequences
        to avoid validation warnings about unused protocols.

        Returns:
            List of protocol dictionaries in ISA-JSON format
        """
        protocols = []
        protocol_templates = self._load_protocol_templates()
        added_protocol_ids = set()  # Track added protocol IDs to avoid duplicates

        # Get protocols actually used in process sequences
        used_protocol_names = self._get_used_protocol_names()

        # First, add protocols from study_data (set by process_partner_data.py or GUI)
        for protocol in self.study_data.get("protocols", []):
            protocol_name = protocol.get("name", "")
            if not protocol_name:
                continue

            # Only export protocols that are actually used
            if protocol_name.lower() not in used_protocol_names:
                continue

            protocol_id = self._get_protocol_id(protocol_name)
            if protocol_id in added_protocol_ids:
                continue

            # Get protocol type from the protocol data
            protocol_type_value = protocol.get("type", "")
            if not protocol_type_value:
                protocol_type_value = protocol_name or "protocol"

            isa_protocol = {
                "@id": protocol_id,
                "name": protocol_name,
                "description": protocol.get("description", ""),
                "protocolType": {"annotationValue": protocol_type_value, "termSource": "OBI"},
                "parameters": protocol.get("parameters", []),
                "components": protocol.get("components", []),
            }
            added_protocol_ids.add(protocol_id)
            protocols.append(isa_protocol)

        # Then, add protocols from protocol templates
        for protocol in protocol_templates:
            protocol_name = protocol.get("name", "")

            # Only export protocols that are actually used
            if protocol_name.lower() not in used_protocol_names:
                continue

            protocol_id = self._get_protocol_id(protocol_name)
            if protocol_id in added_protocol_ids:
                continue

            # Get protocol type from template or use name as fallback
            protocol_type_value = protocol.get("type", "")
            if not protocol_type_value:
                protocol_type_value = protocol_name or "protocol"

            isa_protocol = {
                "@id": protocol_id,
                "name": protocol_name,
                "description": protocol.get("description", ""),
                "protocolType": {"annotationValue": protocol_type_value, "termSource": "OBI"},
            }
            added_protocol_ids.add(protocol_id)

            # Add components if available
            if "components" in protocol:
                isa_protocol["components"] = self._export_protocol_components(protocol)

            # Add parameters if available
            if "parameters" in protocol:
                isa_protocol["parameters"] = self._export_protocol_parameters(protocol)

            protocols.append(isa_protocol)

        # Add assay-specific protocols from assay templates
        assay_protocols = self._get_assay_protocols(added_protocol_ids)
        protocols.extend(assay_protocols)

        return protocols

    def _get_assay_protocols(self, added_protocol_ids: set) -> List[Dict[str, Any]]:
        """
        Get protocols from assay templates that are used in assay process sequences.

        Args:
            added_protocol_ids: Set of protocol IDs already added to avoid duplicates

        Returns:
            List of assay-specific protocol dictionaries
        """
        assay_protocols = []
        assay_templates = self._load_assay_templates()

        # Get all protocol names referenced in assay process sequences
        referenced_protocols = self._get_referenced_assay_protocols()

        for assay_name, protocol_name in referenced_protocols:
            protocol_id = self._get_protocol_id(protocol_name)
            if protocol_id in added_protocol_ids:
                continue  # Skip if already added

            # Find matching assay template
            # Try multiple matching strategies to handle different naming conventions
            assay_template = None
            assay_name_normalized = assay_name.lower().replace("-", " ").replace("_", " ")
            protocol_name_normalized = protocol_name.lower().replace("-", " ").replace("_", " ")

            for template in assay_templates:
                template_name = template.get("name", "").lower().replace("-", " ").replace("_", " ")

                # Try exact match first
                if template_name == assay_name_normalized:
                    assay_template = template
                    break
                # Try protocol name match (e.g., "sds page" matches "sds-page assay")
                elif template_name == protocol_name_normalized:
                    assay_template = template
                    break
                # Try partial match (e.g., "sds page" matches "sds-page assay")
                elif (
                    assay_name_normalized in template_name or template_name in assay_name_normalized
                ):
                    assay_template = template
                    break
                # Try protocol name partial match
                elif (
                    protocol_name_normalized in template_name
                    or template_name in protocol_name_normalized
                ):
                    assay_template = template
                    break

            if assay_template:
                # Create protocol from assay template
                isa_protocol = {
                    "@id": protocol_id,
                    "name": protocol_name,
                    "description": assay_template.get("description", ""),
                    "protocolType": {
                        "annotationValue": assay_template.get("technologyType", {}).get(
                            "annotationValue", protocol_name
                        ),
                        "termSource": assay_template.get("technologyType", {}).get(
                            "termSource", "OBI"
                        ),
                        "termAccession": assay_template.get("technologyType", {}).get(
                            "termAccession", ""
                        ),
                    },
                }

                # Add parameters from assay template
                if "parameters" in assay_template:
                    isa_protocol["parameters"] = self._export_assay_protocol_parameters(
                        assay_template
                    )

                assay_protocols.append(isa_protocol)
                added_protocol_ids.add(protocol_id)

        return assay_protocols

    def _load_assay_templates(self) -> List[Dict[str, Any]]:
        """
        Load assay templates from templates directory.

        Returns:
            List of assay template dictionaries
        """
        assay_templates = []
        assay_dir = Path(__file__).parent.parent / "templates" / "assay_templates"

        if assay_dir.exists():
            for json_file in sorted(assay_dir.glob("*.json")):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        assay_data = json.load(f)
                        assay_templates.append(assay_data)
                except Exception as e:
                    print(f"Error loading assay template {json_file}: {e}")

        return assay_templates

    def _get_referenced_assay_protocols(self) -> List[tuple]:
        """
        Get all protocol names referenced in assay process sequences.

        Returns:
            List of tuples (assay_name, protocol_name)
        """
        referenced = []

        # Handle both simple format and ISA-JSON format
        raw_assays = self.study_data.get("assays", [])
        if not raw_assays and "studies" in self.study_data:
            # Try to get assays from ISA-JSON format
            if isinstance(self.study_data["studies"], list) and len(self.study_data["studies"]) > 0:
                raw_assays = self.study_data["studies"][0].get("assays", [])

        for assay in raw_assays:
            assay_name = assay.get("name", "")
            process_sequence = assay.get("processSequence", [])

            for process in process_sequence:
                executes_protocol = process.get("executesProtocol", "")
                protocol_name = None

                if isinstance(executes_protocol, str):
                    # Extract protocol name from URL if needed
                    if executes_protocol.startswith("http"):
                        # Extract from URL like "https://example.org/inv_1#prot_sds_page"
                        if "#prot_" in executes_protocol:
                            protocol_name = executes_protocol.split("#prot_")[-1].replace("_", " ")
                        else:
                            protocol_name = executes_protocol.split("/")[-1]
                    else:
                        protocol_name = executes_protocol
                elif isinstance(executes_protocol, dict):
                    protocol_name = executes_protocol.get("name", "")

                # Only add if we got a valid protocol name
                if protocol_name:
                    referenced.append((assay_name, protocol_name))

        return referenced

    def _export_assay_protocol_parameters(
        self, assay_template: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Export protocol parameters from an assay template.

        Args:
            assay_template: Assay template dictionary

        Returns:
            List of parameter dictionaries
        """
        parameters = []

        # Get parameters that are actually used in process sequences
        used_parameters = self._get_used_parameter_names()

        for param in assay_template.get("parameters", []):
            param_name = param.get("name", "")
            # Only export parameters that are actually used
            if param_name.lower() not in used_parameters:
                continue

            param_obj: Dict[str, Any] = {
                "@id": f"#parameter/{param_name.replace(' ', '_')}",
                "parameterName": {
                    "annotationValue": param_name,
                    "termSource": param.get("termSource", "OBI"),
                },
            }

            if "termAccession" in param:
                param_obj["parameterName"]["termAccession"] = param["termAccession"]

            parameters.append(param_obj)

        return parameters

    def _get_protocol_id(self, protocol_name: str) -> str:
        """
        Get protocol ID.

        Args:
            protocol_name: Name of the protocol

        Returns:
            Protocol ID as a relative reference (matching BII-S-3.json format)
        """
        # Replace both spaces and hyphens with underscores for consistency
        protocol_id = protocol_name.replace(" ", "_").replace("-", "_").lower()
        # Use relative ID format matching BII-S-3.json: #protocol/protocol_name
        return f"#protocol/{protocol_id}"

    def _get_protocol_object(self, protocol_name: str) -> Dict[str, Any]:
        """
        Get a minimal Protocol object for use in executesProtocol field.

        According to ISA-JSON schema, executesProtocol must be an object,
        not a string reference.

        Args:
            protocol_name: Name of the protocol

        Returns:
            Minimal Protocol object with @id and name
        """
        return {"@id": self._get_protocol_id(protocol_name), "name": protocol_name}

    def _export_protocol_components(self, protocol: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Export protocol components.

        Args:
            protocol: Protocol dictionary

        Returns:
            List of component dictionaries
        """
        components = []
        for component in protocol.get("components", []):
            components.append(
                {"name": component.get("name", ""), "value": component.get("value", "")}
            )
        return components

    def _export_protocol_parameters(self, protocol: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Export protocol parameters.

        Args:
            protocol: Protocol dictionary

        Returns:
            List of parameter dictionaries with @id in #parameter/name format
        """
        parameters = []

        # Get parameters that are actually used in process sequences
        used_parameters = self._get_used_parameter_names()

        for param in protocol.get("parameters", []):
            param_name = param.get("name", "")
            # Only export parameters that are actually used
            if param_name.lower() not in used_parameters:
                continue

            param_obj: Dict[str, Any] = {
                "@id": f"#parameter/{param_name.replace(' ', '_')}",
                "parameterName": {
                    "annotationValue": param_name,
                    "termSource": param.get("termSource", "OBI"),
                },
            }

            if "termAccession" in param:
                param_obj["parameterName"]["termAccession"] = param["termAccession"]

            # Note: defaultValue and unit are NOT allowed in ProtocolParameter schema
            # They should only be in ParameterValue objects in process sequence

            parameters.append(param_obj)

        return parameters

    def _export_material_references(self, material_refs: List[Any]) -> List[Dict[str, Any]]:
        """
        Convert material references to ISA-JSON format.

        According to ISA-JSON schema, inputs and outputs in processSequence
        must be objects with @id field, not string URIs.

        Args:
            material_refs: List of material references (strings or dicts)

        Returns:
            List of material reference objects with @id field
        """
        result = []
        for ref in material_refs:
            if isinstance(ref, dict):
                # Already a dictionary - ensure it has @id
                material_id = ref.get("@id", ref.get("material_id", ""))
                if material_id:
                    result.append({"@id": material_id})
            elif isinstance(ref, str):
                # String URI - convert to object format
                if ref:
                    result.append({"@id": ref})
        return result

    def _export_process_sequence(self) -> List[Dict[str, Any]]:
        """
        Export process sequence to ISA-JSON format.

        Returns:
            List of process dictionaries in ISA-JSON format
        """
        process_sequence = self.study_data.get("process_sequence", {})

        # If not found, try 'processSequence' (camelCase) - for ISA-JSON compatibility
        if not process_sequence and "processSequence" in self.study_data:
            process_sequence = self.study_data.get("processSequence", {})

        processes = process_sequence.get("processes", [])

        # Filter out assay-level processes (those tagged with assayContext).
        # These belong in their respective assay processSequence and must not
        # be duplicated at the study level in the exported ISA-JSON.
        processes = [p for p in processes if "assayContext" not in p]

        isa_processes = []

        for i, process in enumerate(processes):
            process_name = process.get("name", f"p{i}")
            process_id = f"#process_{process_name.replace(' ', '_')}"

            # Get date with default to current date if not provided
            date_value = process.get("date", "")
            if not date_value:
                date_value = datetime.now().strftime("%Y-%m-%d")

            isa_process = {
                "@id": process_id,
                "name": process_name,
                "executesProtocol": self._get_protocol_object(process.get("protocol_ref", "")),
                "date": date_value,
                # Convert inputs/outputs to object format with @id field
                "inputs": self._export_material_references(process.get("inputs", [])),
                "outputs": self._export_material_references(process.get("outputs", [])),
                "parameterValues": [],
            }

            # Add parameter values from either key (parameters from GUI,
            # parameterValues from _create_study_process_sequence)
            raw_params = process.get("parameters", []) or process.get("parameterValues", [])
            for param in raw_params:
                param_value = self._export_parameter_value(param, process_id)
                isa_process["parameterValues"].append(param_value)

            # Store GUI-specific status in comments array for ISA-JSON compliance
            # This allows the GUI to restore process status after loading
            process_status = process.get("status", "Pending")
            if process_status and process_status != "Pending":
                isa_process["comments"] = [{"name": "status", "value": process_status}]

            # NOTE: Other GUI-specific data (_inputNames, _outputNames) are not stored
            # for ISA-JSON compliance. These are handled differently by the GUI.

            isa_processes.append(isa_process)

        return isa_processes

    def _export_parameter_value(self, param: Dict[str, Any], process_id: str) -> Dict[str, Any]:
        """
        Export a parameter value to ISA-JSON format.

        Args:
            param: Parameter data from internal format.  Accepts two shapes:
                - GUI format: {"name": "...", "value": "...", ...}
                - ISA-JSON format from _create_study_process_sequence:
                  {"category": {"@id": "#parameter/..."}, "value": {"annotationValue": "..."}}
            process_id: Parent process ID for constructing @id

        Returns:
            ISA-JSON compliant parameter value with category as @id reference only

        Note: Per ISA-JSON schema and BII-S-3.json example, parameterValues do NOT
        have a 'unit' field. Units are only valid in characteristics and factorValues.
        """
        # B6 FIX: Handle ISA-JSON pre-formatted parameterValues from
        # _create_study_process_sequence (already have category.@id and
        # value.annotationValue).
        if "category" in param and "value" in param and isinstance(param["value"], dict):
            return {
                "category": {"@id": param["category"]["@id"]},
                "value": {"annotationValue": param["value"].get("annotationValue", "")},
            }

        param_name = param.get("name", "")
        _param_id = f"{process_id}#pp_{param_name.replace(' ', '_')}"  # noqa: F841

        # Category should only be an @id reference to the parameter defined in protocols
        # The format is #parameter/param_name (matching what's defined in protocol parameters)
        param_value: Dict[str, Any] = {
            "category": {"@id": f"#parameter/{param_name.replace(' ', '_')}"}
        }

        # Handle value - can be ontology annotation, string, or number
        # NOTE: unit is NOT allowed in parameterValues per ISA-JSON schema
        value = param.get("value", "")
        has_annotation_value = "annotationValue" in param

        # According to ISA-JSON schema, value can be:
        # 1. An ontology annotation (object with annotationValue, termSource, termAccession)
        # 2. A simple string
        # 3. A simple number
        if has_annotation_value:
            # Ontology annotation value
            param_value["value"] = {"annotationValue": param["annotationValue"]}
            if "termSource" in param:
                param_value["value"]["termSource"] = param["termSource"]
            if "termAccession" in param:
                param_value["value"]["termAccession"] = param["termAccession"]
        elif value:
            # Simple value (string or number) - no unit allowed in parameterValues
            try:
                if "." in str(value):
                    param_value["value"] = float(value)
                else:
                    param_value["value"] = int(value)
            except (ValueError, TypeError):
                param_value["value"] = str(value)

        return param_value

    def _export_assays(
        self, other_materials: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Export assays to ISA-JSON format.

        Args:
            other_materials: List of otherMaterials to include at assay level
                           (per ISA-JSON spec, otherMaterials belong at assay level)

        Returns:
            List of assay dictionaries in ISA-JSON format
        """
        assays = []
        # Track assay name occurrences for unique IDs
        assay_name_counts: Dict[str, int] = {}
        # Use empty list if no otherMaterials provided
        if other_materials is None:
            other_materials = []

        # Get assays from study_data - check both locations
        # First check simple format (study_data["assays"])
        # Then check ISA-JSON format (study_data["studies"][0]["assays"])
        raw_assays = self.study_data.get("assays", [])
        if not raw_assays and "studies" in self.study_data:
            # Try to get assays from ISA-JSON format
            if isinstance(self.study_data["studies"], list) and len(self.study_data["studies"]) > 0:
                raw_assays = self.study_data["studies"][0].get("assays", [])

        for assay in raw_assays:
            assay_name = assay.get("name", "")

            # Count occurrences of this assay name
            if assay_name in assay_name_counts:
                assay_name_counts[assay_name] += 1
            else:
                assay_name_counts[assay_name] = 0

            # Generate unique ID with counter
            count = assay_name_counts[assay_name]
            assay_id = f"#assay_{assay_name.replace(' ', '_')}"
            if count > 0:
                assay_id = f"{assay_id}_{count}"

            # Get files for this assay
            # First check if assay already has dataFiles (from previous save)
            if "dataFiles" in assay and assay["dataFiles"]:
                # Preserve existing dataFiles
                assay_files = assay["dataFiles"]
            else:
                # Generate new dataFiles from files field
                assay_files = self._export_assay_files(assay, assay_id)

            # Get process sequence from assay data
            process_sequence = assay.get("processSequence", [])

            # Convert process sequence to ISA-JSON format
            isa_process_sequence = []
            for process in process_sequence:
                # Handle executesProtocol - convert string to Protocol object if needed
                executes_protocol = process.get("executesProtocol", "")
                if isinstance(executes_protocol, str):
                    # Extract protocol name from the URL
                    if executes_protocol.startswith("http"):
                        protocol_name = executes_protocol.split("#prot_")[-1].replace("_", " ")
                    else:
                        protocol_name = executes_protocol
                    # Create minimal Protocol object with relative ID matching BII-S-3.json
                    # Use relative ID format: #protocol/protocol_name
                    protocol_id = (
                        f"#protocol/{protocol_name.replace(' ', '_').replace('-', '_').lower()}"
                    )
                    executes_protocol = {"@id": protocol_id, "name": protocol_name}

                # Get outputs from process
                outputs = self._export_material_references(process.get("outputs", []))

                isa_process = {
                    "@id": process.get("@id", ""),
                    "name": process.get("name", ""),
                    "executesProtocol": executes_protocol,
                    "date": process.get("date", ""),  # ISO8601 format
                    "performer": process.get("performer", ""),  # Optional string
                    # Convert inputs/outputs to object format with @id field
                    "inputs": self._export_material_references(process.get("inputs", [])),
                    "outputs": outputs,
                    "parameterValues": self._export_assay_parameters(assay),
                }
                isa_process_sequence.append(isa_process)

            # If no processSequence exists but we have dataFiles, create a default assay process
            # This follows the ISA-JSON pattern where assays must have processes connecting samples
            # to data
            if not isa_process_sequence and assay_files:
                # Get input samples for this assay
                input_sample_ids = assay.get("inputs", [])
                sample_refs = []
                for inp in input_sample_ids:
                    if isinstance(inp, dict):
                        sample_refs.append(inp)
                    elif isinstance(inp, str):
                        sample_refs.append({"@id": inp})

                # Create a process that connects samples to data files
                # Use a generic assay protocol with relative ID matching BII-S-3.json
                protocol_id = f"assay_{assay_name.replace(' ', '_').replace('-', '_').lower()}"
                assay_protocol_id = f"#protocol/{protocol_id}"

                # Create output references for data files
                data_file_refs = [{"@id": df.get("@id", "")} for df in assay_files if df.get("@id")]

                if sample_refs or data_file_refs:
                    assay_process = {
                        "@id": f"{assay_id}#process_assay",
                        "name": f"{assay_name} assay",
                        "executesProtocol": {
                            "@id": assay_protocol_id,
                            "name": f"assay {assay_name}",
                        },
                        "date": "",
                        "performer": "",
                        "inputs": sample_refs,
                        "outputs": data_file_refs,
                        "parameterValues": self._export_assay_parameters(assay),
                    }
                    isa_process_sequence.append(assay_process)

                    # Add the assay protocol to the list of used protocols if not already present
                    # This will be picked up by _get_assay_protocols
            else:
                # If we have a process sequence and data files, ensure data files are in outputs
                # Add data files to the outputs of the last process if they're not already present
                if assay_files and isa_process_sequence:
                    # Get all existing output IDs from all processes
                    existing_output_ids = set()
                    for proc in isa_process_sequence:
                        for output in proc.get("outputs", []):
                            output_id = output.get("@id", "")
                            if output_id:
                                existing_output_ids.add(output_id)

                    # Add data files that are not already in outputs to the last process
                    last_process = isa_process_sequence[-1]
                    for df in assay_files:
                        file_id = df.get("@id", "")
                        if file_id and file_id not in existing_output_ids:
                            # Add this data file to the last process's outputs
                            if "outputs" not in last_process:
                                last_process["outputs"] = []
                            last_process["outputs"].append({"@id": file_id})

            # Create ISA-JSON assay
            # Get measurement type - always normalize to valid ISA-JSON values
            # Even if measurementType is provided, we need to validate/normalize it
            measurement_type = self._get_measurement_type(assay)

            # Get technology type - always normalize to valid ISA-JSON values
            # Even if technologyType is provided, we need to validate/normalize it
            technology_type = self._get_technology_type(assay)

            # isatools histology config requires empty technology type.
            # Override technology when measurement is "histology" to match the
            # isatools default/histology.json config (measurement='histology', technology='').
            if measurement_type.get("annotationValue") == "histology":
                if technology_type.get("annotationValue", "") != "":
                    technology_type = {"annotationValue": "", "termSource": "", "termAccession": ""}

            # Preserve original semantic types as comments when normalization changes them
            assay_comments: List[Dict[str, str]] = []
            original_meas = ""
            if "measurementType" in assay and isinstance(assay["measurementType"], dict):
                original_meas = assay["measurementType"].get("annotationValue", "")
            if original_meas and original_meas != measurement_type.get("annotationValue", ""):
                assay_comments.append(
                    {
                        "name": "original measurement type",
                        "value": original_meas,
                    }
                )

            original_tech = ""
            if "technologyType" in assay and isinstance(assay["technologyType"], dict):
                original_tech = assay["technologyType"].get("annotationValue", "")
            if original_tech and original_tech != technology_type.get("annotationValue", ""):
                assay_comments.append(
                    {
                        "name": "original technology type",
                        "value": original_tech,
                    }
                )

            # Build assay materials section
            # Per ISA-JSON spec, assays have samples (references to study samples) and
            # otherMaterials
            assay_samples = self._get_assay_sample_references(assay, isa_process_sequence)

            # Collect otherMaterials referenced in assay's process sequence
            assay_other_materials = self._get_assay_process_other_materials(
                isa_process_sequence, other_materials
            )

            # Generate filename for assay (required by ISA-JSON spec)
            # Format: a_{study_id}-{assay_name}.txt (matching BII-S-3.json convention)
            assay_filename = f"a_{self.study_id}-{assay_name.replace(' ', '_')}.txt"

            isa_assay = {
                "@id": assay_id,
                # NOTE: the ISA assay_schema forbids a top-level "name"
                # (additionalProperties: false). Consumers derive the assay
                # display name from @id (see gui/pages/assays.py).
                "measurementType": measurement_type,
                "technologyType": technology_type,
                "dataFiles": assay_files,
                "materials": {"samples": assay_samples, "otherMaterials": assay_other_materials},
                "processSequence": isa_process_sequence,
                "characteristicCategories": [],  # Required by isatools Study.from_dict()
                "unitCategories": [],  # Required by isatools Study.from_dict()
                "filename": assay_filename,  # Required by ISA-JSON spec
            }

            # Add pre-collected comments (original types)
            if assay_comments:
                isa_assay["comments"] = assay_comments

            # Add description to comments if present
            description = assay.get("description", "")
            if description:
                isa_assay.setdefault("comments", []).append(
                    {"name": "description", "value": description}
                )

            assays.append(isa_assay)

        return assays

    def _export_assay_files(self, assay: Dict[str, Any], assay_id: str) -> List[Dict[str, Any]]:
        """
        Export files for an assay in ISA-JSON format.

        Args:
            assay: Assay dictionary
            assay_id: ISA-JSON ID for the assay

        Returns:
            List of file dictionaries in ISA-JSON format
        """
        files = []

        # First, check for files at the assay level (from file_attachment_widget)
        assay_files = assay.get("files", [])

        for file_meta in assay_files:
            # Check if file is already in ISA-JSON format (has @id and @type)
            if "@id" in file_meta and "@type" in file_meta:
                # Already in ISA-JSON format - add directly
                files.append(file_meta)
                continue

            # Add entity_type and entity_id if missing (for ISA-JSON export)
            if "entity_type" not in file_meta:
                file_meta["entity_type"] = "assay"
            if "entity_id" not in file_meta:
                file_meta["entity_id"] = assay.get("name", "")

            # Generate ISA-JSON file reference
            file_reference = self._generate_file_reference(file_meta, assay_id)
            files.append(file_reference)

        # Also check for files at the study level (for backward compatibility)
        study_files = self.study_data.get("files", [])
        assay_name = assay.get("name", "")

        # Filter files for this assay
        for file_meta in study_files:
            if file_meta.get("entity_type") == "assay" and file_meta.get("entity_id") == assay_name:

                # Generate ISA-JSON file reference
                file_reference = self._generate_file_reference(file_meta, assay_id)
                files.append(file_reference)

        return files

    def _generate_file_reference(self, file_meta: Dict[str, Any], entity_id: str) -> Dict[str, Any]:
        """
        Generate an ISA-JSON compliant file reference.

        Args:
            file_meta: File metadata dictionary (can be in ISA-JSON format or internal format)
            entity_id: ISA-JSON ID for the entity (assay or process)

        Returns:
            ISA-JSON compliant file reference dictionary
        """
        # Check if file_meta is already in ISA-JSON format (has @id and @type)
        if "@id" in file_meta and "@type" in file_meta:
            # Already in ISA-JSON format - return as-is, removing invalid properties
            reference = file_meta.copy()
            # Remove properties not allowed by ISA-JSON schema
            reference.pop("path", None)
            reference.pop("generatedBy", None)
            # If fileType exists, convert to type (string enum)
            if "fileType" in reference:
                file_type_ontology = reference.pop("fileType")
                reference["type"] = self._ontology_to_data_type(file_type_ontology)
            return reference

        # Handle internal format (from file_attachment_widget)
        # Determine which path to use (converted if available, else original)
        file_path = (
            file_meta.get("converted_path")
            or file_meta.get("original_path")
            or file_meta.get("file_path", "")
        )

        # Generate ISA-JSON ID
        entity_ref = f"{file_meta.get('entity_type', '')}_{file_meta.get('entity_id', '')}"
        file_id = file_meta.get("file_id", "")
        isa_id = f"#file_{entity_ref}_{file_id[:8] if file_id else ''}"

        # Get file type ontology and convert to ISA-JSON type enum
        file_type = file_meta.get("file_type", "data")
        file_type_ontology = self._get_file_type_ontology(file_type)
        isa_type = self._ontology_to_data_type(file_type_ontology)

        # Build reference - only include properties allowed by ISA-JSON schema
        reference = {
            "@id": isa_id,
            "name": file_meta.get("attachment_name", file_meta.get("original_filename", "unknown")),
            "type": isa_type,
        }

        # Store file path in comments (following BII-S-3.json pattern)
        # Use "TraceDB" as comment name to indicate this is the file path
        if file_path:
            reference.setdefault("comments", []).append({"name": "TraceDB", "value": file_path})

        # Add comments if conversion happened (must be an array of comment objects)
        if file_meta.get("converted_path") or file_meta.get("conversion_status") == "completed":
            original_format = file_meta.get("original_format", "")
            converted_format = file_meta.get("converted_format", "")
            if original_format and converted_format:
                reference.setdefault("comments", []).append(
                    {
                        "name": "description",
                        "value": f"Converted from {original_format} to {converted_format}",
                    }
                )

        return reference

    def _get_file_type_ontology(self, file_type: str) -> Dict[str, str]:
        """
        Get ontology mapping for a file type.

        Args:
            file_type: File type string

        Returns:
            Ontology dictionary
        """
        ontology_map = {
            "image": {
                "annotationValue": "image",
                "termSource": "EDAM",
                "termAccession": "http://edamontology.org/data_3567",
            },
            "data": {
                "annotationValue": "data",
                "termSource": "EDAM",
                "termAccession": "http://edamontology.org/data_0006",
            },
            "sequencing": {
                "annotationValue": "sequence",
                "termSource": "EDAM",
                "termAccession": "http://edamontology.org/data_2044",
            },
            "report": {
                "annotationValue": "report",
                "termSource": "EDAM",
                "termAccession": "http://edamontology.org/data_2531",
            },
        }

        return ontology_map.get(file_type, {"annotationValue": file_type, "termSource": "EDAM"})

    def _ontology_to_data_type(self, ontology: Dict[str, str]) -> str:
        """
        Convert ontology annotation to ISA-JSON Data type enum value.

        The ISA-JSON schema allows these values for the 'type' field:
        - "Raw Data File"
        - "Derived Data File"
        - "Image File"
        - "Acquisition Parameter Data File"
        - "Derived Spectral Data File"
        - "Protein Assignment File"
        - "Raw Spectral Data File"
        - "Peptide Assignment File"
        - "Array Data File"
        - "Derived Array Data File"
        - "Post Translational Modification Assignment File"
        - "Derived Array Data Matrix File"
        - "Free Induction Decay Data File"
        - "Metabolite Assignment File"
        - "Array Data Matrix File"

        Args:
            ontology: Ontology dictionary with annotationValue field

        Returns:
            ISA-JSON compliant type string
        """
        annotation_value = ontology.get("annotationValue", "").lower()

        # Map ontology annotation values to ISA-JSON type enums
        type_map = {
            "image": "Image File",
            "data": "Derived Data File",
            "sequence": "Raw Spectral Data File",
            "report": "Derived Data File",
        }

        return type_map.get(annotation_value, "Derived Data File")

    def _get_technology_type(self, assay: Dict[str, Any]) -> Dict[str, str]:
        """
        Get technology type for an assay.

        Args:
            assay: Assay dictionary

        Returns:
            Technology type dictionary

        Note: ISA-JSON has specific allowed values for technologyType.
        Valid values include: "nucleotide sequencing", "DNA microarray",
        "protein microarray", "gel electrophoresis", "mass spectrometry",
        "NMR spectroscopy", "flow cytometry", "clinical chemistry analysis", etc.
        """
        assay_type = assay.get("assay_type", "").lower()
        assay_name = assay.get("name", "").lower()

        # Also check if technologyType is already provided (from generator or GUI)
        provided_tech_type = ""
        if "technologyType" in assay and isinstance(assay["technologyType"], dict):
            provided_tech_type = assay["technologyType"].get("annotationValue", "").lower()

        # B2 FIX: If the provided technologyType already has a valid OBI
        # accession, pass it through unchanged (same rationale as B1).
        if "technologyType" in assay and isinstance(assay["technologyType"], dict):
            _tt = assay["technologyType"]
            if _tt.get("termAccession") and _tt.get("termSource") == "OBI":
                return _tt

        # Map assay types to valid ISA-JSON technology types
        # These must match the allowed values in the ISA-JSON schema
        technology_map = {
            # SDS-PAGE maps to mass spectrometry (valid for protein work)
            # "gel electrophoresis" is NOT a valid ISA-JSON technology type
            "sds-page": {
                "annotationValue": "mass spectrometry",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000470",
            },
            "gel electrophoresis": {
                "annotationValue": "mass spectrometry",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000470",
            },
            "microscopy": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            "light microscopy": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            # Fluorescence microscopy – pass through with proper ontology annotation
            # so assay technologyType is populated instead of empty.
            "fluorescence microscopy": {
                "annotationValue": "fluorescence microscopy",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000257",
            },
            "fluorometry": {"annotationValue": "", "termSource": "", "termAccession": ""},
            "toxicity test": {
                "annotationValue": "bioassay",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000415",
            },
            "sequencing": {
                "annotationValue": "nucleotide sequencing",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000626",
            },
            "mass spectrometry": {
                "annotationValue": "mass spectrometry",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000470",
            },
            "nmr": {
                "annotationValue": "NMR spectroscopy",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000566",
            },
            "flow cytometry": {
                "annotationValue": "flow cytometry",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000996",
            },
            "protein microarray": {
                "annotationValue": "protein microarray",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0001297",
            },
            "dna microarray": {
                "annotationValue": "DNA microarray",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000456",
            },
            "clinical chemistry": {
                "annotationValue": "clinical chemistry analysis",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000458",
            },
        }

        # Check provided technologyType first (if it's in our map, normalize it)
        if provided_tech_type in technology_map:
            return technology_map[provided_tech_type]

        # Check assay_type
        if assay_type in technology_map:
            return technology_map[assay_type]

        # Check if assay_name contains any known type
        for key, value in technology_map.items():
            if key in assay_name:
                return value

        # Default to a generic valid technology type
        # "bioassay" is a safe default that's accepted by ISA-JSON
        return {
            "annotationValue": "bioassay",
            "termSource": "OBI",
            "termAccession": "http://purl.obolibrary.org/obo/OBI_0000070",
        }

    def _get_measurement_type(self, assay: Dict[str, Any]) -> Dict[str, str]:
        """
        Get measurement type for an assay.

        Args:
            assay: Assay dictionary

        Returns:
            Measurement type dictionary

        Note: ISA-JSON has specific allowed values for measurementType.
        Valid values include: "transcription profiling", "genotyping",
        "protein expression", "metabolite profiling", "cell viability",
        "metagenome sequencing", etc.
        """
        assay_type = assay.get("assay_type", "").lower()
        assay_name = assay.get("name", "").lower()

        # Also check if measurementType is already provided (from generator or GUI)
        provided_meas_type = ""
        if "measurementType" in assay and isinstance(assay["measurementType"], dict):
            provided_meas_type = assay["measurementType"].get("annotationValue", "").lower()

        # B1 FIX: If the provided measurementType already has a valid OBI
        # accession, pass it through unchanged.  This prevents the exporter
        # from overriding semantically correct terms (e.g. "cell death assay")
        # with ISA-JSON configuration fallbacks (e.g. "histology").
        if "measurementType" in assay and isinstance(assay["measurementType"], dict):
            _mt = assay["measurementType"]
            if _mt.get("termAccession") and _mt.get("termSource") == "OBI":
                return _mt

        # Map assay types to valid ISA-JSON measurement types
        # These must match the allowed values in the ISA-JSON schema
        # Order matters: more specific keys should be checked first
        measurement_map = {
            "sds-page": {
                "annotationValue": "protein identification",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0001148",
            },
            "gel electrophoresis": {
                "annotationValue": "protein identification",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0001148",
            },
            "microscopy": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            "toxicity test": {
                "annotationValue": "cell counting",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000061",
            },
            "sequencing": {
                "annotationValue": "transcription profiling",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000424",
            },
            "mass spectrometry": {
                "annotationValue": "metabolite profiling",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000570",
            },
            "nmr": {
                "annotationValue": "metabolite profiling",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000570",
            },
            "flow cytometry": {
                "annotationValue": "cell counting",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000061",
            },
            # Specific assay measurement types used in the project
            "flow cytometry assay": {
                "annotationValue": "cell counting",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000061",
            },
            "facs": {
                "annotationValue": "cell counting",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000061",
            },
            "facs assay": {
                "annotationValue": "cell counting",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000061",
            },
            # Microscopy-based assays map to "histology" measurement type
            # This matches isatools config key ("histology", "") for validation
            "viability assay": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            "calcein": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            "calcein assay": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            "cell counting": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            "dapi": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            "live/dead staining": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            "dapi staining": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            "nuclear staining assay": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            "nuclear staining": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            "fluorescence": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            "fluorescence measurement": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            "toxicity": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
            "toxicity assay": {
                "annotationValue": "histology",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0000112",
            },
        }

        # Check provided measurementType first (if it's in our map, normalize it)
        if provided_meas_type in measurement_map:
            return measurement_map[provided_meas_type]

        # Check assay_type
        if assay_type in measurement_map:
            return measurement_map[assay_type]

        # Check if assay_name contains any known type
        # Sort keys by length (longest first) to match most specific key first
        sorted_keys = sorted(measurement_map.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if key in assay_name:
                return measurement_map[key]

        # Default to a generic valid measurement type
        # "protein expression" is a safe default for protein-related assays
        return {
            "annotationValue": "protein expression",
            "termSource": "OBI",
            "termAccession": "http://purl.obolibrary.org/obo/OBI_0000615",
        }

    def _export_assay_parameters(self, assay: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Export assay parameters.

        Args:
            assay: Assay dictionary

        Returns:
            List of parameter value dictionaries
        """
        # Get raw parameters - can be either a dict or a list
        raw_params = assay.get("parameters", [])

        # Normalize parameters to a list of dicts
        # The GUI stores parameters as a dict: {"param_name": "value"}
        # The exporter expects a list of dicts: [{"name": "param_name", "value": "value"}]
        if isinstance(raw_params, dict):
            # Convert dict format to list format
            normalized_params = []
            for param_name, param_value in raw_params.items():
                normalized_params.append(
                    {
                        "name": param_name,
                        "value": str(param_value) if param_value is not None else "",
                    }
                )
        elif isinstance(raw_params, list):
            # Already in list format - validate each item
            normalized_params = []
            for param in raw_params:
                if isinstance(param, dict):
                    normalized_params.append(param)
                elif isinstance(param, str):
                    # Handle case where list contains strings instead of dicts
                    normalized_params.append({"name": param, "value": ""})
        else:
            normalized_params = []

        parameters = []
        for param in normalized_params:
            param_name = param.get("name", "")

            # Category should only be an @id reference to the parameter defined in protocols
            # Per BII-S-3 reference, parameterValues do NOT have @id on the value object
            param_value = {"category": {"@id": f"#parameter/{param_name.replace(' ', '_')}"}}

            # Handle value - can be numeric with unit, or text value
            value = param.get("value", "")
            unit = param.get("unit", {})
            has_annotation_value = "annotationValue" in param

            # According to ISA-JSON schema, value can be:
            # 1. An ontology annotation (object with annotationValue, termSource, termAccession)
            # 2. A simple string
            # 3. A simple number (optionally with a unit)
            if has_annotation_value:
                # Ontology annotation value
                param_value["value"] = {"annotationValue": param["annotationValue"]}
                if "termSource" in param:
                    param_value["value"]["termSource"] = param["termSource"]
                if "termAccession" in param:
                    param_value["value"]["termAccession"] = param["termAccession"]
            elif value or unit:
                # Simple value (string/number) with optional unit
                if unit and any(unit.values()):
                    # Build unit object with @id following BII-S-3 convention
                    unit_ann = unit.get("annotationValue", "unknown")
                    unit_obj = {
                        "@id": f"#Unit/{unit_ann.replace(' ', '_')}",
                    }
                    if "annotationValue" in unit:
                        unit_obj["annotationValue"] = unit["annotationValue"]
                    if "termSource" in unit:
                        unit_obj["termSource"] = unit["termSource"]
                    if "termAccession" in unit:
                        unit_obj["termAccession"] = unit["termAccession"]

                    if unit_obj:
                        param_value["unit"] = unit_obj
                        # Track unit for unitCategories declaration
                        if not hasattr(self, "_used_unit_categories"):
                            self._used_unit_categories = []
                        unit_id = unit_obj["@id"]
                        if not any(u["@id"] == unit_id for u in self._used_unit_categories):
                            self._used_unit_categories.append(
                                {
                                    "@id": unit_id,
                                    "annotationValue": unit_ann,
                                    "termSource": unit.get("termSource", ""),
                                    "termAccession": unit.get("termAccession", ""),
                                }
                            )

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
                    # else: no value, no unit, no annotation — param_value has only category @id
                    # Still append so the declared protocol parameter is "used" in the process
                    # Ensure every parameterValue has a 'value' key (required by isatools validator)
                    if "value" not in param_value:
                        param_value["value"] = ""

                    parameters.append(param_value)

        return parameters

    def _get_assay_process_other_materials(
        self, process_sequence: List[Dict[str, Any]], base_other_materials: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Get otherMaterials referenced in assay's process sequence.

        Per ISA-JSON spec, assay materials.otherMaterials contains materials that are
        referenced in the assay's process sequence but not in study-level materials.

        Args:
            process_sequence: The assay's process sequence
            base_other_materials: List of otherMaterials to include from assay data

        Returns:
            List of otherMaterial reference dictionaries with @id
        """
        other_material_refs = []

        # Collect otherMaterial IDs from process inputs and outputs
        for process in process_sequence:
            # Check inputs
            for input_ref in process.get("inputs", []):
                if isinstance(input_ref, dict):
                    input_id = input_ref.get("@id", "")
                    # Check if this is an otherMaterial reference
                    if input_id and (
                        "#material_" in input_id
                        or "#otherMaterial_" in input_id
                        or "/otherMaterial_" in input_id
                    ):
                        other_material_refs.append({"@id": input_id})
                elif isinstance(input_ref, str):
                    if (
                        "#material_" in input_ref
                        or "#otherMaterial_" in input_ref
                        or "/otherMaterial_" in input_id
                    ):
                        other_material_refs.append({"@id": input_id})

            # Check outputs
            for output_ref in process.get("outputs", []):
                if isinstance(output_ref, dict):
                    output_id = output_ref.get("@id", "")
                    # Check if this is an otherMaterial reference
                    if output_id and (
                        "#material_" in output_id
                        or "#otherMaterial_" in output_id
                        or "/otherMaterial_" in output_id
                    ):
                        other_material_refs.append({"@id": output_id})
                elif isinstance(output_ref, str):
                    if (
                        "#material_" in output_ref
                        or "#otherMaterial_" in output_id
                        or "/otherMaterial_" in output_id
                    ):
                        other_material_refs.append({"@id": output_id})

        # Add base otherMaterials from assay data
        for mat in base_other_materials:
            mat_id = mat.get("@id", "")
            if mat_id:
                other_material_refs.append({"@id": mat_id})

        # Remove duplicates while preserving order
        seen_ids = set()
        unique_refs = []
        for ref in other_material_refs:
            ref_id = ref.get("@id", "")
            if ref_id not in seen_ids:
                seen_ids.add(ref_id)
                unique_refs.append(ref)

        return unique_refs

    def _get_assay_sample_references(
        self, assay: Dict[str, Any], process_sequence: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Get sample references for an assay based on process sequence inputs.

        Per ISA-JSON spec, assay materials.samples contains references to study-level samples
        that are used as inputs in the assay's process sequence.

        Args:
            assay: Assay dictionary
            process_sequence: The assay's process sequence

        Returns:
            List of sample reference dictionaries with @id
        """
        sample_refs = []

        # Collect sample IDs from process inputs
        for process in process_sequence:
            inputs = process.get("inputs", [])
            for input_ref in inputs:
                if isinstance(input_ref, dict):
                    input_id = input_ref.get("@id", "")
                    # Check if this is a sample reference (contains "/sample/" or "#sample_" in the
                    # ID)
                    if input_id and (
                        "/sample/" in input_id
                        or "#sample_" in input_id
                        or input_id.startswith("#sample/")
                    ):
                        sample_refs.append({"@id": input_id})
                elif isinstance(input_ref, str):
                    if (
                        "/sample/" in input_ref
                        or "#sample_" in input_ref
                        or input_ref.startswith("#sample/")
                    ):
                        sample_refs.append({"@id": input_ref})

        # Remove duplicates while preserving order
        seen_ids = set()
        unique_refs = []
        for ref in sample_refs:
            ref_id = ref.get("@id", "")
            if ref_id not in seen_ids:
                seen_ids.add(ref_id)
                unique_refs.append(ref)

        return unique_refs
