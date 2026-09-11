# Pesquisa — modelos e datasets para ampliar a detecção

Levantamento de **modelos/datasets de EPI que reconhecem mais itens** do que o
VisionEPI hoje, e de **outras bases** com objetos/eventos que seriam úteis
identificar num contexto de segurança industrial.

Data da pesquisa: 2026-09-10.

---

## 1. Baseline atual do projeto

Modelo em uso: **Vyra YOLOv8m** (`Hexmon/vyra-yolo-ppe-detection`, HuggingFace),
licença **CC-BY-4.0** (exige atribuição). 14 classes:

```
Fall-Detected, Gloves, Goggles, Hardhat, Ladder, Mask,
NO-Gloves, NO-Goggles, NO-Hardhat, NO-Mask, NO-Safety Vest,
Person, Safety Cone, Safety Vest
```

O `.env` filtra para 8 (`YOLO_CLASSES=0,1,2,3,5,11,12,13`) e o detector de pessoa
real é o `yolov8n.pt` (COCO), porque a classe `Person` do Vyra não dispara em
imagem real (ver comentário no `.env.example`).

**Lacunas de EPI hoje:** proteção auricular, protetor facial / face shield,
cinto/talabarte (trabalho em altura), calçado de segurança (existe como
_feature_ `safety_shoe` mas o modelo não detecta), macacão/roupa de proteção,
respirador/máscara PFF, luva vs. mão nua com granularidade.

---

## 2. Modelos / datasets de EPI com MAIS classes

Ordenados por cobertura. "Pesos prontos" = dá pra baixar `.pt`/`.onnx` e usar sem
treinar; "dataset" = precisa treinar.

### 2.1 SH17 — 17 classes (o mais completo) — dataset
- **Fonte:** arXiv 2407.04590 · GitHub `ahmadmughees/SH17dataset` · Kaggle
  `mugheesahmad/sh17-dataset-for-ppe-detection`
- **8.099 imagens, 75.994 instâncias.** Indústria de manufatura (imagens Pexels).
- **Classes:** Person, Head, Face, Glasses, Face-mask-medical, **Face-guard**,
  **Ear**, **Earmuffs**, Hands, Gloves, **Foot**, **Shoes**, Safety-vest, Tools,
  Helmet, **Medical-suit**, **Safety-suit**
- **Cobre as lacunas:** proteção auricular (Earmuffs), protetor facial
  (Face-guard), calçado (Shoes/Foot), macacão (Safety-suit), ferramentas.
- **Licença:** **CC BY-NC-SA 4.0** — ⚠️ **não-comercial**. OK para trabalho
  acadêmico/Challenge; bloqueia uso comercial e redistribuição alterada.
- Benchmark do paper: YOLOv9-e ~70,9% mAP.

### 2.2 Roboflow "Safety_PPE" — 12 classes — dataset (+ modelo hospedado)
- **Fonte:** `universe.roboflow.com/safety-jmser/safety_ppe`
- **Classes:** Glove, Goggles, Helmet, **No_BreathingApparatus**, No_Glove,
  No_Goggles, **No_Harness**, No_Helmet, **No_Shoe**, Person, **Safety_Harness**,
  Shoe
- **Cobre:** cinto de segurança (Harness), aparelho de respiração
  (BreathingApparatus), calçado — todos com contraparte NO-* (encaixa direto no
  modelo de histerese/conformidade do projeto).
- Treina em YOLOv8/v11; Roboflow serve API de inferência hospedada.

### 2.3 Ultralytics Construction-PPE — 11 classes — dataset oficial
- **Fonte:** `docs.ultralytics.com/datasets/detect/construction-ppe`
- **1.416 imagens.** Classes: helmet, gloves, vest, **boots**, goggles +
  no_helmet, no_gloves, no_boots, no_goggle, person, ...
- **Cobre:** calçado (boots) com par NO-. Integração trivial com o pipeline
  Ultralytics já usado (`YOLO(...).train(data="construction-ppe.yaml")`).
