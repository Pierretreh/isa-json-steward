"""
Template Index Generator

Scans the templates/ directory and generates:
  - templates/template_index.json  (machine-readable index)
  - templates/template_list.txt    (human-readable list)

Assay and protocol templates get full metadata extracted.
Material templates are listed at file level only.

Usage:
    from utils.template_index import write_template_index
    write_template_index(Path("templates"))
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _extract_annotation_label(value: Any) -> str:
    """Extract the annotationValue from an ISA-style annotation dict."""
    if isinstance(value, dict):
        return str(value.get("annotationValue", ""))
    return ""


def _relative_path(file_path: Path, templates_root: Path) -> str:
    """Get a cross-platform relative path string (forward slashes)."""
    return file_path.relative_to(templates_root.parent).as_posix()


def _summarise_assay(data: Dict, file_path: Path, templates_root: Path) -> Dict:
    """Extract index metadata from a single assay template."""
    at_type = data.get("@type", "")
    # @type can be a plain string like "onto:MicroscopyAssay" or a dict
    type_str = at_type if isinstance(at_type, str) else _extract_annotation_label(at_type)
    return {
        "name": data.get("name", file_path.stem),
        "description": data.get("description", ""),
        "filename": file_path.name,
        "path": _relative_path(file_path, templates_root),
        "type": type_str,
        "measurementType": _extract_annotation_label(data.get("measurementType")),
        "technologyType": _extract_annotation_label(data.get("technologyType")),
        "technologyPlatform": data.get("technologyPlatform", ""),
        "parameter_count": len(data.get("parameters", [])),
    }


def _summarise_protocol(data: Dict, file_path: Path, templates_root: Path) -> Dict:
    """Extract index metadata from a single protocol template."""
    at_type = data.get("@type", "")
    type_str = at_type if isinstance(at_type, str) else _extract_annotation_label(at_type)
    return {
        "name": data.get("name", file_path.stem),
        "description": data.get("description", ""),
        "filename": file_path.name,
        "path": _relative_path(file_path, templates_root),
        "type": type_str,
        "protocolType": _extract_annotation_label(data.get("protocolType")),
        "technologyPlatform": data.get("technologyPlatform", ""),
        "parameter_count": len(data.get("parameters", [])),
    }


def _summarise_material_file(data: Dict, file_path: Path, templates_root: Path) -> Dict:
    """Extract file-level metadata from a material template file."""
    templates_list = data.get("templates", []) if isinstance(data, dict) else []
    return {
        "filename": file_path.name,
        "path": _relative_path(file_path, templates_root),
        "template_count": len(templates_list),
    }


def scan_assay_templates(templates_root: Path) -> List[Dict]:
    """Scan assay_templates/ and return a list of metadata dicts."""
    assay_dir = templates_root / "assay_templates"
    results: List[Dict] = []
    if not assay_dir.exists():
        logger.warning("Assay templates directory not found: %s", assay_dir)
        return results

    for json_file in sorted(assay_dir.glob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            results.append(_summarise_assay(data, json_file, templates_root))
        except Exception as e:
            logger.warning("Error reading assay template %s: %s", json_file, e)

    return results


def scan_protocol_templates(templates_root: Path) -> List[Dict]:
    """Scan protocol_templates/ and return a list of metadata dicts."""
    protocol_dir = templates_root / "protocol_templates"
    results: List[Dict] = []
    if not protocol_dir.exists():
        logger.warning("Protocol templates directory not found: %s", protocol_dir)
        return results

    for json_file in sorted(protocol_dir.glob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            results.append(_summarise_protocol(data, json_file, templates_root))
        except Exception as e:
            logger.warning("Error reading protocol template %s: %s", json_file, e)

    return results


def scan_material_templates(templates_root: Path) -> List[Dict]:
    """Scan material_templates/ and return file-level metadata."""
    material_dir = templates_root / "material_templates"
    results: List[Dict] = []
    if not material_dir.exists():
        logger.warning("Material templates directory not found: %s", material_dir)
        return results

    for json_file in sorted(material_dir.glob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            results.append(_summarise_material_file(data, json_file, templates_root))
        except Exception as e:
            logger.warning("Error reading material template %s: %s", json_file, e)

    return results


def generate_template_index(templates_root: Path) -> Dict:
    """
    Scan all template directories and build the consolidated index.

    Args:
        templates_root: Path to the templates/ directory.

    Returns:
        Dict suitable for serialisation as template_index.json.
    """
    assay_templates = scan_assay_templates(templates_root)
    protocol_templates = scan_protocol_templates(templates_root)
    material_templates = scan_material_templates(templates_root)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "assay": len(assay_templates),
            "protocol": len(protocol_templates),
            "material_files": len(material_templates),
        },
        "assay_templates": assay_templates,
        "protocol_templates": protocol_templates,
        "material_templates": material_templates,
    }


def _format_template_list(index: Dict) -> str:
    """Format the index into a human-readable text list."""
    lines: List[str] = []

    # Assay templates
    lines.append("=== Assay Templates ===")
    for t in index.get("assay_templates", []):
        lines.append(t.get("name", "Unknown"))
    lines.append("")

    # Protocol templates
    lines.append("=== Protocol Templates ===")
    for t in index.get("protocol_templates", []):
        lines.append(t.get("name", "Unknown"))
    lines.append("")

    # Material template files
    lines.append("=== Material Template Files ===")
    for t in index.get("material_templates", []):
        lines.append(t.get("filename", "Unknown"))
    lines.append("")

    return "\n".join(lines)


def write_template_index(templates_root: Path) -> Dict:
    """
    Generate and write both template index files.

    Args:
        templates_root: Path to the templates/ directory.

    Returns:
        The generated index dict.
    """
    templates_root = Path(templates_root)

    index = generate_template_index(templates_root)

    # Write JSON index
    index_path = templates_root / "template_index.json"
    try:
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        logger.info("Wrote template index: %s", index_path)
    except Exception as e:
        logger.error("Failed to write template index %s: %s", index_path, e)

    # Write text list
    list_path = templates_root / "template_list.txt"
    try:
        with open(list_path, "w", encoding="utf-8") as f:
            f.write(_format_template_list(index))
        logger.info("Wrote template list: %s", list_path)
    except Exception as e:
        logger.error("Failed to write template list %s: %s", list_path, e)

    # Summary
    counts = index.get("counts", {})
    logger.info(
        "Template index: %d assay, %d protocol, %d material files",
        counts.get("assay", 0),
        counts.get("protocol", 0),
        counts.get("material_files", 0),
    )

    return index
