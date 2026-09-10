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


---

# Fase 6 — perfil Dahua na bancada, e a latência que ninguém tinha medido

Mesma máquina, mesma fixture, mesmo aquecimento de 12 quadros descartado.
AMD Ryzen 7 5700X, CPU-only, `torch 2.14.0+cpu`, Windows 10, Python 3.11.9.

O que muda nesta fase: até aqui o servidor RTSP local publicava a fixture
**como ela é** — 1280x720, H.264 `ultrafast`. Isso mede o custo de uma fonte de
rede, mas não o custo da fonte que a planta vai entregar. Aqui o publicador
passa a **imitar o perfil de uma Dahua**, e aparece uma segunda pergunta que o
harness de throughput não sabe fazer: **quão velho é o frame que está na tela?**

## O perfil imitado, e o que nele é escolha e não medição

Os parâmetros abaixo são **típicos** de Dahua, não lidos das câmeras da planta
— não há rota até elas. São premissa declarada, e o passo (a) do runbook de
campo existe justamente para conferi-los na sexta:

| | substream (`subtype=1`) | stream principal (`subtype=0`) |
|---|---|---|
| resolução | **704x576** (D1, 4:3) | **1920x1080** (16:9) |
| taxa | 15 fps | 25 fps |
| bitrate | 512 kbps CBR | 4096 kbps CBR |
| GOP (I-frame) | 30 (2x fps) | 50 (2x fps) |
| perfil H.264 | Main, sem B-frame | Main, sem B-frame |

```bash
# substream: o que o cadastro usa por padrao
./ffmpeg.exe -re -stream_loop -1 -i tests/fixtures/bench.mp4 -an \
  -vf "scale=704:576,fps=15" \
  -c:v libx264 -profile:v main -preset veryfast -bf 0 \
  -g 30 -keyint_min 30 -sc_threshold 0 \
  -b:v 512k -maxrate 512k -bufsize 1024k -pix_fmt yuv420p \
  -f rtsp -rtsp_transport tcp -pkt_size 1200 \
  "rtsp://usuario:senha@localhost:8554/cam/realmonitor"
```

Dois detalhes que custaram tempo e ficam registrados:

- **`-pkt_size 1200`.** Sem ele o mediamtx loga `RTP packets are too big
  (1460 > 1440), remuxing them into smaller ones` e o decoder do leitor despeja
  `error while decoding MB ... bytestream -9` em rajada. Não é ruído cosmético:
  é frame corrompido chegando no pipeline.
- **`-preset veryfast`, não `ultrafast`.** A pergunta do substream é "a imagem
  fica boa o bastante para detectar EPI?", e `ultrafast` a 512 kbps degrada
  muito além do que o encoder de uma câmera degradaria. O custo é que o
  publicador consome mais CPU **desta mesma máquina** — confundidor declarado
  abaixo.

Conferido com a própria sonda de campo (`scripts/sondar_cameras.py`), que é o
que vai rodar na planta: `704x576`, **15,00 fps declarados e 14,97 medidos**.

## FPS: 1 e 2 câmeras no perfil substream

`imgsz=416`, `MULTI_PERSON=true`, `detect_every_n=3`, em série.

| cenário | leitura p50 | espera_lock p50 | yolo_epi p50 | FPS/câmera | agregado |
|---|---|---|---|---|---|
| 1 câm, **RTSP substream** | 0,42 | 0,00 | 120,26 | 14,71 | **14,71** |
| 2 câm, **RTSP substream** | 0,60 | **221,16** | 161,24 | 5,80 + 5,80 | **11,60** |
| 1 câm, arquivo substream, CPU livre | 0,39 | 0,00 | 123,52 | 12,81 | 12,81 |
| 2 câm, arquivo substream, CPU livre | 0,58 | **206,33** | 142,76 | 6,45 + 6,45 | 12,90 |