- Dataset pequeno — melhor como _fine-tune_ complementar, não sozinho.

### 2.4 Roboflow "Construction Site Safety" — 10 classes — dataset + pesos
- **Fonte:** `universe.roboflow.com/roboflow-universe-projects/construction-site-safety`
  (também no Kaggle: `snehilsanyal/construction-site-safety-image-dataset-roboflow`)
- **Classes:** Hardhat, Mask, NO-Hardhat, NO-Mask, NO-Safety Vest, Person,
  Safety Cone, Safety Vest, **machinery**, **vehicle**
- **Licença:** CC BY 4.0 (comercial OK). Versão v27 já treinada em YOLOv8s.
- **Cobre:** máquina e veículo em cena — base para alerta de pessoa próxima a
  equipamento móvel (ver §3.4).

### 2.5 Luxonis PPE Detection — 10 classes — **pesos prontos**
- **Fonte:** `models.luxonis.com/luxonis/ppe-detection`
- **Classes:** Hardhat, Mask, NO-Hardhat, NO-Mask, NO-Safety Vest, Person,
  Safety Cone, Safety Vest, machinery, vehicle
- Modelo compilado (OAK / .blob), mas o `.onnx` serve de base. Bom para
  comparar acurácia rápido, sem treinar.

### 2.6 `M3GHAN/YOLOv8-Object-Detection` — GitHub — pesos + pipeline
- Detecta: hard hats, gloves, masks, glasses, **boots**, vests, **PPE-suits**,
  **ear protectors**, **safety harnesses**, person.
- Inclui conversão PascalVOC→YOLO e script de treino. Cobre 3 lacunas de uma vez
  (auricular, cinto, macacão). Verificar licença/tamanho do dataset antes de
  adotar.

### 2.7 `melihuzunoglu/ppe-detection` — HuggingFace — **pesos prontos** (YOLOv11)
- YOLOv11, 640×640, treinado com Ultralytics. Foco em capacete/colete/EPI
  básico — menos classes que o Vyra, mas arquitetura mais nova; serve de
  baseline de comparação de velocidade/precisão em CPU.

### 2.8 `Tanishjain9/yolov8n-ppe-detection-6classes` — HuggingFace — pesos
- Já citado no `.env.example` como alternativa (`models/epi_pretrained.pt`, MIT).
  6 classes, sem classe `person` — exige `MULTI_PERSON_DETECTION=true` e
  `YOLO_CLASSES` vazio.

### 2.9 GDUT-HWD / CHV — cor de capacete — dataset
- **GDUT-HWD:** 3.174 imgs, 5 classes = capacete por cor (azul/amarelo/branco/
  vermelho) + cabeça sem capacete.
- **CHV:** curadoria de GDUT-HWD + SHW, adiciona colete → 5 categorias.
- **Uso:** distinguir função/área por cor do capacete (visitante vs. equipe vs.
  brigada). Complementa, não substitui, o modelo principal.

### Resumo — o que adotar para ampliar EPI

| Objetivo | Melhor fonte | Custo |
|---|---|---|
| Máxima cobertura de EPI (auricular, face shield, macacão, calçado) | **SH17** | treinar; licença NC |
| Cinto/talabarte + respirador com par NO-* | **Roboflow Safety_PPE** | treinar |
| Calçado de segurança rápido, mesmo ecossistema | **Ultralytics Construction-PPE** (fine-tune) | treinar leve |
| Comparar sem treinar | **Luxonis** / **melihuzunoglu** (pesos prontos) | baixo |
| Uso comercial futuro | **Roboflow Construction Site Safety** (CC BY 4.0) | treinar |

⚠️ **Licença importa:** SH17 é **NC** (não-comercial). Se o Challenge virar
produto, priorizar CC-BY-4.0 (Vyra, Construction Site Safety) ou MIT
(Tanishjain9).

⚠️ **Mapa de classes:** trocar/combinar modelo exige revisar `YOLO_CLASSES` e as
chaves de _feature_ do frontend (`frontend/src/api/` — `ppe,helmet,vest,gloves,
glasses,mask,safety_shoe,...`). Índices são específicos de cada modelo.

