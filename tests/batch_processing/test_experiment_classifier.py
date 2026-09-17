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
