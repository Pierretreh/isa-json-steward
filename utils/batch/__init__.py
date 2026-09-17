"""
Batch processing pipeline for partner data ingestion.

This package contains library modules for the batch data processing pipeline:
- folder_scanner: Discover experiment folders in partner data
- experiment_classifier: Classify experiments by type
- metadata_extractor: Extract metadata from file formats
- format_converter: Convert proprietary formats to standard formats
- isa_json_generator: Generate ISA-JSON from experiment metadata
- file_organizer: Organize files into ISA-JSON structure
- batch_processor: Orchestrate the full pipeline
- validator: Validate ISA-JSON files and data
"""
