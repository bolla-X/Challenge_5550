"""Ações em lote sobre alertas: resolver ativos, reconhecer todos, apagar resolvidos.

A regra que organiza tudo: alerta é auditoria de segurança, então apagar só é
possível para o que já foi RESOLVIDO. Ativo nunca é tocado por um "apagar".
"""
from __future__ import annotations

from app.extensions import db
from app.models import Alert
from app.repositories.alert_repository import AlertRepository


def _alerta(camera_id=1, status="active", feature="helmet", severity="critical", frame_ref=None):
    repo = AlertRepository()
    alerta = repo.create(
        rule=f"missing_{feature}",
        severity=severity,
        message=f"Sem {feature}",
        feature=feature,
        camera_id=camera_id,
        frame_ref=frame_ref,
    )
    if status == "resolved":
        repo.resolve(alerta)
    return alerta


# ------------------------------------------------------------ apagar --------
def test_apagar_resolvidos_nao_toca_nos_ativos(real_monitor_app, real_monitor_client):
    with real_monitor_app.app_context():
        ativo = _alerta(status="active").id
        _alerta(status="resolved")
        _alerta(status="resolved", feature="vest")

    r = real_monitor_client.delete("/alerts/resolved")
    assert r.status_code == 200
    assert r.get_json()["deleted"] == 2

    with real_monitor_app.app_context():
        restantes = Alert.query.all()
        assert [a.id for a in restantes] == [ativo]
        assert restantes[0].status == "active"


def test_apagar_respeita_a_camera(real_monitor_app, real_monitor_client):
    with real_monitor_app.app_context():
        _alerta(camera_id=1, status="resolved")
        _alerta(camera_id=2, status="resolved")

    r = real_monitor_client.delete("/alerts/resolved?camera_id=2")
    assert r.get_json()["deleted"] == 1
    with real_monitor_app.app_context():
        assert [a.camera_id for a in Alert.query.all()] == [1]


def test_apagar_mais_antigos_que_x_dias(real_monitor_app, real_monitor_client):
    from datetime import datetime, timedelta, timezone

    with real_monitor_app.app_context():
        velho = _alerta(status="resolved")
        _alerta(status="resolved")
        velho.last_seen_at = datetime.now(timezone.utc) - timedelta(days=10)
        db.session.commit()

    r = real_monitor_client.delete("/alerts/resolved?older_than_days=7")
    assert r.get_json()["deleted"] == 1
    with real_monitor_app.app_context():
        assert Alert.query.count() == 1


def test_apagar_remove_a_evidencia_orfa(real_monitor_app, real_monitor_client, tmp_path, monkeypatch):
    pasta = tmp_path / "snaps"
    pasta.mkdir()
    (pasta / "a.jpg").write_bytes(b"x")
    (pasta / "fica.jpg").write_bytes(b"x")
    (pasta / "fora.txt").write_bytes(b"x")

    class Servico:
        absolute_dir = pasta

    monkeypatch.setattr(type(real_monitor_app.extensions["monitor_service"]), "snapshot_service", Servico(), raising=False)

    with real_monitor_app.app_context():
        _alerta(status="resolved", frame_ref="/snapshots/a.jpg")
        _alerta(status="active", frame_ref="/snapshots/fica.jpg")

    r = real_monitor_client.delete("/alerts/resolved")
    assert r.get_json()["evidence_files_removed"] == 1
    assert not (pasta / "a.jpg").exists()
    assert (pasta / "fica.jpg").exists()  # o alerta ativo ainda aponta pra ela
    assert (pasta / "fora.txt").exists()  # nada fora do que o alerta referenciava


def test_apagar_deixa_rastro_na_linha_do_tempo(real_monitor_app, real_monitor_client):
    from app.models import EventLog

    with real_monitor_app.app_context():
        _alerta(status="resolved")
    real_monitor_client.delete("/alerts/resolved")
    with real_monitor_app.app_context():
        evento = EventLog.query.filter_by(event_type="alerts_deleted").one()
        assert evento.metadata_json["total"] == 1


# --------------------------------------------------- resolver ativos ---------
def test_resolver_ativos_de_camera_parada_vai_direto_no_banco(real_monitor_app, real_monitor_client):
    r = real_monitor_client.post("/api/cameras", json={"name": "A", "source_type": "USB", "source": "0"})
    cam = r.get_json()["id"]
    with real_monitor_app.app_context():
        _alerta(camera_id=cam, status="active")
        _alerta(camera_id=cam, status="active", feature="vest")
        outro = _alerta(camera_id=999, status="active").id

    r = real_monitor_client.post(f"/alerts/resolve-active?camera_id={cam}")
    assert r.status_code == 200
    corpo = r.get_json()
    assert corpo["active_before"] == 2
    assert corpo["resolvidos_direto"] == 2

    with real_monitor_app.app_context():
        assert Alert.query.filter_by(camera_id=cam, status="active").count() == 0
        assert db.session.get(Alert, outro).status == "active"  # outra câmera intacta
        # Resolvido, não apagado: continua no histórico.
        assert Alert.query.filter_by(camera_id=cam, status="resolved").count() == 2


# ------------------------------------------------------ reconhecer todos -----
def test_reconhecer_todos_pula_quem_ja_foi_tratado(real_monitor_app, real_monitor_client):
    with real_monitor_app.app_context():
        a = _alerta()
        b = _alerta(feature="vest")
        _alerta(status="resolved", feature="mask")  # resolvido não conta
        AlertRepository().acknowledge(a, note="ja avisei")
        horario_original = db.session.get(Alert, a.id).metadata_json["acknowledged_at"]
        b_id = b.id

    r = real_monitor_client.post("/alerts/acknowledge-all")
    assert r.get_json() == {"acknowledged": 1}

    with real_monitor_app.app_context():
        assert db.session.get(Alert, b_id).metadata_json["acknowledged"] is True
        # Não reescreve o horário de quem já tinha sido tratado.
        assert db.session.get(Alert, a.id).metadata_json["acknowledged_at"] == horario_original


def test_marca_de_reconhecido_sobrevive_a_renovacao_do_worker(real_monitor_app):
    """O worker regrava a metadata a cada 2 s; isso não pode apagar o "avisei"."""
    with real_monitor_app.app_context():
        alerta = _alerta()
        alerta_id = alerta.id
        # Outra thread (a rota HTTP) grava a marca direto no banco.
        Alert.query.filter_by(id=alerta_id).update(
            {"metadata_json": {"acknowledged": True, "acknowledged_at": "2026-01-01T00:00:00+00:00"}}
        )
        db.session.commit()
        db.session.expire_all()

        AlertRepository().touch(alerta, metadata={"person_id": "person_1", "confirmation_frames": 9})

        meta = db.session.get(Alert, alerta_id).metadata_json
        assert meta["acknowledged"] is True
        assert meta["person_id"] == "person_1"  # o que o worker mandou também entra


# ------------------------------------------------------------- filtros ------
def test_filtra_por_tipo_e_camera(real_monitor_app, real_monitor_client):
    with real_monitor_app.app_context():
        _alerta(camera_id=1, feature="helmet")
        _alerta(camera_id=1, feature="vest")
        _alerta(camera_id=2, feature="helmet")

    def ids(qs):
        return sorted((a["camera_id"], a["feature"]) for a in real_monitor_client.get(f"/alerts?{qs}").get_json()["items"])

    assert ids("feature=helmet") == [(1, "helmet"), (2, "helmet")]
    assert ids("feature=helmet&camera_id=2") == [(2, "helmet")]
    assert ids("camera_id=1") == [(1, "helmet"), (1, "vest")]