**A previsão para a planta, e o quanto ela vale.** Uma câmera entregou
**14,71 fps** e duas **11,60 agregado**. Isso bate com o que a Fase 5 já media
em modo fixture (15,38 e 12,89 com 2 câmeras): trocar a fonte de arquivo para
RTSP no perfil Dahua **não mudou a ordem de grandeza**. O gargalo continua
sendo a inferência serializada pelo `inference_lock` — `espera_lock` p50 de
**221 ms** com 2 câmeras, exatamente o mesmo fenômeno do baseline.

**Variação entre execuções é grande e precisa ser dita:** o cenário "1 câm
arquivo substream" deu 12,81 / 15,76 / 14,76 em três execuções do **mesmo**
comando. Trate tudo aqui como faixa de 13 a 16 fps para uma câmera, não como
ponto.

## O substream NÃO sai mais barato — e a razão é o aspecto, não a resolução

Este é o achado que contradiz o motivo pelo qual o default virou `subtype=1`.

Mesmo cenário, mesmo `imgsz=416`, mudando só a fonte (p50 em ms, uma câmera,
CPU livre):

| estágio | SUB 704x576 | MAIN 1920x1080 | delta |
|---|---|---|---|
| leitura | 0,39 | 1,86 | −79% |
| **yolo_epi** | **123,52** | **92,42** | **+34%** |
| **yolo_pessoa** | **33,37** | **26,72** | **+25%** |
| pose | 24,49 | 32,26 | −24% |
| anotação | 0,37 | 0,87 | −58% |
| encode | 1,28 | 5,71 | −78% |
| serialização | 0,04 | 0,51 | −92% |
| **ms/frame ponderado** | **62,56** | **59,44** | **+5%** |
| FPS medido | 12,81 | 15,17 | |

O stream principal tem **6,7x mais pixels** e mesmo assim custa **menos** por
frame. Não é erro de medição: `YOLO_IMGSZ` fixa o lado maior da entrada da
rede, então **a resolução da fonte não chega ao modelo — o aspecto chega.** O
letterbox do ultralytics leva o lado maior a 416 e arredonda o menor para
múltiplo de 32 (o stride):

- 704x576 (4:3, D1) → tensor **416x352** = 146k px
- 1920x1080 (16:9)  → tensor **416x256** = 106k px, **38% menor**

Isolado, com a **mesma cena** e o mesmo lado maior, em medições **intercaladas**
A/B/A/B (n=40 cada, para cancelar deriva térmica e carga de fundo):

| entrada | tensor | yolo_epi p50 | p95 |
|---|---|---|---|
| 704x576 — 4:3 | 416x352 (146k px) | **106,94 ms** | 131,11 |
| 704x396 — 16:9 | 416x256 (106k px) | **83,94 ms** | 108,30 |

**O 4:3 custa +27,4% de inferência.** A primeira tentativa mediu em bloco
(todas as amostras de A, depois todas as de B) e o ruído da máquina foi de
±18% — maior que o efeito. Intercalar foi o que tornou o número legível; fica
registrado como método, não como detalhe.

**Consequência prática:** o que o substream economiza (decode, anotação,
encode: ~6 ms/frame) é menor que o que ele acrescenta em inferência (+31 ms em
1 de cada 3 frames = ~10 ms/frame amortizados). Por isso o FPS entre os dois
perfis é **empate dentro do ruído** — medianas de 3 execuções: substream 14,76,
principal 15,17.

**A ressalva que impede generalizar:** isto vale porque o substream imitado é
**4:3**. Se o substream da câmera da planta for 16:9 (640x360, 704x396), o
efeito desaparece e o substream volta a ser estritamente mais barato. O passo
(a) do runbook **reporta a resolução real de cada câmera nos dois subtypes**, e
é esse dado que decide.

## Latência: o frame na tela é de 13 segundos atrás

`scripts/bench_latencia.py`. Cada frame sai do publicador com um número de
sequência gravado em blocos preto/branco na primeira faixa de pixels; quem lê
decodifica e consulta a tabela de publicação. Publicador e leitor são o mesmo
processo, então não há relógio a sincronizar. Amostra cujo checksum não fecha é
**descartada** (a anotação desenha caixas por cima), e a taxa de descarte sai no
relatório — descarte alto invalidaria a medição e precisa aparecer.

