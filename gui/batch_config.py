"""
Qt-free configuration snapshot for the batch pipeline worker.

``BatchConfig`` is a plain ``str``/``bool`` dataclass — it deliberately
depends on the standard library only (``dataclasses``) and imports
**no** PyQt6 modules.  This keeps it importable on machines where PyQt6
is unavailable or its native graphics libraries (e.g. ``libEGL.so.1``)
are missing, so the plain-fields contract can be exercised by tests on
every machine.

The Qt-dependent worker (:class:`gui.batch_runner.BatchWorker`) and the
dialog (:class:`gui.dialogs.batch_processing.BatchProcessingDialog`)
import :class:`BatchConfig` from this module (``gui.batch_runner``
re-exports it for backward compatibility).
"""

from dataclasses import dataclass


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
    # Validation layers to run in stage 7 (comma-separated subset of
    # ``schema,semantic,data_file,template,shacl,owl,ols``).  Empty string =
    # the code default: all six core layers, EXCEPT the optional ``ols`` layer.
    validation_layers: str = ""
    # Optional, network-dependent OLS (EBI Ontology Lookup Service) layer.
    # Default OFF; only effective when ``validation_layers`` includes ``ols``
    # (an empty ``validation_layers`` with ``enable_ols=True`` adds ``ols``).
    enable_ols: bool = False
