"""Modo privacidade (F4): o que sai do worker tem rosto desfocado, e só o supervisor desliga."""

from __future__ import annotations

import numpy as np
import pytest
from app import create_app
from app.config import AuthTestConfig
from app.extensions import db
from app.models import ROLE_OPERATOR, ROLE_SUPERVISOR, ROLE_TECHNICAL, Camera, EventLog
from app.services.auth_service import AuthService
from app.vision.privacidade import desfocar, regioes_de_rosto
from app.vision.schemas import BoundingBox, Detection, FrameAnalysis
from app.vision.yolo_pose_detector import NOMES_COCO

SENHA = "senha-forte-de-teste"


def _analise(*dets):
    return FrameAnalysis(detections=list(dets), pose=None, risk_events=[], poses=[])


def _pessoa(caixa, keypoints=None):
    det = Detection(label="person", confidence=0.9, box=caixa, category="person", track_id=1)
    return det.with_keypoints(keypoints) if keypoints else det


def test_sem_pose_desfoca_o_terco_superior_da_pessoa():
    regioes = regioes_de_rosto(_analise(_pessoa(BoundingBox(100, 100, 200, 400))), (540, 960, 3))
    assert len(regioes) == 1
    x1, y1, x2, y2 = regioes[0]
    assert y1 <= 100 and 190 <= y2 <= 260, "terço superior (com margem), não a pessoa inteira"


def test_com_pose_desfoca_em_volta_da_cabeca():
    pontos = {n: (0.0, 0.0, 0.0) for n in NOMES_COCO}
    pontos.update({"nose": (150, 130, 0.9), "left_eye": (145, 125, 0.9), "right_eye": (155, 125, 0.9),
                   "left_ear": (140, 128, 0.8), "right_ear": (160, 128, 0.8)})
    det = _pessoa(BoundingBox(100, 100, 200, 400), tuple(pontos[n] for n in NOMES_COCO))
    x1, y1, x2, y2 = regioes_de_rosto(_analise(det), (540, 960, 3))[0]
    assert x1 <= 140 and x2 >= 160 and y1 <= 125 and y2 >= 130
    assert y2 < 250, "com a cabeça localizada, não precisa desfocar até o peito"


def test_margem_cresce_com_a_idade_da_analise():
    det = _pessoa(BoundingBox(300, 100, 400, 400))
    novo = regioes_de_rosto(_analise(det), (540, 960, 3), idade_s=0.0)[0]
    velho = regioes_de_rosto(_analise(det), (540, 960, 3), idade_s=1.0)[0]
    assert (velho[2] - velho[0]) > (novo[2] - novo[0]), "análise velha: a pessoa já andou, a margem tem que crescer"


def test_desfoque_altera_so_a_regiao_e_nao_mexe_no_original():
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 255, (540, 960, 3), dtype=np.uint8)
    original = frame.copy()
    saida = desfocar(frame, [(100, 100, 220, 200)])
    assert np.array_equal(frame, original), "o quadro original (o da inferência) não pode ser alterado"
    assert not np.array_equal(saida[100:200, 100:220], original[100:200, 100:220])
    assert np.array_equal(saida[300:, 300:], original[300:, 300:])


@pytest.fixture()
def app(tmp_path):
    class Cfg(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'privacidade.db'}"

    aplicacao = create_app(Cfg)
    with aplicacao.app_context():
        db.create_all()
        camera = Camera(name="Portaria", source_type="USB", source="0")
        db.session.add(camera)
        db.session.commit()
        aplicacao.config["ID"] = camera.id
        aplicacao.extensions["monitor_service"].load_cameras_from_db()
        for email, papel in (("sup@f.com", ROLE_SUPERVISOR), ("tec@f.com", ROLE_TECHNICAL), ("op@f.com", ROLE_OPERATOR)):
            AuthService().create_user(email=email, name=email, password=SENHA, role=papel,
                                      camera_id=camera.id if papel == ROLE_OPERATOR else None)
        yield aplicacao
        db.session.remove()
        db.drop_all()


def _cliente(app, email):
    c = app.test_client()
    assert c.post("/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return c


@pytest.mark.parametrize("email", ["tec@f.com", "op@f.com"])
def test_so_supervisor_desliga_a_privacidade(app, email):
    resposta = _cliente(app, email).patch(f"/api/cameras/{app.config['ID']}/privacidade", json={"ativa": False})
    assert resposta.status_code == 403
    assert app.extensions["monitor_service"].worker_da_camera(app.config["ID"]).privacidade_ativa is True


def test_supervisor_desliga_e_a_troca_fica_auditada(app):
    resposta = _cliente(app, "sup@f.com").patch(
        f"/api/cameras/{app.config['ID']}/privacidade", json={"ativa": False, "motivo": "perícia do acidente 42"}
    )
    assert resposta.status_code == 200, resposta.get_json()
    assert app.extensions["monitor_service"].worker_da_camera(app.config["ID"]).privacidade_ativa is False
    with app.app_context():
        eventos = EventLog.query.filter_by(event_type="privacy_toggled").all()
    assert len(eventos) == 1
    assert eventos[0].subject == "sup@f.com"
    assert eventos[0].metadata_json["motivo"] == "perícia do acidente 42"
    assert eventos[0].severity == "warning"


def test_padrao_e_ligado():
    assert AuthTestConfig.PRIVACIDADE_PADRAO is True
