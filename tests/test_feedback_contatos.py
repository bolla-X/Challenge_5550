"""Feedback dentro do app e contatos da página pública `/produto` (MISSÃO 4, Fase 3 itens 10 e 11).

Roda com `AUTH_REQUIRED=True` e banco em arquivo (mesmo desenho de `tests/test_onboarding_assistente.py`).
O blueprint ainda não é registrado por `create_app` (quem liga é `app/__init__.py`), então a fixture o registra
quando falta.

Papéis esperados:
- `POST /api/feedback`: qualquer conta logada; sem sessão, 401.
- `GET /api/feedback`, `POST /api/feedback/<id>/lido`: só Supervisor (Técnico e Operador, 403; sem sessão, 401).
- `POST /api/contatos`: PÚBLICA, com limite por IP.
- `GET /api/contatos`, `POST /api/contatos/<id>/lido`: só Supervisor.
"""

from __future__ import annotations

import pytest
from app import create_app
from app.api.feedback import feedback_bp
from app.config import AuthTestConfig
from app.extensions import db
from app.models import ROLE_OPERATOR, ROLE_SUPERVISOR, ROLE_TECHNICAL, Camera, Contato, Feedback
from app.services.auth_service import AuthService
from app.utils.limite_por_ip import LimitePorIp

SENHA = "senha-forte-de-teste"
CONTATO_VALIDO = {
    "nome": "Ana Souza",
    "empresa": "Metalúrgica Exemplo",
    "email": "ana@exemplo.com.br",
    "mensagem": "Quero ver o sistema rodando na nossa planta.",
    "consentimento": True,
}


def _criar_app(tmp_path):
    class Config(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'feedback-test.db'}"
        CONTATOS_POR_IP_MAX = 3
        CONTATOS_JANELA_S = 600

    app = create_app(Config)
    if "feedback" not in app.blueprints:  # idempotente: não quebra quando o create_app passar a registrar
        app.register_blueprint(feedback_bp)
    return app


@pytest.fixture()
def app(tmp_path):
    app = _criar_app(tmp_path)
    with app.app_context():
        db.create_all()
        camera = Camera(name="Pátio", source="0")
        db.session.add(camera)
        db.session.commit()
        for papel in (ROLE_SUPERVISOR, ROLE_TECHNICAL):
            AuthService().create_user(email=f"{papel}@fabrica.com", name=papel.title(), password=SENHA, role=papel)
        AuthService().create_user(
            email="operator@fabrica.com", name="Operador", password=SENHA, role=ROLE_OPERATOR, camera_id=camera.id
        )
        db.session.remove()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _cliente(app, papel: str):
    cliente = app.test_client()
    r = cliente.post("/api/auth/login", json={"email": f"{papel}@fabrica.com", "password": SENHA})
    assert r.status_code == 200, r.get_json()
    return cliente


@pytest.fixture()
def sup(app):
    return _cliente(app, ROLE_SUPERVISOR)


def _contar(app, modelo) -> int:
    with app.app_context():
        return modelo.query.count()


# ============================================================== feedback: envio ==
def test_feedback_sem_sessao_e_401(app):
    r = app.test_client().post("/api/feedback", json={"texto": "oi"})
    assert r.status_code == 401
    assert _contar(app, Feedback) == 0


@pytest.mark.parametrize("papel", [ROLE_OPERATOR, ROLE_TECHNICAL, ROLE_SUPERVISOR])
def test_qualquer_conta_logada_envia_feedback(app, papel):
    r = _cliente(app, papel).post("/api/feedback", json={"texto": "  A tela de alertas demora a abrir.  ", "tela": "/evacuacao"})
    assert r.status_code == 201, r.get_json()
    item = r.get_json()["feedback"]
    assert item["texto"] == "A tela de alertas demora a abrir."
    assert item["tela"] == "/evacuacao"
    assert item["lido"] is False
    assert item["tipo_de_conta"] == papel  # vem da sessão


def test_tipo_de_conta_e_user_id_vem_da_sessao_nao_do_corpo(app):
    cliente = _cliente(app, ROLE_OPERATOR)
    r = cliente.post("/api/feedback", json={"texto": "oi", "tipo_de_conta": "supervisor", "user_id": 999, "lido": True})
    assert r.status_code == 201
    with app.app_context():
        item = Feedback.query.one()
        assert item.tipo_de_conta == ROLE_OPERATOR
        assert item.user_id != 999
        assert item.lido is False


