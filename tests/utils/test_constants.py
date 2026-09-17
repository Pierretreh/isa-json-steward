"""
Unit tests for utils.constants.

These tests verify that the constant classes exist, are instantiable,
and that the key constants have the expected types and sane values.
"""

from typing import List, Type

import pytest

from utils.constants import (
    FileConstants,
    ISAJsonConstants,
    OntologyConstants,
    TemplateConstants,
    UIConstants,
    ValidationConstants,
)

ALL_CONSTANT_CLASSES: List[Type] = [
    UIConstants,
    FileConstants,
    OntologyConstants,
    ISAJsonConstants,
    ValidationConstants,
    TemplateConstants,
]


@pytest.mark.unit
class TestConstantClassesExist:
    """Verify all constant classes exist and can be instantiated."""

    @pytest.mark.parametrize("cls", ALL_CONSTANT_CLASSES, ids=lambda c: c.__name__)
    def test_class_exists(self, cls):
        """Each constant class is defined and is a class."""
        assert isinstance(cls, type)
        assert cls.__name__

    @pytest.mark.parametrize("cls", ALL_CONSTANT_CLASSES, ids=lambda c: c.__name__)
    def test_instantiable(self, cls):
        """Each constant class can be instantiated without arguments."""
        instance = cls()
        assert isinstance(instance, cls)


@pytest.mark.unit
class TestUIConstants:
    """Verify UIConstants values are sane."""

    def test_window_dimensions_are_positive_ints(self):
        """Window dimension constants are positive integers."""
        for value in (
            UIConstants.MIN_WINDOW_WIDTH,
            UIConstants.MIN_WINDOW_HEIGHT,
            UIConstants.DEFAULT_WINDOW_WIDTH,
            UIConstants.DEFAULT_WINDOW_HEIGHT,
        ):
            assert isinstance(value, int)
            assert value > 0

    def test_default_window_is_larger_than_min(self):
        """The default window size is not smaller than the minimum size."""
        assert UIConstants.DEFAULT_WINDOW_WIDTH >= UIConstants.MIN_WINDOW_WIDTH
        assert UIConstants.DEFAULT_WINDOW_HEIGHT >= UIConstants.MIN_WINDOW_HEIGHT

    def test_sidebar_and_dialogs_are_positive(self):
        """Sidebar and dialog dimension constants are positive integers."""
        for value in (
            UIConstants.SIDEBAR_WIDTH,
            UIConstants.SIDEBAR_ITEM_HEIGHT,
            UIConstants.DIALOG_MIN_WIDTH,
            UIConstants.DIALOG_MIN_HEIGHT,
            UIConstants.WIZARD_MIN_WIDTH,
            UIConstants.WIZARD_MIN_HEIGHT,
        ):
            assert isinstance(value, int)
            assert value > 0

    def test_timeouts_are_positive_milliseconds(self):
        """Timeout constants are positive integers (milliseconds)."""
        for value in (
            UIConstants.AUTO_SAVE_TIMEOUT,
            UIConstants.MESSAGE_TIMEOUT,
            UIConstants.STATUS_MESSAGE_TIMEOUT,
        ):
            assert isinstance(value, int)
            assert value > 0

    def test_spacing_values_are_ordered(self):
        """Spacing constants increase from small to xl."""
        assert (
            UIConstants.SPACING_SMALL
            < UIConstants.SPACING_MEDIUM
            < UIConstants.SPACING_LARGE
            < UIConstants.SPACING_XLARGE
        )

    def test_icon_and_font_sizes_are_positive(self):
        """Icon and font size constants are positive integers."""
        for value in (
            UIConstants.ICON_SIZE_SMALL,
            UIConstants.ICON_SIZE_MEDIUM,
            UIConstants.ICON_SIZE_LARGE,
            UIConstants.FONT_SIZE_SMALL,
            UIConstants.FONT_SIZE_NORMAL,
            UIConstants.FONT_SIZE_LARGE,
            UIConstants.FONT_SIZE_XLARGE,
        ):
            assert isinstance(value, int)
            assert value > 0

    def test_tree_columns_are_sequential_indices(self):
        """Tree column constants are distinct non-negative indices."""
        columns = {
            UIConstants.TREE_COLUMN_NAME,
            UIConstants.TREE_COLUMN_TYPE,
            UIConstants.TREE_COLUMN_ID,
        }
        assert len(columns) == 3
        assert all(isinstance(c, int) and c >= 0 for c in columns)


@pytest.mark.unit
class TestFileConstants:
    """Verify FileConstants values are sane."""

    def test_file_size_limits_are_positive_bytes(self):
        """File size limit constants are positive integers (bytes)."""
        assert FileConstants.MAX_FILE_SIZE > 0
        assert FileConstants.MAX_IMAGE_SIZE > 0
        assert isinstance(FileConstants.MAX_FILE_SIZE, int)
        assert isinstance(FileConstants.MAX_IMAGE_SIZE, int)

    @pytest.mark.parametrize(
        "extensions",
        [
            FileConstants.IMAGE_EXTENSIONS,
            FileConstants.DOCUMENT_EXTENSIONS,
            FileConstants.DATA_EXTENSIONS,
        ],
        ids=["image", "document", "data"],
    )
    def test_extension_sets_are_nonempty(self, extensions):
        """Each file extension collection is a non-empty set."""
        assert isinstance(extensions, set)
        assert len(extensions) > 0

    @pytest.mark.parametrize(
        "extensions",
        [
            FileConstants.IMAGE_EXTENSIONS,
            FileConstants.DOCUMENT_EXTENSIONS,
            FileConstants.DATA_EXTENSIONS,
        ],
        ids=["image", "document", "data"],
    )
    def test_extensions_start_with_dot(self, extensions):
        """Every file extension begins with a leading dot."""
        for ext in extensions:
            assert isinstance(ext, str)
            assert ext.startswith(".")
            assert len(ext) > 1

    def test_known_image_extensions_present(self):
        """A few well-known image extensions are included."""
        for ext in (".jpg", ".png", ".tiff"):
            assert ext in FileConstants.IMAGE_EXTENSIONS

    def test_known_document_extensions_present(self):
        """A few well-known document extensions are included."""
        for ext in (".pdf", ".docx", ".xlsx", ".csv"):
            assert ext in FileConstants.DOCUMENT_EXTENSIONS

    def test_known_data_extensions_present(self):
        """A few well-known data extensions are included."""
        for ext in (".json", ".xml", ".yaml"):
            assert ext in FileConstants.DATA_EXTENSIONS


