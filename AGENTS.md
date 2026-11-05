# AGENTS.md — isa-json-steward

Guidance for AI coding agents working on this repository. GUI-specific
detail lives in [`gui/AGENTS.md`](gui/AGENTS.md). The authoritative design
spec for agent tooling is
[`plans/agent-gui-observability.md`](plans/agent-gui-observability.md).

## 1. Project at a glance

ISA-JSON Data Steward: a PyQt6 desktop application plus a batch toolkit for
managing ISA-JSON investigation metadata (investigations → studies →
materials / assays / files / images / process sequences), with ontology
verification and SHACL-based validation. Entry points: `isa-json-steward-gui`
(`gui.main:main`) and `isa-json-steward-batch`
(`utils.batch.batch_processor:main`).

## 2. Repository map

| Path | Contents |
|------|----------|
| `gui/` | PyQt6 app: `app.py` (StewardApp), `main_window.py`, `pages/` (10), `dialogs/` (10), `widgets/`, `resources/styles/*.qss`, `agent_tools/` (agent observability toolkit) |
| `utils/` | Core logic: config, directory/file management, ISA-JSON export/validation, ontology, templates |
| `utils/batch/` | The shared 7-stage batch pipeline (also driven from the GUI) |
| `tests/` | pytest suite; GUI tests in `tests/gui/` |
| `config/` | JSON configuration (settings, assay types, people, profile, …) |
| `docs/` | Setup and user workflow guides |
| `plans/` | Design specs (`agent-gui-observability.md`) |
| `reports/` | Agent-tool output: widget-tree dumps, screenshots, event logs (gitignored) |

## 3. Commands

```bash
# Install (dev tooling + the mcp SDK for the MCP server)
pip install -e ".[dev,agent]"

# GUI tests, headless (bare works — no -o addopts= needed since E-1)
QT_QPA_PLATFORM=offscreen pytest -m gui

# Visual-regression baselines (P2-2; compare, then regenerate — section 10)
QT_QPA_PLATFORM=offscreen pytest -m gui_visual
ISA_STEWARD_UPDATE_BASELINES=1 QT_QPA_PLATFORM=offscreen pytest -m gui_visual

# Full suite (serial — bare works everywhere)
pytest tests/

# Full suite, parallel — recommended (pytest-xdist dev extra; ~2.5 min vs
# ~5 min serial). --dist loadfile keeps each test module on ONE worker
# (GUI/QSettings isolation + visual-module determinism); never drop it.
QT_QPA_PLATFORM=offscreen pytest tests/ -n auto --dist loadfile

# Agent observability CLI (JSON on stdout; artifacts under reports/)
python -m gui.agent_tools pages
python -m gui.agent_tools dump [--page PAGE] [--widget TEST_ID] [--text] [--out PATH]
python -m gui.agent_tools screenshot [--page PAGE] [--widget TEST_ID] [--annotate] [--theme light|dark] [--out DIR]
python -m gui.agent_tools click TEST_ID
python -m gui.agent_tools set-text TEST_ID VALUE
python -m gui.agent_tools get-state TEST_ID

# Stdio MCP server (long-lived offscreen GUI; see section 8)
python -m gui.agent_tools mcp-serve
```

Coverage is not gated in [`pytest.ini`](pytest.ini) `addopts` (E-1): the
`--cov=utils --cov-fail-under=60` gate runs only in CI
([`.github/workflows/test.yml`](.github/workflows/test.yml)), so bare runs —
including `QT_QPA_PLATFORM=offscreen pytest -m gui` — work without
`pytest-cov` installed.

All `gui.agent_tools` commands boot the real GUI offscreen
(`QT_QPA_PLATFORM=offscreen` is applied automatically unless already set),
perform one action, print one JSON object, and exit. Success is
`{"ok": true, ...}` with artifact **paths** (never base64); failure is
`{"ok": false, "error": ..., "known_ids": [...]}` with exit code 1.