def test_feedback_guarda_so_o_caminho_da_tela(app):
    """Query e fragmento podem carregar token (ex.: `?t=` do controle do palco): não vão para o banco."""
    cliente = _cliente(app, ROLE_TECHNICAL)
    cliente.post("/api/feedback", json={"texto": "a", "tela": "/palco/controle?t=SEGREDO#x"})
    cliente.post("/api/feedback", json={"texto": "b", "tela": "https://externo.example/x"})
    cliente.post("/api/feedback", json={"texto": "c", "tela": 42})
    with app.app_context():
        telas = {f.texto: f.tela for f in Feedback.query.all()}
    assert telas == {"a": "/palco/controle", "b": None, "c": None}


@pytest.mark.parametrize("corpo", [{}, {"texto": ""}, {"texto": "   \n\t "}, {"texto": None}, {"texto": 123}, {"texto": ["a"]}])
def test_feedback_vazio_ou_invalido_e_400(app, corpo):
    r = _cliente(app, ROLE_TECHNICAL).post("/api/feedback", json=corpo)
    assert r.status_code == 400
    assert r.get_json()["campo"] == "texto"
    assert _contar(app, Feedback) == 0


def test_feedback_sem_json_e_400(app):
    cliente = _cliente(app, ROLE_TECHNICAL)
    assert cliente.post("/api/feedback", data="texto solto").status_code == 400
    assert cliente.post("/api/feedback", json=["x"]).status_code == 400


def test_feedback_limite_de_2000_caracteres(app):
    cliente = _cliente(app, ROLE_TECHNICAL)
    assert cliente.post("/api/feedback", json={"texto": "x" * 2000}).status_code == 201
    r = cliente.post("/api/feedback", json={"texto": "x" * 2001})
    assert r.status_code == 400
    assert "2.000" in r.get_json()["error"]
    assert _contar(app, Feedback) == 1


def test_feedback_conta_so_depois_de_tirar_os_espacos_das_pontas(app):
    assert _cliente(app, ROLE_TECHNICAL).post("/api/feedback", json={"texto": "  " + "x" * 2000 + "  "}).status_code == 201


def test_feedback_texto_com_html_volta_como_texto_puro(app, sup):
    """O servidor não interpreta nada: guarda e devolve a string; quem escapa é a tela (React)."""
    r = _cliente(app, ROLE_TECHNICAL).post("/api/feedback", json={"texto": "<script>alert(1)</script>"})
    assert r.status_code == 201
    assert sup.get("/api/feedback").get_json()["items"][0]["texto"] == "<script>alert(1)</script>"


# ============================================================ feedback: leitura ==
def test_leitura_do_feedback_sem_sessao_e_401(app):
    assert app.test_client().get("/api/feedback").status_code == 401
    assert app.test_client().post("/api/feedback/1/lido").status_code == 401


@pytest.mark.parametrize("papel", [ROLE_TECHNICAL, ROLE_OPERATOR])
def test_so_supervisor_le_e_marca_feedback(app, sup, papel):
    sup_item = _cliente(app, ROLE_TECHNICAL).post("/api/feedback", json={"texto": "oi"}).get_json()["feedback"]
    cliente = _cliente(app, papel)
    for r in (cliente.get("/api/feedback"), cliente.post(f"/api/feedback/{sup_item['id']}/lido")):
        assert r.status_code == 403
        assert r.get_json()["code"] == "forbidden"
    with app.app_context():
        assert db.session.get(Feedback, sup_item["id"]).lido is False


def test_supervisor_lista_feedback_do_mais_novo_ao_mais_antigo_com_o_autor(app, sup):
    tecnico = _cliente(app, ROLE_TECHNICAL)
    tecnico.post("/api/feedback", json={"texto": "primeiro"})
    tecnico.post("/api/feedback", json={"texto": "segundo"})
    corpo = sup.get("/api/feedback").get_json()
    assert [i["texto"] for i in corpo["items"]] == ["segundo", "primeiro"]
    assert corpo["count"] == 2
    assert corpo["nao_lidos"] == 2
    assert corpo["items"][0]["autor"] == "Technical"


