"""Monta o vídeo final da Sprint 4 a partir das gravações (cartelas + demo) e confere com ffprobe.

    python scripts/video/montar_video.py [--saida bench/runtime/video] [--destino <arquivo.mp4>]

Ordem do storyboard: 1 abertura, 2 problema, 3 solução, 4 demonstração, 5 impacto,
6 evolução, 7 encerramento. Cada trecho vira H.264 1920x1080 30 fps, yuv420p, sem
áudio (`-an`); a concatenação é sem recodificar. Depois:

- ffprobe: duração (≤ 300 s; alvo 240–285 s), resolução, codec, ausência de áudio;
- 6 frames-chave em `<saida>/frames/` para conferir a legenda a olho.

Sai com 1 se alguma conferência falhar.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gravar_cartelas import CARTELAS  # noqa: E402

# A página leva ~0,5 s para pintar depois que a gravação começa: corta o começo.
CORTE_INICIAL_CARTELA_S = 0.6
DEMO_S = 150


def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def _trecho(origem: Path, destino: Path, inicio: float, duracao: float) -> None:
    _ff("-ss", f"{inicio:.2f}", "-i", str(origem), "-t", f"{duracao:.2f}",
        "-vf", "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-an", str(destino))


def _sonda(arquivo: Path) -> dict:
    saida = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt",
                            "-of", "json", str(arquivo)], check=True, capture_output=True, text=True).stdout
    return json.loads(saida)


def montar(saida: Path, destino: Path) -> int:
    trechos = saida / "trechos"
    shutil.rmtree(trechos, ignore_errors=True)
    trechos.mkdir(parents=True)
    duracao = {ordem: s for ordem, _, s in CARTELAS}
    nomes = {ordem: cena for ordem, cena, _ in CARTELAS}
    lista: list[Path] = []
    for ordem in range(1, 8):
        alvo = trechos / f"{ordem}.mp4"
        if ordem == 4:
            _trecho(saida / "demo" / "4-demonstracao.webm", alvo, 0.3, DEMO_S)
        else:
            _trecho(saida / "cartelas" / f"{ordem}-{nomes[ordem]}.webm", alvo, CORTE_INICIAL_CARTELA_S, duracao[ordem])
        lista.append(alvo)
    concat = trechos / "lista.txt"
    concat.write_text("".join(f"file '{t.as_posix()}'\n" for t in lista), encoding="utf-8")
    destino.parent.mkdir(parents=True, exist_ok=True)
    _ff("-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", "-movflags", "+faststart", str(destino))

    info = _sonda(destino)
    video = [s for s in info["streams"] if s["codec_type"] == "video"]
    audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
    total = float(info["format"]["duration"])
    checagens = {
        "duração ≤ 300 s": total <= 300,
        "duração entre 240 e 285 s": 240 <= total <= 285,
        "1920x1080": bool(video) and (video[0]["width"], video[0]["height"]) == (1920, 1080),
        "H.264": bool(video) and video[0]["codec_name"] == "h264",
        "sem áudio": not audio,
    }
    print(json.dumps({"arquivo": str(destino), "duracao_s": round(total, 2), "tamanho_bytes": int(info["format"]["size"]),
                      "video": video[0] if video else None, "checagens": checagens}, ensure_ascii=False, indent=1))

    # Frames-chave: meio da abertura, da solução, de três sub-cenas da demo e da evolução.
    frames = saida / "frames"
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir()
    instantes = {"1-abertura": 8, "3-solucao": 58, "4c-incidente": 70 + 40, "4d-historico": 70 + 75,
                 "4f-ca-vencido": 70 + 112, "6-evolucao": 70 + 150 + 20 + 20}
    for nome, t in instantes.items():
        _ff("-ss", str(t), "-i", str(destino), "-frames:v", "1", str(frames / f"{nome}.png"))
    print(f"[montagem] frames-chave em {frames}")
    return 0 if all(checagens.values()) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--saida", type=Path, default=RAIZ / "bench" / "runtime" / "video")
    ap.add_argument("--destino", type=Path, default=None)
    args = ap.parse_args()
    saida = args.saida.resolve()
    return montar(saida, (args.destino or saida / "VisionEPI_pitch_demo.mp4").resolve())


if __name__ == "__main__":
    raise SystemExit(main())
