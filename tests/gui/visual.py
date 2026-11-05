"""Visual-regression capture/compare helpers (P2-2, Batch C1).

Golden screenshots per (page, theme), compared with a Pillow diff.  The
pinned design lives in ``plans/gui-usability-improvements.md`` (P2-2):

* **Storage:** ``tests/gui/baselines/<page>_<theme>_<platform>.png`` -- one
  baseline per page id x theme, keyed by platform suffix (``windows`` /
  ``linux`` / ``macos``) because offscreen rasterization differs across
  OS/font stacks (the plan's stated flake risk).
* **Capture:** :func:`capture_page` drives the real ``MainWindow`` at a
  pinned window size (1280x800) with the pinned font env (X-2) and grabs
  through :func:`gui.agent_tools.screenshot.gui_screenshot` with a fixed
  ``max_edge``.  The theme is applied *session-only* via
  ``gui_screenshot(theme=...)`` (apply/restore) -- the user's persisted
  ``gui/theme`` is never rewritten (U-06).
* **Compare:** Pillow ``ImageChops.difference`` + ``ImageStat``; a capture
  fails when the differing-pixel ratio exceeds :data:`DIFF_RATIO_MAX` or
  the mean channel delta exceeds :data:`MEAN_DELTA_MAX`.  On failure the
  expected/actual/diff PNGs are written to ``reports/visual_diff/`` (file
  paths only, never base64).
* **Lifecycle:** ``ISA_STEWARD_UPDATE_BASELINES=1`` (re)generates baselines
  and records ``fingerprint_<platform>.json`` (render-scoped environment
  identity: platform + OS build + Qt/PyQt6 + font environment).  A
  comparison runs only where the current environment matches that
  fingerprint -- skip-with-message locally, fail in CI on mismatch;
  ``ISA_STEWARD_VISUAL_STRICT=1`` forces a cross-env comparison
  (:func:`fingerprint_action`).  Baselines are CI-runner-canonical; the
  sanctioned refresh path is the ``visual-baselines`` workflow_dispatch job.

Determinism contract for :func:`capture_page` (why each step exists):

* the ``auto_save_timer`` is stopped -- no ``save_data()`` side effects and
  no transient "Auto-saved" status text (same rule as ``HeadlessGui``);
* ``QApplication.setCursorFlashTime(0)`` + focus clearing -- a blinking
  caret in a focused field would make back-to-back captures differ;
* the status-bar message is normalized to the generic ``View: ...`` line
  navigation sets -- page-specific messages are transient UI state (and the
  ontology page's "No ontology found (searched: ...)" embeds absolute
  machine paths, which would break cross-machine comparisons);
* the window is resized to :data:`WINDOW_SIZE` on every capture;
* **settle sweep:** after navigation the widget tree is force-polished
  (``ensurePolished`` on every widget), nudged through a 1279->1280 resize
  (so ``resizeEvent``-driven sizing like the process page's params-scroll
  formula replays the same event stream in every window), and all layouts
  are activated before grabbing.
* **theme-kick convergence:** applying a stylesheet is a repolish "kick"
  that drives size-feedback loops (page height -> min heights -> sizeHint
  -> page height) to their settled fixed point -- observed: an empty
  ``QListWidget`` on the process page rests at 70px before a repolish kick
  and collapses to 58px after it, shifting everything below by ~12px, and
  that settled state is sticky.  :func:`capture_page` applies the capture
  theme twice with settles before grabbing (``gui_screenshot`` then
  re-applies the same theme -- a further kick on an already-converged,
  sticky state), so the grab never samples the pre-kick layout.
* **grab-until-stable:** a stylesheet apply/relayout can still be settling
  when ``gui_screenshot`` grabs; :func:`capture_page` therefore grabs
  repeatedly until two consecutive captures are pixel-identical
  (:data:`STABLE_GRABS` attempts), so a half-settled layout can never be
  compared.

Thresholds are pinned constants on purpose -- tune them here (and re-read
the plan) rather than per-test.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform as _platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from gui.agent_tools.runtime import ensure_offscreen_fontdir

# X-2: pin the offscreen font env BEFORE any QApplication is constructed
# (the QPA font database reads QT_QPA_FONTDIR once at construction).  Test
# modules are imported at collection time, which precedes the first test's
# QApplication setup, so this module-level call runs early enough.
ensure_offscreen_fontdir()

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from gui.agent_tools.screenshot import _apply_theme, gui_screenshot  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_DIR = Path(__file__).resolve().parent / "baselines"
DIFF_DIR = REPO_ROOT / "reports" / "visual_diff"

#: Env gate that (re)generates baselines instead of comparing (plan P2-2).
UPDATE_ENV = "ISA_STEWARD_UPDATE_BASELINES"

#: Env gate that forces a comparison even when the recorded baseline
#: fingerprint does not match this environment (deliberate cross-env check).
STRICT_ENV = "ISA_STEWARD_VISUAL_STRICT"

#: Schema id of the ``fingerprint_<platform>.json`` sidecar written next to
#: the baseline PNGs (see :func:`env_fingerprint`).
FINGERPRINT_SCHEMA = "isa-gui/baseline-fingerprint/1"

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800
WINDOW_SIZE = (WINDOW_WIDTH, WINDOW_HEIGHT)

#: Fixed capture cap -- 1280x800 never downscales at this value.
MAX_EDGE = 2048

#: How long to pump the event loop after navigation/resize before grabbing.
SETTLE_MS = 80

#: Grab-until-stable attempts per capture (two consecutive identical grabs
#: win early; see the module docstring for why this exists).
STABLE_GRABS = 5

THEMES = ("light", "dark")

#: Canonical page ids (``MainWindow.initialize_pages``).  The meta-test in
#: ``test_visual_regression.py`` fails loudly when this list goes stale.
PAGE_IDS = (
    "dashboard",
    "studies",
    "process_sequence",
    "materials",
    "assays",
    "files",
    "images",
    "ontology",
    "templates",
    "settings",
)

KNOWN_PLATFORMS = ("windows", "linux", "macos")

# Pinned comparison tolerance (plan P2-2 step 2: "fail when differing-pixel
# ratio > threshold (start ~0.5%) or mean channel delta > small epsilon").
#: A pixel counts as differing when any channel delta exceeds this.
PIXEL_DELTA_THRESHOLD = 1
#: Maximum share of differing pixels (0.5%).
DIFF_RATIO_MAX = 0.005
#: Maximum mean absolute channel delta over the whole image.
MEAN_DELTA_MAX = 2.0


# ---------------------------------------------------------------------------
# Environment / naming
# ---------------------------------------------------------------------------


def platform_key() -> str:
    """Platform suffix for baseline names: ``windows`` / ``linux`` / ``macos``."""
    name = _platform.system().lower()
    return "macos" if name == "darwin" else name


def is_update_mode() -> bool:
    """True when ``ISA_STEWARD_UPDATE_BASELINES=1`` (regenerate baselines)."""
    return os.environ.get(UPDATE_ENV, "").strip() == "1"


def in_ci() -> bool:
    """True on GitHub Actions-style runners (``CI`` env truthy)."""
    return os.environ.get("CI", "").strip().lower() in ("1", "true", "yes")


def baseline_name(page_id: str, theme: str) -> str:
    """Baseline stem: ``<page>_<theme>_<platform>`` (plan's platform suffix)."""
    return f"{page_id}_{theme}_{platform_key()}"


def baseline_path(page_id: str, theme: str) -> Path:
    """Path of the baseline PNG for *page_id* x *theme* on this platform."""
    return BASELINE_DIR / f"{baseline_name(page_id, theme)}.png"


def committed_platform_keys() -> set:
    """Platform suffixes that have at least one baseline PNG committed."""
    keys = set()
    if BASELINE_DIR.is_dir():
        for png in BASELINE_DIR.glob("*.png"):
            suffix = png.stem.rsplit("_", 1)[-1]
            if suffix in KNOWN_PLATFORMS:
                keys.add(suffix)
    return keys


def missing_baseline_action() -> str:
    """Policy for a missing baseline (plan P2-2 step 3, per-runner decision).

    * ``"fail"`` -- the platform owns a committed baseline set and we are in
      CI: a page x theme baseline went missing (e.g. a page was added) and
      must fail loudly.
    * ``"skip"`` -- everything else: locally a missing baseline is a skip
      with a clear message; platforms with no committed set at all (e.g.
      linux before someone runs the update flow there) always skip.

    Rationale: baselines can only be captured on machines that run the GUI;
    the windows set is generated on a Windows dev box, so non-owning CI
    legs must not fail on "no baselines for this platform".
    """
    if platform_key() in committed_platform_keys() and in_ci():
        return "fail"
    return "skip"


# ---------------------------------------------------------------------------
# Environment fingerprint (runner-canonical baseline policy)
# ---------------------------------------------------------------------------


def fingerprint_path() -> Path:
    """Sidecar recording where this platform's baseline set was captured."""
    return BASELINE_DIR / f"fingerprint_{platform_key()}.json"


def _fonts_fingerprint() -> Optional[str]:
    """Cheap fingerprint of the pinned offscreen font dir (X-2).

    Names + *sizes* only (no file reads): a font update changes sizes even
    when the file names stay identical -- exactly the runner-image drift that
    changes rasterization.  ``None`` when no font dir is pinned (fontconfig
    environments, where the OS string already separates the worlds).
    """
    fontdir = os.environ.get("QT_QPA_FONTDIR", "").strip()
    if not fontdir or not Path(fontdir).is_dir():
        return None
    entries = []
    with os.scandir(fontdir) as it:
        for entry in it:
            if entry.is_file():
                try:
                    entries.append(f"{entry.name}:{entry.stat().st_size}")
                except OSError:
                    continue
    return hashlib.sha256("\n".join(sorted(entries)).encode("utf-8")).hexdigest()


def env_fingerprint() -> dict:
    """Render-relevant environment identity of the current machine.

    Deliberately render-scoped (platform + OS build + Qt/PyQt6 + font
    environment, NO Python version): the CI matrix runs 3.11 and 3.12 legs
    that share one canonical baseline set, and interpreter versions do not
    affect Qt rasterization.  Recorded next to the baselines in update mode
    so a comparison only runs where it can be meaningful.
    """
    return {
        "schema": FINGERPRINT_SCHEMA,
        "platform": platform_key(),
        "os": _platform.platform(),
        "qt": QT_VERSION_STR,
        "pyqt6": PYQT_VERSION_STR,
        "font_env": {
            "QT_QPA_FONTDIR": os.environ.get("QT_QPA_FONTDIR", ""),
            "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM", ""),
        },
        "fonts_sha256": _fonts_fingerprint(),
    }


