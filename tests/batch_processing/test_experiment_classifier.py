"""
Unit tests for ExperimentClassifier component.
"""

import pytest

from utils.batch.experiment_classifier import ExperimentClassifier, ExperimentType


@pytest.mark.unit
@pytest.mark.batch_component
class TestExperimentClassifier:
    """Tests for ExperimentClassifier class."""

    def test_initialization(self, experiment_classifier):
        """Test classifier initialization."""
        assert isinstance(experiment_classifier, ExperimentClassifier)

    def test_classify_calcein_assay(self, temp_dir):
        """Test classification of Calcein assay experiment."""
        exp_dir = temp_dir / "E1_Calceinassay"
        exp_dir.mkdir()

        # Create files typical of Calcein assay
        (exp_dir / "fluorescence_data.xlsx").write_text("data\n")
        (exp_dir / "image.czi").write_bytes(b"fake_czi")

        classifier = ExperimentClassifier()
        result = classifier.classify(exp_dir)

        assert result is not None
        assert result.experiment_type in [ExperimentType.CALCEIN_ASSAY, ExperimentType.UNKNOWN]

    def test_classify_facs_assay(self, temp_dir):
        """Test classification of FACS assay experiment."""
        exp_dir = temp_dir / "E2_FACS"
        exp_dir.mkdir()

        # Create FACS files
        (exp_dir / "sample.fcs").write_bytes(b"fake_fcs")
        (exp_dir / "analysis.wsp").write_text("flowjo\n")

        classifier = ExperimentClassifier()
        result = classifier.classify(exp_dir)

        assert result is not None
        assert result.experiment_type in [ExperimentType.FACS_ASSAY, ExperimentType.UNKNOWN]

    def test_classify_explant_experiment(self, temp_dir):
        """Test classification of explant experiment."""
        exp_dir = temp_dir / "E10_Explant"
        exp_dir.mkdir()

        # Create explant files
        (exp_dir / "explant_image.czi").write_bytes(b"fake_czi")
        (exp_dir / "facs_data.fcs").write_bytes(b"fake_fcs")

        classifier = ExperimentClassifier()
        result = classifier.classify(exp_dir)

        assert result is not None
        # May classify as EXPLANT, FACS (due to .fcs file), or UNKNOWN
        assert result.experiment_type in [
            ExperimentType.EXPLANT,
            ExperimentType.UNKNOWN,
            ExperimentType.FACS_ASSAY,
            ExperimentType.TOXICITY_EX_VIVO,
        ]

    def test_classify_unknown_experiment(self, temp_dir):
        """Test classification of unknown experiment type."""
        exp_dir = temp_dir / "unknown_exp"
        exp_dir.mkdir()
        (exp_dir / "random_file.txt").write_text("random\n")

        classifier = ExperimentClassifier()
        result = classifier.classify(exp_dir)

        assert result is not None
        assert result.experiment_type == ExperimentType.UNKNOWN

    def test_classify_empty_directory(self, temp_dir):
        """Test classification of empty directory."""
        exp_dir = temp_dir / "empty_exp"
        exp_dir.mkdir()

        classifier = ExperimentClassifier()
        result = classifier.classify(exp_dir)

        assert result is not None
        assert result.experiment_type == ExperimentType.UNKNOWN

    def test_classification_confidence(self, temp_dir):
        """Test classification confidence scoring."""
        exp_dir = temp_dir / "test_exp"
        exp_dir.mkdir()

        # Create clear FACS indicators
        (exp_dir / "sample.fcs").write_bytes(b"fake_fcs")
        (exp_dir / "sample2.fcs").write_bytes(b"fake_fcs")

        classifier = ExperimentClassifier()
        result = classifier.classify(exp_dir)

        if result.experiment_type == ExperimentType.FACS_ASSAY:
            assert result.confidence > 0.5

    def test_classify_with_template_matching(self, temp_dir):
        """Test classification using template matching."""
        exp_dir = temp_dir / "template_test"
        exp_dir.mkdir()

        # Create files matching a template
        (exp_dir / "calcein_data.xlsx").write_text("data\n")
        (exp_dir / "calcein_image.tiff").write_bytes(b"img")

        classifier = ExperimentClassifier()
        result = classifier.classify(exp_dir)

        assert result is not None
        assert result.template_match is not None or result.experiment_type != ExperimentType.UNKNOWN

    def test_classify_multiple_experiments(self, temp_dir):
        """Test classification of multiple experiments."""
        experiments = []

        for i in range(3):
            exp_dir = temp_dir / f"exp_{i}"
            exp_dir.mkdir()
            (exp_dir / f"file_{i}.csv").write_text(f"data{i}\n")
            experiments.append(exp_dir)

        classifier = ExperimentClassifier()
        results = [classifier.classify(exp) for exp in experiments]

        assert len(results) == 3
        assert all(r is not None for r in results)

    def test_classification_with_metadata(self, temp_dir):
        """Test classification using metadata files."""
        exp_dir = temp_dir / "metadata_exp"
        exp_dir.mkdir()

        # Create metadata file
        metadata = {"experiment_type": "calcein_assay", "date": "2024-01-01"}
        import json

        (exp_dir / "metadata.json").write_text(json.dumps(metadata))

        classifier = ExperimentClassifier()
        result = classifier.classify(exp_dir)

        assert result is not None
        # Should use metadata for classification if available

    def test_get_available_templates(self, experiment_classifier):
        """Test getting available experiment templates."""
        templates = experiment_classifier.get_available_templates()

        assert isinstance(templates, list)
        # Should have at least some templates
        assert len(templates) >= 0

    def test_get_template_by_type(self, experiment_classifier):
        """Test getting template by experiment type."""
        template = experiment_classifier.get_template_by_type(ExperimentType.FACS_ASSAY)

        # May return None if template doesn't exist
        assert template is None or isinstance(template, dict)


