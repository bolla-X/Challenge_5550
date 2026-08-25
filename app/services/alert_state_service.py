from __future__ import annotations

import logging
from dataclasses import dataclass
from time import monotonic
from typing import Any

from flask_socketio import SocketIO

from app.models import Alert
from app.repositories.alert_repository import AlertRepository
from app.services.risk_rules import RuleAlert

logger = logging.getLogger(__name__)


@dataclass
class AlertRuntimeState:
    key: str
    rule_alert: RuleAlert
    violation_frames: int = 0
    normal_frames: int = 0
    alert: Alert | None = None
    # Cópia simples do último `alert.to_dict()`, tirada SEMPRE dentro do
    # thread do worker, logo após gravar. Existe porque `alert` é um objeto do
    # SQLAlchemy preso à sessão que o carregou: ler um atributo dele de outro
    # thread (a rota /status é quem faz isso) pode disparar refresh e estourar
    # "This session is in 'prepared' state" quando o worker está no meio de um
    # commit. Um dict não tem sessão nem lazy load, então atravessa threads.
    snapshot: dict[str, Any] | None = None
    # Ocorrências vistas mas ainda não gravadas, e quando foi a última
    # gravação. Ver AlertStateService.intervalo_touch.
    ocorrencias_pendentes: int = 0
    ultimo_touch: float = 0.0


