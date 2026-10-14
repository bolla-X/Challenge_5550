# CHANGELOG — NEXT 2026

Cada entrada: **o que mudou · por quê · evidência (comando + número) · o que
foi rejeitado**. Números de desempenho sempre com a ressalva de que a máquina
de medição (i7-1355U, 12 lógicos, 15,7 GB, sem GPU, Windows 11) estava
compartilhada com processos de fora do projeto; o bench registra essa carga
(`carga_de_fundo_pct`) e as comparações foram rodadas **intercaladas**.

## Git

- Base: `feat/completo-com-rebrand` @ `1bf191a`. `main` tem 15 commits que a
  base não tem (Sprint 4) e a base tem 37 que a `main` não tem; o merge de teste
  (`git merge-tree --write-tree origin/feat/completo-com-rebrand origin/main`)
  deu **conflito** em `.env.example`, `app/config.py`, `risk_rules.py`,
  `person_compliance_matcher.py`, `yolo_ppe_detector.py`, `global.css`,
  `app/static/dist/*`, `docs/SPRINT4.md`. Pela regra pré-decidida, **mantida a
  base, sem merge**.
- Trabalho local preservado: branch `wip-preservado-2026-10-12` (aponta para a
  `sprint4` local, com 2 commits não publicados); arquivos não rastreados
  (`Claude outputs/`, `Sprint4_IA_entrega/`, `.pptx`) intocados.
- Ponto de rollback total: tag **`pre-next-2026`** (publicada) em `1bf191a`.

## Baseline verde (pré-requisito do portão)

- **`VISIONEPI_DOTENV=0`** desliga a leitura do `.env`; `tests/conftest.py` liga
  isso antes do import. Motivo: `test_default_features_liga_todos_os_epis`
  falhava na baseline porque o `.env` da máquina tinha outro `DEFAULT_FEATURES`
  — o teste dependia de quem roda. Evidência: `pytest -x` → `1 failed, 336
  passed` antes; `4 passed` em `tests/test_ppe_defaults.py` depois.
- `ruff check .`: 10 erros → 0 (6 de ordem de import corrigidos com `--fix`, 4
  linhas longas quebradas à mão). Nenhum teste desligado, nenhum assert afrouxado.

## Instrumentação e benchmark

- `app/services/pipeline_stats.py`: p50/p95/p99 por etapa e taxas, sempre
  ligados (custo: `perf_counter` + `deque.append`), expostos em
  `GET /api/diagnostics/pipeline` (respeita o escopo do operador).
- MJPEG com `Content-Length`, `X-Frame-Id` e `X-Capture-Ts` por parte.
- `scripts/bench.py`: servidor real, fixtures, Playwright, psutil; perfis
  `atual` e `batata` (2 threads + afinidade nos 2 núcleos lógicos mais lentos,
  medidos — num híbrido Intel são E-cores); cenários 1 e 4 câmeras; `--arvores`
  para comparar código/configuração intercalados; `--soak`.
- **Erro de método encontrado e corrigido no caminho:** (1) no Windows o
  `python.exe` do venv é um lançador e o interpretador real é processo filho —
  medir só o PID do `Popen` dava 0 % de CPU e 3 MB; (2) com só o servidor em
  prioridade alta, o Chromium passava fome numa máquina carregada; (3) a sonda
  e o player copiavam o buffer inteiro a cada pedaço recebido (cópia
  quadrática) e, uma vez atrasados, nunca recuperavam — a idade do quadro media
  o leitor, não o sistema. As rodadas afetadas estão marcadas em BENCHMARKS.md.

## Métricas do portão (13/10)

O bench herdado media bem o VÍDEO (idade do quadro exibido) e nada da ANÁLISE.
O vídeo pode estar fresco enquanto as caixas e os alertas são de segundos atrás
— exatamente o que o operador não vê. Métricas principais agora:

- **FPS de análise por câmera** (`analises_publicadas`/s);
- **idade da análise p50/p95**: da captura do quadro ANALISADO até o resultado
  sair (regras, alertas e emissão feitos) — `CameraWorker._registrar_analise_publicada`;
- **latência de alerta**: do primeiro quadro com a violação até o
  `alert_created` chegar ao navegador. Gabarito: `scripts/primeira_violacao.py`
  (referência PyTorch@640 + `RuleEngine`, sem histerese) → `multidao`,
  `missing_helmet`, **quadro 0** (pedestres, ninguém de capacete; conferido no
  quadro extraído). Âncora: instante em que o servidor leu o quadro
  (`/api/diagnostics/pipeline?quadro=K`); chegada: ouvinte Socket.IO oficial
  injetado no Chromium, conectado ANTES de ligar as câmeras.

A baseline recebeu o MESMO instrumento num branch local de medição
(`bench/base-instrumentada`, só pipeline_stats + 6 linhas no loop), para a
comparação ser da mesma régua. A câmera 1 do bench passou a ser a `multidao`.

**Perfil batata reprodutível.** "Os 2 núcleos mais lentos medidos" escolheu
`[4,5]`, `[0,2]` e `[1,7]` em rodadas diferentes (cronometragem sob carga de
fundo variável; `[1,7]` mistura P-core com HT e E-core). Agora:
`GetSystemCpuSetInformation` → os 2 últimos núcleos de menor `EfficiencyClass`
(https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-system_cpu_set_information):
**E-cores 10 e 11** neste i7-1355U (lógicos 0–3 = 2 P-cores com HT, classe 1;
4–11 = E-cores, classe 0).

## Achados de desempenho do perfil batata (13/10)

| Achado | Evidência | Mudança |
|---|---|---|
| Decoder FFmpeg do OpenCV abre **12 threads por câmera** (uma por núcleo lógico), mesmo com o processo preso a 2 núcleos | `psutil.num_threads()` antes/depois de `VideoCapture(...).read()`: +12; com `CAP_PROP_N_THREADS=2`: +2 | `abrir_captura(..., threads_decode=2)` para arquivo e rede; `CAPTURA_THREADS_DECODE`. Doc: `CAP_PROP_N_THREADS = 70, //!< (**open-only**) Set the maximum number of threads to use. Use 0 to use as many threads as CPU cores` (`modules/videoio/include/opencv2/videoio.hpp`, branch 4.x; docs.opencv.org devolveu desafio Cloudflare ao cliente automatizado) |
| Vídeo concorrente custa ~40 % na inferência nos 2 E-cores; baixar a prioridade da thread de vídeo recupera só ~6 % | micro-bench intercalado, 3 rodadas: sem vídeo 2143 ms, vídeo normal 3041, vídeo abaixo do normal 2848 (medianas) | **não adotado** (dentro do ruído) |
| Análise pronta esperava até ~0,9 s para sair: um commit SQLite por alerta criado/tocado/resolvido | etapa `alertas` p99 565 ms / máx 917 ms; `espera_publicacao` p50 522 ms (bench `diag-espera`) | uma transação por análise, eventos depois do commit: `alertas` máx 154 ms, `espera_publicacao` p50 185 ms (`diag-espera2`); `tests/test_alert_state.py::test_uma_analise_com_muitos_alertas_faz_um_commit_so_e_emite_depois` |
| Histerese de 8 quadros = ~0,7 s no loop antigo, ~27 s a 0,3 análise/s | latência de alerta batata 1 câm.: base 31 s, PyTorch 18 s, ONNX 42 s (medianas de 3) | cria com 8 quadros **ou** 2 s com ≥ 2 inferências novas seguidas; resolve com 20 **ou** 6 s com ≥ 3 (`ALERT_CREATE_AFTER_SECONDS`, `ALERT_MIN_CONFIRMATIONS`, `ALERT_RESOLVE_AFTER_SECONDS`, `ALERT_MIN_RESOLVE_CONFIRMATIONS`); 7 testes novos |
| No modo assíncrono, os degraus de N do controlador não aliviam nada e atrasam a redução da pose em ~30 s | o slot por câmera já guarda só o quadro mais novo | escada assíncrona começa pela pose (`tests/test_controlador_adaptativo.py::test_no_modo_assincrono_a_escada_comeca_pela_pose`) |
| Primeira análise depois de ligar a câmera levava ~30 s (pose carregada preguiçosamente, predictor e sessão ONNX criados na 1ª inferência) e isso entrava inteiro na latência do 1º alerta | log da rodada ONNX: câmera ligada 10:31:23, `sessao_onnx_ajustada` 10:31:53, alerta 10:31:59 | `MonitorService.aquecer()` chamado pelo `run.py` antes de servir (não no construtor: o `wsgi.py` também é importado pelos comandos `flask users`) |
| No batata 4 câm., FPS de análise do PR1 0,10–0,11/câm. contra 0,14–0,15 da base (**inconclusivo sob saturação, n≈4 análises por câmera por rodada** — ver nota do ADENDO 1 abaixo; a causa apontada abaixo foi confirmada depois pela métrica de CPU): cada análise custava ~2x disputando os 2 núcleos com o vídeo das 4 fontes em tempo real (a base toca o arquivo em câmera lenta, no ritmo da inferência) | custo por análise: EPI 1837 vs 1379 ms, pessoa 358 vs 241 ms (`*-gate2-b4-*.json`) | (1) câmera sem espectador publica vídeo a `VIDEO_FPS_SEM_ESPECTADOR=2` (miniatura = 1 quadro/s por cartão), análise nova fura a cadência; (2) o agendador faz o resize só do quadro que vai inferir; (3) acima da taxa útil a captura só AVANÇA a fonte (`VideoStream.pular`: grab sem retrieve), mantendo o tempo real. Micro-bench (2 E-cores, 4 fontes): inferência EPI ONNX 791 ms sem vídeo, 1178 ms com as 4 convertendo todo quadro, 981 ms convertendo ~2,5 quadros/s cada; prioridade de thread mais baixa sozinha: 1186 ms (não adotada) |

