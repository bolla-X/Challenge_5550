from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass
from time import monotonic, sleep
from typing import Any

import cv2

logger = logging.getLogger(__name__)


def capture_api(source: Any) -> int:
    """Backend do OpenCV a usar para abrir `source`.

    No Windows o padrão é o MSMF, e ele é ruim para webcam USB: medido nesta
    máquina, abrir o índice 1 (webcam externa) levou **20 segundos** contra
    0,86s do DirectShow — a captura em si roda a ~30 FPS nos dois. Esse custo
    de abertura é o que fazia a descoberta de câmeras varrer 0..5 e parecer
    travada, e o que atrasava a subida da segunda câmera no multicam.

    Só vale para índice numérico (USB/webcam): RTSP e arquivo têm o próprio
    caminho no FFMPEG, onde o padrão (CAP_ANY) já é o certo.
    """
    if sys.platform == "win32" and isinstance(source, int):
        return cv2.CAP_DSHOW
    return cv2.CAP_ANY


class VideoStreamError(RuntimeError):
    pass


# Estados possíveis da captura, na ordem em que aparecem na vida real.
IDLE = "idle"                  # nunca abriu (monitoramento parado)
LIVE = "live"                  # entregando frames
RECONNECTING = "reconnecting"  # caiu, tentando voltar dentro do backoff
UNAVAILABLE = "unavailable"    # tentou várias vezes e já está no teto do backoff


@dataclass(frozen=True)
class StreamStatus:
    state: str
    consecutive_failures: int
    reconnect_attempts: int
    total_reconnects: int
    last_error: str | None
    seconds_until_retry: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "consecutive_failures": self.consecutive_failures,
            "reconnect_attempts": self.reconnect_attempts,
            "total_reconnects": self.total_reconnects,
            "last_error": self.last_error,
            "seconds_until_retry": round(self.seconds_until_retry, 2),
        }


