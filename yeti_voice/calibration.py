"""Conservative analysis for the guided ten-second voice calibration."""

from array import array
from dataclasses import dataclass
import math
import statistics

from .settings import Settings


SAMPLE_RATE = 48_000
CAPTURE_SECONDS = 10
SILENCE_SECONDS = 3
FRAME_SAMPLES = 960  # 20 ms


@dataclass(frozen=True)
class CalibrationMetrics:
    noise_dbfs: float
    speech_dbfs: float
    processed_speech_dbfs: float
    snr_db: float
    peak_dbfs: float
    clipping_percent: float


@dataclass(frozen=True)
class CalibrationResult:
    valid: bool
    message: str
    metrics: CalibrationMetrics
    suggestion: Settings | None


def _dbfs(amplitude):
    return 20 * math.log10(max(float(amplitude), 1e-12))


def _frame_rms(samples):
    return [
        math.sqrt(sum(value * value for value in samples[start : start + FRAME_SAMPLES]) / FRAME_SAMPLES)
        for start in range(0, len(samples) - FRAME_SAMPLES + 1, FRAME_SAMPLES)
    ]


def _decode_pcm(payload, expected_bytes, label):
    if not isinstance(payload, (bytes, bytearray)) or len(payload) != expected_bytes:
        raise ValueError(f"O áudio {label} da calibração está incompleto")
    samples = array("f")
    samples.frombytes(payload)
    if not all(math.isfinite(value) for value in samples):
        raise ValueError(f"O áudio {label} contém amostras inválidas")
    return samples


def analyze_voice_sample(sample):
    """Analyze 3 s of room tone followed by 7 s of normal speech.

    ``sample.settings`` is deliberately the source of the suggestion so a
    later slider change cannot rewrite the settings snapshot used to record.
    """
    expected_bytes = CAPTURE_SECONDS * SAMPLE_RATE * 4
    samples = _decode_pcm(sample.original, expected_bytes, "original")
    processed = _decode_pcm(sample.processed, expected_bytes, "tratado")
    if not isinstance(sample.settings, Settings):
        raise ValueError("A gravação não contém um snapshot válido dos ajustes")

    split = SILENCE_SECONDS * SAMPLE_RATE
    silence_frames = _frame_rms(samples[:split])
    speech_frames = _frame_rms(samples[split:])
    noise_rms = statistics.median(silence_frames)
    noise_db = _dbfs(noise_rms)

    activity_threshold = max(noise_rms * 2.5, 10 ** (-50 / 20))
    active_indices = [
        index for index, value in enumerate(speech_frames)
        if value >= activity_threshold
    ]
    active_frames = [speech_frames[index] for index in active_indices]
    active_fraction = len(active_frames) / len(speech_frames)
    speech_rms = statistics.median(active_frames) if active_frames else 1e-12
    speech_db = _dbfs(speech_rms)
    processed_frames = _frame_rms(processed[split:])
    processed_active = [processed_frames[index] for index in active_indices]
    processed_rms = statistics.median(processed_active) if processed_active else 1e-12
    processed_db = _dbfs(processed_rms)
    snr_db = speech_db - noise_db
    peak = max(abs(value) for value in samples)
    peak_db = _dbfs(peak)
    clipped = sum(abs(value) >= 0.999 for value in samples)
    clipping_percent = 100 * clipped / len(samples)
    metrics = CalibrationMetrics(
        noise_db, speech_db, processed_db, snr_db, peak_db, clipping_percent
    )

    if clipped and (clipping_percent >= 0.01 or peak >= 1.0):
        return CalibrationResult(
            False,
            "O sinal saturou. Reduza o ganho físico no Blue Yeti e grave novamente.",
            metrics,
            None,
        )
    if active_fraction < 0.20 or snr_db < 8 or speech_db < -45:
        return CalibrationResult(
            False,
            "Não houve fala suficiente acima do ruído. Fale normalmente e aproxime o microfone.",
            metrics,
            None,
        )
    if processed_db < -70:
        return CalibrationResult(
            False,
            "A fala não apareceu no áudio tratado. Grave novamente antes de aplicar ajustes.",
            metrics,
            None,
        )

    noise = round(45 + max(0.0, noise_db + 55) * 2 + max(0.0, 25 - snr_db) * 1.5)
    noise = max(30, min(95, noise))
    gain = sample.settings.gain_db + (-20.0 - processed_db)
    gain = max(-12.0, min(6.0, gain))
    gain = round(gain * 2) / 2
    suggestion = Settings(noise=noise, clarity=sample.settings.clarity, gain_db=gain)
    message = (
        "Sugestão pronta. A clareza foi preservada; aplique apenas se quiser usar "
        "a redução de ruído e o volume calculados."
    )
    return CalibrationResult(True, message, metrics, suggestion)
