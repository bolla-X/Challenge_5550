"""Antes/depois de intervenção e ROI (MISSÃO 4, M8).

Roda com `AUTH_REQUIRED=True` e banco em arquivo (mesmo desenho de `tests/test_feedback_contatos.py`). O blueprint
ainda não é registrado por `create_app` (quem liga é `app/__init__.py`), então a fixture o registra quando falta.

Papéis esperados: Supervisor cria, edita e apaga; Técnico ou mais lê, compara e calcula o ROI; Operador, 403; sem
sessão, 401. As comparações chamam `servico.comparar(..., agora)` com o relógio injetado; a API usa o relógio real e
por isso só aparece aqui com datas bem no passado ou bem no futuro.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest
from app import create_app
from app.api.intervencoes import intervencoes_bp
from app.config import AuthTestConfig
from app.extensions import db
from app.models import ROLE_OPERATOR, ROLE_SUPERVISOR, ROLE_TECHNICAL, Alert, Camera, Incidente, Intervencao, PontoDaLiga
from app.services import intervencoes as servico
from app.services.auth_service import AuthService

SENHA = "senha-forte-de-teste"
DIA = date(2026, 10, 10)
DEPOIS_DE_TUDO = datetime(2026, 11, 30, 12, 0, tzinfo=timezone.utc)


def _criar_app(tmp_path):
    class Config(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'intervencoes-test.db'}"

    app = create_app(Config)
    if "intervencoes" not in app.blueprints:  # idempotente: não quebra quando o create_app passar a registrar
        app.register_blueprint(intervencoes_bp)
    return app


@pytest.fixture()
def app(tmp_path):
    app = _criar_app(tmp_path)
    with app.app_context():
        db.create_all()
        db.session.add_all([
            Camera(name="Pátio", location="Setor A", source="0"),
            Camera(name="Doca", location="Setor A", source="1"),
            Camera(name="Almoxarifado", location="Setor B", source="2"),
        ])
        db.session.commit()
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


# ---------------------------------------------------------------- ajudantes ---
def _local(dia: date, hora: int = 12, minuto: int = 0) -> datetime:
    """Instante UTC de `hora:minuto` locais do dia (o servidor conta dias em hora local)."""
    return datetime.combine(dia, time(hora, minuto)).astimezone(timezone.utc)


def _alerta(camera_id: int, dia: date, *, regra="missing_helmet", falso_positivo=False, hora=12, minuto=0) -> None:
    db.session.add(Alert(
        camera_id=camera_id, rule=regra, severity="high", message="m", status="resolved",
        metadata_json={"false_positive": True} if falso_positivo else {}, created_at=_local(dia, hora, minuto),
    ))
    db.session.commit()


def _intervencao(app, *, camera_id=1, setor=None, dia=DIA) -> int:
    with app.app_context():
        item = Intervencao(camera_id=None if setor else camera_id, setor=setor, titulo="Nova sinalização",
                           descricao="Faixas no piso", data_da_intervencao=dia, criada_por="x@x")
        db.session.add(item)
        db.session.commit()
        return item.id


def _comparar(app, intervencao_id: int, *, janela=3, agora=DEPOIS_DE_TUDO):
    with app.app_context():
        return servico.comparar(db.session.get(Intervencao, intervencao_id), janela, agora)


# ------------------------------------------------------------ janelas iguais ---
def test_janelas_iguais_antes_e_depois_com_a_fronteira_no_inicio_do_dia(app):
    with app.app_context():
        for d in (7, 8, 9):  # antes (janela de 3 dias)
            _alerta(1, date(2026, 10, d))
        _alerta(1, date(2026, 10, 9), hora=23, minuto=59)  # último minuto do antes
        _alerta(1, date(2026, 10, 10), hora=0, minuto=0)  # 00:00 do dia da intervenção: já é depois
        for d in (11, 12):
            _alerta(1, date(2026, 10, d))
        _alerta(1, date(2026, 10, 6))  # fora do antes
        _alerta(1, date(2026, 10, 13))  # fora do depois
    r = _comparar(app, _intervencao(app))
    assert r["janela_dias"] == 3
    assert (r["antes"]["alertas"]["total"], r["depois"]["alertas"]["total"]) == (4, 3)
    assert r["antes"]["dias_na_janela"] == r["depois"]["dias_na_janela"] == 3
    assert r["depois"]["completa"] is True
    assert r["variacao"]["alertas_pct"] == -25.0


def test_contagem_por_regra_une_as_regras_dos_dois_lados(app):
    with app.app_context():
        _alerta(1, date(2026, 10, 8), regra="missing_helmet")
        _alerta(1, date(2026, 10, 9), regra="missing_helmet")
        _alerta(1, date(2026, 10, 9), regra="fallen_person")
        _alerta(1, date(2026, 10, 11), regra="missing_helmet")
        _alerta(1, date(2026, 10, 11), regra="risk_area_presence")
    r = _comparar(app, _intervencao(app))
    assert r["antes"]["alertas"]["por_regra"] == {"missing_helmet": 2, "fallen_person": 1}
    assert r["depois"]["alertas"]["por_regra"] == {"missing_helmet": 1, "risk_area_presence": 1}
    assert {x["regra"]: (x["antes"], x["depois"]) for x in r["por_regra"]} == {
        "missing_helmet": (2, 1), "fallen_person": (1, 0), "risk_area_presence": (0, 1),
    }
    assert r["por_regra"][0]["regra"] == "missing_helmet"  # a mais frequente primeiro


def test_falso_positivo_nao_entra_na_contagem(app):
    with app.app_context():
        _alerta(1, date(2026, 10, 9))
        _alerta(1, date(2026, 10, 9), falso_positivo=True)
        _alerta(1, date(2026, 10, 11), falso_positivo=True)
    r = _comparar(app, _intervencao(app))
    assert (r["antes"]["alertas"]["total"], r["depois"]["alertas"]["total"]) == (1, 0)


def test_escopo_da_camera_ignora_as_outras_e_o_do_setor_soma_as_cameras_dele(app):
    with app.app_context():
        _alerta(1, date(2026, 10, 9))  # Pátio (Setor A)
        _alerta(2, date(2026, 10, 9))  # Doca (Setor A)
        _alerta(3, date(2026, 10, 9))  # Almoxarifado (Setor B)
    por_camera = _comparar(app, _intervencao(app, camera_id=1))
    por_setor = _comparar(app, _intervencao(app, setor="Setor A"))
    assert por_camera["antes"]["alertas"]["total"] == 1 and por_camera["escopo"]["camera_ids"] == [1]
    assert por_setor["antes"]["alertas"]["total"] == 2 and por_setor["escopo"]["camera_ids"] == [1, 2]


def test_incidentes_entram_na_comparacao(app):
    with app.app_context():
        for quando in (_local(date(2026, 10, 9)), _local(date(2026, 10, 11)), _local(date(2026, 10, 12))):
            db.session.add(Incidente(camera_id=1, rule="missing_helmet", severity="high", titulo="t", aberto_em=quando))
        db.session.add(Incidente(camera_id=3, rule="r", severity="high", titulo="outra câmera", aberto_em=_local(date(2026, 10, 9))))
        db.session.commit()
    r = _comparar(app, _intervencao(app))
    assert (r["antes"]["incidentes"]["total"], r["depois"]["incidentes"]["total"]) == (1, 2)
    assert r["variacao"]["incidentes_pct"] == 100.0


# ------------------------------------------------------------------- amostra ---
def test_amostra_traz_dias_com_dados_e_minutos_conformes(app):
    with app.app_context():
        _alerta(1, date(2026, 10, 8))
        _alerta(1, date(2026, 10, 8), hora=15)  # mesmo dia: conta um dia só
        _alerta(1, date(2026, 10, 9), falso_positivo=True)  # falso positivo também mostra que o sistema estava de pé
        db.session.add(Incidente(camera_id=1, rule="r", severity="high", titulo="t", aberto_em=_local(date(2026, 10, 11))))
        for minuto in range(3):
            db.session.add(PontoDaLiga(setor="Setor A", camera_id=1, tipo="minuto_conforme", pontos=1, ref=f"1:{minuto}",
                                       criado_em=_local(date(2026, 10, 12), 9, minuto)))
        db.session.commit()
    r = _comparar(app, _intervencao(app))
    assert r["antes"]["amostra"]["dias_com_dados"] == 2  # 8 e 9
    assert r["depois"]["amostra"]["dias_com_dados"] == 2  # 11 (incidente) e 12 (pontos)
    assert r["depois"]["amostra"]["minutos_conformes_registrados"] == 3
    assert r["antes"]["amostra"]["minutos_conformes_registrados"] == 0
    assert r["depois"]["amostra"]["dias_decorridos"] == 3
    # sem os minutos com gente gravados por período, nada é dividido por exposição: e o texto diz isso
    assert r["antes"]["amostra"]["minutos_observados"] is None
    assert r["exposicao"]["disponivel"] is False and "minutos com gente" in r["exposicao"]["motivo"]


def test_sem_dados_a_amostra_diz_zero_dias_e_nao_inventa_variacao(app):
    r = _comparar(app, _intervencao(app))
    assert r["antes"]["amostra"]["dias_com_dados"] == 0 and r["depois"]["amostra"]["dias_com_dados"] == 0
    assert r["variacao"] == {"alertas_pct": None, "incidentes_pct": None}  # antes == 0: não há base para percentual


# --------------------------------------------------------------------- aviso ---
def test_aviso_de_correlacao_nao_e_causa_vem_sempre(app):
    id_ = _intervencao(app)
    completo = _comparar(app, id_)
    parcial = _comparar(app, id_, agora=_local(date(2026, 10, 11)))
    futuro = _comparar(app, id_, agora=_local(date(2026, 9, 1)))
    for r in (completo, parcial, futuro):
        assert r["aviso"] == "Correlação não é causa: outras mudanças no período também contam."
    assert servico.AVISO == completo["aviso"]


# ------------------------------------------------------------ janela incompleta ---
def test_janela_depois_incompleta_conta_so_o_que_ja_aconteceu_e_nao_extrapola(app):
    with app.app_context():
        _alerta(1, date(2026, 10, 9))
        _alerta(1, date(2026, 10, 10))
        _alerta(1, date(2026, 10, 11))
        _alerta(1, date(2026, 10, 14))  # depois do "agora": ainda não aconteceu
    r = _comparar(app, _intervencao(app), janela=7, agora=_local(date(2026, 10, 12), 8))
    assert r["depois"]["completa"] is False
    assert r["depois"]["dias_decorridos"] == 2 and r["depois"]["dias_na_janela"] == 7
    assert r["depois"]["alertas"]["total"] == 2  # 10 e 11; o dia 14 não entra
    assert r["variacao"] is None  # sem percentual com a janela aberta
    assert "ainda não terminou" in r["aviso_da_janela"] and "faltam 5 dias de 7" in r["aviso_da_janela"]
    assert "não foram extrapolados" in r["aviso_da_janela"]
    assert r["antes"]["completa"] is True


def test_intervencao_no_futuro_nao_tem_depois(app):
    with app.app_context():
        _alerta(1, date(2026, 10, 14))
    r = _comparar(app, _intervencao(app, dia=date(2026, 10, 20)), janela=7, agora=_local(date(2026, 10, 15)))
    assert r["depois"]["alertas"]["total"] == 0 and r["depois"]["amostra"]["dias_com_dados"] == 0
    assert r["variacao"] is None
    assert "ainda não aconteceu" in r["aviso_da_janela"]


def test_janela_completa_nao_tem_aviso_de_janela(app):
    assert _comparar(app, _intervencao(app))["aviso_da_janela"] is None


# --------------------------------------------------------------- API: comparação ---
def test_api_comparacao_devolve_o_contrato_e_valida_a_janela(app, tec):
    id_ = _intervencao(app, dia=date.today() - timedelta(days=60))
    r = tec.get(f"/api/intervencoes/{id_}/comparacao?janela_dias=7")
    assert r.status_code == 200, r.get_json()
    corpo = r.get_json()
    assert {"intervencao", "janela_dias", "antes", "depois", "por_regra", "variacao", "exposicao", "aviso", "aviso_da_janela"} <= set(corpo)
    assert corpo["janela_dias"] == 7 and corpo["depois"]["completa"] is True
    assert tec.get(f"/api/intervencoes/{id_}/comparacao").get_json()["janela_dias"] == 7  # padrão
    for ruim in ("0", "91", "abc", "-3", "2.5"):
        r = tec.get(f"/api/intervencoes/{id_}/comparacao?janela_dias={ruim}")
        assert (r.status_code, r.get_json()["code"]) == (400, "campo_invalido"), ruim
    assert tec.get("/api/intervencoes/999/comparacao").status_code == 404


def test_api_janela_aberta_avisa_e_nao_calcula_variacao(app, tec):
    id_ = _intervencao(app, dia=date.today() - timedelta(days=1))
    corpo = tec.get(f"/api/intervencoes/{id_}/comparacao?janela_dias=7").get_json()
    assert corpo["depois"]["completa"] is False
    assert corpo["variacao"] is None and "ainda não terminou" in corpo["aviso_da_janela"]
    assert corpo["aviso"].startswith("Correlação não é causa")


# ------------------------------------------------------------------------ ROI ---
PREMISSAS = {
    "custo_da_intervencao": 10000, "incidentes_evitados": 4, "custo_medio_por_incidente": 5000,
    "periodo_dias": 30, "horas_perdidas_por_incidente": 2, "custo_da_hora": 100,
}


def test_roi_calcula_so_com_as_premissas_e_devolve_a_formula_em_texto(app, tec):
    id_ = _intervencao(app)
    r = tec.post(f"/api/intervencoes/{id_}/roi", json=PREMISSAS)
    assert r.status_code == 200, r.get_json()
    corpo = r.get_json()
    assert corpo["resultado"] == {
        "custo_por_incidente": 5200.0, "economia": 20800.0, "ganho_liquido": 10800.0, "roi_pct": 108.0, "payback_dias": 14.4,
    }
    assert corpo["premissas"]["custo_da_intervencao"] == 10000.0 and corpo["premissas"]["periodo_dias"] == 30
    assert "R$ 20.800,00" in corpo["formula"] and "R$ 10.000,00" in corpo["formula"] and "108" in corpo["formula"]
    assert corpo["aviso"].startswith("Estimativa com as suas premissas")


def test_roi_nao_depende_do_que_ha_no_banco(app, tec):
    id_ = _intervencao(app)
    sem_dados = tec.post(f"/api/intervencoes/{id_}/roi", json=PREMISSAS).get_json()
    with app.app_context():
        for d in range(1, 9):
            _alerta(1, date(2026, 10, d))
            db.session.add(Incidente(camera_id=1, rule="r", severity="high", titulo="t", aberto_em=_local(date(2026, 10, d))))
        db.session.commit()
    com_dados = tec.post(f"/api/intervencoes/{id_}/roi", json=PREMISSAS).get_json()
    assert sem_dados == com_dados


def test_roi_ignora_campos_que_nao_sao_premissas(app, tec):
    id_ = _intervencao(app)
    corpo = tec.post(f"/api/intervencoes/{id_}/roi", json={**PREMISSAS, "custo_oficial_do_acidente": 999999}).get_json()
    assert "custo_oficial_do_acidente" not in corpo["premissas"]
    assert corpo["resultado"]["economia"] == 20800.0


@pytest.mark.parametrize(("faltando", "rotulo"), [
    ("custo_da_intervencao", "custo da intervenção"),
    ("incidentes_evitados", "incidentes"),
    ("custo_medio_por_incidente", "custo médio"),
    ("periodo_dias", "período"),
])
def test_roi_sem_premissa_obrigatoria_e_400_e_nao_usa_valor_padrao(app, tec, faltando, rotulo):
    id_ = _intervencao(app)
    corpo = {k: v for k, v in PREMISSAS.items() if k != faltando}
    r = tec.post(f"/api/intervencoes/{id_}/roi", json=corpo)
    assert (r.status_code, r.get_json()["code"]) == (400, "campo_invalido")
    mensagem = r.get_json()["error"]
    assert rotulo in mensagem and "só números digitados por você" in mensagem
    assert faltando not in mensagem  # o nome do campo da API não aparece para o usuário


@pytest.mark.parametrize("ruim", [-1, "100", True, None, [1]])
def test_roi_rejeita_premissa_negativa_ou_que_nao_e_numero(app, tec, ruim):
    id_ = _intervencao(app)
    r = tec.post(f"/api/intervencoes/{id_}/roi", json={**PREMISSAS, "custo_da_intervencao": ruim})
    assert r.status_code == 400


def test_roi_rejeita_corpo_que_nao_e_objeto_e_periodo_quebrado(app, tec):
    id_ = _intervencao(app)
    assert tec.post(f"/api/intervencoes/{id_}/roi", json=[1, 2]).status_code == 400
    assert tec.post(f"/api/intervencoes/{id_}/roi", json={**PREMISSAS, "periodo_dias": 0}).status_code == 400
    assert tec.post(f"/api/intervencoes/{id_}/roi", json={**PREMISSAS, "periodo_dias": 7.5}).status_code == 400
    assert tec.post("/api/intervencoes/999/roi", json=PREMISSAS).status_code == 404


def test_roi_so_com_obrigatorias_assume_zero_horas_e_zero_custo_da_hora():
    r = servico.calcular_roi({"custo_da_intervencao": 1000, "incidentes_evitados": 2, "custo_medio_por_incidente": 800, "periodo_dias": 10})
    assert r["resultado"]["custo_por_incidente"] == 800.0 and r["resultado"]["economia"] == 1600.0
    assert r["premissas"]["horas_perdidas_por_incidente"] == 0.0


def test_roi_casos_de_borda_nao_dividem_por_zero():
    base = {"custo_medio_por_incidente": 800, "periodo_dias": 10}
    sem_custo = servico.calcular_roi({**base, "custo_da_intervencao": 0, "incidentes_evitados": 2})
    assert sem_custo["resultado"]["roi_pct"] is None and "zero" in sem_custo["formula"]
    sem_economia = servico.calcular_roi({**base, "custo_da_intervencao": 500, "incidentes_evitados": 0})
    assert sem_economia["resultado"]["payback_dias"] is None and sem_economia["resultado"]["ganho_liquido"] == -500.0
    assert sem_economia["resultado"]["roi_pct"] == -100.0


def test_roi_rejeita_numero_nao_finito():
    with pytest.raises(servico.DadoInvalido):
        servico.calcular_roi({**PREMISSAS, "custo_da_intervencao": math.inf})
    with pytest.raises(servico.DadoInvalido):
        servico.calcular_roi({**PREMISSAS, "custo_da_intervencao": math.nan})
    with pytest.raises(servico.DadoInvalido):
        servico.calcular_roi({**PREMISSAS, "custo_da_intervencao": 1e15})


# --------------------------------------------------------------------- papéis ---
NOVA = {"titulo": "Nova sinalização", "descricao": "Faixas no piso", "data_da_intervencao": "2026-10-10", "camera_id": 1}


def test_sem_sessao_tudo_e_401(app):
    anonimo = app.test_client()
    for metodo, url in (
        ("get", "/api/intervencoes"), ("post", "/api/intervencoes"), ("get", "/api/intervencoes/1"), ("put", "/api/intervencoes/1"),
        ("delete", "/api/intervencoes/1"), ("get", "/api/intervencoes/1/comparacao"), ("post", "/api/intervencoes/1/roi"),
    ):
        assert getattr(anonimo, metodo)(url).status_code == 401, (metodo, url)


def test_operador_nao_acessa_nada(app):
    op = _cliente(app, ROLE_OPERATOR)
    id_ = _intervencao(app)
    base = f"/api/intervencoes/{id_}"
    for metodo, url in (
        ("get", "/api/intervencoes"), ("post", "/api/intervencoes"), ("get", base), ("put", base),
        ("delete", base), ("get", f"{base}/comparacao"), ("post", f"{base}/roi"),
    ):
        assert getattr(op, metodo)(url).status_code == 403, (metodo, url)
    with app.app_context():
        assert Intervencao.query.count() == 1  # nada foi criado nem apagado


def test_tecnico_le_mas_nao_cria_edita_nem_apaga(app, tec):
    id_ = _intervencao(app)
    assert tec.get("/api/intervencoes").status_code == 200
    assert tec.get(f"/api/intervencoes/{id_}").status_code == 200
    assert tec.get(f"/api/intervencoes/{id_}/comparacao").status_code == 200
    assert tec.post(f"/api/intervencoes/{id_}/roi", json=PREMISSAS).status_code == 200
    assert tec.post("/api/intervencoes", json=NOVA).status_code == 403
    assert tec.put(f"/api/intervencoes/{id_}", json=NOVA).status_code == 403
    assert tec.delete(f"/api/intervencoes/{id_}").status_code == 403
    with app.app_context():
        assert Intervencao.query.count() == 1


def test_supervisor_cria_le_edita_e_apaga(app, sup):
    r = sup.post("/api/intervencoes", json=NOVA)
    assert r.status_code == 201, r.get_json()
    criada = r.get_json()["intervencao"]
    assert criada["criada_por"] == "supervisor@fabrica.com"  # vem da sessão
    assert criada["data_da_intervencao"] == "2026-10-10" and criada["camera_id"] == 1 and criada["setor"] is None

    assert sup.get("/api/intervencoes").get_json()["count"] == 1
    r = sup.put(f"/api/intervencoes/{criada['id']}", json={**NOVA, "titulo": "Sinalização ampliada", "camera_id": None, "setor": "Setor A"})
    assert r.status_code == 200, r.get_json()
    assert (r.get_json()["intervencao"]["titulo"], r.get_json()["intervencao"]["setor"], r.get_json()["intervencao"]["camera_id"]) == (
        "Sinalização ampliada", "Setor A", None)

    assert sup.delete(f"/api/intervencoes/{criada['id']}").get_json() == {"deleted": criada["id"]}
    assert sup.get(f"/api/intervencoes/{criada['id']}").status_code == 404
    assert sup.delete(f"/api/intervencoes/{criada['id']}").status_code == 404


def test_criada_por_nao_vem_do_corpo(app, sup):
    r = sup.post("/api/intervencoes", json={**NOVA, "criada_por": "outro@x.com", "id": 77})
    assert r.get_json()["intervencao"]["criada_por"] == "supervisor@fabrica.com"
    assert r.get_json()["intervencao"]["id"] != 77


def test_apagar_a_intervencao_nao_apaga_o_historico(app, sup):
    id_ = _intervencao(app)
    with app.app_context():
        _alerta(1, date(2026, 10, 9))
        db.session.add(Incidente(camera_id=1, rule="r", severity="high", titulo="t", aberto_em=_local(date(2026, 10, 9))))
        db.session.commit()
    assert sup.delete(f"/api/intervencoes/{id_}").status_code == 200
    with app.app_context():
        assert Alert.query.count() == 1 and Incidente.query.count() == 1


# ------------------------------------------------------------------ validação ---
@pytest.mark.parametrize(("mudanca", "codigo"), [
    ({"camera_id": 1, "setor": "Setor A"}, "escopo_invalido"),
    ({"camera_id": None, "setor": None}, "escopo_invalido"),
    ({"camera_id": None, "setor": "  "}, "escopo_invalido"),
    ({"camera_id": 999}, "camera_nao_encontrada"),
    ({"camera_id": "1"}, "campo_invalido"),
    ({"camera_id": True}, "campo_invalido"),
    ({"camera_id": None, "setor": "Setor Inexistente"}, "setor_desconhecido"),
    ({"titulo": "   "}, "campo_invalido"),
    ({"titulo": "x" * 161}, "campo_invalido"),
    ({"descricao": "x" * 2001}, "campo_invalido"),
    ({"data_da_intervencao": "10/10/2026"}, "campo_invalido"),
    ({"data_da_intervencao": None}, "campo_invalido"),
    ({"data_da_intervencao": 20261010}, "campo_invalido"),
])
def test_cadastro_invalido(app, sup, mudanca, codigo):
    r = sup.post("/api/intervencoes", json={**NOVA, **mudanca})
    assert r.status_code == (404 if codigo == "camera_nao_encontrada" else 400), r.get_json()
    assert r.get_json()["code"] == codigo
    with app.app_context():
        assert Intervencao.query.count() == 0


def test_corpo_que_nao_e_objeto_e_400(app, sup):
    assert sup.post("/api/intervencoes", json=[1]).status_code == 400
    assert sup.post("/api/intervencoes").status_code == 400


def test_edicao_invalida_nao_altera_o_registro(app, sup):
    id_ = _intervencao(app)
    assert sup.put(f"/api/intervencoes/{id_}", json={**NOVA, "titulo": "Outro", "data_da_intervencao": "lixo"}).status_code == 400
    with app.app_context():
        assert db.session.get(Intervencao, id_).titulo == "Nova sinalização"


def test_listagem_filtra_por_camera_e_por_setor(app, tec):
    _intervencao(app, camera_id=1)
    _intervencao(app, camera_id=3, dia=date(2026, 9, 1))
    _intervencao(app, setor="Setor A", dia=date(2026, 10, 20))
    assert tec.get("/api/intervencoes").get_json()["count"] == 3
    assert tec.get("/api/intervencoes?camera_id=3").get_json()["count"] == 1
    assert [i["setor"] for i in tec.get("/api/intervencoes?setor=Setor A").get_json()["items"]] == ["Setor A"]
    datas = [i["data_da_intervencao"] for i in tec.get("/api/intervencoes").get_json()["items"]]
    assert datas == sorted(datas, reverse=True)  # a mais recente primeiro


# ------------------------------------------------------------------ migração ---
def test_migracao_encadeia_na_cabeca_anterior():
    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory

    pasta = Path(__file__).resolve().parent.parent / "migrations"
    configuracao = AlembicConfig()
    configuracao.set_main_option("script_location", str(pasta))
    script = ScriptDirectory.from_config(configuracao)
    revisao = script.get_revision("b6c7d8e9f0a1")
    assert revisao.down_revision == "a5b6c7d8e9f0"
    assert len(script.get_heads()) == 1
