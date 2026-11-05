"""
Screenshot capture for agent inspection (P0-4, annotation P1-2).

``gui_screenshot()`` grabs a widget via ``QWidget.grab()`` (safe under
``QT_QPA_PLATFORM=offscreen``) and writes a PNG to ``reports/``.  The longest
image edge is downscaled to ``max_edge`` (default 2048) with Pillow so the
vision model gets a right-sized image.  File *paths* are returned -- never
base64 -- so tool responses stay small.

``annotate=True`` draws the P1-2 set-of-marks overlay (numbered badges +
right-side legend panel, see :mod:`gui.agent_tools.annotate`) and writes the
``<name>.legend.json`` sidecar next to the PNG.  ``result.marks`` (and the
sidecar) carry root-anchored global ``Mark`` rects -- the dump geometry space.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from .annotate import Mark, collect_marks, legend_path_for, marks_to_json


@dataclass
class ScreenshotResult:
    """Outcome of a :func:`gui_screenshot` capture."""

    path: Path
    width: int
    height: int
    marks: Optional[list[Mark]] = field(default=None)  # populated when annotate=True


def grab_widget(widget: Optional[QWidget] = None) -> QPixmap:
    """Grab ``widget`` (default: active window) as a ``QPixmap``.

    Works headless (``QT_QPA_PLATFORM=offscreen``) -- ``QWidget.grab()``
    renders the widget's backing store without a real display.
    """
    if widget is None:
        widget = QApplication.activeWindow()
    if widget is None:
        raise RuntimeError("grab_widget: no active window; pass widget explicitly")
    return widget.grab()


def _default_name(widget: QWidget) -> str:
    from .ids import get_test_id

    base = get_test_id(widget) or type(widget).__name__
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = base.replace("/", "_").replace("\\", "_").replace(":", "_")
    return f"{safe}_{stamp}"


def _resize_to_max_edge(pixmap: QPixmap, max_edge: int) -> QPixmap:
    """Downscale so the longest edge is <= ``max_edge`` (Pillow LANCZOS)."""
    if max_edge <= 0:
        raise ValueError("max_edge must be positive")
    width, height = pixmap.width(), pixmap.height()
    longest = max(width, height)
    if longest <= max_edge:
        return pixmap

    from PIL import Image

    payload = QByteArray()
    buffer = QBuffer(payload)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    image: Image.Image = Image.open(io.BytesIO(payload.data()))
    scale = max_edge / float(longest)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    image = image.resize(new_size, Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, "PNG")
    out.seek(0)
    scaled = QPixmap()
    scaled.loadFromData(out.read())
    return scaled


def _apply_theme(theme: str) -> None:
    """Switch the Qt stylesheet before grabbing -- session-only (U-06).

    Never touches ``QSettings``: prefers the running application's
    ``apply_theme(theme, persist=False)`` (``StewardApp``) and falls back to
    applying the theme QSS directly so ``theme=`` works with any
    ``QApplication`` (e.g. offscreen test harnesses).  Callers restore the
    previous stylesheet afterwards (see :func:`gui_screenshot`).
    """
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    apply_theme = getattr(app, "apply_theme", None)
    if callable(apply_theme):
        apply_theme(theme, persist=False)
    else:
        style_path = (
            Path(__file__).resolve().parent.parent / "resources" / "styles" / f"{theme}.qss"
        )
        if style_path.exists():
            app.setStyleSheet(style_path.read_text(encoding="utf-8"))
    QApplication.processEvents()


def gui_screenshot(
    widget: Optional[QWidget] = None,
    *,
    out_dir: Path = Path("reports"),
    name: Optional[str] = None,
    annotate: bool = False,
    max_edge: int = 2048,
    theme: Optional[str] = None,
) -> ScreenshotResult:
    """Capture ``widget`` (default: active window) to a PNG in ``out_dir``.

    - ``name`` defaults to ``<testId|class>_<timestamp>``.
    - ``max_edge`` caps the longest image edge (downscaled via Pillow).
    - ``theme`` switches the Qt stylesheet (``light``/``dark``) for the capture
      only (``apply_theme(theme, persist=False)`` when available, raw QSS
      otherwise); the previous stylesheet is restored afterwards and the
      user's persisted ``gui/theme`` is never rewritten (AGENTS.md section
      8.1).  Light theme is preferred for text-heavy review (better OCR).
    - ``annotate=True`` draws the set-of-marks overlay and writes the
      ``<name>.legend.json`` sidecar; ``result.marks`` is populated with the
      root-anchored global marks (dump geometry space).
    """
    if widget is None:
        widget = QApplication.activeWindow()
    if widget is None:
        raise RuntimeError("gui_screenshot: no active window; pass widget explicitly")

    app = QApplication.instance()
    previous_style: Optional[str] = None
    if theme is not None and isinstance(app, QApplication):
        previous_style = app.styleSheet()
        _apply_theme(theme)

    try:
        pixmap = grab_widget(widget)
        marks: Optional[list[Mark]] = None
        if annotate:
            marks = collect_marks(widget)
            # collect_marks rects are root-anchored widget coordinates; the grab
            # may be devicePixelRatio-scaled -- convert to pixmap pixels for
            # drawing (the returned/sidecar marks stay in the global space).
            scale = pixmap.width() / widget.width() if widget.width() else 1.0
            px_marks = [
                Mark(
                    m.index,
                    m.test_id,
                    (
                        round(m.rect[0] * scale),
                        round(m.rect[1] * scale),
                        round(m.rect[2] * scale),
                        round(m.rect[3] * scale),
                    ),
                    m.label,
                )
                for m in marks
            ]
            from .annotate import annotate as annotate_pixmap

            pixmap, _drawn = annotate_pixmap(pixmap, px_marks)

        pixmap = _resize_to_max_edge(pixmap, max_edge)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        file_name = name or _default_name(widget)
        if not file_name.lower().endswith(".png"):
            file_name = f"{file_name}.png"
        path = (out_dir / file_name).resolve()
        if not pixmap.save(str(path), "PNG"):
            raise RuntimeError(f"gui_screenshot: failed to write {path}")

        if marks is not None:
            legend_path_for(path).write_text(marks_to_json(marks), encoding="utf-8")

        return ScreenshotResult(
            path=path, width=pixmap.width(), height=pixmap.height(), marks=marks
        )
    finally:
        # U-06: theme= is session-only -- never leave the app in the other
        # theme, even when the capture fails mid-way.
        if previous_style is not None and isinstance(app, QApplication):
            app.setStyleSheet(previous_style)
            QApplication.processEvents()
