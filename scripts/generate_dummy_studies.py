#!/usr/bin/env python3
"""
Dummy Study Generator for the ISA-JSON Data Steward.

Regenerates the (gitignored) ``investigations/inv_dummy/`` dataset with
*representative* studies that actually populate the GUI pages: sources,
samples (treatment x donor factor design), other materials, study-level
process sequences, protocol declarations, calcein / facs / elisa assays
with real placeholder files, people, publications, characteristic
categories and unit categories.  A couple of studies are deliberately
empty so the GUI empty states can be exercised.

The generator drives the real project APIs -- ``MaterialManager`` and
``ProcessSequenceManager`` to build the source -> process -> samples /
otherMaterials -> assay chains, and ``ISAJsonExporter`` to produce the
ISA-JSON document -- mirroring ``domain-profile/scripts/
generate_test_study.py``.  Fields the exporter deliberately normalizes
away (``materialType``, ``derivesFrom``, ``performer``, ...) are restored
on the exported document so every field read by a GUI page loader is
present (see reports/diag_evidence for the field-by-field spec).

Usage:
    python scripts/generate_dummy_studies.py [options]

Options:
    --out DIR               Output (investigation) directory
                            (default: investigations/inv_dummy)
    --count N               Total number of studies (default: 8)
    --seed S                RNG seed for deterministic output (default: 42)
    --investigation-id ID   Investigation id (default: output dir name)

The output directory is deleted and regenerated on every run.
"""

import argparse
import json
import random
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path so the real managers can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.isa_json_exporter import ISAJsonExporter  # noqa: E402
from utils.material_manager import MaterialManager  # noqa: E402
from utils.process_sequence_manager import ProcessSequenceManager  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = "investigations/inv_dummy"
DEFAULT_COUNT = 8
DEFAULT_SEED = 42

INVESTIGATION_TITLE = "Dummy Studies Investigation"
INVESTIGATION_DESCRIPTION = (
    "Synthetic investigation of representative dummy studies generated for "
    "testing, demos and load checks of the ISA-JSON Data Steward."
)

TREATMENT_POOL = [
    "Control",
    "CompoundA 5uM",
    "CompoundB 10uM",
    "Isopropanol 5uM",
]
DONOR_POOL = ["A", "B", "C"]

# Characteristic categories declared by the generated studies.  Factor
# characteristics use #characteristic_category/factor* per the factor
# extraction rules convention.
CHARACTERISTIC_CATEGORIES = [
    {
        "@id": "#characteristic_category/organism",
        "characteristicType": {
            "annotationValue": "organism",
            "termSource": "OBI",
            "termAccession": "http://purl.obolibrary.org/obo/OBI_0100026",
        },
    },
    {
        "@id": "#characteristic_category/material_type",
        "characteristicType": {
            "annotationValue": "material type",
            "termSource": "OBI",
            "termAccession": "http://purl.obolibrary.org/obo/OBI_0000100",
        },
    },
    {
        "@id": "#characteristic_category/factor_treatment",
        "characteristicType": {
            "annotationValue": "treatment",
            "termSource": "EFO",
            "termAccession": "http://purl.obolibrary.org/obo/OBI_0000716",
        },
    },
    {
        "@id": "#characteristic_category/factor_donor",
        "characteristicType": {
            "annotationValue": "donor",
            "termSource": "EFO",
            "termAccession": "",
        },
    },
    {
        "@id": "#characteristic_category/compound_concentration",
        "characteristicType": {
            "annotationValue": "compound concentration",
            "termSource": "OBI",
            "termAccession": "",
        },
    },
]

UNIT_CATEGORIES = [
    {
        "@id": "#Unit/micromolar",
        "annotationValue": "micromolar",
        "termSource": "UO",
        "termAccession": "http://purl.obolibrary.org/obo/UO_0000062",
    }
]

MATERIAL_TYPE_CHARACTERISTIC = {
    "category": {"@id": "#characteristic_category/material_type"},
    "value": {"annotationValue": "biological sample", "termSource": "OBI"},
}

