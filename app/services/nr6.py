"""Ligação de cada infração de EPI ao requisito da NR-6 (G10).

Fonte (lida em 13/10/2026, docs/NEXT2026/PESQUISA.md):
https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/participacao-social/conselhos-e-orgaos-colegiados/comissao-tripartite-partitaria-permanente/normas-regulamentadora/normas-regulamentadoras-vigentes/nr-06-atualizada-2025-ii.pdf
(Portaria MTE nº 57, de 16/01/2025; o próprio PDF avisa que não substitui o
texto publicado no DOU).

Só entra o que o texto sustenta, com o trecho literal:

- toda infração de EPI liga a 6.5.1 e) (a organização deve exigir o uso) e a
  6.6.1 a) (o trabalhador deve usar o EPI fornecido);
- e ao item do Anexo I do tipo de EPI: A.1 capacete, B.1 óculos, C.1 protetor
  auditivo, F.1 luvas, G.1 calçado.

Ficam DE FORA, com o motivo (aparecem no relatório como "sem item sustentado"):

- colete de alta visibilidade: o Anexo I não o lista (E.1 é vestimenta contra
  agentes térmicos/mecânicos/químicos/radiação/umidade; E.2 é colete à prova de
  balas);
- máscara: a classe do modelo não distingue respirador (Anexo I, D) de máscara
  comum — ligar ao Anexo D afirmaria mais do que o modelo vê.
"""

from __future__ import annotations

from typing import Any

FONTE_NR6 = (
    "https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/participacao-social/conselhos-e-orgaos-colegiados/"
    "comissao-tripartite-partitaria-permanente/normas-regulamentadora/normas-regulamentadoras-vigentes/"
    "nr-06-atualizada-2025-ii.pdf"
)

ITENS_GERAIS: list[dict[str, str]] = [
    {"item": "6.5.1 e)", "texto": "Cabe à organização, quanto ao EPI: […] e) exigir seu uso;"},
    {
        "item": "6.6.1 a)",
        "texto": "Cabe ao trabalhador, quanto ao EPI: a) usar o fornecido pela organização, observado o disposto no item 6.5.2;",
    },
]

ANEXO_I: dict[str, dict[str, str]] = {
    "helmet": {"item": "Anexo I, A.1", "texto": "A.1 - Capacete"},
    "glasses": {"item": "Anexo I, B.1", "texto": "B.1 - Óculos"},
    "ear_protection": {"item": "Anexo I, C.1", "texto": "C.1 - Protetor auditivo"},
    "gloves": {"item": "Anexo I, F.1", "texto": "F.1 - Luvas"},
    "safety_shoe": {"item": "Anexo I, G.1", "texto": "G.1 - Calçado"},
}

SEM_ITEM: dict[str, str] = {
    "vest": "O Anexo I não lista colete de alta visibilidade (E.2 é colete à prova de balas).",
    "mask": "O modelo não distingue respirador (Anexo I, D) de máscara comum.",
}


def epi_da_regra(regra: str) -> str | None:
    """`missing_helmet` / `incorrect_helmet` → `helmet`; outras regras → None."""
    for prefixo in ("missing_", "incorrect_"):
        if regra.startswith(prefixo):
            return regra[len(prefixo):]
    return None


def mapear(contagem_por_regra: dict[str, int]) -> list[dict[str, Any]]:
    """Uma linha por EPI com infração: quantas, e os itens da NR-6 (ou o motivo de não haver)."""
    por_epi: dict[str, int] = {}
    for regra, n in contagem_por_regra.items():
        epi = epi_da_regra(regra)
        if epi:
            por_epi[epi] = por_epi.get(epi, 0) + n
    linhas = []
    for epi, n in sorted(por_epi.items(), key=lambda kv: -kv[1]):
        if epi in ANEXO_I:
            linhas.append({"epi": epi, "alertas": n, "itens": [*ITENS_GERAIS, ANEXO_I[epi]], "sem_item": None})
        else:
            linhas.append({"epi": epi, "alertas": n, "itens": [], "sem_item": SEM_ITEM.get(epi, "Sem item sustentado pelo texto.")})
    return linhas
