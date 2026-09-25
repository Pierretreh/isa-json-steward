"""
Batch pipeline dialog for the ISA-JSON Data Steward GUI.

Provides a modal dialog to configure and launch the shared 7-stage batch
pipeline (see :mod:`gui.batch_runner`), showing live stage progress and
log lines while it runs, and a results view (summary cards, per-experiment
table, errors/warnings, report link) when it completes.

The dialog resolves profile-derived values (investigation id, templates
root) **on the main thread** before starting the worker, and never calls
``get_profile()``/``set_profile()`` from the worker thread (D2).
"""

import re
from pathlib import Path

from PyQt6.QtCore import QUrl, pyqtSlot
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..batch_runner import BatchConfig, BatchWorker
from ..widgets.common import ActionButton, InfoCard, PrimaryButton, SectionHeader

# Matches the per-experiment classification line produced by
# BatchProcessor._classify_experiments() (D4), e.g.
# "  E1: microscopy (0.85 confidence)".
_INFO_EXPERIMENT_PATTERN = re.compile(
    r"^\s*(?P<id>\S+):\s*(?P<type>.+?)\s*\((?P<conf>[\d.]+)\s*confidence\)$"
)


class BatchProcessingDialog(QDialog):
    """Modal dialog to run the 7-stage batch pipeline."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Run Batch Pipeline")
        self.setMinimumWidth(640)
        self.worker: BatchWorker | None = None
        self._result = None
        self._report_path: str | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- Setup section -------------------------------------------
        layout.addWidget(SectionHeader("Pipeline Setup"))

        form = QFormLayout()

        self.data_root_edit = QLineEdit()
        self.data_root_edit.setPlaceholderText(
            "Root directory containing E1_, E2_, ... experiment folders"
        )
        browse_data_btn = QPushButton("Browse...")
        browse_data_btn.setFixedWidth(80)
        browse_data_btn.clicked.connect(self._browse_data_root)
        data_root_row = QHBoxLayout()
        data_root_row.addWidget(self.data_root_edit)
        data_root_row.addWidget(browse_data_btn)
        form.addRow("Data root", data_root_row)

        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("Output directory for the processed investigation")
        browse_out_btn = QPushButton("Browse...")
        browse_out_btn.setFixedWidth(80)
        browse_out_btn.clicked.connect(self._browse_output_dir)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_dir_edit)
        output_row.addWidget(browse_out_btn)
        form.addRow("Output directory", output_row)

        self.investigation_id_edit = QLineEdit()
        self.investigation_id_edit.setPlaceholderText("e.g. inv_default")
        form.addRow("Investigation ID", self.investigation_id_edit)

        self.inv_inm_edit = QLineEdit()
        self.inv_inm_edit.setPlaceholderText("Optional: path to inv_inm for material references")
        form.addRow("inv_inm path", self.inv_inm_edit)

        self.skip_conversion_check = QCheckBox("Skip file format conversion (stage 4)")
        self.skip_conversion_check.setChecked(True)
        form.addRow("Options", self.skip_conversion_check)

        self.skip_validation_check = QCheckBox("Skip validation (stage 7)")
        self.skip_validation_check.setChecked(True)
        form.addRow("Options", self.skip_validation_check)

        layout.addLayout(form)

        # Prefill the investigation id from the active profile (main thread).
        self._prefill_from_profile()

        # --- Progress section ------------------------------------------
        layout.addWidget(SectionHeader("Progress"))

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(1, 7)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(180)
        self.log_view.setPlaceholderText("Pipeline log output...")
        layout.addWidget(self.log_view)

        # --- Results section (hidden until success) ---------------------
        self.results_widget = QWidget()
        self.results_widget.hide()
        self._setup_results_ui()
        layout.addWidget(self.results_widget)

        # --- Action buttons --------------------------------------------
        actions = QHBoxLayout()
        self.start_btn = PrimaryButton("Start")
        self.start_btn.clicked.connect(self._on_start)
        actions.addWidget(self.start_btn)

        self.cancel_btn = ActionButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        actions.addWidget(self.cancel_btn)

        self.close_btn = ActionButton("Close")
        self.close_btn.clicked.connect(self.close)
        actions.addWidget(self.close_btn)

        actions.addStretch()
        layout.addLayout(actions)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #c0392b; padding: 2px;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

    def _setup_results_ui(self) -> None:
        layout = QVBoxLayout(self.results_widget)
        layout.setContentsMargins(0, 8, 0, 0)

        layout.addWidget(SectionHeader("Results"))

        # Summary cards
        cards = QGridLayout()
        cards.setSpacing(12)
        self.card_experiments = InfoCard("Experiments", "—")
        self.card_files = InfoCard("Files", "—")
        self.card_validation = InfoCard("Validation", "—")
        self.card_duration = InfoCard("Duration", "—")
        cards.addWidget(self.card_experiments, 0, 0)
        cards.addWidget(self.card_files, 0, 1)
        cards.addWidget(self.card_validation, 0, 2)
        cards.addWidget(self.card_duration, 0, 3)
        layout.addLayout(cards)

        # Per-experiment table
        self.experiment_tree = QTreeWidget()
        self.experiment_tree.setHeaderLabels(["Experiment", "Type", "Confidence"])
        self.experiment_tree.setColumnWidth(0, 140)
        self.experiment_tree.setColumnWidth(1, 220)
        self.experiment_tree.setMaximumHeight(180)
        layout.addWidget(self.experiment_tree)

        # Errors / warnings
        self.messages_view = QPlainTextEdit()
        self.messages_view.setReadOnly(True)
        self.messages_view.setMaximumHeight(140)
        layout.addWidget(self.messages_view)

        # Report link
        report_row = QHBoxLayout()
        self.report_label = QLabel("Report: —")
        self.report_label.setOpenExternalLinks(True)
        report_row.addWidget(self.report_label)
        self.open_folder_btn = ActionButton("Open Folder")
        self.open_folder_btn.clicked.connect(self._open_report_folder)
        report_row.addWidget(self.open_folder_btn)
        report_row.addStretch()
        layout.addLayout(report_row)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prefill_from_profile(self) -> None:
        """Prefill the investigation id from the active profile (main thread)."""
        try:
            from utils.config_loader import get_profile

            profile = get_profile()
            inv_id = profile.get_investigation_defaults().get("investigation_id", "")
            if inv_id:
                self.investigation_id_edit.setText(str(inv_id))
        except Exception:
            # Profile unavailable — fall back to the CLI default.
            self.investigation_id_edit.setText("inv_default")

    def _templates_root(self) -> str:
        """Resolve the active profile's assay-templates directory (main thread)."""
        try:
            from utils.config_loader import get_profile

            profile = get_profile()
            return str(Path(profile.get_templates_root()) / "assay_templates")
        except Exception:
            return "templates/assay_templates"

    def _browse_data_root(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Data Root", self.data_root_edit.text() or "."
        )
        if path:
            self.data_root_edit.setText(path)

    def _browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self.output_dir_edit.text() or "."
        )
        if path:
            self.output_dir_edit.setText(path)

    def _set_inputs_enabled(self, enabled: bool) -> None:
        """Enable/disable the setup inputs and Start button."""
        for widget in (
            self.data_root_edit,
            self.output_dir_edit,
            self.investigation_id_edit,
            self.inv_inm_edit,
            self.skip_conversion_check,
            self.skip_validation_check,
            self.start_btn,
        ):
            widget.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_start(self) -> None:
        """Validate inputs and start the worker thread."""
        if self._worker_running():
            return

        data_root = self.data_root_edit.text().strip()
        output_dir = self.output_dir_edit.text().strip()
        investigation_id = self.investigation_id_edit.text().strip() or "inv_default"

        errors = []
        if not data_root:
            errors.append("Data root is required.")
        elif not Path(data_root).is_dir():
            errors.append(f"Data root does not exist or is not a directory: {data_root}")
        if not output_dir:
            errors.append("Output directory is required.")

        if errors:
            self.error_label.setText("\n".join(errors))
            return
        self.error_label.setText("")

        self.results_widget.hide()
        self.progress_bar.setValue(1)
        self.log_view.setPlainText("")

        cfg = BatchConfig(
            data_root=data_root,
            output_dir=output_dir,
            investigation_id=investigation_id,
            templates_root=self._templates_root(),
            inv_inm_path=self.inv_inm_edit.text().strip(),
            skip_conversion=self.skip_conversion_check.isChecked(),
            skip_validation=self.skip_validation_check.isChecked(),
        )

        self.worker = BatchWorker(cfg, self)
        self.worker.stageChanged.connect(self._on_stage_changed)
        self.worker.progressPct.connect(self._on_progress)
        self.worker.logLine.connect(self._on_log_line)
        self.worker.failed.connect(self._on_failed)
        self.worker.succeeded.connect(self._on_succeeded)

        self._set_inputs_enabled(False)
        self.cancel_btn.setEnabled(True)
        self.worker.start()

    def _on_cancel(self) -> None:
        """Request cancellation of the running pipeline (D5)."""
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_cancel()
            self.log_view.appendPlainText("Cancellation requested...")

    @pyqtSlot(int, str)
    def _on_stage_changed(self, stage: int, title: str) -> None:
        self.progress_bar.setValue(stage)
        self.progress_bar.setFormat(f"Stage {stage}/7: {title}")

    @pyqtSlot(int)
    def _on_progress(self, pct: int) -> None:
        # Coarse percentage is informational; the bar stays in stage range (1..7).
        self.progress_bar.setFormat(f"Stage {max(1, int(pct / 100 * 7))}/7 (~{pct}%)")

    @pyqtSlot(str)
    def _on_log_line(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    @pyqtSlot(str)
    def _on_failed(self, message: str) -> None:
        self.error_label.setText(f"Batch processing failed: {message}")
        self._worker_finished()

    @pyqtSlot(object, str)
    def _on_succeeded(self, result, report_path: str) -> None:
        self._result = result
        self._report_path = report_path
        self.progress_bar.setValue(7)
        self.progress_bar.setFormat("Complete")
        self._show_results()
        self._worker_finished()

    def _worker_finished(self) -> None:
        """Common cleanup when the worker has stopped."""
        self._set_inputs_enabled(True)
        self.cancel_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Results view (D4)
    # ------------------------------------------------------------------

    def _show_results(self) -> None:
        result = self._result
        if result is None:
            return

        self.card_experiments.value_label.setText(
            f"{result.total_experiments} total · {result.successful_experiments} ok · "
            f"{result.failed_experiments} failed"
        )
        self.card_files.value_label.setText(
            f"{result.total_files} total · {result.converted_files} converted · "
            f"{result.failed_conversions} failed"
        )
        validation_text = "✓ PASSED" if result.validation_passed else "✗ FAILED"
        self.card_validation.value_label.setText(validation_text)
        self.card_duration.value_label.setText(f"{result.processing_time_seconds:.1f}s")

        # Per-experiment table: prefer structured classifications (D5), fall back
        # to parsing the human-readable info lines (D4) so no data is lost.
        self.experiment_tree.clear()
        rows = self._parse_experiment_rows(result)
        for exp_id, exp_type, confidence in rows:
            item = QTreeWidgetItem([exp_id, exp_type, confidence])
            self.experiment_tree.addTopLevelItem(item)
        if not rows:
            self.experiment_tree.addTopLevelItem(
                QTreeWidgetItem(["(no per-experiment classifications)"])
            )
        self.experiment_tree.expandAll()

        # Errors / warnings (verbatim, never truncated)
        msg_lines = []
        if result.errors:
            msg_lines.append(f"ERRORS ({len(result.errors)}):")
            msg_lines.extend(f"  - {e}" for e in result.errors)
        if result.warnings:
            msg_lines.append(f"WARNINGS ({len(result.warnings)}):")
            msg_lines.extend(f"  - {w}" for w in result.warnings)
        if result.info:
            msg_lines.append("INFO:")
            msg_lines.extend(f"  {line}" for line in result.info)
        self.messages_view.setPlainText("\n".join(msg_lines) if msg_lines else "(no messages)")

        # Report link + Open Folder
        if self._report_path:
            self.report_label.setText(f"Report: {self._report_path}")
            self.open_folder_btn.setEnabled(True)
        else:
            self.report_label.setText("Report: —")
            self.open_folder_btn.setEnabled(False)

        self.results_widget.show()

    @staticmethod
    def _parse_experiment_rows(result) -> list[tuple[str, str, str]]:
        """Build (id, type, confidence) rows for the results table.

        Prefers the structured ``result.classifications`` (D5) and falls back
        to regex-parsing the human-readable ``result.info`` lines (D4).
        """
        rows: list[tuple[str, str, str]] = []
        classifications = getattr(result, "classifications", None)
        if classifications:
            for exp_id, info in classifications.items():
                confidence = info.get("confidence", "")
                rows.append(
                    (
                        str(exp_id),
                        str(info.get("type", "")),
                        f"{confidence}" if confidence is not None else "",
                    )
                )
            return rows

        for line in getattr(result, "info", []) or []:
            match = _INFO_EXPERIMENT_PATTERN.match(line)
            if match:
                rows.append((match.group("id"), match.group("type"), match.group("conf")))
        return rows

    def _open_report_folder(self) -> None:
        if not self._report_path:
            return
        folder = str(Path(self._report_path).parent)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _worker_running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def closeEvent(self, event) -> None:  # noqa: N802
        """Confirm and wait for a running worker before closing."""
        if self._worker_running():
            reply = QMessageBox.question(
                self,
                "Batch pipeline still running",
                "The batch pipeline is still running. Close and let it finish, or cancel?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            if self.worker is not None:
                self.worker.wait(2000)
        event.accept()
