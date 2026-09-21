"""
Main entry point for the ISA Data Steward GUI.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from .app import create_app
from .main_window import MainWindow

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import utilities for logging setup
from utils.logging_config import get_logger, setup_logging  # noqa: E402

logger = get_logger(__name__)


def discover_profile_dir(project_root: Path) -> Optional[Path]:
    """Discover the profile directory for the GUI.

    Priority:
    1. --profile CLI argument
    2. ISA_STEWARD_PROFILE environment variable
    3. Any *-profile/ directory in the project root
    """
    # 1. Environment variable
    env = os.environ.get("ISA_STEWARD_PROFILE")
    if env and Path(env).is_dir():
        logger.info("Using profile from ISA_STEWARD_PROFILE env: %s", env)
        return Path(env).resolve()

    # 2. Auto-discover *-profile/ directories
    profile_dirs = sorted(project_root.glob("*-profile"))
    if profile_dirs:
        logger.info("Auto-discovered profile directory: %s", profile_dirs[0])
        return profile_dirs[0].resolve()

    logger.info("No profile directory discovered; using default config/")
    return None


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="ISA Data Steward GUI")
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Path to a profile directory (overrides auto-discovery and ISA_STEWARD_PROFILE env)",
    )
    args = parser.parse_args()

    # Setup logging
    log_level = "INFO"  # Can be loaded from settings
    log_file = Path("isa_steward.log")
    setup_logging(log_level=log_level, log_file=log_file)

    logger.info("Starting ISA Data Steward GUI application...")

    # Discover and activate the profile before creating the app
    project_root = Path(__file__).resolve().parent.parent
    profile_path: Optional[Path] = None

    if args.profile:
        profile_path = Path(args.profile).resolve()
        if not profile_path.is_dir():
            logger.error("Profile directory not found: %s", profile_path)
            sys.exit(1)
        logger.info("Using profile from --profile argument: %s", profile_path)
    else:
        profile_path = discover_profile_dir(project_root)

    if profile_path is not None:
        from utils.config_loader import ProfileConfigError, get_profile, set_profile

        set_profile(str(profile_path))
        logger.info("Profile activated: %s", profile_path)
        try:
            # Force resolution of profile.json (triggers the
            # min_core_version check) and report any config files that
            # had to be served from the core defaults.
            profile = get_profile()
            profile.profile
            profile.log_profile_load_summary()
        except ProfileConfigError as exc:
            logger.error("%s", exc)
            sys.exit(1)

    # Create application
    app = create_app()

    # Create and show main window
    window = MainWindow(app)
    window.show()

    # Run event loop
    logger.info("Application started successfully")
    result = app.exec()
    logger.info(f"Application exited with code: {result}")
    sys.exit(result)


if __name__ == "__main__":
    main()
