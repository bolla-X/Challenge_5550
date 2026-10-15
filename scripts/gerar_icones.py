"""Gera os ícones do PWA (X10) a partir do mesmo desenho do favicon.svg.

    python scripts/gerar_icones.py

Desenho original do projeto (moldura de câmera + ponto de estado), sem
recurso de terceiros. Desenha 4x maior e reduz (antisserrilhado), com Pillow,
que já vem com o ultralytics. Saída em frontend/public/icons/.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "frontend" / "public" / "icons"
FUNDO = (26, 26, 28)
TRACO = (255, 255, 255)
PONTO = (175, 70, 6)  # --danger do tema claro


def desenhar(lado: int, *, mascaravel: bool) -> Image.Image:
    s = 4
    n = lado * s
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if mascaravel:
        d.rectangle([0, 0, n, n], fill=FUNDO)  # sangra até a borda; o SO recorta
        escala = 0.62  # conteúdo dentro da zona segura (80 % central)
    else:
        d.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * 9 / 32), fill=FUNDO)
        escala = 1.0
    u = n / 32 * escala
    off = (n - 32 * u) / 2
    x0, y0, x1, y1 = off + 9 * u, off + 10.5 * u, off + 23 * u, off + 21.5 * u
    d.rounded_rectangle([x0, y0, x1, y1], radius=int(3 * u), outline=TRACO, width=max(2, int(1.8 * u)))
    r = 2.6 * u
    d.ellipse([x0 - r, y0 - r, x0 + r, y0 + r], fill=PONTO)
    return img.resize((lado, lado), Image.LANCZOS)


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    for lado in (192, 512):
        desenhar(lado, mascaravel=False).save(DESTINO / f"icone-{lado}.png", optimize=True)
    desenhar(512, mascaravel=True).save(DESTINO / "icone-mascaravel-512.png", optimize=True)
    desenhar(180, mascaravel=True).convert("RGB").save(DESTINO / "apple-touch-icon.png", optimize=True)
    print(f"ícones em {DESTINO.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
