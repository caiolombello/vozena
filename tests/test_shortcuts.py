import os
import subprocess
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from yeti_voice.shortcuts import ACTION_ID, GlobalShortcut, bind_shortcut


class Types:
    @staticmethod
    def Array(value, signature=None):
        return list(value)

    @staticmethod
    def Struct(value, signature=None):
        return tuple(value)

    UInt32 = int


class Registry:
    def __init__(self, available=True, assigned=None):
        self.available = available
        self.assigned = assigned
        self.calls = []

    def globalShortcutAvailable(self, sequence, component, **kwargs):
        return self.available

    def doRegister(self, identity, **kwargs):
        self.calls.append(("register", identity))

    def setShortcutKeys(self, identity, keys, flags, **kwargs):
        self.calls.append(("set", keys, flags))
        return keys if self.assigned is None else self.assigned

    def getComponent(self, component, **kwargs):
        return "/component/yeti_voz"


class ShortcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_saved_custom_binding_is_returned_without_overwrite_flags(self):
        saved_key = QKeySequence("Ctrl+Alt+M")[0].toCombined()
        registry = Registry(assigned=[([saved_key],)])
        path, assigned = bind_shortcut(registry, Types)
        self.assertEqual(path, "/component/yeti_voz")
        self.assertEqual(assigned, [saved_key])
        self.assertEqual([call[2] for call in registry.calls if call[0] == "set"], [8, 2])
        self.assertEqual(registry.calls[0], ("register", ACTION_ID))

    def test_conflicting_default_requests_no_active_key_and_leaves_other_apps_untouched(self):
        registry = Registry(available=False)
        _, assigned = bind_shortcut(registry, Types)
        self.assertEqual(assigned, [])
        self.assertEqual(registry.calls[-1], ("set", [], 2))

    def test_only_owned_action_signal_invokes_callback(self):
        calls = []
        shortcut = GlobalShortcut(lambda: calls.append(True))
        shortcut.pressed("kwin", "toggle-mute", 1)
        shortcut.pressed("yeti-voz", "other", 1)
        self.assertFalse(calls)
        shortcut.pressed("yeti-voz", "toggle-mute", 1)
        self.assertEqual(calls, [True])
        shortcut.close()
        shortcut.pressed("yeti-voz", "toggle-mute", 1)
        self.assertEqual(calls, [True])

    def test_registration_uses_system_busctl_in_an_isolated_runtime(self):
        replies = [
            '{"type":"b","data":[true]}',
            '',
            '{"type":"a(ai)","data":[[[[301989965,0,0,0]]]]}',
            '{"type":"a(ai)","data":[[[[201326669,0,0,0]]]]}',
            '{"type":"o","data":["/component/yeti_voz"]}',
            '',
            '',
        ]
        labels, statuses = [], []
        with patch("subprocess.run", side_effect=[
            subprocess.CompletedProcess([], 0, reply, "") for reply in replies
        ]) as run, patch("yeti_voice.shortcuts.QDBusConnection.sessionBus") as session_bus:
            session_bus.return_value.connect.return_value = True
            shortcut = GlobalShortcut(lambda: None)
            shortcut.binding_changed.connect(labels.append)
            shortcut.status_changed.connect(statuses.append)
            shortcut.start()
            try:
                deadline = time.monotonic() + 2
                while not labels and not statuses and time.monotonic() < deadline:
                    QApplication.processEvents()
                    time.sleep(.01)
                self.assertEqual(labels, ["Ctrl+Alt+M"], statuses)
                calls = [call.args[0] for call in run.call_args_list]
                self.assertEqual([call[8] for call in calls[:5]], [
                    "globalShortcutAvailable", "doRegister", "setShortcutKeys",
                    "setShortcutKeys", "getComponent",
                ])
                self.assertEqual(calls[0][9:], ["(ai)s", "1", "301989965", "yeti-voz"])
                self.assertEqual(calls[2][9:], ["asa(ai)u", "4", *ACTION_ID,
                                              "1", "1", "301989965", "8"])
                self.assertEqual(calls[3][-1], "2")
                for call in run.call_args_list:
                    self.assertEqual(call.args[0][:4], ["busctl", "--user", "--timeout=0.5", "--json=short"])
                    self.assertTrue(call.kwargs["check"])
                    self.assertLessEqual(call.kwargs["timeout"], 1)
            finally:
                shortcut.close()
                shortcut.finish()
            self.assertEqual(run.call_args.args[0][8:], ["setInactive", "as", "4", *ACTION_ID])

    def test_missing_or_timed_out_busctl_reports_unavailable_without_binding(self):
        for error in (FileNotFoundError("busctl"), subprocess.TimeoutExpired("busctl", 1)):
            with self.subTest(error=type(error).__name__), patch("subprocess.run", side_effect=error):
                labels, statuses = [], []
                shortcut = GlobalShortcut(lambda: None)
                shortcut.binding_changed.connect(labels.append)
                shortcut.status_changed.connect(statuses.append)
                shortcut.start()
                try:
                    deadline = time.monotonic() + 2
                    while not statuses and time.monotonic() < deadline:
                        QApplication.processEvents()
                        time.sleep(.01)
                    self.assertEqual(statuses, ["Atalho global indisponível nesta sessão do desktop."])
                    self.assertEqual(labels, [])
                finally:
                    shortcut.close()
                    shortcut.finish()

    @unittest.skipUnless(os.environ.get("YETI_RUN_DESKTOP_TESTS") == "1", "opt-in KDE integration")
    def test_kde_daemon_delivers_the_registered_action(self):
        """No controller or microphone is started by this desktop check."""
        calls, labels, statuses = [], [], []
        shortcut = GlobalShortcut(lambda: calls.append(True))
        shortcut.binding_changed.connect(labels.append)
        shortcut.status_changed.connect(statuses.append)
        shortcut.start()
        try:
            deadline = time.monotonic() + 4
            while not labels and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(.01)
            self.assertTrue(labels and labels[0], statuses)
            subprocess.run(["busctl", "--user", "call", "org.kde.kglobalaccel", shortcut._path,
                            "org.kde.kglobalaccel.Component", "invokeShortcut", "s", "toggle-mute"],
                           check=True, capture_output=True, timeout=1)
            deadline = time.monotonic() + 1
            while not calls and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(.01)
            self.assertEqual(calls, [True])
        finally:
            shortcut.close()
            shortcut.finish()


if __name__ == "__main__":
    unittest.main()
