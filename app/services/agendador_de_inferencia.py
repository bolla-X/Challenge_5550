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

**Rodízio ponderado (MISSÃO 2, P0.1).** O rodízio igualitário dava à câmera
que alguém está olhando (portal, tela de foco, palco) só 1/N das inferências:
com 4 câmeras o Portal não chegava a "Liberado" e o E2E só passava parando as
outras. Agora a escolha é um *smooth weighted round-robin* (o do nginx):
cada câmera pendente ganha crédito igual ao seu peso, a de maior crédito é
servida e paga o total. As câmeras em foco somam peso igual ao número das
outras — pelo menos 50 % das vagas — e as demais dividem o resto. Uma guarda
de espera máxima (`espera_max_s`, padrão 2,5 s) serve primeiro a câmera
pendente há mais tempo sem inferência, para nenhuma ficar sem análise.

Quando a máquina não dá conta das duas metas ao mesmo tempo (vazão abaixo de
~2 análises/s com 4 câmeras, medido com a CPU a 100 % por outros processos), o
foco vence: depois de uma vaga fora do foco, a próxima é do foco. As outras
continuam sendo servidas em rodízio, só mais devagar.

**Prioridade de confirmação.** Uma análise que vê sinal de emergência (a
classe de queda) pede `priorizar(camera, s)`: a PRÓXIMA vaga dessa câmera
passa à frente (uma vaga por pedido, válida por `s` segundos). A regra de emergência continua
exigindo 2 análises seguidas — o que muda é que a 2ª vem logo, em vez de
esperar a vez no rodízio (a queda da gravação fica no chão ~1 s).
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
    # Aplicado só ao quadro que vai de fato ser inferido (resize/rotação): o
    # worker submete a cada quadro que chega, e a maioria é sobrescrita no slot
    # sem nunca ser analisada — preparar todos era trabalho jogado fora.
    preparar: Callable[[Any], Any] | None = None
    frame: Any = None
    ts_ms: float = 0.0
    pendente: bool = False
    servidos: int = 0
    descartados: int = 0
    ultima_ms: float = field(default=0.0)
    # Rodízio ponderado: crédito acumulado e quando foi servida pela última vez.
    credito: float = 0.0
    ultimo_servico: float = 0.0
    servidos_em_foco: int = 0
    # Regra dos 3 s: maior intervalo entre duas vagas seguidas desta câmera e
    # quantos intervalos passaram de 3 s (a espera da subida não conta).
    escolhas: int = 0
    maior_espera_s: float = 0.0
    esperas_acima_de_3s: int = 0


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
    def __init__(
        self,
        *,
        lote: bool = False,
        lote_max: int = 4,
        focadas: Callable[[], set[int]] | None = None,
        espera_max_s: float = 2.5,
        fracao_foco: float = 0.5,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self.lote = bool(lote)
        self.lote_max = max(1, int(lote_max))
        # Quem está em foco na UI agora (ver MonitorService.cameras_em_foco).
        self._focadas = focadas or (lambda: set())
        self.espera_max_s = max(0.1, float(espera_max_s))
        # Fração das vagas do foco quando ninguém está atrasado: 0,5 a 0,7.
        self.fracao_foco = min(0.7, max(0.5, float(fracao_foco)))
        self._relogio = relogio
        self._slots: dict[int, _Slot] = {}
        self._ordem: list[int] = []
        # Prioridade de confirmação: câmera -> até quando vale e quantas vagas
        # ainda passa à frente. UMA vaga por pedido: com 2 s de exclusividade,
        # cada falso positivo isolado da classe de queda roubava as vagas da
        # câmera em foco (E2E do portal com 4 câmeras).
        self._prioridade_ate: dict[int, float] = {}
        self._fichas: dict[int, int] = {}
        # A última vaga foi de uma câmera em foco? (garante ≥ 1 de cada 2 ao foco)
        self._ultima_foi_foco = False
        self._cond = threading.Condition()
        self._rodando = threading.Event()
        self._thread: threading.Thread | None = None
        self.inferencias = 0
        self.ultimo_erro: str | None = None

    # ----------------------------------------------------------- registro
    def registrar(self, camera_id: int, analisar, entregar, *, stats=None, detectar_lote=None, pos_lote=None,
                  preparar=None) -> None:
        with self._cond:
            slot = _Slot(camera_id, analisar, entregar, stats, detectar_lote, pos_lote, preparar)
            slot.ultimo_servico = self._relogio()
            self._slots[camera_id] = slot
            if camera_id not in self._ordem:
                self._ordem.append(camera_id)
        self._garantir_thread()

    def remover(self, camera_id: int) -> None:
        with self._cond:
            self._slots.pop(camera_id, None)
            if camera_id in self._ordem:
                self._ordem.remove(camera_id)

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

    def descartar_pendente(self, camera_id: int) -> None:
        """Joga fora o quadro esperando vez (câmera pausada pelo palco).

        Sem isto, ao entrar na cena do Portal cada câmera recém-pausada ainda
        tinha um quadro no slot — e, esperando há mais de `espera_max_s`, a
        guarda os servia ANTES do portal: até uma análise inteira por câmera.
        """
        with self._cond:
            slot = self._slots.get(camera_id)
            if slot is not None and slot.pendente:
                slot.pendente, slot.frame = False, None

    def priorizar(self, camera_id: int, segundos: float = 2.0) -> None:
        """Serve esta câmera primeiro por `segundos` (sinal de emergência a confirmar)."""
        with self._cond:
            self._prioridade_ate[camera_id] = self._relogio() + max(0.0, float(segundos))
            self._fichas[camera_id] = 1

    def em_prioridade(self, camera_id: int) -> bool:
        with self._cond:
            return self._prioridade_ate.get(camera_id, 0.0) > self._relogio()

    def pendentes(self) -> int:
        with self._cond:
            return sum(1 for s in self._slots.values() if s.pendente)

    def estado(self) -> dict[str, Any]:
        with self._cond:
            return {
                "modo": "lote" if self.lote else "rodizio_ponderado",
                "cameras": list(self._ordem),
                "em_foco": sorted(self._focadas_registradas()),
                "espera_max_s": self.espera_max_s,
                "fracao_foco": self.fracao_foco,
                "inferencias": self.inferencias,
                "ultimo_erro": self.ultimo_erro,
                "por_camera": {
                    str(s.camera_id): {
                        "servidos": s.servidos,
                        "servidos_em_foco": s.servidos_em_foco,
                        "descartados": s.descartados,
                        "ultima_ms": round(s.ultima_ms, 1),
                        "maior_espera_s": round(s.maior_espera_s, 2),
                        "esperas_acima_de_3s": s.esperas_acima_de_3s,
                        "vagas": s.escolhas,
                    }
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

    def _focadas_registradas(self) -> set[int]:
        try:
            focadas = set(self._focadas() or ())
        except Exception:  # noqa: BLE001  (fonte de foco com problema = sem prioridade, nunca para o agendador)
            focadas = set()
        return focadas & set(self._slots)

    def pesos(self, focadas: set[int]) -> dict[int, float]:
        """Peso de cada câmera registrada: as em foco somam `fracao_foco` do total (≥ 50 %)."""
        ids = list(self._slots)
        outras = [c for c in ids if c not in focadas]
        if not focadas or not outras:
            return {c: 1.0 for c in ids}
        peso_foco = len(outras) / len(focadas) * self.fracao_foco / (1.0 - self.fracao_foco)
        return {c: (peso_foco if c in focadas else 1.0) for c in ids}

    def _escolher(self) -> list[_Slot]:
        """Próximos slots a servir (rodízio ponderado + guarda de espera). Chamar com o lock."""
        pendentes = [self._slots[c] for c in self._ordem if c in self._slots and self._slots[c].pendente]
        if not pendentes:
            return []
        agora = self._relogio()
        focadas = self._focadas_registradas()
        pesos = self.pesos(focadas)
        limite = self.lote_max if self.lote else 1
        escolhidos: list[_Slot] = []
        while pendentes and len(escolhidos) < limite:
            atrasados = [s for s in pendentes if agora - s.ultimo_servico >= self.espera_max_s]
            urgentes = [s for s in pendentes
                        if self._fichas.get(s.camera_id, 0) > 0 and self._prioridade_ate.get(s.camera_id, 0.0) > agora]
            em_foco = [s for s in pendentes if s.camera_id in focadas]
            if urgentes:
                slot = urgentes[0]
                self._fichas[slot.camera_id] -= 1
            elif atrasados and em_foco and not self._ultima_foi_foco and len(em_foco) < len(pendentes):
                # Máquina lenta: a guarda das outras dispararia sempre e o foco
                # cairia a 1/N. A vaga alterna — o foco nunca fica abaixo de 50 %.
                slot = min(em_foco, key=lambda s: s.ultimo_servico)
            elif atrasados:
                slot = min(atrasados, key=lambda s: s.ultimo_servico)
            else:
                total = sum(pesos.get(s.camera_id, 1.0) for s in pendentes)
                for s in pendentes:
                    s.credito += pesos.get(s.camera_id, 1.0)
                slot = max(pendentes, key=lambda s: s.credito)  # empate: o primeiro na ordem
                slot.credito -= total
            pendentes.remove(slot)
            escolhidos.append(slot)
            self._ultima_foi_foco = slot.camera_id in focadas
        for slot in escolhidos:
            slot.pendente = False
            if slot.escolhas:
                espera = agora - slot.ultimo_servico
                slot.maior_espera_s = max(slot.maior_espera_s, espera)
                slot.esperas_acima_de_3s += espera > 3.0
            slot.escolhas += 1
            slot.ultimo_servico = agora
            if slot.camera_id in focadas:
                slot.servidos_em_foco += 1
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
                trabalho = [(s, s.preparar(f) if s.preparar else f, ts) for s, f, ts in trabalho]
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
