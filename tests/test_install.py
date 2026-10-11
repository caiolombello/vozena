import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from yeti_voice.install import PLUGIN_PATHS, install


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.home = self.base / "home with spaces"
        self.source = self.base / "source tree"
        (self.source / "yeti_voice").mkdir(parents=True)
        (self.source / "yeti_voice/__main__.py").write_text("# app\n")
        (self.source / "assets").mkdir()
        (self.source / "assets/vozena.svg").write_text("<svg/>\n")
        manifest = {}
        for name, relative in PLUGIN_PATHS.items():
            payload = f"binary-{name}".encode()
            plugin = self.source / ".deps" / relative
            plugin.parent.mkdir(parents=True, exist_ok=True)
            plugin.write_bytes(payload)
            lic = self.source / ".deps" / name / ("COPYING" if name == "lsp" else "LICENSE")
            lic.parent.mkdir(parents=True, exist_ok=True)
            lic.write_text(f"license {name}\n")
            manifest[name] = {"path": relative, "sha256": hashlib.sha256(payload).hexdigest()}
        manifest_path = self.source / ".deps/manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest))

    def tearDown(self):
        self.temp.cleanup()

    def test_install_is_self_contained_atomic_and_preserves_user_settings(self):
        config = self.home / ".config/yeti-voice/settings.json"
        config.parent.mkdir(parents=True)
        config.write_text('{"noise": 42}\n')
        root = self.home / ".local/share/yeti-voice"
        result = install(source_dir=self.source, home=self.home)

        self.assertEqual(result.current, root / "current")
        self.assertEqual(result.current.resolve(), result.release)
        self.assertTrue((result.release / "yeti_voice/__main__.py").is_file())
        self.assertTrue((result.release / "assets/vozena.svg").is_file())
        self.assertTrue((result.release / ".deps/rnnoise/LICENSE").is_file())
        self.assertTrue((result.release / ".deps/lsp/COPYING").is_file())
        self.assertFalse((result.release / ".deps/downloads").exists())
        self.assertFalse((result.release / "tests").exists())
        self.assertEqual(config.read_text(), '{"noise": 42}\n')
        self.assertIn("--toggle-mute", result.desktop_entry.read_text())
        self.assertIn("--show", result.desktop_entry.read_text())
        self.assertIn('"' + str(result.launcher) + '"', result.desktop_entry.read_text())
        self.assertIn("home with spaces", result.launcher.read_text())
        self.assertEqual(result.launcher.name, "vozena")
        self.assertEqual((self.home / ".local/bin/yeti-voz").read_text(), result.launcher.read_text())

        # A repeat install is idempotent and preserves the same release.
        repeated = install(source_dir=self.source, home=self.home)
        self.assertEqual(repeated.release, result.release)
        self.assertEqual(repeated.current.resolve(), result.release)

    def test_rejects_unowned_install_root_without_touching_it(self):
        root = self.home / ".local/share/yeti-voice"
        root.mkdir(parents=True)
        sentinel = root / "keep.txt"
        sentinel.write_text("owned by someone else")
        with self.assertRaises(FileExistsError):
            install(source_dir=self.source, home=self.home)
        self.assertEqual(sentinel.read_text(), "owned by someone else")

    def test_rejects_unowned_launcher(self):
        launcher = self.home / ".local/bin/yeti-voz"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("user program\n")
        with self.assertRaises(FileExistsError):
            install(source_dir=self.source, home=self.home)
        self.assertEqual(launcher.read_text(), "user program\n")

    def test_source_change_promotes_new_immutable_release(self):
        first = install(source_dir=self.source, home=self.home)
        (self.source / "yeti_voice/__main__.py").write_text("# updated app\n")
        second = install(source_dir=self.source, home=self.home)
        self.assertNotEqual(first.release, second.release)
        self.assertTrue(first.release.is_dir())
        self.assertEqual(second.current.resolve(), second.release)

    def test_rejects_tampered_application_files_on_idempotent_reuse(self):
        first = install(source_dir=self.source, home=self.home)
        (first.release / "yeti_voice/__main__.py").write_text("# tampered\n")
        with self.assertRaisesRegex(ValueError, "alterada após a cópia"):
            install(source_dir=self.source, home=self.home)

    def test_module_entrypoint_reports_launcher_and_concise_failure(self):
        command = [sys.executable, "-m", "yeti_voice.install", "--source-dir", str(self.source), "--home", str(self.home)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.home / ".local/bin/vozena"), result.stdout)
        self.assertNotIn("Traceback", result.stderr)

        other_home = self.base / "other home"
        root = other_home / ".local/share/yeti-voice"
        root.mkdir(parents=True)
        (root / "keep.txt").write_text("unowned")
        failed_command = [sys.executable, "-m", "yeti_voice.install", "--source-dir", str(self.source), "--home", str(other_home)]
        failed = subprocess.run(failed_command, capture_output=True, text=True, check=False)
        self.assertEqual(failed.returncode, 1)
        self.assertIn("yeti-voz install:", failed.stderr)
        self.assertNotIn("Traceback", failed.stderr)

    def test_rejects_unowned_desktop_entry(self):
        desktop = self.home / ".local/share/applications/yeti-voz.desktop"
        desktop.parent.mkdir(parents=True)
        desktop.write_text("[Desktop Entry]\nName=Other app\n")
        with self.assertRaises(FileExistsError):
            install(source_dir=self.source, home=self.home)
        self.assertIn("Other app", desktop.read_text())

    def test_bad_plugin_hash_never_promotes_a_release(self):
        bad = self.source / ".deps" / PLUGIN_PATHS["rnnoise"]
        bad.write_bytes(b"changed")
        root = self.home / ".local/share/yeti-voice"
        with self.assertRaisesRegex(ValueError, "hash diferente"):
            install(source_dir=self.source, home=self.home)
        self.assertFalse((root / "current").exists())
        self.assertFalse((root / "releases").exists())

    def test_runtime_interpreter_with_spaces_survives_source_removal(self):
        runtime = self.base / "runtime with spaces"
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(runtime)], check=True)
        python = runtime / "bin/python"
        (self.source / "yeti_voice/__main__.py").write_text("import sys\nprint(sys.prefix)\n")
        result = install(source_dir=self.source, home=self.home, python_executable=python)
        import shutil
        shutil.rmtree(self.source)
        completed = subprocess.run([str(result.launcher)], capture_output=True, text=True, check=True)
        self.assertEqual(completed.stdout.strip(), str(runtime))
        self.assertIn(str(python), (result.release / "run.sh").read_text())

    def test_unowned_primary_launcher_is_preserved_before_installation(self):
        launcher = self.home / ".local/bin/vozena"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("other application\n")
        with self.assertRaises(FileExistsError):
            install(source_dir=self.source, home=self.home)
        self.assertEqual(launcher.read_text(), "other application\n")
        self.assertFalse((self.home / ".local/share/yeti-voice").exists())

    def test_symlinked_release_directory_is_preserved(self):
        first = install(source_dir=self.source, home=self.home)
        outside = self.base / "outside"
        outside.mkdir()
        import shutil
        shutil.rmtree(first.release.parent)
        first.release.parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(FileExistsError):
            install(source_dir=self.source, home=self.home)
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
