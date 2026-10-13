from __future__ import annotations

import logging
from dataclasses import dataclass
from time import monotonic
from typing import Any

from flask_socketio import SocketIO

from app.models import Alert
from app.repositories.alert_repository import AlertRepository
from app.services.risk_rules import RuleAlert
from app.utils.salas import emitir_para_camera
from app.vision.schemas import BoundingBox

logger = logging.getLogger(__name__)


# Quanto tempo a violacao pode ficar AUSENTE sem a soneca cair. O rastreador de
# pessoas perde e reencontra a mesma pessoa a cada poucos frames; se a soneca
# caisse junto, o "resolver todos" nao segurava nada.
SONECA_AUSENCIA_S = 10.0
# Reenvio da lista de ativos mesmo sem mudança (ver _emit_active).
PULSACAO_ATIVOS_S = 2.0
# IoU minimo entre a caixa da pessoa silenciada e a de um alerta novo da mesma
# regra pra considerar que e a MESMA pessoa com id novo.
SONECA_IOU_MESMA_PESSOA = 0.25


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
    # Instante (monotonic) da 1ª confirmação da sequência atual de violação
    # e da 1ª da sequência atual de normalidade (histerese por tempo).
    violacao_desde: float | None = None
    normal_desde: float | None = None


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
        silencio_apos_limpar: float = 60.0,
        create_after_seconds: float | None = None,
        min_confirmacoes: int = 2,
        resolve_after_seconds: float | None = None,
        min_confirmacoes_resolver: int = 3,
    ) -> None:
        self.repository = repository
        self.socketio = socketio
        # Toda emissão e todo Alert criado carimba a câmera de origem. Sem
        # isso, dois workers emitindo `active_alerts` sobrescreviam a lista um
        # do outro no dashboard ~12x por segundo.
        self.camera_id = camera_id
        self.create_after_frames = max(1, int(create_after_frames))
        self.resolve_after_frames = max(1, int(resolve_after_frames))
        # Histerese também por TEMPO. Os limiares em quadros (8 para criar, 20
        # para resolver) foram calibrados para o loop antigo a ~12 inferências/s,
        # onde 8 confirmações eram ~0,7 s. Numa máquina que faz 0,3 análise/s
        # as mesmas 8 viram ~27 s — medido no bench (docs/NEXT2026/BENCHMARKS.md:
        # 60–84 s de latência de alerta no perfil batata). Agora cria quando
        # bate o limiar em quadros OU quando a violação se sustenta por
        # `create_after_seconds` com pelo menos `min_confirmacoes` inferências
        # NOVAS e seguidas. O mínimo de confirmações é o que protege contra o
        # falso positivo de um quadro só; o tempo é o que a pessoa no chão de
        # fábrica entende. Resolver segue a mesma lógica, com mínimos maiores.
        # None desliga (só quadros, como antes).
        self.create_after_seconds = create_after_seconds
        self.min_confirmacoes = max(1, int(min_confirmacoes))
        self.resolve_after_seconds = resolve_after_seconds
        self.min_confirmacoes_resolver = max(1, int(min_confirmacoes_resolver))
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
        # "Soneca" depois de um "resolver todos" manual. Sem ela, quem continua
        # sem o EPI recriava o mesmo alerta ~1 s depois (3 frames de histerese)
        # e o botao parecia nao fazer nada. Chave (regra+pessoa) -> ate quando
        # fica quieto e quantos frames seguidos a violacao ja esta ausente.
        self.silencio_apos_limpar = max(0.0, float(silencio_apos_limpar))
        self._silenciados: dict[str, dict[str, Any]] = {}
        self._ultima_assinatura_ativos: tuple | None = None
        self._ultimo_emit_ativos = 0.0

    @staticmethod
    def _caixa_da_pessoa(metadata: dict[str, Any] | None) -> BoundingBox | None:
        caixa = (metadata or {}).get("person_box")
        if isinstance(caixa, dict) and all(k in caixa for k in ("x1", "y1", "x2", "y2")):
            try:
                return BoundingBox(int(caixa["x1"]), int(caixa["y1"]), int(caixa["x2"]), int(caixa["y2"]))
            except (TypeError, ValueError):
                return None
        return None

    def _silenciado(self, key: str, item: RuleAlert) -> bool:
        agora = monotonic()
        for chave in [k for k, v in self._silenciados.items() if agora >= v["ate"]]:
            # Acabou o tempo: se ainda estiver sem EPI, o alerta volta, que e
            # a rede de seguranca contra silenciar um risco real pra sempre.
            del self._silenciados[chave]

        soneca = self._silenciados.get(key)
        caixa = self._caixa_da_pessoa(item.metadata)
        if soneca is None and caixa is not None:
            # O rastreador reatribuiu o id da pessoa (Pessoa 18 virou 26). Na
            # mesma regra, uma caixa sobreposta a de quem foi silenciado e a
            # mesma pessoa: herda a soneca em vez de disparar tudo de novo.
            for outra in self._silenciados.values():
                if (
                    outra["rule"] == item.rule
                    and outra["box"] is not None
                    and outra["box"].iou(caixa) >= SONECA_IOU_MESMA_PESSOA
                ):
                    soneca = self._silenciados[key] = dict(outra)
                    break
        if soneca is None:
            return False
        soneca["visto"] = agora
        if caixa is not None:
            soneca["box"] = caixa  # acompanha a pessoa enquanto ela se move
        return True

    def _resolver_features_desligadas(self, desligadas: set[str]) -> list[dict[str, Any]]:
        """Encerra na hora os alertas de uma feature que acabou de ser desligada.

        Sem isto o alerta só resolvia depois de `resolve_after_frames`
        detecções sem violação — e, em câmera que não recebia o botão, nunca.
        """
        resolved: list[dict[str, Any]] = []
        for key in list(self._states.keys()):
            state = self._states[key]
            if state.rule_alert.feature not in desligadas:
                continue
            if state.alert is not None and state.alert.status == "active":
                state.alert = self.repository.resolve(
                    state.alert,
                    metadata=(state.alert.metadata_json or {}) | {"resolution_reason": "feature_disabled"},
                )
                payload = state.alert.to_dict()
                state.snapshot = payload
                resolved.append(payload)
                self._emitir("alert_resolved", payload)
                logger.info("alert_resolved", extra={"alert": payload})
            del self._states[key]
        return resolved

    def process(
        self,
        current_violations: list[RuleAlert],
        *,
        deteccao_nova: bool = True,
        features_desligadas: set[str] | frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        """Avança a histerese e grava/resolve o que passou do limiar.

        `deteccao_nova=False` significa que este frame REAPROVEITOU a análise do
        frame anterior (ver `CameraWorker._analyze_frame` e
        `DETECTION_EVERY_N_FRAMES`). Nesse caso não há confirmação nova a
        contar: as detecções são literalmente as mesmas, e contá-las de novo
        transformava `create_after_frames=3` em "cria na primeira detecção".
        Medido: a fixture de 7 s gerava 76 alertas para 6 pessoas rastreadas.

        O default é `True` para que qualquer chamador que não saiba de
        intercalação siga com o comportamento de antes.
        """
        encerrados_por_desligar = self._resolver_features_desligadas(set(features_desligadas)) if features_desligadas else []

        if not deteccao_nova:
            ativos = self.active_alerts()
            self._emit_active(ativos)
            return {"active": ativos, "changed": [], "created": [], "updated": [], "resolved": encerrados_por_desligar}

        # UMA transação por análise: create/touch/resolve fazem só flush e o
        # commit é único no fim. Medido no bench (multidão, perfil batata): com
        # dezenas de pessoas x 7 EPIs, um commit SQLite por alerta tocado deixava
        # a análise nova até ~0,9 s parada aqui antes de sair (etapa `alertas`,
        # p99 565 ms). Os eventos vão DEPOIS do commit: o navegador nunca recebe
        # um alerta que ainda não está no banco.
        pendentes: list[tuple[str, Any]] = []

        def emitir(evento: str, payload: Any) -> None:
            pendentes.append((evento, payload))

        current_by_key = {item.key: item for item in current_violations}
        # A soneca so vale enquanto a violacao continua: se sumiu de verdade
        # (mesma histerese de resolucao), uma violacao NOVA depois dispara.
        agora = monotonic()
        for key in list(self._silenciados):
            if key in current_by_key:
                self._silenciados[key]["visto"] = agora
            elif agora - self._silenciados[key]["visto"] >= SONECA_AUSENCIA_S:
                del self._silenciados[key]
        created: list[dict[str, Any]] = []
        updated: list[dict[str, Any]] = []
        created_or_updated: list[dict[str, Any]] = []
        resolved: list[dict[str, Any]] = list(encerrados_por_desligar)

        for key, item in current_by_key.items():
            state = self._states.get(key)
            if state is None:
                state = AlertRuntimeState(key=key, rule_alert=item)
                self._states[key] = state
            state.rule_alert = item
            if state.violation_frames == 0:
                state.violacao_desde = agora
            state.violation_frames += 1
            state.normal_frames = 0
            state.normal_desde = None

            if (
                state.alert is None
                and self._confirmou(state.violation_frames, state.violacao_desde, agora,
                                    self.create_after_frames, self.create_after_seconds, self.min_confirmacoes)
                and not self._silenciado(key, item)
            ):
                state.alert = self.repository.create(
                    commit=False,
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
                emitir("alert_created", payload)
                emitir("alert", payload)  # compatibilidade com clientes antigos
                logger.warning("alert_created", extra={"alert": payload})
            elif state.snapshot is not None and state.snapshot.get("status") == "active":
                # Alerta que continua ativo: acumula e só grava de tempos em
                # tempos (ver self.intervalo_touch). A condição olha o
                # snapshot, não `state.alert.status`, para não tocar no ORM
                # a cada frame — mesmo motivo de active_alerts().
                state.ocorrencias_pendentes += 1
                if agora - state.ultimo_touch < self.intervalo_touch:
                    continue
                state.alert = self.repository.touch(
                    state.alert,
                    metadata=item.metadata | {"confirmation_frames": state.violation_frames},
                    incremento=state.ocorrencias_pendentes,
                    commit=False,
                )
                state.ocorrencias_pendentes = 0
                state.ultimo_touch = agora
                payload = state.alert.to_dict()
                state.snapshot = payload
                updated.append(payload)
                created_or_updated.append(payload)
                emitir("alert_updated", payload)

        for key in list(self._states.keys()):
            if key in current_by_key:
                continue
            state = self._states[key]
            if state.normal_frames == 0:
                state.normal_desde = agora
            state.normal_frames += 1
            state.violation_frames = 0
            state.violacao_desde = None
            if self._confirmou(state.normal_frames, state.normal_desde, agora, self.resolve_after_frames,
                               self.resolve_after_seconds, self.min_confirmacoes_resolver):
                if state.alert is not None and state.alert.status == "active":
                    state.alert = self.repository.resolve(
                        state.alert,
                        metadata=(state.alert.metadata_json or {}) | {"resolution_frames": state.normal_frames},
                        commit=False,
                    )
                    payload = state.alert.to_dict()
                    state.snapshot = payload
                    resolved.append(payload)
                    emitir("alert_resolved", payload)
                    logger.info("alert_resolved", extra={"alert": payload})
                del self._states[key]

        if pendentes:
            self.repository.salvar()
        for evento, payload in pendentes:
            self._emitir(evento, payload)
        active = self.active_alerts()
        self._emit_active(active)
        return {"active": active, "changed": created_or_updated, "created": created, "updated": updated, "resolved": resolved}

    @staticmethod
    def _confirmou(confirmacoes: int, desde: float | None, agora: float, limiar_quadros: int,
                   limiar_s: float | None, minimo: int) -> bool:
        if confirmacoes >= limiar_quadros:
            return True
        return limiar_s is not None and desde is not None and confirmacoes >= minimo and agora - desde >= limiar_s

    def _emitir(self, evento: str, payload) -> None:
        """Emite respeitando o escopo de camera do Operador.

        Ver `app/utils/salas.py`. Antes disto todo emit era broadcast e o
        operador de um setor recebia o feed de todos os outros.
        """
        emitir_para_camera(self.socketio, evento, payload, self.camera_id)

    def _emit_active(self, active: list[dict[str, Any]]) -> None:
        """Emite a lista de ativos quando ela MUDA (ou a cada 2 s, de pulsação).

        Antes saía a cada chamada de `process` — ou seja, a cada frame de cada
        câmera, ~12 vezes por segundo, com a mesma lista. Com o Socket.IO em
        long-polling, cada emit é serializado e enfileirado por cliente. A
        pulsação garante que um painel que perdeu um evento se acerte sozinho.
        """
        assinatura = tuple((a.get("id"), a.get("status"), a.get("occurrences"), a.get("last_seen_at")) for a in active)
        agora = monotonic()
        if assinatura == self._ultima_assinatura_ativos and agora - self._ultimo_emit_ativos < PULSACAO_ATIVOS_S:
            return
        self._ultima_assinatura_ativos = assinatura
        self._ultimo_emit_ativos = agora
        self._emitir("active_alerts", {"camera_id": self.camera_id, "items": active, "count": len(active)})

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


    def resolve_all(self, *, reason: str = "manual_reset", silenciar_s: float = 0.0) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        if silenciar_s > 0:
            agora = monotonic()
            for key, estado in self._states.items():
                self._silenciados[key] = {
                    "ate": agora + float(silenciar_s),
                    "visto": agora,
                    "rule": estado.rule_alert.rule,
                    "box": self._caixa_da_pessoa(estado.rule_alert.metadata),
                }
        for key in list(self._states.keys()):
            state = self._states[key]
            if state.alert is not None:
                # Chamado também do `stop()`, na thread da requisição: o alerta
                # foi criado na sessão da thread do worker.
                state.alert = self.repository.na_sessao(state.alert)
            if state.alert is not None and state.alert.status == "active":
                state.alert = self.repository.resolve(
                    state.alert,
                    metadata=(state.alert.metadata_json or {}) | {"resolution_reason": reason},
                )
                payload = state.alert.to_dict()
                state.snapshot = payload
                resolved.append(payload)
                self._emitir("alert_resolved", payload)
        self._states.clear()
        self._emit_active([])
        return resolved

    def reset(self) -> None:
        self._states.clear()
        self._silenciados.clear()
        self._ultima_assinatura_ativos = None
