"""
Tests for the GUI batch pipeline worker and dialog (plan §5, T3–T6).

These tests verify:
* ``BatchConfig`` defaults and ``BatchWorker`` construction (headless-safe, T3)
* a worker end-to-end run on a temp data root (T4)
* GUI↔CLI parity: same inputs via ``BatchProcessor`` directly vs. the
  ``BatchWorker`` yield identical summary fields (T5, the executable proof of
  the paper's "shared core modules and profile" claim)
* the dialog smoke test: Start with an empty ``data_root`` shows a validation
  error and does not start a thread (T6)

Qt-dependent tests skip cleanly when PyQt6 is unavailable.
"""

import time
from pathlib import Path

import pytest

try:
    from PyQt6.QtWidgets import QApplication  # noqa: F401

    PYQT6_AVAILABLE = True
except (ImportError, OSError):
    PYQT6_AVAILABLE = False


def _make_experiment_root(temp_dir: Path) -> Path:
    """Create a minimal ``E1_test_experiment/data.csv`` data root."""
    exp_dir = temp_dir / "E1_test_experiment"
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "data.csv").write_text("col1,col2\nval1,val2\n", encoding="utf-8")
    return temp_dir


def _run_worker(worker, timeout_seconds: float = 60.0):
    """Spin the Qt event loop until the worker finishes (or timeout).

    Returns a tuple ``(outcome, result, report_path, failure)`` where
    ``outcome`` is ``"succeeded"``, ``"failed"`` or ``"timeout"``.
    """
    from PyQt6.QtCore import QEventLoop, QTimer

    state = {"outcome": "timeout", "result": None, "report_path": None, "failure": None}

    def _on_succeeded(result, report_path):
        state.update(outcome="succeeded", result=result, report_path=report_path)
        loop.quit()

    def _on_failed(message):
        state.update(outcome="failed", failure=message)
        loop.quit()

    def _on_finished():
        loop.quit()

    loop = QEventLoop()
    worker.succeeded.connect(_on_succeeded)
    worker.failed.connect(_on_failed)
    worker.finished.connect(_on_finished)
    QTimer.singleShot(int(timeout_seconds * 1000), loop.quit)
    worker.start()
    loop.exec()
    if state["outcome"] == "timeout":
        worker.wait(int(timeout_seconds * 1000))
    return state["outcome"], state["result"], state["report_path"], state["failure"]


@pytest.mark.gui
@pytest.mark.gui_widget
class TestBatchConfig:
    """BatchConfig dataclass defaults (T3, headless-safe)."""

    def test_batch_config_defaults(self):
        from gui.batch_runner import BatchConfig

        cfg = BatchConfig()
        assert cfg.data_root == ""
        assert cfg.output_dir == ""
        assert cfg.investigation_id == "inv_default"
        assert cfg.templates_root == ""
        assert cfg.inv_inm_path == ""
        assert cfg.skip_conversion is True
        assert cfg.skip_validation is True

    def test_batch_config_is_plain_fields(self):
        """The config snapshot uses only str/bool fields (thread-safe)."""
        from dataclasses import fields

        from gui.batch_runner import BatchConfig

        for f in fields(BatchConfig):
            assert f.type in (str, bool, "str", "bool"), f"{f.name} is not a plain str/bool"


