# AGENTS.md — gui/

GUI-module guidance for AI coding agents. Project-wide context:
[`../AGENTS.md`](../AGENTS.md). Design spec:
[`../plans/agent-gui-observability.md`](../plans/agent-gui-observability.md).

## 1. Module map

| File | Role |
|------|------|
| `app.py` | `StewardApp` (QApplication): theme, fonts, QSettings-backed state |
| `main.py` | `main()` entry point (`isa-json-steward-gui`) |
| `main_window.py` | `MainWindow`: sidebar + `QStackedWidget` + status bar, page registry, auto-save |
| `pages/` | 10 content pages (`BasePage`/`ScrollablePage` subclasses) |
| `dialogs/` | 10 modal dialogs |
| `widgets/` | Reusable composites: `common.py`, `sidebar.py`, `status_bar.py`, `path_picker.py`, `collapsible_group_box.py`, `file_attachment_widget.py`, `graph_widget.py`, … |
| `resources/styles/` | `dark.qss` / `light.qss` — objectName-keyed styling |
| `agent_tools/` | Agent observability toolkit (ids, dump, screenshot, annotate, events, crash, runtime, cli, mcp_server) |

## 2. Page inventory

`page_id` = key in `MainWindow.pages`. Root testId is `page.<page_id>`.

| page_id | Class | File | Key testIds |
|---------|-------|------|-------------|
| dashboard | `DashboardPage` | `pages/dashboard.py` | `page.dashboard.createInvestigationButton`, `.createStudyButton`, `.openRecentStudyButton`, `.browseOntologyButton`, `.runBatchButton` |
| studies | `StudiesPage` | `pages/studies.py` | `page.studies.studiesTree`, `.refreshButton`, `.createInvestigationButton`, `.createStudyButton`, `.deleteButton` |
| process_sequence | `ProcessSequencePage` | `pages/process_sequence.py` | `page.process_sequence.processTree`, `.addProcessButton`, `.removeProcessButton`, `.saveButton`, `.validateButton`, `.inputsList`, `.outputsList`, `.selectInputsButton`, `.selectOutputsButton`, `.parameterValueField_<n>` |
| materials | `MaterialsPage` | `pages/materials.py` | `page.materials.materialsTable`, `.typeFilter`, `.addButton`, `.editButton`, `.deleteButton`, `.refreshButton` |
| assays | `AssaysPage` | `pages/assays.py` | `page.assays.assaysTable`, `.templateCombo`, `.addButton`, `.editButton`, `.deleteButton` |
| files | `FilesPage` | `pages/files.py` | `page.files.fileTree`, `.filterCombo`, `.searchField`, `.refreshButton`, `.exportButton`, `.deleteButton` |
| images | `ImagesPage` | `pages/images.py` | `page.images.rawImagesList`, `.processedImagesList`, `.importButton`, `.convertButton`, `.refreshButton` |
| ontology | `OntologyBrowserPage` | `pages/ontology_browser.py` | `page.ontology.ontologyTree`, `.searchField`, `.searchButton`, `.clearButton`, `.expandAllButton`, `.collapseAllButton`, `.categoryCombo`, `.legendButton`, `.termDescription` |
| templates | `TemplatesPage` | `pages/templates.py` | `page.templates.templateList`, `.typeCombo`, `.createButton`, `.editButton`, `.importButton`, `.exportButton` |
| settings | `SettingsPage` | `pages/settings.py` | `page.settings.saveButton`, `.resetButton`, `.themeCombo`, `.baseUrlField`, `.<x>Check` toggles, `.<x>Spin`/`.<x>Field` inputs |

## 3. Dialog inventory

Root testId is `dialog.<dialogName>` where `<dialogName>` is the class name
minus a trailing `Dialog`, lowerCamelCased.

| Dialog class | File | Key testIds |
|--------------|------|-------------|
| `AddParameterDialog` | `dialogs/add_parameter_dialog.py` | `dialog.addParameter.nameField`, `.unitField`, `.valueField`, `.addButton`, `.cancelButton` |
| `ParameterDialog` | `dialogs/parameter_dialog.py` | `dialog.parameter.valueField_<n>`, `.saveButton`, `.cancelButton` |
| `AssayDialog` | `dialogs/assay_dialog.py` | `dialog.assay.nameField`, `.typeCombo`, `.dateField`, `.descriptionField`, `.formViewButton`, `.jsonViewButton`, `.addParameterButton`, `.inputsList`, `.selectInputsButton`, `.saveButton`, `.valueField_<n>`, `.firstNameField`…`.affiliationField` |
| `MaterialDialog` | `dialogs/material_dialog.py` | `dialog.material.nameField`, `.typeCombo`, `.derivesFromField`, `.descriptionField`, `.saveButton`, `.characteristicsList`, `.addCharacteristicButton`, `.removeCharacteristicButton` |
| `CharacteristicDialog` | `dialogs/material_dialog.py` | `dialog.characteristic.typeField`, `.sourceCombo`, `.accessionField`, `.valueField`, `.okButton`, `.cancelButton` |
| `MaterialSelectionDialog` | `dialogs/material_selection_dialog.py` | `dialog.materialSelection.searchField`, `.materialsTree`, `.groupByTypeCheck`, `.okButton`, `.cancelButton` |
| `StudyWizard` | `dialogs/study_wizard.py` | `dialog.studyWizard.investigationCombo`, `.createInvestigationButton`, `.nameField`, `.strainField`, `.plasmidField`, `.sequencePathField`, `.browseButton`, `.createButton`, `.cancelButton` |
| `InvestigationDialog` | `dialogs/investigation_dialog.py` | `dialog.investigation.idField`, `.titleField`, `.descriptionField`, `.createButton`, `.cancelButton` |
| `ImageConverterDialog` | `dialogs/image_converter.py` | `dialog.imageConverter.filePathField`, `.browseButton`, `.descriptionField`, `.convertButton`, `.cancelButton` |
| `TemplateEditorDialog` | `dialogs/template_editor.py` | `dialog.templateEditor.nameField`, `.descriptionField`, `.jsonEditor`, `.formatButton`, `.parametersTable`, `.addParameterButton`, `.saveButton`, `.unitCombo_<n>`, `.removeButton_<n>` |
| `BatchProcessingDialog` | `dialogs/batch_processing.py` | `dialog.batchProcessing.dataRootField`, `.outputDirField`, `.investigationIdField`, `.startButton`, `.cancelButton`, `.experimentTree`, `.openFolderButton`, `.logView` |

