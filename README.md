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
    --profile ./domain-profile \
    --investigation-id inv_ukf \
    --inv-inm-path path/to/existing/investigation \
    --skip-conversion \
    --skip-validation

# Validate ISA-JSON files
python scripts/isa_json_validation.py path/to/file.json
```

### Using Profiles

The application supports domain-specific profiles that customize templates, ontology references, classification patterns, and configuration. A profile directory contains its own `config/` folder (e.g. `profile.json`, `experiment_patterns.json`, `fcs_markers.json`, …). Files missing from a profile are served from the built-in `config/` directory, and each such fallback is logged as a warning so incomplete profiles are easy to spot.

```bash
# GUI — load a profile
python -m gui.main --profile ./path/to/profile/

# GUI — or set via environment variable
export ISA_STEWARD_PROFILE=./path/to/profile/

# Batch pipeline — load a profile
isa-json-steward-batch --data-root ./data --output-dir ./output --profile ./path/to/profile/
```

Without a profile, the built-in default `config/` directory is used. See the [Profile Documentation](docs/DIRECTORY_STRUCTURE.md) for the profile layout and [User Workflow Guide](docs/USER_WORKFLOW_GUIDE.md) for batch usage.

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
