"""Seed da Gestão de EPIs (ES Sprint 4, F1.4 e F1.5): idempotente, determinístico e sem tocar o painel ao vivo.

Conta o que o contrato (docs/specs/es-sprint4-contrato-gestao.md) promete: 24 colaboradores, 10 itens de catálogo
(1 CA vencido, 2 a vencer), ~60 entregas, 15 ocorrências (4 abertas, 3 em tratamento) e 40 alertas históricos resolvidos.
Os testes injetam `dia` (o relógio do seed); só o corte de "24 horas" usa o relógio real, de propósito.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from app import create_app
from app.cli import gestao_cli
from app.config import TestConfig
from app.extensions import db
from app.models import Alert, Camera, Colaborador, EntregaEpi, EpiCatalogo, Ocorrencia
from app.services import gestao_epi as servico
from app.services import gestao_seed as seed

DIA = date(2026, 10, 23)
ESPERADO = {
    "colaboradores": 24, "epis": 10, "entregas": 60, "ocorrencias": 15, "alertas": 40,
}


@pytest.fixture()
def app(tmp_path):
    class Config(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'gestao-seed.db'}"
        AUTO_CREATE_TABLES = True

    app = create_app(Config)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _contagens() -> dict[str, int]:
    return {
        "colaboradores": Colaborador.query.count(), "epis": EpiCatalogo.query.count(), "entregas": EntregaEpi.query.count(),
        "ocorrencias": Ocorrencia.query.count(), "alertas": Alert.query.count(),
    }


def _foto() -> dict:
    """Tudo o que o seed grava, em dados comparáveis (sem ids)."""
    return {
        "colaboradores": sorted((c.matricula, c.nome, c.setor, c.funcao, c.admissao.isoformat()) for c in Colaborador.query),
        "epis": sorted((e.ca, e.nome, e.validade_ca.isoformat()) for e in EpiCatalogo.query),
        "entregas": sorted((e.codigo, e.colaborador.matricula, e.epi.ca, e.entregue_em.isoformat(),
                            e.devolvido_em.isoformat() if e.devolvido_em else "", e.motivo) for e in EntregaEpi.query),
        "ocorrencias": sorted((o.codigo, o.tipo, o.status, o.ocorrida_em.isoformat()) for o in Ocorrencia.query),
        "alertas": sorted((a.metadata_json["seed_id"], a.rule, a.created_at.isoformat()) for a in Alert.query),
    }


def test_primeira_execucao_cria_o_que_o_contrato_promete(app):
    resultado = seed.semear(dia=DIA)
    assert {k: v["criados"] for k, v in resultado.items()} == ESPERADO
    assert all(v["existentes"] == 0 for v in resultado.values())
    assert _contagens() == ESPERADO


def test_rodar_duas_vezes_nao_duplica_nada(app):
    seed.semear(dia=DIA)
    antes = _foto()
    segunda = seed.semear(dia=DIA)
    assert {k: v["criados"] for k, v in segunda.items()} == dict.fromkeys(ESPERADO, 0)
    assert {k: v["existentes"] for k, v in segunda.items()} == ESPERADO
    assert _contagens() == ESPERADO and _foto() == antes


def test_rodar_em_outro_dia_nao_duplica_nem_mexe_no_que_existe(app):
    """Chave natural: matrícula, CA, código, seed_id. As datas relativas ficam as da primeira vez."""
    seed.semear(dia=DIA)
    antes = _foto()
    seed.semear(dia=DIA + timedelta(days=40))
    assert _contagens() == ESPERADO and _foto() == antes


def test_completa_so_o_que_falta_e_preserva_edicao_manual(app):
    seed.semear(dia=DIA)
    Colaborador.query.filter_by(matricula="MI-0001").one().nome = "Nome editado à mão"
    Ocorrencia.query.filter_by(codigo="SEED-OCO-0001").delete()
    db.session.commit()
    resultado = seed.semear(dia=DIA)
    assert resultado["ocorrencias"] == {"criados": 1, "existentes": 14, "ignorados": 0}
    assert resultado["colaboradores"]["criados"] == 0
    assert Colaborador.query.filter_by(matricula="MI-0001").one().nome == "Nome editado à mão"
    assert _contagens() == ESPERADO


def test_e_deterministico_mesma_entrada_mesmo_resultado(app):
    assert seed.montar_plano(DIA, [1, 2, 3]) == seed.montar_plano(DIA, [1, 2, 3])
    plano = seed.montar_plano(DIA, [1, 2, 3])
    assert plano.colaboradores[0] == seed.montar_plano(DIA, []).colaboradores[0]
    assert [c["matricula"] for c in plano.colaboradores][:3] == ["MI-0001", "MI-0002", "MI-0003"]


def test_conteudo_do_catalogo_e_das_entregas(app):
    seed.semear(dia=DIA)
    epis = EpiCatalogo.query.all()
    situacoes = [e.situacao_ca(DIA) for e in epis]
    assert (situacoes.count("vencido"), situacoes.count("a_vencer"), situacoes.count("valido")) == (1, 2, 7)
    assert all(e.ficticio and 900000 <= int(e.ca) <= 999999 and e.fabricante.startswith("Fabricante Fictício ") for e in epis)
    assert {e.categoria for e in epis} <= {"helmet", "vest", "gloves", "glasses", "mask", "safety_shoe", "ear_protection", "outro"}
    entregas = EntregaEpi.query.all()
    situacao = [e.situacao(DIA) for e in entregas]
    assert situacao.count("devolvido") == 6 and situacao.count("troca_vencida") == 8
    assert all(DIA - timedelta(days=365) <= e.entregue_em <= DIA for e in entregas)  # últimos 12 meses
    assert all(e.troca_prevista_em == e.entregue_em + timedelta(days=e.epi.vida_util_dias) for e in entregas)
    assert all(e.ficticio and e.registrado_por == seed.REGISTRADO_POR for e in entregas)
    assert len({e.codigo for e in entregas}) == 60 and all(e.codigo.startswith("SEED-ENT-") for e in entregas)
    devolvidas = [e for e in entregas if e.devolvido_em]
    assert all(e.devolvido_em >= e.entregue_em for e in devolvidas)
    substituicoes = [e for e in entregas if e.motivo in ("substituicao", "dano", "perda")]
    assert len(substituicoes) >= 6  # cada devolução por substituição tem a entrega nova no histórico


def test_conteudo_dos_colaboradores_e_das_ocorrencias(app):
    seed.semear(dia=DIA)
    colaboradores = Colaborador.query.all()
    assert {c.setor for c in colaboradores} == {"Obra", "Expedição", "Manutenção", "Portaria", "Usinagem", "Almoxarifado"}
    assert all(c.ficticio and c.ativo for c in colaboradores) and len({c.nome for c in colaboradores}) == 24
    assert all(c.admissao < DIA for c in colaboradores)
    ocorrencias = Ocorrencia.query.all()
    por_status = [o.status for o in ocorrencias]
    assert (por_status.count("aberta"), por_status.count("em_tratamento"), por_status.count("encerrada")) == (4, 3, 8)
    assert len({o.tipo for o in ocorrencias}) == 4 and len({o.gravidade for o in ocorrencias}) == 4
    assert all(o.acao_corretiva and o.encerrada_em for o in ocorrencias if o.status == "encerrada")
    assert all(o.encerrada_em is None for o in ocorrencias if o.status != "encerrada")
    assert all(o.ficticio for o in ocorrencias) and all(o.alerta_id is None for o in ocorrencias)
    limite = datetime.combine(DIA - timedelta(days=90), datetime.min.time()).astimezone(timezone.utc)
    assert all(o.ocorrida_em.replace(tzinfo=timezone.utc) >= limite for o in ocorrencias)


def test_alertas_historicos_sao_resolvidos_marcados_e_nenhum_nas_ultimas_24h(app):
    """O painel ao vivo não muda: nada `active`, nada recente, marcado como simulado. Usa o relógio REAL: o seed roda com `hoje`."""
    db.session.add_all([Camera(name="A", location="Obra", source="0"), Camera(name="B", location="Portaria", source="1")])
    db.session.commit()
    ids_das_cameras = {c.id for c in Camera.query.all()}
    seed.semear(dia=date.today())
    alertas = Alert.query.all()
    assert len(alertas) == 40 and {a.status for a in alertas} == {"resolved"}
    assert Alert.query.filter_by(status="active").count() == 0
    corte = datetime.now(timezone.utc) - timedelta(hours=24)
    assert all(a.created_at.replace(tzinfo=timezone.utc) < corte for a in alertas)
    assert all(a.last_seen_at.replace(tzinfo=timezone.utc) < corte for a in alertas)
    assert all(a.resolved_at is not None for a in alertas)
    mais_novo = max(a.created_at.replace(tzinfo=timezone.utc) for a in alertas)
    mais_velho = min(a.created_at.replace(tzinfo=timezone.utc) for a in alertas)
    assert datetime.now(timezone.utc) - mais_novo >= timedelta(days=1) and datetime.now(timezone.utc) - mais_velho <= timedelta(days=31)
    assert all(a.metadata_json["simulado"] is True and a.metadata_json["seed_id"].startswith("SEED-ALR-") for a in alertas)
    assert len({a.metadata_json["seed_id"] for a in alertas}) == 40
    assert {a.camera_id for a in alertas} <= ids_das_cameras and None not in {a.camera_id for a in alertas}
    regras = {(a.rule, a.feature) for a in alertas}
    assert regras <= {("missing_helmet", "helmet"), ("missing_vest", "vest"), ("missing_gloves", "gloves"),
                      ("risk_area_presence", "risk_area"), ("fall_detected", "falls")}
    assert len(regras) >= 4


def test_sem_camera_o_alerta_historico_fica_sem_camera(app):
    seed.semear(dia=DIA)
    assert Camera.query.count() == 0 and {a.camera_id for a in Alert.query.all()} == {None}


def test_seed_nao_cria_incidente_nem_evento(app):
    """Não passa pelo estado de alertas: sem incidente, sem log de evento, sem nada que o painel ao vivo leia."""
    from app.models import EventLog, Incidente

    seed.semear(dia=DIA)
    assert Incidente.query.count() == 0 and EventLog.query.count() == 0


def test_nada_do_seed_liga_pessoa_a_rastreio_ou_imagem(app):
    seed.semear(dia=DIA)
    colunas = {c.name for modelo in (Colaborador, EntregaEpi, Ocorrencia) for c in modelo.__table__.columns}
    assert not {c for c in colunas if "person" in c or "track" in c or "camera" in c or "frame" in c or "snapshot" in c or "cpf" in c}


def test_resumo_da_api_apos_o_seed_bate_com_o_contrato(app):
    seed.semear(dia=DIA)
    resumo = servico.resumo(DIA, datetime.combine(DIA, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=12))
    assert resumo["colaboradores_ativos"] == 24 and resumo["epis_no_catalogo"] == 10
    assert resumo["cas_vencidos"] == 1 and resumo["cas_a_vencer"] == 2 and resumo["simulados"] is True
    assert resumo["ocorrencias_abertas"] == 4 and resumo["trocas_vencidas"] == 8
    assert resumo["entregas_vigentes"] + resumo["trocas_vencidas"] == 60 - 6  # o resto das 60 foi devolvido


def test_comando_semear_recusa_fora_do_modo_demo_sem_a_flag_explicita(app):
    runner = app.test_cli_runner()
    assert not app.config.get("DEMO_MODE")
    recusado = runner.invoke(gestao_cli, ["semear"])
    assert recusado.exit_code != 0 and "--dados-ficticios" in recusado.output and "FICTÍCIOS" in recusado.output
    assert "40 alertas" in recusado.output
    assert _contagens() == dict.fromkeys(ESPERADO, 0)  # nada foi gravado


def test_comando_semear_imprime_criados_e_existentes_e_e_idempotente(app):
    runner = app.test_cli_runner()
    primeiro = runner.invoke(gestao_cli, ["semear", "--dados-ficticios"])
    assert primeiro.exit_code == 0, primeiro.output
    assert "colaboradores" in primeiro.output and "criados:  24" in primeiro.output and "149 registro(s) criado(s)" in primeiro.output
    segundo = runner.invoke(gestao_cli, ["semear", "--dados-ficticios"])
    assert segundo.exit_code == 0 and "0 registro(s) criado(s)" in segundo.output and "já existiam:  24" in segundo.output
    assert _contagens() == ESPERADO


def test_comando_semear_roda_sem_a_flag_no_modo_demo(app):
    app.config["DEMO_MODE"] = True
    assert app.test_cli_runner().invoke(gestao_cli, ["semear"]).exit_code == 0
    assert _contagens() == ESPERADO


def test_registro_real_com_a_mesma_chave_e_ignorado_e_nada_do_seed_e_pendurado_nele(app):
    """Matrícula/CA que já existem como registro REAL ficam como estão; entregas e ocorrências do seed não se ligam a eles."""
    real_c = Colaborador(matricula="MI-0001", nome="Pessoa Real", setor="Obra", funcao="Cargo real", admissao=DIA, ficticio=False)
    real_e = EpiCatalogo(nome="Capacete real", categoria="helmet", ca="900101", validade_ca=DIA, fabricante="Fabricante real",
                         vida_util_dias=10, ficticio=False)
    db.session.add_all([real_c, real_e])
    db.session.commit()
    resultado = seed.semear(dia=DIA)
    assert resultado["colaboradores"] == {"criados": 23, "existentes": 0, "ignorados": 1}
    assert resultado["epis"] == {"criados": 9, "existentes": 0, "ignorados": 1}
    assert resultado["entregas"]["ignorados"] > 0 and resultado["entregas"]["criados"] + resultado["entregas"]["ignorados"] == 60
    assert real_c.nome == "Pessoa Real" and real_c.ficticio is False and real_e.nome == "Capacete real"
    assert EntregaEpi.query.filter_by(colaborador_id=real_c.id).count() == 0 and EntregaEpi.query.filter_by(epi_id=real_e.id).count() == 0
    assert Ocorrencia.query.filter_by(colaborador_id=real_c.id).count() == 0
    assert Ocorrencia.query.count() == 15  # ocorrência simulada nasce sem vínculo em vez de ser descartada
    # de novo: mesma resposta, nada novo
    de_novo = seed.semear(dia=DIA)
    assert {k: v["criados"] for k, v in de_novo.items()} == dict.fromkeys(ESPERADO, 0)


def test_realismo_das_entregas_ninguem_recebe_antes_de_ser_admitido_e_admissao_so_no_primeiro_mes(app):
    seed.semear(dia=DIA)
    for entrega in EntregaEpi.query.all():
        dias = (entrega.entregue_em - entrega.colaborador.admissao).days
        assert dias >= 0, entrega.codigo
        if entrega.motivo == "admissao":
            assert dias <= 30, entrega.codigo
    motivos = {e.motivo for e in EntregaEpi.query.all()}
    assert "admissao" in motivos and motivos & {"substituicao", "perda", "dano"}
    assert all(e.ca_na_entrega == e.epi.ca and e.epi_nome_na_entrega == e.epi.nome for e in EntregaEpi.query.all())  # congelado


def test_risco_ao_vivo_ignora_alerta_simulado(app):
    """O painel de risco não pode mudar por causa do seed: o simulado nunca entra na conta, mesmo dentro da janela."""
    from app.models import utc_now
    from app.services import risk_score_service as risco

    agora = utc_now()
    depois = agora + timedelta(minutes=1)
    db.session.add(Alert(rule="missing_helmet", severity="critical", message="simulado", feature="helmet", created_at=agora,
                         last_seen_at=agora, metadata_json={"simulado": True, "seed_id": "SEED-ALR-9999"}))
    db.session.commit()
    so_simulado = risco.compute_risk_score(now=depois)
    assert so_simulado["overall"]["alert_count"] == 0 and so_simulado["overall"]["score"] == 0.0
    assert all(b["overall"]["score"] == 0.0 for b in risco.compute_risk_trend(hours=2, now=depois)["buckets"])
    db.session.add(Alert(rule="missing_helmet", severity="critical", message="real", feature="helmet",
                         created_at=agora, last_seen_at=agora))
    db.session.commit()
    com_real = risco.compute_risk_score(now=depois)
    assert com_real["overall"]["alert_count"] == 1 and com_real["features"]["helmet"]["alert_count"] == 1
    assert any(b["overall"]["score"] > 0 for b in risco.compute_risk_trend(hours=2, now=depois)["buckets"])


def test_relatorio_mensal_conta_tudo_mas_avisa_quantos_alertas_sao_simulados(app):
    from app.services import relatorio_mensal as rm

    marco = datetime(2026, 3, 10, 12, tzinfo=timezone.utc)
    db.session.add_all([
        Alert(rule="missing_helmet", severity="high", message="Sem capacete · Pessoa 1", feature="helmet", status="resolved",
              created_at=marco, first_seen_at=marco, last_seen_at=marco),
        Alert(rule="missing_helmet", severity="high", message="Sem capacete · Pessoa 2", feature="helmet", status="resolved",
              created_at=marco, first_seen_at=marco, last_seen_at=marco, metadata_json={"simulado": True, "seed_id": "SEED-ALR-9999"}),
    ])
    db.session.commit()
    relatorio = rm.montar_relatorio_mensal(2026, 3, visao_da_planta=False)
    assert relatorio["alertas"]["total"] == 2 and relatorio["alertas_simulados"] == 1 and relatorio["alertas"]["simulados"] == 1
    assert "Este relatório inclui 1 alerta simulado (histórico de demonstração, sem vídeo)." in rm.renderizar_html(relatorio)
    sem_simulado = rm.montar_relatorio_mensal(2026, 4, visao_da_planta=False)
    assert sem_simulado["alertas_simulados"] == 0 and "alerta simulado" not in rm.renderizar_html(sem_simulado)
    db.session.query(Alert).filter(Alert.message.like("%Pessoa 1")).delete()
    db.session.commit()
    todos_simulados = rm.renderizar_html(rm.montar_relatorio_mensal(2026, 3, visao_da_planta=False))
    assert "1 alerta simulado" in todos_simulados


def test_filtro_unico_de_alertas_simulados_separa_reais_e_simulados(app):
    from app.services.alertas_simulados import e_simulado, sem_simulados, so_simulados

    db.session.add_all([
        Alert(rule="r", severity="low", message="sem metadados", feature="helmet"),
        Alert(rule="r", severity="low", message="falso", feature="helmet", metadata_json={"simulado": False}),
        Alert(rule="r", severity="low", message="outro campo", feature="helmet", metadata_json={"false_positive": True}),
        Alert(rule="r", severity="low", message="simulado", feature="helmet", metadata_json={"simulado": True}),
    ])
    db.session.commit()
    assert sorted(a.message for a in sem_simulados(Alert.query)) == ["falso", "outro campo", "sem metadados"]
    assert [a.message for a in so_simulados(Alert.query)] == ["simulado"]
    assert [e_simulado(a) for a in Alert.query.order_by(Alert.id)] == [False, False, False, True]


def test_registro_pela_flask_cli_do_app(app):
    assert "gestao" in app.cli.commands and "semear" in app.cli.commands["gestao"].commands
