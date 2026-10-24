"""Short voice samples remain in RAM for explicit original/processed listening."""

from array import array
from dataclasses import dataclass
import json
import math
from pathlib import Path
import tempfile
import time
import uuid

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .engine import PINNED_CAPTURE, PipeWireProcess, check_dependencies, find_yeti, node_named
from .processing import make_config, serialize_config
from .settings import Settings

SAMPLE_RATE = 48000
# The Yeti's mute button delivers digital silence; any open microphone,
# even in a quiet room, stays far above -80 dBFS.
SILENCE_PEAK = 10 ** (-80 / 20)


@dataclass(frozen=True)
class VoiceSample:
    original: bytes
    processed: bytes
    settings: Settings

    @property
    def duration_seconds(self):
        return len(self.original) / (SAMPLE_RATE * 4)

    @property
    def original_peak(self):
        samples = array("f")
        samples.frombytes(self.original)
        return max(map(abs, samples), default=0.0)

    def audio_for(self, mode):
        if mode not in ("original", "processed"):
            raise ValueError("Unknown listening mode")
        return self.original if mode == "original" else self.processed

    @classmethod
    def from_interleaved(cls, payload, settings, *, frames):
        if len(payload) != frames * 2 * 4:
            raise ValueError("Incomplete voice sample")
        samples = array("f")
        samples.frombytes(payload)
        if not all(math.isfinite(value) for value in samples):
            raise ValueError("Invalid voice sample")
        return cls(samples[::2].tobytes(), samples[1::2].tobytes(), settings)


def make_test_config(settings, source_name, *, output_node, capture_node, monitor=False):
    """One mono input publishes original/processed as the left/right channels.

    Independent stream channel counts are documented in PipeWire 1.6.9:
    https://pipewire.pages.freedesktop.org/pipewire/page_module_filter_chain.html
    """
    config = make_config(settings, source_name, output_node=output_node, capture_node=capture_node)
    args = config['context.modules'][-1]['args']
    graph = args['filter.graph']
    graph['nodes'].append({'type': 'builtin', 'name': 'original', 'label': 'copy'})
    graph['links'].append({'output': 'input:Out', 'input': 'original:In'})
    graph['outputs'] = ['original:Out', 'compare:Out']
    args['node.description'] = 'Vozena · teste de voz'
    args['audio.channels'] = 2
    args['audio.position'] = ['FL', 'FR']
    args['capture.props'].update({'audio.channels': 1, 'audio.position': ['MONO']})
    if monitor:
        args['capture.props']['stream.capture.sink'] = True
    args['playback.props'].update({'node.description': 'Vozena · teste de voz',
                                  'audio.channels': 2, 'audio.position': ['FL', 'FR']})
    return config


def default_sink(objects):
    for row in objects:
        if row.get('props', {}).get('metadata.name') == 'default':
            for item in row.get('metadata', []):
                if item.get('key') == 'default.audio.sink':
                    value = item.get('value')
                    if isinstance(value, str):
                        value = json.loads(value)
                    if isinstance(value, dict):
                        return value.get('name')
    return None


