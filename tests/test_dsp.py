import math
import unittest

from yeti_voice.processing import make_config
from yeti_voice.settings import Settings
from ladspa_host import process, rms, white_noise


def plugin_node(name):
    graph = make_config(Settings(), "offline-fixture")["context.modules"][-1]["args"]["filter.graph"]
    return next(node for node in graph["nodes"] if node["name"] == name)


class DspBehaviorTests(unittest.TestCase):
    sample_rate = 48000

    def test_compressor_reduces_quiet_loud_level_difference(self):
        node = plugin_node("compressor")
        block = self.sample_rate
        t = [i / self.sample_rate for i in range(block)]
        quiet = [0.02 * math.sin(2 * math.pi * 440 * x) for x in t]
        loud = [0.5 * math.sin(2 * math.pi * 440 * x) for x in t]
        result = process(node["plugin"], node["label"], node["control"], quiet + loud, self.sample_rate)
        quiet_rms, loud_rms = rms(result[:block]), rms(result[block:])
        input_ratio = rms(loud) / rms(quiet)
        output_ratio = loud_rms / quiet_rms
        self.assertLess(output_ratio, input_ratio * 0.8, (input_ratio, output_ratio))

    def test_limiter_holds_overload_near_configured_ceiling(self):
        node = plugin_node("limiter")
        samples = [1.5 * math.sin(2 * math.pi * 997 * i / self.sample_rate) for i in range(self.sample_rate)]
        result = process(node["plugin"], node["label"], node["control"], samples, self.sample_rate)
        # 3 ms lookahead lets the attack settle; allow 0.12 dB numerical/oversampling tolerance.
        settled = result[1000:]
        peak_db = 20 * math.log10(max(abs(x) for x in settled))
        self.assertLessEqual(peak_db, -0.88, peak_db)

    def test_rnnoise_attenuates_steady_white_noise(self):
        node = plugin_node("denoise")
        samples = white_noise(self.sample_rate * 4, 0.12, 7241)
        result = process(node["plugin"], node["label"], node["control"], samples, self.sample_rate)
        self.assertTrue(all(math.isfinite(x) for x in result))
        # Exclude initial adaptation interval; a substantial attenuation is expected on noise-only input.
        before = rms(samples[self.sample_rate:])
        after = rms(result[self.sample_rate:])
        self.assertLess(after, before * 0.8, (before, after))


if __name__ == "__main__":
    unittest.main()
