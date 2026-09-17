"""Tests for GraphBuilder in utils/graph_builder.py.

Covers:
  - GraphBuilder.__init__
  - _get_category_for_term
  - extract_subclass_relations
  - extract_exactmatch_relations
  - extract_closematch_relations
  - extract_io_relations
  - extract_nodes
  - build_graph_data
  - calculate_force_directed_layout
  - _resolve_external_label
"""

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from utils.graph_builder import PROJECT_NS, GraphBuilder

# ---------------------------------------------------------------------------
# Helpers to build small test graphs
# ---------------------------------------------------------------------------


def _make_simple_graph():
    """Create a small RDF graph with a few project classes and relationships."""
    g = Graph()

    # Bind namespaces
    g.bind("onto", PROJECT_NS)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("skos", SKOS)

    # Define some project classes
    class_a = PROJECT_NS["ClassA"]
    class_b = PROJECT_NS["ClassB"]
    class_c = PROJECT_NS["ProcessX"]
    external = URIRef("http://purl.obolibrary.org/obo/OBI_0000001")

    # ClassA is an OWL:Class with label
    g.add((class_a, RDF.type, OWL.Class))
    g.add((class_a, RDFS.label, Literal("Class A")))
    g.add((class_a, RDFS.subClassOf, class_b))

    # ClassB is an OWL:Class
    g.add((class_b, RDF.type, OWL.Class))
    g.add((class_b, RDFS.label, Literal("Class B")))

    # ProcessX is an OWL:Class
    g.add((class_c, RDF.type, OWL.Class))
    g.add((class_c, RDFS.label, Literal("Process X")))
    g.add((class_c, RDFS.subClassOf, URIRef("http://pmdontology.org/co/ManufacturingProcess")))

    # External match
    g.add((class_a, SKOS.exactMatch, external))

    # Close match
    g.add((class_b, SKOS.closeMatch, URIRef("http://purl.obolibrary.org/obo/UO_0000001")))

    # I/O relations
    g.add((class_c, PROJECT_NS.hasInput, class_a))
    g.add((class_c, PROJECT_NS.hasOutput, class_b))

    return g


def _make_empty_graph():
    """Create an empty RDF graph."""
    return Graph()


def _make_graph_with_materials():
    """Create a graph with material-like classes."""
    g = Graph()
    g.bind("onto", PROJECT_NS)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)

    # Material-like class (subClassOf Sample)
    sample_class = PROJECT_NS["CellPellet"]
    g.add((sample_class, RDF.type, OWL.Class))
    g.add((sample_class, RDFS.label, Literal("Cell Pellet")))
    g.add((sample_class, RDFS.subClassOf, URIRef("http://pmdontology.org/co/Sample")))

    return g


