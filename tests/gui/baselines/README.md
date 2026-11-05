# Visual-regression baselines (P2-2)

Golden screenshots for [`tests/gui/test_visual_regression.py`](../test_visual_regression.py)
(visual.py helpers and pinned tolerances live in [`tests/gui/visual.py`](../visual.py)).

- **Layout:** `<page>_<theme>_<platform>.png` — one PNG per page id × theme,
  keyed by platform suffix (`windows` / `linux` / `macos`) because offscreen
  rasterization differs across OS/font stacks. Each committed platform set
  also carries an environment fingerprint sidecar `fingerprint_<platform>.json`
  (render-scoped identity: platform + OS build + Qt/PyQt6 version + font
  environment, schema `isa-gui/baseline-fingerprint/1`) recording **where** the
  set was captured.
- **Capture:** the full `MainWindow` at a pinned 1280×800, offscreen
  (`QT_QPA_PLATFORM=offscreen`), both themes (`light`, `dark`), via
  `gui_screenshot(theme=…)` (session-only — never persists the user's theme).
- **Compare:** Pillow `ImageChops.difference` + `ImageStat`; fail when the
  differing-pixel ratio > 0.5% or the mean channel delta > 2.0. On failure
  the expected/actual/diff PNGs are written to `reports/visual_diff/`.
- **Fingerprint policy:** a comparison runs only when the current environment
  matches the recorded fingerprint. On a **recorded** mismatch: **skip with
  a message locally** (a dev box must not false-alarm red against
  runner-canonical baselines) and **fail in CI** (the meaningful gate — a
  stale fingerprint means the runner image drifted). A set with **no
  recorded fingerprint** (the documented transitional state for sets that
  predate the sidecar) gets full **legacy amnesty**: the comparison is
  **skipped everywhere, CI included**, with a message naming the canonical
  refresh below — "missing"-style fail-in-CI semantics would keep CI red
  until that one-time manual step, which is exactly what the amnesty
  defers. The refresh attaches `fingerprint_<os>.json` and activates the
  strict recorded-mismatch behavior above. `ISA_STEWARD_VISUAL_STRICT=1`
  forces the comparison anyway (deliberate cross-env check). Missing
  baseline PNGs keep the plan's policy: skip locally, fail in CI on a
  platform that owns a committed set.

## Canonical refresh (CI-runner baselines) — the sanctioned path

Baselines are canonical when captured **on the CI runners**; runner font
rasterization differs from dev boxes (the plan's documented risk), so
regenerating on a runner is the legitimate answer to runner-side diffs:

1. GitHub → **Actions** → **Test Suite** → **Run workflow** (`workflow_dispatch`).
   The `visual-baselines` job runs
   `ISA_STEWARD_UPDATE_BASELINES=1 pytest tests/gui/test_visual_regression.py -m gui_visual`
   on `ubuntu-latest` and `windows-latest` and uploads `tests/gui/baselines/`
   as the `visual-baselines-<os>` artifact (PNGs + `fingerprint_<os>.json`).
2. Download the artifact(s), **review the PNGs** (AGENTS.md §11: never commit
   an unexplained diff), and commit the platform-keyed files:
   `*_windows.png` + `fingerprint_windows.json` from the windows artifact,
   `*_linux.png` + `fingerprint_linux.json` from the ubuntu one.
3. CI now compares strictly (its env matches the recorded fingerprint); local
   runs skip against the runner-canonical set unless `ISA_STEWARD_VISUAL_STRICT=1`.

## Local refresh (iteration only — NOT canonical)

```bash
ISA_STEWARD_UPDATE_BASELINES=1 QT_QPA_PLATFORM=offscreen pytest -m gui_visual
```

This writes local PNGs **and** `fingerprint_<platform>.json` for the local
environment (subsequent local runs compare and stay self-consistent). **Do not
commit locally regenerated PNGs as the canonical set** — pass them through the
`visual-baselines` dispatch job instead.

Re-baseline after **intentional** styling/layout changes (QSS edits, widget
geometry, page layout) — never to silence an unexplained diff.

Platform gating note: runners without a committed platform set skip the
comparisons entirely (e.g. the linux CI leg skips the 20
`test_page_matches_baseline` params while the windows leg runs them) — the
per-job skip-count delta is this by design.
