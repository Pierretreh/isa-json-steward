"""
Configuration Loader Utility for ISA-JSON Data Steward.

This module provides centralized configuration loading with validation
and support for environment-specific configurations.

It includes:
- ``Config`` dataclass and ``ConfigLoader`` for application settings
  (``config/settings.json``).
- ``ProfileLoader`` for loading domain-specific profile configuration
  from all JSON files in the ``config/`` directory.  Files are loaded
  lazily on first access.  An optional *profile directory* can override
  the default ``config/`` location.
- Module-level singleton helpers ``get_profile()`` / ``set_profile()``
  so every module can access the loaded profile without passing it
  around.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from importlib.metadata import version as _pkg_version
except ImportError:  # pragma: no cover
    _pkg_version = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _get_core_version() -> Optional[str]:
    """Return the installed core package version (e.g. ``2.0.0``).

    Resolved via ``importlib.metadata`` from the distribution
    ``isa-json-steward``.  Returns ``None`` when the metadata is not
    available (e.g. running from a source checkout without an install).
    """
    if _pkg_version is None:
        return None
    try:
        return _pkg_version("isa-json-steward")
    except Exception:  # pragma: no cover - DistributionNotFound etc.
        return None


@dataclass
class Config:
    """Application configuration."""

    # Directory paths
    base_path: str = "."
    investigations_root: str = "investigations"
    templates_root: str = "templates"
    ontologies_root: str = "ontologies"
    exports_root: str = "exports"
    archive_root: str = "archive"
    config_root: str = "config"
    docs_root: str = "docs"

    # URLs
    base_url: str = "https://example.org/investigations"
    investigation_url_template: str = "{base_url}/{investigation_id}"
    study_url_template: str = "{base_url}/{investigation_id}/studies/{study_id}"
    material_url_template: str = (
        "{base_url}/{investigation_id}/studies/{study_id}#{material_type}_{material_name}"
    )
    process_url_template: str = (
        "{base_url}/{investigation_id}/studies/{study_id}#process_{process_id}"
    )

    # GUI settings
    auto_save_interval: int = 300
    backup_count: int = 5
    backup_on_save: bool = True
    window_width: int = 1200
    window_height: int = 800
    min_window_width: int = 800
    min_window_height: int = 600

    # Validation
    validate_on_save: bool = True
    validate_required_fields: bool = True
    validate_ontology_terms: bool = True
    validate_units: bool = True
    validate_date_formats: bool = True
    warn_on_missing_metadata: bool = True

    # Export settings
    export_default_format: str = "JSON"
    export_include_raw_data: bool = False
    export_include_processed_data: bool = True
    export_include_assay_data: bool = True
    export_include_protocols: bool = True

    # Version control
    version_control_enabled: bool = True
    version_control_auto_version: bool = True
    version_control_prefix: str = "v"
    version_control_max_versions: int = 10
    version_control_compress_old: bool = False


class ConfigError(Exception):
    """Exception raised when configuration is invalid."""

    pass


class ConfigValidationError(ConfigError):
    """Exception raised when configuration validation fails."""

    pass


class ProfileConfigError(ConfigError):
    """Exception raised when an explicitly supplied profile is incomplete.

    Used in *strict* mode: any config file (including ``profile.json``)
    that is missing from the profile directory and would have to be
    served from the core defaults is an error condition.
    """

    pass


class ConfigLoader:
    """Loader for application configuration."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration loader.

        Args:
            config_path: Path to configuration file (default: config/settings.json)
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "settings.json"
        else:
            config_path = Path(config_path)

        self.config_path = config_path
        self._config: Optional[Config] = None
        self._raw_config: Optional[Dict[str, Any]] = None

    def load(self) -> Config:
        """
        Load configuration from file.

        Returns:
            Config object with loaded settings

        Raises:
            ConfigError: If configuration file cannot be loaded
            ConfigValidationError: If configuration is invalid
        """
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._raw_config = json.load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {self.config_path}")
            raise ConfigError(f"Configuration file not found: {self.config_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in configuration file: {e}")
            raise ConfigError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            logger.error(f"Error loading configuration: {e}", exc_info=True)
            raise ConfigError(f"Error loading configuration: {e}")

        # Validate configuration
        self._validate_config(self._raw_config)

        # Build Config object
        config = self._build_config(self._raw_config)

        logger.info(f"Configuration loaded from {self.config_path}")
        return config

    def _validate_config(self, config: Dict[str, Any]):
        """
        Validate configuration structure and values.

        Args:
            config: Raw configuration dictionary

        Raises:
            ConfigValidationError: If configuration is invalid
        """
        # Check required sections
        required_sections = ["application", "directories", "urls"]
        for section in required_sections:
            if section not in config:
                raise ConfigValidationError(f"Missing required configuration section: {section}")

        # Validate URLs
        if "urls" in config:
            urls = config["urls"]
            if "base_url" not in urls:
                raise ConfigValidationError("Missing base_url in urls section")

            base_url = urls["base_url"]
            if not base_url.startswith(("http://", "https://")):
                raise ConfigValidationError(
                    f"base_url must start with http:// or https://, got: {base_url}"
                )

        # Validate file size limits
        if "validation" in config:
            validation = config.get("validation", {})
            if "max_file_size" in validation:
                max_size = validation["max_file_size"]
                if not isinstance(max_size, int) or max_size <= 0:
                    raise ConfigValidationError(
                        f"max_file_size must be a positive integer, got: {max_size}"
                    )

    def _build_config(self, raw_config: Dict[str, Any]) -> Config:
        """
        Build Config object from raw configuration.

        Args:
            raw_config: Raw configuration dictionary

        Returns:
            Config object
        """
        # Get directories
        dirs = raw_config.get("directories", {})

        # Get URLs
        urls = raw_config.get("urls", {})
        base_url = urls.get("base_url", "https://example.org/investigations")

        # Build URL templates
        investigation_template = urls.get(
            "investigation_url_template", "{base_url}/{investigation_id}"
        )
        study_template = urls.get(
            "study_url_template", "{base_url}/{investigation_id}/studies/{study_id}"
        )
        material_template = urls.get(
            "material_url_template",
            "{base_url}/{investigation_id}/studies/{study_id}#{material_type}_{material_name}",
        )
        process_template = urls.get(
            "process_url_template",
            "{base_url}/{investigation_id}/studies/{study_id}#process_{process_id}",
        )

        # Get validation settings
        validation = raw_config.get("validation", {})

        # Get export settings
        export_config = raw_config.get("export", {})

        # Get version control settings
        version_control = raw_config.get("version_control", {})

        # Get GUI settings
        gui_config = raw_config.get("gui", {})

        return Config(
            # Directories
            base_path=dirs.get("base_path", "."),
            investigations_root=dirs.get("investigations_root", "investigations"),
            templates_root=dirs.get("templates_root", "templates"),
            ontologies_root=dirs.get("ontologies_root", "ontologies"),
            exports_root=dirs.get("exports_root", "exports"),
            archive_root=dirs.get("archive_root", "archive"),
            config_root=dirs.get("config_root", "config"),
            docs_root=dirs.get("docs_root", "docs"),
            # URLs
            base_url=base_url,
            investigation_url_template=investigation_template,
            study_url_template=study_template,
            material_url_template=material_template,
            process_url_template=process_template,
            # GUI settings
            auto_save_interval=gui_config.get("auto_save_interval", 300),
            backup_count=gui_config.get("backup_count", 5),
            backup_on_save=gui_config.get("backup_on_save", True),
            window_width=gui_config.get("window_width", 1200),
            window_height=gui_config.get("window_height", 800),
            min_window_width=gui_config.get("min_window_width", 800),
            min_window_height=gui_config.get("min_window_height", 600),
            # Validation
            validate_on_save=validation.get("validate_on_save", True),
            validate_required_fields=validation.get("validate_required_fields", True),
            validate_ontology_terms=validation.get("validate_ontology_terms", True),
            validate_units=validation.get("validate_units", True),
            validate_date_formats=validation.get("validate_date_formats", True),
            warn_on_missing_metadata=validation.get("warn_on_missing_metadata", True),
            # Export
            export_default_format=export_config.get("default_format", "JSON"),
            export_include_raw_data=export_config.get("include_raw_data", False),
            export_include_processed_data=export_config.get("include_processed_data", True),
            export_include_assay_data=export_config.get("include_assay_data", True),
            export_include_protocols=export_config.get("include_protocols", True),
            # Version control
            version_control_enabled=version_control.get("enabled", True),
            version_control_auto_version=version_control.get("auto_version_on_save", True),
            version_control_prefix=version_control.get("version_prefix", "v"),
            version_control_max_versions=version_control.get("max_versions", 10),
            version_control_compress_old=version_control.get("compress_old_versions", False),
        )

    def save(self, config: Config) -> None:
        """
        Save configuration to file.

        Args:
            config: Config object to save
        """
        try:
            # Build raw config dictionary (cleaned structure)
            raw_config = {
                "directories": {
                    "base_path": config.base_path,
                    "investigations_root": config.investigations_root,
                    "templates_root": config.templates_root,
                    "ontologies_root": config.ontologies_root,
                    "exports_root": config.exports_root,
                    "archive_root": config.archive_root,
                    "config_root": config.config_root,
                    "docs_root": config.docs_root,
                },
                "urls": {
                    "base_url": config.base_url,
                    "investigation_url_template": config.investigation_url_template,
                    "study_url_template": config.study_url_template,
                    "material_url_template": config.material_url_template,
                    "process_url_template": config.process_url_template,
                },
                "gui": {
                    "auto_save_interval": config.auto_save_interval,
                    "backup_count": config.backup_count,
                    "backup_on_save": config.backup_on_save,
                    "window_width": config.window_width,
                    "window_height": config.window_height,
                    "min_window_width": config.min_window_width,
                    "min_window_height": config.min_window_height,
                },
                "validation": {
                    "validate_on_save": config.validate_on_save,
                    "validate_required_fields": config.validate_required_fields,
                    "validate_ontology_terms": config.validate_ontology_terms,
                    "validate_units": config.validate_units,
                    "validate_date_formats": config.validate_date_formats,
                    "warn_on_missing_metadata": config.warn_on_missing_metadata,
                },
                "export": {
                    "default_format": config.export_default_format,
                    "include_raw_data": config.export_include_raw_data,
                    "include_processed_data": config.export_include_processed_data,
                    "include_assay_data": config.export_include_assay_data,
                    "include_protocols": config.export_include_protocols,
                },
                "version_control": {
                    "enabled": config.version_control_enabled,
                    "auto_version_on_save": config.version_control_auto_version,
                    "version_prefix": config.version_control_prefix,
                    "max_versions": config.version_control_max_versions,
                    "compress_old_versions": config.version_control_compress_old,
                },
            }

            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write: write to temp file first
            temp_path = self.config_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(raw_config, f, indent=2)

            # Rename temp file to actual file (atomic operation)
            temp_path.replace(self.config_path)

            logger.info(f"Configuration saved to {self.config_path}")

        except Exception as e:
            logger.error(f"Error saving configuration: {e}", exc_info=True)
            raise ConfigError(f"Error saving configuration: {e}")

    def save_setting(self, key_path: str, value: Any) -> None:
        """
        Save a single setting value by dot-notation path.

        Args:
            key_path: Dot-separated path (e.g., "directories.base_path")
            value: Value to set
        """
        try:
            # Load current config
            if self._raw_config is None:
                self.load()
            assert self._raw_config is not None  # guaranteed after load()

            # Navigate to the target key
            keys = key_path.split(".")
            target = self._raw_config

            # Traverse to the parent of the target key
            for key in keys[:-1]:
                if key not in target:
                    target[key] = {}
                target = target[key]

            # Set the value
            target[keys[-1]] = value

            # Save the updated config
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write: write to temp file first
            temp_path = self.config_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self._raw_config, f, indent=2)

            # Rename temp file to actual file (atomic operation)
            temp_path.replace(self.config_path)

            logger.info(f"Setting '{key_path}' saved to {self.config_path}")

        except Exception as e:
            logger.error(f"Error saving setting '{key_path}': {e}", exc_info=True)
            raise ConfigError(f"Error saving setting '{key_path}': {e}")

    def save_section(self, section: str, settings: Dict[str, Any]) -> None:
        """
        Save an entire section of settings.

        Args:
            section: Section name (e.g., "directories", "urls")
            settings: Dictionary of settings to save in the section
        """
        try:
            # Load current config
            if self._raw_config is None:
                self.load()
            assert self._raw_config is not None  # guaranteed after load()

            # Update the section
            self._raw_config[section] = settings

            # Save the updated config
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write: write to temp file first
            temp_path = self.config_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self._raw_config, f, indent=2)

            # Rename temp file to actual file (atomic operation)
            temp_path.replace(self.config_path)

            logger.info(f"Section '{section}' saved to {self.config_path}")

        except Exception as e:
            logger.error(f"Error saving section '{section}': {e}", exc_info=True)
            raise ConfigError(f"Error saving section '{section}': {e}")

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a configuration value by dot-notation path.

        Args:
            key_path: Dot-separated path (e.g., "directories.base_path")
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        if self._config is None:
            self.load()

        keys = key_path.split(".")
        value = self._raw_config

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default

        return value if value is not None else default

    def reload(self) -> Config:
        """
        Reload configuration from file.

        Returns:
            Config object with reloaded settings
        """
        return self.load()


