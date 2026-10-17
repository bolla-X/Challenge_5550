"""Publicador MQTT (paho-mqtt 2.x) para o estado e os alertas da planta.

Tópicos (prefixo configurável, padrão `visionepi`):

    <prefixo>/<camera_id>/alerta   JSON do alerta, QoS 1, SEM retain (evento)
    <prefixo>/planta/estado        JSON do estado da planta, QoS 1, retain=True (estado)

Estado com retain: um painel que conecta depois recebe o último estado na hora, em
vez de esperar a próxima mudança. Alerta é evento: retain faria um assinante novo
"ver" um alerta de ontem como se fosse de agora.

Nunca bloqueia o chamador: `publish()` do paho só enfileira e o thread de rede
(`loop_start`) cuida do resto. Broker fora do ar não lança nada: o cliente tenta
reconectar sozinho (1 s, dobrando até 30 s) e `status()` diz que está desconectado.
Enquanto desconectado a fila do paho guarda até `MAX_FILA` mensagens; passou disso,
`publicar_*` devolve False (descarta) em vez de crescer sem limite.

Sem TLS nem credenciais: broker de chão de fábrica isolado (ver limitações no
`opcua.py`).
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

import paho.mqtt.client as paho

logger = logging.getLogger(__name__)

MAX_FILA = 200
_CARACTERES_PROIBIDOS = {"+": "_", "#": "_", "/": "_", "\x00": "_"}


def _segmento(valor: Any) -> str:
    """Um segmento de tópico: sem `/`, `+`, `#` (que viram curinga ou nível a mais)."""
    texto = str(valor).strip()
    return "".join(_CARACTERES_PROIBIDOS.get(c, c) for c in texto) or "_"


def _json(dados: Any) -> bytes:
    return json.dumps(dados, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")


class PublicadorMQTT:
    def __init__(self, host: str, porta: int = 1883, prefixo: str = "visionepi", client_id: str | None = None) -> None:
        self.host = host
        self.porta = int(porta)
        self.prefixo = prefixo.strip("/") or "visionepi"
        self._cliente = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id=client_id or "", clean_session=True)
        self._cliente.reconnect_delay_set(min_delay=1, max_delay=30)
        self._cliente.max_queued_messages_set(MAX_FILA)
        self._cliente.on_connect = self._ao_conectar
        self._cliente.on_connect_fail = self._ao_falhar_conexao
        self._cliente.on_disconnect = self._ao_desconectar
        self._conectado = threading.Event()
        self._tentativa_resolvida = threading.Event()
        self._erro: str | None = None
        self._iniciado = False

    @property
    def endpoint(self) -> str:
        return f"mqtt://{self.host}:{self.porta}"

    @property
    def conectado(self) -> bool:
        return self._conectado.is_set()

    def topico_alerta(self, camera_id: Any) -> str:
        return f"{self.prefixo}/{_segmento(camera_id)}/alerta"

    @property
    def topico_estado(self) -> str:
        return f"{self.prefixo}/planta/estado"

    def status(self) -> dict[str, Any]:
        return {"conectado": self.conectado, "endpoint": self.endpoint, "erro": None if self.conectado else self._erro}

    # -- callbacks (rodam no thread de rede do paho) -------------------------

    def _ao_conectar(self, _cliente, _dados, _flags, codigo, _props=None) -> None:
        if codigo.is_failure:
            self._erro = f"O broker MQTT em {self.host}:{self.porta} recusou a conexão ({codigo})."
        else:
            self._erro = None
            self._conectado.set()
        self._tentativa_resolvida.set()

    def _ao_falhar_conexao(self, _cliente, _dados) -> None:
        self._erro = f"Broker MQTT inacessível em {self.host}:{self.porta}; tentando reconectar."
        self._tentativa_resolvida.set()

    def _ao_desconectar(self, _cliente, _dados, _flags, codigo, _props=None) -> None:
        self._conectado.clear()
        self._erro = f"Conexão com o broker MQTT em {self.host}:{self.porta} perdida ({codigo}); tentando reconectar."

    # -- ciclo de vida -------------------------------------------------------

    def iniciar(self, aguardar_s: float = 2.0) -> dict[str, Any]:
        """Dispara a conexão em segundo plano e espera até `aguardar_s` pelo 1º resultado.

        Nunca lança. Se o broker não responde nesse prazo, devolve desconectado e o
        paho segue tentando; `status()` vira conectado quando ele atender.
        """
        if self._iniciado:
            return self.status()
        try:
            self._cliente.connect_async(self.host, self.porta, keepalive=30)
            self._cliente.loop_start()
            self._iniciado = True
        except Exception as exc:  # noqa: BLE001 - host inválido etc.: vira status, não exceção
            self._erro = f"Não foi possível iniciar o cliente MQTT para {self.host}:{self.porta}: {exc}"
            logger.warning("mqtt_nao_iniciou", extra={"erro": str(exc)})
            return self.status()
        self._tentativa_resolvida.wait(aguardar_s)
        if not self.conectado and self._erro is None:
            self._erro = f"Broker MQTT em {self.host}:{self.porta} não respondeu ainda; tentando reconectar."
        return self.status()

    def parar(self) -> None:
        if not self._iniciado:
            return
        self._iniciado = False
        try:
            self._cliente.disconnect()
        except Exception:  # noqa: BLE001
            logger.debug("mqtt_disconnect_falhou", exc_info=True)
        try:
            self._cliente.loop_stop()
        except Exception:  # noqa: BLE001
            logger.debug("mqtt_loop_stop_falhou", exc_info=True)
        self._conectado.clear()

    # -- publicação ----------------------------------------------------------

    def _publicar(self, topico: str, dados: Any, retain: bool) -> bool:
        if not self._iniciado:
            return False
        try:
            info = self._cliente.publish(topico, _json(dados), qos=1, retain=retain)
        except Exception as exc:  # noqa: BLE001 - nunca derruba o laço de captura
            logger.warning("mqtt_publicar_falhou", extra={"topico": topico, "erro": str(exc)})
            return False
        # NO_CONN: o paho guardou a mensagem na fila e reenvia quando reconectar (não é perda).
        return info.rc in (paho.MQTT_ERR_SUCCESS, paho.MQTT_ERR_NO_CONN)

    def publicar_alerta(self, camera_id: Any, alerta: dict[str, Any]) -> bool:
        """`<prefixo>/<camera_id>/alerta`, QoS 1, sem retain. False = não enfileirou."""
        return self._publicar(self.topico_alerta(camera_id), alerta, retain=False)

    def publicar_estado(self, estado_planta: dict[str, Any]) -> bool:
        """`<prefixo>/planta/estado`, QoS 1, retain=True. False = não enfileirou."""
        return self._publicar(self.topico_estado, estado_planta, retain=True)