@pytest.mark.gui
@pytest.mark.gui_widget
class TestBatchWorker:
    """BatchWorker construction and end-to-end execution (T3/T4/T5)."""

    @pytest.fixture(autouse=True)
    def _check_pyqt6(self, qapp):
        if not PYQT6_AVAILABLE:
            pytest.skip("PyQt6 not installed")

    def test_worker_constructible(self):
        from gui.batch_runner import BatchConfig, BatchWorker

        cfg = BatchConfig(
            data_root=".",
            output_dir=".",
            skip_conversion=True,
            skip_validation=True,
        )
        worker = BatchWorker(cfg)
        assert worker is not None
        assert not worker.isRunning()
        assert hasattr(worker, "request_cancel")

    def test_request_cancel_sets_event(self):
        from gui.batch_runner import BatchConfig, BatchWorker

        worker = BatchWorker(BatchConfig())
        assert not worker._cancel_event.is_set()
        worker.request_cancel()
        assert worker._cancel_event.is_set()

    def test_worker_end_to_end(self, qapp, temp_dir):
        """T4: worker runs the full pipeline on a temp data root."""
        from gui.batch_runner import BatchConfig, BatchWorker

        data_root = _make_experiment_root(temp_dir)
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        cfg = BatchConfig(
            data_root=str(data_root),
            output_dir=str(output_dir),
            investigation_id="test_inv",
            skip_conversion=True,
            skip_validation=True,
        )
        worker = BatchWorker(cfg)

        outcome, result, report_path, failure = _run_worker(worker)
        assert outcome == "succeeded", f"worker failed: {failure}"
        assert result is not None
        assert result.total_experiments == 1
        assert (output_dir / "processing_report.json").exists()
        assert report_path is not None and report_path.endswith("processing_report.json")

    def test_gui_cli_parity(self, qapp, temp_dir):
        """T5: identical summary fields via BatchProcessor directly vs BatchWorker.

        This is the executable proof of the paper's claim that the GUI and the
        CLI "share the same core modules and profile".
        """
        from gui.batch_runner import BatchConfig, BatchWorker
        from utils.batch.batch_processor import BatchProcessor

        data_root = _make_experiment_root(temp_dir)
        out_direct = temp_dir / "out_direct"
        out_worker = temp_dir / "out_worker"
        out_direct.mkdir()
        out_worker.mkdir()

        # Direct (CLI-equivalent) run
        processor = BatchProcessor(investigation_id="test_inv")
        direct = processor.process_batch(
            data_root=str(data_root),
            output_dir=str(out_direct),
            skip_conversion=True,
            skip_validation=True,
        )

        # GUI worker run with the same inputs
        cfg = BatchConfig(
            data_root=str(data_root),
            output_dir=str(out_worker),
            investigation_id="test_inv",
            skip_conversion=True,
            skip_validation=True,
        )
        worker = BatchWorker(cfg)
        outcome, result, _report, failure = _run_worker(worker)
        assert outcome == "succeeded", f"worker failed: {failure}"

        # Compare the summary fields (deterministic across both paths)
        summary_fields = (
            "total_experiments",
            "successful_experiments",
            "failed_experiments",
            "total_files",
            "converted_files",
            "failed_conversions",
            "validation_passed",
        )
        for field_name in summary_fields:
            assert getattr(result, field_name) == getattr(direct, field_name), (
                f"parity mismatch on {field_name}: "
                f"worker={getattr(result, field_name)} direct={getattr(direct, field_name)}"
            )
        # Both produced a report with the same summary block
        import json

        direct_report = json.loads((out_direct / "processing_report.json").read_text())
        worker_report = json.loads((out_worker / "processing_report.json").read_text())
        assert direct_report["summary"] == worker_report["summary"]
        assert direct_report["summary"]["total_experiments"] == 1


