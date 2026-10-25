"""Safe, per-user installation for Yeti Voz.

The live application and bundled PipeWire plugins are copied into immutable
version directories. Only the ``current`` symlink changes during an upgrade.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .plugins import BUNDLED, is_system, verify_system_plugin

MANAGED_MARKER = "# Managed by Yeti Voz installer"
ROOT_MARKER = ".yeti-voz-install.json"
DESKTOP_MARKER = "X-YetiVoz-Managed=true"
DESKTOP_IDENTITY = "Comment=Áudio local para chamadas e reuniões com Blue Yeti"
PLUGIN_PATHS = BUNDLED


@dataclass(frozen=True)
class InstallResult:
    release: Path
    current: Path
    launcher: Path
    desktop_entry: Path


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_fingerprint(source: Path, manifest: dict) -> str:
    digest = hashlib.sha256()
    for tree in (source / "yeti_voice", source / "assets"):
        for path in sorted(tree.rglob("*")):
            if not path.is_file() or path.is_symlink() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            digest.update(path.relative_to(source).as_posix().encode("utf-8") + b"\0")
            digest.update(bytes.fromhex(_hash(path)))
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        path = source / name
        if path.is_file():
            digest.update(name.encode() + b"\0" + bytes.fromhex(_hash(path)))
    for name, relative in PLUGIN_PATHS.items():
        entry = manifest[name]
        pin = ("system:" + entry["path"]).encode() if is_system(entry) else bytes.fromhex(entry["sha256"])
        digest.update(name.encode("ascii") + b"\0" + pin)
    return digest.hexdigest()[:12]


def _validate_dependencies(source: Path) -> dict:
    manifest_path = source / ".deps/manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Manifesto de plugins inválido: {exc}") from exc
    if not isinstance(manifest, dict) or set(manifest) != set(PLUGIN_PATHS):
        raise ValueError("O manifesto precisa declarar RNNoise e LSP.")
    for name, expected_path in PLUGIN_PATHS.items():
        entry = manifest.get(name)
        if is_system(entry):
            try:
                verify_system_plugin(name, entry["path"])
            except (OSError, ValueError) as exc:
                raise ValueError(str(exc)) from exc
            continue
        if not isinstance(entry, dict) or entry.get("path") != expected_path:
            raise ValueError(f"Caminho declarado inválido para o plugin {name}.")
        expected_hash = entry.get("sha256")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise ValueError(f"Hash inválido para o plugin {name}.")
        plugin_path = (source / ".deps" / expected_path).resolve()
        try:
            plugin_path.relative_to((source / ".deps").resolve())
        except ValueError as exc:
            raise ValueError(f"Caminho fora da pasta de plugins: {name}.") from exc
        if not plugin_path.is_file() or _hash(plugin_path) != expected_hash:
            raise ValueError(f"Plugin {name} ausente ou com hash diferente do manifesto.")
    return manifest


def _copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.name == "__pycache__" or path.suffix == ".pyc":
            continue
        target = destination / path.name
        if path.is_dir():
            _copy_tree(path, target)
        elif path.is_file() and not path.is_symlink():
            shutil.copy2(path, target)


def _copy_release(source: Path, staging: Path, manifest: dict, build_id: str) -> None:
    (staging / "yeti_voice").mkdir()
    _copy_tree(source / "yeti_voice", staging / "yeti_voice")
    shutil.copytree(source / "assets", staging / "assets", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        if (source / name).is_file():
            shutil.copy2(source / name, staging / name)
    (staging / ".deps").mkdir()
    shutil.copy2(source / ".deps/manifest.json", staging / ".deps/manifest.json")
    for name, relative in PLUGIN_PATHS.items():
        if is_system(manifest[name]):
            continue  # Provided and licensed by the distribution package.
        plugin = source / ".deps" / relative
        target = staging / ".deps" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plugin, target)
        # Preserve the plugin's license in the installed tree.
        license_source = source / ".deps" / name
        if license_source.is_dir():
            license_target = staging / ".deps" / name
            for candidate in license_source.rglob("*"):
                if candidate.is_file() and ("LICENSE" in candidate.name.upper() or "COPYING" in candidate.name.upper()):
                    relative_path = candidate.relative_to(license_source)
                    target_license = license_target / relative_path
                    target_license.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(candidate, target_license)
    (staging / ".release.json").write_text(
        json.dumps({"application": "yeti-voz", "version": __version__, "build": build_id}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # Verify the copied bytes, rather than trusting the source after the copy.
    for name, relative in PLUGIN_PATHS.items():
        if is_system(manifest[name]):
            continue
        if _hash(staging / ".deps" / relative) != manifest[name]["sha256"]:
            raise ValueError(f"A cópia do plugin {name} falhou na verificação SHA-256.")


def _atomic_text(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _desktop_escape(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$") + '"'


def _desktop_value_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n")


def _known_desktop(path: Path) -> bool:
    if path.is_symlink():
        return False
    if not path.exists():
        return True
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    return DESKTOP_MARKER in text or ("Name=Yeti Voz" in text and DESKTOP_IDENTITY in text)


def _known_launcher(path: Path) -> bool:
    if path.is_symlink():
        return False
    if not path.exists() and not path.is_symlink():
        return True
    try:
        return MANAGED_MARKER in path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False


def install(*, source_dir: Path | str | None = None, home: Path | str | None = None,
            install_root: Path | str | None = None,
            python_executable: Path | str | None = None) -> InstallResult:
    """Install/update into a user-owned data directory without sudo.

    ``install_root`` and ``home`` are injectable for isolated tests. The
    function does not touch the user's configuration or enable autostart.
    """
    source = Path(source_dir) if source_dir is not None else Path(__file__).resolve().parent.parent
    source = source.resolve(strict=True)
    home_path = (Path(home).expanduser() if home is not None else Path.home()).absolute()
    root = Path(install_root) if install_root is not None else home_path / ".local/share/yeti-voice"
    root = root.expanduser().absolute()
    # Preserve the venv's interpreter path: resolving its symlink would lose the venv.
    python = Path(python_executable or sys.executable).expanduser().absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError(f"Interpretador Python indisponível: {python}")
    launcher = home_path / ".local/bin/vozena"
    legacy_launcher = home_path / ".local/bin/yeti-voz"
    desktop = home_path / ".local/share/applications/yeti-voz.desktop"
    manifest = _validate_dependencies(source)

    if root.is_symlink():
        raise FileExistsError(f"Destino da instalação é um link: {root}")
    if root.exists():
        marker_path = root / ROOT_MARKER
        try:
            marker_data = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            marker_data = None
        if not root.is_dir() or not isinstance(marker_data, dict) or marker_data.get("application") != "yeti-voz":
            raise FileExistsError(f"Destino existente não pertence ao instalador Yeti Voz: {root}")
    for candidate in (launcher, legacy_launcher):
        if not _known_launcher(candidate):
            raise FileExistsError(f"Executável existente não pertence ao Vozena: {candidate}")
    if not _known_desktop(desktop):
        raise FileExistsError(f"Atalho existente não pertence ao Yeti Voz: {desktop}")

    releases = root / "releases"
    if releases.is_symlink():
        raise FileExistsError(f"Pasta de versões é um link: {releases}")
    build_id = _source_fingerprint(source, manifest)
    release_name = f"{__version__}-{build_id}"
    release = releases / release_name
    current = root / "current"
    if release.is_symlink():
        raise FileExistsError(f"Versão existente é um link: {release}")
    if current.exists() and not current.is_symlink():
        raise FileExistsError(f"O caminho current não é um link gerenciado: {current}")
    if current.is_symlink():
        old_target = (current.parent / os.readlink(current)).resolve()
        try:
            old_target.relative_to((root / "releases").resolve())
        except ValueError as exc:
            raise FileExistsError("O link current aponta para fora das versões Yeti Voz.") from exc
    releases.mkdir(parents=True, exist_ok=True)

    if not release.exists():
        staging = Path(tempfile.mkdtemp(prefix=f".{__version__}.", dir=releases))
        try:
            _copy_release(source, staging, manifest, build_id)
            os.replace(staging, release)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    else:
        try:
            release_info = json.loads((release / ".release.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FileExistsError(f"Versão existente não pertence ao instalador: {release}") from exc
        if release_info != {"application": "yeti-voz", "version": __version__, "build": build_id}:
            raise FileExistsError(f"Versão existente não pertence ao instalador: {release}")
        if _source_fingerprint(release, manifest) != build_id:
            raise ValueError(f"A versão instalada foi alterada após a cópia: {release}")
        for name, relative in PLUGIN_PATHS.items():
            if is_system(manifest[name]):
                continue
            if not (release / ".deps" / relative).is_file() or _hash(release / ".deps" / relative) != manifest[name]["sha256"]:
                raise ValueError(f"A versão instalada tem o plugin {name} alterado; remova-a manualmente antes de reinstalar.")

    run_content = ('#!/bin/sh\nset -eu\ncd -- "$(dirname -- "$0")"\n'
                   f'exec {shlex.quote(str(python))} -m yeti_voice "$@"\n')
    _atomic_text(release / "run.sh", run_content, 0o755)
    marker = {"application": "yeti-voz", "version": __version__, "build": build_id}
    _atomic_text(root / ROOT_MARKER, json.dumps(marker, sort_keys=True) + "\n", 0o600)
    link_tmp = root / f".current-{os.getpid()}"
    link_tmp.unlink(missing_ok=True)
    link_tmp.symlink_to(Path("releases") / release_name)
    os.replace(link_tmp, current)

    # Use a stable shell launcher; paths with spaces remain one argument.
    launcher_content = f"#!/bin/sh\n{MANAGED_MARKER}\nexec {shlex.quote(str(current / 'run.sh'))} \"$@\"\n"
    _atomic_text(launcher, launcher_content, 0o755)
    _atomic_text(legacy_launcher, launcher_content, 0o755)
    icon = current / "assets/vozena.svg"
    desktop_text = "\n".join([
        "[Desktop Entry]", "Type=Application", "Name=Vozena",
        DESKTOP_IDENTITY,
        f"Exec={_desktop_escape(str(launcher))}", f"Icon={_desktop_value_escape(str(icon))}",
        "Terminal=false", "Categories=AudioVideo;Audio;", "Keywords=Vozena;Yeti;microfone;voz;reuniões;",
        "StartupNotify=true", DESKTOP_MARKER, "Actions=Show;ToggleMute;", "",
        "[Desktop Action Show]", "Name=Abrir Vozena", f"Exec={_desktop_escape(str(launcher))} --show", "",
        "[Desktop Action ToggleMute]", "Name=Alternar silêncio", f"Exec={_desktop_escape(str(launcher))} --toggle-mute", "",
    ])
    _atomic_text(desktop, desktop_text, 0o644)
    return InstallResult(release=release, current=current, launcher=launcher, desktop_entry=desktop)


def main(argv=None) -> int:
    """Run the user installer with concise, actionable output."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Instalar Vozena para este usuário")
    parser.add_argument("--source-dir", type=Path, help="Pasta do projeto (padrão: pasta atual do pacote)")
    parser.add_argument("--home", type=Path, help=argparse.SUPPRESS)
    options = parser.parse_args(argv)
    try:
        result = install(source_dir=options.source_dir, home=options.home)
    except (OSError, ValueError) as error:
        print(f"yeti-voz install: {error}", file=sys.stderr)
        return 1
    print(f"Instalação do Vozena concluída. Inicie pelo menu ou execute: {result.launcher}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
