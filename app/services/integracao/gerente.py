"""Gerente da integração industrial: sobe o que a configuração liga e nunca derruba o app.

O `MonitorService` fala só com esta classe. Ela lê as chaves de configuração,
liga OPC UA, broker MQTT embutido, publicador MQTT e webhook, e entrega o estado
da planta e os alertas a quem estiver no ar.

Contrato de robustez: `iniciar()`, `publicar_*()` e `parar()` NUNCA lançam. Porta
ocupada, broker fora, URL de webhook rejeitada: tudo vira `status()` com mensagem
em pt-BR, e o resto da integração continua. Integração é periférico; o laço de
captura de EPI não pode parar por causa dela.

Chaves de configuração (todas opcionais; padrão = desligado):

    OPCUA_ATIVO (bool)  OPCUA_HOST ("127.0.0.1")  OPCUA_PORTA (4840)
    MQTT_ATIVO (bool)   MQTT_HOST ("127.0.0.1")   MQTT_PORTA (1883)
    MQTT_BROKER_EMBUTIDO (bool)   sobe o broker amqtt em MQTT_HOST:MQTT_PORTA (demo offline)
    WEBHOOK_URL (str)   WEBHOOK_PERMITIR_REDE_LOCAL (bool)
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from .broker import BrokerEmbutido
from .mqtt import PublicadorMQTT
from .opcua import ServidorOPCUA
from .webhook import UrlWebhookInvalida, Webhook

logger = logging.getLogger(__name__)

INTERVALO_REPUBLICACAO_S = 5.0
_VERDADEIROS = {"1", "true", "t", "yes", "y", "sim", "on"}


def _booleano(valor: Any) -> bool:
    if isinstance(valor, str):
        return valor.strip().lower() in _VERDADEIROS
    return bool(valor)


def _porta(config: Mapping[str, Any], chave: str, padrao: int) -> int:
    bruto = config.get(chave)
    if bruto in (None, ""):
        return padrao
    try:
        porta = int(bruto)
    except (TypeError, ValueError):
        raise ValueError(f"{chave} deve ser um número de porta (recebi {bruto!r}).") from None
    if not 1 <= porta <= 65535:
        raise ValueError(f"{chave} fora do intervalo 1-65535 (recebi {porta}).")
    return porta


def _situacao(ativo: bool, estado: str, endpoint: str | None = None, erro: str | None = None) -> dict[str, Any]:
    return {"ativo": ativo, "estado": estado, "endpoint": endpoint, "erro": erro}


def _chave_de_estado(estado: dict[str, Any]) -> str:
    """Identidade do estado SEM o carimbo de tempo (ele muda a cada chamada)."""
    return json.dumps({k: v for k, v in estado.items() if k != "ts"}, sort_keys=True, default=str)


class GerenteDeIntegracao:
    def __init__(
        self,
        config: Mapping[str, Any],
        relogio: Callable[[], float] = time.monotonic,
        agora: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._config = config
        self._relogio = relogio
        self._agora = agora
        self._tranca = threading.Lock()
        self._opcua: ServidorOPCUA | None = None
        self._mqtt: PublicadorMQTT | None = None
        self._broker: BrokerEmbutido | None = None
        self._webhook: Webhook | None = None
        self._status = self._status_desligado()
        self._iniciado = False
        self._ultima_chave: str | None = None
        self._ultima_publicacao = 0.0

    @staticmethod
    def _status_desligado() -> dict[str, dict[str, Any]]:
        return {nome: _situacao(False, "desligado") for nome in ("opcua", "mqtt", "broker", "webhook")}

    # -- ciclo de vida -------------------------------------------------------

    def iniciar(self) -> dict[str, dict[str, Any]]:
        """Sobe o que estiver ligado e devolve `status()`. Nunca lança."""
        with self._tranca:
            if self._iniciado:
                return self._status_atual()
            self._iniciado = True
            self._status = self._status_desligado()
            self._subir_broker()
            self._subir_mqtt()
            self._subir_opcua()
            self._subir_webhook()
        return self.status()

    def parar(self) -> None:
        with self._tranca:
            componentes = [self._webhook, self._mqtt, self._opcua, self._broker]
            self._webhook = self._mqtt = self._opcua = self._broker = None
            self._iniciado = False
            self._ultima_chave = None
        for componente in componentes:
            if componente is None:
                continue
            try:
                componente.parar()
            except Exception:  # noqa: BLE001
                logger.warning("integracao_parar_falhou", extra={"componente": type(componente).__name__}, exc_info=True)
        self._status = self._status_desligado()

    def status(self) -> dict[str, dict[str, Any]]:
        return self._status_atual()

    def _status_atual(self) -> dict[str, dict[str, Any]]:
        atual = {nome: dict(situacao) for nome, situacao in self._status.items()}
        if self._mqtt is not None:  # o MQTT reconecta sozinho: o estado muda depois do iniciar()
            mqtt = self._mqtt.status()
            atual["mqtt"].update(
                estado="no_ar" if mqtt["conectado"] else "falhou",
                erro=mqtt["erro"],
            )
        if self._webhook is not None:
            atual["webhook"]["estatisticas"] = self._webhook.estatisticas()
        return atual

    def _falha(self, nome: str, ativo_em: str | None, mensagem: str, exc: BaseException | None = None) -> None:
        self._status[nome] = _situacao(True, "falhou", ativo_em, mensagem)
        logger.warning("integracao_falhou", extra={"componente": nome, "erro": mensagem}, exc_info=exc)

    def _subir_broker(self) -> None:
        if not _booleano(self._config.get("MQTT_BROKER_EMBUTIDO")):
            return
        host = self._config.get("MQTT_HOST") or "127.0.0.1"
        try:
            broker = BrokerEmbutido(_porta(self._config, "MQTT_PORTA", 1883), host)
            situacao = broker.iniciar()
        except Exception as exc:  # noqa: BLE001
            self._falha("broker", None, f"Não foi possível iniciar o broker MQTT embutido: {exc}", exc)
            return
        self._status["broker"] = _situacao(True, situacao["estado"], situacao["endpoint"], situacao["erro"])
        if situacao["estado"] == "no_ar":
            self._broker = broker

    def _subir_mqtt(self) -> None:
        if not _booleano(self._config.get("MQTT_ATIVO")):
            return
        host = self._config.get("MQTT_HOST") or "127.0.0.1"
        try:
            publicador = PublicadorMQTT(host, _porta(self._config, "MQTT_PORTA", 1883))
            situacao = publicador.iniciar()
        except Exception as exc:  # noqa: BLE001
            self._falha("mqtt", None, f"Não foi possível iniciar o publicador MQTT: {exc}", exc)
            return
        self._mqtt = publicador  # fica de pé mesmo desconectado: ele reconecta sozinho
        self._status["mqtt"] = _situacao(True, "no_ar" if situacao["conectado"] else "falhou", situacao["endpoint"], situacao["erro"])

    def _subir_opcua(self) -> None:
        if not _booleano(self._config.get("OPCUA_ATIVO")):
            return
        try:
            servidor = ServidorOPCUA(_porta(self._config, "OPCUA_PORTA", 4840), self._config.get("OPCUA_HOST") or "127.0.0.1")
            situacao = servidor.iniciar()
        except Exception as exc:  # noqa: BLE001
            self._falha("opcua", None, f"Não foi possível iniciar o servidor OPC UA: {exc}", exc)
            return
        self._status["opcua"] = _situacao(True, situacao["estado"], situacao["endpoint"], situacao["erro"])
        if situacao["estado"] == "no_ar":
            self._opcua = servidor

    def _subir_webhook(self) -> None:
        url = str(self._config.get("WEBHOOK_URL") or "").strip()
        if not url:
            return
        try:
            webhook = Webhook(url, permitir_rede_local=_booleano(self._config.get("WEBHOOK_PERMITIR_REDE_LOCAL")))
        except UrlWebhookInvalida as exc:
            self._falha("webhook", None, f"WEBHOOK_URL rejeitada: {exc}")
            return
        except Exception as exc:  # noqa: BLE001
            self._falha("webhook", None, f"Não foi possível configurar o webhook: {exc}", exc)
            return
        webhook.iniciar()
        self._webhook = webhook
        self._status["webhook"] = _situacao(True, "no_ar", webhook.endpoint)

    # -- publicação ----------------------------------------------------------

    def publicar_estado(self, estado_planta: dict[str, Any]) -> bool:
        """Entrega o estado da planta ao OPC UA e ao MQTT. Só publica se MUDOU ou passaram 5 s.

        O laço de captura chama isto a cada ciclo; sem a deduplicação seriam dezenas
        de publicações idênticas por segundo. O reenvio periódico existe para quem
        conectou depois e para o OPC UA/CLP perceber que o gateway está vivo.
        Devolve True se publicou.
        """
        try:
            chave = _chave_de_estado(estado_planta)
            with self._tranca:
                agora = self._relogio()
                if chave == self._ultima_chave and agora - self._ultima_publicacao < INTERVALO_REPUBLICACAO_S:
                    return False
                self._ultima_chave = chave
                self._ultima_publicacao = agora
                opcua, mqtt = self._opcua, self._mqtt
            if opcua is not None:
                opcua.publicar(estado_planta)
            if mqtt is not None:
                mqtt.publicar_estado(estado_planta)
            return True
        except Exception:  # noqa: BLE001 - integração nunca derruba o laço de captura
            logger.warning("integracao_publicar_estado_falhou", exc_info=True)
            return False

    def publicar_alerta(self, camera_id: Any, alerta: dict[str, Any]) -> bool:
        """Entrega um alerta ao MQTT (`visionepi/<camera_id>/alerta`) e ao webhook. True se algum aceitou."""
        aceito = False
        try:
            mqtt, webhook = self._mqtt, self._webhook
            if mqtt is not None:
                aceito = mqtt.publicar_alerta(camera_id, alerta) or aceito
            if webhook is not None:
                carga = {"tipo": "alerta", "camera_id": camera_id, "alerta": alerta, "ts": self._agora().isoformat()}
                aceito = webhook.enviar(carga) or aceito
        except Exception:  # noqa: BLE001
            logger.warning("integracao_publicar_alerta_falhou", exc_info=True)
        return aceito
