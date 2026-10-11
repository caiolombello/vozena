#!/usr/bin/env python3
"""Create a deterministic clean source release. Third-party binaries stay upstream."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parent.parent
FILES = ("pyproject.toml", "requirements.lock", "run.sh", "vozena.desktop", "README.md",
         "LICENSE", "THIRD_PARTY_NOTICES.md", "CONTRIBUTING.md", "SECURITY.md", ".gitignore")
TREES = ("yeti_voice", "scripts", "tests", "assets", "site", ".github", "docs")
EXCLUDED_PARTS = {"__pycache__", "node_modules", ".venv", ".deps", ".git", "dist", "artifacts"}
IMAGE_SUFFIXES = {".svg", ".webp", ".png", ".jpg", ".jpeg", ".ico"}
TREE_SUFFIXES = {
    "yeti_voice": {".py"}, "scripts": {".py"}, "tests": {".py"},
    "assets": IMAGE_SUFFIXES,
    "site": IMAGE_SUFFIXES | {".html", ".css", ".js"},
    ".github": {".yml", ".yaml", ".md"}, "docs": {".md"},
}
TREE_FILES = {"scripts/plugins.lock.json", "site/.nojekyll"}


def regular_source_file(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    return (path.is_file() and not path.is_symlink()
            and not any((root / parent).is_symlink() for parent in relative.parents))


def release_files(root: Path):
    for name in FILES:
        path = root / name
        if regular_source_file(root, path):
            yield path
    for name in TREES:
        for path in sorted((root / name).rglob("*")):
            relative = path.relative_to(root)
            hidden = any(part.startswith(".") for part in relative.parts[1:])
            explicitly_allowed = relative.as_posix() in TREE_FILES
            if (regular_source_file(root, path)
                    and not EXCLUDED_PARTS.intersection(relative.parts)
                    and (explicitly_allowed or (not hidden and path.suffix in TREE_SUFFIXES[name]))):
                yield path


def build_release(root: Path, output: Path) -> Path:
    version_source = (root / "yeti_voice/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"$', version_source, re.MULTILINE)
    if not match:
        raise ValueError("A semantic release version is required.")
    version = match.group(1)
    required = ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "requirements.lock",
                "scripts/plugins.lock.json", "scripts/prepare.py")
    for name in required:
        if not regular_source_file(root, root / name):
            raise ValueError(f"Source release requires {name}")
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / f"vozena-{version}-source.tar.gz"
    prefix = f"vozena-{version}"
    with archive_path.open("wb") as target, gzip.GzipFile(fileobj=target, mode="wb", filename="", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for path in sorted(release_files(root)):
                data = path.read_bytes()
                info = tarfile.TarInfo(f"{prefix}/{path.relative_to(root).as_posix()}")
                info.size = len(data)
                info.mode = 0o755 if path.suffix == ".sh" else 0o644
                info.mtime = 0
                archive.addfile(info, io.BytesIO(data))
    (output / "SHA256SUMS").write_text(
        hashlib.sha256(archive_path.read_bytes()).hexdigest() + "  " + archive_path.name + "\n",
        encoding="utf-8",
    )
    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", "--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(build_release(args.root.resolve(), args.output.resolve()))


if __name__ == "__main__":
    main()
