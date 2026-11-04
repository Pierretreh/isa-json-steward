"""Batch-2 theme-contrast tests (U-03, U-04, U-09).

Acceptance coverage from ``plans/gui-usability-fixes.md`` (section 3):

- **U-03**: the new QSS rules exist in both theme files (scroll viewports,
  item views, ``uiRole`` roles, panel role); page backgrounds render the theme
  background on all 10 pages in both themes; list widgets / details panels
  render dark-in-dark with light text; dashboard stat values and group-box
  titles keep >= 4.5:1 contrast in both themes.
- **U-04**: alternating tree rows keep >= 4.5:1 text contrast and genuinely
  alternate backgrounds in both themes (``page.studies.studiesTree`` and
  ``page.ontology.ontologyTree``).
- **U-09**: the sidebar title chip paints its own background (no
  white-on-white) and keeps >= 4.5:1 contrast in both themes.

Pixel probes follow the proven subtask-1 pattern: children are hidden to
sample the exact ``#contentPage`` background, and foreground/background probes
use the modal (most common) background color versus the farthest *frequent*
color of a rendered region -- the QSS palette renders solid colors, so the
probes are deterministic and never sample single anti-aliasing pixels.
"""

import re
from collections import Counter
from pathlib import Path

import pytest

try:
    from PyQt6.QtCore import QRect
    from PyQt6.QtWidgets import (
        QApplication,
        QFrame,
        QGroupBox,
        QListWidgetItem,
        QTreeWidgetItem,
        QWidget,
    )

    PYQT6_AVAILABLE = True
except (ImportError, OSError):
    PYQT6_AVAILABLE = False

pytestmark = pytest.mark.gui

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLES = REPO_ROOT / "gui" / "resources" / "styles"

DARK_BG = (0x1E, 0x1E, 0x1E)
LIGHT_BG = (0xFF, 0xFF, 0xFF)
SIDEBAR_CHIPS = {"dark": (0x25, 0x25, 0x26), "light": (0x2C, 0x3E, 0x50)}


# ---------------------------------------------------------------------------
# Color helpers (deterministic pixel probes)
# ---------------------------------------------------------------------------


def _srgb_luminance(color) -> float:
    def channel(c: float) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in color[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(c1, c2) -> float:
    lighter = max(_srgb_luminance(c1), _srgb_luminance(c2))
    darker = min(_srgb_luminance(c1), _srgb_luminance(c2))
    return (lighter + 0.05) / (darker + 0.05)


def _close(c1, c2, tol: int = 8) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(c1, c2))


def _grab(widget):
    return widget.grab().toImage()


def _region_of(child, ancestor):
    """Rect of ``child`` in ``ancestor`` grab coordinates.

    Transparent child widgets (labels) composite onto a flat gray when grabbed
    directly, so their pixels must be sampled from an opaque ancestor's grab.
    """
    top_left = child.mapTo(ancestor, child.rect().topLeft())
    return QRect(top_left, child.size())


def _region_contrast(image, rect=None, min_count: int = 8):
    """Return ``(background, foreground, ratio)`` for a rendered region.

    Background is the modal color; foreground is the frequent color (seen at
    least ``min_count`` times) farthest from the background -- robust against
    anti-aliasing without sampling single glyph pixels.
    """
    rect = rect or image.rect()
    counts: Counter = Counter()
    for y in range(rect.top(), rect.bottom()):
        for x in range(rect.left(), rect.right()):
            p = image.pixelColor(x, y)
            counts[(p.red(), p.green(), p.blue())] += 1
    if not counts:
        raise AssertionError(f"empty probe region {rect}")
    bg, _ = counts.most_common(1)[0]
    fg = max(
        (c for c, n in counts.items() if n >= min_count and c != bg),
        key=lambda c: sum(abs(a - b) for a, b in zip(c, bg)),
        default=bg,
    )
    return bg, fg, _contrast(bg, fg)


@pytest.fixture
def apply_theme(qapp):
    """Apply a theme QSS for the test body and restore the previous one."""
    previous: list = []

    def _apply(name: str) -> str:
        qss = (STYLES / f"{name}.qss").read_text(encoding="utf-8")
        if not previous:
            previous.append(qapp.styleSheet())
        qapp.setStyleSheet(qss)
        QApplication.processEvents()
        return qss

    yield _apply
    if previous:
        qapp.setStyleSheet(previous[0])
    QApplication.processEvents()


def _show_page(main_window, page_id: str):
    page = main_window.pages[page_id]
    main_window.content_stack.setCurrentWidget(page)
    QApplication.processEvents()
    return page


# ---------------------------------------------------------------------------
# (a) QSS-text assertions: the new rules exist in both theme files
# ---------------------------------------------------------------------------


