# ADR 0006: Runtime OpenVINO/ONNX escolhido só entre exports aprovados por um guarda de concordância

- **Status:** aceito (vigente)
- **Data:** 14/10/2026 (squash do PR7, `a6d303b`; as medições são de 13/10 e estão em `docs/NEXT2026/CHANGELOG.md`)

## Contexto

Em 24/08 o OpenVINO foi rejeitado por ser mais lento no worker real (`2d74e96`, citado em `docs/SPRINT3.md`); em 09/09 o ONNX no Ryzen 7 deu
26 % menos FPS que o PyTorch. No NEXT 2026 o alvo era uma máquina fraca ("perfil batata": 2 E-cores). Trocar de runtime muda o resultado do
modelo, e um "mais rápido" que perde capacete não serve.

## Decisão

- **Guarda de concordância** (`scripts/concordancia.py`): referência PyTorch@640, IoU ≥ 0,5, mesma classe; mínimo de **97 %** para trocar de
  runtime e 95 % para mudar de resolução. Para pose, também o erro de keypoint (p95 ≤ 0,05).
- `PPE_RUNTIME`, `PERSON_RUNTIME` e `POSE_RUNTIME` = `auto`: primeiro runtime **aprovado** de `RUNTIME_ORDEM=openvino-gpu,onnx,pytorch`
  (`app/vision/runtime_do_modelo.py`). Teste de carga e uma inferência no boot, com volta ao `.pt` se falhar. A aprovação só vale para o mesmo
  peso do export (achado da integração com o peso da Sprint 4).
- Resolução de inferência `YOLO_IMGSZ=640`: 416 deu 63,6 % de concordância (capacete 8 %) e 512 deu 72,0 %.
- Resultados: ONNX estático 95,04 % (reprovado); ONNX dinâmico 100 %; OpenVINO dinâmico na iGPU FP32 100 %, FP16 99,17 %. Escolhido FP32
  (empate de CPU com FP16, e 100 % no guarda).
- `scripts/preparar.py` baixa os pesos (SHA-256), gera os exports, roda o guarda e aquece o cache do OpenVINO (`runtime/ov_cache/`).

## Consequências

- Ganho medido (batata, 1 câmera, 3 repetições, `*-l1-r*.json`): CPU do servidor por análise de **6.432 ms (ONNX) para 1.401 ms (OpenVINO
  GPU FP32), -78 %**. Sob saturação de CPU de terceiros (indicativo): análises por segundo por câmera 0,28 (ONNX) para 1,27 (OpenVINO GPU FP32).
- Sem iGPU Intel visível, o resolvedor pula para o ONNX; sem export aprovado, PyTorch.
- Partida a frio é lenta: após reiniciar o PC, a pose levou 213 s e o total 248 s para compilar; com o cache quente, 32 s. Por isso o roteiro
  manda subir a demo antes da banca (`docs/NEXT2026/DEMO.md`).
- O ultralytics fica preso em **8.3.40**: sob o 8.4 o runtime "OpenVINO GPU" rodou na CPU. Os ajustes de runtime dependem dos internos da 8.3.40.
- Salvar uma área de detecção de formato novo recompila o modelo (cerca de 21 s na iGPU, sem análise de nenhuma câmera nesse intervalo).

## Alternativas

- Só PyTorch: **rejeitada** pelo custo de CPU na máquina fraca.
- ONNX estático e OpenVINO estático: **reprovados** no guarda (95,04 % e 94,65 %).
- Lote de 4 câmeras numa chamada (`INFERENCIA_LOTE`): implementado e **desligado** (95,04 % com formatos diferentes).
- Modelo leve de EPI de terceiros e YOLOE-26: **descartados** (sem candidato aprovado; restrição de licença do MobileCLIP).
