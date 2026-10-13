# PESQUISA — fontes externas que influenciaram decisões (NEXT 2026)

**Data de acesso de todas as fontes:** 2026-10-12. Levantamento feito por um
subagente de pesquisa com leituras públicas (WebFetch/WebSearch), sem enviar
código do projeto a lugar nenhum. Conteúdo externo tratado como dado não
confiável. Nenhum código de terceiro foi copiado sem checar a licença.

**Legenda:** **[V]** verificado na fonte (código ou doc oficial) · **[H]**
hipótese/inferência · **[NA]** não foi possível abrir.

> O que foi efetivamente **medido aqui** (e não só lido) está em
> `BENCHMARKS.md` e `CHANGELOG.md`. Esta página registra o que foi lido e o
> veredito antes da medição; o CHANGELOG diz o que a medição confirmou ou
> derrubou.

---

## 1. ultralytics/ultralytics (AGPL-3.0 [V])

URLs: https://docs.ultralytics.com/modes/export/ · https://docs.ultralytics.com/models/yolo26/ ·
https://docs.ultralytics.com/models/yoloe/ · https://docs.ultralytics.com/tasks/pose/ ·
https://docs.ultralytics.com/integrations/openvino/ ·
https://docs.ultralytics.com/guides/yolo-thread-safe-inference/

- **Manutenção:** release `v8.4.176` em 2026-10-12 [V]. O projeto está preso no 8.3.40.
- **Export/INT8 [V]:** na doc atual `int8`/`half` estão depreciados e viram `quantize=8`;
  `data` é o YAML de calibração e `fraction` define o subconjunto. INT8 no OpenVINO usa
  NNCF PTQ. No 8.3.40 a API é `int8=True, data=...` [H, deduzido da nota de depreciação].
- **Backend OpenVINO** (`ultralytics/nn/backends/openvino.py`) [V]: `PERFORMANCE_HINT: LATENCY`
  fixo, sem `NUM_STREAMS`/`INFERENCE_NUM_THREADS`, inferência síncrona.
- **Backend ONNX** (`ultralytics/nn/backends/onnx.py`) [V]: `InferenceSession` com
  `session_options=None`, sem fixar threads.
- **YOLO26** [V]: existe desde o 8.4.0 (jan/2026), head sem NMS. A doc não fala de
  compatibilidade de pesos YOLOv8 treinados no 8.3.x [H: precisa testar em venv separado].
- **YOLOE/YOLOE-26** [V]: vocabulário aberto via `set_classes([...])`, exige ultralytics ≥ 8.4.0,
  baixa text encoder de ~254 MB na primeira chamada.
- **Trackers embutidos** (`ultralytics/trackers/track.py`) [V]: o estado mora em
  `predictor.trackers`, dentro do objeto do modelo; com modelo compartilhado entre câmeras e
  `persist=True` os IDs se misturam. O guia de thread-safety diz que compartilhar instância entre
  threads "causes race conditions".
- **Pose** [V]: yolo26n-pose 40,3 ms CPU ONNX (doc), 17 keypoints COCO.

**Vereditos:** tracker embutido → **rejeitar** (modelo compartilhado). YOLO26/YOLOE → **medir**,
condicionado ao upgrade 8.3→8.4 não quebrar o Vyra. INT8 OpenVINO → **medir no worker real**.

## 2. roboflow/supervision (MIT [V])

URL: https://github.com/roboflow/supervision — 0.30.9 em 2026-10-08 [V].

- Dependências da 0.30.9 [V]: `numpy>=1.21.2` (aceita o 1.26.4 do projeto), mas puxa
  `scipy`, `matplotlib`, `pillow`, **`av` (PyAV)**, `pydeprecate`, etc.
- **ByteTrack** (`src/supervision/tracker/byte_tracker/core.py`) [V]: estado **por instância**
  (Kalman, listas tracked/lost/removed); **depreciado desde 0.28 e removido no 0.31**.
  Associação em dois estágios por score (altas → baixas).
