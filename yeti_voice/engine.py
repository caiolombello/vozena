"""Owned PipeWire worker and an in-memory level meter, activated by the UI."""

from array import array
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .processing import CAPTURE_NODE, OUTPUT_NODE, ROOT, make_config, props_payload, serialize_config
from .settings import Settings


def graph_snapshot():
    """Synchronous diagnostic helper; never called from the controller's UI path."""
    result = subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=2, check=True)
    return json.loads(result.stdout)


def node_named(objects, name):
    return next((row for row in objects if row.get("info", {}).get("props", {}).get("node.name") == name), None)


def find_yeti(objects):
    return next((row for row in objects
                 if row.get("info", {}).get("props", {}).get("media.class") == "Audio/Source"
                 and row["info"]["props"].get("alsa.components", "").lower() == "usbb58e:9e84"), None)


def check_dependencies():
    for command in ("pipewire", "pw-dump", "pw-cli", "pw-cat"):
        if not shutil.which(command):
            raise RuntimeError(f"Componente de áudio ausente: {command}")
    manifest = json.loads((ROOT / ".deps/manifest.json").read_text())
    for label, item in manifest.items():
        path = ROOT / ".deps" / item["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError(f"Filtro {label} ausente ou diferente da versão preparada")


class VoiceController(QObject):
    status_changed = Signal(str)
    running_changed = Signal(bool)
    level_changed = Signal(float)
    device_changed = Signal(str)
    error_occurred = Signal(str)
    active_changed = Signal(bool)
    muted_changed = Signal(bool)

    def __init__(self, parent=None, *, meter_enabled=True):
        super().__init__(parent)
        self._running = False
        self._starting = False
        self._start_requested = False
        self._active = False
        self._suspended = False
        self._recovering = False
        self._recovery_attempt = 0
        self._retrying = False
        self._parameter_failure_pending = False
        self._stale_nodes_attempts = 0
        self._stopping = False
        self._description = ""
        self._source = None
        self._capture_id = None
        self._settings = Settings()
        self._bypass = False
        self._muted = False
        self._temporary = None
        self._generation = 0
        self._meter_enabled = meter_enabled
        self._meter_started = False
        self._parameters_dirty = False
        self._parameters_pending = False
        self._probe_pending = False
        self._pcm = bytearray()
        self._peak = 0.0
        self._diagnostics = bytearray()
        self._worker = QProcess(self)
        self._worker.readyReadStandardError.connect(self._worker_stderr)
        self._worker.finished.connect(self._worker_finished)
        self._worker.errorOccurred.connect(self._worker_error)
        self._meter = QProcess(self)
        self._meter.readyReadStandardOutput.connect(self._read_meter)
        self._meter.finished.connect(self._meter_finished)
        self._meter.errorOccurred.connect(self._meter_error)
        self._probe = QProcess(self)
        self._probe.finished.connect(self._probe_finished)
        self._probe.errorOccurred.connect(self._probe_error)
        self._probe_deadline = QTimer(self)
        self._probe_deadline.setSingleShot(True)
        self._probe_deadline.timeout.connect(self._probe_timeout)
        self._parameters = QProcess(self)
        self._parameters.finished.connect(self._parameters_finished)
        self._parameters.errorOccurred.connect(self._parameters_error)
        self._parameters_deadline = QTimer(self)
        self._parameters_deadline.setSingleShot(True)
        self._parameters_deadline.timeout.connect(self._parameters_timeout)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(2000)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start()
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._retry)
        self._level_timer = QTimer(self)
        self._level_timer.setInterval(100)
        self._level_timer.timeout.connect(self._emit_level)
        self.refresh()

    @property
    def running(self):
        return self._running

    @property
    def active(self):
        return self._active

    @property
    def muted(self):
        return self._muted

    @property
    def device_description(self):
        return self._description

    def refresh(self):
        if self._stopping or self._suspended or self._probe.state() != QProcess.ProcessState.NotRunning:
            return
        self._probe_pending = True
        self._probe.start("pw-dump", [])
        self._probe_deadline.start(2000)

    def _probe_finished(self, exit_code, _status):
        if not self._probe_pending or self._stopping:
            return
        self._probe_pending = False
        self._probe_deadline.stop()
        try:
            if exit_code != 0:
                raise ValueError("PipeWire probe failed")
            objects = json.loads(bytes(self._probe.readAllStandardOutput()))
            if not isinstance(objects, list):
                raise ValueError("Invalid PipeWire graph")
            self._inspect_graph(objects)
        except (OSError, ValueError, KeyError, TypeError):
            self._probe_unavailable()

    def _probe_error(self, error):
        if self._probe_pending and error == QProcess.ProcessError.FailedToStart:
            self._probe_pending = False
            self._probe_deadline.stop()
            self._probe_unavailable()

    def _probe_timeout(self):
        if not self._probe_pending:
            return
        self._probe_pending = False
        self._probe.kill()
        self._probe_unavailable()

    def _probe_unavailable(self):
        if self._stopping:
            return
        if self._active:
            self._recover("Aguardando o serviço de áudio…")
        else:
            self.status_changed.emit("Serviço de áudio indisponível")

    def _inspect_graph(self, objects):
        source = find_yeti(objects)
        description = source["info"]["props"].get("alsa.card_name", "Blue Yeti") if source else ""
        if description != self._description:
            self._description = description
            self.device_changed.emit(description)
        if self._start_requested:
            if not source:
                self._start_requested = False
                if self._active:
                    self._recover("Aguardando a conexão USB do Blue Yeti…")
                else:
                    self._fail("Blue Yeti não detectado. Confira a conexão USB.")
            elif node_named(objects, OUTPUT_NODE) or node_named(objects, CAPTURE_NODE):
                if self._retrying and self._stale_nodes_attempts < 5:
                    self._start_requested = False
                    self._starting = False
                    self._stale_nodes_attempts += 1
                    self._refresh_timer.stop()
                    self.status_changed.emit("Aguardando a limpeza do áudio anterior…")
                    self._schedule_retry()
                else:
                    self._fail("Já existe um tratamento do Yeti ativo. Feche a outra instância.")
            else:
                self._launch_worker(source["info"]["props"]["node.name"])
            return
        if self._active and (self._running or self._starting) and (not source or source["info"]["props"].get("node.name") != self._source):
            self._recover("Aguardando a reconexão do Blue Yeti…")
            return
        capture = node_named(objects, CAPTURE_NODE)
        output = node_named(objects, OUTPUT_NODE)
        if self._starting and capture and output:
            self._capture_id = capture["id"]
            self._starting = False
            self._running = True
            self._recovering = False
            self._retrying = False
            self._recovery_attempt = 0
            self._stale_nodes_attempts = 0
            self._refresh_timer.setInterval(2000)
            self._parameters_dirty = True
            self.running_changed.emit(True)
        if self._running:
            if not capture or not output:
                self._recover("Reconectando o áudio processado…")
            elif self._parameter_failure_pending:
                self._parameter_failure_pending = False
                self._fail("Não foi possível aplicar os ajustes de voz")
            elif self._parameters_dirty and not self._parameters_pending:
                # Resolve the owned name on each write: numeric PipeWire IDs can be reused.
                self._capture_id = capture["id"]
                self._parameters_dirty = False
                self._parameters_pending = True
                self._parameters.start("pw-cli", ["set-param", str(self._capture_id), "Props",
                    props_payload(self._settings, bypass=self._bypass, muted=self._muted)])
                self._parameters_deadline.start(2000)
        elif not self._starting and not self._active:
            self.status_changed.emit("Pronto para ativar" if source else "Conecte o Blue Yeti")
        elif self._active and not self._running and not self._starting and not self._recovering:
            self._schedule_retry()

    def start(self, settings):
        if self._suspended:
            self.status_changed.emit("O áudio será retomado quando o sistema sair da suspensão")
            return
        if self._active:
            return
        try:
            check_dependencies()
            self._settings = settings
            self._set_active(True)
            self._set_muted(False)
            self._suspended = False
            self._recovery_attempt = 0
            self._starting = True
            self._start_requested = True
            self._generation += 1
            generation = self._generation
            self.status_changed.emit("Preparando o tratamento…")
            self._refresh_timer.setInterval(150)
            self.refresh()
            QTimer.singleShot(6000, lambda: self._start_timeout(generation))
        except (OSError, ValueError, RuntimeError) as error:
            self._fail(str(error))

    def _launch_worker(self, source_name):
        try:
            self._start_requested = False
            self._source = source_name
            self._diagnostics.clear()
            self._temporary = tempfile.TemporaryDirectory(prefix="yeti-voice-")
            path = Path(self._temporary.name) / "yeti-voice.conf"
            path.write_text(serialize_config(make_config(
                self._settings, source_name, bypass=self._bypass, muted=self._muted)))
            self._worker.start("pipewire", ["-c", str(path)])
        except (OSError, ValueError, RuntimeError) as error:
            self._fail(str(error))

    def update_settings(self, settings):
        self._settings = settings
        self._push_parameters()

    def set_bypass(self, bypass):
        self._bypass = bool(bypass)
        self._push_parameters()

    def set_mute(self, muted):
        self._set_muted(bool(muted))
        self._push_parameters()

    def _set_muted(self, muted):
        muted = bool(muted)
        if muted != self._muted:
            self._muted = muted
            self.muted_changed.emit(muted)

    def _set_active(self, active):
        active = bool(active)
        if active != self._active:
            self._active = active
            self.active_changed.emit(active)

    def set_suspended(self, suspended):
        suspended = bool(suspended)
        if suspended == self._suspended:
            return
        self._suspended = suspended
        if suspended:
            self._retry_timer.stop()
            if self._active:
                self._recover("Áudio pausado durante a suspensão do sistema")
        elif self._active:
            self._recovering = False
            self._recovery_attempt = 0
            self.status_changed.emit("Retomando o áudio…")
            self.refresh()

    def _schedule_retry(self, *, immediate=False):
        if not self._active or self._suspended or self._stopping:
            return
        delays = (500, 1000, 2000, 4000, 8000, 15000)
        delay = 0 if immediate else delays[min(self._recovery_attempt, len(delays) - 1)]
        if not immediate:
            self._recovery_attempt += 1
        if not self._retry_timer.isActive():
            self._retry_timer.start(delay)

    def _retry(self):
        if self._active and not self._suspended and not self._running and not self._starting:
            processes = (self._probe, self._parameters, self._meter, self._worker)
            if any(process.state() != QProcess.ProcessState.NotRunning for process in processes):
                self._retry_timer.start(200)
                return
            self._starting = True
            self._start_requested = True
            self._generation += 1
            generation = self._generation
            self._refresh_timer.setInterval(500)
            self._refresh_timer.start()
            self.refresh()
            QTimer.singleShot(6000, lambda: self._start_timeout(generation))

    def _recover(self, message):
        if not self._active or self._stopping:
            return
        self._recovering = True
        self._retrying = True
        self._generation += 1
        self._retry_timer.stop()
        self._starting = False
        self._start_requested = False
        self._running = False
        self._meter_started = False
        self._parameters_pending = False
        self._parameters_dirty = False
        self._parameter_failure_pending = False
        self._probe_pending = False
        self._probe_deadline.stop()
        self._parameters_deadline.stop()
        self._level_timer.stop()
        self._refresh_timer.stop()
        processes = (self._probe, self._parameters, self._meter, self._worker)
        process_ids = []
        for process in processes:
            if process.state() != QProcess.ProcessState.NotRunning:
                process_ids.append((process, int(process.processId())))
                process.terminate()
        for process, pid in process_ids:
            if pid:
                QTimer.singleShot(300, lambda process=process, pid=pid: self._kill_if_same_process(process, pid))
        self._cleanup_temporary_if_worker_stopped()
        self._source = None
        self._capture_id = None
        self._pcm.clear()
        self._peak = 0.0
        self.running_changed.emit(False)
        self.level_changed.emit(-60.0)
        self.status_changed.emit(message)
        self._recovering = False
        self._schedule_retry()

    def _kill_if_same_process(self, process, pid):
        if int(process.processId()) == pid and process.state() != QProcess.ProcessState.NotRunning:
            process.kill()

    def _cleanup_temporary_if_worker_stopped(self):
        if self._temporary and self._worker.state() == QProcess.ProcessState.NotRunning:
            self._temporary.cleanup()
            self._temporary = None

    def _push_parameters(self):
        if self._running:
            self._parameters_dirty = True
            self.refresh()

    def _parameters_finished(self, exit_code, _status):
        if not self._parameters_pending or self._stopping:
            return
        self._parameters_pending = False
        self._parameters_deadline.stop()
        errors = bytes(self._parameters.readAllStandardError()).strip()
        if exit_code != 0 or errors:
            # Confirm the graph still exists before treating a write failure as
            # a bad configuration. A disappearing graph is a reconnect case.
            self._parameter_failure_pending = True
            self.refresh()
        elif self._running:
            if self._parameters_dirty:
                self.refresh()
            else:
                self.status_changed.emit("Microfone processado silenciado" if self._muted else
                    ("Áudio original" if self._bypass else "Escolha Yeti Processado na chamada"))
                if self._meter_enabled and not self._meter_started:
                    self._start_meter()

    def _parameters_error(self, error):
        if self._parameters_pending and error == QProcess.ProcessError.FailedToStart:
            self._parameters_pending = False
            self._parameters_deadline.stop()
            self._fail("Não foi possível aplicar os ajustes de voz")
        elif self._parameters_pending:
            self._parameters_pending = False
            self._parameters_deadline.stop()
            if self._active and self._running:
                self._parameter_failure_pending = True
                self.refresh()
            else:
                self._fail("Não foi possível aplicar os ajustes de voz")

    def _parameters_timeout(self):
        if self._parameters_pending:
            self._parameters_pending = False
            self._parameters.kill()
            self._parameter_failure_pending = True
            self.refresh()

    def _start_meter(self):
        self._meter_started = True
        self._pcm.clear()
        self._peak = 0.0
        self._meter.start("pw-cat", ["--record", "--raw", "--format=f32", "--rate=48000",
                                     "--channels=1", "--latency=20ms", "--target=" + OUTPUT_NODE,
                                     "--properties={ node.dont-fallback = true }", "-"])
        self._level_timer.start()

    def _read_meter(self):
        self._pcm.extend(bytes(self._meter.readAllStandardOutput()))
        length = len(self._pcm) // 4 * 4
        if length:
            samples = array("f")
            samples.frombytes(self._pcm[:length])
            del self._pcm[:length]
            peak = max((abs(value) for value in samples if math.isfinite(value)), default=0.0)
            self._peak = max(self._peak, peak)

    def _emit_level(self):
        self.level_changed.emit(max(-60.0, 20 * math.log10(max(self._peak, 1e-6))))
        self._peak = 0.0

    def _worker_stderr(self):
        self._diagnostics.extend(bytes(self._worker.readAllStandardError()))
        del self._diagnostics[:-4000]

    def _worker_finished(self, *_):
        if self._running and self._active:
            self._recover("Reconectando o motor de áudio…")
        elif self._starting:
            self._fail("O motor de áudio parou. Ative novamente para tentar outra vez.")
        else:
            self._cleanup_temporary_if_worker_stopped()

    def _worker_error(self, error):
        if error == QProcess.ProcessError.FailedToStart and (self._running or self._starting):
            self._fail("Não foi possível iniciar o motor de áudio")
        elif self._running and self._active:
            self._recover("Reconectando o motor de áudio…")
        elif self._starting:
            self._fail("Não foi possível iniciar o motor de áudio")

    def _meter_finished(self, *_):
        if self._running and self._active:
            self._recover("Reconectando o medidor de áudio…")

    def _meter_error(self, error):
        if self._running and error == QProcess.ProcessError.FailedToStart:
            self._fail("Não foi possível abrir o medidor de nível")
        elif self._running and self._active:
            self._recover("Reconectando o medidor de áudio…")

    def _start_timeout(self, generation):
        if generation == self._generation and self._starting:
            if self._active and self._retrying:
                self._recover("Aguardando o áudio ficar disponível…")
            else:
                self._fail("A entrada de áudio não ficou pronta. Confira o PipeWire e tente novamente.")

    def _fail(self, message):
        self.stop()
        self.error_occurred.emit(message)

    def stop(self):
        self._stopping = True
        self._generation += 1
        self._retry_timer.stop()
        self._set_active(False)
        self._starting = False
        self._start_requested = False
        self._running = False
        self._set_muted(False)
        self._recovering = False
        self._retrying = False
        self._parameter_failure_pending = False
        self._stale_nodes_attempts = 0
        self._meter_started = False
        self._parameters_pending = False
        self._parameters_dirty = False
        self._probe_pending = False
        self._probe_deadline.stop()
        self._parameters_deadline.stop()
        self._level_timer.stop()
        self._refresh_timer.setInterval(2000)
        self._refresh_timer.start()
        for process in (self._probe, self._parameters, self._meter, self._worker):
            if process.state() != QProcess.ProcessState.NotRunning:
                process.terminate()
                if not process.waitForFinished(100):
                    process.kill()
                    process.waitForFinished(100)
        if self._temporary:
            self._temporary.cleanup()
            self._temporary = None
        self._source = None
        self._capture_id = None
        self._pcm.clear()
        self._peak = 0.0
        self._stopping = False
        self.running_changed.emit(False)
        self.level_changed.emit(-60.0)
        self.status_changed.emit("Tratamento pausado")
