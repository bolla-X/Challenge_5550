"""API documentada (M11): documento OpenAPI 3.1 e página /api/docs gerados do url_map."""

from __future__ import annotations

import json
import re

import pytest
from app import create_app
from app.api.busca import busca_bp
from app.api.openapi import openapi_bp
from app.config import AuthTestConfig
from app.extensions import db
from app.models import ROLE_OPERATOR, ROLE_SUPERVISOR, ROLE_TECHNICAL
from app.services.auth_service import AuthService
from app.services.openapi_doc import ACESSO_EXPLICITO, ROTAS, construir_documento, conta_minima
from app.utils.auth import login_required, require_role

SENHA = "senha-forte-de-teste"
METODOS = {"get", "put", "post", "delete", "patch"}


@pytest.fixture()
def app_auth(tmp_path):
    class Cfg(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'openapi.db'}"

    app = create_app(Cfg)
    for blueprint in (openapi_bp, busca_bp):  # quem liga em app/__init__.py é a sessão principal
        if blueprint.name not in app.blueprints:
            app.register_blueprint(blueprint)
    with app.app_context():
        db.create_all()
        AuthService().create_user(email="sup@x.local", name="Sup", password=SENHA, role="supervisor")
        AuthService().create_user(email="tec@x.local", name="Tec", password=SENHA, role="technical")
        AuthService().create_user(email="op@x.local", name="Op", password=SENHA, role="operator")
    return app