**Política de gravação sem espectador (decisão de produto, 13/10).** Mesmo
com as três mudanças acima, no batata 4 câm. sob saturação o FPS de análise
do PR1 ficou 0,05 contra 0,08 da base (`*-gate4-r*.json`, fundo ~1000 %) —
regressão NOMINAL e **inconclusiva sob saturação (n≈4 análises)**: com a
máquina cheia, tempo de relógio mede a carga de fundo (ADENDO 1). A métrica
que decide passou a ser CPU-ms do servidor por análise (ver BENCHMARKS.md).
Causa: manter um arquivo H.264 no relógio exige decodificar TODO quadro
(25–30/s por gravação); a base não paga isso porque toca o arquivo em câmera
lenta (fração do tempo real 0,01–0,04). Alternativas medidas e rejeitadas:

- decode por hardware: `CAP_PROP_HW_ACCELERATION=VIDEO_ACCELERATION_ANY`
  devolve aceleração 0 neste build do OpenCV (indisponível);
- busca por keyframe: o modo bruto (`CAP_PROP_FORMAT=-1` +
  `CAP_PROP_LRF_HAS_KEY_FRAME`) indexa os keyframes barato (31 ms para 375
  quadros; GOP = 12), mas `set(CAP_PROP_POS_FRAMES)` + `read()` custou 64 ms
  (960x540) e 164 ms (1280x720) POR QUADRO — pior que decodificar em sequência;
- lote de 4 câmeras numa chamada (`INFERENCIA_LOTE`): reprova no guarda sem
  precisar de bench — com quadros de formatos diferentes (960x540 e 720x576)
  o ultralytics usa letterbox QUADRADO (`same_shapes` falso em
  `engine/predictor.py`), o mesmo caso medido em 95,04 % (< 97 %).

Adotado: **gravação (arquivo) sem ninguém no MJPEG avança a
`CAPTURA_FPS_SEM_ESPECTADOR=4` quadros/s** em vez de no relógio
(`GRAVACAO_SEM_ESPECTADOR_NA_TAXA_UTIL=true`); ao abrir o foco, volta ao tempo
real de onde está. Câmera AO VIVO (webcam, RTSP) não muda. A tela já rotula
arquivo como GRAVAÇÃO. Testes: `test_gravacao_sem_espectador_desacelera_em_vez_de_decodificar_tudo`,
`test_gravacao_com_espectador_segue_o_relogio`.

**Documentação no código que estava errada:** o comentário de
`VideoStream._ler_do_capture` dizia que descartar N quadros com `grab()` custa
"N demux e UM decode". Medido num E-core (1 thread de decode): `grab()` 1,17 ms
contra `read()` 2,89 ms (960x540); 3,25 contra 5,97 ms (1280x720). O `grab()`
do FFmpeg decodifica; economiza a conversão para BGR e a cópia. Comentário
corrigido.

Teste ajustado (contrato, não afrouxamento): `test_arquivo_local_nao_recebe_timeout`
afirmava `params is None`; a intenção declarada era "sem timeout de rede em
arquivo". Agora afirma que o ÚNICO parâmetro de abertura de arquivo é
`CAP_PROP_N_THREADS=2` — timeouts seguem proibidos.

## ADENDO 1 — métricas de CPU e decisões (13/10)

Máquina saturada por terceiros: tempo de relógio passou a ser "sob saturação —
indicativo". Portão e decisões usam CPU-ms do processo do servidor por análise
concluída e por quadro publicado, e contadores determinísticos
(`scripts/resumo_cpu.py`; regra: reprova só se a mediana do novo for > 10 %
pior E as 3 repetições pareadas concordarem).

**Runtime (decisão A):** batata 1 câm., CPU-ms por análise (`*-dec1cam-r*.json`,
3 repetições): ONNX **2.926**, OpenVINO 3.373, PyTorch 4.427 (ONNX/PyTorch por
repetição: 0,74 / 0,64 / 0,66). Confirmado em `*-rt-r*.json` (2 repetições, sob
saturação): ONNX 5.655 vs PyTorch 9.026. **ONNX segue padrão.**

**Spinning do ONNX (decisão A):** ligar (`ONNX_SPINNING=1`) AUMENTOU o CPU por
análise (1 câm. 7.458 vs 5.655; 4 câm. 8.656 vs 6.657, `*-rt-r*.json`).
**Desligado** (padrão).

**Duas fontes de trabalho idêntico repetido a cada quadro de vídeo** (achadas
porque a 1ª rodada com a métrica nova reprovou o batata 4 câm. em CPU-ms por
análise: +12 %, repetições 1,12 / 1,13 / 1,16, `*-gate5-r*.json`):

| Achado | Evidência | Mudança |
|---|---|---|
| Regras, conformidade e `analysis.to_dict()` (com as poses da multidão) refeitos a cada quadro publicado, para a MESMA análise (~95 % dos quadros) | regras/matcher/conformidade são função pura (sem relógio nem estado — `grep` em `risk_rules.py`, `person_compliance_matcher.py`, `compliance_service.py`) | `_publicar` reaproveita enquanto a análise, a zona, os recursos e a lista de alertas ativos forem os mesmos; contador `publicacoes_reaproveitadas`; `tests/test_publicacao_reaproveitada.py` |
| Emitir para sala vazia não é de graça | python-socketio 5.16.4, `socketio/manager.py`, `Manager.emit`: `pkt.encode()` antes de `get_participants()`. O comentário de `app/utils/salas.py` dizia o contrário | `_tem_alguem` pula a emissão quando a sala comprovadamente está vazia; com dublê de teste, emite como antes |

## E2E do portão do PR1 (13/10)

