from array import array
import math
from types import SimpleNamespace
import unittest

from yeti_voice.settings import Settings


SAMPLE_RATE = 48_000


def pcm_segment(seconds, amplitude, frequency=180.0):
    return [
        amplitude * math.sin(2 * math.pi * frequency * index / SAMPLE_RATE)
        for index in range(round(seconds * SAMPLE_RATE))
    ]


def sample_from(values, settings=Settings(), processed=None):
    processed = values if processed is None else processed
    return SimpleNamespace(
        original=array("f", values).tobytes(),
        processed=array("f", processed).tobytes(),
        settings=settings,
    )


class CalibrationTest(unittest.TestCase):
    def test_clean_guided_capture_produces_bounded_suggestion_and_preserves_clarity(self):
        from yeti_voice.calibration import analyze_voice_sample

        silence = pcm_segment(3, 0.001, 91)
        speech = pcm_segment(7, 0.12)
        snapshot = Settings(noise=40, clarity=17, gain_db=0)

        result = analyze_voice_sample(sample_from(silence + speech, snapshot))

        self.assertTrue(result.valid)
        self.assertIsNotNone(result.suggestion)
        self.assertEqual(result.suggestion.clarity, 17)
        self.assertGreaterEqual(result.suggestion.noise, 0)
        self.assertLessEqual(result.suggestion.noise, 100)
        self.assertGreaterEqual(result.suggestion.gain_db, -12)
        self.assertLessEqual(result.suggestion.gain_db, 6)
        self.assertGreater(result.metrics.snr_db, 20)

    def test_sparse_noise_spikes_do_not_define_the_noise_floor(self):
        from yeti_voice.calibration import analyze_voice_sample

        silence = pcm_segment(3, 0.001, 91)
        for offset in (10_000, 80_000, 120_000):
            silence[offset : offset + 100] = [0.3] * 100
        speech = pcm_segment(7, 0.1)

        result = analyze_voice_sample(sample_from(silence + speech))

        self.assertTrue(result.valid)
        self.assertLess(result.metrics.noise_dbfs, -50)

    def test_hardware_clipping_refuses_a_suggestion(self):
        from yeti_voice.calibration import analyze_voice_sample

        silence = pcm_segment(3, 0.001, 91)
        speech = [1.0 if index % 2 else -1.0 for index in range(7 * SAMPLE_RATE)]

        result = analyze_voice_sample(sample_from(silence + speech))

        self.assertFalse(result.valid)
        self.assertIsNone(result.suggestion)
        self.assertIn("ganho físico", result.message.lower())

    def test_gain_is_delta_from_snapshot_using_processed_speech_level(self):
        from yeti_voice.calibration import analyze_voice_sample

        silence = pcm_segment(3, 0.001, 91)
        speech = pcm_segment(7, 0.1)
        processed = pcm_segment(3, 0.001, 91) + pcm_segment(7, 0.2)
        snapshot = Settings(noise=50, clarity=23, gain_db=-3.0)

        result = analyze_voice_sample(
            sample_from(silence + speech, snapshot, processed)
        )

        self.assertTrue(result.valid)
        self.assertAlmostEqual(result.suggestion.gain_db, -6.0, delta=0.5)
        self.assertEqual(result.suggestion.clarity, 23)

    def test_silent_processed_voice_refuses_a_suggestion(self):
        from yeti_voice.calibration import analyze_voice_sample

        original = pcm_segment(3, 0.001, 91) + pcm_segment(7, 0.1)
        processed = [0.0] * (10 * SAMPLE_RATE)

        result = analyze_voice_sample(sample_from(original, processed=processed))

        self.assertFalse(result.valid)
        self.assertIsNone(result.suggestion)
        self.assertIn("tratado", result.message.lower())

    def test_insufficient_speech_refuses_a_suggestion(self):
        from yeti_voice.calibration import analyze_voice_sample

        result = analyze_voice_sample(sample_from(pcm_segment(10, 0.001, 91)))

        self.assertFalse(result.valid)
        self.assertIsNone(result.suggestion)
        self.assertIn("fala", result.message.lower())

    def test_rejects_wrong_length_or_non_finite_pcm(self):
        from yeti_voice.calibration import analyze_voice_sample

        with self.assertRaises(ValueError):
            analyze_voice_sample(sample_from([0.0] * SAMPLE_RATE))
        values = [0.0] * (10 * SAMPLE_RATE)
        values[-1] = math.nan
        with self.assertRaises(ValueError):
            analyze_voice_sample(sample_from(values))
        malformed = sample_from([0.0] * (10 * SAMPLE_RATE))
        malformed.processed = malformed.processed[:-4]
        with self.assertRaises(ValueError):
            analyze_voice_sample(malformed)


if __name__ == "__main__":
    unittest.main()