@pytest.mark.gui
@pytest.mark.gui_dialog
class TestBatchProcessingDialog:
    """BatchProcessingDialog smoke tests (T6)."""

    @pytest.fixture(autouse=True)
    def _check_pyqt6(self, qapp):
        if not PYQT6_AVAILABLE:
            pytest.skip("PyQt6 not installed")

    def test_dialog_constructs(self):
        from gui.dialogs.batch_processing import BatchProcessingDialog

        dialog = BatchProcessingDialog()
        try:
            assert dialog.data_root_edit is not None
            assert dialog.output_dir_edit is not None
            assert dialog.progress_bar is not None
            assert dialog.start_btn is not None
        finally:
            dialog.close()

    def test_start_with_empty_data_root_shows_error(self):
        """Start with an empty data_root shows a validation error, no thread."""
        from gui.dialogs.batch_processing import BatchProcessingDialog

        dialog = BatchProcessingDialog()
        try:
            dialog.data_root_edit.setText("")
            dialog.output_dir_edit.setText("some/output")
            dialog._on_start()
            assert dialog.error_label.text().strip() != ""
            assert "Data root" in dialog.error_label.text()
            assert dialog.worker is None
        finally:
            dialog.close()

    def test_start_with_valid_paths_starts_worker(self, qapp, temp_dir):
        """Start with valid paths constructs and starts the worker."""
        from PyQt6.QtCore import QCoreApplication

        from gui.dialogs.batch_processing import BatchProcessingDialog

        data_root = _make_experiment_root(temp_dir)
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        dialog = BatchProcessingDialog()
        try:
            dialog.data_root_edit.setText(str(data_root))
            dialog.output_dir_edit.setText(str(output_dir))
            dialog.skip_conversion_check.setChecked(True)
            dialog.skip_validation_check.setChecked(True)

            # Allow the worker to finish so we can assert it started.
            dialog._on_start()
            assert dialog.worker is not None
            # Pump the event loop until the (queued) succeeded/failed slot has
            # been delivered and the dialog re-enabled its inputs.
            deadline = time.time() + 60.0
            while not dialog.start_btn.isEnabled() and time.time() < deadline:
                QCoreApplication.processEvents()
                time.sleep(0.02)
            assert dialog.start_btn.isEnabled()
        finally:
            dialog.close()

    def test_results_parsing_from_classifications(self):
        """The D5 classifications path drives the results table."""
        from gui.dialogs.batch_processing import BatchProcessingDialog
        from utils.batch.batch_processor import BatchProcessingResult

        result = BatchProcessingResult(
            total_experiments=1,
            successful_experiments=1,
            failed_experiments=0,
            total_files=1,
            converted_files=0,
            failed_conversions=0,
            validation_passed=True,
            processing_time_seconds=0.5,
            classifications={
                "E1": {
                    "type": "microscopy",
                    "template": "microscopy_assay.json",
                    "confidence": 0.85,
                }
            },
        )
        rows = BatchProcessingDialog._parse_experiment_rows(result)
        assert rows == [("E1", "microscopy", "0.85")]

    def test_results_parsing_fallback_from_info_lines(self):
        """The D4 regex fallback parses human-readable info lines."""
        from gui.dialogs.batch_processing import BatchProcessingDialog
        from utils.batch.batch_processor import BatchProcessingResult

        result = BatchProcessingResult(
            total_experiments=1,
            successful_experiments=1,
            failed_experiments=0,
            total_files=1,
            converted_files=0,
            failed_conversions=0,
            validation_passed=True,
            processing_time_seconds=0.5,
            info=["  E1: microscopy (0.85 confidence)"],
        )
        rows = BatchProcessingDialog._parse_experiment_rows(result)
        assert rows == [("E1", "microscopy", "0.85")]

    def test_cancel_event_short_circuits_pipeline(self, temp_dir):
        """D5: a pre-set cancel_event stops the run before Step 2."""
        import threading as _threading

        from gui.batch_runner import BatchConfig, BatchWorker

        data_root = _make_experiment_root(temp_dir)
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        cfg = BatchConfig(
            data_root=str(data_root),
            output_dir=str(output_dir),
            skip_conversion=True,
            skip_validation=True,
        )
        worker = BatchWorker(cfg)
        # Pre-set the cancel event so the pipeline stops before Step 2.
        worker._cancel_event = _threading.Event()
        worker._cancel_event.set()

        outcome, result, _report, _failure = _run_worker(worker)
        assert outcome == "succeeded"
        assert "Pipeline cancelled by user" in result.errors
        assert result.classifications == {}
        # No Step-7 / report output was produced (cancelled before organizing).
        assert not (output_dir / "processing_report.json").exists()
