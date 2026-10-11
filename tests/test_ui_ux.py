import os
from array import array
import math
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea

from yeti_voice.settings import Settings
from yeti_voice.desktop import DesktopIntegration
from yeti_voice.ui import MainWindow
from yeti_voice.voice_test import VoiceSample


class FakeController(QObject):
    status_changed = Signal(str)
    running_changed = Signal(bool)
    level_changed = Signal(float)
    device_changed = Signal(str)
    error_occurred = Signal(str)
    active_changed = Signal(bool)
    muted_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.running = False
        self.active = False
        self.muted = False
        self.device_description = "Blue Yeti (teste)"
        self.calls = []

    def start(self, settings):
        self.calls.append(("start", settings))

    def update_settings(self, settings):
        self.calls.append(("update", settings))

    def set_bypass(self, bypass):
        self.calls.append(("bypass", bypass))

    def set_mute(self, muted):
        self.calls.append(("mute", muted))

    def stop(self):
        self.calls.append(("stop",))


class FakeVoiceTest(QObject):
    state_changed = Signal(str)
    progress_changed = Signal(float)
    clip_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self.state = "idle"
        self.has_clip = False
        self.sample = None
        self.calls = []

    def record(self, settings):
        self.calls.append(("record", settings))

    def play(self, mode):
        self.calls.append(("play", mode))

    def cancel(self):
        self.calls.append(("cancel",))

    def clear(self):
        self.calls.append(("clear",))

    def close(self):
        self.calls.append(("close",))


class MainWindowUxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.controller = FakeController()
        self.voice_test = FakeVoiceTest()
        self.saved = []
        self.window = MainWindow(
            self.controller, Settings(), self.saved.append, self.voice_test
        )
        self.window.show()
        QTest.qWait(1)

    def tearDown(self):
        self.window.close()

    def test_pages_match_available_tasks_and_navigation_has_no_side_effects(self):
        self.assertEqual(
            [self.window.pages.tabText(index) for index in range(3)],
            ["Microfone", "Calibrar", "Comparar áudio"],
        )
        self.controller.calls.clear()
        self.voice_test.calls.clear()

        for index in range(3):
            self.window.pages.setCurrentIndex(index)
            QTest.qWait(1)

        self.assertEqual(self.controller.calls, [])
        self.assertEqual(self.voice_test.calls, [])

        without_voice = MainWindow(self.controller, Settings(), self.saved.append)
        self.addCleanup(without_voice.close)
        self.assertEqual(without_voice.pages.count(), 1)
        self.assertEqual(without_voice.pages.tabText(0), "Microfone")

    def test_session_header_and_errors_remain_visible_at_minimum_viewport(self):
        self.window.resize(720, 600)
        self.controller.error_occurred.emit("Falha de teste")
        QTest.qWait(1)

        self.assertFalse(self.window.pages.isAncestorOf(self.window.session_header))
        self.assertFalse(self.window.pages.isAncestorOf(self.window.error_banner))
        for index in range(3):
            self.window.pages.setCurrentIndex(index)
            for widget in (
                self.window.session_header,
                self.window.start_button,
                self.window.mute_button,
                self.window.error_banner,
            ):
                self.assertTrue(widget.isVisible())
                bottom = widget.mapTo(self.window, QPoint(0, 0)).y() + widget.height()
                self.assertLessEqual(bottom, self.window.height())

            page = self.window.pages.widget(index)
            scroll = page if isinstance(page, QScrollArea) else page.findChild(QScrollArea)
            self.assertIsNotNone(scroll)
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)

    def test_external_mute_signal_updates_text_state_and_checked_value(self):
        self.controller.active_changed.emit(True)
        self.controller.running_changed.emit(True)
        self.controller.calls.clear()

        self.controller.muted_changed.emit(True)
        self.assertEqual(self.window.state_label.text(), "Silenciado")
        self.assertEqual(self.window.mute_button.text(), "Reativar microfone")
        self.assertTrue(self.window.mute_button.isChecked())
        self.assertEqual(self.controller.calls, [])

        self.controller.muted_changed.emit(False)
        self.assertEqual(self.window.state_label.text(), "Ativo")
        self.assertEqual(self.window.mute_button.text(), "Silenciar")
        self.assertFalse(self.window.mute_button.isChecked())

    def test_sliders_are_named_for_accessibility_and_gain_uses_half_db_keys(self):
        expected = (
            (self.window.noise_slider, "ruído"),
            (self.window.clarity_slider, "clareza"),
            (self.window.gain_slider, "volume"),
        )
        for slider, word in expected:
            self.assertIn(word, slider.accessibleName().lower())
            self.assertTrue(slider.toolTip())

        before = self.window.gain_slider.value()
        self.window.gain_slider.setFocus()
        QTest.keyClick(self.window.gain_slider, Qt.Key.Key_Right)
        self.assertTrue(self.window.gain_slider.hasFocus())
        self.assertEqual(self.window.gain_slider.value(), before + 1)
        self.assertIn("+0.5 dB", self.window.gain_value.text())

    def test_busy_voice_task_disables_other_starts_and_exposes_global_cancel(self):
        self.window.pages.setCurrentIndex(1)
        self.window.calibration_button.click()
        self.voice_test.state_changed.emit("recording")
        self.voice_test.progress_changed.emit(20)
        self.window.pages.setCurrentIndex(0)

        self.assertFalse(self.window.calibration_button.isEnabled())
        self.assertFalse(self.window.voice_record_button.isEnabled())
        self.assertTrue(self.window.activity_card.isVisible())
        self.assertTrue(self.window.activity_cancel_button.isVisible())
        self.assertIn("silêncio", self.window.calibration_instruction.text().lower())

        self.window.activity_cancel_button.click()
        self.assertEqual(self.voice_test.calls[-1], ("cancel",))

    def test_calibration_failure_after_idle_reports_failed_instead_of_canceled(self):
        self.window.calibration_button.click()
        self.voice_test.state_changed.emit("preparing")
        self.voice_test.state_changed.emit("idle")
        self.voice_test.error_occurred.emit("Não foi possível gravar")
        self.assertIn("falhou", self.window.calibration_status_label.text())
        self.assertEqual(self.window.calibration_instruction.text(), "Não foi possível calibrar")
        self.assertEqual(self.window.error_label.text(), "Não foi possível gravar")
        self.assertFalse(self.window.calibration_apply_button.isEnabled())
        self.assertFalse(self.window.activity_card.isVisible())

    def test_calibration_result_reveals_apply_action_after_resize(self):
        self.window.pages.setCurrentIndex(1)
        self.window.calibration_button.click()
        silence = array("f", [0.001] * (3 * 48_000))
        speech = array("f", (0.1 * math.sin(index / 17) for index in range(7 * 48_000)))
        payload = (silence + speech).tobytes()
        self.voice_test.sample = VoiceSample(payload, payload, Settings())
        self.voice_test.clip_changed.emit(True)
        self.voice_test.state_changed.emit("ready")
        QTest.qWait(1)
        self.window.resize(680, 600)
        QTest.qWait(1)
        viewport = self.window.pages.widget(1).viewport()
        button = self.window.calibration_apply_button
        self.assertTrue(button.isEnabled())
        top = button.mapTo(viewport, QPoint(0, 0)).y()
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(top + button.height(), viewport.height())
        self.assertEqual(self.saved, [])

    def test_error_can_be_dismissed_without_audio_or_configuration_action(self):
        self.controller.calls.clear()
        self.voice_test.calls.clear()
        self.voice_test.error_occurred.emit("Não foi possível gravar")

        self.assertTrue(self.window.error_banner.isVisible())
        self.assertEqual(self.window.error_label.text(), "Não foi possível gravar")
        self.window.dismiss_error_button.click()
        self.assertFalse(self.window.error_banner.isVisible())
        self.assertEqual(self.controller.calls, [])
        self.assertEqual(self.voice_test.calls, [])

    def test_audio_actions_preserve_warning_until_explicitly_dismissed(self):
        self.controller.error_occurred.emit("Microfone desconectado")
        self.window.start_button.click()
        self.window.voice_record_button.click()
        self.voice_test.clip_changed.emit(True)
        self.voice_test.state_changed.emit("ready")
        self.window.voice_original_button.click()
        self.window.calibration_button.click()
        self.assertTrue(self.window.error_banner.isVisible())
        self.assertEqual(self.window.error_label.text(), "Microfone desconectado")

    def test_scrolling_over_unfocused_controls_does_not_change_audio_settings(self):
        self.window.start_button.setFocus()
        before = self.window._settings_from_controls()
        profile = self.window.preset_combo.currentText()
        for control in (self.window.preset_combo, self.window.noise_slider,
                        self.window.clarity_slider, self.window.gain_slider):
            event = QWheelEvent(
                QPointF(10, 10), QPointF(control.mapToGlobal(QPoint(10, 10))),
                QPoint(), QPoint(0, 120), Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False,
            )
            self.app.sendEvent(control, event)
            self.assertFalse(event.isAccepted())
        QTest.qWait(180)
        self.assertEqual(self.window._settings_from_controls(), before)
        self.assertEqual(self.window.preset_combo.currentText(), profile)
        self.assertEqual(self.saved, [])

    def test_keyboard_tab_navigation_reaches_each_adjustment(self):
        self.window.start_button.setFocus()
        reached = set()
        for _ in range(12):
            focused = self.app.focusWidget()
            reached.add(focused)
            QTest.keyClick(focused, Qt.Key.Key_Tab)
        for control in (self.window.preset_combo, self.window.noise_slider,
                        self.window.clarity_slider, self.window.gain_slider):
            self.assertIn(control, reached)

    def test_standard_window_shows_meter_and_signal_without_scrolling(self):
        self.window.resize(900, 780)
        QTest.qWait(1)
        self.assertEqual(self.window.pages.widget(0).verticalScrollBar().maximum(), 0)
        self.assertTrue(self.window.level_meter.isVisible())
        self.assertTrue(self.window.processed_button.isVisible())

    def test_footer_matches_actual_desktop_close_behavior(self):
        for available, expected in ((False, "Fechar encerra o app"), (True, "Fechar → bandeja")):
            desktop = DesktopIntegration(
                self.window, self.controller, self.voice_test, tray_available=available
            )
            try:
                self.assertEqual(self.window.tray_help.text(), expected)
                self.assertTrue(self.window.tray_help.toolTip())
            finally:
                desktop.close()

    def test_live_original_and_treated_selection_is_always_exclusive(self):
        self.controller.active_changed.emit(True)
        self.controller.running_changed.emit(True)

        for button, expected in (
            (self.window.original_button, (True, False)),
            (self.window.original_button, (True, False)),
            (self.window.processed_button, (False, True)),
            (self.window.processed_button, (False, True)),
        ):
            button.click()
            self.assertEqual(
                (
                    self.window.original_button.isChecked(),
                    self.window.processed_button.isChecked(),
                ),
                expected,
            )


if __name__ == "__main__":
    unittest.main()
