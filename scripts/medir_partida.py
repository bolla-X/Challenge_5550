"""Tempo de subida da demo: de `python run.py --demo` até a primeira análise publicada.

    python scripts/medir_partida.py --frio 3     # cada rodada com um cache NOVO e vazio
    python scripts/medir_partida.py --quente 3   # cache de runtime/ov_cache (aquecido)

"Frio" aponta `OV_CACHE_DIR` para uma pasta nova e vazia a cada rodada (nada é
apagado: cada rodada ganha um nome novo em bench/runtime/). "Quente" usa o
cache padrão, `runtime/ov_cache/`, que o `scripts/preparar.py` aquece.

Marcos de cada rodada (segundos desde o Popen): HTTP respondendo, acessos
impressos (modelos aquecidos e câmeras ligadas) e a primeira análise publicada
em qualquer câmera (`analises_publicadas` do diagnóstico do pipeline). O
resultado vai para bench/runtime/partida.jsonl, uma linha por rodada.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "e2e"))

from capturas_de_tela import ServidorDemo  # noqa: E402


def uma_rodada(cache: Path, rotulo: str, limite_s: float = 600.0) -> dict:
    os.environ["OV_CACHE_DIR"] = str(cache)
    servidor = ServidorDemo()
    inicio = time.monotonic()
    marcos: dict[str, float] = {}
    try:
        servidor.subir(0)
        marcos["acessos_impressos_s"] = round(time.monotonic() - inicio, 1)
        sessao = servidor.sessao("supervisor")
        while time.monotonic() - inicio < limite_s:
            try:
                diag = sessao.get(servidor.base + "/api/diagnostics/pipeline", timeout=5).json()
            except requests.RequestException:
                diag = {}
            totais = [(((c or {}).get("stats") or {}).get("totais") or {}).get("analises_publicadas", 0)
                      for c in (diag.get("cameras") or {}).values()]
            if any(totais):
                marcos["primeira_analise_s"] = round(time.monotonic() - inicio, 1)
                break
            time.sleep(0.25)
    finally:
        servidor.parar()
    linha = {"rotulo": rotulo, "cache": str(cache.relative_to(RAIZ)) if cache.is_relative_to(RAIZ) else str(cache),
             "ts": round(time.time()), **marcos}
    with (RAIZ / "bench" / "runtime" / "partida.jsonl").open("a", encoding="utf-8") as saida:
        saida.write(json.dumps(linha) + "\n")
    print(f"[partida] {linha}", flush=True)
    return linha


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frio", type=int, default=0, help="rodadas com cache novo e vazio")
    ap.add_argument("--quente", type=int, default=0, help="rodadas com o cache padrão (runtime/ov_cache)")
    args = ap.parse_args()
    resultados: dict[str, list[float]] = {"frio": [], "quente": []}
    for i in range(args.frio):
        cache = RAIZ / "bench" / "runtime" / f"ov_cache_frio_{int(time.time())}_{i}"
        resultados["frio"].append(uma_rodada(cache, "frio").get("primeira_analise_s", float("nan")))
    for _ in range(args.quente):
        resultados["quente"].append(uma_rodada(RAIZ / "runtime" / "ov_cache", "quente").get("primeira_analise_s", float("nan")))
    for rotulo, tempos in resultados.items():
        if tempos:
            print(f"[partida] {rotulo}: {tempos} s; mediana {statistics.median(tempos):.1f} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
