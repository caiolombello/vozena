"""Opt-in integration checks. Synthetic audio is routed only to an owned null sink."""

from array import array
from concurrent.futures import ThreadPoolExecutor
import math
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile
import time
import unittest
import uuid

from PySide6.QtWidgets import QApplication

from yeti_voice.engine import VoiceController, graph_snapshot, node_named
from yeti_voice.processing import CAPTURE_NODE, OUTPUT_NODE, make_config, props_payload, serialize_config, spa_value
from yeti_voice.settings import Settings
from yeti_voice.voice_test import VoiceTestController


def wait_until(predicate, timeout=6):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if result := predicate():
            return result
        time.sleep(.025)
    raise AssertionError("Timed out waiting for PipeWire")


def parameters(node_id):
    # pw-cli prints floats with the locale's decimal separator ("0,850000" in pt_BR).
    output = subprocess.check_output(["pw-cli", "enum-params", str(node_id), "Props"], text=True, timeout=2,
                                     env={**os.environ, "LC_ALL": "C"})
    return {name: (value == "true" if kind == "Bool" else float(value))
            for name, kind, value in re.findall(r'String "([^"\n]+)"\s+(Float|Int|Bool) (\S+)', output)}


def default_source():
    return subprocess.check_output(["pactl", "get-default-source"], text=True, timeout=2).strip()


def wait_for_parameters(node_id, expected):
    def applied():
        values = parameters(node_id)
        return values if all(abs(values.get(key, float("inf")) - value) < 1e-5
                             for key, value in expected.items()) else None
    return wait_until(applied)


def rms(samples):
    return math.sqrt(sum(value * value for value in samples) / len(samples))