---

## 3. Outras bases — objetos/eventos úteis de identificar

Além de EPI, o que mais faz sentido detectar num sistema de risco industrial.

### 3.1 Fogo e fumaça
- **D-Fire** — `github.com/gaia-solutions-on-demand/DFireDataset` — ~21.000 imgs,
  anotação YOLO (fire, smoke). Leve, fácil de treinar.
- **FASDD** (Flame And Smoke Detection Dataset) — ~120.000 imgs, sub-bases
  CV/UAV/RS, anotação VOC/YOLO/COCO/TDML. YOLOv10 reportado ~91% mAP@50.
- **Uso:** princípio de incêndio como categoria de alerta crítico; encaixa no
  ciclo de vida de alertas com histerese que já existe.

### 3.2 Objetos de canteiro / planta
- **SODA** — 19.846 imgs, 286.201 objetos, **15 classes**: slogan, fence, hook,
  hopper, electric box, cutter, handcart, scaffold, brick, rebar, wood, board,
  helmet, vest, person. (`arxiv.org/abs/2202.09554`)
- **MOCS** (Moving Objects in Construction Sites) — 41.668 imgs, 174 canteiros,
  **13 classes de objetos móveis**: worker, tower crane, hanging hook, vehicle
  crane, roller, bulldozer, excavator, truck, loader, pump truck, concrete mixer,
  pile driver, other vehicles.
- **ACID** (Alberta Construction Image Dataset) — 10.000 imgs, 10 classes de
  equipamento pesado.
- **Uso:** detectar máquina pesada / guindaste / carga suspensa em cena → base
  para "pessoa sob carga suspensa", "pessoa na rota da empilhadeira",
  "andaime sem alguém" etc.

### 3.3 Comportamento inseguro / ações (vídeo, não só frame)
- **Action Recognition based Industrial Safety Violation Detection** —
  `arxiv.org/pdf/2412.05531` — reconhecimento de ação para violações.
- **UnsafeNet** — vídeos de fábrica anotados como comportamento seguro/inseguro.
- **Dataset de 5 comportamentos inseguros** (paper 2025): sem capacete, sem
  cinto, sem colete, invasão de área perigosa, escalada em posição insegura
  (450 imgs de escalada insegura).
- **Trabalho em altura / guarda-corpo** — `nature.com/articles/s41598-025-19048-w`
  — detecção de proteção em operação em altura + relação espacial; ausência de
  guarda-corpo como causa principal de queda.
- **Uso:** vai além do que o MediaPipe Pose faz hoje (pose global por frame) —
  permitiria classificar a ação, não só a postura. Requer modelo temporal
  (CNN+LSTM / STGCN), não YOLO puro.

### 3.4 Empilhadeira × pedestre
- Não há dataset aberto forte e consolidado — o campo é dominado por soluções
  comerciais (ELOKON, Powerfleet, Yale, Trio Mobil) com radar+UWB+visão.
- Alternativa: combinar **MOCS/ACID** (detectar a empilhadeira) + **área de
  risco configurável** que o VisionEPI já tem → alerta quando pessoa e
  empilhadeira ocupam a mesma zona. Não precisa de dataset novo.

### 3.5 Sinalização e ambiente (menor prioridade)
- Placas de perigo / advertência, extintores, saídas de emergência bloqueadas,
  derramamento no piso, área molhada. Não achei dataset pronto de referência —
  provável necessidade de coleta própria via Roboflow.

### Resumo — bases correlatas

| Categoria | Base | Tamanho | Pronto p/ YOLO |
|---|---|---|---|
| Fogo/fumaça | D-Fire | ~21k | sim |
| Fogo/fumaça (grande) | FASDD | ~120k | sim |
| Objetos de canteiro | SODA (15 cl.) | ~20k | sim |
| Máquinas móveis | MOCS (13 cl.) | ~42k | sim |
| Equipamento pesado | ACID (10 cl.) | 10k | sim |
| Ação insegura | arXiv 2412.05531 / UnsafeNet | — | não (temporal) |
| Trabalho em altura | s41598-025-19048-w | — | parcial |

