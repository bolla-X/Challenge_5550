"""Re-associação de ID depois do rastreador (MISSÃO 2, P0.2).

O rastreador (IoU ou ByteTrack) perde a pessoa por uma oclusão curta ou uma
caixa que pulou, e ela volta como "Pessoa N+1" — cada volta abria alertas
novos. Regra da missão, aplicada à saída de qualquer rastreador: um track
NOVO que surge a até `distancia_larguras` × a largura da caixa de onde um
track sumiu, em até `janela_s`, herda o ID antigo.

Sem aparência e sem rosto: só posição e tempo. O ID continua sendo de
rastreio, nunca identidade.

Os IDs que saem daqui são próprios (1, 2, 3…), não os do rastreador: assim
o ID herdado nunca colide com um ID cru que o rastreador venha a reusar.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from app.vision.schemas import BoundingBox, Detection


@dataclass
class _Sumido:
    id_estavel: int
    caixa: BoundingBox
    desde: float


class ReassociadorDeIds:
    def __init__(
        self,
        *,
        distancia_larguras: float = 1.5,
        janela_s: float = 2.0,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self.distancia_larguras = float(distancia_larguras)
        self.janela_s = float(janela_s)
        self._relogio = relogio
        self._mapa: dict[int, int] = {}  # id cru do rastreador -> id estável
        self._vistos: dict[int, BoundingBox] = {}  # id estável -> última caixa (análise anterior)
        self._sumidos: list[_Sumido] = []
        self._proximo = 1
        self.herancas = 0

    def reset(self) -> None:
        self._mapa.clear()
        self._vistos.clear()
        self._sumidos.clear()
        self._proximo = 1
        self.herancas = 0

    def _novo_id(self) -> int:
        novo = self._proximo
        self._proximo += 1
        return novo

    def aplicar(self, deteccoes: list[Detection]) -> list[Detection]:
        agora = self._relogio()
        self._sumidos = [s for s in self._sumidos if agora - s.desde <= self.janela_s]

        crus = [d.track_id for d in deteccoes]
        novos = [i for i, cru in enumerate(crus) if cru is not None and cru not in self._mapa]
        estaveis: dict[int, int] = {}
        for i, cru in enumerate(crus):
            if cru is not None and cru in self._mapa:
                estaveis[i] = self._mapa[cru]

        # O ID cru que voltou retoma o estável dele: sai da lista de sumidos.
        em_cena = set(estaveis.values())
        self._sumidos = [s for s in self._sumidos if s.id_estavel not in em_cena]

        # Pares (track novo, sumido) dentro do raio, do mais perto ao mais longe.
        pares = []
        for i in novos:
            cx, cy = deteccoes[i].box.center
            for j, sumido in enumerate(self._sumidos):
                sx, sy = sumido.caixa.center
                dist = ((cx - sx) ** 2 + (cy - sy) ** 2) ** 0.5
                if dist <= self.distancia_larguras * max(sumido.caixa.width, 1):
                    pares.append((dist, i, j))
        pares.sort()
        herdou: dict[int, int] = {}
        usados: set[int] = set()
        for _, i, j in pares:
            if i in herdou or j in usados:
                continue
            herdou[i] = self._sumidos[j].id_estavel
            usados.add(j)
        self._sumidos = [s for j, s in enumerate(self._sumidos) if j not in usados]
        self.herancas += len(herdou)
        # O ID cru antigo, se voltar, não pode duplicar o estável que foi herdado.
        herdados = set(herdou.values())
        self._mapa = {c: e for c, e in self._mapa.items() if e not in herdados}

        for i in novos:
            estavel = herdou.get(i) or self._novo_id()
            cru = crus[i]
            assert cru is not None
            self._mapa[cru] = estavel
            estaveis[i] = estavel

        # Quem estava na análise anterior e não está nesta passa a "sumido".
        atuais = {estaveis[i]: deteccoes[i].box for i in estaveis}
        for id_estavel, caixa in self._vistos.items():
            if id_estavel not in atuais:
                self._sumidos.append(_Sumido(id_estavel, caixa, agora))
        self._vistos = atuais
        # IDs crus esquecidos pelo rastreador não voltam: o mapa só cresce com
        # quem está em cena (limite natural: pessoas por cena x tempo de turno).
        if len(self._mapa) > 5000:
            vivos = {crus[i] for i in estaveis}
            self._mapa = {c: e for c, e in self._mapa.items() if c in vivos}

        saida = [d.with_track_id(estaveis[i]) if i in estaveis else d for i, d in enumerate(deteccoes)]
        saida.sort(key=lambda d: d.track_id or 0)
        return saida


class RastreadorComReassociacao:
    """Mesma interface do `PersonTracker`: rastreador cru + re-associação por cima."""

    def __init__(self, rastreador, reassociador: ReassociadorDeIds | None = None) -> None:
        self.rastreador = rastreador
        self.reassociador = reassociador or ReassociadorDeIds()
        self.confianca_minima = getattr(rastreador, "confianca_minima", None)

    def reset(self) -> None:
        self.rastreador.reset()
        self.reassociador.reset()

    @property
    def active_count(self) -> int:
        return self.rastreador.active_count

    def update(self, detections: list[Detection]) -> list[Detection]:
        return self.reassociador.aplicar(self.rastreador.update(detections))