# One assay definition per covered assay type (config/assay_types.json:
# calcein / facs; elisa mirrors the historical dummy studies).
ASSAY_DEFS = [
    {
        "key": "calcein",
        "name": "Calcein assay",
        "measurement_type": {"annotationValue": "viability assay", "termSource": "OBI"},
        "technology_type": {"annotationValue": "fluorescence microscopy", "termSource": "OBI"},
        "process_name": "image acquisition",
        "protocol_name": "image acquisition",
        "file_ext": "png",
        "data_type": "Image File",
        "parameters": [{"name": "exposure time", "value": "50 ms"}],
    },
    {
        "key": "facs",
        "name": "FACS assay",
        "measurement_type": {"annotationValue": "flow cytometry assay", "termSource": "OBI"},
        "technology_type": {"annotationValue": "flow cytometry", "termSource": "OBI"},
        "process_name": "flow cytometry acquisition",
        "protocol_name": "flow cytometry acquisition",
        "file_ext": "fcs",
        "data_type": "Raw Data File",
        "parameters": [{"name": "event count", "value": 10000}],
    },
    {
        "key": "elisa",
        "name": "ELISA assay",
        "measurement_type": {"annotationValue": "protein expression", "termSource": "OBI"},
        "technology_type": {"annotationValue": "ELISA", "termSource": "OBI"},
        "process_name": "ELISA readout",
        "protocol_name": "ELISA readout",
        "file_ext": "csv",
        "data_type": "Raw Data File",
        "parameters": [{"name": "wavelength", "value": "450 nm"}],
    },
]

PEOPLE = [
    {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane.doe@example.org",
        "affiliation": "Institute of Biomaterials",
        "roles": ["principal investigator"],
    },
    {
        "first_name": "John",
        "last_name": "Smith",
        "email": "john.smith@example.org",
        "affiliation": "Institute of Biomaterials",
        "roles": ["researcher"],
    },
]

PUBLICATIONS = [
    {
        "title": "Representative dummy data for ISA-JSON stewardship",
        "pubmed_id": "39000001",
        "doi": "10.1234/dummy.2026.001",
        "authors": "Doe J, Smith J",
        "status": "published",
    }
]


# ----------------------------------------------------------------------
# Placeholder file generation (small, deterministic, PIL-based)
# ----------------------------------------------------------------------


def _write_placeholder_image(path: Path, label: str, rng: random.Random) -> None:
    """Write a small gel/microscopy-like placeholder PNG (or TIFF twin)."""
    from PIL import Image, ImageDraw

    width, height = 320, 240
    img = Image.new("RGB", (width, height), color=(28, 28, 32))
    draw = ImageDraw.Draw(img)

    lane_width = width // 6
    for i in range(1, 6):
        x = i * lane_width
        draw.line([(x, 16), (x, height - 16)], fill=(52, 52, 58), width=1)

    for lane in range(6):
        lane_x = lane * lane_width + lane_width // 2
        for _ in range(rng.randint(2, 4)):
            band_y = rng.randint(30, height - 40)
            band_h = rng.randint(4, 12)
            intensity = rng.randint(140, 250)
            draw.rectangle(
                [lane_x - 18, band_y, lane_x + 18, band_y + band_h],
                fill=(intensity, intensity, intensity),
            )

    draw.text((8, 4), label, fill=(210, 210, 210))
    draw.text((8, height - 14), "dummy placeholder", fill=(150, 150, 150))

    if path.suffix.lower() in (".tif", ".tiff"):
        img.save(path, "TIFF")
    else:
        img.save(path, "PNG")


def _write_placeholder_fcs(path: Path, label: str) -> None:
    """Write a tiny FCS-like placeholder (text bytes, not a valid FCS file)."""
    content = (
        "FCS3.0    "
        f"# dummy FCS placeholder for {label}\n"
        "$BEGINANALYSIS 0\n$ENDANALYSIS 0\n$BEGINSTEXT 0\n$ENDSTEXT 0\n"
        "$MODE L\n$DATATYPE I\n$PAR 2\n$TOT 100\n"
    )
    path.write_bytes(content.encode("ascii"))


