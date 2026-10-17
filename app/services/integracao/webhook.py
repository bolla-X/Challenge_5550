"""Webhook de saída (POST JSON) com defesa contra SSRF e fila que nunca trava o chamador.

O destino é configuração de quem administra a planta, mas a URL é uma entrada que
faz o servidor abrir conexão: sem validação, ela vira um jeito de alcançar o
serviço de metadados da nuvem (169.254.169.254) ou painéis internos. Por isso:

- só `http` e `https`, sem usuário/senha embutidos na URL;
- o host é RESOLVIDO e TODOS os endereços devolvidos são checados;
- SEMPRE bloqueados, mesmo com `permitir_rede_local=True`: link-local
  (169.254.0.0/16 e fe80::/10, onde moram os metadados de nuvem), multicast,
  não especificado (0.0.0.0, ::), reservado e os IPs de metadados conhecidos
  (fd00:ec2::254, 100.100.100.200);
- bloqueados por padrão e liberados só por `permitir_rede_local=True` (chão de
  fábrica costuma exigir): loopback, RFC1918 (10/8, 172.16/12, 192.168/16),
  ULA IPv6 (fc00::/7) e CGNAT (100.64/10);
- a conexão é aberta no IP JÁ VALIDADO (resolve-e-valida a cada envio, na hora de
  conectar), então trocar o DNS entre a checagem e o POST (DNS rebinding) não
  contorna nada. TLS continua verificando o nome original do host;
- redirecionamento NÃO é seguido: 3xx conta como falha (um 302 para
  `http://169.254.169.254/` seria o desvio clássico).

Sem rede no construtor: host que não resolve na hora de criar é aceito (a planta
pode subir antes da rede) e é checado de novo a cada envio.

Entrega: fila limitada em thread de fundo. Cheia, descarta a MAIS ANTIGA (o alerta
novo vale mais que o velho). Sem retentativa: o MQTT/OPC UA são o canal confiável.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import logging
import queue
import socket
import threading
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

Resolvedor = Callable[[str, int], list[str]]

_SEMPRE_BLOQUEADAS = [
    ipaddress.ip_network(rede) for rede in ("0.0.0.0/8", "169.254.0.0/16", "fe80::/10", "fd00:ec2::254/128", "100.100.100.200/32")
]
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


class UrlWebhookInvalida(ValueError):
    """URL de webhook rejeitada (esquema, host ou endereço de destino não permitidos)."""


class HostNaoResolvido(UrlWebhookInvalida):
    """O DNS não resolveu o host (pode ser rede ainda fora do ar, não necessariamente URL ruim)."""


def _resolver_padrao(host: str, porta: int) -> list[str]:
    infos = socket.getaddrinfo(host, porta, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(info[4][0] for info in infos))


def _motivo_bloqueio(texto_ip: str, permitir_rede_local: bool) -> str | None:
    """None se o destino pode receber o POST; senão o motivo (pt-BR)."""
    try:
        ip = ipaddress.ip_address(texto_ip.split("%", 1)[0])
    except ValueError:
        return f"endereço inválido ({texto_ip})"
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 é loopback, não "público"
    if any(ip in rede for rede in _SEMPRE_BLOQUEADAS) or ip.is_link_local:
        return f"{ip} é endereço link-local/metadados de nuvem"
    if ip.is_multicast:
        return f"{ip} é multicast"
    if ip.is_unspecified:
        return f"{ip} é o endereço não especificado"
    if ip.is_global:
        return None
    local = ip.is_loopback or ip.is_private or ip in _CGNAT
    if local and permitir_rede_local:
        return None
    if local:
        return f"{ip} é endereço local/privado (use permitir_rede_local=True só se o destino for da rede da planta)"
    return f"{ip} é endereço reservado"


def _resolver_e_validar(host: str, porta: int, permitir_rede_local: bool, resolver: Resolvedor) -> list[str]:
    """IPs do host, todos validados. Qualquer um proibido rejeita o host inteiro."""
    try:
        ips = resolver(host, porta)
    except OSError as exc:
        raise HostNaoResolvido(f"Não foi possível resolver o host '{host}': {exc}") from exc
    if not ips:
        raise UrlWebhookInvalida(f"O host '{host}' não resolveu para nenhum endereço.")
    for ip in ips:
        motivo = _motivo_bloqueio(ip, permitir_rede_local)
        if motivo:
            raise UrlWebhookInvalida(f"Destino bloqueado ({host}): {motivo}.")
    return ips


def validar_url(
    url: str,
    permitir_rede_local: bool = False,
    resolver: Resolvedor | None = None,
    tolerar_falha_dns: bool = False,
) -> tuple[str, str, int, str]:
    """Valida a URL e devolve `(esquema, host, porta, caminho_com_query)`. Lança `UrlWebhookInvalida`."""
    try:
        partes = urlsplit((url or "").strip())
        porta = partes.port
    except ValueError as exc:
        raise UrlWebhookInvalida(f"URL de webhook inválida: {exc}") from exc
    if partes.scheme not in ("http", "https"):
        raise UrlWebhookInvalida(f"Esquema '{partes.scheme or '(nenhum)'}' não permitido: use http ou https.")
    if not partes.hostname:
        raise UrlWebhookInvalida("URL de webhook sem host.")
    if partes.username or partes.password:
        raise UrlWebhookInvalida("Não coloque usuário/senha na URL do webhook.")
    host = partes.hostname
    porta = porta or (443 if partes.scheme == "https" else 80)
    try:
        _resolver_e_validar(host, porta, permitir_rede_local, resolver or _resolver_padrao)
    except HostNaoResolvido:
        if not tolerar_falha_dns:
            raise
    caminho = (partes.path or "/") + (f"?{partes.query}" if partes.query else "")
    return partes.scheme, host, porta, caminho


class Webhook:
    def __init__(
        self,
        url: str,
        timeout_s: float = 3.0,
        permitir_rede_local: bool = False,
        tamanho_fila: int = 100,
        resolver: Resolvedor | None = None,
    ) -> None:
        self._resolver = resolver or _resolver_padrao
        self.permitir_rede_local = permitir_rede_local
        self._esquema, self._host, self._porta, self._caminho = validar_url(
            url, permitir_rede_local, self._resolver, tolerar_falha_dns=True
        )
        self.timeout_s = timeout_s
        self._fila: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=max(1, int(tamanho_fila)))
        self._tranca = threading.Lock()
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self._enviados = 0
        self._falhas = 0
        self._descartados = 0
        self._ultimo_erro: str | None = None

    @property
    def endpoint(self) -> str:
        """Só `esquema://host:porta`: o caminho (e a query) pode carregar o segredo, no estilo dos webhooks do Slack."""
        return f"{self._esquema}://{self._host}:{self._porta}"

    def estatisticas(self) -> dict[str, Any]:
        return {
            "enviados": self._enviados,
            "falhas": self._falhas,
            "descartados": self._descartados,
            "pendentes": self._fila.qsize(),
            "ultimo_erro": self._ultimo_erro,
        }

    # -- ciclo de vida -------------------------------------------------------

    def iniciar(self) -> None:
        with self._tranca:
            if self._thread is not None and self._thread.is_alive():
                return
            self._parar.clear()
            self._thread = threading.Thread(target=self._laco, name="webhook-envio", daemon=True)
            self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=self.timeout_s + 2)
        self._thread = None

    # -- envio ---------------------------------------------------------------

    def enviar(self, carga: dict[str, Any]) -> bool:
        """Enfileira o POST; nunca bloqueia. Fila cheia descarta o mais antigo (e conta)."""
        if self._parar.is_set():
            return False
        self.iniciar()
        with self._tranca:
            if self._fila.full():
                try:
                    self._fila.get_nowait()
                    self._descartados += 1
                except queue.Empty:
                    pass
            try:
                self._fila.put_nowait(carga)
            except queue.Full:
                self._descartados += 1
                return False
        return True

    def _laco(self) -> None:
        while not self._parar.is_set():
            try:
                carga = self._fila.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._postar(carga)
                self._enviados += 1
            except Exception as exc:  # noqa: BLE001 - uma falha não pode matar o thread de envio
                self._falhas += 1
                self._ultimo_erro = f"{type(exc).__name__}: {exc}"
                logger.warning("webhook_falhou", extra={"destino": self.endpoint, "erro": self._ultimo_erro})

    def _postar(self, carga: dict[str, Any]) -> None:
        corpo = json.dumps(carga, ensure_ascii=False, default=str).encode("utf-8")
        classe = http.client.HTTPSConnection if self._esquema == "https" else http.client.HTTPConnection
        conexao = classe(self._host, self._porta, timeout=self.timeout_s)
        conexao._create_connection = self._conectar_validado  # type: ignore[attr-defined]
        try:
            conexao.request(
                "POST",
                self._caminho,
                body=corpo,
                headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "VisionEPI-Webhook/1"},
            )
            resposta = conexao.getresponse()
            resposta.read(1024)
            if not 200 <= resposta.status < 300:
                complemento = " (redirecionamento não é seguido)" if 300 <= resposta.status < 400 else ""
                raise RuntimeError(f"resposta HTTP {resposta.status}{complemento}")
        finally:
            conexao.close()

    def _conectar_validado(self, endereco: tuple[str, int], timeout: float, source_address: Any = None) -> socket.socket:
        """Valida e conecta no MESMO endereço resolvido (fecha a janela de DNS rebinding)."""
        host, porta = endereco
        ultimo: OSError | None = None
        for ip in _resolver_e_validar(host, porta, self.permitir_rede_local, self._resolver):
            try:
                return socket.create_connection((ip, porta), timeout, source_address)
            except OSError as exc:
                ultimo = exc
        raise ultimo or OSError(f"sem endereço para {host}")