1ª execução: 3 passed, 1 failed — `test_queda_da_fonte_mostra_reconectando_e_volta`
("a fonte de rede nunca ficou ao vivo"). Reproduzindo o cenário (mesmo
servidor do E2E, câmera "Rede" aberta, diagnóstico por 40 s) apareceu um bug
real introduzido pelo `grab` da captura: a decisão de pular era tomada ANTES
de o `grab()` esperar o próximo quadro, e numa fonte ao vivo o quadro que
chegava era justamente o descartado — câmera de rede a 10 fps, COM
espectador, publicava ~5 fps (`frames_pulados` 5,4/s). Correção: avança
primeiro, decide depois; `VideoStream.converter()` entrega o quadro em que o
`pular()` parou (e o `pular()` de fonte de rede drena o buffer como o
`read()`). Teste de regressão `test_fonte_ao_vivo_mais_lenta_que_a_taxa_util_nao_perde_quadro`:
falha no código anterior (7 de ≥ 9 quadros) e passa no novo. A rodada de CPU
do portão (`gate6`) foi medida ANTES desta correção; ela só acrescenta
conversões até o FPS configurado na câmera assistida.

Pendência registrada para o PR4 (confiabilidade da demo): câmera do tipo
"Arquivo" cadastrada pela API não usa `em_loop` — no fim do vídeo acumula 15
falhas e reabre do início (log do E2E: `video_stream_reconnecting`,
`consecutive_failures: 15`, a cada volta da fixture). Comportamento anterior
a esta missão; é um engasgo visível a cada loop.

## L1 — OpenVINO na iGPU Intel (ADENDO 1): aprovado, vira o padrão

Docs lidas: export OpenVINO da Ultralytics
(https://docs.ultralytics.com/integrations/openvino/ — `dynamic`, dispositivo
`intel:gpu`, `quantize=16` no lugar do `half` deprecado) e plugin de GPU do
OpenVINO
(https://docs.openvino.ai/2026/openvino-workflow/running-inference/inference-devices-and-modes/gpu-device.html
— shape dinâmico é "preview" e rende menos que estático; cada shape novo
compila kernel em tempo de execução; precisão segue a IR; `ov::cache_dir`
cobre totalmente só modelo estático).

- `openvino.Core().available_devices` = `['CPU', 'GPU']`; GPU = "Intel(R)
  Iris(R) Xe Graphics (iGPU)".
- Export: o `vyra_ppe_640_dyn_openvino_model` já era dinâmico de verdade
  (`shape="?,3,?,?"` no `.xml`); o letterbox retangular vem da correção de
  `dynamic` no AutoBackend (§4.2).
- `YoloPPEDetector`: dispositivo (CPU|GPU) e dica de precisão
  (`INFERENCE_PRECISION_HINT` f32|f16); GPU com `CACHE_DIR`; falhou na GPU →
  compila na CPU e o diagnóstico mostra "CPU (fallback da GPU)"
  (`tests/test_runtime_do_modelo.py::test_gpu_que_nao_compila_cai_para_cpu`).
  O dispositivo ativo sai em `/api/diagnostics/pipeline` (`modelos.*.dispositivo`).
- Guarda (`concordancia-epi-20261013-140531.json`,
  `concordancia-pessoa-20261013-140747.json`), dispositivo conferido no JSON:

| candidato | EPI | pessoa | bancada EPI p50 |
|---|---|---|---|
| openvino-dyn@cpu-fp32 | 100 % | — | 705 ms |
| openvino-dyn@cpu-fp16 | 100 % | — | 675 ms |
| **openvino-dyn@gpu-fp32** | **100 %** | **100 %** | **125 ms** |
| openvino-dyn@gpu-fp16 | 99,17 % | 99,88 % | 105 ms |

  Hipótese registrada (não verificada): o 99,17 % do "OpenVINO dinâmico"
  anterior vinha do `device_name="AUTO"` do ultralytics caindo na GPU em f16;
  forçado na CPU, deu 100 %.
- CPU do servidor (batata 1 câm., 3 repetições, `*-l1-r*.json`):

| perfil | câm. | árvore | análises/rodada | CPU-ms por análise | CPU-ms por quadro | encodes por quadro |
|---|---|---|---|---|---|---|
| batata | 1 | onnx | 40, 16, 17 | **6,431.8** [2,836.9, 6,818.4, 6,431.8] | **249.9** [241.4, 249.9, 258.2] | **1.0** [1.0, 1.0, 1.0] |
| batata | 1 | ovgpu16 | 103, 77, 80 | **1,349.6** [1,023.1, 1,403.7, 1,349.6] | **239.7** [215.9, 239.7, 247.8] | **1.0** [1.0, 1.0, 1.0] |
| batata | 1 | ovgpu32 | 90, 76, 52 | **1,400.7** [1,167.1, 1,400.7, 2,034.4] | **226.0** [213.5, 226.0, 278.4] | **1.0** [1.0, 1.0, 1.0] |

  Relógio, sob saturação — indicativo:

| perfil | câm. | árvore | n | FPS de análise/câm. | idade da análise p50 (ms) | idade p95 (ms) | latência de alerta (s) | fundo (% de 1 núcleo) |
|---|---|---|---|---|---|---|---|---|
| batata | 1 | onnx | 3 | **0,28** [0,67, 0,27, 0,28] | **4.310** [1.846, 4.541, 4.310] | **5.674** [2.757, 5.674, 5.674] | **5,7** [5,4, 8,8, 5,7] | 845 |
| batata | 1 | ovgpu16 | 3 | **1,33** [1,72, 1,28, 1,33] | **943** [741, 943, 1.010] | **2.165** [1.184, 2.194, 2.165] | **3,0** [3,0, 2,7, 4,4] | 722 |
| batata | 1 | ovgpu32 | 3 | **1,27** [1,50, 1,27, 0,87] | **966** [826, 966, 1.511] | **1.959** [1.205, 1.959, 3.056] | **3,4** [3,1, 3,4, 4,4] | 640 |

- Decisão: GPU FP32 e FP16 empatam em CPU-ms (dentro de 10 %) → **FP32**
  (100 % no guarda). `RUNTIME_ORDEM=openvino-gpu,onnx,pytorch`; sem GPU visível
  ao OpenVINO, o resolvedor pula para o ONNX
  (`test_sem_gpu_o_auto_pula_o_openvino_gpu`).
- Ressalva para a banca: o perfil "batata" limita a CPU do servidor a 2
  E-cores, mas a iGPU é a da máquina inteira. Uma máquina fraca de verdade com
  gráfico Intel integrado tem esse caminho; sem iGPU, vale o ONNX.

## L2 — modelo de EPI leve para o modo batata (ADENDO 1): sem candidato

Restrição de segurança declarada: peso `.pt` do Ultralytics é *pickle* —
carregá-lo (inclusive para converter em ONNX) executa código do arquivo. Peso
de terceiros só entra aqui em formato que carrega sem executar código (ONNX,
safetensors).

Buscas (13/10):

- Hugging Face, API pública `api/models?search=` com `ppe`, `helmet`,
  `hardhat`, `safety vest`, `personal protective`, filtrando quem publica
  `.onnx`: só modelos de **capacete apenas** (`vivekvar/helmet-v5` Apache-2.0,
  `goyalsamarth/helmetCPT` MIT, `HudatersU/Safety_helmet` GPL-3.0,
  `raghavendra24/helmet-yolov8s` sem licença…) ou fora do tema; o único com
  capacete E colete em ONNX é o próprio Vyra (`Hexmon/vyra-yolo-ppe-detection`,
  YOLOv8**m**, CC BY 4.0, treinado no "PPE Combined Model v4" da Roboflow).
- Busca web: candidatos YOLOv8n de EPI (`Tanishjain9/yolov8n-ppe-detection-6classes`
  MIT, `Hansung-Cho/yolov8-ppe-detection`, `ayushgupta7777/safetyvision-yolov8`)
  só em `.pt` — descartados pela restrição acima.
- GitHub (`gh search repos "ppe detection yolov8"`): dos 20 primeiros, só
  `Kanon14/PPE-Detection-YOLOv8` e `Venta02/ppe-detection-yolov8` declaram
  licença (MIT), e nenhum dos dois publica pesos (árvore sem `.onnx/.pt/.safetensors`).

