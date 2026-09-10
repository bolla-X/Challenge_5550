from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass
from time import monotonic, sleep
from typing import Any

import cv2

from app.llm import redigir_segredos

logger = logging.getLogger(__name__)


def capture_api(source: Any) -> int:
    """Backend do OpenCV a usar para abrir `source`.

    No Windows o padrão é o MSMF, e ele é ruim para webcam USB: medido nesta
    máquina, abrir o índice 1 (webcam externa) levou **20 segundos** contra
    0,86s do DirectShow — a captura em si roda a ~30 FPS nos dois. Esse custo
    de abertura é o que fazia a descoberta de câmeras varrer 0..5 e parecer
    travada, e o que atrasava a subida da segunda câmera no multicam.

    Para fonte de REDE (rtsp/http), o backend é o FFMPEG explícito, e não
    `CAP_ANY`. Medido contra um servidor RTSP local morto: com `CAP_ANY` a
    abertura custa **34.319 ms** contra **30.054 ms** com `CAP_FFMPEG` — os
    4,3 s de diferença são o OpenCV tentando os outros backends depois de o
    FFMPEG falhar. E o pior não é o tempo: o backend `CAP_IMAGES` chega a ser
    tentado e loga

        VIDEOIO(CV_IMAGES): raised OpenCV exception: ... CAP_IMAGES: error,
        expected '0?[1-9][du]' pattern, got: rtsp://...

    que não tem relação nenhuma com a causa real e manda quem está
    diagnosticando atrás de um problema de padrão de nome de arquivo.

    Arquivo local segue em `CAP_ANY`: é o caminho do modo fixture e não há
    nada a ganhar ali.
    """
    if sys.platform == "win32" and isinstance(source, int):
        return cv2.CAP_DSHOW
    if isinstance(source, str) and source.startswith(("rtsp://", "rtsps://", "http://", "https://")):
        return cv2.CAP_FFMPEG
    return cv2.CAP_ANY


