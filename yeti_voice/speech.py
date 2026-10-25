"""Conservative detection of sustained speech in raw microphone PCM."""

from array import array
from collections import deque
import math

FRAME_SAMPLES = 960  # 20 ms at 48 kHz


class SpeechDetector:
    """Report speech that clearly rises above the room's own noise floor.

    Each 20 ms frame counts as speech when it is at least 12 dB above the
    quietest tenth of the last 3 s and above -45 dBFS. Steady sounds such as
    a fan raise the floor with them, so only varying speech-like activity
    triggers. Detection needs 0.6 s of speech within 1.5 s.
    """

    def __init__(self, *, window_frames=75, needed_frames=30, history_frames=150,
                 minimum_dbfs=-45.0, margin_db=12.0):
        self._window = deque(maxlen=window_frames)
        self._history = deque(maxlen=history_frames)
        self._needed = needed_frames
        self._minimum = 10 ** (minimum_dbfs / 20)
        self._margin = 10 ** (margin_db / 20)
        self._pending = bytearray()

    def feed(self, payload):
        """Consume mono f32 PCM; True once sustained speech is detected."""
        self._pending.extend(payload)
        frame_bytes = FRAME_SAMPLES * 4
        detected = False
        while len(self._pending) >= frame_bytes:
            samples = array("f")
            samples.frombytes(self._pending[:frame_bytes])
            del self._pending[:frame_bytes]
            energy = sum(value * value for value in samples if math.isfinite(value))
            rms = math.sqrt(energy / FRAME_SAMPLES)
            self._history.append(rms)
            floor = sorted(self._history)[len(self._history) // 10]
            self._window.append(rms >= max(self._minimum, floor * self._margin))
            if sum(self._window) >= self._needed:
                self._window.clear()
                detected = True
        return detected
