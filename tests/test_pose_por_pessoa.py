"""Pose por pessoa: atribuição de queda/postura e geometria em pixels.

Antes havia UMA pose global por frame. Com duas pessoas em cena, "pessoa caída"
não dizia qual — o alerta saía sempre com `subject: "global_pose"`. E a
geometria comparava dx com dy em coordenadas normalizadas, que têm escalas
diferentes: num frame 960x540, 0.1 em x são 96 px e 0.1 em y são 54 px.
"""
from __future__ import annotations

import pytest
from app.services.feature_manager import FeatureManager
from app.services.risk_rules import FALLEN_TORSO_RATIO, RuleEngine
from app.vision.schemas import PoseLandmark, PoseResult

FRAME = (540, 960, 3)
TODAS_FEATURES = "ppe,helmet,vest,gloves,glasses,mask,safety_shoe,pose,falls,posture,risk_area"


def _engine() -> RuleEngine:
    return RuleEngine(
        FeatureManager.from_config({"DEFAULT_FEATURES": TODAS_FEATURES}),
        cooldown_seconds=0,
        risk_polygon=[(0.7, 0.1), (1, 0.1), (1, 1), (0.7, 1)],
        supported_ppe_getter=set,
    )


def _pose(*, ombro_px, quadril_px, nariz_px=None, person_id=None, track_id=None) -> PoseResult:
    """Monta uma pose a partir de coordenadas em PIXELS do frame."""
    altura, largura = FRAME[:2]

    def lm(nome, ponto):
        return PoseLandmark(name=nome, x=ponto[0] / largura, y=ponto[1] / altura, z=0.0, visibility=0.9)

    ox, oy = ombro_px
    qx, qy = quadril_px
    nariz_px = nariz_px or (ox, oy - 40)
    return PoseResult(
        landmarks=[
            lm("left_shoulder", (ox - 20, oy)),
            lm("right_shoulder", (ox + 20, oy)),
            lm("left_hip", (qx - 15, qy)),
            lm("right_hip", (qx + 15, qy)),
            lm("nose", nariz_px),
        ],
        person_id=person_id,
        track_id=track_id,
    )


def _em_pe(**kw) -> PoseResult:
    # Torso vertical: ombro em cima, quadril 150 px abaixo, quase sem desvio.
    return _pose(ombro_px=(400, 200), quadril_px=(405, 350), **kw)


def _caida(**kw) -> PoseResult:
    # Torso horizontal: ombro e quadril na mesma altura, 200 px de distância.
    return _pose(ombro_px=(300, 400), quadril_px=(500, 405), nariz_px=(260, 400), **kw)


# ------------------------------------------------- geometria em pixels ------
def test_pessoa_em_pe_nao_e_marcada_como_caida():
    """O caso que a normalização quebrava: num recorte de pessoa em pé (80x300),
    o limiar declarado de 1.6 virava 0.43 e qualquer inclinação leve alertava."""
    alertas = _engine().evaluate([], _em_pe(), FRAME)
    assert not [a for a in alertas if a.rule == "fallen_person"]


def test_pessoa_deitada_e_marcada_como_caida():
    alertas = _engine().evaluate([], _caida(), FRAME)
    assert [a for a in alertas if a.rule == "fallen_person"]


def test_limiar_de_queda_vale_em_pixels_nao_em_fracao_do_frame():
    """Com o limiar em 1.6, dx=100px precisa de dy < 62.5px para alertar.

    Na versão normalizada isso dependia da proporção do frame: 1.6 virava 2.84
    num 960x540. O teste fixa o significado em pixels.
    """
    engine = _engine()
    dx = 100
    dy_limite = dx / FALLEN_TORSO_RATIO  # 62.5 px

    logo_abaixo = _pose(ombro_px=(400, 300), quadril_px=(400 + dx, 300 + int(dy_limite) - 5))
    logo_acima = _pose(ombro_px=(400, 300), quadril_px=(400 + dx, 300 + int(dy_limite) + 5))

    assert [a for a in engine.evaluate([], logo_abaixo, FRAME) if a.rule == "fallen_person"]
    assert not [a for a in engine.evaluate([], logo_acima, FRAME) if a.rule == "fallen_person"]


