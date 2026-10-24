"""Session autostart writes and removes only Vozena's own entry."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yeti_voice import autostart
from yeti_voice.install import MANAGED_MARKER


class AutostartTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.home = Path(self.directory.name)
        self.entry = self.home / ".config/autostart/vozena.desktop"
        self.launcher = self.home / ".local/bin/vozena"
        self.launcher.parent.mkdir(parents=True)
        self.launcher.write_text(f"#!/bin/sh\n{MANAGED_MARKER}\nexec true\n")

    def tearDown(self):
        self.directory.cleanup()

    def test_enabling_starts_the_installed_launcher_in_the_tray(self):
        self.assertEqual(autostart.installed_launcher(self.home), self.launcher)
        autostart.set_autostart(True, launcher=self.launcher, path=self.entry)
        text = self.entry.read_text()
        self.assertIn(f'Exec="{self.launcher}" --background', text)
        self.assertIn(autostart.AUTOSTART_MARKER, text)
        self.assertTrue(autostart.autostart_enabled(self.entry))
        self.assertEqual(self.entry.stat().st_mode & 0o777, 0o644)
        autostart.set_autostart(False, path=self.entry)
        self.assertFalse(self.entry.exists())
        self.assertFalse(autostart.autostart_enabled(self.entry))

    def test_entries_of_other_apps_are_never_touched(self):
        self.entry.parent.mkdir(parents=True)
        self.entry.write_text("[Desktop Entry]\nName=Outro app\n")
        for enabled in (True, False):
            with self.assertRaises(FileExistsError):
                autostart.set_autostart(enabled, launcher=self.launcher, path=self.entry)
        self.assertEqual(self.entry.read_text(), "[Desktop Entry]\nName=Outro app\n")
        self.assertFalse(autostart.autostart_enabled(self.entry))

    def test_source_checkouts_cannot_enable_autostart(self):
        self.launcher.write_text("#!/bin/sh\nexec something-else\n")
        self.assertIsNone(autostart.installed_launcher(self.home))
        with patch.object(autostart, "installed_launcher", return_value=None):
            with self.assertRaises(FileNotFoundError):
                autostart.set_autostart(True, path=self.entry)
        self.assertFalse(self.entry.exists())


if __name__ == "__main__":
    unittest.main()