class VideoStream:
    """Captura de uma fonte de vídeo, com reconexão automática.

    O comportamento anterior tinha dois furos operacionais:

    1. Uma fonte RTSP que cai costuma deixar o `VideoCapture` "aberto" e apenas
       devolver `False` em todo `read()`. Como `read()` só reabria quando
       `isOpened()` era falso, a câmera ficava em "Frame indisponível" para
       sempre — sem nunca tentar voltar.
    2. Quando a fonte sumia de vez, `open()` levantava exceção a cada iteração
       do loop (~12x/s), enchendo o log de traceback e martelando o dispositivo.

    Agora falhas consecutivas de leitura forçam uma reconexão de verdade
    (release + open), e as tentativas seguem backoff exponencial com teto, para
    que uma fonte morta custe uma tentativa a cada `max_backoff_seconds` em vez
    de doze por segundo.

    `read()` nunca levanta exceção: devolve `(False, None)` e o estado fica
    legível em `status()`, que o worker publica no dashboard.
    """

    def __init__(
        self,
        source: str | int,
        width: int,
        height: int,
        *,
        failures_before_reconnect: int = 15,
        initial_backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 30.0,
    ) -> None:
        self.source = source
        self.width = width
        self.height = height
        # A ~12 FPS, 15 frames ruins ≈ 1,2 s — tolera engasgo de rede sem
        # derrubar a conexão, mas não deixa a câmera morta indefinidamente.
        self.failures_before_reconnect = max(1, int(failures_before_reconnect))
        self.initial_backoff_seconds = max(0.05, float(initial_backoff_seconds))
        self.max_backoff_seconds = max(self.initial_backoff_seconds, float(max_backoff_seconds))

        self._capture: cv2.VideoCapture | None = None
        self._lock = threading.RLock()
        self._latest_frame = None

        self._state = IDLE
        self._consecutive_failures = 0
        self._reconnect_attempts = 0
        self._total_reconnects = 0
        self._last_error: str | None = None
        self._backoff = self.initial_backoff_seconds
        self._next_attempt_at = 0.0

    # ------------------------------------------------------------- estado --
    def status(self) -> StreamStatus:
        with self._lock:
            return StreamStatus(
                state=self._state,
                consecutive_failures=self._consecutive_failures,
                reconnect_attempts=self._reconnect_attempts,
                total_reconnects=self._total_reconnects,
                last_error=self._last_error,
                seconds_until_retry=max(0.0, self._next_attempt_at - monotonic()),
            )

    @property
    def is_live(self) -> bool:
        with self._lock:
            return self._state == LIVE

    # ------------------------------------------------------------- abertura -
    def open(self) -> None:
        """Abre a fonte. Levanta VideoStreamError se não conseguir.

        Continua existindo para chamadas explícitas (warmup/preflight), onde
        falhar alto é o comportamento desejado. O loop de captura usa `read()`,
        que nunca levanta.
        """
        with self._lock:
            if not self._open_locked():
                raise VideoStreamError(f"Não foi possível abrir a fonte de vídeo: {self.source}")

    def _open_locked(self) -> bool:
        if self._capture and self._capture.isOpened():
            return True
        self._release_locked(quiet=True)
        try:
            capture = cv2.VideoCapture(self.source, capture_api(self.source))
        except Exception as exc:  # noqa: BLE001  (cv2 levanta tipos variados)
            self._last_error = str(exc)
            return False
        if not capture.isOpened():
            capture.release()
            self._last_error = f"Não foi possível abrir a fonte de vídeo: {self.source}"
            return False

        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        # Buffer de 1 frame: a câmera entrega ~30 FPS, mas o pipeline consome
        # bem menos (a inferência é o gargalo). Com o buffer padrão, os frames
        # não consumidos ENFILEIRAM e `read()` devolve imagem velha — o vídeo
        # aparece atrasado em segundos e piora quanto mais tempo roda. Com 1,
        # `read()` sempre pega o frame mais recente e o atraso não acumula.
        # Nem todo backend respeita; quando ignora, o comportamento é o de
        # antes, então não há risco em pedir.
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._capture = capture
        self._last_error = None
        logger.info("video_stream_opened", extra={"source": str(self.source)})
        return True

    # -------------------------------------------------------------- leitura -
    def read(self) -> tuple[bool, Any]:
        with self._lock:
            if self._capture is None:
                # Fora da janela de backoff? Se ainda não deu a hora, devolve
                # falha barata em vez de martelar o dispositivo.
                if monotonic() < self._next_attempt_at:
                    return False, None
                self._reconnect_attempts += 1
                if not self._open_locked():
                    self._schedule_retry()
                    return False, None
                self._on_reconnected()

            ok, frame = self._capture.read()
            if ok and frame is not None:
                self._on_success(frame)
                return True, frame

            self._on_failure()
            return False, None

    def _on_success(self, frame) -> None:
        if self._state != LIVE:
            logger.info("video_stream_live", extra={"source": str(self.source)})
        self._latest_frame = frame.copy()
        self._state = LIVE
        self._consecutive_failures = 0
        self._reconnect_attempts = 0
        self._backoff = self.initial_backoff_seconds
        self._next_attempt_at = 0.0
        self._last_error = None

    def _on_failure(self) -> None:
        self._consecutive_failures += 1
        self._last_error = "Frame indisponível"
        if self._consecutive_failures < self.failures_before_reconnect:
            return
        # Passou do limite: a fonte pode estar "aberta" e morta ao mesmo tempo
        # (caso clássico do RTSP). Derruba e agenda reconexão.
        logger.warning(
            "video_stream_reconnecting",
            extra={"source": str(self.source), "consecutive_failures": self._consecutive_failures},
        )
        self._release_locked(quiet=True)
        self._schedule_retry()

    def _on_reconnected(self) -> None:
        if self._state in (RECONNECTING, UNAVAILABLE):
            self._total_reconnects += 1
            logger.info(
                "video_stream_reconnected",
                extra={"source": str(self.source), "total_reconnects": self._total_reconnects},
            )
        self._consecutive_failures = 0

    def _schedule_retry(self) -> None:
        self._next_attempt_at = monotonic() + self._backoff
        no_teto = self._backoff >= self.max_backoff_seconds
        self._state = UNAVAILABLE if no_teto else RECONNECTING
        self._backoff = min(self._backoff * 2, self.max_backoff_seconds)

    # ------------------------------------------------------------ auxiliares -
    def latest_frame(self) -> Any:
        with self._lock:
            return None if self._latest_frame is None else self._latest_frame.copy()

    def release(self) -> None:
        with self._lock:
            self._release_locked()
            self._state = IDLE
            self._consecutive_failures = 0
            self._reconnect_attempts = 0
            self._backoff = self.initial_backoff_seconds
            self._next_attempt_at = 0.0

    def _release_locked(self, *, quiet: bool = False) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
            if not quiet:
                logger.info("video_stream_released", extra={"source": str(self.source)})

    def warmup(self, attempts: int = 5) -> bool:
        self.open()
        for _ in range(attempts):
            ok, _ = self.read()
            if ok:
                return True
            sleep(0.1)
        return False