Dois trechos, medidos em fases separadas: **FONTE** (publicação → o
`VideoStream` de produção devolver o frame) e **DASHBOARD** (publicação → o
mesmo frame sair pelo MJPEG do Flask, por HTTP de verdade, na rota por câmera
que o `camera-grid.tsx` pede).

| fonte | FONTE p50 | deriva | DASHBOARD p50 | deriva |
|---|---|---|---|---|
| 15 fps | 2.336 ms | −1 ms/s | 13.534 ms | **+135 ms/s** |
| 8 fps | 4.378 ms | −5 ms/s | 12.645 ms | **+35 ms/s** |
| 6 fps, `TARGET_FPS=30` | 5.836 ms | −3 ms/s | 12.476 ms | **−1 ms/s** |

**A deriva é o número que importa, não o p50.** Atraso constante é buffer e tem
teto; atraso que cresce é **fila**, e aí não existe número para relatar —
existe uma rampa. A 15 fps o dashboard ganha **+135 ms de atraso por segundo**,
isto é **+8,1 s a cada minuto**: depois de cinco minutos de apresentação, o
vídeo na tela é de minutos atrás. O script imprime esse aviso sozinho.

**A causa é aritmética, e é a única parte que transfere direto para a planta:**
o worker consome ~10 a 14 fps (medido ao vivo contra esta fonte: **9,8 fps**,
pelo próprio diagnóstico de tela) e a fonte produz 15. A diferença enfileira. A
cura é folga — fonte mais lenta que o pipeline —, e a última linha da tabela
mostra a deriva zerando quando ela existe.

### `CAP_PROP_BUFFERSIZE=1` não funciona em RTSP, e o comentário do código diz que sim

`video_stream.py` pede buffer de 1 frame, e o comentário afirma: *"Com 1,
`read()` sempre pega o frame mais recente e o atraso não acumula."* Medido
contra o servidor local, abrindo o stream e **parando de ler por 10 s**:

| | `set()` retornou | `get()` | frames instantâneos ao voltar a ler |
|---|---|---|---|
| pedindo `BUFFERSIZE=1` | **False** | 0.0 | **104** |
| sem pedir nada | — | — | **104** |

O backend FFMPEG **recusa** a propriedade, e o comportamento é idêntico com e
sem o pedido: 104 frames saem de enfiada antes de a leitura voltar a bloquear.
Não há descarte de frame velho em lugar nenhum do caminho. **O pedido é um
no-op em fonte de rede** — vale para webcam, não para RTSP.

Não foi corrigido nesta fase, e de propósito: mexer no `read()` do
`VideoStream` na semana do demo, com `camera_worker.py` a 34% de cobertura e o
loop de frame sem teste, é exatamente o tipo de mudança que a Fase 1 já
recusou. O caminho, quando houver caracterização: `grab()` em laço curto
descartando sem decodificar, e `retrieve()` só no último.

### Quanto do número absoluto é artefato da bancada

O p50 do FONTE **não é previsão para a planta**, e a decomposição mostra por
quê:

- **É contagem de frames, não tempo.** 2.336 ms a 15 fps, 4.378 a 8 fps e 5.836
  a 6 fps dão **exatamente 35 frames nos três casos**. Atraso de rede seria
  constante em segundos; este é constante em quadros, o que aponta para fila na
  cadeia local (publicador → mediamtx → demuxer), não para latência de rede.
- **2,0 s eram do meu encoder.** O `-preset veryfast` do x264 usa
  `rc-lookahead=40` por padrão e o publicador segurava os frames antes de
  emitir: com `-rc-lookahead 0` o FONTE caiu de **4.337 para 2.337 ms**. Uma
  Dahua tem encoder de hardware, que emite quadro a quadro. O script passa
  `-rc-lookahead 0` por padrão desde então.
- **Não é o bitrate.** 512 kbps e 4096 kbps deram **3.003 ms** os dois.

Portanto: **MEDIDO** que existe fila e que ela cresce quando a fonte é mais
rápida que o pipeline; **NÃO MEDIDO** quanto de atraso absoluto a Dahua real vai
somar. O que a planta acrescenta — buffer do encoder da câmera, MTU e perda da
rede industrial, switch — não existe em `localhost`.

