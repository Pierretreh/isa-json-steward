"""Default configuration package for ISA-JSON Data Steward.

This package bundles the default JSON configuration files (settings,
profiles, marker panels, naming conventions, and extraction rules) so
they are shipped inside the wheel and resolved at runtime relative to
the installed location.

These files are read by :mod:`utils.config_loader` and
:mod:`utils.directory_manager`; users may override them via profile
directories without modifying this package.
"""
