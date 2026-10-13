"""Custo de cada protótipo do PR3 por análise, contra o orçamento do quadro.

    python scripts/custo_dos_prototipos.py [--segundos 120]

Sobe o MESMO servidor do E2E (4 câmeras com as gravações de demonstração),
liga o que só roda quando configurado (portaria/portal na câmera Canteiro,
planta calibrada na Multidão), espera e lê `GET /api/diagnostics/pipeline`.
Para cada câmera: p50/p95 de cada etapa nova (`g1_portal`, `g3_g4_g7_sinais`,
`g5_planta`, `g8_andon`, `g9_rotulos`) e o orçamento do quadro = p50 da soma
das inferências (EPI + pessoa + pose) daquela câmera. Regra da missão: um
protótipo entra se custar ≤ 10 % desse orçamento.

Grava `bench/results/custo-prototipos-<carimbo>.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "e2e"))

from conftest import ServidorE2E  # noqa: E402

ETAPAS_NOVAS = ["g1_portal", "g3_g4_g7_sinais", "g5_planta", "g8_andon", "g9_rotulos"]
INFERENCIAS = ["inferencia_epi", "inferencia_pessoa", "inferencia_pose"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segundos", type=float, default=120.0)
    args = ap.parse_args()
    servidor = ServidorE2E()
    try:
        servidor.subir()
        tec = servidor.sessao("technical")
        canteiro, multidao = servidor.cameras["Canteiro"], servidor.cameras["Multidão"]
        tec.put(f"{servidor.base}/api/cameras/{canteiro}/gate", json={"required": ["helmet", "vest"]}, timeout=10)
        tec.put(f"{servidor.base}/api/cameras/{multidao}/planta", timeout=10, json={
            "pontos_camera": [[0.05, 0.55], [0.95, 0.55], [0.98, 0.98], [0.02, 0.98]],
            "pontos_planta": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]],
        })
        print(f"[custo] medindo {args.segundos:.0f} s com 4 câmeras…")
        time.sleep(args.segundos)
        diag = tec.get(f"{servidor.base}/api/diagnostics/pipeline?janela_s={int(args.segundos)}", timeout=30).json()
    finally:
        servidor.parar()

    nomes = {v: k for k, v in servidor.cameras.items()}
    saida = {"segundos": args.segundos, "cameras": {}}
    for cid, cam in (diag.get("cameras") or {}).items():
        etapas = cam["stats"]["etapas"]
        orcamento = sum((etapas.get(e) or {}).get("p50") or 0.0 for e in INFERENCIAS)
        linha = {"orcamento_ms_p50": round(orcamento, 1), "analises": (etapas.get("inferencia_epi") or {}).get("n")}
        for e in ETAPAS_NOVAS:
            if e in etapas:
                p50, p95 = etapas[e].get("p50"), etapas[e].get("p95")
                linha[e] = {"n": etapas[e].get("n"), "p50_ms": p50, "p95_ms": p95,
                            "p95_sobre_orcamento": round(p95 / orcamento, 4) if orcamento and p95 is not None else None}
        saida["cameras"][nomes.get(int(cid), cid)] = linha
        print(nomes.get(int(cid), cid), json.dumps(linha, ensure_ascii=False))
    destino = RAIZ / "bench" / "results" / f"custo-prototipos-{datetime.now():%Y%m%d-%H%M%S}.json"
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[custo] {destino.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
