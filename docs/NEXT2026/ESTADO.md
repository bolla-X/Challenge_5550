# ESTADO — missão NEXT 2026

Retomar lendo só este arquivo e `MISSAO.md` (inclui o ADENDO 1). Reescrito a cada marco.

## Marco atual: PR2 em construção (Fase 2)

| PR | Situação | Evidência |
|---|---|---|
| PR1 performance + benchmark | **mergeado** (squash `3891aaa`) | https://github.com/bolla-X/Challenge_5550/pull/10 |
| Alavancas L1/L2 (entram no PR2) | L1 **aprovada** (OpenVINO iGPU FP32 padrão do `auto`; CPU-ms/análise −78 %); L2 **sem candidato** | CHANGELOG "L1", "L2"; `bench/results/*-l1-r*.json` |
| PR2 diferenciais | em andamento na branch local `next-2026` | ver abaixo |
| PR3, PR4 | não iniciados | — |

### PR2 — o que já está na `next-2026`

- WIP `b344f5e` (F1, F3, F4, F5, F7, F9, F10, Sobre, iniciar-todas) por cherry-pick.
- F2 queda do modelo por ID + linha do tempo; F6 celular como câmera; F8 descartado (licença).
- Detector de pessoa padrão (`ef81e3b`) → pose passou a rodar em toda análise →
  pose no `auto` (OpenVINO iGPU aprovado: caixas 100 %, keypoints p95 0,0) (`289d382`).
- Bug do `stop()` (alerta ficava ativo no banco) corrigido (`9d439b3`).
- Pílula de aproximação cede só a emergência/EPI crítico; E2E do replay abre o grupo.
- Revisão visual 1366x768 feita e corrigida (`5953fcf`).
- E2E: `e2e-pr2d` 9/11 → os 2 restantes passaram isolados (`e2e-pr2e`, 2/2).
  Falta a rodada completa única do portão.
- Bench de CPU do portão rodando: `scripts/rodar_portao.py --rotulo pr2gate`
  (base = worktree `../VisionEPI-pr1` em `3891aaa`, com `models/export` por junção).

### PR3 — adiantado em worktree `../VisionEPI-pr3` (branch local `pr3-wip`)

- `71192a1`: G3 SOS, G4 imóvel, G7 ergonomia (`app/vision/sinais_por_id.py`),
  G6 fala pt-BR (`frontend/src/audio/fala.ts` + E2E com Web Speech falsa),
  G10 NR-6 no relatório (`app/services/nr6.py`).
- Não commitado ainda: G1 Portal (`gate_service.avaliar_portal`, `PortalState`,
  `/api/cameras/<id>/portal`, tela `/portal`, `tests/test_portal.py` 9/9).
- Depois do squash do PR2: recriar `next-2026` da base e trazer o `pr3-wip` por cherry-pick.

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

1. `bench/runtime/pr2gate.estado` = FIM → `python scripts/resumo_cpu.py bench/results/*-pr2gate-r*.json --base pr1 --novo pr2`.
2. E2E completo numa rodada única (11/11).
3. Push, PR2 contra `feat/completo-com-rebrand`, squash, recriar `next-2026`, cherry-pick do `pr3-wip`.
