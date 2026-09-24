"""
Batch processor for the ISA-JSON Data Steward 7-stage pipeline.

This module orchestrates the entire batch processing pipeline:
1. Scan experiment folders
2. Classify experiments
3. Extract metadata
4. Convert file formats
5. Generate ISA-JSON
6. Organize files
7. Validate results

It can be run from the command line::

    python -m utils.batch.batch_processor --data-root ./data --output-dir ./output
"""

import argparse
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.batch.experiment_classifier import ExperimentClassifier
from utils.batch.file_organizer import FileOrganizer
from utils.batch.folder_scanner import FolderMetadata, FolderScanner
from utils.batch.format_converter import ConversionResult, FormatConverter
from utils.batch.isa_json_generator import ISAJsonGenerator
from utils.batch.metadata_extractor import MetadataExtractor
from utils.batch.validator import DataFileValidator, ISAJsonValidator, MetadataValidator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BatchProcessingResult:
    """Result of batch processing operation."""

    total_experiments: int
    successful_experiments: int
    failed_experiments: int
    total_files: int
    converted_files: int
    failed_conversions: int
    validation_passed: bool
    processing_time_seconds: float
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)


class BatchProcessor:
    """Batch processor orchestrating the 7-stage ISA-JSON pipeline."""

    def __init__(
        self,
        investigation_id: str = "inv_default",
        inv_inm_path: Optional[str] = None,
        templates_root: Optional[str] = None,
    ):
        """
        Initialize the batch processor.

        Args:
            investigation_id: Investigation identifier
            inv_inm_path: Path to inv_inm investigation for material references
            templates_root: Optional assay-templates directory (the active
                profile's ``templates/assay_templates``). When provided, the
                classifier and ISA-JSON generator resolve templates from the
                profile; otherwise the built-in default location is used.
        """
        self.investigation_id = investigation_id
        self.inv_inm_path = inv_inm_path
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.scanner: Optional[FolderScanner] = None  # Will be initialized with data_root
        template_root = templates_root or "templates/assay_templates"
        self.classifier = ExperimentClassifier(template_root)
        self.metadata_extractor = MetadataExtractor()
        self.format_converter = FormatConverter()
        self.isa_generator = ISAJsonGenerator(template_root)
        self.file_organizer = FileOrganizer(investigation_id)
        self.isa_validator = ISAJsonValidator()
        self.file_validator = DataFileValidator()
        self.metadata_validator = MetadataValidator()

    def process_batch(
        self,
        data_root: str,
        output_dir: str,
        skip_conversion: bool = False,
        skip_validation: bool = False,
    ) -> BatchProcessingResult:
        """
        Process a batch of experiment folders.

        Args:
            data_root: Root directory containing experiment folders
            output_dir: Output directory for processed data
            skip_conversion: Skip file format conversion
            skip_validation: Skip validation step

        Returns:
            BatchProcessingResult object
        """
        start_time = datetime.now()

        result = BatchProcessingResult(
            total_experiments=0,
            successful_experiments=0,
            failed_experiments=0,
            total_files=0,
            converted_files=0,
            failed_conversions=0,
            validation_passed=True,
            processing_time_seconds=0,
        )

        try:
            # Step 1: Scan experiment folders
            self.logger.info("=" * 60)
            self.logger.info("Step 1: Scanning experiment folders")
            self.logger.info("=" * 60)

            scanner = FolderScanner(data_root)
            self.scanner = scanner
            experiments = scanner.scan_experiments()
            result.total_experiments = len(experiments)
            result.info.append(f"Found {len(experiments)} experiment folders")

            if not experiments:
                result.errors.append("No experiment folders found")
                return result

            # Step 2: Classify experiments
            self.logger.info("\n" + "=" * 60)
            self.logger.info("Step 2: Classifying experiments")
            self.logger.info("=" * 60)

            classification_results = self._classify_experiments(experiments)
            result.info.extend(classification_results["info"])

            # Step 3: Extract metadata
            self.logger.info("\n" + "=" * 60)
            self.logger.info("Step 3: Extracting metadata")
            self.logger.info("=" * 60)

            metadata_results = self._extract_metadata(experiments)
            result.total_files = metadata_results["total_files"]
            result.info.extend(metadata_results["info"])

            # Step 4: Convert file formats
            conversion_results = []
            if not skip_conversion:
                self.logger.info("\n" + "=" * 60)
                self.logger.info("Step 4: Converting file formats")
                self.logger.info("=" * 60)

                conversion_results = self._convert_files(data_root, output_dir)
                result.converted_files = len([r for r in conversion_results if r.success])
                result.failed_conversions = len([r for r in conversion_results if not r.success])
                result.info.append(f"  Total files: {len(conversion_results)}")
                result.info.append(f"  Successful: {result.converted_files}")
                result.info.append(f"  Failed: {result.failed_conversions}")
            else:
                self.logger.info("\nSkipping file conversion")

            # Step 5: Generate ISA-JSON (one study per experiment)
            self.logger.info("\n" + "=" * 60)
            self.logger.info("Step 5: Generating ISA-JSON (per-experiment studies)")
            self.logger.info("=" * 60)

            investigation = self.isa_generator.generate_investigation(
                experiments=experiments,
                investigation_id=self.investigation_id,
                investigation_title=f"{self.investigation_id} Investigation",
                investigation_description=f"Investigation for {self.investigation_id}",
            )

            # Use lightweight investigation dict (study references only)
            investigation_dict = self.isa_generator._investigation_to_dict_lightweight(
                investigation
            )
            result.info.append(
                f"Generated investigation with {len(investigation.studies)} studies (one per experiment)"  # noqa: E501
            )

            # Step 6: Organize files
            self.logger.info("\n" + "=" * 60)
            self.logger.info("Step 6: Organizing files")
            self.logger.info("=" * 60)

            # Add material references if inv_inm path provided
            if self.inv_inm_path:
                investigation_dict = self.file_organizer.create_material_references(
                    investigation_dict, self.inv_inm_path
                )
                result.info.append("Added material references from inv_inm")

            # Build full study dicts for file organization and saving
            full_studies = [self.isa_generator._study_to_dict(s) for s in investigation.studies]
            full_investigation_dict = dict(investigation_dict)
            full_investigation_dict["studies"] = full_studies

            # Organize files: saves lightweight investigation JSON, per-study JSONs,
            # and copies original/converted files into study subfolders
            inv_path = self.file_organizer.organize_investigation(
                conversion_results, output_dir, full_investigation_dict, data_root=data_root
            )

            # Organize metadata files
            if conversion_results:
                self.file_organizer.organize_metadata_files(conversion_results, output_dir)

            # Create directory manifest
            manifest = self.file_organizer.create_directory_manifest(inv_path)
            result.info.append(f"Organized files to {inv_path}")
            result.info.append(f"Total files: {manifest['file_count']}")
            result.info.append(f"Total size: {manifest['total_size_bytes'] / (1024*1024):.2f} MB")

            # Step 7: Validate results
            if not skip_validation:
                self.logger.info("\n" + "=" * 60)
                self.logger.info("Step 7: Validating results")
                self.logger.info("=" * 60)

                validation_results = self._validate_results(inv_path)
                result.validation_passed = validation_results["passed"]
                result.errors.extend(validation_results["errors"])
                result.warnings.extend(validation_results["warnings"])
                result.info.extend(validation_results["info"])
            else:
                self.logger.info("\nSkipping validation")

            # Calculate success rate
            result.successful_experiments = result.total_experiments - result.failed_experiments

            # Save processing report
            self._save_processing_report(result, output_dir)

        except Exception as e:
            result.errors.append(f"Batch processing failed: {e}")
            self.logger.error(f"Batch processing error: {e}", exc_info=True)

        # Calculate processing time
        end_time = datetime.now()
        result.processing_time_seconds = (end_time - start_time).total_seconds()

        # Log summary
        self._log_summary(result)

        return result

    def _classify_experiments(self, experiments: List[FolderMetadata]) -> Dict[str, Any]:
        """
        Classify all experiments.

        Args:
            experiments: List of experiment metadata

        Returns:
            Dictionary with classification results
        """
        results: Dict[str, Any] = {"info": [], "classifications": {}}

        for exp in experiments:
            try:
                exp_type = self.classifier.classify_experiment(exp)
                results["classifications"][exp.experiment_id] = {
                    "type": exp_type.type_name,
                    "template": exp_type.assay_template,
                    "confidence": exp_type.confidence,
                }
                results["info"].append(
                    f"  {exp.experiment_id}: {exp_type.type_name} "
                    f"({exp_type.confidence:.2f} confidence)"
                )
            except Exception as e:
                results["info"].append(f"  {exp.experiment_id}: Classification failed - {e}")

        return results

    def _extract_metadata(self, experiments: List[FolderMetadata]) -> Dict[str, Any]:
        """
        Extract metadata from all experiments.

        Args:
            experiments: List of experiment metadata

        Returns:
            Dictionary with metadata extraction results
        """
        results: Dict[str, Any] = {"info": [], "total_files": 0}

        for exp in experiments:
            try:
                metadata = self.metadata_extractor.extract_all_metadata(exp.folder_path)
                file_count = len(metadata.files)
                results["total_files"] += file_count
                results["info"].append(
                    f"  {exp.experiment_id}: Extracted metadata for {file_count} files"
                )
            except Exception as e:
                results["info"].append(f"  {exp.experiment_id}: Metadata extraction failed - {e}")

        return results

    def _convert_files(self, data_root: str, output_dir: str) -> List[ConversionResult]:
        """
        Convert all files in the data root.

        Args:
            data_root: Root directory containing files
            output_dir: Output directory for converted files

        Returns:
            List of conversion results
        """
        conversion_dir = f"{output_dir}/converted"
        conversion_results = self.format_converter.batch_convert_folder(data_root, conversion_dir)

        _results = {  # noqa: F841
            "info": [
                f"  Total files: {len(conversion_results)}",
                f"  Successful: {len([r for r in conversion_results if r.success])}",
                f"  Failed: {len([r for r in conversion_results if not r.success])}",
            ]
        }

        return conversion_results

    def _validate_results(self, investigation_path: str) -> Dict[str, Any]:
        """
        Validate the processed investigation.

        Args:
            investigation_path: Path to investigation JSON file

        Returns:
            Dictionary with validation results
        """
        results: Dict[str, Any] = {"passed": True, "errors": [], "warnings": [], "info": []}

        # Validate ISA-JSON structure
        self.logger.info("  Validating ISA-JSON structure...")
        isa_result = self.isa_validator.validate_investigation(investigation_path)

        if not isa_result.is_valid:
            results["passed"] = False
            results["errors"].extend(isa_result.errors)

        results["warnings"].extend(isa_result.warnings)
        results["info"].extend(isa_result.info)

        # Validate data files
        self.logger.info("  Validating data files...")
        file_result, file_results = self.file_validator.validate_files(investigation_path)

        if not file_result.is_valid:
            results["passed"] = False
            results["errors"].extend(file_result.errors)

        results["warnings"].extend(file_result.warnings)
        results["info"].extend(file_result.info)

        # Validate metadata
        self.logger.info("  Validating metadata...")
        metadata_result = self.metadata_validator.validate_metadata(investigation_path)

        if not metadata_result.is_valid:
            results["passed"] = False
            results["errors"].extend(metadata_result.errors)

        results["warnings"].extend(metadata_result.warnings)
        results["info"].extend(metadata_result.info)

        return results

    def _save_processing_report(self, result: BatchProcessingResult, output_dir: str):
        """
        Save a processing report.

        Args:
            result: Batch processing result
            output_dir: Output directory
        """
        report = {
            "processing_date": datetime.now().isoformat(),
            "investigation_id": self.investigation_id,
            "summary": {
                "total_experiments": result.total_experiments,
                "successful_experiments": result.successful_experiments,
                "failed_experiments": result.failed_experiments,
                "total_files": result.total_files,
                "converted_files": result.converted_files,
                "failed_conversions": result.failed_conversions,
                "validation_passed": result.validation_passed,
                "processing_time_seconds": result.processing_time_seconds,
            },
            "errors": result.errors,
            "warnings": result.warnings,
            "info": result.info,
        }

        report_path = Path(output_dir) / "processing_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        self.logger.info(f"Saved processing report to {report_path}")

    def _log_summary(self, result: BatchProcessingResult):
        """
        Log a summary of the batch processing.

        Args:
            result: Batch processing result
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("BATCH PROCESSING SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Total experiments: {result.total_experiments}")
        self.logger.info(f"Successful: {result.successful_experiments}")
        self.logger.info(f"Failed: {result.failed_experiments}")
        self.logger.info(f"Total files: {result.total_files}")
        self.logger.info(f"Converted files: {result.converted_files}")
        self.logger.info(f"Failed conversions: {result.failed_conversions}")
        self.logger.info(f"Validation: {'PASSED' if result.validation_passed else 'FAILED'}")
        self.logger.info(f"Processing time: {result.processing_time_seconds:.2f} seconds")

        if result.errors:
            self.logger.warning(f"\nErrors ({len(result.errors)}):")
            for error in result.errors:
                self.logger.warning(f"  - {error}")

        if result.warnings:
            self.logger.info(f"\nWarnings ({len(result.warnings)}):")
            for warning in result.warnings[:10]:  # Show first 10 warnings
                self.logger.info(f"  - {warning}")
            if len(result.warnings) > 10:
                self.logger.info(f"  ... and {len(result.warnings) - 10} more warnings")

        self.logger.info("=" * 60)


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser for the batch processor.

    Returns:
        A configured ``ArgumentParser`` instance.
    """
    parser = argparse.ArgumentParser(
        prog="isa-json-steward-batch",
        description=(
            "ISA-JSON Data Steward — run the 7-stage batch pipeline "
            "(scan → classify → extract → convert → generate → organize → validate)."
        ),
    )
    parser.add_argument(
        "--data-root",
        required=True,
        help="Root directory containing experiment folders",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for the processed investigation",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help=(
            "Path to a domain profile directory (config/ + templates/ + ontologies/). "
            "Defaults to the built-in profile."
        ),
    )
    parser.add_argument(
        "--investigation-id",
        default=None,
        help="Investigation identifier (default: from the profile's investigation defaults)",
    )
    parser.add_argument(
        "--inv-inm-path",
        default=None,
        help="Optional path to an existing investigation for material references",
    )
    parser.add_argument(
        "--skip-conversion",
        action="store_true",
        help="Skip the file format conversion stage",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip the validation stage",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Run the batch processor CLI.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code: 0 on success, 1 otherwise.
    """
    import sys

    from utils.config_loader import ProfileConfigError, get_profile, set_profile

    args = build_arg_parser().parse_args(argv)

    # Activate the profile (defaults to the built-in profile when omitted).
    profile = set_profile(args.profile) if args.profile else get_profile()
    # Force resolution of profile.json (namespace, min_core_version check)
    # and log which files were served from core defaults, if any.
    try:
        profile.profile
        profile.log_profile_load_summary()
        defaults = profile.get_investigation_defaults()
    except ProfileConfigError as exc:
        print(f"Profile error: {exc}", file=sys.stderr)
        return 1
    inv_id = args.investigation_id or defaults.get("investigation_id", "inv_default")
    templates_root = str(profile.get_templates_root() / "assay_templates")

    processor_name = defaults.get("processor_name", "ISA-JSON Data Steward")

    print("=" * 60)
    print(processor_name)
    print("=" * 60)
    print(f"Data root:          {args.data_root}")
    print(f"Output directory:   {args.output_dir}")
    print(f"Profile:            {profile.get_config_dir()}")
    print(f"Templates:          {templates_root}")
    print(f"Skip conversion:    {args.skip_conversion}")
    print(f"Skip validation:    {args.skip_validation}")
    if args.inv_inm_path:
        print(f"inv_inm path:       {args.inv_inm_path}")
    print("=" * 60)
    print()

    processor = BatchProcessor(
        investigation_id=inv_id,
        inv_inm_path=args.inv_inm_path,
        templates_root=templates_root,
    )

    result = processor.process_batch(
        data_root=args.data_root,
        output_dir=args.output_dir,
        skip_conversion=args.skip_conversion,
        skip_validation=args.skip_validation,
    )

    if result.validation_passed and result.failed_experiments == 0 and not result.errors:
        print("\n✓ Batch processing completed successfully!")
        return 0
    print("\n✗ Batch processing completed with errors!")
    return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
