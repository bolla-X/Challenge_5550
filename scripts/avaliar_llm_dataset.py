"""Mede a camada LLM no MESMO conjunto anotado da avaliacao do YOLO (Sprint 4).

Por que existe: a Sprint 3 mediu o Gemini em 3 cenas, e o proprio relatorio diz
que 3 cenas sustentam existencia, nao acuracia. Este script roda o prompt v2
sobre uma cena por grupo do conjunto de teste (``uma_por_cena``, 81 imagens) e
compara, POR IMAGEM, tres regras de alerta:

- ``yolo``: so o detector, politica "evidencia";
- ``llm``: so o Gemini;
- ``yolo_ou_llm_nos_nao_verificados``: o detector decide onde tem evidencia, e
  o LLM so desempata onde o detector ficou em "nao verificado".

Cada resposta do Gemini e congelada em ``tests/goldens/sprint4/`` (mesmo
formato dos goldens da Sprint 3, sem a chave). Rodar de novo PULA o que ja foi
gravado — o free tier devolve 503 em pico, e o remedio e repetir o comando.

    python scripts/avaliar_llm_dataset.py --yolo docs/avaliacao/cppe_test_416_bruto.json
    python scripts/avaliar_llm_dataset.py --yolo ... --so-metricas   # sem rede

Sem ``GEMINI_API_KEY`` no .env o script avisa e calcula so o que ja existe.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.llm import AnalisadorDeRisco, ProvedorGemini, carregar_prompt  # noqa: E402
from app.vision.avaliacao import Matriz, alerta_combinado, contar, verdade_por_imagem  # noqa: E402
from scripts.avaliar_dataset import cenas  # noqa: E402

DIR_GOLDENS = RAIZ / "tests" / "goldens" / "sprint4"
REGRAS = ("yolo", "llm", "yolo_ou_llm_nos_nao_verificados")


def _jpeg(caminho: Path, lado_maior: int = 1280) -> bytes:
    img = cv2.imread(str(caminho))
    h, w = img.shape[:2]
    escala = min(1.0, lado_maior / max(h, w))
    if escala < 1.0:
        img = cv2.resize(img, (int(w * escala), int(h * escala)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes()


def gravar(nome: str, caminho: Path, provedor: ProvedorGemini, versao: str) -> None:
    destino = DIR_GOLDENS / f"{Path(nome).stem}_{versao}.json"
    if destino.exists():
        return
    imagem = _jpeg(caminho)
    inicio = time.perf_counter()
    try:
        crua = provedor.analisar(imagem, carregar_prompt(versao))
    except Exception as exc:  # noqa: BLE001
        print(f"  [FALHOU] {nome}: {type(exc).__name__}: {exc}")
        return
    analise = AnalisadorDeRisco(provedor=provedor).validar(crua)
    registro = {
        "cena": nome,
        "versao": versao,
        "modelo": provedor.modelo,
        "gravado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "latencia_ms": round((time.perf_counter() - inicio) * 1000.0, 1),
        "bytes_imagem": len(imagem),
        "resposta_crua": crua,
        "analise_validada": analise.model_dump() if analise else None,
    }
    DIR_GOLDENS.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [ok] {destino.name}: {registro['latencia_ms']:.0f} ms, {'valida' if analise else 'REJEITADA'}")


def metricas(bruto: dict, imagens: list[dict], versao: str) -> dict:
    epis = [e for e in bruto["avaliados"] if e in ("helmet", "vest", "gloves", "glasses")]
    matrizes = {regra: {epi: Matriz() for epi in epis} for regra in REGRAS}
    respondidas = 0
    for r in imagens:
        golden = DIR_GOLDENS / f"{Path(r['imagem']).stem}_{versao}.json"
        if not golden.exists():
            continue
        dados = json.loads(golden.read_text(encoding="utf-8"))
        analise = dados.get("analise_validada")
        llm = set(analise["epis_ausentes"]) if analise else None
        respondidas += 1
        pessoas_gt = [p["status"] for p in r["gt"]]
        for epi in epis:
            verdade = verdade_por_imagem(pessoas_gt, epi)
            status_yolo = [p["status"][epi] for p in r["politicas"]["evidencia"]]
            for regra in REGRAS:
                contar(matrizes[regra][epi], verdade=verdade, alerta=alerta_combinado(status_yolo, llm, epi, regra=regra),
                       exemplo=r["imagem"])
    return {
        "imagens_com_resposta": respondidas,
        "regras": {regra: {epi: m.to_dict() for epi, m in por_epi.items()} for regra, por_epi in matrizes.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--yolo", required=True, help="_bruto.json de scripts/avaliar_dataset.py")
    parser.add_argument("--dataset", default=str(RAIZ / "datasets" / "construction-ppe"))
    parser.add_argument("--subconjuntos", default=str(RAIZ / "docs" / "avaliacao" / "subconjuntos_test.json"))
    parser.add_argument("--versao", default="v2")
    parser.add_argument("--intervalo", type=float, default=7.0, help="segundos entre chamadas (free tier: ~10 RPM)")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--limite", type=int, default=0)
    parser.add_argument("--so-metricas", action="store_true")
    args = parser.parse_args()

    bruto = json.loads(Path(args.yolo).read_text(encoding="utf-8"))
    curadoria = json.loads(Path(args.subconjuntos).read_text(encoding="utf-8"))
    alvo = [u[0] for u in cenas(bruto["por_imagem"], curadoria["grupos"])]
    if args.limite:
        alvo = alvo[: args.limite]
    dir_img = Path(args.dataset) / "images" / bruto["split"]

    if not args.so_metricas:
        provedor = ProvedorGemini(timeout_s=args.timeout)
        if not provedor.configurado:
            print("GEMINI_API_KEY ausente: calculando so sobre goldens ja gravados.", file=sys.stderr)
        else:
            print(f"modelo {provedor.modelo}, prompt {args.versao}, {len(alvo)} imagens")
            for i, r in enumerate(alvo, 1):
                if (DIR_GOLDENS / f"{Path(r['imagem']).stem}_{args.versao}.json").exists():
                    continue
                print(f"[{i}/{len(alvo)}] {r['imagem']}")
                gravar(r["imagem"], dir_img / r["imagem"], provedor, args.versao)
                time.sleep(args.intervalo)

    resultado = metricas(bruto, alvo, args.versao)
    resultado.update({"yolo": Path(args.yolo).name, "versao": args.versao, "alvo": len(alvo)})
    saida = RAIZ / "docs" / "avaliacao" / f"llm_{args.versao}_{Path(args.yolo).stem.replace('_bruto', '')}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{resultado['imagens_com_resposta']} de {len(alvo)} imagens com resposta do LLM -> {saida.relative_to(RAIZ)}")
    for regra, por_epi in resultado["regras"].items():
        print(f"-- {regra}")
        for epi, m in por_epi.items():
            print(f"   {epi:8s} P={m['precisao']} R={m['revocacao']} vp={m['vp']} fp={m['fp']} fn={m['fn']} vn={m['vn']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