class TestQssRules:
    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_scroll_viewport_rules_present(self, theme):
        qss = (STYLES / f"{theme}.qss").read_text(encoding="utf-8")
        assert "QWidget#contentPage QScrollArea," in qss
        assert "QWidget#contentPage QScrollArea > QWidget > QWidget" in qss

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_ui_role_rules_present(self, theme):
        qss = (STYLES / f"{theme}.qss").read_text(encoding="utf-8")
        for role in ("muted", "statValue", "error", "success", "warning"):
            assert f'QLabel[uiRole="{role}"]' in qss, f"{theme}: missing {role} rule"
        assert 'QFrame[uiRole="panel"]' in qss, f"{theme}: missing panel rule"

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_sidebar_title_has_own_background(self, theme):
        qss = (STYLES / f"{theme}.qss").read_text(encoding="utf-8")
        match = re.search(r"QLabel#sidebarTitle\s*\{([^}]*)\}", qss, re.S)
        assert match, f"{theme}: QLabel#sidebarTitle rule missing"
        assert "background-color" in match.group(1)
        assert "color" in match.group(1)

    def test_dark_theme_item_view_rules(self):
        qss = (STYLES / "dark.qss").read_text(encoding="utf-8")
        for selector in ("QListWidget", "QTextBrowser", "QTreeView", "QTableView"):
            # Selectors may share a block (e.g. "QTreeView, QTableView {"),
            # so match a block header containing the selector, not a line start.
            assert re.search(rf"\b{selector}\b[^{{;]*{{", qss), f"missing {selector} block"
        # U-04: item text color lives on the ::item rules, alternating rows on
        # the base rules.
        for base in ("QTreeWidget", "QTableWidget", "QListWidget"):
            assert re.search(rf"^{base}\s*{{[^}}]*alternate-background-color", qss, re.M | re.S)
            assert re.search(rf"^{base}::item\s*{{[^}}]*color", qss, re.M | re.S)

    def test_light_theme_alternate_parity(self):
        qss = (STYLES / "light.qss").read_text(encoding="utf-8")
        for base in ("QTreeWidget", "QTableWidget", "QListWidget"):
            assert re.search(rf"^{base}\s*{{[^}}]*alternate-background-color", qss, re.M | re.S)


# ---------------------------------------------------------------------------
# (b) Pixel probes
# ---------------------------------------------------------------------------


