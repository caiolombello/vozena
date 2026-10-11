import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("uninstaller", ROOT / "scripts/uninstall.py")
uninstaller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uninstaller)


class UninstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home with spaces"
        self.root = self.home / ".local/share/yeti-voice"
        self.root.mkdir(parents=True)
        (self.root / ".yeti-voz-install.json").write_text(json.dumps({"application": "yeti-voz"}))
        (self.root / "releases").mkdir()
        (self.root / "releases/source.py").write_text("# installed app\n")
        self.launchers = []
        for name in ("vozena", "yeti-voz"):
            path = self.home / ".local/bin" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            self.write_status_launcher(path, False)
            self.launchers.append(path)
        self.desktop = self.home / ".local/share/applications/yeti-voz.desktop"
        self.desktop.parent.mkdir(parents=True)
        self.desktop.write_text("[Desktop Entry]\n" + uninstaller.DESKTOP_MARKER + "\n")
        self.settings = self.home / ".config/yeti-voice/settings.json"
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('{"noise":42}\n')
        self.runtime = self.home / ".local/share/vozena/runtime/owned"
        self.runtime.mkdir(parents=True)
        (self.runtime / "keep").write_text("runtime preserved")

    def tearDown(self):
        self.temp.cleanup()

    def write_status_launcher(self, path, active):
        path.write_text("#!/bin/sh\n" + uninstaller.LAUNCHER_MARKER + "\n"
                        + "printf '%s\\n' '" + json.dumps({"ok": active}) + "'\n"
                        + f"exit {0 if active else 1}\n")
        path.chmod(0o755)

    def test_dry_run_preserves_everything(self):
        paths = uninstaller.uninstall(home=self.home, dry_run=True)
        self.assertEqual(set(paths), {self.root, *self.launchers, self.desktop})
        self.assertTrue(all(path.exists() for path in paths))

    def test_removes_only_owned_app_paths_and_preserves_settings_and_runtime(self):
        sentinel = self.home / ".local/bin/unrelated"
        sentinel.write_text("other app")
        uninstaller.uninstall(home=self.home)
        self.assertFalse(self.root.exists())
        self.assertFalse(any(path.exists() for path in self.launchers))
        self.assertFalse(self.desktop.exists())
        self.assertEqual(self.settings.read_text(), '{"noise":42}\n')
        self.assertEqual((self.runtime / "keep").read_text(), "runtime preserved")
        self.assertEqual(sentinel.read_text(), "other app")

    def test_unowned_root_refuses_all_removal(self):
        (self.root / ".yeti-voz-install.json").unlink()
        with self.assertRaisesRegex(ValueError, "Unowned"):
            uninstaller.uninstall(home=self.home)
        self.assertTrue(self.root.exists())
        self.assertTrue(all(path.exists() for path in self.launchers))

    def test_active_instance_is_refused_without_stopping_it(self):
        self.write_status_launcher(self.launchers[0], True)
        with self.assertRaisesRegex(ValueError, "is open"):
            uninstaller.uninstall(home=self.home)
        self.assertTrue(self.root.exists())
        self.assertTrue(all(path.exists() for path in self.launchers))

    def test_unresponsive_instance_socket_refuses_removal(self):
        socket = self.home / ".cache/yeti-voice/yeti-voz.sock"
        socket.parent.mkdir(parents=True)
        socket.touch()
        with self.assertRaisesRegex(ValueError, "socket remains"):
            uninstaller.uninstall(home=self.home)
        self.assertTrue(self.root.exists())

    def test_unknown_launcher_and_desktop_are_preserved(self):
        self.launchers[0].write_text("other user program\n")
        self.desktop.write_text("[Desktop Entry]\nName=Other app\n")
        uninstaller.uninstall(home=self.home)
        self.assertEqual(self.launchers[0].read_text(), "other user program\n")
        self.assertIn("Other app", self.desktop.read_text())

    def test_symlink_install_root_never_deletes_target(self):
        original = self.root.with_name("original")
        self.root.rename(original)
        self.root.symlink_to(original, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            uninstaller.uninstall(home=self.home)
        self.assertTrue((original / "releases/source.py").exists())

    def test_parent_symlink_outside_home_is_refused(self):
        applications = self.desktop.parent
        outside = Path(self.temp.name) / "outside"
        applications.rename(outside)
        applications.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "escapes"):
            uninstaller.uninstall(home=self.home)
        self.assertTrue((outside / "yeti-voz.desktop").exists())
        self.assertTrue(self.root.exists())


if __name__ == "__main__":
    unittest.main()
