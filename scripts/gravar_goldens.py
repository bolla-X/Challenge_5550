"""Grava as respostas REAIS do Gemini para as 3 cenas, nas 2 versões de prompt.

Rodado **à mão**, uma vez. Nunca pelo `pytest`.

    python scripts/gravar_goldens.py

Depois disso as respostas estão congeladas em `tests/goldens/`, e
`tests/test_llm_goldens.py` roda contra elas — offline, determinístico, sem
cota e sem rede. É o que separa "o teste passa" de "o teste passa porque a API
estava de bom humor hoje".

Precisa de `GEMINI_API_KEY` no `.env`. A chave **não** entra no arquivo
gravado: o golden guarda a resposta, o modelo e a latência, nunca o segredo.

Reescrever um golden é decisão consciente — use `--forcar`. Sem isso o script
recusa sobrescrever, porque um golden trocado sem intenção transforma um teste
de regressão num teste que sempre passa.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.llm import AnalisadorDeRisco, ProvedorGemini, carregar_prompt, versoes_de_prompt  # noqa: E402
from scripts.fetch_fixtures import CENAS, caminho_da_cena  # noqa: E402

DIR_GOLDENS = RAIZ / "tests" / "goldens"


def gravar(cena_nome: str, versao: str, provedor: ProvedorGemini, *, forcar: bool) -> dict | None:
    destino = DIR_GOLDENS / f"{cena_nome}_{versao}.json"
    if destino.exists() and not forcar:
        print(f"  [existe] {destino.name} — use --forcar para reescrever")
        return None

    imagem = caminho_da_cena(cena_nome).read_bytes()
    analisador = AnalisadorDeRisco(provedor=provedor)

    inicio = time.perf_counter()
    try:
        crua = provedor.analisar(imagem, carregar_prompt(versao))
    except Exception as exc:  # noqa: BLE001
        # `redigir_segredos` ja passou dentro do provedor; ainda assim nao
        # gravamos nada de uma chamada que falhou.
        print(f"  [FALHOU] {cena_nome}/{versao}: {type(exc).__name__}: {exc}")
        return None
    latencia_ms = (time.perf_counter() - inicio) * 1000.0

    analise = analisador.validar(crua)
    registro = {
        "cena": cena_nome,
        "versao": versao,
        "modelo": provedor.modelo,
        "gravado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "latencia_ms": round(latencia_ms, 1),
        "bytes_imagem": len(imagem),
        "resposta_crua": crua,
        "analise_validada": analise.model_dump() if analise else None,
    }
    DIR_GOLDENS.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")

    situacao = "valida" if analise else "REJEITADA pelo schema"
    print(f"  [ok] {destino.name}: {latencia_ms:7.0f} ms, resposta {situacao}")
    if analise:
        print(
            f"       nivel={analise.nivel_risco} epis={analise.epis_ausentes} "
            f"conf={analise.confianca}"
        )
    return registro


def main() -> int:
    analisador_cli = argparse.ArgumentParser(description="Grava goldens reais do Gemini.")
    analisador_cli.add_argument("--forcar", action="store_true", help="Reescreve goldens existentes.")
    argumentos = analisador_cli.parse_args()

    provedor = ProvedorGemini()
    if not provedor.configurado:
        print(
            "GEMINI_API_KEY ausente.\n"
            "Coloque a chave no .env (esse arquivo e ignorado pelo git) e rode de novo.\n"
            "Obtenha em https://aistudio.google.com/apikey (free tier).",
            file=sys.stderr,
        )
        return 1

    print(f"modelo: {provedor.modelo} | cenas: {len(CENAS)} | versoes: {versoes_de_prompt()}")
    gravados = 0
    for cena in CENAS:
        for versao in versoes_de_prompt():
            print(f"\n{cena.nome} / {versao}")
            if gravar(cena.nome, versao, provedor, forcar=argumentos.forcar):
                gravados += 1

    esperados = len(CENAS) * len(versoes_de_prompt())
    print(f"\n{gravados} de {esperados} goldens gravados em {DIR_GOLDENS.relative_to(RAIZ)}")
    print("Agora rode: pytest tests/test_llm_goldens.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