---

## 4. Recomendação de próximos passos

1. **Ganho rápido, sem treinar:** rodar **Luxonis** ou **melihuzunoglu** lado a
   lado com o Vyra num punhado de imagens reais e comparar precisão/latência em
   CPU. Decide se vale trocar de base.
2. **Ampliar EPI de verdade:** _fine-tune_ do Vyra (ou YOLOv11m) com **SH17**
   para adicionar Earmuffs, Face-guard, Shoes, Safety-suit — respeitando a
   licença NC enquanto for acadêmico. Reavaliar `YOLO_CLASSES` e as _features_
   do frontend.
3. **Cinto/talabarte:** se trabalho em altura entrar no escopo, **Roboflow
   Safety_PPE** dá `Safety_Harness` + `No_Harness` prontos para o modelo de
   histerese.
4. **Nova categoria de alerta:** **D-Fire** (fogo/fumaça) é o melhor
   custo-benefício — dataset pequeno, YOLO puro, alerta crítico óbvio.
5. **Pessoa × máquina:** reaproveitar a **área de risco** já existente +
   detector de máquina de **MOCS/ACID**, sem depender de solução comercial.

---

## Fontes

- [SH17 — arXiv 2407.04590](https://arxiv.org/abs/2407.04590) ·
  [GitHub](https://github.com/ahmadmughees/SH17dataset) ·
  [Kaggle](https://www.kaggle.com/datasets/mugheesahmad/sh17-dataset-for-ppe-detection)
- [Roboflow Safety_PPE (12 classes)](https://universe.roboflow.com/safety-jmser/safety_ppe)
- [Ultralytics Construction-PPE](https://docs.ultralytics.com/datasets/detect/construction-ppe)
- [Roboflow Construction Site Safety](https://universe.roboflow.com/roboflow-universe-projects/construction-site-safety) ·
  [Kaggle](https://www.kaggle.com/datasets/snehilsanyal/construction-site-safety-image-dataset-roboflow)
- [Luxonis PPE Detection](https://models.luxonis.com/luxonis/ppe-detection/fd8699bf-3819-4134-9374-3735b9660d3c)
- [M3GHAN/YOLOv8-Object-Detection](https://github.com/M3GHAN/YOLOv8-Object-Detection)
- [melihuzunoglu/ppe-detection (HF, YOLOv11)](https://huggingface.co/melihuzunoglu/ppe-detection)
- [Tanishjain9/yolov8n-ppe-detection-6classes (HF)](https://huggingface.co/Tanishjain9/yolov8n-ppe-detection-6classes)
- [GDUT-HWD / hardhat benchmark — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S092658051930264X) ·
  [CA-CentripetalNet (arXiv)](https://arxiv.org/pdf/2307.04103)
- [D-Fire dataset](https://github.com/gaia-solutions-on-demand/DFireDataset)
- [FASDD — Copernicus ESSD](https://essd.copernicus.org/preprints/essd-2023-73/)
- [SODA — arXiv 2202.09554](https://arxiv.org/abs/2202.09554)
- [MOCS — "Dataset and benchmark for detecting moving objects in construction sites"](https://www.researchgate.net/publication/347870835_Dataset_and_benchmark_for_detecting_moving_objects_in_construction_sites)
- [AIDCON / ACID context — MDPI](https://www.mdpi.com/2072-4292/16/17/3295)
- [Action Recognition Industrial Safety Violation — arXiv 2412.05531](https://arxiv.org/pdf/2412.05531)
- [Working-at-high safety recognition — Scientific Reports](https://www.nature.com/articles/s41598-025-19048-w)
- [Sec-YOLO unsafe behavior — PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12453777/)
- [Forklift pedestrian safety (comercial) — Trio Mobil](https://www.triomobil.com/en/blog/a-guide-to-forklift-pedestrian-safety)
