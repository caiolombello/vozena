#!/usr/bin/env python3
"""Prepare pinned dependencies and install Vozena without starting audio.

No sudo, system package installation, global Python installation or audio graph
changes occur here. Binary plugins come directly from their upstream providers.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import venv
import zipfile

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_MARKER = ".vozena-runtime.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dependency_path(root: Path, relative: str) -> Path:
    base = root / ".deps"
    target = base / relative
    try:
        target.resolve().relative_to(base.resolve())
    except ValueError as error:
        raise ValueError(f"Dependency path escapes .deps: {target}") from error
    return target


def check_platform() -> None:
    release = platform.freedesktop_os_release()
    if (sys.platform != "linux" or release.get("ID") != "fedora"
            or release.get("VERSION_ID") != "44" or platform.machine() != "x86_64"):
        raise ValueError("This bootstrap supports Fedora 44 x86_64 only; other distributions are untested.")
    if sys.version_info < (3, 11):
        raise ValueError("Python 3.11 or newer is required.")
    libc, version = platform.libc_ver()
    if libc != "glibc" or tuple(int(part) for part in version.split(".")) < (2, 43):
        raise ValueError("The pinned Fedora plugin requires glibc >= 2.43.")
    missing = [name for name in ("pipewire", "pw-dump", "pw-cli", "pw-cat", "rpm2cpio", "cpio")
               if not shutil.which(name)]
    if missing:
        raise ValueError("Missing system commands: " + ", ".join(missing)
                         + ". See the Fedora prerequisites in README.md.")


def download(url: str, destination: Path, expected_hash: str) -> Path:
    """Keep existing cache files intact; publish downloads only after validation."""
    if destination.is_symlink():
        raise ValueError(f"Refusing a symlink download target: {destination}")
    if destination.exists():
        if sha256(destination) != expected_hash:
            raise ValueError(f"Existing download has an unexpected hash: {destination}")
        return destination
    if not url.startswith("https://"):
        raise ValueError("Downloads require HTTPS.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".download-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as target, urllib.request.urlopen(url, timeout=60) as response:
            if not response.url.startswith("https://"):
                raise ValueError("Refusing a non-HTTPS redirect.")
            shutil.copyfileobj(response, target)
        if sha256(temporary) != expected_hash:
            raise ValueError(f"Downloaded SHA-256 mismatch: {url}")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def write_verified(destination: Path, payload: bytes, expected_hash: str) -> None:
    if hashlib.sha256(payload).hexdigest() != expected_hash:
        raise ValueError(f"Extracted SHA-256 mismatch: {destination}")
    if destination.is_symlink():
        raise ValueError(f"Refusing a symlink plugin target: {destination}")
    if destination.exists():
        if sha256(destination) != expected_hash:
            raise ValueError(f"Existing dependency has an unexpected hash: {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".plugin-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
        temporary.chmod(0o644)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def archive_member(archive: Path, kind: str, member: str) -> bytes:
    # Never extract whole archives or let archive paths create files.
    if kind == "zip":
        with zipfile.ZipFile(archive) as stream:
            return stream.read(member)
    if kind == "rpm":
        with tempfile.TemporaryFile() as cpio_stream:
            subprocess.run(["rpm2cpio", str(archive)], stdout=cpio_stream, check=True)
            cpio_stream.seek(0)
            result = subprocess.run(["cpio", "--extract", "--to-stdout", "--quiet", member],
                                    stdin=cpio_stream, capture_output=True, check=True)
            return result.stdout
    raise ValueError(f"Unsupported archive format: {kind}")


def plugin_lock(root: Path) -> dict:
    return json.loads((root / "scripts/plugins.lock.json").read_text(encoding="utf-8"))["plugins"]


def manifest_for(lock: dict) -> dict:
    return {name: {key: item[key] for key in ("version", "path", "sha256", "source")}
            for name, item in lock.items()}


def check_plugins(root: Path, *, load: bool = True) -> None:
    lock = plugin_lock(root)
    manifest = json.loads((root / ".deps/manifest.json").read_text(encoding="utf-8"))
    if manifest != manifest_for(lock):
        raise ValueError("Prepared plugin manifest differs from scripts/plugins.lock.json.")
    for item in lock.values():
        for entry in (item, *item["licenses"]):
            path = dependency_path(root, entry["path"])
            if path.is_symlink() or not path.is_file() or sha256(path) != entry["sha256"]:
                raise ValueError(f"Missing or modified dependency: {path}")
        if load:
            ctypes.CDLL(str(dependency_path(root, item["path"])))


def prepare_plugins(root: Path) -> None:
    deps = root / ".deps"
    if deps.is_symlink():
        raise ValueError("Refusing a symlink .deps directory.")
    lock = plugin_lock(root)
    manifest = deps / "manifest.json"
    expected = manifest_for(lock)
    if manifest.is_symlink():
        raise ValueError("Refusing a symlink dependency manifest.")
    if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8")) != expected:
        raise ValueError("Existing dependency manifest differs from the pinned release; preserved.")
    # Validate existing files before downloading anything. Missing files can be
    # prepared, but mismatching user files must never be overwritten.
    complete = manifest.is_file()
    for item in lock.values():
        for entry in (item, *item["licenses"]):
            path = dependency_path(root, entry["path"])
            if path.is_symlink() or (path.exists() and sha256(path) != entry["sha256"]):
                raise ValueError(f"Existing dependency has an unexpected hash or is a symlink: {path}")
            complete = complete and path.is_file()
    if complete:
        check_plugins(root)
        return
    for label, item in lock.items():
        entries = (item, *item["licenses"])
        if all(dependency_path(root, entry["path"]).is_file()
               and sha256(dependency_path(root, entry["path"])) == entry["sha256"]
               for entry in entries):
            continue
        print(f"Preparing {label} from its pinned upstream release...", flush=True)
        archive_info = item["archive"]
        archive = download(archive_info["url"], dependency_path(root, "downloads/" + archive_info["filename"]),
                           archive_info["sha256"])
        write_verified(dependency_path(root, item["path"]), archive_member(archive, archive_info["format"],
                                                        archive_info["member"]), item["sha256"])
        for license_entry in item["licenses"]:
            target = dependency_path(root, license_entry["path"])
            if "url" in license_entry:
                download(license_entry["url"], target, license_entry["sha256"])
            else:
                write_verified(target, archive_member(archive, archive_info["format"],
                                                       license_entry["member"]), license_entry["sha256"])
    if manifest.exists():
        if json.loads(manifest.read_text(encoding="utf-8")) != expected:
            raise ValueError("Existing dependency manifest differs from the pinned release; preserved.")
    else:
        manifest.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    check_plugins(root)


def runtime_dir(root: Path) -> Path:
    pin = sha256(root / "requirements.lock")[:12]
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    return Path.home() / ".local/share/vozena/runtime" / f"py{python_version}-{pin}"


def prepare_environment(root: Path, directory: Path) -> Path:
    """Create a persistent venv in place; never copy or relocate it."""
    directory = directory.expanduser().absolute()
    expected = {"application": "vozena", "requirements_sha256": sha256(root / "requirements.lock"),
                "python": f"{sys.version_info.major}.{sys.version_info.minor}"}
    marker = directory / RUNTIME_MARKER
    if directory.exists():
        try:
            previous = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = None
        if previous != expected or directory.is_symlink():
            raise ValueError(f"Runtime directory is unowned or has different pins; preserved: {directory}")
    else:
        directory.parent.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True, system_site_packages=False).create(directory)
        marker.write_text(json.dumps(expected, sort_keys=True) + "\n", encoding="utf-8")
    python = directory / "bin/python"
    subprocess.run([str(python), "-I", "-m", "pip", "--isolated", "install",
                    "--disable-pip-version-check", "--no-cache-dir", "--require-hashes", "--only-binary=:all:",
                    "--index-url", "https://pypi.org/simple", "-r", str(root / "requirements.lock")], check=True)
    check_environment(python)
    return python


def check_environment(python: Path) -> None:
    subprocess.run([str(python), "-I", "-c",
                    "import PySide6; assert PySide6.__version__ == '6.11.2'; "
                    "from PySide6 import QtCore, QtGui, QtWidgets, QtDBus, QtNetwork"], check=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Source checkout to prepare")
    parser.add_argument("--venv-dir", type=Path, help="Persistent runtime location (never moved/copied)")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--plugins-only", action="store_true", help="Prepare plugins without a runtime or installation")
    actions.add_argument("--check", action="store_true", help="Offline system/plugin/runtime verification; no installation")
    options = parser.parse_args(argv)
    try:
        root = options.root.resolve(strict=True)
        check_platform()
        if options.check:
            check_plugins(root)
            check_environment((options.venv_dir or runtime_dir(root)) / "bin/python")
            print("Pinned plugins and Python runtime verified; no audio was started.")
            return 0
        prepare_plugins(root)
        if options.plugins_only:
            print("Pinned plugins prepared; no audio was started.")
            return 0
        python = prepare_environment(root, options.venv_dir or runtime_dir(root))
        subprocess.run([str(python), "-m", "yeti_voice.install", "--source-dir", str(root)],
                       cwd=root, check=True)
        print("Installation completed; the app was not launched.")
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(f"Vozena preparation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
