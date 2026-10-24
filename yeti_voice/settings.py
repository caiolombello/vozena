"""Voice controls, meeting-oriented starting profiles and app preferences."""

from dataclasses import asdict, dataclass, replace
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

CUSTOM_LABEL = "Personalizado"
PROFILE_NAME_LIMIT = 40


def validate_profile_name(name):
    if not isinstance(name, str):
        raise ValueError("Nome de perfil inválido")
    name = " ".join(name.split())
    if not name:
        raise ValueError("Dê um nome ao perfil")
    if len(name) > PROFILE_NAME_LIMIT:
        raise ValueError(f"O nome do perfil pode ter até {PROFILE_NAME_LIMIT} caracteres")
    if name in PRESETS or name == CUSTOM_LABEL:
        raise ValueError("Esse nome já é usado por um perfil do Vozena")
    return name


@dataclass(frozen=True)
class Preferences:
    start_at_login: bool = False
    activate_on_launch: bool = False
    # Input configured before "Yeti Processado" became the system default.
    previous_default_source: str = ""
    profiles: tuple = ()  # ((name, Settings), ...) in the user's order

    def __post_init__(self):
        for name in ("start_at_login", "activate_on_launch"):
            if type(getattr(self, name)) is not bool:
                raise ValueError("Preferência inválida")
        if not isinstance(self.previous_default_source, str):
            raise ValueError("Microfone anterior inválido")
        names = []
        for entry in self.profiles:
            if (not isinstance(entry, tuple) or len(entry) != 2
                    or not isinstance(entry[1], Settings)):
                raise ValueError("Perfil inválido")
            if validate_profile_name(entry[0]) != entry[0] or entry[0] in names:
                raise ValueError("Perfil com nome inválido ou repetido")
            names.append(entry[0])

    @property
    def profile_map(self):
        return dict(self.profiles)

    def with_profile(self, name, settings):
        name = validate_profile_name(name)
        profiles = [(key, value) for key, value in self.profiles if key != name]
        profiles.append((name, settings))
        return replace(self, profiles=tuple(profiles))

    def without_profile(self, name):
        return replace(self, profiles=tuple((key, value) for key, value in self.profiles if key != name))

    def to_dict(self):
        return {
            "start_at_login": self.start_at_login,
            "activate_on_launch": self.activate_on_launch,
            "previous_default_source": self.previous_default_source,
            "profiles": [{"name": name, **settings.to_dict()} for name, settings in self.profiles],
        }

    @classmethod
    def from_dict(cls, values):
        if not isinstance(values, dict):
            raise ValueError("Preferências inválidas")
        profiles = values.get("profiles", [])
        if not isinstance(profiles, list) or not all(isinstance(item, dict) for item in profiles):
            raise ValueError("Perfis inválidos")
        return cls(
            start_at_login=values.get("start_at_login", False),
            activate_on_launch=values.get("activate_on_launch", False),
            previous_default_source=values.get("previous_default_source", ""),
            profiles=tuple((item.get("name"), Settings.from_dict(item)) for item in profiles),
        )
