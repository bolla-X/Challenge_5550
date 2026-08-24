from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.vision.schemas import BoundingBox, Detection

PPE_KEYS = ("helmet", "vest", "gloves", "glasses", "mask", "safety_shoe")



# Rótulo em pt-BR de cada EPI. Fonte única: o ComplianceService e o

# FrameAnnotator liam de listas próprias que podiam divergir.

PPE_LABELS: dict[str, str] = {

    "helmet": "Capacete",

    "vest": "Colete",

    "gloves": "Luvas",

    "glasses": "Óculos",

    "mask": "Máscara",

    "safety_shoe": "Calçado de segurança",

}



@dataclass(frozen=True)

class _Zone:

    """Onde cada EPI é esperado dentro da caixa da pessoa.



    `ideal` é a altura relativa típica do item (0 = topo da cabeça, 1 = pés) e

    `top`/`bottom` a faixa ainda aceitável. A pontuação é GRADUADA em torno de

    `ideal`, não binária dentro da faixa: com duas pessoas sobrepostas, um

    capacete cai dentro da faixa "cabeça" de ambas, e só a distância até o

    ideal diz de quem ele é de verdade. Com pontuação binária dava empate, e o

    desempate virava a ordem da lista — ou seja, sorte.



    `max_per_person` é o que garante exclusividade por tipo (uma pessoa tem um

    capacete, mas pode ter duas luvas).

    """



    top: float

    ideal: float

    bottom: float

    max_per_person: int





_ZONES: dict[str, _Zone] = {

    "helmet": _Zone(0.00, 0.08, 0.30, 1),

    "glasses": _Zone(0.00, 0.10, 0.25, 1),

    "mask": _Zone(0.02, 0.14, 0.30, 1),

    "vest": _Zone(0.18, 0.42, 0.70, 1),

    "gloves": _Zone(0.30, 0.62, 0.95, 2),

    "safety_shoe": _Zone(0.78, 0.95, 1.00, 2),

}



# Quanto da caixa do EPI precisa cair dentro da caixa da pessoa para a

# associação ser sequer considerada.

_MIN_CONTAINMENT = 0.5

# Tolerância (em fração da altura da pessoa) para o EPI ficar FORA da faixa e

# ainda ser considerado — cobre pessoa agachada ou caixa mal ajustada.

_OUT_OF_ZONE_TOLERANCE = 0.15





class PersonComplianceMatcher:

    """Agrupa detecções de EPI por pessoa.



    Duas trocas em relação à versão anterior:



    1. Id da pessoa vem do `track_id` (PersonTracker) quando existe, em vez da

       ordenação espacial por x1 — que trocava os ids sempre que duas pessoas

       se cruzavam no frame.

    2. Associação EPI-pessoa é geométrica e EXCLUSIVA: pontua contenção real da

       caixa + aderência à faixa vertical esperada, ordena e atribui cada EPI a

       no máximo uma pessoa. Antes bastava o centro do EPI cair numa faixa da

       caixa da pessoa, sem exclusividade — com duas pessoas próximas, o mesmo

       capacete satisfazia as duas.

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

        people = [item for item in detections if item.label == "person" or item.category == "person"]

        # Com track_id, a ordem já é estável entre frames. Sem ele (tracking

        # desligado), cai na ordenação espacial de antes — comportamento

        # conhecido, não uma regressão silenciosa.

        if people and all(item.track_id is not None for item in people):

            people = sorted(people, key=lambda item: item.track_id or 0)

        else:

            people = sorted(people, key=lambda item: (item.box.x1, item.box.y1))



        ppes = [item for item in detections if item.label in PPE_KEYS]

        assignments = self._assign(people, ppes)



        result: list[dict[str, Any]] = []

        for index, person in enumerate(people, start=1):

            person_id = f"person_{person.track_id}" if person.track_id is not None else f"person_{index}"

            matched = assignments[id(person)]

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

                    "label": PPE_LABELS[key],

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

                    "track_id": person.track_id,

                    "label": f"Pessoa {person.track_id if person.track_id is not None else index}",

                    "confidence": round(float(person.confidence), 4),

                    "box": person.box.to_dict(),

                    "ppe": compliance,

                    "risk_area": risk_status,

                }

            )

        return result



    def _assign(self, people: list[Detection], ppes: list[Detection]) -> dict[int, dict[str, list[Detection]]]:

        """Atribuição gulosa: melhor par (EPI, pessoa) primeiro, cada EPI usado

        uma única vez e respeitando o limite por pessoa de cada tipo."""

        matched: dict[int, dict[str, list[Detection]]] = {id(person): {key: [] for key in PPE_KEYS} for person in people}

        if not people or not ppes:

            return matched



        scored: list[tuple[float, int, int]] = []

        for ppe_index, ppe in enumerate(ppes):

            for person_index, person in enumerate(people):

                score = self._score(person.box, ppe)

                if score > 0:

                    scored.append((score, ppe_index, person_index))

        scored.sort(key=lambda item: item[0], reverse=True)



        used_ppes: set[int] = set()

        for _score, ppe_index, person_index in scored:

            if ppe_index in used_ppes:

                continue

            ppe = ppes[ppe_index]

            person = people[person_index]

            bucket = matched[id(person)][ppe.label]

            if len(bucket) >= _ZONES[ppe.label].max_per_person:

                continue

            bucket.append(ppe)

            used_ppes.add(ppe_index)

        return matched



    def _score(self, person_box: BoundingBox, ppe: Detection) -> float:

        """0 = não pode ser desta pessoa. Maior = associação mais plausível."""

        zone = _ZONES.get(ppe.label)

        if zone is None:

            return 0.0

        containment = ppe.box.containment_in(person_box)

        if containment < _MIN_CONTAINMENT:

            return 0.0



        cx, cy = ppe.box.center

        rel_y = (cy - person_box.y1) / max(1, person_box.height)



        if rel_y < zone.top or rel_y > zone.bottom:

            # Fora da faixa: ainda possível, mas perde de longe para quem tem o

            # item dentro dela.

            distance = min(abs(rel_y - zone.top), abs(rel_y - zone.bottom))

            if distance > _OUT_OF_ZONE_TOLERANCE:

                return 0.0

            zone_fit = 0.2 * (1 - distance / _OUT_OF_ZONE_TOLERANCE)

        else:

            # Dentro da faixa: quanto mais perto da altura típica do item,

            # melhor. É este gradiente que decide de quem é o capacete quando

            # duas pessoas se sobrepõem.

            spread = max(zone.ideal - zone.top, zone.bottom - zone.ideal, 1e-6)

            zone_fit = max(0.05, 1.0 - abs(rel_y - zone.ideal) / spread)



        # Alinhamento horizontal: EPI perto do eixo vertical da pessoa é mais

        # plausível do que EPI colado na borda da caixa. Desempata pessoas lado

        # a lado, onde a altura relativa sozinha não distingue nada.

        person_cx, _person_cy = person_box.center

        rel_x_offset = abs(cx - person_cx) / max(1, person_box.width / 2)

        horizontal_fit = max(0.3, 1.0 - 0.5 * min(1.0, rel_x_offset))



        return containment * zone_fit * horizontal_fit * max(0.05, ppe.confidence)



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

