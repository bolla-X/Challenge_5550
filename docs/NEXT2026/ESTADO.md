# ESTADO — missão NEXT 2026

Retomar lendo só este arquivo e `MISSAO.md` (inclui o ADENDO 1). Reescrito a cada marco.

## Marco atual: PR3 em validação (Fase 3)

| PR | Situação | Evidência |
|---|---|---|
| PR1 performance + benchmark | **mergeado** (squash `3891aaa`) | https://github.com/bolla-X/Challenge_5550/pull/10 |
| PR2 diferenciais + L1 | **mergeado** (squash `753daa0`) | https://github.com/bolla-X/Challenge_5550/pull/11 — portão: pytest 488, E2E 11/11, CPU-ms/análise −69 a −71 % |
| PR3 funções criativas | `next-2026` recriada de `753daa0` + cherry-pick do `pr3-wip` | ver abaixo |
| PR4 | não iniciado | — |

### PR3 — na `next-2026`

- G1 Portal (`/portal`), G2 Você vs. a IA (`/desafio`, GABARITO.md), G3 SOS,
  G4 imóvel, G5 planta (aba Planta), G6 fala pt-BR, G7 ergonomia, G8 Modo TV
  (`/tv`, metas por setor, migração `e7f8a9b0c1d2`), G9 rotular (`/rotular`),
  G10 NR-6 no relatório; laboratório "Pergunte à planta" (desligado).
- Migrações novas: `e7f8a9b0c1d2` (metas_setor), `f9a0b1c2d3e4` (cameras.planta).
- pytest 554; ruff ok; build ok. E2E (17 fluxos) rodando: `bench/runtime/e2e-pr3a.out`.
- Custo por protótipo medido em `pipeline_stats` (etapas `g1_portal`,
  `g3_g4_g7_sinais`, `g5_planta`, `g8_andon`, `g9_rotulos`).

## Decisões em vigor

- Runtime padrão: `RUNTIME_ORDEM=openvino-gpu,onnx,pytorch` (sem GPU → ONNX).
- `ONNX_SPINNING` desligado; tracker IoU; imgsz 640; adaptativo só N/pose/telemetria.
- Gravação sem espectador avança a 4 quadros/s; câmera ao vivo em tempo real.
- Histerese de alerta: 8 quadros OU 2 s com ≥ 2 confirmações (não afrouxar por fixture).

## Como medir (ADENDO 1)

- Bench destacado: `scripts/rodar_portao.py --liberar-docker`; progresso em `bench/runtime/<rótulo>.estado`.
- Decisão por CPU: `python scripts/resumo_cpu.py <jsons> --base X --novo Y`.
- E2E destacado: `Start-Process .venv\Scripts\python.exe -ArgumentList -m,pytest,e2e,-q -RedirectStandardOutput bench\runtime\e2e-X.out`.

## Pendências

- `.env.example` negado pelas permissões (ainda `YOLO_IMGSZ=416`).
- Câmera "Arquivo" pela API não usa `em_loop` (15 falhas a cada volta) → PR4.
- BENCHMARKS sem rodada com terceiros < 15 % → `scripts/bench.py --rapido` no PR4.
- Ruído: 5 alertas por pessoa (um por EPI).

## Próximo passo exato

1. E2E do PR3 (`e2e-pr3a.out`) 17/17; corrigir o que falhar.
2. Custo por protótipo (≤ 10 % do orçamento do quadro) lendo `/api/diagnostics/pipeline`
   com as câmeras rodando; bench CPU-ms PR2 (`753daa0`) × PR3, 3 repetições.
3. Capturas das telas novas; CHANGELOG do PR3; PR3 → squash; recriar `next-2026`.
4. PR4 (demo, confiabilidade, docs), incluindo o ruído de alertas (5 por pessoa).
