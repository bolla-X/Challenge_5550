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
    def __init__(self, video: Path, porta: int, *, fps: float = 10.0) -> None:
        self.video = Path(video)
        self.porta = porta
        self.fps = fps
        self._quadros = self._carregar()
        self._servidor: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._vivo = threading.Event()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.porta}/video.mjpg"

    def _carregar(self) -> list[bytes]:
        cap = cv2.VideoCapture(str(self.video))
        quadros = []
        while len(quadros) < 150:
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.resize(frame, (640, 360))
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
                try:
                    while fonte._vivo.is_set():
                        corpo = fonte._quadros[i % len(fonte._quadros)]
                        self.wfile.write(b"--quadro\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(corpo)).encode() + b"\r\n\r\n" + corpo + b"\r\n")
                        i += 1
                        time.sleep(1.0 / fonte.fps)
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
