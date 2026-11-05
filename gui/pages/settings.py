"""
Settings page for ISA-JSON Data Steward GUI.
"""

import json
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
    QSpinBox,
    QWidget,
)

from utils.logging_config import get_logger

from ..agent_tools.ids import set_test_id
from ..widgets.collapsible_group_box import CollapsibleGroupBox
from ..widgets.common import ActionButton, DangerButton, PrimaryButton, SectionHeader, set_ui_role
from ..widgets.path_picker import PathPicker
from ..widgets.url_line_edit import UrlLineEdit
from .base_page import ScrollablePage

logger = get_logger(__name__)


def _settings_config_path() -> Path:
    """Return the path of the settings config file.

    Honors the ``ISA_STEWARD_CONFIG_PATH`` environment variable (read on every
    call so tests can isolate reads/writes), falling back to the repo-relative
    ``config/settings.json``.  Both the load and the explicit-save write go
    through this helper (U-02).
    """
    env_path = os.environ.get("ISA_STEWARD_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    return Path(__file__).parent.parent.parent / "config" / "settings.json"


_CHECKBOX_ROW_HEIGHT = 22


def _wrap_checkbox_field(checkbox: QCheckBox) -> QWidget:
    """Wrap a checkbox field in a left-aligned, fixed-height row (U-15).

    A bare checkbox in a ``QFormLayout`` field cell stretches to the full
    column width and sits at its ~15px natural height (the sweep's
    "full-width 15px-tall checkbox rows").  The wrapper gives every checkbox
    row a consistent 22px height and keeps the checkbox at the row's left
    edge.
    """
    container = QWidget()
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    container.setFixedHeight(_CHECKBOX_ROW_HEIGHT)
    checkbox.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    row.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    row.addStretch()
    return container


class SettingsPage(ScrollablePage):
    """Settings page for application configuration."""

    # U-02: settings persist ONLY through the explicit Save button, so the
    # auto-save tick must never claim "Auto-saved" for this page (U-07).
    auto_save_persists = False

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self._restart_required = False
        self._raw_config = {}
        self._config_load_failed = False
        self._form_layouts: list[QFormLayout] = []
        self.setup_settings_ui()

    def setup_settings_ui(self):
        """Set up the settings UI."""
        # Load config from settings.json
        self._load_config_from_file()

        # Appearance Section
        self._setup_appearance_section()

        # Window Section
        self._setup_window_section()

        # Data Management Section
        self._setup_data_management_section()

        # Directories Section
        self._setup_directories_section()

        # URLs Section
        self._setup_urls_section()

        # Validation Section
        self._setup_validation_section()

        # Export Section
        self._setup_export_section()

        # Version Control Section
        self._setup_version_control_section()

        # Save/Reset buttons
        self._setup_action_buttons()

        # U-15: uniform label-column width so field columns line up across
        # sections (each QFormLayout otherwise sizes its label column to its
        # own longest label -- sweep evidence: Appearance x=350 vs x=385..444).
        self._align_form_columns()

    def _load_config_from_file(self):
        """Load configuration from the settings config file.

        On failure the ``_config_load_failed`` flag is raised and
        :meth:`_on_save_settings` refuses to write: a Save backed by an empty
        ``_raw_config`` would silently drop the unmanaged top-level sections
        (e.g. ``application``) from the config file (U-02/U-12 config-loss
        edge).  Navigating back to the page (``on_enter``) reloads and clears
        the flag once the file parses again.
        """
        try:
            config_path = _settings_config_path()
            with open(config_path, "r", encoding="utf-8") as f:
                self._raw_config = json.load(f)
            self._config_load_failed = False
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self._raw_config = {}
            self._config_load_failed = True

    def _make_form_layout(self) -> QFormLayout:
        """Create a section form layout with the U-15 polish settings.

        The plan's pinned calls: left-aligned labels, left-aligned form rows
        and all non-fixed fields grow.  Layouts are registered for the
        cross-section column alignment pass (:meth:`_align_form_columns`).
        """
        layout = QFormLayout()
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._form_layouts.append(layout)
        return layout

    def _align_form_columns(self):
        """Give every section label column one uniform width (U-15).

        QFormLayout sizes each form's label column to its own longest label,
        so the field columns started at different x per section.  Setting
        every label's minimum width to the widest label's natural width lines
        the field columns up across all sections.
        """
        labels: list[QLabel] = []
        for form in self._form_layouts:
            for row in range(form.rowCount()):
                item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                label = item.widget() if item is not None else None
                if isinstance(label, QLabel):
                    labels.append(label)
        if not labels:
            return
        column_width = max(label.sizeHint().width() for label in labels)
        for label in labels:
            label.setMinimumWidth(column_width)

    def _setup_appearance_section(self):
        """Set up appearance settings section."""
        self.add_widget(SectionHeader("Appearance"))

        appearance_group = CollapsibleGroupBox("Appearance Settings")
        appearance_layout = self._make_form_layout()

        # Theme
        self.theme_combo = QComboBox()
        set_test_id(self.theme_combo, "page.settings.themeCombo", accessible_name="Theme")
        self.theme_combo.setAccessibleDescription("Application color theme: light or dark")
        self.theme_combo.addItems(["light", "dark"])
        self.theme_combo.setCurrentText(
            self.main_window.app.settings.value("gui/theme", "light", str)
        )
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        appearance_layout.addRow("Theme:", self.theme_combo)

        # Font Family
        self.font_family_combo = QComboBox()
        set_test_id(
            self.font_family_combo,
            "page.settings.fontFamilyCombo",
            accessible_name="Font family",
        )
        self.font_family_combo.setAccessibleDescription("Font family used across the application")
        self.font_family_combo.addItems(
            ["Segoe UI", "Arial", "Helvetica", "Calibri", "Verdana", "Tahoma", "Times New Roman"]
        )
        self.font_family_combo.setCurrentText(
            self.main_window.app.settings.value("gui/font_family", "Segoe UI", str)
        )
        appearance_layout.addRow("Font Family:", self.font_family_combo)

        # Font Size
        self.font_size_spin = QSpinBox()
        set_test_id(self.font_size_spin, "page.settings.fontSizeSpin", accessible_name="Font size")
        self.font_size_spin.setAccessibleDescription("Base font size in points (8 to 24)")
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(self.main_window.app.settings.value("gui/font_size", 10, int))
        self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
        appearance_layout.addRow("Font Size:", self.font_size_spin)

        appearance_group.add_layout(appearance_layout)
        self.add_widget(appearance_group)

    def _setup_window_section(self):
        """Set up window settings section."""
        window_group = CollapsibleGroupBox("Window Settings")
        window_layout = self._make_form_layout()

        # Window Width
        self.window_width_spin = QSpinBox()
        set_test_id(
            self.window_width_spin,
            "page.settings.windowWidthSpin",
            accessible_name="Window width",
        )
        self.window_width_spin.setAccessibleDescription(
            "Default window width in pixels (800 to 2560)"
        )
        self.window_width_spin.setRange(800, 2560)
        self.window_width_spin.setSuffix(" px")
        self.window_width_spin.setValue(self._raw_config.get("gui", {}).get("window_width", 1200))
        self.window_width_spin.valueChanged.connect(self._on_window_dim_changed)
        window_layout.addRow("Window Width:", self.window_width_spin)

        # Window Height
        self.window_height_spin = QSpinBox()
        set_test_id(
            self.window_height_spin,
            "page.settings.windowHeightSpin",
            accessible_name="Window height",
        )
        self.window_height_spin.setAccessibleDescription(
            "Default window height in pixels (600 to 1440)"
        )
        self.window_height_spin.setRange(600, 1440)
        self.window_height_spin.setSuffix(" px")
        self.window_height_spin.setValue(self._raw_config.get("gui", {}).get("window_height", 800))
        self.window_height_spin.valueChanged.connect(self._on_window_dim_changed)
        window_layout.addRow("Window Height:", self.window_height_spin)

        # Min Window Width
        self.min_window_width_spin = QSpinBox()
        set_test_id(
            self.min_window_width_spin,
            "page.settings.minWindowWidthSpin",
            accessible_name="Minimum window width",
        )
        self.min_window_width_spin.setAccessibleDescription(
            "Minimum window width in pixels (400 to 1200)"
        )
        self.min_window_width_spin.setRange(400, 1200)
        self.min_window_width_spin.setSuffix(" px")
        self.min_window_width_spin.setValue(
            self._raw_config.get("gui", {}).get("min_window_width", 800)
        )
        self.min_window_width_spin.valueChanged.connect(self._on_window_dim_changed)
        window_layout.addRow("Min Window Width:", self.min_window_width_spin)

        # Min Window Height
        self.min_window_height_spin = QSpinBox()
        set_test_id(
            self.min_window_height_spin,
            "page.settings.minWindowHeightSpin",
            accessible_name="Minimum window height",
        )
        self.min_window_height_spin.setAccessibleDescription(
            "Minimum window height in pixels (300 to 900)"
        )
        self.min_window_height_spin.setRange(300, 900)
        self.min_window_height_spin.setSuffix(" px")
        self.min_window_height_spin.setValue(
            self._raw_config.get("gui", {}).get("min_window_height", 600)
        )
        self.min_window_height_spin.valueChanged.connect(self._on_window_dim_changed)
        window_layout.addRow("Min Window Height:", self.min_window_height_spin)

        # U-07: window dims apply live (_on_window_dim_changed) -- no restart
        # indicator here; the single dynamic hint lives in the page footer.

        window_group.add_layout(window_layout)
        self.add_widget(window_group)

    def _setup_data_management_section(self):
        """Set up data management settings section."""
        data_group = CollapsibleGroupBox("Data Management")
        data_layout = self._make_form_layout()

        # Auto-Save Interval
        self.autosave_interval_spin = QSpinBox()
        set_test_id(
            self.autosave_interval_spin,
            "page.settings.autoSaveIntervalSpin",
            accessible_name="Auto-save interval",
        )
        self.autosave_interval_spin.setAccessibleDescription(
            "Seconds between automatic saves (30 to 3600)"
        )
        self.autosave_interval_spin.setRange(30, 3600)
        self.autosave_interval_spin.setSuffix(" seconds")
        self.autosave_interval_spin.setValue(
            self._raw_config.get("gui", {}).get("auto_save_interval", 300)
        )
        self.autosave_interval_spin.valueChanged.connect(self._on_autosave_interval_changed)
        data_layout.addRow("Auto-Save Interval:", self.autosave_interval_spin)

        # Backup Count
        self.backup_count_spin = QSpinBox()
        set_test_id(
            self.backup_count_spin,
            "page.settings.backupCountSpin",
            accessible_name="Backup count",
        )
        self.backup_count_spin.setAccessibleDescription(
            "Number of configuration backups kept (0 to 50)"
        )
        self.backup_count_spin.setRange(0, 50)
        self.backup_count_spin.setSuffix(" backups")
        self.backup_count_spin.setValue(self._raw_config.get("gui", {}).get("backup_count", 5))
        # U-07 audit: backup settings have no startup reader -- they take
        # effect at their next read, so no restart flag.
        data_layout.addRow("Backup Count:", self.backup_count_spin)

        # Backup on Save
        self.backup_on_save_check = QCheckBox()
        set_test_id(
            self.backup_on_save_check,
            "page.settings.backupOnSaveCheck",
            accessible_name="Back up settings on save",
        )
        self.backup_on_save_check.setAccessibleDescription(
            "Back up the configuration on every explicit save"
        )
        self.backup_on_save_check.setChecked(
            self._raw_config.get("gui", {}).get("backup_on_save", True)
        )
        data_layout.addRow("Backup on Save:", _wrap_checkbox_field(self.backup_on_save_check))

        data_group.add_layout(data_layout)
        self.add_widget(data_group)

    def _setup_directories_section(self):
        """Set up directories settings section."""
        dirs_config = self._raw_config.get("directories", {})

        dirs_group = CollapsibleGroupBox("Directory Configuration")
        dirs_layout = self._make_form_layout()

        # Base Path
        self.base_path_picker = PathPicker()
        set_test_id(
            self.base_path_picker,
            "page.settings.basePathPicker",
            accessible_name="Base path",
        )
        self.base_path_picker.setAccessibleDescription(
            "Root directory that study data is organized under"
        )
        self.base_path_picker.set_path(dirs_config.get("base_path", "."))
        self.base_path_picker.set_placeholder_text("Select base directory...")
        self.base_path_picker.pathChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Base Path:", self.base_path_picker)

        # Investigations Root
        self.investigations_root_edit = QLineEdit()
        set_test_id(
            self.investigations_root_edit,
            "page.settings.investigationsRootField",
            accessible_name="Investigations root",
        )
        self.investigations_root_edit.setAccessibleDescription(
            "Directory that stores investigations"
        )
        self.investigations_root_edit.setText(
            dirs_config.get("investigations_root", "investigations")
        )
        self.investigations_root_edit.textChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Investigations Root:", self.investigations_root_edit)

        # Templates Root
        self.templates_root_edit = QLineEdit()
        set_test_id(
            self.templates_root_edit,
            "page.settings.templatesRootField",
            accessible_name="Templates root",
        )
        self.templates_root_edit.setAccessibleDescription("Directory that stores templates")
        self.templates_root_edit.setText(dirs_config.get("templates_root", "templates"))
        self.templates_root_edit.textChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Templates Root:", self.templates_root_edit)

        # Ontologies Root
        self.ontologies_root_edit = QLineEdit()
        set_test_id(
            self.ontologies_root_edit,
            "page.settings.ontologiesRootField",
            accessible_name="Ontologies root",
        )
        self.ontologies_root_edit.setAccessibleDescription("Directory that stores ontologies")
        self.ontologies_root_edit.setText(dirs_config.get("ontologies_root", "ontologies"))
        self.ontologies_root_edit.textChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Ontologies Root:", self.ontologies_root_edit)

        # Exports Root
        self.exports_root_edit = QLineEdit()
        set_test_id(
            self.exports_root_edit,
            "page.settings.exportsRootField",
            accessible_name="Exports root",
        )
        self.exports_root_edit.setAccessibleDescription("Directory that exports are written to")
        self.exports_root_edit.setText(dirs_config.get("exports_root", "exports"))
        self.exports_root_edit.textChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Exports Root:", self.exports_root_edit)

        # Archive Root
        self.archive_root_edit = QLineEdit()
        set_test_id(
            self.archive_root_edit,
            "page.settings.archiveRootField",
            accessible_name="Archive root",
        )
        self.archive_root_edit.setAccessibleDescription(
            "Directory that archived investigations move to"
        )
        self.archive_root_edit.setText(dirs_config.get("archive_root", "archive"))
        self.archive_root_edit.textChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Archive Root:", self.archive_root_edit)

        # Config Root
        self.config_root_edit = QLineEdit()
        set_test_id(
            self.config_root_edit,
            "page.settings.configRootField",
            accessible_name="Config root",
        )
        self.config_root_edit.setAccessibleDescription("Directory that stores configuration files")
        self.config_root_edit.setText(dirs_config.get("config_root", "config"))
        self.config_root_edit.textChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Config Root:", self.config_root_edit)

        # Docs Root
        self.docs_root_edit = QLineEdit()
        set_test_id(self.docs_root_edit, "page.settings.docsRootField", accessible_name="Docs root")
        self.docs_root_edit.setAccessibleDescription("Directory that stores documentation")
        self.docs_root_edit.setText(dirs_config.get("docs_root", "docs"))
        self.docs_root_edit.textChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Docs Root:", self.docs_root_edit)

        # U-07: directory fields genuinely feed DirectoryManager construction
        # at startup, so they keep the restart flag; the single dynamic hint
        # lives in the page footer instead of per-section labels.

        dirs_group.add_layout(dirs_layout)
        self.add_widget(dirs_group)

    def _setup_urls_section(self):
        """Set up URLs settings section."""
        urls_config = self._raw_config.get("urls", {})

        urls_group = CollapsibleGroupBox("URL Configuration")
        urls_layout = self._make_form_layout()

        # Base URL
        self.base_url_edit = UrlLineEdit()
        set_test_id(self.base_url_edit, "page.settings.baseUrlField", accessible_name="Base URL")
        self.base_url_edit.setAccessibleDescription("Base URL used to build entity links")
        self.base_url_edit.set_url(
            urls_config.get("base_url", "https://example.org/investigations")
        )
        self.base_url_edit.set_allow_templates(False)
        self.base_url_edit.urlChanged.connect(self._mark_restart_required)
        urls_layout.addRow("Base URL:", self.base_url_edit)

        # Investigation URL Template
        self.investigation_url_template_edit = QLineEdit()
        set_test_id(
            self.investigation_url_template_edit,
            "page.settings.investigationUrlTemplateField",
            accessible_name="Investigation URL template",
        )
        self.investigation_url_template_edit.setAccessibleDescription(
            "URL template for investigation links"
        )
        self.investigation_url_template_edit.setText(
            urls_config.get("investigation_url_template", "{base_url}/{investigation_id}")
        )
        self.investigation_url_template_edit.setPlaceholderText("{base_url}/{investigation_id}")
        self.investigation_url_template_edit.textChanged.connect(self._mark_restart_required)
        urls_layout.addRow("Investigation URL Template:", self.investigation_url_template_edit)

        # Study URL Template
        self.study_url_template_edit = QLineEdit()
        set_test_id(
            self.study_url_template_edit,
            "page.settings.studyUrlTemplateField",
            accessible_name="Study URL template",
        )
        self.study_url_template_edit.setAccessibleDescription("URL template for study links")
        self.study_url_template_edit.setText(
            urls_config.get(
                "study_url_template", "{base_url}/{investigation_id}/studies/{study_id}"
            )
        )
        self.study_url_template_edit.setPlaceholderText(
            "{base_url}/{investigation_id}/studies/{study_id}"
        )
        self.study_url_template_edit.textChanged.connect(self._mark_restart_required)
        urls_layout.addRow("Study URL Template:", self.study_url_template_edit)

        # Material URL Template
        self.material_url_template_edit = QLineEdit()
        set_test_id(
            self.material_url_template_edit,
            "page.settings.materialUrlTemplateField",
            accessible_name="Material URL template",
        )
        self.material_url_template_edit.setAccessibleDescription("URL template for material links")
        self.material_url_template_edit.setText(
            urls_config.get(
                "material_url_template",
                "{base_url}/{investigation_id}/studies/{study_id}#{material_type}_{material_name}",
            )
        )
        self.material_url_template_edit.setPlaceholderText(
            "{base_url}/{investigation_id}/studies/{study_id}#{material_type}_{material_name}"
        )
        self.material_url_template_edit.textChanged.connect(self._mark_restart_required)
        urls_layout.addRow("Material URL Template:", self.material_url_template_edit)

        # Process URL Template
        self.process_url_template_edit = QLineEdit()
        set_test_id(
            self.process_url_template_edit,
            "page.settings.processUrlTemplateField",
            accessible_name="Process URL template",
        )
        self.process_url_template_edit.setAccessibleDescription("URL template for process links")
        self.process_url_template_edit.setText(
            urls_config.get(
                "process_url_template",
                "{base_url}/{investigation_id}/studies/{study_id}#process_{process_id}",
            )
        )
        self.process_url_template_edit.setPlaceholderText(
            "{base_url}/{investigation_id}/studies/{study_id}#process_{process_id}"
        )
        self.process_url_template_edit.textChanged.connect(self._mark_restart_required)
        urls_layout.addRow("Process URL Template:", self.process_url_template_edit)

        # U-07: URL config is baked into exports via MaterialManager's
        # cached base URL, so URL changes keep the restart flag (plan:
        # "possibly URL templates if export caches them" -- they do).

        urls_group.add_layout(urls_layout)
        self.add_widget(urls_group)

    def _setup_validation_section(self):
        """Set up validation settings section."""
        validation_config = self._raw_config.get("validation", {})

        validation_group = CollapsibleGroupBox("Validation Settings")
        validation_layout = self._make_form_layout()

        # Validate on Save
        self.validate_on_save_check = QCheckBox()
        set_test_id(
            self.validate_on_save_check,
            "page.settings.validateOnSaveCheck",
            accessible_name="Validate on save",
        )
        self.validate_on_save_check.setAccessibleDescription(
            "Validate the investigation before saving"
        )
        self.validate_on_save_check.setChecked(validation_config.get("validate_on_save", True))
        validation_layout.addRow(
            "Validate on Save:", _wrap_checkbox_field(self.validate_on_save_check)
        )

        # Validate Required Fields
        self.validate_required_fields_check = QCheckBox()
        set_test_id(
            self.validate_required_fields_check,
            "page.settings.validateRequiredFieldsCheck",
            accessible_name="Validate required fields",
        )
        self.validate_required_fields_check.setAccessibleDescription(
            "Check that all required fields are filled in"
        )
        self.validate_required_fields_check.setChecked(
            validation_config.get("validate_required_fields", True)
        )
        validation_layout.addRow(
            "Validate Required Fields:",
            _wrap_checkbox_field(self.validate_required_fields_check),
        )

        # Validate Ontology Terms
        self.validate_ontology_terms_check = QCheckBox()
        set_test_id(
            self.validate_ontology_terms_check,
            "page.settings.validateOntologyTermsCheck",
            accessible_name="Validate ontology terms",
        )
        self.validate_ontology_terms_check.setAccessibleDescription(
            "Check ontology terms against the loaded ontologies"
        )
        self.validate_ontology_terms_check.setChecked(
            validation_config.get("validate_ontology_terms", True)
        )
        validation_layout.addRow(
            "Validate Ontology Terms:",
            _wrap_checkbox_field(self.validate_ontology_terms_check),
        )

        # Validate Units
        self.validate_units_check = QCheckBox()
        set_test_id(
            self.validate_units_check,
            "page.settings.validateUnitsCheck",
            accessible_name="Validate units",
        )
        self.validate_units_check.setAccessibleDescription("Check that units are recognized")
        self.validate_units_check.setChecked(validation_config.get("validate_units", True))
        validation_layout.addRow("Validate Units:", _wrap_checkbox_field(self.validate_units_check))

        # Validate Date Formats
        self.validate_date_formats_check = QCheckBox()
        set_test_id(
            self.validate_date_formats_check,
            "page.settings.validateDateFormatsCheck",
            accessible_name="Validate date formats",
        )
        self.validate_date_formats_check.setAccessibleDescription(
            "Check that dates use supported formats"
        )
        self.validate_date_formats_check.setChecked(
            validation_config.get("validate_date_formats", True)
        )
        validation_layout.addRow(
            "Validate Date Formats:", _wrap_checkbox_field(self.validate_date_formats_check)
        )

        # Warn on Missing Metadata
        self.warn_on_missing_metadata_check = QCheckBox()
        set_test_id(
            self.warn_on_missing_metadata_check,
            "page.settings.warnOnMissingMetadataCheck",
            accessible_name="Warn on missing metadata",
        )
        self.warn_on_missing_metadata_check.setAccessibleDescription(
            "Emit warnings for missing recommended metadata"
        )
        self.warn_on_missing_metadata_check.setChecked(
            validation_config.get("warn_on_missing_metadata", True)
        )
        validation_layout.addRow(
            "Warn on Missing Metadata:",
            _wrap_checkbox_field(self.warn_on_missing_metadata_check),
        )

        validation_group.add_layout(validation_layout)
        self.add_widget(validation_group)

    def _setup_export_section(self):
        """Set up export settings section."""
        export_config = self._raw_config.get("export", {})

        export_group = CollapsibleGroupBox("Export Settings")
        export_layout = self._make_form_layout()

        # Default Export Format
        self.export_format_combo = QComboBox()
        set_test_id(
            self.export_format_combo,
            "page.settings.exportFormatCombo",
            accessible_name="Export format",
        )
        self.export_format_combo.setAccessibleDescription(
            "Format used when exporting: JSON, CSV, Excel or ISA-Tab"
        )
        self.export_format_combo.addItems(["JSON", "CSV", "Excel", "ISA-Tab"])
        self.export_format_combo.setCurrentText(export_config.get("default_format", "JSON"))
        export_layout.addRow("Default Export Format:", self.export_format_combo)

        # Include Raw Data
        self.include_raw_data_check = QCheckBox()
        set_test_id(
            self.include_raw_data_check,
            "page.settings.includeRawDataCheck",
            accessible_name="Include raw data in exports",
        )
        self.include_raw_data_check.setAccessibleDescription("Include raw data files in exports")
        self.include_raw_data_check.setChecked(export_config.get("include_raw_data", False))
        export_layout.addRow("Include Raw Data:", _wrap_checkbox_field(self.include_raw_data_check))

        # Include Processed Data
        self.include_processed_data_check = QCheckBox()
        set_test_id(
            self.include_processed_data_check,
            "page.settings.includeProcessedDataCheck",
            accessible_name="Include processed data in exports",
        )
        self.include_processed_data_check.setAccessibleDescription(
            "Include processed data files in exports"
        )
        self.include_processed_data_check.setChecked(
            export_config.get("include_processed_data", True)
        )
        export_layout.addRow(
            "Include Processed Data:", _wrap_checkbox_field(self.include_processed_data_check)
        )

        # Include Assay Data
        self.include_assay_data_check = QCheckBox()
        set_test_id(
            self.include_assay_data_check,
            "page.settings.includeAssayDataCheck",
            accessible_name="Include assay data in exports",
        )
        self.include_assay_data_check.setAccessibleDescription("Include assay data in exports")
        self.include_assay_data_check.setChecked(export_config.get("include_assay_data", True))
        export_layout.addRow(
            "Include Assay Data:", _wrap_checkbox_field(self.include_assay_data_check)
        )

        # Include Protocols
        self.include_protocols_check = QCheckBox()
        set_test_id(
            self.include_protocols_check,
            "page.settings.includeProtocolsCheck",
            accessible_name="Include protocols in exports",
        )
        self.include_protocols_check.setAccessibleDescription("Include protocols in exports")
        self.include_protocols_check.setChecked(export_config.get("include_protocols", True))
        export_layout.addRow(
            "Include Protocols:", _wrap_checkbox_field(self.include_protocols_check)
        )

        export_group.add_layout(export_layout)
        self.add_widget(export_group)

    def _setup_version_control_section(self):
        """Set up version control settings section."""
        vc_config = self._raw_config.get("version_control", {})

        vc_group = CollapsibleGroupBox("Version Control Settings")
        vc_layout = self._make_form_layout()

        # Enable Version Control
        self.enable_version_control_check = QCheckBox()
        set_test_id(
            self.enable_version_control_check,
            "page.settings.enableVersionControlCheck",
            accessible_name="Enable version control",
        )
        self.enable_version_control_check.setAccessibleDescription(
            "Keep versioned copies of the configuration"
        )
        self.enable_version_control_check.setChecked(vc_config.get("enabled", True))
        vc_layout.addRow(
            "Enable Version Control:", _wrap_checkbox_field(self.enable_version_control_check)
        )

        # Auto-Version on Save
        self.auto_version_on_save_check = QCheckBox()
        set_test_id(
            self.auto_version_on_save_check,
            "page.settings.autoVersionOnSaveCheck",
            accessible_name="Version configuration on save",
        )
        self.auto_version_on_save_check.setAccessibleDescription(
            "Create a configuration version on every explicit save"
        )
        self.auto_version_on_save_check.setChecked(vc_config.get("auto_version_on_save", True))
        vc_layout.addRow(
            "Auto-Version on Save:", _wrap_checkbox_field(self.auto_version_on_save_check)
        )

        # Version Prefix
        # U-07 audit: version-control fields have no startup reader -- they
        # take effect at their next read, so no restart flag.
        self.version_prefix_edit = QLineEdit()
        set_test_id(
            self.version_prefix_edit,
            "page.settings.versionPrefixField",
            accessible_name="Version prefix",
        )
        self.version_prefix_edit.setAccessibleDescription("Prefix used for version names")
        self.version_prefix_edit.setText(vc_config.get("version_prefix", "v"))
        vc_layout.addRow("Version Prefix:", self.version_prefix_edit)

        # Max Versions
        self.max_versions_spin = QSpinBox()
        set_test_id(
            self.max_versions_spin,
            "page.settings.maxVersionsSpin",
            accessible_name="Maximum versions kept",
        )
        self.max_versions_spin.setAccessibleDescription("Maximum number of versions kept")
        self.max_versions_spin.setRange(0, 100)
        self.max_versions_spin.setSpecialValueText("Unlimited")
        self.max_versions_spin.setValue(vc_config.get("max_versions", 10))
        vc_layout.addRow("Max Versions:", self.max_versions_spin)

        # Compress Old Versions
        self.compress_old_versions_check = QCheckBox()
        set_test_id(
            self.compress_old_versions_check,
            "page.settings.compressOldVersionsCheck",
            accessible_name="Compress old versions",
        )
        self.compress_old_versions_check.setAccessibleDescription(
            "Compress versions beyond the newest ones"
        )
        self.compress_old_versions_check.setChecked(vc_config.get("compress_old_versions", False))
        vc_layout.addRow(
            "Compress Old Versions:", _wrap_checkbox_field(self.compress_old_versions_check)
        )

        vc_group.add_layout(vc_layout)
        self.add_widget(vc_group)

    def _setup_action_buttons(self):
        """Set up the fixed footer action row (U-07).

        Save/Reset live in a footer OUTSIDE the scroll area so they are
        always reachable without scrolling (the old in-form row sat at
        y≈1804 in a 774px viewport).  The restart hint and the "Restart
        Now" button appear only while a restart is pending.
        """
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 4, 0, 4)
        footer_layout.setSpacing(8)

        # Single dynamic "restart needed" hint (U-07), themed via the
        # warning uiRole (no inline colors).
        self.restart_hint = QLabel("⚠ Restart required for directory/URL changes")
        set_test_id(
            self.restart_hint,
            "page.settings.restartHintLabel",
            accessible_name="Restart hint",
        )
        set_ui_role(self.restart_hint, "warning")
        self.restart_hint.setVisible(False)
        footer_layout.addWidget(self.restart_hint)

        footer_layout.addStretch()

        # Reset to Defaults button (U-14: destructive -> DangerButton)
        reset_btn = DangerButton(
            "Reset to Defaults",
            test_id="page.settings.resetButton",
            accessible_name="Reset settings to defaults",
        )
        reset_btn.setAccessibleDescription("Discard changes and restore the default settings")
        reset_btn.clicked.connect(self._on_reset_to_defaults)
        footer_layout.addWidget(reset_btn)

        # Save Settings button
        save_btn = PrimaryButton(
            "Save Settings",
            test_id="page.settings.saveButton",
            accessible_name="Save settings",
        )
        save_btn.clicked.connect(self._on_save_settings)
        footer_layout.addWidget(save_btn)

        # Restart Now button (U-07): explicit, non-modal restart affordance
        self.restart_btn = ActionButton(
            "Restart Now",
            test_id="page.settings.restartButton",
            accessible_name="Restart now",
        )
        self.restart_btn.setAccessibleDescription(
            "Restart the application to apply directory and URL changes"
        )
        self.restart_btn.clicked.connect(self._on_restart_now)
        self.restart_btn.setVisible(False)
        footer_layout.addWidget(self.restart_btn)

        self.add_footer(footer)

    def _set_restart_pending_visible(self, visible: bool):
        """Show/hide the restart hint and Restart Now button together."""
        self.restart_hint.setVisible(visible)
        self.restart_btn.setVisible(visible)

    def _mark_restart_required(self):
        """Mark that a restart is required (U-07, narrowed wiring).

        Only values genuinely read once at startup flag here: directory
        roots (they feed ``DirectoryManager`` construction and the startup
        template-index pass) and URL config (baked into exports through
        ``MaterialManager``).  Cheap settings apply live instead (window
        dims, auto-save interval, theme, font); backup and version-control
        fields have no startup reader and take effect at their next read.
        """
        self._restart_required = True
        self._set_restart_pending_visible(True)

    def _on_window_dim_changed(self, _value=None):
        """Apply window sizing settings live (U-07: no restart needed)."""
        self.main_window.setMinimumSize(
            self.min_window_width_spin.value(), self.min_window_height_spin.value()
        )
        self.main_window.resize(self.window_width_spin.value(), self.window_height_spin.value())

    def _on_autosave_interval_changed(self, value: int):
        """Re-arm the auto-save timer live (U-07: no restart needed)."""
        self.main_window.auto_save_timer.stop()
        if value > 0:
            self.main_window.auto_save_timer.start(value * 1000)

    def _on_restart_now(self):
        """Handle the Restart Now button (U-07).

        Shutdown is scheduled through the event loop and delegates to the
        normal close path.  There is deliberately no interpreter exit call
        here: ``gui/main.py`` owns the process exit code, and exiting from
        inside a slot would abort the Qt event loop unsafely (the old
        Yes-path quit the application and exited the interpreter inline).
        """
        self.main_window.status_bar.show_message("Restarting application…", 2000)
        QTimer.singleShot(0, self._perform_restart)

    def _perform_restart(self):
        self.main_window.close()
        QApplication.quit()

    def _on_theme_changed(self, theme: str):
        """Handle theme change."""
        self.main_window.app.set_theme(theme)

    def _on_font_size_changed(self, size: int):
        """Handle font size change."""
        font = QFont()
        font.setPointSize(size)
        self.main_window.app.setFont(font)

    def _on_save_settings(self):
        """Handle save settings button click.

        This button is the ONLY persistence path for settings (U-02):
        :meth:`save_data` is a no-op, so closing the window or an auto-save
        tick never rewrites the config file.
        """
        # U-02/U-12 guard: never write from a failed load -- the config on
        # disk must not lose the sections this form does not manage.
        if self._config_load_failed:
            self.main_window.status_bar.show_message(
                "Settings not saved: configuration failed to load; "
                "restore the settings file and reopen Settings before saving.",
                8000,
            )
            return
        try:
            # Validate settings
            if not self._validate_settings():
                return

            # Build updated config
            updated_config = self._raw_config.copy()

            # Update GUI settings
            updated_config["gui"] = {
                "auto_save_interval": self.autosave_interval_spin.value(),
                "backup_count": self.backup_count_spin.value(),
                "backup_on_save": self.backup_on_save_check.isChecked(),
                "window_width": self.window_width_spin.value(),
                "window_height": self.window_height_spin.value(),
                "min_window_width": self.min_window_width_spin.value(),
                "min_window_height": self.min_window_height_spin.value(),
            }

            # Update directories settings
            updated_config["directories"] = {
                "base_path": self.base_path_picker.path(),
                "investigations_root": self.investigations_root_edit.text(),
                "templates_root": self.templates_root_edit.text(),
                "ontologies_root": self.ontologies_root_edit.text(),
                "exports_root": self.exports_root_edit.text(),
                "archive_root": self.archive_root_edit.text(),
                "config_root": self.config_root_edit.text(),
                "docs_root": self.docs_root_edit.text(),
            }

            # Update URLs settings
            updated_config["urls"] = {
                "base_url": self.base_url_edit.url(),
                "investigation_url_template": self.investigation_url_template_edit.text(),
                "study_url_template": self.study_url_template_edit.text(),
                "material_url_template": self.material_url_template_edit.text(),
                "process_url_template": self.process_url_template_edit.text(),
            }

            # Update validation settings
            updated_config["validation"] = {
                "validate_on_save": self.validate_on_save_check.isChecked(),
                "validate_required_fields": self.validate_required_fields_check.isChecked(),
                "validate_ontology_terms": self.validate_ontology_terms_check.isChecked(),
                "validate_units": self.validate_units_check.isChecked(),
                "validate_date_formats": self.validate_date_formats_check.isChecked(),
                "warn_on_missing_metadata": self.warn_on_missing_metadata_check.isChecked(),
            }

            # Update export settings
            updated_config["export"] = {
                "default_format": self.export_format_combo.currentText(),
                "include_raw_data": self.include_raw_data_check.isChecked(),
                "include_processed_data": self.include_processed_data_check.isChecked(),
                "include_assay_data": self.include_assay_data_check.isChecked(),
                "include_protocols": self.include_protocols_check.isChecked(),
            }

            # Update version control settings
            updated_config["version_control"] = {
                "enabled": self.enable_version_control_check.isChecked(),
                "auto_version_on_save": self.auto_version_on_save_check.isChecked(),
                "version_prefix": self.version_prefix_edit.text(),
                "max_versions": self.max_versions_spin.value(),
                "compress_old_versions": self.compress_old_versions_check.isChecked(),
            }

            # Save to config file (path injectable via ISA_STEWARD_CONFIG_PATH)
            config_path = _settings_config_path()
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(updated_config, f, indent=2)
                # N4: end with exactly one newline (POSIX text file -- keeps
                # VCS diffs quiet on every explicit save).
                f.write("\n")

            # Save appearance settings to QSettings
            self.main_window.app.settings.setValue("gui/theme", self.theme_combo.currentText())
            self.main_window.app.settings.setValue(
                "gui/font_family", self.font_family_combo.currentText()
            )
            self.main_window.app.settings.setValue("gui/font_size", self.font_size_spin.value())

            if self._restart_required:
                # U-07: non-modal status message + explicit Restart Now
                # button -- never a blocking QMessageBox and never an
                # interpreter exit from inside a slot.  The flag stays set:
                # the restart is still pending until the app actually
                # restarts.
                self._set_restart_pending_visible(True)
                self.main_window.status_bar.show_message(
                    "Settings saved — restart to apply directory/URL changes", 8000
                )
            else:
                self.main_window.status_bar.show_message("Settings saved!", 3000)

        except Exception as e:
            QMessageBox.critical(
                self, "Error Saving Settings", f"Failed to save settings: {str(e)}"
            )

    def _validate_settings(self) -> bool:
        """Validate all settings before saving."""
        # Validate base URL
        if not self.base_url_edit.is_valid():
            QMessageBox.warning(self, "Invalid URL", "Base URL must start with http:// or https://")
            return False

        # Validate directory paths
        if not self.base_path_picker.is_valid():
            QMessageBox.warning(self, "Invalid Path", "Base path must be a valid directory path")
            return False

        # Validate version prefix
        if not self.version_prefix_edit.text():
            QMessageBox.warning(self, "Invalid Version Prefix", "Version prefix cannot be empty")
            return False

        return True

    def _on_reset_to_defaults(self):
        """Handle reset to defaults button click."""
        reply = QMessageBox.question(
            self,
            "Reset to Defaults",
            "Are you sure you want to reset all settings to their default values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Reset all settings to defaults
            self._reset_all_widgets_to_defaults()
            self.main_window.status_bar.show_message("Settings reset to defaults!", 3000)

    def _reset_all_widgets_to_defaults(self):
        """Reset all widgets to their default values."""
        # Appearance
        self.theme_combo.setCurrentText("light")
        self.font_family_combo.setCurrentText("Segoe UI")
        self.font_size_spin.setValue(10)

        # Window
        self.window_width_spin.setValue(1200)
        self.window_height_spin.setValue(800)
        self.min_window_width_spin.setValue(800)
        self.min_window_height_spin.setValue(600)

        # Data Management
        self.autosave_interval_spin.setValue(300)
        self.backup_count_spin.setValue(5)
        self.backup_on_save_check.setChecked(True)

        # Directories
        self.base_path_picker.set_path(".")
        self.investigations_root_edit.setText("investigations")
        self.templates_root_edit.setText("templates")
        self.ontologies_root_edit.setText("ontologies")
        self.exports_root_edit.setText("exports")
        self.archive_root_edit.setText("archive")
        self.config_root_edit.setText("config")
        self.docs_root_edit.setText("docs")

        # URLs
        self.base_url_edit.set_url("https://example.org/investigations")
        self.investigation_url_template_edit.setText("{base_url}/{investigation_id}")
        self.study_url_template_edit.setText("{base_url}/{investigation_id}/studies/{study_id}")
        self.material_url_template_edit.setText(
            "{base_url}/{investigation_id}/studies/{study_id}#{material_type}_{material_name}"
        )
        self.process_url_template_edit.setText(
            "{base_url}/{investigation_id}/studies/{study_id}#process_{process_id}"
        )

        # Validation
        self.validate_on_save_check.setChecked(True)
        self.validate_required_fields_check.setChecked(True)
        self.validate_ontology_terms_check.setChecked(True)
        self.validate_units_check.setChecked(True)
        self.validate_date_formats_check.setChecked(True)
        self.warn_on_missing_metadata_check.setChecked(True)

        # Export
        self.export_format_combo.setCurrentText("JSON")
        self.include_raw_data_check.setChecked(False)
        self.include_processed_data_check.setChecked(True)
        self.include_assay_data_check.setChecked(True)
        self.include_protocols_check.setChecked(True)

        # Version Control
        self.enable_version_control_check.setChecked(True)
        self.auto_version_on_save_check.setChecked(True)
        self.version_prefix_edit.setText("v")
        self.max_versions_spin.setValue(10)
        self.compress_old_versions_check.setChecked(False)

    def on_enter(self):
        """Called when the page is shown."""
        # Reload config from file
        self._load_config_from_file()

    def on_exit(self):
        """Called when the page is hidden."""
        pass

    def save_data(self):
        """Save page data.

        Intentionally a no-op (U-02): settings persist ONLY through the
        explicit "Save Settings" button (:meth:`_on_save_settings`).  The
        page-lifecycle hooks -- ``MainWindow.closeEvent`` and the auto-save
        timer -- must never rewrite the config as a side effect (the old
        behaviour silently rewrote ``config/settings.json`` on close and could
        pop a blocking restart modal at shutdown).
        """
        return
