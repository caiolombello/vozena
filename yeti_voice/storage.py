"""Only this app's three preferences, saved atomically when the user edits them."""

import json
import os
from pathlib import Path
import tempfile

from .settings import Settings


def settings_path():
    directory = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return directory / "yeti-voice" / "settings.json"


def load_settings(path=None):
    path = Path(path) if path is not None else settings_path()
    try:
        return Settings.from_dict(json.loads(path.read_text())), None
    except FileNotFoundError:
        return Settings(), None
    except (OSError, ValueError, TypeError) as error:
        return Settings(), f"Os ajustes salvos não puderam ser lidos. Usando o perfil Reuniões: {error}"


def save_settings(settings, path=None):
    path = Path(path) if path is not None else settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            json.dump(settings.to_dict(), file, ensure_ascii=False, allow_nan=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
