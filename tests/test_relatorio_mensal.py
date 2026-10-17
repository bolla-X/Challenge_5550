"""Relatório mensal para a CIPA (M10): números do mês, escopo do Operador e NADA individual."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

import pytest
from app import create_app
from app.config import AuthTestConfig
from app.extensions import db
from app.models import Alert, Camera, Incidente, Intervencao, PermissaoDeTrabalho, PontoDaLiga
from app.services import custodia
from app.services import relatorio_mensal as rm
from app.services.auth_service import AuthService
from app.services.evacuacao import gravar_relatorio

SENHA = "senha-forte-de-teste"
MES = "2026-03"
UTC = timezone.utc


def _em(dia: int, hora: int = 12, mes: int = 3) -> datetime:
    return datetime(2026, mes, dia, hora, tzinfo=UTC)


@pytest.fixture()
def app_mensal(tmp_path):
    class Cfg(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'mensal.db'}"
        EVACUACAO_DIR = str(tmp_path / "evacuacoes")

    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
        db.session.add_all([Camera(id=1, name="Portaria", location="Entrada", source_type="Arquivo", source="x"),
                            Camera(id=2, name="Pátio", location="Pátio", source_type="Arquivo", source="x")])
        db.session.commit()
        AuthService().create_user(email="sup@x.local", name="Sup", password=SENHA, role="supervisor")
        AuthService().create_user(email="tec@x.local", name="Tec", password=SENHA, role="technical")
        AuthService().create_user(email="op@x.local", name="Op", password=SENHA, role="operator", camera_id=1)
        AuthService().create_user(email="semsetor@x.local", name="Sem", password=SENHA, role="operator")
    # O yield fica FORA do app context: com um contexto aberto o cliente de teste o reaproveita e o `g` (usuário em cache)
    # vaza de uma requisição para a outra, entre clientes de contas diferentes.
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _entrar(app, email):
    cliente = app.test_client()
    assert cliente.post("/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return cliente


def _alerta(camera_id, quando, *, severity="high", rule="missing_helmet", message="Sem capacete · Pessoa 7", **meta):
    return Alert(camera_id=camera_id, rule=rule, severity=severity, message=message, feature="helmet", status="resolved",
                 metadata_json=meta, created_at=quando, first_seen_at=quando, last_seen_at=quando)


def _popular(app):
    """Março de 2026 com dados sintéticos CHEIOS de campo individual (para provar que nenhum vaza)."""
    with app.app_context():
        db.session.add_all([
            # câmera 1: 3 alertas (1 falso positivo, 1 crítico)
            _alerta(1, _em(10), severity="critical"),
            _alerta(1, _em(11)),
            _alerta(1, _em(12), false_positive=True, person_id=7),
            # câmera 2: 1 alerta com "Avisei o colaborador"
            _alerta(2, _em(13), rule="missing_vest", message="Sem colete · Pessoa 9", acknowledged=True,
                    acknowledged_by="joao@empresa.com"),
            # fora do mês: nunca contam
            _alerta(1, _em(28, mes=2)),
            _alerta(1, _em(2, mes=4)),
        ])
        aberto = _em(10)
        db.session.add_all([
            Incidente(camera_id=1, rule="missing_helmet", zona="Zona A", severity="critical", titulo="Sem capacete",
                      pessoas=[7, 9], alert_ids=[1], aberto_em=aberto, atualizado_em=aberto,
                      reconhecido_em=aberto + timedelta(seconds=120), reconhecido_papel="operator"),
            Incidente(camera_id=1, rule="missing_helmet", zona="Zona A", severity="high", titulo="Sem capacete",
                      pessoas=[4], alert_ids=[2], aberto_em=_em(11), atualizado_em=_em(11),
                      reconhecido_em=_em(11) + timedelta(seconds=60), reconhecido_papel="technical"),
            Incidente(camera_id=2, rule="missing_vest", zona="Fora da zona", severity="high", titulo="Sem colete",
                      pessoas=[9], alert_ids=[4], aberto_em=_em(13), atualizado_em=_em(13)),
            Incidente(camera_id=1, rule="missing_helmet", zona="Zona A", severity="high", titulo="Sem capacete",
                      pessoas=[1], alert_ids=[5], aberto_em=_em(2, mes=4), atualizado_em=_em(2, mes=4)),
        ])
        db.session.add_all([
            PontoDaLiga(setor="Entrada", camera_id=1, tipo="minuto_conforme", pontos=1, ref=f"1:{n}", criado_em=_em(10)) for n in range(3)
        ] + [
            PontoDaLiga(setor="Pátio", camera_id=2, tipo="minuto_conforme", pontos=1, ref=f"2:{n}", criado_em=_em(10)) for n in range(2)
        ] + [PontoDaLiga(setor="Entrada", camera_id=1, tipo="checkin_portal", pontos=10, ref="c:1", criado_em=_em(10))])
        db.session.add_all([
            PermissaoDeTrabalho(numero="PT-2026-0001", camera_id=1, tipo="altura", descricao="Telhado", responsavel="João Silva",
                                inicio=_em(14, 8), fim=_em(14, 18), criada_por="joao@empresa.com", criada_em=_em(14, 7),
                                status="encerrada", encerrada_em=_em(14, 17), encerrada_por="maria@empresa.com"),
            PermissaoDeTrabalho(numero="PT-2026-0002", camera_id=1, tipo="espaco_confinado", descricao="Tanque", responsavel="Ana Souza",
                                inicio=_em(15, 8), fim=_em(15, 18), criada_por="ana@empresa.com", criada_em=_em(15, 7)),
            PermissaoDeTrabalho(numero="PT-2026-0003", camera_id=2, tipo="geral", descricao="Solda", responsavel="Pedro Lima",
                                inicio=_em(16, 8), fim=_em(16, 18), criada_por="pedro@empresa.com", criada_em=_em(16, 7),
                                status="cancelada", encerrada_em=_em(16, 9), encerrada_por="pedro@empresa.com"),
        ])
        db.session.commit()
        pasta = rm_pasta(app)
        base = {"duracao_s": 185.5, "iniciada_por": "sup@x.local", "encerrada_por": "sup@x.local", "ponto_de_encontro_camera_id": 1,
                "total_maximo_somado": 9, "chegadas_ponto_de_encontro": 6, "sha256": "abc"}
        gravar_relatorio(base | {"inicio": _em(20, 14).isoformat(), "fim": _em(20, 14).isoformat()}, pasta)
        gravar_relatorio(base | {"inicio": _em(5, 14, mes=2).isoformat(), "fim": _em(5, 14, mes=2).isoformat()}, pasta)  # fevereiro


def rm_pasta(app):
    from app.services.evacuacao import pasta_dos_relatorios

    return pasta_dos_relatorios(app)


def _json(cliente, mes=MES, extra=""):
    resposta = cliente.get(f"/api/relatorio/mensal?mes={mes}{extra}")
    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    return resposta.get_json()


def _html(cliente, mes=MES, extra=""):
    resposta = cliente.get(f"/relatorio/mensal?mes={mes}{extra}")
    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    return resposta.get_data(as_text=True)


# ------------------------------------------------------------------ mês sem dados
def test_mes_sem_dados_responde_zerado_e_diz_que_nao_ha_registro(app_mensal):
    tec = _entrar(app_mensal, "tec@x.local")
    dados = _json(tec)
    assert dados["mes"] == MES and dados["rotulo"] == "março de 2026"
    assert dados["periodo"] == {"inicio": "2026-03-01", "fim": "2026-03-31"}
    assert dados["sem_dados"] is True
    assert dados["alertas"]["total"] == 0 and dados["alertas"]["por_regra"] == {}
    assert dados["incidentes"]["total"] == 0 and dados["incidentes"]["mediana_ate_reconhecer_s"] is None
    assert dados["indicadores"]["minutos_conformes"] == 0
    assert dados["permissoes"]["emitidas"] == 0
    assert dados["evacuacoes"]["total"] == 0
    assert dados["cadeia_de_custodia"] == {"disponivel": True, "integra": True}
    pagina = _html(tec)
    assert "Nenhum dado registrado neste mês" in pagina
    assert "Relatório mensal para a CIPA" in pagina


def test_sem_o_modelo_de_intervencoes_a_secao_diz_que_nao_ha_registro(app_mensal, monkeypatch):
    monkeypatch.delattr(rm.modelos, "Intervencao")  # versão do banco sem a funcionalidade
    tec = _entrar(app_mensal, "tec@x.local")
    assert _json(tec)["intervencoes"] == {"disponivel": False, "total": None, "itens": []}
    assert "Sem registro de intervenções disponível" in _html(tec)


def test_mes_sem_intervencao_com_tabela_diz_zero(app_mensal):
    assert _json(_entrar(app_mensal, "tec@x.local"))["intervencoes"] == {"disponivel": True, "total": 0, "itens": []}


# ------------------------------------------------------------------ mês com dados
def test_mes_com_dados_conta_so_o_mes(app_mensal):
    _popular(app_mensal)
    d = _json(_entrar(app_mensal, "tec@x.local"))
    assert d["sem_dados"] is False
    a = d["alertas"]
    assert (a["total"], a["validos"], a["falsos_positivos"], a["criticos"], a["colaboradores_avisados"]) == (4, 3, 1, 1, 1)
    assert a["por_regra"] == {"Sem capacete": 2, "Sem colete": 1}
    assert a["por_camera"] == {"Portaria": 2, "Pátio": 1}
    i = d["incidentes"]
    assert (i["total"], i["criticos"], i["reconhecimentos"]) == (3, 1, 2)
    assert i["mediana_ate_reconhecer_s"] == 90.0  # mediana de 60 s e 120 s
    assert i["por_regra"] == {"Sem capacete": 2, "Sem colete": 1}
    assert i["por_zona"] == {"Zona A": 2, "Fora da zona": 1}
    assert i["por_camera"] == {"Portaria": 2, "Pátio": 1}
    assert d["indicadores"]["minutos_conformes"] == 5, "só `minuto_conforme`, não check-in"
    assert d["indicadores"]["minutos_com_gente"] is None and d["indicadores"]["conformidade_pct"] is None
    p = d["permissoes"]
    assert (p["emitidas"], p["encerradas"], p["canceladas"]) == (3, 1, 1)
    assert p["por_tipo"] == {"Trabalho em altura": 1, "Espaço confinado": 1, "Geral": 1}
    e = d["evacuacoes"]
    assert e["total"] == 1 and e["itens"][0]["duracao_s"] == 185.5 and e["itens"][0]["total_maximo_somado"] == 9
    assert "dupla contagem" in e["aviso"]
    assert d["cadeia_de_custodia"] == {"disponivel": True, "integra": True}
    assert set(d["fontes"]) >= {"alertas", "incidentes", "permissoes", "evacuacoes", "cadeia_de_custodia", "indicadores"}


def test_html_traz_numeros_fontes_periodo_e_botao_de_imprimir(app_mensal):
    _popular(app_mensal)
    pagina = _html(_entrar(app_mensal, "tec@x.local"))
    assert "Imprimir / salvar PDF" in pagina and "window.print()" in pagina
    assert "@media print" in pagina and "size: A4" in pagina
    assert "Fonte de cada número" in pagina and "contado pelo sistema" in pagina
    assert "Período: 01/03/2026 a 31/03/2026" in pagina
    assert "Março de 2026" in pagina
    assert "1 falso positivo" in pagina and "2 reconhecimentos" in pagina and "1,5 min" in pagina
    assert "Sem capacete" in pagina and "Zona A" in pagina and "Espaço confinado" in pagina
    assert "dupla contagem" in pagina
    assert "Íntegra" in pagina
    assert "http" not in re.sub(r"<style>.*?</style>", "", pagina, flags=re.S), "sem dependência externa nem link"


def test_cadeia_adulterada_aparece_como_nao_integra_sem_detalhe(app_mensal, monkeypatch):
    monkeypatch.setattr(custodia, "verificar", lambda **_: {"integra": False, "adulterada": True,
                                                              "quebrado": {"elo_sha256": "SEGREDO-DO-ELO"}, "elos": [{"x": 1}]})
    tec = _entrar(app_mensal, "tec@x.local")
    assert _json(tec)["cadeia_de_custodia"] == {"disponivel": True, "integra": False}
    pagina = _html(tec)
    assert "NÃO íntegra" in pagina and "SEGREDO-DO-ELO" not in pagina


def test_cadeia_que_falha_nao_derruba_o_relatorio(app_mensal, monkeypatch):
    def quebra(**_):
        raise RuntimeError("disco")

    monkeypatch.setattr(custodia, "verificar", quebra)
    assert _json(_entrar(app_mensal, "tec@x.local"))["cadeia_de_custodia"] == {"disponivel": False, "integra": None}


def test_limites_do_mes_sao_meio_aberto_na_hora_local(app_mensal):
    inicio, fim = rm.limites_do_mes(2026, 3)
    with app_mensal.app_context():
        db.session.add_all([_alerta(1, inicio), _alerta(1, fim), _alerta(1, inicio - timedelta(seconds=1)),
                            _alerta(1, fim - timedelta(seconds=1))])
        db.session.commit()
    assert _json(_entrar(app_mensal, "tec@x.local"))["alertas"]["total"] == 2, "início conta; o instante do mês seguinte não"


def test_dezembro_fecha_em_31_e_janeiro_abre_o_ano_seguinte(app_mensal):
    inicio, fim = rm.limites_do_mes(2026, 12)
    assert fim == rm.limites_do_mes(2027, 1)[0] and fim > inicio
    assert _json(_entrar(app_mensal, "tec@x.local"), mes="2026-12")["periodo"] == {"inicio": "2026-12-01", "fim": "2026-12-31"}


# ------------------------------------------------------------------ nada individual
_PROIBIDOS = ("Pessoa ", "pessoa ", "@", "track", "João", "joao", "Silva", "Ana ", "Souza", "Pedro", "maria", "sup@x", "operator",
              "technical", "responsavel", "criada_por", "iniciada_por", "encerrada_por", "e-mail", "email", "person_id", "acknowledged_by")


def _sem_estilo(pagina: str) -> str:
    """`@page`/`@media` do CSS não são o `@` de um e-mail: olha só o texto da página."""
    return re.sub(r"<style>.*?</style>", "", pagina, flags=re.S)


@pytest.mark.parametrize("email", ["tec@x.local", "sup@x.local", "op@x.local"])
def test_json_e_html_sem_campo_individual(app_mensal, email):
    _popular(app_mensal)
    cliente = _entrar(app_mensal, email)
    corpos = {"json": json.dumps(_json(cliente), ensure_ascii=False), "html": _sem_estilo(_html(cliente))}
    for formato, corpo in corpos.items():
        achados = [termo for termo in _PROIBIDOS if termo in corpo]
        assert not achados, f"{formato} vazou campo individual: {achados}"


# ------------------------------------------------------------------ perfis e escopo
@pytest.mark.parametrize("caminho", ["/api/relatorio/mensal", "/relatorio/mensal"])
def test_sem_sessao_401(app_mensal, caminho):
    assert app_mensal.test_client().get(f"{caminho}?mes={MES}").status_code == 401


@pytest.mark.parametrize("caminho", ["/api/relatorio/mensal", "/relatorio/mensal"])
def test_operador_sem_setor_403(app_mensal, caminho):
    resposta = _entrar(app_mensal, "semsetor@x.local").get(f"{caminho}?mes={MES}")
    assert resposta.status_code == 403


@pytest.mark.parametrize("email", ["op@x.local", "tec@x.local", "sup@x.local"])
@pytest.mark.parametrize("caminho", ["/api/relatorio/mensal", "/relatorio/mensal"])
def test_perfis_com_acesso_recebem_200(app_mensal, email, caminho):
    resposta = _entrar(app_mensal, email).get(f"{caminho}?mes={MES}")
    assert resposta.status_code == 200
    assert resposta.mimetype == ("application/json" if caminho.startswith("/api") else "text/html")


def test_operador_so_ve_o_setor_dele(app_mensal):
    _popular(app_mensal)
    op = _entrar(app_mensal, "op@x.local")
    d = _json(op, extra="&camera_id=2")  # o parâmetro é ignorado: o escopo vem da sessão
    assert d["camera_id"] == 1
    assert d["alertas"]["total"] == 3 and d["alertas"]["por_camera"] == {"Portaria": 2}
    assert d["incidentes"]["total"] == 2 and d["incidentes"]["por_camera"] == {"Portaria": 2}
    assert d["indicadores"]["minutos_conformes"] == 3
    assert d["permissoes"]["emitidas"] == 2 and d["permissoes"]["canceladas"] == 0
    assert d["evacuacoes"]["disponivel"] is False and d["evacuacoes"]["total"] is None and d["evacuacoes"]["itens"] == []
    assert d["cadeia_de_custodia"]["disponivel"] is False and d["cadeia_de_custodia"]["integra"] is None
    pagina = _html(op)
    assert "Pátio" not in pagina and "Portaria" in pagina and "câmera #1" in pagina
    assert "Disponível para Técnico e Supervisor" in pagina


def test_tecnico_pode_filtrar_uma_camera_e_continua_vendo_a_planta_nas_secoes_globais(app_mensal):
    _popular(app_mensal)
    d = _json(_entrar(app_mensal, "tec@x.local"), extra="&camera_id=2")
    assert d["camera_id"] == 2 and d["alertas"]["total"] == 1 and d["indicadores"]["minutos_conformes"] == 2
    assert d["evacuacoes"]["total"] == 1 and d["cadeia_de_custodia"]["disponivel"] is True


# ------------------------------------------------------------------ parâmetro mes
@pytest.mark.parametrize("mes", ["2026-13", "2026-00", "26-03", "marco", "2026-3", "1999-12", "2101-01", "2026-03-01"])
def test_mes_invalido_responde_400_em_portugues(app_mensal, mes):
    tec = _entrar(app_mensal, "tec@x.local")
    for caminho in ("/api/relatorio/mensal", "/relatorio/mensal"):
        resposta = tec.get(f"{caminho}?mes={mes}")
        assert resposta.status_code == 400
        assert resposta.get_json() == {"error": "Informe o mês no formato AAAA-MM (por exemplo, 2026-10).", "code": "mes_invalido"}


def test_sem_mes_usa_o_mes_corrente(app_mensal):
    d = _entrar(app_mensal, "tec@x.local").get("/api/relatorio/mensal").get_json()
    assert d["mes"] == datetime.now().astimezone().strftime("%Y-%m")


# ------------------------------------------------------------------ serviço puro (sem HTTP)
def test_contador_ao_vivo_so_no_mes_corrente_e_respeita_a_camera(app_mensal):
    resumos = [{"camera_id": 1, "minutos_com_pessoas": 8, "minutos_conformes": 6},
               {"camera_id": 2, "minutos_com_pessoas": 2, "minutos_conformes": 2}]
    dentro, fora = _em(20), _em(20, mes=4)
    with app_mensal.app_context():
        vivo = rm.montar_relatorio_mensal(2026, 3, agora=dentro, andon=lambda: resumos)["indicadores"]["desde_que_o_servidor_subiu"]
        assert vivo["minutos_com_gente"] == 10 and vivo["minutos_conformes"] == 8 and vivo["conformidade_pct"] == 80.0
        so_1 = rm.montar_relatorio_mensal(2026, 3, camera_id=1, agora=dentro, andon=lambda: resumos)
        assert so_1["indicadores"]["desde_que_o_servidor_subiu"]["conformidade_pct"] == 75.0
        assert rm.montar_relatorio_mensal(2026, 3, agora=fora, andon=lambda: resumos)["indicadores"]["desde_que_o_servidor_subiu"] is None
        assert rm.montar_relatorio_mensal(2026, 3, agora=dentro)["indicadores"]["desde_que_o_servidor_subiu"] is None

        def quebra():
            raise RuntimeError("worker caído")

        assert rm.montar_relatorio_mensal(2026, 3, agora=dentro, andon=quebra)["indicadores"]["desde_que_o_servidor_subiu"] is None


def test_html_escapa_o_que_vem_do_banco(app_mensal):
    with app_mensal.app_context():
        db.session.add(Camera(id=3, name="<script>alert(1)</script>", source_type="Arquivo", source="x"))
        db.session.add(_alerta(3, _em(10), message="<b>x</b> · Pessoa 1"))
        db.session.commit()
    pagina = _html(_entrar(app_mensal, "tec@x.local"))
    assert "<script>alert(1)</script>" not in pagina and "&lt;script&gt;" in pagina
    assert "<b>x</b>" not in pagina


def _intervencao(**campos):
    base = {"titulo": "Nova sinalização", "descricao": "texto longo que não deve sair", "criada_por": "joao@empresa.com"}
    return Intervencao(**(base | campos))


def test_intervencoes_do_mes_por_camera_e_por_setor(app_mensal):
    with app_mensal.app_context():
        db.session.add_all([
            _intervencao(camera_id=1, titulo="Treinamento de capacete", data_da_intervencao=date(2026, 3, 10)),
            _intervencao(setor="Pátio", titulo="Faixa de pedestres", data_da_intervencao=date(2026, 3, 20)),
            _intervencao(camera_id=2, titulo="Corrimão novo", data_da_intervencao=date(2026, 3, 31)),
            _intervencao(camera_id=1, titulo="de fevereiro", data_da_intervencao=date(2026, 2, 28)),
            _intervencao(camera_id=1, titulo="de abril", data_da_intervencao=date(2026, 4, 1)),
        ])
        db.session.commit()
    tec, op = _entrar(app_mensal, "tec@x.local"), _entrar(app_mensal, "op@x.local")
    d = _json(tec)["intervencoes"]
    assert d["disponivel"] is True and d["total"] == 3
    assert [(i["data"], i["titulo"], i["escopo"]) for i in d["itens"]] == [
        ("2026-03-10", "Treinamento de capacete", "Portaria"),
        ("2026-03-20", "Faixa de pedestres", "Pátio"),
        ("2026-03-31", "Corrimão novo", "Pátio"),
    ]
    do_operador = [i["titulo"] for i in _json(op)["intervencoes"]["itens"]]
    assert do_operador == ["Treinamento de capacete"], "operador: a câmera 1 e o setor dela (Entrada)"
    assert [i["titulo"] for i in _json(tec, extra="&camera_id=2")["intervencoes"]["itens"]] == ["Faixa de pedestres", "Corrimão novo"]
    pagina = _sem_estilo(_html(tec))
    assert "3 intervenções" in pagina and "Treinamento de capacete" in pagina and "10/03/2026" in pagina
    corpo = json.dumps(d, ensure_ascii=False) + pagina
    assert "joao@" not in corpo and "criada_por" not in corpo and "texto longo" not in corpo


def test_intervencao_de_setor_aparece_para_o_operador_do_setor(app_mensal):
    with app_mensal.app_context():
        db.session.add(_intervencao(setor="Entrada", titulo="Cancela nova", data_da_intervencao=date(2026, 3, 5)))
        db.session.commit()
    assert [i["titulo"] for i in _json(_entrar(app_mensal, "op@x.local"))["intervencoes"]["itens"]] == ["Cancela nova"]


def test_tabela_de_intervencoes_ausente_nao_derruba_o_relatorio(app_mensal):
    with app_mensal.app_context():
        Intervencao.__table__.drop(db.engine)
    tec = _entrar(app_mensal, "tec@x.local")
    assert _json(tec)["intervencoes"] == {"disponivel": False, "total": None, "itens": []}
    assert "Sem registro de intervenções disponível" in _html(tec), "o resto do relatório continua saindo"
    with app_mensal.app_context():
        Intervencao.__table__.create(db.engine)  # devolve a tabela para o `drop_all` da fixture
