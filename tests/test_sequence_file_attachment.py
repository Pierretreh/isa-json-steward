"""
Test script for sequence file attachment feature.
"""

import sys
import tempfile
import traceback
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))  # noqa: E402

from utils.directory_manager import DirectoryManager  # noqa: E402
from utils.isa_json_exporter import ISAJsonExporter  # noqa: E402


def create_test_sequence_file():
    """Create a temporary test sequence file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".fasta", delete=False) as f:
        f.write(">test_sequence\nATCGATCGATCGATCG\n")
        return Path(f.name)


def test_sequence_file_copy():
    """Test that sequence file is copied to study folder."""
    print("Testing sequence file copy to study folder...")

    # Create test sequence file
    seq_file = create_test_sequence_file()
    print(f"Created test sequence file: {seq_file}")

    # Create temporary directory manager
    with tempfile.TemporaryDirectory() as temp_dir:
        dm = DirectoryManager(base_path=str(Path(temp_dir)))

        # Create investigation and study
        investigation_id = "test_inv_1"
        study_id = "test_study_1"

        dm.create_investigation_directory(investigation_id)
        dm.create_study_directory(investigation_id, study_id)

        # Test copy_sequence_file_to_study
        result = dm.copy_sequence_file_to_study(seq_file, investigation_id, study_id)

        if result:
            print(f"✓ Sequence file copied to: {result}")

            # Verify file exists
            expected_path = (
                dm.get_study_path(investigation_id, study_id)
                / "raw_data"
                / "sequences"
                / seq_file.name
            )
            if expected_path.exists():
                print(f"✓ File exists at expected location: {expected_path}")

                # Verify content
                with open(expected_path, "r") as f:
                    content = f.read()
                    if "test_sequence" in content:
                        print("✓ File content is correct")
                    else:
                        print("✗ File content mismatch")
            else:
                print(f"✗ File not found at expected location: {expected_path}")
        else:
            print("✗ Failed to copy sequence file")

        # Cleanup
        seq_file.unlink()


def test_study_json_with_sequence():
    """Test that study JSON includes sequence file reference in comments."""
    print("\nTesting study JSON with sequence file reference...")

    # Create test study data with sequence file
    seq_file = create_test_sequence_file()

    study_data = {
        "investigation_id": "test_inv_1",
        "study_id": "test_study_1",
        "study_name": "Test Study",
        "bacterial_strain": "E. coli",
        "protein_plasmid": "pET28a",
        "sequence_data": {
            "sequence_id": "test_sequence",
            "sequence": "ATCGATCGATCGATCG",
            "description": "Test sequence",
            "file_path": str(seq_file),
        },
        "sequence_file_path": str(seq_file),
        "copied_sequence_path": "raw_data/sequences/" + seq_file.name,
        "created_at": "2026-04-09T12:00:00",
        "assays": [],
        "process_sequence": {},
    }

    # Create exporter and generate ISA-JSON
    exporter = ISAJsonExporter(study_data, "test_inv_1", "test_study_1")
    isa_json = exporter.export_complete_isa_json()

    # Check if study has comments
    if "studies" in isa_json and len(isa_json["studies"]) > 0:
        study = isa_json["studies"][0]
        if "comments" in study:
            print(f"✓ Study has {len(study['comments'])} comments:")
            for comment in study["comments"]:
                print(f"  - {comment['name']}: {comment['value']}")

            # Check for sequence file comment
            sequence_file_comment = next(
                (c for c in study["comments"] if c["name"] == "Sequence File"), None
            )
            if sequence_file_comment:
                print(f"✓ Sequence file comment found: {sequence_file_comment['value']}")
            else:
                print("✗ Sequence file comment not found")

            # Check for sequence ID comment
            sequence_id_comment = next(
                (c for c in study["comments"] if c["name"] == "Sequence ID"), None
            )
            if sequence_id_comment:
                print(f"✓ Sequence ID comment found: {sequence_id_comment['value']}")
            else:
                print("✗ Sequence ID comment not found")
        else:
            print("✗ Study has no comments field")
    else:
        print("✗ No studies in ISA-JSON")

    # Cleanup
    seq_file.unlink()


if __name__ == "__main__":
    print("=" * 60)
    print("Sequence File Attachment Test Suite")
    print("=" * 60)

    try:
        test_sequence_file_copy()
        test_study_json_with_sequence()

        print("\n" + "=" * 60)
        print("All tests completed!")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        traceback.print_exc()  # noqa: F811
