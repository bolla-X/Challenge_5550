"""Primeiro acesso do supervisor (MISSÃO 4, Fase 3): assistente, detecção e senha temporária.

Não confundir com `tests/test_onboarding.py`, que trata do caminho de instalação
(`flask db upgrade` num clone limpo).

Roda com `AUTH_REQUIRED=True` e banco em arquivo (mesmo desenho de `tests/test_auth.py`):
cada requisição abre o próprio contexto, como em produção. O blueprint ainda não é
registrado por `create_app` (quem liga é `app/__init__.py`), então a fixture o registra.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from app import create_app
from app.api.onboarding import onboarding_bp
from app.config import AuthTestConfig
from app.extensions import db
from app.models import ROLE_OPERATOR, ROLE_SUPERVISOR, ROLE_TECHNICAL, Camera, EstadoDoOnboarding, User
from app.services import onboarding as servico
from app.services.auth_service import AuthService
from sqlalchemy import text
from werkzeug.security import check_password_hash

SENHA = "senha-forte-de-teste"
QUADRADO = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
PADRAO_DE_RISCO = [[0.70, 0.10], [0.98, 0.10], [0.98, 0.95], [0.70, 0.95]]  # RISK_AREA_POLYGON do ambiente
ROTAS = [
    ("GET", "/api/onboarding", None),
    ("PUT", "/api/onboarding/camera", {"estado": "feito"}),
    ("POST", "/api/onboarding/refazer", {}),
    ("POST", "/api/onboarding/concluir", {}),
]


def _criar_app(tmp_path):
    class Config(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'onboarding-test.db'}"
        SAUDE_VISUAL_DIR = str(tmp_path / "referencias")

    app = create_app(Config)
    if "onboarding" not in app.blueprints:  # idempotente: não quebra quando o create_app passar a registrar
        app.register_blueprint(onboarding_bp)
    return app


@pytest.fixture()
def app(tmp_path):
    """Só a conta do supervisor existe: o ponto de partida honesto do primeiro acesso."""
    app = _criar_app(tmp_path)
    with app.app_context():
        db.create_all()
        AuthService().create_user(email="supervisor@fabrica.com", name="Supervisora", password=SENHA, role=ROLE_SUPERVISOR)
        db.session.remove()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _conta(app, papel: str, **extra) -> None:
    with app.app_context():
        AuthService().create_user(email=f"{papel}@fabrica.com", name=papel.title(), password=SENHA, role=papel, **extra)
        db.session.remove()


def _cliente(app, papel: str):
    cliente = app.test_client()
    r = cliente.post("/api/auth/login", json={"email": f"{papel}@fabrica.com", "password": SENHA})
    assert r.status_code == 200, r.get_json()
    return cliente


@pytest.fixture()
def sup(app):
    return _cliente(app, ROLE_SUPERVISOR)


def _camera(app, **campos) -> int:
    with app.app_context():
        camera = Camera(name=campos.pop("name", "Pátio"), source="0", **campos)
        db.session.add(camera)
        db.session.commit()
        return camera.id


def _estado(sup) -> dict:
    r = sup.get("/api/onboarding")
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _passo(estado: dict, nome: str) -> dict:
    return next(p for p in estado["passos"] if p["passo"] == nome)


def _item(estado: dict, nome: str) -> dict:
    return next(i for i in estado["checklist"]["itens"] if i["passo"] == nome)


# ------------------------------------------------------------------- papéis --
@pytest.mark.parametrize("metodo,caminho,corpo", ROTAS)
def test_sem_sessao_e_401(app, metodo, caminho, corpo):
    r = app.test_client().open(caminho, method=metodo, json=corpo)
    assert r.status_code == 401


@pytest.mark.parametrize("papel", [ROLE_TECHNICAL, ROLE_OPERATOR])
@pytest.mark.parametrize("metodo,caminho,corpo", ROTAS)
def test_tecnico_e_operador_recebem_403(app, papel, metodo, caminho, corpo):
    extra = {} if papel == ROLE_TECHNICAL else {"camera_id": _camera(app)}
    _conta(app, papel, **extra)
    r = _cliente(app, papel).open(caminho, method=metodo, json=corpo)
    assert r.status_code == 403
    assert r.get_json()["code"] == "forbidden"


def test_tecnico_barrado_nao_grava_nada(app):
    _conta(app, ROLE_TECHNICAL)
    _cliente(app, ROLE_TECHNICAL).put("/api/onboarding/camera", json={"estado": "feito"})
    with app.app_context():
        assert db.session.get(EstadoDoOnboarding, 1) is None


@pytest.mark.parametrize("metodo,caminho,corpo", ROTAS)
def test_supervisor_acessa_todas_as_rotas(sup, metodo, caminho, corpo):
    assert sup.open(caminho, method=metodo, json=corpo).status_code == 200


# ------------------------------------------------------------ estado inicial --
def test_estado_inicial_e_tudo_pendente_e_sem_linha_no_banco(app, sup):
    estado = _estado(sup)
    assert estado["ordem"] == ["camera", "referencia", "planta", "zonas", "epis", "usuarios", "pronto"]
    assert [p["passo"] for p in estado["passos"]] == estado["ordem"]
    assert {p["estado"] for p in estado["passos"]} == {"pendente"}
    assert estado["proximo_passo"] == "camera"
    assert estado["progresso"] == {"total": 7, "feitos": 0, "pulados": 0, "resolvidos": 0}
    assert estado["concluido"] is False and estado["concluido_em"] is None
    assert estado["checklist"]["pronto_para_operar"] is False
    assert estado["checklist"]["pendentes"] == 6
    assert _passo(estado, "pronto")["detectado"] is None  # o checklist final não tem detecção própria
    with app.app_context():
        assert db.session.get(EstadoDoOnboarding, 1) is None  # ler não grava


# ----------------------------------------------------- detecção automática --
def test_detecta_camera_cadastrada(app, sup):
    assert _passo(_estado(sup), "camera")["detectado"] is False
    _camera(app)
    passo = _passo(_estado(sup), "camera")
    assert (passo["detectado"], passo["estado"], passo["marcado"]) == (True, "feito", "pendente")
    assert passo["detalhe"] == "1 câmera cadastrada."
    _camera(app, name="Escada")
    assert _passo(_estado(sup), "camera")["detalhe"] == "2 câmeras cadastradas."


def test_detecta_referencia_da_saude_visual_pelo_arquivo_no_disco(app, sup, tmp_path):
    cid = _camera(app)
    assert _passo(_estado(sup), "referencia")["detectado"] is False
    pasta = tmp_path / "referencias"
    pasta.mkdir()
    (pasta / f"camera_{cid + 1}.png").write_bytes(b"png")  # referência de OUTRA câmera não conta
    assert _passo(_estado(sup), "referencia")["detectado"] is False
    (pasta / f"camera_{cid}.png").write_bytes(b"png")
    passo = _passo(_estado(sup), "referencia")
    assert (passo["detectado"], passo["estado"]) == (True, "feito")
    assert passo["detalhe"] == "1 câmera com imagem de referência."


def test_referencia_com_saude_visual_desligada_nao_finge(app, sup, tmp_path):
    cid = _camera(app)
    (tmp_path / "referencias").mkdir()
    (tmp_path / "referencias" / f"camera_{cid}.png").write_bytes(b"png")
    app.config["SAUDE_VISUAL_ATIVA"] = False
    passo = _passo(_estado(sup), "referencia")
    assert passo["detectado"] is False
    assert "desligada" in passo["detalhe"]


def test_caminho_da_referencia_e_o_do_worker(app, tmp_path):
    """O serviço e o `CameraWorker` têm que olhar o MESMO arquivo, com e sem `SAUDE_VISUAL_DIR`."""
    from app.services.camera_worker import CameraWorker

    for pasta in (str(tmp_path / "referencias"), ""):
        app.config["SAUDE_VISUAL_DIR"] = pasta
        do_worker = CameraWorker._caminho_da_referencia(SimpleNamespace(app=app, camera_id=7))
        assert servico.caminho_da_referencia(app.config, app.instance_path, 7) == do_worker


def test_detecta_planta_calibrada_so_com_quatro_pontos_nos_dois_lados(app, sup):
    cid = _camera(app, planta={"pontos_camera": QUADRADO[:1], "pontos_planta": QUADRADO})
    assert _passo(_estado(sup), "planta")["detectado"] is False
    with app.app_context():
        db.session.get(Camera, cid).planta = {"pontos_camera": QUADRADO, "pontos_planta": QUADRADO}
        db.session.commit()
    passo = _passo(_estado(sup), "planta")
    assert (passo["detectado"], passo["detalhe"]) == (True, "1 câmera com a planta calibrada.")


def test_zona_so_conta_quando_difere_do_padrao_do_ambiente(app, sup):
    cid = _camera(app)  # risk_polygon None: usa o padrão
    assert _passo(_estado(sup), "zonas")["detectado"] is False

    def definir(poligono):
        with app.app_context():
            db.session.get(Camera, cid).risk_polygon = poligono
            db.session.commit()

    definir(PADRAO_DE_RISCO)  # gravada, mas idêntica ao padrão
    assert _passo(_estado(sup), "zonas")["detectado"] is False
    definir([{"x": x, "y": y} for x, y in PADRAO_DE_RISCO])  # mesmo polígono, outro formato
    assert _passo(_estado(sup), "zonas")["detectado"] is False
    definir([[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]])
    passo = _passo(_estado(sup), "zonas")
    assert (passo["detectado"], passo["detalhe"]) == (True, "1 câmera com zona de risco própria.")
    definir("lixo")  # formato que não é polígono não conta
    assert _passo(_estado(sup), "zonas")["detectado"] is False


def test_detecta_epis_exigidos_na_portaria(app, sup):
    cid = _camera(app)
    assert _passo(_estado(sup), "epis")["detectado"] is False
    with app.app_context():
        db.session.get(Camera, cid).gate_required = []  # portaria ligada sem nenhum EPI não conta
        db.session.commit()
    assert _passo(_estado(sup), "epis")["detectado"] is False
    with app.app_context():
        db.session.get(Camera, cid).gate_required = ["helmet", "vest"]
        db.session.commit()
    passo = _passo(_estado(sup), "epis")
    assert (passo["detectado"], passo["detalhe"]) == (True, "1 câmera com EPIs exigidos na portaria.")


def test_detecta_conta_alem_do_supervisor_e_ignora_conta_desativada(app, sup):
    passo = _passo(_estado(sup), "usuarios")
    assert (passo["detectado"], passo["detalhe"]) == (False, "Só a sua conta existe.")
    _conta(app, ROLE_TECHNICAL)
    with app.app_context():
        User.query.filter_by(email="technical@fabrica.com").one().active = False
        db.session.commit()
    assert _passo(_estado(sup), "usuarios")["detectado"] is False
    with app.app_context():
        User.query.filter_by(email="technical@fabrica.com").one().active = True
        db.session.commit()
    passo = _passo(_estado(sup), "usuarios")
    assert (passo["detectado"], passo["detalhe"]) == (True, "1 conta além da sua.")


def test_checklist_pronto_so_com_tudo_detectado(app, sup, tmp_path):
    cid = _camera(app, planta={"pontos_camera": QUADRADO, "pontos_planta": QUADRADO},
                  risk_polygon=[[0.1, 0.1], [0.5, 0.1], [0.5, 0.5]], gate_required=["helmet"])
    _conta(app, ROLE_TECHNICAL)
    estado = _estado(sup)
    assert [i["ok"] for i in estado["checklist"]["itens"]] == [True, False, True, True, True, True]
    assert estado["checklist"]["pendentes"] == 1 and estado["checklist"]["pronto_para_operar"] is False

    (tmp_path / "referencias").mkdir()
    (tmp_path / "referencias" / f"camera_{cid}.png").write_bytes(b"png")
    estado = _estado(sup)
    assert all(i["ok"] for i in estado["checklist"]["itens"])
    assert estado["checklist"]["pronto_para_operar"] is True


# ------------------------------------------------- marcar, pular, refazer ... --
def test_marcar_feito_grava_quem_marcou_e_sobrevive_a_nova_leitura(app, sup):
    r = sup.put("/api/onboarding/planta", json={"estado": "feito"})
    assert r.status_code == 200
    passo = _passo(r.get_json(), "planta")
    assert (passo["estado"], passo["marcado"], passo["detectado"]) == ("feito", "feito", False)
    assert r.get_json()["progresso"] == {"total": 7, "feitos": 1, "pulados": 0, "resolvidos": 1}
    assert _passo(_estado(sup), "planta")["estado"] == "feito"
    with app.app_context():
        linha = db.session.get(EstadoDoOnboarding, 1)
        assert linha.atualizado_por == "supervisor@fabrica.com"
        assert linha.passos["planta"] == "feito" and linha.passos["camera"] == "pendente"


def test_marcar_feito_nao_finge_o_checklist(sup):
    """Marcado à mão conta na barra de progresso; o ✓ do 'pronto para operar' só vem do que foi detectado."""
    estado = sup.put("/api/onboarding/camera", json={"estado": "feito"}).get_json()
    assert _passo(estado, "camera")["estado"] == "feito"
    assert _item(estado, "camera")["ok"] is False
    assert estado["checklist"]["pronto_para_operar"] is False


def test_pular_e_voltar_para_pendente(sup):
    estado = sup.put("/api/onboarding/zonas", json={"estado": "pulado"}).get_json()
    assert (_passo(estado, "zonas")["estado"], estado["progresso"]["pulados"], estado["progresso"]["resolvidos"]) == ("pulado", 1, 1)
    assert _item(estado, "zonas")["ok"] is False  # pulado é pendente de verdade no checklist
    estado = sup.put("/api/onboarding/zonas", json={"estado": "pendente"}).get_json()
    assert (_passo(estado, "zonas")["estado"], estado["progresso"]["resolvidos"]) == ("pendente", 0)


def test_o_que_foi_detectado_vence_a_marcacao_de_pulado(app, sup):
    _camera(app)
    passo = _passo(sup.put("/api/onboarding/camera", json={"estado": "pulado"}).get_json(), "camera")
    assert (passo["estado"], passo["marcado"], passo["detectado"]) == ("feito", "pulado", True)


def test_proximo_passo_pula_o_que_ja_esta_resolvido(app, sup):
    _camera(app)
    sup.put("/api/onboarding/referencia", json={"estado": "pulado"})
    assert _estado(sup)["proximo_passo"] == "planta"


@pytest.mark.parametrize("corpo", [{"estado": "quase"}, {"estado": ""}, {}, {"estado": None}])
def test_estado_invalido_e_400(sup, corpo):
    r = sup.put("/api/onboarding/camera", json=corpo)
    assert r.status_code == 400 and r.get_json()["code"] == "estado_invalido"


def test_corpo_que_nao_e_objeto_e_400(sup):
    assert sup.put("/api/onboarding/camera", json=["feito"]).status_code == 400
    assert sup.put("/api/onboarding/camera", data="x", content_type="text/plain").status_code == 400


def test_passo_desconhecido_e_404_e_nao_grava(app, sup):
    r = sup.put("/api/onboarding/teletransporte", json={"estado": "feito"})
    assert r.status_code == 404 and r.get_json()["code"] == "passo_desconhecido"
    with app.app_context():
        assert db.session.get(EstadoDoOnboarding, 1) is None


def test_concluir_marca_o_passo_final_e_registra_quando(sup):
    r = sup.post("/api/onboarding/concluir")
    estado = r.get_json()
    assert estado["concluido"] is True and estado["concluido_em"]
    assert _passo(estado, "pronto")["estado"] == "feito"


def test_concluir_com_pendencia_e_permitido_mas_o_checklist_continua_honesto(sup):
    estado = sup.post("/api/onboarding/concluir").get_json()
    assert estado["concluido"] is True
    assert estado["checklist"]["pronto_para_operar"] is False
    assert estado["checklist"]["pendentes"] == 6


def test_desfazer_o_passo_final_reabre_o_assistente(sup):
    sup.post("/api/onboarding/concluir")
    estado = sup.put("/api/onboarding/pronto", json={"estado": "pendente"}).get_json()
    assert estado["concluido"] is False and estado["concluido_em"] is None


def test_refazer_zera_as_marcacoes_mas_nao_o_que_existe(app, sup):
    _camera(app)
    sup.put("/api/onboarding/planta", json={"estado": "feito"})
    sup.put("/api/onboarding/zonas", json={"estado": "pulado"})
    sup.post("/api/onboarding/concluir")
    estado = sup.post("/api/onboarding/refazer").get_json()
    assert estado["concluido"] is False and estado["concluido_em"] is None
    assert {p["marcado"] for p in estado["passos"]} == {"pendente"}
    assert _passo(estado, "camera")["estado"] == "feito"  # a câmera continua cadastrada: não some por "refazer"
    assert _passo(estado, "planta")["estado"] == "pendente"
    assert estado["proximo_passo"] == "referencia"


def test_marcacao_corrompida_no_banco_e_ignorada(app, sup):
    with app.app_context():
        db.session.add(EstadoDoOnboarding(id=1, passos={"camera": "talvez", "fantasma": "feito", "planta": "pulado"}))
        db.session.commit()
    estado = _estado(sup)
    assert _passo(estado, "camera")["estado"] == "pendente"
    assert _passo(estado, "planta")["estado"] == "pulado"
    assert len(estado["passos"]) == 7


def test_duas_primeiras_escritas_seguidas_nao_duplicam_a_linha_unica(app, sup):
    sup.put("/api/onboarding/camera", json={"estado": "feito"})
    sup.put("/api/onboarding/planta", json={"estado": "feito"})
    with app.app_context():
        assert EstadoDoOnboarding.query.count() == 1


# --------------------------------------------------------------------- demo --
def test_demo_semeia_o_primeiro_acesso_concluido_e_o_refazer_continua_disponivel(app, monkeypatch):
    import app.demo as demo

    monkeypatch.setattr(demo, "webcam_disponivel", lambda indice=0: False)
    info = demo.semear(app)
    demo_sup = app.test_client()
    r = demo_sup.post("/api/auth/login", json={"email": "supervisor@demo.local", "password": info["senhas"]["supervisor"]})
    assert r.status_code == 200

    estado = demo_sup.get("/api/onboarding").get_json()
    assert estado["concluido"] is True
    assert {p["estado"] for p in estado["passos"]} == {"feito"}
    assert estado["progresso"]["resolvidos"] == 7 and estado["proximo_passo"] is None
    assert estado["atualizado_por"] == "demo"
    # A detecção roda sobre o que a demo realmente semeou (câmeras, planta, zona, portaria, contas).
    # A referência só nasce com a câmera ligada: nesta semeadura (sem worker) ela segue pendente, e o checklist não finge.
    assert [i["ok"] for i in estado["checklist"]["itens"]] == [True, False, True, True, True, True]

    refeito = demo_sup.post("/api/onboarding/refazer").get_json()
    assert refeito["concluido"] is False
    assert {p["marcado"] for p in refeito["passos"]} == {"pendente"}


def test_fora_da_demo_o_primeiro_acesso_nao_vem_concluido(app, sup):
    assert _estado(sup)["concluido"] is False


# ----------------------------------------------------------- senha temporária --
def _criar_conta_temporaria(sup, **extra):
    corpo = {"email": "novo@fabrica.com", "name": "Pessoa Nova", "role": ROLE_TECHNICAL, "senha_temporaria": True} | extra
    return sup.post("/api/users", json=corpo)


def test_senha_temporaria_aparece_uma_vez_e_a_conta_entra_com_ela(app, sup):
    r = _criar_conta_temporaria(sup)
    assert r.status_code == 201
    corpo = r.get_json()
    senha = corpo["senha_temporaria"]
    assert isinstance(senha, str) and len(senha) >= 16
    assert r.headers["Cache-Control"] == "no-store"
    assert corpo["user"]["email"] == "novo@fabrica.com" and "password_hash" not in corpo["user"]

    entrou = app.test_client().post("/api/auth/login", json={"email": "novo@fabrica.com", "password": senha})
    assert entrou.status_code == 200


def test_senha_temporaria_nao_volta_em_nenhuma_leitura(app, sup):
    senha = _criar_conta_temporaria(sup).get_json()["senha_temporaria"]
    lista = sup.get("/api/users")
    assert senha not in lista.get_data(as_text=True)
    assert "senha_temporaria" not in lista.get_data(as_text=True)
    assert senha not in sup.get("/api/onboarding").get_data(as_text=True)
    with app.app_context():
        novo = User.query.filter_by(email="novo@fabrica.com").one()
        assert senha not in str(novo.to_dict())


def test_senha_temporaria_so_o_hash_e_persistido(app, sup):
    senha = _criar_conta_temporaria(sup).get_json()["senha_temporaria"]
    with app.app_context():
        novo = User.query.filter_by(email="novo@fabrica.com").one()
        assert novo.password_hash != senha and check_password_hash(novo.password_hash, senha)
        for tabela in ("users", "onboarding"):
            for linha in db.session.execute(text(f"SELECT * FROM {tabela}")):  # noqa: S608  (nome fixo, não vem de entrada)
                assert senha not in repr(tuple(linha)), f"senha em claro na tabela {tabela}"


def test_senha_temporaria_nunca_vai_para_o_log(sup, caplog):
    with caplog.at_level(logging.DEBUG):
        senha = _criar_conta_temporaria(sup).get_json()["senha_temporaria"]
    assert senha not in caplog.text
    assert not any(senha in repr(vars(registro)) for registro in caplog.records)


def test_cada_senha_temporaria_e_diferente_e_forte(sup):
    primeira = _criar_conta_temporaria(sup).get_json()["senha_temporaria"]
    segunda = _criar_conta_temporaria(sup, email="outra@fabrica.com").get_json()["senha_temporaria"]
    assert primeira != segunda
    assert len(primeira) >= 16 and len(segunda) >= 16


def test_senha_temporaria_com_senha_informada_e_400_e_nao_cria_conta(app, sup):
    r = _criar_conta_temporaria(sup, password=SENHA)
    assert r.status_code == 400
    with app.app_context():
        assert User.query.filter_by(email="novo@fabrica.com").first() is None


def test_conta_sem_senha_temporaria_segue_igual(sup):
    r = sup.post("/api/users", json={"email": "manual@fabrica.com", "name": "Manual", "role": ROLE_TECHNICAL, "password": SENHA})
    assert r.status_code == 201
    assert "senha_temporaria" not in r.get_json() and "Cache-Control" not in r.headers


def test_so_o_booleano_true_pede_senha_temporaria(sup):
    r = _criar_conta_temporaria(sup, senha_temporaria="true")  # texto não liga a geração: cai na regra de senha mínima
    assert r.status_code == 400
    assert "senha_temporaria" not in r.get_json()


def test_senha_temporaria_mantem_as_regras_de_operador_e_de_duplicidade(app, sup):
    r = _criar_conta_temporaria(sup, role=ROLE_OPERATOR)
    assert r.status_code == 400 and "câmera" in r.get_json()["error"]
    cid = _camera(app)
    assert _criar_conta_temporaria(sup, email="op@fabrica.com", role=ROLE_OPERATOR, camera_id=cid).status_code == 201
    assert _criar_conta_temporaria(sup).status_code == 201
    repetida = _criar_conta_temporaria(sup)  # mesmo e-mail: recusa, e sem devolver senha nenhuma
    assert repetida.status_code == 400 and "senha_temporaria" not in repetida.get_json()


def test_tecnico_nao_cria_conta_com_senha_temporaria(app):
    _conta(app, ROLE_TECHNICAL)
    r = _criar_conta_temporaria(_cliente(app, ROLE_TECHNICAL))
    assert r.status_code == 403 and "senha_temporaria" not in r.get_data(as_text=True)
