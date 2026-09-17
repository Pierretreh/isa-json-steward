"""
Graph Builder for Ontology Visualization.

Extracts nodes and edges from the project ontology RDF graph for visualization
in the GUI's graph widget.

Extracts the following relationship types:
- rdfs:subClassOf (class hierarchy)
- skos:closeMatch (external ontology alignment)
- skos:exactMatch (external ontology alignment)
- hasInput / hasOutput (process I/O)
- hasParameter (process parameters)
- hasExpectedFormat (data file formats)
"""

from typing import Dict, List, Optional

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDFS, SKOS

from utils.config_loader import get_profile


def _get_project_namespace() -> Namespace:
    """Return the project ontology namespace from the active profile."""
    return Namespace(get_profile().get_namespace())


# Project ontology namespace (loaded from profile)
PROJECT_NS = _get_project_namespace()


class GraphBuilder:
    """Builder for creating graph data structures from ontology RDF graphs."""

    # Class-level label cache, shared across all instances (built lazily)
    _external_label_cache: Dict[str, str] = {}
    _external_label_loaded: bool = False

    def __init__(self, ontology_graph: Graph):
        """
        Initialize the graph builder.

        Args:
            ontology_graph: The RDFLib Graph containing the ontology.
        """
        self.graph = ontology_graph
        self.category_map = {
            "Materials": "Material",
            "Processes": "Process",
            "Protocols": "Process",
            "Assays": "Assay",
            "Parameters": "Parameter",
            "DataFiles": "DataFile",
            "External": "External",
            "Devices": "Device",
        }

        # Category patterns for URI-based classification (fallback)
        self.category_patterns = {
            "Materials": [
                "cells",
                "dna",
                "bacteria",
                "culture",
                "pellet",
                "lysate",
                "supernatant",
                "fraction",
                "solution",
                "depot",
                "collagen",
                "column",
                "wash",
                "elution",
                "protein",
                "buffer",
                "medium",
                "inductor",
                "dilutant",
                "anti",
                "vegf",
                "protease",
                "dialysis",
                "membrane",
                "agarose",
                "ethidium",
                "calcein",
                "dapi",
                "tunel",
            ],
            "Processes": [
                "transformation",
                "expression",
                "harvesting",
                "addition",
                "lysis",
                "centrifugation",
                "division",
                "dilution",
                "digestion",
                "purification",
                "dialysis",
                "assembly",
                "sequencing",
                "monitoring",
                "weighing",
                "resuspension",
                "staining",
                "microscopy",
                "electroporation",
            ],
            "Assays": [
                "assay",
                "test",
                "staining",
                "gel",
                "sequencing",
                "monitoring",
                "weighing",
                "microscopy",
                "toxicity",
                "tunel",
                "sds",
                "page",
            ],
            "Parameters": [
                "temperature",
                "time",
                "volume",
                "concentration",
                "ph",
                "od",
                "speed",
                "amount",
                "duration",
                "finish",
                "planned",
                "sonication",
                "type",
                "number",
                "mw",
                "raw",
                "conc",
                "image",
                "band",
                "categorical",
                "fluence",
                "result",
                "res",
            ],
            "Devices": [
                "device",
                "machine",
                "instrument",
                "centrifuge",
                "sonicator",
                "spectrophotometer",
                "microscope",
                "electrophoresis",
                "illuminator",
                "incubator",
                "balance",
                "spectrometer",
                "cellsorter",
            ],
        }

    def _resolve_external_label(self, uri: str) -> str:
        """
        Resolve a human-readable label for an external ontology URI.

        Uses a pre-loaded label cache (built once from cached ontology files)
        with URI-parsing fallback for uncached URIs.

        Args:
            uri: The external ontology URI.

        Returns:
            A human-readable label string.
        """
        # Build label cache once (class-level, shared across instances)
        if not hasattr(GraphBuilder, "_external_label_cache"):
            GraphBuilder._external_label_cache = {}
            GraphBuilder._external_label_loaded = False

        # Load all labels from cached ontologies once
        if not GraphBuilder._external_label_loaded:
            GraphBuilder._external_label_loaded = True
            self._preload_external_labels()

        # Try cache
        if uri in GraphBuilder._external_label_cache:
            return GraphBuilder._external_label_cache[uri]

        # Fallback: extract readable name from URI
        if "#" in uri:
            label = uri.split("#")[-1]
        else:
            label = uri.split("/")[-1]

        # Clean up OBO-style IDs (e.g., OBI_0000425 → OBI:0000425)
        if label.startswith(("OBI_", "UO_", "CHEBI_", "NCBITaxon_", "PATO_", "EFO_")):
            prefix = label.split("_")[0]
            number = label[len(prefix) + 1 :]
            label = f"{prefix}:{number}"

        GraphBuilder._external_label_cache[uri] = label
        return label

    def _preload_external_labels(self):
        """
        Pre-load all rdfs:label entries from cached ontology files.
        Only loads files under 50MB. Results are cached at the class level.
        """
        from pathlib import Path

        cache_dir = Path(__file__).parent.parent / "ontologies" / "cached"

        ontology_files = [
            ("obi.owl", "xml"),
            ("uo.owl", "xml"),
            ("pmd_co_3.1.0.owl", "xml"),
        ]

        for filename, fmt in ontology_files:
            file_path = cache_dir / filename
            if not file_path.exists():
                continue

            # Skip very large files
            if file_path.stat().st_size > 50 * 1024 * 1024:
                continue

            try:
                from rdflib import Graph as RdfGraph

                g = RdfGraph()
                g.parse(str(file_path), format=fmt)

                count = 0
                for s, p, o in g.triples((None, RDFS.label, None)):
                    GraphBuilder._external_label_cache[str(s)] = str(o)
                    count += 1

            except Exception:
                pass

    def _get_category_for_term(self, uri: str) -> str:
        """
        Determine the category for a term using the ontology's class hierarchy.

        Checks rdfs:subClassOf relationships in the graph to determine category,
        with name-pattern fallback for terms without clear hierarchy.

        Args:
            uri: The URI of the ontology term

        Returns:
            The category name (default: "Materials")
        """
        uri_ref = URIRef(uri)

        # Check rdfs:subClassOf chain to determine category
        try:
            parents = [str(o) for s, p, o in self.graph.triples((uri_ref, RDFS.subClassOf, None))]
        except Exception:
            parents = []

        for parent in parents:
            parent_lower = parent.lower()
            # Material hierarchy (PMDco Sample, Source, OtherMaterial)
            if any(m in parent_lower for m in ["sample", "source", "othermaterial"]):
                return "Materials"
            # Process hierarchy (PMDco ManufacturingProcess)
            if "manufacturingprocess" in parent_lower:
                return "Processes"
            # Assay hierarchy — OBI terms (OBI_*) or PMDco assay
            if parent.startswith("http://purl.obolibrary.org/obo/OBI_"):
                return "Assays"
            if "pmd/co/assay" in parent_lower:
                return "Assays"
            # Data file hierarchy
            if any(
                d in parent_lower for d in ["datafile", "obi_0000031", "obi_0000021", "obi_0000973"]
            ):
                return "DataFiles"

        # Check if it's an external URI (not from the project ontology)
        ns_uri = get_profile().get_namespace()
        if not uri.startswith(ns_uri):
            return "External"

        # Fallback to name patterns for project terms without clear hierarchy
        term_name = uri.split("#")[-1].lower()

        for category, patterns in self.category_patterns.items():
            if any(pattern in term_name for pattern in patterns):
                return category

        return "Materials"

    def extract_subclass_relations(self, category: str) -> List[Dict[str, str]]:
        """
        Extract rdfs:subClassOf relationships.

        Returns:
            List of edge dictionaries with source, target, and relation.
        """
        edges = []
        ns_uri = get_profile().get_namespace()

        for s, p, o in self.graph.triples((None, RDFS.subClassOf, None)):
            s_str = str(s)
            o_str = str(o)

            if not s_str.startswith(ns_uri):
                continue

            edges.append({"source": s_str, "target": o_str, "relation": "subClassOf"})

        return edges

    def extract_exactmatch_relations(self) -> List[Dict[str, str]]:
        """
        Extract skos:exactMatch relationships.

        Returns:
            List of edge dictionaries with source, target, and relation.
        """
        edges = []
        ns_uri = get_profile().get_namespace()

        for s, p, o in self.graph.triples((None, SKOS.exactMatch, None)):
            s_str = str(s)
            o_str = str(o)

            if s_str.startswith(ns_uri):
                edges.append({"source": s_str, "target": o_str, "relation": "exactMatch"})

        return edges

    def extract_closematch_relations(self) -> List[Dict[str, str]]:
        """
        Extract skos:closeMatch relationships.

        Returns:
            List of edge dictionaries with source, target, and relation.
        """
        edges = []
        ns_uri = get_profile().get_namespace()

        for s, p, o in self.graph.triples((None, SKOS.closeMatch, None)):
            s_str = str(s)
            o_str = str(o)

            if s_str.startswith(ns_uri):
                edges.append({"source": s_str, "target": o_str, "relation": "closeMatch"})

        return edges

    def extract_io_relations(self) -> List[Dict[str, str]]:
        """
        Extract hasInput, hasOutput, hasParameter, and hasExpectedFormat relationships.

        Returns:
            List of edge dictionaries with source, target, and relation.
        """
        edges = []
        ns_uri = get_profile().get_namespace()

        io_properties = [
            (PROJECT_NS.hasInput, "hasInput"),
            (PROJECT_NS.hasOutput, "hasOutput"),
            (PROJECT_NS.hasParameter, "hasParameter"),
            (PROJECT_NS.hasExpectedFormat, "hasExpectedFormat"),
        ]

        for prop, relation_name in io_properties:
            for s, p, o in self.graph.triples((None, prop, None)):
                s_str = str(s)
                o_str = str(o)

                if s_str.startswith(ns_uri):
                    edges.append({"source": s_str, "target": o_str, "relation": relation_name})

        return edges

    def extract_nodes(self, category: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Extract all nodes (OWL classes) from the ontology.

        Args:
            category: Optional filter for specific category. If None, all nodes
                      are extracted with their auto-detected categories.

        Returns:
            List of node dictionaries with uri, label, type, and category.
        """
        from rdflib import OWL

        nodes = []

        ns_uri = get_profile().get_namespace()
        for s in self.graph.subjects(None, OWL.Class):
            s_str = str(s)

            if not s_str.startswith(ns_uri):
                continue

            labels = list(self.graph.objects(s, RDFS.label))
            label = str(labels[0]) if labels else s_str.split("#")[-1]

            node_category = self._get_category_for_term(s_str)

            if category is not None and node_category != category:
                continue

            node_type = self.category_map.get(node_category, "Term")

            nodes.append(
                {"uri": s_str, "label": label, "type": node_type, "category": node_category}
            )

        return nodes

    def build_graph_data(self, category: str) -> Dict[str, List[Dict[str, str]]]:
        """
        Build complete graph data structure for a category.

        Args:
            category: The ontology category to build graph for.

        Returns:
            Dictionary with "nodes" and "edges" lists.
        """
        nodes = self.extract_nodes(None if category == "All" else category)

        # Extract all edge types
        edges = []
        edges.extend(self.extract_subclass_relations(category))
        edges.extend(self.extract_exactmatch_relations())
        edges.extend(self.extract_closematch_relations())
        edges.extend(self.extract_io_relations())

        # Collect external parent URIs from edges
        node_uris = {node["uri"] for node in nodes}
        ns_uri = get_profile().get_namespace()
        external_parent_uris = set()
        for edge in edges:
            if edge["source"] in node_uris and edge["target"] not in node_uris:
                # Only add truly external URIs (not project-internal terms)
                if not edge["target"].startswith(ns_uri):
                    external_parent_uris.add(edge["target"])

        # Add external parent nodes with resolved labels
        for uri in external_parent_uris:
            # Try to get label from the project ontology graph
            labels = list(self.graph.objects(URIRef(uri), RDFS.label))
            label = str(labels[0]) if labels else ""

            # If no label found, extract a human-readable name from the URI
            if not label:
                label = self._resolve_external_label(uri)

            source_category = "default"
            for edge in edges:
                if edge["target"] == uri and edge["source"] in node_uris:
                    for node in nodes:
                        if node["uri"] == edge["source"]:
                            source_category = node["category"]
                            break
                    break

            nodes.append(
                {"uri": uri, "label": label, "type": "External", "category": source_category}
            )

        # Filter edges to only include nodes that exist
        node_uris = {node["uri"] for node in nodes}
        filtered_edges = [
            edge for edge in edges if edge["source"] in node_uris and edge["target"] in node_uris
        ]

        return {"nodes": nodes, "edges": filtered_edges}

    def calculate_force_directed_layout(
        self, nodes: List[Dict[str, str]], edges: List[Dict[str, str]], iterations: int = 50
    ) -> Dict[str, tuple]:
        """
        Calculate node positions using a simple force-directed layout algorithm.

        Args:
            nodes: List of node dictionaries.
            edges: List of edge dictionaries.
            iterations: Number of iterations for the algorithm.

        Returns:
            Dictionary mapping node URIs to (x, y) positions.
        """
        import math
        import random

        positions = {}
        for node in nodes:
            positions[node["uri"]] = (random.uniform(-300, 300), random.uniform(-300, 300))

        adjacency: Dict[str, List[str]] = {}
        for edge in edges:
            source = edge["source"]
            target = edge["target"]
            if source not in adjacency:
                adjacency[source] = []
            if target not in adjacency:
                adjacency[target] = []
            adjacency[source].append(target)
            if edge["relation"] == "subClassOf":
                adjacency[target].append(source)

        k = 100
        repulsion_strength = 50000
        attraction_strength = 0.01
        damping = 0.9

        for _ in range(iterations):
            forces = {uri: (0.0, 0.0) for uri in positions}

            for i, uri_i in enumerate(positions):
                for j, uri_j in enumerate(positions):
                    if i >= j:
                        continue

                    xi, yi = positions[uri_i]
                    xj, yj = positions[uri_j]

                    dx = xi - xj
                    dy = yi - yj
                    dist = max(math.sqrt(dx * dx + dy * dy), 0.1)

                    repulsion = repulsion_strength / (dist * dist)
                    fx = repulsion * dx / dist
                    fy = repulsion * dy / dist

                    forces[uri_i] = (forces[uri_i][0] + fx, forces[uri_i][1] + fy)
                    forces[uri_j] = (forces[uri_j][0] - fx, forces[uri_j][1] - fy)

            for uri in positions:
                if uri in adjacency:
                    for neighbor in adjacency[uri]:
                        if neighbor in positions:
                            xi, yi = positions[uri]
                            xj, yj = positions[neighbor]

                            dx = xj - xi
                            dy = yj - yi
                            dist = max(math.sqrt(dx * dx + dy * dy), 0.1)

                            attraction = attraction_strength * (dist - k)
                            fx = attraction * dx / dist
                            fy = attraction * dy / dist

                            forces[uri] = (forces[uri][0] + fx, forces[uri][1] + fy)

            for uri in positions:
                fx, fy = forces[uri]
                x, y = positions[uri]
                positions[uri] = (x + fx * damping, y + fy * damping)

        return positions