Conjuntos rotulados públicos com capacete e colete e licença compatível
existem (ex.: "Dataset of Personal Protective Equipment", Data in Brief 2025,
CC BY 4.0, 2.286 imagens, YOLO; "Construction Site Safety" da Roboflow, CC BY
4.0, com split de teste). Sem candidato aprovado, a avaliação comparativa não
foi feita. **Resultado: L2 não entra; o Vyra segue como único modelo de EPI.**
Sem treino nem fine-tune nesta máquina, como manda o adendo.

# PR2 — diferenciais F1–F10

Base: WIP `b344f5e` (F1 replay, F3 aproximação, F4 privacidade, F5
diagnóstico, F7 mapa de calor, F9 relatório, F10 escala, Sobre/Licenças,
"Iniciar" ligando todas) trazido por cherry-pick sobre o PR1 + alavancas L1/L2.
Antes de código novo: build do frontend ok (o `dist` do WIP estava defasado do
próprio código) e suíte com 1 falha — `test_toda_rota_exige_sessao` acusou
`GET /api/alerts/<int:alert_id>/clip/<int:indice>.jpg -> 404`. A rota TINHA
`@login_required`; a varredura só substituía parâmetros conhecidos e deixava
`<int:indice>` literal na URL, então o Flask respondia 404 antes da
autenticação. Corrigido o TESTE para substituir qualquer parâmetro (fica mais
forte: rota nova passa a ser exercitada, não ignorada por 404).

## F2 — queda pelo modelo, atribuída a um ID; linha do tempo por ID

- Sondagem na fixture `next_queda` (domínio público): o Vyra vê `fall_detected`
  em 44 de 500 quadros, em janelas curtas — a maior em 6,0–6,9 s (24 quadros);
  as outras de 1 a 7 quadros. Nos quadros com a pessoa caída, o detector de
  pessoa NÃO a vê: maior fração da caixa de queda dentro de alguma pessoa
  = 0,00–0,18.
- Regra (`app/vision/quedas.py`): a queda pertence à pessoa que mais a contém
  (≥ 0,3); se ninguém a contém, a caixa de queda entra no rastreador como
  pessoa e ganha ID. Alerta `fall_detected`, crítico, feature `falls`,
  independente da pose. A pílula da tela mostra emergência com pessoa (queda,
  SOS) antes de EPI crítico.
- Linha do tempo de conformidade por ID (`app/services/linha_do_tempo_conformidade.py`):
  só mudanças (EPIs, queda, zona), 120 eventos por ID, 64 IDs; API
  `/api/cameras/<id>/conformidade-por-id[/<pessoa>]`; botão "Linha do tempo"
  no cartão da pessoa, com o aviso "ID de rastreio — não identifica ninguém".
- E2E `test_queda_do_modelo_chega_ao_navegador_com_id`: o alerta chega com
  "Queda detectada — Pessoa N". Primeiras execuções: (1) chegou SEM pessoa —
  a injeção só existia no modo com detector de pessoa separado, e o padrão é
  `MULTI_PERSON_DETECTION=false`; corrigido para os dois modos; (2) com 4–5
  câmeras no agendador, a câmera "Queda" analisa pouco dentro da janela de
  ~0,9 s e a histerese (NÃO afrouxada) quase nunca confirma — o teste pausa
  as outras câmeras durante a execução, como o técnico faria. Limitação real
  registrada para a BANCA: num pátio com muitas câmeras numa máquina fraca,
  uma queda que o modelo só enxerga por < 1 s pode não virar alerta.

## F3 — a pílula de aproximação nunca aparecia (E2E) — duas causas

1. No modo de um modelo só (`MULTI_PERSON_DETECTION=false`), as pessoas vinham
   da classe `Person` do Vyra SEM passar pelo rastreador; a projeção só usa
   pessoas com ID de rastreio → nunca havia trilha. Corrigido: essas pessoas
   também passam pelo rastreador (`tests/test_rastreio_modelo_unico.py`, que
   falha no código anterior).
2. Mesmo rastreadas, quase não havia pessoas: medido (1 quadro/s, Vyra@640 e
   yolov8n@640), pessoas por quadro — multidão **0,1 vs 7,1**, canteiro **0,0
   vs 1,0**, queda **0,0 vs 2,0** (classe `Person` do Vyra vs yolov8n). No
   padrão antigo o sistema estava praticamente cego para pessoas — quedas por
   ID, aproximação, linha do tempo e EPI por pessoa dependiam disso. Diagnóstico
   no servidor do E2E: 18 leituras de status em 90 s, 0 pré-alertas.
   **Mudança: `MULTI_PERSON_DETECTION=true` é o padrão** (o `.env.example` já
   dizia `true` e o teste de onboarding conferia isso; o default do código
   divergia). Os portões do PR1 já foram medidos com ele ligado. Simulação com
   yolov8n e a mesma zona: 5 de 15 análises com pré-alerta a 1 análise/s.
   Também: `PERSON_MODEL_PATH` padrão passou de `yolov8n.pt` (que o ultralytics
   baixaria da internet se não achasse no diretório de trabalho) para
   `models/yolov8n.pt`.

## Pose no mesmo `auto` (OpenVINO na iGPU) — consequência do detector de pessoa padrão

Com `MULTI_PERSON_DETECTION=true` como padrão, cada análise passou a rodar
também o yolov8n (~100 ms na iGPU) e o **YOLO-pose em PyTorch (236 ms por
quadro, medido na fixture de queda)** — no modo antigo a pose não rodava, porque
os esqueletos só são calculados no ramo multi-pessoa. A reexecução do E2E
(`bench/runtime/e2e-pr2c.out`) caiu para 7/11: queda, replay, aproximação e
privacidade estouraram o tempo; na janela do teste de queda não houve nenhum
`fall_detected` na câmera Queda (houve depois, fora da janela).

Correção: o YOLO-pose entra no resolvedor de runtime como modelo `esqueleto`
(`POSE_RUNTIME=auto`, mesma `RUNTIME_ORDEM`). Guarda estendida para pose:
concordância de caixas (≥ 97 %) **e** erro dos keypoints — distância ao da
referência PyTorch@640 dividida pela diagonal da caixa, p95 ≤ 0,05
(`scripts/concordancia.py --modelo esqueleto`, 120 quadros das 3 fixtures):

| candidato | concordância | pares | erro kp p50 | erro kp p95 | bancada p50 |
|---|---|---|---|---|---|
| OpenVINO iGPU FP32 | 100 % | 459 | 0,0000 | 0,0000 | 63 ms |
| OpenVINO iGPU FP16 | 99,25 % | 456 | 0,0008 | 0,0048 | 78 ms |
| OpenVINO CPU FP32 | 100 % | 459 | 0,0000 | 0,0000 | 150 ms |
| ONNX dinâmico | 100 % | 459 | 0,0000 | 0,0000 | 87 ms |
| PyTorch (medição avulsa) | referência | — | — | — | 236 ms |

Bancada é só pista (processo isolado); a decisão vale pelo E2E e pelo bench do
portão. Fonte: `bench/results/concordancia-esqueleto-20261013-170752.json`.

## Revisão visual do PR2 (capturas 1920x1080 e 1366x768, claro e escuro)

`python e2e/capturas_de_tela.py` (16 telas × 4 combinações, fora do git em
`bench/runtime/capturas/`). Critérios: cor só para status, tema claro como
padrão da demo, nada quebrando em 1366x768. Corrigido:

| tela | problema | correção |
|---|---|---|
| foco da câmera | barra de abas quebrava em 2 linhas ("Mais" caía) | sem quebra; abas mais justas abaixo de 1440 px |
| foco da câmera | pílula do alerta vazava pela direita do vídeo | largura máxima com reticências |
| Diagnóstico | KPIs (4 colunas fixas) e barras estouravam o painel | grade `auto-fit` e colunas com mínimo |
| foco da câmera | cabeçalho mostrava o caminho inteiro do arquivo (com a pasta do usuário) | só o nome do arquivo |
| Prova de escala | modal sem respiro (texto colado na borda) | padding |
| Pessoas | descrição antiga ("quando o modelo PPE completo estiver disponível") | "o número é do rastreio, não uma identidade" |

