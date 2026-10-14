"""Modo TV / Andon (G8): conformidade por setor, sequência de minutos e conquistas.

Princípios de gamificação da missão, aplicados aqui:

- só indicador POSITIVO: minuto conforme, check-in no portal, alerta
  reconhecido, contribuição de rótulo;
- minuto sem ninguém na câmera é NEUTRO: não conta e não quebra a sequência.
  "Zero alerta" porque não havia pessoa não é mérito — nunca é premiado;
- tudo por SETOR (agregado das câmeras). Nenhum número por pessoa ou por ID.

O minuto é conforme quando, em TODAS as análises dele com gente na cena, todo
EPI exigido e verificável estava "ok" para todas as pessoas. Um EPI que o
modelo não verifica (desligado, classe ausente) não conta contra nem a favor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ESTADOS_VERIFICAVEIS = {"ok", "missing", "incorrect"}


def conformidade_do_quadro(people: list[dict[str, Any]], exigidos: list[str]) -> tuple[int, int, dict[str, bool]]:
    """(pares ok, pares verificáveis, {epi: todos ok}) das pessoas deste quadro."""
    ok = total = 0
    por_epi: dict[str, bool] = {}
    for pessoa in people:
        ppe = pessoa.get("ppe") or {}
        for chave in exigidos:
            status = (ppe.get(chave) or {}).get("status")
            if status not in ESTADOS_VERIFICAVEIS:
                continue
            total += 1
            bom = status == "ok"
            ok += bom
            por_epi[chave] = por_epi.get(chave, True) and bom
    return ok, total, por_epi


@dataclass
class _Minuto:
    indice: int
    com_pessoas: bool = False
    conforme: bool = True
    por_epi: dict[str, bool] = field(default_factory=dict)


class ContadorDeMinutos:
    """Minutos conformes de UMA câmera, alimentado a cada análise nova."""

    def __init__(self) -> None:
        # Chamado com o índice do minuto (epoch // 60) quando um minuto COM
        # pessoas fecha conforme — a Liga de Setores (X8) anota o ponto.
        self.ao_fechar_conforme = None
        self.reset()

    def reset(self) -> None:
        self._atual: _Minuto | None = None
        self.sequencia = 0  # minutos conformes seguidos (neutros não quebram)
        self.melhor_sequencia = 0
        self.minutos_com_pessoas = 0
        self.minutos_conformes = 0
        # epi -> minutos com pessoas em que esse EPI NÃO esteve sempre ok
        self.falhas_por_epi: dict[str, int] = {}
        self.epis_vistos: set[str] = set()
        self.ultimo_ok = 0
        self.ultimo_total = 0

    def registrar(self, people: list[dict[str, Any]], exigidos: list[str], agora_s: float) -> None:
        indice = int(agora_s // 60)
        if self._atual is not None and indice != self._atual.indice:
            self._fechar(self._atual)
            self._atual = None
        if self._atual is None:
            self._atual = _Minuto(indice)
        ok, total, por_epi = conformidade_do_quadro(people, exigidos)
        self.ultimo_ok, self.ultimo_total = ok, total
        if total == 0:
            return  # ninguém verificável neste quadro: neutro
        m = self._atual
        m.com_pessoas = True
        m.conforme = m.conforme and ok == total
        for chave, bom in por_epi.items():
            m.por_epi[chave] = m.por_epi.get(chave, True) and bom

    def _fechar(self, m: _Minuto) -> None:
        if not m.com_pessoas:
            return
        self.minutos_com_pessoas += 1
        for chave, bom in m.por_epi.items():
            self.epis_vistos.add(chave)
            if not bom:
                self.falhas_por_epi[chave] = self.falhas_por_epi.get(chave, 0) + 1
        if m.conforme:
            self.minutos_conformes += 1
            self.sequencia += 1
            self.melhor_sequencia = max(self.melhor_sequencia, self.sequencia)
            if self.ao_fechar_conforme is not None:
                self.ao_fechar_conforme(m.indice)
        else:
            self.sequencia = 0

    def resumo(self) -> dict[str, Any]:
        return {
            "conformidade_atual": round(self.ultimo_ok / self.ultimo_total, 4) if self.ultimo_total else None,
            "sequencia_min": self.sequencia,
            "melhor_sequencia_min": self.melhor_sequencia,
            "minutos_com_pessoas": self.minutos_com_pessoas,
            "minutos_conformes": self.minutos_conformes,
            "epis_sempre_ok": sorted(k for k in self.epis_vistos if not self.falhas_por_epi.get(k)),
        }


# Conquistas do setor: só condições positivas, com um mínimo de minutos
# observados para não "ganhar" com um minuto de câmera ligada.
MINUTOS_MINIMOS_PARA_CONQUISTA = 10
NOMES_EPI = {"helmet": "capacete", "vest": "colete", "gloves": "luvas", "glasses": "óculos", "mask": "máscara",
             "safety_shoe": "calçado", "ear_protection": "protetor auricular"}


def conquistas(setor: dict[str, Any], metas: dict[str, Any]) -> list[dict[str, str]]:
    saida = []
    if setor["minutos_com_pessoas"] >= MINUTOS_MINIMOS_PARA_CONQUISTA:
        for chave in setor["epis_sempre_ok"]:
            saida.append({"id": f"turno_100_{chave}", "texto": f"Turno com 100% {NOMES_EPI.get(chave, chave)}"})
    meta_min = metas.get("minutos_conformes")
    if meta_min and setor["minutos_conformes"] >= meta_min:
        saida.append({"id": "meta_minutos", "texto": f"Meta de {meta_min} minutos conformes atingida"})
    meta_checkins = metas.get("checkins_portal")
    if meta_checkins and setor["checkins_portal"] >= meta_checkins:
        saida.append({"id": "meta_checkins", "texto": f"Meta de {meta_checkins} check-ins no portal atingida"})
    if setor.get("alertas_reconhecidos", 0) > 0 and setor.get("alertas_reconhecidos") == setor.get("alertas_criticos", 0):
        saida.append({"id": "todos_reconhecidos", "texto": "Todos os alertas críticos foram reconhecidos"})
    return saida


def agregar_setor(nome: str, cameras: list[dict[str, Any]]) -> dict[str, Any]:
    """Soma as câmeras de um setor. Sequência do setor = a MENOR das câmeras com gente."""
    com_dado = [c for c in cameras if c.get("minutos_com_pessoas") or c.get("conformidade_atual") is not None]
    ok = sum(c.get("_ok", 0) for c in cameras)
    total = sum(c.get("_total", 0) for c in cameras)
    epis = None
    for c in com_dado:
        atuais = set(c.get("epis_sempre_ok") or [])
        epis = atuais if epis is None else epis & atuais
    return {
        "setor": nome,
        "cameras": [{k: v for k, v in c.items() if not k.startswith("_")} for c in cameras],
        "conformidade_atual": round(ok / total, 4) if total else None,
        "sequencia_min": min((c["sequencia_min"] for c in com_dado), default=0),
        "minutos_com_pessoas": sum(c.get("minutos_com_pessoas", 0) for c in cameras),
        "minutos_conformes": sum(c.get("minutos_conformes", 0) for c in cameras),
        "epis_sempre_ok": sorted(epis or []),
        "checkins_portal": sum(c.get("checkins_portal", 0) for c in cameras),
    }