@unittest.skipUnless(os.environ.get("YETI_RUN_PIPEWIRE_TESTS") == "1", "opt-in PipeWire integration")
class PipeWireIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_owned_graph_recovers_after_suspend_and_source_removal_while_muted(self):
        """Only graph metadata is consumed; the physical capture stays passive."""
        before = default_source()
        controller = VoiceController(meter_enabled=False)
        errors = []
        controller.error_occurred.connect(errors.append)
        settings = Settings(82, 21, -3.5)
        try:
            controller.start(settings)
            wait_until(lambda: controller.running or errors)
            self.assertFalse(errors)
            controller.set_mute(True)
            controller.set_bypass(True)
            original = node_named(graph_snapshot(), CAPTURE_NODE)
            initial_serial = original['info']['props']['object.serial']
            wait_for_parameters(original['id'], {'compare:Gain 1': 0, 'compare:Gain 2': 0})

            controller.set_suspended(True)
            wait_until(lambda: node_named(graph_snapshot(), OUTPUT_NODE) is None)
            self.assertTrue(controller.active)
            self.assertTrue(controller.muted)
            self.assertFalse(controller.running)
            controller.set_suspended(False)
            wait_until(lambda: controller.running or errors, timeout=8)
            self.assertFalse(errors)
            resumed = node_named(graph_snapshot(), CAPTURE_NODE)
            self.assertNotEqual(resumed['info']['props']['object.serial'], initial_serial)
            wait_for_parameters(resumed['id'], {'compare:Gain 1': 0, 'compare:Gain 2': 0,
                                                'blend:Gain 2': .82})

            # Destroy only our virtual node to exercise actual graph recovery.
            processed = node_named(graph_snapshot(), OUTPUT_NODE)
            removed_serial = processed['info']['props']['object.serial']
            subprocess.run(['pw-cli', 'destroy', str(processed['id'])], check=True,
                           capture_output=True, timeout=2)
            def replaced():
                current = node_named(graph_snapshot(), OUTPUT_NODE)
                return (current and current['info']['props']['object.serial'] != removed_serial
                        and controller.running) or bool(errors)
            wait_until(replaced, timeout=10)
            self.assertFalse(errors)
            self.assertTrue(controller.active)
            self.assertTrue(controller.muted)
            self.assertTrue(controller._bypass)
            self.assertEqual(controller._settings, settings)
            recovered = node_named(graph_snapshot(), CAPTURE_NODE)
            wait_for_parameters(recovered['id'], {'compare:Gain 1': 0, 'compare:Gain 2': 0})
            self.assertEqual(default_source(), before)
        finally:
            controller.stop()
            controller._refresh_timer.stop()
            wait_until(lambda: node_named(graph_snapshot(), OUTPUT_NODE) is None)
        self.assertFalse(controller.active)
        self.assertEqual(default_source(), before)

    def test_voice_sample_records_and_plays_without_changing_meeting_controls(self):
        before = default_source()
        fixture_name = 'yeti_voice.test.sink.' + uuid.uuid4().hex
        fixture = None
        meeting = VoiceController(meter_enabled=False)
        preview = VoiceTestController(duration_seconds=2, source_name=fixture_name,
                                      playback_target=fixture_name)
        errors = []
        meeting.error_occurred.connect(errors.append)
        preview.error_occurred.connect(errors.append)
        properties = {'factory.name': 'support.null-audio-sink', 'node.name': fixture_name,
                      'media.class': 'Audio/Sink', 'object.linger': True, 'node.virtual': True,
                      'audio.channels': 1, 'audio.position': ['MONO'], 'priority.session': 0}
        try:
            subprocess.run(['pw-cli', 'create-node', 'adapter', spa_value(properties)],
                           check=True, capture_output=True, timeout=2)
            fixture = wait_until(lambda: node_named(graph_snapshot(), fixture_name))
            meeting.start(Settings(40, 15, -2))
            wait_until(lambda: meeting.running or errors)
            self.assertFalse(errors)
            meeting.set_bypass(True)
            meeting.set_mute(True)
            capture = node_named(graph_snapshot(), CAPTURE_NODE)
            initial = wait_for_parameters(capture['id'], {'blend:Gain 2': .4,
                'compare:Gain 1': 0, 'compare:Gain 2': 0})
            preview.record(Settings())
            wait_until(lambda: preview.state == 'recording' or errors)
            self.assertFalse(errors)
            common = ['--raw', '--format=f32', '--rate=48000', '--channels=1', '--latency=20ms',
                      '--properties={ node.dont-fallback = true }', '--target=' + fixture_name, '-']
            generator = random.Random(908)
            signal = array('f', (generator.uniform(-.04, .04) for _ in range(96000))).tobytes()
            with ThreadPoolExecutor(max_workers=1) as pool:
                player = pool.submit(subprocess.run, ['pw-cat', '--playback', *common],
                                     input=signal, capture_output=True, timeout=5)
                wait_until(lambda: preview.has_clip or errors)
                result = player.result(timeout=6)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertFalse(errors)
            self.assertEqual(preview.sample.duration_seconds, 2)
            # A section of the original channel must be the actual injected PCM,
            # rather than unrelated noise or a second capture at another time.
            original_chunk = preview.sample.original[48000 * 4:48000 * 4 + 1024]
            self.assertGreaterEqual(signal.find(original_chunk), 0)
            original, processed = array('f'), array('f')
            original.frombytes(preview.sample.original)
            processed.frombytes(preview.sample.processed)
            original_rms = rms(original[24000:72000])
            processed_rms = rms(processed[24000:72000])
            self.assertGreater(original_rms, .015)
            self.assertLess(processed_rms, original_rms * .7)
            self.assertGreater(processed_rms, original_rms * .01)
            preview.play('processed')  # This explicitly targets only the owned null sink.
            wait_until(lambda: preview.state == 'ready' or errors)
            self.assertFalse(errors)
            self.assertTrue(meeting.running)
            after = parameters(capture['id'])
            for key in ('blend:Gain 2', 'presence:Gain', 'gain:Gain 1',
                        'compare:Gain 1', 'compare:Gain 2'):
                self.assertAlmostEqual(initial[key], after[key], places=5)
            self.assertEqual(default_source(), before)
            print(f'Voice-test PipeWire RMS: original={original_rms:.6f}, processed={processed_rms:.6f}')
        finally:
            preview.close()
            meeting.stop()
            meeting._refresh_timer.stop()
            if fixture is not None:
                current = node_named(graph_snapshot(), fixture_name)
                if current:
                    subprocess.run(['pw-cli', 'destroy', str(current['id'])], check=True,
                                   capture_output=True, timeout=2)
            wait_until(lambda: node_named(graph_snapshot(), OUTPUT_NODE) is None)
        self.assertIsNone(preview.sample)
        self.assertEqual(default_source(), before)

    def test_live_controls_and_stop_preserve_default_microphone(self):
        before = default_source()
        controller = VoiceController(meter_enabled=False)
        errors = []
        controller.error_occurred.connect(errors.append)
        try:
            controller.start(Settings())
            wait_until(lambda: controller.running or errors)
            self.assertFalse(errors)
            self.assertTrue(controller.running)
            self.assertEqual(default_source(), before)
            controller.update_settings(Settings(85, 45, -2.5))
            capture = node_named(graph_snapshot(), CAPTURE_NODE)
            values = wait_for_parameters(capture["id"], {"blend:Gain 2": .85,
                "gain:Gain 1": 10 ** (-2.5 / 20), "presence:Gain": 1.8})
            self.assertAlmostEqual(values["blend:Gain 2"], .85, places=5)
            self.assertAlmostEqual(values["gain:Gain 1"], 10 ** (-2.5 / 20), places=5)
            self.assertAlmostEqual(values["presence:Gain"], 1.8, places=5)
            self.assertAlmostEqual(values["dry_delay:Delay (s)"], .01, places=5)
            controller.set_mute(True)
            values = wait_for_parameters(capture["id"], {"compare:Gain 1": 0, "compare:Gain 2": 0})
            self.assertEqual(values["compare:Gain 1"], 0)
            self.assertEqual(values["compare:Gain 2"], 0)
            controller.set_mute(False)
            controller.set_bypass(True)
            values = wait_for_parameters(capture["id"], {"compare:Gain 1": 1, "compare:Gain 2": 0})
            self.assertEqual(values["compare:Gain 1"], 1)
            self.assertEqual(values["compare:Gain 2"], 0)
        finally:
            controller.stop()
            controller._refresh_timer.stop()
            wait_until(lambda: node_named(graph_snapshot(), OUTPUT_NODE) is None)
        self.assertEqual(default_source(), before)
        self.assertFalse(errors)

    def test_synthetic_audio_is_processed_and_muted_in_realtime(self):
        before = default_source()
        suffix = uuid.uuid4().hex[:8]
        fixture_name = "yeti_voice.test.sink." + suffix
        output_name = "yeti_voice.test.source." + suffix
        capture_name = "yeti_voice.test.capture." + suffix
        fixture = None
        worker = None
        properties = {
            "factory.name": "support.null-audio-sink", "node.name": fixture_name,
            "node.description": "Yeti synthetic test", "media.class": "Audio/Sink",
            "object.linger": True, "audio.channels": 1, "audio.position": ["MONO"],
            "node.virtual": True, "priority.session": 0,
        }
        try:
            subprocess.run(["pw-cli", "create-node", "adapter", spa_value(properties)],
                           check=True, capture_output=True, timeout=2)
            fixture = wait_until(lambda: node_named(graph_snapshot(), fixture_name))
            with tempfile.TemporaryDirectory(prefix="yeti-synthetic-") as directory:
                config = make_config(Settings(), fixture_name, output_node=output_name, capture_node=capture_name)
                config["context.modules"][-1]["args"]["capture.props"]["stream.capture.sink"] = True
                path = Path(directory) / "fixture.conf"
                path.write_text(serialize_config(config))
                worker = subprocess.Popen(["pipewire", "-c", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                capture = wait_until(lambda: node_named(graph_snapshot(), capture_name))
                wait_until(lambda: node_named(graph_snapshot(), output_name))
                generator = random.Random(725)
                source_samples = [generator.uniform(-.04, .04) for _ in range(96000)]

                def read_mode(*, bypass=False, muted=False):
                    subprocess.run(["pw-cli", "set-param", str(capture["id"]), "Props",
                                    props_payload(Settings(), bypass=bypass, muted=muted)],
                                   check=True, capture_output=True, timeout=2)
                    common = ["--raw", "--format=f32", "--rate=48000", "--channels=1", "--latency=20ms",
                              "--properties={ node.dont-fallback = true }"]
                    recorder = subprocess.Popen(["pw-cat", "--record", *common, "--target=" + output_name,
                                                 "--sample-count=96000", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    try:
                        with ThreadPoolExecutor(max_workers=1) as pool:
                            future = pool.submit(recorder.communicate, timeout=10)
                            time.sleep(.15)
                            player = subprocess.run(["pw-cat", "--playback", *common, "--target=" + fixture_name, "-"],
                                                    input=array("f", source_samples).tobytes(), capture_output=True, timeout=10)
                            self.assertEqual(player.returncode, 0, player.stderr.decode())
                            payload, errors = future.result(timeout=12)
                        self.assertFalse(errors, errors.decode())
                        self.assertEqual(len(payload), 96000 * 4)
                        # PipeWire 1.6.9 quits sample-count recording without setting
                        # data.drained, so its fully completed recording returns 1.
                        # https://github.com/PipeWire/pipewire/blob/1.6.9/src/tools/pw-cat.c
                        self.assertIn(recorder.returncode, (0, 1))
                        samples = array("f")
                        samples.frombytes(payload)
                        self.assertEqual(len(samples), 96000)
                        self.assertTrue(all(math.isfinite(value) for value in samples))
                        return samples[24000:80000]
                    finally:
                        if recorder.poll() is None:
                            recorder.kill()
                            recorder.communicate(timeout=2)

                original = read_mode(bypass=True)
                treated = read_mode()
                muted = read_mode(muted=True)
                self.assertAlmostEqual(rms(original) / rms(source_samples), 1, delta=.05)
                self.assertGreater(rms(treated), rms(original) * .01)
                self.assertLess(rms(treated), rms(original) * .7)
                self.assertLess(max(abs(value) for value in muted), 1e-7)
                print(f"Synthetic PipeWire RMS: original={rms(original):.6f}, treated={rms(treated):.6f}, mute={rms(muted):.6f}")
        finally:
            if worker is not None:
                worker.terminate()
                worker.communicate(timeout=5)
            if fixture is not None:
                current = node_named(graph_snapshot(), fixture_name)
                if current:
                    subprocess.run(["pw-cli", "destroy", str(current["id"])], check=True, capture_output=True, timeout=2)
        self.assertIsNone(node_named(graph_snapshot(), output_name))
        self.assertIsNone(node_named(graph_snapshot(), fixture_name))
        self.assertEqual(default_source(), before)
