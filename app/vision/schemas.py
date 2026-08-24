from __future__ import annotations

from dataclasses import asdict, dataclass, replace
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
    landmarks: list[PoseLandmark]

    @property
    def found(self) -> bool:
        return bool(self.landmarks)

    def by_name(self, name: str) -> PoseLandmark | None:
        for landmark in self.landmarks:
            if landmark.name == name:
                return landmark
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"found": self.found, "landmarks": [item.to_dict() for item in self.landmarks]}


@dataclass(frozen=True)
class FrameAnalysis:
    detections: list[Detection]
    pose: PoseResult | None
    risk_events: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "detections": [item.to_dict() for item in self.detections],
            "pose": self.pose.to_dict() if self.pose else {"found": False, "landmarks": []},
            "risk_events": self.risk_events,
        }
