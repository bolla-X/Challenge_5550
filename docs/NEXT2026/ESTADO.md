# ESTADO — missão NEXT 2026

Retomar lendo só este arquivo e `MISSAO.md` (inclui o ADENDO 1). Reescrito a cada marco.

## Marco atual: PR4 no portão (Fase 4) — última etapa da missão

| PR | Situação | Evidência |
|---|---|---|
| PR1 performance + benchmark | **mergeado** (`3891aaa`) | https://github.com/bolla-X/Challenge_5550/pull/10 |
| PR2 diferenciais + L1 | **mergeado** (`753daa0`) | https://github.com/bolla-X/Challenge_5550/pull/11 |
| PR3 funções criativas | **mergeado** (`b8de7ac`) | https://github.com/bolla-X/Challenge_5550/pull/12 |
| PR4 demo, confiabilidade, docs | portão verde: pytest 569, ruff, tsc, E2E 18/18, soak 20 min (0 erros de console, RSS pico +6,1 %), reset 7,7–9,7 s | PR aberto a seguir |

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

- `.env.example` negado pelas permissões desta máquina (ainda `YOLO_IMGSZ=416`; o código usa 640).
- Ruído de alertas na multidão (5 por pessoa + troca de ID). A demo liga só 3 EPIs.
- G3 (SOS) fora do roteiro: sem vídeo de licença livre para verificar.
- Números absolutos sob carga de terceiros (13–77 %): rodar `scripts/bench.py --rapido` na máquina da banca.

## Próximo passo exato

Merge do PR4; depois, só manutenção.
