# User Workflow Guide

> **Last updated**: 2026-09-17

This guide provides step-by-step instructions for scientists to enter experimental data into the ISA-JSON Data Steward.

## Overview

The ISA-JSON Data Steward uses ISA-JSON format for FAIR data management. There are two ways to create ISA-JSON studies:

1. **GUI** — Interactive desktop application for manual data entry
2. **Batch pipeline** — Automated conversion of partner experiment folders

## GUI Workflow

### Launch

```bash
python -m gui.main
```

### Creating a Study

1. **Investigations page**: Create or select an investigation
2. **Studies page**: Create a new study within the investigation
3. **Materials page**: Add sources, samples, and other materials with ontology-linked characteristics
4. **Process Sequence page**: Build process chains linking materials through protocols
5. **Assays page**: Configure assay workflows from templates (FACS, microscopy, ELISA, etc.)
6. **Files page**: Attach, convert, and manage data files
7. **Ontology Browser**: Browse and search PMDco, OBI, and UO ontologies for term selection

### Key Features

- **Template system**: Pre-configured templates for 22 assay types, 16 protocol types, and common materials
- **Ontology integration**: All terms can be linked to PMDco, OBI, UO, ChEBI, and NCBITaxon
- **ISA-JSON export**: Studies are exported as valid ISA-JSON files
- **Dark/light theme**: Toggle via settings page

## Batch Pipeline Workflow

For converting partner experiment folders (CZI, FCS, XLSX files) into ISA-JSON studies:

```bash
# Process all experiments
isa-json-steward-batch --data-root "path/to/data" --investigation-id inv_ukf

# Or using the module invocation
python -m utils.batch --data-root "path/to/data" --investigation-id inv_ukf

# Process with a domain profile
isa-json-steward-batch --data-root "path/to/data" --profile ./domain-profile
```

The pipeline automatically:
1. Scans experiment folders and classifies experiment types
2. Extracts metadata from proprietary files (CZI, FCS, XLSX)
3. Converts files to open standards (TIFF, CSV)
4. Generates ISA-JSON study files using templates
5. Validates output against the ISA-JSON specification

Output is written to `investigations/{investigation_id}/`.

## Tips for Scientists

- **Material naming**: Use descriptive names that include key identifiers (e.g., "pVV021_4uM", not "sample_1")
- **Ontology terms**: Always prefer ontology-linked values over free text when possible
- **Templates**: Start from templates rather than building from scratch — they include correct ontology references
- **Validation**: Check the validation output after export to catch missing metadata early

## References

- [README](../README.md) — Project overview and installation
- [Setup Guide](SETUP_GUIDE.md) — Installation and configuration
- [Directory Structure](DIRECTORY_STRUCTURE.md) — File organization
- [ISA-JSON Specification](https://isa-specs.readthedocs.io/) — Format reference
