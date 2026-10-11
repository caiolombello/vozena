import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal, qInstallMessageHandler
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from yeti_voice.desktop import CommandServer, DesktopIntegration, SuspendMonitor


class Controller(QObject):
    running_changed = Signal(bool)
    active_changed = Signal(bool)
    muted_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.active = False
        self.running = False
        self.muted = False
        self.suspensions = []

    def set_mute(self, muted):
        self.muted = muted
        self.muted_changed.emit(muted)

    def set_suspended(self, sleeping):
        self.suspensions.append(sleeping)


class VoiceTest:
    state = "idle"

    def __init__(self):
        self.cancelled = 0

    def cancel(self):
        self.cancelled += 1


class Bus:
    def connect(self, *args):
        return True

    def disconnect(self, *args):
        return True


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_paused_mute_command_never_activates_audio(self):
        controller, voice, window = Controller(), VoiceTest(), QWidget()
        desktop = DesktopIntegration(window, controller, voice, tray_available=False)
        self.assertFalse(desktop.command("toggle-mute")["ok"])
        self.assertFalse(controller.active)
        self.assertFalse(controller.muted)
        desktop.close()
        window.close()

    def test_mute_controls_preserve_activation_while_reconnecting(self):
        controller, voice, window = Controller(), VoiceTest(), QWidget()
        controller.active = True
        desktop = DesktopIntegration(window, controller, voice, tray_available=False)
        self.assertTrue(desktop.command("toggle-mute")["muted"])
        self.assertTrue(controller.active)
        self.assertFalse(controller.running)
        self.assertFalse(desktop.command("toggle-mute")["muted"])
        desktop.close()
        window.close()

    def test_tray_close_hides_window_and_cancels_sample_without_stopping_live_audio(self):
        controller, voice, window = Controller(), VoiceTest(), QWidget()
        controller.active = controller.running = True
        desktop = DesktopIntegration(window, controller, voice, tray_available=True)
        window.show()
        window.close()
        self.assertFalse(window.isVisible())
        self.assertEqual(voice.cancelled, 1)
        self.assertTrue(controller.running)
        self.assertTrue(desktop.tray.isVisible())
        desktop.command("show")
        self.assertTrue(window.isVisible())
        desktop.close()
        window.close()

    def test_suspend_cancels_preview_and_forwards_both_events(self):
        controller, voice = Controller(), VoiceTest()
        monitor = SuspendMonitor(controller, voice, bus=Bus())
        monitor.sleep_changed(True)
        monitor.sleep_changed(False)
        self.assertEqual(controller.suspensions, [True, False])
        self.assertEqual(voice.cancelled, 1)
        monitor.close()

    def test_socket_is_same_user_only_and_accepts_only_known_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "control.sock")
            calls = []
            server = CommandServer(lambda command: calls.append(command) or {"ok": True}, path=path)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o700)
            for command, accepted in [(b"status\n", True), (b"start\n", False)]:
                connection = QLocalSocket()
                connection.connectToServer(path)
                self.assertTrue(connection.waitForConnected(100))
                connection.write(command)
                connection.flush()
                QTest.qWait(30)
                response = json.loads(bytes(connection.readAll()))
                self.assertEqual(response["ok"], accepted)
                connection.abort()
            self.assertEqual(calls, ["status"])
            server.close()

    def test_idle_command_socket_times_out_without_qt_binding_warnings(self):
        warnings = []
        previous = qInstallMessageHandler(lambda _kind, _context, message: warnings.append(message))
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = str(Path(directory) / "idle.sock")
                server = CommandServer(lambda _: {"ok": True}, path=path)
                connection = QLocalSocket()
                connection.connectToServer(path)
                self.assertTrue(connection.waitForConnected(100))
                QTest.qWait(1200)
                self.assertEqual(connection.state(), QLocalSocket.LocalSocketState.UnconnectedState)
                server.close()
            self.assertFalse(any('Cannot add dynamic method "abort()"' in message for message in warnings), warnings)
        finally:
            qInstallMessageHandler(previous)


if __name__ == "__main__":
    unittest.main()
