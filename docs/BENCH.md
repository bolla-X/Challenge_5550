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


---

# Pós-Fase-1 (commit `f379910`)

Mesma máquina, mesma fixture, mesmo aquecimento de 12 quadros descartado.
AMD Ryzen 7 5700X, CPU-only, `torch 2.14.0+cpu`, Windows 10.

> **Estes são números de PIPELINE, não do worker do Flask.** `socketio.emit`,
> `AlertStateService` (que grava no SQLite dentro do loop) e
> `ComplianceService` ficam **fora** do harness. O custo real em produção é
> maior que o medido aqui. Esta ressalva vale para a tabela do baseline
> também, e precisa aparecer no slide.

## Por estágio, baseline vs pós-Fase-1 (p50 em ms)

| cenário | leitura | espera_lock | yolo_epi | yolo_pessoa | pose | matching | anotação | encode | serial. | fim-a-fim p95 | **FPS** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A baseline `73edc00` — 416, MP=false | 0,70 | — | 81,89 | — | 25,62 | 0,01 | 0,42 | 2,52 | 0,30 | 129,11 | 24,32 |
| **A' pós-F1 `f379910`** — 416, MP=false | 0,72 | 0,00 | 84,07 | — | 25,80 | 0,01 | 0,42 | 2,34 | 0,30 | 129,65 | **24,04** |
| C baseline `73edc00` — 416, MP=true | 0,73 | 0,00 | 82,93 | 23,23 | 27,09 | 0,02 | 0,45 | 2,55 | 0,31 | 157,39 | 19,42 |
| **C' pós-F1 `f379910`** — 416, MP=true | 0,73 | 0,00 | 83,25 | 22,75 | 26,76 | 0,02 | 0,45 | 2,47 | 0,31 | 156,89 | **19,56** |
| H baseline `73edc00` — 2 câmeras, 416, MP=true | 1,02 | 133,72 | 93,28 | 27,15 | 28,68 | 0,03 | 0,63 | 3,52 | 0,57 | 331,79 | 19,13 |
| **H' pós-F1 `f379910`** — 2 câmeras, 416, MP=true | 1,01 | 127,80 | 89,73 | 26,31 | 28,02 | 0,03 | 0,64 | 3,50 | 0,57 | 317,34 | **19,87** |

Delta agregado: **A −1,1% · C +0,7% · H +3,9%**.

## Por que o delta é ~zero, e por que isso está certo

Nenhuma mudança da Fase 1 tocou o pipeline de visão, e o número confirma isso:
o re-bench serve como **prova de não-regressão**, não como vitrine de ganho.

O ganho da Fase 1 vive num estágio que **este harness não mede por
construção** — `AlertStateService`, que grava no SQLite dentro do loop de
captura. Medido à parte, com o caminho de alerta incluído, A/B no mesmo
processo sobre a mesma fixture:

| | alertas criados | parede | FPS | emits `created`/`resolved` |
|---|---|---|---|---|
| Antes (histerese conta iteração) | 76 | 10,6 s | 19,77 | 152 / 152 |
| **Depois (histerese conta detecção)** | **26** | 9,7 s | **21,58** | 52 / 52 |

**−66% de alertas e +9,2% de FPS**, porque são 100 escritas a menos no SQLite
e 200 emissões a menos por 7 segundos de vídeo.

`MULTI_PERSON_DETECTION=true` (P0) também não aparece no delta: o harness
recebe o modo por flag (`--multi-person`), não pelo `.env`. O custo dele já
estava medido no baseline — é a diferença A→C, **−20% de FPS**.

## P2 — custo do Pose: medido, e NÃO aplicado

A alavanca é real: pela subtração do baseline, o Pose consome **+34,7%** do
throughput no cenário A. A mudança proposta era trocar `static_image_mode` de
`True` para o modo de stream no caminho por pessoa.

**Documentação oficial**, https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/pose.md#static_image_mode :

> "If set to `false`, the solution treats the input images as a video stream.
> It will try to detect the most prominent person in the very first images, and
> upon a successful detection further localizes the pose landmarks. In
> subsequent images, it then simply tracks those landmarks without invoking
> another detection until it loses track, on reducing computation and latency.
> If set to `true`, person detection runs every input image, **ideal for
> processing a batch of static, possibly unrelated, images**. Default to
> `false`."