# Singleton instance for convenience
_config_loader = None


def get_config_loader(config_path: Optional[Path] = None) -> ConfigLoader:
    """
    Get singleton configuration loader instance.

    Args:
        config_path: Optional path to configuration file

    Returns:
        ConfigLoader instance
    """
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader(config_path)
    return _config_loader


def get_config(config_path: Optional[Path] = None) -> Config:
    """
    Convenience function to get configuration.

    Args:
        config_path: Optional path to configuration file

    Returns:
        Config object
    """
    loader = get_config_loader(config_path)
    return loader.load()


def get_base_url() -> str:
    """
    Get the base URL from configuration.

    Returns:
        Base URL string
    """
    loader = get_config_loader()
    config = loader.load()
    return config.base_url


def get_url_template(template_name: str, config_path: Optional[Path] = None) -> str:
    """
    Get a URL template by name.

    Args:
        template_name: Name of template (investigation_url_template, study_url_template, etc.)
        config_path: Optional path to configuration file

    Returns:
        URL template string
    """
    loader = get_config_loader()
    config = loader.load()

    template_map = {
        "investigation": config.investigation_url_template,
        "study": config.study_url_template,
        "material": config.material_url_template,
        "process": config.process_url_template,
    }

    return template_map.get(template_name, "")


