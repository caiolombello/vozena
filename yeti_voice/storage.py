"""Vozena's own voice controls and preferences, saved atomically."""

import json
import os
from pathlib import Path
import tempfile

from .settings import Preferences, Settings


def settings_path():
    directory = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return directory / "yeti-voice" / "settings.json"


def preferences_path():
    return settings_path().with_name("preferences.json")


def _write_json(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            json.dump(values, file, ensure_ascii=False, allow_nan=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_settings(path=None):
    path = Path(path) if path is not None else settings_path()
    try:
        return Settings.from_dict(json.loads(path.read_text())), None
    except FileNotFoundError:
        return Settings(), None
    except (OSError, ValueError, TypeError) as error:
        return Settings(), f"Os ajustes salvos não puderam ser lidos. Usando o perfil Reuniões: {error}"


def save_settings(settings, path=None):
    _write_json(Path(path) if path is not None else settings_path(), settings.to_dict())


def load_preferences(path=None):
    path = Path(path) if path is not None else preferences_path()
    try:
        return Preferences.from_dict(json.loads(path.read_text())), None
    except FileNotFoundError:
        return Preferences(), None
    except (OSError, ValueError, TypeError) as error:
        return Preferences(), f"As preferências salvas não puderam ser lidas e foram ignoradas: {error}"


def save_preferences(preferences, path=None):
    _write_json(Path(path) if path is not None else preferences_path(), preferences.to_dict())
