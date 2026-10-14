"""Vídeo de backup da demo: o Modo Apresentação (`/palco`) percorrendo todas as cenas.

    python e2e/video_do_palco.py                 # bench/runtime/video-palco/

Sobe a demo (`run.py --demo`, sem webcam, como `e2e/capturas_de_tela.py`), grava
o navegador em 1920×1080 com o Playwright e avança as cenas pelo teclado,
dando a cada uma o tempo que ela precisa (a da queda espera o alerta ao vivo).
Converte com o ffmpeg em MP4 (H.264) para o plano B do DEMO.md e em GIF curto
para o README. Sem ffmpeg, fica o WebM do Playwright (e o motivo no terminal).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from capturas_de_tela import ServidorDemo  # noqa: E402

from conftest import entrar  # noqa: E402

DESTINO = RAIZ / "bench" / "runtime" / "video-palco"
# Segundos em cada cena (chave do roteiro em app/services/palco.py). A queda
# espera o alerta ao vivo (até 60 s) e mais um pouco para o replay entrar.
TEMPO_DA_CENA = {"abertura": 7, "portal": 14, "enganar": 9, "raiox": 9, "gemeo": 12, "queda": 8, "incidente": 10,
                 "custodia": 9, "simulador": 9, "liga": 8, "retrospectiva": 12, "encerramento": 6}


def gravar(servidor: ServidorDemo, pasta: Path) -> Path:
    from playwright.sync_api import sync_playwright

    pasta.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=True, args=["--use-angle=d3d11", "--enable-gpu"])
        contexto = navegador.new_context(viewport={"width": 1920, "height": 1080}, color_scheme="light",
                                         record_video_dir=str(pasta), record_video_size={"width": 1920, "height": 1080})
        contexto.add_init_script("try { localStorage.setItem('visionepi-theme', 'light'); } catch (e) {}")
        pagina = contexto.new_page()
        entrar(pagina, servidor, "supervisor")
        pagina.wait_for_timeout(3000)
        pagina.goto(servidor.base + "/palco")
        palco = pagina.locator("[data-testid=palco]")
        palco.wait_for(timeout=30_000)
        for _ in range(20):
            pagina.keyboard.press("ArrowLeft")
        pagina.wait_for_function("document.querySelector('[data-testid=palco]')?.dataset.cena === '0'", timeout=15_000)
        total = int(pagina.locator(".palco-indice").inner_text().split("/")[1])
        for i in range(total):
            chave = palco.get_attribute("data-chave")
            if chave == "queda":
                inicio = time.monotonic()
                try:
                    pagina.locator("[data-testid=pilula-incidente]", has_text="Queda").wait_for(timeout=60_000)
                    print(f"[video] queda ao vivo em {time.monotonic() - inicio:.1f} s", flush=True)
                except Exception:  # noqa: BLE001  (grava assim mesmo; o log diz)
                    print("[video] a queda não confirmou em 60 s nesta gravação", flush=True)
            pagina.wait_for_timeout(TEMPO_DA_CENA.get(chave or "", 8) * 1000)
            if i < total - 1:
                pagina.keyboard.press("ArrowRight")
                pagina.wait_for_function(f"document.querySelector('[data-testid=palco]')?.dataset.cena === '{i + 1}'",
                                         timeout=15_000)
        video = pagina.video.path()
        contexto.close()
        navegador.close()
    final = pasta / "palco.webm"
    shutil.move(video, final)
    return final


def converter(webm: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("[video] ffmpeg não encontrado: fica o WebM", flush=True)
        return
    mp4 = webm.with_suffix(".mp4")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-preset", "slow", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)], check=True)
    # GIF do README: os primeiros 24 s (abertura e portal), 800 px, 8 fps, paleta própria.
    gif = webm.parent / "palco.gif"
    filtro = ("fps=8,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", "0", "-t", "24", "-i", str(mp4), "-vf", filtro, str(gif)], check=True)
    print(f"[video] {mp4} ({mp4.stat().st_size // 1024} KB), {gif} ({gif.stat().st_size // 1024} KB)", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aquecer", type=float, default=150.0)
    args = ap.parse_args()
    servidor = ServidorDemo()
    try:
        servidor.subir(args.aquecer)
        webm = gravar(servidor, DESTINO)
    finally:
        servidor.parar()
    converter(webm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
