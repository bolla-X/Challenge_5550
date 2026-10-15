"""Pessoa + esqueleto numa passada só, com YOLO-pose (17 keypoints COCO).

O caminho antigo custava DUAS etapas por pessoa: um YOLO de pessoa (yolov8n)
para achar as caixas e depois o MediaPipe rodando de novo em cada recorte,
uma pessoa por vez (até POSE_MAX_PEOPLE). Medido no bench da baseline: ~180 ms
de pessoa + ~140–240 ms de pose por inferência, crescendo com o número de
pessoas. Um modelo de pose multi-pessoa devolve as caixas E os keypoints de
todo mundo numa chamada de custo fixo — então ele SUBSTITUI o detector de
pessoa, e a pose de cada track vem de graça, já associada à caixa que o
tracker vai numerar (associação por identidade, IoU = 1).

Os nomes dos keypoints COCO coincidem com os do MediaPipe para os pontos que
as regras usam (`nose`, `left_shoulder`, `right_hip`...), então queda e
postura (`app/services/risk_rules.py`) funcionam sem mudança.

Quando o detector de pessoa NÃO é este (ex.: `POSE_BACKEND=yolo` com
`MULTI_PERSON_DETECTION=false`, pessoas vindas do Vyra), `associar_esqueletos`
faz a associação por IoU entre caixa de pessoa e caixa do esqueleto.
"""

from __future__ import annotations

from typing import Any

from app.vision.schemas import BoundingBox, Detection, PoseLandmark, PoseResult
from app.vision.yolo_ppe_detector import YoloPPEDetector

NOMES_COCO = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
)


class YoloPoseDetector(YoloPPEDetector):
    """Detector de PESSOA que também devolve o esqueleto de cada uma."""

    def __init__(self, model_path: str, **kwargs: Any) -> None:
        kwargs.setdefault("classes", [0])
        super().__init__(model_path, **kwargs)
        self.e_pose = True
        self.task = "pose"

    def _converter(self, result, names) -> list[Detection]:
        pessoas = super()._converter(result, names)
        keypoints = getattr(result, "keypoints", None)
        if keypoints is None or not pessoas:
            return pessoas
        xy = keypoints.xy.detach().cpu().numpy()
        conf = keypoints.conf.detach().cpu().numpy() if keypoints.conf is not None else None
        com_esqueleto = []
        for indice, pessoa in enumerate(pessoas):
            if indice >= len(xy):
                com_esqueleto.append(pessoa)
                continue
            pontos = tuple(
                (float(x), float(y), float(conf[indice][k]) if conf is not None else 1.0)
                for k, (x, y) in enumerate(xy[indice])
            )
            com_esqueleto.append(pessoa.with_keypoints(pontos))
        return com_esqueleto

    def diagnostics(self) -> dict[str, Any]:
        diag = dict(super().diagnostics())
        diag["pose_backend"] = "yolo"
        return diag


def pose_da_deteccao(det: Detection, frame_shape, *, person_id: str | None = None) -> PoseResult | None:
    """Converte os keypoints (pixels) de uma detecção em PoseResult normalizado."""
    if not det.keypoints:
        return None
    altura, largura = frame_shape[:2]
    landmarks = [
        PoseLandmark(name=nome, x=x / max(1, largura), y=y / max(1, altura), z=0.0, visibility=c)
        for nome, (x, y, c) in zip(NOMES_COCO, det.keypoints, strict=False)
        # (0, 0) é o "não visto" do ultralytics: sem isto, ponto ausente viraria
        # um ponto real no canto da imagem e entortaria o torso.
        if not (x == 0.0 and y == 0.0)
    ]
    if not landmarks:
        return None
    return PoseResult(landmarks=landmarks, person_id=person_id, track_id=det.track_id)


def caixa_do_esqueleto(det: Detection) -> BoundingBox | None:
    pontos = [(x, y) for x, y, c in det.keypoints or () if c > 0.3 and not (x == 0.0 and y == 0.0)]
    if len(pontos) < 3:
        return None
    xs, ys = [p[0] for p in pontos], [p[1] for p in pontos]
    return BoundingBox(int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))


def associar_esqueletos(pessoas: list[Detection], esqueletos: list[Detection], *, iou_min: float = 0.3) -> list[Detection]:
    """Dá a cada pessoa (com track) o esqueleto de maior IoU, guloso, um para um."""
    pares = sorted(
        ((p.box.iou(e.box), i, j) for i, p in enumerate(pessoas) for j, e in enumerate(esqueletos) if e.keypoints),
        reverse=True,
    )
    usadas, usados = set(), set()
    saida = list(pessoas)
    for iou, i, j in pares:
        if iou < iou_min:
            break
        if i in usadas or j in usados:
            continue
        usadas.add(i)
        usados.add(j)
        saida[i] = pessoas[i].with_keypoints(esqueletos[j].keypoints)
    return saida
