"""
Settings page for ISA-JSON Data Steward GUI.
"""

import json
from pathlib import Path

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QWidget,
)

from ..widgets.collapsible_group_box import CollapsibleGroupBox
from ..widgets.common import ActionButton, PrimaryButton, SectionHeader
from ..widgets.path_picker import PathPicker
from ..widgets.url_line_edit import UrlLineEdit
from .base_page import ScrollablePage


class SettingsPage(ScrollablePage):
    """Settings page for application configuration."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self._restart_required = False
        self._raw_config = {}
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

    def _load_config_from_file(self):
        """Load configuration from config/settings.json."""
        try:
            config_path = Path(__file__).parent.parent.parent / "config" / "settings.json"
            with open(config_path, "r", encoding="utf-8") as f:
                self._raw_config = json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            self._raw_config = {}

    def _setup_appearance_section(self):
        """Set up appearance settings section."""
        self.add_widget(SectionHeader("Appearance"))

        appearance_group = CollapsibleGroupBox("Appearance Settings")
        appearance_layout = QFormLayout()

        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["light", "dark"])
        self.theme_combo.setCurrentText(
            self.main_window.app.settings.value("gui/theme", "light", str)
        )
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        appearance_layout.addRow("Theme:", self.theme_combo)

        # Font Family
        self.font_family_combo = QComboBox()
        self.font_family_combo.addItems(
            ["Segoe UI", "Arial", "Helvetica", "Calibri", "Verdana", "Tahoma", "Times New Roman"]
        )
        self.font_family_combo.setCurrentText(
            self.main_window.app.settings.value("gui/font_family", "Segoe UI", str)
        )
        appearance_layout.addRow("Font Family:", self.font_family_combo)

        # Font Size
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(self.main_window.app.settings.value("gui/font_size", 10, int))
        self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
        appearance_layout.addRow("Font Size:", self.font_size_spin)

        appearance_group.add_layout(appearance_layout)
        self.add_widget(appearance_group)

    def _setup_window_section(self):
        """Set up window settings section."""
        window_group = CollapsibleGroupBox("Window Settings")
        window_layout = QFormLayout()

        # Window Width
        self.window_width_spin = QSpinBox()
        self.window_width_spin.setRange(800, 2560)
        self.window_width_spin.setSuffix(" px")
        self.window_width_spin.setValue(self._raw_config.get("gui", {}).get("window_width", 1200))
        self.window_width_spin.valueChanged.connect(self._mark_restart_required)
        window_layout.addRow("Window Width:", self.window_width_spin)

        # Window Height
        self.window_height_spin = QSpinBox()
        self.window_height_spin.setRange(600, 1440)
        self.window_height_spin.setSuffix(" px")
        self.window_height_spin.setValue(self._raw_config.get("gui", {}).get("window_height", 800))
        self.window_height_spin.valueChanged.connect(self._mark_restart_required)
        window_layout.addRow("Window Height:", self.window_height_spin)

        # Min Window Width
        self.min_window_width_spin = QSpinBox()
        self.min_window_width_spin.setRange(400, 1200)
        self.min_window_width_spin.setSuffix(" px")
        self.min_window_width_spin.setValue(
            self._raw_config.get("gui", {}).get("min_window_width", 800)
        )
        self.min_window_width_spin.valueChanged.connect(self._mark_restart_required)
        window_layout.addRow("Min Window Width:", self.min_window_width_spin)

        # Min Window Height
        self.min_window_height_spin = QSpinBox()
        self.min_window_height_spin.setRange(300, 900)
        self.min_window_height_spin.setSuffix(" px")
        self.min_window_height_spin.setValue(
            self._raw_config.get("gui", {}).get("min_window_height", 600)
        )
        self.min_window_height_spin.valueChanged.connect(self._mark_restart_required)
        window_layout.addRow("Min Window Height:", self.min_window_height_spin)

        # Restart required indicator
        restart_label = QLabel("⚠️ Requires application restart")
        restart_label.setStyleSheet("color: #f39c12; font-size: 10px;")
        window_layout.addRow("", restart_label)

        window_group.add_layout(window_layout)
        self.add_widget(window_group)

    def _setup_data_management_section(self):
        """Set up data management settings section."""
        data_group = CollapsibleGroupBox("Data Management")
        data_layout = QFormLayout()

        # Auto-Save Interval
        self.autosave_interval_spin = QSpinBox()
        self.autosave_interval_spin.setRange(30, 3600)
        self.autosave_interval_spin.setSuffix(" seconds")
        self.autosave_interval_spin.setValue(
            self._raw_config.get("gui", {}).get("auto_save_interval", 300)
        )
        self.autosave_interval_spin.valueChanged.connect(self._mark_restart_required)
        data_layout.addRow("Auto-Save Interval:", self.autosave_interval_spin)

        # Backup Count
        self.backup_count_spin = QSpinBox()
        self.backup_count_spin.setRange(0, 50)
        self.backup_count_spin.setSuffix(" backups")
        self.backup_count_spin.setValue(self._raw_config.get("gui", {}).get("backup_count", 5))
        self.backup_count_spin.valueChanged.connect(self._mark_restart_required)
        data_layout.addRow("Backup Count:", self.backup_count_spin)

        # Backup on Save
        self.backup_on_save_check = QCheckBox()
        self.backup_on_save_check.setChecked(
            self._raw_config.get("gui", {}).get("backup_on_save", True)
        )
        self.backup_on_save_check.stateChanged.connect(self._mark_restart_required)
        data_layout.addRow("Backup on Save:", self.backup_on_save_check)

        data_group.add_layout(data_layout)
        self.add_widget(data_group)

    def _setup_directories_section(self):
        """Set up directories settings section."""
        dirs_config = self._raw_config.get("directories", {})

        dirs_group = CollapsibleGroupBox("Directory Configuration")
        dirs_layout = QFormLayout()

        # Base Path
        self.base_path_picker = PathPicker()
        self.base_path_picker.set_path(dirs_config.get("base_path", "."))
        self.base_path_picker.set_placeholder_text("Select base directory...")
        self.base_path_picker.pathChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Base Path:", self.base_path_picker)

        # Investigations Root
        self.investigations_root_edit = QLineEdit()
        self.investigations_root_edit.setText(
            dirs_config.get("investigations_root", "investigations")
        )
        self.investigations_root_edit.textChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Investigations Root:", self.investigations_root_edit)

        # Templates Root
        self.templates_root_edit = QLineEdit()
        self.templates_root_edit.setText(dirs_config.get("templates_root", "templates"))
        self.templates_root_edit.textChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Templates Root:", self.templates_root_edit)

        # Ontologies Root
        self.ontologies_root_edit = QLineEdit()
        self.ontologies_root_edit.setText(dirs_config.get("ontologies_root", "ontologies"))
        self.ontologies_root_edit.textChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Ontologies Root:", self.ontologies_root_edit)

        # Exports Root
        self.exports_root_edit = QLineEdit()
        self.exports_root_edit.setText(dirs_config.get("exports_root", "exports"))
        self.exports_root_edit.textChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Exports Root:", self.exports_root_edit)

        # Archive Root
        self.archive_root_edit = QLineEdit()
        self.archive_root_edit.setText(dirs_config.get("archive_root", "archive"))
        self.archive_root_edit.textChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Archive Root:", self.archive_root_edit)

        # Config Root
        self.config_root_edit = QLineEdit()
        self.config_root_edit.setText(dirs_config.get("config_root", "config"))
        self.config_root_edit.textChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Config Root:", self.config_root_edit)

        # Docs Root
        self.docs_root_edit = QLineEdit()
        self.docs_root_edit.setText(dirs_config.get("docs_root", "docs"))
        self.docs_root_edit.textChanged.connect(self._mark_restart_required)
        dirs_layout.addRow("Docs Root:", self.docs_root_edit)

        # Restart required indicator
        restart_label = QLabel("⚠️ Requires application restart")
        restart_label.setStyleSheet("color: #f39c12; font-size: 10px;")
        dirs_layout.addRow("", restart_label)

        dirs_group.add_layout(dirs_layout)
        self.add_widget(dirs_group)

    def _setup_urls_section(self):
        """Set up URLs settings section."""
        urls_config = self._raw_config.get("urls", {})

        urls_group = CollapsibleGroupBox("URL Configuration")
        urls_layout = QFormLayout()

        # Base URL
        self.base_url_edit = UrlLineEdit()
        self.base_url_edit.set_url(
            urls_config.get("base_url", "https://example.org/investigations")
        )
        self.base_url_edit.set_allow_templates(False)
        self.base_url_edit.urlChanged.connect(self._mark_restart_required)
        urls_layout.addRow("Base URL:", self.base_url_edit)

        # Investigation URL Template
        self.investigation_url_template_edit = QLineEdit()
        self.investigation_url_template_edit.setText(
            urls_config.get("investigation_url_template", "{base_url}/{investigation_id}")
        )
        self.investigation_url_template_edit.setPlaceholderText("{base_url}/{investigation_id}")
        self.investigation_url_template_edit.textChanged.connect(self._mark_restart_required)
        urls_layout.addRow("Investigation URL Template:", self.investigation_url_template_edit)

        # Study URL Template
        self.study_url_template_edit = QLineEdit()
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

        # Restart required indicator
        restart_label = QLabel("⚠️ Requires application restart")
        restart_label.setStyleSheet("color: #f39c12; font-size: 10px;")
        urls_layout.addRow("", restart_label)

        urls_group.add_layout(urls_layout)
        self.add_widget(urls_group)

    def _setup_validation_section(self):
        """Set up validation settings section."""
        validation_config = self._raw_config.get("validation", {})

        validation_group = CollapsibleGroupBox("Validation Settings")
        validation_layout = QFormLayout()

        # Validate on Save
        self.validate_on_save_check = QCheckBox()
        self.validate_on_save_check.setChecked(validation_config.get("validate_on_save", True))
        validation_layout.addRow("Validate on Save:", self.validate_on_save_check)

        # Validate Required Fields
        self.validate_required_fields_check = QCheckBox()
        self.validate_required_fields_check.setChecked(
            validation_config.get("validate_required_fields", True)
        )
        validation_layout.addRow("Validate Required Fields:", self.validate_required_fields_check)

        # Validate Ontology Terms
        self.validate_ontology_terms_check = QCheckBox()
        self.validate_ontology_terms_check.setChecked(
            validation_config.get("validate_ontology_terms", True)
        )
        validation_layout.addRow("Validate Ontology Terms:", self.validate_ontology_terms_check)

        # Validate Units
        self.validate_units_check = QCheckBox()
        self.validate_units_check.setChecked(validation_config.get("validate_units", True))
        validation_layout.addRow("Validate Units:", self.validate_units_check)

        # Validate Date Formats
        self.validate_date_formats_check = QCheckBox()
        self.validate_date_formats_check.setChecked(
            validation_config.get("validate_date_formats", True)
        )
        validation_layout.addRow("Validate Date Formats:", self.validate_date_formats_check)

        # Warn on Missing Metadata
        self.warn_on_missing_metadata_check = QCheckBox()
        self.warn_on_missing_metadata_check.setChecked(
            validation_config.get("warn_on_missing_metadata", True)
        )
        validation_layout.addRow("Warn on Missing Metadata:", self.warn_on_missing_metadata_check)

        validation_group.add_layout(validation_layout)
        self.add_widget(validation_group)

    def _setup_export_section(self):
        """Set up export settings section."""
        export_config = self._raw_config.get("export", {})

        export_group = CollapsibleGroupBox("Export Settings")
        export_layout = QFormLayout()

        # Default Export Format
        self.export_format_combo = QComboBox()
        self.export_format_combo.addItems(["JSON", "CSV", "Excel", "ISA-Tab"])
        self.export_format_combo.setCurrentText(export_config.get("default_format", "JSON"))
        export_layout.addRow("Default Export Format:", self.export_format_combo)

        # Include Raw Data
        self.include_raw_data_check = QCheckBox()
        self.include_raw_data_check.setChecked(export_config.get("include_raw_data", False))
        export_layout.addRow("Include Raw Data:", self.include_raw_data_check)

        # Include Processed Data
        self.include_processed_data_check = QCheckBox()
        self.include_processed_data_check.setChecked(
            export_config.get("include_processed_data", True)
        )
        export_layout.addRow("Include Processed Data:", self.include_processed_data_check)

        # Include Assay Data
        self.include_assay_data_check = QCheckBox()
        self.include_assay_data_check.setChecked(export_config.get("include_assay_data", True))
        export_layout.addRow("Include Assay Data:", self.include_assay_data_check)

        # Include Protocols
        self.include_protocols_check = QCheckBox()
        self.include_protocols_check.setChecked(export_config.get("include_protocols", True))
        export_layout.addRow("Include Protocols:", self.include_protocols_check)

        export_group.add_layout(export_layout)
        self.add_widget(export_group)

    def _setup_version_control_section(self):
        """Set up version control settings section."""
        vc_config = self._raw_config.get("version_control", {})

        vc_group = CollapsibleGroupBox("Version Control Settings")
        vc_layout = QFormLayout()

        # Enable Version Control
        self.enable_version_control_check = QCheckBox()
        self.enable_version_control_check.setChecked(vc_config.get("enabled", True))
        vc_layout.addRow("Enable Version Control:", self.enable_version_control_check)

        # Auto-Version on Save
        self.auto_version_on_save_check = QCheckBox()
        self.auto_version_on_save_check.setChecked(vc_config.get("auto_version_on_save", True))
        vc_layout.addRow("Auto-Version on Save:", self.auto_version_on_save_check)

        # Version Prefix
        self.version_prefix_edit = QLineEdit()
        self.version_prefix_edit.setText(vc_config.get("version_prefix", "v"))
        self.version_prefix_edit.textChanged.connect(self._mark_restart_required)
        vc_layout.addRow("Version Prefix:", self.version_prefix_edit)

        # Max Versions
        self.max_versions_spin = QSpinBox()
        self.max_versions_spin.setRange(0, 100)
        self.max_versions_spin.setSpecialValueText("Unlimited")
        self.max_versions_spin.setValue(vc_config.get("max_versions", 10))
        self.max_versions_spin.valueChanged.connect(self._mark_restart_required)
        vc_layout.addRow("Max Versions:", self.max_versions_spin)

        # Compress Old Versions
        self.compress_old_versions_check = QCheckBox()
        self.compress_old_versions_check.setChecked(vc_config.get("compress_old_versions", False))
        vc_layout.addRow("Compress Old Versions:", self.compress_old_versions_check)

        vc_group.add_layout(vc_layout)
        self.add_widget(vc_group)

    def _setup_action_buttons(self):
        """Set up save and reset buttons."""
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # Reset to Defaults button
        reset_btn = ActionButton("Reset to Defaults")
        reset_btn.clicked.connect(self._on_reset_to_defaults)
        button_layout.addWidget(reset_btn)

        # Save Settings button
        save_btn = PrimaryButton("Save Settings")
        save_btn.clicked.connect(self._on_save_settings)
        button_layout.addWidget(save_btn)

        button_widget = QWidget()
        button_widget.setLayout(button_layout)
        self.add_widget(button_widget)

    def _mark_restart_required(self):
        """Mark that restart is required."""
        self._restart_required = True

    def _on_theme_changed(self, theme: str):
        """Handle theme change."""
        self.main_window.app.set_theme(theme)

    def _on_font_size_changed(self, size: int):
        """Handle font size change."""
        font = QFont()
        font.setPointSize(size)
        self.main_window.app.setFont(font)

    def _on_save_settings(self):
        """Handle save settings button click."""
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

            # Save to config file
            config_path = Path(__file__).parent.parent.parent / "config" / "settings.json"
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(updated_config, f, indent=2)

            # Save appearance settings to QSettings
            self.main_window.app.settings.setValue("gui/theme", self.theme_combo.currentText())
            self.main_window.app.settings.setValue(
                "gui/font_family", self.font_family_combo.currentText()
            )
            self.main_window.app.settings.setValue("gui/font_size", self.font_size_spin.value())

            # Show restart prompt if needed
            if self._restart_required:
                reply = QMessageBox.question(
                    self,
                    "Restart Required",
                    "Some settings require application restart to take effect. Restart now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    # Restart application
                    import sys

                    from PyQt6.QtWidgets import QApplication

                    QApplication.quit()
                    sys.exit(0)

            self.main_window.status_bar.show_message("Settings saved!", 3000)
            self._restart_required = False

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
        """Save page data."""
        self._on_save_settings()
