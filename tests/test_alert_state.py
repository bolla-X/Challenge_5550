from __future__ import annotations

from app.repositories.alert_repository import AlertRepository
from app.services.alert_state_service import AlertStateService
from app.services.risk_rules import RuleAlert


class DummySocket:
    def __init__(self):
        self.events = []

    def emit(self, event, payload=None, *args, **kwargs):
        self.events.append((event, payload))


def missing_helmet():
    return RuleAlert(
        rule="missing_helmet",
        severity="critical",
        message="Sem capacete",
        feature="helmet",
        metadata={"present_labels": ["person"]},
    )


def test_alert_state_creates_and_resolves_after_confirmation_frames(app):
    with app.app_context():
        socket = DummySocket()
        service = AlertStateService(AlertRepository(), socket, create_after_frames=2, resolve_after_frames=2)

        first = service.process([missing_helmet()])
        assert first["active"] == []

        second = service.process([missing_helmet()])
        assert len(second["active"]) == 1
        assert second["active"][0]["status"] == "active"
        assert any(event == "alert_created" for event, _ in socket.events)

        still_active = service.process([])
        assert len(still_active["active"]) == 1

        resolved = service.process([])
        assert resolved["active"] == []
        assert len(resolved["resolved"]) == 1
        assert resolved["resolved"][0]["status"] == "resolved"
        assert any(event == "alert_resolved" for event, _ in socket.events)


def test_alerta_ativo_nao_grava_a_cada_frame(app):
    """Renovar um alerta que continua ativo não pode gravar por frame.

    Cada gravação é um commit dentro do loop de captura (~9 ms). Com vários
    alertas e duas câmeras a 24 FPS isso saturava a CPU e travava o vídeo
    justamente quando havia infração. Aqui o intervalo é alto de propósito:
    depois de criado, nenhum frame seguinte pode gerar novo `alert_updated`.
    """
    with app.app_context():
        socket = DummySocket()
        service = AlertStateService(
            AlertRepository(), socket, create_after_frames=1, resolve_after_frames=99, intervalo_touch=3600.0
        )

        service.process([missing_helmet()])  # cria
        socket.events.clear()

        for _ in range(30):
            service.process([missing_helmet()])

        assert not [evento for evento, _ in socket.events if evento == "alert_updated"]
        # e o alerta segue ativo, com as ocorrências contadas em memória
        estado = next(iter(service._states.values()))
        assert estado.ocorrencias_pendentes == 30
        assert service.active_alerts()[0]["status"] == "active"


def test_ocorrencias_acumuladas_entram_na_gravacao(app):
    """Espaçar a gravação não pode PERDER contagem: o que ficou pendente
    precisa entrar de uma vez no próximo commit."""
    with app.app_context():
        socket = DummySocket()
        # intervalo_touch=0 grava sempre, então o acumulado vai junto na hora
        service = AlertStateService(
            AlertRepository(), socket, create_after_frames=1, resolve_after_frames=99, intervalo_touch=3600.0
        )
        service.process([missing_helmet()])
        base = service.active_alerts()[0]["occurrences"]

        for _ in range(9):
            service.process([missing_helmet()])  # nada é gravado ainda
        estado = next(iter(service._states.values()))
        assert estado.ocorrencias_pendentes == 9
        assert service.active_alerts()[0]["occurrences"] == base

        # força o vencimento do intervalo em vez de dormir no teste
        estado.ultimo_touch -= 7200.0
        service.process([missing_helmet()])

        # as 9 pendentes + esta entram de uma vez, nenhuma se perde
        assert service.active_alerts()[0]["occurrences"] == base + 10
        assert estado.ocorrencias_pendentes == 0