- `roboflow/trackers` (substituto, Apache-2.0) exige `numpy>=2.0.2` → **incompatível** com
  mediapipe 0.10.14 [V].
- PolygonZone, DetectionsSmoother e HeatMapAnnotator lidos no código [V].

**Veredito:** **adaptar** — comparar o tracker IoU atual com ByteTrack **por câmera**. Para não
puxar PyAV/matplotlib nem herdar uma API em remoção, a opção preferida é vendorizar o
algoritmo (MIT, só numpy/scipy) mantendo o aviso de licença. Adotar só se reduzir fragmentação
sem custar > 1 ms p95 (critério da missão).

## 3. ONNX Runtime e OpenVINO — threads e hints

- ONNX Runtime threading: https://onnxruntime.ai/docs/performance/tune-performance/threading.html [V]
  — `intra_op_num_threads` (0 = núcleos físicos), `session.intra_op.allow_spinning` consome CPU
  extra; para várias sessões simultâneas, afinidade separada ou pool global.
- OpenVINO hints (fonte `.rst` em `docs/articles_en/.../high-level-performance-hints.rst` e
  `cpu-device/performance-hint-and-thread-scheduling.rst`) [V]: LATENCY = 1 stream;
  `enable_cpu_pinning` não suportado no Windows; oneTBB com busy-wait concorre com o OpenMP do
  PyTorch ("occupy cores for additional time"), recomendação: limitar threads de cada lado ou
  `OMP_WAIT_POLICY=PASSIVE`.
- **Leitura para o VisionEPI [H]:** o i7-1355U tem 2 P-cores + 8 E-cores; LATENCY FP32 tende a
  usar E-cores, e no worker real concorre com PyTorch (yolov8n de pessoa), MediaPipe e captura.
  Isso é consistente com a nota de projeto "OpenVINO ganha na bancada e perde no worker", mas
  não está provado.

**Veredito:** **medir** dentro do worker real, com um único thread de inferência (o agendador
novo) e threads limitadas — nunca escolher backend por bancada isolada.

## 4. ifzhang/ByteTrack e NirAharon/BoT-SORT (MIT [V])

- ByteTrack: algoritmo de associação em dois estágios por score; repo parado desde 2022 [V].
  → **adotar o algoritmo** via implementação derivada, não o repo de pesquisa.
- BoT-SORT: acrescenta GMC (optical flow por frame) e ReID [V]. Câmera fixa → **rejeitar**.

## 5. blakeblackshear/frigate (MIT [V], v0.18.0)

- Captura (`frigate/video/ffmpeg.py: capture_frames`) [V]: anel de N slots em shared memory;
  `put(..., False)` não bloqueia — com fila cheia o próximo frame sobrescreve o slot
  (**"último frame vence"**).
- Detecção (`frigate/video/detect.py`, `frigate/object_detection/base.py`) [V]: detector em
  processo separado; só detecta em regiões de movimento/objetos rastreados.
- Gravação por evento (`frigate/record/maintainer.py`) [V]: segmentos em cache, mantidos se
  cruzam `[início − pre_capture, fim + post_capture]`.

**Veredito:** **adaptar os padrões** — captura com buffer de 1 por câmera, inferência
desacoplada do vídeo, clipe de incidente com pré/pós-captura a partir de buffer. Importar o
Frigate em si: rejeitado (Docker/Linux, outro produto).

## 6. Tencent/ncnn (BSD-3 [V]) e Tau-J/rtmlib (Apache-2.0 [V])

- ncnn tem wheel cp311-win_amd64 [V], mas a doc da Ultralytics foca ARM e não traz benchmark
  x86 → **rejeitar por ora**.
- rtmlib (`rtmlib/tools/base.py: BaseTool`) [V]: ORT sem SessionOptions; depende de
  `opencv-python` **e** `opencv-contrib-python` (conflito conhecido de `cv2` [H]) → não
  instalar; **medir** só se a pose YOLO não couber.

