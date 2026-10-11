import os
import subprocess
import time
import unittest

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
