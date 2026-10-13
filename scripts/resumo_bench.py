"""Tabela markdown das métricas do portão a partir de rodadas do `scripts/bench.py`.

    python scripts/resumo_bench.py bench/results/*-dec1cam-r*.json

Agrupa por (perfil, câmeras, árvore) e mostra a MEDIANA das repetições, com
os valores individuais entre colchetes — o fundo da máquina de medição varia
de rodada para rodada, e esconder a dispersão seria vender precisão que não há.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any


def _mediana(valores: list[float]) -> float | None:
    valores = [v for v in valores if v is not None]
    return statistics.median(valores) if valores else None


def _fmt(v: float | None, casas: int = 0) -> str:
    if v is None:
        return "—"
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def metricas(r: dict[str, Any]) -> dict[str, float | None]:
    cams = list(r.get("cameras", {}).values())
    fps = [c.get("fps_analise") for c in cams if c.get("fps_analise") is not None]
    p50 = [(c.get("idade_analise_ms") or {}).get("p50") for c in cams]
    p95 = [(c.get("idade_analise_ms") or {}).get("p95") for c in cams]
    primeira = int(next(iter(r.get("cameras", {"0": None}))))
    lat = next((v for v in (r.get("latencia_alerta") or {}).values() if v.get("camera_id") == primeira), None)
    return {
        "fps_analise": statistics.mean(fps) if fps else None,
        "idade_p50": max((v for v in p50 if v is not None), default=None),
        "idade_p95": max((v for v in p95 if v is not None), default=None),
        "alerta_s": (lat["latencia_ms"] / 1000.0) if lat and lat.get("latencia_ms") is not None else None,
        "sem_alerta_s": lat.get("sem_alerta_em_s") if lat else None,
        "fundo": r["processo"].get("carga_de_fundo_pct_media"),
        "cpu": r["processo"].get("cpu_pct_media"),
    }


def main(caminhos: list[str]) -> int:
    grupos: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
    for caminho in caminhos:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        for r in dados["resultados"]:
            partes = r["rotulo"].split("-")
            arvore = partes[2] if len(partes) > 3 else "-"
            grupos.setdefault((r["perfil"], len(r["fixtures"]), arvore), []).append(metricas(r))
    print("| perfil | câm. | árvore | n | FPS de análise/câm. | idade da análise p50 (ms) | idade p95 (ms) "
          "| latência de alerta (s) | fundo (% de 1 núcleo) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for (perfil, cams, arvore), ms in sorted(grupos.items()):
        def col(chave, casas=0, ms=ms):
            vals = [m[chave] for m in ms]
            individuais = ", ".join(_fmt(v, casas) for v in vals)
            return f"**{_fmt(_mediana(vals), casas)}** [{individuais}]"
        alerta = col("alerta_s", 1)
        sem = [m["sem_alerta_s"] for m in ms if m["sem_alerta_s"] is not None]
        if sem:
            alerta += f" ({len(sem)}× sem alerta em ≥{min(sem):.0f} s)"
        print(f"| {perfil} | {cams} | {arvore} | {len(ms)} | {col('fps_analise', 2)} | {col('idade_p50')} | {col('idade_p95')} | "
              f"{alerta} | {_fmt(_mediana([m['fundo'] for m in ms]))} |")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
