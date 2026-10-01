# ISA-JSON Data Steward

A desktop application and command-line toolkit for creating, validating, and managing ISA-JSON investigation metadata.

## Features

- **GUI Application** — Desktop interface for managing ISA-JSON studies, assays, materials, and process sequences
- **Batch Processing Pipeline** — 7-stage automated conversion of experimental data to ISA-JSON format (scan → classify → extract → convert → generate → organize → validate)
- **Experiment Classification** — Automatic assay-type detection from folder names, file types, and subdirectory structure
- **ISA-JSON Export** — Generate compliant ISA-JSON files with full metadata
- **Ontology Integration** — Browse and link ontology terms to experimental metadata
- **Template System** — Configurable templates for assays, devices, materials, and protocols
- **Validation** — ISA-JSON schema validation and semantic checks

## Requirements

- Python 3.11+

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

### GUI Application
```bash
python -m gui.main
```

### CLI Tools
```bash
# Run the 7-stage batch pipeline (--data-root and --output-dir are required)
isa-json-steward-batch --data-root ./data --output-dir ./output

# Or using the module invocation
python -m utils.batch --data-root ./data --output-dir ./output

# Useful options
isa-json-steward-batch --data-root ./data --output-dir ./output \
    --profile ./path/to/profile/ \
    --investigation-id inv_001 \
    --inv-inm-path path/to/existing/investigation \
    --skip-conversion \
    --skip-validation

# Validate ISA-JSON files
python scripts/isa_json_validation.py path/to/file.json
```

### Using Profiles

The application supports domain-specific profiles that customize templates, ontology references, classification patterns, and configuration. A profile directory contains its own `config/` folder (e.g. `profile.json`, `experiment_patterns.json`, `fcs_markers.json`, …). Files missing from a profile are served from the built-in `config/` directory, and each such fallback is logged as a warning so incomplete profiles are easy to spot. Domain-specific knowledge (factor rules, assay templates, ontology) ships in swappable profile directories; the core is domain-agnostic.

```bash
# GUI — load a profile
python -m gui.main --profile ./path/to/profile/

# GUI — or set via environment variable
export ISA_STEWARD_PROFILE=./path/to/profile/

# Batch pipeline — load a profile
isa-json-steward-batch --data-root ./data --output-dir ./output --profile ./path/to/profile/
```

Without a profile, the built-in default `config/` directory is used. See the [Profile Documentation](docs/DIRECTORY_STRUCTURE.md) for the profile layout and [User Workflow Guide](docs/USER_WORKFLOW_GUIDE.md) for batch usage.

## Validation

Stage 7 of the batch pipeline validates the generated ISA-JSON against a set of
**layers**, each with a defined severity. The result of every layer is recorded
in the `processing_report.json` `validation` block (layer name,
`passed`/`failed`/`skipped` status, `errors`, `warnings`, `info`, duration) and
shown as per-layer status chips in the GUI. A blocking layer failure sets
`validation_passed` to `false`; non-blocking layers only warn.

| Layer | Implemented by | Severity | Notes |
|-------|----------------|----------|-------|
| `schema` | `SchemaLayer` (wraps `ISAJsonValidator`) | **Error** (blocks export) | ISA-JSON structure, required fields, data types, plus offline isatools spec validation where available. |
| `semantic` | `SemanticValidator` | Warning (non-blocking) | Ontology-term verification via prefix/namespace resolution and offline `rdflib` lookup of the profile's cached ontologies. |
| `data_file` | `DataFileLayer` (wraps `DataFileValidator`) | **Error** (blocks export) | Data-file presence, readability and FAIR checks. |
| `template` | `TemplateValidator` | Warning (non-blocking) | Generated assay vs the profile assay template: parameter presence, type/unit accession match, required attachments. |
| `shacl` | `ShaclValidator` (via `pyshacl`) | **Error** (blocks export) | SHACL shape validation of the profile ontology. Skipped gracefully when `pyshacl` or the shapes file is absent. |
| `owl` | `OwlConsistencyValidator` | **Error** (blocks export) | `rdflib`-only OWL structural consistency (circular `subClassOf`, conflicting definitions). Deep reasoning remains the offline/CI HermiT gate. |
| `ols` *(optional)* | `OlsValidator` | Warning (non-blocking) | **OFF by default, network-dependent.** Resolves terms that could not be verified locally against the EBI OLS web service. |

### Choosing layers

```bash
# Run all core layers (the default — everything except the optional `ols`)
isa-json-steward-batch --data-root ./data --output-dir ./output

# Select a subset, or add the optional OLS layer
isa-json-steward-batch --data-root ./data --output-dir ./output \
    --validation-layers schema,semantic,template

# Enable the optional OLS layer (network lookup)
isa-json-steward-batch --data-root ./data --output-dir ./output \
    --validation-layers schema,semantic,data_file,template,shacl,owl,ols \
    --enable-ols

# Skip all validation (Stage 7 is still reported as skipped)
isa-json-steward-batch --data-root ./data --output-dir ./output --skip-validation
```

The same options are available in the GUI: the batch dialog offers a
**Validation layers** section with one checkbox per core layer (all
default-checked) and a separate, clearly-labelled optional
**OLS lookup (network, slow)** checkbox (default **unchecked**).

### The optional OLS layer

`ols` is **optional and OFF by default**. It is a convenience for users who did
not download the reference ontologies locally and would rather let the
EBI **Ontology Lookup Service** (OLS) web service cross-check unresolved
terms. Because it makes live HTTP calls it is slower, depends on network
availability, and **skips gracefully** (status `skipped`, an info note) if OLS
is unreachable — it never causes a hard failure. Prefer the offline `semantic`
layer when the ontologies are cached; enable `ols` only when you want a
web-service fallback.

The profile can also declare a default layer set and the shapes/ontology
paths under a `validation` section of its `profile.json`
(e.g. `{"validation": {"layers": ["schema", "semantic", "data_file", "template", "shacl", "owl"], "enable_ols": false, "semantic": {"cache_dir": "ontologies/cached"}}}`);
these settings are additive and fall back to the code defaults when absent.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
pre-commit run --all-files
```

## Project Structure

```
├── gui/              # Desktop GUI application
│   ├── dialogs/      # Dialog windows
│   ├── pages/        # Main application pages
│   ├── widgets/      # Reusable UI widgets
│   └── resources/    # Stylesheets and assets
├── utils/            # Core utilities
│   └── batch/        # Batch processing pipeline (run via `isa-json-steward-batch` or `python -m utils.batch`)
├── scripts/          # Standalone CLI tools
├── tests/            # Test suite
├── config/           # Default configuration
└── docs/             # Documentation
```

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
