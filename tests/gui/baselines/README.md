# Visual-regression baselines (P2-2)

Golden screenshots for [`tests/gui/test_visual_regression.py`](../test_visual_regression.py)
(visual.py helpers and pinned tolerances live in [`tests/gui/visual.py`](../visual.py)).

- **Layout:** `<page>_<theme>_<platform>.png` — one PNG per page id × theme,
  keyed by platform suffix (`windows` / `linux` / `macos`) because offscreen
  rasterization differs across OS/font stacks.
- **Capture:** the full `MainWindow` at a pinned 1280×800, offscreen
  (`QT_QPA_PLATFORM=offscreen`), both themes (`light`, `dark`), via
  `gui_screenshot(theme=…)` (session-only — never persists the user's theme).
- **Compare:** Pillow `ImageChops.difference` + `ImageStat`; fail when the
  differing-pixel ratio > 0.5% or the mean channel delta > 2.0. On failure
  the expected/actual/diff PNGs are written to `reports/visual_diff/`.
- **Regenerate** (then review and commit the PNGs):

  ```bash
  ISA_STEWARD_UPDATE_BASELINES=1 QT_QPA_PLATFORM=offscreen pytest -m gui_visual
  ```

Re-baseline after **intentional** styling/layout changes (QSS edits, widget
geometry, page layout) — never to silence an unexplained diff. CI runners
can regenerate their own set via the `visual-baselines` workflow job
(manual dispatch); see `AGENTS.md` sections 9–10.