class VoiceTestController(QObject):
    """Explicit capture/listening, independent of the live meeting controller.

    The sample snapshots recording settings. It is replaced on record and
    forgotten on clear/close. No PCM files or background microphone capture.
    QProcess buffering/EOF follows Qt for Python 6.11's documented pattern:
    https://doc.qt.io/qtforpython-6.11/PySide6/QtCore/QProcess.html
    """
    state_changed = Signal(str)
    progress_changed = Signal(float)
    clip_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, parent=None, *, duration_seconds=10, source_name=None, playback_target=None):
        super().__init__(parent)
        if type(duration_seconds) is not int or not 1 <= duration_seconds <= 15:
            raise ValueError('Voice test duration must be 1–15 seconds')
        self._duration = duration_seconds
        self._source_override = source_name
        self._playback_target = playback_target
        self._state = 'idle'
        self._sample = None
        self._settings = Settings()
        self._buffer = bytearray()
        self._expected_bytes = duration_seconds * SAMPLE_RATE * 8
        self._temporary = None
        self._purpose = None
        self._probe_active = False
        self._stopping = False
        self._closed = False
        self._play_mode = None
        self._play_started = None
        self._capture_name = ''
        self._output_name = ''
        self._stderr = {name: bytearray() for name in ('probe', 'worker', 'recorder', 'player')}
        self._probe = PipeWireProcess(self)
        self._worker = PipeWireProcess(self)
        self._recorder = PipeWireProcess(self)
        self._player = PipeWireProcess(self)
        for name, process in self._processes():
            process.readyReadStandardError.connect(lambda name=name: self._read_stderr(name))
            process.errorOccurred.connect(lambda error, name=name: self._process_error(name, error))
        self._probe.finished.connect(self._probe_finished)
        self._worker.finished.connect(self._worker_finished)
        self._recorder.readyReadStandardOutput.connect(self._read_audio)
        self._recorder.finished.connect(self._record_finished)
        self._player.started.connect(self._write_audio)
        self._player.finished.connect(self._play_finished)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._probe_graph)
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.timeout.connect(self._timed_out)
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(100)
        self._progress_timer.timeout.connect(self._emit_progress)

    @property
    def state(self):
        return self._state

    @property
    def sample(self):
        return self._sample

    @property
    def has_clip(self):
        return self._sample is not None

    def _processes(self):
        return (('probe', self._probe), ('worker', self._worker),
                ('recorder', self._recorder), ('player', self._player))

    def record(self, settings):
        if self._closed or self._state in ('preparing', 'recording'):
            return
        self.clear()
        self._settings = settings
        token = uuid.uuid4().hex
        self._capture_name = 'yeti_voice.test.capture.' + token
        self._output_name = 'yeti_voice.test.source.' + token
        self._purpose = 'record'
        self._set_state('preparing')
        try:
            check_dependencies()
        except (OSError, ValueError, RuntimeError) as error:
            self._fail(str(error))
            return
        self._deadline.start(6000)
        self._poll_timer.start()
        self._probe_graph()

    def play(self, mode):
        if mode not in ('original', 'processed'):
            raise ValueError('Unknown listening mode')
        if self._closed or not self.has_clip or self._state in ('preparing', 'recording'):
            return
        self.cancel()
        self._play_mode = mode
        self._purpose = 'play'
        self._set_state('playing_' + mode)
        self._deadline.start(3000)
        self._probe_graph()

    def _probe_graph(self):
        if self._stopping or self._purpose is None or self._probe.state() != QProcess.ProcessState.NotRunning:
            return
        self._probe_active = True
        self._stderr['probe'].clear()
        self._probe.start('pw-dump', [])

    def _probe_finished(self, code, status):
        if self._stopping or not self._probe_active or self._purpose is None:
            return
        self._probe_active = False
        try:
            if code != 0 or status != QProcess.ExitStatus.NormalExit:
                raise ValueError('Audio service unavailable')
            objects = json.loads(bytes(self._probe.readAllStandardOutput()))
            if not isinstance(objects, list):
                raise ValueError('Invalid audio graph')
            if self._purpose == 'record':
                if self._temporary is None:
                    source = node_named(objects, self._source_override) if self._source_override else find_yeti(objects)
                    if source is None:
                        self._fail('Blue Yeti não detectado. Confira a conexão USB.')
                        return
                    props = source['info']['props']
                    self._temporary = tempfile.TemporaryDirectory(prefix='yeti-voice-test-')
                    path = Path(self._temporary.name) / 'voice-test.conf'
                    config = make_test_config(self._settings, props['node.name'],
                        output_node=self._output_name, capture_node=self._capture_name,
                        monitor=props.get('media.class') == 'Audio/Sink')
                    path.write_text(serialize_config(config))
                    self._worker.start('pipewire', ['-c', str(path)])
                elif node_named(objects, self._output_name) and node_named(objects, self._capture_name):
                    self._purpose = None
                    self._poll_timer.stop()
                    self._set_state('recording')
                    self._deadline.start((self._duration + 3) * 1000)
                    self._progress_timer.start()
                    self._recorder.start('pw-cat', ['--record', '--raw', '--format=f32', '--rate=48000',
                        '--channels=2', '--channel-map=FL,FR', '--latency=20ms',
                        PINNED_CAPTURE, '--target=' + self._output_name,
                        '--sample-count=' + str(self._duration * SAMPLE_RATE), '-'])
            elif self._purpose == 'play':
                target = self._playback_target or default_sink(objects)
                sink = node_named(objects, target) if target else None
                if not sink or sink['info']['props'].get('media.class') != 'Audio/Sink':
                    self._fail('Nenhuma saída de áudio disponível. Conecte seus fones e tente novamente.')
                    return
                self._purpose = None
                # Let WirePlumber route playback to the current output. Pinning the
                # default sink with node.dont-fallback made WirePlumber 0.5.13
                # (Ubuntu 26.04) destroy the stream right after linking, so nothing
                # was heard. See PINNED_CAPTURE in engine.py.
                target_args = ['--target=' + self._playback_target] if self._playback_target else []
                self._player.start('pw-cat', ['--playback', '--raw', '--format=f32', '--rate=48000',
                    '--channels=1', '--channel-map=MONO', '--latency=20ms', *target_args, '-'])
        except (OSError, ValueError, KeyError, TypeError):
            self._fail('Não foi possível preparar o teste. Confira o serviço de áudio.')

    def _read_audio(self):
        chunk = bytes(self._recorder.readAllStandardOutput())
        if self._stopping or self._state != 'recording':
            return
        if len(self._buffer) + len(chunk) > self._expected_bytes:
            self._fail('O teste recebeu áudio além do limite. Tente novamente.')
            return
        self._buffer.extend(chunk)

    def _record_finished(self, code, status):
        if self._stopping or self._state != 'recording':
            return
        self._read_audio()
        if self._state != 'recording':
            return
        self._read_stderr('recorder')
        try:
            # pw-cat 1.6.9 sample-count recording quits without data.drained and
            # returns 1; only exact, finite PCM with no diagnostics is accepted.
            # https://github.com/PipeWire/pipewire/blob/1.6.9/src/tools/pw-cat.c
            if code not in (0, 1) or status != QProcess.ExitStatus.NormalExit or self._stderr['recorder']:
                raise ValueError('Recording failed')
            sample = VoiceSample.from_interleaved(self._buffer, self._settings,
                                                  frames=self._duration * SAMPLE_RATE)
        except ValueError:
            self._fail('A gravação ficou incompleta. Confira o Yeti e tente novamente.')
            return
        if sample.original_peak < SILENCE_PEAK:
            self._fail('A gravação ficou em silêncio. Confira se o botão de mudo do Yeti está '
                       'ativado (luz vermelha piscando) e grave de novo.')
            return
        self._stop_processes()
        self._sample = sample
        self.clip_changed.emit(True)
        self._set_state('ready')
        self.progress_changed.emit(100.0)

    def _write_audio(self):
        if self._stopping or not self._state.startswith('playing_') or not self.has_clip:
            return
        payload = self._sample.audio_for(self._play_mode)
        if self._player.write(payload) != len(payload):
            self._fail('Não foi possível reproduzir a amostra.')
            return
        self._player.closeWriteChannel()
        self._play_started = time.monotonic()
        self._deadline.start((self._duration + 3) * 1000)
        self._progress_timer.start()

    def _play_finished(self, code, status):
        if self._stopping or not self._state.startswith('playing_'):
            return
        self._read_stderr('player')
        if code != 0 or status != QProcess.ExitStatus.NormalExit or self._stderr['player']:
            self._fail('A reprodução foi interrompida. Confira a saída de áudio.')
        else:
            self._stop_processes()
            self._set_state('ready')
            self.progress_changed.emit(100.0)

    def _read_stderr(self, name):
        process = dict(self._processes())[name]
        self._stderr[name].extend(bytes(process.readAllStandardError()))
        del self._stderr[name][:-4000]

    def _process_error(self, name, _error):
        if not self._stopping and (self._purpose is not None or self._state in ('recording', 'playing_original', 'playing_processed')):
            self._fail('Não foi possível executar o teste de voz. Confira o serviço de áudio.')

    def _worker_finished(self, *_):
        if not self._stopping and self._state in ('preparing', 'recording'):
            self._fail('O motor do teste de voz parou. Tente novamente.')

    def _emit_progress(self):
        if self._state == 'recording':
            value = len(self._buffer) * 100 / self._expected_bytes
        elif self._play_started is not None and self._state.startswith('playing_'):
            value = (time.monotonic() - self._play_started) * 100 / self._duration
        else:
            return
        self.progress_changed.emit(min(100.0, value))

    def _set_state(self, state):
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)

    def _timed_out(self):
        self._fail('O teste de voz não respondeu. Confira o áudio e tente novamente.')

    def _fail(self, message):
        self.cancel()
        self.error_occurred.emit(message)

    def _stop_processes(self):
        self._stopping = True
        self._purpose = None
        self._probe_active = False
        self._poll_timer.stop()
        self._deadline.stop()
        self._progress_timer.stop()
        for _name, process in self._processes():
            if process.state() != QProcess.ProcessState.NotRunning:
                process.terminate()
                if not process.waitForFinished(100):
                    process.kill()
                    process.waitForFinished(100)
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None
        self._buffer.clear()
        for buffer in self._stderr.values():
            buffer.clear()
        self._play_started = None
        self._stopping = False

    def cancel(self):
        self._stop_processes()
        self._set_state('ready' if self.has_clip else 'idle')
        self.progress_changed.emit(0.0)

    def clear(self):
        self.cancel()
        self._sample = None
        self.clip_changed.emit(False)
        self._set_state('idle')

    def close(self):
        self.clear()
        self._closed = True
