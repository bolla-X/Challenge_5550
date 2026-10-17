"""Regressões dos bugs confirmados num bug hunt (C2 a C7). Cada teste nasceu como repro que FALHAVA.

C2  commit que falha deixa `state.alert` transitório: toda análise seguinte levanta (alert_state_service).
C3  `stop()` + `start()` deixa DOIS loops de captura no mesmo worker (camera_worker).
C4  `touch` apagava a marca de falso positivo (e as outras chaves de ação humana) do metadata (alert_repository).
C5  alerta resolvido por fora: o estado era descartado sem `desanexar`, e o incidente nunca fechava.
C6  `alert_id`, `camera_id` e `detalhe` do elo ficavam fora do hash: editá-los escondia adulteração (custodia).
C7  POST /api/simulador com `horas` inválido devolvia 500 em vez de 400.
"""

from __future__ import annotations

import threading
import time

import pytest
from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import Alert, ElodeCustodia, Incidente
from app.repositories.alert_repository import AlertRepository
from app.services import custodia
from app.services.alert_state_service import AlertStateService
from app.services.risk_rules import RuleAlert
from sqlalchemy.exc import OperationalError

from test_alert_state import DummySocket
from test_camera_worker_falha_de_fonte import FonteMorta, SocketDuble, montar_worker
from test_custodia import _alerta
from test_simulador import pessoa

ITEM = RuleAlert(rule="missing_helmet", severity="critical", message="Sem capacete · Pessoa 3", feature="helmet",
                 metadata={"person_id": "person_3"})


def _svc(repositorio: AlertRepository | None = None) -> AlertStateService:
    return AlertStateService(repositorio or AlertRepository(), DummySocket(), create_after_frames=1, resolve_after_frames=1,
                             camera_id=1, intervalo_touch=0.0, custodia=False)


# ---------------------------------------------------------------- C2
class _RepoQueTravaUmaVez(AlertRepository):
    """O commit da análise falha uma vez ("database is locked"), como no E2E com várias câmeras."""

    def __init__(self) -> None:
        self.falhas = 1

    def salvar(self) -> None:
        if self.falhas:
            self.falhas -= 1
            raise OperationalError("COMMIT", {}, Exception("database is locked"))
        super().salvar()


def test_c2_process_se_recupera_depois_de_um_commit_falho(app):
    svc = _svc(_RepoQueTravaUmaVez())
    with pytest.raises(OperationalError):
        svc.process([ITEM])
    db.session.rollback()  # o que CameraWorker._recuperar_sessao faz
    for _ in range(3):  # a pessoa continua sem capacete: 3 análises novas, nenhuma pode levantar
        resultado = svc.process([ITEM])
    assert len(resultado["active"]) == 1
    assert Alert.query.filter_by(status="active").count() == 1


def test_c2_commit_falho_nao_deixa_incidente_orfao_nem_alerta_fantasma(app):
    svc = _svc(_RepoQueTravaUmaVez())
    with pytest.raises(OperationalError):
        svc.process([ITEM])
    assert svc.active_alerts() == [] and svc.active_incidents() == []
    db.session.rollback()
    svc.process([ITEM])
    assert Alert.query.count() == 1 and Incidente.query.filter_by(status="active").count() == 1


# ---------------------------------------------------------------- C3
class _SocketComThread(SocketDuble):
    """Ao contrário do dublê padrão, inicia a thread de verdade (o loop é o objeto do teste)."""

    def start_background_task(self, target, *args, **kwargs):
        t = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
        t.start()
        return t


def test_c3_stop_start_imediato_deixa_um_loop_so():
    dormir = time.sleep  # captura antes de qualquer patch
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        w = montar_worker(app, socket=_SocketComThread())
        assert w.agendador is None
        w.video_stream = FonteMorta()
        w.cleanup_service.cleanup_startup_artifacts = lambda: {}
        vistos: list[tuple[float, int]] = []

        def falha_lenta() -> None:
            vistos.append((time.monotonic(), threading.get_ident()))
            dormir(0.2)  # uma iteração que demora (inferência na CPU, read RTSP)

        w._handle_capture_failure = falha_lenta
        w.start()
        dormir(0.1)
        w.stop()
        w.start()  # exatamente o que app/api/palco.py:_preparar faz
        dormir(0.5)  # o loop antigo, se ainda vivo, já deveria ter saído
        marco = time.monotonic()
        dormir(0.8)
        threads_vivas = {tid for t, tid in vistos if t >= marco}
        w.stop()
        dormir(0.4)
        db.session.remove()
        db.drop_all()
        assert len(threads_vivas) == 1, f"{len(threads_vivas)} loops de captura rodando no mesmo worker"


# ---------------------------------------------------------------- C4
@pytest.mark.parametrize("chave", ["false_positive", "false_positive_reason", "false_positive_at", "resolution_reason"])
def test_c4_touch_preserva_marca_de_falso_positivo(app, chave):
    svc = _svc()
    alert_id = svc.process([ITEM])["created"][0]["id"]
    AlertRepository().mark_false_positive(db.session.get(Alert, alert_id), reason="boné confundido")
    svc.process([ITEM])  # a pessoa continua na cena: o worker renova o alerta
    db.session.expire_all()
    meta = db.session.get(Alert, alert_id).metadata_json
    assert chave in meta, f"`{chave}` apagada pelo touch: {sorted(meta)}"


def test_c4_touch_preserva_snapshot_available(app):
    repo = AlertRepository()
    alerta = repo.create(rule="missing_helmet", severity="critical", message="x", metadata={"person_id": "person_1"})
    repo.update_frame_ref(alerta, "alert_1.jpg")  # a rota/gravador grava, de outra thread, depois do worker
    repo.touch(alerta, metadata={"person_id": "person_1", "confirmation_frames": 4})
    db.session.expire_all()
    assert db.session.get(Alert, alerta.id).metadata_json.get("snapshot_available") is True


