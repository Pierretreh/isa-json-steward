"""
Application setup for the ISA Data Steward GUI.
"""

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QByteArray, QSettings, Qt
from PyQt6.QtWidgets import QApplication

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.config_loader import get_profile  # noqa: E402

from .agent_tools.crash import StewardNotifyMixin  # noqa: E402


class StewardApp(StewardNotifyMixin, QApplication):
    """Main application class for the ISA Data Steward GUI.

    Mixes in :class:`~gui.agent_tools.crash.StewardNotifyMixin` (P1-1): once
    ``install_crash_hooks()`` is called (see ``gui/main.py``), exceptions
    escaping Qt event dispatch are captured as crash bundles instead of
    aborting the process (see gui/agent_tools/crash.py for details).
    """

    def __init__(self, argv):
        super().__init__(argv)
        profile = get_profile()
        app_name = profile.profile.get("app_name", "ISA-JSON Data Steward")
        org_name = profile.profile.get("project", "ISA Data Steward")
        self.setApplicationName(app_name)
        self.setApplicationVersion("2.0.0")
        self.setOrganizationName(org_name)

        # Load settings
        self.settings = QSettings(org_name, "DataSteward")

        # Apply theme
        self.apply_theme()

        # Set default font
        self.setup_fonts()

    def apply_theme(self, theme: Optional[str] = None, persist: bool = False) -> None:
        """Apply a theme stylesheet (U-06: session-only unless asked to persist).

        Args:
            theme: ``"light"`` / ``"dark"`` (any shipped ``<name>.qss``);
                ``None`` keeps the theme currently configured in the settings.
            persist: when *True*, write ``gui/theme`` to :class:`QSettings` as
                the user's preference (the settings-page theme combo is the
                persisting caller).  Defaults to *False*: applying a theme is
                session-only and never rewrites user preferences
                (AGENTS.md section 8.1).
        """
        if theme is None:
            theme = self.settings.value("gui/theme", "light", str)
        if persist:
            self.settings.setValue("gui/theme", theme)

        # Load stylesheet
        style_path = Path(__file__).parent / "resources" / "styles" / f"{theme}.qss"
        if style_path.exists():
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def setup_fonts(self) -> None:
        """Set up application fonts."""
        from PyQt6.QtGui import QFont

        # Set default font family
        font_family = self.settings.value("gui/font_family", "Segoe UI", str)
        font_size = self.settings.value("gui/font_size", 10, int)

        font = QFont(font_family, font_size)
        self.setFont(font)

    def set_theme(self, theme: str) -> None:
        """Set application theme and persist it as the user's preference.

        Explicit user choice (settings-page theme combo); tooling that only
        needs a session theme uses ``apply_theme(theme, persist=False)``.
        """
        self.apply_theme(theme, persist=True)

    def get_current_investigation(self) -> str:
        """Get current investigation ID."""
        return str(self.settings.value("current/investigation", "", str))

    def set_current_investigation(self, investigation_id: str) -> None:
        """Set current investigation ID."""
        self.settings.setValue("current/investigation", investigation_id)

    def get_current_study(self) -> str:
        """Get current study ID."""
        return str(self.settings.value("current/study", "", str))

    def set_current_study(self, study_id: str) -> None:
        """Set current study ID."""
        self.settings.setValue("current/study", study_id)

    def get_window_geometry(self) -> bytes:
        """Get saved window geometry."""
        # Use QByteArray as type hint (PyQt6 stores geometry as QByteArray)
        geometry = self.settings.value("gui/geometry", QByteArray(), QByteArray)
        # Convert QByteArray to bytes for compatibility
        return bytes(geometry.data()) if geometry else b""

    def set_window_geometry(self, geometry: bytes) -> None:
        """Save window geometry."""
        # Convert bytes to QByteArray for storage
        self.settings.setValue("gui/geometry", QByteArray(geometry))

    def get_window_state(self) -> bytes:
        """Get saved window state."""
        # Use QByteArray as type hint (PyQt6 stores state as QByteArray)
        state = self.settings.value("gui/state", QByteArray(), QByteArray)
        # Convert QByteArray to bytes for compatibility
        return bytes(state.data()) if state else b""

    def set_window_state(self, state: bytes) -> None:
        """Save window state."""
        # Convert bytes to QByteArray for storage
        self.settings.setValue("gui/state", QByteArray(state))


def create_app() -> StewardApp:
    """Create and return application instance."""
    app = StewardApp(sys.argv)

    # Enable high DPI scaling
    app.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    return app
