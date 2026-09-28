"""Avalia o pipeline de EPI POR PESSOA num conjunto anotado (Sprint 4).

Usa os componentes reais do app — ``YoloPPEDetector`` e
``PersonComplianceMatcher`` — na mesma composicao de ``CameraWorker._analyze_frame``
(detector de EPI + detector de pessoa opcional), sobre imagens com ground truth
no formato YOLO. Nao usa Flask, banco nem rede.

Uma execucao = uma configuracao de detector. As duas politicas de "missing"
(``ausencia`` e ``evidencia``) sao calculadas sobre as MESMAS deteccoes: o
modelo roda uma vez, o matcher roda duas. Assim a diferenca entre politicas e
so a regra, nunca ruido de inferencia.

Uso:

    python scripts/avaliar_dataset.py --config sprint3 --split test
    python scripts/avaliar_dataset.py --config vyra_neg --split test
    python scripts/avaliar_dataset.py --config cppe --modelo models/visionepi_cppe_n416.pt --split test

Saida: ``docs/avaliacao/<config>_<split>.json`` com as metricas e as
deteccoes por imagem (para analise de erro e para as evidencias).
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

import cv2

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.vision.avaliacao import (  # noqa: E402
    EPIS_AVALIADOS,
    Matriz,
    casar_pessoas,
    contar,
    ground_truth_por_pessoa,
    ler_rotulos_yolo,
)
from app.vision.person_compliance_matcher import PPE_KEYS, PersonComplianceMatcher  # noqa: E402
from app.vision.schemas import BoundingBox  # noqa: E402
from app.vision.yolo_ppe_detector import YoloPPEDetector  # noqa: E402

NOMES_CPPE = ["helmet", "gloves", "vest", "boots", "goggles", "none", "Person", "no_helmet", "no_goggle", "no_gloves", "no_boots"]

# Configuracoes de detector. `classes` e o filtro do ultralytics (None = todas).
CONFIGS = {
    # Producao ate a Sprint 3: .env.example (YOLO_CLASSES=0,1,2,3,5,11,12,13),
    # sem as classes negativas, + YOLOv8n COCO para pessoa.
    "sprint3": {"modelo": "models/vyra_ppe.pt", "classes": [0, 1, 2, 3, 5, 11, 12, 13], "pessoa": "models/yolov8n.pt"},
    # Mesmo Vyra, agora com as negativas (6 NO-Gloves, 7 NO-Goggles,
    # 8 NO-Hardhat, 9 NO-Mask, 10 NO-Safety Vest).
    "vyra_neg": {"modelo": "models/vyra_ppe.pt", "classes": [0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13], "pessoa": "models/yolov8n.pt"},
    # Modelo treinado no Construction-PPE: um peso so, com Person proprio.
    "cppe": {"modelo": "models/visionepi_cppe_n416.pt", "classes": None, "pessoa": None},
    # O mesmo treinado, mas com pessoa vinda do COCO — isola o efeito do
    # detector de pessoa.
    "cppe_coco": {"modelo": "models/visionepi_cppe_n416.pt", "classes": None, "pessoa": "models/yolov8n.pt"},
}


def _imagem_de(rotulo: Path, dir_imagens: Path) -> Path | None:
    for ext in (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"):
        candidato = dir_imagens / f"{rotulo.stem}{ext}"
        if candidato.exists():
            return candidato
    return None


def _ic95(valores: list[float]) -> list[float] | None:
    valores = sorted(v for v in valores if v is not None)
    if len(valores) < 20:
        return None
    return [round(valores[int(0.025 * len(valores))], 4), round(valores[int(0.975 * len(valores)) - 1], 4)]


def avaliar(args) -> dict:
    cfg = dict(CONFIGS[args.config])
    if args.modelo:
        cfg["modelo"] = args.modelo
    raiz_ds = Path(args.dataset)
    dir_rot = raiz_ds / "labels" / args.split
    dir_img = raiz_ds / "images" / args.split
    excluir = set(args.excluir.split(",")) if args.excluir else set()

    detector = YoloPPEDetector(
        model_path=str(RAIZ / cfg["modelo"]), confidence=args.conf, classes=cfg["classes"], require_person=False, imgsz=args.imgsz
    )
    detector_pessoa = None
    if cfg["pessoa"]:
        detector_pessoa = YoloPPEDetector(
            model_path=str(RAIZ / cfg["pessoa"]), confidence=args.conf, classes=[0], imgsz=args.imgsz
        )
    suportados = detector.supported_ppe_classes()
    avaliados = [epi for epi in EPIS_AVALIADOS if epi in suportados]
    tudo = dict.fromkeys(PPE_KEYS, True)
    matchers = {p: PersonComplianceMatcher(missing_policy=p) for p in ("ausencia", "evidencia")}

    rotulos = sorted(dir_rot.glob("*.txt"))
    if args.limite:
        rotulos = rotulos[: args.limite]

    # Aquecimento: a primeira inferencia paga carga de pesos e JIT.
    primeira = _imagem_de(rotulos[0], dir_img)
    if primeira is not None:
        img0 = cv2.imread(str(primeira))
        detector.detect(img0)
        if detector_pessoa:
            detector_pessoa.detect(img0)

    por_imagem = []
    latencias = []
    for rotulo in rotulos:
        caminho = _imagem_de(rotulo, dir_img)
        if caminho is None or caminho.name in excluir:
            continue
        img = cv2.imread(str(caminho))
        if img is None:
            continue
        altura, largura = img.shape[:2]
        gt = ground_truth_por_pessoa(ler_rotulos_yolo(rotulo, NOMES_CPPE, largura=largura, altura=altura))

        t0 = time.perf_counter()
        deteccoes = detector.detect(img)
        if detector_pessoa:
            # Com dois detectores, a pessoa vem SO do COCO — mesma regra do
            # CameraWorker com MULTI_PERSON_DETECTION=true (o Person do Vyra
            # nao generaliza, ver README).
            deteccoes = [d for d in deteccoes if d.label != "person"] + detector_pessoa.detect(img)
        latencias.append((time.perf_counter() - t0) * 1000)

        registro = {
            "imagem": caminho.name,
            "largura": largura,
            "altura": altura,
            "gt": [{"caixa": p.caixa.to_dict(), "status": p.status} for p in gt],
            "deteccoes": [d.to_dict() for d in deteccoes],
            "politicas": {},
        }
        for politica, matcher in matchers.items():
            pessoas = matcher.build(deteccoes, supported_ppe={k: k in suportados for k in PPE_KEYS}, enabled_ppe=tudo)
            registro["politicas"][politica] = [
                {"caixa": p["box"], "status": {epi: p["ppe"][epi]["status"] for epi in PPE_KEYS}} for p in pessoas
            ]
        por_imagem.append(registro)

    return {"config": args.config, "cfg": cfg, "split": args.split, "imgsz": args.imgsz, "conf": args.conf,
            "avaliados": avaliados, "latencia_ms": latencias, "por_imagem": por_imagem}


def metricas(bruto: dict, imagens: list[dict] | None = None, *, iou_minimo: float = 0.5) -> dict:
    imagens = bruto["por_imagem"] if imagens is None else imagens
    saida: dict = {"pessoas": {}, "politicas": {}}
    gt_total = sum(len(r["gt"]) for r in imagens)
    prev_total = sum(len(r["politicas"]["ausencia"]) for r in imagens)
    casadas = 0
    for politica in ("ausencia", "evidencia"):
        condicional = {epi: Matriz() for epi in bruto["avaliados"]}
        ponta = {epi: Matriz() for epi in bruto["avaliados"]}
        fantasmas = dict.fromkeys(bruto["avaliados"], 0)
        casadas = 0
        for r in imagens:
            gt_caixas = [BoundingBox(**p["caixa"]) for p in r["gt"]]
            prev = r["politicas"][politica]
            prev_caixas = [BoundingBox(**p["caixa"]) for p in prev]
            pares = casar_pessoas(gt_caixas, prev_caixas, iou_minimo=iou_minimo)
            casadas += len(pares)
            for i, pessoa_gt in enumerate(r["gt"]):
                j = pares.get(i)
                for epi in bruto["avaliados"]:
                    verdade = pessoa_gt["status"][epi]
                    if j is None:
                        # Pessoa nao detectada: nenhum alerta sobre ela.
                        contar(ponta[epi], verdade=verdade, alerta=False, exemplo=f"{r['imagem']}#{i}")
                        continue
                    alerta = prev[j]["status"][epi] == "missing"
                    contar(condicional[epi], verdade=verdade, alerta=alerta, exemplo=f"{r['imagem']}#{i}")
                    contar(ponta[epi], verdade=verdade, alerta=alerta, exemplo=f"{r['imagem']}#{i}")
            usados = set(pares.values())
            for j, p in enumerate(prev):
                if j in usados:
                    continue
                for epi in bruto["avaliados"]:
                    if p["status"][epi] == "missing":
                        fantasmas[epi] += 1
        saida["politicas"][politica] = {
            "condicional": {epi: m.to_dict() for epi, m in condicional.items()},
            "ponta_a_ponta": {epi: m.to_dict() for epi, m in ponta.items()},
            "alertas_em_pessoa_inexistente": fantasmas,
            "exemplos": {epi: m.exemplos for epi, m in condicional.items()},
        }
    saida["pessoas"] = {
        "anotadas": gt_total,
        "previstas": prev_total,
        "casadas": casadas,
        "revocacao": round(casadas / gt_total, 4) if gt_total else None,
        "precisao": round(casadas / prev_total, 4) if prev_total else None,
    }
    return saida


def cenas(imagens: list[dict], grupos: dict[str, list[str]]) -> list[list[dict]]:
    """Agrupa imagens por CENA: quadros da mesma sequencia viram uma unidade."""
    grupo_de = {nome: g for g, nomes in grupos.items() for nome in nomes}
    unidades: dict[str, list[dict]] = {}
    for r in imagens:
        unidades.setdefault(grupo_de.get(r["imagem"], r["imagem"]), []).append(r)
    return list(unidades.values())


def subconjuntos(imagens: list[dict], curadoria: dict | None) -> dict[str, list[dict]]:
    if not curadoria:
        return {"completo": imagens}
    grupos = curadoria["grupos"]
    nao_industrial = set(curadoria["nao_industrial"])
    maior = max(grupos, key=lambda g: len(grupos[g]))
    fora_maior = [r for r in imagens if r["imagem"] not in set(grupos[maior])]
    return {
        "completo": imagens,
        f"sem_{maior}": fora_maior,
        "uma_por_cena": [unidade[0] for unidade in cenas(imagens, grupos)],
        "industrial_uma_por_cena": [u[0] for u in cenas(imagens, grupos) if u[0]["imagem"] not in nao_industrial],
    }


def bootstrap(bruto: dict, n: int = 400, semente: int = 0, grupos: dict | None = None) -> dict:
    """IC 95% por reamostragem de CENAS (a unidade independente).

    Reamostrar imagens trataria 47 quadros da mesma pessoa no mesmo terraco
    como 47 evidencias independentes, e o intervalo sairia estreito demais.
    """
    rng = random.Random(semente)
    unidades = cenas(bruto["por_imagem"], grupos or {})
    acumulado: dict = {}
    for _ in range(n):
        amostra = [r for _ in unidades for r in unidades[rng.randrange(len(unidades))]]
        m = metricas(bruto, amostra)
        for politica, bloco in m["politicas"].items():
            for epi, mat in bloco["ponta_a_ponta"].items():
                for chave in ("precisao", "revocacao", "f1"):
                    acumulado.setdefault(politica, {}).setdefault(epi, {}).setdefault(chave, []).append(mat[chave])
    return {
        politica: {epi: {k: _ic95(v) for k, v in por_epi.items()} for epi, por_epi in bloco.items()}
        for politica, bloco in acumulado.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", choices=sorted(CONFIGS), required=True)
    parser.add_argument("--modelo", help="sobrescreve o peso de EPI da config")
    parser.add_argument("--dataset", default=str(RAIZ / "datasets" / "construction-ppe"))
    parser.add_argument("--split", default="test")
    parser.add_argument("--imgsz", type=int, default=416)
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--limite", type=int, default=0)
    parser.add_argument("--excluir", default="", help="nomes de imagem separados por virgula")
    parser.add_argument("--sufixo", default="")
    parser.add_argument("--saida", default=str(RAIZ / "docs" / "avaliacao"))
    parser.add_argument("--subconjuntos", default=str(RAIZ / "docs" / "avaliacao" / "subconjuntos_test.json"),
                        help="curadoria de cenas/grupos; vazio desliga")
    parser.add_argument("--reusar", action="store_true", help="recalcula a partir do _bruto.json, sem modelo")
    args = parser.parse_args()

    destino = Path(args.saida)
    nome = f"{args.config}_{args.split}_{args.imgsz}{args.sufixo}"
    if args.reusar:
        # Recalcula metricas sobre deteccoes ja gravadas, sem rodar modelo.
        bruto = json.loads((destino / f"{nome}_bruto.json").read_text(encoding="utf-8"))
    else:
        bruto = avaliar(args)
    curadoria = json.loads(Path(args.subconjuntos).read_text(encoding="utf-8")) if args.subconjuntos else None
    grupos = curadoria["grupos"] if curadoria else {}
    resumo = metricas(bruto)
    resumo["ic95_ponta_a_ponta"] = bootstrap(bruto, grupos=grupos)
    resumo["subconjuntos"] = {}
    for rotulo, imagens in subconjuntos(bruto["por_imagem"], curadoria).items():
        m = metricas(bruto, imagens)
        resumo["subconjuntos"][rotulo] = {
            "imagens": len(imagens),
            "pessoas": m["pessoas"],
            "ponta_a_ponta": {pol: bloco["ponta_a_ponta"] for pol, bloco in m["politicas"].items()},
        }
    lat = bruto["latencia_ms"]
    # Latencia aqui e da inferencia por IMAGEM (detector de EPI + de pessoa),
    # medida junto com a avaliacao. Com outro processo disputando a CPU ela
    # nao vale como bench: o numero de FPS oficial e o de bench_pipeline.py.
    resumo["latencia_ms"] = {
        "p50": round(statistics.median(lat), 1),
        "p90": round(sorted(lat)[int(0.9 * len(lat)) - 1], 1),
        "n": len(lat),
    } if lat else None
    resumo.update({k: bruto[k] for k in ("config", "cfg", "split", "imgsz", "conf", "avaliados")})
    resumo["imagens"] = len(bruto["por_imagem"])
    resumo["excluidas"] = args.excluir.split(",") if args.excluir else []

    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"{nome}.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    (destino / f"{nome}_bruto.json").write_text(json.dumps(bruto, ensure_ascii=False), encoding="utf-8")

    print(f"== {nome}: {resumo['imagens']} imagens, pessoas {resumo['pessoas']}, latencia {resumo['latencia_ms']}")
    for politica, bloco in resumo["politicas"].items():
        print(f"-- politica {politica} (ponta a ponta)")
        for epi, m in bloco["ponta_a_ponta"].items():
            print(
                f"   {epi:12s} P={m['precisao']} R={m['revocacao']} F1={m['f1']} "
                f"vp={m['vp']} fp={m['fp']} fn={m['fn']} vn={m['vn']} semverdade+alerta={m['sem_verdade_com_alerta']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