def test_marcar_feedback_como_lido_e_filtrar(app, sup):
    tecnico = _cliente(app, ROLE_TECHNICAL)
    a = tecnico.post("/api/feedback", json={"texto": "a"}).get_json()["feedback"]["id"]
    tecnico.post("/api/feedback", json={"texto": "b"})

    r = sup.post(f"/api/feedback/{a}/lido")
    assert r.status_code == 200
    assert r.get_json()["feedback"]["lido"] is True
    assert sup.post(f"/api/feedback/{a}/lido").status_code == 200  # idempotente

    todos = sup.get("/api/feedback").get_json()
    assert todos["count"] == 2
    assert todos["nao_lidos"] == 1
    assert [i["texto"] for i in sup.get("/api/feedback?lido=false").get_json()["items"]] == ["b"]
    assert [i["texto"] for i in sup.get("/api/feedback?lido=true").get_json()["items"]] == ["a"]

    r = sup.post(f"/api/feedback/{a}/lido", json={"lido": False})  # desfazer
    assert r.get_json()["feedback"]["lido"] is False
    assert sup.get("/api/feedback").get_json()["nao_lidos"] == 2


def test_marcar_lido_valida_o_corpo_e_o_id(app, sup):
    a = _cliente(app, ROLE_TECHNICAL).post("/api/feedback", json={"texto": "a"}).get_json()["feedback"]["id"]
    assert sup.post("/api/feedback/9999/lido").status_code == 404
    assert sup.post(f"/api/feedback/{a}/lido", json={"lido": "sim"}).status_code == 400
    with app.app_context():
        assert db.session.get(Feedback, a).lido is False


def test_limite_da_listagem_respeita_o_teto(app, sup):
    tecnico = _cliente(app, ROLE_TECHNICAL)
    for i in range(3):
        tecnico.post("/api/feedback", json={"texto": f"f{i}"})
    assert sup.get("/api/feedback?limit=2").get_json()["count"] == 2
    assert sup.get("/api/feedback?limit=0").get_json()["count"] == 3  # 0 cai no padrão, não em "nada"


# ============================================================ contatos: envio ==
def test_contato_publico_aceita_sem_sessao(app):
    r = app.test_client().post("/api/contatos", json=CONTATO_VALIDO)
    assert r.status_code == 201
    assert r.get_json() == {"ok": True}
    with app.app_context():
        c = Contato.query.one()
        assert (c.nome, c.empresa, c.email) == ("Ana Souza", "Metalúrgica Exemplo", "ana@exemplo.com.br")
        assert c.consentimento is True
        assert c.lido is False
        assert c.criado_em is not None


def test_contato_tambem_funciona_com_sessao(app):
    assert _cliente(app, ROLE_TECHNICAL).post("/api/contatos", json=CONTATO_VALIDO).status_code == 201


def test_contato_nao_grava_ip_nem_devolve_dados(app):
    """O IP só vive na memória do limitador: nenhuma coluna de `contatos` o guarda."""
    assert {c.name for c in Contato.__table__.columns} == {
        "id", "nome", "empresa", "email", "mensagem", "consentimento", "criado_em", "lido",
    }


def test_contato_sem_empresa_e_valido(app):
    corpo = {k: v for k, v in CONTATO_VALIDO.items() if k != "empresa"}
    assert app.test_client().post("/api/contatos", json=corpo).status_code == 201
    with app.app_context():
        assert Contato.query.one().empresa is None


@pytest.mark.parametrize(
    "alteracao,campo",
    [
        ({"nome": ""}, "nome"),
        ({"nome": "   "}, "nome"),
        ({"nome": "n" * 121}, "nome"),
        ({"nome": 12}, "nome"),
        ({"empresa": "e" * 161}, "empresa"),
        ({"email": ""}, "email"),
        ({"email": "sem-arroba"}, "email"),
        ({"email": "a@b"}, "email"),
        ({"email": "a b@c.com"}, "email"),
        ({"email": "a@b.com " + "x" * 260}, "email"),
        ({"mensagem": ""}, "mensagem"),
        ({"mensagem": "m" * 2001}, "mensagem"),
        ({"consentimento": False}, "consentimento"),
        ({"consentimento": "true"}, "consentimento"),
        ({"consentimento": 1}, "consentimento"),
        ({"consentimento": None}, "consentimento"),
    ],
)
def test_contato_invalido_e_400_e_nao_grava(app, alteracao, campo):
    r = app.test_client().post("/api/contatos", json=CONTATO_VALIDO | alteracao)
    assert r.status_code == 400
    assert r.get_json()["campo"] == campo
    assert _contar(app, Contato) == 0


