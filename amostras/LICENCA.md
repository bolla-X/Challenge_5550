# Amostra de vídeo versionada

`canteiro_amostra.mp4` — 7 s, 640x360, 12 fps, H.264, sem áudio, ~0,5 MB.

É a única gravação que o repositório redistribui. Serve para o modo demonstração subir num clone que ainda não
rodou `python scripts/fetch_fixtures.py`: cada câmera da demo cuja gravação completa não foi baixada toca esta
amostra (`app/demo_ambiente.py::fonte_da_gravacao`). Com as gravações baixadas, a amostra não é usada.

## Atribuição

| Campo | Valor |
|---|---|
| Obra original | [Building construction Moira Close Broadwater Farm Haringey 2025 13.webm](https://commons.wikimedia.org/wiki/File:Building_construction_Moira_Close_Broadwater_Farm_Haringey_2025_13.webm) |
| **Autor** | **Acabashi** |
| **Licença** | **CC BY-SA 4.0** — https://creativecommons.org/licenses/by-sa/4.0/ |
| Mudanças | recorte dos frames 3596–3806 (o mesmo de `tests/fixtures/bench.mp4`, ver `docs/FIXTURES.md`), redimensionado para 640x360 e 12 fps, áudio removido |

Esta amostra é obra derivada e é distribuída sob a **mesma licença, CC BY-SA 4.0**, com a atribuição acima.

Como foi gerada (a partir da `bench.mp4` baixada por `scripts/fetch_fixtures.py`):

```bash
ffmpeg -i tests/fixtures/bench.mp4 -t 7 -vf "scale=640:360,fps=12" -c:v libx264 -preset slow -crf 28 -pix_fmt yuv420p -an -movflags +faststart amostras/canteiro_amostra.mp4
```
