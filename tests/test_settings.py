import math
from pathlib import Path
import tempfile
import unittest

from yeti_voice.settings import Settings
from yeti_voice.storage import load_settings, save_settings


class SettingsTests(unittest.TestCase):
    def test_saved_controls_survive_restart_without_touching_other_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            neighbor = Path(directory) / "other-app.json"
            neighbor.write_text("protected")
            expected = Settings(85, 42, -2.5)
            save_settings(expected, path)
            actual, warning = load_settings(path)
            self.assertEqual(actual, expected)
            self.assertIsNone(warning)
            self.assertEqual(neighbor.read_text(), "protected")

    def test_corrupt_saved_controls_are_preserved_and_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"noise":200}')
            actual, warning = load_settings(path)
            self.assertEqual(actual, Settings())
            self.assertTrue(warning)
            self.assertEqual(path.read_text(), '{"noise":200}')

    def test_invalid_gain_and_noise_are_rejected(self):
        for values in ({"noise":-1}, {"noise":True}, {"clarity":101},
                       {"gain_db":math.nan}, {"gain_db":math.inf}, {"gain_db":7}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Settings.from_dict(values)
