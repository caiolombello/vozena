"""Native tray controls, same-user commands and suspend notifications."""

import json
import os
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer, Slot, SLOT
from PySide6.QtDBus import QDBusConnection, QDBusMessage
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


def runtime_directory():
    directory = Path(os.environ.get("XDG_RUNTIME_DIR", str(Path.home() / ".cache/yeti-voice")))
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def command_path():
    return str(runtime_directory() / "yeti-voz.sock")


def send_command(command, path=None):
    """CLI-only bounded request; never starts an app or microphone stream."""
    connection = QLocalSocket()
    connection.connectToServer(path or command_path())
    if not connection.waitForConnected(500):
        return {"ok": False, "message": "Vozena não está em execução."}
    connection.write(command.encode("ascii") + b"\n")
    if not connection.waitForBytesWritten(500):
        connection.abort()
        return {"ok": False, "message": "Não foi possível enviar o comando."}
    payload = bytearray()
    for _ in range(2):
        if not connection.bytesAvailable() and not connection.waitForReadyRead(500):
            break
        payload.extend(bytes(connection.readAll()))
        if b"\n" in payload or len(payload) > 4096:
            break
    connection.abort()
    try:
        return json.loads(payload)
    except (ValueError, UnicodeError):
        return {"ok": False, "message": "O aplicativo não respondeu ao comando."}


