# Setup Guide

> **Last updated**: 2026-09-17

## Prerequisites

- Python 3.11 or higher
- Git

## Installation

### Clone and Install

```bash
git clone <repository-url>
cd isa-json-steward

# Install in editable mode
pip install -e .

# Optional: install development dependencies
pip install -e ".[dev]"

# Optional: install file conversion extras (CZI, FCS support)
pip install -e ".[conversion]"
```

### Launch the GUI

```bash
python -m gui.main
```

The GUI automatically creates the required directory structure on first launch.

## Directory Initialization

The directory structure is managed by [`utils/directory_manager.py`](../utils/directory_manager.py). On first GUI launch, it creates:

- `investigations/` — Root for all investigations
- `templates/` — ISA-JSON templates (already present in repo)
- `ontologies/` — Ontology files (already present in repo)
- `exports/` — Exported data
- `config/` — Configuration files (already present in repo)
- `docs/` — Documentation (already present in repo)

## Ontology Pipeline

To regenerate the ontology from templates:

```bash
# 1. Download/update external ontologies
python scripts/cache_ontologies.py --force

# 2. Generate ontology (includes verification + OWL axioms)
python scripts/generate_ontology.py

# 3. Generate SHACL shapes and validate
python scripts/generate_shacl.py --validate ontologies/onto.ttl

# 4. Run HermiT reasoner
python scripts/validate_reasoner.py

# 5. Review verification report
cat ontologies/validation_report.json
```

## Batch Data Processing

To process partner experimental data into ISA-JSON, run the 7-stage batch pipeline (scan → classify → extract → convert → generate → organize → validate). Both `--data-root` and `--output-dir` are **required**:

```bash
# Process all experiment folders found in the data directory
isa-json-steward-batch --data-root "path/to/data" --output-dir ./output

# Or using the module invocation
python -m utils.batch --data-root "path/to/data" --output-dir ./output

# Process with a domain profile and skip conversion
isa-json-steward-batch --data-root "path/to/data" --output-dir ./output \
    --profile ./domain-profile --skip-conversion
```

### Batch CLI Options

| Option | Description |
|--------|-------------|
| `--data-root` *(required)* | Root directory containing experiment folders (named `E1`, `E2`, …) |
| `--output-dir` *(required)* | Output directory for the processed investigation |
| `--profile` | Path to a domain profile directory; defaults to the built-in `config/` |
| `--investigation-id` | Investigation identifier (default: from the profile's investigation defaults) |
| `--inv-inm-path` | Optional path to an existing investigation for material references |
| `--skip-conversion` | Skip the file format conversion stage |
| `--skip-validation` | Skip the validation stage |

The output investigation is written to `{--output-dir}/{investigation_id}/`, and a `processing_report.json` summary is written to `{--output-dir}/`.

## Running Tests

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=utils --cov-report=html

# Run specific test categories
pytest tests/batch_processing/     # Batch pipeline tests
pytest tests/utils/                # Utility module tests
pytest tests/integration/          # Integration tests
pytest tests/e2e/                  # End-to-end tests (requires representative data)
```

## Troubleshooting

**Issue: `ModuleNotFoundError` when running scripts**
- Ensure you installed with `pip install -e .` from the project root

**Issue: GUI doesn't launch**
- Check Python version: `python --version` (must be 3.9+)
- Check PyQt6 is installed: `pip show PyQt6`

**Issue: Tests skip with "Representative data not available"**
- The E2E tests require the partner representative dataset in the expected location
- Run unit and integration tests instead: `pytest -m "not requires_data"`

## References

- [README](../README.md) — Project overview
- [Directory Structure](DIRECTORY_STRUCTURE.md) — Full directory layout
- [User Workflow Guide](USER_WORKFLOW_GUIDE.md) — Scientist workflow guide