## 7. Projetos públicos de EPI e queda

Nenhum dos abaixo tem LICENSE (`license: null` na API do GitHub) [V] → **só ideias, nenhum
código copiado.**

| Repo | O que o código faz | Ideia aproveitável | Veredito |
|---|---|---|---|
| [Pratham-22/ppe-compliance](https://github.com/Pratham-22/ppe-compliance) | `scripts/ppe_compliance.py`: EPI→pessoa pelo centro da caixa; `PPEStateMachine(window=15, min_ratio=0.6)` por track | janela por track com mínimo de amostras | adaptar ideia |
| [GajuuzZ/Human-Falling-Detect-Tracks](https://github.com/GajuuzZ/Human-Falling-Detect-Tracks) | `main.py`: tracker + 30 frames de keypoints por track; separa "Fall Down" de "Lying Down" | queda por janela temporal por track | adaptar ideia |
| [hafizqaim/Workspace-Safety-Detection-using-YOLOv8](https://github.com/hafizqaim/Workspace-Safety-Detection-using-YOLOv8) | inferência dentro do gerador MJPEG **por cliente** | contraexemplo (custo cresce com espectadores) | rejeitar |
| [ZijianWang-ZW/PPE_detection](https://github.com/ZijianWang-ZW/PPE_detection) | código não lido [NA] | dataset CHV | só como referência |
| [AnshulSood11/PPE-Detection-YOLO-Deep_SORT](https://github.com/AnshulSood11/PPE-Detection-YOLO-Deep_SORT) | código não lido [NA] | violação só após N segundos | ideia (já coberta pela histerese) |

## 8. Câmera do celular — MDN e Chromium

- https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia [V]: só em
  *secure context*; fora dele `navigator.mediaDevices` é `undefined`.
- https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts [V]: `https`, `localhost`,
  `127.0.0.0/8`, `::1`, `*.localhost` são confiáveis; `http://192.168.x.x` não se encaixa em
  nenhuma regra → **celular na LAN precisa de HTTPS**.
- Chromium (`media/base/media_switches.cc`, `media/capture/video/file_video_capture_device.cc`)
  [V]: `--use-fake-device-for-media-stream --use-file-for-fake-video-capture=<arquivo>` aceita
  `.y4m` (I420) e `.mjpeg`.

## 9. Flask-SocketIO / python-socketio / Engine.IO

- `emit` aceita `bytes`; o cliente recebe `ArrayBuffer` [V].
- **No long-polling, binário vai em base64 com prefixo `b`** (~+33% e CPU extra); no WebSocket,
  frame binário puro [V]. Em modo `threading`, o WebSocket depende do pacote `simple-websocket`
  (`engineio/async_drivers/threading.py`) [V].
- O frontend deste projeto força `transports: ["polling"]` (ver `frontend/src/socket/client.ts`).

**Consequência para a decisão de transporte de vídeo:** com o socket em polling, mover o vídeo
para dentro do Socket.IO *pioraria* (base64). O vídeo já sai binário por HTTP multipart
(MJPEG). A decisão registrada no CHANGELOG parte daqui.

## 10. Ideias de produto (com fonte)

- Clipe por evento com pré/pós-captura (Frigate `record/maintainer.py`) → F1 (replay).
- Desfoque de rosto: `BlurAnnotator` do supervision (por bbox); YuNet do `opencv_zoo` (MIT);
  alternativa sem modelo extra: caixa do rosto pelos keypoints da pose / terço superior da
  caixa [H] → F4.
- Heatmap de violações (`HeatMapAnnotator`) → F7.

## Decisões influenciadas (resumo)

- Tracker: ByteTrack **por câmera**, vendorizado (MIT); adotar só se medir < 1 ms p95 e reduzir
  fragmentação. `model.track(persist=True)` rejeitado.
- `roboflow/trackers` rejeitado (numpy ≥ 2).
- OpenVINO/ONNX: medir **dentro do worker**, com um único thread de inferência e threads
  limitadas.
- Captura: buffer de 1 por câmera, "último frame vence".
- Replay: buffer circular de JPEG em memória, clipe com pré/pós-captura.
- Vídeo continua binário por HTTP; Socket.IO só para metadados (polling → base64).
- Celular como câmera: HTTPS obrigatório fora de localhost; teste E2E com câmera falsa do Chromium.
- ncnn, BoT-SORT/GMC: rejeitados.

**Não aberto/verificado pelo subagente:** LICENSE do ONNX Runtime, OpenVINO, Flask-SocketIO e
python-socketio; compatibilidade dos pesos 8.3 no 8.4; ficha técnica do i7-1355U.

## Fontes lidas em 13/10/2026 (missão NEXT 2026)

### OpenVINO — plugin de CPU, hint e threads
https://docs.openvino.ai/2026/openvino-workflow/running-inference/inference-devices-and-modes/cpu-device/performance-hint-and-thread-scheduling.html
- `INFERENCE_NUM_THREADS` "limits the number of logical processors used for
  CPU inference"; no hint LATENCY o padrão é P-cores ou P-cores+E-cores de um
  soquete. No i7-1355U (2 P + 8 E, razão 4) o FP32 usa os dois tipos.
- `ENABLE_CPU_PINNING`: desligado por padrão no Windows.
- Uso: `YoloPPEDetector._recompilar_openvino_na_cpu`.

### Câmera do celular (F6)
- getUserMedia: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia
  — só em contexto seguro; em contexto inseguro `navigator.mediaDevices` é
  `undefined`. Câmera traseira: `facingMode: { exact: "environment" }`.
- Contextos seguros: https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts
  — confiáveis: `https`, `127.0.0.0/8`, `::1`, `localhost`. Um IP de LAN em
  `http://` NÃO é contexto seguro → o celular precisa de HTTPS.

### Alerta falado (G6)
- https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis — `speak()`
  "Adds an utterance to the utterance queue"; `cancel()` esvazia a fila;
  `getVoices()` + evento `voiceschanged` (lista chega assíncrona).
- https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice/localService
  — `localService` true = sintetizador local (funciona offline).

### NR-6 (G10)
Página oficial: https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/participacao-social/conselhos-e-orgaos-colegiados/comissao-tripartite-partitaria-permanente/normas-regulamentadora/normas-regulamentadoras-vigentes/norma-regulamentadora-no-6-nr-6
(última modificação: Portaria MTE nº 57, de 16/01/2025). Texto:
https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/participacao-social/conselhos-e-orgaos-colegiados/comissao-tripartite-partitaria-permanente/normas-regulamentadora/normas-regulamentadoras-vigentes/nr-06-atualizada-2025-ii.pdf
(extraído com `pdftotext -layout`; o PDF diz "Este texto não substitui o publicado no DOU").

Itens que EXISTEM no texto e podem ser citados:
- 6.5.1 "Cabe à organização, quanto ao EPI:" … "e) exigir seu uso;"
  e "b) orientar e treinar o empregado;"
- 6.6.1 "Cabe ao trabalhador, quanto ao EPI:" … "a) usar o fornecido pela
  organização, observado o disposto no item 6.5.2;"
- Anexo I: "A.1 - Capacete"; "B.1 - Óculos"; "C.1 - Protetor auditivo";
  "D - EPI PARA PROTEÇÃO RESPIRATÓRIA" (respiradores, PFF); "F.1 - Luvas";
  "G.1 - Calçado".

Mapeamentos NÃO sustentados pelo texto (ficam de fora no G10):
- Colete de alta visibilidade: o Anexo I não o lista (E.1 são vestimentas
  contra agentes térmicos/mecânicos/químicos/radiação/umidade; E.2 é "Colete à
  prova de balas" para vigilantes).
- "Máscara" do modelo Vyra (classe `Mask`) não distingue respirador (D) de
  máscara comum; ligar a detecção ao Anexo D afirmaria mais do que o modelo vê.
