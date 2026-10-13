# Auditoria — VisionEPI antes do NEXT 2026

**Base auditada:** `feat/completo-com-rebrand` @ `1bf191a` (tag de rollback
`pre-next-2026`). **Data:** 2026-10-12. Método: leitura do código (fonte da
verdade), não do README; números vêm do `scripts/bench.py` (instrumentação
adicionada sem mudar comportamento, commit `2f3c49a`) e estão em
`bench/results/20261012-234702-baseline.json`.

> **Ressalva de medição.** A máquina de medição (i7-1355U, 12 lógicos, sem GPU)
> estava compartilhada com processos fora deste projeto (Java, VM do WSL,
> Defender), registrados pelo bench como `carga_de_fundo_pct` ≈ **1.040–1.130 %
> de 1.200 %**. Os números absolutos da baseline abaixo medem o VisionEPI
> **sob disputa de CPU**; servem para localizar gargalos estruturais (que não
> dependem da carga), não como FPS de uma máquina dedicada. As comparações
> antes/depois em `BENCHMARKS.md` foram rodadas **intercaladas**, para que a
> carga de fundo afete os dois lados igualmente.

## 1. Arquitetura real

```
run.py (Werkzeug threading + Flask-SocketIO async_mode=threading)
 └─ MonitorService ── carrega 1x e compartilha:
      ├─ detector EPI   YoloPPEDetector(models/vyra_ppe.pt, YOLOv8m, 14 classes)
      ├─ detector pessoa YoloPPEDetector(models/yolov8n.pt, COCO classe 0)  [MULTI_PERSON_DETECTION=true]
      ├─ MediaPipePoseEstimator (instância única, static_image_mode por recorte)
      ├─ inference_lock (threading.Lock global)
      └─ 1 CameraWorker por câmera habilitada (thread via socketio.start_background_task)
           loop síncrono: read → [lock: EPI → pessoa → tracker IoU → filtro → pose] →
                          regras → histerese/DB → conformidade → anotação → JPEG → emits
API REST (Flask) + MJPEG (/api/cameras/<id>/video_feed) + frame.jpg (miniaturas 1 Hz)
Frontend React/Vite (app/static/dist), Socket.IO forçado em long-polling
```

## 2. Um quadro, da captura ao pixel (baseline)

| # | Etapa (arquivo) | Cópia de dados | Lock / fila | Encoding / serialização | Onde o quadro envelhece |
|---|---|---|---|---|---|
| 1 | `VideoStream.read()` (`app/vision/video_stream.py`) | `cv2.read()` aloca o quadro; `_on_success` faz **`frame.copy()`** para `_latest_frame` (2,7 MB a 720p) — e nada no app lê esse campo | `RLock` do stream | decode do codec (arquivo/RTSP) | **Arquivo não tem ritmo próprio**: o loop só pede o próximo quadro depois de terminar o anterior → a fixture "toca" em câmera lenta. Medido: `fracao_do_tempo_real` = **0,003–0,014** (o vídeo anda 1 s a cada 70–300 s de relógio) |
| 2 | rotação (`_aplicar_rotacao`) | cópia só se `rotation≠0` | — | — | — |
| 3 | inferência (`_analyze_frame`) | letterbox/tensor do ultralytics (2 modelos = 2 cópias redimensionadas); recorte + `cvtColor` por pessoa no MediaPipe | **`inference_lock` global**: todas as câmeras em fila, sem ordem garantida | — | **Espera do lock**: p50 **37,1 s** com 4 câmeras (cada worker espera as inferências das outras 3). EPI p50 3,1–9,0 s, pessoa 0,3–3,0 s, pose 0,19–0,30 s (sob carga) |
| 4 | regras + histerese (`risk_rules.py`, `alert_state_service.py`) | dicts por pessoa | — | **INSERT/COMMIT síncrono** na criação/resolução; *touch* a cada 2 s | p50 < 1 ms sem alerta |
| 5 | snapshot do alerta (`snapshot_service.py`) | quadro anotado | — | **`cv2.imwrite` síncrono** no loop | 10–30 ms no quadro em que o alerta nasce |
| 6 | anotação (`annotator.py`) | **`frame.copy()` + 1 cópia por camada** de opacidade (`_com_opacidade`: até 4 cópias de quadro inteiro + `addWeighted`) | — | — | p50 34–48 ms, **a cada quadro, com ou sem espectador** |
| 7 | JPEG (`cv2.imencode` q80) | buffer novo | `_thread_lock` do worker | ~220 KB por quadro a 1280×720 (a fixture vinha maior que os 960×540 cadastrados e ninguém reduzia) | p50 16–29 ms, **a cada quadro, com ou sem espectador** |
| 8 | telemetria (`_emitir`) | `analysis.to_dict()` (~26 KB com landmarks) | fila por cliente do Engine.IO | JSON por emit; **duas emissões** (sala `parque` + `camera:<id>`) | `analysis` a 8 Hz para **todo** o parque, mesmo de câmera que ninguém olha; `active_alerts` **a cada quadro** |
| 9 | MJPEG (`camera_video_feed`) | concatenação `b"--frame..." + jpeg` | sondagem da versão a cada 1/(4·fps) s | multipart binário (não base64) | até 21 ms de sondagem |
| 10 | navegador (`<img src=video_feed>`) | decode no browser | 1 conexão HTTP por stream (limite de 6 por origem) | — | sem como medir quando cada quadro chega; sem detecção de travamento |

**Socket.IO:** `frontend/src/socket/client.ts` força `transports: ["polling"]`
(comentário: o proxy do Vite derrubava o upgrade). Em long-polling, payload
binário vai em **base64** (Engine.IO, ver PESQUISA.md §9). Por isso mover o
VÍDEO para o socket pioraria; o vídeo já sai binário por HTTP.