## Como reproduzir

```bash
python scripts/fetch_fixtures.py
# 1. mediamtx no ar (docs/DEMO.md) e o publicador de perfil acima

# 2. throughput, 1 e 2 cameras
python scripts/bench_pipeline.py --imgsz 416 --multi-person \
  --fonte "rtsp://usuario:senha@localhost:8554/cam/realmonitor?channel=1&subtype=1"
python scripts/bench_pipeline.py --imgsz 416 --multi-person --cameras 2 \
  --fonte "rtsp://usuario:senha@localhost:8554/cam/realmonitor?channel=1&subtype=1"

# 3. latencia (o script sobe o proprio publicador e o proprio Flask)
python scripts/bench_latencia.py --ffmpeg ./ffmpeg.exe \
  --url "rtsp://usuario:senha@localhost:8554/cam/realmonitor"
```


---

# Fase 7 — o descarte de frame atrasado: antes e depois

Mesma máquina, mesmo servidor RTSP local no perfil Dahua (704x576, 15 fps,
512 kbps), **mesma metodologia** da Fase 6: carimbo de sequência no frame,
`-rc-lookahead 0` no publicador, duas fases separadas.

O que mudou no código: `VideoStream._ler_do_capture` passa a descartar frame
atrasado **em fonte de rede** — `grab()` em laço (avança sem decodificar),
`retrieve()` só no último. Arquivo e webcam ficam de fora (ver a docstring do
método e os testes de contraprova em `tests/test_video_stream.py`).

## Latência: 13,5 s → 2,55 s, e a deriva zerou

| | ANTES (Fase 6) | DEPOIS, 40 s | DEPOIS, 120 s |
|---|---|---|---|
| FONTE p50 | 2.336 ms | 2.336 ms | 2.336 ms |
| FONTE deriva | −1 ms/s | −0 ms/s | −0 ms/s |
| **DASHBOARD p50** | **13.534 ms** | **2.553 ms** | **2.550 ms** |
| DASHBOARD p95 | 17.306 ms | 2.681 ms | **2.623 ms** |
| DASHBOARD max | 17.873 ms | 18.169 ms | **2.953 ms** |
| **DASHBOARD deriva** | **+135 ms/s** | −48 ms/s | **−0 ms/s** |
| pipeline + HTTP (p50 − p50) | 11.198 ms | 217 ms | **214 ms** |
| amostras descartadas (checksum) | 80 | 0 | 0 |

**O número que decide é a deriva, e ela zerou.** Antes o atraso crescia
+135 ms/s — 8,1 s a cada minuto, sem teto: depois de cinco minutos de
apresentação a tela mostrava vídeo de minutos atrás. Agora fica plano.

**A deriva de −48 ms/s da janela de 40 s não é ruído: é a fila ENCOLHENDO.**
Enquanto o worker sobe (carga dos dois pesos YOLO + MediaPipe), a fonte
continua publicando e o backlog se forma; com o descarte, o worker drena esse
backlog e o atraso cai até o piso. É por isso que aquela execução tem `max` de
18,2 s — é a primeira amostra, antes de drenar. Na janela de 120 s a parte
drenada pesa menos e a deriva aparece como **−0 ms/s**, com `max` de 2.953 ms:
o piso, não uma rampa. O aviso do script passou a distinguir os dois sinais —
fila crescendo é ATENÇÃO, fila drenando é NOTA.

**O trecho `pipeline + HTTP` caiu 52x** (11.198 → 214 ms). Era ali que a fila
vivia: o worker lia frames cada vez mais velhos do buffer do decoder. Os
214 ms restantes são o pipeline de visão mais o `time.sleep(1/TARGET_FPS)` do
gerador de MJPEG, e são o que se espera.

**O FONTE não mudou, e isso está certo.** Aqueles 2.336 ms constantes (exatos
35 frames) vivem **acima** do leitor — na cadeia publicador → mediamtx →
demuxer da bancada. Nenhum descarte no leitor alcança isso, e a Fase 6 já
atribuiu esse número a artefato de bancada, não à planta. O que o descarte
conserta é a fila do lado de cá, que é a que crescia.

