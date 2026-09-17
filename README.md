# ISA-JSON Data Steward

A desktop application and command-line toolkit for creating, validating, and managing ISA-JSON investigation metadata.

## Features

- **GUI Application** — Desktop interface for managing ISA-JSON studies, assays, materials, and process sequences
- **Batch Processing Pipeline** — Automated conversion of experimental data to ISA-JSON format
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
# Generate ISA-JSON from batch data
isa-json-steward-batch --data-root ./data --output-dir ./output

# Or using the module invocation
python -m utils.batch --data-root ./data --output-dir ./output

# Validate ISA-JSON files
python scripts/isa_json_validation.py path/to/file.json
```

### Using Profiles

The application supports domain-specific profiles that customize templates, ontology references, and configuration:

```bash
# Load a profile
python -m gui.main --profile ./path/to/profile/

# Or set via environment variable
export ISA_STEWARD_PROFILE=./path/to/profile/
```

See the [Profile Documentation](docs/USER_WORKFLOW_GUIDE.md) for details on creating custom profiles.

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