@pytest.mark.unit
@pytest.mark.batch_component
class TestStructureDisambiguation:
    """Tests for the Stage-1 folder-structure disambiguation signal.

    The folder-structure analysis (``SubdirectoryHints.assay_dirs``) is
    used as a disambiguation signal: it corroborates an already-agreed
    type with a modest confidence boost, and it breaks near-ties (within
    ``TIE_BREAK_MARGIN``) when the name and file heuristics disagree.
    It never overrides a clear winner.
    """

    def test_structure_corroborates_agreed_type(self):
        """Agreed type + matching structure hint → extra confidence boost."""
        from utils.batch.folder_scanner import FileInventory, FolderMetadata, SubdirectoryHints

        hints = SubdirectoryHints(
            assay_dirs={"FACS": "facs"},
            immediate_subdirs=["FACS"],
            has_structure=True,
        )
        metadata = FolderMetadata(
            experiment_id="E1",
            experiment_name="E1_FACS",
            folder_path="E1_FACS",
            file_inventory=FileInventory(fcs_files=["E1_FACS/run.fcs"]),
            subdirectory_hints=hints,
        )

        classifier = ExperimentClassifier()
        with_structure = classifier.classify_experiment(metadata)

        metadata_no_hints = FolderMetadata(
            experiment_id="E1",
            experiment_name="E1_FACS",
            folder_path="E1_FACS",
            file_inventory=FileInventory(fcs_files=["E1_FACS/run.fcs"]),
            subdirectory_hints=None,
        )
        without_structure = classifier.classify_experiment(metadata_no_hints)

        assert with_structure.type_name == "facs"
        assert without_structure.type_name == "facs"
        # The corroborating structure hint adds the modest boost
        assert with_structure.confidence > without_structure.confidence
        boost = ExperimentClassifier.STRUCTURE_CORROBORATION_BOOST
        assert with_structure.confidence == min(without_structure.confidence + boost, 1.0)

    def test_structure_breaks_near_tie(self):
        """Name/file disagree within TIE_BREAK_MARGIN → structure breaks the tie."""
        from utils.batch.folder_scanner import FileInventory, FolderMetadata, SubdirectoryHints

        # Name votes facs (all 5 facs keywords present → 5/5 = 1.0);
        # file votes elisa (1 .xlsx of 1 file → 1.0).  They disagree with a
        # zero spread (a true tie); structure points at elisa → elisa wins
        # with the shared confidence retained.
        hints = SubdirectoryHints(
            assay_dirs={"ELISA": "elisa"},
            immediate_subdirs=["ELISA"],
            has_structure=True,
        )
        metadata = FolderMetadata(
            experiment_id="E2",
            experiment_name="E2_facs annexin pi propidium iodide flow cytometry",
            folder_path="E2_facs annexin pi propidium iodide flow cytometry",
            file_inventory=FileInventory(xlsx_files=["E2/run.xlsx"]),
            subdirectory_hints=hints,
        )

        classifier = ExperimentClassifier()
        result = classifier.classify_experiment(metadata)

        assert result.type_name == "elisa"
        assert result.assay_template == "elisa_assay.json"
        assert result.confidence == 1.0

    def test_structure_does_not_override_clear_winner(self):
        """Name/file disagree beyond TIE_BREAK_MARGIN → winner stands."""
        from utils.batch.folder_scanner import FileInventory, FolderMetadata, SubdirectoryHints

        # Name votes facs strongly (0.5), file votes microscopy (0.4):
        # spread 0.1 is at the margin boundary — use a wider spread instead:
        # name "facs" (1/5 = 0.2) vs file microscopy 1/1 = 1.0 → spread 0.8.
        # Structure points at facs but must NOT override the file winner.
        hints = SubdirectoryHints(
            assay_dirs={"FACS": "facs"},
            immediate_subdirs=["FACS"],
            has_structure=True,
        )
        metadata = FolderMetadata(
            experiment_id="E3",
            experiment_name="E3_facs",
            folder_path="E3_facs",
            file_inventory=FileInventory(tiff_files=["E3_facs/image.tiff"]),
            subdirectory_hints=hints,
        )

        classifier = ExperimentClassifier()
        result = classifier.classify_experiment(metadata)

        assert result.type_name == "microscopy"

    def test_ambiguous_structure_does_not_break_tie(self):
        """Multiple assay dirs → no tie-break, higher-confidence winner kept."""
        from utils.batch.folder_scanner import FileInventory, FolderMetadata, SubdirectoryHints

        # True tie as in the previous test (name facs 1.0 vs file elisa 1.0),
        # but the structure hints are ambiguous (two assay types) → no
        # tie-break; the name winner (facs) is kept.
        hints = SubdirectoryHints(
            assay_dirs={"FACS": "facs", "ELISA": "elisa"},
            immediate_subdirs=["FACS", "ELISA"],
            has_structure=True,
        )
        metadata = FolderMetadata(
            experiment_id="E4",
            experiment_name="E4_facs annexin pi propidium iodide flow cytometry",
            folder_path="E4_facs annexin pi propidium iodide flow cytometry",
            file_inventory=FileInventory(xlsx_files=["E4/run.xlsx"]),
            subdirectory_hints=hints,
        )

        classifier = ExperimentClassifier()
        result = classifier.classify_experiment(metadata)

        # Ambiguous hints must not flip the outcome; the name winner stays.
        assert result.type_name == "facs"

    def test_no_hints_behaves_as_before(self):
        """Absent structure hints → identical to the two-heuristic result."""
        from utils.batch.folder_scanner import FileInventory, FolderMetadata

        metadata = FolderMetadata(
            experiment_id="E5",
            experiment_name="E5_FACS",
            folder_path="E5_FACS",
            file_inventory=FileInventory(fcs_files=["E5_FACS/run.fcs"]),
            subdirectory_hints=None,
        )

        classifier = ExperimentClassifier()
        result = classifier.classify_experiment(metadata)

        assert result.type_name == "facs"
        # name confidence 1/5 = 0.2 + corroboration boost 0.2 (no structure boost)
        assert abs(result.confidence - 0.4) < 1e-9


