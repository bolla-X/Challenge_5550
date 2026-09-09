"""Golden tests: 3 cenas × 2 versões de prompt, contra respostas congeladas.

A chamada real ao Gemini acontece **uma vez**, à mão, por
`scripts/gravar_goldens.py`. A partir daí a resposta está gravada em
`tests/goldens/` e estes testes rodam offline.

Por que assim, e não chamando a API no teste: um teste que chama a rede não é
determinístico. Ele passa ou falha por cota, latência, versão de modelo e humor
do serviço — e quando falha, ninguém sabe se o bug é do código ou do dia. Com
a resposta congelada, o que está sob teste é **o nosso validador contra uma
resposta real**, que é exatamente o que queremos travar.

O que estes testes NÃO fazem: julgar se o modelo acertou. Isso é conteúdo de
`docs/SPRINT3.md`, escrito por gente olhando a cena. Aqui só afirmamos que uma
resposta real do modelo atravessa o schema sem virar `None` por acidente, e que
o resultado é estável.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.llm import AnalisadorDeRisco, AnaliseRisco, versoes_de_prompt

RAIZ = Path(__file__).resolve().parent.parent
DIR_GOLDENS = RAIZ / "tests" / "goldens"

CENAS = ("segura", "risco", "ambigua")
CASOS = [(cena, versao) for cena in CENAS for versao in versoes_de_prompt()]

AUSENTE = (
    "Golden ausente: {arquivo}. Ele guarda uma resposta REAL do Gemini e e gravado "
    "a mao, uma vez, com:\n"
    "    python scripts/fetch_fixtures.py   # baixa as 3 cenas\n"
    "    python scripts/gravar_goldens.py   # exige GEMINI_API_KEY no .env\n"
    "Sem ele este teste nao tem o que verificar."
)


def carregar_golden(cena: str, versao: str) -> dict:
    arquivo = DIR_GOLDENS / f"{cena}_{versao}.json"
    if not arquivo.exists():
        pytest.skip(AUSENTE.format(arquivo=arquivo.relative_to(RAIZ)))
    return json.loads(arquivo.read_text(encoding="utf-8"))


@pytest.mark.parametrize(("cena", "versao"), CASOS)
def test_golden_atravessa_o_schema(cena, versao):
    """A resposta real gravada tem que validar — offline, sem rede."""
    golden = carregar_golden(cena, versao)
    analisador = AnalisadorDeRisco(provedor=None)

    analise = analisador.validar(golden["resposta_crua"])

    assert isinstance(analise, AnaliseRisco), (
        f"{cena}/{versao}: a resposta real gravada foi REJEITADA pelo schema.\n"
        f"motivos: {analisador.ultimos_erros}\n"
        f"resposta: {golden['resposta_crua'][:300]}"
    )


@pytest.mark.parametrize(("cena", "versao"), CASOS)
def test_golden_e_estavel(cena, versao):
    """Revalidar a mesma resposta tem que dar o mesmo resultado.

    Pega mudanca silenciosa no validador ou no schema: se alguem apertar uma
    regra, o golden gravado passa a divergir e este teste acusa — que e o
    comportamento certo, e a hora de decidir se o golden ou a regra muda.
    """
    golden = carregar_golden(cena, versao)
    if golden["analise_validada"] is None:
        pytest.skip(f"{cena}/{versao}: golden gravado ja era invalido; nada a comparar")

    revalidada = AnalisadorDeRisco(provedor=None).validar(golden["resposta_crua"])

    assert revalidada is not None
    assert revalidada.model_dump() == golden["analise_validada"], (
        f"{cena}/{versao}: revalidar a resposta gravada deu resultado diferente do gravado. "
        "O validador ou o schema mudou desde a gravacao."
    )


@pytest.mark.parametrize(("cena", "versao"), CASOS)
def test_golden_registra_procedencia(cena, versao):
    """Golden sem modelo e latencia nao serve de evidencia para o relatorio."""
    golden = carregar_golden(cena, versao)

    assert golden["cena"] == cena
    assert golden["versao"] == versao
    assert golden["modelo"], "sem o nome do modelo o numero nao e comparavel depois"
    assert golden["latencia_ms"] > 0, "a latencia real vai para docs/SPRINT3.md"
    assert golden["bytes_imagem"] > 0
    assert "AIza" not in json.dumps(golden), "golden nunca pode carregar chave de API"