## 4. GUI architecture

`StewardApp` (QApplication subclass, [`gui/app.py`](gui/app.py)) →
`MainWindow` ([`gui/main_window.py`](gui/main_window.py)) → `Sidebar` +
`QStackedWidget` (objectName `contentArea`) + `StatusBar`.

- 10 pages in `gui/pages/` registered in `MainWindow.initialize_pages()`
  under keys `dashboard, studies, process_sequence, materials, assays, files,
  images, ontology, templates, settings` (`MainWindow.pages`).
- 10 dialogs in `gui/dialogs/`, opened on demand from pages.
- Navigation: `Sidebar.navigationRequested(str)` signal →
  `MainWindow._navigate_to_page()`.
- Page lifecycle hooks on `BasePage`/`ScrollablePage`
  ([`gui/pages/base_page.py`](gui/pages/base_page.py)): `on_enter()`,
  `on_exit()`, `refresh()`, `validate_data()`, `save_data()`.
- `BasePage.dataChanged` signal → auto-save timer (`_auto_save`).

## 5. Widget ID convention

Interactive widgets carry a unique `testId` Qt dynamic property (set via
[`set_test_id()`](gui/agent_tools/ids.py)), which also fills an **empty**
`accessibleName` — `set_test_id()` **never overwrites a deliberate name**
(a pre-set name, or an earlier `accessible_name=`, always wins). Since P2-3
the convention is to pass human `accessible_name=` text at every creation
site, so the raw-testId fill only survives as a last-resort fallback (the
P2-3 enforcement tests reject it on tagged widgets). **`objectName` values
are NEVER renamed** — they are the QSS style keys (`#sidebar`,
`#sidebarTitle`, `#sidebarButton`, `#contentArea`, `#contentPage`, `#card`,
`#formLabel`, `#primaryButton`, `#dangerButton`).

Grammar (section 2.1 of the design plan):

```
testId  := <scope>.<qualifier>.<name>     # exactly 2 or 3 dot-separated segments
scope   := window | sidebar | statusBar | page | dialog | widget
name    := lowerCamelCase role noun (saveButton, nameField, materialsTable, ...)
```

Examples: `page.materials.saveButton`, `page.process_sequence.runButton`,
`dialog.studyWizard.nextButton`, `sidebar.navButton.materials`,
`window.main.contentStack`, `statusBar.messageLabel`.

Accessibility convention (P2-3, `plans/gui-usability-improvements.md`):

- Pass `accessible_name="Save settings"` (sentence-case human phrase —
  **never** the raw `testId`) to `set_test_id()` / the `test_id=`-kwargs of
  [`gui/widgets/common.py`](gui/widgets/common.py) at every interactive
  widget's creation site.
- Ambiguous multi-field form fields also get
  `setAccessibleDescription(...)` at the creation site (e.g. the
  [`gui/pages/settings.py`](gui/pages/settings.py) and
  [`gui/dialogs/assay_dialog.py`](gui/dialogs/assay_dialog.py) forms);
  existing tooltips can seed descriptions (copy, never rewrite the tooltip).
- Enforcement lives in
  [`tests/gui/test_agent_ids.py`](tests/gui/test_agent_ids.py)
  (`TestAccessibleNameCoverage`, `TestAccessibleDescriptions`): every tagged
  widget's name must be non-empty, differ from its `testId`, and not be
  `testId`-shaped.

Rules of thumb:

- Set IDs **at widget creation sites** in `gui/main_window.py`,
  `gui/widgets/sidebar.py`, `gui/pages/*.py`, `gui/dialogs/*.py`; common
  leaf widgets accept a `test_id=` kwarg (and `accessible_name=`)
  ([`gui/widgets/common.py`](gui/widgets/common.py)).
- Reusable composite widgets from `gui/widgets/` (PathPicker,
  CollapsibleGroupBox, GraphWidget, FileAttachmentWidget, …) do **not** tag
  their internals — address the container from its creating page/dialog.
