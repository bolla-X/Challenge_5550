"""Fase 5, item 5 (MISSÃO 4): correções da auditoria de segurança.

Cada teste nasceu vermelho contra o código anterior (ver docs/NEXT2026/CHANGELOG.md, "Fase 5 item 5").
Os itens que exigem servidor de verdade (OPC UA, broker, webhook) estão em `tests/test_integracao_industrial.py`.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest
from app import create_app
from app.config import AuthTestConfig, Config, TestConfig
from app.extensions import db
from app.llm import redigir_segredos
from app.models import ROLE_OPERATOR, ROLE_SUPERVISOR, ROLE_TECHNICAL, Camera, Contato, User
from app.services.auth_service import AuthService
from app.services.regras_editor import RegraInvalida
from app.services.regras_editor import validar as validar_regra

RAIZ = Path(__file__).resolve().parent.parent
SENHA = "senha-forte-de-teste"
CONTATO_VALIDO = {
    "nome": "Ana Souza",
    "empresa": "Metalúrgica Exemplo",
    "email": "ana@exemplo.com.br",
    "mensagem": "Quero ver o sistema rodando na nossa planta.",
    "consentimento": True,
}
TOKEN_DO_CELULAR = "AbCdEfGhIjKlMnOpQrStUvWx"  # 24 caracteres, como `secrets.token_urlsafe(18)`


@pytest.fixture()
def app_auth(tmp_path):
    class Config_(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'seguranca.db'}"
        CONTATOS_POR_IP_MAX = 1000

    app = create_app(Config_)
    with app.app_context():
        db.create_all()
        db.session.add_all([Camera(name="Pátio", source="0"), Camera(name="Doca", source="1")])
        db.session.commit()
        for papel in (ROLE_SUPERVISOR, ROLE_TECHNICAL):
            AuthService().create_user(email=f"{papel}@fabrica.com", name=papel.title(), password=SENHA, role=papel)
        AuthService().create_user(email="operator@fabrica.com", name="Operador", password=SENHA, role=ROLE_OPERATOR, camera_id=1)
        db.session.remove()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _entrar(app, papel: str):
    cliente = app.test_client()
    r = cliente.post("/api/auth/login", json={"email": f"{papel}@fabrica.com", "password": SENHA})
    assert r.status_code == 200, r.get_json()
    return cliente


# ======================================================== 2. token do celular ==
def test_camera_celular_nao_expoe_o_token_no_to_dict(app):
    camera = Camera(name="Celular", source_type="Celular", source=f"celular://{TOKEN_DO_CELULAR}")
    db.session.add(camera)
    db.session.commit()
    assert camera.to_dict()["source"] == "celular://***"


def test_api_de_cameras_nao_devolve_o_token_do_celular(client, app):
    camera = Camera(name="Celular", source_type="Celular", source=f"celular://{TOKEN_DO_CELULAR}")
    db.session.add(camera)
    db.session.commit()
    for caminho in ("/api/cameras", f"/api/cameras/{camera.id}"):
        resposta = client.get(caminho)
        assert resposta.status_code == 200
        assert TOKEN_DO_CELULAR not in resposta.get_data(as_text=True)


def test_atualizar_camera_celular_nao_depende_do_source_do_cliente(client, app):
    camera = Camera(name="Celular", source_type="Celular", source=f"celular://{TOKEN_DO_CELULAR}")
    db.session.add(camera)
    db.session.commit()
    camera_id = camera.id
    for source in ("celular://***", "celular://token-escolhido-pelo-cliente", "rtsp://outra/coisa"):
        r = client.patch(f"/api/cameras/{camera_id}", json={"name": "Celular 2", "source": source})
        assert r.status_code == 200, r.get_json()
        db.session.expire_all()
        assert db.session.get(Camera, camera_id).source == f"celular://{TOKEN_DO_CELULAR}"


# ====================================================== 3. CORS do Socket.IO ==
POLLING = "/socket.io/?EIO=4&transport=polling"


def _handshake(app, origem: str | None):
    cabecalhos = {"Origin": origem} if origem else {}
    return app.test_client().get(POLLING, headers=cabecalhos)


def test_env_origens_padrao_e_mesma_origem(monkeypatch):
    from app.config import env_origens

    monkeypatch.delenv("ORIGENS_DE_TESTE", raising=False)
    assert env_origens("ORIGENS_DE_TESTE") is None
    monkeypatch.setenv("ORIGENS_DE_TESTE", "   ")
    assert env_origens("ORIGENS_DE_TESTE") is None


def test_env_origens_aceita_lista_separada_por_virgula_e_asterisco_explicito(monkeypatch):
    from app.config import env_origens

    monkeypatch.setenv("ORIGENS_DE_TESTE", "http://localhost:5173, https://painel.exemplo.com ,,")
    assert env_origens("ORIGENS_DE_TESTE") == ["http://localhost:5173", "https://painel.exemplo.com"]
    monkeypatch.setenv("ORIGENS_DE_TESTE", "*")
    assert env_origens("ORIGENS_DE_TESTE") == "*"


def test_socketio_sem_configuracao_so_aceita_a_mesma_origem(monkeypatch):
    # Sem a chave na configuração, o `create_app` não pode cair em "*".
    monkeypatch.delattr(Config, "SOCKETIO_CORS_ALLOWED_ORIGINS")
    app = create_app(TestConfig)
    assert _handshake(app, "http://localhost").status_code == 200
    assert _handshake(app, None).status_code == 200
    assert _handshake(app, "http://evil.example").status_code == 400


def test_socketio_padrao_do_config_e_mesma_origem():
    from app.config import env_origens

    class Cfg(TestConfig):
        SOCKETIO_CORS_ALLOWED_ORIGINS = env_origens("VARIAVEL_QUE_NAO_EXISTE_XYZ")

    app = create_app(Cfg)
    assert _handshake(app, "http://evil.example").status_code == 400


def test_socketio_com_lista_aceita_so_as_origens_da_lista():
    class Cfg(TestConfig):
        SOCKETIO_CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]

    app = create_app(Cfg)
    assert _handshake(app, "http://localhost:5173").status_code == 200
    assert _handshake(app, "http://evil.example").status_code == 400


def test_socketio_asterisco_so_quando_configurado_explicitamente():
    class Cfg(TestConfig):
        SOCKETIO_CORS_ALLOWED_ORIGINS = "*"

    assert _handshake(create_app(Cfg), "http://qualquer.example").status_code == 200


# ============================================================ 4. corpo grande ==
def test_corpo_maior_que_o_limite_e_413(client, app):
    from app.vision.fonte_celular import MAX_BYTES_QUADRO

    assert app.config["MAX_CONTENT_LENGTH"] >= MAX_BYTES_QUADRO  # o quadro do celular cabe
    r = client.post("/api/contatos", data=b"x" * (7 * 1024 * 1024), content_type="application/json")
    assert r.status_code == 413


def test_corpo_pequeno_continua_passando(client):
    r = client.post("/api/contatos", json=CONTATO_VALIDO | {"consentimento": False})
    assert r.status_code == 400  # chegou na validação


# ================================================================ 5. CSRF ==
@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_mutacao_com_sec_fetch_site_de_fora_e_403(client, site):
    r = client.post("/api/auth/logout", headers={"Sec-Fetch-Site": site})
    assert r.status_code == 403
    assert "error" in r.get_json() and "origem" in r.get_json()["error"].lower()


@pytest.mark.parametrize("metodo", ["post", "put", "patch", "delete"])
def test_todo_metodo_de_escrita_e_barrado(client, metodo):
    r = getattr(client, metodo)("/api/auth/logout", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


@pytest.mark.parametrize("site", ["same-origin", "none"])
def test_mutacao_da_mesma_origem_passa(client, site):
    assert client.post("/api/auth/logout", headers={"Sec-Fetch-Site": site}).status_code == 200


def test_mutacao_sem_cabecalhos_passa_curl_e_test_client(client):
    assert client.post("/api/auth/logout").status_code == 200


def test_leitura_de_fora_nao_e_barrada(client):
    assert client.get("/api/auth/me", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


def test_sem_sec_fetch_site_compara_o_origin_com_o_host(client):
    assert client.post("/api/auth/logout", headers={"Origin": "http://evil"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"Origin": "null"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"Origin": "http://localhost"}).status_code == 200


def test_sec_fetch_site_tem_precedencia_sobre_o_origin(client):
    r = client.post("/api/auth/logout", headers={"Sec-Fetch-Site": "cross-site", "Origin": "http://localhost"})
    assert r.status_code == 403
    r = client.post("/api/auth/logout", headers={"Sec-Fetch-Site": "same-origin", "Origin": "http://localhost:5173"})
    assert r.status_code == 200  # o navegador já disse que é a mesma origem (proxy do Vite em dev)


# ============================================================ 6. host da demo ==
def _ambiente_da_demo(monkeypatch, tmp_path, **ambiente):
    import app.demo_ambiente as amb

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    for _, _, arquivo in amb.GRAVACOES:
        (fixtures / arquivo).write_bytes(b"")
    pasta = tmp_path / "demo"
    monkeypatch.setattr(amb, "FIXTURES", fixtures)
    monkeypatch.setattr(amb, "PASTA", pasta)
    monkeypatch.setattr(amb, "BANCO", pasta / "demo.db")
    monkeypatch.setattr(amb, "TOKEN", pasta / "token")
    copia = {k: v for k, v in os.environ.items() if k != "HOST"} | ambiente
    monkeypatch.setattr(os, "environ", copia)  # `preparar_ambiente` escreve aqui: não pode vazar para os outros testes
    amb.preparar_ambiente()
    return copia


def test_demo_escuta_so_no_loopback_por_padrao(monkeypatch, tmp_path):
    assert _ambiente_da_demo(monkeypatch, tmp_path)["HOST"] == "127.0.0.1"


def test_demo_respeita_o_host_ja_definido(monkeypatch, tmp_path):
    assert _ambiente_da_demo(monkeypatch, tmp_path, HOST="0.0.0.0")["HOST"] == "0.0.0.0"


# ===================================================== 8. excluir contato (LGPD) ==
def _novo_contato(app) -> int:
    assert app.test_client().post("/api/contatos", json=CONTATO_VALIDO).status_code == 201
    with app.app_context():
        return Contato.query.order_by(Contato.id.desc()).first().id


def test_excluir_contato_sem_sessao_e_401(app_auth):
    contato_id = _novo_contato(app_auth)
    assert app_auth.test_client().delete(f"/api/contatos/{contato_id}").status_code == 401


@pytest.mark.parametrize("papel", [ROLE_TECHNICAL, ROLE_OPERATOR])
def test_so_supervisor_exclui_contato(app_auth, papel):
    contato_id = _novo_contato(app_auth)
    assert _entrar(app_auth, papel).delete(f"/api/contatos/{contato_id}").status_code == 403
    with app_auth.app_context():
        assert db.session.get(Contato, contato_id) is not None


def test_supervisor_exclui_contato_de_vez(app_auth):
    contato_id = _novo_contato(app_auth)
    outro = _novo_contato(app_auth)
    sup = _entrar(app_auth, ROLE_SUPERVISOR)
    r = sup.delete(f"/api/contatos/{contato_id}")
    assert r.status_code == 200
    assert r.get_json() == {"deleted": True, "id": contato_id}
    with app_auth.app_context():
        assert db.session.get(Contato, contato_id) is None
        assert db.session.get(Contato, outro) is not None  # só o pedido some
    assert [c["id"] for c in sup.get("/api/contatos").get_json()["items"]] == [outro]


def test_excluir_contato_inexistente_e_404(app_auth):
    sup = _entrar(app_auth, ROLE_SUPERVISOR)
    assert sup.delete("/api/contatos/9999").status_code == 404
    contato_id = _novo_contato(app_auth)
    assert sup.delete(f"/api/contatos/{contato_id}").status_code == 200
    assert sup.delete(f"/api/contatos/{contato_id}").status_code == 404  # idempotência: segunda vez não existe mais


# ============================================== 10. token no log de acesso ==
def _registro_do_werkzeug(requisicao: str) -> logging.LogRecord:
    return logging.LogRecord("werkzeug", logging.INFO, __file__, 0, '"%s" %s %s', (requisicao, 200, "-"), None)


@pytest.mark.parametrize(
    "requisicao,esperada",
    [
        ("GET /cam?t=AbCdEf-_123456 HTTP/1.1", "GET /cam?t=*** HTTP/1.1"),
        ("GET /palco/controle?x=1&t=segredo123 HTTP/1.1", "GET /palco/controle?x=1&t=*** HTTP/1.1"),
        ("POST /api/celular/AbCdEf-_123456/quadro HTTP/1.1", "POST /api/celular/***/quadro HTTP/1.1"),
        ("GET /api/cameras HTTP/1.1", "GET /api/cameras HTTP/1.1"),
        ("GET /api/x?tt=1&dt=2 HTTP/1.1", "GET /api/x?tt=1&dt=2 HTTP/1.1"),  # só o parâmetro `t`
    ],
)
def test_filtro_do_log_de_acesso_esconde_tokens(requisicao, esperada):
    from app.utils.logging_config import FiltroDeTokensNoAcesso

    registro = _registro_do_werkzeug(requisicao)
    assert FiltroDeTokensNoAcesso().filter(registro) is True  # nunca descarta a linha
    assert registro.getMessage() == f'"{esperada}" 200 -'


def test_configure_logging_instala_o_filtro_no_werkzeug_uma_vez():
    from app.utils.logging_config import FiltroDeTokensNoAcesso, configure_logging

    configure_logging()
    configure_logging()
    filtros = [f for f in logging.getLogger("werkzeug").filters if isinstance(f, FiltroDeTokensNoAcesso)]
    assert len(filtros) == 1


# ============================================ 11. Operador só vê o estado do canal ==
def test_operador_ve_so_o_estado_de_cada_integracao(app_auth):
    corpo = _entrar(app_auth, ROLE_OPERATOR).get("/api/integracao/estado").get_json()
    assert set(corpo["integracoes"]) == {"opcua", "mqtt", "broker", "webhook"}
    for canal in corpo["integracoes"].values():
        assert set(canal) == {"estado"}


@pytest.mark.parametrize("papel", [ROLE_TECHNICAL, ROLE_SUPERVISOR])
def test_tecnico_e_supervisor_continuam_vendo_endereco_e_motivo(app_auth, papel):
    corpo = _entrar(app_auth, papel).get("/api/integracao/estado").get_json()
    assert {"ativo", "estado", "endpoint", "erro"} <= set(corpo["integracoes"]["opcua"])


# ===================================== 12. mudar papel/câmera revoga as sessões ==
def _id_do_operador(app) -> int:
    with app.app_context():
        return User.query.filter_by(email="operator@fabrica.com").one().id


def _logado(cliente) -> bool:
    return cliente.get("/api/auth/me").get_json()["user"] is not None


def test_mudar_o_papel_derruba_as_sessoes_da_conta(app_auth):
    operador = _entrar(app_auth, ROLE_OPERATOR)
    assert _logado(operador)
    r = _entrar(app_auth, ROLE_SUPERVISOR).patch(f"/api/users/{_id_do_operador(app_auth)}", json={"role": ROLE_TECHNICAL})
    assert r.status_code == 200
    assert not _logado(operador)


def test_mudar_a_camera_derruba_as_sessoes_da_conta(app_auth):
    operador = _entrar(app_auth, ROLE_OPERATOR)
    r = _entrar(app_auth, ROLE_SUPERVISOR).patch(f"/api/users/{_id_do_operador(app_auth)}", json={"camera_id": 2})
    assert r.status_code == 200
    assert not _logado(operador)


def test_alteracao_sem_mudar_papel_nem_camera_nao_derruba_a_sessao(app_auth):
    operador = _entrar(app_auth, ROLE_OPERATOR)
    sup = _entrar(app_auth, ROLE_SUPERVISOR)
    uid = _id_do_operador(app_auth)
    assert sup.patch(f"/api/users/{uid}", json={"name": "Outro Nome"}).status_code == 200
    assert sup.patch(f"/api/users/{uid}", json={"role": ROLE_OPERATOR, "camera_id": 1}).status_code == 200  # mesmos valores
    assert _logado(operador)


@pytest.mark.parametrize("camera_id", [9999, "1", True, [1]])
def test_camera_que_nao_existe_e_400_e_nao_muda_nada(app_auth, camera_id):
    operador = _entrar(app_auth, ROLE_OPERATOR)
    r = _entrar(app_auth, ROLE_SUPERVISOR).patch(f"/api/users/{_id_do_operador(app_auth)}", json={"camera_id": camera_id})
    assert r.status_code == 400
    assert "câmera" in r.get_json()["error"].lower()
    with app_auth.app_context():
        assert db.session.get(User, _id_do_operador(app_auth)).camera_id == 1
    assert _logado(operador)


# ============================================================ 13. service worker ==
def test_service_worker_nao_guarda_o_relatorio_como_casca():
    texto = (RAIZ / "frontend" / "public" / "sw.js").read_text(encoding="utf-8")
    linha = next(trecho for trecho in texto.splitlines() if trecho.startswith("const SEM_CASCA"))
    assert "relatorio" in linha


# ================================================== 14. e-mail e `mailto:` ==
@pytest.mark.parametrize(
    "email",
    [
        "ana@exemplo.com.br?bcc=outro",
        "a&b@exemplo.com",
        "a#b@exemplo.com",
        "a%40b@exemplo.com",
        "a/b@exemplo.com",
        "ana@exemplo.com/x",
        "ana@exemplo.com#x",
    ],
)
def test_email_com_caracteres_de_mailto_e_400(client, email):
    r = client.post("/api/contatos", json=CONTATO_VALIDO | {"email": email})
    assert r.status_code == 400
    assert r.get_json()["campo"] == "email"


def test_email_comum_continua_valido(app_auth):
    r = app_auth.test_client().post("/api/contatos", json=CONTATO_VALIDO | {"email": "ana.souza+planta@exemplo-fabrica.com.br"})
    assert r.status_code == 201


# ===================================================== 15. polígonos limitados ==
def _poligono(n: int) -> list[list[float]]:
    return [[0.1 + 0.8 * (i % 2), 0.1 + 0.8 * ((i // 2) % 2)] for i in range(n)]


def test_area_vigia_com_mais_de_64_pontos_e_recusada():
    from app.services.permissoes import PermissaoInvalida, normalizar_poligono

    assert len(normalizar_poligono(_poligono(64), "area_vigia")) == 64
    with pytest.raises(PermissaoInvalida) as erro:
        normalizar_poligono(_poligono(65), "area_vigia")
    assert erro.value.code == "campo_invalido"
    assert "64" in str(erro.value)


def test_area_de_risco_do_worker_recusa_mais_de_64_pontos():
    from app.services.camera_worker import CameraWorker

    assert len(CameraWorker._normalizar_poligono(_poligono(64))) == 64
    with pytest.raises(ValueError, match="64"):
        CameraWorker._normalizar_poligono(_poligono(65))


# ===================================================== 16. id da regra com "\n" ==
@pytest.mark.parametrize("id_", ["abc\n", "abc\n\n", "\nabc"])
def test_id_de_regra_nao_aceita_quebra_de_linha(id_):
    with pytest.raises(RegraInvalida) as erro:
        validar_regra({"id": id_})
    assert str(erro.value).startswith("id:")


# ================================================ 17. redação de segredos ==
@pytest.mark.parametrize(
    "bruto,esperado",
    [
        ("rtsp://usuario:p@ss@192.168.0.10/stream", "rtsp://***@192.168.0.10/stream"),
        ("rtsp://usuario:p@ss@w@rd@host:554/c", "rtsp://***@host:554/c"),
        ("rtsp://usuario:senha@host/stream", "rtsp://***@host/stream"),
        ("rtsp://host/stream?user=admin&password=123&canal=1", "rtsp://host/stream?user=***&password=***&canal=1"),
        ("http://h/x?token=abc&key=k&secret=s&auth=a&pwd=p&pass=q", "http://h/x?token=***&key=***&secret=***&auth=***&pwd=***&pass=***"),
        ("http://h/x?TOKEN=abc", "http://h/x?TOKEN=***"),
        ("rtsp://host/x?canal=1&subtype=0", "rtsp://host/x?canal=1&subtype=0"),
        ("rtsp://host/x?mail=a@b.com", "rtsp://host/x?mail=a@b.com"),
        (f"celular://{TOKEN_DO_CELULAR}", "celular://***"),
    ],
)
def test_redigir_segredos_cobre_query_senha_com_arroba_e_celular(bruto, esperado):
    assert redigir_segredos(bruto) == esperado


# ======================================================= 18. cabeçalhos ==
@pytest.mark.parametrize("caminho", ["/api/auth/me", "/rota-que-nao-existe", "/cam"])
def test_cabecalhos_de_seguranca_em_toda_resposta(client, caminho):
    r = client.get(caminho)
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert r.headers["Referrer-Policy"] == "same-origin"