## FPS: sem regressão distinguível do ruído

`scripts/bench_pipeline.py` **não passa por `VideoStream`** (abre a fonte
direto), então ele mede o pipeline de visão sem tocar no código que mudou —
serve como controle de não-regressão do resto:

| cenário | Fase 6 | Fase 7 |
|---|---|---|
| 1 câm, RTSP perfil Dahua | 14,71 fps | **16,57 fps** |
| 2 câm, RTSP perfil Dahua | 11,60 agregado | **15,01 agregado** |

Para medir o efeito real do descarte é preciso o **worker de verdade**, que é
quem usa o `VideoStream`. A/B **intercalado** no mesmo processo e na mesma
máquina (liga/desliga `_descartar_atrasados`, duas repetições de cada, 45 s
por execução):

| | execução 1 | execução 2 | média |
|---|---|---|---|
| SEM descarte (comportamento antigo) | 6,30 fps | 8,60 fps | 7,45 |
| COM descarte (o fix) | 7,10 fps | 7,00 fps | 7,05 |

**−5,4% de média, e isso está dentro do ruído:** o cenário SEM descarte
sozinho variou de **6,30 a 8,60 fps** (36% de amplitude) entre duas execuções
idênticas. Um delta de 5% medido contra ruído de 36% não sustenta "custou FPS"
nem "não custou nada" — o que se pode afirmar é que **não há regressão
distinguível**, e que o custo teórico (alguns `grab()` a mais por leitura, sem
decode) é pequeno perto de um frame de inferência.

O que NÃO se pode dizer, e quase foi dito: que caiu de 9,8 para 8,0 fps. Esses
dois números vieram de execuções em sessões diferentes, com carga de fundo
diferente. Só o A/B intercalado responde a essa pergunta.

## Modo fixture: continua lendo todos os frames

Contraprova executada com a fixture real (210 quadros) pelo `VideoStream` de
produção, pedindo 240 leituras para atravessar a virada do loop:

```
descarte ligado nesta fonte? False   (arquivo nao entra no caminho de rede)
frames do arquivo: 210
lidos com sucesso: 240  | leituras que falharam (a virada): 1
```

Uma única falha, que é a leitura que bate no fim antes de rebobinar —
comportamento documentado e coberto por
`test_fim_de_arquivo_em_loop_rebobina_em_vez_de_falhar`. Nenhum frame pulado.


---

# Fase 8 — cenário "USB local": webcam física, e as duas fontes convivendo

Hardware: **Logi Webcam C920e**, índice 0, `640x480`. Mesma máquina de sempre.
Números **separados** dos de fixture e dos de RTSP de propósito: é outra fonte,
com outro custo e outro comportamento de buffer.

> ⚠️ **A cena estava VAZIA e isso enviesa o FPS para cima.** A lente da C920e
> estava obstruída durante toda esta medição: a câmera abre, entrega frame a
> 14,39 fps, e a imagem é **preta** (média de pixel 0,02, máximo 3–8, constante
> por 6 s, idêntico no CAP_DSHOW e no CAP_MSMF; dispositivo sem erro no
> gerenciador e consentimento do Windows em `Allow` nas duas chaves). Sem
> objeto na cena o YOLO não produz detecção, o NMS fica barato e o
> `estimate_for_people` não roda por pessoa. **Trate o FPS de USB abaixo como
> teto, não como o que uma cena real entrega.**

## Descoberta

`GET /api/cameras/discover?max_index=3` encontrou **um** dispositivo:

| índice | disponível | resolução |
|---|---|---|
| 0 | sim | 640x480 |
| 1, 2, 3 | não | — |

Backend importa, e o projeto já escolhe o certo (`capture_api` → `CAP_DSHOW`
para `int` no Windows). Medido abrindo o índice 0:

| backend | abriu | resolução | fps declarado | tempo de abertura |
|---|---|---|---|---|
| **CAP_DSHOW** (o usado) | sim | 640x480 | **0,00** | **2,52 s** |
| CAP_MSMF | sim | 640x480 | 30,00 | 10,22 s |
| CAP_ANY | sim | 640x480 | 30,00 | 9,46 s |

