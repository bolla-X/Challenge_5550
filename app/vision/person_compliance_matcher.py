from __future__ import annotations

from typing import Any

from app.vision.schemas import BoundingBox, Detection

PPE_KEYS = ("helmet", "vest", "gloves", "glasses")


class PersonComplianceMatcher:
    """Agrupa detecções de EPI por pessoa sem depender de tracking externo.

    O objetivo aqui é manter a lógica multi-pessoa funcional enquanto o modelo PPE
    definitivo não chega. IDs são estáveis apenas por ordenação espacial do frame.
    """

    def build(
        self,
        detections: list[Detection],
        *,
        supported_ppe: dict[str, bool],
        enabled_ppe: dict[str, bool],
        risk_polygon: list[tuple[float, float]] | None = None,
        frame_shape: tuple[int, int, int] | None = None,
    ) -> list[dict[str, Any]]:
        people = sorted(
            [item for item in detections if item.label == "person" or item.category == "person"],
            key=lambda item: (item.box.x1, item.box.y1),
        )
        ppes = [item for item in detections if item.label in PPE_KEYS]
        result: list[dict[str, Any]] = []

        for index, person in enumerate(people, start=1):
            person_id = f"person_{index}"
            matched = self.match_ppe(person, ppes)
            compliance: dict[str, dict[str, Any]] = {}
            for key in PPE_KEYS:
                if not enabled_ppe.get(key, False):
                    status = "disabled"
                    message = "Feature desativada"
                elif not supported_ppe.get(key, False):
                    status = "unsupported"
                    message = "Classe não suportada pelo modelo atual"
                elif matched[key]:
                    status = "ok"
                    message = "Detectado"
                else:
                    status = "missing"
                    message = "Ausente"

                compliance[key] = {
                    "key": key,
                    "status": status,
                    "message": message,
                    "detections": [item.to_dict() for item in matched[key]],
                    "confidence": max([item.confidence for item in matched[key]], default=0.0),
                }

            risk_status = self._risk_status(person.box, risk_polygon, frame_shape)
            result.append(
                {
                    "id": person_id,
                    "index": index,
                    "label": f"Pessoa {index}",
                    "confidence": round(float(person.confidence), 4),
                    "box": person.box.to_dict(),
                    "ppe": compliance,
                    "risk_area": risk_status,
                }
            )
        return result

    def match_ppe(self, person: Detection, ppes: list[Detection]) -> dict[str, list[Detection]]:
        matched: dict[str, list[Detection]] = {key: [] for key in PPE_KEYS}
        for ppe in ppes:
            if ppe.label not in matched:
                continue
            if self._ppe_belongs_to_person(person.box, ppe):
                matched[ppe.label].append(ppe)
        return matched

    def _ppe_belongs_to_person(self, person_box: BoundingBox, ppe: Detection) -> bool:
        cx, cy = ppe.box.center
        if not self._point_inside_box(cx, cy, person_box):
            return False

        rel_y = (cy - person_box.y1) / max(1, person_box.height)
        rel_x = (cx - person_box.x1) / max(1, person_box.width)

        if ppe.label == "helmet":
            return rel_y <= 0.38
        if ppe.label == "glasses":
            # Faixa mais restrita que a do capacete: oculos ficam na altura
            # dos olhos, o capacete cobre o topo da cabeca inteiro.
            return rel_y <= 0.30
        if ppe.label == "vest":
            return 0.18 <= rel_y <= 0.78 and 0.12 <= rel_x <= 0.88
        if ppe.label == "gloves":
            return 0.25 <= rel_y <= 0.92
        return True

    @staticmethod
    def _point_inside_box(x: int, y: int, box: BoundingBox) -> bool:
        return box.x1 <= x <= box.x2 and box.y1 <= y <= box.y2

    def _risk_status(
        self,
        box: BoundingBox,
        polygon: list[tuple[float, float]] | None,
        frame_shape: tuple[int, int, int] | None,
    ) -> dict[str, Any]:
        if not polygon or not frame_shape:
            return {"status": "unknown", "message": "Área não avaliada"}
        height, width = frame_shape[:2]
        cx, cy = box.center
        point = (cx / max(1, width), cy / max(1, height))
        inside = self._point_in_polygon(point, polygon)
        return {
            "status": "inside" if inside else "outside",
            "message": "Dentro da área de risco" if inside else "Fora da área de risco",
            "point": {"x": round(point[0], 4), "y": round(point[1], 4)},
        }

    @staticmethod
    def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
        x, y = point
        inside = False
        j = len(polygon) - 1
        for i in range(len(polygon)):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            intersects = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / max(yj - yi, 1e-12) + xi)
            if intersects:
                inside = not inside
            j = i
        return inside
