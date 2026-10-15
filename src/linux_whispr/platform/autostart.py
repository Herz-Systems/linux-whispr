"""Manage autostart via XDG autostart desktop entry."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from linux_whispr.constants import APP_NAME

logger = logging.getLogger(__name__)

AUTOSTART_DIR = Path.home() / ".config" / "autostart"
DESKTOP_ENTRY_NAME = f"{APP_NAME}.desktop"


def _desktop_string(value: Path | str) -> str:
    """Escape a filesystem path for a Desktop Entry string value."""
    return str(value).replace("\\", "\\\\")


def _desktop_exec(executable: Path) -> str:
    """Quote an Exec argument, then escape it as a Desktop Entry string."""
    value = str(executable)
    for character in ("\\", '"', "`", "$"):
        value = value.replace(character, f"\\{character}")
    value = value.replace("%", "%%")
    return _desktop_string(f'"{value}"')


def _launcher_path() -> Path:
    """Locate the user-local wrapper installed by install.sh."""
    installed_launcher = os.environ.get("LINUX_WHISPR_LAUNCHER")
    if installed_launcher:
        return Path(installed_launcher)

    bin_home = os.environ.get("XDG_BIN_HOME")
    return (Path(bin_home) if bin_home else Path.home() / ".local" / "bin") / APP_NAME


def _desktop_entry_content() -> str:
    launcher_path = _launcher_path()
    launcher = _desktop_exec(launcher_path)
    try_launcher = _desktop_string(launcher_path)
    return f"""\
[Desktop Entry]
Type=Application
Name=LinuxWhispr
Comment=Privacy-first voice dictation for Linux
Exec={launcher}
TryExec={try_launcher}
Icon=linux-whispr
Terminal=false
Categories=Utility;Accessibility;
StartupNotify=false
StartupWMClass=linux-whispr
X-GNOME-Autostart-enabled=true
"""


def enable_autostart() -> None:
    """Install an XDG autostart desktop entry."""
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    entry_path = AUTOSTART_DIR / DESKTOP_ENTRY_NAME
    entry_path.write_text(_desktop_entry_content())
    logger.info("Autostart enabled: %s", entry_path)


def disable_autostart() -> None:
    """Remove the XDG autostart desktop entry."""
    entry_path = AUTOSTART_DIR / DESKTOP_ENTRY_NAME
    if entry_path.exists():
        entry_path.unlink()
        logger.info("Autostart disabled: removed %s", entry_path)
    else:
        logger.debug("Autostart entry not found at %s", entry_path)


def is_autostart_enabled() -> bool:
    """Check if autostart is currently enabled."""
    return (AUTOSTART_DIR / DESKTOP_ENTRY_NAME).exists()
