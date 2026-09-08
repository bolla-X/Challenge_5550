# Benchmark do pipeline de visão — Baseline

**Baseline (commit `73edc00`, AMD Ryzen 7 5700X, CPU-only, `torch 2.14.0+cpu`,
Windows 10 Pro 10.0.19045, Python 3.11.9, `ultralytics 8.3.40`)**

Sem GPU: `torch.cuda.is_available() == False`. `torch.get_num_threads() == 8`,
`cv2.getNumThreads() == 16`. Nenhuma linha do projeto chama
`torch.set_num_threads`.

Reproduzir:

```bash
python scripts/fetch_fixtures.py
python scripts/bench_pipeline.py --imgsz 416 --multi-person
```

## Como medir de novo sem se enganar

- **Entrada fixa:** `tests/fixtures/bench.mp4` — 210 quadros, 1280x720, 29,97
  fps, canteiro de obra real. Origem, licença e checksum em
  [FIXTURES.md](FIXTURES.md). Sem isso, dois números não são comparáveis.
- **Aquecimento descartado:** os 12 primeiros quadros rodam o pipeline inteiro
  mas ficam fora da estatística. A primeira inferência inclui carga do peso do
  disco e warmup do ultralytics — medida uma vez, ela sozinha vira o `max` do
  relatório inteiro. Sem descartar, o `max` de `yolo_epi` era **2068 ms**; com
  descarte, **86 ms**.
- **Nunca rode dois cenários em paralelo.** Eles disputam a mesma CPU e
  contaminam um ao outro. A matriz abaixo foi executada em série.
- **`espera_lock` é medido separado de `yolo_epi`.** Sem essa separação, o
  tempo parado esperando outra câmera soltar o `inference_lock` apareceria como
  custo de inferência e a conclusão sobre contenção sairia errada.

## O que este harness é, e o que não é

`scripts/bench_pipeline.py` usa **os componentes reais** — `YoloPPEDetector`,
`MediaPipePoseEstimator`, `PersonTracker`, `PersonComplianceMatcher`,
`FrameAnnotator` — na **mesma ordem** de `CameraWorker._loop`, com o mesmo
`inference_lock` compartilhado entre câmeras.

**Não** é o worker do Flask. Ficam de fora: `socketio.emit` de verdade,
`AlertStateService` (que grava no SQLite dentro do loop) e `ComplianceService`.
O estágio `serializacao` mede o `to_dict()` do payload — o custo por frame
atribuível ao preparo da emissão, não o envio. Portanto **o custo real por
frame em produção é maior que o medido aqui**; o que está medido é o custo de
visão, que é o que domina.

## Matriz — 1 câmera

Valores em **ms, p50 / p95**. `detect_every_n=3` em todos os cenários, então
os estágios de inferência têm n=100 amostras e os demais n=300.

| # | cenário | leitura | espera_lock | yolo_epi | yolo_pessoa | pose | matching | anotação | encode | serialização | fim-a-fim p50 | fim-a-fim p95 | **FPS** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** | 416, MP=false, pose on — *baseline do projeto* | 0,70 / 1,36 | — | **81,89** / 86,12 | — | 25,62 / 46,42 | 0,01 | 0,42 | 2,52 | 0,30 | 4,30 | 129,11 | **24,32** |
| **B** | 640, MP=false, pose on | 0,76 / 1,39 | — | **166,30** / 194,99 | — | 25,65 / 47,54 | 0,01 | 0,48 | 2,57 | 0,31 | 4,53 | 220,38 | **14,05** |
| **C** | 416, MP=**true**, pose on | 0,73 / 1,22 | 0,00 / 0,01 | 82,93 / 87,24 | **23,23** / 25,09 | 27,09 / 57,56 | 0,02 | 0,45 | 2,55 | 0,31 | 4,40 | 157,39 | **19,42** |
| **D** | 640, MP=**true**, pose on | 0,73 / 1,35 | 0,00 / 0,01 | 160,55 / 166,96 | **35,78** / 38,66 | 47,48 / 68,11 | 0,08 | 0,52 | 2,55 | 0,46 | 4,61 | 264,92 | **11,67** |
| **E** | 416, MP=false, **pose OFF** | 0,77 / 1,04 | — | 79,36 / 83,73 | — | — | 0,01 | 0,43 | 2,68 | 0,03 | 4,14 | 85,88 | **32,74** |
| **F** | 640, MP=true, **pose OFF** | 0,82 / 1,52 | — | 163,66 / 223,76 | 37,05 / 60,78 | — | 0,09 | 0,56 | 2,76 | 0,04 | 4,63 | 240,14 | **13,20** |
| **G** | 640, MP=true, pose on, **ONNX** | 0,79 / 1,64 | — | **213,12** / 266,89 | 60,27 / 84,69 | 49,62 / 72,49 | 0,09 | 0,60 | 2,66 | 0,49 | 5,11 | 379,97 | **8,63** |

