# ADR 0002: YOLO Vyra para EPI + detector de pessoa dedicado (`MULTI_PERSON_DETECTION=true`)

- **Status:** aceito (vigente com o peso Vyra; o peso da Sprint 4 de IA é uma alternativa configurável)
- **Data:** 09/09/2026 (teste vermelho `0769c97`, correção `a42d2e5`, "liga o detector de pessoa no default"). O modelo Vyra entrou em 24/08 (`e4cd04c`).

## Contexto

O Vyra (`Hexmon/vyra-yolo-ppe-detection`, YOLOv8m, 14 classes, CC-BY-4.0) tem uma classe `Person`, e por isso o projeto nasceu com
`MULTI_PERSON_DETECTION=false`. A medição mostrou que a classe não generaliza (README, `docs/SPRINT3.md`):

- 36 células testadas (3 fotos de canteiro x `imgsz` 416/640/960/1280 x 3 limiares): **zero** detecções de `Person`.
- Na matriz de confusão do próprio autor, `Person` tem cerca de 277 instâncias de validação contra cerca de 8.946 de `Hardhat`.
- Na mesma imagem, `yolov8n.pt` (COCO) acha as duas pessoas com 0,87 e 0,73.
- Sem lista de pessoas, o `PersonComplianceMatcher` não avalia ninguém e **nenhum alerta de EPI é criado**.
- Pessoas por quadro (Vyra x yolov8n, 1 quadro/s): multidão 0,1 x 7,1, canteiro 0,0 x 1,0, queda 0,0 x 2,0 (CHANGELOG do NEXT, F3).

## Decisão

- EPI: peso Vyra (`models/vyra_ppe.pt`). Pessoa: **YOLOv8n COCO dedicado** (`models/yolov8n.pt`) com `MULTI_PERSON_DETECTION=true` como
  padrão em `app/config.py` e `.env.example`, travado por `tests/test_onboarding.py` (README: "travado por `tests/test_onboarding.py`").
- `PERSON_MODEL_PATH` aponta para `models/yolov8n.pt` de propósito: com o nome solto o Ultralytics baixaria o peso no diretório de
  trabalho, fora da pasta ignorada pelo git.

## Consequências

- Custo declarado: **-20 % de FPS** (24,32 para 19,42 a `imgsz=416`, `docs/BENCH.md`).
- Um segundo peso não versionado: baixado por `scripts/preparar.py` com conferência de SHA-256.
- A Sprint 4 de IA (28/09) mediu um peso próprio com a classe `Person` treinada junto (`models/visionepi_cppe_n416.pt`): nele
  `MULTI_PERSON_DETECTION=false` volta a fazer sentido, também por medição (`docs/SPRINT4.md`). Como todas as medições do NEXT 2026
  foram feitas com o Vyra, o padrão continua Vyra + `true`, e o peso próprio fica documentado como opção (três linhas juntas no `.env`).
- O YOLO11n-pose não substitui o detector de pessoa: concordância de caixas de 83,8 % com o yolov8n (CHANGELOG §4.4).

## Alternativas

- Usar a classe `Person` do Vyra: **rejeitada** (medido, acima).
- Ensemble Vyra + SH17 (Fase 1): o código existe (`app/vision/ensemble_ppe_detector.py`), mas `PPE_EXTRA_MODELS` vem vazio; no teste do SH17
  o ensemble ficou pior em mAP@0,5 que o SH17 sozinho na maioria das classes (`docs/challenge/FASE1-DETECCAO-DE-EPIS.md` §3.1).
- Peso próprio de um modelo só: **mantida como alternativa**, não como padrão.