- Dialogs use `<dialogClass>` minus a trailing `Dialog`, lowerCamelCased:
  `dialog.assay.*`, `dialog.material.*`, `dialog.studyWizard.*`.
- Dynamic rows use an index suffix, e.g.
  `dialog.assay.valueField_0`, `page.process_sequence.parameterValueField_0`.
- Never reuse a `testId`; `find_by_test_id()` raises `WidgetIdError` on
  duplicates.

## 6. Observability toolkit (`gui/agent_tools/`)

| API | Purpose |
|-----|---------|
| [`dump_widget_tree()`](gui/agent_tools/dump.py) | Widget tree as JSON (schema `isa-gui/widget-tree/1`) with global geometry, dynamic properties, plus `widget_tree_to_text()` for an LLM-friendly rendering |
| [`gui_screenshot()`](gui/agent_tools/screenshot.py) | `QWidget.grab()` capture to `reports/*.png`, longest edge downscaled to ≤2048 px via Pillow; `annotate=True` adds the set-of-marks overlay |
| [`annotate.py`](gui/agent_tools/annotate.py) | Set-of-marks (P1-2): numbered badges + right-side legend panel (`"#1  page.materials.saveButton  —  Save"`) and a `<name>.legend.json` sidecar next to the PNG |
| [`events.py`](gui/agent_tools/events.py) | JSONL GUI-event stream (schema `isa-gui/event/1`) with a 500-event ring buffer for crash bundles |
| [`crash.py`](gui/agent_tools/crash.py) | Crash bundles + `sys`/`threading` excepthooks + `StewardNotifyMixin` |
| [`HeadlessGui`](gui/agent_tools/runtime.py) | Boot/drive/tear-down the GUI offscreen: `navigate`, `find`, `click`, `set_text`, `get_state`, `dump`, `screenshot` |
| [`mcp_server.py`](gui/agent_tools/mcp_server.py) | P2-1 stdio MCP server (FastMCP) over one long-lived `HeadlessGui` |
| [`python -m gui.agent_tools`](gui/agent_tools/cli.py) | One-shot CLI over the above + `mcp-serve` |

Artifacts land in `reports/` (gitignored). Annotated captures pair every PNG
with a `.legend.json` sidecar so badge→testId ground truth never depends on
OCR.

Dump geometry rule (N5): hidden nodes (`visible: false`) report a **zeroed**
`geometry` rect (`{"x": 0, "y": 0, "width": 0, "height": 0}`) — stale-rect
normalization (hidden widgets are skipped by layouts and can keep leftover
rects from earlier layout passes). Schema keys/types are unchanged; only
hidden nodes' geometry values differ. Legend sidecars are unaffected (marks
are computed from live widgets and already drop hidden/empty-geometry ones).

Annotate clip-drop (U-15a): annotated captures **drop** (never shrink) marks
whose widgets are clipped by the captured root or an ancestor scroll
viewport — below-fold widgets get no badge
([`collect_marks()`](gui/agent_tools/annotate.py); full note in the
[`annotate.py`](gui/agent_tools/annotate.py) module docstring). Badge numbers
follow the surviving DFS order and shift when fold positions change;
`<name>.legend.json` stays the badge→testId ground truth, so sweep consumers
must re-baseline legends when fold positions change.

Legend label sourcing (P2-3): `Mark.label` (the `{index, test_id, rect,
label}` sidecar field) reads the widget text, falling back to
`accessibleName`, then the class name. Since the P2-3 accessibility rollout
fills `accessibleName` with human names, legend **labels for text-less
widgets** (line edits, combos, trees) now read as human phrases instead of
raw testIds — sidecar schema is unchanged; only label text differs.

## 7. Crash & event artifacts