> A, B, E, F e G foram medidos antes de `espera_lock` existir como estágio
> próprio, então nesses cinco a espera está embutida em `yolo_epi`. Com **uma**
> câmera isso é imaterial: C e D mostram `espera_lock` p50 = **0,00 ms**.

### Leitura da matriz

**A resolução domina, e é o maior botão da máquina.** 416 → 640 dobra o custo
do YOLO (81,89 → 166,30 ms, **2,03x**) e derruba o FPS de 24,32 para 14,05
(−42%). Nada mais no pipeline chega perto dessa alavanca. Confere com o
comentário já existente em `app/config.py:96-99`.

**O `fim-a-fim` p50 é enganoso se lido sozinho.** Ele fica em ~4,4 ms porque,
com `detect_every_n=3`, dois de cada três frames não rodam inferência nenhuma
— o frame mediano é barato. **O p95 é o número honesto**: 129 ms (A) a 265 ms
(D). É o p95 que a pessoa vê como travada.

**O segundo YOLO é barato perto do que resolve.** Ligar `MULTI_PERSON` custa
23,23 ms a 416 (A→C: 24,32 → 19,42 fps, −20%) e 35,78 ms a 640. Em troca, o
sistema passa a **detectar pessoas** — sem ele, a classe `Person` do Vyra não
dispara em imagem real e nenhuma conformidade é avaliada (ver
[AMBIENTE.md](AMBIENTE.md) e a seção do README sobre o modelo).

**Encode: um por frame, 2,5 ms, e não é gargalo.** Confirmado por medição e por
leitura do código (`camera_worker.py:453`): há **um único** `cv2.imencode` por
frame, e o resultado é reaproveitado por todos os consumidores MJPEG. Não há
re-encode por cliente.

**`matching`, `anotação` e `serialização` somam menos de 1 ms.** Toda a lógica
Python de associação EPI-pessoa custa 0,01–0,08 ms. Não há nada a ganhar ali.

## Custo do MediaPipe Pose, por subtração

| cenário | pose ON | pose OFF | ganho | pose p50 isolado |
|---|---|---|---|---|
| 416, MP=false (A vs E) | 24,32 fps | **32,74 fps** | **+8,43 fps (+34,7%)** | 25,62 ms |
| 640, MP=true (D vs F) | 11,67 fps | **13,20 fps** | **+1,53 fps (+13,1%)** | 47,48 ms |

A pose é o **segundo** item mais caro do orçamento, e o mais caro em termos
relativos no cenário barato: a 416 ela consome mais de um quarto do throughput.
Custa mais quando há mais gente em quadro — `POSE_PER_PERSON=true` roda até
`POSE_MAX_PEOPLE=4` inferências por frame, e o p95 (57,56 ms em C contra 27,09
de p50) mostra exatamente essa cauda.

## Escalonamento 1 → 2 câmeras: **não escala**

| cenário | 1 câmera | 2 câmeras (agregado) | por câmera | escalonamento |
|---|---|---|---|---|
| 416, MP=true (C → H) | 19,42 fps | **19,13 fps** | 9,5 + 9,5 | **0,99x** |
| 640, MP=true (D → I) | 11,67 fps | **11,84 fps** | 5,9 + 5,9 | **1,02x** |

Dobrar o número de câmeras **não aumenta o throughput agregado em nada**. Cada
câmera recebe exatamente metade.

### A contenção é o `inference_lock`, medida — não é thread do torch

