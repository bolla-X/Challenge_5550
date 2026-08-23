from __future__ import annotations

from dataclasses import dataclass, asdict
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

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    box: BoundingBox
    class_id: int | None = None
    category: str = "object"

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": round(float(self.confidence), 4),
            "box": self.box.to_dict(),
            "class_id": self.class_id,
            "category": self.category,
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
