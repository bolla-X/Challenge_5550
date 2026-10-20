"""Liga de Setores, missões e nível da planta (X8) + Retrospectiva (X7)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import Camera, Missao, PontoDaLiga
from app.services import liga, retrospectiva
from app.services.andon import ContadorDeMinutos

AGORA = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)


def _cameras():
    db.session.add_all([Camera(name="Pátio", location="Expedição", source_type="USB", source="0"),
                        Camera(name="Canteiro", location="Obra", source_type="USB", source="1")])
    db.session.commit()


def test_so_existe_ponto_positivo():
    assert all(v > 0 for v in liga.PONTOS.values())
    assert not any("alerta" in k and "zero" in k for k in liga.PONTOS)


def test_mesmo_fato_nao_conta_duas_vezes(app):
    with app.app_context():
        _cameras()
        assert liga.registrar("checkin_portal", ref="evento:1", camera_id=1) is not None
        assert liga.registrar("checkin_portal", ref="evento:1", camera_id=1) is None
        assert PontoDaLiga.query.count() == 1
        assert PontoDaLiga.query.one().setor == "Expedição"


def test_placar_da_temporada_por_setor_inclui_setor_sem_ponto(app):
    with app.app_context():
        _cameras()
        liga.registrar("checkin_portal", ref="e:1", camera_id=1, quando=AGORA)
        liga.registrar("rotulo", ref="r:1", camera_id=2, quando=AGORA)
        liga.registrar("rotulo", ref="r:velho", camera_id=2, quando=AGORA - timedelta(days=14))  # outra temporada
        inicio, fim = liga.temporada(AGORA)
        placar = liga.placar(inicio, fim)
        assert [(s["setor"], s["pontos"]) for s in placar] == [("Expedição", 10), ("Obra", 2)]


def test_nivel_da_planta():
    assert liga.nivel(0)["nivel"] == 1
    assert liga.nivel(99)["nivel"] == 1 and liga.nivel(100)["nivel"] == 2
    assert liga.nivel(300)["nivel"] == 3 and liga.nivel(1000)["nivel"] == 5
    n = liga.nivel(150)
    assert n["xp_do_nivel"] == 100 and n["xp_do_proximo"] == 300 and n["progresso"] == 0.25


def test_reconhecimento_so_soma():
    assert liga.pontos_do_reconhecimento(20) == "reconhecido_rapido"
    assert liga.pontos_do_reconhecimento(120) == "reconhecido"
    assert liga.pontos_do_reconhecimento(900) is None  # demorar não tira ponto, só não ganha


def test_missao_do_turno_com_hora_limite(app):
    with app.app_context():
        _cameras()
        t = liga.turno(AGORA, "06:00-14:00,14:00-22:00,22:00-06:00")
        corte = (t["inicio"].astimezone() + timedelta(hours=1)).strftime("%H:%M")
        m = Missao(titulo="2 check-ins até 16h", tipo="checkin_portal", alvo=2, ate_hora=corte)
        db.session.add(m)
        db.session.commit()
        liga.registrar("checkin_portal", ref="a", camera_id=1, quando=t["inicio"] + timedelta(minutes=10))
        liga.registrar("checkin_portal", ref="b", camera_id=1, quando=t["inicio"] + timedelta(minutes=90))  # depois do limite
        pontos = liga._pontos_entre(t["inicio"], t["fim"])
        p = liga.progresso_da_missao(m, t["inicio"], t["fim"], pontos)
        assert p["feito"] == 1 and not p["cumprida"]
        liga.registrar("checkin_portal", ref="c", camera_id=1, quando=t["inicio"] + timedelta(minutes=20))
        p = liga.progresso_da_missao(m, t["inicio"], t["fim"], liga._pontos_entre(t["inicio"], t["fim"]))
        assert p["cumprida"] and p["progresso"] == 1.0


def test_minuto_conforme_com_gente_vira_ponto_e_minuto_vazio_e_neutro():
    fechados = []
    c = ContadorDeMinutos()
    c.ao_fechar_conforme = fechados.append
    gente_ok = [{"ppe": {"helmet": {"status": "ok"}}}]
    c.registrar(gente_ok, ["helmet"], 60.0)
    c.registrar([], ["helmet"], 120.0)  # fecha o minuto 1 (conforme, com gente)
    c.registrar([], ["helmet"], 180.0)  # fecha o minuto 2 (vazio: neutro)
    assert fechados == [1]


def test_retrospectiva_sem_dado_nao_inventa_numero(app):
    with app.app_context():
        _cameras()
        r = retrospectiva.montar("turno", AGORA)
        por_chave = {c["chave"]: c for c in r["cards"]}
        assert por_chave["conformidade"]["valor"] == 0
        assert por_chave["destaque"]["valor"] == "Sem dado"
        assert por_chave["reconhecimento"]["valor"] == "Sem dado"
        assert "Pessoa" not in str(r)


def test_retrospectiva_da_semana_com_dados(app):
    with app.app_context():
        _cameras()
        for i in range(90):
            liga.registrar("minuto_conforme", ref=f"1:{i}", camera_id=1, quando=AGORA - timedelta(minutes=i + 1))
        liga.registrar("rotulo", ref="r1", camera_id=2, quando=AGORA - timedelta(minutes=5))
        r = retrospectiva.montar("semana", AGORA)
        por_chave = {c["chave"]: c for c in r["cards"]}
        assert por_chave["conformidade"]["valor"] == 1.5
        assert por_chave["destaque"]["valor"] == "Expedição"
        assert por_chave["rotulos"]["valor"] == 1


def test_api_liga_e_missoes(app, client):
    with app.app_context():
        _cameras()
    r = client.post("/api/liga/missoes", json={"titulo": "Revisar 20 rótulos", "tipo": "rotulo", "alvo": 20})
    assert r.status_code == 201
    assert client.post("/api/liga/missoes", json={"titulo": "x", "tipo": "zero_alertas", "alvo": 1}).status_code == 400
    estado = client.get("/api/liga").get_json()
    assert estado["missoes"][0]["titulo"] == "Revisar 20 rótulos"
    assert {s["setor"] for s in estado["setores"]} == {"Expedição", "Obra"}
    assert client.get("/api/retrospectiva?periodo=semana").status_code == 200


def test_retrospectiva_conta_a_missao_cumprida_mesmo_depois_de_apagada(app):
    """Apagar uma missão hoje não reescreve o passado: o turno em que ela foi cumprida continua contando."""
    with app.app_context():
        _cameras()
        t = liga.turno(AGORA, "06:00-14:00,14:00-22:00,22:00-06:00")
        m = Missao(titulo="1 check-in", tipo="checkin_portal", alvo=1, criado_em=t["inicio"] - timedelta(hours=1))
        db.session.add(m)
        db.session.commit()
        liga.registrar("checkin_portal", ref="a", camera_id=1, quando=t["inicio"] + timedelta(minutes=10))
        antes = {c["chave"]: c for c in retrospectiva.montar("turno", AGORA)["cards"]}["missoes"]
        assert antes["valor"] == 1, antes
        liga.desativar_missao(m)
        depois = {c["chave"]: c for c in retrospectiva.montar("turno", AGORA)["cards"]}["missoes"]
        assert depois["valor"] == 1, depois
        assert depois["detalhe"] != "Nenhuma missão configurada pelo supervisor", depois


def test_retrospectiva_nao_conta_missao_em_turno_anterior_a_criacao(app):
    """Missão criada hoje não vale para os turnos de dias atrás, mesmo que os pontos daquele turno a cumprissem."""
    with app.app_context():
        _cameras()
        dois_dias = AGORA - timedelta(days=2)
        liga.registrar("checkin_portal", ref="velho", camera_id=1, quando=dois_dias)
        db.session.add(Missao(titulo="1 check-in", tipo="checkin_portal", alvo=1, criado_em=AGORA - timedelta(minutes=1)))
        db.session.commit()
        cartao = {c["chave"]: c for c in retrospectiva.montar("semana", AGORA)["cards"]}["missoes"]
        assert cartao["valor"] == 0, cartao
