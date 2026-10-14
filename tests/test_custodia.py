"""Cadeia de custódia das evidências (X3, MISSÃO 2).

O teste obrigatório da missão: adulterar 1 byte de um clipe faz a verificação
apontar EXATAMENTE o elo quebrado.
"""

from __future__ import annotations

from pathlib import Path

from app.extensions import db
from app.models import Alert, ElodeCustodia, EventLog
from app.repositories.alert_repository import AlertRepository
from app.services import custodia


def _alerta(n: int = 1) -> Alert:
    return AlertRepository().create(rule="missing_helmet", severity="critical", message=f"Sem capacete — Pessoa {n}",
                                    feature="helmet", metadata={"person_id": f"person_{n}"}, camera_id=2)


def _clipe(pasta: Path, alert_id: int, quadros: int = 3) -> Path:
    destino = pasta / f"alert_{alert_id}"
    destino.mkdir(parents=True)
    for i in range(quadros):
        (destino / f"{i:04d}.jpg").write_bytes(bytes([0xFF, 0xD8, i, 1, 2, 3, 4, 0xFF, 0xD9]))
    (destino / "clip.json").write_text('{"alert_id": %d, "total": %d}' % (alert_id, quadros), encoding="utf-8")
    return destino


def _cadeia(app, tmp_path):
    with app.app_context():
        a1 = _alerta(1)
        custodia.registrar_alerta(a1)
        snap = tmp_path / "snap_1.jpg"
        snap.write_bytes(b"\xff\xd8snapshot\xff\xd9")
        custodia.registrar_snapshot(a1, snap)
        clipe = _clipe(tmp_path / "clips", a1.id)
        custodia.registrar_clipe(a1.id, 2, clipe)
        ev = EventLog(camera_id=2, event_type="privacy_toggled", message="Privacidade DESLIGADA por sup@x", subject="sup@x",
                      metadata_json={"ativa": False})
        db.session.add(ev)
        db.session.commit()
        custodia.registrar_evento(ev)
        a2 = _alerta(2)
        custodia.registrar_alerta(a2)
        return {"a1": a1.id, "a2": a2.id, "clipe": clipe, "snap": snap, "evento": ev.id}


def test_cadeia_integra_e_encadeada(app, tmp_path):
    _cadeia(app, tmp_path)
    with app.app_context():
        r = custodia.verificar()
        assert r["integra"] and not r["adulterada"]
        assert [e["tipo"] for e in r["elos"]] == ["alerta", "snapshot", "clipe", "privacidade", "alerta"]
        elos = ElodeCustodia.query.order_by(ElodeCustodia.id).all()
        assert elos[0].anterior_sha256 == custodia.GENESE
        assert all(b.anterior_sha256 == a.elo_sha256 for a, b in zip(elos, elos[1:], strict=False))
        assert r["ultimo_elo"] == elos[-1].elo_sha256


def test_um_byte_adulterado_no_clipe_aponta_exatamente_o_elo_do_clipe(app, tmp_path):
    ids = _cadeia(app, tmp_path)
    quadro = ids["clipe"] / "0001.jpg"
    dados = bytearray(quadro.read_bytes())
    dados[3] ^= 0x01  # um bit de um byte
    quadro.write_bytes(bytes(dados))
    with app.app_context():
        r = custodia.verificar()
        assert r["adulterada"] and not r["integra"]
        quebrado = r["quebrado"]
        assert quebrado["tipo"] == "clipe" and quebrado["id"] == 3
        assert quebrado["situacao"] == "conteudo_alterado"
        assert quebrado["arquivo"] == "0001.jpg"
        # Os outros elos continuam ok: só UM foi apontado.
        problemas = [e for e in r["elos"] if e["situacao"] != "ok"]
        assert [e["id"] for e in problemas] == [3]


def test_alterar_a_linha_da_cadeia_no_banco_e_detectado(app, tmp_path):
    _cadeia(app, tmp_path)
    with app.app_context():
        elo = db.session.get(ElodeCustodia, 2)
        elo.conteudo_sha256 = "0" * 64  # tenta "acertar" o hash depois de trocar o snapshot
        db.session.commit()
        r = custodia.verificar()
        assert r["quebrado"]["id"] == 2 and r["quebrado"]["situacao"] == "registro_alterado"


def test_remover_um_elo_quebra_a_cadeia_no_seguinte(app, tmp_path):
    _cadeia(app, tmp_path)
    with app.app_context():
        db.session.delete(db.session.get(ElodeCustodia, 2))
        db.session.commit()
        r = custodia.verificar()
        assert r["quebrado"]["id"] == 3 and r["quebrado"]["situacao"] == "cadeia_quebrada"


def test_alerta_editado_no_banco_e_detectado(app, tmp_path):
    ids = _cadeia(app, tmp_path)
    with app.app_context():
        db.session.get(Alert, ids["a2"]).severity = "low"
        db.session.commit()
        r = custodia.verificar()
        assert r["quebrado"]["id"] == 5 and r["quebrado"]["situacao"] == "conteudo_alterado"


