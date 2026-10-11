"""The three user controls and meeting-oriented starting profiles."""

from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class Settings:
    noise: int = 70
    clarity: int = 35
    gain_db: float = 0.0

    def __post_init__(self):
        for name in ("noise", "clarity"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError(f"{name} deve estar entre 0 e 100")
        if isinstance(self.gain_db, bool) or not isinstance(self.gain_db, (int, float)):
            raise ValueError("Volume inválido")
        if not math.isfinite(self.gain_db) or not -12 <= self.gain_db <= 6:
            raise ValueError("Volume deve estar entre -12 e +6 dB")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, values):
        if not isinstance(values, dict):
            raise ValueError("Configuração inválida")
        return cls(**{name: values[name] for name in ("noise", "clarity", "gain_db") if name in values})


PRESETS = {
    "Reuniões": Settings(70, 35, 0.0),
    "Voz natural": Settings(40, 15, 0.0),
    "Ambiente ruidoso": Settings(95, 40, 0.0),
}