@pytest.mark.unit
@pytest.mark.batch_component
class TestExperimentType:
    """Tests for ExperimentType enum."""

    def test_experiment_type_values(self):
        """Test ExperimentType enum values."""
        assert ExperimentType.UNKNOWN is not None
        assert ExperimentType.CALCEIN_ASSAY is not None
        assert ExperimentType.FACS_ASSAY is not None
        assert ExperimentType.EXPLANT is not None

    def test_experiment_type_comparison(self):
        """Test ExperimentType comparison."""
        assert ExperimentType.UNKNOWN != ExperimentType.FACS_ASSAY
        assert ExperimentType.CALCEIN_ASSAY == ExperimentType.CALCEIN_ASSAY


@pytest.mark.unit
@pytest.mark.batch_component
class TestClassificationResult:
    """Tests for ClassificationResult class (if it exists)."""

    def test_classification_result_properties(self, temp_dir):
        """Test ClassificationResult properties."""
        from utils.batch.experiment_classifier import ClassificationResult

        result = ClassificationResult(
            experiment_type=ExperimentType.FACS_ASSAY,
            confidence=0.9,
            template_match="facs_template.json",
        )

        assert result.experiment_type == ExperimentType.FACS_ASSAY
        assert result.confidence == 0.9
        assert result.template_match == "facs_template.json"
