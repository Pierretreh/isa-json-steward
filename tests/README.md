# ISA-JSON Data Steward — Test Suite

This directory contains the test suite for the ISA-JSON Data Steward project.

## Test Structure

```
tests/
├── __init__.py                          # Test package initialization
├── conftest.py                          # Shared fixtures and configuration
├── test_validation.py                   # Tests for validation utilities
├── test_material_manager.py             # Tests for MaterialManager
├── test_file_manager.py                 # Tests for FileManager
├── test_file_manager_extended.py        # Extended FileManager tests
├── test_file_converter.py               # Tests for file conversion utilities
├── test_process_sequence_manager.py     # Tests for ProcessSequenceManager
├── test_sequence_file_attachment.py     # Tests for sequence file attachments
├── test_directory_manager.py            # Tests for DirectoryManager
├── test_dna_conversion.py               # Tests for DNA conversion
├── test_lab_book_xml_parser.py          # Tests for lab book XML parsing
├── test_link_microscopy_files.py        # Tests for microscopy file linking
├── test_parse_excel_metadata.py         # Tests for Excel metadata parsing
├── test_parse_microscopy_docx.py        # Tests for microscopy DOCX parsing
├── batch_processing/                    # Batch pipeline component tests
│   ├── __init__.py
│   ├── test_batch_processor.py
│   ├── test_experiment_classifier.py
│   ├── test_file_sample_mapping.py
│   ├── test_folder_scanner.py
│   ├── test_format_converter.py
│   ├── test_isa_json_generator.py
│   ├── test_metadata_extractor_fcs.py
│   ├── test_metadata_extractor_extended.py
│   ├── test_process_partner_data.py
│   ├── test_e100_factor_parsing.py
│   ├── test_e100_fcs_enrichment.py
│   └── test_validator.py
├── e2e/                                 # End-to-end pipeline tests
│   ├── __init__.py
│   └── test_full_pipeline_with_representative_data.py
├── gui/                                 # GUI tests
│   ├── __init__.py
│   └── test_steward_app.py
├── integration/                         # Integration tests
│   ├── __init__.py
│   └── batch_pipeline/
│       ├── __init__.py
│       └── test_single_experiment_pipeline.py
└── utils/                               # Utility module tests
    ├── __init__.py
    ├── test_constants.py
    ├── test_graph_builder.py
    ├── test_isa_json_exporter.py
    ├── test_isa_json_preview_helpers.py
    ├── test_logging_config.py
    ├── test_material_handover_validator.py
    ├── test_ontology_manager.py
    ├── test_profile_loader.py
    └── test_template_index.py
```

## Running Tests

### Install Dependencies

```bash
# Install in editable mode with development dependencies
pip install -e ".[dev]"
```

### Run All Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=utils --cov-report=html --cov-report=term-missing

# Run specific test file
pytest tests/test_validation.py -v

# Run with markers
pytest tests/ -m "unit"        # Run only unit tests
pytest tests/ -m "integration"  # Run only integration tests
pytest tests/ -m "slow"         # Run slow tests
```

### Test Markers

- `unit`: Fast, isolated unit tests
- `integration`: Slower tests that may use external resources
- `slow`: Long-running tests
- `gui`: GUI-related tests (requires PyQt6)
- `security`: Security-related tests
- `file_ops`: File operation tests

## Test Fixtures

The `conftest.py` file provides the following fixtures:

### Directory Fixtures
- `temp_dir`: Temporary directory for test files
- `temp_study_dir`: Temporary study directory structure
- `sample_text_file`: Sample text file for testing
- `sample_json_file`: Sample JSON file for testing

### Data Fixtures
- `sample_study_data`: Sample study data dictionary
- `sample_material_data`: Sample material data
- `sample_process_data`: Sample process data
- `directory_manager`: DirectoryManager instance
- `file_manager`: FileManager instance
- `material_manager`: MaterialManager instance
- `process_sequence_manager`: ProcessSequenceManager instance

## Coverage Requirements

The project aims for 70% minimum code coverage on the `utils/` package.

Current coverage areas:
- ✅ Validation utilities
- ✅ MaterialManager
- ✅ FileManager
- ✅ ProcessSequenceManager
- ✅ OntologyManager
- ✅ ISA-JSON Exporter
- ✅ Batch pipeline components

## Writing Tests

When adding new tests:

1. Use descriptive test names that follow the pattern `test_<function>_<scenario>`
2. Group related tests in test classes
3. Use fixtures from `conftest.py` when possible
4. Mark tests with appropriate markers (`@pytest.mark.unit`, `@pytest.mark.slow`, etc.)
5. Write assertions that are clear and specific
6. Test both success and failure cases
7. Use `pytest.raises` for exception testing
8. Clean up resources in `teardown` if needed

## CI/CD Integration

The project includes a GitHub Actions workflow (`.github/workflows/test.yml`) that:

- Runs tests on Python 3.10, 3.11, 3.12
- Installs dependencies via `pip install -e ".[dev]"`
- Runs security checks with `bandit` and `safety`
- Runs code quality checks with `flake8` and `mypy`
- Generates coverage reports
- Uploads coverage to Codecov

## Test Categories

### Unit Tests
Fast, isolated tests that don't require external resources or full application context.

### Integration Tests
Slower tests that may interact with multiple components or external systems.

### GUI Tests
Tests that require PyQt6 and may need Qt test fixtures.

### Security Tests
Tests for security-related functionality like file validation, input sanitization, and access control.

## Troubleshooting

### Tests Failing

If tests are failing:

1. **Check if methods exist**: Ensure the methods being tested actually exist in the class
2. **Verify fixture data**: Check that sample data matches expected structure
3. **Check imports**: Ensure all necessary imports are available
4. **Run with verbose output**: Use `-v` flag to see detailed test output
5. **Check test isolation**: Tests should not depend on each other

### Coverage Issues

If coverage is below 70%:

1. **Add tests for missing coverage**: Identify untested code paths
2. **Test edge cases**: Add tests for boundary conditions and error scenarios
3. **Test error paths**: Ensure exception handling is tested

## Contributing Tests

When adding tests:

1. Follow the existing test structure and patterns
2. Add fixtures to `conftest.py` for shared test data
3. Update this README with new test categories
4. Ensure all tests pass before committing
5. Run full test suite before pushing changes

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-qt Documentation](https://pytest-qt.readthedocs.io/)
- [Python Testing Best Practices](https://docs.python-guide.org/writing/tests/)