**O DirectShow abre 4x mais rápido** — confirma a escolha que já estava no
código. Em compensação ele **não reporta FPS** (`0,00`), o que torna o
declarado inútil em USB e o medido obrigatório. Medido pela sonda de campo
(`scripts/sondar_cameras.py --usb 0`): **14,39 fps reais**, abertura em 670 ms.

## FPS

`imgsz=416`, `MULTI_PERSON=true`, `detect_every_n=3`, worker real (Flask +
`AlertStateService` + `ComplianceService` + anotação), lido no próprio
diagnóstico de tela.

| cenário | por câmera | agregado |
|---|---|---|
| **1 webcam USB, CPU livre** | **8,90 / 9,00 fps** | **~8,95** |
| **webcam USB + 1 RTSP (perfil Dahua), simultâneas** | 4,9 a 7,7 cada | **9,9 a 14,7** |

A faixa larga do caso de duas câmeras é o publicador ffmpeg da bancada
disputando CPU (o mesmo confundidor de −24% já declarado na Fase 2). Na planta
esse publicador não existe.

**O teto da fonte é 14,39 fps e o pipeline entrega ~9** — ou seja, o consumidor
é mais lento que a webcam. Em RTSP isso produziria fila crescente; em USB não,
pelo motivo medido logo abaixo.

## Latência USB: não há fila, e por isso não há deriva

O mesmo experimento que diagnosticou o RTSP — abrir, **parar de ler por 10 s**,
voltar a ler e contar quantos frames saem instantâneos:

| fonte | `set(BUFFERSIZE,1)` | `get()` | frames instantâneos após 10 s parado |
|---|---|---|---|
| **USB (DirectShow)** | **False** | **−1.0** | **1** — a leitura seguinte bloqueou 62 ms |
| RTSP (FFMPEG) | False | 0.0 | **104** |

**A webcam devolve UM frame e depois bloqueia** ~1/14,4 fps esperando o
próximo. O driver entrega só o quadro corrente: não há fila para acumular,
então **a deriva de latência do RTSP não existe em USB** — e é por isso que o
descarte de frame atrasado fica desligado nessa fonte (`_ler_do_capture`).

Note que `CAP_PROP_BUFFERSIZE` é recusado **também** no DirectShow. A diferença
não é a propriedade funcionar; é o driver já se comportar como se ela
funcionasse.

**NÃO VERIFICADO: a latência absoluta publicação → dashboard em USB.** O
`bench_latencia.py` mede o atraso carimbando um número de sequência **no frame
antes de publicar**, e numa câmera física não há como carimbar o fóton: o
instante em que a cena aconteceu não é observável sem uma referência externa
(filmar um cronômetro na tela, por exemplo). O que estava em jogo — **se o
atraso cresce** — está medido acima: não cresce, porque não há fila.

## As duas fontes convivendo (USB + RTSP)

**Cada fonte com seu caminho de captura**, verificado nos objetos reais criados
a partir do banco:

```
cam 1 [  USB] descarta_frame_atrasado=False
cam 2 [ RTSP] descarta_frame_atrasado=True
```

**Rodando ao mesmo tempo**, lido do diagnóstico de cada card:

```
cam 1:  4.90 fps   640x480  modo=ao_vivo  det30s={}
cam 2:  5.00 fps   704x576  modo=ao_vivo  det30s={'person': 13, 'vest': 103}
```

Duas resoluções diferentes, dois caminhos de captura diferentes, no mesmo
processo. A câmera de lente tampada não detecta nada e a RTSP detecta — mesmo
modelo, mesmo instante, e é exatamente essa comparação que o painel serve para
fazer.

**Uma morrendo não derruba a outra.** Matando o servidor RTSP e o publicador
com as duas ativas:

| | cam 1 (USB) | cam 2 (RTSP) |
|---|---|---|
| antes | 5,30 fps · `ao_vivo` | 5,20 fps · `ao_vivo` |
| 30 s depois | 6,30 fps · **`ao_vivo`** | 6,20 fps · **`fixture`** |
| 60 s depois | 8,30 fps · **`ao_vivo`** | 8,10 fps · **`fixture`** |