**Status: implemented (P1-1).** Installed by `gui/main.py` at startup and by
`HeadlessGui.start()` for every CLI/MCP agent session
(`setup_gui_event_log()` → `install_event_filter(app)` →
`install_crash_hooks(app)`); cheap and non-blocking. Set
`ISA_STEWARD_AGENT_DIAGNOSTICS=0` to skip the install entirely (opt-out).

Crash bundles are written to `crash_reports/<YYYYmmdd-HHMMSS-fff>/`
(collision-suffixed, gitignored) containing:

| File | Content |
|------|---------|
| `exception.txt` / `exception.json` | formatted traceback; `{type, message, thread, fatal}` |
| `widget_tree.json` / `widget_tree.txt` | `dump_widget_tree()` of the active window |
| `screenshot.png` | `gui_screenshot()` of the active window (grab only — the window is never closed, so no `closeEvent` modal path can trigger) |
| `events.jsonl` | ring-buffer tail (last 500 GUI events) |
| `meta.json` | python/Qt/PyQt versions, platform, `QT_QPA_PLATFORM`, theme, current page, `sys.argv`, cwd, hook context, artifact errors |

`fatal: false` marks exceptions raised during Qt event dispatch (slot /
event-handler / timer code): with the hooks installed the GUI survives them
(PyQt6 would otherwise `qFatal`-abort). `fatal: true` marks top-level
interpreter and `threading.excepthook` crashes. Thread-crash bundles skip
`widget_tree.*`/`screenshot.png` (widget access is GUI-thread-only). Hazard:
destroying a `QThread` whose `run()` aborted on a Python exception can
access-violate at process shutdown — catch exceptions inside `run()`.

GUI events are appended as JSONL (schema `isa-gui/event/1`) to
`reports/gui_events.jsonl` (path overridable via env
`ISA_STEWARD_GUI_EVENTS`):

```json
{"ts": "2026-11-02T20:48:50.769Z", "seq": 1234, "session": "<uuid4>",
 "kind": "gui_event", "event": "click", "test_id": "page.materials.saveButton",
 "class": "PrimaryButton", "object_name": "primaryButton", "page": "materials",
 "detail": {"text": "Save"}}
```

- `kind` ∈ `gui_event | log | crash | state`; `event` ∈ `click |
  text_changed | toggled | navigate | page_enter | page_exit | data_changed |
  error | crash`, plus `key_press`/`focus_in` rows from the event filter.
- Capture points: the application-level event filter (`install_event_filter`)
  on tagged widgets, explicit `log_gui_event()` calls in
  `MainWindow._navigate_to_page()` / `_on_page_data_changed()` and in
  `HeadlessGui` synthetic actions, and WARNING+ log records forwarded as
  `kind: "log"` rows via `utils.logging_config.JsonlEventHandler`
  (`setup_gui_event_log()`).

**Settings write contract (U-02).** The product no longer rewrites
[`config/settings.json`](config/settings.json) on close:
[`SettingsPage.save_data()`](gui/pages/settings.py) is a **no-op** and
settings persist **only** via the explicit Save button
([`_on_save_settings()`](gui/pages/settings.py)), which honors
`ISA_STEWARD_CONFIG_PATH` (the config path is injectable per call) and
refuses to write while the `_config_load_failed` guard is set (a Save backed
by a failed load would wipe unmanaged sections). `MainWindow.closeEvent` can
still open a modal (`QMessageBox.question` on validation errors), so tooling
that must never block **hides** instead of closing the window and harness
teardown navigates back to the dashboard before close
([`tests/gui/conftest.py`](tests/gui/conftest.py)) — **defense-in-depth**
against the modal path, not protection from a live rewrite. The "never
`close()`" practice stays as a recommendation.