class TestPageBackgrounds:
    """U-03 acceptance 1: no light patches from the scroll viewports."""

    @pytest.mark.parametrize("theme,expected", [("dark", DARK_BG), ("light", LIGHT_BG)])
    def test_all_pages_show_theme_background(self, main_window, apply_theme, theme, expected):
        apply_theme(theme)
        for page_id in main_window.pages:
            page = _show_page(main_window, page_id)
            hidden_state = [(w, w.isHidden()) for w in page.findChildren(QWidget)]
            for w, _ in hidden_state:
                w.hide()
            QApplication.processEvents()
            try:
                img = _grab(page)
                w, h = img.width(), img.height()
                probes = [(w // 2, h // 2), (4, 4), (w - 5, h - 5)]
                for x, y in probes:
                    p = img.pixelColor(x, y)
                    got = (p.red(), p.green(), p.blue())
                    assert _close(got, expected), (
                        f"page {page_id!r} {theme}: background probe {got} at {(x, y)} "
                        f"!= theme background {expected}"
                    )
            finally:
                for w, was_hidden in hidden_state:
                    w.setVisible(not was_hidden)
            QApplication.processEvents()


class TestPanelsAndLists:
    """U-03 acceptance 2: details panels and list widgets render themed."""

    @pytest.mark.parametrize("theme,expected", [("dark", DARK_BG), ("light", LIGHT_BG)])
    def test_list_widget_surface_and_text(self, main_window, apply_theme, theme, expected):
        from gui.agent_tools.ids import find_by_test_id

        apply_theme(theme)
        page = _show_page(main_window, "images")
        raw_list = find_by_test_id(page, "page.images.rawImagesList")
        assert raw_list is not None
        raw_list.clear()
        raw_list.addItem(QListWidgetItem("sample_001.czi"))
        QApplication.processEvents()

        img = _grab(raw_list)
        # Empty-area background probe (right margin, no text there).
        p = img.pixelColor(img.width() - 6, img.height() // 2)
        assert _close((p.red(), p.green(), p.blue()), expected, tol=12), (
            f"QListWidget {theme}: background {(p.red(), p.green(), p.blue())} != {expected}"
        )
        bg, fg, ratio = _region_contrast(img)
        assert ratio >= 4.5, f"QListWidget {theme}: item text {fg} on {bg} = {ratio:.2f}:1"

    @pytest.mark.parametrize("theme", ["dark", "light"])
    def test_details_panel_background_and_text(self, main_window, apply_theme, theme):
        apply_theme(theme)
        page = _show_page(main_window, "studies")
        panels = [f for f in page.findChildren(QFrame) if f.property("uiRole") == "panel"]
        assert panels, "details panel with uiRole='panel' not found"
        img = _grab(panels[0])
        p = img.pixelColor(3, 3)
        panel_bg = (p.red(), p.green(), p.blue())
        if theme == "dark":
            assert _srgb_luminance(panel_bg) < 0.15, f"panel not dark: {panel_bg}"
        else:
            assert _srgb_luminance(panel_bg) > 0.85, f"panel not light: {panel_bg}"

        # Sample the browser's text over the opaque panel grab (the browser
        # itself is styled transparent and composites onto gray when grabbed).
        bg, fg, ratio = _region_contrast(img, _region_of(page.details_browser, panels[0]))
        assert ratio >= 4.5, f"details text {fg} on {bg} = {ratio:.2f}:1 in {theme}"


class TestStatValues:
    """U-03 acceptance 4: dashboard stat values legible in both themes."""

    @pytest.mark.parametrize("theme", ["dark", "light"])
    def test_dashboard_stat_values_legible(self, main_window, apply_theme, theme):
        from gui.widgets.common import InfoCard

        apply_theme(theme)
        page = _show_page(main_window, "dashboard")
        cards = page.findChildren(InfoCard)
        assert cards, "no InfoCard stat cards on the dashboard"
        for card in cards:
            # Sample over the opaque card grab (the label is transparent).
            img = _grab(card)
            bg, fg, ratio = _region_contrast(img, _region_of(card.value_label, card))
            assert ratio >= 4.5, (
                f"stat value {card.value_label.text()!r} in {theme}: "
                f"{fg} on {bg} = {ratio:.2f}:1"
            )


class TestGroupTitles:
    """U-03 acceptance 3: CollapsibleGroupBox titles legible in both themes."""

    @pytest.mark.parametrize("theme", ["dark", "light"])
    def test_settings_group_title_legible(self, main_window, apply_theme, theme):
        apply_theme(theme)
        page = _show_page(main_window, "settings")
        boxes = [b for b in page.findChildren(QGroupBox) if b.title()]
        assert boxes, "no titled group boxes on the settings page"
        for box in boxes:
            img = _grab(box)
            # Title band: the top margin strip, right of the collapse button.
            band = QRect(32, 0, min(220, img.width() - 36), 14)
            bg, fg, ratio = _region_contrast(img, band)
            assert ratio >= 4.5, (
                f"group title {box.title()!r} in {theme}: {fg} on {bg} = {ratio:.2f}:1"
            )


class TestSidebarTitle:
    """U-09: the sidebar title paints its own chip and stays legible."""

    @pytest.mark.parametrize("theme", ["dark", "light"])
    def test_sidebar_title_chip_and_contrast(self, main_window, apply_theme, theme):
        from gui.agent_tools.ids import find_by_test_id

        apply_theme(theme)
        title = find_by_test_id(main_window, "sidebar.title")
        assert title is not None
        img = _grab(title)
        bg, fg, ratio = _region_contrast(img)
        assert _close(bg, SIDEBAR_CHIPS[theme]), (
            f"sidebar title chip background {bg} != {SIDEBAR_CHIPS[theme]} in {theme} "
            "(the label must paint its own background)"
        )
        assert ratio >= 4.5, f"sidebar title {fg} on {bg} = {ratio:.2f}:1 in {theme}"


class TestAlternatingRows:
    """U-04: alternating tree rows stay legible in both themes."""

    @pytest.mark.parametrize("theme", ["dark", "light"])
    @pytest.mark.parametrize(
        "page_id,test_id",
        [
            ("studies", "page.studies.studiesTree"),
            ("ontology", "page.ontology.ontologyTree"),
        ],
    )
    def test_tree_rows_alternate_with_legible_text(
        self, main_window, apply_theme, theme, page_id, test_id
    ):
        from gui.agent_tools.ids import find_by_test_id

        apply_theme(theme)
        page = _show_page(main_window, page_id)
        tree = find_by_test_id(page, test_id)
        assert tree is not None
        tree.clear()
        columns = tree.columnCount()
        items = []
        for i in range(4):
            values = [f"row_{i:03d} - dummy label for probing"] + ["x"] * (columns - 1)
            items.append(QTreeWidgetItem(tree, values))
        QApplication.processEvents()

        img = _grab(tree.viewport())
        row_bgs = []
        for item in items:
            rect = tree.visualRect(tree.indexFromItem(item))
            assert rect.isValid() and rect.height() > 0
            # Background probe at the row's right edge (no text there).
            p = img.pixelColor(img.width() - 6, rect.center().y())
            row_bgs.append((p.red(), p.green(), p.blue()))
            bg, fg, ratio = _region_contrast(img, rect)
            assert ratio >= 4.5, (
                f"{test_id} {theme} row {item.text(0)!r}: {fg} on {bg} = {ratio:.2f}:1"
            )

        # Consecutive rows genuinely alternate; the pattern repeats.  Solid
        # QSS colors render exactly, so compare exact tuples (the light pair
        # #ffffff/#f7f9fa deliberately differs by only ~8 levels).
        assert row_bgs[0] != row_bgs[1], f"{theme}: rows do not alternate: {row_bgs}"
        assert row_bgs[0] == row_bgs[2], f"{theme}: alternating pattern broken: {row_bgs}"
        assert row_bgs[1] == row_bgs[3], f"{theme}: alternating pattern broken: {row_bgs}"
