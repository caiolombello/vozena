#!/usr/bin/env python3
"""Remove only a managed Vozena installation; preserve settings and Python runtime."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

LAUNCHER_MARKER = "# Managed by Yeti Voz installer"
DESKTOP_MARKER = "X-YetiVoz-Managed=true"
AUTOSTART_MARKER = "X-Vozena-Autostart=true"


def contained(path: Path, home: Path) -> None:
    try:
        path.resolve().relative_to(home.resolve())
    except ValueError as error:
        raise ValueError(f"Managed path escapes the selected home: {path}") from error
    if path.is_symlink():
        raise ValueError(f"Refusing a symlink managed path: {path}")


def marked_file(path: Path, marker: str, home: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    contained(path, home)
    return path.is_file() and marker in path.read_text(encoding="utf-8")


def uninstall(*, home: Path | None = None, dry_run: bool = False) -> list[Path]:
    custom_home = home is not None
    home = (home or Path.home()).expanduser().absolute()
    root = home / ".local/share/yeti-voice"
    planned = []
    if root.exists() or root.is_symlink():
        contained(root, home)
        try:
            marker = json.loads((root / ".yeti-voz-install.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Unowned installation directory; preserved: {root}") from error
        if not isinstance(marker, dict) or marker.get("application") != "yeti-voz":
            raise ValueError(f"Unowned installation directory; preserved: {root}")
        planned.append(root)
    launchers = [home / ".local/bin" / name for name in ("vozena", "yeti-voz")]
    owned_launchers = [path for path in launchers if marked_file(path, LAUNCHER_MARKER, home)]
    planned.extend(owned_launchers)
    desktop = home / ".local/share/applications/yeti-voz.desktop"
    if marked_file(desktop, DESKTOP_MARKER, home):
        planned.append(desktop)
    config = home / ".config" if custom_home else Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))
    # A login entry pointing at a removed launcher would fail at every login.
    autostart = config / "autostart/vozena.desktop"
    if marked_file(autostart, AUTOSTART_MARKER, home):
        planned.append(autostart)
    if not planned:
        return []
    if not owned_launchers:
        raise ValueError("No managed launcher can verify instance status; installation preserved.")
    environment = dict(os.environ, HOME=str(home))
    if custom_home:
        environment.pop("XDG_RUNTIME_DIR", None)
    result = subprocess.run([str(owned_launchers[0]), "--status"], capture_output=True,
                            text=True, timeout=5, check=False, env=environment)
    try:
        status = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("Cannot verify instance status; installation preserved.") from error
    if not isinstance(status, dict) or type(status.get("ok")) is not bool:
        raise ValueError("Cannot verify instance status; installation preserved.")
    if status["ok"]:
        raise ValueError("Vozena is open. Close the app before uninstalling; no process was stopped.")
    if result.returncode != 1:
        raise ValueError("Unexpected instance status; installation preserved.")
    socket_dir = Path(environment.get("XDG_RUNTIME_DIR", str(home / ".cache/yeti-voice")))
    if (socket_dir / "yeti-voz.sock").exists():
        raise ValueError("Instance socket remains but status is unavailable; installation preserved.")
    if not dry_run:
        for path in planned:
            if path == root:
                shutil.rmtree(path)
            else:
                path.unlink()
    return planned


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview removal without changing files")
    parser.add_argument("--home", type=Path, help=argparse.SUPPRESS)
    options = parser.parse_args(argv)
    try:
        paths = uninstall(home=options.home, dry_run=options.dry_run)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Vozena uninstall failed: {error}", file=sys.stderr)
        return 1
    for path in paths:
        print(f"{'Would remove' if options.dry_run else 'Removed'}: {path}")
    print("Settings and the Python runtime were preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