**Teardown hazards (N9) — probe-only.** Two `MainWindow` lifecycles in one
process, or a bare `python -c` teardown with diagnostics disabled
(`ISA_STEWARD_AGENT_DIAGNOSTICS=0`), can access-violate (`0xC0000005`) at
interpreter exit. Not reachable via the product entry points
([`gui/main.py`](gui/main.py), the CLI, the MCP server). Probe rules:
(a) run **one** `MainWindow` lifecycle per probe process; (b) a `0xC0000005`
*after* a successful JSON result during probe teardown is a known
artifact-class crash, not a product bug; (c) keep
`ISA_STEWARD_AGENT_DIAGNOSTICS` on in probes.
[`HeadlessGui.shutdown()`](gui/agent_tools/runtime.py) is idempotent
(double-`shutdown()` is a no-op) — the crash is Qt teardown at interpreter
exit, not the shutdown call itself.

Ignore `reports/` and `crash_reports/`; never commit their contents.

## 8. MCP tools

**Status: implemented (P2-1).** A stdio MCP server exposes the observability
toolkit against ONE long-lived offscreen [`HeadlessGui`](gui/agent_tools/runtime.py)
(created lazily on the first tool call, pumped with `processEvents` between
calls). Start it with:

```bash
pip install -e ".[agent]"        # installs the mcp SDK (1.x FastMCP line)
python -m gui.agent_tools mcp-serve
```

It is registered for zoo code in [`.mcp.json`](.mcp.json) (server name
`isa-gui`). Implementation: [`gui/agent_tools/mcp_server.py`](gui/agent_tools/mcp_server.py).

### 8.1 Tool surface (exactly 7 tools)

| Tool | Parameters | Returns (JSON string) |
|------|-----------|----------------------|
| `dump_widget_tree` | `test_id: str = null`, `as_text: bool = true` | LLM text form (default) or `{"tree": ...}` (schema `isa-gui/widget-tree/1`) |
| `screenshot` | `test_id: str = null`, `annotate: bool = true`, `theme: str = null`, `max_edge: int = 2048` | `{"path", "width", "height", "legend": [{index, test_id, label}], "legend_path"}` |
| `navigate` | `page_id: str` | `{"ok": true, "page": "materials"}` |
| `click_widget` | `test_id: str` | `{"ok": true, "clicked": "..."}` |
| `set_text` | `test_id: str`, `value: str` | `{"ok": true}` |
| `get_state` | `test_id: str` | `{"text", "checked", "enabled", "visible", "value"}` |
| `run_gui_test` | `pattern: str` | `{"returncode", "passed", "failed", "skipped", "output_tail"}` (runs `python -m pytest tests/gui -k <pattern> -q` offscreen) |

Errors return `{"ok": false, "error": "WidgetIdError: unknown id ...",
"known_ids": [...]}` — never raw tracebacks (those land in `crash_reports/`
bundles). All outputs are **file paths**, never base64.

Behavior notes:

- `screenshot(theme=...)` is **session-only**: the theme QSS is applied for
  the capture and the previous stylesheet is restored afterwards; the user's
  persisted `gui/theme` (QSettings) is never rewritten. `theme=null` keeps
  the application's current theme (prefer `light` for text-heavy review).
  The session default is `theme=None` — agent boots never force a theme
  (`StewardApp.apply_theme(theme, persist=False)` is the non-persisting
  path; only the settings-page combo persists via `set_theme()`).
- `HeadlessGui.start()` runs profile auto-discovery before creating the
  application (U-05): the `profile=` kwarg, then `ISA_STEWARD_PROFILE`, then
  `*-profile/` in the repo root (`utils.config_loader.discover_profile_dir`);
  the settings-page theme combo remains the only persisting theme caller.
- The runtime stops `MainWindow.auto_save_timer` so tool calls never trigger
  `save_data()` side effects. Exercise persistence explicitly by clicking a
  page's `saveButton` — settings persist **only** via the explicit Save
  button ([`SettingsPage.save_data()`](gui/pages/settings.py) is a no-op,
  U-02; section 7).