# ---------------------------------------------------------------- C5
def test_c5_incidente_fecha_quando_o_alerta_foi_resolvido_por_fora(app):
    svc = _svc()
    r = svc.process([ITEM])
    alert_id, inc_id = r["created"][0]["id"], r["created"][0]["metadata"]["incidente_id"]
    AlertRepository().mark_false_positive(db.session.get(Alert, alert_id), reason="fp")
    svc.process([ITEM])
    svc.process([])  # a violação acabou
    db.session.commit()
    db.session.expire_all()
    assert db.session.get(Incidente, inc_id).status == "resolved"
    assert svc.active_incidents() == []


def test_c5_incidente_fecha_quando_a_feature_e_desligada_com_alerta_resolvido_por_fora(app):
    svc = _svc()
    r = svc.process([ITEM])
    alert_id, inc_id = r["created"][0]["id"], r["created"][0]["metadata"]["incidente_id"]
    AlertRepository().mark_false_positive(db.session.get(Alert, alert_id), reason="fp")
    svc.process([], features_desligadas={"helmet"})
    db.session.expire_all()
    assert db.session.get(Incidente, inc_id).status == "resolved"
    assert svc.active_incidents() == []


# ---------------------------------------------------------------- C6
def _snapshot_adulterado(tmp_path, *, forjar: bool = True):
    a1 = _alerta(1)
    custodia.registrar_alerta(a1)
    snap = tmp_path / "snap_1.jpg"
    snap.write_bytes(b"\xff\xd8snapshot-original\xff\xd9")
    custodia.registrar_snapshot(a1, snap)
    assert custodia.verificar(alert_ids={a1.id})["integra"]
    if forjar:
        snap.write_bytes(b"\xff\xd8snapshot-FORJADO\xff\xd9")
    return a1, ElodeCustodia.query.filter_by(tipo="snapshot").one()


def test_c6_snapshot_adulterado_com_elo_desvinculado_e_detectado_no_incidente(app, tmp_path):
    a1, elo = _snapshot_adulterado(tmp_path)
    elo.alert_id = None
    elo.detalhe = {**elo.detalhe, "alert_ids": []}
    db.session.commit()
    r = custodia.verificar(alert_ids={a1.id})
    assert r["adulterada"], f"incidente reportado como integra={r['integra']} com {r['elos_verificados']} elo(s)"


def test_c6_editar_camera_id_do_elo_e_detectado(app, tmp_path):
    _, elo = _snapshot_adulterado(tmp_path, forjar=False)
    elo.camera_id = 99
    db.session.commit()
    assert custodia.verificar()["quebrado"]["situacao"] == "registro_alterado"


def test_c6_elos_antigos_sem_versao_continuam_verificados_junto_dos_novos(app, tmp_path):
    """Coexistência: elo gravado no formato original (hash sem alert_id/camera_id/detalhe) + elo novo na mesma cadeia."""
    a1 = _alerta(1)
    conteudo = custodia.sha256_bytes(custodia.conteudo_do_alerta(a1))
    criado_em = "2026-10-01T12:00:00+00:00"
    antigo = ElodeCustodia(
        id=1, tipo="alerta", ref=f"alerta:{a1.id}", camera_id=a1.camera_id, alert_id=a1.id, descricao=a1.message, detalhe={},
        conteudo_sha256=conteudo, anterior_sha256=custodia.GENESE, criado_em=criado_em,
        elo_sha256=custodia.sha256_bytes(f"1|alerta|alerta:{a1.id}|{conteudo}|{custodia.GENESE}|{criado_em}".encode()),
    )
    db.session.add(antigo)
    db.session.commit()
    a2 = _alerta(2)
    custodia.registrar_alerta(a2)  # formato novo, encadeado ao antigo
    r = custodia.verificar()
    assert r["integra"] and r["elos_na_cadeia"] == 2
    assert custodia.verificar(alert_ids={a1.id})["integra"]


def test_c6_remover_a_marca_de_versao_de_um_elo_novo_e_detectado(app, tmp_path):
    """Rebaixar o elo para o formato antigo (apagando a versão) não esconde a edição: o hash não fecha."""
    a1, elo = _snapshot_adulterado(tmp_path)
    elo.alert_id = None
    elo.detalhe = {k: v for k, v in elo.detalhe.items() if k != "formato_elo"} | {"alert_ids": []}
    db.session.commit()
    assert custodia.verificar(alert_ids={a1.id})["adulterada"]


# ---------------------------------------------------------------- C7
@pytest.mark.parametrize("horas", ["abc", None, float("nan"), float("inf"), [1], {}])
def test_c7_horas_invalidas_viram_400(real_monitor_app, real_monitor_client, tmp_path, horas):
    from app.models import Camera

    real_monitor_app.config["TRILHAS_DIR"] = str(tmp_path)
    real_monitor_app.config["PROPAGATE_EXCEPTIONS"] = False
    with real_monitor_app.app_context():
        cam = Camera(name="Pátio", source_type="Arquivo", source="x.mp4")
        db.session.add(cam)
        db.session.commit()
        monitor = real_monitor_app.extensions["monitor_service"]
        monitor.load_cameras_from_db()
        worker = monitor.worker_da_camera(cam.id)
        worker.trilhas.registrar(time.time() - 5, [pessoa(1)], 960, 540)
        cid = cam.id
    r = real_monitor_client.post("/api/simulador", json={"camera_id": cid, "horas": horas})
    assert r.status_code == 400, (r.status_code, r.get_data(as_text=True)[:120])
    assert "horas" in r.get_json()["error"]
