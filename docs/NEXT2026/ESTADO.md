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

- WIP `b344f5e` (F1, F3, F4, F5, F7, F9, F10, Sobre, iniciar-todas) trazido por
  cherry-pick; `dist` recompilado; varredura de rotas corrigida.
- F2 queda do modelo atribuída a ID + linha do tempo por ID — E2E passou (com as
  outras câmeras pausadas durante o teste; ver CHANGELOG F2).
- F6 celular como câmera (`/cam`, token, `run.py --https`, QR vendorizado MIT).
- F8 **descartado**: licença do MobileCLIP (só pesquisa); ultralytics fica 8.3.40.
- Controle de privacidade só para supervisor; dispositivo ativo no Diagnóstico.
- E2E novos: replay, pílula de aproximação, privacidade, diagnóstico, relatório,
  queda, celular — rodando (`bench/runtime/e2e-pr2.out`).
- `e2e/capturas_de_tela.py`: capturas em `bench/runtime/capturas/` (fora do git).

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

1. Ler `bench/runtime/e2e-pr2.out`; corrigir o que falhar.
2. `python e2e/capturas_de_tela.py`; revisar as imagens (cor só para status,
   tema claro padrão da demo, 1366x768 sem quebra); iterar.
3. Portão do PR2: pytest, ruff, build, E2E, CPU-ms (3 repetições, base = PR1 `3891aaa`) → PR → squash.
