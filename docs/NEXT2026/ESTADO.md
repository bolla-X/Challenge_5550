# ESTADO — missão NEXT 2026

Retomar lendo só este arquivo e `MISSAO.md` (inclui o ADENDO 1). Reescrito a cada marco.

## Marco atual: PR1 MERGEADO → alavancas L1/L2 (antes do PR2)

| PR | Situação | Evidência |
|---|---|---|
| PR1 performance + benchmark | **mergeado** (squash `3891aaa` em `feat/completo-com-rebrand`) | https://github.com/bolla-X/Challenge_5550/pull/10 — pytest 445 passed, ruff limpo, build ok, E2E 4 passed, portão por CPU (`bench/results/*-gate6-r*.json`) sem reprova |
| PR2 diferenciais F1–F10 | não iniciado | WIP preparado em worktree `../VisionEPI-pr2` (branch local `pr2-preparo`, cherry-pick do `b344f5e` sobre o PR1 ANTES das últimas mudanças do PR1 — refazer sobre `next-2026` atual) |
| PR3, PR4 | não iniciados | — |

`next-2026` foi recriada a partir de `origin/feat/completo-com-rebrand` @ `3891aaa`.

## Decisões em vigor (com a regra do ADENDO 1)

- Runtime padrão: ONNX dinâmico (`PPE_RUNTIME=auto`); CPU-ms por análise batata 1 câm.: ONNX 2.926, OpenVINO 3.373, PyTorch 4.427.
- `ONNX_SPINNING` desligado (ligar aumentou CPU-ms por análise).
- Tracker padrão: IoU (ByteTrack em config).
- imgsz 640 fixo; controlador adaptativo só mexe em N/pose/telemetria.
- Gravação (arquivo) sem espectador avança a 4 quadros/s; câmera ao vivo em tempo real.

## Como medir (ADENDO 1)

- Rodadas sempre destacadas: `scripts/rodar_portao.py --liberar-docker` (WSL + Docker Desktop desligados durante a rodada e religados no fim).
- Decisão: `python scripts/resumo_cpu.py <jsons> --base X --novo Y` (reprova só se mediana > 10 % pior e as 3 repetições concordarem). Relógio = indicativo.
- Teto: 2 rodadas por decisão; sem decisão → default mais simples.
- Árvores: `bench/runtime/arvores_gate.txt` (base × PR1). Para o PR2, a "base" passa a ser o PR1 (`3891aaa`).

## Pendências registradas

- `.env.example` negado pelas permissões (ainda `YOLO_IMGSZ=416`).
- Câmera "Arquivo" pela API não usa `em_loop`: 15 falhas e reabertura a cada volta do vídeo (PR4).
- BENCHMARKS.md ainda sem rodada com CPU de terceiros < 15 %; `scripts/bench.py --rapido` precisa existir até o PR4 (DEMO.md).
- Ruído de alertas: 5 alertas por pessoa (um por EPI) — avaliar agrupamento na Fase 2.

## Próximo passo exato

1. Branch `alavancas` a partir de `next-2026`:
   - L1: OpenVINO na iGPU — doc do export Ultralytics + plugin GPU, `openvino.Core().available_devices`, export dinâmico, guarda CPU/GPU × FP32/FP16.
   - L2: modelo de EPI leve — busca HF/GitHub + conjunto rotulado público; avaliar no mesmo conjunto; sem treino.
2. Depois: PR2 (Fase 2 do MISSAO.md), trazendo `alavancas` e o WIP `b344f5e`.
