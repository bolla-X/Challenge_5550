# Vídeo da Sprint 4 — como reproduzir

Vídeo **sem narração e sem áudio** (decisão do grupo). Roteiro, tempos e legendas:
[docs/pitch/storyboard.md](../../docs/pitch/storyboard.md). O MP4 não é versionado; estes scripts o refazem.

Pré-requisitos: o ambiente do README pronto (venv, `scripts/preparar.py`, build do frontend), o Chromium do
Playwright (`python -m playwright install chromium`) e o `ffmpeg`/`ffprobe` no PATH.

```bash
python scripts/video/gravar_cartelas.py
```

```bash
python scripts/video/gravar_demo.py
```

```bash
python scripts/video/montar_video.py
```

| Script | O que faz | Saída (fora do git, em `bench/runtime/video/`) |
|---|---|---|
| `cartelas.html` | as 6 cartelas (abertura, problema, solução, impacto, evolução, encerramento) no visual do VisionEPI, tema claro, uma por âncora (`#abertura` …) | — |
| `gravar_cartelas.py` | grava cada cartela com o `record_video_dir` do Playwright, 1920x1080, com a duração do storyboard | `cartelas/<n>-<cena>.webm` |
| `gravar_demo.py` | sobe `run.py --demo` (sem webcam, sem câmera IP, sem `GEMINI_API_KEY`), espera alerta + segunda opinião no Pátio e grava as sub-cenas 4a–4h com barra de legenda e cursor injetados no DOM | `demo/4-demonstracao.webm` + `.json` com o início de cada sub-cena |
| `montar_video.py` | recodifica cada trecho (H.264, yuv420p, 30 fps, `-an`), concatena, confere com `ffprobe` e extrai 6 frames-chave | `VisionEPI_pitch_demo.mp4`, `frames/*.png` |

A legenda e o cursor existem só durante a gravação (injetados pelo Playwright); o app não muda.