- Tool handlers never `close()` the window; teardown hides it
  (defense-in-depth against the `closeEvent` modal path — the
  `config/settings.json` rewrite half of the old hazard is gone since U-02,
  section 7).
- Boots are write-free (N6): the template index is built in-memory; writing
  `template_index.json`/`template_list.txt` into the active profile is
  opt-in via `ISA_STEWARD_TEMPLATE_INDEX_WRITE=1`.
- `click_widget` on a button that opens a **modal dialog** blocks until the
  dialog is closed — drive dialog flows from pytest-qt (section 9) instead.
- The server pre-imports the GUI modules at startup (a lazy first-call import
  of the `gui.main_window` chain can deadlock its native `numpy` init inside
  the stdio runtime on Windows); the window itself still boots lazily on the
  first tool call.

### 8.2 MCP vs CLI vs pytest

| Need | Use |
|------|-----|
| Rapid inspect/drive loop, vision review | MCP: `navigate` → `screenshot` + `dump_widget_tree` → `click_widget`/`set_text`/`get_state` |
| One-shot scripted checks, CI, shell pipelines | CLI `python -m gui.agent_tools ...` |
| Behavioral assertions, modal dialogs, signals, regressions | pytest-qt (`tests/gui/`, `-m gui`) — modals/dialogs are only safe here |

The MCP tools and the CLI wrap the same [`HeadlessGui`](gui/agent_tools/runtime.py)
API, so tool names/`testId`s are interchangeable between the two.

### 8.3 Registration & other zoo-code config formats

[`.mcp.json`](.mcp.json) (repo root, the de-facto standard read by
Codex/Cursor/Copilot-style tools) registers the server with the invariant
contract: **stdio transport, command `python -m gui.agent_tools mcp-serve`,
env `QT_QPA_PLATFORM=offscreen`, cwd = repo root.** Zoo code's own
configuration may use a different shape (e.g. an `mcp_servers` map in its
settings file, or `command`/`args` as a single shell string) — whatever the
format, register those four facts. Verify with the MCP `tools/list` call
returning exactly the 7 tools of section 8.1.

## 9. Testing conventions

- Markers (see [`pytest.ini`](pytest.ini)): `gui`, `gui_widget`, `gui_page`,
  `gui_dialog`, `gui_workflow`, `gui_visual`, plus `unit`, `integration`,
  `e2e`, `slow`, `batch*`, `security`, `file_ops`, `isa_validation`,
  `requires_data`.
- GUI tests must pass headless: `QT_QPA_PLATFORM=offscreen pytest -m gui`.
- `pytest-qt` is a declared dev extra; `qtbot` comes from the plugin.
  `pytest-xdist` is also a dev extra: the recommended full-suite form is
  `QT_QPA_PLATFORM=offscreen pytest tests/ -n auto --dist loadfile`
  (`--dist loadfile` keeps every test module in a single worker — required
  for GUI/QApplication isolation and the visual module's determinism;
  serial runs stay supported and are what the MCP `run_gui_test` tool uses).
- Zombie-widget guard: the autouse `_zombie_widget_guard` fixture in
  [`tests/gui/conftest.py`](tests/gui/conftest.py) flushes `DeferredDelete`
  events before/after every GUI test. pytest-qt's teardown only calls
  `close()` + `deleteLater()` and a plain `processEvents()` does not deliver
  deferred deletes — without the flush each test's window survives as a
  zombie and later `setStyleSheet`/`MainWindow` boots re-polish a growing
  widget tree (per-test setup grew to 20s+ in-suite; the guard keeps boots at
  ~0.15-0.3s). Custom teardown that calls `deleteLater()` is covered too;
  explicit flushes (as in [`tests/gui/test_agent_ids.py`](tests/gui/test_agent_ids.py))
  remain harmless.
