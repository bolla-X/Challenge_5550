"""Métricas de portão sob saturação (ADENDO 1 do MISSAO.md): CPU por trabalho feito.

    python scripts/resumo_cpu.py bench/results/*-gate5-r*.json --base base --novo pr1

Tempo de relógio numa máquina saturada mede a disputa, não o VisionEPI. CPU
gasta pelo PROCESSO do servidor por unidade de trabalho concluída é bem menos
sensível a isso:

- `cpu_ms_por_analise`: CPU-ms do servidor na janela / análises concluídas;
- `cpu_ms_por_quadro`: CPU-ms do servidor / quadros publicados;
- `encodes_por_quadro`: JPEGs codificados / quadros publicados (determinístico).

CPU-ms vem das amostras de 1 s do psutil (`processo.amostras[].cpu_pct`, em %
de um núcleo): soma(cpu_pct) x 10 ms. Análises e quadros vêm das taxas do
`/api/diagnostics/pipeline` na mesma janela.

Regra (item 4 do adendo): a métrica do `--novo` só REPROVA se a mediana for
pior que a da `--base` em mais de 10 % E as repetições pareadas (mesmo arquivo)
concordarem todas na direção "pior".
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

METRICAS = ("cpu_ms_por_analise", "cpu_ms_por_quadro", "encodes_por_quadro")


def metricas(r: dict[str, Any]) -> dict[str, float | None]:
    amostras = r["processo"]["amostras"][1:]
    janela = float(r.get("duracao_s") or 60.0)
    # Preferência: delta de cpu_times do servidor na janela (exato); senão, as amostras de 1 s.
    cpu_ms = r.get("cpu_ms_servidor_janela")
    if cpu_ms is None:
        cpu_ms = sum(a["cpu_pct"] for a in amostras) * 10.0 * (janela / max(1, len(amostras)))
    cams = list(r.get("cameras", {}).values())
    analises = sum((c.get("fps_analise") or 0.0) for c in cams) * janela
    quadros = sum((c.get("fps_publicado") or 0.0) for c in cams) * janela
    encodes = sum(((c.get("etapas") or {}).get("encode") or {}).get("n", 0) for c in cams)
    return {
        "cpu_ms_por_analise": cpu_ms / analises if analises else None,
        "cpu_ms_por_quadro": cpu_ms / quadros if quadros else None,
        "encodes_por_quadro": encodes / quadros if quadros else None,
        "analises": analises,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivos", nargs="+")
    ap.add_argument("--base", default="base")
    ap.add_argument("--novo", default="pr1")
    args = ap.parse_args()

    # (cenário, árvore) -> {arquivo: métricas}
    dados: dict[tuple[str, int, str], dict[str, dict[str, float | None]]] = {}
    for caminho in args.arquivos:
        for r in json.loads(Path(caminho).read_text(encoding="utf-8"))["resultados"]:
            partes = r["rotulo"].split("-")
            arvore = partes[2] if len(partes) > 3 else "-"
            dados.setdefault((r["perfil"], len(r["fixtures"]), arvore), {})[caminho] = metricas(r)

    print("| perfil | câm. | árvore | análises/rodada | CPU-ms por análise | CPU-ms por quadro | encodes por quadro |")
    print("|---|---|---|---|---|---|---|")
    for (perfil, cams, arvore), por_arquivo in sorted(dados.items()):
        linha = [perfil, str(cams), arvore,
                 ", ".join(f"{m['analises']:.0f}" for m in por_arquivo.values())]
        for chave in METRICAS:
            vals = [m[chave] for m in por_arquivo.values() if m[chave] is not None]
            med = statistics.median(vals) if vals else None
            linha.append(f"**{med:,.1f}** [{', '.join(f'{v:,.1f}' for v in vals)}]" if med is not None else "—")
        print("| " + " | ".join(linha) + " |")

    print()
    print(f"Regra: {args.novo} reprova se mediana > {args.base} em mais de 10 % e todas as repetições pareadas concordarem.")
    cenarios = sorted({(p, c) for p, c, _ in dados})
    for perfil, cams in cenarios:
        base = dados.get((perfil, cams, args.base), {})
        novo = dados.get((perfil, cams, args.novo), {})
        pares = [arq for arq in novo if arq in base]
        for chave in METRICAS:
            razoes = [novo[a][chave] / base[a][chave] for a in pares
                      if novo[a][chave] is not None and base[a][chave] not in (None, 0)]
            if not razoes:
                continue
            mb = statistics.median([base[a][chave] for a in pares if base[a][chave] is not None])
            mn = statistics.median([novo[a][chave] for a in pares if novo[a][chave] is not None])
            pior = mn > mb * 1.10 and all(r > 1.0 for r in razoes)
            veredito = "REPROVA" if pior else "passa"
            print(f"- {perfil} {cams} câm. {chave}: novo/base por repetição = "
                  f"{', '.join(f'{r:.2f}' for r in razoes)}; medianas {mn:,.1f} vs {mb:,.1f} → **{veredito}**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
