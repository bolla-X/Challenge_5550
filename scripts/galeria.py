"""Galeria versionada: capturas finais em WebP ≤ 250 KB (MISSÃO 2, Fase C, item 8).

    python scripts/galeria.py --rodada r2 [--antes r0]

Lê `bench/runtime/capturas/<rodada>/<tamanho>-<tema>/*.png` (de
`e2e/capturas_de_tela.py`) e grava `docs/NEXT2026/galeria/<tamanho>-<tema>/<tela>.webp`,
baixando a qualidade (e, se preciso, a escala) até caber em 250 KB. Com
`--antes`, grava também `antes-depois/<tela>.webp`: a mesma tela, antes à
esquerda e depois à direita (1920×1080, claro), para as telas que mais mudaram.
O `index.md` da galeria é escrito à mão (tem as notas da revisão).
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
CAPTURAS = RAIZ / "bench" / "runtime" / "capturas"
GALERIA = RAIZ / "docs" / "NEXT2026" / "galeria"
TETO = 250 * 1024


def webp_ate_o_teto(imagem: Image.Image, destino: Path) -> int:
    """Grava em WebP com a maior qualidade que cabe no teto; reduz a escala se nem q=40 couber."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    im = imagem.convert("RGB")
    while True:
        for qualidade in (88, 80, 72, 64, 56, 48, 40):
            memoria = io.BytesIO()
            im.save(memoria, "WEBP", quality=qualidade, method=6)
            if memoria.tell() <= TETO:
                destino.write_bytes(memoria.getvalue())
                return memoria.tell()
        im = im.resize((int(im.width * 0.85), int(im.height * 0.85)), Image.LANCZOS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rodada", required=True)
    ap.add_argument("--antes", default="", help="rodada de capturas do código anterior ao PR6")
    ap.add_argument("--telas-antes-depois", default="02-supervisor-inicio,07-foco-alerta-critico,16-tv,14-liga,13-auditoria,17-portal")
    ap.add_argument("--variacao", default="1920x1080-claro",
                    help="tamanho-tema do antes/depois; fora do padrão, o arquivo leva o sufixo (ex.: 55-produto-390x844-claro)")
    ap.add_argument("--so-antes-depois", action="store_true", help="não regrava a galeria, só o antes/depois")
    args = ap.parse_args()
    origem = CAPTURAS / args.rodada
    total = 0
    pastas = [] if args.so_antes_depois else sorted(p for p in origem.iterdir() if p.is_dir() and p.name != "folhas")
    for pasta in pastas:
        for png in sorted(pasta.glob("*.png")):
            tamanho = webp_ate_o_teto(Image.open(png), GALERIA / pasta.name / f"{png.stem}.webp")
            total += 1
            print(f"{pasta.name}/{png.stem}.webp {tamanho // 1024} KB")
    if args.antes:
        for tela in [t.strip() for t in args.telas_antes_depois.split(",") if t.strip()]:
            antes = CAPTURAS / args.antes / args.variacao / f"{tela}.png"
            depois = origem / args.variacao / f"{tela}.png"
            nome = tela if args.variacao == "1920x1080-claro" else f"{tela}-{args.variacao}"
            if not (antes.exists() and depois.exists()):
                print(f"antes-depois/{tela}: falta captura")
                continue
            a, d = Image.open(antes).convert("RGB"), Image.open(depois).convert("RGB")
            lado = Image.new("RGB", (a.width + d.width + 24, max(a.height, d.height)), (128, 128, 128))
            lado.paste(a, (0, 0))
            lado.paste(d, (a.width + 24, 0))
            lado.thumbnail((2400, 2400))
            tamanho = webp_ate_o_teto(lado, GALERIA / "antes-depois" / f"{nome}.webp")
            print(f"antes-depois/{nome}.webp {tamanho // 1024} KB")
    print(f"{total} capturas na galeria")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
