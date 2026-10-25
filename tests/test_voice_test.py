"""Voice samples and the explicit, asynchronous record/listen workflow."""

from array import array
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from yeti_voice.settings import Settings
from yeti_voice.voice_test import VoiceSample, VoiceTestController


class VoiceSampleTests(unittest.TestCase):
    def test_original_and_processed_come_from_the_same_recorded_frames(self):
        payload = array('f', [0.25, 0.125, -0.5, -0.1, 0.75, 0.3]).tobytes()
        sample = VoiceSample.from_interleaved(payload, Settings(85, 45, -2), frames=3)
        original = array('f')
        original.frombytes(sample.audio_for('original'))
        processed = array('f')
        processed.frombytes(sample.audio_for('processed'))
        self.assertEqual(list(original), [.25, -.5, .75])
        self.assertAlmostEqual(processed[0], .125)
        self.assertAlmostEqual(processed[1], -.1)
        self.assertAlmostEqual(processed[2], .3)
        self.assertEqual(sample.settings, Settings(85, 45, -2))
        self.assertAlmostEqual(sample.duration_seconds, 3 / 48000)


class VoiceTestWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        commands = {
            'pw-dump': '''import json, os, pathlib, time
root = pathlib.Path(os.environ['YETI_TEST_COMMAND_DIR'])
time.sleep(float(os.environ.get('YETI_TEST_PROBE_DELAY', '0')))
objects = [{'id': 1, 'info': {'props': {'node.name': 'fixture.sink', 'media.class': 'Audio/Sink'}}},
 {'props': {'metadata.name': 'default'}, 'metadata': [{'key': 'default.audio.sink', 'value': {'name': 'fixture.sink'}}]}]
if not os.environ.get('YETI_TEST_NO_DEVICE'):
 objects.append({'id': 2, 'info': {'props': {'node.name': 'fixture.yeti', 'media.class': 'Audio/Source', 'alsa.components': 'USBb58e:9e84'}}})
if (root / 'nodes.json').exists():
 objects += json.loads((root / 'nodes.json').read_text())
print(json.dumps(objects))
''',
            'pipewire': '''import json, os, pathlib, re, signal, sys, time
root = pathlib.Path(os.environ['YETI_TEST_COMMAND_DIR'])
config = pathlib.Path(sys.argv[-1]).read_text()
names = re.findall(r'"node.name" = "([^"]+)"', config)
path = root / 'nodes.json'
path.write_text(json.dumps([{'id': n+10, 'info': {'props': {'node.name': name}}} for n,name in enumerate(names)]))
def finish(*_):
 path.unlink(missing_ok=True)
 sys.exit(0)
signal.signal(signal.SIGTERM, finish)
while True: time.sleep(.1)
''',
            'pw-cat': '''from array import array
import os, pathlib, sys, time
root = pathlib.Path(os.environ['YETI_TEST_COMMAND_DIR'])
with (root / 'calls.txt').open('a') as log: log.write(' '.join(sys.argv[1:]) + '\\n')
if os.environ.get('PIPEWIRE_DEBUG') != '0':
 # What every client prints without RTKit; it must not turn success into failure.
 sys.stderr.write('W mod.rt: Realtime scheduling disabled: insufficient realtime privileges\\n')
if '--record' in sys.argv:
 frames = int(next(arg.split('=')[1] for arg in sys.argv if arg.startswith('--sample-count=')))
 payload = array('f', [0.0, 0.0] if os.environ.get('YETI_TEST_SILENT') else [.25, .125]).tobytes() * frames
 if os.environ.get('YETI_TEST_SHORT_RECORD'): payload = payload[:len(payload)//2]
 time.sleep(float(os.environ.get('YETI_TEST_RECORD_DELAY', '.03')))
 sys.stdout.buffer.write(payload)
 sys.exit(1)
(root / 'played.raw').write_bytes(sys.stdin.buffer.read())
time.sleep(float(os.environ.get('YETI_TEST_PLAY_DELAY', '.03')))
''',
        }
        for name, code in commands.items():
            path = self.root / name
            path.write_text('#!/usr/bin/env python3\n' + code)
            path.chmod(0o700)
        self.environment = patch.dict(os.environ, {
            'PATH': str(self.root) + os.pathsep + os.environ['PATH'],
            'YETI_TEST_COMMAND_DIR': str(self.root),
        })
        self.environment.start()
        self.controller = VoiceTestController(duration_seconds=1)
        self.errors = []
        self.controller.error_occurred.connect(self.errors.append)

    def tearDown(self):
        self.controller.close()
        self.environment.stop()
        self.directory.cleanup()

    def wait_until(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            QApplication.processEvents()
            if predicate():
                return
            time.sleep(.005)
        self.fail('Voice test did not reach expected state')

    def test_recording_is_explicit_and_keeps_paired_audio_only_in_memory(self):
        self.assertEqual(self.controller.state, 'idle')
        self.assertFalse(self.controller.has_clip)
        self.assertFalse((self.root / 'calls.txt').exists())
        settings = Settings(85, 45, -2)
        self.controller.record(settings)
        self.assertEqual(self.controller.state, 'preparing')
        self.wait_until(lambda: self.controller.has_clip or self.errors)
        self.assertFalse(self.errors)
        self.assertEqual(self.controller.state, 'ready')
        sample = self.controller.sample
        self.assertEqual(sample.settings, settings)
        self.assertEqual(sample.duration_seconds, 1)
        self.assertEqual(sample.original, array('f', [.25] * 48000).tobytes())
        self.assertEqual(sample.processed, array('f', [.125] * 48000).tobytes())
        self.assertFalse((self.root / 'played.raw').exists())
        self.assertFalse((self.root / 'nodes.json').exists())

    def test_listening_plays_the_selected_version_and_keeps_the_sample(self):
        self.controller.record(Settings())
        self.wait_until(lambda: self.controller.has_clip or self.errors)
        self.assertFalse(self.errors)
        for mode, value in [('original', .25), ('processed', .125)]:
            self.controller.play(mode)
            self.assertEqual(self.controller.state, 'playing_' + mode)
            self.wait_until(lambda: self.controller.state == 'ready' or self.errors)
            self.assertFalse(self.errors)
            self.assertTrue(self.controller.has_clip)
            self.assertEqual((self.root / 'played.raw').read_bytes(),
                             array('f', [value] * 48000).tobytes())
        self.controller.clear()
        self.assertIsNone(self.controller.sample)
        self.assertEqual(self.controller.state, 'idle')

    def test_playback_follows_the_default_output_while_capture_stays_pinned(self):
        """WirePlumber 0.5.13 (Ubuntu 26.04) destroyed playback pinned to the default sink."""
        self.controller.record(Settings())
        self.wait_until(lambda: self.controller.has_clip or self.errors)
        self.controller.play('original')
        self.wait_until(lambda: self.controller.state == 'ready' or self.errors)
        self.assertFalse(self.errors)
        record, play = (self.root / 'calls.txt').read_text().splitlines()
        self.assertIn('--target=yeti_voice.test.source.', record)
        self.assertIn('node.dont-fallback = true', record)
        self.assertIn('node.dont-reconnect = true', record)
        self.assertNotIn('--target', play)
        self.assertNotIn('dont-fallback', play)

    def test_explicit_playback_target_is_still_honoured(self):
        self.controller.close()
        self.controller = VoiceTestController(duration_seconds=1, playback_target='fixture.sink')
        self.controller.error_occurred.connect(self.errors.append)
        self.controller.record(Settings())
        self.wait_until(lambda: self.controller.has_clip or self.errors)
        self.controller.play('processed')
        self.wait_until(lambda: self.controller.state == 'ready' or self.errors)
        self.assertFalse(self.errors)
        play = (self.root / 'calls.txt').read_text().splitlines()[-1]
        self.assertIn('--playback', play)
        self.assertIn('--target=fixture.sink', play)
        self.assertNotIn('dont-fallback', play)

    def test_cancel_before_probe_completion_never_records(self):
        with patch.dict(os.environ, {'YETI_TEST_PROBE_DELAY': '.3'}):
            self.controller.record(Settings())
            self.controller.cancel()
            self.wait_until(lambda: self.controller.state == 'idle')
            for _ in range(80):
                QApplication.processEvents()
                time.sleep(.005)
        self.assertFalse(self.controller.has_clip)
        self.assertFalse((self.root / 'calls.txt').exists())
        self.assertFalse(self.errors)

    def test_incomplete_recording_is_rejected_instead_of_offered_for_listening(self):
        with patch.dict(os.environ, {'YETI_TEST_SHORT_RECORD': '1'}):
            self.controller.record(Settings())
            self.wait_until(lambda: bool(self.errors))
        self.assertFalse(self.controller.has_clip)
        self.assertEqual(self.controller.state, 'idle')
        self.assertFalse((self.root / 'nodes.json').exists())

    def test_silent_recording_points_to_the_yeti_mute_button(self):
        with patch.dict(os.environ, {'YETI_TEST_SILENT': '1'}):
            self.controller.record(Settings())
            self.wait_until(lambda: bool(self.errors))
        self.assertIn('silêncio', self.errors[0])
        self.assertIn('mudo do Yeti', self.errors[0])
        self.assertFalse(self.controller.has_clip)
        self.assertEqual(self.controller.state, 'idle')

    def test_missing_yeti_never_falls_back_to_another_microphone(self):
        with patch.dict(os.environ, {'YETI_TEST_NO_DEVICE': '1'}):
            self.controller.record(Settings())
            self.wait_until(lambda: bool(self.errors))
        self.assertIn('não detectado', self.errors[0])
        self.assertFalse((self.root / 'calls.txt').exists())
        self.assertFalse(self.controller.has_clip)

    def test_cancel_recording_and_close_release_the_sample(self):
        with patch.dict(os.environ, {'YETI_TEST_RECORD_DELAY': '.5'}):
            self.controller.record(Settings())
            self.wait_until(lambda: self.controller.state == 'recording')
            self.controller.cancel()
        self.assertFalse(self.controller.has_clip)
        self.assertEqual(self.controller.state, 'idle')
        self.assertFalse((self.root / 'nodes.json').exists())
        self.controller.record(Settings())
        self.wait_until(lambda: self.controller.has_clip or self.errors)
        self.assertFalse(self.errors)
        self.controller.close()
        self.assertFalse(self.controller.has_clip)
        self.assertIsNone(self.controller.sample)
        self.assertEqual(self.controller.state, 'idle')

    def test_stopping_playback_keeps_the_clip_until_clear(self):
        self.controller.record(Settings())
        self.wait_until(lambda: self.controller.has_clip or self.errors)
        self.assertFalse(self.errors)
        with patch.dict(os.environ, {'YETI_TEST_PLAY_DELAY': '.5'}):
            self.controller.play('original')
            self.wait_until(lambda: (self.root / 'played.raw').exists())
            self.controller.cancel()
        self.assertEqual(self.controller.state, 'ready')
        self.assertTrue(self.controller.has_clip)
        self.controller.play('processed')
        self.wait_until(lambda: self.controller.state == 'ready' or self.errors)
        self.assertFalse(self.errors)

    def test_immediate_record_restart_cannot_receive_the_cancelled_attempt(self):
        self.controller.record(Settings(40, 15, -2))
        self.controller.cancel()
        self.controller.record(Settings(95, 40, 1))
        self.wait_until(lambda: self.controller.has_clip or self.errors)
        self.assertFalse(self.errors)
        self.assertEqual(self.controller.sample.settings, Settings(95, 40, 1))
        self.assertEqual(self.controller.state, 'ready')

    def test_slow_audio_service_keeps_ui_responsive_during_preparation(self):
        ticks = []
        with patch.dict(os.environ, {'YETI_TEST_PROBE_DELAY': '.3'}):
            QTimer.singleShot(20, lambda: ticks.append(True))
            before = time.monotonic()
            self.controller.record(Settings())
            self.assertLess(time.monotonic() - before, .15)
            self.wait_until(lambda: bool(ticks))
            self.assertEqual(self.controller.state, 'preparing')
            self.assertFalse(self.controller.has_clip)
            self.controller.cancel()
        self.assertFalse(self.errors)
