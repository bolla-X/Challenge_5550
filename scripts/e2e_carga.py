"""Inferências/s por câmera durante cada teste E2E (evidência de "sensível à carga").

    python scripts/e2e_carga.py              # só os testes que falharam
    python scripts/e2e_carga.py --todos      # todos

Lê `bench/runtime/e2e-testes.jsonl` (início e fim de cada teste, gravado pelo
`e2e/conftest.py`) e `bench/runtime/e2e-inferencia.jsonl` (amostra a cada 2 s
das inferências/s de cada câmera, janela de 2 s). Para cada teste imprime, por
câmera, o mínimo e a média de inferências/s dentro da janela do teste.

Regra do portão (MISSÃO 4): uma falha só é "sensível à carga" se o teste passar
isolado E a câmera envolvida tiver recebido menos de 1 inferência/s durante a
espera. Este script dá a segunda metade da evidência.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent.parent / "bench" / "runtime"


def _ler(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []
    return [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines() if linha.strip()]


def taxas_na_janela(amostras: list[dict], inicio: float, fim: float) -> dict[str, dict[str, float | int]]:
    por_camera: dict[str, list[float]] = {}
    for amostra in amostras:
        if inicio <= amostra["ts"] <= fim:
            for cid, c in amostra["cameras"].items():
                por_camera.setdefault(cid, []).append(float(c.get("inferencias", 0.0)))
    return {cid: {"n": len(v), "min": round(min(v), 2), "media": round(sum(v) / len(v), 2)}
            for cid, v in sorted(por_camera.items()) if v}


def main(argv: list[str]) -> int:
    todos = "--todos" in argv
    testes = _ler(RUNTIME / "e2e-testes.jsonl")
    amostras = _ler(RUNTIME / "e2e-inferencia.jsonl")
    for t in testes:
        if not todos and t["resultado"] != "failed":
            continue
        taxas = taxas_na_janela(amostras, t["inicio"], t["fim"])
        resumo = "  ".join(f"cam {cid}: min {v['min']} média {v['media']} (n={v['n']})" for cid, v in taxas.items())
        print(f"{t['resultado']:7} {t['fim'] - t['inicio']:6.1f}s  {t['teste']}\n          {resumo or 'sem amostras'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
