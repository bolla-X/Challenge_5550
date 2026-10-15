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

    def __init__(self, *, iou_threshold: float = 0.2, max_age: int = 45, max_center_dist: float = 0.6) -> None:
        self.iou_threshold = iou_threshold
        # Fallback quando o IoU falha (pessoa sentou, virou, caixa mudou muito):
        # aceita o par se os centros estão a menos de esta fração do tamanho
        # da caixa do track. Segura o id em vez de gerar "Pessoa N+1".
        self.max_center_dist = max_center_dist
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
            (self._afinidade(track.box, det.box, track.misses), track_id, index)
            for track_id, track in self._tracks.items()
            for index, det in enumerate(detections)
        ]
        pairs.sort(key=lambda item: item[0], reverse=True)

        matched_tracks: dict[int, int] = {}
        used_detections: set[int] = set()
        for afinidade, track_id, index in pairs:
            if afinidade <= 0:
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

    def _afinidade(self, track_box: BoundingBox, det_box: BoundingBox, misses: int) -> float:
        """0 = não combina. IoU manda; distância entre centros é o plano B.

        O plano B vale menos (metade) para não roubar o par de quem tem IoU
        real, e encolhe conforme o track fica tempo sem ser visto.
        """
        iou = track_box.iou(det_box)
        if iou >= self.iou_threshold:
            return 1.0 + iou
        tamanho = max(track_box.width, track_box.height, 1)
        dx = track_box.center[0] - det_box.center[0]
        dy = track_box.center[1] - det_box.center[1]
        dist = (dx * dx + dy * dy) ** 0.5 / tamanho
        limite = self.max_center_dist / (1 + 0.05 * misses)
        return 0.5 * (1 - dist / limite) if dist < limite else 0.0

    def _age_unmatched(self, matched_ids: set[int]) -> None:
        for track_id in list(self._tracks.keys()):
            if track_id in matched_ids:
                continue
            track = self._tracks[track_id]
            track.misses += 1
            if track.misses > self.max_age:
                del self._tracks[track_id]


class ByteTrackPessoas:
    """Mesma interface do `PersonTracker`, com ByteTrack por baixo (um por câmera).

    O que o ByteTrack faz que o tracker IoU não faz: a SEGUNDA associação com
    detecções de baixa confiança (entre 0,1 e o limiar de ativação). Uma pessoa
    meio encoberta, que o modelo vê com 0,2 de confiança, continua no MESMO
    track em vez de sumir e voltar como "Pessoa N+1". Por isso o detector de
    pessoa, com este tracker, entrega a partir de 0,1 (`confianca_minima`) — e
    só tracks ATIVOS saem daqui: caixa fraca nunca cria pessoa nova.

    Kalman e associação em dois estágios vêm de `app/vision/bytetrack/`
    (derivado de supervision 0.30.9, MIT). Decisão e números em
    docs/NEXT2026/CHANGELOG.md (comparação com o tracker IoU nas fixtures).
    """

    confianca_minima = 0.1

    def __init__(self, *, limiar_ativacao: float = 0.35, max_perdido: int = 15) -> None:
        from app.vision.bytetrack.core import ByteTrack

        self._limiar = limiar_ativacao
        self._max_perdido = max_perdido
        self._bt = ByteTrack(
            track_activation_threshold=limiar_ativacao,
            lost_track_buffer=max_perdido,
            # `frame_rate` só escala o buffer (frame_rate/30 * buffer): 30 deixa
            # `max_perdido` em INFERÊNCIAS, que é a unidade que o worker vê.
            frame_rate=30,
        )
        self._ativos = 0

    def reset(self) -> None:
        self._bt.reset()
        self._ativos = 0

    @property
    def active_count(self) -> int:
        return self._ativos

    def update(self, detections: list[Detection]) -> list[Detection]:
        import numpy as np

        tensores = np.array(
            [[d.box.x1, d.box.y1, d.box.x2, d.box.y2, d.confidence] for d in detections], dtype=np.float32
        ).reshape(-1, 5)
        tracks = self._bt.update_with_tensors(tensores)
        self._ativos = len(tracks)
        if not tracks or not detections:
            return []
        # Cada track ativo volta para a detecção de ONDE veio (maior IoU entre a
        # caixa do track — já atualizada com essa detecção — e a da detecção).
        pares = sorted(
            (
                (BoundingBox(*(int(v) for v in t.tlbr)).iou(d.box), ti, di)
                for ti, t in enumerate(tracks)
                for di, d in enumerate(detections)
            ),
            reverse=True,
        )
        usados_t, usados_d, saida = set(), set(), []
        for iou, ti, di in pares:
            if iou < 0.3:
                break
            if ti in usados_t or di in usados_d:
                continue
            usados_t.add(ti)
            usados_d.add(di)
            saida.append(detections[di].with_track_id(int(tracks[ti].external_track_id)))
        saida.sort(key=lambda det: det.track_id or 0)
        return saida
