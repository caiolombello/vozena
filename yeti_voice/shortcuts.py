"""KDE Wayland global shortcut, with saved bindings and conflict handling."""

import json
import subprocess

from PySide6.QtCore import QObject, QThread, Signal, Slot, SLOT
from PySide6.QtDBus import QDBusConnection
from PySide6.QtGui import QKeySequence


ACTION_ID = ["yeti-voz", "toggle-mute", "Vozena", "Alternar silêncio do Yeti Processado"]
DEFAULT_KEY = "Meta+Shift+M"
SERVICE = "org.kde.kglobalaccel"
INTERFACE = "org.kde.KGlobalAccel"
COMPONENT_INTERFACE = "org.kde.kglobalaccel.Component"


class _Types:
    """Plain containers keep the KDE typed registration contract dependency-free."""
    @staticmethod
    def Array(value, signature=None):
        return list(value)

    @staticmethod
    def Struct(value, signature=None):
        return tuple(value)

    UInt32 = int


class _BusctlInterface:
    """Use Fedora's system D-Bus client from the isolated Python runtime."""
    def _call(self, method, signature, arguments, result_type="", timeout=.5):
        result = subprocess.run(
            ["busctl", "--user", f"--timeout={timeout}", "--json=short", "call",
             SERVICE, "/kglobalaccel", INTERFACE, method, signature,
             *[str(value) for value in arguments]],
            capture_output=True, text=True, check=True, timeout=timeout + .5,
        )
        if not result_type:
            return None
        reply = json.loads(result.stdout)
        if reply["type"] != result_type or len(reply["data"]) != 1:
            raise ValueError("Unexpected KDE shortcut reply")
        return reply["data"][0]

    def globalShortcutAvailable(self, sequence, component, timeout=.5):
        return self._call("globalShortcutAvailable", "(ai)s",
                          [len(sequence[0]), *sequence[0], component], "b", timeout)

    def doRegister(self, identity, timeout=.5):
        self._call("doRegister", "as", [len(identity), *identity], timeout=timeout)

    def setShortcutKeys(self, identity, sequences, flags, timeout=.5):
        arguments = [len(identity), *identity, len(sequences)]
        for sequence in sequences:
            arguments.extend([len(sequence[0]), *sequence[0]])
        return self._call("setShortcutKeys", "asa(ai)u", [*arguments, flags], "a(ai)", timeout)

    def getComponent(self, component, timeout=.5):
        return self._call("getComponent", "s", [component], "o", timeout)

    def setInactive(self, identity, timeout=.5):
        self._call("setInactive", "as", [len(identity), *identity], timeout=timeout)


def bind_shortcut(interface, dbus):
    """KDE v2 API; flag 2 loads saved bindings without overwriting them."""
    identity = dbus.Array(ACTION_ID, signature="s")
    key = QKeySequence(DEFAULT_KEY)[0].toCombined()
    sequence = dbus.Struct((dbus.Array([key], signature="i"),), signature="ai")
    available = bool(interface.globalShortcutAvailable(sequence, ACTION_ID[0], timeout=.5))
    interface.doRegister(identity, timeout=.5)
    defaults = dbus.Array([sequence], signature="(ai)")
    interface.setShortcutKeys(identity, defaults, dbus.UInt32(8), timeout=.5)
    # Empty defaults avoid taking a conflicting shortcut. Saved user bindings
    # are still restored by KDE's normal autoloading mode.
    requested = defaults if available else dbus.Array([], signature="(ai)")
    assigned = interface.setShortcutKeys(identity, requested, dbus.UInt32(2), timeout=.5)
    path = str(interface.getComponent(ACTION_ID[0], timeout=.5))
    keys = [int(value) for value in assigned[0][0]] if assigned else []
    return path, keys


class _Registration(QThread):
    ready = Signal(str, object)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.interface = None
        self.dbus = _Types

    def run(self):
        try:
            self.interface = _BusctlInterface()
            path, keys = bind_shortcut(self.interface, self.dbus)
            if self.isInterruptionRequested():
                self.deactivate()
            else:
                self.ready.emit(path, keys)
        except Exception:
            self.deactivate()
            self.failed.emit("Atalho global indisponível nesta sessão do desktop.")

    def deactivate(self):
        if self.interface is not None and self.dbus is not None:
            try:
                self.interface.setInactive(self.dbus.Array(ACTION_ID, signature="s"), timeout=.5)
            except Exception:
                pass


class GlobalShortcut(QObject):
    status_changed = Signal(str)
    binding_changed = Signal(str)

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback
        self._path = None
        self._closed = False
        self._bus = QDBusConnection.sessionBus()
        self._worker = _Registration(self)
        self._worker.ready.connect(self._ready)
        self._worker.failed.connect(self.status_changed)

    def start(self):
        self._worker.start()

    @Slot(str, object)
    def _ready(self, path, keys):
        if self._closed:
            return
        self._path = path
        connected = self._bus.connect(
            SERVICE, path, COMPONENT_INTERFACE, "globalShortcutPressed",
            self, SLOT("pressed(QString,QString,qlonglong)"),
        )
        self._bus.connect(
            SERVICE, "/kglobalaccel", INTERFACE, "yourShortcutsChanged",
            self, SLOT("shortcut_changed(QDBusMessage)"),
        )
        if not connected:
            self.status_changed.emit("Não foi possível ouvir o atalho global do KDE.")
            return
        self._show_binding(keys)

    def _show_binding(self, keys):
        label = QKeySequence(*keys).toString(QKeySequence.SequenceFormat.NativeText) if keys else ""
        self.binding_changed.emit(label)
        if label:
            self.status_changed.emit(f"Atalho global: {label} · alternar silêncio do Yeti Processado")
        else:
            self.status_changed.emit("Atalho sem tecla livre. Configure Vozena em Configurações do KDE → Atalhos.")

    @Slot(str, str, "qlonglong")
    def pressed(self, component, action, _timestamp):
        if not self._closed and component == ACTION_ID[0] and action == ACTION_ID[1]:
            self._callback()

    @Slot("QDBusMessage")
    def shortcut_changed(self, message):
        # Custom a(ai) is a QDBusArgument in PySide; use a fresh bounded lookup
        # rather than presenting an obsolete binding after a KDE settings edit.
        arguments = message.arguments()
        if arguments and list(arguments[0]) == ACTION_ID:
            self.binding_changed.emit("")
            self.status_changed.emit("Atalho alterado no KDE. Reabra o Vozena para atualizar a tecla exibida.")

    def close(self):
        self._closed = True
        self._worker.requestInterruption()
        if self._path:
            self._bus.disconnect(SERVICE, self._path, COMPONENT_INTERFACE, "globalShortcutPressed",
                                 self, SLOT("pressed(QString,QString,qlonglong)"))
        self._bus.disconnect(SERVICE, "/kglobalaccel", INTERFACE, "yourShortcutsChanged",
                             self, SLOT("shortcut_changed(QDBusMessage)"))
        if not self._worker.isRunning():
            self._worker.deactivate()

    def finish(self):
        # Called after the GUI loop exits; every D-Bus request has a short timeout.
        self._worker.wait()
        self._worker.deactivate()
