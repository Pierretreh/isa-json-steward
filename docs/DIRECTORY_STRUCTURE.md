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
├── config/                             # Default profile configuration (built-in profile)
│   ├── settings.json                   # Application settings (URLs, GUI, validation)
│   ├── directory_structure.json        # Directory layout definition
│   ├── profile.json                    # Profile metadata (namespace, ontology, templates dir)
│   ├── experiment_patterns.json        # Classification patterns (type keywords, file indicators, subdirectory patterns)
│   ├── fcs_markers.json                # FCS channel markers, operators, instrument aliases
│   ├── protein_names.json              # Protein and drug name mappings
│   ├── people.json                     # Investigation/study people
│   ├── investigation_defaults.json     # Investigation defaults (id, title, generator)
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

Domain-specific configuration — templates, ontology references, and classification patterns — is loaded via **profiles**. A profile is a directory containing a `config/` folder with the profile's configuration files (and, typically, `templates/` and `ontologies/`):

- `config/profile.json` — Profile metadata (name, namespace, ontology files, templates directory, optional `min_core_version`)
- `config/experiment_patterns.json` — Experiment-classification patterns (type keywords, file indicators, subdirectory assay/processing-state/timepoint patterns)
- `config/fcs_markers.json`, `config/protein_names.json`, `config/people.json`, `config/investigation_defaults.json`, `config/settings.json` — Domain-specific reference data

Lookup order for each config file: the profile's `config/` directory first (with `profile.json` also accepted at the profile root), then the built-in `config/` directory shipped with the package. A profile may therefore override only a subset of files; any file served from the built-in defaults is logged at `WARNING` level and reported via `log_profile_load_summary()`, so mixed-domain configurations are easy to spot.

The built-in `config/` directory (at the repository root) acts as the default profile when no profile directory is supplied.

To use a profile:

```bash
# GUI — via CLI flag
python -m gui.main --profile ./path/to/profile/

# GUI — via environment variable
export ISA_STEWARD_PROFILE=./path/to/profile/

# Batch pipeline — via CLI flag
isa-json-steward-batch --data-root "path/to/data" --output-dir ./output --profile ./path/to/profile/
```

See [`USER_WORKFLOW_GUIDE.md`](USER_WORKFLOW_GUIDE.md) for the batch workflow and the GUI workflow.

## Investigation Output Structure

When the batch pipeline or GUI creates an investigation, the output follows this structure:

```
{output-dir}/
├── processing_report.json              # Batch pipeline run summary
├── metadata/                           # Extracted metadata files + metadata_index.json
├── converted/                          # Intermediate converted files (CZI→TIFF, FCS→CSV)
└── {investigation_id}/
    ├── {investigation_id}.json         # Lightweight investigation JSON (study references)
    ├── directory_manifest.json         # File counts/sizes manifest
    └── studies/
        ├── study_E1/
        │   ├── study.json              # Full study metadata (ISA-JSON)
        │   ├── files/
        │   │   ├── original/           # Original data files
        │   │   └── converted/          # Converted files
        │   └── assays/
        │       └── {assay_id}/
        │           ├── assay.json      # Assay metadata
        │           └── ...             # Data files + <name>_metadata.json
        └── study_E2/
            └── ...
```

## Configuration Files

| File | Purpose |
|------|---------|
| [`config/profile.json`](../config/profile.json) | Profile metadata (name, namespace, ontology files, templates directory) |
| [`config/experiment_patterns.json`](../config/experiment_patterns.json) | Experiment classification: type→template map, keywords, file indicators, subdirectory assay/processing-state/timepoint patterns |
| [`config/fcs_markers.json`](../config/fcs_markers.json) | FCS channel-marker mappings, known operators, instrument aliases |
| [`config/protein_names.json`](../config/protein_names.json) | Protein and drug name mappings |
| [`config/people.json`](../config/people.json) | Investigation and study people |
| [`config/investigation_defaults.json`](../config/investigation_defaults.json) | Investigation defaults (id, title, description, generator) |
| [`config/settings.json`](../config/settings.json) | Application settings (URLs, GUI config, validation rules, export options) |
| [`config/directory_structure.json`](../config/directory_structure.json) | Directory layout definition for DirectoryManager |
| [`config/factor_extraction_rules.json`](../config/factor_extraction_rules.json) | Rules for extracting experimental factors from data filenames |
| [`pyproject.toml`](../pyproject.toml) | Python project metadata, dependencies, and optional extras |

## References

- [ISA-JSON Specification](https://isa-specs.readthedocs.io/)
- [FAIR Principles](https://www.go-fair.org/fair-principles/)
- [PMDco Ontology](https://w3id.org/pmd/co/)