# ---------------------------------------------------------------------------
# ProfileLoader – domain-specific configuration
# ---------------------------------------------------------------------------


class ProfileLoader:
    """Load and provide access to all domain-specific configuration files.

    Config files are loaded **lazily** on first access and then cached in
    memory.  If a *profile directory* is given, all files are read from
    that directory; otherwise the default ``config/`` directory relative
    to the project root is used.

    This class is intentionally independent of any project-specific
    modules – it is a pure config-loading utility.
    """

    # File names (relative to config_dir) and the corresponding cache keys
    _PROFILE_FILE = "profile.json"
    _CONFIG_FILES: Dict[str, str] = {
        "protein_names": "protein_names.json",
        "experiment_patterns": "experiment_patterns.json",
        "fcs_markers": "fcs_markers.json",
        "people": "people.json",
        "investigation_defaults": "investigation_defaults.json",
        "settings": "settings.json",
        "factor_extraction_rules": "factor_extraction_rules.json",
    }

    # The project root is the parent of ``utils/`` – used for fallback
    # config resolution and as the canonical investigations root.
    _PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

    def __init__(
        self,
        profile_path: Optional[str] = None,
        strict: bool = False,
    ) -> None:
        """Initialise the ProfileLoader.

        Args:
            profile_path: Optional path to a profile directory that
                overrides the default ``config/`` directory.  May be a
                string or ``None``.
            strict: When *True* (and *profile_path* is given), any config
                file that is missing from the profile directory and would
                have to be served from the core default ``config/``
                raises :class:`ProfileConfigError` instead of silently
                falling back.  Use this to fail fast on incomplete
                profiles, e.g. in batch pipelines.
        """
        if profile_path is not None:
            self._profile_root = Path(profile_path).resolve()
            self._config_dir = self._profile_root / "config"
            self._profile_explicit = True
        else:
            self._profile_root = Path(__file__).resolve().parent.parent
            self._config_dir = self._profile_root / "config"
            self._profile_explicit = False

        self.strict = strict and self._profile_explicit
        # Track files served from core defaults (for load summaries)
        self._fallback_files: List[str] = []

        # Cached data – populated lazily
        self._profile: Optional[Dict[str, Any]] = None
        self._cache: Dict[str, Any] = {}

        logger.debug(
            "ProfileLoader initialised with profile_root=%s, config_dir=%s, strict=%s",
            self._profile_root,
            self._config_dir,
            self.strict,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _candidate_paths(self, filename: str) -> List[Path]:
        """Return the ordered list of lookup locations for *filename*.

        Profile directories may keep their metadata either at the profile
        root (``profile_dir/profile.json``) or inside ``profile_dir/config/``.
        Both layouts are supported; the profile root is checked first.
        """
        candidates = [self._config_dir / filename]
        if filename == self._PROFILE_FILE:
            candidates.insert(0, self._profile_root / filename)
        candidates.append(self._PROJECT_ROOT / "config" / filename)
        return candidates

    def _read_json(self, filename: str) -> Dict[str, Any]:
        """Read and parse a JSON config file.

        Lookup order (first existing file wins):

        1. the profile's ``config/`` directory (or the profile root for
           ``profile.json``), then
        2. the **core** default ``config/`` directory shipped with the
           package, so that a partial profile (e.g. overriding only some
           files) still has access to all configuration sections.

        When a profile was explicitly supplied, serving a file from the
        core defaults is logged at ``WARNING`` level and recorded in
        :attr:`fallback_files` – a silently mixed config is the most
        common way a wrong domain (namespace, people, …) ends up in
        generated ISA-JSON.

        In *strict* mode, a file missing from an explicitly supplied
        profile raises :class:`ProfileConfigError` instead of falling
        back, so incomplete profiles fail fast.

        Returns an empty dict only if the file cannot be found in *either*
        location or is invalid JSON.
        """
        candidates = self._candidate_paths(filename)

        for index, path in enumerate(candidates):
            is_default_fallback = index == len(candidates) - 1
            if not path.exists():
                continue

            try:
                with open(path, "r", encoding="utf-8") as fh:
                    result: Dict[str, Any] = json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("Error reading %s: %s", path, exc)
                return {}

            if is_default_fallback:
                if self.strict:
                    raise ProfileConfigError(
                        f"Profile at {self._profile_root} is missing "
                        f"'{filename}' (would fall back to core default "
                        f"{path}). Add the file to the profile or disable "
                        f"strict mode."
                    )
                if self._profile_explicit:
                    logger.warning(
                        "Config file '%s' not found in profile %s – using "
                        "CORE DEFAULT %s. The profile may be incomplete and "
                        "the resulting config may mix domains.",
                        filename,
                        self._profile_root,
                        path,
                    )
                    if filename not in self._fallback_files:
                        self._fallback_files.append(filename)
                else:
                    logger.debug("Loaded core default config %s", path)
            return result

        logger.warning(
            "Config file not found in profile or core defaults: %s " "(searched: %s)",
            filename,
            ", ".join(str(c) for c in candidates),
        )
        return {}

    def log_profile_load_summary(self) -> None:
        """Log a summary of which files were served from core defaults.

        Call this once after profile activation (e.g. in CLI entry
        points) so that mixed-domain configurations are easy to spot in
        batch logs.
        """
        if self._profile_explicit and self._fallback_files:
            logger.warning(
                "Profile %s: %d config file(s) were served from CORE "
                "DEFAULTS: %s. Review the profile for missing files.",
                self._profile_root,
                len(self._fallback_files),
                ", ".join(sorted(self._fallback_files)),
            )

    def _get_section(self, key: str) -> Dict[str, Any]:
        """Return a cached config section, loading it if necessary."""
        if key not in self._cache:
            filename = self._CONFIG_FILES.get(key)
            if filename is None:
                logger.warning("Unknown config section: %s", key)
                return {}
            self._cache[key] = self._read_json(filename)
        result: Dict[str, Any] = self._cache[key]
        return result

    # ------------------------------------------------------------------
    # Profile metadata
    # ------------------------------------------------------------------

    @property
    def fallback_files(self) -> List[str]:
        """Names of config files served from the core default ``config/``.

        Only populated when an explicit profile is active and a file had
        to be read from the core defaults.
        """
        return list(self._fallback_files)

    @property
    def profile(self) -> Dict[str, Any]:
        """Return the parsed ``profile.json`` metadata (cached).

        On first access the profile's ``min_core_version`` (if present)
        is validated against the core package version; an incompatible
        core version raises :class:`ProfileConfigError`.
        """
        if self._profile is None:
            self._profile = self._read_json(self._PROFILE_FILE)
            self._enforce_min_core_version(self._profile)
        return self._profile

    def _enforce_min_core_version(self, profile_data: Dict[str, Any]) -> None:
        """Validate ``min_core_version`` against the installed core.

        Comparison is done on the first two version components
        (major.minor), so a requirement of ``1.0.0`` is satisfied by core
        ``2.0.0`` and any later version.  Missing or unparseable values
        are ignored with a debug log – the field is optional.
        """
        min_version = profile_data.get("min_core_version")
        if not min_version or not isinstance(min_version, str):
            return

        core_version = _get_core_version()
        if core_version is None:
            logger.debug(
                "Could not determine core version; skipping "
                "min_core_version check (required: %s)",
                min_version,
            )
            return

        def _parts(v: str) -> List[int]:
            out: List[int] = []
            for part in v.split(".")[:2]:
                digits = "".join(ch for ch in part if ch.isdigit())
                out.append(int(digits) if digits else 0)
            return out

        min_parts = _parts(min_version)
        core_parts = _parts(core_version)
        if core_parts[:2] < min_parts[:2]:
            raise ProfileConfigError(
                f"Profile '{profile_data.get('name', '?')}' requires core "
                f"version >= {min_version}, but installed core is "
                f"{core_version}. Upgrade the core or the profile."
            )
        logger.debug(
            "min_core_version OK: required >=%s, core=%s",
            min_version,
            core_version,
        )

    def get_namespace(self) -> str:
        """Return the ontology namespace URI, e.g. ``https://example.org/onto#``."""
        result: str = self.profile.get("namespace", "")
        return result

    def get_namespace_prefix(self) -> str:
        """Return the namespace prefix, e.g. ``onto``."""
        result: str = self.profile.get("namespace_prefix", "")
        return result

    def get_ontology_filenames(self) -> Dict[str, str]:
        """Return a dict mapping logical names to ontology file paths.

        Keys: ``main_owl``, ``main_ttl``, ``shapes``.
        """
        ont_dir = str(Path(self.profile.get("ontologies_dir", "ontologies")))
        return {
            "main_owl": str(Path(ont_dir) / self.profile.get("ontology_main_file", "")),
            "main_ttl": str(Path(ont_dir) / self.profile.get("ontology_main_ttl", "")),
            "shapes": str(Path(ont_dir) / self.profile.get("ontology_shapes", "")),
        }

    def get_templates_dir(self) -> str:
        """Return the configured templates directory."""
        result: str = self.profile.get("templates_dir", "templates")
        return result

    def get_profile_root(self) -> Path:
        """Return the profile root directory.

        This is the top-level directory of the profile (or project root
        when no profile is active).  It is the parent of both ``config/``
        and ``templates/``.
        """
        return self._profile_root

    def get_templates_root(self) -> Path:
        """Return the resolved templates directory path.

        Resolves the relative ``templates_dir`` from ``profile.json``
        against the profile root directory.
        """
        return self._profile_root / self.get_templates_dir()

    def get_investigations_root(self) -> Path:
        """Return the resolved investigations directory path.

        Reads ``investigations_root`` from the ``settings`` config
        section (``directories.investigations_root``) and resolves it
        against the **project root** directory – not the profile root.
        The profile provides metadata and configuration, but generated
        output (investigations) is written to the project tree.

        Defaults to ``investigations`` if the setting is absent.
        """
        settings = self._get_section("settings")
        dirs = settings.get("directories", {})
        inv_root = dirs.get("investigations_root", "investigations")
        return Path(self._PROJECT_ROOT / inv_root)

    def get_config_dir(self) -> str:
        """Return the configured config directory (within the profile)."""
        return str(self._config_dir)

    # ------------------------------------------------------------------
    # Protein / drug names
    # ------------------------------------------------------------------

    def get_protein_name(self, code: str) -> str:
        """Return the display name for *code*, or *code* itself if unknown."""
        data = self._get_section("protein_names")
        result: str = data.get("protein_names", {}).get(code, code)
        return result

    def get_drug_name(self, code: str) -> str:
        """Return the display name for a drug *code*, or *code* itself if unknown."""
        data = self._get_section("protein_names")
        result: str = data.get("drug_names", {}).get(code, code)
        return result

    def get_protein_name_map(self) -> Dict[str, str]:
        """Return the full protein-name mapping dict."""
        return dict(self._get_section("protein_names").get("protein_names", {}))

    def get_drug_name_map(self) -> Dict[str, str]:
        """Return the full drug-name mapping dict."""
        return dict(self._get_section("protein_names").get("drug_names", {}))

    # ------------------------------------------------------------------
    # Factor extraction rules
    # ------------------------------------------------------------------

    def get_factor_extraction_rules(self) -> Dict[str, Any]:
        """Return the parsed ``factor_extraction_rules.json`` content.

        Includes the ``rules`` list and the optional ``factor_aliases``
        mapping.  Returns an empty dict when the file is absent or empty.
        """
        data = self._get_section("factor_extraction_rules")
        result: Dict[str, Any] = dict(data) if data else {}
        return result

    # ------------------------------------------------------------------
    # Experiment patterns
    # ------------------------------------------------------------------

    def get_experiment_template(self, experiment_type: str) -> str:
        """Return the template filename for *experiment_type*, or empty string."""
        aliases = self._get_section("experiment_patterns").get("type_name_aliases", {})
        canonical: str = aliases.get(experiment_type, experiment_type)
        mapping = self._get_section("experiment_patterns").get("type_to_template", {})
        result: str = mapping.get(canonical, "")
        return result

    def get_experiment_keywords(self, experiment_type: str) -> List[str]:
        """Return the keyword list for *experiment_type*."""
        aliases = self._get_section("experiment_patterns").get("type_name_aliases", {})
        canonical = aliases.get(experiment_type, experiment_type)
        return list(
            self._get_section("experiment_patterns").get("type_keywords", {}).get(canonical, [])
        )

    def get_type_to_template(self) -> Dict[str, str]:
        """Return the full type-to-template mapping."""
        return dict(self._get_section("experiment_patterns").get("type_to_template", {}))

    def get_type_name_aliases(self) -> Dict[str, str]:
        """Return the full type-name-alias mapping."""
        return dict(self._get_section("experiment_patterns").get("type_name_aliases", {}))

    def get_type_keywords(self) -> Dict[str, List[str]]:
        """Return the full type-keywords mapping."""
        return dict(self._get_section("experiment_patterns").get("type_keywords", {}))

    def get_type_file_indicators(self) -> Dict[str, List[str]]:
        """Return the type-file-indicator mapping."""
        return dict(self._get_section("experiment_patterns").get("type_file_indicators", {}))

    def get_cell_type_map(self) -> Dict[str, str]:
        """Return the cell-type mapping."""
        return dict(self._get_section("experiment_patterns").get("cell_type_map", {}))

    def get_assay_type_map(self) -> Dict[str, List[str]]:
        """Return the assay-type mapping."""
        return dict(self._get_section("experiment_patterns").get("assay_type_map", {}))

    # ------------------------------------------------------------------
    # Subdirectory-structure patterns (Stage-1 hints)
    # ------------------------------------------------------------------

    def get_subdirectory_assay_patterns(self) -> Dict[str, str]:
        """Return the subdirectory-name → assay-type pattern mapping."""
        return dict(self._get_section("experiment_patterns").get("subdirectory_assay_patterns", {}))

    def get_subdirectory_processing_states(self) -> List[Dict[str, str]]:
        """Return the ordered list of subdirectory processing-state patterns."""
        raw = self._get_section("experiment_patterns").get("subdirectory_processing_states", [])
        result: List[Dict[str, str]] = []
        for entry in raw:
            if isinstance(entry, dict) and "pattern" in entry and "state" in entry:
                result.append({"pattern": str(entry["pattern"]), "state": str(entry["state"])})
        return result

    def get_subdirectory_compensation_patterns(self) -> List[str]:
        """Return the compensation-run subdirectory patterns."""
        raw = self._get_section("experiment_patterns").get("subdirectory_compensation_patterns", [])
        return [str(p) for p in raw]

    def get_subdirectory_timepoint_prefixes(self) -> Dict[str, str]:
        """Return the timepoint-prefix expansion mapping (e.g. ``D`` → ``Day``)."""
        return dict(
            self._get_section("experiment_patterns").get("subdirectory_timepoint_prefixes", {})
        )

    # ------------------------------------------------------------------
    # FCS markers
    # ------------------------------------------------------------------

    def get_fcs_markers(self) -> Dict[str, Any]:
        """Return the channel-marker mappings."""
        return dict(self._get_section("fcs_markers").get("channel_markers", {}))

    def get_known_operators(self) -> List[str]:
        """Return the list of known FCS operators."""
        return list(self._get_section("fcs_markers").get("known_operators", []))

    def get_instrument_aliases(self) -> Dict[str, str]:
        """Return the instrument-alias mapping."""
        return dict(self._get_section("fcs_markers").get("instrument_aliases", {}))

    # ------------------------------------------------------------------
    # People
    # ------------------------------------------------------------------

    def get_people(self) -> List[Dict[str, Any]]:
        """Return the people list."""
        return list(self._get_section("people").get("people", []))

    # ------------------------------------------------------------------
    # Investigation defaults
    # ------------------------------------------------------------------

    def get_investigation_defaults(self) -> Dict[str, Any]:
        """Return the investigation defaults dict."""
        return dict(self._get_section("investigation_defaults"))

    # ------------------------------------------------------------------
    # App settings (convenience wrapper around existing ConfigLoader)
    # ------------------------------------------------------------------

    def get_settings(self) -> Dict[str, Any]:
        """Return the raw ``settings.json`` dict."""
        return dict(self._get_section("settings"))


# ---------------------------------------------------------------------------
# Module-level singleton for ProfileLoader
# ---------------------------------------------------------------------------

_profile: Optional[ProfileLoader] = None


def get_profile(profile_path: Optional[str] = None) -> ProfileLoader:
    """Return the singleton ``ProfileLoader`` instance.

    On first call the instance is created.  Subsequent calls ignore
    *profile_path* and return the cached instance – use ``set_profile()``
    to change the profile directory after initialisation.
    """
    global _profile
    if _profile is None:
        _profile = ProfileLoader(profile_path)
    return _profile


def set_profile(profile_path: str, strict: bool = False) -> ProfileLoader:
    """Create a new ``ProfileLoader`` for *profile_path* and install it
    as the module-level singleton.

    Args:
        profile_path: Path to the profile directory.
        strict: When *True*, a config file missing from the profile
            raises :class:`ProfileConfigError` instead of falling back
            to the core defaults.

    Returns:
        The newly created ``ProfileLoader`` instance.
    """
    global _profile
    _profile = ProfileLoader(profile_path, strict=strict)
    return _profile
