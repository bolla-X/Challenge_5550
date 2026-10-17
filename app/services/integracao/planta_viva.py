"""Estado vivo da planta (M2): resume os workers a cada ~1 s e publica.

Uma fonte só para a torre de luz virtual (`/torre`, Modo TV), o OPC UA, o MQTT e
o webhook: o `estado_da_planta` calculado aqui é o mesmo que vai para todos.
Alerta novo (id que não estava ativo no tique anterior) sai em
`visionepi/<camera>/alerta` e no webhook; a latência é a do tique (≤ 1 s), em
troca de não tocar no loop de captura de nenhuma câmera.

Nada aqui identifica pessoa: só contagens por regra, conformidade agregada e a
mensagem do alerta (que traz o rótulo de rastreio, nunca nome).
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from app.services.integracao.estado import estado_da_planta
from app.utils.salas import SALA_PARQUE

logger = logging.getLogger(__name__)

CRITICA = "critical"


def resumo_da_camera(worker: Any, nome: str) -> dict[str, Any]:
    """Resumo de UMA câmera no formato de entrada de `estado_da_planta`.

    Lê só snapshots (dicts) que o próprio worker publica para outros threads;
    nunca o ORM. `getattr` defensivo: dublês de teste e workers parados não têm tudo.
    """
    rodando = bool(getattr(getattr(worker, "_running", None), "is_set", lambda: False)())
    ativos: list[dict[str, Any]] = []
    incidentes: list[dict[str, Any]] = []
    servico = getattr(worker, "alert_state_service", None)
    if rodando and servico is not None:
        try:
            ativos = list(servico.active_alerts())
            incidentes = list(servico.active_incidents())
        except Exception:  # noqa: BLE001  (resumo é melhor esforço; nunca derruba o tique)
            ativos, incidentes = [], []
    por_regra: dict[str, int] = {}
    for inc in incidentes:
        regra = str(inc.get("rule") or inc.get("regra") or "desconhecida")
        por_regra[regra] = por_regra.get(regra, 0) + 1
    if not incidentes:
        for a in ativos:
            regra = str(a.get("rule") or "desconhecida")
            por_regra[regra] = por_regra.get(regra, 0) + 1
    criticos = [a for a in ativos if a.get("severity") == CRITICA]
    ultimo = max(ativos, key=lambda a: str(a.get("created_at") or ""), default=None)
    saude = "ok"
    monitor_saude = getattr(worker, "saude_visual", None)
    if rodando and monitor_saude is not None:
        try:
            saude = str(monitor_saude.estado().get("estado") or "ok")
        except Exception:  # noqa: BLE001
            saude = "ok"
    sinal = "live"
    if rodando:
        try:
            sinal = str(worker.video_stream.status().to_dict().get("state") or "live")
        except Exception:  # noqa: BLE001
            sinal = "live"
    if not rodando or sinal in ("reconnecting", "unavailable"):
        estado = "offline"
    elif criticos:
        estado = "alarme"
    elif ativos:
        estado = "atencao"
    else:
        estado = "ok"
    conformidade = None
    try:
        conformidade = worker.andon.resumo().get("conformidade_atual") if rodando else None
    except Exception:  # noqa: BLE001
        conformidade = None
    return {
        "id": worker.camera_id,
        "nome": nome,
        "estado": estado,
        "incidentes_por_regra": por_regra,
        "incidentes_criticos": len(criticos),
        "conformidade": conformidade,
        "ultimo_alerta": (
            {"mensagem": ultimo.get("message"), "severidade": ultimo.get("severity"), "ts": ultimo.get("created_at")} if ultimo else None
        ),
        "saude_visual": saude,
        "critico_nao_reconhecido": any(not a.get("acknowledged") for a in criticos),
        "_ativos": ativos,
    }


class PublicadorDaPlanta:
    """Tique periódico: resume, publica (com deduplicação no gerente) e avisa a UI."""

    def __init__(self, workers: Callable[[], list[tuple[Any, str]]], gerente: Any, socketio: Any = None, intervalo_s: float = 1.0) -> None:
        self._workers = workers
        self.gerente = gerente
        self.socketio = socketio
        self.intervalo_s = intervalo_s
        self._lock = threading.Lock()
        self._estado: dict[str, Any] | None = None
        self._ids_vistos: dict[int, set[Any]] = {}
        self._torre_anterior: tuple[str, bool] | None = None
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def estado(self) -> dict[str, Any]:
        with self._lock:
            if self._estado is not None:
                return self._estado
        return self.tique()

    def tique(self) -> dict[str, Any]:
        resumos = []
        for worker, nome in self._workers():
            try:
                resumos.append(resumo_da_camera(worker, nome))
            except Exception as exc:  # noqa: BLE001
                logger.warning("resumo_de_camera_falhou",
                               extra={"camera_id": getattr(worker, "camera_id", None), "erro": type(exc).__name__})
        novos: list[tuple[int, dict[str, Any]]] = []
        for r in resumos:
            ativos = r.pop("_ativos")
            ids = {a.get("id") for a in ativos}
            antes = self._ids_vistos.get(r["id"])
            if antes is not None:
                novos += [(r["id"], a) for a in ativos if a.get("id") not in antes]
            self._ids_vistos[r["id"]] = ids
        estado = estado_da_planta(resumos)
        with self._lock:
            self._estado = estado
        if self.gerente is not None:
            for camera_id, alerta in novos:
                self.gerente.publicar_alerta(camera_id, {
                    "id": alerta.get("id"), "camera_id": camera_id, "regra": alerta.get("rule"), "severidade": alerta.get("severity"),
                    "mensagem": alerta.get("message"), "ts": alerta.get("created_at"),
                })
            self.gerente.publicar_estado(estado)
        torre = (estado["torre"], bool(estado["sirene"]))
        if self.socketio is not None and torre != self._torre_anterior:
            try:
                self.socketio.emit("estado_da_planta", estado, to=SALA_PARQUE)
            except Exception:  # noqa: BLE001
                pass
        self._torre_anterior = torre
        return estado

    def iniciar(self) -> None:
        if self._thread is not None:
            return

        def laco() -> None:
            if self.gerente is not None:
                try:
                    self.gerente.iniciar()
                except Exception as exc:  # noqa: BLE001  (o gerente já não lança; isto é cinto e suspensório)
                    logger.warning("integracao_nao_iniciou", extra={"erro": type(exc).__name__})
            while not self._parar.wait(self.intervalo_s):
                try:
                    self.tique()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("tique_da_planta_falhou", extra={"erro": type(exc).__name__})

        self._thread = threading.Thread(target=laco, name="estado-da-planta", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        if self.gerente is not None:
            try:
                self.gerente.parar()
            except Exception:  # noqa: BLE001
                pass
