"""Um único thread de inferência para todas as câmeras, em rodízio justo.

Antes cada `CameraWorker` chamava o modelo no próprio loop, sob um
`inference_lock` compartilhado. Isso tinha três defeitos medidos (baseline em
docs/NEXT2026/BENCHMARKS.md):

1. **o vídeo andava no ritmo da inferência**: enquanto um worker esperava o
   lock, ele também não publicava frame — com 4 câmeras, cada uma via ~1/4 da
   vazão do modelo E ~1/4 do FPS de vídeo;
2. **o lock não é justo**: `threading.Lock` não garante ordem de chegada; uma
   câmera podia ganhar o lock várias vezes seguidas;
3. **N threads disputando os mesmos núcleos** para chamar o PyTorch, cada uma
   com seu pool interno de OpenMP.

Agora o worker só **entrega** o frame mais novo ao agendador (slot por câmera,
último vence — frame velho não espera na fila) e segue publicando vídeo com a
análise mais recente que tiver. O agendador percorre as câmeras em rodízio,
uma inferência por vez, e devolve o resultado ao worker por callback.

Modo `lote`: com mais de uma câmera pendente, roda UMA chamada `predict` com
todos os frames (`detect_lote`). Mantido atrás de configuração porque só vale
se o p95 por câmera melhorar — medido no bench, não presumido.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class _Slot:
    camera_id: int
    analisar: Callable[[Any, Callable[[str], None]], Any]
    entregar: Callable[[Any, float], None]
    stats: Any | None = None
    detectar_lote: Callable[[list[Any]], list[Any]] | None = None
    pos_lote: Callable[[Any, Any, Callable[[str], None]], Any] | None = None
    frame: Any = None
    ts_ms: float = 0.0
    pendente: bool = False
    servidos: int = 0
    descartados: int = 0
    ultima_ms: float = field(default=0.0)


class Cronometro:
    """Marca etapas em `stats` a partir do thread do agendador.

    O `_perf_marca` do worker usa um relógio compartilhado com o loop do worker;
    chamá-lo de outro thread misturaria os intervalos das duas threads.
    """

    def __init__(self, stats: Any | None) -> None:
        self._stats = stats
        self._t = time.perf_counter()

    def __call__(self, etapa: str) -> None:
        agora = time.perf_counter()
        if self._stats is not None:
            self._stats.duracao(etapa, (agora - self._t) * 1000.0)
        self._t = agora


class AgendadorDeInferencia:
    def __init__(self, *, lote: bool = False, lote_max: int = 4) -> None:
        self.lote = bool(lote)
        self.lote_max = max(1, int(lote_max))
        self._slots: dict[int, _Slot] = {}
        self._ordem: list[int] = []
        self._proximo = 0
        self._cond = threading.Condition()
        self._rodando = threading.Event()
        self._thread: threading.Thread | None = None
        self.inferencias = 0
        self.ultimo_erro: str | None = None

    # ----------------------------------------------------------- registro
    def registrar(self, camera_id: int, analisar, entregar, *, stats=None, detectar_lote=None, pos_lote=None) -> None:
        with self._cond:
            self._slots[camera_id] = _Slot(camera_id, analisar, entregar, stats, detectar_lote, pos_lote)
            if camera_id not in self._ordem:
                self._ordem.append(camera_id)
        self._garantir_thread()

    def remover(self, camera_id: int) -> None:
        with self._cond:
            self._slots.pop(camera_id, None)
            if camera_id in self._ordem:
                self._ordem.remove(camera_id)
                self._proximo = 0

    def submeter(self, camera_id: int, frame: Any, ts_ms: float) -> None:
        """Entrega o frame mais novo. Não bloqueia: só troca o conteúdo do slot."""
        with self._cond:
            slot = self._slots.get(camera_id)
            if slot is None:
                return
            if slot.pendente:
                slot.descartados += 1
                if slot.stats is not None:
                    slot.stats.contar("inferencias_descartadas")
            slot.frame, slot.ts_ms, slot.pendente = frame, ts_ms, True
            self._cond.notify()

    def pendentes(self) -> int:
        with self._cond:
            return sum(1 for s in self._slots.values() if s.pendente)

    def estado(self) -> dict[str, Any]:
        with self._cond:
            return {
                "modo": "lote" if self.lote else "rodizio",
                "cameras": list(self._ordem),
                "inferencias": self.inferencias,
                "ultimo_erro": self.ultimo_erro,
                "por_camera": {
                    str(s.camera_id): {"servidos": s.servidos, "descartados": s.descartados, "ultima_ms": round(s.ultima_ms, 1)}
                    for s in self._slots.values()
                },
            }

    def parar(self) -> None:
        self._rodando.clear()
        with self._cond:
            self._cond.notify_all()
        if self._thread is not None:
            self._thread.join(2.0)
        self._thread = None

    # --------------------------------------------------------------- thread
    def _garantir_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._rodando.set()
        self._thread = threading.Thread(target=self._laco, name="agendador-de-inferencia", daemon=True)
        self._thread.start()

    def _escolher(self) -> list[_Slot]:
        """Próximos slots a servir, em rodízio a partir de `_proximo`. Chamar com o lock."""
        if not self._ordem:
            return []
        n = len(self._ordem)
        escolhidos: list[_Slot] = []
        for passo in range(n):
            indice = (self._proximo + passo) % n
            slot = self._slots.get(self._ordem[indice])
            if slot is None or not slot.pendente:
                continue
            escolhidos.append(slot)
            if not self.lote or len(escolhidos) >= self.lote_max:
                self._proximo = (indice + 1) % n
                break
        else:
            if escolhidos:
                self._proximo = (self._ordem.index(escolhidos[-1].camera_id) + 1) % n
        for slot in escolhidos:
            slot.pendente = False
        return escolhidos

    def _laco(self) -> None:
        while self._rodando.is_set():
            with self._cond:
                escolhidos = self._escolher()
                if not escolhidos:
                    self._cond.wait(0.5)
                    continue
                trabalho = [(s, s.frame, s.ts_ms) for s in escolhidos]
            try:
                if len(trabalho) > 1 and all(s.detectar_lote and s.pos_lote for s, _, _ in trabalho):
                    self._servir_lote(trabalho)
                else:
                    for slot, frame, ts in trabalho:
                        self._servir_um(slot, frame, ts)
                self.ultimo_erro = None
            except Exception as exc:  # noqa: BLE001  (uma câmera com problema não para as outras)
                self.ultimo_erro = str(exc)
                logger.exception("agendador_falhou", extra={"error": str(exc)})
                time.sleep(0.2)

    def _servir_um(self, slot: _Slot, frame: Any, ts_ms: float) -> None:
        inicio = time.perf_counter()
        resultado = slot.analisar(frame, Cronometro(slot.stats))
        self._concluir(slot, resultado, ts_ms, inicio)

    def _servir_lote(self, trabalho: list[tuple[_Slot, Any, float]]) -> None:
        inicio = time.perf_counter()
        frames = [frame for _, frame, _ in trabalho]
        brutos = trabalho[0][0].detectar_lote(frames)
        custo_lote = (time.perf_counter() - inicio) * 1000.0
        for (slot, frame, ts_ms), bruto in zip(trabalho, brutos, strict=True):
            if slot.stats is not None:
                slot.stats.duracao("inferencia_lote", custo_lote)
            t0 = time.perf_counter()
            resultado = slot.pos_lote(frame, bruto, Cronometro(slot.stats))
            self._concluir(slot, resultado, ts_ms, t0)

    def _concluir(self, slot: _Slot, resultado: Any, ts_ms: float, inicio: float) -> None:
        slot.ultima_ms = (time.perf_counter() - inicio) * 1000.0
        slot.servidos += 1
        self.inferencias += 1
        if slot.stats is not None:
            slot.stats.contar("inferencias")
            slot.stats.duracao("idade_na_inferencia", time.time() * 1000.0 - ts_ms)
        slot.entregar(resultado, ts_ms)
