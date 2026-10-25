"""Run the native app; capture starts from explicit activation or voice testing."""

import argparse
import json
import signal
import sys

from PySide6.QtCore import QCoreApplication, QLockFile, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .engine import VoiceController, check_dependencies, find_yeti, graph_snapshot
from .desktop import CommandServer, DesktopIntegration, PlasmaOsd, SuspendMonitor, runtime_directory, send_command
from .processing import ROOT
from .storage import load_preferences, load_settings, save_preferences, save_settings
from .shortcuts import GlobalShortcut
from .autostart import SessionAutostart
from .ui import MainWindow
from .voice_test import VoiceTestController


def main():
    parser = argparse.ArgumentParser(description="Vozena — áudio local para chamadas")
    parser.add_argument("--version", action="version", version=f"Vozena {__version__}")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--diagnose", action="store_true", help="Verificar dependências e dispositivo sem captar áudio")
    actions.add_argument("--render", metavar="PNG", help="Renderizar a interface pausada e encerrar")
    actions.add_argument("--toggle-mute", action="store_true", help="Alternar silêncio na instância aberta")
    actions.add_argument("--show", action="store_true", help="Mostrar a janela existente")
    actions.add_argument("--status", action="store_true", help="Consultar a instância aberta sem captar áudio")
    parser.add_argument("--background", action="store_true",
                        help="Abrir na bandeja, sem mostrar a janela (usado no início automático)")
    options = parser.parse_args()
    if options.diagnose:
        try:
            check_dependencies()
            source = find_yeti(graph_snapshot())
            print(json.dumps({"dependencies": "ok", "yeti_detected": bool(source),
                              "audio_captured": False}, ensure_ascii=False))
            return 0 if source else 1
        except Exception as error:
            print(json.dumps({"error": str(error), "audio_captured": False}, ensure_ascii=False))
            return 1

    if options.toggle_mute or options.status:
        command_app = QCoreApplication(sys.argv[:1])
        result = send_command("toggle-mute" if options.toggle_mute else "status")
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Vozena")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("yeti-voz")
    app.setWindowIcon(QIcon(str(ROOT / "assets/vozena.svg")))
    lock = None
    if not options.render:
        runtime = runtime_directory()
        lock = QLockFile(str(runtime / "yeti-voz.lock"))
        if not lock.tryLock(100):
            if options.background:
                return 0
            result = send_command("show")
            if not result.get("ok"):
                QMessageBox.information(None, "Vozena", result["message"])
            return 0 if result.get("ok") else 1

    controller = VoiceController()
    voice_test = VoiceTestController()
    settings, warning = load_settings()
    preferences, preferences_warning = load_preferences()

    def persist(values):
        try:
            save_settings(values)
        except OSError as error:
            controller.error_occurred.emit(f"Não foi possível salvar os ajustes: {error}")

    window = MainWindow(controller, settings, persist, voice_test,
                        preferences=preferences, save_preferences=save_preferences,
                        autostart=None if options.render else SessionAutostart())
    desktop = commands = sleep_monitor = shortcut = None
    if not options.render:
        desktop = DesktopIntegration(window, controller, voice_test, app, osd=PlasmaOsd())
        try:
            commands = CommandServer(desktop.command, app)
        except OSError as error:
            controller.error_occurred.emit(f"Controle da instância indisponível: {error}")
        sleep_monitor = SuspendMonitor(controller, voice_test, app)
        shortcut = GlobalShortcut(desktop.toggle_mute, app)
        shortcut.status_changed.connect(window.set_shortcut_status)
        shortcut.binding_changed.connect(desktop.set_shortcut)
        shortcut.start()
        app.aboutToQuit.connect(desktop.close)
        app.aboutToQuit.connect(window.close)
        if commands:
            app.aboutToQuit.connect(commands.close)
        app.aboutToQuit.connect(sleep_monitor.close)
        app.aboutToQuit.connect(shortcut.close)
        if not sleep_monitor.connected:
            controller.error_occurred.emit("Não foi possível acompanhar a suspensão do sistema.")
    for message in (warning, preferences_warning):
        if message:
            controller.error_occurred.emit(message)
    app.aboutToQuit.connect(controller.stop)
    app.aboutToQuit.connect(voice_test.close)
    if preferences.activate_on_launch and not options.render:
        window.activate_when_ready()
    if not (options.background and desktop and desktop.tray):
        window.show()
    if options.render:
        window.set_shortcut_status("Atalho global: Meta+Shift+M · alternar silêncio do Yeti Processado")
        def render():
            window.grab().save(options.render)
            app.quit()
        QTimer.singleShot(100, render)
    signal.signal(signal.SIGTERM, lambda *_: desktop.quit() if desktop else app.quit())
    signal.signal(signal.SIGINT, lambda *_: desktop.quit() if desktop else app.quit())
    result = app.exec()
    if shortcut:
        shortcut.finish()
    if lock:
        lock.unlock()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
