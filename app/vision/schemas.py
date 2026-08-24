from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class BoundingBox:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    @property
    def center(self) -> tuple[int, int]:
        return (self.x1 + self.width // 2, self.y1 + self.height // 2)

    @property
    def area(self) -> int:
        return self.width * self.height

    def intersection_area(self, other: "BoundingBox") -> int:
        dx = min(self.x2, other.x2) - max(self.x1, other.x1)
        dy = min(self.y2, other.y2) - max(self.y1, other.y1)
        return dx * dy if dx > 0 and dy > 0 else 0

    def iou(self, other: "BoundingBox") -> float:
        """Intersection over Union — base do tracking e do matching EPI-pessoa."""
        inter = self.intersection_area(other)
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0

    def containment_in(self, other: "BoundingBox") -> float:
        """Fração DESTA caixa que cai dentro de `other`. Assimétrico de
        propósito: um capacete pequeno pode estar 100% contido numa pessoa
        grande, e é isso que interessa — não o IoU, que seria baixíssimo."""
        return self.intersection_area(other) / self.area if self.area > 0 else 0.0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    box: BoundingBox
    class_id: int | None = None
    category: str = "object"
    # Id estável ENTRE frames, atribuído pelo PersonTracker (só para pessoas).
    # None = objeto não rastreado (EPIs) ou tracking desligado.
    track_id: int | None = None

    def with_track_id(self, track_id: int | None) -> "Detection":
        return replace(self, track_id=track_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": round(float(self.confidence), 4),
            "box": self.box.to_dict(),
            "class_id": self.class_id,
            "category": self.category,
            "track_id": self.track_id,
        }


@dataclass(frozen=True)
class PoseLandmark:
    name: str
    x: float
    y: float
    z: float
    visibility: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PoseResult:
    """Uma pose. Os landmarks estao SEMPRE em coordenadas normalizadas do frame
    inteiro, mesmo quando a estimativa veio de um recorte por pessoa — quem
    recorta remapeia antes de devolver, para que anotador e frontend nao
    precisem saber de onde a pose veio.

    `person_id`/`track_id` dizem de QUEM e a pose. Ficam None na pose global
    (frame inteiro), que e o caminho usado quando nao ha caixa de pessoa.
    """

    landmarks: list[PoseLandmark]
    person_id: str | None = None
    track_id: int | None = None

    @property
    def found(self) -> bool:
        return bool(self.landmarks)

    def by_name(self, name: str) -> PoseLandmark | None:
        for landmark in self.landmarks:
            if landmark.name == name:
                return landmark
        return None

    def point_px(self, name: str, frame_shape: tuple[int, int, int]) -> tuple[float, float] | None:
        """Landmark em PIXELS do frame.

        Comparar dx com dy em coordenadas normalizadas mistura escalas: num
        frame 960x540, 0.1 em x sao 96 px e 0.1 em y sao 54 px. Toda geometria
        de pose (queda, inclinacao) precisa de pixels para o limiar significar
        o que diz significar.
        """
        landmark = self.by_name(name)
        if landmark is None:
            return None
        height, width = frame_shape[:2]
        return (landmark.x * width, landmark.y * height)

    def to_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "person_id": self.person_id,
            "track_id": self.track_id,
            "landmarks": [item.to_dict() for item in self.landmarks],
        }


@dataclass(frozen=True)
class FrameAnalysis:
    detections: list[Detection]
    pose: PoseResult | None
    risk_events: list[dict[str, Any]]
    # Uma pose por pessoa detectada. `pose` acima continua sendo a primeira
    # delas (ou a global, quando nao ha caixa de pessoa) para nao quebrar
    # clientes que ja liam esse campo.
    poses: list[PoseResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        vazio = {"found": False, "person_id": None, "track_id": None, "landmarks": []}
        return {
            "detections": [item.to_dict() for item in self.detections],
            "pose": self.pose.to_dict() if self.pose else vazio,
            "poses": [item.to_dict() for item in self.poses],
            "risk_events": self.risk_events,
        }