def record_fingerprint() -> Path:
    """Write this environment's fingerprint beside the baseline PNGs."""
    path = fingerprint_path()
    path.write_text(
        json.dumps(env_fingerprint(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def load_fingerprint() -> Optional[dict]:
    """Fingerprint recorded for this platform, or ``None`` when absent."""
    path = fingerprint_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def strict_visual() -> bool:
    """True when ``ISA_STEWARD_VISUAL_STRICT=1`` forces cross-env comparison."""
    return os.environ.get(STRICT_ENV, "").strip() == "1"


def fingerprint_action(recorded: Optional[dict]) -> tuple:
    """Policy for comparing baselines captured in a different environment.

    Returns ``(action, reason)``; ``action`` is one of:

    * ``"compare"`` -- the recorded fingerprint matches this environment, or
      ``ISA_STEWARD_VISUAL_STRICT=1`` deliberately forces the comparison.
    * ``"skip"`` -- local run without a matching fingerprint: skip with the
      reason (P2-2 philosophy -- a dev box must not false-alarm red against
      runner-canonical baselines).
    * ``"fail"`` -- CI without a matching fingerprint: fail loudly (CI is the
      meaningful gate; a stale fingerprint means the runner image drifted --
      re-run the ``visual-baselines`` dispatch job and commit the artifact).
    """
    if strict_visual() or recorded == env_fingerprint():
        return "compare", ""
    if recorded is None:
        recorded_txt = "none recorded (set predates fingerprints)"
    else:
        recorded_txt = json.dumps(recorded, sort_keys=True)
    reason = (
        f"baseline fingerprint mismatch for platform {platform_key()!r}:\n"
        f"  recorded: {recorded_txt}\n"
        f"  current:  {json.dumps(env_fingerprint(), sort_keys=True)}\n"
        "baselines are CI-runner-canonical (AGENTS.md sections 9-10): refresh them"
        " with the 'visual-baselines' workflow_dispatch job, download the"
        " visual-baselines-<os> artifact and commit it, or set"
        f" {STRICT_ENV}=1 to force a cross-env comparison."
    )
    if in_ci():
        return "fail", reason
    return "skip", reason


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def process_events(ms: int = SETTLE_MS) -> None:
    """Pump the Qt event loop for roughly *ms* milliseconds."""
    app = QApplication.instance()
    if app is None:
        return
    deadline = time.monotonic() + ms / 1000.0
    while True:
        app.processEvents()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.01, remaining))


def _normalize_status_bar(window, page_id: str) -> None:
    """Force the canonical ``View: ...`` status message before grabbing.

    Page ``on_enter()`` handlers may leave transient messages behind (the
    ontology page renders absolute search paths when no ontology file is
    found); those are UI state, not styling, and would break cross-machine
    pixel comparisons.  The message we pin is the one
    ``MainWindow._navigate_to_page`` itself sets.
    """
    status_bar = getattr(window, "status_bar", None)
    if status_bar is not None:
        status_bar.show_message(f"View: {page_id.replace('_', ' ').title()}")


def _flush_destroyed_widgets() -> None:
    """Deliver pending DeferredDelete events so torn-down windows are freed.

    ``deleteLater()`` objects are destroyed only when their DeferredDelete
    event is delivered, and a bare ``processEvents()`` does not deliver
    those (Qt delivers them on event-loop return).  Without this flush,
    every window torn down earlier in the session stays alive and each
    capture's stylesheet apply/restore re-polishes the whole zombie tree --
    measured +1.6 s per capture per leaked window (quadratic module runs).
    """
    from PyQt6.QtCore import QEvent

    app = QApplication.instance()
    if app is None:
        return
    app.sendPostedEvents(None, int(QEvent.Type.DeferredDelete))
    app.processEvents()


def prepare_window(window) -> None:
    """Put *window* into the pinned, capture-stable state (see module docs)."""
    _flush_destroyed_widgets()
    timer = getattr(window, "auto_save_timer", None)
    if timer is not None:
        timer.stop()
    app = QApplication.instance()
    if app is not None:
        # A blinking caret in a focused field is the classic nondeterminism
        # source in widget grabs; 0 disables cursor flashing entirely.
        app.setCursorFlashTime(0)
        focus = QApplication.focusWidget()
        if focus is not None:
            focus.clearFocus()
    window.resize(*WINDOW_SIZE)
    process_events()


def _force_settled_layout(window) -> None:
    """Force the widget tree into its final, capture-stable layout state.

    Polish every widget (QSS polish changes sizeHints), replay a resize
    nudge so resizeEvent-driven sizing converges identically in every
    window, and activate every layout.  See the module docstring.
    """
    from PyQt6.QtWidgets import QWidget

    widgets = [window, *window.findChildren(QWidget)]
    for widget in widgets:
        widget.ensurePolished()
    window.resize(WINDOW_WIDTH - 1, WINDOW_HEIGHT)
    process_events(20)
    window.resize(*WINDOW_SIZE)
    process_events(20)
    for widget in window.findChildren(QWidget):
        layout = widget.layout()
        if layout is not None:
            layout.activate()
    process_events(SETTLE_MS)


def capture_page(
    window,
    page_id: str,
    theme: str,
    out_dir: Path,
    name: Optional[str] = None,
) -> Path:
    """Capture *page_id* under *theme* and return the written PNG path.

    Uses ``gui_screenshot(theme=...)`` so the theme switch is session-only
    (applied for the grab, previous stylesheet restored afterwards).
    """
    if page_id not in window.pages:
        raise ValueError(f"unknown page {page_id!r}; known: {sorted(window.pages)}")
    prepare_window(window)
    window._navigate_to_page(page_id)
    process_events()
    _normalize_status_bar(window, page_id)
    # Theme-kick convergence (module docstring): each stylesheet apply is a
    # repolish kick that settles the ambiguous size-feedback loops; twice is
    # enough for the settled state to be reached and sticky.
    _apply_theme(theme)
    process_events(SETTLE_MS)
    _apply_theme(theme)
    _force_settled_layout(window)
    stem = name or baseline_name(page_id, theme)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    previous: Optional[bytes] = None
    path: Optional[Path] = None
    for _attempt in range(STABLE_GRABS):
        result = gui_screenshot(
            widget=window,
            out_dir=out_dir,
            name=stem,
            annotate=False,
            max_edge=MAX_EDGE,
            theme=theme,
        )
        path = result.path
        current = _png_pixels(path)
        if current == previous:
            return path
        previous = current
        _apply_theme(theme)
        _force_settled_layout(window)
    raise RuntimeError(
        f"capture_page: {stem!r} did not stabilize within {STABLE_GRABS} grabs;"
        " the layout is still settling at grab time"
    )


def _png_pixels(path: Path) -> bytes:
    """Decoded RGB pixel bytes of a PNG (encoding-independent comparison)."""
    from PIL import Image

    with Image.open(path) as image:
        return image.convert("RGB").tobytes()


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


@dataclass
class CompareResult:
    """Outcome of :func:`compare_images`."""

    ok: bool
    diff_ratio: float
    mean_delta: float
    size_mismatch: bool = False
    expected_size: tuple = (0, 0)
    actual_size: tuple = (0, 0)

    def describe(self, artifacts: Optional[dict] = None) -> str:
        """Human/agent-readable failure summary with artifact paths."""
        if self.size_mismatch:
            head = (
                f"size mismatch: expected {self.expected_size[0]}x{self.expected_size[1]}"
                f" vs actual {self.actual_size[0]}x{self.actual_size[1]}"
            )
        else:
            head = (
                f"{self.diff_ratio * 100:.2f}% pixels differ (max {DIFF_RATIO_MAX * 100:.2f}%),"
                f" mean channel delta {self.mean_delta:.2f} (max {MEAN_DELTA_MAX:.2f})"
            )
        lines = [f"visual regression: {head}"]
        if artifacts:
            for kind in ("expected", "actual", "diff"):
                if kind in artifacts:
                    lines.append(f"  {kind}: {artifacts[kind]}")
            lines.append(
                "If the change is intentional, refresh baselines with"
                f" {UPDATE_ENV}=1 QT_QPA_PLATFORM=offscreen pytest -m gui_visual"
            )
        return "\n".join(lines)


def _max_channel(diff) -> object:
    """Per-pixel max-channel image of a Pillow difference image."""
    from PIL import ImageChops

    r, g, b = diff.convert("RGB").split()
    return ImageChops.lighter(ImageChops.lighter(r, g), b)


def _diff_stats(expected, actual):
    """Return ``(diff_ratio, mean_delta, mask)`` for two RGB images."""
    from PIL import ImageChops, ImageStat

    diff = ImageChops.difference(expected, actual)
    band_means = ImageStat.Stat(diff).mean
    mean_delta = sum(band_means) / len(band_means)
    mask = _max_channel(diff).point(lambda v: 255 if v > PIXEL_DELTA_THRESHOLD else 0)
    total = mask.width * mask.height
    differing = mask.histogram()[255] if total else 0
    diff_ratio = differing / total if total else 0.0
    return diff_ratio, mean_delta, mask


def compare_images(expected_path: Path, actual_path: Path) -> CompareResult:
    """Pillow-diff *actual_path* against *expected_path* (pinned tolerance)."""
    from PIL import Image

    expected = Image.open(expected_path).convert("RGB")
    actual = Image.open(actual_path).convert("RGB")
    if expected.size != actual.size:
        return CompareResult(
            ok=False,
            diff_ratio=1.0,
            mean_delta=float("inf"),
            size_mismatch=True,
            expected_size=expected.size,
            actual_size=actual.size,
        )
    diff_ratio, mean_delta, _mask = _diff_stats(expected, actual)
    ok = diff_ratio <= DIFF_RATIO_MAX and mean_delta <= MEAN_DELTA_MAX
    return CompareResult(
        ok=ok,
        diff_ratio=diff_ratio,
        mean_delta=mean_delta,
        expected_size=expected.size,
        actual_size=actual.size,
    )


def write_diff_artifacts(name: str, expected_path: Path, actual_path: Path) -> dict:
    """Write ``<name>.expected/.actual/.diff.png`` into ``reports/visual_diff/``.

    The diff image is a red-highlight view (differing pixels in red over the
    dimmed actual capture) for agent/vision review.  Returns the written
    paths keyed ``expected`` / ``actual`` / ``diff`` (``diff`` omitted on a
    size mismatch, where the two captures are not comparable pixel-wise).
    """
    from PIL import Image, ImageEnhance

    DIFF_DIR.mkdir(parents=True, exist_ok=True)
    expected = Image.open(expected_path).convert("RGB")
    actual = Image.open(actual_path).convert("RGB")

    artifacts = {}
    exp_out = DIFF_DIR / f"{name}.expected.png"
    act_out = DIFF_DIR / f"{name}.actual.png"
    expected.save(exp_out)
    actual.save(act_out)
    artifacts["expected"] = exp_out
    artifacts["actual"] = act_out

    if expected.size == actual.size:
        _diff_ratio, _mean_delta, mask = _diff_stats(expected, actual)
        base = ImageEnhance.Brightness(actual).enhance(0.35)
        red = Image.new("RGB", actual.size, (255, 0, 0))
        diff_out = DIFF_DIR / f"{name}.diff.png"
        Image.composite(red, base, mask).save(diff_out)
        artifacts["diff"] = diff_out
    return artifacts


def clear_diff_artifacts() -> None:
    """Remove stale ``reports/visual_diff/`` PNGs (used before fresh runs)."""
    if DIFF_DIR.is_dir():
        for png in DIFF_DIR.glob("*.png"):
            png.unlink()