# ---------------------------------------------------------------------------
# GraphBuilder.__init__ tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGraphBuilderInit:
    """Tests for GraphBuilder initialization."""

    def test_init_with_graph(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        assert gb.graph is g
        assert isinstance(gb.category_map, dict)
        assert isinstance(gb.category_patterns, dict)

    def test_category_map_keys(self):
        gb = GraphBuilder(_make_empty_graph())
        expected_keys = {
            "Materials",
            "Processes",
            "Protocols",
            "Assays",
            "Parameters",
            "DataFiles",
            "External",
            "Devices",
        }
        assert set(gb.category_map.keys()) == expected_keys


# ---------------------------------------------------------------------------
# _get_category_for_term tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetCategoryForTerm:
    """Tests for _get_category_for_term."""

    def test_material_via_parent(self):
        g = _make_graph_with_materials()
        gb = GraphBuilder(g)
        cat = gb._get_category_for_term(str(PROJECT_NS["CellPellet"]))
        assert cat == "Materials"

    def test_process_via_parent(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        cat = gb._get_category_for_term(str(PROJECT_NS["ProcessX"]))
        assert cat == "Processes"

    def test_external_uri(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        cat = gb._get_category_for_term("http://purl.obolibrary.org/obo/OBI_0000001")
        assert cat == "External"

    def test_onto_term_name_pattern_fallback(self):
        """Test that project terms without hierarchy fall back to name patterns."""
        g = Graph()
        g.bind("owl", OWL)
        g.bind("rdfs", RDFS)
        # A project term with 'toxicity' in the name but no subClassOf
        # (avoid 'calcein' which matches Materials patterns)
        uri = PROJECT_NS["toxicity_test"]
        g.add((uri, RDF.type, OWL.Class))
        g.add((uri, RDFS.label, Literal("Toxicity Test")))

        gb = GraphBuilder(g)
        cat = gb._get_category_for_term(str(PROJECT_NS["toxicity_test"]))
        assert cat == "Assays"

    def test_onto_term_with_device_pattern(self):
        g = Graph()
        g.bind("owl", OWL)
        g.bind("rdfs", RDFS)
        uri = PROJECT_NS["centrifuge_device"]
        g.add((uri, RDF.type, OWL.Class))

        gb = GraphBuilder(g)
        cat = gb._get_category_for_term(str(PROJECT_NS["centrifuge_device"]))
        assert cat == "Devices"

    def test_onto_term_with_parameter_pattern(self):
        g = Graph()
        g.bind("owl", OWL)
        g.bind("rdfs", RDFS)
        uri = PROJECT_NS["temperature_value"]
        g.add((uri, RDF.type, OWL.Class))

        gb = GraphBuilder(g)
        cat = gb._get_category_for_term(str(PROJECT_NS["temperature_value"]))
        assert cat == "Parameters"

    def test_unknown_onto_term_defaults_to_materials(self):
        g = Graph()
        g.bind("owl", OWL)
        g.bind("rdfs", RDFS)
        uri = PROJECT_NS["UnknownThing"]
        g.add((uri, RDF.type, OWL.Class))

        gb = GraphBuilder(g)
        cat = gb._get_category_for_term(str(PROJECT_NS["UnknownThing"]))
        assert cat == "Materials"


# ---------------------------------------------------------------------------
# extract_subclass_relations tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractSubclassRelations:
    """Tests for extract_subclass_relations."""

    def test_extracts_onto_subclasses(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        edges = gb.extract_subclass_relations("All")
        # ClassA subClassOf ClassB, ProcessX subClassOf ManufacturingProcess
        assert len(edges) >= 1
        sources = [e["source"] for e in edges]
        assert str(PROJECT_NS["ClassA"]) in sources
        for e in edges:
            assert e["relation"] == "subClassOf"

    def test_empty_graph(self):
        gb = GraphBuilder(_make_empty_graph())
        edges = gb.extract_subclass_relations("All")
        assert edges == []


# ---------------------------------------------------------------------------
# extract_exactmatch_relations tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractExactmatchRelations:
    """Tests for extract_exactmatch_relations."""

    def test_extracts_exact_matches(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        edges = gb.extract_exactmatch_relations()
        assert len(edges) >= 1
        for e in edges:
            assert e["relation"] == "exactMatch"
            assert e["source"].startswith(str(PROJECT_NS))

    def test_empty_graph(self):
        gb = GraphBuilder(_make_empty_graph())
        edges = gb.extract_exactmatch_relations()
        assert edges == []


# ---------------------------------------------------------------------------
# extract_closematch_relations tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractClosematchRelations:
    """Tests for extract_closematch_relations."""

    def test_extracts_close_matches(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        edges = gb.extract_closematch_relations()
        assert len(edges) >= 1
        for e in edges:
            assert e["relation"] == "closeMatch"

    def test_empty_graph(self):
        gb = GraphBuilder(_make_empty_graph())
        edges = gb.extract_closematch_relations()
        assert edges == []


# ---------------------------------------------------------------------------
# extract_io_relations tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractIoRelations:
    """Tests for extract_io_relations."""

    def test_extracts_io_relations(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        edges = gb.extract_io_relations()
        relations = {e["relation"] for e in edges}
        assert "hasInput" in relations
        assert "hasOutput" in relations

    def test_empty_graph(self):
        gb = GraphBuilder(_make_empty_graph())
        edges = gb.extract_io_relations()
        assert edges == []


# ---------------------------------------------------------------------------
# extract_nodes tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractNodes:
    """Tests for extract_nodes."""

    def test_extracts_onto_nodes(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        nodes = gb.extract_nodes()
        uris = {n["uri"] for n in nodes}
        assert str(PROJECT_NS["ClassA"]) in uris
        assert str(PROJECT_NS["ClassB"]) in uris
        assert str(PROJECT_NS["ProcessX"]) in uris

    def test_nodes_have_labels(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        nodes = gb.extract_nodes()
        for n in nodes:
            assert "label" in n
            assert "type" in n
            assert "category" in n

    def test_filter_by_category(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        nodes = gb.extract_nodes(category="Processes")
        for n in nodes:
            assert n["category"] == "Processes"

    def test_empty_graph(self):
        gb = GraphBuilder(_make_empty_graph())
        nodes = gb.extract_nodes()
        assert nodes == []


# ---------------------------------------------------------------------------
# build_graph_data tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildGraphData:
    """Tests for build_graph_data."""

    def test_returns_nodes_and_edges(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        data = gb.build_graph_data("All")
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    def test_nodes_have_required_keys(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        data = gb.build_graph_data("All")
        for node in data["nodes"]:
            assert "uri" in node
            assert "label" in node
            assert "type" in node

    def test_edges_have_required_keys(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        data = gb.build_graph_data("All")
        for edge in data["edges"]:
            assert "source" in edge
            assert "target" in edge
            assert "relation" in edge

    def test_filter_by_category(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        data = gb.build_graph_data("Processes")
        for node in data["nodes"]:
            assert node["category"] == "Processes"

    def test_empty_graph(self):
        gb = GraphBuilder(_make_empty_graph())
        data = gb.build_graph_data("All")
        assert data["nodes"] == []
        assert data["edges"] == []

    def test_external_parent_nodes_added(self):
        """External parent URIs from edges should be added as nodes."""
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        data = gb.build_graph_data("All")
        # The ManufacturingProcess parent should be added as an external node
        external_uris = [n["uri"] for n in data["nodes"] if n["type"] == "External"]
        # At least the ManufacturingProcess should be there
        assert len(external_uris) >= 1


# ---------------------------------------------------------------------------
# calculate_force_directed_layout tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCalculateForceDirectedLayout:
    """Tests for calculate_force_directed_layout."""

    def test_returns_positions_for_all_nodes(self):
        g = _make_simple_graph()
        gb = GraphBuilder(g)
        nodes = [
            {"uri": "a", "label": "A", "type": "Material", "category": "Materials"},
            {"uri": "b", "label": "B", "type": "Material", "category": "Materials"},
        ]
        edges = [{"source": "a", "target": "b", "relation": "subClassOf"}]
        positions = gb.calculate_force_directed_layout(nodes, edges)
        assert "a" in positions
        assert "b" in positions
        assert len(positions["a"]) == 2  # (x, y)

    def test_single_node(self):
        g = _make_empty_graph()
        gb = GraphBuilder(g)
        nodes = [{"uri": "x", "label": "X", "type": "Term", "category": "Materials"}]
        positions = gb.calculate_force_directed_layout(nodes, [])
        assert "x" in positions

    def test_empty_graph_layout(self):
        g = _make_empty_graph()
        gb = GraphBuilder(g)
        positions = gb.calculate_force_directed_layout([], [])
        assert positions == {}

    def test_positions_are_tuples(self):
        g = _make_empty_graph()
        gb = GraphBuilder(g)
        nodes = [
            {"uri": "n1", "label": "N1", "type": "Term", "category": "Materials"},
            {"uri": "n2", "label": "N2", "type": "Term", "category": "Materials"},
        ]
        positions = gb.calculate_force_directed_layout(nodes, [], iterations=10)
        for uri, pos in positions.items():
            assert isinstance(pos, tuple)
            assert len(pos) == 2
            assert isinstance(pos[0], float)
            assert isinstance(pos[1], float)

    def test_iterations_parameter(self):
        """More iterations should still produce valid positions."""
        g = _make_empty_graph()
        gb = GraphBuilder(g)
        nodes = [
            {"uri": "a", "label": "A", "type": "Term", "category": "Materials"},
            {"uri": "b", "label": "B", "type": "Term", "category": "Materials"},
        ]
        positions = gb.calculate_force_directed_layout(nodes, [], iterations=200)
        assert len(positions) == 2


# ---------------------------------------------------------------------------
# _resolve_external_label tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveExternalLabel:
    """Tests for _resolve_external_label."""

    def test_hash_uri(self):
        g = _make_empty_graph()
        gb = GraphBuilder(g)
        # Reset class-level cache to avoid cross-test pollution
        if hasattr(GraphBuilder, "_external_label_cache"):
            GraphBuilder._external_label_cache = {}
            GraphBuilder._external_label_loaded = True
        label = gb._resolve_external_label("http://example.org/onto#MyTerm")
        assert label == "MyTerm"

    def test_slash_uri(self):
        g = _make_empty_graph()
        gb = GraphBuilder(g)
        if hasattr(GraphBuilder, "_external_label_cache"):
            GraphBuilder._external_label_cache = {}
            GraphBuilder._external_label_loaded = True
        label = gb._resolve_external_label("http://example.org/onto/MyTerm")
        assert label == "MyTerm"

    def test_obo_style_id(self):
        g = _make_empty_graph()
        gb = GraphBuilder(g)
        if hasattr(GraphBuilder, "_external_label_cache"):
            GraphBuilder._external_label_cache = {}
            GraphBuilder._external_label_loaded = True
        label = gb._resolve_external_label("http://purl.obolibrary.org/obo/OBI_0000425")
        assert label == "OBI:0000425"

    def test_uo_style_id(self):
        g = _make_empty_graph()
        gb = GraphBuilder(g)
        if hasattr(GraphBuilder, "_external_label_cache"):
            GraphBuilder._external_label_cache = {}
            GraphBuilder._external_label_loaded = True
        label = gb._resolve_external_label("http://purl.obolibrary.org/obo/UO_0000002")
        assert label == "UO:0000002"