| estágio | 1 câmera p50 | 2 câmeras p50 | variação |
|---|---|---|---|
| **`espera_lock`** (416) | **0,00 ms** | **133,72 ms** | — |
| `yolo_epi` (416) | 82,93 ms | 93,28 ms | +12% |
| `yolo_pessoa` (416) | 23,23 ms | 27,15 ms | +17% |
| `pose` (416) | 27,09 ms | 28,68 ms | +6% |
| **`espera_lock`** (640) | **0,00 ms** | **237,44 ms** | — |
| `yolo_epi` (640) | 160,55 ms | 171,44 ms | +7% |
| `pose` (640) | 47,48 ms | 47,52 ms | +0% |

O tempo todo que a segunda câmera perde aparece em `espera_lock`, enquanto as
etapas de inferência propriamente ditas quase não mudam (+0% a +17%,
compatível com pressão de cache/memória, não com disputa de threads).

Se fosse oversubscription de thread do torch, o custo **das inferências**
subiria substancialmente — não é o que acontece. E o valor da espera fecha a
conta: a 416, uma câmera segura o lock por `yolo_epi` + `yolo_pessoa` + `pose`
≈ 149 ms, e a outra espera 134 ms.

O lock é `monitor_service.py:74`, aplicado em `camera_worker.py:621-637`,
envolvendo YOLO **e** MediaPipe juntos. O comentário que o justifica argumenta
a partir de **GPU** ("ela já processa um kernel por vez") — raciocínio que não
se transfere para esta máquina, que não tem GPU. **Não foi alterado nesta
fase**: `camera_worker.py` está a 34% de cobertura e o loop de frame não é
exercitado por nenhum teste. Mexer nele exige caracterização antes.

## ONNX: a promessa não se confirmou nesta máquina

A documentação oficial da Ultralytics não impõe fabricante para ONNX e declara
"up to 3x CPU speedup"
([integrations/onnx](https://docs.ultralytics.com/integrations/onnx/)). Medido
aqui, com o `best.onnx` que o próprio Hexmon publica (sem exportar nada):

| | PyTorch `.pt` (D) | ONNX (G) | delta |
|---|---|---|---|
| `yolo_epi` p50 | 160,55 ms | **213,12 ms** | **+32,7%** |
| `yolo_epi` p95 | 166,96 ms | 266,89 ms | +59,8% |
| FPS | 11,67 | **8,63** | **−26,1%** |

**No Ryzen 7 5700X, o ONNX Runtime 1.29.0 foi 33% mais lento que o PyTorch**,
não 3x mais rápido. O ganho anunciado não se materializou neste hardware.

Isso ecoa o que já havia acontecido com o OpenVINO (rejeitado no commit
`2d74e96` por ser mais lento no worker real). Registrado como **medição, não
como adoção**: `onnxruntime` foi instalado só no venv local para este
benchmark e **não** entrou no `requirements.txt`.

## Hipóteses testadas e derrubadas

**O `frame.copy()` de `video_stream.py:198` não é gargalo.** Medido isolado:
**0,136 ms** por frame de 1280x720. A 12 fps são 1,6 ms por segundo de
operação — ruído. Continua sendo código morto (nenhum leitor de
`latest_frame()` em `app/`), mas removê-lo é limpeza, **não** otimização, e não
deve ser vendido como ganho de performance.

**O segundo YOLO não roda quando `MULTI_PERSON_DETECTION=false`.** Confirmado
no código e na medição: A e B não têm estágio `yolo_pessoa`.

## Ordem de ataque sugerida para a Fase 1

Por p95 medido, decrescente. **Nenhum destes foi aplicado.**

1. **Resolução de inferência** — a maior alavanca isolada (2,03x entre 416 e
   640). Envolve trade-off de precisão: a 416 o modelo perde capacete que acha
   a 640, e o Vyra foi treinado a 640 (`args.yaml`).
2. **`inference_lock` cobrindo YOLO + pose de todas as câmeras** — 134 a 237 ms
   de espera pura com 2 câmeras. É o item que decide se multi-câmera escala.
3. **MediaPipe Pose** — 13% a 35% do throughput, dependendo do cenário.
4. **`active_alerts` emitido a cada frame**, fora do `TELEMETRY_HZ`
   (`alert_state_service.py:153`) — não medido aqui (o harness não emite), mas
   confirmado por leitura de código.

Nada acima entra sem: teste de caracterização verde **antes**, mudança mínima,
`pytest` verde e re-bench com delta registrado neste arquivo.