class AlertStateService:
    """Mantém alertas operacionais ativos e resolve quando a condição normal retorna.

    Banco mantém histórico; dashboard recebe somente o estado ativo/resolvido via WebSocket.
    """

    def __init__(
        self,
        repository: AlertRepository,
        socketio: SocketIO,
        *,
        create_after_frames: int = 3,
        resolve_after_frames: int = 5,
        camera_id: int | None = None,
        intervalo_touch: float = 2.0,
    ) -> None:
        self.repository = repository
        self.socketio = socketio
        # Toda emissão e todo Alert criado carimba a câmera de origem. Sem
        # isso, dois workers emitindo `active_alerts` sobrescreviam a lista um
        # do outro no dashboard ~12x por segundo.
        self.camera_id = camera_id
        self.create_after_frames = max(1, int(create_after_frames))
        self.resolve_after_frames = max(1, int(resolve_after_frames))
        # Segundos entre gravações de um alerta que CONTINUA ativo.
        #
        # Antes o `touch` (last_seen_at + occurrences) fazia um commit por
        # alerta POR FRAME, dentro do loop de captura. Medido aqui: 9,2 ms por
        # commit, e o SQLite sustenta ~109 por segundo. Com 5 alertas ativos,
        # duas câmeras e 24 FPS seriam 240 commits/s — mais de dois núcleos só
        # gravando, e o vídeo travava exatamente quando havia infração, que é
        # justamente a hora da demonstração.
        #
        # Criar e resolver continuam gravando na hora: o que espaça é só a
        # renovação de um alerta que já está na tela. 0 desliga o espaçamento.
        self.intervalo_touch = max(0.0, float(intervalo_touch))
        self._states: dict[str, AlertRuntimeState] = {}

    def process(self, current_violations: list[RuleAlert]) -> dict[str, Any]:
        current_by_key = {item.key: item for item in current_violations}
        created: list[dict[str, Any]] = []
        updated: list[dict[str, Any]] = []
        created_or_updated: list[dict[str, Any]] = []
        resolved: list[dict[str, Any]] = []

        for key, item in current_by_key.items():
            state = self._states.get(key)
            if state is None:
                state = AlertRuntimeState(key=key, rule_alert=item)
                self._states[key] = state
            state.rule_alert = item
            state.violation_frames += 1
            state.normal_frames = 0

            if state.alert is None and state.violation_frames >= self.create_after_frames:
                state.alert = self.repository.create(
                    camera_id=self.camera_id,
                    rule=item.rule,
                    severity=item.severity,
                    message=item.message,
                    feature=item.feature,
                    metadata=item.metadata | {"confirmation_frames": state.violation_frames},
                    status="active",
                )
                payload = state.alert.to_dict()
                state.snapshot = payload
                # Acabou de ser gravado: o relógio do espaçamento começa aqui.
                state.ultimo_touch = monotonic()
                state.ocorrencias_pendentes = 0
                created.append(payload)
                created_or_updated.append(payload)
                self.socketio.emit("alert_created", payload)
                self.socketio.emit("alert", payload)  # compatibilidade com clientes antigos
                logger.warning("alert_created", extra={"alert": payload})
            elif state.snapshot is not None and state.snapshot.get("status") == "active":
                # Alerta que continua ativo: acumula e só grava de tempos em
                # tempos (ver self.intervalo_touch). A condição olha o
                # snapshot, não `state.alert.status`, para não tocar no ORM
                # a cada frame — mesmo motivo de active_alerts().
                state.ocorrencias_pendentes += 1
                agora = monotonic()
                if agora - state.ultimo_touch < self.intervalo_touch:
                    continue
                state.alert = self.repository.touch(
                    state.alert,
                    metadata=item.metadata | {"confirmation_frames": state.violation_frames},
                    incremento=state.ocorrencias_pendentes,
                )
                state.ocorrencias_pendentes = 0
                state.ultimo_touch = agora
                payload = state.alert.to_dict()
                state.snapshot = payload
                updated.append(payload)
                created_or_updated.append(payload)
                self.socketio.emit("alert_updated", payload)

        for key in list(self._states.keys()):
            if key in current_by_key:
                continue
            state = self._states[key]
            state.normal_frames += 1
            state.violation_frames = 0
            if state.normal_frames >= self.resolve_after_frames:
                if state.alert is not None and state.alert.status == "active":
                    state.alert = self.repository.resolve(
                        state.alert,
                        metadata=(state.alert.metadata_json or {}) | {"resolution_frames": state.normal_frames},
                    )
                    payload = state.alert.to_dict()
                    state.snapshot = payload
                    resolved.append(payload)
                    self.socketio.emit("alert_resolved", payload)
                    logger.info("alert_resolved", extra={"alert": payload})
                del self._states[key]

        active = self.active_alerts()
        self._emit_active(active)
        return {"active": active, "changed": created_or_updated, "created": created, "updated": updated, "resolved": resolved}

    def _emit_active(self, active: list[dict[str, Any]]) -> None:
        self.socketio.emit("active_alerts", {"camera_id": self.camera_id, "items": active, "count": len(active)})

    def active_alerts(self) -> list[dict[str, Any]]:
        """Alertas ativos como dados puros.

        Lê o `snapshot` e NUNCA o objeto `Alert` — este método é chamado tanto
        pelo worker quanto pela rota /status, e tocar no ORM a partir do thread
        HTTP quebrava com "This session is in 'prepared' state" quando o worker
        commitava ao mesmo tempo. Ver comentário em AlertRuntimeState.snapshot.
        """
        items: list[dict[str, Any]] = []
        for state in list(self._states.values()):
            snapshot = state.snapshot
            if snapshot is not None and snapshot.get("status") == "active":
                items.append(snapshot)
        return sorted(items, key=lambda item: item.get("severity", ""), reverse=True)


    def resolve_all(self, *, reason: str = "manual_reset") -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for key in list(self._states.keys()):
            state = self._states[key]
            if state.alert is not None and state.alert.status == "active":
                state.alert = self.repository.resolve(
                    state.alert,
                    metadata=(state.alert.metadata_json or {}) | {"resolution_reason": reason},
                )
                payload = state.alert.to_dict()
                state.snapshot = payload
                resolved.append(payload)
                self.socketio.emit("alert_resolved", payload)
        self._states.clear()
        self._emit_active([])
        return resolved

    def reset(self) -> None:
        self._states.clear()
