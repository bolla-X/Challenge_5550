"""Permissão de Trabalho digital (MISSÃO 4, M5): validação, checklist, vigência, regras e API.

As regras do avaliador são testadas com `people` sintéticos e dependências
injetadas (sem banco); a vigência e o cache, e a API, contra o banco de verdade.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from app import create_app
from app.api.permissoes import permissoes_bp
from app.config import AuthTestConfig
from app.extensions import db
from app.models import ROLE_OPERATOR, ROLE_SUPERVISOR, ROLE_TECHNICAL, Camera, EventLog, PermissaoDeTrabalho, utc_now
from app.services import permissoes as servico
from app.services.auth_service import AuthService
from app.services.permissoes import AvaliadorDePermissao, PermissaoInvalida
from app.services.risk_rules import RuleAlert

SENHA = "senha-forte-de-teste"
FRAME = (540, 960, 3)
T0 = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
AREA_VIGIA = [[0.0, 0.0], [0.3, 0.0], [0.3, 1.0], [0.0, 1.0]]  # faixa esquerda do quadro


# ============================================================ fixtures ======
@pytest.fixture()
def app(tmp_path):
    class Cfg(AuthTestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'permissoes.db'}"

    app = create_app(Cfg)
    # O blueprint é registrado em app/__init__.py pelo integrador; aqui só garante que a suíte funciona nos dois casos.
    if "permissoes" not in app.blueprints:
        app.register_blueprint(permissoes_bp)
    with app.app_context():
        db.create_all()
        portaria = Camera(name="Portaria", source_type="USB", source="0")
        almox = Camera(name="Almoxarifado", source_type="USB", source="1")
        db.session.add_all([portaria, almox])
        db.session.commit()
        app.config["ID_PORTARIA"] = portaria.id
        app.config["ID_ALMOX"] = almox.id
        AuthService().create_user(
            email="ana@fabrica.com", name="Ana", password=SENHA, role=ROLE_OPERATOR, camera_id=portaria.id
        )
        AuthService().create_user(email="tec@fabrica.com", name="Tec", password=SENHA, role=ROLE_TECHNICAL)
        AuthService().create_user(email="sup@fabrica.com", name="Sup", password=SENHA, role=ROLE_SUPERVISOR)
        db.session.remove()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def contexto(app):
    """Contexto de app para quem chama o serviço direto. Os testes de API NÃO o usam: dentro de um contexto
    externo as requisições reaproveitariam o mesmo `g` (e o usuário em cache), misturando os papéis."""
    with app.app_context():
        yield


def entrar(app, email: str):
    c = app.test_client()
    assert c.post("/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return c


def dados(app, **extra) -> dict:
    """Corpo válido de emissão (janela relativa a T0, para uso com `agora=T0`)."""
    base = {
        "camera_id": app.config["ID_PORTARIA"],
        "tipo": "geral",
        "descricao": "Manutenção do painel 3",
        "responsavel": "Carlos (líder de manutenção)",
        "inicio": T0.isoformat(),
        "fim": (T0 + timedelta(hours=4)).isoformat(),
        "epis_exigidos": ["helmet"],
    }
    return base | extra


def corpo_http(app, **extra) -> dict:
    """Corpo válido para a API, que valida contra o relógio real."""
    agora = utc_now()
    return dados(app, inicio=(agora - timedelta(minutes=5)).isoformat(), fim=(agora + timedelta(hours=4)).isoformat()) | extra


def emitir(app, agora=T0, **extra) -> PermissaoDeTrabalho:
    permissao, _ = servico.emitir_permissao(dados(app, **extra), criada_por="tec@fabrica.com", agora=agora)
    return permissao


def emitir_agora(app, **extra) -> PermissaoDeTrabalho:
    """Emite com a janela relativa ao relógio real (para testes via API, que não injetam o relógio)."""
    permissao, _ = servico.emitir_permissao(corpo_http(app, **extra), criada_por="tec@fabrica.com")
    return permissao


def pessoa(n: int, *, x1=500, y1=200, x2=700, y2=500, dentro=True, ppe=None) -> dict:
    """`people` sintético no formato do PersonComplianceMatcher (caixa em pixels, quadro 960x540)."""
    return {
        "id": f"person_{n}",
        "label": f"Pessoa {n}",
        "box": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        "ppe": {epi: {"status": status} for epi, status in (ppe or {}).items()},
        "risk_area": {"status": "inside" if dentro else "outside"},
    }


def vigia_na_area(n: int, *, dentro_da_zona=False) -> dict:
    """Pés em x≈0.10 do quadro (dentro da faixa esquerda de AREA_VIGIA)."""
    return pessoa(n, x1=50, y1=200, x2=150, y2=500, dentro=dentro_da_zona)


def pt_com_vigia(**extra) -> PermissaoDeTrabalho:
    campos = dict(
        id=7, numero="PT-2026-0007", camera_id=1, tipo="espaco_confinado", descricao="Limpeza do tanque", responsavel="Ana",
        inicio=T0, fim=T0 + timedelta(hours=4), epis_exigidos=[], exige_vigia=True, area_vigia=AREA_VIGIA, status="ativa",
        criada_por="x",
    )
    return PermissaoDeTrabalho(**(campos | extra))


def avaliador(permissao=None, zona=True) -> AvaliadorDePermissao:
    return AvaliadorDePermissao(buscar_permissao=lambda camera_id, agora: permissao, zona_exige=lambda camera_id: zona)


def avaliar(av: AvaliadorDePermissao, people, supported=frozenset({"helmet", "vest"})) -> list[dict]:
    return av.avaliar(1, people, FRAME, T0 + timedelta(hours=1), set(supported))


# ========================================================== validação =======
def test_duracao_de_ate_24h_vale_e_acima_e_recusada(app, contexto):
    campos, _ = servico.validar_dados(dados(app, fim=(T0 + timedelta(hours=24)).isoformat()), T0)
    assert campos["fim"] - campos["inicio"] == timedelta(hours=24)
    with pytest.raises(PermissaoInvalida) as erro:
        servico.validar_dados(dados(app, fim=(T0 + timedelta(hours=24, minutes=1)).isoformat()), T0)
    assert erro.value.code == "duracao_excedida"


@pytest.mark.parametrize("delta", [timedelta(0), timedelta(minutes=-5)])
def test_fim_tem_que_ser_depois_do_inicio(app, contexto, delta):
    with pytest.raises(PermissaoInvalida) as erro:
        servico.validar_dados(dados(app, fim=(T0 + delta).isoformat()), T0)
    assert erro.value.code == "janela_invalida"


def test_nao_emite_permissao_que_ja_expirou(app, contexto):
    with pytest.raises(PermissaoInvalida) as erro:
        servico.validar_dados(dados(app), T0 + timedelta(hours=5))
    assert erro.value.code == "janela_invalida"


def test_vigia_exige_area_de_vigia(app, contexto):
    with pytest.raises(PermissaoInvalida) as erro:
        servico.validar_dados(dados(app, tipo="espaco_confinado", exige_vigia=True), T0)
    assert erro.value.code == "area_vigia_obrigatoria"
    with pytest.raises(PermissaoInvalida):
        servico.validar_dados(dados(app, exige_vigia=True, area_vigia=[[0, 0], [1, 1]]), T0)  # < 3 pontos
    campos, _ = servico.validar_dados(dados(app, exige_vigia=True, area_vigia=[{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 2}]), T0)
    assert campos["area_vigia"][2] == [1.0, 1.0]  # limitado a 0–1


def test_area_de_vigia_sem_exigir_vigia_vira_aviso_e_e_descartada(app, contexto):
    campos, avisos = servico.validar_dados(dados(app, exige_vigia=False, area_vigia=AREA_VIGIA), T0)
    assert campos["area_vigia"] is None
    assert any("area_vigia" in a for a in avisos)


def test_acima_da_jornada_avisa_citando_o_item_da_norma(app, contexto):
    _, avisos = servico.validar_dados(dados(app, tipo="espaco_confinado", fim=(T0 + timedelta(hours=10)).isoformat()), T0)
    assert any("33.5.12" in a for a in avisos)
    _, avisos = servico.validar_dados(dados(app, tipo="altura", fim=(T0 + timedelta(hours=10)).isoformat()), T0)
    assert any("35.5.8.2" in a for a in avisos)
    _, avisos = servico.validar_dados(dados(app), T0)  # 4 h: sem aviso de jornada
    assert avisos == []


def test_espaco_confinado_sem_vigia_avisa(app, contexto):
    _, avisos = servico.validar_dados(dados(app, tipo="espaco_confinado"), T0)
    assert any("33.7.1 c" in a for a in avisos)


@pytest.mark.parametrize(
    "campo, valor",
    [("tipo", "radioativo"), ("epis_exigidos", ["capacete_de_ouro"]), ("epis_exigidos", "helmet"), ("responsavel", " "),
     ("descricao", ""), ("inicio", "ontem"), ("exige_vigia", "sim"), ("camera_id", "abc")],
)
def test_campos_invalidos_sao_recusados(app, contexto, campo, valor):
    with pytest.raises(PermissaoInvalida):
        servico.validar_dados(dados(app) | {campo: valor}, T0)


def test_data_sem_fuso_vale_como_utc(app, contexto):
    campos, _ = servico.validar_dados(dados(app, inicio="2026-10-17T12:00:00", fim="2026-10-17T14:00:00"), T0)
    assert campos["inicio"] == T0


# =========================================================== checklist ======
def test_checklist_automatica_so_para_o_que_o_modelo_detecta(app, contexto):
    permissao = pt_com_vigia(epis_exigidos=["helmet", "gloves", "ear_protection"])
    itens = servico.checklist(permissao, {"helmet", "vest"})
    assert itens == [
        {"epi": "helmet", "rotulo": "Capacete", "verificacao": "automatica"},
        {"epi": "gloves", "rotulo": "Luvas", "verificacao": "manual"},
        {"epi": "ear_protection", "rotulo": "Protetor auricular", "verificacao": "manual"},
    ]


def test_checklist_sem_modelo_e_tudo_manual():
    assert {i["verificacao"] for i in servico.checklist(pt_com_vigia(epis_exigidos=["helmet", "vest"]), set())} == {"manual"}


def test_norma_so_cita_nr33_e_nr35_com_url():
    nr33 = servico.norma_da_permissao("espaco_confinado")
    assert nr33["codigo"] == "NR-33" and nr33["url"].endswith("nr-33-atualizada-2022-_retificada.pdf")
    assert {"33.7.1 c)", "33.3.4.1 a)", "33.5.5", "33.5.12"} <= {i["item"] for i in nr33["itens"]}
    nr35 = servico.norma_da_permissao("altura")
    assert nr35["codigo"] == "NR-35" and {i["item"] for i in nr35["itens"]} == {"35.5.7", "35.5.8.2"}
    assert servico.norma_da_permissao("geral") is None


# ======================================================== vigência + cache ==
def test_permissao_ativa_respeita_a_janela_de_horario(app, contexto):
    criada = emitir(app, inicio=(T0 + timedelta(hours=1)).isoformat(), fim=(T0 + timedelta(hours=5)).isoformat())
    cam = criada.camera_id
    assert servico.permissao_ativa(cam, T0) is None  # ainda não começou
    assert servico.permissao_ativa(cam, T0 + timedelta(hours=1)).id == criada.id  # início inclusivo
    assert servico.permissao_ativa(cam, T0 + timedelta(hours=4, minutes=59)).id == criada.id
    assert servico.permissao_ativa(cam, T0 + timedelta(hours=5)) is None  # fim exclusivo
    assert servico.permissao_ativa(cam, T0 + timedelta(days=2)) is None  # expirada, status ainda "ativa"
    assert servico.permissao_ativa(cam + 1, T0 + timedelta(hours=2)) is None  # outra câmera


def test_permissao_ativa_devolve_copia_desanexada(app, contexto):
    criada = emitir(app)
    ativa = servico.permissao_ativa(criada.camera_id, T0 + timedelta(hours=1))
    assert ativa is not criada and ativa not in db.session
    assert ativa.numero == criada.numero and ativa.epis_exigidos == ["helmet"]


def test_encerrar_invalida_o_cache_na_hora(app, contexto):
    criada = emitir(app)
    agora = T0 + timedelta(hours=1)
    assert servico.permissao_ativa(criada.camera_id, agora) is not None  # popula o cache
    servico.encerrar_permissao(criada.id, por="tec@fabrica.com", agora=agora)
    assert servico.permissao_ativa(criada.camera_id, agora) is None  # sem esperar o TTL


def test_cancelar_invalida_o_cache_na_hora(app, contexto):
    criada = emitir(app)
    agora = T0 + timedelta(hours=1)
    assert servico.permissao_ativa(criada.camera_id, agora) is not None
    servico.cancelar_permissao(criada.id, por="tec@fabrica.com", agora=agora)
    assert servico.permissao_ativa(criada.camera_id, agora) is None


def test_emitir_invalida_o_cache_de_ausencia(app, contexto):
    cam = app.config["ID_PORTARIA"]
    agora = T0 + timedelta(hours=1)
    assert servico.permissao_ativa(cam, agora) is None  # cacheia "nenhuma"
    emitir(app)
    assert servico.permissao_ativa(cam, agora) is not None


def test_cache_evita_ler_o_banco_ate_o_ttl_ou_a_invalidacao(app, contexto):
    cam = app.config["ID_PORTARIA"]
    agora = T0 + timedelta(hours=1)
    relogio = {"t": 100.0}
    servico._cache().relogio = lambda: relogio["t"]
    assert servico.permissao_ativa(cam, agora) is None
    # Escrita "por fora" (outro processo): o serviço não foi avisado.
    db.session.add(pt_com_vigia(id=None, numero="PT-externa", camera_id=cam, exige_vigia=False, area_vigia=None))
    db.session.commit()
    assert servico.permissao_ativa(cam, agora) is None  # dentro do TTL: não leu o banco
    relogio["t"] += servico.TTL_CACHE_S + 0.1
    assert servico.permissao_ativa(cam, agora).numero == "PT-externa"  # TTL venceu
    db.session.query(PermissaoDeTrabalho).delete()
    db.session.commit()
    servico.invalidar_cache(cam)
    assert servico.permissao_ativa(cam, agora) is None


def test_encerrar_so_vale_para_permissao_ativa(app, contexto):
    criada = emitir(app)
    servico.encerrar_permissao(criada.id, por="a@x.com", agora=T0)
    with pytest.raises(PermissaoInvalida) as erro:
        servico.cancelar_permissao(criada.id, por="a@x.com", agora=T0)
    assert erro.value.code == "permissao_nao_ativa"
    with pytest.raises(LookupError):
        servico.encerrar_permissao(9999, por="a@x.com")


def test_emissao_e_encerramento_viram_event_log(app, contexto):
    criada = emitir(app)
    assert criada.numero == f"PT-{T0.year}-{criada.id:04d}"
    servico.encerrar_permissao(criada.id, por="sup@fabrica.com", agora=T0 + timedelta(hours=1))
    tipos = [e.event_type for e in EventLog.query.order_by(EventLog.id).all()]
    assert tipos == ["permissao_emitida", "permissao_encerrada"]
    evento = EventLog.query.filter_by(event_type="permissao_encerrada").one()
    assert evento.camera_id == criada.camera_id and evento.metadata_json["por"] == "sup@fabrica.com"
    db.session.refresh(criada)
    assert criada.status == "encerrada" and criada.encerrada_por == "sup@fabrica.com"


def test_emitir_para_camera_inexistente(app, contexto):
    with pytest.raises(LookupError):
        servico.emitir_permissao(dados(app, camera_id=9999), criada_por="x", agora=T0)


# ================================================== regras do avaliador =====
def test_dentro_da_zona_sem_permissao_alerta_cada_pessoa(app, contexto):
    alertas = avaliar(avaliador(None, zona=True), [pessoa(1), pessoa(2, x1=300, x2=400), pessoa(3, dentro=False)])
    assert [a["rule"] for a in alertas] == ["sem_permissao_ativa", "sem_permissao_ativa"]
    assert alertas[0]["message"] == "Entrada na zona sem permissão ativa · Pessoa 1"
    assert {a["severity"] for a in alertas} == {"high"}
    assert alertas[0]["metadata"]["person_id"] == "person_1" and alertas[0]["metadata"]["person_box"]["x1"] == 500
    regras = [RuleAlert(**a) for a in alertas]  # contrato com o motor de alertas
    assert len({r.key for r in regras}) == 2


def test_zona_que_nao_exige_permissao_nao_alerta():
    assert avaliar(avaliador(None, zona=False), [pessoa(1)]) == []


def test_ninguem_na_zona_nao_consulta_permissao_nem_zona():
    def explode(*_):
        raise AssertionError("não deveria consultar nada")

    av = AvaliadorDePermissao(buscar_permissao=explode, zona_exige=explode)
    assert avaliar(av, [pessoa(1, dentro=False)]) == []
    assert avaliar(av, []) == []


def test_com_permissao_vigente_e_sem_vigia_exigido_nao_alerta_nada():
    assert avaliar(avaliador(pt_com_vigia(exige_vigia=False, area_vigia=None)), [pessoa(1)]) == []


def test_com_permissao_dentro_e_sem_ninguem_na_area_do_vigia_e_critico():
    alertas = avaliar(avaliador(pt_com_vigia()), [pessoa(1)])
    assert len(alertas) == 1
    alerta = alertas[0]
    assert alerta["rule"] == "sem_vigia" and alerta["severity"] == "critical"
    assert alerta["message"] == "Pessoa no espaço confinado sem vigia na área de vigia"
    assert alerta["metadata"]["subject"] == "permissao_7" and alerta["metadata"]["pessoas_na_zona"] == ["person_1"]
    assert RuleAlert(**alerta).key == "sem_vigia:permissao_trabalho:permissao_7"


def test_varios_entrantes_geram_um_unico_sem_vigia_por_permissao():
    alertas = avaliar(avaliador(pt_com_vigia()), [pessoa(1), pessoa(2, x1=300, x2=400)])
    assert len(alertas) == 1 and alertas[0]["metadata"]["pessoas_na_zona"] == ["person_1", "person_2"]


def test_alguem_na_area_do_vigia_silencia_o_alerta():
    assert avaliar(avaliador(pt_com_vigia()), [pessoa(1), vigia_na_area(2)]) == []


def test_pessoa_na_area_do_vigia_nao_conta_como_entrante_mesmo_com_areas_sobrepostas():
    # O vigia também está "inside" da zona de risco (áreas sobrepostas), mas é vigia.
    av = avaliador(pt_com_vigia(epis_exigidos=["helmet"]))
    sozinho = vigia_na_area(2, dentro_da_zona=True) | {"ppe": {"helmet": {"status": "missing"}}}
    assert avaliar(av, [sozinho]) == []  # nem sem_vigia, nem EPI: não é entrante
    com_entrante = avaliar(av, [pessoa(1, ppe={"helmet": "ok"}), sozinho])
    assert com_entrante == []  # há vigia (ele mesmo) e o entrante está em dia


def test_pes_sao_o_centro_da_base_da_caixa_e_nao_o_centro_da_caixa():
    faixa_de_baixo = [[0.0, 0.8], [0.3, 0.8], [0.3, 1.0], [0.0, 1.0]]  # canto inferior esquerdo; o entrante pisa em x≈0,63
    # Caixa alta (y 100..500): o centro está em y≈0,56 (fora da faixa), os pés em y≈0,93 (dentro).
    alto = pessoa(2, x1=50, x2=150, y1=100, y2=500, dentro=False)
    assert servico.pe_normalizado(alto["box"], FRAME) == pytest.approx((100 / 960, 500 / 540))
    assert avaliar(avaliador(pt_com_vigia(area_vigia=faixa_de_baixo)), [pessoa(1), alto]) == []
    # Mesma caixa com os pés acima da faixa (y2=300 -> 0,56): não é vigia, e então falta vigia.
    suspenso = pessoa(2, x1=50, x2=150, y1=100, y2=300, dentro=False)
    assert len(avaliar(avaliador(pt_com_vigia(area_vigia=faixa_de_baixo)), [pessoa(1), suspenso])) == 1


def test_permissao_fora_da_janela_equivale_a_sem_permissao(app, contexto):
    criada = emitir(app, tipo="geral", epis_exigidos=[])
    servico.definir_zona_controlada(criada.camera_id, True, por="tec@fabrica.com")
    av = AvaliadorDePermissao()  # ligação real: cache + banco
    p = [pessoa(1)]
    dentro = av.avaliar(criada.camera_id, p, FRAME, T0 + timedelta(hours=1), set())
    assert dentro == []  # PT vigente: nenhum alerta (sem vigia e sem EPI exigidos)
    fora = av.avaliar(criada.camera_id, p, FRAME, T0 + timedelta(hours=5), set())
    assert [a["rule"] for a in fora] == ["sem_permissao_ativa"]
    servico.encerrar_permissao(criada.id, por="tec@fabrica.com", agora=T0 + timedelta(hours=2))
    encerrada = av.avaliar(criada.camera_id, p, FRAME, T0 + timedelta(hours=3), set())
    assert [a["rule"] for a in encerrada] == ["sem_permissao_ativa"]


def test_epi_exigido_detectavel_ausente_ou_incorreto_alerta():
    av = avaliador(pt_com_vigia(exige_vigia=False, area_vigia=None, epis_exigidos=["helmet", "vest"]))
    pessoas = [
        pessoa(1, ppe={"helmet": "missing", "vest": "ok"}),
        pessoa(2, x1=300, x2=400, ppe={"helmet": "incorrect", "vest": "missing"}),
        pessoa(3, x1=100, x2=200, ppe={"helmet": "ok", "vest": "ok"}),
        pessoa(4, dentro=False, ppe={"helmet": "missing"}),  # fora da zona: não é da conta da PT
    ]
    alertas = avaliar(av, pessoas)
    assert [(a["rule"], a["metadata"]["person_id"]) for a in alertas] == [
        ("permissao_helmet", "person_1"), ("permissao_helmet", "person_2"), ("permissao_vest", "person_2")]
    primeiro = alertas[0]
    assert primeiro["severity"] == "high"
    assert primeiro["message"] == "Sem Capacete exigido pela permissão nº PT-2026-0007 · Pessoa 1"
    assert primeiro["metadata"]["permissao_id"] == 7 and primeiro["metadata"]["status"] == "missing"
    assert alertas[1]["metadata"]["status"] == "incorrect"
    assert len({RuleAlert(**a).key for a in alertas}) == 3


def test_epi_nao_detectavel_nao_alerta_e_aparece_como_manual():
    permissao = pt_com_vigia(exige_vigia=False, area_vigia=None, epis_exigidos=["helmet", "gloves"])
    gente = [pessoa(1, ppe={"helmet": "ok", "gloves": "missing"})]  # "gloves" missing seria ruído: o modelo não vê luva
    assert avaliar(avaliador(permissao), gente, supported={"helmet"}) == []
    manuais = [i["epi"] for i in servico.checklist(permissao, {"helmet"}) if i["verificacao"] == "manual"]
    assert manuais == ["gloves"]


def test_epi_ausente_e_sem_vigia_geram_os_dois_alertas():
    av = avaliador(pt_com_vigia(epis_exigidos=["helmet"]))
    alertas = avaliar(av, [pessoa(1, ppe={"helmet": "missing"})])
    assert {a["rule"] for a in alertas} == {"sem_vigia", "permissao_helmet"}


# ================================================================ API =======
def test_sem_sessao_e_401(app):
    c = app.test_client()
    assert c.get("/api/permissoes").status_code == 401
    assert c.post("/api/permissoes", json={}).status_code == 401
    assert c.get(f"/api/cameras/{app.config['ID_PORTARIA']}/zona-controlada").status_code == 401


def test_operador_nao_cria_nem_encerra_nem_cancela(app):
    ana = entrar(app, "ana@fabrica.com")
    assert ana.post("/api/permissoes", json=corpo_http(app)).status_code == 403
    with app.app_context():
        criada = emitir_agora(app).id
    assert ana.post(f"/api/permissoes/{criada}/encerrar").status_code == 403
    assert ana.post(f"/api/permissoes/{criada}/cancelar").status_code == 403


def test_tecnico_cria_e_o_detalhe_traz_checklist_e_norma(app, monkeypatch):
    monkeypatch.setattr("app.api.permissoes._epis_suportados", lambda camera_id: {"helmet"})
    tec = entrar(app, "tec@fabrica.com")
    resposta = tec.post(
        "/api/permissoes",
        json=corpo_http(app, tipo="espaco_confinado", epis_exigidos=["helmet", "gloves"], exige_vigia=True, area_vigia=AREA_VIGIA),
    )
    assert resposta.status_code == 201
    corpo = resposta.get_json()
    assert corpo["status"] == "ativa" and corpo["vigente"] is True and corpo["criada_por"] == "tec@fabrica.com"
    assert corpo["numero"].startswith("PT-") and corpo["avisos"] == []
    assert [(i["epi"], i["verificacao"]) for i in corpo["checklist"]] == [("helmet", "automatica"), ("gloves", "manual")]
    assert corpo["norma"]["codigo"] == "NR-33" and corpo["norma"]["url"].startswith("https://www.gov.br/")
    detalhe = tec.get(f"/api/permissoes/{corpo['id']}").get_json()
    assert detalhe["norma"]["itens"] and detalhe["checklist"] == corpo["checklist"]
    assert "avisos" not in detalhe


def test_supervisor_tambem_cria(app):
    assert entrar(app, "sup@fabrica.com").post("/api/permissoes", json=corpo_http(app)).status_code == 201


def test_sem_modelo_o_checklist_da_api_e_todo_manual(app):
    tec = entrar(app, "tec@fabrica.com")
    corpo = tec.post("/api/permissoes", json=corpo_http(app)).get_json()  # DummyMonitor/sem worker: nada automático
    assert {i["verificacao"] for i in corpo["checklist"]} == {"manual"}


def test_api_valida_e_devolve_codigo_estavel(app):
    tec = entrar(app, "tec@fabrica.com")
    agora = utc_now()
    longa = tec.post("/api/permissoes", json=corpo_http(app, fim=(agora + timedelta(hours=30)).isoformat()))
    assert longa.status_code == 400 and longa.get_json()["code"] == "duracao_excedida"
    sem_area = tec.post("/api/permissoes", json=corpo_http(app, exige_vigia=True))
    assert sem_area.status_code == 400 and sem_area.get_json()["code"] == "area_vigia_obrigatoria"
    assert tec.post("/api/permissoes", json=corpo_http(app, camera_id=9999)).status_code == 404
    assert tec.post("/api/permissoes", data="isto nao e json", content_type="text/plain").status_code == 400


def test_encerrar_e_cancelar_pela_api_com_guarda_de_estado(app):
    tec = entrar(app, "tec@fabrica.com")
    a = tec.post("/api/permissoes", json=corpo_http(app)).get_json()
    b = tec.post("/api/permissoes", json=corpo_http(app)).get_json()
    encerrada = tec.post(f"/api/permissoes/{a['id']}/encerrar")
    assert encerrada.status_code == 200
    assert encerrada.get_json()["status"] == "encerrada" and encerrada.get_json()["vigente"] is False
    assert encerrada.get_json()["encerrada_por"] == "tec@fabrica.com"
    repetida = tec.post(f"/api/permissoes/{a['id']}/cancelar")
    assert repetida.status_code == 409 and repetida.get_json()["code"] == "permissao_nao_ativa"
    assert tec.post(f"/api/permissoes/{b['id']}/cancelar").get_json()["status"] == "cancelada"
    assert tec.post("/api/permissoes/9999/encerrar").status_code == 404
    # Histórico segue legível depois de encerrada/cancelada (ler ≠ usar).
    assert tec.get(f"/api/permissoes/{a['id']}").get_json()["status"] == "encerrada"
    assert tec.get("/api/permissoes?status=encerrada").get_json()["count"] == 1
    assert tec.get("/api/permissoes?status=ativa").get_json()["count"] == 0
    assert tec.get("/api/permissoes?status=qualquer").status_code == 400


def test_escopo_de_camera_do_operador_na_listagem_e_no_detalhe(app):
    portaria, almox = app.config["ID_PORTARIA"], app.config["ID_ALMOX"]
    with app.app_context():
        na_portaria = emitir_agora(app, camera_id=portaria).id
        no_almox = emitir_agora(app, camera_id=almox).id
    ana = entrar(app, "ana@fabrica.com")
    corpo = ana.get("/api/permissoes").get_json()
    assert [i["id"] for i in corpo["items"]] == [na_portaria]
    # ?camera_id= de outro setor não fura o escopo.
    assert [i["id"] for i in ana.get(f"/api/permissoes?camera_id={almox}").get_json()["items"]] == [na_portaria]
    assert ana.get(f"/api/permissoes/{na_portaria}").status_code == 200
    assert ana.get(f"/api/permissoes/{no_almox}").status_code == 404
    tec = entrar(app, "tec@fabrica.com")
    assert tec.get("/api/permissoes").get_json()["count"] == 2
    assert [i["id"] for i in tec.get(f"/api/permissoes?camera_id={almox}").get_json()["items"]] == [no_almox]


def test_operador_sem_setor_ve_lista_vazia(app):
    with app.app_context():
        AuthService().create_user(email="semsetor@fabrica.com", name="Sem Setor", password=SENHA, role=ROLE_OPERATOR)
        emitir_agora(app)
    assert entrar(app, "semsetor@fabrica.com").get("/api/permissoes").get_json() == {"items": [], "count": 0}


def test_zona_controlada_get_put_e_escopo(app):
    portaria, almox = app.config["ID_PORTARIA"], app.config["ID_ALMOX"]
    ana, tec = entrar(app, "ana@fabrica.com"), entrar(app, "tec@fabrica.com")
    assert ana.get(f"/api/cameras/{portaria}/zona-controlada").get_json() == {
        "camera_id": portaria, "exige_permissao": False, "atualizada_em": None}
    assert ana.get(f"/api/cameras/{almox}/zona-controlada").status_code == 404  # fora do setor
    assert ana.put(f"/api/cameras/{portaria}/zona-controlada", json={"exige_permissao": True}).status_code == 403
    assert tec.put(f"/api/cameras/{portaria}/zona-controlada", json={"exige_permissao": "sim"}).status_code == 400
    assert tec.put("/api/cameras/9999/zona-controlada", json={"exige_permissao": True}).status_code == 404
    ligada = tec.put(f"/api/cameras/{portaria}/zona-controlada", json={"exige_permissao": True})
    assert ligada.status_code == 200 and ligada.get_json()["exige_permissao"] is True
    assert ana.get(f"/api/cameras/{portaria}/zona-controlada").get_json()["exige_permissao"] is True
    with app.app_context():
        assert servico.zona_exige_permissao(portaria) is True  # PUT invalidou o cache
    assert tec.put(f"/api/cameras/{portaria}/zona-controlada", json={"exige_permissao": False}).status_code == 200
    with app.app_context():
        assert servico.zona_exige_permissao(portaria) is False
        assert EventLog.query.filter_by(event_type="zona_controlada_atualizada").count() == 2
