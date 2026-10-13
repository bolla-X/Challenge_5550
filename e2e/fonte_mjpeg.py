"""Fonte de vídeo de rede que o teste pode DERRUBAR e religar.

Uma câmera IP de verdade não está disponível no E2E. Este servidor HTTP serve
uma fixture como MJPEG (`multipart/x-mixed-replace`, o mesmo formato de muita
câmera IP barata) e pode ser parado e iniciado de novo na mesma porta — é o
que exercita o caminho RECONECTANDO → AO VIVO do worker de ponta a ponta.
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2


class FonteMJPEG:
    def __init__(self, video: Path, porta: int, *, fps: float | None = 10.0, tamanho: tuple[int, int] | None = (640, 360),
                 max_quadros: int | None = 150) -> None:
        """`fps=None` = o do arquivo; `tamanho=None` = reduz só se passar de 960 no lado maior;
        `max_quadros=None` = o arquivo inteiro (o bench usa assim: câmera IP em tempo real)."""
        self.video = Path(video)
        self.porta = porta
        self.tamanho = tamanho
        self.max_quadros = max_quadros
        self._quadros = self._carregar()
        self.fps = fps or self._fps_do_arquivo or 25.0
        self._servidor: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._vivo = threading.Event()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.porta}/video.mjpg"

    def _carregar(self) -> list[bytes]:
        cap = cv2.VideoCapture(str(self.video))
        self._fps_do_arquivo = cap.get(cv2.CAP_PROP_FPS) or None
        quadros = []
        while self.max_quadros is None or len(quadros) < self.max_quadros:
            ok, frame = cap.read()
            if not ok:
                break
            if self.tamanho is not None:
                frame = cv2.resize(frame, self.tamanho)
            elif max(frame.shape[:2]) > 960:
                escala = 960 / max(frame.shape[:2])
                frame = cv2.resize(frame, (round(frame.shape[1] * escala), round(frame.shape[0] * escala)),
                                   interpolation=cv2.INTER_AREA)
            quadros.append(cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])[1].tobytes())
        cap.release()
        if not quadros:
            raise RuntimeError(f"não consegui ler {self.video}")
        return quadros

    def iniciar(self) -> None:
        fonte = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silencioso
                pass

            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=quadro")
                self.end_headers()
                i = 0
                proximo = time.monotonic()
                try:
                    while fonte._vivo.is_set():
                        corpo = fonte._quadros[i % len(fonte._quadros)]
                        self.wfile.write(b"--quadro\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(corpo)).encode() + b"\r\n\r\n" + corpo + b"\r\n")
                        i += 1
                        # Agenda pelo relógio: `sleep(1/fps)` fixo somava o tempo de
                        # escrita e a "câmera" andava abaixo do FPS declarado.
                        proximo += 1.0 / fonte.fps
                        if time.monotonic() - proximo > 1.0:
                            # Cliente lento segurou a escrita: câmera de verdade não
                            # "recupera" em rajada, ela simplesmente segue.
                            proximo = time.monotonic()
                        time.sleep(max(0.0, proximo - time.monotonic()))
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

        self._vivo.set()
        self._servidor = ThreadingHTTPServer(("127.0.0.1", self.porta), Handler)
        self._servidor.daemon_threads = True
        self._thread = threading.Thread(target=self._servidor.serve_forever, daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._vivo.clear()
        if self._servidor is not None:
            self._servidor.shutdown()
            self._servidor.server_close()
            self._servidor = None