- Measured timings (Windows dev box, 2026-11): full suite 15:13 serial →
  7:43 serial with the zombie guard → 2:31 with `-n auto --dist loadfile`
  (run twice, stable); GUI suite (`-m gui`) 14:21 → 4:48 with the guard
  alone. Remaining critical path: `test_consecutive_captures_within_threshold`
  (~2 min, 40 convergent captures — coverage, do not shrink) and the 22
  `gui_visual` baseline comparisons (~2.5 min serial).
- Fixtures: shared `qapp` plus the P1-3 harness fixtures `stub_app`,
  `main_window` and `agent` in
  [`tests/gui/conftest.py`](tests/gui/conftest.py); the `StubApp` pattern
  builds a `MainWindow` without touching real QSettings (its teardown returns
  to the dashboard before close — defense-in-depth against the closeEvent
  modal path, section 7).
- Test IDs are covered by [`tests/gui/test_agent_ids.py`](tests/gui/test_agent_ids.py)
  (coverage, uniqueness, grammar), the toolkit by
  [`tests/gui/test_agent_tools.py`](tests/gui/test_agent_tools.py),
  crash/event/annotate diagnostics by
  [`tests/gui/test_agent_diagnostics.py`](tests/gui/test_agent_diagnostics.py),
  and pytest-qt idioms by
  [`tests/gui/test_qt_idioms.py`](tests/gui/test_qt_idioms.py).
- Useful pytest-qt idioms: `qtbot.waitSignal`, `qtbot.waitUntil`,
  `qtbot.mouseClick`, `qtbot.addWidget`, `qtbot.captureExceptions`,
  `qtbot.screenshot`; see
  [`tests/gui/test_batch_runner.py`](tests/gui/test_batch_runner.py) for the
  `waitSignal(worker.succeeded, timeout=60_000)` reference.
- Visual regression (P2-2):
  [`tests/gui/test_visual_regression.py`](tests/gui/test_visual_regression.py)
  compares per-(page, theme) golden PNGs in
  [`tests/gui/baselines/`](tests/gui/baselines) (layout
  `<page>_<theme>_<platform>.png`, platform suffix `windows`/`linux`/`macos`)
  using the pinned Pillow diff in
  [`tests/gui/visual.py`](tests/gui/visual.py): fail when the differing-pixel
  ratio > 0.5% or mean channel delta > 2.0. Capture is the full
  `MainWindow` at a pinned 1280×800 via `gui_screenshot(theme=…)`
  (session-only themes, U-06) with the X-2 font env pinned; the status-bar
  message is normalized to the generic `View: …` line before each grab
  (page-specific messages can embed absolute machine paths). Missing
  baselines skip locally with a clear message and fail only in CI on a
  platform that owns a committed set (windows). Diff artifacts
  (expected/actual/diff PNGs) land in `reports/visual_diff/` (uploaded by CI
  on failure).

## 10. Agent workflow

1. Read this file and [`gui/AGENTS.md`](gui/AGENTS.md).
2. Edit code.
3. Run GUI tests headless: `QT_QPA_PLATFORM=offscreen pytest -m gui`.
4. If tests pass, take ground truth: `dump_widget_tree()` (MCP) or
   `python -m gui.agent_tools dump --text`, plus `screenshot(annotate=True)`
   / `python -m gui.agent_tools screenshot --page <page> --annotate`. Pair
   every screenshot with its dump.
5. Reproduce/inspect the defect via the numbered badges and `testId` (never
   by coordinates), edit, and add or adjust a test that reproduces it first.
6. `run_gui_test(pattern)` (MCP) or `QT_QPA_PLATFORM=offscreen pytest -m gui
   -k <pattern>` — iterate.
7. Re-dump / re-screenshot to confirm the fix; check `reports/gui_events.jsonl`
   for unexpected events; if a crash occurred, read the newest
   `crash_reports/<ts>/` bundle.
8. Finish with the full headless suite
   (`QT_QPA_PLATFORM=offscreen pytest tests/ -n auto --dist loadfile`).

### Visual-regression baselines (P2-2)

