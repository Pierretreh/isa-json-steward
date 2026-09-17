# Directory Structure Documentation

> **Last updated**: 2026-09-17

## Overview

This document describes the directory structure for the ISA-JSON Data Steward project. The structure follows ISA-Tab/ISA-JSON conventions and supports FAIR data principles.

## Root Directory Structure

```
isa-json-steward/
├── pyproject.toml                      # Project metadata and dependencies
├── README.md                           # Project overview and setup instructions
├── pytest.ini                          # Test configuration
│
├── config/                             # Application configuration
│   ├── settings.json                   # Application settings (URLs, GUI, validation)
│   ├── directory_structure.json        # Directory layout definition
│   ├── profile.json                    # Active profile configuration
│   └── factor_extraction_rules.json    # Rules for extracting experimental factors from filenames
│
├── docs/                               # Documentation
│   ├── DIRECTORY_STRUCTURE.md          # This file
│   ├── SETUP_GUIDE.md                  # Setup instructions
│   └── USER_WORKFLOW_GUIDE.md          # User workflow guide
│
├── gui/                                # PyQt6 desktop application
│   ├── main.py                         # Entry point: `python -m gui.main`
│   ├── app.py                          # QApplication setup
│   ├── main_window.py                  # Main window with sidebar navigation
│   ├── dialogs/                        # Modal dialogs (assay, material, study wizard, etc.)
│   ├── pages/                          # Main application pages
│   │   ├── studies.py                  #   Study management
│   │   ├── assays.py                   #   Assay configuration
│   │   ├── materials.py                #   Material management
│   │   ├── process_sequence.py         #   Process chain builder
│   │   ├── files.py                    #   File attachment management
│   │   ├── images.py                   #   Image viewing/conversion
│   │   ├── ontology_browser.py         #   Ontology term browser
│   │   ├── templates.py                #   Template management
│   │   ├── settings.py                 #   Application settings
│   │   └── dashboard.py                #   Overview dashboard
│   ├── widgets/                        # Reusable UI widgets
│   └── resources/styles/               # QSS stylesheets (light/dark themes)
│
├── scripts/                            # Standalone CLI scripts
│   ├── isa_json_validation.py          # Single-file ISA-JSON validation
│   └── generate_template_index.py      # Generate machine-readable template index
│
├── tests/                              # Test suite (pytest)
│   ├── conftest.py                     # Shared fixtures and configuration
│   ├── batch_processing/               # Batch pipeline component tests
│   ├── integration/                    # Integration tests
│   ├── e2e/                            # End-to-end pipeline tests
│   └── utils/                          # Utility module tests
│
└── utils/                              # Python library modules
    ├── batch/                          # Batch data processing pipeline
    │   ├── __main__.py                 #   `python -m utils.batch` entry point
    │   ├── batch_processor.py          #   Pipeline orchestrator & `isa-json-steward-batch` CLI
    │   ├── folder_scanner.py           #   Data folder discovery
    │   ├── experiment_classifier.py    #   Experiment type classification
    │   ├── metadata_extractor.py       #   Metadata extraction (CZI, FCS, XLSX)
    │   ├── format_converter.py         #   Proprietary → standard format conversion
    │   ├── isa_json_generator.py       #   ISA-JSON file generation
    │   ├── file_organizer.py           #   ISA-JSON directory organization
    │   └── validator.py                #   ISA-JSON and data file validation
    ├── isa_json_exporter.py            # ISA-JSON export from GUI/internal data
    ├── isa_json_preview_helpers.py     # ISA-JSON preview helpers
    ├── ontology_manager.py             # Ontology operations and RDF conversion
    ├── material_manager.py             # Material management (sources, samples, other)
    ├── material_handover_validator.py  # Material handover validation
    ├── process_sequence_manager.py     # Process sequence management
    ├── file_manager.py                 # File attachment management
    ├── file_converter.py               # File format conversion utilities
    ├── file_type_validator.py          # File type validation
    ├── directory_manager.py            # Directory structure management
    ├── config_loader.py                # Configuration loading utilities
    ├── constants.py                    # Project-wide constants
    ├── graph_builder.py                # Ontology graph construction
    ├── template_index.py               # Template indexing and lookup
    ├── validation.py                   # Validation utilities
    └── logging_config.py               # Logging configuration
```

## Profiles

Domain-specific configuration (templates, ontology references, reference documents) is loaded via **profiles** rather than being bundled in the repository. A profile is a directory containing:

- `templates/` — Assay, protocol, material, and device templates (JSON)
- `ontologies/` — Ontology files (TTL, OWL) and cached external ontology copies
- `references/` — Project-specific reference documents
- `plans/` — Architecture and planning documents

To use a profile:

```bash
# Via CLI flag
python -m gui.main --profile ./path/to/profile/

# Via environment variable
export ISA_STEWARD_PROFILE=./path/to/profile/
```

See [`USER_WORKFLOW_GUIDE.md`](USER_WORKFLOW_GUIDE.md) for details on creating custom profiles.

## Investigation Output Structure

When the batch pipeline or GUI creates an investigation, the output follows this structure:

```
output/
├── inv_name/
│   ├── inv_name.json                   # Lightweight investigation JSON (study references)
│   └── studies/
│       ├── study_E1_experiment_name/
│       │   ├── study.json              # Full study metadata (ISA-JSON)
│       │   └── files/
│       │       ├── original/           # Original data files
│       │       └── converted/          # Converted files (CZI→TIFF, FCS→CSV)
│       └── study_E2_experiment_name/
│           ├── study.json
│           └── files/
```

## Configuration Files

| File | Purpose |
|------|---------|
| [`config/settings.json`](../config/settings.json) | Application settings (URLs, GUI config, validation rules, export options) |
| [`config/directory_structure.json`](../config/directory_structure.json) | Directory layout definition for DirectoryManager |
| [`config/factor_extraction_rules.json`](../config/factor_extraction_rules.json) | Rules for extracting experimental factors from data filenames |
| [`config/profile.json`](../config/profile.json) | Active profile configuration |
| [`pyproject.toml`](../pyproject.toml) | Python project metadata, dependencies, and optional extras |

## References

- [ISA-JSON Specification](https://isa-specs.readthedocs.io/)
- [FAIR Principles](https://www.go-fair.org/fair-principles/)
- [PMDco Ontology](https://w3id.org/pmd/co/)
