"""The UI remains responsive when PipeWire command-line clients stall."""

import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QApplication

from yeti_voice.engine import PipeWireProcess, VoiceController, default_node_name, node_consumers
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

    def test_level_meter_only_reads_while_the_window_wants_it(self):
        """An active reader keeps the Yeti capturing even with no meeting."""
        self.controller = controller = VoiceController()
        controller._running = controller._active = True
        statuses = []
        controller.status_changed.connect(statuses.append)
        with patch.object(controller._meter, "start") as start:
            controller.set_meter_wanted(False)
            controller._parameters_pending = True
            controller._parameters_finished(0, None)
            start.assert_not_called()
            controller.set_meter_wanted(True)
            self.assertEqual(start.call_count, 1)
            self.assertTrue(controller._level_timer.isActive())
            controller.set_meter_wanted(False)
        self.assertFalse(controller._meter_started)
        self.assertFalse(controller._level_timer.isActive())
        controller._meter_finished()
        controller._meter_error(QProcess.ProcessError.Crashed)
        self.assertNotIn("Reconectando o medidor de áudio…", statuses)
        self.assertTrue(controller.active)

    def test_pipewire_tools_run_without_library_log_noise(self):
        process = PipeWireProcess()
        with patch.dict(os.environ, {"PIPEWIRE_DEBUG": "4", "HOME_MARKER": "kept"}):
            process.start("true", [])
        process.waitForFinished(2000)
        environment = process.processEnvironment()
        self.assertEqual(environment.value("PIPEWIRE_DEBUG"), "0")
        self.assertEqual(environment.value("HOME_MARKER"), "kept")

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


def graph(*, links=(), default_source=None, configured_source=None):
    objects = [
        {"id": 10, "type": "PipeWire:Interface:Node", "info": {"props": {"node.name": OUTPUT_NODE}}},
        {"id": 11, "type": "PipeWire:Interface:Node", "info": {"props": {
            "node.name": "Chromium input", "application.name": "Google Chrome"}}},
        {"id": 12, "type": "PipeWire:Interface:Node", "info": {"props": {"node.name": "yeti_voice.meter",
            "application.name": "pw-cat"}}},
        {"id": 13, "type": "PipeWire:Interface:Node", "info": {"props": {
            "node.name": "ZOOM VoiceEngine", "node.description": "ZOOM VoiceEngine"}}},
        {"id": 14, "type": "PipeWire:Interface:Node", "info": {"props": {"node.name": "other.source"}}},
    ]
    for number, (output, target, state) in enumerate(links):
        objects.append({"id": 100 + number, "type": "PipeWire:Interface:Link", "info": {
            "output-node-id": output, "input-node-id": target, "state": state}})
    metadata = []
    if default_source:
        metadata.append({"key": "default.audio.source", "value": {"name": default_source}})
    if configured_source:
        # Some pw-dump versions print JSON metadata values as strings.
        metadata.append({"key": "default.configured.audio.source",
                         "value": '{ "name": "%s" }' % configured_source})
    objects.append({"props": {"metadata.name": "default"}, "metadata": metadata})
    return objects


class GraphUsageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_consumers_are_apps_reading_the_processed_microphone(self):
        objects = graph(links=[(10, 11, "active"), (10, 11, "active"), (10, 12, "active"),
                               (10, 13, "paused"), (14, 13, "active"), (10, 14, "error")])
        self.assertEqual(node_consumers(objects, OUTPUT_NODE), ["Google Chrome", "ZOOM VoiceEngine"])
        self.assertEqual(node_consumers(objects, "missing.node"), [])

    def test_default_metadata_accepts_objects_and_json_strings(self):
        objects = graph(default_source=OUTPUT_NODE, configured_source="alsa_input.yeti")
        self.assertEqual(default_node_name(objects, "default.audio.source"), OUTPUT_NODE)
        self.assertEqual(default_node_name(objects, "default.configured.audio.source"), "alsa_input.yeti")
        self.assertIsNone(default_node_name(objects, "default.audio.sink"))

    def test_controller_publishes_usage_only_while_running(self):
        with patch.object(VoiceController, "refresh"):
            controller = VoiceController(meter_enabled=False)
        consumers, defaults = [], []
        controller.consumers_changed.connect(consumers.append)
        controller.default_source_changed.connect(lambda *state: defaults.append(state))
        objects = graph(links=[(10, 11, "active")], default_source=OUTPUT_NODE, configured_source=OUTPUT_NODE)
        controller._publish_usage(objects)
        self.assertEqual(consumers, [])
        self.assertEqual(defaults, [(True, OUTPUT_NODE)])
        controller._running = True
        controller._publish_usage(objects)
        controller._publish_usage(objects)
        self.assertEqual(consumers, [["Google Chrome"]])
        self.assertEqual(controller.consumers, ["Google Chrome"])
        controller._refresh_timer.stop()
        controller.stop()
        self.assertEqual(consumers[-1], [])
        controller._refresh_timer.stop()

    def test_default_source_is_configured_through_wireplumber_metadata(self):
        with patch.object(VoiceController, "refresh"):
            controller = VoiceController(meter_enabled=False)
        controller._refresh_timer.stop()
        with patch.object(controller._metadata, "start") as start:
            self.assertTrue(controller.set_default_source(OUTPUT_NODE))
            controller.set_default_source(None)
        self.assertEqual(start.call_args_list[0].args, ("pw-metadata", [
            "-n", "default", "0", "default.configured.audio.source",
            '{"name": "yeti_voice.processed"}', "Spa:String:JSON"]))
        self.assertEqual(start.call_args_list[1].args, ("pw-metadata", [
            "-n", "default", "-d", "0", "default.configured.audio.source"]))


class MuteWatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch.object(VoiceController, "refresh"):
            self.controller = VoiceController(meter_enabled=False)
        self.controller._refresh_timer.stop()
        self.controller._running = self.controller._active = True
        self.controller._source = "alsa_input.usb-yeti"

    def tearDown(self):
        with patch.object(VoiceController, "refresh"):
            self.controller.stop()
        self.controller._refresh_timer.stop()

    def test_passive_watch_runs_only_while_muted_in_a_meeting(self):
        watch = self.controller._mute_watch
        launches = []

        def launch(program, arguments=()):
            launches.append((program, list(arguments)))
            PipeWireProcess.start(watch, "sleep", ["5"])

        with patch.object(watch, "start", side_effect=launch), \
                patch.object(self.controller, "_push_parameters"):
            self.controller.set_mute(True)
            self.assertEqual(launches, [])
            self.controller._publish_usage(graph(links=[(10, 11, "active")]))
            self.assertEqual(len(launches), 1)
            program, arguments = launches[0]
            self.assertEqual(program, "pw-cat")
            self.assertIn("--target=alsa_input.usb-yeti", arguments)
            properties = next(argument for argument in arguments if argument.startswith("--properties="))
            self.assertIn("node.passive = true", properties)
            self.assertIn('node.name = "yeti_voice.mute-watch"', properties)
            self.assertNotEqual(watch.state(), QProcess.ProcessState.NotRunning)
            self.controller.set_mute(False)
            self.assertEqual(watch.state(), QProcess.ProcessState.NotRunning)
            self.controller.set_mute(True)
            self.assertEqual(len(launches), 2)
            self.controller.set_mute_watch_enabled(False)
            self.assertEqual(watch.state(), QProcess.ProcessState.NotRunning)

    def test_talking_alert_is_rate_limited(self):
        alerts = []
        self.controller.talking_while_muted.connect(lambda: alerts.append(True))
        self.controller._muted = True
        with patch.object(self.controller._mute_watch, "readAllStandardOutput", return_value=b"pcm"), \
                patch.object(self.controller._speech, "feed", return_value=True):
            self.controller._read_mute_watch()
            self.controller._read_mute_watch()
            self.assertEqual(len(alerts), 1)
            self.controller._last_talk_alert -= 31
            self.controller._read_mute_watch()
        self.assertEqual(len(alerts), 2)