A USB seguiu intacta; a RTSP caiu para a fonte de demonstração e **continuou
publicando frame**, como projetado. As duas ganharam FPS depois da morte
porque o publicador ffmpeg parou de disputar CPU.

## O diagnóstico de tela, no navegador de verdade

Painel **Modelo YOLO** (perfil Técnico), com as duas câmeras ativas no mesmo
instante — copiado da tela:

| | cam 1 (webcam, lente tampada) | cam 2 (RTSP, cena real) |
|---|---|---|
| Detecções (30s) | **NENHUMA** | **100 em 2 classe(s)** — `person · 10`, `vest · 90` |
| Fonte agora | **640x480 · 6.9 fps** | **704x576 · 4.7 fps** |
| Modelo | Modelo PPE completo | Modelo PPE completo |

É a leitura de 5 segundos que o painel existe para dar: **modelo saudável nas
duas, fonte cega numa só.** Se o problema fosse o modelo, as duas colunas
diriam NENHUMA.

> O painel **só aparece no perfil Técnico**. O modo da interface é o **papel**
> de quem logou (`setMode(user.role)`), e não há seletor: um Supervisor não vê
> `#panel-model`, verificado no DOM. Quem for diagnosticar em campo precisa
> entrar como **Técnico**.


---

# Fase 9 — o capacete é fraco, e não é a resolução

Pergunta que veio do campo: no perfil D1 a contagem de 30 s deu `helmet: 2`
contra `vest: 127`. Isso é a fonte pequena ou o modelo?

Medido rodando o Vyra com `conf=0.05` **só para observar** (nenhuma mudança de
configuração: `YOLO_CONFIDENCE` continua 0,35), sobre as 3 cenas reais de
`tests/fixtures/cenas/` e a fixture — todas com pessoas de **capacete branco
visível a olho nu** — cada uma na resolução nativa e reescalada para D1:

| cena | resolução | `vest` | `helmet` |
|---|---|---|---|
| segura | 1280x866 | 0,57 | **0,17** |
| segura | 704x576 (D1) | 0,51 | **0,18** |
| risco | 1280x854 | — | **0,15** |
| risco | 704x576 (D1) | — | **0,14** |
| ambigua | 1280x914 | 0,13 | **0,59** |
| ambigua | 704x576 (D1) | 0,11 | **0,55** |
| fixture | 1280x720 | 0,31 | **0,23** |
| fixture | 704x576 (D1) | 0,47 | **0,26** |

**Em 3 das 4 cenas o capacete não alcança o limiar de 0,35** — fica em 0,14 a
0,26, com o capacete claramente na imagem. Só a `ambigua` passa (0,55).

**E a resolução quase não muda nada:** nativa contra D1 difere no máximo
**0,04** em todas as linhas, e em duas delas o D1 sai *melhor*. Ou seja, o
`helmet: 2` contra `vest: 127` **não é culpa do substream nem do
enquadramento** — é a confiança do modelo nessa classe, que vive logo abaixo
do corte.

O que isso significa para a sexta, e o que **não** significa:

- **Não** é caso de baixar `YOLO_CONFIDENCE`. A 0,05 apareceram detecções de
  capacete, mas junto vem tudo o que estiver acima de 0,05 — e o modelo já
  produz dois falsos positivos de "sem capacete" na cena SEGURA
  ([SPRINT3.md](SPRINT3.md)). Trocar-se-ia alerta perdido por alerta errado.
- É coerente com o que a matriz de confusão do autor já dizia sobre este peso:
  as classes têm suporte muito desigual no dataset de treino.
- A regra do passo (e) do runbook continua valendo, e agora com número:
  **capacete fraco não se conserta com limiar**, e a diferença entre `vest` e
  `helmet` na contagem de 30 s é esperada, não é sintoma de fonte ruim.

**NÃO VERIFICADO: cena INTERNA.** As quatro cenas acima são canteiro a céu
aberto. Se o capacete se comporta pior (ou melhor) sob luz de galpão, com
capacete de outra cor ou de aba total, isto não mede — e é justamente o que o
teste com a webcam responderia.