def test_contato_sem_consentimento_no_corpo_e_400(app):
    corpo = {k: v for k, v in CONTATO_VALIDO.items() if k != "consentimento"}
    r = app.test_client().post("/api/contatos", json=corpo)
    assert r.status_code == 400
    assert r.get_json()["campo"] == "consentimento"


def test_contato_sem_json_e_400(app):
    cliente = app.test_client()
    assert cliente.post("/api/contatos", data="x").status_code == 400
    assert cliente.post("/api/contatos", json=[1]).status_code == 400


def test_contato_invalido_nao_gasta_o_limite(app):
    cliente = app.test_client()
    for _ in range(10):
        assert cliente.post("/api/contatos", json=CONTATO_VALIDO | {"email": "x"}).status_code == 400
    assert cliente.post("/api/contatos", json=CONTATO_VALIDO).status_code == 201


# ===================================================== contatos: limite por IP ==
def test_limite_por_ip_responde_429_com_retry_after(app):
    cliente = app.test_client()
    for _ in range(3):  # CONTATOS_POR_IP_MAX da fixture
        assert cliente.post("/api/contatos", json=CONTATO_VALIDO).status_code == 201
    r = cliente.post("/api/contatos", json=CONTATO_VALIDO)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    assert "Tente de novo" in r.get_json()["error"]
    assert _contar(app, Contato) == 3


def test_limite_e_por_endereco(app):
    a = app.test_client()
    for _ in range(3):
        a.post("/api/contatos", json=CONTATO_VALIDO, environ_overrides={"REMOTE_ADDR": "10.0.0.1"})
    assert a.post("/api/contatos", json=CONTATO_VALIDO, environ_overrides={"REMOTE_ADDR": "10.0.0.1"}).status_code == 429
    assert a.post("/api/contatos", json=CONTATO_VALIDO, environ_overrides={"REMOTE_ADDR": "10.0.0.2"}).status_code == 201


def test_limite_nao_confia_em_x_forwarded_for(app):
    """Se confiasse, bastaria mudar o cabeçalho para escapar do limite."""
    cliente = app.test_client()
    for i in range(3):
        cliente.post("/api/contatos", json=CONTATO_VALIDO, headers={"X-Forwarded-For": f"1.1.1.{i}"})
    r = cliente.post("/api/contatos", json=CONTATO_VALIDO, headers={"X-Forwarded-For": "9.9.9.9"})
    assert r.status_code == 429


def test_limite_libera_quando_a_janela_passa(app):
    relogio = {"t": 1000.0}
    with app.app_context():
        app.extensions["limite_contatos"] = LimitePorIp(2, 60, agora=lambda: relogio["t"])
    cliente = app.test_client()
    assert cliente.post("/api/contatos", json=CONTATO_VALIDO).status_code == 201
    assert cliente.post("/api/contatos", json=CONTATO_VALIDO).status_code == 201
    assert cliente.post("/api/contatos", json=CONTATO_VALIDO).status_code == 429
    relogio["t"] += 59
    assert cliente.post("/api/contatos", json=CONTATO_VALIDO).status_code == 429
    relogio["t"] += 2
    assert cliente.post("/api/contatos", json=CONTATO_VALIDO).status_code == 201


def test_limitador_janela_deslizante_e_teto_de_enderecos():
    relogio = {"t": 0.0}
    limite = LimitePorIp(2, 10, agora=lambda: relogio["t"])
    assert limite.segundos_para_liberar("a") == 0
    limite.registrar("a")
    relogio["t"] = 4
    limite.registrar("a")
    assert limite.segundos_para_liberar("a") == 7  # a mais antiga (t=0) sai da janela em t=10
    relogio["t"] = 10
    assert limite.segundos_para_liberar("a") == 0

    from app.utils import limite_por_ip

    limite = LimitePorIp(1, 1000, agora=lambda: relogio["t"])
    antigo, limite_por_ip.MAXIMO_DE_ENDERECOS = limite_por_ip.MAXIMO_DE_ENDERECOS, 3
    try:
        for ip in ("a", "b", "c", "d"):
            limite.registrar(ip)
        assert len(limite._ocorrencias) == 3
        assert "a" not in limite._ocorrencias  # o mais antigo saiu; a memória não cresce sem limite
    finally:
        limite_por_ip.MAXIMO_DE_ENDERECOS = antigo


