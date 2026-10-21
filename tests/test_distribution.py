import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parent.parent


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = script("prepare")
release = script("build_release")


class DistributionTests(unittest.TestCase):
    def test_dependency_parent_symlink_cannot_escape_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            (root / ".deps").mkdir(parents=True)
            outside = Path(directory) / "outside"
            outside.mkdir()
            (root / ".deps/downloads").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "escapes"):
                prepare.dependency_path(root, "downloads/archive.zip")

    def test_platform_rejects_other_distributions_before_downloads(self):
        with patch.object(prepare.platform, "freedesktop_os_release", return_value={"ID": "ubuntu", "VERSION_ID": "24.04"}):
            with self.assertRaisesRegex(ValueError, "Fedora 44 and Ubuntu 26.04 x86_64 only"):
                prepare.check_platform()

    def test_platform_accepts_fedora_44(self):
        with patch.object(prepare.platform, "freedesktop_os_release", return_value={"ID": "fedora", "VERSION_ID": "44"}):
            with patch.object(prepare.platform, "libc_ver", return_value=("glibc", "2.43")):
                prepare.check_platform()

    def test_platform_accepts_ubuntu_26_04(self):
        with patch.object(prepare.platform, "freedesktop_os_release", return_value={"ID": "ubuntu", "VERSION_ID": "26.04"}):
            with patch.object(prepare.platform, "libc_ver", return_value=("glibc", "2.43")):
                prepare.check_platform()

    def test_platform_rejects_older_glibc(self):
        with patch.object(prepare.platform, "freedesktop_os_release", return_value={"ID": "ubuntu", "VERSION_ID": "26.04"}):
            with patch.object(prepare.platform, "libc_ver", return_value=("glibc", "2.39")):
                with self.assertRaisesRegex(ValueError, "glibc >= 2.43"):
                    prepare.check_platform()

    def test_platform_rejects_other_architectures(self):
        with patch.object(prepare.platform, "machine", return_value="aarch64"):
            with patch.object(prepare.platform, "freedesktop_os_release", return_value={"ID": "ubuntu", "VERSION_ID": "26.04"}):
                with self.assertRaisesRegex(ValueError, "x86_64 only"):
                    prepare.check_platform()

    def test_bad_download_cache_is_preserved_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "cached.zip"
            target.write_bytes(b"unrelated user bytes")
            with patch.object(prepare.urllib.request, "urlopen") as request:
                with self.assertRaisesRegex(ValueError, "unexpected hash"):
                    prepare.download("https://example.invalid/archive.zip", target, "0" * 64)
                request.assert_not_called()
            self.assertEqual(target.read_bytes(), b"unrelated user bytes")

    def test_corrupted_download_never_becomes_a_cached_dependency(self):
        import io
        response = io.BytesIO(b"truncated upstream payload")
        response.url = "https://example.invalid/file"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "archive.zip"
            with patch.object(prepare.urllib.request, "urlopen", return_value=response):
                with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                    prepare.download(response.url, target, "0" * 64)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_only_selected_zip_member_is_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plugins.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../../escape", "must not be extracted")
                archive.writestr("linux-rnnoise/ladspa/plugin.so", b"selected")
            payload = prepare.archive_member(path, "zip", "linux-rnnoise/ladspa/plugin.so")
            self.assertEqual(payload, b"selected")
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ["plugins.zip"])

    def test_archive_member_rpm_without_rpm2cpio(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pkg.rpm"
            path.write_bytes(b"dummy")
            # Mock _extract_rpm_payload returning a cpio stream with our member
            with patch.object(prepare.shutil, "which", return_value=None):
                with patch.object(prepare, "_extract_rpm_payload", return_value=b"cpio-stream"):
                    with patch.object(prepare.subprocess, "run") as mock_run:
                        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"extracted-so")
                        payload = prepare.archive_member(path, "rpm", "./usr/lib/plugin.so")
                        self.assertEqual(payload, b"extracted-so")
                        mock_run.assert_called_once_with(
                            ["cpio", "--extract", "--to-stdout", "--quiet", "./usr/lib/plugin.so"],
                            input=b"cpio-stream", capture_output=True, check=True
                        )

    def test_existing_plugin_is_not_overwritten_on_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plugin.so"
            path.write_bytes(b"user data")
            with self.assertRaisesRegex(ValueError, "unexpected hash"):
                prepare.write_verified(path, b"new plugin", hashlib.sha256(b"new plugin").hexdigest())
            self.assertEqual(path.read_bytes(), b"user data")

    def test_unowned_runtime_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.lock").write_text("pins")
            runtime = root / "user-runtime"
            runtime.mkdir()
            (runtime / "keep").write_text("owned by user")
            with self.assertRaisesRegex(ValueError, "unowned"):
                prepare.prepare_environment(root, runtime)
            self.assertEqual((runtime / "keep").read_text(), "owned by user")

    def test_source_archive_is_deterministic_and_excludes_private_and_binary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "checkout"
            for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "requirements.lock",
                         "scripts/plugins.lock.json", "scripts/prepare.py", "run.sh"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("source\n")
            package = root / "yeti_voice"
            package.mkdir()
            (package / "__init__.py").write_text('__version__ = "0.4.0"\n')
            for name in (".deps/plugin.so", ".venv/bin/python", "artifacts/secret.json",
                         "yeti_voice/__pycache__/cached.pyc", "site/node_modules/private/file",
                         "tests/private.wav", "scripts/.env", "assets/plugin.so", "scripts/.env.py"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("excluded\n")
            (root / "tests/symlink.py").symlink_to(root / "README.md")
            outside = Path(directory) / "outside"
            outside.mkdir()
            (outside / "private.svg").write_text("excluded")
            (root / "assets/linked").symlink_to(outside, target_is_directory=True)
            for name in ("assets/icon.svg", "site/app.webp", "site/.nojekyll", ".github/workflows/ci.yml"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("public asset\n")
            output = Path(directory) / "dist"
            archive = release.build_release(root, output)
            first = archive.read_bytes()
            self.assertEqual(first, release.build_release(root, output).read_bytes())
            with tarfile.open(archive) as source:
                names = source.getnames()
                self.assertIn("vozena-0.4.0/scripts/prepare.py", names)
                self.assertIn("vozena-0.4.0/requirements.lock", names)
                self.assertIn("vozena-0.4.0/site/.nojekyll", names)
                self.assertIn("vozena-0.4.0/.github/workflows/ci.yml", names)
                self.assertIn("vozena-0.4.0/assets/icon.svg", names)
                self.assertIn("vozena-0.4.0/site/app.webp", names)
                for excluded in ("tests/private.wav", "scripts/.env", "assets/plugin.so",
                                 "scripts/.env.py", "tests/symlink.py", "assets/linked/private.svg"):
                    self.assertNotIn("vozena-0.4.0/" + excluded, names)
                self.assertTrue(all(not any(part in release.EXCLUDED_PARTS for part in Path(name).parts)
                                    for name in names))
                self.assertEqual(source.getmember("vozena-0.4.0/run.sh").mode, 0o755)
            self.assertEqual((output / "SHA256SUMS").read_text(),
                             hashlib.sha256(first).hexdigest() + "  " + archive.name + "\n")


if __name__ == "__main__":
    unittest.main()