class CommandServer(QObject):
    """Only an existing instance holding the application lock may listen."""

    def __init__(self, handler, parent=None, *, path=None):
        super().__init__(parent)
        self._handler = handler
        self._connections = set()
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.setMaxPendingConnections(8)
        self.path = path or command_path()
        QLocalServer.removeServer(self.path)
        if not self.server.listen(self.path):
            raise OSError(self.server.errorString())
        self.server.newConnection.connect(self._accept)

    def _accept(self):
        while self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            if len(self._connections) >= 8:
                connection.abort()
                connection.deleteLater()
                continue
            self._connections.add(connection)
            connection.setReadBufferSize(128)
            deadline = QTimer(connection)
            deadline.setSingleShot(True)
            # A Python callable keeps the wrapper available with official Qt wheels.
            deadline.timeout.connect(lambda c=connection: c.abort())
            deadline.start(1000)
            connection.readyRead.connect(lambda c=connection: self._read(c))
            connection.disconnected.connect(lambda c=connection: self._discard(c))
            self._read(connection)

    def _discard(self, connection):
        self._connections.discard(connection)
        connection.deleteLater()

    def _read(self, connection):
        if connection.bytesAvailable() > 64:
            connection.abort()
            return
        if not connection.canReadLine():
            return
        command = bytes(connection.readLine(65)).strip()
        if command not in (b"show", b"toggle-mute", b"status"):
            response = {"ok": False, "message": "Comando desconhecido."}
        else:
            response = self._handler(command.decode("ascii"))
        connection.write(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")
        connection.disconnectFromServer()

    def close(self):
        self.server.close()
        for connection in tuple(self._connections):
            connection.abort()


class SuspendMonitor(QObject):
    def __init__(self, controller, voice_test, parent=None, *, bus=None):
        super().__init__(parent)
        self._controller = controller
        self._voice_test = voice_test
        self._bus = bus or QDBusConnection.systemBus()
        self.connected = self._bus.connect(
            "org.freedesktop.login1", "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager", "PrepareForSleep",
            self, SLOT("sleep_changed(bool)"),
        )

    @Slot(bool)
    def sleep_changed(self, sleeping):
        if sleeping:
            self._voice_test.cancel()
        self._controller.set_suspended(sleeping)

    def close(self):
        self._bus.disconnect(
            "org.freedesktop.login1", "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager", "PrepareForSleep",
            self, SLOT("sleep_changed(bool)"),
        )


class PlasmaOsd:
    """Plasma's own on-screen display, the one used for its microphone keys."""

    def __init__(self, bus=None):
        self._bus = bus or QDBusConnection.sessionBus()

    def show(self, icon, text):
        interface = self._bus.interface() if self._bus.isConnected() else None
        if interface is None or not interface.isServiceRegistered("org.kde.plasmashell").value():
            return False
        message = QDBusMessage.createMethodCall(
            "org.kde.plasmashell", "/org/kde/osdService", "org.kde.osdService", "showText")
        message.setArguments([icon, text])
        return self._bus.send(message)


class DesktopIntegration(QObject):
    def __init__(self, window, controller, voice_test, parent=None, *, tray_available=None, osd=None):
        super().__init__(parent)
        self.window = window
        self.controller = controller
        self.voice_test = voice_test
        self._osd = osd
        controller.muted_changed.connect(self._announce_mute)
        if hasattr(controller, "talking_while_muted"):
            controller.talking_while_muted.connect(self._warn_talking)
        self._quitting = False
        self._shortcut = ""
        self._base_icon = QApplication.windowIcon()
        self.tray = None
        available = QSystemTrayIcon.isSystemTrayAvailable() if tray_available is None else tray_available
        if hasattr(window, "set_tray_available"):
            window.set_tray_available(available)
        if available:
            self.tray = QSystemTrayIcon(self._base_icon, self)
            self.menu = QMenu(window)
            self.menu.addAction("Abrir Vozena", self.show_window)
            self.mute_action = self.menu.addAction("Silenciar microfone", self.toggle_mute)
            self.menu.addSeparator()
            self.menu.addAction("Encerrar Vozena", self.quit)
            self.tray.setContextMenu(self.menu)
            self.tray.activated.connect(self._activated)
            controller.running_changed.connect(self.refresh)
            controller.active_changed.connect(self.refresh)
            controller.muted_changed.connect(self.refresh)
            self.tray.show()
            window.installEventFilter(self)
            QApplication.instance().setQuitOnLastWindowClosed(False)
            self.refresh()

    def eventFilter(self, watched, event):
        if watched is self.window and event.type() == QEvent.Type.Close and not self._quitting:
            self.voice_test.cancel()
            self.window.hide()
            event.ignore()
            return True
        return super().eventFilter(watched, event)

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self.toggle_mute()

    def show_window(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def toggle_mute(self):
        if not self.controller.active:
            return False
        self.controller.set_mute(not self.controller.muted)
        return True

    def _notify(self, title, text, warning=False):
        if self.tray is not None:
            icon = QSystemTrayIcon.MessageIcon.Warning if warning else QSystemTrayIcon.MessageIcon.Information
            self.tray.showMessage(title, text, icon, 6000 if warning else 2500)

    def _announce_mute(self, muted):
        # The shortcut and tray change mute while another window has focus.
        if not self.controller.active or self.window.isActiveWindow():
            return
        text = "Yeti Processado silenciado" if muted else "Yeti Processado ativo"
        icon = "microphone-sensitivity-muted" if muted else "microphone-sensitivity-high"
        if not (self._osd and self._osd.show(icon, text)):
            self._notify("Vozena", text)

    def _warn_talking(self):
        hint = f" Use {self._shortcut} para reativar." if self._shortcut else ""
        text = "Você está falando, mas o Yeti Processado está silenciado." + hint
        if self.tray is not None:
            self._notify("Microfone silenciado", text, warning=True)
        elif self._osd:
            self._osd.show("microphone-sensitivity-muted", "Você está falando com o microfone silenciado")

    def set_shortcut(self, label):
        self._shortcut = label
        self.refresh()

    def refresh(self, *_):
        if self.tray is None:
            return
        if not self.controller.active:
            state, color = "Pausado", "#82919a"
        elif self.controller.muted:
            state, color = "Microfone silenciado", "#ef6c73"
        elif not self.controller.running:
            state, color = "Reconectando", "#efba62"
        else:
            state, color = "Microfone ativo", "#34c6b0"
        pixmap = self._base_icon.pixmap(32, 32)
        if not pixmap.isNull():
            painter = QPainter(pixmap)
            painter.setPen(QColor("#171b20"))
            painter.setBrush(QColor(color))
            painter.drawEllipse(20, 20, 11, 11)
            painter.end()
            self.tray.setIcon(QIcon(pixmap))
        suffix = f" · {self._shortcut}" if self._shortcut else ""
        self.tray.setToolTip(f"Vozena · {state}{suffix}\nFechar a janela mantém o app na bandeja.")
        self.mute_action.setEnabled(self.controller.active)
        self.mute_action.setText("Reativar microfone" if self.controller.muted else "Silenciar microfone")

    def command(self, command):
        if command == "show":
            self.show_window()
        elif command == "toggle-mute" and not self.toggle_mute():
            return {"ok": False, "message": "Ative o processamento antes de silenciar."}
        return {"ok": True, "active": self.controller.active,
                "running": self.controller.running, "muted": self.controller.muted,
                "voice_test": self.voice_test.state,
                "tray": bool(self.tray and self.tray.isVisible()),
                "shortcut": self._shortcut, "window_visible": self.window.isVisible()}

    def quit(self):
        self._quitting = True
        self.window.close()
        QApplication.instance().quit()

    def close(self):
        self._quitting = True
        if self.tray is not None:
            self.tray.hide()
        self.window.removeEventFilter(self)
