"""Visual-regression baseline tests (P2-2, Batch C1).

Compare every page x theme capture against the platform-keyed golden PNGs
in ``tests/gui/baselines/`` (helpers and the pinned tolerance live in
``tests/gui/visual.py``; the design is ``plans/gui-usability-improvements.md``
P2-2).

Run/refresh (bare after E-1)::

    QT_QPA_PLATFORM=offscreen pytest -m gui_visual
    ISA_STEWARD_UPDATE_BASELINES=1 QT_QPA_PLATFORM=offscreen pytest -m gui_visual

On failure the expected/actual/diff PNGs are written to
``reports/visual_diff/`` for agent/vision review.

Comparisons only run in the environment the baselines were captured in
(``fingerprint_<platform>.json``, see ``tests/gui/visual.py``): a recorded
mismatch skips locally and fails in CI, while a legacy set with no recorded
fingerprint (the documented pre-fingerprint transitional state) is skipped
everywhere under the legacy amnesty
(``ISA_STEWARD_VISUAL_STRICT=1`` forces a cross-env comparison).
Canonical baselines are captured ON the CI runners via the
``visual-baselines`` workflow_dispatch job -- see
``tests/gui/baselines/README.md`` for the refresh flow.
"""

import os

import pytest

pytestmark = [pytest.mark.gui, pytest.mark.gui_visual]

# Baselines are captured with the offscreen platform (deterministic
# rasterization); a windowed run would compare against PNGs it cannot
# reproduce, so skip it with a clear message instead of failing.
if os.environ.get("QT_QPA_PLATFORM", "").strip() != "offscreen":
    pytest.skip(
        "visual baselines require QT_QPA_PLATFORM=offscreen",
        allow_module_level=True,
    )

try:
    from .visual import (
        BASELINE_DIR,
        PAGE_IDS,
        THEMES,
        UPDATE_ENV,
        baseline_name,
        baseline_path,
        capture_page,
        committed_platform_keys,
        compare_images,
        fingerprint_action,
        is_update_mode,
        load_fingerprint,
        missing_baseline_action,
        platform_key,
        record_fingerprint,
        write_diff_artifacts,
    )
except ImportError:  # pragma: no cover - PyQt6/Pillow absent
    pytest.skip("PyQt6/Pillow not available", allow_module_level=True)


@pytest.mark.parametrize("theme", THEMES, ids=list(THEMES))
@pytest.mark.parametrize("page_id", PAGE_IDS)
def test_page_matches_baseline(page_id, theme, main_window, tmp_path):
    """Every page x theme capture matches its platform baseline (P2-2)."""
    name = baseline_name(page_id, theme)

    if is_update_mode():
        written = capture_page(main_window, page_id, theme, BASELINE_DIR, name=name)
        assert written.is_file(), f"update mode failed to write {written}"
        # Record the capturing environment beside the PNGs so comparisons
        # only run where they can be meaningful (runner-canonical policy).
        record_fingerprint()
        return

    expected = baseline_path(page_id, theme)
    if not expected.is_file():
        if missing_baseline_action() == "fail":
            pytest.fail(
                f"missing baseline {expected.name} for platform {platform_key()!r} in CI;"
                f" regenerate with {UPDATE_ENV}=1 QT_QPA_PLATFORM=offscreen pytest -m gui_visual"
                " and commit tests/gui/baselines/"
            )
        pytest.skip(
            f"missing baseline {expected.name}; capture it once with"
            f" {UPDATE_ENV}=1 QT_QPA_PLATFORM=offscreen pytest -m gui_visual"
        )

    action, reason = fingerprint_action(load_fingerprint())
    if action == "skip":
        pytest.skip(reason)
    if action == "fail":
        pytest.fail(reason)

    actual = capture_page(main_window, page_id, theme, tmp_path, name=name)
    result = compare_images(expected, actual)
    if not result.ok:
        artifacts = write_diff_artifacts(name, expected, actual)
        pytest.fail(result.describe(artifacts))


def test_consecutive_captures_within_threshold(main_window, tmp_path):
    """Flakiness guard (P2-2 acceptance 3): two captures of the same
    page x theme on one machine stay within the pinned threshold."""
    for page_id in PAGE_IDS:
        for theme in THEMES:
            first = capture_page(
                main_window, page_id, theme, tmp_path, name=f"{page_id}_{theme}_first"
            )
            second = capture_page(
                main_window, page_id, theme, tmp_path, name=f"{page_id}_{theme}_second"
            )
            result = compare_images(first, second)
            if not result.ok:
                artifacts = write_diff_artifacts(f"{page_id}_{theme}_flake", first, second)
                pytest.fail(
                    f"nondeterministic capture for {page_id}/{theme}:"
                    f" {result.describe(artifacts)}"
                )


def test_baseline_inventory(main_window):
    """Meta-test: every page id x theme has a baseline in each committed
    platform set -- fails loudly when a page is added or renamed."""
    if is_update_mode():
        pytest.skip(f"{UPDATE_ENV}=1: baselines are being regenerated")

    pages = set(main_window.pages)
    assert pages == set(PAGE_IDS), (
        "PAGE_IDS in tests/gui/visual.py is stale;"
        f" MainWindow pages are {sorted(pages)}; update PAGE_IDS and"
        f" regenerate baselines with {UPDATE_ENV}=1"
    )

    keys = committed_platform_keys()
    assert keys, (
        "no baselines committed under tests/gui/baselines/;"
        f" capture them with {UPDATE_ENV}=1 QT_QPA_PLATFORM=offscreen pytest -m gui_visual"
    )

    missing = [
        f"{page_id}_{theme}_{key}.png"
        for key in sorted(keys)
        for page_id in PAGE_IDS
        for theme in THEMES
        if not (BASELINE_DIR / f"{page_id}_{theme}_{key}.png").is_file()
    ]
    assert not missing, f"missing baseline(s) for committed platform set(s): {missing}"
