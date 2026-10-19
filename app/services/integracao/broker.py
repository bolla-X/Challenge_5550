"""Broker MQTT embutido (amqtt) para a demo OFFLINE: sem Mosquitto, sem Docker, sem internet.

Mesmo desenho do `opcua.py`: thread próprio com event loop próprio, porque o app é
threading e o amqtt é asyncio. `iniciar()` devolve o status e nunca lança.

Escopo: demo e bancada. Aceita conexão anônima, sem TLS, sem ACL e guarda
retained só em memória (some ao reiniciar). Por isso RECUSA subir fora do
loopback (127.0.0.1/localhost). Para produção use um broker de verdade
(Mosquitto, EMQX, HiveMQ) com TLS e credencial e aponte `MQTT_HOST`/`MQTT_PORTA` para ele.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from amqtt.broker import Broker

from ._erros import descrever_falha_de_bind

logger = logging.getLogger(__name__)
# O amqtt loga cada pacote em INFO/DEBUG; em demo isso afoga o console.
logging.getLogger("amqtt").setLevel(logging.WARNING)
logging.getLogger("transitions").setLevel(logging.WARNING)

HOSTS_LOCAIS = ("127.0.0.1", "localhost")


class BrokerEmbutido:
    def __init__(self, porta: int = 1883, host: str = "127.0.0.1", timeout_inicio_s: float = 10.0) -> None:
        self.porta = int(porta)
        self.host = host
        self.timeout_inicio_s = timeout_inicio_s
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._broker: Broker | None = None
        self._pronto = threading.Event()
        self._erro: str | None = None
        self._no_ar = False

    @property
    def endpoint(self) -> str:
        return f"mqtt://{self.host}:{self.porta}"

    def status(self) -> dict[str, Any]:
        return {"estado": "no_ar" if self._no_ar else "falhou", "endpoint": self.endpoint, "erro": self._erro}

    def iniciar(self) -> dict[str, Any]:
        """Sobe o broker e devolve `status()`. Nunca lança: falha vira `erro` em pt-BR."""
        if self._thread is not None and self._thread.is_alive():
            return self.status()
        if self.host not in HOSTS_LOCAIS:
            # Anônimo e sem TLS: aberto na rede, qualquer máquina publicaria no tópico de alerta da planta.
            self._erro = (
                f"O broker MQTT embutido é anônimo e sem TLS: só sobe em 127.0.0.1 ou localhost (recebi {self.host}). "
                "Use um broker da planta com TLS e credencial e aponte MQTT_HOST para ele."
            )
            logger.warning("broker_embutido_recusado_fora_do_loopback", extra={"host": self.host})
            return self.status()
        self._pronto.clear()
        self._erro = None
        self._thread = threading.Thread(target=self._executar, name="mqtt-broker-embutido", daemon=True)
        self._thread.start()
        if not self._pronto.wait(self.timeout_inicio_s) and self._erro is None:
            self._erro = f"O broker MQTT embutido não respondeu em {self.timeout_inicio_s:g} s."
        if self._erro is not None:
            self.parar()
        return self.status()

    def parar(self) -> None:
        loop, thread = self._loop, self._thread
        if loop is not None and thread is not None and thread.is_alive():
            futuro = asyncio.run_coroutine_threadsafe(self._encerrar(), loop)
            try:
                futuro.result(timeout=5)
            except Exception:  # noqa: BLE001 - parar nunca lança; o thread sai mesmo assim
                logger.warning("broker_parar_falhou", exc_info=True)
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=5)
        elif thread is not None:
            thread.join(timeout=5)
        self._no_ar = False
        self._thread = None
        self._loop = None

    def _configuracao(self) -> dict[str, Any]:
        return {
            "listeners": {"default": {"type": "tcp", "bind": f"{self.host}:{self.porta}"}},
            "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True}},
        }

    def _executar(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._subir())
            self._no_ar = True
        except Exception as exc:  # noqa: BLE001 - qualquer falha de subida vira status
            self._erro = self._mensagem_de_erro(exc)
            logger.warning("broker_nao_subiu", extra={"erro": str(exc)})
            self._loop = None
            self._pronto.set()
            loop.close()
            return
        self._pronto.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    def _mensagem_de_erro(self, exc: Exception) -> str:
        return descrever_falha_de_bind(exc, "MQTT embutido", self.host, self.porta)

    async def _subir(self) -> None:
        broker = Broker(self._configuracao(), loop=asyncio.get_running_loop())
        await broker.start()
        self._broker = broker

    async def _encerrar(self) -> None:
        broker, self._broker = self._broker, None
        if broker is not None:
            await broker.shutdown()