# =========================================================== contatos: leitura ==
def test_leitura_dos_contatos_sem_sessao_e_401(app):
    assert app.test_client().get("/api/contatos").status_code == 401
    assert app.test_client().post("/api/contatos/1/lido").status_code == 401


@pytest.mark.parametrize("papel", [ROLE_TECHNICAL, ROLE_OPERATOR])
def test_so_supervisor_le_e_marca_contatos(app, papel):
    app.test_client().post("/api/contatos", json=CONTATO_VALIDO)
    cliente = _cliente(app, papel)
    with app.app_context():
        contato_id = Contato.query.one().id
    for r in (cliente.get("/api/contatos"), cliente.post(f"/api/contatos/{contato_id}/lido")):
        assert r.status_code == 403
    with app.app_context():
        assert db.session.get(Contato, contato_id).lido is False


def test_supervisor_le_e_marca_contato_como_lido(app, sup):
    publico = app.test_client()
    publico.post("/api/contatos", json=CONTATO_VALIDO)
    publico.post("/api/contatos", json=CONTATO_VALIDO | {"nome": "Bruno"})

    corpo = sup.get("/api/contatos").get_json()
    assert [c["nome"] for c in corpo["items"]] == ["Bruno", "Ana Souza"]
    assert corpo["nao_lidos"] == 2
    assert corpo["items"][1]["email"] == "ana@exemplo.com.br"
    assert corpo["items"][1]["consentimento"] is True

    ana = corpo["items"][1]["id"]
    r = sup.post(f"/api/contatos/{ana}/lido")
    assert r.status_code == 200
    assert r.get_json()["contato"]["lido"] is True
    assert sup.get("/api/contatos").get_json()["nao_lidos"] == 1
    assert [c["nome"] for c in sup.get("/api/contatos?lido=false").get_json()["items"]] == ["Bruno"]
    assert sup.post("/api/contatos/9999/lido").status_code == 404


def test_feedback_e_contatos_nao_se_misturam(app, sup):
    _cliente(app, ROLE_TECHNICAL).post("/api/feedback", json={"texto": "só feedback"})
    app.test_client().post("/api/contatos", json=CONTATO_VALIDO)
    assert [i["texto"] for i in sup.get("/api/feedback").get_json()["items"]] == ["só feedback"]
    assert [i["nome"] for i in sup.get("/api/contatos").get_json()["items"]] == ["Ana Souza"]


# ================================================================== migração ==
def test_migracao_cria_as_duas_tabelas_com_as_colunas_do_modelo(tmp_path):
    """A migração nova encadeia em `f4a5b6c7d8e9` e cria exatamente o que o modelo declara."""
    from pathlib import Path

    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory
    from app.config import TestConfig
    from flask_migrate import downgrade, upgrade
    from sqlalchemy import create_engine, inspect

    raiz = Path(__file__).resolve().parent.parent
    banco = tmp_path / "migrado.db"

    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(raiz / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_revision("a5b6c7d8e9f0").down_revision == "f4a5b6c7d8e9"

    class ConfigMigracao(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{banco.as_posix()}"

    app = create_app(ConfigMigracao)
    with app.app_context():
        upgrade(directory=str(raiz / "migrations"), revision="a5b6c7d8e9f0")

    motor = create_engine(f"sqlite:///{banco.as_posix()}")
    inspetor = inspect(motor)
    for modelo in (Feedback, Contato):
        colunas = {c["name"]: c for c in inspetor.get_columns(modelo.__tablename__)}
        assert set(colunas) == {c.name for c in modelo.__table__.columns}, modelo.__tablename__
        for coluna in modelo.__table__.columns:
            assert colunas[coluna.name]["nullable"] == coluna.nullable, f"{modelo.__tablename__}.{coluna.name}"
    motor.dispose()

    with app.app_context():
        downgrade(directory=str(raiz / "migrations"), revision="f4a5b6c7d8e9")
    motor = create_engine(f"sqlite:///{banco.as_posix()}")
    assert {"feedback", "contatos"}.isdisjoint(inspect(motor).get_table_names())
    motor.dispose()