def abrir_captura(source: Any, *, open_timeout_ms: int = 5000):
    """Constrói o `VideoCapture` como a produção constrói.

    O teto NÃO pode ir por `capture.set()`: a documentação do OpenCV marca a
    propriedade como **open-only** — OpenCV 4.11.0,
    `modules/videoio/include/opencv2/videoio.hpp`:

        CAP_PROP_OPEN_TIMEOUT_MSEC=53, //!< (**open-only**) timeout in
        milliseconds for opening a video capture (applicable for FFmpeg and
        GStreamer back-ends only)

    Medido: `set()` antes do `open()` deu 30.045 ms, igual a não fazer nada.
    Vai então pela sobrecarga de construtor que aceita parâmetros de abertura —
    `VideoCapture(const String& filename, int apiPreference, const
    std::vector<int>& params)`, com params em pares
    `(paramId_1, paramValue_1, ...)` — que deu 3.037 ms.

    Arquivo local e webcam não recebem teto: não há rede para esperar, e a
    fonte do modo fixture é justamente um arquivo local.

    É função de módulo, e não método, porque a sondagem de campo
    (`scripts/sondar_cameras.py`) e o bench (`scripts/bench_pipeline.py`)
    precisam abrir a fonte EXATAMENTE como o worker abre. Cada um com a sua
    cópia mediria outra coisa — e o backend/teto errado foi justamente o que
    custou 34 s por tentativa antes (docs/BENCH.md, Fase 2).
    """
    api = capture_api(source)
    if api != cv2.CAP_FFMPEG or not isinstance(source, str):
        return cv2.VideoCapture(source, api)
    teto = max(500, int(open_timeout_ms))
    return cv2.VideoCapture(
        source,
        api,
        [
            int(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC), teto,
            int(cv2.CAP_PROP_READ_TIMEOUT_MSEC), teto,
        ],
    )


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
        em_loop: bool = False,
        open_timeout_ms: int = 5000,
    ) -> None:
        self.source = source
        self.width = width
        self.height = height
        # Arquivo que deve reiniciar ao terminar (a fonte de demonstração do
        # modo fixture). Sem isto o fim do vídeo entra no caminho de FALHA:
        # seriam 15 leituras ruins mais o backoff inicial de 0,5 s a cada
        # volta — meio segundo de imagem congelada a cada 7 s de fixture, na
        # frente de quem está assistindo.
        self.em_loop = bool(em_loop)
        self._rebobinando = False
        # Teto para a ABERTURA de fonte de rede. O default do OpenCV é o
        # próprio callback de interrupção dele, em 30 s ("Stream timeout
        # triggered after 30043.883000 ms" no log) — e com 5 tentativas antes
        # do modo fixture isso são ~150 s de câmera parada antes de o demo ter
        # imagem. Medido: 3.037 ms com o teto contra 34.319 ms sem.
        self.open_timeout_ms = max(500, int(open_timeout_ms))
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
                raise VideoStreamError(f"Não foi possível abrir a fonte de vídeo: {redigir_segredos(str(self.source))}")

    def _abrir_capture(self):
        return abrir_captura(self.source, open_timeout_ms=self.open_timeout_ms)

    def _open_locked(self) -> bool:
        if self._capture and self._capture.isOpened():
            return True
        self._release_locked(quiet=True)
        try:
            capture = self._abrir_capture()
        except Exception as exc:  # noqa: BLE001  (cv2 levanta tipos variados)
            self._last_error = redigir_segredos(str(exc))
            return False
        if not capture.isOpened():
            capture.release()
            self._last_error = f"Não foi possível abrir a fonte de vídeo: {redigir_segredos(str(self.source))}"
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
        logger.info("video_stream_opened", extra={"source": redigir_segredos(str(self.source))})
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
            logger.info("video_stream_live", extra={"source": redigir_segredos(str(self.source))})
        self._latest_frame = frame.copy()
        self._state = LIVE
        self._rebobinando = False
        self._consecutive_failures = 0
        self._reconnect_attempts = 0
        self._backoff = self.initial_backoff_seconds
        self._next_attempt_at = 0.0
        self._last_error = None

    def _on_failure(self) -> None:
        # Fim de arquivo em loop NÃO é falha de fonte: rebobina e segue. Uma
        # tentativa só, controlada por `_rebobinando`: se a leitura depois do
        # rebobinamento também falhar, o arquivo está ilegível de verdade e o
        # caminho normal de falha assume — senão um .mp4 corrompido giraria
        # para sempre sem nunca aparecer como problema.
        if self.em_loop and self._capture is not None and not self._rebobinando:
            self._rebobinando = True
            self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            return
        self._rebobinando = False

        self._consecutive_failures += 1
        self._last_error = "Frame indisponível"
        if self._consecutive_failures < self.failures_before_reconnect:
            return
        # Passou do limite: a fonte pode estar "aberta" e morta ao mesmo tempo
        # (caso clássico do RTSP). Derruba e agenda reconexão.
        logger.warning(
            "video_stream_reconnecting",
            extra={"source": redigir_segredos(str(self.source)), "consecutive_failures": self._consecutive_failures},
        )
        self._release_locked(quiet=True)
        self._schedule_retry()

    def _on_reconnected(self) -> None:
        if self._state in (RECONNECTING, UNAVAILABLE):
            self._total_reconnects += 1
            logger.info(
                "video_stream_reconnected",
                extra={"source": redigir_segredos(str(self.source)), "total_reconnects": self._total_reconnects},
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
                logger.info("video_stream_released", extra={"source": redigir_segredos(str(self.source))})

    def warmup(self, attempts: int = 5) -> bool:
        self.open()
        for _ in range(attempts):
            ok, _ = self.read()
            if ok:
                return True
            sleep(0.1)
        return False
