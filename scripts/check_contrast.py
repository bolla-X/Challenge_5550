"""Contraste WCAG 2.1 dos tokens de tokens.css, par a par, nos dois temas.

Confere texto sobre fundo sólido (canvas, surface, sunken), limite de
controle sobre canvas (3:1) e on-accent sobre accent. Depois compõe cada
fundo rgba (tint-danger, overlay, scrim) sobre os fundos reais e confere o
texto que de fato assenta nele. Sai com 1 se qualquer par ficar abaixo do
mínimo. Se falhar, corrija o token, não o script.
"""

import pathlib
import re
import sys

CSS = pathlib.Path("frontend/src/styles/tokens.css").read_text(encoding="utf-8")
HEX = r"--([\w-]+)\s*:\s*(#[0-9A-Fa-f]{6})"
RGBA = r"--([\w-]+)\s*:\s*rgba\((\d+),\s*(\d+),\s*(\d+),\s*([.\d]+)\)"

TEXTO = ["text", "text-2", "text-3", "accent", "danger", "stop", "ok"]
# Fundos rgba e o texto que de fato assenta em cada um. Sobre a linha tingida
# fica --text (título), --text-2 (contexto e horário) e --danger (ponto, chip).
# O overlay flutua sobre vídeo, então também sobre preto e branco puros.
COMPOSTOS = [
    ("tint-danger", ["canvas", "surface"], ["text", "text-2", "danger"]),
    ("overlay", ["canvas", "surface", "#000000", "#FFFFFF"], ["on-overlay"]),
    ("scrim", ["canvas", "surface"], ["text"]),
]


def blocos(css: str) -> tuple[str, str]:
    """Texto do bloco claro (antes do @media) e do bloco escuro forçado."""
    return css.split("@media")[0], css.split(':root[data-theme="dark"]')[1]


def cores_hex(bloco: str) -> dict[str, str]:
    return dict(re.findall(HEX, bloco))


def cores_rgba(bloco: str) -> dict[str, tuple[int, int, int, float]]:
    return {n: (int(r), int(g), int(b), float(a)) for n, r, g, b, a in re.findall(RGBA, bloco)}


def linear(v: int) -> float:
    c = v / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminancia(hex_: str) -> float:
    h = hex_.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)


def razao(a: str, b: str) -> float:
    la, lb = luminancia(a), luminancia(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def compor(rgba: tuple[int, int, int, float], fundo_hex: str) -> str:
    """Cor rgba assentada sobre um fundo opaco: a*fg + (1-a)*bg por canal."""
    r, g, b, a = rgba
    f = fundo_hex.lstrip("#")
    br, bg, bb = (int(f[i : i + 2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % (round(a * r + (1 - a) * br), round(a * g + (1 - a) * bg), round(a * b + (1 - a) * bb))


def main() -> int:
    claro, escuro = blocos(CSS)
    claro_hex, escuro_hex = cores_hex(claro), cores_hex(escuro)
    claro_rgba, escuro_rgba = cores_rgba(claro), cores_rgba(escuro)
    falhas = 0

    def conferir(rotulo: str, r: float, minimo: float) -> None:
        nonlocal falhas
        ok = r >= minimo
        falhas += 0 if ok else 1
        print(f"{rotulo} {r:5.2f}:1 {'ok' if ok else 'FALHA'}")

    temas = (("CLARO", claro_hex, claro_rgba), ("ESCURO", escuro_hex, {**claro_rgba, **escuro_rgba}))

    for nome, p, rgba in temas:
        # --overlay e --on-overlay só existem no bloco claro.
        hexs = {**claro_hex, **p}
        for fundo_rgba, bases, textos in COMPOSTOS:
            for base in bases:
                base_hex = base if base.startswith("#") else hexs[base]
                composto = compor(rgba[fundo_rgba], base_hex)
                for fg in textos:
                    conferir(f"{nome:6} {fg:>10} sobre {fundo_rgba}+{base:<8} ({composto})", razao(hexs[fg], composto), 4.5)

    for nome, p, _ in temas:
        for fundo in ("canvas", "surface", "sunken"):
            for fg in TEXTO:
                conferir(f"{nome:6} {fg:>8} sobre {fundo:<8}", razao(p[fg], p[fundo]), 4.5)
        conferir(f"{nome:6} control-line sobre canvas", razao(p["control-line"], p["canvas"]), 3.0)
        print("       (alvo 3:1)")
        conferir(f"{nome:6} on-accent sobre accent   ", razao(p["on-accent"], p["accent"]), 4.5)

    print("falhas:", falhas)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
