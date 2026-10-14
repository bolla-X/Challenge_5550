# ESTADO — missão NEXT 2026

Retomar lendo só este arquivo e `MISSAO.md` (inclui o ADENDO 1). Reescrito a cada marco.

## Marco atual: PR4 em construção (Fase 4)

| PR | Situação | Evidência |
|---|---|---|
| PR1 performance + benchmark | **mergeado** (`3891aaa`) | https://github.com/bolla-X/Challenge_5550/pull/10 |
| PR2 diferenciais + L1 | **mergeado** (`753daa0`) | https://github.com/bolla-X/Challenge_5550/pull/11 |
| PR3 funções criativas | **mergeado** (`b8de7ac`) | https://github.com/bolla-X/Challenge_5550/pull/12 — pytest 559, E2E 17/17, protótipos ≤ 3,4 % do orçamento |
| PR4 demo, confiabilidade, docs | em andamento na `next-2026` | ver abaixo |

### PR4 — plano
1. Câmera "Arquivo" pela API com `em_loop` (rebobina em vez de reconectar).
2. `python run.py --demo` (banco isolado, senhas só no terminal, GRAVAÇÃO/AO VIVO, tema claro) e `flask demo reset` < 10 s.
3. Soak 20 min 4 câmeras (RSS < +10 %, console limpo) e testes de falha (modelo ausente, fonte inválida, webcam ausente, LLM fora, banco indisponível).
4. `scripts/bench.py --rapido` (≤ 5 min); DEMO.md, BANCA.md (rascunho no scratchpad da sessão), README, CHANGELOG final.

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

Seguir o plano do PR4 acima, na ordem; portão: pytest, ruff, build, E2E, soak.
