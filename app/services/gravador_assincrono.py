"""Escrita de evidência FORA do caminho do frame: fila limitada + um thread.

Gravar o snapshot de um alerta (`cv2.imwrite` do quadro anotado + UPDATE do
`frame_ref`) acontecia dentro do loop da câmera, justamente no quadro em que o
alerta nasce: o vídeo daquela câmera engasgava ali. Agora o worker só entrega
(id do alerta, quadro) e segue.

Fila LIMITADA de propósito: se o disco travar, a fila enche e o item novo é
descartado e contado (`descartados`), em vez de a memória crescer sem teto ou o
loop da câmera passar a esperar o disco. Perder um snapshot é ruim; travar a
detecção de todas as câmeras é pior.

Só vai para cá o que não precisa voltar ao loop: a criação/toque/resolução do
alerta continuam síncronas porque o objeto ORM pertence à sessão do thread do
worker (ver AlertRuntimeState.snapshot).
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)


class GravadorAssincrono:
    def __init__(self, app: Any, *, tamanho: int = 64) -> None:
        self.app = app
        self._fila: queue.Queue = queue.Queue(maxsize=tamanho)
        self.descartados = 0
        self.gravados = 0
        self.ultimo_erro: str | None = None
        self._thread = threading.Thread(target=self._laco, name="gravador-assincrono", daemon=True)
        self._thread.start()

    def enfileirar(self, tarefa: Callable[..., None], *args: Any) -> bool:
        try:
            self._fila.put_nowait((tarefa, args))
            return True
        except queue.Full:
            self.descartados += 1
            logger.warning("gravador_fila_cheia", extra={"descartados": self.descartados})
            return False

    def pendentes(self) -> int:
        return self._fila.qsize()

    def esperar_vazio(self, timeout: float = 5.0) -> bool:
        """Para testes e para o stop: espera a fila esvaziar."""
        import time

        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            if self._fila.unfinished_tasks == 0:
                return True
            time.sleep(0.01)
        return False

    def _laco(self) -> None:
        from app.extensions import db

        while True:
            tarefa, args = self._fila.get()
            try:
                with self.app.app_context():
                    try:
                        tarefa(*args)
                        self.gravados += 1
                    finally:
                        db.session.remove()
            except Exception as exc:  # noqa: BLE001  (uma gravação ruim não para as outras)
                self.ultimo_erro = str(exc)
                logger.warning("gravador_tarefa_falhou", extra={"error": str(exc)})
            finally:
                self._fila.task_done()