## 3. Um alerta, da detecção à resolução (baseline)

1. `RuleEngine.analyze` gera `RuleAlert` por pessoa (EPI ausente, área de
   risco) e por pose (queda/postura por geometria de landmarks).
2. `AlertStateService.process`: histerese **por detecção nova** (não por
   quadro): `ALERT_CREATE_AFTER_FRAMES=8` confirmações → `INSERT` + `COMMIT`
   síncronos → `alert_created` no socket → snapshot anotado gravado
   **síncrono** → submissão ao LLM (assíncrona, opcional, nunca decide).
3. Enquanto ativo: *touch* no banco a cada 2 s (`ALERT_TOUCH_INTERVAL_SECONDS`).
4. `ALERT_RESOLVE_AFTER_FRAMES=20` detecções sem a violação → `resolve` +
   `COMMIT` → `alert_resolved` → evento de linha do tempo (`INSERT`).
5. Frontend: `active_alerts`/`alert_*` no store Zustand; pill crítico sobre o
   vídeo; histórico e linha do tempo.

**Achados:** a classe `Fall-Detected` do Vyra é detectada e desenhada, mas
**nenhuma regra a consome** (confirmado no código e já registrado no README);
queda depende só da geometria do MediaPipe, que achou o torso em 1 de 8
quadros de pessoa em pé testados (`fall_probe`, ver CHANGELOG).

## 4. Status real de cada feature do README

| Feature (README) | Status | Evidência |
|---|---|---|
| Detecção de EPI em tempo real (Vyra, 14 classes) | **Parcial** | Funciona, mas o `.env.example` infere a 416: contra a referência a 640, **capacete concorda 8 %** e o total 63,6 % (`scripts/concordancia.py`). "Tempo real" não se sustenta sob carga (seção 2). |
| Multi-pessoa com identidade estável (tracker IoU) | **Funciona, com fragmentação** | bench.mp4: **5 IDs para 3 pessoas** (`scripts/comparar_trackers.py`). |
| Multi-câmera de verdade | **Parcial** | Um worker por câmera, modelos compartilhados — mas o `inference_lock` serializa tudo e o vídeo de cada câmera anda no ritmo da fila (espera p50 37 s com 4 câmeras sob carga). O próprio Roadmap do README admite. |
| Postura e quedas (MediaPipe) | **Parcial** | Regra por geometria funciona (testes); detecção de torso fraca nas fixtures; `Fall-Detected` do modelo ignorado. |
| Área de risco configurável | **Funciona** | Editor + regra + testes (`test_zona_de_risco_por_camera.py`). |
| Histerese de alertas | **Funciona** | `test_alert_state.py`, `test_camera_worker_cache.py`. |
| Tendência de risco | **Funciona** (não exercitado por mim na UI) | `test_risk_score_service.py`. |
| Command palette | **Presente no código, não exercitado** | `components/command-palette.tsx`. |
| Alertas sonoros | **Presente no código, não exercitado** | `audio/chime.ts`. |
| Autenticação com papéis | **Funciona** | 30+ testes de escopo REST/socket; E2E do operador. |
| Modos Operador/Técnico/Supervisor | **Funciona** | Roteamento em `App.tsx`; E2E. |
| Dashboard em tempo real via WebSocket | **Funciona, com custo** | Long-polling forçado; `analysis` para todo o parque; `active_alerts` por quadro. |
| Roadmap: retry/backoff de fonte | **Funciona** | `test_camera_worker_falha_de_fonte.py`; E2E de queda de fonte. Sem *jitter*. |
| Roadmap: config por câmera em runtime | **Parcial** | Edição reconstrói o worker (sem reiniciar o processo); features por câmera só no próximo build do worker. |
| Suíte de testes verde | **Não estava** | `test_default_features_liga_todos_os_epis` falhava pelo `.env` da máquina; `ruff check .` com 10 erros. |

## 5. Gargalos (ordem de impacto)

1. **Vídeo acoplado à inferência** (loop síncrono + lock global): com N câmeras
   cada uma recebe ~1/N da vazão do modelo **e** ~1/N do FPS de vídeo.
2. **Trabalho por quadro sem consumidor**: anotação (34–48 ms) e JPEG
   (16–29 ms) a cada quadro, em toda câmera, assistida ou não.
3. **Fixture sem ritmo**: o arquivo toca em câmera lenta e a "idade" do que se
   vê cresce sem limite (p95 de 10–50 s no navegador).
4. **Telemetria para todos**: `analysis` (8 Hz × câmeras) para o parque inteiro
   e `active_alerts` a cada quadro, em long-polling.
5. **Escrita síncrona no loop**: snapshot (`imwrite`) e commits no quadro do alerta.

## 6. Riscos para a demo

| Risco | Probabilidade | Efeito | Mitigação adotada |
|---|---|---|---|
| Máquina carregada / fraca derruba o FPS | alta | vídeo "travado", alerta atrasado | pipeline assíncrono, controlador adaptativo com aviso DEGRADADO |
| Pessoa "trocando de ID" na frente da banca | média | histórico poluído | medido; ByteTrack disponível (laboratório) |
| Webcam/RTSP não abre no local | média | tela preta | fixtures como câmeras "GRAVAÇÃO" (modo demo); fallback de fixture |
| Modelo a 416 não ver capacete | alta | "sem capacete" falso | imgsz 640 (guarda de qualidade) |
| Senha/banco de demo sujos | média | login falha | modo demo com banco isolado e reset (PR3) |
| Projetor com resolução diferente | média | layout quebrado | screenshots 1366×768 e 1920×1080 (PR2) |
