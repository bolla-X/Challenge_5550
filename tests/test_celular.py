"""F6: celular como câmera — token como única credencial, fonte e pareamento."""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from app import create_app
from app.config import AuthTestConfig
from app.extensions import db
from app.models import ROLE_OPERATOR, ROLE_TECHNICAL, Camera
from app.services.auth_service import AuthService
from app.vision.fonte_celular import PREFIXO, FonteDeCelular, fonte_do_token

SENHA = "senha-forte-de-teste"


def _jpeg(cor=(0, 128, 255)) -> bytes:
    img = np.zeros((90, 160, 3), dtype=np.uint8)
    img[:] = cor
    return cv2.imencode(".jpg", img)[1].tobytes()


@pytest.fixture()
def app(tmp_path):
    class Cfg(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'cel.db'}"

    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
        AuthService().create_user(email="tec@f.com", name="Tec", password=SENHA, role=ROLE_TECHNICAL)
        AuthService().create_user(email="op@f.com", name="Op", password=SENHA, role=ROLE_OPERATOR)
        db.session.remove()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _entrar(app, email):
    c = app.test_client()
    assert c.post("/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return c


def test_fonte_entrega_so_quadro_novo_e_recusa_lixo():
    fonte = FonteDeCelular(PREFIXO + "tok-teste", 960, 540)
    try:
        assert fonte_do_token("tok-teste") is fonte
        assert fonte.receber(b"nao-e-jpeg") is False
        assert fonte.status().state == "idle"
        assert fonte.receber(_jpeg()) is True
        ok, quadro = fonte.read()
        assert ok and quadro.shape == (90, 160, 3)
        assert fonte.status().state == "live"
        # Sem quadro novo, o read espera e devolve falha (não repete o anterior).
        assert fonte.read() == (False, None)
    finally:
        fonte.release()
    assert fonte_do_token("tok-teste") is None


def test_camera_celular_ganha_token_e_pareamento_e_so_de_tecnico(app):
    tec = _entrar(app, "tec@f.com")
    r = tec.post("/api/cameras", json={"name": "Celular", "source_type": "Celular", "source": "ignorado"})
    assert r.status_code == 201
    cam = r.get_json()
    with app.app_context():
        fonte = db.session.get(Camera, cam["id"]).source
    assert fonte.startswith(PREFIXO) and len(fonte) > len(PREFIXO) + 16, "token gerado, não digitado"

    par = tec.get(f"/api/cameras/{cam['id']}/celular").get_json()
    assert par["caminho"] == f"/cam?t={fonte[len(PREFIXO):]}"
    assert par["aviso"], "em HTTP o técnico é avisado de que o celular exige HTTPS"

    assert app.test_client().get(f"/api/cameras/{cam['id']}/celular").status_code == 401
    assert _entrar(app, "op@f.com").get(f"/api/cameras/{cam['id']}/celular").status_code in (403, 404)


def test_envio_sem_token_valido_nao_entra(app):
    anonimo = app.test_client()
    assert anonimo.post("/api/celular/inexistente/quadro", data=_jpeg(), content_type="image/jpeg").status_code == 404
    assert anonimo.get("/cam").status_code == 200, "a página é pública e não carrega dado"


def test_envio_com_token_valido_e_limitado(app):
    fonte = FonteDeCelular(PREFIXO + "tok-rota", 960, 540)
    try:
        anonimo = app.test_client()
        assert anonimo.post("/api/celular/tok-rota/quadro", data=b"lixo", content_type="image/jpeg").status_code == 400
        import time

        time.sleep(0.1)
        assert anonimo.post("/api/celular/tok-rota/quadro", data=_jpeg(), content_type="image/jpeg").status_code == 200
        assert anonimo.post("/api/celular/tok-rota/quadro", data=_jpeg(), content_type="image/jpeg").status_code == 429
        assert fonte.recebidos == 1
    finally:
        fonte.release()


def test_certificado_local_cobre_os_ips_e_e_reaproveitado(tmp_path):
    from app.utils.https_local import garantir_certificado
    from cryptography import x509

    cert, chave = garantir_certificado(tmp_path, ["192.168.0.10"])
    lido = x509.load_pem_x509_certificate(cert.read_bytes())
    ips = {str(i) for i in lido.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)}
    assert {"127.0.0.1", "192.168.0.10"} <= ips
    antes = cert.read_bytes()
    garantir_certificado(tmp_path, ["192.168.0.10"])
    assert cert.read_bytes() == antes, "mesmo IP: reaproveita"
    garantir_certificado(tmp_path, ["10.0.0.5"])
    assert cert.read_bytes() != antes, "IP novo: gera outro"
    assert chave.exists()
