"""
Batch pipeline worker for the ISA-JSON Data Steward GUI.

This module hosts the Qt-side orchestration of the shared 7-stage batch
pipeline (``utils.batch.batch_processor.BatchProcessor``).  It deliberately
reuses the *exact same* core modules and active profile as the CLI entry
point (``isa-json-steward-batch``) so that the GUI and the CLI execute
identical pipeline code.

Design notes (see ``plans/gui-parity-plan.md``, decisions D2/D3/D5):

* ``BatchConfig`` is a plain ``str``/``bool`` dataclass snapshot taken on the
  main thread.  The worker never touches the ``ProfileLoader`` singleton:
  ``investigation_id`` and ``templates_root`` must already be resolved on the
  main thread (``get_profile()``) and passed in as plain strings.
* Per-stage progress is obtained by attaching a private ``logging.Handler``
  to the ``utils.batch.batch_processor`` logger and regex-matching the
  ``Step 1: ...`` .. ``Step 7: ...`` lines.  The handler is attached inside
  ``run()`` and always detached again in ``finally``.
"""

import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

# Matches the per-stage log lines emitted by BatchProcessor.process_batch(),
# e.g. "Step 1: Scanning experiment folders" (batch_processor.py, "Step N: ...").
STAGE_LOG_PATTERN = re.compile(r"^Step ([1-7]): (.*)$")

# Total number of pipeline stages (used to scale the progress bar).
TOTAL_STAGES = 7


@dataclass
class BatchConfig:
    """Main-thread snapshot of everything the worker needs.

    All fields are plain strings/booleans (no profile objects) so they are
    safe to read from a worker thread.
    """

    data_root: str = ""
    output_dir: str = ""
    investigation_id: str = "inv_default"
    templates_root: str = ""
    inv_inm_path: str = ""
    skip_conversion: bool = True
    skip_validation: bool = True


class _StageHandler(logging.Handler):
    """Private logging handler that translates stage log lines into signals.

    It only forwards records that carry a message matching
    :data:`STAGE_LOG_PATTERN`; everything else is silently ignored.
    """

    def __init__(self, on_stage, on_log):
        super().__init__(level=logging.INFO)
        self._on_stage = on_stage
        self._on_log = on_log

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
        try:
            message = record.getMessage()
            match = STAGE_LOG_PATTERN.match(message)
            if match:
                stage = int(match.group(1))
                self._on_stage(stage, match.group(2))
                self._on_log(message)
            else:
                self._on_log(message)
        except Exception:  # pragma: no cover - never break the pipeline for logging
            self.handleError(record)


class BatchWorker(QThread):
    """QThread worker running the shared 7-stage batch pipeline.

    Signals:
        stageChanged: ``(stage_index 1..7, stage_title)``
        progressPct:  coarse percentage (``stage / 7 * 100``)
        logLine:      one log line from the pipeline
        failed:       error message when the run did not complete
        succeeded:    ``(BatchProcessingResult, report_path)``
    """

    stageChanged = pyqtSignal(int, str)
    progressPct = pyqtSignal(int)
    logLine = pyqtSignal(str)
    failed = pyqtSignal(str)
    succeeded = pyqtSignal(object, str)

    def __init__(self, cfg: BatchConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._cancel_event = threading.Event()
        self._handler: Optional[_StageHandler] = None

    def run(self) -> None:
        """Execute the batch pipeline (runs on the worker thread).

        IMPORTANT (D2): this method must never call ``get_profile()`` or
        ``set_profile()``.  All profile-derived values are passed in as plain
        strings on :attr:`cfg`.
        """
        from utils.batch.batch_processor import BatchProcessor

        target_logger = logging.getLogger("utils.batch.batch_processor")
        self._handler = _StageHandler(self._emit_stage, self._emit_log)
        target_logger.addHandler(self._handler)

        result = None
        try:
            processor = BatchProcessor(
                investigation_id=self.cfg.investigation_id,
                inv_inm_path=self.cfg.inv_inm_path or None,
                templates_root=self.cfg.templates_root or None,
            )
            result = processor.process_batch(
                data_root=self.cfg.data_root,
                output_dir=self.cfg.output_dir,
                skip_conversion=self.cfg.skip_conversion,
                skip_validation=self.cfg.skip_validation,
                cancel_event=self._cancel_event,
            )
            report_path = str(Path(self.cfg.output_dir) / "processing_report.json")
            self.succeeded.emit(result, report_path)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            self.failed.emit(str(exc))
        finally:
            if self._handler is not None:
                target_logger.removeHandler(self._handler)
                self._handler = None

    def _emit_stage(self, stage: int, title: str) -> None:
        """Emit the stageChanged + progressPct signals."""
        self.stageChanged.emit(stage, title)
        self.progressPct.emit(int(stage / TOTAL_STAGES * 100))

    def _emit_log(self, message: str) -> None:
        """Emit a single log line."""
        self.logLine.emit(message)

    def request_cancel(self) -> None:
        """Request cancellation of the running pipeline (D5).

        The pipeline checks the underlying ``threading.Event`` between stages
        and stops before the next step.
        """
        self._cancel_event.set()
