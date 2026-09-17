"""
Folder Scanner for discovering experiment folders in partner data.

This module scans the partner representative data directory to discover
experiment folders and extract basic metadata.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class FileInventory:
    """Inventory of files in an experiment folder."""

    czi_files: List[str] = field(default_factory=list)
    tiff_files: List[str] = field(default_factory=list)
    tiff_metadata_files: List[str] = field(default_factory=list)
    fcs_files: List[str] = field(default_factory=list)
    wsp_files: List[str] = field(default_factory=list)
    xlsx_files: List[str] = field(default_factory=list)
    xml_files: List[str] = field(default_factory=list)
    png_files: List[str] = field(default_factory=list)
    jpg_files: List[str] = field(default_factory=list)
    other_files: List[str] = field(default_factory=list)

    def get_all_files(self) -> List[str]:
        """Get all files in the inventory."""
        return (
            self.czi_files
            + self.tiff_files
            + self.tiff_metadata_files
            + self.fcs_files
            + self.wsp_files
            + self.xlsx_files
            + self.xml_files
            + self.png_files
            + self.jpg_files
            + self.other_files
        )

    def get_file_count(self) -> int:
        """Get total number of files."""
        return len(self.get_all_files())


@dataclass
class SubdirectoryHints:
    """Automatically detected subdirectory structure hints.

    Captures patterns found in experiment folder subdirectories that encode
    experimental metadata (timepoints, processing states, assay types).
    """

    # Timepoint directories: D0, D1, Day1, Day2, T0, T1, etc.
    timepoint_dirs: Dict[str, str] = field(default_factory=dict)
    # e.g., {"D0": "Day 0", "D1": "Day 1"}

    # Processing state directories: filtriert, unfiltriert, filtered, raw, etc.
    processing_dirs: Dict[str, str] = field(default_factory=dict)
    # e.g., {"filtriert": "filtered", "unfiltriert": "unfiltered"}

    # Assay-type directories: FACS/, Microscopy/, ELISA/, Calcein/, DAPI/
    assay_dirs: Dict[str, str] = field(default_factory=dict)
    # e.g., {"FACS": "facs", "Calcein": "calcein"}

    # All immediate subdirectory names (for config-driven matching)
    immediate_subdirs: List[str] = field(default_factory=list)

    # Files grouped by their immediate parent subdirectory
    files_by_subdir: Dict[str, List[str]] = field(default_factory=dict)
    # e.g., {"D0": ["file1.fcs", "file2.fcs"], "D1": ["file3.fcs"]}

    # Whether any meaningful subdirectory structure was detected
    has_structure: bool = False


@dataclass
class FolderMetadata:
    """Metadata extracted from experiment folder."""

    experiment_id: str
    experiment_name: str
    folder_path: str
    created_date: Optional[str] = None
    modified_date: Optional[str] = None
    file_count: int = 0
    file_inventory: Optional[FileInventory] = None
    subdirectory_hints: Optional[SubdirectoryHints] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


class FolderScanner:
    """Scanner for discovering experiment folders."""

    def __init__(self, data_root: str):
        """
        Initialize the folder scanner.

        Args:
            data_root: Root directory containing experiment folders
        """
        self.data_root = Path(data_root)
        self.logger = logging.getLogger(__name__)

    def scan_experiments(self) -> List[FolderMetadata]:
        """
        Scan for experiment folders in the data root.

        Returns:
            List of folder metadata for each experiment
        """
        experiments: List[FolderMetadata] = []

        if not self.data_root.exists():
            self.logger.error(f"Data root does not exist: {self.data_root}")
            return experiments

        # Scan for experiment folders (starting with E followed by number)
        for item in self.data_root.iterdir():
            if item.is_dir():
                # Check if folder name matches experiment pattern (E1, E10, E100, etc.)
                if re.match(r"^E\d+", item.name):
                    metadata = self._extract_folder_metadata(item)
                    if metadata:
                        experiments.append(metadata)
                        self.logger.info(
                            f"Found experiment: {metadata.experiment_id} - {metadata.experiment_name}"  # noqa: E501
                        )

        self.logger.info(f"Total experiments found: {len(experiments)}")
        return experiments

    def _extract_folder_metadata(self, folder_path: Path) -> Optional[FolderMetadata]:
        """
        Extract metadata from an experiment folder.

        Args:
            folder_path: Path to the experiment folder

        Returns:
            FolderMetadata object
        """
        try:
            # Extract experiment ID and name from folder name
            experiment_id, experiment_name = self._parse_folder_name(folder_path.name)

            # Get file timestamps
            stat_info = folder_path.stat()
            created_date = datetime.fromtimestamp(stat_info.st_ctime).isoformat()
            modified_date = datetime.fromtimestamp(stat_info.st_mtime).isoformat()

            # Build file inventory
            file_inventory = self._build_file_inventory(folder_path)

            # Analyze subdirectory structure for experimental metadata hints
            subdirectory_hints = self._analyze_subdirectory_structure(folder_path)

            metadata = FolderMetadata(
                experiment_id=experiment_id,
                experiment_name=experiment_name,
                folder_path=str(folder_path),
                created_date=created_date,
                modified_date=modified_date,
                file_count=file_inventory.get_file_count(),
                file_inventory=file_inventory,
                subdirectory_hints=subdirectory_hints,
            )

            return metadata

        except Exception as e:
            self.logger.error(f"Error extracting metadata from {folder_path}: {e}")
            return None

    def _parse_folder_name(self, folder_name: str) -> tuple[str, str]:
        """
        Parse experiment ID and name from folder name.

        Args:
            folder_name: Name of the folder

        Returns:
            Tuple of (experiment_id, experiment_name)
        """
        # Extract experiment ID (E1, E10, E100, etc.)
        match = re.match(r"^(E\d+)", folder_name)
        if match:
            experiment_id = match.group(1)
            experiment_name = folder_name
        else:
            experiment_id = folder_name
            experiment_name = folder_name

        return experiment_id, experiment_name

    def _build_file_inventory(self, folder_path: Path) -> FileInventory:
        """
        Build inventory of files in a folder.

        Args:
            folder_path: Path to the folder

        Returns:
            FileInventory object
        """
        inventory = FileInventory()

        for item in folder_path.rglob("*"):
            if item.is_file():
                suffix = item.suffix.lower()
                relative_path = str(item.relative_to(folder_path))

                if suffix == ".czi":
                    inventory.czi_files.append(relative_path)
                elif suffix == ".tiff" or suffix == ".tif":
                    inventory.tiff_files.append(relative_path)
                elif suffix == ".xml":
                    # Check if it's a TIFF metadata file
                    if "tiff_metadata" in item.name:
                        inventory.tiff_metadata_files.append(relative_path)
                    else:
                        inventory.xml_files.append(relative_path)
                elif suffix == ".fcs":
                    inventory.fcs_files.append(relative_path)
                elif suffix == ".wsp":
                    inventory.wsp_files.append(relative_path)
                elif suffix == ".xlsx" or suffix == ".xls":
                    inventory.xlsx_files.append(relative_path)
                elif suffix == ".png":
                    inventory.png_files.append(relative_path)
                elif suffix == ".jpg" or suffix == ".jpeg":
                    inventory.jpg_files.append(relative_path)
                else:
                    inventory.other_files.append(relative_path)

        return inventory

    def _analyze_subdirectory_structure(self, folder_path: Path) -> SubdirectoryHints:
        """Analyze subdirectory structure for experimental metadata hints.

        Automatically detects:
        1. Timepoint dirs: D0, D1, Day1, Day2, T0, T1, Week1, etc.
        2. Processing state dirs: filtriert, unfiltriert, filtered, unfiltered, raw, processed
        3. Assay dirs: FACS/, Microscopy/, ELISA/, Calcein/, DAPI/
        4. German lab conventions: Filtriert vorher, unfiltriert, genommen

        Args:
            folder_path: Path to the experiment folder

        Returns:
            SubdirectoryHints with detected patterns
        """
        hints = SubdirectoryHints()

        if not folder_path.exists() or not folder_path.is_dir():
            return hints

        # Scan immediate subdirectories
        for item in sorted(folder_path.iterdir()):
            if not item.is_dir():
                continue
            name = item.name
            hints.immediate_subdirs.append(name)

            # Collect files per subdirectory
            subdir_files = []
            for f in item.rglob("*"):
                if f.is_file():
                    subdir_files.append(str(f.relative_to(folder_path)))
            if subdir_files:
                hints.files_by_subdir[name] = subdir_files

            # --- Timepoint detection ---
            # Pattern: D0, D1, D2, ..., Day0, Day1, T0, T1, Week1
            timepoint_match = re.match(r"^(D|Day|T|Time|Week|W)(\d+)$", name, re.IGNORECASE)
            if timepoint_match:
                raw_prefix = timepoint_match.group(1)
                num = timepoint_match.group(2)
                # Expand single-letter abbreviations to full words
                prefix_map = {"D": "Day", "T": "Time", "W": "Week"}
                prefix = prefix_map.get(raw_prefix.upper(), raw_prefix.capitalize())
                hints.timepoint_dirs[name] = f"{prefix} {num}"
                continue

            # --- Processing state detection ---
            # Sort by length descending so longer patterns match first
            # (e.g., 'unfiltriert' before 'filtriert')
            processing_map = [
                ("unfiltriert", "unfiltered"),
                ("unfiltered", "unfiltered"),
                ("filtriert", "filtered"),
                ("filtered", "filtered"),
                ("processed", "processed"),
                ("bearbeitet", "processed"),
                ("raw", "raw"),
                ("roh", "raw"),
            ]
            name_lower = name.lower()
            processing_matched = False
            for pattern, state in processing_map:
                if pattern in name_lower:
                    # Handle "Filtriert vorher" → "pre-filtered"
                    if "vorher" in name_lower or "before" in name_lower:
                        state = "pre-filtered"
                    hints.processing_dirs[name] = state
                    processing_matched = True
                    break

            if processing_matched:
                continue

            # C5: Compensation run detection
            # e.g., "alte Kompensation", "neue Kompensation", "Compensation vom 04.03"
            compensation_patterns = ["kompensation", "compensation", "compensierung"]
            for pattern in compensation_patterns:
                if pattern in name_lower:
                    hints.processing_dirs[name] = "compensation_run"
                    processing_matched = True
                    break

            if processing_matched:
                continue

            # --- Assay type detection ---
            assay_map = {
                "facs": "facs",
                "flow cytometry": "facs",
                "microscopy": "microscopy",
                "calcein": "calcein",
                "dapi": "dapi",
                "elisa": "elisa",
                "western blot": "western_blot",
                "wb": "western_blot",
                "tunel": "tunel",
                "slidescanner": "slidescanner",
            }
            for pattern, assay_type in assay_map.items():
                if pattern in name_lower:
                    hints.assay_dirs[name] = assay_type
                    break

        # Mark as having structure if any patterns were detected
        hints.has_structure = bool(
            hints.timepoint_dirs or hints.processing_dirs or hints.assay_dirs
        )

        return hints

    def get_file_inventory(self, folder_path: str) -> FileInventory:
        """
        Get file inventory for a specific folder.

        Args:
            folder_path: Path to the folder

        Returns:
            FileInventory object
        """
        folder = Path(folder_path)
        if not folder.exists():
            self.logger.error(f"Folder does not exist: {folder_path}")
            return FileInventory()

        return self._build_file_inventory(folder)

    def group_by_type(self, experiments: List[FolderMetadata]) -> Dict[str, List[FolderMetadata]]:
        """
        Group experiments by type based on folder name.

        Args:
            experiments: List of experiment metadata

        Returns:
            Dictionary mapping experiment types to lists of experiments
        """
        groups: Dict[str, List[FolderMetadata]] = {
            "facs": [],
            "calcein": [],
            "microscopy": [],
            "elisa": [],
            "western_blot": [],
            "tunel": [],
            "dapi": [],
            "he_staining": [],
            "gfap": [],
            "fluorescence": [],
            "other": [],
        }

        for exp in experiments:
            name_lower = exp.experiment_name.lower()

            if "facs" in name_lower or "annexin" in name_lower or "pi" in name_lower:
                groups["facs"].append(exp)
            elif "calcein" in name_lower:
                groups["calcein"].append(exp)
            elif "slidescanner" in name_lower or "microscopy" in name_lower:
                groups["microscopy"].append(exp)
            elif "elisa" in name_lower:
                groups["elisa"].append(exp)
            elif "wb" in name_lower or "western" in name_lower:
                groups["western_blot"].append(exp)
            elif "tunel" in name_lower:
                groups["tunel"].append(exp)
            elif "dapi" in name_lower:
                groups["dapi"].append(exp)
            elif "h und e" in name_lower or "h&e" in name_lower or "h-e" in name_lower:
                groups["he_staining"].append(exp)
            elif "gfap" in name_lower:
                groups["gfap"].append(exp)
            elif "fluoreszenzmessung" in name_lower or "fluorescence" in name_lower:
                groups["fluorescence"].append(exp)
            else:
                groups["other"].append(exp)

        # Log grouping results
        for exp_type, exp_list in groups.items():
            if exp_list:
                self.logger.info(f"Group '{exp_type}': {len(exp_list)} experiments")

        return groups

    def save_scan_results(self, experiments: List[FolderMetadata], output_path: str):
        """
        Save scan results to a JSON file.

        Args:
            experiments: List of experiment metadata
            output_path: Path to output JSON file
        """
        results = []
        for exp in experiments:
            result = {
                "experiment_id": exp.experiment_id,
                "experiment_name": exp.experiment_name,
                "folder_path": exp.folder_path,
                "created_date": exp.created_date,
                "modified_date": exp.modified_date,
                "file_count": exp.file_count,
                "file_inventory": (
                    {
                        "czi_files": exp.file_inventory.czi_files,
                        "tiff_files": exp.file_inventory.tiff_files,
                        "tiff_metadata_files": exp.file_inventory.tiff_metadata_files,
                        "fcs_files": exp.file_inventory.fcs_files,
                        "wsp_files": exp.file_inventory.wsp_files,
                        "xlsx_files": exp.file_inventory.xlsx_files,
                        "xml_files": exp.file_inventory.xml_files,
                        "png_files": exp.file_inventory.png_files,
                        "jpg_files": exp.file_inventory.jpg_files,
                        "other_files": exp.file_inventory.other_files,
                    }
                    if exp.file_inventory
                    else None
                ),
                "subdirectory_hints": (
                    {
                        "timepoint_dirs": exp.subdirectory_hints.timepoint_dirs,
                        "processing_dirs": exp.subdirectory_hints.processing_dirs,
                        "assay_dirs": exp.subdirectory_hints.assay_dirs,
                        "immediate_subdirs": exp.subdirectory_hints.immediate_subdirs,
                        "files_by_subdir": exp.subdirectory_hints.files_by_subdir,
                        "has_structure": exp.subdirectory_hints.has_structure,
                    }
                    if exp.subdirectory_hints
                    else None
                ),
            }
            results.append(result)

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved scan results to {output_path}")


def main():
    """Main function for testing the folder scanner."""
    import sys

    # Default to partner representative data directory
    data_root = "partner representative data"
    output_path = "scripts/scan_results.json"

    if len(sys.argv) > 1:
        data_root = sys.argv[1]
    if len(sys.argv) > 2:
        output_path = sys.argv[2]

    scanner = FolderScanner(data_root)
    experiments = scanner.scan_experiments()

    if experiments:
        # Group by type
        _groups = scanner.group_by_type(experiments)  # noqa: F841

        # Save results
        scanner.save_scan_results(experiments, output_path)

        print("\nScan complete!")
        print(f"Total experiments: {len(experiments)}")
        print(f"Results saved to: {output_path}")
    else:
        print("No experiments found.")


if __name__ == "__main__":
    main()
