"""Celular como câmera (F6): o navegador do celular manda JPEGs, o worker lê daqui.

A página `/cam?t=<token>` usa `getUserMedia` — que só existe em contexto
seguro: "in insecure contexts, `navigator.mediaDevices` is `undefined`"
(https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia),
e um IP de LAN em `http://` não é contexto seguro
(https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts). Por
isso o servidor sobe em HTTPS (`run.py --https`) quando há celular.

A câmera cadastrada tem `source = "celular://<token>"`. O token (aleatório,
por câmera) é a ÚNICA credencial do celular: autoriza enviar quadro para
aquela câmera e nada mais — não dá sessão, não lê nada.

Interface igual à parte do `VideoStream` que o worker usa (`read`, `status`,
`release`, `source`, `width`, `height`); sem `pular`/`converter`, a captura
contínua só usa `read`.
"""

from __future__ import annotations

import secrets
import threading
import time
from typing import Any

import cv2
import numpy as np

from app.vision.video_stream import IDLE, LIVE, RECONNECTING, StreamStatus

PREFIXO = "celular://"
MAX_BYTES_QUADRO = 4 * 1024 * 1024
SEM_QUADRO_S = 3.0

_registro: dict[str, FonteDeCelular] = {}
_registro_lock = threading.Lock()


def novo_token() -> str:
    return secrets.token_urlsafe(18)


def e_celular(source: Any) -> bool:
    return isinstance(source, str) and source.startswith(PREFIXO)


def fonte_do_token(token: str) -> FonteDeCelular | None:
    with _registro_lock:
        return _registro.get(token)


class FonteDeCelular:
    fps_da_fonte = None

    def __init__(self, source: str, width: int = 960, height: int = 540) -> None:
        self.source = source
        self.token = source[len(PREFIXO):]
        self.width, self.height = width, height
        self._cond = threading.Condition()
        self._quadro: np.ndarray | None = None
        self._seq = 0
        self._lido = 0
        self._ultimo_em: float | None = None
        self.recebidos = 0
        self.rejeitados = 0
        with _registro_lock:
            _registro[self.token] = self

    # ------------------------------------------------------------- lado HTTP
    def receber(self, jpeg: bytes) -> bool:
        """Um quadro do celular. False se não for uma imagem válida e limitada."""
        if not jpeg or len(jpeg) > MAX_BYTES_QUADRO:
            self.rejeitados += 1
            return False
        quadro = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if quadro is None:
            self.rejeitados += 1
            return False
        with self._cond:
            self._quadro = quadro
            self._seq += 1
            self._ultimo_em = time.monotonic()
            self.recebidos += 1
            self._cond.notify_all()
        return True

    # ----------------------------------------------------------- lado worker
    def read(self) -> tuple[bool, Any]:
        """Espera (até 1 s) um quadro MAIS NOVO que o último entregue."""
        with self._cond:
            if self._seq <= self._lido:
                self._cond.wait(1.0)
            if self._seq <= self._lido or self._quadro is None:
                return False, None
            self._lido = self._seq
            return True, self._quadro

    def status(self) -> StreamStatus:
        with self._cond:
            ultimo = self._ultimo_em
        if ultimo is None:
            estado = IDLE
        elif time.monotonic() - ultimo <= SEM_QUADRO_S:
            estado = LIVE
        else:
            estado = RECONNECTING
        return StreamStatus(state=estado, consecutive_failures=0, reconnect_attempts=0, total_reconnects=0,
                            last_error=None if estado != RECONNECTING else "celular sem enviar quadro", seconds_until_retry=0.0)

    def release(self) -> None:
        with _registro_lock:
            if _registro.get(self.token) is self:
                del _registro[self.token]