def _write_placeholder_csv(path: Path, label: str, rng: random.Random) -> None:
    """Write a tiny OD-measurement table."""
    lines = ["well,sample,od450"]
    for well_row in ("A", "B"):
        for col in range(1, 5):
            lines.append(f"{well_row}{col},{label},{rng.uniform(0.05, 2.5):.3f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_placeholder_file(path: Path, label: str, rng: random.Random) -> None:
    """Dispatch to the right placeholder writer for the file suffix."""
    suffix = path.suffix.lower()
    if suffix in (".png", ".tif", ".tiff"):
        _write_placeholder_image(path, label, rng)
    elif suffix == ".fcs":
        _write_placeholder_fcs(path, label)
    else:
        _write_placeholder_csv(path, label, rng)


# ----------------------------------------------------------------------
# Study construction (drives MaterialManager / ProcessSequenceManager /
# ISAJsonExporter)
# ----------------------------------------------------------------------


def _material_record(
    material_type: str,
    name: str,
    characteristics: Optional[List[Dict[str, Any]]] = None,
    derives_from: Optional[List[str]] = None,
    factor_values: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build the internal material record handed to MaterialManager."""
    record: Dict[str, Any] = {
        "name": name,
        "materialType": material_type,
        "characteristics": characteristics if characteristics is not None else [],
    }
    if derives_from is not None:
        record["derivesFrom"] = derives_from
    if factor_values is not None:
        record["factorValues"] = factor_values
    return record


def _process_record(
    name: str,
    protocol_ref: str,
    inputs: List[Dict[str, Any]],
    outputs: List[Dict[str, Any]],
    parameters: List[Dict[str, Any]],
    performer: str,
    day: str,
    status: str,
    comment: str,
) -> Dict[str, Any]:
    """Build the internal process record handed to ProcessSequenceManager."""
    return {
        "name": name,
        "protocol_ref": protocol_ref,
        "date": day,
        "status": status,
        "performer": performer,
        "inputs": inputs,
        "outputs": outputs,
        "parameters": parameters,
        "comments": [{"name": "note", "value": comment}],
    }


def _io_ref(material: Dict[str, Any]) -> Dict[str, str]:
    """Internal input/output reference for a material record."""
    return {
        "material_id": material["@id"],
        "name": material["name"],
        "materialType": material.get("materialType", "sample"),
    }


def _build_full_study(
    rng: random.Random, investigation_id: str, study_id: str, day: date
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Build one fully populated representative study.

    Returns ``(exported_doc, meta, file_specs)`` where *meta* carries the
    blueprint information the exporter strips (process performers etc.)
    and *file_specs* describes the placeholder files to materialize.
    """
    donors = DONOR_POOL[: rng.randint(2, 3)]
    treatments = rng.sample(TREATMENT_POOL, 2)
    if "Control" not in treatments:
        treatments[0] = "Control"

    day_str = day.isoformat()

    study_data: Dict[str, Any] = {
        "identifier": study_id,
        "study_name": f"Dummy study {study_id} — {', '.join(treatments)}",
        "study_description": (
            f"Representative dummy study {study_id}: donor x treatment factor "
            "design with calcein, facs and elisa assays."
        ),
        "submission_date": day_str,
        "investigation_name": INVESTIGATION_TITLE,
        "investigation_description": INVESTIGATION_DESCRIPTION,
        "people": [dict(p) for p in PEOPLE],
        "publications": [dict(p) for p in PUBLICATIONS],
        "study_design_descriptors": [
            {
                "annotationValue": "intervention design",
                "termSource": "OBI",
                "termAccession": "http://purl.obolibrary.org/obo/OBI_0001154",
            }
        ],
        "factors": [
            {
                "@id": "#factor/treatment",
                "name": "treatment",
                "type": "treatment",
                "term_source": "EFO",
            },
            {
                "@id": "#factor/donor",
                "name": "donor",
                "type": "donor",
                "term_source": "EFO",
            },
        ],
        "materials": {"sources": [], "samples": [], "otherMaterials": []},
        "process_sequence": {"processes": []},
        "protocols": [],
        "assays": [],
    }

    mm = MaterialManager(
        study_data,
        directory_manager=None,
        investigation_id=investigation_id,
        study_id=study_id,
    )

    # --- Sources: one per donor -------------------------------------
    donor_sources: List[Dict[str, Any]] = []
    for donor in donors:
        mm.add_material(
            "source",
            _material_record(
                "source",
                f"Donor {donor}",
                characteristics=[
                    {
                        "category": {"@id": "#characteristic_category/organism"},
                        "value": {
                            "annotationValue": "Homo sapiens",
                            "termSource": "NCBITaxon",
                            "termAccession": "http://purl.obolibrary.org/obo/NCBITaxon_9606",
                        },
                    }
                ],
                derives_from=[],
            ),
        )
        donor_sources.append(mm.materials["sources"][-1])

    # --- Other materials -------------------------------------------
    mm.add_material(
        "otherMaterial",
        _material_record(
            "otherMaterial",
            "lysis buffer",
            characteristics=[dict(MATERIAL_TYPE_CHARACTERISTIC)],
            derives_from=[],
        ),
    )
    lysis_buffer = mm.materials["otherMaterials"][-1]
    mm.add_material(
        "otherMaterial",
        _material_record(
            "otherMaterial",
            "CompoundA 5uM solution",
            characteristics=[
                {
                    "category": {"@id": "#characteristic_category/compound_concentration"},
                    "value": {
                        "value": 5,
                        "unit": {
                            "@id": "#Unit/micromolar",
                            "annotationValue": "micromolar",
                            "termSource": "UO",
                            "termAccession": "http://purl.obolibrary.org/obo/UO_0000062",
                        },
                    },
                }
            ],
            derives_from=[],
        ),
    )
    compound_solution = mm.materials["otherMaterials"][-1]

    # --- Study-level process chain ---------------------------------
    pm = ProcessSequenceManager(study_data, mm)

    # P1: sample dilution  (source -> intermediate samples)
    intermediates: List[Dict[str, Any]] = []
    for source in donor_sources:
        mm.add_material(
            "sample",
            _material_record(
                "sample",
                f"{source['name']} diluted",
                characteristics=[dict(MATERIAL_TYPE_CHARACTERISTIC)],
                derives_from=[source["@id"]],
            ),
        )
        intermediates.append(mm.materials["samples"][-1])

    pm.add_process(
        _process_record(
            "sample dilution",
            "sample dilution",
            [_io_ref(m) for m in donor_sources],
            [_io_ref(m) for m in intermediates],
            [{"name": "dilution factor", "value": f"1:{rng.choice([5, 10, 20])}"}],
            "Jane Doe",
            (day - timedelta(days=rng.randint(2, 6))).isoformat(),
            "Completed",
            "Donors diluted in PBS before treatment.",
        )
    )

    # P2: treatment incubation (intermediates x treatments -> treated samples)
    treated: List[Dict[str, Any]] = []
    for intermediate in intermediates:
        donor = intermediate["name"].split()[1]
        for treatment in treatments:
            concentration = {
                "category": {"@id": "#characteristic_category/compound_concentration"},
                "value": {
                    "value": 5,
                    "unit": {
                        "@id": "#Unit/micromolar",
                        "annotationValue": "micromolar",
                        "termSource": "UO",
                        "termAccession": "http://purl.obolibrary.org/obo/UO_0000062",
                    },
                },
            }  # noqa: E501
            mm.add_material(
                "sample",
                _material_record(
                    "sample",
                    f"{donor} {treatment}",
                    characteristics=[
                        {
                            "category": {"@id": "#characteristic_category/factor_treatment"},
                            "value": {"annotationValue": treatment},
                        },
                        {
                            "category": {"@id": "#characteristic_category/factor_donor"},
                            "value": {"annotationValue": donor},
                        },
                        dict(concentration),
                    ],
                    derives_from=[intermediate["@id"]],
                    factor_values=[
                        {
                            "category": {"@id": "#factor/treatment"},
                            "value": {"annotationValue": treatment},
                        },
                        {
                            "category": {"@id": "#factor/donor"},
                            "value": {"annotationValue": donor},
                        },
                    ],
                ),
            )
            treated.append(mm.materials["samples"][-1])

    pm.add_process(
        _process_record(
            "treatment incubation",
            "treatment incubation",
            [_io_ref(m) for m in intermediates] + [_io_ref(compound_solution)],
            [_io_ref(m) for m in treated],
            [
                {"name": "incubation time", "value": f"{rng.choice([2, 4, 24])} h"},
                {"name": "temperature", "value": "37"},
            ],
            "John Smith",
            (day - timedelta(days=rng.randint(1, 3))).isoformat(),
            "Completed",
            f"Samples treated with {', '.join(treatments)}.",
        )
    )

    # P3: aliquot preparation (treated -> assay aliquots)
    aliquots: List[Dict[str, Any]] = []
    for sample in treated:
        mm.add_material(
            "sample",
            _material_record(
                "sample",
                f"{sample['name']} aliquot",
                characteristics=[dict(MATERIAL_TYPE_CHARACTERISTIC)],
                derives_from=[sample["@id"]],
                factor_values=sample.get("factorValues"),
            ),
        )
        aliquots.append(mm.materials["samples"][-1])

    pm.add_process(
        _process_record(
            "aliquot preparation",
            "aliquot preparation",
            [_io_ref(m) for m in treated] + [_io_ref(lysis_buffer)],
            [_io_ref(m) for m in aliquots],
            [{"name": "aliquot volume", "value": 100}],
            "John Smith",
            (day - timedelta(days=1)).isoformat(),
            "In Progress",
            "Aliquots prepared for the assay measurements.",
        )
    )

    # --- Assays (calcein / facs / elisa) ---------------------------
    file_specs: List[Dict[str, Any]] = []
    _add_assays(
        rng,
        study_data,
        study_id,
        day_str,
        aliquots,
        [lysis_buffer, compound_solution],
        file_specs,
    )

    # --- Protocols (>= 2, incl. the assay protocols) ---------------
    study_data["protocols"] = _protocol_declarations()

    # --- Export via the real ISAJsonExporter -----------------------
    exporter = ISAJsonExporter(
        study_data=study_data, investigation_id=investigation_id, study_id=study_id
    )
    doc = exporter.export_complete_isa_json()

    meta = {
        "study_id": study_id,
        "kind": "full",
        "title": study_data["study_name"],
        "description": study_data["study_description"],
        "submission_date": day_str,
        "materials": {
            "sources": mm.materials["sources"],
            "samples": mm.materials["samples"],
            "otherMaterials": mm.materials["otherMaterials"],
        },
        "processes": pm.get_processes(),
        "assays": study_data["assays"],
    }
    return doc, meta, file_specs


def _build_assay_only_study(
    rng: random.Random, investigation_id: str, study_id: str, day: date
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Build a study whose materials exist only at assay level.

    Exercises the Materials-page fallback
    (``gui/pages/materials.py`` ``_collect_assay_materials``) and the
    process-sequence merge of assay-level processes.
    """
    day_str = day.isoformat()
    study_data: Dict[str, Any] = {
        "identifier": study_id,
        "study_name": f"Dummy study {study_id} — assay-level materials",
        "study_description": (
            f"Representative dummy study {study_id}: all materials live at the "
            "assay level to exercise the GUI fallbacks."
        ),
        "submission_date": day_str,
        "investigation_name": INVESTIGATION_TITLE,
        "investigation_description": INVESTIGATION_DESCRIPTION,
        "people": [dict(p) for p in PEOPLE],
        "publications": [],
        "study_design_descriptors": [
            {
                "annotationValue": "exploratory design",
                "termSource": "OBI",
                "termAccession": "",
            }
        ],
        "factors": [],
        "materials": {"sources": [], "samples": [], "otherMaterials": []},
        "process_sequence": {"processes": []},
        "protocols": [],
        "assays": [],
    }

    assay_samples = []
    for i in range(1, 3):
        assay_samples.append(
            {
                "@id": f"#{study_id}#sample_S{i}",
                "name": f"S{i}",
                "materialType": "sample",
                "characteristics": [dict(MATERIAL_TYPE_CHARACTERISTIC)],
                "derivesFrom": [],
            }
        )

    file_specs: List[Dict[str, Any]] = []
    _add_assays(
        rng,
        study_data,
        study_id,
        day_str,
        assay_samples,
        [],
        file_specs,
    )

    study_data["protocols"] = _protocol_declarations()

    exporter = ISAJsonExporter(
        study_data=study_data, investigation_id=investigation_id, study_id=study_id
    )
    doc = exporter.export_complete_isa_json()

    meta = {
        "study_id": study_id,
        "kind": "assay_only",
        "title": study_data["study_name"],
        "description": study_data["study_description"],
        "submission_date": day_str,
        "materials": {"sources": [], "samples": [], "otherMaterials": []},
        "processes": [],
        "assays": study_data["assays"],
    }
    return doc, meta, file_specs


def _build_empty_study(
    investigation_id: str, study_id: str, day: date
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Build a deliberately empty study (exercises GUI empty states)."""
    day_str = day.isoformat()
    study_data: Dict[str, Any] = {
        "identifier": study_id,
        "study_name": f"Dummy study {study_id} — empty",
        "study_description": (
            f"Deliberately empty dummy study {study_id} to exercise the GUI " "empty states."
        ),
        "submission_date": day_str,
        "investigation_name": INVESTIGATION_TITLE,
        "investigation_description": INVESTIGATION_DESCRIPTION,
        "people": [],
        "publications": [],
        "study_design_descriptors": [],
        "factors": [],
        "materials": {"sources": [], "samples": [], "otherMaterials": []},
        "process_sequence": {"processes": []},
        "protocols": [],
        "assays": [],
    }
    exporter = ISAJsonExporter(
        study_data=study_data, investigation_id=investigation_id, study_id=study_id
    )
    doc = exporter.export_complete_isa_json()
    meta = {
        "study_id": study_id,
        "kind": "empty",
        "title": study_data["study_name"],
        "description": study_data["study_description"],
        "submission_date": day_str,
        "materials": {"sources": [], "samples": [], "otherMaterials": []},
        "processes": [],
        "assays": [],
    }
    return doc, meta, []


def _protocol_declarations() -> List[Dict[str, Any]]:
    """Protocol declarations referenced by the generated processes."""
    return [
        {
            "name": "sample dilution",
            "description": "Dilution of donor material before treatment.",
            "type": "sample dilution",
            "parameters": [
                {
                    "@id": "#parameter/dilution_factor",
                    "parameterName": {"annotationValue": "dilution factor", "termSource": "OBI"},
                }
            ],
            "components": [],
        },
        {
            "name": "treatment incubation",
            "description": "Incubation of samples under treatment conditions.",
            "type": "incubation",
            "parameters": [
                {
                    "@id": "#parameter/incubation_time",
                    "parameterName": {"annotationValue": "incubation time", "termSource": "OBI"},
                },
                {
                    "@id": "#parameter/temperature",
                    "parameterName": {"annotationValue": "temperature", "termSource": "OBI"},
                },
            ],
            "components": [],
        },
        {
            "name": "aliquot preparation",
            "description": "Splitting treated samples into assay aliquots.",
            "type": "sample division",
            "parameters": [
                {
                    "@id": "#parameter/aliquot_volume",
                    "parameterName": {"annotationValue": "aliquot volume", "termSource": "OBI"},
                }
            ],
            "components": [],
        },
        {
            "name": "image acquisition",
            "description": "Fluorescence image acquisition for calcein assays.",
            "type": "data acquisition",
            "parameters": [
                {
                    "@id": "#parameter/exposure_time",
                    "parameterName": {"annotationValue": "exposure time", "termSource": "OBI"},
                }
            ],
            "components": [],
        },
        {
            "name": "flow cytometry acquisition",
            "description": "FACS acquisition of live/dead stained samples.",
            "type": "data acquisition",
            "parameters": [
                {
                    "@id": "#parameter/event_count",
                    "parameterName": {"annotationValue": "event count", "termSource": "OBI"},
                }
            ],
            "components": [],
        },
        {
            "name": "ELISA readout",
            "description": "ELISA plate readout.",
            "type": "data acquisition",
            "parameters": [
                {
                    "@id": "#parameter/wavelength",
                    "parameterName": {"annotationValue": "wavelength", "termSource": "OBI"},
                }
            ],
            "components": [],
        },
    ]


def _add_assays(
    rng: random.Random,
    study_data: Dict[str, Any],
    study_id: str,
    day_str: str,
    samples: List[Dict[str, Any]],
    other_materials: List[Dict[str, Any]],
    file_specs: List[Dict[str, Any]],
) -> None:
    """Append the calcein / facs / elisa assays to *study_data*.

    Each assay carries ``materials`` (sample + otherMaterial refs) and a
    ``processSequence`` (exercising the GUI merge at
    ``gui/pages/process_sequence.py``) plus ``dataFiles`` that reference
    real placeholder files (added to *file_specs*).
    """
    for assay_def in ASSAY_DEFS:
        key = assay_def["key"]
        assay_id = f"#assay/{study_id}_{key}"

        data_files: List[Dict[str, Any]] = []
        outputs: List[Dict[str, Any]] = []
        for i, sample in enumerate(samples, start=1):
            file_name = f"{key}_S{i}_{day_str.replace('-', '')}.{assay_def['file_ext']}"
            data_file_id = f"#data/{study_id}_{key}_file_{i:02d}"
            data_files.append(
                {
                    "@id": data_file_id,
                    "name": file_name,
                    "filename": file_name,
                    "type": assay_def["data_type"],
                    "path": f"files/original/{file_name}",
                    "comments": [
                        {"name": "Original file", "value": "true"},
                        {"name": "File format", "value": assay_def["file_ext"]},
                        {"name": "TraceDB", "value": f"files/original/{file_name}"},
                    ],
                }
            )
            outputs.append({"@id": data_file_id})
            file_specs.append(
                {
                    "study_id": study_id,
                    "name": file_name,
                    "ext": assay_def["file_ext"],
                    "label": f"{assay_def['name']} {sample.get('name', f'S{i}')}",
                }
            )

        sample_inputs = [{"@id": s["@id"]} for s in samples]
        assay: Dict[str, Any] = {
            "@id": assay_id,
            "name": assay_def["name"],
            "assay_type": key,
            "measurementType": dict(assay_def["measurement_type"]),
            "technologyType": dict(assay_def["technology_type"]),
            "inputs": sample_inputs,
            "materials": {
                "samples": [dict(s) for s in samples],
                "otherMaterials": [dict(m) for m in other_materials],
            },
            "processSequence": [
                {
                    "@id": f"{assay_id}#process_{key}",
                    "name": assay_def["process_name"],
                    "executesProtocol": assay_def["protocol_name"],
                    "date": day_str,
                    "performer": rng.choice(["Jane Doe", "John Smith"]),
                    "inputs": sample_inputs,
                    "outputs": outputs,
                }
            ],
            "parameters": [dict(p) for p in assay_def["parameters"]],
            "dataFiles": data_files,
        }
        study_data["assays"].append(assay)


# ----------------------------------------------------------------------
# Export enrichment (fields the exporter normalizes away)
# ----------------------------------------------------------------------


def _enrich_study(doc: Dict[str, Any], meta: Dict[str, Any]) -> None:
    """Restore the fields every GUI loader reads but the exporter strips.

    Adds ``materialType`` / ``derivesFrom`` to materials, ``performer`` /
    ``status`` / ``comments`` to processes, and the declared
    characteristic/unit categories.  Also guarantees the study-level
    material sections are complete (the exporter keeps only otherMaterials
    referenced from the study-level process sequence).
    """
    study = doc["studies"][0]

    # 1. Study-level materials: canonical records with every required field.
    study["materials"] = {
        "sources": [
            {
                "@id": m.get("@id", ""),
                "name": m.get("name", ""),
                "materialType": "source",
                "characteristics": m.get("characteristics", []),
                "derivesFrom": m.get("derivesFrom", []),
            }
            for m in meta["materials"]["sources"]
        ],
        "samples": [
            {
                "@id": m.get("@id", ""),
                "name": m.get("name", ""),
                "materialType": "sample",
                "characteristics": m.get("characteristics", []),
                "derivesFrom": m.get("derivesFrom", []),
                "factorValues": m.get("factorValues", []),
            }
            for m in meta["materials"]["samples"]
        ],
        "otherMaterials": [
            {
                "@id": m.get("@id", ""),
                "type": "Extract Name",
                "name": m.get("name", ""),
                "materialType": "otherMaterial",
                "characteristics": m.get("characteristics", []),
                "derivesFrom": m.get("derivesFrom", []),
            }
            for m in meta["materials"]["otherMaterials"]
        ],
    }

    # 2. Study-level processes: performer / status / comments round-trip.
    meta_by_name = {p.get("name", ""): p for p in meta["processes"]}
    for process in study.get("processSequence", []):
        record = meta_by_name.get(process.get("name", ""), {})
        process["performer"] = record.get("performer", "")
        process["status"] = record.get("status", "Pending")
        comments = process.setdefault("comments", [])
        if not any(c.get("name") == "status" for c in comments):
            comments.append({"name": "status", "value": process["status"]})
        for comment in record.get("comments", []):
            if comment not in comments:
                comments.append(comment)

    # 3. Declared categories (the exporter only knows three fixed ones).
    study["characteristicCategories"] = [
        dict(c) for c in (CHARACTERISTIC_CATEGORIES if meta["kind"] != "empty" else [])
    ]
    study["unitCategories"] = [
        dict(u) for u in (UNIT_CATEGORIES if meta["kind"] != "empty" else [])
    ]

    # 4. Assays: enrich sample refs with names so the fallback renderer
    #    (materials.py _collect_assay_materials) has meaningful rows.
    #    Index both study-level samples and assay-level sample records.
    samples_by_id = {m.get("@id", ""): m for m in meta["materials"]["samples"]}
    for assay in meta.get("assays", []):
        for sample in assay.get("materials", {}).get("samples", []):
            samples_by_id.setdefault(sample.get("@id", ""), sample)
    for assay in study.get("assays", []):
        for sample in assay.get("materials", {}).get("samples", []):
            record = samples_by_id.get(sample.get("@id", ""))
            if record:
                sample.setdefault("name", record.get("name", ""))
                sample.setdefault("materialType", "sample")
                sample.setdefault("characteristics", record.get("characteristics", []))
                sample.setdefault("derivesFrom", record.get("derivesFrom", []))

    # 5. Study identifier/title bookkeeping.
    study["title"] = meta["title"]
    study["description"] = meta["description"]


def _investigation_shell(doc: Dict[str, Any], study_id: str, meta: Dict[str, Any]) -> None:
    """Add the per-study document shell (mirrors the historical dummies)."""
    doc["@id"] = f"#investigation/{study_id}"
    doc["identifier"] = study_id
    doc["title"] = meta["title"]
    doc["description"] = "Synthetic study generated for testing purposes."
    doc["submissionDate"] = meta["submission_date"]
    doc["publicReleaseDate"] = ""
    comments = doc.setdefault("comments", [])
    comments.append({"name": "Generated by", "value": "generate_dummy_studies.py"})
    comments.append({"name": "dummy_data", "value": "true"})


# ----------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------


def generate_dummy_studies(
    out_dir: str = DEFAULT_OUT,
    count: int = DEFAULT_COUNT,
    seed: int = DEFAULT_SEED,
    investigation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Regenerate the dummy-studies investigation.

    Args:
        out_dir: Output (investigation) directory.  Relative paths are
            resolved against the repository root.  The directory is
            deleted and recreated.
        count: Total number of studies to generate (populated + empty).
        seed: RNG seed -- the output is fully deterministic per seed.
        investigation_id: Investigation id (default: the output dir name).

    Returns:
        Summary dict (counts, per-study information) for tests/CLI.
    """
    out_path = Path(out_dir)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    inv_id = investigation_id or out_path.name
    rng = random.Random(seed)

    if count < 2:
        raise ValueError("count must be >= 2 (need at least one populated and one empty study)")

    # Fresh dataset every run (investigations/ is gitignored).
    if out_path.exists():
        shutil.rmtree(out_path)
    studies_root = out_path / "studies"
    studies_root.mkdir(parents=True)

    empty_count = 2 if count >= 8 else 1
    full_count = count - empty_count
    # With enough room, one populated study stores its materials only at
    # the assay level (exercises the Materials-page fallback).
    assay_only_index = full_count if full_count >= 6 else 0

    base_day = date(2025, 6, 12) + timedelta(days=seed % 90)

    study_summaries: List[Dict[str, Any]] = []
    for i in range(1, count + 1):
        study_id = f"study_D{i:03d}"
        day = base_day + timedelta(days=rng.randint(0, 30))
        if i > full_count:
            doc, meta, file_specs = _build_empty_study(inv_id, study_id, day)
        elif i == assay_only_index:
            doc, meta, file_specs = _build_assay_only_study(rng, inv_id, study_id, day)
        else:
            doc, meta, file_specs = _build_full_study(rng, inv_id, study_id, day)

        _enrich_study(doc, meta)
        _investigation_shell(doc, study_id, meta)

        study_dir = studies_root / study_id
        (study_dir / "files" / "original").mkdir(parents=True, exist_ok=True)
        (study_dir / "files" / "converted").mkdir(parents=True, exist_ok=True)

        for spec in file_specs:
            original = study_dir / "files" / "original" / spec["name"]
            _write_placeholder_file(original, spec["label"], rng)
            # Converted twin: same content, TIFF for images, copy otherwise.
            converted_name = Path(spec["name"]).stem + (
                ".tif" if spec["ext"] == "png" else f".{spec['ext']}"
            )
            converted = study_dir / "files" / "converted" / converted_name
            if spec["ext"] == "png":
                _write_placeholder_image(converted, spec["label"], rng)
            else:
                shutil.copyfile(original, converted)

        study_json = study_dir / "study.json"
        with open(study_json, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)

        study_summaries.append(
            {
                "@id": f"#study/{study_id}",
                "filename": f"studies/{study_id}",
                "identifier": study_id,
                "title": meta["title"],
                "description": meta["description"],
                "submissionDate": meta["submission_date"],
                "publicReleaseDate": "",
                "kind": meta["kind"],
            }
        )

    # Investigation JSON, regenerated in sync with the per-study files.
    inv_doc = {
        "@id": f"#investigation/{inv_id}",
        "identifier": inv_id,
        "title": INVESTIGATION_TITLE,
        "description": INVESTIGATION_DESCRIPTION,
        "submissionDate": base_day.isoformat(),
        "publicReleaseDate": "",
        "studies": [
            {k: v for k, v in summary.items() if k != "kind"} for summary in study_summaries
        ],
    }
    with open(out_path / f"{inv_id}.json", "w", encoding="utf-8") as fh:
        json.dump(inv_doc, fh, indent=2, ensure_ascii=False)

    return {
        "investigation_id": inv_id,
        "out_dir": str(out_path),
        "seed": seed,
        "count": count,
        "empty": empty_count,
        "assay_only": 1 if assay_only_index else 0,
        "studies": study_summaries,
    }


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Regenerate the representative dummy-studies investigation",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=DEFAULT_OUT,
        help=f"Output investigation directory (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help=f"Total number of studies (default: {DEFAULT_COUNT})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"RNG seed for deterministic output (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--investigation-id",
        type=str,
        default=None,
        help="Investigation id (default: the output directory name)",
    )
    args = parser.parse_args(argv)

    try:
        summary = generate_dummy_studies(
            out_dir=args.out,
            count=args.count,
            seed=args.seed,
            investigation_id=args.investigation_id,
        )
    except Exception as exc:  # pragma: no cover - CLI failure path
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