# --------------------------------------------------------- atribuição -------
def test_queda_sai_atribuida_a_pessoa_certa():
    """Duas pessoas, só uma caída: o alerta tem que apontar QUAL."""
    engine = _engine()
    poses = [
        _em_pe(person_id="person_1", track_id=1),
        _caida(person_id="person_2", track_id=2),
    ]
    alertas = [a for a in engine.analyze([], None, FRAME, poses=poses).alerts if a.rule == "fallen_person"]

    assert len(alertas) == 1
    assert alertas[0].metadata["person_id"] == "person_2"
    assert "Pessoa 2" in alertas[0].message


def test_chave_do_alerta_separa_as_pessoas():
    """Sem person_id na chave, duas quedas simultâneas viravam um alerta só."""
    engine = _engine()
    poses = [_caida(person_id="person_1", track_id=1), _caida(person_id="person_2", track_id=2)]
    alertas = [a for a in engine.analyze([], None, FRAME, poses=poses).alerts if a.rule == "fallen_person"]

    assert len(alertas) == 2
    assert len({a.key for a in alertas}) == 2


def test_sem_caixa_de_pessoa_cai_no_comportamento_global():
    """Rede de segurança: MediaPipe achou um corpo que o YOLO não detectou."""
    alertas = [a for a in _engine().evaluate([], _caida(), FRAME) if a.rule == "fallen_person"]

    assert len(alertas) == 1
    assert alertas[0].metadata["subject"] == "global_pose"
    assert "Pessoa" not in alertas[0].message.replace("Pessoa caída", "")


def test_feature_desligada_silencia_a_pose_inteira():
    engine = RuleEngine(
        FeatureManager.from_config({"DEFAULT_FEATURES": "ppe,helmet"}),  # sem pose/falls
        cooldown_seconds=0,
        risk_polygon=[(0.7, 0.1), (1, 0.1), (1, 1), (0.7, 1)],
        supported_ppe_getter=set,
    )
    poses = [_caida(person_id="person_1", track_id=1)]
    assert engine.analyze([], None, FRAME, poses=poses).alerts == []


# ------------------------------------------------------------ postura -------
def test_postura_usa_a_altura_do_torso_da_propria_pessoa():
    """O limiar tem que independer de a pessoa estar perto ou longe da câmera.

    Duas pessoas com a MESMA proporção cabeça-à-frente/torso, em escalas
    diferentes, precisam receber o mesmo veredito.
    """
    engine = _engine()

    def com_escala(escala: float, avanco_relativo: float) -> PoseResult:
        altura_torso = 150 * escala
        avanco = altura_torso * avanco_relativo
        return _pose(
            ombro_px=(400, 200),
            quadril_px=(400, 200 + int(altura_torso)),
            nariz_px=(400 + int(avanco), 160),
        )

    for escala in (0.4, 1.0, 2.0):
        perto_do_limite_abaixo = engine.evaluate([], com_escala(escala, 0.20), FRAME)
        acima_do_limite = engine.evaluate([], com_escala(escala, 0.90), FRAME)
        assert not [a for a in perto_do_limite_abaixo if a.rule == "suspicious_posture"], f"escala {escala}"
        assert [a for a in acima_do_limite if a.rule == "suspicious_posture"], f"escala {escala}"


def test_landmark_pouco_visivel_nao_gera_alerta():
    """Ombro/quadril mal detectados não podem virar 'pessoa caída'."""
    pose = PoseResult(
        landmarks=[
            PoseLandmark(name=nome, x=0.5, y=0.5, z=0.0, visibility=0.1)
            for nome in ("left_shoulder", "right_shoulder", "left_hip", "right_hip", "nose")
        ]
    )
    assert _engine().evaluate([], pose, FRAME) == []


# ------------------------------------------------ contrato do resultado -----
def test_analyze_devolve_as_poses_avaliadas():
    """O ComplianceService lê daqui para dar a cada pessoa a SUA pose."""
    poses = [_em_pe(person_id="person_1", track_id=1), _caida(person_id="person_2", track_id=2)]
    resultado = _engine().analyze([], None, FRAME, poses=poses)

    assert [p.person_id for p in resultado.poses] == ["person_1", "person_2"]


def test_pose_result_converte_landmark_para_pixels():
    pose = _pose(ombro_px=(480, 270), quadril_px=(480, 400))
    x, y = pose.point_px("left_shoulder", FRAME)

    assert x == pytest.approx(460, abs=1)
    assert y == pytest.approx(270, abs=1)
    assert pose.point_px("landmark_inexistente", FRAME) is None
