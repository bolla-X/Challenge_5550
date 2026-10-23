"""Grava as cartelas do vídeo (docs/pitch/storyboard.md) com o Playwright.

    python scripts/video/gravar_cartelas.py [--saida bench/runtime/video]

Cada cena de `scripts/video/cartelas.html` vira um `.webm` 1920x1080 em
`<saida>/cartelas/<n>-<cena>.webm`, com a duração do storyboard (mais 1 s de
folga, cortada na montagem). O vídeo do Playwright só é gravado ao fechar o
contexto (https://playwright.dev/python/docs/videos), por isso um contexto por cena.
"""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PAGINA = (RAIZ / "scripts" / "video" / "cartelas.html").as_uri()

# (ordem, âncora, segundos) — os mesmos do storyboard.
CARTELAS = [
    (1, "abertura", 15),
    (2, "problema", 25),
    (3, "solucao", 30),
    (5, "impacto", 20),
    (6, "evolucao", 25),
    (7, "encerramento", 10),
]
TAMANHO = {"width": 1920, "height": 1080}


def gravar(saida: Path, so: set[str] | None = None) -> list[Path]:
    from playwright.sync_api import sync_playwright

    pasta = saida / "cartelas"
    pasta.mkdir(parents=True, exist_ok=True)
    gerados: list[Path] = []
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=True)
        try:
            for ordem, cena, segundos in CARTELAS:
                if so and cena not in so:
                    continue
                temporaria = pasta / f"_tmp-{cena}"
                shutil.rmtree(temporaria, ignore_errors=True)
                contexto = navegador.new_context(viewport=TAMANHO, record_video_dir=str(temporaria), record_video_size=TAMANHO)
                pagina = contexto.new_page()
                pagina.goto(f"{PAGINA}#{cena}")
                pagina.wait_for_function("document.fonts.status === 'loaded'")
                time.sleep(segundos + 1)
                video = pagina.video
                contexto.close()
                destino = pasta / f"{ordem}-{cena}.webm"
                Path(video.path()).replace(destino)
                shutil.rmtree(temporaria, ignore_errors=True)
                gerados.append(destino)
                print(f"[cartelas] {destino.relative_to(RAIZ)} ({segundos} s)", flush=True)
        finally:
            navegador.close()
    return gerados


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--saida", type=Path, default=RAIZ / "bench" / "runtime" / "video")
    ap.add_argument("--so", nargs="*", help="grava só estas cenas (âncoras)")
    args = ap.parse_args()
    gravar(args.saida.resolve(), set(args.so) if args.so else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