Não corrigido (anotado): na grade, o primeiro cartão fica ~15 px mais alto que
os vizinhos — causa não isolada; "Visão geral" do supervisor ainda é um
marcador "em construção" (vira o painel agregado/Modo TV no PR3, G8).

## E2E com pessoas de verdade na cena: dois testes e uma regra de tela

Com o detector de pessoa padrão, a câmera Multidão passou a ter ~8 pessoas com
alerta. Rodada `e2e-pr2d`: 9/11. Diagnóstico por captura de tela (script
Playwright contra o servidor do E2E, 120 s na aba Alertas):

- **Replay**: a aba Alertas agrupa por pessoa e recolhe os grupos quando há
  mais de 3 (`alerts.tsx`); o botão "Ver replay" existia, dentro de um grupo
  fechado. O teste agora abre o primeiro grupo. Sem mudança no produto.
- **Pílula de aproximação**: a pílula cedia a QUALQUER alerta `high`, e "pessoa
  na área de risco" é `high`. Com a zona do teste (40 % do quadro) sempre havia
  alguém dentro, então a projeção de quem se aproximava nunca aparecia — o
  mesmo aconteceria numa doca movimentada. Regra nova (`cobrePreAlerta`): o
  pré-alerta cede só para emergência (queda, SOS) ou EPI crítico.

Ruído observado (não corrigido neste PR, vai para o PR4): ~1.000 alertas em 16
min no servidor do E2E — 5 por pessoa e um novo conjunto a cada troca de ID do
rastreador na multidão. Cada alerta também grava o próprio clipe de replay.

## Alerta que ficava ativo depois de parar a câmera

Achado no log do servidor do E2E (`alert_state_stop_resolution_failed`,
"Instance <Alert> is not bound to a Session"). `CameraWorker.stop()` roda na
thread da requisição e resolve alertas criados na sessão da thread do worker; o
objeto chegava desanexado e expirado pelo commit. Resultado: exceção (lendo
`status`) ou commit vazio — o alerta continuava `active` no banco com a câmera
parada. Correção: `AlertRepository.na_sessao()` traz o alerta para a sessão da
thread atual antes de ler/alterar. Teste que reproduz (falhava com `'active' ==
'resolved'`): `tests/test_alert_repository.py::test_resolve_de_outra_thread_nao_perde_o_alerta`.

## F6 — celular como câmera via QR

- Docs: getUserMedia só em contexto seguro, e em contexto inseguro
  "`navigator.mediaDevices` is `undefined`"
  (https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia);
  IP de LAN em `http://` não é contexto seguro
  (https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts).
- Fonte `celular://<token>` (`app/vision/fonte_celular.py`); token aleatório é
  a única credencial do celular: só envia quadro para aquela câmera.
  `GET /cam` e `POST /api/celular/<token>/quadro` são as duas rotas públicas
  (listadas na varredura, com testes de token desconhecido → 404, imagem
  inválida → 400, teto de taxa → 429). Pareamento `GET /api/cameras/<id>/celular`
  só para técnico.
- HTTPS local: `python run.py --https` gera certificado autoassinado com o
  `cryptography` (SAN localhost, 127.0.0.1 e IP da LAN; chave em `instance/`,
  fora do git) e escuta na rede.
- QR: Project Nayuki, MIT, arquivo único vendorizado em
  `frontend/src/vendor/qrcodegen.ts` (lido antes: só cálculo, sem rede/eval/DOM)
  — ATRIBUICOES.md.
- E2E `test_celular_vira_camera_pelo_link_do_qr` com o Chromium em
  `--use-fake-device-for-media-stream --use-fake-ui-for-media-stream`: página
  sem login, câmera falsa, ≥ 10 quadros no servidor, QR na aba da câmera.

## F8 — YOLOE-26 (vocabulário aberto): descartado

- Condições da missão ATENDIDAS: (a) o Vyra carrega no ultralytics 8.4.176
  (instalação lateral `bench/_ul84`, `YOLO_CONFIG_DIR` separado) com
  concordância de **100 %** contra o 8.3.40 (121 de 121 caixas,
  `scripts/dump_deteccoes.py`); (b) a suíte passa inteira sob o 8.4:
  **486 passed**.
