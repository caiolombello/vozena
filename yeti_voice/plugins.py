"""Where the LADSPA plugins come from: pinned copies or the distribution.

Pinned plugins live under .deps and are verified by SHA-256. The LSP plugin
may instead come from the distribution package (lsp-plugins-ladspa), which
the package manager keeps updated. A system plugin is accepted only when
its whole path is root-owned and not writable by others, and when it
exposes every label and control Vozena sets (checked in a separate process).
No Qt imports: scripts/prepare.py uses this module with the system Python.
"""

import json
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
CHECKER = Path(__file__).resolve().with_name("ladspa_check.py")
BUNDLED = {
    "rnnoise": "rnnoise/linux-rnnoise/ladspa/librnnoise_ladspa.so",
    "lsp": "lsp/usr/lib64/ladspa/lsp-plugins-ladspa.so",
}
# Fedora installs LADSPA plugins in lib64, Debian and Ubuntu in lib.
SYSTEM_CANDIDATES = {
    "lsp": ("/usr/lib64/ladspa/lsp-plugins-ladspa.so", "/usr/lib/ladspa/lsp-plugins-ladspa.so",
            "/usr/lib/x86_64-linux-gnu/ladspa/lsp-plugins-ladspa.so"),
}
_verified = {}


def is_system(entry):
    return isinstance(entry, dict) and entry.get("provider") == "system"


def system_entry(path):
    return {"version": "system", "path": str(path), "provider": "system",
            "source": "distribution package lsp-plugins-ladspa"}


def plugin_paths(root=ROOT):
    """Resolved plugin files; bundled locations when nothing is prepared yet."""
    try:
        manifest = json.loads((Path(root) / ".deps/manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    paths = {}
    for name, relative in BUNDLED.items():
        entry = manifest.get(name)
        paths[name] = Path(entry["path"]) if is_system(entry) else Path(root) / ".deps" / relative
    return paths


def _check_secure(path):
    """Root-owned and not group/other-writable, from the file up to /."""
    for current in (path, *path.parents):
        info = current.stat()
        if info.st_uid != 0 or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ValueError(f"{current} pode ser alterado por outros usuários")
    return path.stat()


def verify_system_plugin(name, path, *, python=None):
    """Raise ValueError unless the system plugin is safe and has our controls."""
    from .processing import ladspa_requirements

    path = Path(path)
    if not path.is_absolute():
        raise ValueError(f"Caminho do filtro {name} do sistema precisa ser absoluto")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"Filtro {name} do sistema ausente: {path}")
    info = _check_secure(resolved)
    key = (str(resolved), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    if _verified.get(name) == key:
        return
    required = ladspa_requirements()[name]
    result = subprocess.run([python or sys.executable, "-I", str(CHECKER), str(resolved), json.dumps(required)],
                            capture_output=True, text=True, timeout=20, check=False)
    if result.returncode != 0:
        detail = (result.stderr.strip().splitlines() or ["verificação falhou"])[0]
        raise ValueError(f"O filtro {name} do sistema não é compatível com o Vozena ({detail})")
    _verified[name] = key


def find_system_plugin(name, *, python=None, candidates=None):
    """First compatible system copy of a plugin, or None."""
    for candidate in candidates or SYSTEM_CANDIDATES.get(name, ()):
        path = Path(candidate)
        if not path.exists():
            continue
        try:
            verify_system_plugin(name, path, python=python)
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
        return path
    return None
