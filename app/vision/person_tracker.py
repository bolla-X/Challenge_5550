from __future__ import annotations

from dataclasses import dataclass, field

from app.vision.schemas import BoundingBox, Detection


@dataclass
class _Track:
    track_id: int
    box: BoundingBox
    misses: int = 0
    hits: int = 1
    history: list[BoundingBox] = field(default_factory=list)


class PersonTracker:
    """Ids de pessoa estáveis entre frames, por associação IoU.

    Por que não `model.track(persist=True)` do Ultralytics, que era o plano
    original: o estado do tracker vive DENTRO do objeto do modelo, e os
    modelos YOLO aqui são compartilhados por todas as câmeras (carregados uma
    vez pelo MonitorService justamente para não multiplicar VRAM). Alimentar o
    mesmo tracker com frames de câmeras diferentes intercalados corromperia a
    associação — a alternativa seria uma cópia do modelo por câmera, que é
    exatamente o custo que a arquitetura evita.

    Este tracker vive no CameraWorker, então cada câmera tem o seu, custa
    memória desprezível e resolve o problema real: sem id estável, duas
    pessoas se cruzando trocavam de `person_1`/`person_2` (a ordenação era
    espacial, por x1), e como o id entra na CHAVE do alerta, o alerta de uma
    "resolvia" e o da outra "criava" — histerese furada e histórico poluído.

    Deliberadamente simples: sem filtro de Kalman, sem re-identificação por
    aparência. Cobre o caso que quebra hoje (pessoas andando pelo frame a
    ~12 FPS); oclusão longa ou troca de câmera continuam gerando id novo.
    """

    def __init__(self, *, iou_threshold: float = 0.3, max_age: int = 15) -> None:
        self.iou_threshold = iou_threshold
        # Quantos frames um track sobrevive sem ser visto. A 12 FPS, 15 frames
        # ≈ 1,2 s — cobre oclusão curta (alguém passa na frente) sem manter
        # fantasma de quem já saiu de cena.
        self.max_age = max_age
        self._tracks: dict[int, _Track] = {}
        self._next_id = 1

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1

    @property
    def active_count(self) -> int:
        return sum(1 for track in self._tracks.values() if track.misses == 0)

    def update(self, detections: list[Detection]) -> list[Detection]:
        """Devolve as mesmas detecções com `track_id` preenchido.

        A ordem de saída é estável por track_id (não por posição no frame),
        para que `Pessoa 1` continue sendo a mesma pessoa entre frames.
        """
        if not detections:
            self._age_unmatched(set())
            return []

        # Associação gulosa por IoU: todos os pares (track, detecção) ordenados
        # por IoU decrescente, cada lado consumido no máximo uma vez. Para o
        # número de pessoas em cena (unidades, não centenas) isto é mais barato
        # e mais previsível que o húngaro.
        pairs = [
            (track.box.iou(det.box), track_id, index)
            for track_id, track in self._tracks.items()
            for index, det in enumerate(detections)
        ]
        pairs.sort(key=lambda item: item[0], reverse=True)

        matched_tracks: dict[int, int] = {}
        used_detections: set[int] = set()
        for iou, track_id, index in pairs:
            if iou < self.iou_threshold:
                break
            if track_id in matched_tracks or index in used_detections:
                continue
            matched_tracks[track_id] = index
            used_detections.add(index)

        assigned: dict[int, int] = {}
        for track_id, index in matched_tracks.items():
            track = self._tracks[track_id]
            track.box = detections[index].box
            track.misses = 0
            track.hits += 1
            assigned[index] = track_id

        for index, det in enumerate(detections):
            if index in used_detections:
                continue
            track_id = self._next_id
            self._next_id += 1
            self._tracks[track_id] = _Track(track_id=track_id, box=det.box)
            assigned[index] = track_id

        self._age_unmatched(set(matched_tracks.keys()))

        tracked = [det.with_track_id(assigned[index]) for index, det in enumerate(detections)]
        tracked.sort(key=lambda det: det.track_id or 0)
        return tracked

    def _age_unmatched(self, matched_ids: set[int]) -> None:
        for track_id in list(self._tracks.keys()):
            if track_id in matched_ids:
                continue
            track = self._tracks[track_id]
            track.misses += 1
            if track.misses > self.max_age:
                del self._tracks[track_id]