def _entrar(app, email):
    cliente = app.test_client()
    assert cliente.post("/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return cliente


@pytest.fixture()
def documento(app_auth):
    return construir_documento(app_auth)


def _operacoes(documento):
    return {
        (metodo.upper(), caminho): op
        for caminho, metodos in documento["paths"].items()
        for metodo, op in metodos.items()
        if metodo in METODOS
    }


# ------------------------------------------------------------------ papéis ---
@pytest.mark.parametrize("url", ["/api/openapi.json", "/api/docs"])
def test_sem_sessao_401_operador_403_tecnico_e_supervisor_200(app_auth, url):
    assert app_auth.test_client().get(url).status_code == 401
    operador = _entrar(app_auth, "op@x.local").get(url)
    assert operador.status_code == 403 and operador.get_json()["required_role"] == "technical"
    assert _entrar(app_auth, "tec@x.local").get(url).status_code == 200
    assert _entrar(app_auth, "sup@x.local").get(url).status_code == 200


# ----------------------------------------------------------------- documento ---
def test_documento_valido_no_essencial(app_auth):
    resposta = _entrar(app_auth, "tec@x.local").get("/api/openapi.json")
    assert resposta.mimetype == "application/json"
    doc = resposta.get_json()
    assert doc["openapi"].startswith("3.1.")
    assert doc["info"]["title"] and doc["info"]["version"]
    assert doc["paths"] and all(caminho.startswith("/") for caminho in doc["paths"])
    esquema = doc["components"]["securitySchemes"]["sessao"]
    assert (esquema["type"], esquema["in"], esquema["name"]) == ("apiKey", "cookie", "session")
    nomes_das_tags = {t["name"] for t in doc["tags"]}
    assert {"Alertas", "Incidentes", "Evacuação", "Regras", "Busca", "Custódia"} <= nomes_das_tags
    assert json.loads(json.dumps(doc)) == doc  # serializável sem perda


def test_toda_rota_api_registrada_aparece_com_os_metodos_certos(app_auth, documento):
    esperado = set()
    for regra in app_auth.url_map.iter_rules():
        if regra.rule.startswith("/api/"):
            caminho = re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", regra.rule)
            esperado |= {(m, caminho) for m in regra.methods - {"HEAD", "OPTIONS"}}
    publicado = {(m, c) for (m, c) in _operacoes(documento) if c.startswith("/api/")}
    assert esperado and publicado == esperado


def test_rota_que_nao_e_da_api_so_entra_se_for_de_integracao(documento):
    fora_do_prefixo = {(m, c) for (m, c) in _operacoes(documento) if not c.startswith("/api/")}
    assert fora_do_prefixo and fora_do_prefixo <= set(map(_chave_para_par, ROTAS))
    assert ("GET", "/alerts") in fora_do_prefixo and ("GET", "/dashboard") not in _operacoes(documento)


def _chave_para_par(chave):
    metodo, caminho = chave.split(" ", 1)
    return metodo, caminho


def test_toda_descricao_curada_aponta_para_uma_rota_que_existe(documento):
    existentes = set(_operacoes(documento))
    orfas = [chave for chave in ROTAS if _chave_para_par(chave) not in existentes]
    assert orfas == []  # rota renomeada ou removida: a descrição ficou para trás


def test_operacoes_tem_id_unico_resumo_e_tag(documento):
    ids = [op["operationId"] for op in _operacoes(documento).values()]
    assert len(ids) == len(set(ids))
    for op in _operacoes(documento).values():
        assert op["summary"] and op["tags"] and op["description"].startswith(op["summary"])
    curadas = [op for chave, op in _operacoes(documento).items() if op["x-integracao"]]
    assert len(curadas) == len(ROTAS)


def test_parametros_de_caminho_e_de_consulta(documento):
    clipe = documento["paths"]["/api/alerts/{alert_id}/clip"]["get"]["parameters"]
    assert clipe == [{"name": "alert_id", "in": "path", "required": True, "schema": {"type": "integer"}}]
    busca = {p["name"]: p for p in documento["paths"]["/api/busca/trilhas"]["get"]["parameters"]}
    assert busca["camera_id"]["required"] is True and busca["zona"]["required"] is False
    assert {"de", "ate", "zona", "permanencia_min_s", "epi_ausente", "vel_min", "vel_max", "limite"} <= set(busca)
    assert documento["paths"]["/api/regras"]["post"]["requestBody"]["content"]["application/json"]


# ------------------------------------------------------------------- acesso ---
@pytest.mark.parametrize(
    ("operacao", "conta"),
    [
        (("GET", "/alerts"), ROLE_OPERATOR),
        (("POST", "/alerts/{alert_id}/acknowledge"), ROLE_OPERATOR),
        (("GET", "/api/incidentes"), ROLE_OPERATOR),
        (("POST", "/api/incidentes/{incidente_id}/reconhecer"), ROLE_OPERATOR),
        (("GET", "/api/cameras/{camera_id}/status"), ROLE_OPERATOR),
        (("GET", "/api/integracao/estado"), ROLE_OPERATOR),
        (("GET", "/api/relatorio/turno"), ROLE_OPERATOR),  # login_required + exige_setor empilhados
        (("GET", "/api/permissoes"), ROLE_OPERATOR),
        (("POST", "/api/permissoes"), ROLE_TECHNICAL),
        (("GET", "/api/regras"), ROLE_TECHNICAL),
        (("DELETE", "/api/regras/{regra_id}"), ROLE_TECHNICAL),
        (("GET", "/api/evacuacao"), ROLE_TECHNICAL),
        (("POST", "/api/evacuacao/iniciar"), ROLE_SUPERVISOR),
        (("POST", "/api/evacuacao/encerrar"), ROLE_SUPERVISOR),
        (("GET", "/api/custodia"), ROLE_TECHNICAL),
        (("GET", "/api/busca/trilhas"), ROLE_TECHNICAL),
        (("GET", "/api/openapi.json"), ROLE_TECHNICAL),
        (("GET", "/api/docs"), ROLE_TECHNICAL),
        (("POST", "/api/auth/login"), None),
    ],
)
def test_conta_minima_vem_do_decorador_da_view(documento, operacao, conta):
    op = _operacoes(documento)[operacao]
    assert op["x-conta-minima"] == conta
    assert (op["security"] == []) is (conta is None)
    assert ("401" in op["responses"]) is (conta is not None)
    assert ("403" in op["responses"]) is (conta not in (None, ROLE_OPERATOR))


def test_a_rota_de_custodia_e_a_de_evacuacao_explicam_a_regra_que_o_decorador_nao_conta(documento):
    custodia = _operacoes(documento)[("GET", "/api/custodia/verificar")]
    assert custodia["x-conta-minima"] == ROLE_OPERATOR and "Técnico" in custodia["description"]
    iniciar = _operacoes(documento)[("POST", "/api/evacuacao/iniciar")]
    assert "token do palco" in iniciar["description"] and "Supervisor" in iniciar["description"]
    por_token = _operacoes(documento)[("POST", "/api/celular/{token}/quadro")]
    assert por_token["x-conta-minima"] is None and "token do celular" in por_token["description"]
    assert set(ACESSO_EXPLICITO) == {
        "GET /api/custodia/verificar",
        "POST /api/evacuacao/iniciar",
        "POST /api/evacuacao/encerrar",
        "GET /api/palco/estado",
        "POST /api/palco/ir",
        "POST /api/celular/{token}/quadro",
    }


def test_conta_minima_le_login_required_require_role_e_pilha():
    def publica():
        return None

    @login_required
    def com_login():
        return None

    @login_required(sempre=True)
    def com_login_sempre():
        return None

    @require_role(ROLE_SUPERVISOR)
    def de_supervisor():
        return None

    @login_required
    @require_role(ROLE_TECHNICAL)
    def pilha():
        return None

    def sem_relacao():
        return None

    assert conta_minima(publica) is None and conta_minima(sem_relacao) is None
    assert conta_minima(com_login) == ROLE_OPERATOR and conta_minima(com_login_sempre) == ROLE_OPERATOR
    assert conta_minima(de_supervisor) == ROLE_SUPERVISOR
    assert conta_minima(pilha) == ROLE_TECHNICAL


# --------------------------------------------------------------------- HTML ---
def test_docs_devolve_html_offline_com_operacoes_conta_e_curl(app_auth):
    resposta = _entrar(app_auth, "tec@x.local").get("/api/docs")
    pagina = resposta.get_data(as_text=True)
    assert resposta.mimetype == "text/html" and pagina.lstrip().lower().startswith("<!doctype html>")
    assert "/api/busca/trilhas" in pagina and "/api/alerts/{alert_id}/clip" in pagina
    assert "Técnico ou acima" in pagina and "Supervisor" in pagina and "Sem login" in pagina
    assert 'curl -b cookies.txt "http://localhost/api/alerts/1/clip"' in pagina
    assert "-X POST" in pagina and "Rotas de integração" in pagina
    assert pagina.index("Rotas de integração") < pagina.index("Demais rotas da API")


def test_docs_nao_depende_de_cdn_nem_de_script(app_auth):
    pagina = _entrar(app_auth, "sup@x.local").get("/api/docs").get_data(as_text=True)
    assert "<script" not in pagina.lower() and "<link" not in pagina.lower()
    externos = re.findall(r'(?:src|href)="(https?://[^"]+)"', pagina)
    assert externos == []


def test_docs_escapa_o_texto_que_vem_das_rotas(app_auth, monkeypatch):
    from app.services import openapi_doc

    monkeypatch.setitem(openapi_doc.ROTAS, "GET /api/busca/trilhas", ("Busca", "Texto <b>perigoso</b> & mais."))
    pagina = _entrar(app_auth, "tec@x.local").get("/api/docs").get_data(as_text=True)
    assert "<b>perigoso</b>" not in pagina and "&lt;b&gt;perigoso&lt;/b&gt; &amp; mais." in pagina


def test_documento_e_deterministico(app_auth):
    assert construir_documento(app_auth) == construir_documento(app_auth)
