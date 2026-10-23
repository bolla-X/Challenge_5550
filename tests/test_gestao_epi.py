"""Gestão de EPIs (ES Sprint 4): API, papéis, regras de negócio e exportação CSV.

Contrato: docs/specs/es-sprint4-contrato-gestao.md. Roda com `AUTH_REQUIRED=True` e banco em arquivo. O relógio é
injetado: `hoje()` do serviço é trocado por uma data fixa, então situação de CA e de entrega não dependem do dia em que
a suíte roda.

Papéis: Técnico ou mais lê tudo, registra entrega, devolução e ocorrência e exporta; Supervisor cadastra e edita
colaborador e item do catálogo; Operador, 403 em tudo; sem sessão, 401. (A grade completa está em
tests/test_matriz_de_permissoes.py; aqui ficam as regras.)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from app import create_app
from app.config import AuthTestConfig
from app.extensions import db
from app.models import (
    CATEGORIAS_DE_EPI,
    ROLE_OPERATOR,
    ROLE_SUPERVISOR,
    ROLE_TECHNICAL,
    Alert,
    Colaborador,
    EntregaEpi,
    EpiCatalogo,
    EventLog,
    Ocorrencia,
    utc_now,
)
from app.services import gestao_epi as servico
from app.services.auth_service import AuthService
from app.vision.person_compliance_matcher import PPE_KEYS

SENHA = "senha-forte-de-teste"
HOJE = date(2026, 10, 23)


def _dia(dias: int) -> str:
    return (HOJE + timedelta(days=dias)).isoformat()


@pytest.fixture(autouse=True)
def _relogio_fixo(monkeypatch):
    monkeypatch.setattr(servico, "hoje", lambda: HOJE)


@pytest.fixture()
def app(tmp_path):
    class Config(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'gestao-test.db'}"

    app = create_app(Config)
    with app.app_context():
        db.create_all()
        for papel in (ROLE_SUPERVISOR, ROLE_TECHNICAL):
            AuthService().create_user(email=f"{papel}@fabrica.com", name=papel.title(), password=SENHA, role=papel)
        AuthService().create_user(email="operator@fabrica.com", name="Operador", password=SENHA, role=ROLE_OPERATOR, camera_id=1)
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


@pytest.fixture()
def tec(app):
    return _cliente(app, ROLE_TECHNICAL)


@pytest.fixture()
def op(app):
    return _cliente(app, ROLE_OPERATOR)


# ---------------------------------------------------------------- ajudantes ---
def _novo_colaborador(sup, matricula="T-001", nome="Ana Teste", setor="Obra", ativo=True) -> dict:
    r = sup.post("/api/gestao/colaboradores", json={
        "matricula": matricula, "nome": nome, "setor": setor, "funcao": "Pedreiro", "admissao": "2025-01-10",
    })
    assert r.status_code == 201, r.get_json()
    colaborador = r.get_json()["colaborador"]
    if not ativo:
        colaborador = sup.put(f"/api/gestao/colaboradores/{colaborador['id']}", json={"ativo": False}).get_json()["colaborador"]
    return colaborador


def _novo_epi(sup, ca="900001", validade_em=200, vida_util=90, nome="Luva de teste", categoria="gloves") -> dict:
    r = sup.post("/api/gestao/epis", json={
        "nome": nome, "categoria": categoria, "ca": ca, "validade_ca": _dia(validade_em), "fabricante": "Fabricante Fictício A",
        "vida_util_dias": vida_util,
    })
    assert r.status_code == 201, r.get_json()
    return r.get_json()["epi"]


def _entregar(cliente, colaborador, epi, **extra):
    corpo = {"colaborador_id": colaborador["id"], "epi_id": epi["id"], "quantidade": 1, "entregue_em": _dia(-10),
             "motivo": "admissao", **extra}
    return cliente.post("/api/gestao/entregas", json=corpo)


# -------------------------------------------------------------------- papéis ---
def test_categorias_do_catalogo_sao_as_chaves_de_epi_da_visao_mais_outro():
    assert CATEGORIAS_DE_EPI == (*PPE_KEYS, "outro")


@pytest.mark.parametrize("url", [
    "/api/gestao/resumo", "/api/gestao/colaboradores", "/api/gestao/epis", "/api/gestao/entregas", "/api/gestao/ocorrencias",
    "/api/gestao/exportar/epis.csv",
])
def test_leitura_sem_sessao_401_operador_403_tecnico_ok(app, op, tec, url):
    assert app.test_client().get(url).status_code == 401
    assert op.get(url).status_code == 403
    assert tec.get(url).status_code == 200


def test_tecnico_nao_cadastra_colaborador_nem_item_mas_registra_entrega_e_ocorrencia(sup, tec):
    corpo = {"matricula": "X", "nome": "X", "setor": "Obra", "funcao": "X", "admissao": "2025-01-01"}
    assert tec.post("/api/gestao/colaboradores", json=corpo).status_code == 403
    assert tec.put("/api/gestao/colaboradores/1", json=corpo).status_code == 403
    assert tec.post("/api/gestao/epis", json={}).status_code == 403
    assert tec.put("/api/gestao/epis/1", json={}).status_code == 403
    colaborador, epi = _novo_colaborador(sup), _novo_epi(sup)
    assert _entregar(tec, colaborador, epi).status_code == 201
    ocorrencia = {"tipo": "quase_acidente", "gravidade": "baixa", "setor": "Obra", "descricao": "Teste."}
    assert tec.post("/api/gestao/ocorrencias", json=ocorrencia).status_code == 201


def test_operador_nao_escreve_em_lugar_nenhum(op):
    for metodo, url in (("post", "/api/gestao/entregas"), ("post", "/api/gestao/ocorrencias"), ("post", "/api/gestao/colaboradores"),
                        ("post", "/api/gestao/entregas/1/devolucao"), ("put", "/api/gestao/ocorrencias/1")):
        assert getattr(op, metodo)(url, json={}).status_code == 403, url


# ------------------------------------------------------------ colaboradores ---
def test_cria_colaborador_e_recusa_matricula_repetida(sup):
    primeiro = _novo_colaborador(sup)
    assert primeiro["ativo"] is True and primeiro["ficticio"] is False and primeiro["admissao"] == "2025-01-10"
    assert primeiro["entregas_vigentes"] == 0 and primeiro["pendencias"] == 0
    repetida = sup.post("/api/gestao/colaboradores", json={
        "matricula": "T-001", "nome": "Outra", "setor": "Obra", "funcao": "X", "admissao": "2025-01-10"})
    assert repetida.status_code == 409 and repetida.get_json()["code"] == "matricula_duplicada"


@pytest.mark.parametrize(("campo", "valor"), [("nome", ""), ("matricula", None), ("admissao", "10/01/2025"), ("setor", 7)])
def test_colaborador_com_campo_invalido_da_400_com_mensagem_em_portugues(sup, campo, valor):
    corpo = {"matricula": "T-9", "nome": "Ana", "setor": "Obra", "funcao": "X", "admissao": "2025-01-10", campo: valor}
    r = sup.post("/api/gestao/colaboradores", json=corpo)
    assert r.status_code == 400
    assert r.get_json()["code"] == "campo_invalido" and r.get_json()["error"].endswith(".")


def test_edicao_e_parcial_e_matricula_repetida_na_edicao_da_409(sup):
    ana = _novo_colaborador(sup, "T-001", "Ana")
    beto = _novo_colaborador(sup, "T-002", "Beto")
    editado = sup.put(f"/api/gestao/colaboradores/{ana['id']}", json={"setor": "Usinagem"}).get_json()["colaborador"]
    assert editado["setor"] == "Usinagem" and editado["nome"] == "Ana" and editado["matricula"] == "T-001"
    mesma = sup.put(f"/api/gestao/colaboradores/{ana['id']}", json={"matricula": "T-001"})
    assert mesma.status_code == 200  # a própria matrícula não conta como repetida
    repetida = sup.put(f"/api/gestao/colaboradores/{beto['id']}", json={"matricula": "T-001"})
    assert repetida.status_code == 409 and repetida.get_json()["code"] == "matricula_duplicada"
    assert sup.put("/api/gestao/colaboradores/9999", json={}).status_code == 404


def test_lista_de_colaboradores_filtra_por_busca_setor_e_ativo_e_devolve_os_setores(sup, tec):
    _novo_colaborador(sup, "A-1", "Ana Souza", "Obra")
    _novo_colaborador(sup, "B-2", "Bruno Lima", "Usinagem")
    _novo_colaborador(sup, "C-3", "Carla Souza", "Obra", ativo=False)
    tudo = tec.get("/api/gestao/colaboradores").get_json()
    assert tudo["count"] == 3 and tudo["setores"] == ["Obra", "Usinagem"]
    assert [c["nome"] for c in tudo["items"]] == ["Ana Souza", "Bruno Lima", "Carla Souza"]
    assert [c["matricula"] for c in tec.get("/api/gestao/colaboradores?busca=souza").get_json()["items"]] == ["A-1", "C-3"]
    assert [c["matricula"] for c in tec.get("/api/gestao/colaboradores?busca=b-2").get_json()["items"]] == ["B-2"]
    assert [c["matricula"] for c in tec.get("/api/gestao/colaboradores?setor=Usinagem").get_json()["items"]] == ["B-2"]
    assert [c["matricula"] for c in tec.get("/api/gestao/colaboradores?ativo=true").get_json()["items"]] == ["A-1", "B-2"]
    assert [c["matricula"] for c in tec.get("/api/gestao/colaboradores?ativo=false").get_json()["items"]] == ["C-3"]
    assert tec.get("/api/gestao/colaboradores?ativo=talvez").status_code == 400


# ------------------------------------------------------------------ catálogo ---
@pytest.mark.parametrize(("validade_em", "situacao", "dias"), [
    (-1, "vencido", -1), (0, "a_vencer", 0), (30, "a_vencer", 30), (31, "valido", 31), (400, "valido", 400),
])
def test_situacao_do_ca_nos_limites(sup, validade_em, situacao, dias):
    epi = _novo_epi(sup, validade_em=validade_em)
    assert epi["situacao_ca"] == situacao and epi["dias_para_vencer"] == dias and epi["entregas_vigentes"] == 0


def test_catalogo_recusa_ca_repetido_e_valida_categoria_e_vida_util(sup):
    _novo_epi(sup, ca="900001")
    corpo = {"nome": "Outro", "categoria": "gloves", "ca": "900001", "validade_ca": _dia(100), "fabricante": "F",
             "vida_util_dias": 30}
    repetido = sup.post("/api/gestao/epis", json=corpo)
    assert repetido.status_code == 409 and repetido.get_json()["code"] == "ca_duplicado"
    assert sup.post("/api/gestao/epis", json={**corpo, "ca": "900002", "categoria": "chapeu"}).status_code == 400
    assert sup.post("/api/gestao/epis", json={**corpo, "ca": "900002", "vida_util_dias": 0}).status_code == 400
    assert sup.post("/api/gestao/epis", json={**corpo, "ca": "900002", "vida_util_dias": "90"}).status_code == 400
    assert sup.post("/api/gestao/epis", json={**corpo, "ca": "900002", "validade_ca": "amanhã"}).status_code == 400


def test_lista_do_catalogo_filtra_por_categoria_e_situacao_e_conta_entregas_vigentes(sup, tec):
    capacete = _novo_epi(sup, "900010", 400, 1095, "Capacete", "helmet")
    luva = _novo_epi(sup, "900011", -5, 90, "Luva vencida", "gloves")
    _novo_epi(sup, "900012", 10, 30, "Respirador", "mask")
    ana = _novo_colaborador(sup)
    assert _entregar(tec, ana, capacete).status_code == 201
    itens = tec.get("/api/gestao/epis").get_json()["items"]
    assert {i["ca"]: i["entregas_vigentes"] for i in itens} == {"900010": 1, "900011": 0, "900012": 0}
    assert [i["ca"] for i in tec.get("/api/gestao/epis?situacao=vencido").get_json()["items"]] == [luva["ca"]]
    assert [i["ca"] for i in tec.get("/api/gestao/epis?situacao=a_vencer").get_json()["items"]] == ["900012"]
    assert [i["ca"] for i in tec.get("/api/gestao/epis?categoria=helmet").get_json()["items"]] == ["900010"]
    assert tec.get("/api/gestao/epis?situacao=quase").status_code == 400
    assert tec.get("/api/gestao/epis?categoria=chapeu").status_code == 400


def test_renovar_o_ca_pelo_catalogo_libera_a_entrega(sup, tec):
    ana, luva = _novo_colaborador(sup), _novo_epi(sup, validade_em=-3)
    assert _entregar(tec, ana, luva).status_code == 409
    renovado = sup.put(f"/api/gestao/epis/{luva['id']}", json={"validade_ca": _dia(365)}).get_json()["epi"]
    assert renovado["situacao_ca"] == "valido" and renovado["nome"] == luva["nome"]
    assert _entregar(tec, ana, luva).status_code == 201


# ------------------------------------------------------------------ entregas ---
def test_entrega_calcula_a_troca_prevista_e_a_situacao(sup, tec):
    ana, luva = _novo_colaborador(sup), _novo_epi(sup, vida_util=90)
    r = _entregar(tec, ana, luva, quantidade=2, entregue_em=_dia(-10), observacao="  par novo ")
    assert r.status_code == 201
    entrega = r.get_json()["entrega"]
    assert entrega["troca_prevista_em"] == _dia(80) and entrega["situacao"] == "vigente" and entrega["devolvido_em"] is None
    assert entrega["codigo"].startswith("ENT-") and entrega["registrado_por"] == "technical@fabrica.com"
    assert entrega["observacao"] == "par novo" and entrega["quantidade"] == 2 and entrega["ficticio"] is False
    assert entrega["colaborador"] == {"id": ana["id"], "matricula": "T-001", "nome": "Ana Teste", "setor": "Obra"}
    assert entrega["epi"] == {"id": luva["id"], "nome": "Luva de teste", "categoria": "gloves", "ca": "900001",
                              "situacao_ca": "valido"}


def test_entrega_sem_data_usa_hoje(sup, tec):
    ana, luva = _novo_colaborador(sup), _novo_epi(sup, vida_util=30)
    r = tec.post("/api/gestao/entregas", json={"colaborador_id": ana["id"], "epi_id": luva["id"], "quantidade": 1, "motivo": "admissao"})
    assert r.status_code == 201 and r.get_json()["entrega"]["entregue_em"] == HOJE.isoformat()


def test_ca_vencido_bloqueia_a_entrega_com_409_e_texto_de_politica_da_empresa(sup, tec):
    ana, luva = _novo_colaborador(sup), _novo_epi(sup, validade_em=-1)
    r = _entregar(tec, ana, luva)
    assert r.status_code == 409 and r.get_json()["code"] == "ca_vencido"
    mensagem = r.get_json()["error"]
    assert "política da empresa" in mensagem and "22/10/2026" in mensagem and "NR-6" not in mensagem
    with sup.application.app_context():
        assert EntregaEpi.query.count() == 0  # nada foi gravado


def test_ca_que_vence_hoje_ainda_pode_ser_entregue(sup, tec):
    ana, luva = _novo_colaborador(sup), _novo_epi(sup, validade_em=0)
    assert _entregar(tec, ana, luva).status_code == 201


def test_colaborador_desligado_continua_legivel_mas_nao_recebe_entrega(sup, tec):
    """Ler não é usar: o histórico fica, a trava de escrita é do servidor."""
    ana, luva = _novo_colaborador(sup), _novo_epi(sup)
    assert _entregar(tec, ana, luva).status_code == 201
    sup.put(f"/api/gestao/colaboradores/{ana['id']}", json={"ativo": False})
    r = _entregar(tec, ana, luva)
    assert r.status_code == 409 and r.get_json()["code"] == "colaborador_inativo"
    detalhe = tec.get(f"/api/gestao/colaboradores/{ana['id']}").get_json()
    assert detalhe["colaborador"]["ativo"] is False and len(detalhe["entregas"]) == 1


def test_entrega_com_referencia_inexistente_ou_dado_invalido(sup, tec):
    ana, luva = _novo_colaborador(sup), _novo_epi(sup)
    base = {"colaborador_id": ana["id"], "epi_id": luva["id"], "quantidade": 1, "motivo": "admissao"}
    assert tec.post("/api/gestao/entregas", json={**base, "colaborador_id": 9999}).get_json()["code"] == "colaborador_nao_encontrado"
    assert tec.post("/api/gestao/entregas", json={**base, "epi_id": 9999}).status_code == 404
    for invalido in ({"quantidade": 0}, {"quantidade": "2"}, {"quantidade": True}, {"motivo": "presente"}, {"entregue_em": "ontem"},
                     {"colaborador_id": "x"}, {"observacao": "x" * 501}):
        r = tec.post("/api/gestao/entregas", json={**base, **invalido})
        assert r.status_code == 400, invalido
    assert tec.post("/api/gestao/entregas", data="isto não é json", content_type="application/json").status_code == 400


def test_devolucao_marca_a_data_e_devolver_de_novo_da_409(sup, tec):
    ana, luva = _novo_colaborador(sup), _novo_epi(sup)
    entrega = _entregar(tec, ana, luva).get_json()["entrega"]
    r = tec.post(f"/api/gestao/entregas/{entrega['id']}/devolucao", json={"devolvido_em": _dia(-2)})
    assert r.status_code == 200
    assert r.get_json()["entrega"]["devolvido_em"] == _dia(-2) and r.get_json()["entrega"]["situacao"] == "devolvido"
    de_novo = tec.post(f"/api/gestao/entregas/{entrega['id']}/devolucao", json={})
    assert de_novo.status_code == 409 and de_novo.get_json()["code"] == "ja_devolvido"
    assert tec.post("/api/gestao/entregas/9999/devolucao", json={}).status_code == 404


def test_devolucao_sem_corpo_usa_hoje_e_nao_pode_ser_antes_da_entrega(sup, tec):
    ana, luva = _novo_colaborador(sup), _novo_epi(sup)
    primeira = _entregar(tec, ana, luva).get_json()["entrega"]
    segunda = _entregar(tec, ana, luva).get_json()["entrega"]
    assert tec.post(f"/api/gestao/entregas/{primeira['id']}/devolucao").get_json()["entrega"]["devolvido_em"] == HOJE.isoformat()
    antes = tec.post(f"/api/gestao/entregas/{segunda['id']}/devolucao", json={"devolvido_em": _dia(-30)})
    assert antes.status_code == 400 and antes.get_json()["code"] == "data_invalida"


def test_devolver_vale_para_colaborador_desligado_e_ca_vencido(sup, tec):
    """Devolução é o fim do ciclo: não pode depender do colaborador estar ativo nem do CA estar em dia."""
    ana, luva = _novo_colaborador(sup), _novo_epi(sup)
    entrega = _entregar(tec, ana, luva).get_json()["entrega"]
    sup.put(f"/api/gestao/colaboradores/{ana['id']}", json={"ativo": False})
    sup.put(f"/api/gestao/epis/{luva['id']}", json={"validade_ca": _dia(-5)})
    assert tec.post(f"/api/gestao/entregas/{entrega['id']}/devolucao", json={}).status_code == 200


def test_listagem_de_entregas_filtra_por_colaborador_epi_e_situacao_e_o_historico_vem_do_mais_recente(sup, tec):
    ana, beto = _novo_colaborador(sup, "A-1", "Ana"), _novo_colaborador(sup, "B-1", "Beto")
    luva, capacete = _novo_epi(sup, "900001", vida_util=90), _novo_epi(sup, "900002", vida_util=1095, nome="Capacete", categoria="helmet")
    velha = _entregar(tec, ana, luva, entregue_em=_dia(-200)).get_json()["entrega"]  # troca prevista há 110 dias
    recente = _entregar(tec, ana, luva, entregue_em=_dia(-5)).get_json()["entrega"]
    devolvida = _entregar(tec, ana, capacete, entregue_em=_dia(-50)).get_json()["entrega"]
    tec.post(f"/api/gestao/entregas/{devolvida['id']}/devolucao", json={})
    _entregar(tec, beto, capacete, entregue_em=_dia(-1))
    assert velha["situacao"] == "troca_vencida" and recente["situacao"] == "vigente"

    def ids(consulta):
        return [e["id"] for e in tec.get(f"/api/gestao/entregas{consulta}").get_json()["items"]]

    assert ids(f"?colaborador_id={ana['id']}") == [recente["id"], devolvida["id"], velha["id"]]
    assert ids(f"?epi_id={capacete['id']}")[0] != devolvida["id"]  # a de Beto (ontem) vem antes da de Ana (50 dias)
    assert ids("?situacao=troca_vencida") == [velha["id"]]
    assert ids("?situacao=devolvido") == [devolvida["id"]]
    assert len(ids("?situacao=vigente")) == 2
    assert tec.get("/api/gestao/entregas?situacao=outra").status_code == 400
    historico = tec.get(f"/api/gestao/colaboradores/{ana['id']}").get_json()["entregas"]
    assert [e["id"] for e in historico] == [recente["id"], devolvida["id"], velha["id"]]


def test_colaborador_mostra_entregas_vigentes_e_pendencias(sup, tec):
    """Pendência = entrega em aberto com a troca vencida OU com o CA do EPI vencido."""
    ana = _novo_colaborador(sup)
    ok, antigo, ca_vencido = _novo_epi(sup, "900001"), _novo_epi(sup, "900002", vida_util=30), _novo_epi(sup, "900003", validade_em=5)
    _entregar(tec, ana, ok)
    _entregar(tec, ana, antigo, entregue_em=_dia(-60))
    _entregar(tec, ana, ca_vencido)
    sup.put(f"/api/gestao/epis/{ca_vencido['id']}", json={"validade_ca": _dia(-1)})
    item = tec.get("/api/gestao/colaboradores").get_json()["items"][0]
    assert (item["entregas_vigentes"], item["pendencias"]) == (2, 2)
    assert tec.get(f"/api/gestao/colaboradores/{ana['id']}").get_json()["colaborador"]["pendencias"] == 2
    assert tec.get("/api/gestao/colaboradores/9999").status_code == 404


# --------------------------------------------------------------- ocorrências ---
def _ocorrencia(cliente, **extra):
    corpo = {"tipo": "quase_acidente", "gravidade": "media", "setor": "Obra", "descricao": "Ferramenta caiu.", **extra}
    return cliente.post("/api/gestao/ocorrencias", json=corpo)


def test_ocorrencia_nasce_aberta_com_instante_em_utc(sup, tec):
    ana = _novo_colaborador(sup)
    r = _ocorrencia(tec, ocorrida_em="2026-10-20T08:30:00-03:00", colaborador_id=ana["id"])
    assert r.status_code == 201
    ocorrencia = r.get_json()["ocorrencia"]
    assert ocorrencia["status"] == "aberta" and ocorrencia["encerrada_em"] is None and ocorrencia["codigo"].startswith("OCO-")
    assert ocorrencia["ocorrida_em"] == "2026-10-20T11:30:00+00:00"
    assert ocorrencia["colaborador"] == {"id": ana["id"], "nome": "Ana Teste", "matricula": "T-001"}
    assert ocorrencia["registrada_por"] == "technical@fabrica.com" and ocorrencia["alerta_id"] is None
    sem_colaborador = _ocorrencia(tec).get_json()["ocorrencia"]
    assert sem_colaborador["colaborador"] is None and sem_colaborador["ocorrida_em"].endswith("+00:00")


def test_ocorrencia_sem_fuso_vale_utc(tec):
    assert _ocorrencia(tec, ocorrida_em="2026-10-20T08:30").get_json()["ocorrencia"]["ocorrida_em"] == "2026-10-20T08:30:00+00:00"


@pytest.mark.parametrize("invalido", [
    {"tipo": "susto"}, {"gravidade": "enorme"}, {"setor": ""}, {"descricao": ""}, {"ocorrida_em": "ontem"}, {"descricao": "x" * 2001},
])
def test_ocorrencia_invalida_da_400(tec, invalido):
    assert _ocorrencia(tec, **invalido).status_code == 400


def test_ocorrencia_aponta_para_colaborador_e_alerta_que_existem(app, tec):
    assert _ocorrencia(tec, colaborador_id=9999).get_json()["code"] == "colaborador_nao_encontrado"
    assert _ocorrencia(tec, alerta_id=9999).get_json()["code"] == "alerta_nao_encontrado"
    with app.app_context():
        alerta = Alert(rule="missing_helmet", severity="critical", message="Sem capacete", feature="helmet")
        db.session.add(alerta)
        db.session.commit()
        alerta_id = alerta.id
    assert _ocorrencia(tec, alerta_id=alerta_id).get_json()["ocorrencia"]["alerta_id"] == alerta_id


def test_encerrar_preenche_a_data_reabrir_limpa_e_encerrar_de_novo_mantem(tec):
    ocorrencia = _ocorrencia(tec).get_json()["ocorrencia"]
    url = f"/api/gestao/ocorrencias/{ocorrencia['id']}"
    em_tratamento = tec.put(url, json={"status": "em_tratamento", "acao_corretiva": "Isolar a área."}).get_json()["ocorrencia"]
    assert em_tratamento["status"] == "em_tratamento" and em_tratamento["encerrada_em"] is None
    encerrada = tec.put(url, json={"status": "encerrada"}).get_json()["ocorrencia"]
    assert encerrada["encerrada_em"] is not None and encerrada["acao_corretiva"] == "Isolar a área."  # a ação anterior fica
    de_novo = tec.put(url, json={"status": "encerrada", "acao_corretiva": "Área isolada e treinamento feito."}).get_json()["ocorrencia"]
    assert de_novo["encerrada_em"] == encerrada["encerrada_em"]
    reaberta = tec.put(url, json={"status": "aberta"}).get_json()["ocorrencia"]
    assert reaberta["status"] == "aberta" and reaberta["encerrada_em"] is None
    assert tec.put(url, json={"status": "feita"}).status_code == 400
    assert tec.put("/api/gestao/ocorrencias/9999", json={"status": "aberta"}).status_code == 404


def test_lista_de_ocorrencias_filtra_e_ordena_da_mais_recente(tec):
    antiga = _ocorrencia(tec, ocorrida_em="2026-09-01T10:00:00+00:00", tipo="acidente", setor="Obra").get_json()["ocorrencia"]
    nova = _ocorrencia(tec, ocorrida_em="2026-10-01T10:00:00+00:00", tipo="ato_inseguro", setor="Usinagem").get_json()["ocorrencia"]
    tec.put(f"/api/gestao/ocorrencias/{antiga['id']}", json={"status": "encerrada"})

    def ids(consulta):
        return [o["id"] for o in tec.get(f"/api/gestao/ocorrencias{consulta}").get_json()["items"]]

    assert ids("") == [nova["id"], antiga["id"]]
    assert ids("?status=encerrada") == [antiga["id"]] and ids("?status=aberta") == [nova["id"]]
    assert ids("?tipo=ato_inseguro") == [nova["id"]] and ids("?setor=Obra") == [antiga["id"]]
    assert tec.get("/api/gestao/ocorrencias?status=feita").status_code == 400
    assert tec.get("/api/gestao/ocorrencias?tipo=susto").status_code == 400


# -------------------------------------------------------------------- resumo ---
def test_resumo_conta_cada_indicador(app, sup, tec):
    assert tec.get("/api/gestao/resumo").get_json() == {
        "colaboradores_ativos": 0, "epis_no_catalogo": 0, "entregas_vigentes": 0, "trocas_vencidas": 0, "cas_vencidos": 0,
        "cas_a_vencer": 0, "ocorrencias_abertas": 0, "ocorrencias_30d": 0, "alertas_30d": 0,
        "alertas_simulados_30d": 0, "simulados": False,
    }
    with app.app_context():  # `agora()` é o relógio real (só `hoje()` está fixo): um alerta de agora e outro de 40 dias atrás
        db.session.add_all([
            Alert(rule="missing_helmet", severity="critical", message="a", feature="helmet", created_at=utc_now()),
            Alert(rule="missing_helmet", severity="critical", message="b", feature="helmet", created_at=utc_now() - timedelta(days=40)),
        ])
        db.session.commit()
    ana, beto = _novo_colaborador(sup, "A-1", "Ana"), _novo_colaborador(sup, "B-1", "Beto", ativo=False)
    assert beto["ativo"] is False
    curta, vencido, a_vencer = _novo_epi(sup, "900001", 200, 30), _novo_epi(sup, "900002", -1), _novo_epi(sup, "900003", 7)
    _entregar(tec, ana, curta, entregue_em=_dia(-5))     # vigente
    _entregar(tec, ana, curta, entregue_em=_dia(-60))    # troca vencida
    devolvida = _entregar(tec, ana, curta, entregue_em=_dia(-8)).get_json()["entrega"]
    tec.post(f"/api/gestao/entregas/{devolvida['id']}/devolucao", json={})
    _ocorrencia(tec)
    em_tratamento = _ocorrencia(tec).get_json()["ocorrencia"]
    tec.put(f"/api/gestao/ocorrencias/{em_tratamento['id']}", json={"status": "em_tratamento"})
    _ocorrencia(tec, ocorrida_em="2020-01-01T00:00:00+00:00")
    resumo = tec.get("/api/gestao/resumo").get_json()
    assert resumo["colaboradores_ativos"] == 1 and resumo["epis_no_catalogo"] == 3
    assert (resumo["entregas_vigentes"], resumo["trocas_vencidas"]) == (1, 1)
    assert (resumo["cas_vencidos"], resumo["cas_a_vencer"]) == (1, 1)
    assert vencido["situacao_ca"] == "vencido" and a_vencer["dias_para_vencer"] == 7
    assert resumo["ocorrencias_abertas"] == 2 and resumo["ocorrencias_30d"] == 2
    assert resumo["simulados"] is False and resumo["alertas_30d"] == 1 and resumo["alertas_simulados_30d"] == 0


def test_resumo_avisa_quando_ha_registro_simulado(app, tec):
    with app.app_context():
        db.session.add(Colaborador(matricula="S-1", nome="Fictício", setor="Obra", funcao="X", admissao=HOJE, ficticio=True))
        db.session.commit()
    assert tec.get("/api/gestao/resumo").get_json()["simulados"] is True


# ----------------------------------------------------------------------- CSV ---
def test_csv_tem_bom_ponto_e_virgula_nome_de_arquivo_e_cabecalho_de_download(sup, tec):
    ana, luva = _novo_colaborador(sup), _novo_epi(sup)
    _entregar(tec, ana, luva)
    r = tec.get("/api/gestao/exportar/entregas.csv")
    assert r.status_code == 200 and r.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert r.headers["Content-Disposition"] == "attachment; filename=visionepi-entregas-2026-10-23.csv"
    corpo = r.get_data()
    assert corpo.startswith(b"\xef\xbb\xbf")
    linhas = corpo.decode("utf-8-sig").split("\r\n")
    assert linhas[0].startswith("Código;Matrícula;Colaborador;Setor;EPI;CA;") and linhas[1].count(";") == linhas[0].count(";")
    assert "T-001;Ana Teste;Obra;Luva de teste;900001" in linhas[1]


@pytest.mark.parametrize("recurso", servico.RECURSOS_DE_EXPORTACAO)
def test_todo_recurso_exporta_com_cabecalho_mesmo_vazio(tec, recurso):
    r = tec.get(f"/api/gestao/exportar/{recurso}.csv")
    assert r.status_code == 200 and r.headers["Content-Disposition"].endswith(f"visionepi-{recurso}-2026-10-23.csv")
    assert r.get_data().decode("utf-8-sig").count("\r\n") == 1  # só o cabeçalho


def test_recurso_de_exportacao_desconhecido_da_404_em_json(tec):
    r = tec.get("/api/gestao/exportar/usuarios.csv")
    assert r.status_code == 404 and r.get_json()["code"] == "recurso_desconhecido"


def test_csv_neutraliza_formula_digitada_pelo_usuario(sup, tec):
    _novo_colaborador(sup, nome="=HYPERLINK(\"http://x\")")
    texto = tec.get("/api/gestao/exportar/colaboradores.csv").get_data().decode("utf-8-sig")
    assert "'=HYPERLINK" in texto and ";=HYPERLINK" not in texto


def test_csv_de_ocorrencias_leva_o_colaborador_e_o_de_alertas_nao_leva_metadados(app, sup, tec):
    ana = _novo_colaborador(sup)
    _ocorrencia(tec, colaborador_id=ana["id"], descricao="Linha com; ponto e vírgula")
    with app.app_context():
        db.session.add(Alert(rule="missing_helmet", severity="critical", message="Sem capacete · Pessoa 3", feature="helmet",
                             metadata_json={"person_id": "person_3", "person_box": [1, 2, 3, 4], "simulado": True}))
        db.session.commit()
    ocorrencias = tec.get("/api/gestao/exportar/ocorrencias.csv").get_data().decode("utf-8-sig")
    assert '"Linha com; ponto e vírgula"' in ocorrencias and "T-001;Ana Teste" in ocorrencias
    alertas = tec.get("/api/gestao/exportar/alertas.csv").get_data().decode("utf-8-sig")
    assert "Sem capacete · Pessoa 3" in alertas and "person_3" not in alertas and "person_box" not in alertas
    assert alertas.split("\r\n")[1].endswith(";não;sim")  # falso positivo não, simulado sim


# ------------------------------------------------------------ modelos e docs ---
def test_situacao_dos_modelos_depende_so_da_data_recebida():
    epi = EpiCatalogo(nome="x", categoria="outro", ca="9", validade_ca=HOJE + timedelta(days=30), fabricante="f", vida_util_dias=10)
    entrega = EntregaEpi(entregue_em=HOJE, troca_prevista_em=HOJE, devolvido_em=None)
    assert epi.situacao_ca(HOJE) == "a_vencer" and epi.situacao_ca(HOJE + timedelta(days=30)) == "a_vencer"
    assert epi.situacao_ca(HOJE + timedelta(days=31)) == "vencido"
    assert epi.situacao_ca(HOJE - timedelta(days=1)) == "valido" and epi.situacao_ca(HOJE - timedelta(days=100)) == "valido"
    assert entrega.situacao(HOJE) == "vigente" and entrega.situacao(HOJE + timedelta(days=1)) == "troca_vencida"
    entrega.devolvido_em = HOJE
    assert entrega.situacao(HOJE + timedelta(days=99)) == "devolvido"


def test_rotas_aparecem_na_api_documentada_com_a_conta_certa(app):
    from app.services.openapi_doc import construir_documento

    caminhos = construir_documento(app)["paths"]
    assert caminhos["/api/gestao/colaboradores"]["post"]["x-conta-minima"] == ROLE_SUPERVISOR
    assert caminhos["/api/gestao/colaboradores"]["get"]["x-conta-minima"] == ROLE_TECHNICAL
    assert caminhos["/api/gestao/entregas"]["post"]["x-conta-minima"] == ROLE_TECHNICAL
    assert caminhos["/api/gestao/exportar/{recurso}.csv"]["get"]["tags"] == ["Gestão de EPIs"]


def test_tela_de_gestao_e_rota_de_spa_conhecida(app):
    r = app.test_client().get("/gestao")
    assert r.status_code == 200 and r.mimetype == "text/html"
    r.close()


# ===================================================== rodada de correções (auditor, CX e UX) ===
# --- S1: privacidade --------------------------------------------------------------------------
def test_ocorrencia_ligada_a_alerta_da_camera_nao_identifica_o_colaborador(app, sup, tec):
    ana = _novo_colaborador(sup)
    with app.app_context():
        alerta = Alert(rule="missing_helmet", severity="critical", message="Sem capacete", feature="helmet")
        db.session.add(alerta)
        db.session.commit()
        alerta_id = alerta.id
    r = _ocorrencia(tec, colaborador_id=ana["id"], alerta_id=alerta_id)
    assert r.status_code == 400 and r.get_json()["code"] == "vinculo_proibido"
    assert "não pode identificar o colaborador" in r.get_json()["error"]
    assert _ocorrencia(tec, colaborador_id=9999, alerta_id=9999).get_json()["code"] == "vinculo_proibido"  # antes de procurar
    with app.app_context():
        assert Ocorrencia.query.count() == 0
    assert _ocorrencia(tec, colaborador_id=ana["id"]).status_code == 201 and _ocorrencia(tec, alerta_id=alerta_id).status_code == 201


def test_editar_ocorrencia_nao_cria_vinculo_entre_colaborador_e_alerta(app, sup, tec):
    ana = _novo_colaborador(sup)
    with app.app_context():
        alerta = Alert(rule="missing_helmet", severity="critical", message="Sem capacete", feature="helmet")
        db.session.add(alerta)
        db.session.commit()
        alerta_id = alerta.id
    ocorrencia = _ocorrencia(tec, alerta_id=alerta_id).get_json()["ocorrencia"]
    editada = tec.put(f"/api/gestao/ocorrencias/{ocorrencia['id']}", json={"status": "em_tratamento", "colaborador_id": ana["id"]})
    assert editada.status_code == 200 and editada.get_json()["ocorrencia"]["colaborador"] is None  # o PUT não troca vínculo


# --- S3: duplicidade e maiúsculas -------------------------------------------------------------
def test_matricula_e_gravada_em_maiusculas_e_a_repetida_vale_em_qualquer_caixa(sup):
    criado = _novo_colaborador(sup, "mi-0007")
    assert criado["matricula"] == "MI-0007"
    repetida = sup.post("/api/gestao/colaboradores", json={
        "matricula": "Mi-0007", "nome": "Outra", "setor": "Obra", "funcao": "X", "admissao": "2025-01-10"})
    assert repetida.status_code == 409 and repetida.get_json()["code"] == "matricula_duplicada"


def test_corrida_de_dois_pedidos_vira_409_duplicado_e_nao_500(sup, monkeypatch):
    """A checagem prévia passa para os dois pedidos; quem perde na gravação leva 409 `duplicado` (a restrição única do banco)."""
    def sem_checagem(colaborador, corpo):
        colaborador.matricula, colaborador.nome, colaborador.setor = "CORRIDA", "Ana", "Obra"
        colaborador.funcao, colaborador.admissao, colaborador.ativo = "X", date(2025, 1, 1), True
        return colaborador

    monkeypatch.setattr(servico, "aplicar_colaborador", sem_checagem)
    assert sup.post("/api/gestao/colaboradores", json={}).status_code == 201
    r = sup.post("/api/gestao/colaboradores", json={})
    assert r.status_code == 409 and r.get_json()["code"] == "duplicado"
    with sup.application.app_context():
        assert Colaborador.query.count() == 1  # a sessão foi desfeita, nada pela metade


# --- S4: registro legal congelado -------------------------------------------------------------
def test_entrega_guarda_o_ca_e_o_nome_do_dia_mesmo_se_o_catalogo_mudar_depois(sup, tec):
    ana, luva = _novo_colaborador(sup), _novo_epi(sup, ca="900001", nome="Luva original")
    entrega = _entregar(tec, ana, luva).get_json()["entrega"]
    assert (entrega["epi"]["ca"], entrega["epi"]["nome"]) == ("900001", "Luva original")
    sup.put(f"/api/gestao/epis/{luva['id']}", json={"ca": "900777", "nome": "Luva renomeada", "validade_ca": _dia(-3)})
    historico = tec.get(f"/api/gestao/colaboradores/{ana['id']}").get_json()["entregas"][0]
    assert (historico["epi"]["ca"], historico["epi"]["nome"]) == ("900001", "Luva original")  # o que foi entregue não muda
    assert historico["epi"]["situacao_ca"] == "vencido"  # mas o selo reflete o item de HOJE
    assert tec.get("/api/gestao/entregas").get_json()["items"][0]["epi"]["ca"] == "900001"
    csv = tec.get("/api/gestao/exportar/entregas.csv").get_data().decode("utf-8-sig")
    assert ";Luva original;900001;" in csv and "900777" not in csv
    assert tec.get("/api/gestao/epis").get_json()["items"][0]["ca"] == "900777"  # o catálogo mostra o atual


# --- S5: trilha de edição no EventLog ---------------------------------------------------------
def _eventos(app, tipo):
    with app.app_context():
        return [e.to_dict() for e in EventLog.query.filter_by(event_type=tipo).order_by(EventLog.id.asc())]


def test_editar_colaborador_grava_evento_com_quem_e_o_que_mudou(app, sup):
    ana = _novo_colaborador(sup)
    assert _eventos(app, "gestao_colaborador_editado") == []  # cadastrar não é editar
    sup.put(f"/api/gestao/colaboradores/{ana['id']}", json={"setor": "Usinagem", "ativo": False})
    [evento] = _eventos(app, "gestao_colaborador_editado")
    assert evento["subject"] == "supervisor@fabrica.com" and "T-001" in evento["message"]
    assert evento["metadata"]["por"] == "supervisor@fabrica.com" and evento["metadata"]["id"] == ana["id"]
    assert evento["metadata"]["antes"] == {"ativo": True, "setor": "Obra"}
    assert evento["metadata"]["depois"] == {"ativo": False, "setor": "Usinagem"}
    sup.put(f"/api/gestao/colaboradores/{ana['id']}", json={"setor": "Usinagem"})  # nada mudou: nada gravado
    assert len(_eventos(app, "gestao_colaborador_editado")) == 1


def test_renovar_o_ca_grava_validade_antes_e_depois(app, sup):
    luva = _novo_epi(sup, validade_em=-10)
    sup.put(f"/api/gestao/epis/{luva['id']}", json={"validade_ca": _dia(365)})
    [evento] = _eventos(app, "gestao_epi_editado")
    assert evento["metadata"]["antes"] == {"validade_ca": _dia(-10)} and evento["metadata"]["depois"] == {"validade_ca": _dia(365)}
    assert "900001" in evento["message"]


def test_ocorrencia_grava_status_antes_e_depois_e_a_data_de_encerramento_anterior_na_reabertura(app, tec):
    ocorrencia = _ocorrencia(tec).get_json()["ocorrencia"]
    url = f"/api/gestao/ocorrencias/{ocorrencia['id']}"
    encerrada = tec.put(url, json={"status": "encerrada", "acao_corretiva": "Feito."}).get_json()["ocorrencia"]
    tec.put(url, json={"status": "aberta"})
    encerrar, reabrir = _eventos(app, "gestao_ocorrencia_atualizada")
    assert encerrar["metadata"]["antes"]["status"] == "aberta" and encerrar["metadata"]["depois"]["status"] == "encerrada"
    assert "aberta → encerrada" in encerrar["message"]
    assert reabrir["metadata"]["antes"]["encerrada_em"] == encerrada["encerrada_em"]  # o que a reabertura apagou
    assert reabrir["metadata"]["depois"]["encerrada_em"] is None and reabrir["metadata"]["por"] == "technical@fabrica.com"


# --- S6: datas ----------------------------------------------------------------------------------
def test_entrega_com_data_futura_ou_ano_absurdo_da_400_e_nunca_500(sup, tec):
    ana, luva = _novo_colaborador(sup), _novo_epi(sup)
    futura = _entregar(tec, ana, luva, entregue_em=_dia(1))
    assert futura.status_code == 400 and futura.get_json()["code"] == "data_invalida"
    assert _entregar(tec, ana, luva, entregue_em=_dia(0)).status_code == 201
    for absurda in ("0001-01-01", "1899-12-31", "9999-12-31", "2028-01-01"):
        r = _entregar(tec, ana, luva, entregue_em=absurda)
        assert r.status_code == 400, absurda
    assert sup.post("/api/gestao/colaboradores", json={
        "matricula": "Z", "nome": "Z", "setor": "Obra", "funcao": "X", "admissao": "9999-12-31"}).status_code == 400
    assert sup.post("/api/gestao/epis", json={
        "nome": "Z", "categoria": "outro", "ca": "9", "validade_ca": "0001-01-01", "fabricante": "F",
        "vida_util_dias": 1}).status_code == 400


def test_ca_vencido_antes_da_data_da_entrega_tambem_bloqueia(sup, tec):
    """`validade_ca < entregue_em` implica vencido hoje (a entrega não pode ser futura): uma regra cobre as duas."""
    ana, luva = _novo_colaborador(sup), _novo_epi(sup, validade_em=-20)
    r = _entregar(tec, ana, luva, entregue_em=_dia(-5))
    assert r.status_code == 409 and r.get_json()["code"] == "ca_vencido"
    assert _entregar(tec, ana, luva, entregue_em=_dia(-40)).status_code == 409  # mesmo com CA válido naquele dia: política é de hoje


def test_devolucao_nao_pode_ser_futura(sup, tec):
    ana, luva = _novo_colaborador(sup), _novo_epi(sup)
    entrega = _entregar(tec, ana, luva).get_json()["entrega"]
    r = tec.post(f"/api/gestao/entregas/{entrega['id']}/devolucao", json={"devolvido_em": _dia(1)})
    assert r.status_code == 400 and r.get_json()["code"] == "data_invalida"
    assert tec.post(f"/api/gestao/entregas/{entrega['id']}/devolucao", json={"devolvido_em": "0001-01-01"}).status_code == 400


def test_ocorrencia_aceita_ate_cinco_minutos_a_frente_do_relogio_e_recusa_alem(tec):
    agora = datetime.now(timezone.utc)
    assert _ocorrencia(tec, ocorrida_em=(agora + timedelta(minutes=2)).isoformat()).status_code == 201
    r = _ocorrencia(tec, ocorrida_em=(agora + timedelta(minutes=10)).isoformat())
    assert r.status_code == 400 and r.get_json()["code"] == "data_invalida"
    for absurdo in ("9999-12-31T23:59:59+00:00", "0001-01-01T00:00:00+14:00", "1899-01-01T00:00:00"):
        assert _ocorrencia(tec, ocorrida_em=absurdo).status_code == 400, absurdo


# --- S7: limites e SQL --------------------------------------------------------------------------
def test_filtro_de_situacao_em_sql_concorda_com_a_regra_do_modelo(app, sup):
    ana, luva = _novo_colaborador(sup), _novo_epi(sup)
    with app.app_context():
        for i, (troca, devolvido) in enumerate([
            (HOJE - timedelta(days=1), None), (HOJE, None), (HOJE + timedelta(days=1), None), (HOJE - timedelta(days=1), HOJE),
            (HOJE + timedelta(days=9), HOJE),
        ]):
            db.session.add(EntregaEpi(
                codigo=f"T-{i}", colaborador_id=ana["id"], epi_id=luva["id"], ca_na_entrega="9", epi_nome_na_entrega="x",
                quantidade=1, entregue_em=HOJE - timedelta(days=30), troca_prevista_em=troca, devolvido_em=devolvido,
                motivo="admissao", registrado_por="t",
            ))
        db.session.commit()
        todas = EntregaEpi.query.all()
        for situacao in servico.SITUACOES_DE_ENTREGA:
            no_sql = {e.codigo for e in EntregaEpi.query.filter(servico.filtro_de_situacao(situacao, HOJE))}
            no_modelo = {e.codigo for e in todas if e.situacao(HOJE) == situacao}
            assert no_sql == no_modelo and no_sql, situacao


def test_listagens_avisam_quando_passam_do_limite(sup, tec, monkeypatch):
    monkeypatch.setattr(servico, "LIMITE_DA_LISTAGEM", 2)
    ana = _novo_colaborador(sup, "A-1", "Ana")
    _novo_colaborador(sup, "B-1", "Beto")
    _novo_colaborador(sup, "C-1", "Carla")
    luva = _novo_epi(sup, "900001")
    _novo_epi(sup, "900002")
    _novo_epi(sup, "900003")
    for _ in range(3):
        _entregar(tec, ana, luva)
        _ocorrencia(tec)
    for url in ("colaboradores", "epis", "entregas", "ocorrencias"):
        corpo = tec.get(f"/api/gestao/{url}").get_json()
        assert corpo["count"] == 2 and len(corpo["items"]) == 2 and corpo["truncado"] is True, url
    assert tec.get("/api/gestao/colaboradores?busca=ana").get_json()["truncado"] is False
    assert tec.get(f"/api/gestao/colaboradores/{ana['id']}").get_json()["entregas_truncado"] is True
    monkeypatch.setattr(servico, "LIMITE_DA_LISTAGEM", 3)
    assert tec.get("/api/gestao/entregas").get_json()["truncado"] is False  # exatamente no limite não é truncado


def test_exportacao_tem_teto_e_avisa_no_cabecalho(sup, tec, monkeypatch):
    for i in range(3):
        _novo_colaborador(sup, f"M-{i}", f"Pessoa {i}")
    completo = tec.get("/api/gestao/exportar/colaboradores.csv")
    assert "X-Registros-Truncados" not in completo.headers
    monkeypatch.setattr(servico, "LIMITE_DA_EXPORTACAO", 2)
    r = tec.get("/api/gestao/exportar/colaboradores.csv")
    assert r.headers["X-Registros-Truncados"] == "true" and r.get_data().decode("utf-8-sig").count("\r\n") == 3  # cabeçalho + 2


def test_catalogo_conta_entregas_vigentes_por_item_com_group_by(sup, tec):
    ana = _novo_colaborador(sup)
    a, b = _novo_epi(sup, "900001"), _novo_epi(sup, "900002", vida_util=30)
    _entregar(tec, ana, a)
    _entregar(tec, ana, a)
    _entregar(tec, ana, b, entregue_em=_dia(-90))  # troca vencida: não é vigente
    devolvida = _entregar(tec, ana, b).get_json()["entrega"]
    tec.post(f"/api/gestao/entregas/{devolvida['id']}/devolucao", json={})
    assert {i["ca"]: i["entregas_vigentes"] for i in tec.get("/api/gestao/epis").get_json()["items"]} == {"900001": 2, "900002": 0}


# --- S12: filtros ------------------------------------------------------------------------------
@pytest.mark.parametrize("consulta", [
    "colaborador_id=abc", "epi_id=x", "colaborador_id=0", "epi_id=-3", "colaborador_id=99999999999", "epi_id=1.5",
])
def test_filtro_de_id_que_nao_e_numero_positivo_da_400(tec, consulta):
    r = tec.get(f"/api/gestao/entregas?{consulta}")
    assert r.status_code == 400 and r.get_json()["code"] == "filtro_invalido"


def test_busca_e_limitada_a_100_caracteres_e_curinga_do_like_vale_como_texto(sup, tec):
    _novo_colaborador(sup, "A-1", "Ana Souza")
    assert tec.get(f"/api/gestao/colaboradores?busca={'a' * 5000}").status_code == 200
    assert tec.get("/api/gestao/colaboradores?busca=%25").get_json()["count"] == 0  # "%" não casa com tudo
    assert tec.get("/api/gestao/colaboradores?busca=a_a").get_json()["count"] == 0  # "_" não casa com qualquer letra
    assert tec.get("/api/gestao/colaboradores?busca=ana").get_json()["count"] == 1


# --- resumo e simulados ---------------------------------------------------------------------------
def test_resumo_separa_alertas_simulados_sem_tirar_da_contagem_total(app, tec):
    with app.app_context():
        db.session.add_all([
            Alert(rule="missing_helmet", severity="critical", message="real", feature="helmet", created_at=utc_now()),
            Alert(rule="missing_helmet", severity="critical", message="simulado", feature="helmet", created_at=utc_now(),
                  metadata_json={"simulado": True, "seed_id": "SEED-ALR-9999"}),
            Alert(rule="missing_helmet", severity="critical", message="marca falsa", feature="helmet", created_at=utc_now(),
                  metadata_json={"simulado": False}),
        ])
        db.session.commit()
    resumo = tec.get("/api/gestao/resumo").get_json()
    assert resumo["alertas_30d"] == 3 and resumo["alertas_simulados_30d"] == 1
