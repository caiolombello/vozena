"""Talking-while-muted detection must ignore steady room sound."""

from array import array
import math
import random
import unittest

from yeti_voice.speech import SpeechDetector

RATE = 48000


def tone(seconds, dbfs, *, seed=1):
    generator = random.Random(seed)
    amplitude = 10 ** (dbfs / 20) * math.sqrt(2)
    return [amplitude * math.sin(2 * math.pi * 180 * n / RATE) * (0.8 + 0.4 * generator.random())
            for n in range(int(seconds * RATE))]


def noise(seconds, dbfs, *, seed=2):
    generator = random.Random(seed)
    amplitude = 10 ** (dbfs / 20) * math.sqrt(3)
    return [generator.uniform(-amplitude, amplitude) for _ in range(int(seconds * RATE))]


def speech(seconds, dbfs):
    samples = []
    while len(samples) < seconds * RATE:
        samples += tone(.22, dbfs) + noise(.08, -62)
    return samples


def feed(detector, samples, chunk=4096):
    payload = array("f", samples).tobytes()
    return [detector.feed(payload[start:start + chunk]) for start in range(0, len(payload), chunk)]


class SpeechDetectorTests(unittest.TestCase):
    def test_quiet_room_never_triggers(self):
        self.assertFalse(any(feed(SpeechDetector(), noise(5, -62))))

    def test_steady_fan_noise_never_triggers(self):
        self.assertFalse(any(feed(SpeechDetector(), noise(6, -30))))

    def test_speech_after_room_tone_triggers_within_a_second(self):
        detector = SpeechDetector()
        self.assertFalse(any(feed(detector, noise(2, -62))))
        results = feed(detector, speech(2, -24), chunk=1920 * 4)
        first = results.index(True)
        self.assertLess((first + 1) * 1920 / RATE, 1.0)

    def test_short_click_does_not_trigger(self):
        detector = SpeechDetector()
        samples = noise(2, -62) + tone(.15, -10) + noise(2, -62)
        self.assertFalse(any(feed(detector, samples)))


if __name__ == "__main__":
    unittest.main()
