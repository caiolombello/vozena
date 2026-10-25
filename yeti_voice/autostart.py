"""Optional session autostart through a managed XDG autostart entry.

The entry is the source of truth, so removing it from the desktop's own
autostart settings is reflected in Vozena. Only entries carrying the
marker below are ever rewritten or removed.
https://specifications.freedesktop.org/autostart-spec/latest/
"""

import os
from pathlib import Path

from .install import MANAGED_MARKER, _atomic_text, _desktop_escape, _desktop_value_escape

AUTOSTART_MARKER = "X-Vozena-Autostart=true"


def autostart_path():
    config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return config / "autostart" / "vozena.desktop"


def installed_launcher(home=None):
    """The installer's managed launcher; a source checkout cannot autostart."""
    launcher = (Path(home) if home is not None else Path.home()) / ".local/bin/vozena"
    try:
        if not launcher.is_symlink() and MANAGED_MARKER in launcher.read_text(encoding="utf-8"):
            return launcher
    except (OSError, UnicodeError):
        pass
    return None


def _owned(path):
    try:
        return not path.is_symlink() and AUTOSTART_MARKER in path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False


def autostart_enabled(path=None):
    return _owned(Path(path) if path is not None else autostart_path())


def set_autostart(enabled, *, launcher=None, path=None):
    path = Path(path) if path is not None else autostart_path()
    if path.exists() and not _owned(path):
        raise FileExistsError(f"Já existe uma entrada de início automático que não é do Vozena: {path}")
    if not enabled:
        path.unlink(missing_ok=True)
        return
    launcher = launcher or installed_launcher()
    if launcher is None:
        raise FileNotFoundError("Instale o Vozena para que ele possa iniciar com o sistema.")
    icon = Path(launcher).resolve().parent.parent / "share/yeti-voice/current/assets/vozena.svg"
    _atomic_text(path, "\n".join([
        "[Desktop Entry]", "Type=Application", "Name=Vozena",
        "Comment=Deixa o microfone tratado pronto para reuniões",
        f"Exec={_desktop_escape(str(launcher))} --background",
        f"Icon={_desktop_value_escape(str(icon))}",
        "Terminal=false", "X-GNOME-Autostart-enabled=true", AUTOSTART_MARKER, "",
    ]), 0o644)


class SessionAutostart:
    """The window's view of autostart; injectable for tests."""

    def available(self):
        return installed_launcher() is not None

    def enabled(self):
        return autostart_enabled()

    def set(self, enabled):
        set_autostart(enabled)