- Bloqueio de LICENÇA: prompt de texto no YOLOE-26 baixa o codificador
  `mobileclip2_b.ts` (~254 MB, doc https://docs.ultralytics.com/models/yoloe/).
  A licença dos modelos MobileCLIP (`apple/ml-mobileclip`, arquivo
  `LICENSE_MODELS`) restringe a "Research Purposes" e diz que isso "does not
  include any commercial exploitation, product development or use in any
  commercial product". Definir classes de EPI do produto com ele é
  desenvolvimento de produto. A variante sem prompt (`-seg-pf.pt`) usa
  vocabulário embutido de procedência não documentada, e não há conjunto
  rotulado aqui para provar qualidade.
- Achado ao tentar: sob o 8.4 o runtime "OpenVINO GPU" rodou na CPU (log:
  "inference on (CPU)"; concordância 99,17 %) — os ajustes de runtime deste
  projeto dependem dos internos do 8.3.40. Trocar de versão exige refazer essa
  camada.
- **Decisão: F8 descartado; ultralytics segue 8.3.40.**

## 4.1 Pipeline

| Mudança | Motivo | Evidência |
|---|---|---|
| Captura em thread por câmera, último quadro vence (`app/vision/captura_continua.py`) | arquivo tocava em câmera lenta; fonte não era lida durante a inferência | `fracao_do_tempo_real` 0,11 → 0,83–0,88 (bench `pr1`, atual, 1 e 4 câm.) |
| Agendador único de inferência em rodízio (`app/services/agendador_de_inferencia.py`) | lock global sem ordem; vídeo acoplado à fila | espera do lock p50 **37 s** (4 câm., baseline sob carga) eliminada; vídeo publicado 0,84 → 10,7 fps com 4 câmeras |
| Lote de N câmeras numa chamada `predict` | — | implementado (`INFERENCIA_LOTE`), **desligado**: ver seção "Medido e rejeitado" |
| Encode uma vez por versão, só sob demanda; anotação só sob demanda | anotação 34–48 ms + JPEG 16–29 ms por quadro sem espectador | `test_encode_so_sob_demanda_e_no_maximo_um_por_quadro` (contrato novo, asserts exatos) |
| Overlay no navegador (`LiveVideo` em canvas, `video_feed?meta=1`) | caixas desenhadas no pixel custavam cópias do quadro inteiro | — |
| Quadro reduzido para a resolução da câmera | fixture 1280×720 numa câmera de 960×540 | bytes de vídeo por quadro ~220 KB → ~100 KB |
| `active_alerts` só quando muda (+ pulsação de 2 s) | saía a cada quadro de cada câmera | testes de escopo do socket seguem verdes |
| Sala `foco:<id>` para `analysis`/`compliance_state` | telemetria de 8 Hz ia para o parque inteiro | 3 testes novos em `tests/test_escopo_socket.py` (inclui operador tentando focar outra câmera) |
| Snapshot de alerta fora do loop (`GravadorAssincrono`, fila limitada) | `imwrite` no quadro em que o alerta nasce | `tests/test_gravador_assincrono.py` |
| Config do caminho do frame lida uma vez (`recarregar_config`) | `app.config.get` e parse de pisos por classe a cada quadro | — |
| Cópia do quadro em `VideoStream._on_success` removida | 2,7 MB copiados por quadro para um campo que ninguém lê no app | `tests/test_video_stream.py` 25 passed |
| Backoff com jitter no player do navegador; estado RECONECTANDO/SEM SINAL na tela | requisito 4.1 / 7 | E2E `test_queda_da_fonte_mostra_reconectando_e_volta` |

**Socket.IO binário — não adotado como transporte de vídeo, com motivo:** o
cliente força long-polling (`frontend/src/socket/client.ts`) e, no Engine.IO,
binário em polling vai em base64 (ver PESQUISA.md §9, protocolo Engine.IO). O
vídeo já é binário por HTTP multipart; movê-lo para o socket pioraria.

## 4.2 Runtime

Guarda: `python scripts/concordancia.py` (referência PyTorch@640, IoU ≥ 0,5,
mesma classe; 126 quadros das 3 fixtures). Resultados em
`bench/results/concordancia-*.json`.

| Candidato (EPI) | Concordância | Veredito |
|---|---|---|
| ONNX estático 640 | 95,04 % | **reprovado** (< 97 %): o letterbox quadrado 640×640 difere do retângulo do PyTorch |
| ONNX dinâmico 640 | **100,0 %** | aprovado no guarda; decisão de uso pelo bench do worker |
| OpenVINO estático 640 | 94,65 % | reprovado |
| OpenVINO dinâmico 640 (antes da correção) | 95,04 % | reprovado — mesmo número do ONNX estático |
| OpenVINO dinâmico 640 (letterbox retangular) | **99,17 %** (capacete 97,6 %, colete 100 %, pessoa 100 %, queda 90,9 % = 5 de 6) | **aprovado** |

**OpenVINO "dinâmico" que rodava como estático.** O `.xml` exportado tem
`shape="?,3,?,?"` (dinâmico de verdade). O problema estava no consumo: o
ultralytics 8.3.40 só preenche `AutoBackend.dynamic` para ONNX e TensorRT
(`ultralytics/nn/autobackend.py`, linhas 221 e 306–319); no OpenVINO fica
False, e o predictor usa letterbox QUADRADO
(`engine/predictor.py:158`, `auto=same_shapes and (self.model.pt or getattr(self.model, "dynamic", False))`).
`YoloPPEDetector._marcar_openvino_dinamico` lê a forma parcial da entrada do
modelo compilado e liga `dynamic`; a primeira chamada é refeita. Testes:
`tests/test_yolo_ppe_detector.py` (dinâmico refaz e vira retangular; estático
continua quadrado). Pessoa (yolov8n) OpenVINO dinâmico: **100 %**
(`concordancia-pessoa-20261013-055740.json`).

**OpenVINO recompilado na CPU com teto de threads.** O mesmo backend compila
com `device_name="AUTO"` e só `PERFORMANCE_HINT`. Pela doc do plugin de CPU
(https://docs.openvino.ai/2026/openvino-workflow/running-inference/inference-devices-and-modes/cpu-device/performance-hint-and-thread-scheduling.html),
no hint LATENCY o padrão de `INFERENCE_NUM_THREADS` é "P-cores ou
P-cores+E-cores" (10 neste i7-1355U) e o pinning de CPU fica desligado no
Windows. Com o processo preso a 2 núcleos, isso é oversubscription. O detector
agora recompila em `CPU`, LATENCY, `INFERENCE_NUM_THREADS = VISIONEPI_THREADS`
quando definido.
| OpenVINO INT8 | — | exige `nncf`; instalado como opcional (`pip install nncf==3.4.0`, `pip check` limpo, numpy/torch intactos) — resultado em BENCHMARKS.md |

Pessoa (yolov8n): ONNX estático 640 = **98,25 %** (aprovado).

- `app/vision/runtime_do_modelo.py`: `PPE_RUNTIME`/`PERSON_RUNTIME` = pytorch |
  onnx | openvino | auto; só export **aprovado** entra; teste de carga + 1
  inferência no boot com **volta ao `.pt`** se falhar (`tests/test_runtime_do_modelo.py`).
- Sessão ONNX recriada com `CPUExecutionProvider` explícito, teto de threads e
  `session.intra_op.allow_spinning=0`: o ultralytics 8.3.40 escolhia o
  `AzureExecutionProvider` (primeiro da lista no onnxruntime 1.29). Doc:
  https://onnxruntime.ai/docs/performance/tune-performance/threading.html
- INT8 OpenVINO segue a doc de export da Ultralytics
  (https://docs.ultralytics.com/modes/export/ — argumentos `int8`/`data`) e a de
  integração OpenVINO (https://docs.ultralytics.com/integrations/openvino/).

## 4.3 Resolução

| imgsz (EPI) | Concordância | Capacete | Colete |
|---|---|---|---|
| 640 (a própria referência, controle de sanidade) | **100,0 %** | 100 % | 100 % |
| 512 | 72,0 % | 17 % | 86 % |
| 416 (o `.env.example` de antes) | **63,6 %** | **8 %** | 78 % |
| 320 | 51,1 % | 0 % | 64 % |

**Correção de registro (13/10):** uma anotação da sessão anterior dizia "640
fica em 72 % de concordância", o que é impossível com 640 como referência. Re-
executado (`python scripts/concordancia.py --candidatos pytorch:640,pytorch:512,openvino-dyn:640`
→ `bench/results/concordancia-epi-20261013-055538.json`): **pytorch:640 = 100,0 %**
(121 de 121 caixas) e **pytorch:512 = 72,03 %**. O 72 % era do 512, com o
rótulo trocado na anotação; a tabela acima sempre esteve certa.

Nenhum passa os 95 % → **mantido 640** (regra pré-decidida). Pessoa a 416:
86,0 % → também 640. Consequência registrada: o `.env.example` anterior (416)
perdia quase todo capacete que a referência vê.

## 4.4 Pose por pessoa

- `app/vision/yolo_pose_detector.py`: yolo11n-pose (Ultralytics, AGPL-3.0)
  numa passada para todas as pessoas; cada esqueleto associado ao track do
  detector de pessoa por IoU; pose a cada K inferências com reaproveitamento
  do último esqueleto por track; `POSE_BACKEND=yolo|mediapipe`.
- **Rejeitado:** usar o yolo11n-pose COMO detector de pessoa (economizaria uma
  chamada de modelo): concordância de caixas de pessoa com o yolov8n de **83,8 %**
  (`scripts/concordancia.py --modelo pessoa`). Sem rótulo não dá para saber
  qual dos dois erra — então não se troca.
- Testes de queda: `tests/test_pose_yolo.py` (esqueleto vai para o track certo;
  queda sai com o `person_id` da pessoa caída). Nas fixtures reais, nem o
  YOLO-pose nem o MediaPipe acham a pessoa deitada do filme antigo; em pé, o
  YOLO-pose achou torso em 3 de 8 quadros e o MediaPipe em 1 de 8 (sonda
  `fall_probe`). Upgrade para YOLO26 (Ultralytics ≥ 8.4): ver "Bloqueado".

## 4.5 Tracker

`python scripts/comparar_trackers.py` (mesmas detecções, ~5 Hz; pessoas reais
contadas a olho em folhas de contato):

| Fixture | Pessoas reais | IDs IoU | IDs ByteTrack | p95 IoU | p95 ByteTrack |
|---|---|---|---|---|---|
| bench | 3 | 5 | **3** | 0,29 ms | 5,39 ms |
| queda | 9 (7 + 2 após corte) | 7 | 6 | 0,73 ms | 11,69 ms |
| multidão | > 30 (não contadas) | 18 | 26 | 2,84 ms | 16,79 ms |

ByteTrack reduz fragmentação mas custa **+5 a +14 ms p95**, acima do teto de
1 ms → **não adotado como padrão**. Vendorizado (MIT) em `app/vision/bytetrack/`
e disponível como laboratório (`TRACKER=bytetrack`).

**Re-decisão de 13/10 com o critério da missão** (ByteTrack vira padrão se
reduzir fragmentação nas fixtures E custar p95 ≤ 3 % da inferência p95 no
perfil batata). Detector da aplicação (yolov8n@640), E-cores 10 e 11,
`VISIONEPI_THREADS=2` (`bench/results/trackers-yolov8n-20261013-*.json`):

| passo (fixture 25–30 fps) | fixture (reais) | IDs IoU | IDs ByteTrack | ByteTrack p95 / inferência p95 |
|---|---|---|---|---|
| 6 (~5 Hz) | bench (3) | 4 | 2 (funde identidades) | 0,7 % |
| 6 | queda (9) | 7 | 8 | 1,0 % |
| 6 | multidão (>30) | 22 | 35 | **4,2 %** |
| 25 (~1 Hz) | bench / queda / multidão | 4 / 5 / 15 | 0 / 5 / 12 | 0,3 / 1,1 / 3,8 % |
| 50 (~0,5 Hz, taxa real do batata) | bench / queda / multidão | 5 / 4 / 14 | 0 / 4 / 11 | 0,5 / 1,0 / 2,9 % |

E no servidor real (bench batata 1 câm., ONNX, intercalado, 2 repetições,
`*-trk-r{1,2}.json`): latência de alerta IoU 37,0 / 37,6 s contra ByteTrack
37,8 / 40,3 s. Nas taxas baixas o ByteTrack nem ativa track nos clipes curtos
(0 IDs na `bench`), e a ~5 Hz ora funde, ora fragmenta mais. Redução de
fragmentação **não demonstrada** e custo **acima de 3 %** na multidão →
**fica em config** (`TRACKER=bytetrack`), padrão segue IoU.

## 4.6 Controlador adaptativo

`app/services/controlador_adaptativo.py` + `MonitorService.tique_adaptativo`:
mede o p95 da idade do quadro **no momento da inferência**; degraus: N
(frequência de detecção) → K (frequência de pose) → Hz de telemetria;
histerese (3 leituras para degradar, 5 para recuperar, banda morta). Aviso
**DEGRADADO** na tela com o que foi reduzido.

**13/10 — o degrau de resolução saiu.** Existia um degrau "imgsz para o próximo
valor aprovado" (vazio por config, mas presente no código e ligável por
`ADAPTATIVO_IMGSZ_PERMITIDOS`). Regra da missão: o controlador só mexe em
frequência de inferência, de pose e de UI. Removidos o degrau, a config e a
escrita de `det.imgsz` em `MonitorService._aplicar_adaptativo`. Os testes que
afirmavam a descida para 320 foram trocados por afirmações mais estritas do
contrato novo: nenhum degrau tem chave de resolução, nenhuma redução cita
resolução, e o `MonitorService` real no nível máximo mantém EPI e pessoa em
640 (`tests/test_controlador_adaptativo.py`, 10 testes).

## 4.7 Frontend

- Vídeo e overlay fora do React (refs/canvas); seletores finos em `MessageBar`
  (presente em toda tela) e no editor de zona; `compliance` não é mais escrito
  duas vezes por tique.
- Leitor multipart sem cópia quadrática e "último quadro vence" no decode
  (`frontend/src/socket/multipart.ts`).
- `ObjectURL`: o único uso (`export.tsx`) já revoga; sockets limpos no unmount.
- Linha do tempo: já limitada a 80 itens (`MAX_TIMELINE`); virtualização não
  se justifica nesse tamanho.

## Medido e rejeitado

- ByteTrack como padrão (4.5), yolo11n-pose como detector de pessoa (4.4),
  ONNX/OpenVINO estáticos (4.2), qualquer imgsz < 640 (4.3).

## Bloqueado / não feito

- **Pexels**: HTTP 403 (Cloudflare) para cliente automatizado; API exige chave
  → fixtures do Wikimedia Commons (ATRIBUICOES.md).

## URLs de documentação citadas

- https://docs.openvino.ai/2026/openvino-workflow/running-inference/inference-devices-and-modes/cpu-device/performance-hint-and-thread-scheduling.html
- https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-system_cpu_set_information
- https://github.com/opencv/opencv/blob/4.x/modules/videoio/include/opencv2/videoio.hpp (CAP_PROP_N_THREADS)

- https://onnxruntime.ai/docs/performance/tune-performance/threading.html
- https://docs.ultralytics.com/modes/export/
- https://docs.ultralytics.com/integrations/openvino/
- https://docs.ultralytics.com/guides/yolo-thread-safe-inference/
- https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia
- https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts
- https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html

## PR3 — funções criativas (G1–G10 + laboratório)

Princípios de gamificação aplicados em todo o PR: só indicador positivo (minuto
conforme, check-in, alerta reconhecido, rótulo revisado); minuto sem ninguém na
câmera é neutro (nunca se premia "zero alerta"); pontuação só por setor/câmera,
nenhum número por pessoa ou por ID.

| item | o que entrou | teste | onde |
|---|---|---|---|
| G1 Portal de Entrada | `/portal?camera=N`: só os EPIs exigidos (os da portaria da câmera), cada um confirmado / faltando / "não verificável neste enquadramento" (pés ou mãos fora do quadro pela borda da caixa e pelos keypoints; EPI que o modelo não detecta). Libera com todo item verificável confirmado por 3 análises seguidas; check-in vira evento (meta do setor). Sem foto. | `test_portal.py` (9), E2E | `gate_service.avaliar_portal`, `components/portal.tsx` |
| G2 Você vs. a IA | `/desafio`: 3 rodadas, ~1,6 s de clipe desfocado e congela; mesma regra de pontuação para a pessoa e a IA contra gabarito curado à mão; placar só na sessão do navegador | `test_desafio.py` (4), E2E | `services/desafio.py`, `GABARITO.md` |
| G3 SOS por gesto | punhos acima da cabeça ≥ 3 s, por ID, alerta crítico (com histerese) | `test_sinais_por_id.py` (keypoints sintéticos) | `vision/sinais_por_id.py` |
| G4 Pessoa imóvel | pé desloca < 8 % da altura da caixa por ≥ 20 s dentro da zona → alerta "não é diagnóstico" | idem | idem |
| G5 Planta baixa | aba Planta: 4 cliques no chão do vídeo + 4 na planta padrão → homografia; pés ao vivo, zona e calor na planta; pé fora da área calibrada sai vazado | `test_planta.py` (10, pontos conhecidos), E2E | `vision/planta.py`, `planta-panel.tsx` |
| G6 Alerta falado | crítico vira frase pt-BR (`speechSynthesis`, voz local primeiro), respeita o mudo, uma frase esperando no máximo, ≥ 4 s entre inícios, mesma frase não repete em 30 s; sem voz pt-BR → bipe | E2E com Web Speech falsa | `audio/fala.ts` |
| G7 Ergonomia (estimativa) | flexão do tronco 2D por ID; tempo acumulado acima de 45° e 60°; alerta após 10 s acima de 45°; texto diz que não é RULA/REBA/NR-17 | `test_sinais_por_id.py` | `vision/sinais_por_id.py` |
| G8 Modo TV | `/tv` legível a 5 m e "Visão geral" do supervisor: por setor (`Camera.location`), conformidade agora, sequência de minutos 100 %, metas do supervisor (tabela `metas_setor`), conquistas positivas; `prefers-reduced-motion` | `test_andon.py` (8), `test_tv.py`, E2E | `services/andon.py`, `api/tv.py` |
| G9 Aprendizado ativo | EPI com confiança 0,25–0,5 → recorte do quadro público (desfocado), ≤ 1 por câmera a cada 5 s, fila ≤ 300; `/rotular` com ← →; zip YOLO só com confirmados, README com origem e licença; total da equipe no Modo TV | `test_aprendizado_ativo.py` (4), E2E | `services/aprendizado_ativo.py` |
| G10 NR-6 | relatório de turno liga cada infração ao item da NR-6 com trecho literal (6.5.1 e, 6.6.1 a, Anexo I A.1/B.1/C.1/F.1/G.1); colete e máscara ficam "sem item sustentado", com o motivo | `test_nr6.py` (6) | `services/nr6.py` |
| Laboratório | "Pergunte à planta": desligado (`LAB_PERGUNTE_ATIVO`); o LLM só escolhe uma agregação de um catálogo fixo (nunca SQL), o servidor valida e executa, resposta rotulada como gerada | `test_pergunte_a_planta.py` (9) | `services/pergunte_a_planta.py` |

Custo por análise (`scripts/custo_dos_prototipos.py`, 4 câmeras, 120 s,
`bench/results/custo-prototipos-20261013-185753.json`), p95 sobre o orçamento
do quadro (p50 das inferências da câmera, 371–528 ms): G1 0,03 %, G3/G4/G7
≤ 0,16 %, G5 0,28 %, G8 0,03 %, G9 ≤ 3,4 % (≈ 10 ms quando recorta, no máximo a
cada 5 s). Todos abaixo do limite de 10 %.

Limites honestos:
- G2 usa 3 rodadas com caixas marcadas a olho; é exercício, não métrica.
- G3 entra no app, mas **não** no roteiro da demo: não achei vídeo de licença
  livre com alguém erguendo os braços para verificar (regra da missão).
- G5 tem só a planta padrão (SVG gerado); upload de planta e planta
  multicâmera ficaram de fora.
- A câmera padrão (menor id) usa `DEFAULT_FEATURES` do ambiente; quem tem `.env`
  antigo precisa acrescentar `sos,ergonomia,imobilidade` para ligar G3/G4/G7 nela.

Achado na revisão visual (G9): os recortes de capacete saíam inteiros
pixelados — o desfoque de privacidade cobre a cabeça, e o capacete está nela.
Agora o recorte desfoca só olhos e nariz (keypoints da pose); sem keypoints de
alguma pessoa, não recorta; com a privacidade ligada, óculos, máscara e
protetor auricular (só visíveis no rosto) não são coletados. Recorte mínimo de
96 px (capacete a distância tem ~20 px). Na mesma revisão: o vídeo do `/portal`
saía sem proporção (corrigido no CSS).

Erro meu corrigido antes do merge: a primeira versão do gancho do G9 caiu
dentro do bloco `with self._thread_lock` e tirou dele o contador de quadros
(`_frame_counter`/`_latest_capture_ts_ms` só atualizavam quando havia fila de
rótulos). Achado lendo o diff; a suíte não pegava.

Queda breve nunca virava alerta (achado ao investigar o E2E de queda, que
falhou nas duas rodadas completas do PR3 e passava isolado): a histerese comum
(8 quadros OU 2 s com ≥ 2 confirmações) não acontece num evento que o modelo vê
por ~1 s. Medido a 4 análises/s com o Vyra (classe `Fall-Detected`, conf 0,35):

| gravação | análises com queda | maior sequência | pares seguidos |
|---|---|---|---|
| queda | 9 de 84 | 4 (~1 s) | 3 |
| multidão (sem queda) | 2 de 63 | 1 | 0 |
| canteiro (sem queda) | 0 de 30 | 0 | 0 |

A queda real aparece em análises seguidas; o falso positivo, isolado. Regra
nova só para emergência (`ALERT_EMERGENCY_RULES=fall_detected`): 2 análises
NOVAS seguidas criam o alerta. EPI e área de risco seguem a histerese comum
(teste garante). Amostra pequena (3 gravações): o risco de falso alarme de
queda numa planta real fica registrado para a banca.

Corrida benigna no Socket.IO (`join_room` de cliente que acabou de
desconectar, `KeyError` no log do E2E) tratada no handler de foco.

### E2E do PR3 — o que as rodadas completas acharam

As rodadas completas (17 fluxos, 4 câmeras) falharam em testes diferentes a
cada vez. Para parar de adivinhar, o `e2e/conftest.py` passou a gravar a tela e
o texto da página de todo teste que falha (`bench/runtime/e2e-falhas/`). Com
isso:

| falha | o que a captura mostrou | correção |
|---|---|---|
| `/rotular` não avançava | erro 500 no console; no log, `WinError 32`: a imagem era servida com `send_file`, o handle ficava aberto e o Windows recusava mover o arquivo ao decidir | **bug do produto**: imagem servida da memória; teste de regressão falha no código antigo |
| privacidade | depois de `clear_cookies()` a página voltou logada como técnico: uma requisição em andamento devolveu o cookie | teste sai da página antes de limpar |
| pílula de aproximação, portal | multidão a ~0,5 análise/s (DEGRADADO) com 4 câmeras; o rastreio/histerese não fecha a tempo | como no teste de queda: as outras câmeras param durante o teste e voltam no fim |
| fala | a 1ª frase veio do Canteiro — o produto fala alertas críticos de qualquer câmera, como a especificação pede | teste aceita qualquer câmera e exige o nome dela na frase |

## PR4 — demo, confiabilidade, docs

| item | o que entrou | evidência |
|---|---|---|
| `python run.py --demo` | banco isolado `instance/demo/demo.db` recriado a cada vez; 3 contas com senha gerada e impressa só no terminal; Canteiro/Pátio/Escada das gravações ("GRAVAÇÃO") e a webcam como Portal "AO VIVO" (sem webcam, o Portal usa o Canteiro); zona e planta do Pátio prontas; metas por setor; tema claro; LLM desligado; só capacete, colete e luvas ligados (menos ruído) | `tests/test_demo.py`, `tests/test_falhas_da_demo.py`; boot real medido: ~70 s até responder |
| `flask --app wsgi demo reset` | pede ao servidor (token local em `instance/demo/token`) para limpar alertas, eventos, clipes e rótulos e recriar os workers; sem servidor, limpa o banco | medido: **7,7–9,7 s** o comando inteiro (0,6–2,6 s no servidor) |
| câmera "Arquivo" | volta ao início do vídeo (`em_loop`) em vez de contar 15 falhas e reconectar a cada volta | `tests/test_video_stream.py` |
| testes de falha | modelo ausente, webcam ausente, LLM fora no resumo, banco indisponível no checklist (fonte inválida, banco sem tabela e LLM fora no analisador já tinham teste) | `tests/test_falhas_da_demo.py` |
| soak 20 min | 0 erros de console; RSS pico +6,1 % | BENCHMARKS "Soak do PR4" |
| `scripts/bench.py --rapido` | ≤ 5 min, perfil atual, 1 e 4 câmeras — para medir na máquina da banca | DEMO.md |
| E2E da prova de escala (F10) | o roteiro só usa momentos com E2E; F10 não tinha | `e2e/test_fluxos.py` |
| docs | DEMO.md (roteiro de 5 min, reset, plano B), BANCA.md (15 perguntas), README | — |

Achados no caminho:

- **O `flask demo reset` levava ~2 min.** Todo comando `flask` cria o app, e o
  `MonitorService` validava os runtimes (compilando os modelos na GPU) já na
  construção. A validação passou a ser feita no aquecimento ou na primeira
  câmera ligada. Mesmo assim o app completo leva 9–20 s só para importar e
  montar nesta máquina (OpenVINO, OpenCV), então o `wsgi.py` monta um Flask
  mínimo para esse comando. O reset no servidor também levava 12,6 s: cada
  `stop()` espera até 2 s pela thread de captura, e as câmeras paravam em
  sequência. Agora param e religam em paralelo.
- **`requirements.txt` não declarava o runtime padrão.** O `.venv` desta
  máquina tinha `openvino` e `onnxruntime` instalados à mão, e o arquivo dizia
  "OpenVINO fica FORA de propósito". Isso era verdade antes do PR1 (loop
  síncrono) e deixou de ser no PR2. Num clone novo, o `auto` cairia em PyTorch
  sem aviso. Agora estão declarados (OpenVINO só em x86-64), junto com
  `cryptography` (F6) e `playwright` (E2E/bench).
- **README desatualizado em três pontos** (inferência a 416; "nenhuma regra lê
  `Fall-Detected`"; "OpenVINO e ONNX não adotados"): reescritos com o estado
  atual.
- `.env.example` continua sem edição: a permissão desta máquina nega leitura e
  escrita nele. Ainda diz `YOLO_IMGSZ=416`, enquanto o código usa 640 por
  padrão. Quem copia o `.env.example` herda 416 — fica registrado para a equipe
  corrigir à mão.
