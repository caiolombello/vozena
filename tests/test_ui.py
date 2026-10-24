import os
from array import array
import math
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from yeti_voice.processing import OUTPUT_NODE
from yeti_voice.settings import Preferences, Settings
from yeti_voice.ui import MainWindow


class FakeController(QObject):
    status_changed = Signal(str)
    running_changed = Signal(bool)
    level_changed = Signal(float)
    device_changed = Signal(str)
    error_occurred = Signal(str)
    active_changed = Signal(bool)
    muted_changed = Signal(bool)
    consumers_changed = Signal(list)
    default_source_changed = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self.running = False
        self.active = False
        self.muted = False
        self.device_description = "Blue Yeti (teste)"
        self.calls = []
        self.meter_wanted = []

    def start(self, settings):
        self.calls.append(("start", settings))

    def update_settings(self, settings):
        self.calls.append(("update", settings))

    def set_bypass(self, bypass):
        self.calls.append(("bypass", bypass))

    def set_mute(self, muted):
        self.calls.append(("mute", muted))

    def set_suspended(self, suspended):
        self.calls.append(("suspended", suspended))

    def set_meter_wanted(self, wanted):
        self.meter_wanted.append(wanted)

    def set_default_source(self, name):
        self.calls.append(("default_source", name))
        return True

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


class MainWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.controller = FakeController()
        self.saved = []
        self.window = MainWindow(self.controller, Settings(), self.saved.append)

    def tearDown(self):
        self.window.close()

    def enable_voice_test(self):
        self.window.close()
        self.controller.calls.clear()
        self.voice_test = FakeVoiceTest()
        self.window = MainWindow(
            self.controller,
            Settings(),
            self.saved.append,
            self.voice_test,
        )

    def test_meeting_card_shows_which_app_receives_the_processed_voice(self):
        self.assertIn("Ative o tratamento", self.window.destination_detail.text())
        self.assertFalse(self.window.default_source_button.isEnabled())
        self.controller.running_changed.emit(True)
        self.assertIn("Nenhum app", self.window.destination_detail.text())
        self.controller.consumers_changed.emit(["Google Chrome", "ZOOM VoiceEngine"])
        self.assertEqual(self.window.destination_title.text(), "Em uso: Google Chrome, ZOOM VoiceEngine")
        self.assertEqual(self.window.destination_card.property("tone"), "inUse")
        self.controller.running_changed.emit(False)
        self.assertEqual(self.window.destination_title.text(), "Selecione Yeti Processado como microfone")

    def test_processed_microphone_can_become_default_and_be_restored(self):
        saved = []
        self.window.close()
        self.window = MainWindow(self.controller, Settings(), self.saved.append,
                                 preferences=Preferences(), save_preferences=saved.append)
        self.controller.default_source_changed.emit(False, "alsa_input.usb-yeti")
        self.controller.running_changed.emit(True)
        self.window.default_source_button.click()
        self.assertEqual(self.controller.calls[-1], ("default_source", OUTPUT_NODE))
        self.assertEqual(saved[-1].previous_default_source, "alsa_input.usb-yeti")
        self.controller.default_source_changed.emit(True, OUTPUT_NODE)
        self.assertEqual(self.window.default_source_button.text(), "Restaurar microfone anterior")
        self.assertIn("microfone padrão do sistema", self.window.destination_detail.text())
        self.controller.running_changed.emit(False)
        self.assertTrue(self.window.default_source_button.isEnabled())
        self.window.default_source_button.click()
        self.assertEqual(self.controller.calls[-1], ("default_source", "alsa_input.usb-yeti"))
        self.assertEqual(saved[-1].previous_default_source, "")

    def test_autostart_toggle_writes_through_and_reflects_failures(self):
        class Autostart:
            def __init__(self, available=True):
                self.state, self._available, self.fail = False, available, False
            def available(self):
                return self._available
            def enabled(self):
                return self.state
            def set(self, enabled):
                if self.fail:
                    raise FileExistsError("entrada de outro app")
                self.state = enabled
        autostart = Autostart()
        self.window.close()
        self.window = MainWindow(self.controller, Settings(), self.saved.append, autostart=autostart)
        self.window.autostart_check.click()
        self.assertTrue(autostart.state)
        self.assertTrue(self.window.autostart_check.isChecked())
        autostart.fail = True
        self.window.autostart_check.click()
        self.assertTrue(self.window.autostart_check.isChecked())
        self.assertIn("entrada de outro app", self.window.error_label.text())
        self.window.close()
        self.window = MainWindow(self.controller, Settings(), self.saved.append, autostart=Autostart(False))
        self.assertFalse(self.window.autostart_check.isEnabled())
        self.assertIn("instalado", self.window.autostart_help.text())

    def test_activation_on_launch_waits_for_the_yeti(self):
        saved = []
        self.controller.device_description = ""
        self.window.close()
        self.window = MainWindow(self.controller, Settings(40, 15, 0.0), self.saved.append,
                                 preferences=Preferences(activate_on_launch=True), save_preferences=saved.append)
        self.assertTrue(self.window.activate_check.isChecked())
        self.window.activate_when_ready()
        self.assertFalse(any(call[0] == "start" for call in self.controller.calls))
        self.assertIn("quando o Blue Yeti for conectado", self.window.status_label.text())
        self.controller.device_changed.emit("Yeti Stereo Microphone")
        self.assertEqual(self.controller.calls[-1], ("start", Settings(40, 15, 0.0)))
        self.controller.device_changed.emit("")
        self.controller.device_changed.emit("Yeti Stereo Microphone")
        self.assertEqual(sum(call[0] == "start" for call in self.controller.calls), 1)
        self.window.activate_check.click()
        self.assertFalse(saved[-1].activate_on_launch)

    def test_level_meter_follows_window_visibility(self):
        self.assertEqual(self.controller.meter_wanted, [False])
        self.window.show()
        QTest.qWait(20)
        self.window.setWindowState(Qt.WindowState.WindowMinimized)
        QTest.qWait(20)
        self.window.setWindowState(Qt.WindowState.WindowNoState)
        self.window.show()
        QTest.qWait(20)
        self.window.hide()
        self.assertEqual(self.controller.meter_wanted[0], False)
        self.assertIn(True, self.controller.meter_wanted)
        self.assertEqual(self.controller.meter_wanted[-1], False)
        minimized_index = self.controller.meter_wanted.index(True) + 1
        self.assertFalse(self.controller.meter_wanted[minimized_index])

    def test_starts_paused_and_requests_activation(self):
        self.assertEqual(self.window.state_label.text(), "Pausado")
        self.assertFalse(self.window.original_button.isEnabled())

        self.window.start_button.click()

        self.assertEqual(self.controller.calls[-1], ("start", Settings()))

    def test_paused_controls_sync_settings_without_starting_audio(self):
        self.window.noise_slider.setValue(71)
        QTest.qWait(180)
        self.assertEqual(self.saved, [Settings(71, 35, 0.0)])
        self.assertEqual(self.controller.calls, [("update", self.saved[-1])])
        self.assertFalse(any(call[0] == "start" for call in self.controller.calls))

    def test_controls_changed_during_activation_reach_controller(self):
        self.window.start_button.click()
        self.window.noise_slider.setValue(95)
        QTest.qWait(180)

        self.assertEqual(self.controller.calls[0], ("start", Settings()))
        self.assertEqual(
            self.controller.calls[-1],
            ("update", Settings(95, 35, 0.0)),
        )

    def test_live_controls_are_debounced_while_running(self):
        self.controller.running = True
        self.controller.running_changed.emit(True)
        self.window.gain_slider.setValue(1)
        QTest.qWait(180)
        self.assertEqual(self.saved[-1], Settings(70, 35, 0.5))
        self.assertEqual(self.controller.calls[-1], ("update", self.saved[-1]))

    def test_controller_signals_drive_meter_and_stop_resets_it(self):
        self.controller.running_changed.emit(True)
        self.controller.level_changed.emit(-0.5)
        self.assertEqual(self.window.level_label.text(), "-0.5 dBFS")
        self.assertFalse(self.window.saturation_label.isHidden())

        self.controller.running_changed.emit(False)
        self.assertEqual(self.window.level_meter.value(), 0)
        self.assertEqual(self.window.level_label.text(), "— dBFS")
        self.assertTrue(self.window.saturation_label.isHidden())

    def test_compare_mute_and_close_delegate_to_controller(self):
        self.controller.active = True
        self.controller.active_changed.emit(True)
        self.controller.running_changed.emit(True)
        self.window.original_button.click()
        self.window.mute_button.click()
        self.assertIn(("bypass", True), self.controller.calls)
        self.assertIn(("mute", True), self.controller.calls)

        self.window.close()
        self.assertEqual(self.controller.calls[-1], ("stop",))

    def test_voice_test_starts_idle_without_listening_actions(self):
        self.enable_voice_test()

        self.assertTrue(self.window.voice_record_button.isEnabled())
        self.assertFalse(self.window.voice_original_button.isEnabled())
        self.assertFalse(self.window.voice_processed_button.isEnabled())
        self.assertFalse(self.window.voice_cancel_button.isEnabled())
        self.assertFalse(self.window.voice_clear_button.isEnabled())

    def test_voice_record_uses_current_slider_values_before_debounce(self):
        self.enable_voice_test()
        self.window.noise_slider.setValue(91)
        self.window.gain_slider.setValue(-3)

        self.window.voice_record_button.click()

        self.assertEqual(
            self.voice_test.calls[-1],
            ("record", Settings(91, 35, -1.5)),
        )

    def test_voice_clip_enables_listening_and_clear(self):
        self.enable_voice_test()
        self.voice_test.has_clip = True
        self.voice_test.clip_changed.emit(True)
        self.voice_test.state = "ready"
        self.voice_test.state_changed.emit("ready")

        self.assertTrue(self.window.voice_original_button.isEnabled())
        self.assertTrue(self.window.voice_processed_button.isEnabled())
        self.assertTrue(self.window.voice_clear_button.isEnabled())
        self.assertFalse(self.window.voice_snapshot_label.isHidden())
        self.window.voice_original_button.click()
        self.window.voice_processed_button.click()
        self.window.voice_clear_button.click()

        self.assertIn(("play", "original"), self.voice_test.calls)
        self.assertIn(("play", "processed"), self.voice_test.calls)
        self.assertEqual(self.voice_test.calls[-1], ("clear",))

    def test_voice_progress_and_active_states_offer_cancel(self):
        self.enable_voice_test()
        self.voice_test.state = "recording"
        self.voice_test.state_changed.emit("recording")
        self.voice_test.progress_changed.emit(30)

        self.assertEqual(self.window.voice_progress.value(), 30)
        self.assertEqual(self.window.voice_time_label.text(), "7 s restantes")
        self.assertTrue(self.window.voice_cancel_button.isEnabled())
        self.window.voice_cancel_button.click()
        self.assertEqual(self.voice_test.calls[-1], ("cancel",))

        self.voice_test.state = "playing_processed"
        self.voice_test.state_changed.emit("playing_processed")
        self.assertEqual(self.window.voice_cancel_button.text(), "Parar")

    def test_voice_failure_is_visible_and_close_stops_both_controllers(self):
        self.enable_voice_test()
        self.voice_test.error_occurred.emit("Falha no teste de voz")
        self.assertEqual(self.window.error_label.text(), "Falha no teste de voz")
        self.assertFalse(self.window.error_label.isHidden())

        self.window.close()
        self.assertEqual(self.controller.calls[-1], ("stop",))
        self.assertEqual(self.voice_test.calls[-1], ("close",))

    def test_active_intent_survives_recovery_and_mute_comes_from_controller(self):
        self.controller.active = True
        self.controller.active_changed.emit(True)
        self.controller.muted = True
        self.controller.muted_changed.emit(True)
        self.controller.running_changed.emit(False)

        self.assertEqual(self.window.state_label.text(), "Reconectando…")
        self.assertEqual(self.window.start_button.text(), "Parar tratamento")
        self.assertTrue(self.window.mute_button.isEnabled())
        self.assertTrue(self.window.mute_button.isChecked())
        self.window.start_button.click()
        self.assertEqual(self.controller.calls[-1], ("stop",))

    def test_voice_operations_never_control_the_live_meeting(self):
        self.enable_voice_test()
        self.voice_test.has_clip = True
        self.voice_test.clip_changed.emit(True)
        self.voice_test.state_changed.emit("ready")
        self.controller.calls.clear()

        self.window.voice_record_button.click()
        self.voice_test.state_changed.emit("recording")
        self.voice_test.state_changed.emit("ready")
        self.window.voice_original_button.click()
        self.voice_test.state_changed.emit("ready")
        self.window.calibration_button.click()

        forbidden = {"suspended", "start", "stop"}
        self.assertFalse(any(call[0] in forbidden for call in self.controller.calls))

    def test_programmatic_cancel_cannot_calibrate_a_previous_clip(self):
        self.enable_voice_test()
        old_values = [0.0] * (3 * 48_000) + [0.1] * (7 * 48_000)
        self.voice_test.sample = SimpleNamespace(
            original=array("f", old_values).tobytes(),
            processed=array("f", old_values).tobytes(),
            settings=Settings(),
        )
        self.voice_test.has_clip = True
        self.voice_test.clip_changed.emit(True)
        self.voice_test.state_changed.emit("ready")

        self.window.calibration_button.click()
        self.voice_test.has_clip = False
        self.voice_test.clip_changed.emit(False)
        self.voice_test.state_changed.emit("idle")
        self.voice_test.state_changed.emit("ready")  # callback tardio obsoleto

        self.assertFalse(self.window.calibration_apply_button.isEnabled())
        self.assertIn("cancelada", self.window.calibration_status_label.text().lower())

    def test_calibration_uses_snapshot_and_applies_only_on_explicit_click(self):
        self.enable_voice_test()
        self.window.clarity_slider.setValue(17)
        self.window.calibration_button.click()
        recorded = self.voice_test.calls[-1][1]
        self.assertEqual(self.voice_test.calls[-2][0], "cancel")
        self.assertEqual(self.voice_test.calls[-1][0], "record")

        self.window.clarity_slider.setValue(88)
        silence = [0.001 * math.sin(index / 23) for index in range(3 * 48_000)]
        speech = [0.12 * math.sin(index / 17) for index in range(7 * 48_000)]
        self.voice_test.sample = SimpleNamespace(
            original=array("f", silence + speech).tobytes(),
            processed=array("f", silence + speech).tobytes(),
            settings=recorded,
        )
        self.voice_test.has_clip = True
        self.voice_test.clip_changed.emit(True)
        self.voice_test.state_changed.emit("ready")

        self.assertTrue(self.window.calibration_apply_button.isEnabled())
        self.assertEqual(self.window.clarity_slider.value(), 88)
        self.window.calibration_apply_button.click()
        self.assertEqual(self.window.clarity_slider.value(), 17)
        self.assertEqual(self.saved[-1].clarity, 17)

    def test_clipped_calibration_never_enables_apply(self):
        self.enable_voice_test()
        self.window.calibration_button.click()
        recorded = self.voice_test.calls[-1][1]
        values = [0.0] * (3 * 48_000) + [1.0] * (7 * 48_000)
        self.voice_test.sample = SimpleNamespace(
            original=array("f", values).tobytes(),
            processed=array("f", values).tobytes(),
            settings=recorded,
        )
        self.voice_test.has_clip = True
        self.voice_test.clip_changed.emit(True)
        self.voice_test.state_changed.emit("ready")

        self.assertFalse(self.window.calibration_apply_button.isEnabled())
        self.assertIn("ganho físico", self.window.calibration_status_label.text().lower())

    def test_shortcut_status_can_be_published_without_desktop_integration(self):
        self.window.set_shortcut_status("Atalho global: Super+Shift+M")
        self.assertEqual(
            self.window.shortcut_label.text(), "Atalho global: Super+Shift+M"
        )


if __name__ == "__main__":
    unittest.main()
