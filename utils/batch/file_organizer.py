"""
File Organizer for organizing converted files into ISA-JSON structure.

This module organizes converted files into the proper directory structure
for ISA-JSON format, ensuring files are placed in the correct locations.
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.batch.format_converter import ConversionResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FileOrganizer:
    """Organizer for converted files into ISA-JSON structure."""

    def __init__(self, investigation_id: str = "inv_default"):
        """
        Initialize the file organizer.

        Args:
            investigation_id: Investigation identifier
        """
        self.investigation_id = investigation_id
        self.logger = logging.getLogger(__name__)

    def organize_investigation(
        self,
        conversion_results: List[ConversionResult],
        output_dir: str,
        investigation_json: Dict[str, Any],
        data_root: Optional[str] = None,
    ) -> str:
        """
        Organize all files for an investigation into ISA-JSON structure.

        Creates a lightweight investigation JSON (with study references only)
        and per-study subfolders with full study.json and files/original/
        and files/converted/ directories.

        The investigation_json may contain full study data (with assays, materials,
        etc.) or lightweight references. This method splits them appropriately:
        - Investigation JSON gets lightweight study references
        - Each study's full data is saved in its own study.json

        Args:
            conversion_results: List of conversion results
            output_dir: Output directory for organized files
            investigation_json: ISA-JSON investigation data (may have full studies)
            data_root: Root directory of source data files for copying

        Returns:
            Path to organized investigation directory
        """
        output_path = Path(output_dir)
        investigation_path = output_path / self.investigation_id

        # Create investigation directory
        investigation_path.mkdir(parents=True, exist_ok=True)

        # Build lightweight investigation JSON (study references only)
        studies = investigation_json.get("studies", [])
        lightweight_studies = []
        for study in studies:
            lightweight_studies.append(
                {
                    "@id": study.get("@id", ""),
                    "filename": study.get("filename", ""),
                    "identifier": study.get("identifier", ""),
                    "title": study.get("title", ""),
                    "description": study.get("description", ""),
                    "submissionDate": study.get("submissionDate", ""),
                    "publicReleaseDate": study.get("publicReleaseDate", ""),
                }
            )

        lightweight_inv = dict(investigation_json)
        lightweight_inv["studies"] = lightweight_studies

        # Save lightweight investigation JSON
        investigation_file = investigation_path / f"{self.investigation_id}.json"
        with open(investigation_file, "w", encoding="utf-8") as f:
            json.dump(lightweight_inv, f, indent=2, default=str)

        self.logger.info(f"Saved lightweight investigation JSON to {investigation_file}")

        # Organize files for each study (using full study data)
        for study in studies:
            self._organize_study(conversion_results, investigation_path, study, data_root=data_root)

        return str(investigation_path)

    def _organize_study(
        self,
        conversion_results: List[ConversionResult],
        investigation_path: Path,
        study: Dict[str, Any],
        data_root: Optional[str] = None,
    ) -> str:
        """
        Organize files for a study into its own subfolder.

        Creates the following structure:
            studies/{study_id}/
              study.json          (if not already saved by generator)
              files/
                original/         (original format data files)
                converted/        (open format data files)

        Args:
            conversion_results: List of conversion results
            investigation_path: Path to investigation directory
            study: Study data from ISA-JSON
            data_root: Root directory of source data files for copying

        Returns:
            Path to study directory
        """
        study_id = study.get("identifier", "unknown_study")
        study_path = investigation_path / "studies" / study_id

        # Create study directory
        study_path.mkdir(parents=True, exist_ok=True)

        # Save study JSON only if it contains full data (has assays with dataFiles)
        # The generator may have already saved it, so check first
        study_file = study_path / "study.json"
        if not study_file.exists() and study.get("assays"):
            with open(study_file, "w", encoding="utf-8") as f:
                json.dump(study, f, indent=2, default=str)
            self.logger.info(f"Saved study JSON to {study_file}")

        # Create files subdirectories
        files_path = study_path / "files"
        original_path = files_path / "original"
        converted_path = files_path / "converted"
        original_path.mkdir(parents=True, exist_ok=True)
        converted_path.mkdir(parents=True, exist_ok=True)

        # Collect all data files from all assays in this study
        all_data_files = []
        for assay in study.get("assays", []):
            all_data_files.extend(assay.get("dataFiles", []))

        # Copy original and converted files
        self._organize_study_files(
            conversion_results, all_data_files, original_path, converted_path, data_root
        )

        return str(study_path)

    def _organize_study_files(
        self,
        conversion_results: List[ConversionResult],
        data_files: List[Dict[str, Any]],
        original_path: Path,
        converted_path: Path,
        data_root: Optional[str] = None,
    ) -> None:
        """
        Copy original and converted data files into study subfolders.

        Args:
            conversion_results: List of conversion results
            data_files: List of data file entries from ISA-JSON
            original_path: Path to files/original/ directory
            converted_path: Path to files/converted/ directory
            data_root: Root directory of source data files for copying
        """
        for data_file in data_files:
            filename = data_file.get("name", "")
            if not filename:
                continue

            # Try to find the source file in conversion results
            source_found = False
            for result in conversion_results:
                source_name = Path(result.source_file).name
                if source_name == filename:
                    # Copy original file
                    source = Path(result.source_file)
                    if source.exists():
                        dest = original_path / source_name
                        if not dest.exists():
                            shutil.copy2(source, dest)
                            self.logger.info(f"Copied original: {source_name}")
                        source_found = True

                    # Copy converted file
                    if result.target_file and Path(result.target_file).exists():
                        converted_name = Path(result.target_file).name
                        dest = converted_path / converted_name
                        if not dest.exists():
                            shutil.copy2(result.target_file, dest)
                            self.logger.info(f"Copied converted: {converted_name}")
                    break

            # If not found in conversion results, try data_root
            if not source_found and data_root:
                self._copy_from_data_root(filename, original_path, data_root)

    def _copy_from_data_root(self, filename: str, original_path: Path, data_root: str) -> None:
        """
        Search for a file in the data root and copy it to original/.

        Args:
            filename: Name of the file to find
            original_path: Destination directory for original files
            data_root: Root directory to search in
        """
        data_root_path = Path(data_root)
        if not data_root_path.exists():
            return

        # Search recursively for the file
        for candidate in data_root_path.rglob(filename):
            dest = original_path / filename
            if not dest.exists():
                shutil.copy2(candidate, dest)
                self.logger.info(f"Copied original from data_root: {filename}")
                return

    def _organize_assay(
        self, conversion_results: List[ConversionResult], study_path: Path, assay: Dict[str, Any]
    ) -> str:
        """
        Organize files for an assay.

        Args:
            conversion_results: List of conversion results
            study_path: Path to study directory
            assay: Assay data from ISA-JSON

        Returns:
            Path to assay directory
        """
        assay_id = assay.get("assay_id", "unknown_assay")
        assay_path = study_path / "assays" / assay_id

        # Create assay directory
        assay_path.mkdir(parents=True, exist_ok=True)

        # Save assay JSON
        assay_file = assay_path / "assay.json"
        with open(assay_file, "w", encoding="utf-8") as f:
            json.dump(assay, f, indent=2, default=str)

        self.logger.info(f"Saved assay JSON to {assay_file}")

        # Organize data files
        data_files = assay.get("dataFiles", [])
        for data_file in data_files:
            self._organize_data_file(conversion_results, assay_path, data_file)

        return str(assay_path)

    def _organize_data_file(
        self,
        conversion_results: List[ConversionResult],
        assay_path: Path,
        data_file: Dict[str, Any],
    ) -> str:
        """
        Organize a single data file.

        Args:
            conversion_results: List of conversion results
            assay_path: Path to assay directory
            data_file: Data file information

        Returns:
            Path to organized file
        """
        filename = data_file.get("filename", "unknown_file")
        original_path = data_file.get("path", "")

        # Find the converted file in conversion results
        target_file = None
        for result in conversion_results:
            if original_path in result.source_file:
                target_file = result.target_file
                break

        if target_file and Path(target_file).exists():
            # Copy converted file to assay directory
            dest_path = assay_path / filename
            shutil.copy2(target_file, dest_path)

            # Copy metadata file if exists
            if result.metadata_file and Path(result.metadata_file).exists():
                metadata_dest = assay_path / f"{Path(filename).stem}_metadata.json"
                shutil.copy2(result.metadata_file, metadata_dest)

            self.logger.info(f"Organized file: {filename}")
            return str(dest_path)
        else:
            self.logger.warning(f"Could not find converted file for: {filename}")
            return ""

    def create_material_references(
        self, investigation_json: Dict[str, Any], inv_inm_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create material references to inv_inm investigation.

        Args:
            investigation_json: ISA-JSON investigation data
            inv_inm_path: Path to inv_inm investigation

        Returns:
            Updated investigation JSON with material references
        """
        if not inv_inm_path:
            self.logger.info("No inv_inm path provided, skipping material references")
            return investigation_json

        inv_inm_file = Path(inv_inm_path) / "inv_inm" / "inv_inm.json"

        if not inv_inm_file.exists():
            self.logger.warning(f"inv_inm investigation file not found: {inv_inm_file}")
            return investigation_json

        # Load inv_inm investigation
        try:
            with open(inv_inm_file, "r", encoding="utf-8") as f:
                inv_inm_data = json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading inv_inm investigation: {e}")
            return investigation_json

        # Extract material references from inv_inm
        material_refs = self._extract_material_references(inv_inm_data)

        # Add material references to inv_ukf studies
        studies = investigation_json.get("studies", [])
        for study in studies:
            study["materialReferences"] = material_refs

        self.logger.info(f"Added {len(material_refs)} material references to inv_ukf")
        return investigation_json

    def _extract_material_references(self, inv_inm_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract material references from inv_inm investigation.

        Args:
            inv_inm_data: inv_inm investigation data

        Returns:
            List of material reference dictionaries
        """
        material_refs = []

        studies = inv_inm_data.get("studies", [])
        for study in studies:
            # Extract sources
            sources = study.get("materials", {}).get("sources", [])
            for source in sources:
                material_refs.append(
                    {
                        "materialType": "source",
                        "materialId": source.get("name", ""),
                        "investigationId": "inv_inm",
                        "studyId": study.get("identifier", ""),
                    }
                )

            # Extract samples
            samples = study.get("materials", {}).get("samples", [])
            for sample in samples:
                material_refs.append(
                    {
                        "materialType": "sample",
                        "materialId": sample.get("name", ""),
                        "investigationId": "inv_inm",
                        "studyId": study.get("identifier", ""),
                    }
                )

        return material_refs

    def organize_metadata_files(
        self, conversion_results: List[ConversionResult], output_dir: str
    ) -> str:
        """
        Organize metadata files into a dedicated metadata directory.

        Args:
            conversion_results: List of conversion results
            output_dir: Output directory

        Returns:
            Path to metadata directory
        """
        output_path = Path(output_dir)
        metadata_path = output_path / "metadata"

        # Create metadata directory
        metadata_path.mkdir(parents=True, exist_ok=True)

        # Copy all metadata files
        for result in conversion_results:
            if result.metadata_file and Path(result.metadata_file).exists():
                dest_name = Path(result.metadata_file).name
                dest_path = metadata_path / dest_name
                shutil.copy2(result.metadata_file, dest_path)

        # Create metadata index
        metadata_index = {
            "generation_date": datetime.now().isoformat(),
            "total_metadata_files": len([r for r in conversion_results if r.metadata_file]),
            "metadata_files": [
                {
                    "source": r.source_file,
                    "metadata_file": Path(r.metadata_file).name if r.metadata_file else None,
                }
                for r in conversion_results
                if r.metadata_file
            ],
        }

        index_file = metadata_path / "metadata_index.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(metadata_index, f, indent=2)

        self.logger.info(f"Organized metadata files to {metadata_path}")
        return str(metadata_path)

    def create_directory_manifest(self, investigation_path: str) -> Dict[str, Any]:
        """
        Create a manifest of the organized directory structure.

        Args:
            investigation_path: Path to investigation directory

        Returns:
            Directory manifest dictionary
        """
        inv_path = Path(investigation_path)

        manifest = {
            "investigation_id": self.investigation_id,
            "investigation_path": str(inv_path),
            "creation_date": datetime.now().isoformat(),
            "directory_structure": self._build_directory_structure(inv_path),
            "file_count": self._count_files(inv_path),
            "total_size_bytes": self._calculate_total_size(inv_path),
        }

        # Save manifest
        manifest_file = inv_path / "directory_manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        self.logger.info(f"Created directory manifest at {manifest_file}")
        return manifest

    def _build_directory_structure(self, path: Path, max_depth: int = 3) -> Dict[str, Any]:
        """
        Build a recursive directory structure.

        Args:
            path: Path to analyze
            max_depth: Maximum depth to traverse

        Returns:
            Directory structure dictionary
        """
        if max_depth <= 0 or not path.is_dir():
            return {}

        structure: Dict[str, Any] = {"name": path.name, "type": "directory", "children": []}

        try:
            for item in sorted(path.iterdir()):
                if item.is_dir():
                    structure["children"].append(
                        self._build_directory_structure(item, max_depth - 1)
                    )
                else:
                    structure["children"].append(
                        {"name": item.name, "type": "file", "size": item.stat().st_size}
                    )
        except PermissionError:
            structure["error"] = "Permission denied"

        return structure

    def _count_files(self, path: Path) -> int:
        """
        Count total files in directory tree.

        Args:
            path: Path to analyze

        Returns:
            Total file count
        """
        count = 0
        try:
            for item in path.rglob("*"):
                if item.is_file():
                    count += 1
        except PermissionError:
            pass
        return count

    def _calculate_total_size(self, path: Path) -> int:
        """
        Calculate total size of all files.

        Args:
            path: Path to analyze

        Returns:
            Total size in bytes
        """
        total_size = 0
        try:
            for item in path.rglob("*"):
                if item.is_file():
                    total_size += item.stat().st_size
        except PermissionError:
            pass
        return total_size


def main():
    """Main function for testing the file organizer."""
    import sys

    from utils.batch.folder_scanner import FolderScanner
    from utils.batch.format_converter import FormatConverter
    from utils.batch.isa_json_generator import ISAJsonGenerator

    # Test parameters
    test_folder = "partner representative data"
    output_dir = "organized_output"
    inv_inm_path = "investigations/inv_1"

    if len(sys.argv) > 1:
        test_folder = sys.argv[1]
    if len(sys.argv) > 2:
        output_dir = sys.argv[2]
    if len(sys.argv) > 3:
        inv_inm_path = sys.argv[3]

    # Step 1: Scan experiments
    print("Step 1: Scanning experiments...")
    scanner = FolderScanner(test_folder)
    experiments = scanner.scan_experiments()
    print(f"  Found {len(experiments)} experiments")

    # Step 2: Convert files
    print("\nStep 2: Converting files...")
    converter = FormatConverter()
    conversion_dir = f"{output_dir}/converted"
    conversion_results = converter.batch_convert_folder(test_folder, conversion_dir)
    converted_count = len([r for r in conversion_results if r.success])
    print(f"  Converted {converted_count}/{len(conversion_results)} files")

    # Step 3: Generate ISA-JSON
    from utils.config_loader import get_profile

    defaults = get_profile().get_investigation_defaults()
    inv_id = defaults.get("investigation_id", "inv_default")
    inv_title = defaults.get("default_investigation_title", "Partner Data Investigation")
    inv_desc = defaults.get("default_investigation_description", "Investigation of partner data")
    print("\nStep 3: Generating ISA-JSON...")
    generator = ISAJsonGenerator()
    investigation = generator.generate_investigation(
        experiments=experiments,
        investigation_id=inv_id,
        investigation_title=inv_title,
        investigation_description=inv_desc,
    )

    # Convert investigation to lightweight dictionary (study references only)
    investigation_dict = generator._investigation_to_dict_lightweight(investigation)

    # Also get full study dicts for file organization
    _full_studies = [generator._study_to_dict(s) for s in investigation.studies]  # noqa: F841

    # Step 4: Organize files
    print("\nStep 4: Organizing files...")
    organizer = FileOrganizer(investigation_id=inv_id)

    # Add material references
    investigation_dict = organizer.create_material_references(investigation_dict, inv_inm_path)

    # Organize investigation with full study data for file copying
    inv_path = organizer.organize_investigation(
        conversion_results, output_dir, investigation_dict, data_root=test_folder
    )

    # Organize metadata files
    organizer.organize_metadata_files(conversion_results, output_dir)

    # Create directory manifest
    manifest = organizer.create_directory_manifest(inv_path)

    print("\nFile organization complete:")
    print(f"  Investigation path: {inv_path}")
    print(f"  Total files: {manifest['file_count']}")
    print(f"  Total size: {manifest['total_size_bytes'] / (1024*1024):.2f} MB")


if __name__ == "__main__":
    main()