---

# Fase 10 — fonte cega na tela, e o que a checagem custa

O sistema aceitava frame zerado em silêncio: vídeo preto, inferência em nada,
FPS saudável, nenhum aviso. Quem fosse testar noutra máquina concluiria que o
projeto está quebrado. Agora o diagnóstico reporta `fonte_sem_imagem`.

## O custo: 0,0156 ms por segundo de operação

`brilho_do_frame` subamostra em vez de ler o frame inteiro — o passo se adapta
à resolução para dar ~1.000 pixels lidos em qualquer fonte:

| fonte | subamostrado | frame inteiro | mais barato |
|---|---|---|---|
| 640x480 (webcam) | **0,0127 ms** (4.032 valores) | 0,4675 ms (921.600) | **37,0x** |
| 704x576 (D1) | **0,0122 ms** (3.744 valores) | 0,6197 ms (1.216.512) | **50,6x** |
| 1920x1080 | **0,0389 ms** (5.568 valores) | 3,7136 ms (6.220.800) | **95,5x** |

E a medição é **esparsa**: uma vez por segundo
(`INTERVALO_AMOSTRA_BRILHO_S = 1.0`), não por frame. A 15 fps, medir a cada
frame custaria 15 medições/s; assim custa **uma**:

```
0,0156 ms por medicao x 1 por segundo = 0,0156 ms/s
um frame de inferencia a imgsz=416   ~= 120 ms   (Fase 6)
                                        7.692x o custo de uma medicao
```

Amostragem por **tempo**, e não por contagem de frames, de propósito: contar
frames faria a mesma escuridão acusar em tempos diferentes numa câmera de
25 fps e numa de 6. O que o operador percebe é tempo.

## A/B no worker real: abaixo do piso de ruído

Ligando e desligando a amostragem no mesmo processo, intercalado, fonte
fixture, 40 s por execução:

| | execução 1 | execução 2 | média |
|---|---|---|---|
| ANTES (sem amostragem) | 7,10 fps | 8,10 fps | 7,60 |
| DEPOIS (1 medição/s) | 8,70 fps | 8,40 fps | 8,55 |

O "depois" saiu **+12,5% mais rápido**, o que obviamente não é efeito de
adicionar trabalho — é ruído: o cenário ANTES sozinho variou de 7,10 a
8,10 fps (14%) entre execuções idênticas. Com um custo aritmético de
0,0156 ms/s contra um orçamento de ~960 ms/s de trabalho por segundo, **nenhum
A/B nesta máquina consegue resolver o efeito**; o micro-benchmark acima é a
prova, e o A/B só confirma que não há regressão visível.

## Ao vivo: acusa a cega, ignora a boa

Duas câmeras no mesmo processo — a webcam com o stream zerado pelo Windows
(porque o Discord já a tinha aberto) e a fixture com cena real:

```
cam 1 webcam (stream zerado)   fps=8.20   640x480  brilho=0.02    sem_imagem=True
cam 2 fixture (cena real)      fps=8.50  1280x720  brilho=119.27  sem_imagem=False
```

`running=True` e `alertas=0` nas duas: é **diagnóstico**, não veredito. Não
para a captura e não cria alerta, porque cena legitimamente escura cairia no
mesmo teste, e derrubá-la por causa disso seria pior que o silêncio que isto
conserta.

O limiar de **2,0** fica ~60x acima do medido na fonte cega (0,01 a 0,034) e
~60x abaixo da fixture (119). A margem é grande nos dois lados, e esse é o
ponto: o alvo é imagem **zerada**, não imagem escura.

**NÃO VERIFICADO: quanto marca uma cena legitimamente escura** (galpão à noite,
turno sem iluminação). Sensor com ganho alto produz ruído, que *deveria* ficar
acima de 2,0 — mas isso é inferência, não medição, e é exatamente por isso que
`FONTE_BRILHO_MINIMO` e `FONTE_BRILHO_JANELA_S` são configuráveis em vez de
constantes.
