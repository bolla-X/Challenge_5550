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


def test_frame_reaproveitado_nao_conta_como_confirmacao(app):
    """Histerese tem que contar DETECCAO, nao iteracao do loop.

    Com `DETECTION_EVERY_N_FRAMES=3`, dois de cada tres frames reaproveitam a
    mesma `FrameAnalysis` (caracterizado em tests/test_camera_worker_cache.py).
    Como o contador andava a cada chamada de `process`, uma unica inferencia
    real satisfazia sozinha o `create_after_frames=3` — a histerese
    documentada como "cria apos 3 frames ruins" exigia 1.

    Medido na fixture de 7 s: tracks vistos em UMA deteccao criaram 5 alertas
    cada, e a fixture toda gerou 76 alertas para 6 tracks.
    """
    with app.app_context():
        socket = DummySocket()
        service = AlertStateService(AlertRepository(), socket, create_after_frames=3, resolve_after_frames=2)

        # Uma deteccao real, vista tres vezes pelo loop: UMA confirmacao.
        assert service.process([missing_helmet()], deteccao_nova=True)["active"] == []
        assert service.process([missing_helmet()], deteccao_nova=False)["active"] == []
        assert service.process([missing_helmet()], deteccao_nova=False)["active"] == []
        assert not any(evento == "alert_created" for evento, _ in socket.events), (
            "uma deteccao vista tres vezes pelo loop nao pode criar alerta"
        )

        # Segunda deteccao real.
        service.process([missing_helmet()], deteccao_nova=True)
        assert not any(evento == "alert_created" for evento, _ in socket.events)

        # Terceira: agora sim.
        terceira = service.process([missing_helmet()], deteccao_nova=True)
        assert len(terceira["active"]) == 1
        assert any(evento == "alert_created" for evento, _ in socket.events)


def test_frame_reaproveitado_nao_conta_para_resolver(app):
    """O mesmo vale para o outro lado da histerese.

    Sem isto, um alerta resolveria depois de menos deteccoes limpas do que
    `resolve_after_frames` promete — e voltaria a ser criado no proximo frame
    ruim, que e a outra metade do churn medido.
    """
    with app.app_context():
        socket = DummySocket()
        service = AlertStateService(AlertRepository(), socket, create_after_frames=1, resolve_after_frames=3)

        assert len(service.process([missing_helmet()], deteccao_nova=True)["active"]) == 1

        assert service.process([], deteccao_nova=True)["resolved"] == []
        assert service.process([], deteccao_nova=False)["resolved"] == []
        assert service.process([], deteccao_nova=False)["resolved"] == []
        assert service.process([], deteccao_nova=True)["resolved"] == []

        resolvido = service.process([], deteccao_nova=True)
        assert len(resolvido["resolved"]) == 1, "tres deteccoes limpas deveriam resolver"


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
