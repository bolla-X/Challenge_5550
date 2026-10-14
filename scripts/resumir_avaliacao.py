"""Gera docs/avaliacao/RESUMO.md a partir dos JSONs de avaliacao.

Nenhum numero do relatorio e digitado a mao: sai daqui.

    python scripts/resumir_avaliacao.py
"""

from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR = RAIZ / "docs" / "avaliacao"
NOME = {"sprint3": "Sprint 3 (Vyra m + COCO n)", "vyra_neg": "Vyra + classes NO-*", "cppe": "Sprint 4 (VisionEPI n, 1 modelo)",
        "cppe_coco": "Sprint 4 + COCO p/ pessoa"}
EPI = {"helmet": "capacete", "vest": "colete", "gloves": "luvas", "glasses": "óculos", "safety_shoe": "calçado"}


def f(v, casas=2):
    return "—" if v is None else f"{v:.{casas}f}".replace(".", ",")


def ic(par):
    return "—" if not par else f"[{f(par[0])}; {f(par[1])}]"


def carregar(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def main() -> int:
    linhas: list[str] = ["# Resumo da avaliação por pessoa (gerado)", "",
                         "Gerado por `scripts/resumir_avaliacao.py` a partir de `docs/avaliacao/*.json`. "
                         "Positivo = pessoa SEM o EPI (o que gera alerta). P = precisão, R = revocação.", ""]

    # 1. Selecao na validacao
    linhas += ["## 1. Seleção na validação (143 imagens) — o teste não participa", "",
               "| configuração | conf | pessoas R | política | capacete P | capacete R | capacete F1 "
               "| colete P | colete R | colete F1 | F1 médio | ms/img |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for arq in sorted((DIR / "val").glob("*_val_416*.json")):
        if arq.name.endswith("_bruto.json"):
            continue
        r = carregar(arq)
        for pol in ("ausencia", "evidencia"):
            h = r["politicas"][pol]["ponta_a_ponta"]["helmet"]
            v = r["politicas"][pol]["ponta_a_ponta"]["vest"]
            medio = None if h["f1"] is None or v["f1"] is None else (h["f1"] + v["f1"]) / 2
            lat = r["latencia_ms"]["p50"] if r.get("latencia_ms") else None
            linhas.append(
                f"| {NOME.get(r['config'], r['config'])} | {f(r['conf'])} | {f(r['pessoas']['revocacao'])} | {pol} | "
                f"{f(h['precisao'])} | {f(h['revocacao'])} | {f(h['f1'])} | {f(v['precisao'])} | {f(v['revocacao'])} | "
                f"{f(v['f1'])} | **{f(medio)}** | {f(lat, 0)} |"
            )
    linhas.append("")

    # 2. Teste
    linhas += ["## 2. Teste (141 imagens, 236 pessoas) — ponta a ponta, IC 95% por reamostragem de cenas", ""]
    for cfg in ("sprint3", "vyra_neg", "cppe", "cppe_coco"):
        arq = DIR / f"{cfg}_test_416.json"
        if not arq.exists():
            continue
        r = carregar(arq)
        lat = r["latencia_ms"]["p50"] if r.get("latencia_ms") else None
        linhas += [f"### {NOME[cfg]} — pessoas: R {f(r['pessoas']['revocacao'])} · P {f(r['pessoas']['precisao'])} · "
                   f"{f(lat, 0)} ms/imagem", "",
                   "| política | EPI | P | R | F1 | VP | FP | FN | VN | IC95 P | IC95 R | alerta em pessoa não anotada |",
                   "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for pol in ("ausencia", "evidencia"):
            for epi in r["avaliados"]:
                m = r["politicas"][pol]["ponta_a_ponta"][epi]
                c = r["ic95_ponta_a_ponta"][pol][epi]
                linhas.append(
                    f"| {pol} | {EPI[epi]} | {f(m['precisao'])} | {f(m['revocacao'])} | {f(m['f1'])} | {m['vp']} | {m['fp']} | "
                    f"{m['fn']} | {m['vn']} | {ic(c['precisao'])} | {ic(c['revocacao'])} | "
                    f"{r['politicas'][pol]['alertas_em_pessoa_inexistente'][epi]} |"
                )
        linhas.append("")

    # 3. Subconjuntos
    linhas += ["## 3. Subconjuntos do teste (política ausência)", "",
               "| configuração | subconjunto | imagens | pessoas | capacete: alertas falsos / pessoas de capacete "
               "| capacete: violações achadas | "
               "colete: alertas falsos / pessoas de colete | colete: violações achadas |",
               "|---|---|---|---|---|---|---|---|"]
    for cfg in ("sprint3", "cppe"):
        r = carregar(DIR / f"{cfg}_test_416.json")
        for sub, b in r["subconjuntos"].items():
            h = b["ponta_a_ponta"]["ausencia"]["helmet"]
            v = b["ponta_a_ponta"]["ausencia"]["vest"]
            linhas.append(
                f"| {NOME[cfg]} | {sub} | {b['imagens']} | {b['pessoas']['anotadas']} | {h['fp']} / {h['suporte_presente']} | "
                f"{h['vp']} / {h['suporte_ausente']} | {v['fp']} / {v['suporte_presente']} | {v['vp']} / {v['suporte_ausente']} |"
            )
    linhas.append("")
    (DIR / "RESUMO.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"{DIR / 'RESUMO.md'}: {len(linhas)} linhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
