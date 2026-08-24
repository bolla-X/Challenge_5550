"""Recorte por pessoa: remapeamento das coordenadas de volta ao frame.

O MediaPipe devolve landmarks normalizados em relação ao RECORTE. Se esse
remapeamento estiver errado, o esqueleto aparece deslocado no vídeo e toda a
geometria de queda/postura passa a medir a pessoa errada — silenciosamente,
porque os números continuam entre 0 e 1.
"""
from __future__ import annotations

import numpy as np
import pytest
from app.vision.pose_estimator import CROP_PADDING, MIN_CROP_SIDE, MediaPipePoseEstimator
from app.vision.schemas import BoundingBox

FRAME_W, FRAME_H = 960, 540


class FakeLandmark:
    def __init__(self, x, y, z=0.0, visibility=0.9):
        self.x, self.y, self.z, self.visibility = x, y, z, visibility


class FakeLandmarks:
    def __init__(self, pontos):
        self.landmark = [FakeLandmark(x, y) for x, y in pontos]


class FakeResult:
    def __init__(self, pontos):
        self.pose_landmarks = FakeLandmarks(pontos) if pontos else None


class FakePose:
    """Registra os recortes recebidos e devolve landmarks controlados."""

    def __init__(self, resposta):
        self.resposta = resposta
        self.recortes: list[tuple[int, int]] = []

    def process(self, imagem):
        self.recortes.append((imagem.shape[1], imagem.shape[0]))  # (w, h)
        return FakeResult(self.resposta)


class FakeEnum:
    def __init__(self, name):
        self.name = name


@pytest.fixture()
def estimator(monkeypatch):
    est = MediaPipePoseEstimator()
    # Só os dois primeiros nomes importam para estes testes.
    monkeypatch.setattr(
        type(est), "_mp_pose",
        property(lambda self: type("MP", (), {"PoseLandmark": [FakeEnum("LEFT_SHOULDER"), FakeEnum("RIGHT_SHOULDER")]})),
    )
    return est


def _frame():
    return np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)


def _instalar_pose(monkeypatch, estimator, resposta) -> FakePose:
    fake = FakePose(resposta)
    monkeypatch.setattr(type(estimator), "_pose_crop", property(lambda self: fake))
    return fake


# --------------------------------------------------------- remapeamento ----
def test_landmark_do_recorte_volta_para_o_frame(monkeypatch, estimator):
    """Centro do recorte deve virar o centro da caixa no frame."""
    caixa = BoundingBox(x1=400, y1=100, x2=500, y2=400)
    _instalar_pose(monkeypatch, estimator, [(0.5, 0.5), (0.5, 0.5)])

    poses = estimator.estimate_for_people(_frame(), [("person_1", 1, caixa)])

    assert len(poses) == 1
    x_px, y_px = poses[0].point_px("left_shoulder", (FRAME_H, FRAME_W, 3))
    # O recorte tem padding, então o centro dele é o centro da caixa.
    assert x_px == pytest.approx((caixa.x1 + caixa.x2) / 2, abs=2)
    assert y_px == pytest.approx((caixa.y1 + caixa.y2) / 2, abs=2)


def test_pessoas_diferentes_geram_coordenadas_diferentes(monkeypatch, estimator):
    """Mesmo landmark relativo, caixas distintas -> posições distintas no frame."""
    _instalar_pose(monkeypatch, estimator, [(0.5, 0.5), (0.5, 0.5)])
    esquerda = BoundingBox(x1=50, y1=100, x2=150, y2=400)
    direita = BoundingBox(x1=700, y1=100, x2=800, y2=400)

    poses = estimator.estimate_for_people(
        _frame(), [("person_1", 1, esquerda), ("person_2", 2, direita)]
    )

    xs = [p.point_px("left_shoulder", (FRAME_H, FRAME_W, 3))[0] for p in poses]
    assert xs[0] == pytest.approx(100, abs=2)
    assert xs[1] == pytest.approx(750, abs=2)


def test_identidade_da_pessoa_viaja_junto(monkeypatch, estimator):
    _instalar_pose(monkeypatch, estimator, [(0.5, 0.5), (0.5, 0.5)])
    caixa = BoundingBox(x1=400, y1=100, x2=500, y2=400)

    pose = estimator.estimate_for_people(_frame(), [("person_7", 7, caixa)])[0]

    assert pose.person_id == "person_7"
    assert pose.track_id == 7


# ------------------------------------------------------------- recorte -----
def test_recorte_recebe_margem_em_volta_da_caixa(monkeypatch, estimator):
    """MediaPipe erra mais com o corpo colado na borda — daí o padding."""
    caixa = BoundingBox(x1=400, y1=100, x2=500, y2=400)
    fake = _instalar_pose(monkeypatch, estimator, [(0.5, 0.5), (0.5, 0.5)])

    estimator.estimate_for_people(_frame(), [("person_1", 1, caixa)])

    largura, altura = fake.recortes[0]
    assert largura > caixa.width and altura > caixa.height
    assert largura == pytest.approx(caixa.width * (1 + 2 * CROP_PADDING), abs=3)


def test_recorte_nao_estoura_a_borda_do_frame(monkeypatch, estimator):
    """Caixa colada no canto: o padding não pode gerar índice negativo."""
    caixa = BoundingBox(x1=0, y1=0, x2=120, y2=300)
    fake = _instalar_pose(monkeypatch, estimator, [(0.5, 0.5), (0.5, 0.5)])

    poses = estimator.estimate_for_people(_frame(), [("person_1", 1, caixa)])

    largura, altura = fake.recortes[0]
    assert largura <= FRAME_W and altura <= FRAME_H
    x_px, _y = poses[0].point_px("left_shoulder", (FRAME_H, FRAME_W, 3))
    assert 0 <= x_px <= FRAME_W


def test_caixa_pequena_demais_e_ignorada(monkeypatch, estimator):
    """Pessoa distante, poucos pixels: pose não seria confiável."""
    minuscula = BoundingBox(x1=10, y1=10, x2=10 + MIN_CROP_SIDE // 3, y2=10 + MIN_CROP_SIDE // 3)
    fake = _instalar_pose(monkeypatch, estimator, [(0.5, 0.5), (0.5, 0.5)])

    poses = estimator.estimate_for_people(_frame(), [("person_1", 1, minuscula)])

    assert poses == []
    assert fake.recortes == [], "nem deveria chamar o MediaPipe"


def test_pessoa_sem_pose_detectada_nao_entra_no_resultado(monkeypatch, estimator):
    """Sem correspondência 1:1 com a entrada — o chamador não pode assumir."""
    _instalar_pose(monkeypatch, estimator, [])  # MediaPipe não achou nada
    caixa = BoundingBox(x1=400, y1=100, x2=500, y2=400)

    assert estimator.estimate_for_people(_frame(), [("person_1", 1, caixa)]) == []


def test_max_people_limita_o_custo(monkeypatch, estimator):
    """São N inferências por frame; o teto protege o FPS numa cena cheia."""
    fake = _instalar_pose(monkeypatch, estimator, [(0.5, 0.5), (0.5, 0.5)])
    pessoas = [
        (f"person_{i}", i, BoundingBox(x1=50 * i, y1=100, x2=50 * i + 100, y2=400))
        for i in range(1, 9)
    ]

    poses = estimator.estimate_for_people(_frame(), pessoas, max_people=3)

    assert len(poses) == 3
    assert len(fake.recortes) == 3
