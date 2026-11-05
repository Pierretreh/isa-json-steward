"""
Set-of-marks annotated screenshots (P1-2).

plans/agent-gui-observability.md sections 2.4 and 2.6:

- Badge order is DFS widget-tree order, numbered from 1; only widgets with a
  ``testId``, non-empty geometry, and visible relative to the captured root
  are marked.
- Outline: 2 px rounded rectangle in a high-contrast color (the theme
  background inverted), drawn with a contrasting halo so it reads over any
  surface; badge: filled circle with the index at the box's top-left.
- The legend is appended as a right-hand panel on the image itself (lines
  ``"#1  page.materials.saveButton  —  Save"``) **and** written as
  ``<name>.legend.json`` (a JSON list of ``Mark`` dicts) next to the PNG so
  text ground truth never depends on OCR.

Coordinate spaces: ``Mark.rect`` is ``global x,y,w,h`` anchored at the
captured root's top-left corner -- the same space as
:func:`~gui.agent_tools.dump.dump_widget_tree` geometry.  For a
``QWidget.grab()`` capture at devicePixelRatio 1 (the offscreen/CI case) this
equals the PNG's pixel space; :func:`~gui.agent_tools.screenshot.gui_screenshot`
passes pixmap-space rects to :func:`annotate` (scaling for the device pixel
ratio) but reports/legend-writes the root-anchored marks, so dump and legend
always agree.

U-15 (scroll clipping): :func:`collect_marks` only keeps marks for widgets
that are FULLY visible inside the captured root -- i.e. inside the root rect
AND inside every ancestor ``QAbstractScrollArea`` viewport mapped into root
space.  Anything clipped (below a scroll fold, or outside the root) is
**dropped, not shrunk to the visible part**: the legend stays clean and every
legend rect lies fully inside the captured root rect.  Before U-15 the
overlay drew phantom outlines for scroll-clipped widgets and the right-side
legend panel could grow the annotated canvas far beyond the grab (e.g. a
~1390px settings canvas).  Sweep consumers comparing legends must
re-baseline: badge numbers are assigned over the surviving DFS order and
below-the-fold widgets no longer get badges.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QAbstractScrollArea, QApplication, QWidget

from .ids import get_test_id

BADGE_RADIUS = 10
OUTLINE_WIDTH = 2
BOX_CORNER_RADIUS = 4
LEGEND_MIN_WIDTH = 240
LEGEND_MAX_WIDTH = 1024
LEGEND_PADDING = 12
LEGEND_LINE_SPACING = 6
LEGEND_MIN_FONT_POINTS = 7

__all__ = ["Mark", "collect_marks", "annotate", "legend_line", "legend_path_for"]


@dataclass
class Mark:
    """One numbered badge on an annotated screenshot (1-based ``index``)."""

    index: int
    test_id: str
    rect: tuple[int, int, int, int]  # global x,y,w,h (root-anchored; == PNG px when unscaled)
    label: str

    def to_dict(self) -> dict:
        """JSON-friendly dict (rect as a 4-list)."""
        return {
            "index": self.index,
            "test_id": self.test_id,
            "rect": [int(v) for v in self.rect],
            "label": self.label,
        }


def legend_line(mark: Mark) -> str:
    """Legend line for ``mark``: ``"#1  page.materials.saveButton  —  Save"``."""
    return f"#{mark.index}  {mark.test_id}  —  {mark.label}"


def legend_path_for(png_path: Path | str) -> Path:
    """Return the ``<name>.legend.json`` sidecar path for a PNG path."""
    path = Path(png_path)
    return path.with_name(path.stem + ".legend.json")


def collect_marks(root: QWidget) -> list[Mark]:
    """Collect set-of-marks badges for visible testId widgets under ``root``.

    Badge order is DFS widget-tree order (``root`` first), numbered from 1.
    Only widgets with a ``testId``, non-empty geometry and visible relative to
    ``root`` are marked (plan section 2.6).  Rects are global coordinates
    anchored at ``root``'s top-left corner (matching dump geometry).

    U-15: a widget is marked only when its FULL rect is visible in the
    capture -- inside the root rect and inside every ancestor
    ``QAbstractScrollArea`` viewport (the ``widget.parentWidget()`` chain up
    to and including ``root``).  Clipped widgets are dropped, not shrunk (see
    the module docstring), and indices are renumbered over the surviving DFS
    order.
    """
    from .dump import _widget_text

    origin = root.mapToGlobal(QPoint(0, 0))
    root_rect = QRect(0, 0, root.width(), root.height())
    marks: list[Mark] = []

    def _visible_rect(widget: QWidget) -> QRect:
        """``widget`` rect in root coords, clipped to the captured region."""
        top_left = widget.mapToGlobal(QPoint(0, 0)) - origin
        rect = QRect(top_left.x(), top_left.y(), widget.width(), widget.height())
        rect = rect.intersected(root_rect)
        if widget is root:
            # ``grab()`` renders the root's full rect; viewports OUTSIDE the
            # captured root do not clip it.
            return rect
        parent = widget.parentWidget()
        while parent is not None:
            if isinstance(parent, QAbstractScrollArea):
                viewport = parent.viewport()
                if viewport is not None:
                    vp_top_left = viewport.mapToGlobal(QPoint(0, 0)) - origin
                    rect = rect.intersected(
                        QRect(vp_top_left.x(), vp_top_left.y(), viewport.width(), viewport.height())
                    )
            if parent is root:
                break
            parent = parent.parentWidget()
        return rect

    def _walk(widget: QWidget) -> None:
        test_id = get_test_id(widget)
        if test_id and widget.width() > 0 and widget.height() > 0:
            if widget is root or widget.isVisibleTo(root):
                top_left = widget.mapToGlobal(QPoint(0, 0)) - origin
                rect = QRect(top_left.x(), top_left.y(), widget.width(), widget.height())
                # U-15: drop marks clipped by the root or any ancestor scroll
                # viewport (prefer drop over shrinking -- module docstring).
                if _visible_rect(widget) == rect:
                    label = _widget_text(widget) or widget.accessibleName() or type(widget).__name__
                    marks.append(
                        Mark(
                            index=len(marks) + 1,
                            test_id=test_id,
                            rect=(rect.x(), rect.y(), rect.width(), rect.height()),
                            label=label,
                        )
                    )
        for child in widget.children():
            if isinstance(child, QWidget):
                _walk(child)

    _walk(root)
    return marks


def _contrast_colors() -> tuple[QColor, QColor]:
    """Return ``(fg, bg)``: theme background and its inversion (high contrast)."""
    bg = QColor("#ffffff")
    try:
        app = QApplication.instance()
        # isinstance narrows past the stubs' QCoreApplication | None (only a
        # QApplication has activeWindow()/palette()).
        if isinstance(app, QApplication):
            window = app.activeWindow()
            palette_source = window if window is not None else app
            bg = palette_source.palette().window().color()
    except Exception:
        pass
    fg = QColor(255 - bg.red(), 255 - bg.green(), 255 - bg.blue())
    return fg, bg


def _legend_font(metrics_probe_text: str, avail_width: int) -> QFont:
    """Monospace legend font, shrunk so ``metrics_probe_text`` fits ``avail_width``."""
    font = QFont()
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(10)
    while font.pointSize() > LEGEND_MIN_FONT_POINTS:
        if QFontMetrics(font).horizontalAdvance(metrics_probe_text) <= avail_width:
            break
        font.setPointSize(font.pointSize() - 1)
    return font


def annotate(pixmap: QPixmap, marks: list[Mark]) -> tuple[QPixmap, list[Mark]]:
    """Draw numbered boxes + right-side legend on ``pixmap``.

    ``marks`` rects are interpreted in pixmap pixel coordinates.  Returns
    ``(annotated_pixmap, drawn_marks)``; marks with empty geometry are dropped.
    The legend panel is appended on the right (full testIds always visible),
    so the returned pixmap is wider than the input.
    """
    if pixmap.isNull():
        raise ValueError("annotate: pixmap is null")

    drawable = [m for m in marks if m.rect[2] > 0 and m.rect[3] > 0]
    fg, bg = _contrast_colors()

    font = _legend_font(
        max((legend_line(m) for m in drawable), default=""),
        LEGEND_MAX_WIDTH - 2 * LEGEND_PADDING,
    )
    metrics = QFontMetrics(font)
    line_height = metrics.height() + LEGEND_LINE_SPACING

    legend_w = 0
    if drawable:
        max_text_w = max(metrics.horizontalAdvance(legend_line(m)) for m in drawable)
        legend_w = max(
            LEGEND_MIN_WIDTH,
            min(LEGEND_MAX_WIDTH, max_text_w + 2 * LEGEND_PADDING),
        )
    legend_h = max(pixmap.height(), 2 * LEGEND_PADDING + len(drawable) * line_height)

    out = QPixmap(pixmap.width() + legend_w, legend_h)
    out.fill(bg)

    painter = QPainter(out)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.drawPixmap(0, 0, pixmap)

        badge_font = QFont(font)
        badge_font.setPointSize(8)
        for mark in drawable:
            x, y, w, h = mark.rect
            rect = QRect(x, y, w, h)
            # halo pass (bg) then core pass (fg): legible on any surface
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(bg, OUTLINE_WIDTH + 2))
            painter.drawRoundedRect(rect, BOX_CORNER_RADIUS, BOX_CORNER_RADIUS)
            painter.setPen(QPen(fg, OUTLINE_WIDTH))
            painter.drawRoundedRect(rect, BOX_CORNER_RADIUS, BOX_CORNER_RADIUS)

            # numbered badge centered on the box's top-left corner
            center = QPoint(x, y)
            painter.setBrush(fg)
            painter.setPen(QPen(bg, 1))
            painter.drawEllipse(center, BADGE_RADIUS, BADGE_RADIUS)
            painter.setFont(badge_font)
            painter.setPen(QPen(bg, 1))
            painter.drawText(
                QRect(x - BADGE_RADIUS, y - BADGE_RADIUS, 2 * BADGE_RADIUS, 2 * BADGE_RADIUS),
                Qt.AlignmentFlag.AlignCenter,
                str(mark.index),
            )

        if drawable:
            panel_x = pixmap.width()
            painter.fillRect(QRect(panel_x, 0, legend_w, out.height()), bg)
            painter.setPen(QPen(fg, OUTLINE_WIDTH))
            painter.drawLine(panel_x, 0, panel_x, out.height())
            painter.setFont(font)
            baseline = LEGEND_PADDING + metrics.ascent()
            for mark in drawable:
                painter.setPen(QPen(fg, 1))
                painter.drawText(panel_x + LEGEND_PADDING, baseline, legend_line(mark))
                baseline += line_height
    finally:
        painter.end()

    return out, drawable


def marks_to_json(marks: list[Mark]) -> str:
    """Serialize ``marks`` as the ``<name>.legend.json`` payload (a JSON list)."""
    import json

    return json.dumps([m.to_dict() for m in marks], indent=2)
