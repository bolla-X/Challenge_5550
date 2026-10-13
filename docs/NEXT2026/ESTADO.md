# ESTADO — missão NEXT 2026

Retomar lendo só este arquivo e `MISSAO.md`. Reescrito a cada marco.

## Marco atual: FASE 1 (PR1) — medições de decisão em andamento

Branch `next-2026` @ `0eb5dec` (local + `origin/next-2026` em `6385e0f`; ainda não
publicada a parte nova). Worktree congelada do candidato:
`C:/Users/L-BARALDI/Desktop/VisionEPI-novo` (detached no mesmo commit).
Baseline instrumentada: `C:/Users/L-BARALDI/Desktop/VisionEPI-baseline`, branch
LOCAL `bench/base-instrumentada` @ `918219a` = `2f3c49a` + backport SÓ de
medição (idade da análise, instante do quadro). Não é para PR.

### Feito nesta sessão (com evidência)

| Item | Evidência |
|---|---|
| Passo 0 (missão, estado, push das 3 branches, carga de fundo) | commit `51dd005`; push com 3 `[new branch]` |
| "72 %" corrigido: era o pytorch:512; pytorch:640 = 100 % | `bench/results/concordancia-epi-20261013-055538.json` |
| OpenVINO dinâmico rodava com letterbox quadrado → corrigido → 99,17 % (EPI) / 100 % (pessoa), aprovado | mesmo JSON + `concordancia-pessoa-20261013-055740.json`; `tests/test_yolo_ppe_detector.py` |
| OpenVINO recompilado em CPU, LATENCY, `INFERENCE_NUM_THREADS=VISIONEPI_THREADS` | `6e9a027`; doc citada no CHANGELOG §4.2 |
| Métricas do portão: `fps_analise`, `idade_analise` p50/p95, latência de alerta | `6793eb6`; `tests/test_metricas_do_portao.py` |
| Gabarito da latência: `multidao`/`missing_helmet` no quadro 0 | `python scripts/primeira_violacao.py` → `bench/primeira_violacao.json` |
| Controlador adaptativo nunca mexe no imgsz; no assíncrono começa pela pose | `tests/test_controlador_adaptativo.py` (11) |
| Histerese de alerta também por tempo (2 s/≥2 confirmações; resolve 6 s/≥3) | `0eb5dec`; `tests/test_alert_state.py` (+6) |
| Decoder FFmpeg com 2 threads (padrão abria 12 por câmera) | `tests/test_video_stream.py::test_decoder_de_arquivo_abre_com_teto_de_threads` |
| Perfil batata = E-cores 10 e 11 pela topologia | `scripts/bench.py::nucleos_eficientes` |
| Suíte | `pytest -q` → 432 passed; `ruff check .` limpo |

### Medições que já existem (fundo ~1000 % — ver BENCHMARKS.md quando escrito)

`bench/results/20261013-061102-pr1-batata.json` (antes das correções de
histerese/decoder, afinidade ainda instável [1,7]): batata 1 câm. idade da
análise p95 — base 3180 ms, PyTorch 5412, ONNX 3602, OpenVINO 11088; latência
de alerta — base 83,9 s, PyTorch 59,7 s, ONNX sem alerta em 122 s.

### Bloqueios registrados

- `.env.example` está negado para leitura/edição pelas permissões desta
  sessão; ele ainda tem `YOLO_IMGSZ=416` (reprovado no guarda). O default do
  código e do bench é 640.
- Carga de fundo de terceiros variável e alta (ffmpeg `veryslow`, 2 JVMs, outro
  python): 600–1190 % de 1200 % possíveis. Nada foi encerrado.

## Próximo passo exato

1. Ler `scratchpad`/`bench/results/*-b1cam-r{1,2,3}.json` (3 repetições
   intercaladas, batata 1 câm.: base/pytorch/onnx/openvino) e decidir o
   runtime (menor idade da análise p95; empate ≤5 % → PyTorch).
2. Rodar `comparar_trackers.py` no perfil batata (VISIONEPI_CPUS=10,11) e decidir o tracker.
3. Batata 4 câm. e perfil atual 1/4 câm.; escrever `docs/NEXT2026/BENCHMARKS.md`.
4. Portão completo (pytest, ruff, build do frontend, E2E) → PR1 → squash.
