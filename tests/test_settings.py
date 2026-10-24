import math
from pathlib import Path
import tempfile
import unittest

from yeti_voice.settings import Preferences, Settings
from yeti_voice.storage import load_preferences, load_settings, save_preferences, save_settings


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


class PreferencesTests(unittest.TestCase):
    def test_preferences_and_profiles_survive_restart_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            expected = (Preferences(activate_on_launch=True,
                                    previous_default_source="alsa_input.usb-yeti")
                        .with_profile("  Ventilador   ligado ", Settings(90, 30, 1.5))
                        .with_profile("Quarto silencioso", Settings(30, 20, 0.0)))
            save_preferences(expected, path)
            actual, warning = load_preferences(path)
            self.assertIsNone(warning)
            self.assertEqual(actual, expected)
            self.assertEqual([name for name, _ in actual.profiles], ["Ventilador ligado", "Quarto silencioso"])

    def test_profiles_are_replaced_and_removed_by_name(self):
        preferences = Preferences().with_profile("Casa", Settings(50, 20, 0.0))
        preferences = preferences.with_profile("Casa", Settings(60, 25, -1.0))
        self.assertEqual(preferences.profile_map, {"Casa": Settings(60, 25, -1.0)})
        self.assertEqual(preferences.without_profile("Casa").profiles, ())

    def test_profile_names_cannot_hide_built_in_choices(self):
        for name in ("", "   ", "Reuniões", "Personalizado", "x" * 41, None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                Preferences().with_profile(name, Settings())

    def test_missing_and_corrupt_preferences_fall_back_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            self.assertEqual(load_preferences(path), (Preferences(), None))
            path.write_text('{"activate_on_launch": "yes"}')
            preferences, warning = load_preferences(path)
            self.assertEqual(preferences, Preferences())
            self.assertTrue(warning)
            self.assertEqual(path.read_text(), '{"activate_on_launch": "yes"}')