def test_evidencia_apagada_e_ausente_nao_adulterada(app, tmp_path):
    ids = _cadeia(app, tmp_path)
    ids["snap"].unlink()
    with app.app_context():
        r = custodia.verificar()
        assert not r["integra"] and not r["adulterada"] and r["ausentes"] == 1


def test_verificar_so_as_evidencias_de_um_incidente(app, tmp_path):
    ids = _cadeia(app, tmp_path)
    with app.app_context():
        r = custodia.verificar(alert_ids={ids["a2"]})
        assert r["integra"] and [e["ref"] for e in r["elos"]] == [f"alerta:{ids['a2']}"]


def test_alerta_criado_pelo_servico_entra_na_cadeia(app):
    from app.services.alert_state_service import AlertStateService
    from app.services.risk_rules import RuleAlert

    class _Socket:
        def emit(self, *a, **k):
            pass

    with app.app_context():
        s = AlertStateService(AlertRepository(), _Socket(), create_after_frames=1, camera_id=1)
        s.process([RuleAlert("missing_vest", "critical", "Sem colete — Pessoa 1", "vest", {"person_id": "person_1"})])
        elo = ElodeCustodia.query.one()
        assert elo.tipo == "alerta" and custodia.verificar()["integra"]


def test_api_verifica_por_incidente_e_tudo(app, client, tmp_path):
    from app.models import Incidente

    ids = _cadeia(app, tmp_path)
    with app.app_context():
        inc = Incidente(camera_id=2, rule="missing_helmet", feature="helmet", zona="Zona A", severity="critical",
                        titulo="Sem capacete", status="resolved", pessoas=[1], alert_ids=[ids["a1"]], pico_pessoas=1)
        db.session.add(inc)
        db.session.commit()
        inc_id = inc.id
    r = client.get(f"/api/custodia/verificar?incidente_id={inc_id}").get_json()
    assert r["integra"] and {e["tipo"] for e in r["elos"]} == {"alerta", "snapshot", "clipe"}
    tudo = client.get("/api/custodia/verificar").get_json()
    assert tudo["elos_na_cadeia"] == 5


def _lote(app, tmp_path):
    """Três alertas da mesma análise: um quadro e um replay para todos."""
    from app.services.replay import ClipePendente, QuadroDeReplay, gravar_clipe

    with app.app_context():
        alertas = [_alerta(n) for n in (1, 2, 3)]
        snap = tmp_path / "lote.jpg"
        snap.write_bytes(b"\xff\xd8lote\xff\xd9")
        custodia.registrar_snapshot(alertas[0], snap, alert_ids=[a.id for a in alertas])
        quadros = [QuadroDeReplay(ts_ms=i * 100.0, jpeg=bytes([0xFF, 0xD8, i, 0xFF, 0xD9]), overlay=None, escala=1.0)
                   for i in range(3)]
        pendente = ClipePendente(alert_id=alertas[0].id, t0_ms=100.0, inicio_ms=0.0, fim_ms=300.0, alerta={"rule": "missing_helmet"},
                                 acompanhantes=[{"id": a.id, "rule": a.rule} for a in alertas[1:]])
        clipe = gravar_clipe(tmp_path / "clips", pendente, quadros, camera_id=2)
        custodia.registrar_clipe(alertas[0].id, 2, [Path(x) for x in clipe["pastas"]], alert_ids=[a.id for a in alertas])
        return [a.id for a in alertas], tmp_path / "clips"


def test_evidencia_compartilhada_entra_na_verificacao_de_cada_alerta(app, tmp_path):
    ids, _ = _lote(app, tmp_path)
    with app.app_context():
        assert ElodeCustodia.query.count() == 2, "um elo para o quadro e um para o replay, não um por alerta"
        r = custodia.verificar(alert_ids={ids[2]})
        assert r["integra"] and {e["tipo"] for e in r["elos"]} == {"snapshot", "clipe"}


def test_indice_adulterado_de_um_acompanhante_quebra_o_elo_do_replay(app, tmp_path):
    ids, clips = _lote(app, tmp_path)
    indice = clips / f"alert_{ids[1]}" / "clip.json"
    indice.write_text(indice.read_text(encoding="utf-8").replace("missing_helmet", "missing_vest"), encoding="utf-8")
    with app.app_context():
        r = custodia.verificar()
        assert r["quebrado"]["tipo"] == "clipe" and r["quebrado"]["situacao"] == "conteudo_alterado"
        assert r["quebrado"]["arquivo"] == f"alert_{ids[1]}/clip.json"


def test_api_serve_quadro_do_acompanhante_pela_pasta_do_primeiro(app, client, tmp_path):
    ids, clips = _lote(app, tmp_path)
    app.config["REPLAY_DIR"] = str(clips)
    r = client.get(f"/api/alerts/{ids[2]}/clip/1.jpg")
    assert r.status_code == 200 and r.data == bytes([0xFF, 0xD8, 1, 0xFF, 0xD9])
    assert client.get(f"/api/alerts/{ids[2]}/clip").get_json()["quadros_em"] == f"alert_{ids[0]}"
