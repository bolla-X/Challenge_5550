"""Regressão: escrita em `metadata_json` tem que chegar ao BANCO.

O bug original: `metadata = alert.metadata_json or {}` devolvia o próprio dict
do banco; mutar in-place e reatribuir o MESMO objeto não marca o atributo como
sujo, e o commit não escrevia nada. Só "funcionava" quando o dict estava vazio
(aí `or {}` criava um objeto novo por acidente) — e em produção o metadata
nunca está vazio, então a marcação de falso positivo se perdia sempre.

Todos os testes aqui re-leem do banco (`expunge_all`) de propósito: afirmar
sobre o objeto em memória passaria mesmo com o bug presente, que foi
exatamente o motivo de a suíte antiga não pegá-lo.
"""
from __future__ import annotations

import pytest
from app.extensions import db
from app.models import Alert
from app.repositories.alert_repository import AlertRepository

# Metadata NÃO-vazio: é o caso real (todo alerta carrega person_id,
# present_labels, supported_ppe) e é o caso em que o bug se manifestava.
METADATA = {"person_id": "person_1", "present_labels": ["person"]}


@pytest.fixture()
def repository(app):
    return AlertRepository()


def _reload(alert_id: int) -> Alert:
    db.session.expunge_all()
    return db.session.get(Alert, alert_id)


def test_mark_false_positive_persiste_no_banco(app, repository):
    with app.app_context():
        alert = repository.create(rule="missing_vest", severity="high", message="Sem colete", feature="vest", metadata=dict(METADATA))
        alert_id = alert.id
        repository.mark_false_positive(alert, reason="reflexo na lente")

        stored = _reload(alert_id)
        assert stored.metadata_json["false_positive"] is True
        assert stored.metadata_json["false_positive_reason"] == "reflexo na lente"
        assert stored.metadata_json["person_id"] == "person_1"  # não perde o que já existia
        assert stored.status == "resolved"


def test_filtro_false_positive_roda_no_sql_antes_do_limit(app, repository):
    with app.app_context():
        marcados = []
        for index in range(3):
            alert = repository.create(rule="r", severity="high", message=f"a{index}", feature="vest", metadata=dict(METADATA))
            if index < 2:
                repository.mark_false_positive(alert)
                marcados.append(alert.id)

        assert {item.id for item in repository.list_recent(false_positive=True)} == set(marcados)
        assert len(repository.list_recent(false_positive=False)) == 1
        # Sem filtro, os três.
        assert len(repository.list_recent()) == 3


def test_filtro_false_positive_nao_perde_itens_pelo_limit(app, repository):
    """Antes o filtro rodava em Python DEPOIS do `.limit()`: pedir 2 podia
    devolver 0 se os mais recentes não fossem falsos positivos."""
    with app.app_context():
        alvo = repository.create(rule="r", severity="high", message="antigo", feature="vest", metadata=dict(METADATA))
        alvo_id = alvo.id
        repository.mark_false_positive(alvo)
        for index in range(5):
            repository.create(rule="r", severity="high", message=f"novo{index}", feature="vest", metadata=dict(METADATA))

        encontrados = repository.list_recent(limit=2, false_positive=True)
        assert [item.id for item in encontrados] == [alvo_id]


def test_update_frame_ref_persiste_com_metadata_nao_vazio(app, repository):
    with app.app_context():
        alert = repository.create(rule="r", severity="high", message="m", feature="vest", metadata=dict(METADATA))
        alert_id = alert.id
        repository.update_frame_ref(alert, "/snapshots/x.jpg")

        stored = _reload(alert_id)
        assert stored.frame_ref == "/snapshots/x.jpg"
        assert stored.metadata_json["snapshot_available"] is True


def test_acknowledge_nao_resolve_o_alerta(app, repository):
    """"Avisei o colaborador" registra a ação, mas quem resolve o alerta é a
    detecção parar de ver a violação."""
    with app.app_context():
        alert = repository.create(rule="r", severity="critical", message="m", feature="helmet", metadata=dict(METADATA))
        alert_id = alert.id
        repository.acknowledge(alert, note="falei com o João")

        stored = _reload(alert_id)
        assert stored.metadata_json["acknowledged"] is True
        assert stored.metadata_json["acknowledged_note"] == "falei com o João"
        assert stored.status == "active"
        assert stored.resolved_at is None


# ------------------------------------------------------- escopo por câmera --
def test_resolve_all_active_e_escopado_por_camera(app, repository):
    """Iniciar a câmera 2 não pode resolver os alertas vivos da câmera 1."""
    with app.app_context():
        # Guarda os ids ANTES de qualquer expunge: `_reload` destaca as
        # instâncias, e ler `.id` depois disso dispara DetachedInstanceError.
        cam1_id = repository.create(rule="r", severity="high", message="cam1", feature="vest", camera_id=1, metadata=dict(METADATA)).id
        cam2_id = repository.create(rule="r", severity="high", message="cam2", feature="vest", camera_id=2, metadata=dict(METADATA)).id

        resolvidos = repository.resolve_all_active(reason="monitor_start_reset", camera_id=2)

        assert resolvidos == 1
        assert _reload(cam1_id).status == "active"
        assert _reload(cam2_id).status == "resolved"


def test_resolve_all_active_sem_camera_id_atinge_todas(app, repository):
    """Reset global continua existindo — só não é mais o comportamento padrão
    do start de uma câmera."""
    with app.app_context():
        repository.create(rule="r", severity="high", message="a", feature="vest", camera_id=1)
        repository.create(rule="r", severity="high", message="b", feature="vest", camera_id=2)

        assert repository.resolve_all_active(reason="reset") == 2


def test_list_recent_filtra_por_camera(app, repository):
    with app.app_context():
        repository.create(rule="r", severity="high", message="a", feature="vest", camera_id=1)
        repository.create(rule="r", severity="high", message="b", feature="vest", camera_id=2)
        repository.create(rule="r", severity="high", message="c", feature="vest", camera_id=2)

        assert len(repository.list_recent(camera_id=2)) == 2
        assert len(repository.list_recent(camera_id=1)) == 1
        assert len(repository.list_recent()) == 3


def test_snapshots_referenciados_sao_listados_para_protecao(app, repository):
    """A limpeza de startup usa esta lista pra não apagar evidência que o
    histórico ainda aponta."""
    with app.app_context():
        alert = repository.create(rule="r", severity="high", message="m", feature="vest", metadata=dict(METADATA))
        repository.update_frame_ref(alert, "/snapshots/alert_1_missing_vest_x.jpg")
        repository.create(rule="r", severity="high", message="sem evidencia", feature="vest")

        assert repository.referenced_frame_filenames() == {"alert_1_missing_vest_x.jpg"}