Shell IDs: `window.main`, `window.main.contentStack`, `sidebar.title`,
`sidebar.scrollArea`, `sidebar.navButton.<page_id>`,
`statusBar.messageLabel`, `statusBar.investigationLabel`,
`statusBar.studyLabel`, `statusBar.progressBar`.

## 4. Styling rules

- QSS selectors key off `objectName` and are **load-bearing**: never rename
  `sidebar`, `sidebarTitle`, `sidebarButton`, `contentArea`, `contentPage`,
  `card`, `formLabel`, `primaryButton`, `dangerButton`.
- `contentArea` is the `QStackedWidget` in `MainWindow`; `contentPage` is the
  `BasePage` root (`gui/pages/base_page.py`). Both are styled by
  `QWidget#contentArea, QWidget#contentPage` in each theme file — keep the
  pair of selectors in sync across `dark.qss` and `light.qss`.
- Theme switching: `StewardApp.set_theme("light" | "dark")` loads
  `resources/styles/<theme>.qss`. Verify contrast fixes in **both** themes.

## 5. Adding a new widget or page

1. Create the widget/page; call `set_test_id(widget, "<scope>.<qualifier>.<name>")`
   (or pass `test_id=` to `PrimaryButton`/`DangerButton`/`ActionButton`/
   `FormField`) at the creation site — see the ID grammar in
   [`../AGENTS.md`](../AGENTS.md) section 5.
2. Interactive classes that must be tagged: `QAbstractButton` subclasses
   (buttons, checkboxes, tool buttons), `QLineEdit` subclasses, `QComboBox`,
   and item views (`QTableWidget`, `QTreeWidget`, `QListWidget`).
3. **A11y (P2-3):** pass `accessible_name="Save settings"` — a sentence-case
   human phrase, never the raw `testId` — to `set_test_id()` / the
   `test_id=`-kwargs of [`widgets/common.py`](widgets/common.py) at the same
   time (`set_test_id()` only fills an empty `accessibleName`, so a
   deliberate name is never overwritten). Add
   `setAccessibleDescription(...)` to form fields whose label alone is
   ambiguous (multi-field forms); an existing tooltip can seed the
   description. The enforcement tests in
   [`../tests/gui/test_agent_ids.py`](../tests/gui/test_agent_ids.py) reject
   any tagged widget whose name is empty or `testId`-shaped.
4. Do not rename existing `objectName`s; give new styled widgets their own
   objectName + matching QSS rule in **both** theme files.
5. Register the page in `MainWindow.initialize_pages()` (root testId
   `page.<page_id>` comes for free) and add a row to the inventory above.
6. Add/extend tests in `tests/gui/` and run
   `QT_QPA_PLATFORM=offscreen pytest -m gui`.

Known a11y gap (P2-3): `GraphWidget`
([`widgets/graph_widget.py`](widgets/graph_widget.py)) exposes only a
container-level `accessibleName`/`accessibleDescription` at its creation
site; its `QGraphicsScene` canvas items (`GraphNode`/`GraphEdge`) have **no**
`QAccessible` factories and are invisible to accessibility tooling. Building
the factories is only worth it once a consumer needs them (P2-3 scope
documents the gap rather than blocking on it).

## 6. Debugging a GUI issue

1. `python -m gui.agent_tools dump --text` — ground truth for widget state;
   pair with `python -m gui.agent_tools screenshot --page <page> --annotate`
   (PNG + `.legend.json` sidecar under `reports/`, ≤2048 px; badge numbers map
   1:1 to legend entries). The same surface is available over MCP
   (`python -m gui.agent_tools mcp-serve`, tools `dump_widget_tree` /
   `screenshot` / …) — see [`../AGENTS.md`](../AGENTS.md) section 8.
2. Drive the GUI by `testId`: `click`, `set-text`, `get-state` subcommands or
   `HeadlessGui` in-process. Never click by coordinates.
3. Read `reports/gui_events.jsonl` (schema `isa-gui/event/1`) for the event
   trail, and the newest `crash_reports/<ts>/` bundle (see
   [`../AGENTS.md`](../AGENTS.md) section 7) if a crash occurred.
