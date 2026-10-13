"""Pose YOLO multi-pessoa: esqueleto associado ao track e queda atribuída a um ID.

Os esqueletos aqui são montados à mão em PIXELS, no formato que o
`YoloPoseDetector` produz (COCO-17, (x, y, confiança)), para que o teste
verifique a associação e a regra — não o modelo.
"""

from __future__ import annotations

from app.services.feature_manager import FeatureManager
from app.services.risk_rules import RuleEngine
from app.vision.person_tracker import PersonTracker
from app.vision.schemas import BoundingBox, Detection
from app.vision.yolo_pose_detector import NOMES_COCO, associar_esqueletos, pose_da_deteccao

FRAME = (540, 960, 3)
FEATURES = "ppe,pose,falls,posture,risk_area"


def _esqueleto(caixa: BoundingBox, *, deitado: bool) -> Detection:
    """Pessoa com keypoints: em pé (torso vertical) ou deitada (torso horizontal)."""
    pontos = {nome: (0.0, 0.0, 0.0) for nome in NOMES_COCO}
    cx, cy = caixa.center
    if deitado:
        ombro, quadril = (caixa.x1 + 30, cy), (caixa.x2 - 60, cy + 4)
    else:
        ombro, quadril = (cx, caixa.y1 + 40), (cx + 3, caixa.y1 + 160)
    pontos["left_shoulder"] = (ombro[0] - 10, ombro[1], 0.9)
    pontos["right_shoulder"] = (ombro[0] + 10, ombro[1] + 2, 0.9)
    pontos["left_hip"] = (quadril[0] - 10, quadril[1], 0.9)
    pontos["right_hip"] = (quadril[0] + 10, quadril[1] + 2, 0.9)
    pontos["nose"] = (ombro[0] - (40 if deitado else 0), ombro[1] - (0 if deitado else 30), 0.9)
    return Detection(label="person", confidence=0.9, box=caixa, category="person").with_keypoints(
        tuple(pontos[n] for n in NOMES_COCO)
    )


def _pessoa(caixa: BoundingBox) -> Detection:
    return Detection(label="person", confidence=0.9, box=caixa, category="person")


def test_cada_esqueleto_vai_para_o_track_de_maior_iou():
    tracker = PersonTracker()
    a, b = BoundingBox(100, 100, 220, 400), BoundingBox(600, 120, 720, 420)
    pessoas = tracker.update([_pessoa(a), _pessoa(b)])
    # Esqueletos em ordem trocada e com caixas levemente diferentes.
    esqueletos = [_esqueleto(BoundingBox(605, 118, 722, 418), deitado=False), _esqueleto(BoundingBox(98, 104, 221, 398), deitado=False)]
    associadas = associar_esqueletos(pessoas, esqueletos)
    for pessoa, esperado in zip(associadas, (esqueletos[1], esqueletos[0]), strict=True):
        assert pessoa.keypoints == esperado.keypoints, "esqueleto foi para a pessoa errada"
    assert [p.track_id for p in associadas] == [p.track_id for p in pessoas], "a associação não pode mexer no ID"


def test_esqueleto_sem_pessoa_por_perto_nao_e_atribuido():
    pessoas = PersonTracker().update([_pessoa(BoundingBox(100, 100, 220, 400))])
    longe = _esqueleto(BoundingBox(700, 100, 820, 400), deitado=True)
    assert associar_esqueletos(pessoas, [longe])[0].keypoints is None


def test_queda_sai_atribuida_ao_id_da_pessoa_caida():
    tracker = PersonTracker()
    em_pe, caido = BoundingBox(100, 80, 220, 420), BoundingBox(400, 350, 760, 470)
    pessoas = tracker.update([_pessoa(em_pe), _pessoa(caido)])
    pessoas = associar_esqueletos(pessoas, [_esqueleto(em_pe, deitado=False), _esqueleto(caido, deitado=True)])
    poses = [pose_da_deteccao(p, FRAME, person_id=f"person_{p.track_id}") for p in pessoas]

    engine = RuleEngine(FeatureManager.from_config({"DEFAULT_FEATURES": FEATURES}), cooldown_seconds=0,
                        risk_polygon=[(0.9, 0.0), (1, 0.0), (1, 0.1), (0.9, 0.1)], supported_ppe_getter=set)
    quedas = [a for a in engine.analyze([], None, FRAME, poses=poses).alerts if a.rule == "fallen_person"]

    id_caido = next(p.track_id for p in pessoas if p.box == caido)
    assert len(quedas) == 1, f"esperava uma queda, houve {[q.metadata for q in quedas]}"
    assert quedas[0].metadata["person_id"] == f"person_{id_caido}"
    assert f"Pessoa {id_caido}" in quedas[0].message


def test_ponto_nao_visto_do_ultralytics_nao_vira_ponto_real():
    """(0, 0) é 'não detectado' no ultralytics; virar ponto no canto entortaria o torso."""
    det = _esqueleto(BoundingBox(100, 100, 220, 400), deitado=False)
    pose = pose_da_deteccao(det, FRAME)
    assert pose.by_name("left_ankle") is None
    assert pose.by_name("left_shoulder") is not None