Medição em 21 recortes de pessoa reais extraídos da fixture, uma instância
MediaPipe por modo, `model_complexity=0`:

| modo | p50 | média | poses encontradas | veredito "caído" |
|---|---|---|---|---|
| `static_image_mode=True` (atual) | 34,10 ms | 35,48 ms | 11/21 | 0 |
| `static_image_mode=False` | **15,14 ms** | 22,52 ms | 15/21 | 0 |

**2,25x mais rápido no p50.** E ainda assim a mudança não foi aplicada:

1. A doc oficial descreve `True` como o modo **para lotes de imagens
   possivelmente não relacionadas** — que é exatamente o que
   `estimate_for_people` alimenta: recortes de pessoas **diferentes**,
   alternadamente, na mesma instância. O comentário em
   `app/vision/pose_estimator.py:29-35` já previa isso ("alimenta-lo com
   recortes de pessoas diferentes, alternadamente, corrompe a associacao").
2. As 4 poses extras encontradas em modo stream **não são prova de acurácia**.
   O aumento é igualmente compatível com "detectou melhor" e com "arrastou
   landmarks do recorte anterior" — a falha que a doc descreve. Não tenho como
   distinguir as duas com esta medição.
3. O veredito de queda ficou em 0 nos dois modos, mas **a fixture não contém
   queda**, então esse empate não exercita o caso discriminante. Trocar o modo
   com base nele seria esconder risco atrás de FPS.

**O caminho que dá os dois** (correção semântica e o 2,25x): uma instância
MediaPipe **por pessoa rastreada**, cada uma em modo de stream, com despejo
por track que desaparece. Aí cada instância só vê a própria pessoa, e o
tracking passa a ser semanticamente válido. É contido a
`app/vision/pose_estimator.py`, mas move o ponto de injeção dos 8 testes de
`tests/test_pose_estimator_crop.py` e mexe em código relevante para
segurança — exige caracterização própria, não uma troca de flag em dois dias.
Fica registrado como o próximo passo da Fase 2, com o número que o justifica.


---

# Fase 2 — fonte de rede: abertura, FPS e o fio do LLM

Mesma máquina, mesma fixture, mesmo aquecimento de 12 quadros descartado.
Tudo abaixo foi medido contra um **servidor RTSP local com usuário e senha**
(mediamtx v1.21.0 + publicador ffmpeg), porque **não há rota desta máquina para
a rede da planta** — ver [DEMO.md](DEMO.md) para o comando e a declaração de
não-verificação.

## Abrir uma fonte de rede morta custava 34 s por tentativa

Achado pelo servidor local, não por leitura de código: com o mediamtx morto,
cada tentativa de reabrir travava o worker por ~30 s, e o log do OpenCV
despejava uma exceção do backend `CAP_IMAGES` sobre a URL RTSP — erro que não
tem relação com a causa e manda quem diagnostica atrás de padrão de nome de
arquivo.

Abrindo `rtsp://...@localhost:554/...` sem nada escutando na porta:

| como | abriu | tempo |
|---|---|---|
| `CAP_ANY`, sem params — **comportamento anterior** | False | **34.319 ms** |
| `CAP_FFMPEG`, sem params | False | 30.054 ms |
| `CAP_FFMPEG`, `cap.set()` antes do `open()` | False | 30.045 ms |
| `CAP_FFMPEG`, `params=[OPEN_TIMEOUT_MSEC 3000]` | False | **3.037 ms** |
| `OPENCV_FFMPEG_CAPTURE_OPTIONS=timeout;5000000` | False | 30.060 ms |

**11,3x.** Duas coisas se aprendem aqui:

1. Os 4,3 s entre `CAP_ANY` e `CAP_FFMPEG` são o OpenCV tentando outros
   backends depois de o FFMPEG falhar. Fonte de rede agora abre com
   `CAP_FFMPEG` explícito.
2. **`cap.set()` não funciona, e a doc oficial diz por quê.** OpenCV 4.11.0,
   `modules/videoio/include/opencv2/videoio.hpp`:

   > `CAP_PROP_OPEN_TIMEOUT_MSEC=53, //!< (**open-only**) timeout in
   > milliseconds for opening a video capture (applicable for FFmpeg and
   > GStreamer back-ends only)`

   "open-only" significa que precisa ir **na abertura**, pela sobrecarga
   `VideoCapture(const String& filename, int apiPreference, const
   std::vector<int>& params)` — documentada como pares
   `(paramId_1, paramValue_1, ...)`. A variável de ambiente
   `OPENCV_FFMPEG_CAPTURE_OPTIONS` também não resolveu: o teto de 30 s é o
   callback de interrupção do próprio OpenCV, não o `timeout` do FFmpeg.

Efeito medido no fim a fim: o passo "sem religar, cai em modo fixture" da prova
de ciclo saiu de **estourar o limite de 90 s** para concluir em **22 s**. E o
tempo até o modo fixture assumir contra um endereço real da planta
(`10.14.22.97`, sem rota):

| `RTSP_MAX_TENTATIVAS` | tempo até `modo=fixture` |
|---|---|
| 1 | 5,3 s |
| 3 | 17,0 s |
| 5 (default) | 33,2 s |

## FPS: fonte RTSP local vs arquivo local, 1 e 2 câmeras

`scripts/bench_pipeline.py` ganhou `--fonte` para medir as duas com o **mesmo
harness** — dois harnesses diferentes não produzem números comparáveis.
`imgsz=416`, `MULTI_PERSON=true`, `detect_every_n=3`, em série.

| cenário | leitura p50 | leitura p95 | espera_lock p50 | FPS/câmera | agregado |
|---|---|---|---|---|---|
| 1 câm, arquivo, **CPU livre** | 0,79 | 1,32 | — | 17,99 | 17,99 |
| 1 câm, arquivo, publicador ativo | 0,93 | 1,89 | 0,00 | 13,67 | 13,67 |
| 1 câm, **RTSP local** | 2,19 | **109,32** | 0,01 | 12,44 | 12,44 |
| 2 câm, arquivo, CPU livre | 1,09 | 2,16 | 160,07 | 8,02 + 8,01 | 16,02 |
| 2 câm, arquivo, publicador ativo | 1,10 | 2,09 | 156,79 | 8,32 + 8,32 | 16,63 |
| 2 câm, **RTSP local** | 2,37 | **207,00** | 133,96 | 7,83 + 6,96 | 13,93 |

**O confundidor, declarado antes da conclusão.** O publicador ffmpeg encoda
H.264 1280x720@30 na **mesma CPU**. Isolado: 17,99 → 13,67 fps, ou seja
**−24,0% só pelo publicador**. Por isso as comparações válidas são entre linhas
de mesma carga de fundo, e nenhum número desta tabela deve ser comparado com a
tabela do baseline (que rodou com a CPU livre).

- **Custo da fonte RTSP, mesma carga:** 1 câmera **−9,0%** (13,67 → 12,44);
  2 câmeras **−16,2%** no agregado (16,63 → 13,93).
- **O p50 engana; o p95 é o número.** `leitura` p50 sobe pouco (0,93 → 2,19 ms)
  mas o p95 salta **58x** (1,89 → 109,32 ms), com máximo de 2.231 ms em 2
  câmeras. É a fonte de rede esperando o próximo pacote — cauda que arquivo
  local não tem, e que na planta será outra (desconhecida).
- **`espera_lock` continua sendo o item que decide multi-câmera**, exatamente
  como no baseline: 134 a 160 ms de espera pura com 2 câmeras, independente da
  fonte. Trocar a fonte não mexe nisso.

## O fio do LLM não custa FPS

`scripts/bench_llm_worker.py` atravessa o `CameraWorker._loop` **de verdade** —
diferente de `bench_llm.py`, que mede o desenho do serviço a partir de um
pipeline próprio. Aqui entram `AlertStateService` (que grava no SQLite dentro
do loop), `ComplianceService`, anotação e serialização: tudo que este harness
de pipeline declara deixar de fora. Por isso o FPS é menor que o da matriz
acima, e a comparação que vale é **LLM on contra LLM off nesta mesma tabela**.

Provedor simulando 1500 ms de latência, de propósito: com a API real o número
dependeria de rede, cota e humor do serviço.

| execução | LLM off | LLM on | delta |
|---|---|---|---|
| 1 (com perfil por etapa ligado) | 17,32 | 17,71 | **+2,3%** |
| 2 | 15,74 | 15,47 | −1,7% |
| 3 | 17,03 | 16,65 | −2,2% |

**Dentro do ruído.** O que sustenta essa leitura, e não só a média:

- o **mesmo** cenário varia 15,7 a 17,8 fps entre execuções;
- o controle **off/off** (mesmo cenário duas vezes, mesma ordem) deu **+0,6%**,
  então posição no processo não explica delta;
- `submeter()` custou **9 a 13 µs** de p50 (máximo 0,38 ms, a primeira chamada,
  que inclui criar a thread) — batendo com os 11 µs de
  [SPRINT3.md](SPRINT3.md);
- o perfil por etapa não mostra **estágio nenhum** crescendo com o LLM ligado
  (`yolo` 40,4 → 31,6 ms; `pose` 23,7 → 21,7 ms — a execução com LLM foi, se
  algo, mais rápida).

**Honestidade sobre um outlier:** a **primeira** execução deste bench deu
**−37,2%** e não reproduziu em nenhuma das três seguintes. A causa é **NÃO
VERIFICADA** — a suspeita é carga residual da máquina, porque o bench rodou
logo depois do servidor RTSP e do publicador ffmpeg, mas não tenho prova. Fica
registrado porque um relatório que só mostra a execução conveniente não é
auditável.


---

# Fase 5 — duas câmeras em modo fixture

O cenário do demo, que nunca havia rodado: todo o teste de fallback anterior foi
com **uma** câmera. Duas câmeras em endereços da faixa da planta (sem rota desta
máquina), ambas caindo em fixture, ambas decodificando o **mesmo** arquivo em
loop, com o `inference_lock` compartilhado.

Worker REAL (`MonitorService` + `CameraWorker`), `imgsz=416`,
`MULTI_PERSON=true`, `detect_every_n=3` — cenário C, mas com
`AlertStateService`, `ComplianceService`, anotação e serialização incluídos, que
o harness de pipeline deixa de fora.

| | 60 s | 180 s |
|---|---|---|
| câmera 1 | 7,69 fps | 6,45 fps |
| câmera 2 | 7,69 fps | 6,45 fps |
| **agregado** | **15,38 fps** | **12,89 fps** |
| voltas na fixture, por câmera | 2,2 | 5,5 |

**Contra 1 câmera:** o número comparável não é o 19,56 fps do cenário C (harness
de pipeline), e sim o ~17 fps que o mesmo worker real entrega com uma câmera
(`scripts/bench_llm_worker.py`, Fase 4). Duas câmeras entregam 15,4 agregado
contra ~17 de uma — ou seja **dobrar as câmeras não dobra nada**, cada uma
recebe metade. Confirma a conclusão do baseline, agora no worker real e na
fonte que o demo usa.

**Paralelismo real, e divisão justa.** Em 48 janelas de 5 s somadas nas duas
execuções, **nenhuma** teve uma câmera parada (< 0,5 fps), e a razão
`cam1/cam2` ficou entre 0,85 e 1,17 — quase sempre 1,00 exato. Uma não trava a
outra; o lock alterna.

**Sem vazamento em 180 s** (medição a partir de t=5 s, para excluir o degrau de
inicialização):

| | inclinação | 1º terço → último terço |
|---|---|---|
| handles | **−1,69 / min** | 858,2 → 854,8 |
| threads | **−0,78 / min** | 111,1 → 109,5 |
| RSS | +2,48 MB/min | 1120,2 → 1124,0 MB |

Handles e threads **caem**. O RSS deriva +2,48 MB/min, mas a amplitude de ruído
entre amostras é **31,1 MB** — a deriva não é distinguível de plano nesta
janela. Um teste mais longo seria necessário para descartar tendência lenta, e
está fora do escopo desta fase.

A premissa de que "o loop reabre o arquivo a cada volta" **não se aplica**: com
`em_loop=True` o `VideoStream` rebobina via `CAP_PROP_POS_FRAMES` e retorna sem
tocar em `release()`/`open()`. É o que mantém os handles planos apesar das 5,5
voltas por câmera.

**Tempo até as duas assumirem a fixture: 12,6 s** com `RTSP_MAX_TENTATIVAS=1`,
contra 5,3 s de uma só — cada câmera paga o teto de abertura de 5 s e os dois
`open()` não se sobrepõem.

**Variação entre execuções é grande:** 15,38 e 12,89 fps agregados para o mesmo
cenário. Faixa, não ponto.
