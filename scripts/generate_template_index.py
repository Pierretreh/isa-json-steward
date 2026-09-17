#!/usr/bin/env python3
"""
Generate Template Index

Scans the templates/ directory and writes:
  - templates/template_index.json  (machine-readable index)
  - templates/template_list.txt    (human-readable list)

Usage:
    python scripts/generate_template_index.py
    python scripts/generate_template_index.py --templates-root templates/
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.template_index import write_template_index  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="Generate template index files from the templates/ directory"
    )
    parser.add_argument(
        "--templates-root",
        type=str,
        default=None,
        help="Path to the templates directory (default: <project_root>/templates)",
    )
    args = parser.parse_args()

    templates_root = (
        Path(args.templates_root) if args.templates_root else project_root / "templates"
    )

    if not templates_root.exists():
        print(f"Error: templates directory not found: {templates_root}", file=sys.stderr)
        sys.exit(1)

    index = write_template_index(templates_root)

    counts = index.get("counts", {})
    print(f"Generated template index at: {templates_root / 'template_index.json'}")
    print(f"Generated template list at:  {templates_root / 'template_list.txt'}")
    print(f"  Assay templates:      {counts.get('assay', 0)}")
    print(f"  Protocol templates:   {counts.get('protocol', 0)}")
    print(f"  Material template files: {counts.get('material_files', 0)}")


if __name__ == "__main__":
    main()
