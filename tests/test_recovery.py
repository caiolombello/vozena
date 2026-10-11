"""Recovery behavior is tested with synthetic PipeWire metadata only."""

import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication

from yeti_voice.engine import VoiceController
from yeti_voice.processing import make_config
from yeti_voice.settings import Settings


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.graph = Path(self.directory.name) / "graph.json"
        self.graph.write_text("[]")
        dump = Path(self.directory.name) / "pw-dump"
        dump.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib, sys\n"
            f"sys.stdout.write(pathlib.Path({str(self.graph)!r}).read_text())\n"
        )
        dump.chmod(0o700)
        self.path = patch.dict(os.environ, {"PATH": self.directory.name + os.pathsep + os.environ["PATH"]})
        self.path.start()
        self.controller = VoiceController(meter_enabled=False)

    def tearDown(self):
        self.controller.stop()
        self.controller._refresh_timer.stop()
        self.path.stop()
        self.directory.cleanup()

    def pump(self, seconds=0.2):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            QApplication.processEvents()
            time.sleep(0.005)

    def test_missing_yeti_keeps_activation_intent_and_retries_until_stopped(self):
        with patch("yeti_voice.engine.check_dependencies"):
            self.controller.start(Settings())
        self.pump(0.35)
        self.assertTrue(self.controller.active)
        self.assertFalse(self.controller.running)
        self.assertTrue(self.controller._retry_timer.isActive())

        self.controller.set_mute(True)
        self.controller.set_bypass(True)
        self.controller.set_suspended(True)
        self.assertTrue(self.controller.active)
        self.assertTrue(self.controller.muted)
        self.assertTrue(self.controller._bypass)
        self.assertFalse(self.controller._retry_timer.isActive())

        self.controller.set_suspended(False)
        self.pump(0.1)
        self.assertTrue(self.controller.active)
        self.assertTrue(self.controller.muted)
        self.controller.stop()
        self.pump(0.1)
        self.assertFalse(self.controller.active)
        self.assertFalse(self.controller._retry_timer.isActive())

    def test_recovery_preserves_user_settings_mute_bypass_and_closes_graph(self):
        settings = Settings(noise=82, clarity=21, gain_db=-3.5)
        self.controller._set_active(True)
        self.controller._settings = settings
        self.controller._set_muted(True)
        self.controller._bypass = True
        self.controller._running = True
        self.controller._starting = True
        self.controller._start_requested = True
        self.controller._recover("Aguardando reconexão")

        self.assertTrue(self.controller.active)
        self.assertTrue(self.controller.muted)
        self.assertTrue(self.controller._bypass)
        self.assertEqual(self.controller._settings, settings)
        self.assertFalse(self.controller.running)
        self.assertFalse(self.controller._starting)
        self.assertFalse(self.controller._start_requested)
        self.assertTrue(self.controller._retry_timer.isActive())

    def test_new_graph_starts_muted_before_any_stream_can_open(self):
        self.controller._set_active(True)
        self.controller._set_muted(True)
        self.controller._bypass = True
        built_configs = []

        def build_config(*args, **kwargs):
            config = make_config(*args, **kwargs)
            built_configs.append(config)
            return config

        with patch("yeti_voice.engine.make_config", side_effect=build_config) as build, \
             patch.object(self.controller._worker, "start"):
            self.controller._launch_worker("synthetic.yeti")

        build.assert_called_once_with(
            self.controller._settings, "synthetic.yeti", bypass=True, muted=True)
        args = built_configs[0]["context.modules"][-1]["args"]
        compare = next(node for node in args["filter.graph"]["nodes"] if node["name"] == "compare")
        self.assertEqual(compare["control"], {"Gain 1": 0.0, "Gain 2": 0.0})

    def test_retry_callbacks_cannot_reactivate_after_explicit_stop(self):
        with patch("yeti_voice.engine.check_dependencies"):
            self.controller.start(Settings())
        self.pump(0.1)
        generation = self.controller._generation
        self.controller.stop()
        self.controller._start_timeout(generation)
        self.controller._meter_finished()
        self.controller._worker_finished()
        self.controller._retry()
        self.pump(0.1)
        self.assertFalse(self.controller.active)
        self.assertFalse(self.controller.running)
        self.assertFalse(self.controller._start_requested)

    def test_healthy_stream_loss_recovers_without_losing_intent_or_mute(self):
        settings = Settings(noise=77, clarity=18, gain_db=-2.5)
        callbacks = (
            self.controller._worker_finished,
            self.controller._meter_finished,
            lambda: self.controller._worker_error(QProcess.ProcessError.Crashed),
            lambda: self.controller._meter_error(QProcess.ProcessError.Crashed),
        )
        for callback in callbacks:
            self.controller._set_active(True)
            self.controller._set_muted(True)
            self.controller._settings = settings
            self.controller._bypass = True
            self.controller._running = True
            callback()
            self.assertTrue(self.controller.active)
            self.assertFalse(self.controller.running)
            self.assertTrue(self.controller.muted)
            self.assertTrue(self.controller._bypass)
            self.assertEqual(self.controller._settings, settings)
            self.assertTrue(self.controller._retry_timer.isActive())

            # Exercise the queued retry through the fake pw-dump process.
            self.controller._retry_timer.stop()
            self.controller._retry()
            self.pump(0.1)
            self.assertTrue(self.controller.active)
            self.assertTrue(self.controller.muted)
            self.assertFalse(self.controller.running)
            self.controller.stop()

    def test_stop_during_suspend_keeps_os_suspend_state_and_passive_polling(self):
        self.controller.set_suspended(True)
        self.controller.stop()
        self.assertTrue(self.controller._suspended)
        self.assertTrue(self.controller._refresh_timer.isActive())
        self.controller.start(Settings())
        self.assertFalse(self.controller.active)
        self.controller.set_suspended(False)
        with patch("yeti_voice.engine.check_dependencies"):
            self.controller.start(Settings())
        self.assertTrue(self.controller.active)

    def test_parameter_failure_recovers_when_graph_disappears(self):
        self.controller._set_active(True)
        self.controller._running = True
        self.controller._parameters_pending = True
        self.controller._parameters_finished(1, None)
        self.pump(0.15)
        self.assertTrue(self.controller.active)
        self.assertFalse(self.controller.running)
        self.assertTrue(self.controller._retry_timer.isActive())

    def test_parameter_failure_with_healthy_graph_is_fatal_configuration_error(self):
        source = {
            "id": 1,
            "info": {"props": {
                "media.class": "Audio/Source",
                "alsa.components": "USBb58e:9e84",
                "node.name": "alsa_input.synthetic-yeti",
                "alsa.card_name": "Blue Yeti",
            }},
        }
        capture = {"id": 2, "info": {"props": {"node.name": "yeti_voice.capture"}}}
        output = {"id": 3, "info": {"props": {"node.name": "yeti_voice.processed"}}}
        self.graph.write_text(json.dumps([source, capture, output]))
        errors = []
        self.controller.error_occurred.connect(errors.append)
        self.controller._set_active(True)
        self.controller._running = True
        self.controller._source = "alsa_input.synthetic-yeti"
        self.controller._parameters_pending = True
        self.controller._parameters_finished(1, None)
        self.pump(0.15)
        self.assertFalse(self.controller.active)
        self.assertEqual(len(errors), 1)

    def test_parameter_timeout_recovers_and_qprocess_start_error_stays_fatal(self):
        self.controller._set_active(True)
        self.controller._running = True
        self.controller._parameters_pending = True
        self.controller._parameters_timeout()
        self.pump(0.15)
        self.assertTrue(self.controller.active)
        self.assertFalse(self.controller.running)
        self.assertTrue(self.controller._retry_timer.isActive())

        self.controller._set_active(True)
        self.controller._running = True
        errors = []
        self.controller.error_occurred.connect(errors.append)
        self.controller._worker_error(QProcess.ProcessError.FailedToStart)
        self.assertFalse(self.controller.active)
        self.assertEqual(len(errors), 1)
