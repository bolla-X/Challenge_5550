from __future__ import annotationsfrom dataclasses import asdict, dataclassfrom threading import RLock@dataclass
class FeatureFlag:
    key: str
    label: str
    description: str
    enabled: bool = True
    group: str = "geral"

    def to_dict(self) -> dict:
        return asdict(self)


class FeatureManager:
    AVAILABLE_FEATURES: tuple[FeatureFlag, ...] = (
        FeatureFlag("ppe", "EPIs", "Ativa análise geral de equipamentos de proteção", True, "EPIs"),
        FeatureFlag("helmet", "Capacete", "Detecta ausência/presença de capacete", True, "EPIs"),
        FeatureFlag("vest", "Colete", "Detecta ausência/presença de colete refletivo", True, "EPIs"),
        FeatureFlag("gloves", "Luvas", "Detecta ausência/presença de luvas", True, "EPIs"),
        FeatureFlag("glasses", "Óculos", "Detecta ausência/presença de óculos de proteção", True, "EPIs"),
        FeatureFlag("mask", "Máscara", "Detecta ausência/presença de máscara/respirador", True, "EPIs"),
        FeatureFlag("safety_shoe", "Calçado", "Detecta ausência/presença de calçado de segurança", True, "EPIs"),
        FeatureFlag("pose", "Pose", "Ativa MediaPipe Pose Estimation", True, "Postura"),
        FeatureFlag("falls", "Quedas", "Detecta pessoa caída por landmarks de pose", True, "Postura"),
        FeatureFlag("posture", "Postura inadequada", "Detecta inclinação/curvatura suspeita", True, "Postura"),
        FeatureFlag("risk_area", "Área de risco", "Detecta permanência em região de risco simulada", True, "Risco"),
    )

    def __init__(self, features: dict[str, FeatureFlag]) -> None:
        self._features = features
        self._lock = RLock()

    @classmethod
    def from_config(cls, config: dict) -> "FeatureManager":
        enabled_keys = set(config.get("DEFAULT_FEATURES", "").split(","))
        enabled_keys = {item.strip() for item in enabled_keys if item.strip()}
        features = {
            item.key: FeatureFlag(
                key=item.key,
                label=item.label,
                description=item.description,
                enabled=item.key in enabled_keys,
                group=item.group,
            )
            for item in cls.AVAILABLE_FEATURES
        }
        return cls(features)

    @classmethod
    def from_camera_features(cls, camera_features: dict[str, bool]) -> "FeatureManager":
        """Constrói um FeatureManager a partir de Camera.features_json (Fase A,
        Passo 4 — multi-câmera). Cada câmera tem seu próprio FeatureManager
        independente, mesma classe/interface de sempre (is_enabled/list/
        as_dict/update), só a fonte do estado inicial que muda: em vez do
        .env global (DEFAULT_FEATURES), vem do banco, por câmera."""
        features = {
            item.key: FeatureFlag(
                key=item.key,
                label=item.label,
                description=item.description,
                enabled=bool(camera_features.get(item.key, True)),
                group=item.group,
            )
            for item in cls.AVAILABLE_FEATURES
        }
        return cls(features)

    def is_enabled(self, key: str) -> bool:
        with self._lock:
            feature = self._features.get(key)
            return bool(feature and feature.enabled)

    def update(self, updates: dict[str, bool]) -> list[FeatureFlag]:
        with self._lock:
            for key, enabled in updates.items():
                if key in self._features:
                    self._features[key].enabled = bool(enabled)
            return self.list()

    def list(self) -> list[FeatureFlag]:
        with self._lock:
            return [self._features[key] for key in sorted(self._features.keys())]

    def as_dict(self) -> dict:
        return {feature.key: feature.to_dict() for feature in self.list()}