@pytest.mark.unit
class TestOntologyConstants:
    """Verify OntologyConstants values are sane."""

    def test_main_ontology_filename(self):
        """The main ontology file is the expected OWL file name."""
        main_owl = OntologyConstants.get_ontology_main()
        assert main_owl == "onto.owl"
        assert main_owl.endswith(".owl")

    def test_main_ontology_ttl_filename(self):
        """The TTL ontology file is the expected file name."""
        main_ttl = OntologyConstants.get_ontology_main_ttl()
        assert main_ttl == "onto.ttl"
        assert main_ttl.endswith(".ttl")


@pytest.mark.unit
class TestISAJsonConstants:
    """Verify ISAJsonConstants values are sane."""

    def test_default_ids_are_nonempty_strings(self):
        """Default investigation/study IDs are non-empty strings."""
        assert isinstance(ISAJsonConstants.DEFAULT_INVESTIGATION_ID, str)
        assert ISAJsonConstants.DEFAULT_INVESTIGATION_ID
        assert isinstance(ISAJsonConstants.DEFAULT_STUDY_ID, str)
        assert ISAJsonConstants.DEFAULT_STUDY_ID

    @pytest.mark.parametrize(
        "fields",
        [
            ISAJsonConstants.REQUIRED_INVESTIGATION_FIELDS,
            ISAJsonConstants.REQUIRED_STUDY_FIELDS,
            ISAJsonConstants.REQUIRED_ASSAY_FIELDS,
        ],
        ids=["investigation", "study", "assay"],
    )
    def test_required_field_lists(self, fields):
        """Required-field constants are non-empty lists of strings."""
        assert isinstance(fields, list)
        assert len(fields) > 0
        assert all(isinstance(f, str) and f for f in fields)

    def test_required_investigation_fields(self):
        """Investigation requires title and description."""
        assert "title" in ISAJsonConstants.REQUIRED_INVESTIGATION_FIELDS
        assert "description" in ISAJsonConstants.REQUIRED_INVESTIGATION_FIELDS

    def test_required_assay_fields(self):
        """Assay requires measurementType and technologyType."""
        assert "measurementType" in ISAJsonConstants.REQUIRED_ASSAY_FIELDS
        assert "technologyType" in ISAJsonConstants.REQUIRED_ASSAY_FIELDS


@pytest.mark.unit
class TestValidationConstants:
    """Verify ValidationConstants values are sane."""

    def test_id_length_bounds(self):
        """ID length bounds are positive with min <= max."""
        assert ValidationConstants.ID_MIN_LENGTH > 0
        assert ValidationConstants.ID_MAX_LENGTH >= ValidationConstants.ID_MIN_LENGTH

    def test_text_length_bounds(self):
        """Text length bounds are positive with min <= max."""
        assert ValidationConstants.TITLE_MIN_LENGTH > 0
        assert ValidationConstants.TITLE_MAX_LENGTH >= ValidationConstants.TITLE_MIN_LENGTH
        assert ValidationConstants.DESCRIPTION_MAX_LENGTH > 0

    def test_max_url_length_is_positive(self):
        """The max URL length is a positive integer."""
        assert isinstance(ValidationConstants.MAX_URL_LENGTH, int)
        assert ValidationConstants.MAX_URL_LENGTH > 0


@pytest.mark.unit
class TestTemplateConstants:
    """Verify TemplateConstants values are sane."""

    def test_template_file_mapping_is_dict(self):
        """The template mapping is a dict of str -> str (empty by default)."""
        mapping = TemplateConstants.TEMPLATE_FILE_MAPPING
        assert isinstance(mapping, dict)
        for key, value in mapping.items():
            assert isinstance(key, str) and key
            assert isinstance(value, str) and value

    def test_template_file_mapping_keys_are_unique(self):
        """Mapping keys are unique (guaranteed by dict, asserted for clarity)."""
        keys = list(TemplateConstants.TEMPLATE_FILE_MAPPING.keys())
        assert len(keys) == len(set(keys))

    def test_numeric_units_are_nonempty_string_list(self):
        """NUMERIC_UNITS is a non-empty list of non-empty strings."""
        units = TemplateConstants.NUMERIC_UNITS
        assert isinstance(units, list)
        assert len(units) > 0
        assert all(isinstance(u, str) and u for u in units)

    def test_numeric_units_are_unique(self):
        """Numeric units are unique within the list."""
        units = TemplateConstants.NUMERIC_UNITS
        assert len(units) == len(set(units))

    def test_known_units_present(self):
        """A few well-known units are included."""
        for unit in ("minute", "hour", "microlitre", "degree celsius"):
            assert unit in TemplateConstants.NUMERIC_UNITS
