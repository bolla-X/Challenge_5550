"""Simulador "E se?" de regras (X2, MISSÃO 2).

Reprocessa as trilhas gravadas (app/services/trilhas.py) com outra zona,
outra histerese ou outro conjunto de EPIs exigidos, e diz quantos alertas
TERIAM disparado. Determinístico (função pura dos registros e dos
parâmetros), isolado (não toca no banco nem no worker) e nunca cria, muda ou
apaga alerta real.

A histerese é a MESMA lógica do AlertStateService (`_confirmou`): cria com N
confirmações seguidas OU com `criar_apos_s` segundos de violação sustentada e
pelo menos `min_confirmacoes`; resolve do mesmo jeito com os parâmetros de
resolução. Só regras de EPI e de zona: é o que a tela deixa mudar.

Limites (aparecem na tela): a trilha guarda o que o modelo VIU na época — o
simulador não reroda o modelo; EPI que estava desligado na gravação não tem
dado e não pode ser simulado; a "soneca" do "resolver todos" e as regras de
emergência ficam de fora.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from app.services.alert_state_service import AlertStateService

REGRAS_SIMULAVEIS_PREFIXOS = ("missing_", "incorrect_")
REGRA_ZONA = "risk_area_presence"


@dataclass(frozen=True)
class Parametros:
    epis: frozenset[str]
    zona: tuple[tuple[float, float], ...] | None
    criar_apos_quadros: int = 8
    criar_apos_s: float | None = 2.0
    min_confirmacoes: int = 2
    resolver_apos_quadros: int = 20
    resolver_apos_s: float | None = None
    min_confirmacoes_resolver: int = 3


@dataclass
class _Estado:
    violacoes: int = 0
    desde: float | None = None
    normais: int = 0
    normal_desde: float | None = None
    ativo: bool = False
    zona: bool = False


@dataclass
class Resultado:
    alertas: list[dict[str, Any]] = field(default_factory=list)
    incidentes: int = 0
    registros: int = 0
    pessoas: int = 0

    def resumo(self, inicio: float, fim: float, balde_s: float) -> dict[str, Any]:
        return {
            "total": len(self.alertas),
            "por_regra": dict(Counter(a["regra"] for a in self.alertas)),
            "incidentes": self.incidentes,
            "linha": baldes([a["t"] for a in self.alertas], inicio, fim, balde_s),
            "registros": self.registros,
            "pessoas": self.pessoas,
        }


def dentro(ponto: tuple[float, float], poligono: tuple[tuple[float, float], ...]) -> bool:
    x, y = ponto
    dentro_ = False
    j = len(poligono) - 1
    for i in range(len(poligono)):
        xi, yi = poligono[i]
        xj, yj = poligono[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / max(yj - yi, 1e-12) + xi):
            dentro_ = not dentro_
        j = i
    return dentro_


def baldes(instantes: list[float], inicio: float, fim: float, balde_s: float) -> list[list[float]]:
    """[[início do balde, quantidade], ...] cobrindo a janela inteira (zeros incluídos)."""
    balde_s = max(1.0, float(balde_s))
    n = max(1, int((fim - inicio) // balde_s) + 1)
    contagem = [0] * n
    for t in instantes:
        i = int((t - inicio) // balde_s)
        if 0 <= i < n:
            contagem[i] += 1
    return [[round(inicio + i * balde_s, 3), c] for i, c in enumerate(contagem)]


def violacoes(registro: dict[str, Any], p: Parametros) -> dict[tuple[str, str, Any], bool]:
    """Chaves (regra, feature, pessoa) violadas neste registro -> se a pessoa está na zona."""
    saida: dict[tuple[str, str, Any], bool] = {}
    for pessoa in registro.get("p") or []:
        pid, _pe_x, _pe_y, cx, cy, epis = pessoa
        na_zona = bool(p.zona) and dentro((cx, cy), p.zona)  # type: ignore[arg-type]
        for chave in p.epis:
            codigo = (epis or {}).get(chave)
            if codigo == "m":
                saida[(f"missing_{chave}", chave, pid)] = na_zona
            elif codigo == "i":
                saida[(f"incorrect_{chave}", chave, pid)] = na_zona
        if na_zona:
            saida[(REGRA_ZONA, "risk_area", pid)] = True
    return saida


def simular(registros: Iterable[dict[str, Any]], p: Parametros) -> Resultado:
    return simular_com(registros, lambda registro: violacoes(registro, p), p)


def simular_com(
    registros: Iterable[dict[str, Any]],
    violacoes_do_registro: Callable[[dict[str, Any]], dict[tuple[str, str, Any], bool]],
    p: Parametros,
) -> Resultado:
    """Histerese do AlertStateService sobre as violações que `violacoes_do_registro`
    extrai de cada registro. `simular` usa as de EPI/zona; o editor de regras
    (app/services/regras_editor.py) injeta as da regra que está sendo testada —
    a confirmação, a resolução e a contagem de incidentes são as mesmas."""
    estados: dict[tuple[str, str, Any], _Estado] = {}
    resultado = Resultado()
    pessoas: set[Any] = set()
    abertos: Counter[tuple[str, bool]] = Counter()  # (regra, na_zona) -> alertas ativos
    confirmou = AlertStateService._confirmou
    for registro in registros:
        resultado.registros += 1
        agora = float(registro["t"])
        atuais = violacoes_do_registro(registro)
        pessoas.update(pid for pid, *_ in (registro.get("p") or []))
        for chave, na_zona in atuais.items():
            e = estados.setdefault(chave, _Estado())
            if e.violacoes == 0:
                e.desde = agora
            e.violacoes += 1
            e.normais, e.normal_desde = 0, None
            if not e.ativo and confirmou(e.violacoes, e.desde, agora, p.criar_apos_quadros, p.criar_apos_s, p.min_confirmacoes):
                e.ativo, e.zona = True, na_zona
                if abertos[(chave[0], na_zona)] == 0:
                    resultado.incidentes += 1
                abertos[(chave[0], na_zona)] += 1
                resultado.alertas.append({"t": agora, "regra": chave[0], "feature": chave[1], "pessoa": chave[2],
                                          "na_zona": na_zona})
        for chave in [k for k in estados if k not in atuais]:
            e = estados[chave]
            if e.normais == 0:
                e.normal_desde = agora
            e.normais += 1
            e.violacoes, e.desde = 0, None
            if confirmou(e.normais, e.normal_desde, agora, p.resolver_apos_quadros, p.resolver_apos_s,
                         p.min_confirmacoes_resolver):
                if e.ativo:
                    abertos[(chave[0], e.zona)] -= 1
                del estados[chave]
    resultado.pessoas = len(pessoas)
    return resultado


def regra_simulavel(regra: str) -> bool:
    return regra == REGRA_ZONA or regra.startswith(REGRAS_SIMULAVEIS_PREFIXOS)
