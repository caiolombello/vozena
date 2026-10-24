"""The UI remains responsive when PipeWire command-line clients stall."""

import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QApplication

from yeti_voice.engine import VoiceController
from yeti_voice.processing import OUTPUT_NODE
from yeti_voice.settings import Settings


class EngineResponsivenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        command = Path(self.directory.name) / "pw-dump"
        command.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(.4)\nprint('[]')\n")
        command.chmod(0o700)
        self.environment = patch.dict(os.environ, {"PATH": self.directory.name + os.pathsep + os.environ["PATH"]})
        self.environment.start()
        self.controller = None

    def tearDown(self):
        if self.controller is not None:
            self.controller.stop()
            self.controller._refresh_timer.stop()
        self.environment.stop()
        self.directory.cleanup()

    def pump(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(.005)

    def test_level_meter_stays_pinned_when_processed_microphone_is_the_default(self):
        """WirePlumber 0.5.13 destroyed a dont-fallback stream aimed at the default source."""
        self.controller = VoiceController(meter_enabled=False)
        with patch.object(self.controller._meter, "start") as start:
            self.controller._start_meter()
        program, arguments = start.call_args.args
        self.assertEqual(program, "pw-cat")
        self.assertIn("--target=" + OUTPUT_NODE, arguments)
        properties = next(argument for argument in arguments if argument.startswith("--properties="))
        self.assertIn("node.dont-fallback = true", properties)
        self.assertIn("node.dont-reconnect = true", properties)

    def test_slow_graph_probe_does_not_block_constructor_or_ui(self):
        ticks = []
        QTimer.singleShot(20, lambda: ticks.append(time.monotonic()))
        before = time.monotonic()
        self.controller = VoiceController(meter_enabled=False)
        self.assertLess(time.monotonic() - before, .15)
        self.pump(.15)
        self.assertTrue(ticks)
        self.assertEqual(self.controller.device_description, "")

    def test_stop_during_probe_cannot_start_a_late_audio_worker(self):
        self.controller = VoiceController(meter_enabled=False)
        errors = []
        self.controller.error_occurred.connect(errors.append)
        with patch("yeti_voice.engine.check_dependencies"):
            self.controller.start(Settings())
        self.controller.stop()
        self.pump(.5)
        self.assertFalse(self.controller.running)
        self.assertEqual(self.controller._worker.state(), QProcess.ProcessState.NotRunning)
        self.assertFalse(errors)

    def test_probe_timeout_enters_recovery_without_blocking_ui(self):
        self.controller = VoiceController(meter_enabled=False)
        errors, ticks = [], []
        self.controller.error_occurred.connect(errors.append)
        with patch("yeti_voice.engine.check_dependencies"):
            self.controller.start(Settings())
        self.controller._probe_deadline.start(50)
        QTimer.singleShot(20, lambda: ticks.append(True))
        self.pump(.2)
        self.assertTrue(ticks)
        self.assertEqual(errors, [])
        self.assertTrue(self.controller.active)
        self.assertFalse(self.controller.running)
        self.assertTrue(self.controller._retry_timer.isActive())
        self.assertEqual(self.controller._worker.state(), QProcess.ProcessState.NotRunning)
