"""Captura em thread própria por câmera: o ÚLTIMO frame vence.

No loop antigo, ler a fonte, inferir e publicar aconteciam em série na mesma
thread. Duas consequências medidas no `scripts/bench.py` (baseline em
docs/NEXT2026/BENCHMARKS.md):

- **arquivo de fixture tocava em câmera lenta**: o loop só pedia o próximo
  frame depois de terminar o anterior, então um vídeo de 30 fps era consumido
  no ritmo da inferência — a "câmera" ficava cada vez mais atrás do relógio;
- **webcam/RTSP**: enquanto a thread estava presa na inferência, ninguém lia a
  fonte; o frame que saía depois já era velho.

Aqui uma thread só lê a fonte, no ritmo DELA (para arquivo, no FPS declarado,
simulando uma câmera ao vivo), e guarda apenas o frame mais recente. Quem
consome pega o mais novo; o que não foi consumido é sobrescrito e contado em
`frames_descartados` — nunca enfileirado. É o mesmo desenho do Frigate
(`frigate/video/ffmpeg.py: capture_frames`, ver docs/NEXT2026/PESQUISA.md).

A fonte é obtida por uma função a cada leitura (`obter_fonte`), e não guardada:
o worker troca `video_stream` em runtime (modo fixture) e a thread precisa
seguir a troca sem ser recriada.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CapturaContinua:
    def __init__(
        self,
        obter_fonte: Callable[[], Any],
        *,
        stats: Any | None = None,
        tempo_real_em_arquivo: bool = True,
        nome: str = "captura",
        taxa_util: Callable[[], float] | None = None,
    ) -> None:
        self._obter_fonte = obter_fonte
        # Quantos quadros por segundo alguém vai de fato consumir (vídeo
        # assistido, miniatura, inferência). Acima disso a fonte só AVANÇA
        # (`pular`: grab sem retrieve) — continua no tempo real, sem pagar a
        # conversão de quadro que ninguém vai ver. None/0 = converte todos.
        self._taxa_util = taxa_util
        self._ultimo_util = 0.0
        self._stats = stats
        self.tempo_real_em_arquivo = tempo_real_em_arquivo
        self._nome = nome
        self._cond = threading.Condition()
        self._frame = None
        self._ts_ms: float | None = None
        self._seq = 0
        self._consumido = True
        self._rodando = threading.Event()
        self._thread: threading.Thread | None = None
        # True enquanto a última leitura falhou: o worker usa isto para decidir
        # entre "ainda não chegou frame" e "a fonte está caída".
        self.falhando = False

    # ----------------------------------------------------------- ciclo de vida
    def iniciar(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._rodando.set()
        self._thread = threading.Thread(target=self._laco, name=self._nome, daemon=True)
        self._thread.start()

    def parar(self, timeout: float = 2.0) -> None:
        self._rodando.clear()
        with self._cond:
            self._cond.notify_all()
        if self._thread is not None:
            self._thread.join(timeout)
        self._thread = None

    @property
    def ativa(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------- consumo
    def esperar_novo(self, ultimo_seq: int, timeout: float = 0.5) -> tuple[Any, float, int] | None:
        """O frame mais novo com `seq > ultimo_seq`, ou None se não chegar a tempo."""
        with self._cond:
            if self._seq <= ultimo_seq:
                self._cond.wait(timeout)
            if self._seq <= ultimo_seq or self._frame is None:
                return None
            self._consumido = True
            return self._frame, float(self._ts_ms or 0.0), self._seq

    # --------------------------------------------------------------- thread
    def _laco(self) -> None:
        proximo = 0.0
        fonte_anterior = None
        while self._rodando.is_set():
            fonte = self._obter_fonte()
            if fonte is not fonte_anterior:
                proximo = 0.0
                fonte_anterior = fonte
            if self._pular_se_ninguem_precisa(fonte):
                proximo = self._cadenciar(fonte, proximo)
                continue
            try:
                ok, frame = fonte.read()
            except Exception as exc:  # noqa: BLE001  (fonte nunca derruba a thread)
                logger.warning("captura_read_falhou", extra={"error": str(exc)})
                ok, frame = False, None
            if not ok or frame is None:
                self.falhando = True
                with self._cond:
                    self._cond.notify_all()
                # O VideoStream já aplica o backoff (devolve falha barata dentro
                # da janela); aqui só evita girar a CPU entre uma e outra.
                time.sleep(0.05)
                continue
            self.falhando = False
            agora_ms = time.time() * 1000.0
            self._ultimo_util = time.monotonic()
            with self._cond:
                if self._frame is not None and not self._consumido and self._stats is not None:
                    self._stats.contar("frames_descartados")
                self._frame = frame
                self._ts_ms = agora_ms
                self._seq += 1
                self._consumido = False
                self._cond.notify_all()
            if self._stats is not None:
                self._stats.contar("frames_lidos")
                self._stats.quadro_lido(agora_ms)
            proximo = self._cadenciar(fonte, proximo)

    def _pular_se_ninguem_precisa(self, fonte: Any) -> bool:
        """True se avançou a fonte sem converter o quadro (ver `taxa_util`)."""
        taxa = float(self._taxa_util() or 0.0) if self._taxa_util is not None else 0.0
        if taxa <= 0 or not hasattr(fonte, "pular") or time.monotonic() - self._ultimo_util >= 1.0 / taxa:
            return False
        try:
            if not fonte.pular():
                return False
        except Exception:  # noqa: BLE001  (na dúvida, o read() normal decide)
            return False
        self.falhando = False
        if self._stats is not None:
            # Lido da fonte, só não convertido: conta como lido (a fração do
            # tempo real continua honesta) e mantém o índice dos quadros.
            self._stats.contar("frames_lidos")
            self._stats.contar("frames_pulados")
            self._stats.quadro_lido(time.time() * 1000.0)
        return True

    def _cadenciar(self, fonte: Any, proximo: float) -> float:
        """Arquivo entrega tão rápido quanto se pede: sem ritmo, um vídeo de
        30 fps seria "capturado" a 300 fps. Agenda pelo relógio (e não por
        sleep fixo) para não acumular deriva; se atrasou mais de um quadro,
        recomeça a agenda em vez de tentar recuperar em rajada."""
        fps = getattr(fonte, "fps_da_fonte", None) if self._e_arquivo(fonte) else None
        if not (self.tempo_real_em_arquivo and fps):
            return proximo
        intervalo = 1.0 / float(fps)
        agora = time.monotonic()
        proximo = agora + intervalo if proximo == 0.0 or agora - proximo > intervalo else proximo + intervalo
        espera = proximo - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        return proximo

    @staticmethod
    def _e_arquivo(fonte: Any) -> bool:
        origem = getattr(fonte, "source", None)
        return isinstance(origem, str) and not origem.isdigit() and not origem.startswith(
            ("rtsp://", "rtsps://", "http://", "https://")
        )
