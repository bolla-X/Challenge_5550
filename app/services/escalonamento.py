"""Escalonamento de alerta crítico sem reconhecimento (MISSÃO 4, M7).

Alerta CRÍTICO que ninguém reconheceu sobe em dois níveis, cada um no máximo
UMA vez por alerta:

- nível 1, "supervisor": há `supervisor_s` sem reconhecimento. Evento socket
  `escalonamento` para a sala do parque (o PWA do supervisor avisa) e linha
  `alerta_escalonado` na linha do tempo;
- nível 2, "tv_torre": há `tv_s` sem reconhecimento. A câmera passa a sair com
  `escalonado: true` no resumo e a torre/TV piscam em vermelho; o mesmo evento
  e a mesma linha do tempo, agora com `nivel: 2`.

Reconhecer encerra: o alerta sai do ciclo e a câmera deixa de ficar escalonada.
Resolver idem (o alerta deixa de estar ativo).

Prazos: da regra do editor (`metadata["acoes"]["escalonamento"]`, em segundos)
quando houver; senão `ESCALONAR_SUPERVISOR_S` (60) e `ESCALONAR_TV_S` (180).
O nível 2 nunca vem ANTES do nível 1: se a regra pede `supervisor_s` maior que o
`tv_s` herdado, o `tv_s` sobe para o mesmo valor.

Só estado em memória e nenhum relógio global: `Escalonador.avaliar` recebe o
instante. Nada aqui identifica pessoa; só alerta, câmera e regra.

O tempo até reconhecer (criação → "avisei") alimenta a Liga de Setores como
indicador POSITIVO (`registrar_reconhecimento`, que reaproveita
`liga.pontos_do_reconhecimento`): reconhecer rápido vale ponto ao setor,
demorar não tira nada de ninguém. O escalonamento é aviso à supervisão, nunca
punição.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from app.utils.salas import SALA_PARQUE

logger = logging.getLogger(__name__)

CRITICA = "critical"
NIVEL_SUPERVISOR = 1
NIVEL_TV = 2
PAPEL_DO_NIVEL = {NIVEL_SUPERVISOR: "supervisor", NIVEL_TV: "tv_torre"}
EVENTO_SOCKET = "escalonamento"
TIPO_DO_EVENTO = "alerta_escalonado"
PADRAO_SUPERVISOR_S = 60.0
PADRAO_TV_S = 180.0
# Quantos alertas já escalonados o escalonador lembra (garante "uma vez por
# nível" mesmo se um alerta sumir do resumo por um tique e voltar).
MEMORIA_MAXIMA = 4096


@dataclass(frozen=True)
class Prazos:
    supervisor_s: float
    tv_s: float
    origem: str  # "regra" | "configuracao"


def instante(valor: Any) -> datetime | None:
    """`datetime` com fuso a partir de ISO-8601 ou `datetime` (sem fuso = UTC, como o banco guarda)."""
    if isinstance(valor, datetime):
        resultado = valor
    elif isinstance(valor, str) and valor.strip():
        try:
            resultado = datetime.fromisoformat(valor.strip())
        except ValueError:
            return None
    else:
        return None
    return resultado.replace(tzinfo=timezone.utc) if resultado.tzinfo is None else resultado


def _segundos_positivos(valor: Any) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor) if valor > 0 else None


def prazos_do_alerta(alerta: Mapping[str, Any], supervisor_s: float, tv_s: float) -> Prazos:
    """Prazos da regra do editor quando o alerta os traz; o que faltar vem da configuração."""
    escalonamento = ((alerta.get("metadata") or {}).get("acoes") or {}).get("escalonamento") or {}
    da_regra_sup = _segundos_positivos(escalonamento.get("supervisor_s")) if isinstance(escalonamento, dict) else None
    da_regra_tv = _segundos_positivos(escalonamento.get("tv_s")) if isinstance(escalonamento, dict) else None
    sup = da_regra_sup if da_regra_sup is not None else supervisor_s
    tv = da_regra_tv if da_regra_tv is not None else tv_s
    return Prazos(sup, max(tv, sup), "regra" if (da_regra_sup is not None or da_regra_tv is not None) else "configuracao")


class Escalonador:
    """Decide, a cada tique, quais alertas críticos sobem de nível."""

    def __init__(self, supervisor_s: float = PADRAO_SUPERVISOR_S, tv_s: float = PADRAO_TV_S) -> None:
        self.supervisor_s = _segundos_positivos(supervisor_s) or PADRAO_SUPERVISOR_S
        self.tv_s = _segundos_positivos(tv_s) or PADRAO_TV_S
        self._lock = threading.Lock()
        self._emitidos: OrderedDict[Any, int] = OrderedDict()  # id do alerta -> maior nível já emitido
        self._escalonadas: frozenset[Any] = frozenset()

    @classmethod
    def da_configuracao(cls, config: Mapping[str, Any]) -> Escalonador:
        return cls(
            supervisor_s=config.get("ESCALONAR_SUPERVISOR_S", PADRAO_SUPERVISOR_S),
            tv_s=config.get("ESCALONAR_TV_S", PADRAO_TV_S),
        )

    def avaliar(self, alertas_ativos_por_camera: Mapping[Any, Iterable[Mapping[str, Any]]], agora: datetime) -> list[dict[str, Any]]:
        """Alertas ativos por câmera (dicts de `Alert.to_dict()`) -> eventos de escalonamento NOVOS.

        Cada evento: `nivel`, `papel`, `alerta_id`, `camera_id`, `regra`, `severidade`, `mensagem`,
        `segundos_sem_reconhecer`, `prazo_s`, `origem_do_prazo`, `ts`. Depois da chamada,
        `camera_escalonada` / `marcar` refletem o tique.
        """
        agora = instante(agora) or datetime.now(timezone.utc)
        eventos: list[dict[str, Any]] = []
        escalonadas: set[Any] = set()
        with self._lock:
            for camera_id, alertas in (alertas_ativos_por_camera or {}).items():
                for alerta in alertas or ():
                    if alerta.get("severity") != CRITICA or alerta.get("acknowledged"):
                        continue  # só crítico; reconhecer encerra
                    alerta_id = alerta.get("id")
                    criado = instante(alerta.get("created_at"))
                    if alerta_id is None or criado is None:
                        continue
                    espera = (agora - criado).total_seconds()
                    prazos = prazos_do_alerta(alerta, self.supervisor_s, self.tv_s)
                    nivel = self._emitidos.get(alerta_id, 0)
                    for alvo, prazo in ((NIVEL_SUPERVISOR, prazos.supervisor_s), (NIVEL_TV, prazos.tv_s)):
                        if nivel >= alvo or espera < prazo:
                            continue
                        nivel = alvo
                        eventos.append({
                            "nivel": alvo,
                            "papel": PAPEL_DO_NIVEL[alvo],
                            "alerta_id": alerta_id,
                            "camera_id": alerta.get("camera_id", camera_id),
                            "regra": alerta.get("rule"),
                            "severidade": alerta.get("severity"),
                            "mensagem": alerta.get("message"),
                            "segundos_sem_reconhecer": round(espera, 1),
                            "prazo_s": prazo,
                            "origem_do_prazo": prazos.origem,
                            "ts": agora.isoformat(),
                        })
                    if nivel:
                        self._emitidos[alerta_id] = nivel
                        self._emitidos.move_to_end(alerta_id)
                    if nivel >= NIVEL_TV:
                        escalonadas.add(camera_id)
            while len(self._emitidos) > MEMORIA_MAXIMA:
                self._emitidos.popitem(last=False)
            self._escalonadas = frozenset(escalonadas)
        return eventos

    def camera_escalonada(self, camera_id: Any) -> bool:
        with self._lock:
            return camera_id in self._escalonadas

    def marcar(self, resumos: Iterable[dict[str, Any]]) -> None:
        """Põe `escalonado` (bool) em cada resumo de câmera, o campo que `estado_da_planta` repassa à torre e à TV."""
        for resumo in resumos:
            resumo["escalonado"] = self.camera_escalonada(resumo.get("id"))


# ---------------------------------------------------------------- publicação ---
def publicar(eventos: Iterable[dict[str, Any]], socketio: Any = None, app: Any = None) -> None:
    """Emite `escalonamento` ao parque e grava `alerta_escalonado` na linha do tempo.

    Melhor esforço: uma falha aqui é registrada e nunca derruba o tique da planta.
    `app` abre o contexto do Flask para gravar a linha do tempo quando quem chama
    (o thread do tique) não tem um.
    """
    for evento in eventos:
        if socketio is not None:
            try:
                socketio.emit(EVENTO_SOCKET, evento, to=SALA_PARQUE)
            except Exception as exc:  # noqa: BLE001
                logger.warning("escalonamento_nao_emitido", extra={"alerta_id": evento.get("alerta_id"), "erro": type(exc).__name__})
        try:
            if app is not None:
                with app.app_context():
                    _gravar_na_linha_do_tempo(evento)
            else:
                _gravar_na_linha_do_tempo(evento)
        except Exception as exc:  # noqa: BLE001
            logger.warning("escalonamento_nao_gravado", extra={"alerta_id": evento.get("alerta_id"), "erro": type(exc).__name__})


def _gravar_na_linha_do_tempo(evento: Mapping[str, Any]) -> None:
    from app.repositories.event_repository import EventRepository

    destino = "ao supervisor" if evento["nivel"] == NIVEL_SUPERVISOR else "à TV e à torre"
    segundos = int(evento["segundos_sem_reconhecer"])
    EventRepository().create(
        event_type=TIPO_DO_EVENTO,
        severity="high" if evento["nivel"] == NIVEL_SUPERVISOR else CRITICA,
        message=f"Alerta crítico sem reconhecimento há {segundos} s, escalonado {destino}: {evento.get('mensagem') or ''}"[:255],
        camera_id=evento.get("camera_id"),
        subject=f"alerta:{evento['alerta_id']}",
        metadata=dict(evento),
    )


# ------------------------------------------------- tempo até reconhecer (Liga) ---
def segundos_ate_reconhecer(criado_em: Any, reconhecido_em: Any) -> float | None:
    inicio, fim = instante(criado_em), instante(reconhecido_em)
    if inicio is None or fim is None:
        return None
    return round(max(0.0, (fim - inicio).total_seconds()), 1)


def registrar_reconhecimento(alerta: Any) -> dict[str, Any] | None:
    """Tempo até reconhecer o alerta (de `Alert`, já com `acknowledged_at`) e o ponto da Liga, se houver.

    Se o alerta pertence a um incidente, o relógio e a chave do ponto são os do
    INCIDENTE (como em `/api/incidentes/<id>/reconhecer`): reconhecer o incidente
    e reconhecer o alerta dele é o mesmo fato e vale um ponto só, não dois.
    Devolve `{"segundos", "ponto"}` (`ponto` é None quando passou de 3 min) ou None
    quando não dá para medir. Nunca levanta: a Liga não derruba quem reconheceu.
    """
    try:
        from app.extensions import db
        from app.models import Incidente
        from app.services.liga import pontos_do_reconhecimento, registrar

        metadata = alerta.metadata_json or {}
        incidente = db.session.get(Incidente, metadata["incidente_id"]) if metadata.get("incidente_id") else None
        if incidente is not None:
            origem, ref, camera_id = incidente.aberto_em, f"incidente:{incidente.id}", incidente.camera_id
        else:
            origem, ref, camera_id = alerta.created_at, f"alerta:{alerta.id}", alerta.camera_id
        segundos = segundos_ate_reconhecer(origem, metadata.get("acknowledged_at"))
        if segundos is None:
            return None
        tipo = pontos_do_reconhecimento(segundos)
        if tipo:
            registrar(tipo, ref=ref, camera_id=camera_id)
        return {"segundos": segundos, "ponto": tipo}
    except Exception as exc:  # noqa: BLE001
        logger.warning("reconhecimento_nao_registrado", extra={"erro": type(exc).__name__})
        return None