- **What it detects:** unintended styling/layout drift from agent edits —
  the standing detector after any QSS, widget-geometry, or page-layout
  change (section 9 for mechanics, [`tests/gui/baselines/README.md`](tests/gui/baselines/README.md)).
- **When to re-baseline:** after *intentional* visual changes (QSS pass,
  layout fixes, new/renamed pages — the inventory meta-test fails loudly on
  a stale page list). Never re-baseline to silence an unexplained diff —
  read `reports/visual_diff/<name>.diff.png` first.
- **How (agents):** `ISA_STEWARD_UPDATE_BASELINES=1 QT_QPA_PLATFORM=offscreen
  pytest -m gui_visual`, then review the regenerated PNGs and commit them
  together with the change that caused the drift. Baselines are
  platform-keyed; capture on the platform whose set you refresh.
- **CI:** the `test` matrix runs the visual tests and uploads
  `reports/visual_diff/` on failure; a diff on a runner with different font
  rasterization is possible (the plan's stated risk) — resolve it by
  regenerating on that runner via the manual-dispatch `visual-baselines`
  workflow job (uploads `tests/gui/baselines/` as an artifact to commit).
- **Determinism rules:** captures pin the window size (1280×800), disable
  caret flashing, stop `auto_save_timer`, normalize the status-bar message,
  flush destroyed widgets (`DeferredDelete` — leaked windows otherwise make
  every capture's theme apply re-polish a growing zombie tree), converge the
  theme-repolish layout before grabbing (see the
  [`tests/gui/visual.py`](tests/gui/visual.py) docstring for the two-fixed-
  point layout hazard), and grab until two consecutive captures are pixel-
  identical — keep new pages free of timestamps/absolute paths in always-on
  chrome or the flake guard (`test_consecutive_captures_within_threshold`)
  will fail.

### Vision-model notes (Qwen3.8 27B)

- **Crop and cap:** screenshots are capped at 2048 px max edge; when
  reviewing one page, use the per-page crop (not the full window) — less
  visual noise, better detail retention.
- **Pair image + dump:** always read `dump_widget_tree()` text alongside the
  screenshot — the dump is exact ground truth for names/enabled/geometry; the
  image is for layout/overlap/color issues.
- **Reference by ID:** use `testId` values from the legend/dump in all edits
  and tool calls; badges map 1:1 to `.legend.json` legend entries.
- **Themes:** light theme OCRs better; verify contrast fixes in both themes
  (`screenshot(theme="light")` / `theme="dark"` are session-only captures).
- **Fonts:** offscreen boots set `QT_QPA_FONTDIR=C:\Windows\Fonts` on Windows
  when it is unset (X-2 via
  [`ensure_offscreen_platform()`](gui/agent_tools/runtime.py)) so captures
  render real glyphs; an explicit `QT_QPA_FONTDIR` is respected and
  non-Windows behavior is unchanged.
- **Small tool responses:** all MCP/CLI outputs return file paths, not
  base64; open images with the vision tool only when needed.

## 11. Do / Don't

**Do:** keep `testId`s unique and grammar-conformant; run GUI tests headless
before claiming done; pair screenshots with dumps; set IDs at creation sites;
keep tool outputs as file paths; use MCP for the inspect/drive loop and
pytest-qt for modal-dialog flows; re-baseline visual goldens
(`ISA_STEWARD_UPDATE_BASELINES=1`) after intentional styling changes and
commit the PNGs with the change.

**Don't:** rename QSS `objectName`s; commit `reports/` or `crash_reports/`
contents; click by screen coordinates; edit `.qss` selectors without visual
verification (screenshot both themes); break the
`isa-gui/widget-tree/1` dump schema without versioning it; click
modal-opening buttons via MCP expecting a quick return; rely on
`screenshot(theme=...)` to persist a theme (it is session-only); re-baseline
visual goldens to silence an unexplained diff.
