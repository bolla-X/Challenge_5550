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


---

# MISSÃO 2 (`MISSAO-2.md`)

Rollback: tag `pre-missao-2` (HEAD de `feat/completo-com-rebrand` = `906c81e`) e
`main-pre-release` (HEAD de `main` = `6c3ed61`), as duas publicadas.

Antes de começar: `bench/results/` tinha 11 JSON e `scripts/dump_deteccoes.py`
citados no BENCHMARKS/CHANGELOG mas nunca versionados — entraram num commit
próprio (`chore: versiona evidências…`).

### Novidades: Funções novas e visual renovado (14/10/2026)

<!-- Lido por scripts/gerar_novidades.py para a tela "Novidades" do app. Só título e frase para quem usa:
     sem números de medição, sem nomes de arquivo, no vocabulário do GLOSSARIO.md. -->

- **Gêmeo digital.** A planta em 3D com as câmeras, as áreas de risco e as pessoas na cor do estado, nunca em foto.
- **Simulador "E se?".** Teste outra área de risco, outro tempo de confirmação ou outros EPIs sobre o que já aconteceu, antes de mudar a regra de verdade.
- **Cadeia de custódia.** Imagem de evidência, replay e troca de privacidade ficam encadeados, e a tela de Auditoria aponta qualquer alteração.
- **Linha causal.** O que aconteceu com cada Pessoa dentro de um incidente, passo a passo, com o replay no instante certo.
- **Raio-X.** Aperte X para ver por que a IA decidiu: esqueleto, confiança por classe e o que foi descartado.
- **Modo Apresentação.** Um roteiro de cenas para mostrar o sistema, controlado pelo celular por QR code.
- **Retrospectiva.** Cartões do turno e da semana com dados reais, prontos para salvar como imagem.
- **Liga de Setores.** Pontos só positivos por setor, missões por turno e o nível da planta.
- **Tente enganar a IA.** No Portal de Entrada, quem visita tenta driblar a detecção e vê o que o modelo enxergou.
- **Replay e mapa de calor.** Os quadros de antes e depois de cada alerta e onde a planta concentra as violações.
- **Celular como câmera.** Pareie um celular por QR code e use-o como câmera.
- **Aplicativo instalável.** O painel funciona como aplicativo e avisa o alerta crítico com o app aberto.
- **Incidentes mais claros.** Alertas da mesma regra e da mesma zona agora formam um incidente só.
- **Visual novo.** Tema claro e escuro, fontes e ícones próprios e transições suaves entre as telas.

## PR5 — consertos que afetam a demo (Fase A)

### P0.1 Rodízio ponderado (câmera em foco ≥ 50 %)

- **O quê.** `AgendadorDeInferencia` troca o rodízio igualitário por *smooth
  weighted round-robin* (o do nginx): as câmeras em foco somam peso igual ao
  número das outras (≥ 50 % das vagas) e as outras dividem o resto. Guarda de
  espera: quem está há `INFERENCIA_ESPERA_MAX_S` (2,5 s) sem inferência é servido
  primeiro. Foco = `video_feed` aberto (tela de foco, portal, quiosque, palco —
  a grade usa miniatura) **ou** consulta do portal nos últimos `FOCO_LEASE_S` (3 s).
- **Por quê.** O E2E do PR3 só passava parando as outras câmeras: com 4 câmeras o
  portal recebia 1/4 das inferências e não chegava a "Liberado".
- **Evidência.** `tests/test_agendador_ponderado.py` (8): com 4 câmeras sempre
  pendentes, foco ≥ 50 %; inferência de 0,5 s → nenhuma outra fica > 3 s sem
  análise; 0,9 s → a guarda segura em ≤ 2,5 s + 3 inferências. `/api/diagnostics/pipeline`
  passa a mostrar `em_foco` e `servidos_em_foco` por câmera.
- **E2E.** As pausas de câmera dos testes de queda, aproximação e portal foram
  removidas; cada um termina provando que as 4 câmeras estavam ligadas
  (`_todas_ligadas`).

### P0.2 Incidentes por (câmera, regra, zona) + re-associação de ID

- **O quê.** Tabela `incidentes` (migração `a7b8c9d0e1f2`). O alerta continua
  por pessoa (é a evidência: caixa, clipe, replay); o incidente agrupa os alertas
  da mesma regra e zona, com os IDs envolvidos, o pico de pessoas e quando foi
  reconhecido. Zona = nome da área de risco se a pessoa está dentro, "Fora da
  zona" se não, "Toda a câmera" sem zona desenhada. API `/api/incidentes`
  (lista, detalhe, reconhecer). A pílula do vídeo e a aba de alertas mostram o
  incidente ("Sem capacete · Zona A · Pessoas 4, 7, 9").
- **Re-associação.** `app/vision/reassociacao.py`, por cima de qualquer
  rastreador: track novo a até 1,5 × a largura da caixa de onde um track sumiu,
  em até 2 s, herda o ID (`REASSOCIAR_*`). IDs estáveis próprios, para o herdado
  nunca colidir com um cru reutilizado. `tests/test_reassociacao.py` (8).
- **Medição** (`scripts/contar_incidentes.py`, servidor real, 1 câmera, todos os
  EPIs, 150 s com o vídeo aberto; "antes" = worktree em `pre-missao-2`):

  | gravação | análises | alertas criados | IDs com alerta | máx. itens no painel | incidentes criados | máx. incidentes ao mesmo tempo | máx. por regra e zona |
  |---|---|---|---|---|---|---|---|
  | multidão, antes | 295 | 279 | 30 | **64** alertas | — | — | — |
  | multidão, depois | 327 | 250 | 34 | **11** incidentes | 11 | 11 | **1** |
  | queda, antes | 146 | 150 | 9 | 23 alertas | — | — | — |
  | queda, depois | 141 | 96 | 7 | 12 incidentes | 30 | 12 | 1 |
  | canteiro, antes | 307 | 3 | 1 | 3 | — | — | — |
  | canteiro, depois | 398 | 3 | 1 | 3 | 3 | 3 | 1 |

  JSON em `bench/results/incidentes-*.json`. CPU total da máquina durante as
  rodadas: 78–100 % (inclui o próprio servidor). As rodadas não veem exatamente
  os mesmos quadros (a gravação toca em tempo de relógio): a contagem de alertas
  varia; o que muda de natureza é o painel — de até 64 linhas para no máximo 1
  incidente por regra e zona.
- **Consequência.** A demo volta a exigir **todos** os EPIs
  (`EPIS_DESLIGADOS_NA_DEMO = ()`). Calçado e protetor auricular continuam "não
  suportado pelo modelo", nunca "faltando".
- **Achado no caminho.** O ID do incidente sumia na renovação do alerta (o
  `touch` regrava a metadata inteira): o serviço agora repassa o `incidente_id`.
  Incidente "ativo" de uma execução anterior é fechado ao ligar a câmera.

### P0.3 `.env.example` e a permissão que o bloqueava

- `YOLO_IMGSZ=416` → **640** (o 416 foi reprovado no guarda: capacete 8 %), e o
  comentário de que o OpenVINO "foi rejeitado e não é instalado" (falso desde o
  PR2) foi corrigido. Teste novo: `test_env_example_infere_a_640`.
- **Permissão.** O arquivo estava negado por regras amplas no
  `~/.claude/settings.json` do usuário (não havia `.claude/settings*.json` no
  projeto): `Read(**/.env.*)` e `Edit(**/.env.*)`. Como a regra de negação do
  Claude Code não tem exceção, elas foram trocadas pelas variantes explícitas
  (`.env.local`, `.env.*.local`, `.env.development`, `.env.dev`,
  `.env.production`, `.env.prod`, `.env.staging`, `.env.test`, `.env.backup`,
  `.env.bak`, `.env.old`), mantendo `Read/Edit(**/.env)`. Cópia do arquivo
  anterior: `~/.claude/settings.json.bak-missao2`. O hook global
  `guard-secrets.sh` continua barrando **qualquer** `.env.*` que não seja
  `.example/.template/.sample/.dist` — a variante não listada continua protegida
  por ele. O `.env` real não foi lido nem alterado.

## PR5 — funcionalidades fora da caixa (Fase B)

| item | o que entrou | testes |
|---|---|---|
| X1 Gêmeo digital (`/gemeo`) | three.js **0.169.0** (MIT, versão fixa, carregado só nesta rota); planta com setores, zonas como volumes translúcidos recortados ao chão calibrado, cone de visão por câmera, cápsulas na cor do estado (nunca foto) com interpolação; clique na pessoa → linha do tempo + replay; na zona → histórico; órbita limitada; visão de drone; pausa com a aba oculta; regulador de resolução; fallback 2D (`?2d=1` força). `/api/gemeo`. Demo: as 3 gravações calibradas numa planta só (aproximação a olho, dito na doc). | `test_gemeo.py`, `test_planta.py` (recorte), E2E |
| X2 Simulador "E se?" (`/simulador`) | trilha por câmera (`trilha.jsonl` rotativo, 16 MB × 4, sem imagem, ~60 B/pessoa/análise); reprocessa com outra zona (vértices arrastáveis), histerese ou EPIs, com a MESMA lógica de histerese do serviço; compara proposta × regra atual simulada × alertas reais. | `test_simulador.py` (7), E2E |
| X3 Cadeia de custódia | tabela `custodia`; alerta (campos imutáveis), snapshot, clipe (manifesto por arquivo) e troca de privacidade viram elos `sha256(seq|tipo|ref|conteúdo|anterior|instante)`; verificação aponta o primeiro elo quebrado e, no clipe, o arquivo. `/auditoria` e "Verificar integridade" no incidente. | `test_custodia.py` (9, inclui **1 byte adulterado no clipe → elo 3, arquivo 0001.jpg**), E2E |
| X4 Linha causal | narrativa determinística por ID (aproximação F3, entrada/violação, permanência, sinais, reconhecimento), só com o registrado; cada passo abre o replay no quadro do instante. | `test_linha_causal.py` (5), E2E |
| X5 Raio-X (tecla X) | esqueleto com juntas nomeadas, barras de confiança por classe com o piso marcado, detecções descartadas pelo filtro com o motivo, trilhas fantasma de 5 s, vetor de velocidade do F3, decisão (alerta / confirmando n/8 / ok) separada da confiança. | E2E |
| X6 Palco (`/palco`) | roteiro único no servidor (12 cenas); cena reinicia a gravação quando precisa (determinístico); QR → `/palco/controle?t=` (token por processo, só muda a cena); teclado continua mandando se o celular falhar. | `test_palco.py` (4), E2E teclado + Chromium emulando Pixel 7 |
| X7 Retrospectiva (`/retrospectiva`) | stories de turno e semana com dados reais; PNG 1080×1350 por card desenhado em canvas (sem lib); abre no Modo TV nos últimos 10 min do turno (`?retro=1` força). | `test_liga.py`, E2E (PNG validado pelo cabeçalho) |
| X8 Liga de Setores (`/liga`) | livro-razão `liga_pontos` só com pontos positivos por setor (check-in 10, reconhecido ≤ 1 min 15, ≤ 3 min 5, falso positivo revisado 5, rótulo 2, minuto conforme 1); temporada = semana ISO; missões por turno (supervisor); nível da planta; confete leve e som curto só na transição, respeitando mudo e `prefers-reduced-motion`. No Modo TV, na Visão geral e na Retrospectiva. | `test_liga.py` (11), E2E |
| X9 Tente enganar a IA | modo desafio do portal: o visitante declara a tentativa (boné, colete falso, sem EPI, EPI real); Raio-X ligado; cada item explica o que o modelo viu ("visto com 0,62", "viu com 0,31, abaixo do piso — descartado"); placar anônimo da sessão, incluindo "erros com EPI real". | `test_portal.py`, E2E |
| X10 PWA | manifesto, `sw.js` na raiz (casca offline: navegação rede-primeiro com fallback, `/static/dist/` cache-primeiro, `/api` nunca), ícones originais (`scripts/gerar_icones.py`), notificação do sistema + vibração em alerta crítico com o app aberto (uma por incidente, a cada 8 s no máximo). | `test_pwa.py`, E2E |

**Documentação lida e citada (X10):**
- Service Worker exige contexto seguro; `http://localhost` conta como seguro:
  https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API
- Notifications API exige contexto seguro; `requestPermission()` só num gesto do
  usuário; no celular `new Notification()` lança `TypeError` — por isso a
  notificação sai por `registration.showNotification`:
  https://developer.mozilla.org/en-US/docs/Web/API/Notifications_API
- Push com o app **fechado** não entra: o Push API entrega a mensagem por uma
  assinatura num serviço de push do navegador, com o servidor da aplicação
  enviando para esse endpoint — dependência externa que a demo offline não tem:
  https://developer.mozilla.org/en-US/docs/Web/API/Push_API

**X1 — tempo de quadro** (Playwright, 1920×1080, as 4 câmeras inferindo na
mesma iGPU): Chromium com a GPU (`--use-angle=d3d11`, o "perfil normal" de um
navegador de verdade) → intervalo entre quadros p95 **16,7 ms**, desenho p95
4,8 ms. O headless padrão do Playwright desenha no **SwiftShader** (software):
133 ms — por isso o E2E do gêmeo usa um navegador com GPU, e a cena ganhou um
regulador que reduz a resolução interna quando o p95 passa de 40 ms.

**Achados no caminho:**
- A limpeza de artefatos (`CLEANUP_ON_MONITOR_START`) apagava os snapshots a
  cada câmera ligada — e a evidência apagada fica "ausente" na cadeia de
  custódia. A demo já limpa ao subir e no reset; ela e o E2E deixam de limpar a
  cada câmera ligada.
- A custódia fazia 1 commit por alerta criado dentro do loop
  (`test_uma_analise_com_muitos_alertas_faz_um_commit_so_e_emite_depois` pegou).
  Primeira correção: elos na mesma transação da análise. Ela criou uma
  **inversão de trava** (o worker segurava a escrita do SQLite esperando a trava
  da cadeia; o gravador de evidências segurava a trava esperando a escrita →
  `database is locked` e, pior, a sessão do worker ficava quebrada para sempre).
  Correção final: os alertas commitam primeiro e os elos entram num segundo
  commit, em lote (2 commits por análise, o teste mudou para isso); SQLite em
  **WAL** com `busy_timeout` 15 s (`app/extensions.py`); o worker faz rollback da
  sessão em qualquer erro do laço, em vez de seguir com ela inválida.
- Abrir e fechar o arquivo da trilha a cada análise custava ~6 ms no Windows: o
  arquivo fica aberto, com flush a cada segundo.
- O simulador com a regra atual reproduz os alertas reais da demo (21/21, 16/16
  por regra numa janela de 5 min) — é a prova de que ele simula a mesma coisa.
- **Gravador de evidências afogado.** Na rodada 3 do E2E o log mostrou
  `gravador_fila_cheia descartados: 731`: com os 7 EPIs, uma pessoa abre até 7
  alertas na MESMA análise, e cada um enfileirava o seu quadro e o seu replay
  (8 s de JPEG) — o mesmo conteúdo, 7 vezes. Agora: **um** arquivo de quadro e
  **um** conjunto de quadros de replay por análise. Os outros alertas recebem só
  o próprio `clip.json` com `"quadros_em": "alert_<primeiro>"`, e a API serve os
  quadros pela pasta do primeiro. A custódia registra **um** elo de quadro e
  **um** de replay por análise, com `alert_ids` de todos; o manifesto do replay
  cobre todas as pastas (`alert_N/arquivo`), então adulterar o índice de qualquer
  alerta do lote aponta o elo e o arquivo. Testes: `test_replay.py`
  (`test_alertas_da_mesma_analise_compartilham_os_quadros`), `test_custodia.py`
  (3 novos: verificação por alerta acompanhante, índice adulterado, API).

### Decisões de P0.1 tomadas com medição (`scripts/diagnostico_foco.py`)

- **Foco vence sob carga.** Com a máquina a 100 % de CPU (outros processos), a
  guarda de espera (2,5 s) disparava para as 3 câmeras de fundo o tempo todo e o
  foco caía para 26 % das inferências. Regra: quando há atrasados, a câmera em
  foco alterna com eles (nunca duas atrasadas seguidas sem o foco entre elas).
  Medido sob carga (0,5–1 inferência/s no total): foco **52–58 %**.
- **Prioridade de confirmação de emergência = uma vaga.** Uma detecção de queda
  dá à câmera **uma** ficha (válida 2 s) para a análise de confirmação, sem esperar
  o rodízio. A primeira versão (prioridade por janela de tempo) deixava os falsos
  positivos de queda da `multidao` roubarem as vagas do portal.
- **Gravação desacelera durante a confirmação** (`CAPTURA_FPS_CONFIRMACAO`, só
  em fonte gravada): a queda da gravação durava menos que duas análises sob carga.
  A regra das 2 análises **não** foi afrouxada: `scripts/confianca_de_queda.py`
  mostrou falso positivo de queda com confiança **0,84** num quadro da `multidao`
  — um quadro sozinho não separa queda real de falso positivo.
- **Aproximação (F3):** a trilha expirava em 2 s e, sob carga, a análise seguinte
  chegava depois; `validade_s` 6 s, e o aviso só sai para trilhas presentes na
  análise atual.
- **A queda trocava de ID no meio da confirmação.** A confirmação de emergência
  conta análises seguidas da MESMA chave (regra + ID), e o rastreador troca o ID
  de quem cai (caixa em pé × caixa no chão quase não se sobrepõem). Medido com o
  log `queda_vista` e as 4 câmeras (`diagnostico_foco.py --foco queda`, 180 s):
  pares `person_14 → person_3` (3,1 s) e `person_5 → person_4` (3,6 s) na mesma
  queda; a única confirmada manteve o ID. Agora uma queda a ≤ 1,5 largura de
  caixa de outra vista há ≤ 5 s herda o sujeito dela (`continuidade_de` no
  metadado registra o ID que o rastreador deu). `tests/test_quedas.py` (2 novos).
- **Verificação da cadeia inteira em 92 s.** O E2E de 20 min deixou 2 523 elos e
  31 mil quadros de replay; no Windows cada abertura de arquivo custava ~1 ms.
  Leitura dos arquivos em 8 threads: 23 s na mesma cadeia (e a deduplicação acima
  corta os quadros por análise). A mesma medição mostrou 171 elos "conteúdo
  alterado" — não era adulteração: o diagnóstico tinha gravado `alert_1…` na
  MESMA pasta de replay do E2E (os ids recomeçam a cada banco). E2E e diagnóstico
  passam a ter pastas de replay e trilha próprias, zeradas ao subir, e o
  gravador apaga quadros velhos de uma pasta com o mesmo id antes de escrever.
- **Linha causal:** "na Zona A sem capacete" virou "estava na Zona A sem
  capacete" (o passo começava sem verbo quando a pessoa já surgia dentro da zona).
- **Queda com o vídeo aberto: limite assumido, não contornado.** Rodada 4 do
  E2E: com a tela de foco aberta a gravação anda em tempo real, a pessoa fica
  ~0,8 s no chão (6,2–7,0 s do clipe), e com 4 câmeras numa máquina carregada
  duas análises não cabem nisso — 5 min só com avistamentos isolados
  (`queda_vista` a cada 30–70 s). A ficha de prioridade e a câmera lenta da
  confirmação só começam DEPOIS do resultado da 1ª análise (~1 s de latência).
  A mesma gravação sem espectador anda na taxa útil e confirmou 5 quedas no
  mesmo E2E. A regra das 2 análises fica (o falso positivo de 0,84 da
  `multidao` é de um quadro só). Consequências: o E2E da queda espera na grade
  e confere o evento com o ID depois, na aba "Quedas e postura"; a cena "Queda"
  do `/palco` mostra o incidente de queda com a linha causal e o replay do
  momento (`/api/incidentes?rule=`), não o vídeo ao vivo. Numa câmera real a
  pessoa caída fica no chão bem mais que 0,8 s.
- **`[bootstrap] failed: Failed to fetch`** no console quando a página navegava
  no meio do primeiro carregamento (ou o servidor estava ocupado): falha de rede
  agora tenta de novo em 2 s (até 5 vezes) e só vira erro se persistir.
- **400 do Socket.IO no console** (gêmeo, rodadas 3 e 6): o socket conectava no
  carregamento do módulo, antes de saber se havia sessão; na tela de login o
  servidor rejeitava (`socket_rejected_unauthenticated`, ~37 por rodada) e o
  poll seguinte daquele `sid` voltava 400. `autoConnect: false`: o socket só
  conecta em `subscribeToServerEvents`, depois do login.

## ADENDO 2 — retomada depois do reinício do PC (14/10)

### Recuperação

- Estado em disco conferido antes de qualquer mudança: `pytest tests` **649
  passed**, `ruff check .` limpo, `npm run build` reproduz o `app/static/dist`
  commitado byte a byte (nenhum arquivo mudou). Commit `2116c1c` ("wip:
  recuperação pós-reinício") e `git push -u origin next-2026`. Nenhum processo
  nosso tinha sobrado; os processos de terceiros que apareceram depois
  (`driver1015.py` ×6, `his-prospeccao`) não foram tocados.
- O bench "antes × PR5" morreu na 4ª rodada da r1 (`atual-4cam-pr5`): código
  de saída `3221226091` = `0xC000026B`, *STATUS_DLL_INIT_FAILED_LOGOFF* — o
  Windows desligando. Refeito do zero (BENCHMARKS.md, "Portão do PR5").
- **Subida com o cache dos modelos frio leva minutos.** O E2E falhou duas vezes com
  "conexão recusada": o servidor ainda compilava os modelos para a iGPU e o
  `e2e/conftest.py` esperava 120 s e seguia em silêncio. Medido por modelo
  (validação de runtime): 1ª medição pós-reinício pose **213 s**, EPI 31 s,
  pessoa 4 s (248 s no total); a seguinte, com o cache do OpenVINO
  (`ov_cache/`) quente, 7,8 / 22 / 2 s (**32 s**). Causa não identificada: a
  worktree `ch5550-antes`, com o `ov_cache/` dela, validou em 10 s no mesmo
  dia, então não é o reinício por si.
  O conftest agora espera até 300 s e falha dizendo por quê; o DEMO.md manda
  subir a demo uma vez antes da banca.

### A. Tempo até "Liberado" no Portal (4 câmeras ligadas, E2E ×10)

`E2E_PORTAL_REPETICOES=10 pytest e2e/test_fluxos.py -k portal_de_entrada`; cada
repetição grava a portaria (zera o portal), espera o lease de foco expirar e
mede desde abrir `/portal` até `veredito=approved`. p95 por posto mais próximo
(com 10 amostras, é o máximo). Arquivo: `bench/results/portal-liberado-adendo2-20261014.json`.

| rodada | regra | p50 | p95 | p50 / p95 desde o 1º item |
|---|---|---|---|---|
| antes | 3 análises seguidas; análise sem ninguém zera; foco 0,5 | 16,8 s | 81,0 s | 14,7 / 80,3 s |
| depois | + até 2 análises sem ninguém neutras; foco 0,7 | 5,4 s | 31,9 s | 4,8 / 30,6 s |
| **final** | + até 2 análises sem ninguém neutras; **foco 0,5** | **5,6 s** | **21,6 s** | 5,0 / 20,9 s |

**Meta (p50 ≤ 5 s, p95 ≤ 10 s): não atingida.** p50 ficou 0,6 s acima; p95, 2×.

Como chegamos aqui (tudo medido, nada presumido):

1. **Onde o tempo ia.** O portal passou a contar o veredito BRUTO de cada análise
   (`diagnostico` em `/api/cameras/<id>/portal`: contagem, item que faltou e a
   sequência A/D/W com o ID). Em 20 rodadas de `scripts/diagnostico_foco.py
   --portal --repeticoes 10`: o foco recebe ~0,6–1,3 análise/s; **um terço das
   análises não acha ninguém** (W) — na `bench.mp4` os trabalhadores são
   pequenos e passam atrás do guarda-corpo — e cada W zerava a sequência.
   Um simulador das regras sobre essas sequências reproduz a regra antiga
   exatamente (20/20) antes de testar outras.
2. **Confirmações = 3.** Já era o valor (`PORTAL_CONFIRMACOES=3`, desde o PR3):
   não havia o que reduzir.
3. **Peso do foco até 70 % — medido e revertido.** `INFERENCIA_FRACAO_FOCO`
   (novo, 0,5–0,7). A guarda de espera manda: com 4 câmeras a ~2,6 inferências/s,
   o foco ficou em 49 % com 0,7 contra 45 % com 0,5, e os intervalos das outras
   câmeras acima de 3 s foram de **9 %** (0,5: 4/46, 2/51, 5/43; máx. 5,2 s) para
   **~25 %** (0,7: 7/30, 5/37, 7/24; máx. 5,4 s). O 0,7 quebra a regra dos 3 s;
   o padrão voltou a 0,5. O agendador agora mede isso (`maior_espera_s`,
   `esperas_acima_de_3s` por câmera em `/api/diagnostics/pipeline`).
   **Divergência com o que estava escrito:** a seção P0.1 acima diz que
   "nenhuma outra fica > 3 s" — isso vale na simulação com custo fixo; na
   máquina real, sob carga de terceiros, 9 % dos intervalos passam de 3 s
   mesmo com 0,5 (a guarda dispara a 2,5 s, mas várias câmeras vencem juntas e
   a alternância com o foco atrasa a última).
4. **Até 2 análises sem ninguém detectado ficam neutras** na confirmação
   (`PORTAL_AUSENCIAS_TOLERADAS=2`): não contam nem zeram; a 3ª seguida zera.
   "Não detectado" não é "ausente" (regra da missão). Uma análise que VÊ a
   pessoa sem o EPI continua zerando — liberar por engano é o erro caro. No
   simulador: pior caso de 27 análises (ou nunca, em 90 s) para 5.
   `tests/test_portal.py::test_ninguem_detectado_no_meio_da_confirmacao_nao_zera_mas_epi_faltando_zera`.
5. **Rejeitados no simulador:** sequência por ID de rastreio (10 de 20 rodadas
   nunca liberariam — o ID fragmenta na fixture) e sequência por item (o
   capacete sai "não verificável" na maioria das análises; ficaria mais
   estrito, não mais rápido). Antecipar as outras câmeras pelo prazo de 3 s
   renderia, na simulação a 0,37 s por inferência, só 5–8 pontos de vaga ao
   foco: não implementado.

**Por que o p95 não fecha.** As rodadas lentas são as com análises "D" seguidas
(`DDWAWDDWAWAWDAWWWAAA`, `AADWWDAADADWAADADAWWAA`): a maior pessoa do quadro
muda entre trabalhadores distantes, e o modelo vê alguns sem capacete. A
`bench.mp4` é um plano aberto de obra, não um portal; com a webcam diante de
uma pessoa (o Portal da demo quando há webcam) a situação é outra — mas isso
não foi medido aqui (o teste automatizado não tem uma pessoa diante da câmera).
Fica como ameaça no ESTADO.md.

### B. Queda na demo: gravação a 0,25× com o alerta ao vivo

- Regra de emergência mantida: **2 análises seguidas**.
- A cena "Queda" do `/palco` declara `velocidade: 0.25` e `inicio_s: 4.0`
  (`app/services/palco.py`). Ao entrar na cena, a velocidade muda **antes** de a
  troca de cena responder (`_ajustar_velocidades`, síncrono) e a gravação
  reabre em 4,0 s (`VideoStream.inicio_ms`, vale uma vez; a volta do loop é do
  início). Sair da cena devolve todas as gravações a 1×.
- `CameraWorker.tocar_gravacao`: só arquivo (câmera ao vivo não tem como andar
  devagar e fica em 1×). O ritmo da captura vira `fps da fonte × 0,25` e fica
  fixo **inclusive durante a confirmação de emergência** — antes ela baixava a
  gravação para 4 fps, e o rótulo deixaria de ser verdade.
- O rótulo **"GRAVAÇÃO · 0,25×"** sai do que o servidor informa
  (`video.velocidade` no status), nunca do que a cena pediu; o selo de feed de
  qualquer tela mostra "Gravação · 0,25×" enquanto durar.
- Quando o incidente de queda aparece, o painel com a linha causal e o replay
  entra ao lado do vídeo, como continuação da cena.
- Evidência: `tests/test_camera_lenta.py` (4), `tests/test_palco.py::test_camera_lenta_so_dura_a_cena_da_queda`,
  E2E `test_palco_queda_ao_vivo_em_camera_lenta` (rótulo conferido no DOM e
  dentro da caixa do vídeo no instante do alerta; alerta ao vivo **12,9 s**
  depois de entrar na cena — ~2 s de reabertura + 8,8 s de gravação até a
  queda a 0,25× + a confirmação), captura revisada
  (`bench/runtime/e2e-capturas/palco-queda-camera-lenta.png`).

## PR6 — Experiência SSS+++ (Fase C)

Sistema de design em `docs/NEXT2026/DESIGN.md` (fonte da verdade:
`frontend/src/styles/tokens.css`).

- **Tokens:** cor só para estado, tipografia com tamanho/entrelinha/tracking
  juntos, espaço em grade de 4/8, raios e sombras nomeados, movimento com
  durações e curvas nomeadas. Claro é o padrão da demo; o escuro tem valores
  próprios.
- **Fontes self-hosted:** Geist e Geist Mono (SIL OFL 1.1,
  https://github.com/vercel/geist-font), em `frontend/public/fonts`, offline.
- **Ícones:** um conjunto só, Phosphor (MIT, `@phosphor-icons/react` 2.1.10
  fixado), peso regular, via `components/icones.tsx`; nenhum SVG de ícone à mão.
- **Componentes únicos** (botão, cartão, badge de estado, tabela, modal, toast,
  skeleton, estado vazio com ilustração SVG original e uma ação) e o teste
  `e2e/test_estados.py`, que procura "em construção", TODO, lorem,
  placeholder e travessão no texto visível de todas as rotas.
- **Movimento:** View Transitions entre telas (`document.startViewTransition`)
  e entre rotas (`@view-transition { navigation: auto }`); sem a API o
  navegador troca a tela sem animação (MDN:
  https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API). Tudo
  respeita `prefers-reduced-motion` (só troca de opacidade curta).
- **Revisão visual** em quatro rodadas de capturas (`e2e/capturas_de_tela.py`:
  29 telas e estados × 3 tamanhos × 2 temas, pela própria demo), crítica
  escrita com nota por item em `docs/NEXT2026/galeria/index.md`. O que ela
  achou e virou regra está em DESIGN.md ("O que a revisão visual mudou"); os
  maiores: os ícones dos botões estavam invisíveis (uma regra CSS antiga
  apagava ícones preenchidos), o Início e Contas eram dois cartões vazios, a
  barra superior ocupava um terço da tela do celular, alertas mostravam código
  interno (`missing_vest`), o Modo TV quebrava "0 min" em duas linhas e o Raio-X
  virava uma parede de painéis numa multidão (agora: 3 maiores, sem sobrepor).
- **Capturas pela demo** (`run.py --demo`) com `DEMO_WEBCAM=0` (novo), para a
  galeria nunca fotografar a webcam de quem roda; as senhas da demo ficam só
  na memória do script de captura.
- **README de vitrine** com GIF do palco, duas imagens, destaques e "como rodar
  em 3 comandos"; `scripts/preparar.py` baixa os pesos conferindo o SHA-256
  (os `.pt` são pickle), as gravações e aprova os runtimes rápidos.

## ADENDO 3 — fechar o PR6 e integrar com a main (14/10)

### Vídeo do palco (1.1)

- Conferido o MP4 gravado em segundo plano: 142 s, 1920×1080, H.264, as 12
  cenas aparecem (folha de contato, 1 quadro a cada 4 s). Dois defeitos: o MP4
  e o GIF começavam na tela de login, e o Portal mostrava a multidão do
  canteiro. `e2e/video_do_palco.py` agora corta MP4 e GIF a partir da abertura
  do palco; regravado depois do item 1.2.

### Portal com cenário realista (1.2)

- **Fixture `portal.mp4`** (`scripts/fetch_fixtures.py`, que ganhou `recorte`
  e `vai_e_volta`): close de um armador de frente, capacete e colete, quadros
  7000–7084 do vídeo 13 do Moira Close (CC BY-SA 4.0), recortado e ampliado
  1,6×, em vai-e-volta 3× (16,6 s). Escolhido **por medição** com o peso de
  EPI: pessoa em 88 % das amostras, capacete ≥ 0,40 em 64 %, colete em 71 %.
  Descartados (detalhe em ATRIBUICOES.md): plano da laje (capacete 0/14), vídeo
  21 da série, *Démontage d'échafaudage*. O `seek` do OpenCV neste webm cai ~5 s
  adiante (medido): a fixture lê em sequência.
- **Demo:** sem webcam, nasce a câmera "Portal" tocando `portal.mp4` (antes o
  Portal usava a multidão do Canteiro); sem a fixture, recua para o Canteiro.
  **E2E:** a câmera "Canteiro" (a de todos os testes de portal) toca `portal.mp4`.
- **Palco:** cada cena declara `ativas` (`"todas"` ou `"cena"`). Portal e
  "Tente enganar a IA" deixam só a câmera da cena analisando; as outras ficam
  **pausadas pela apresentação** (status `pausa: "apresentacao"`, badge e texto
  nos cartões, rodapé do palco lista quais). Pausa leve: sem análise e captura
  a 1 quadro/s; alertas, incidentes e histerese ficam como estavam (parar e
  religar o worker fecharia tudo isso). Ao sair da cena, voltam. Lease de 8 s
  renovado pela tela do palco (só ela; o celular de controle não sustenta a
  pausa): fechar o palco no meio da cena devolve as câmeras sozinho.
- **Fora do palco nada muda:** o agendador segue dando ao foco ≥ 50 % das vagas.
- **Correção achada pela medição:** ao pausar, cada câmera ainda tinha um
  quadro pendente no agendador e, esperando há mais de 2,5 s, a guarda de
  espera o servia **antes** do portal. `descartar_pendente` (teste em
  `tests/test_agendador_ponderado.py`).
- **Números (E2E do portal repetido 10×, 4 câmeras ligadas, `portal.mp4`;
  `bench/results/portal-adendo3-20261014.json`):**

  | cenário | p50 | p95 | máx |
  |---|---|---|---|
  | no palco, cena do Portal (outras pausadas) | **3,5 s** | **5,9 s** | 5,9 s |
  | no palco, antes de descartar o pendente | 7,3 s | 13,9 s | 15,8 s |
  | fora do palco (`/portal`, 4 câmeras analisando) | 13,4 s | 24,2 s | 24,4 s |

  Meta no palco (p50 ≤ 5 s, p95 ≤ 10 s): **atingida**. Fora do palco, não: o
  que domina são análises que veem a pessoa **sem** o capacete (o peso o vê em
  ~64 % dos quadros) e zeram a sequência (decisão em vigor: EPI faltando zera),
  com ~0,8–1,2 análise/s na câmera em foco. Medido com a CPU da máquina a 83 %
  por processos de fora do projeto (Docker, Teams, Edge, Java). Ao vivo, sem
  navegador, a câmera do portal fez 1,85 análise/s na cena (37 em 20 s) e as
  pausadas 0–1.

### Partida a frio e cache do OpenVINO (1.3)

- Doc oficial lida: *Model Caching Overview* —
  https://docs.openvino.ai/2025/openvino-workflow/running-inference/optimize-inference/optimizing-latency/model-caching-overview.html
  (`core.set_property({props.cache_dir: ...})`; na GPU gera `.cl_cache`, na CPU
  `.blob`; dispositivo sem `EXPORT_IMPORT` ignora sem erro — a iGPU daqui
  anuncia `EXPORT_IMPORT`).
- Antes: `CACHE_DIR` só na compilação da GPU e por modelo
  (`models/export/*/ov_cache`). Agora: um diretório, `runtime/ov_cache/` (fora
  do git; `OV_CACHE_DIR` muda), aplicado ao `Core` inteiro (GPU e CPU).
- `scripts/preparar.py --so-cache` (e o fim do `preparar.py` completo) sobe o
  app num banco temporário e aquece os três modelos nas formas das câmeras da
  demo (960×540, 960×720, 640×480): 56 s.
- `scripts/medir_partida.py`: de `run.py --demo` até a primeira análise
  publicada (`bench/results/partida-adendo3-20261014.json`):

  | cache | rodadas (s) | mediana |
  |---|---|---|
  | frio (pasta nova e vazia) | 58,3 · 67,8 · 75,9 | **67,8 s** |
  | aquecido pelo `preparar.py --so-cache` | 50,3 · 67,0 · 53,2 | **53,2 s** |

  Os ~4 min do ADENDO 2 não se repetiram: "frio" aqui é a pasta de cache, com
  os caches do sistema e do driver da GPU quentes (o PC não foi reiniciado).
  Hipótese não verificada: os 4 min vieram desses caches, logo após o reinício.
- Achados do caminho: no Windows o `python.exe` do venv é um lançador e
  `terminate()` deixava o servidor filho vivo, segurando o banco da demo
  (`encerrar_arvore` com `taskkill /T` em `e2e/conftest.py`); mesmo assim o
  SQLite é solto segundos depois, e o `medir_partida.py` espera o banco livre.

### Portão do PR6 (1.4)

Rodada única, `bench/runtime/portao-pr6-r2/` (saída de cada etapa em arquivo,
exit code conferido):

| etapa | resultado |
|---|---|
| `ruff check .` | 0 erros |
| `pytest` (unitários) | **664 passed** |
| `npm run build` (`tsc -b` + Vite) | exit 0 |
| `pytest e2e` (4 câmeras ligadas, sem pausa de contorno; axe em claro e escuro) | **36 passed** (12 min) |
| `scripts/bench.py --rapido` | 1 câm.: 1,86 análise/s, alerta 2,9 s; 4 câm.: 0,36 análise/s por câmera, alerta 5,0 s (`bench/results/20261014-134154-rapido.json`; 47–54 % de CPU de terceiros) |

A primeira rodada (`portao-pr6/`) reprovou e foi refeita inteira depois das correções:
- `test_gpu_que_nao_compila_cai_para_cpu`: o `set_property` do cache, dentro
  do `try`, fazia o detector desistir de recompilar quando falhava (no teste,
  um `Core` falso sem o método). Falha ao configurar o cache agora só registra
  `openvino_sem_cache` e compila assim mesmo; o teste confere o `CACHE_DIR`.
- 5 E2E nas abas da tela de foco: (1) corrida — o teste decidia entre "aba" e
  "menu Mais" antes de a faixa terminar de entrar (View Transition do PR6);
  agora espera a faixa; (2) **bug real de layout**: com a lateral estreita
  (1280 px, ou a câmera 4:3 do Portal) a última aba transbordava por cima do
  "Mais" e roubava o clique. A faixa agora mede as abas (ResizeObserver) e
  manda para o "Mais" as que não cabem (`components/common.tsx`).
- O `bench --rapido` da 1ª rodada foi interrompido (a rodada ia ser refeita).

### Queda no palco também pausa as outras câmeras

- Depois do portão, o E2E `test_palco_queda_ao_vivo_em_camera_lenta` rodado
  **isolado** falhou 3 de 3 (no portão completo passava porque um teste de
  queda anterior deixava o incidente ativo). Medido na cena (status a cada 2 s):
  a câmera da queda recebia 0,3–0,5 análise/s, com trechos de 5 s sem nenhuma;
  o modelo viu `fall_detected` 2 vezes, mas não em 2 análises seguidas (a regra
  de emergência), com a pessoa ~3 s no chão a 0,25×. A disputa cresceu com a
  câmera do Portal em 4:3 (640×480 na rede contra 640×384).
- A cena "Queda" passou a declarar `ativas: "cena"`, como o Portal: isolado,
  **2 de 2**, alerta ao vivo em 22,2 s e 19,2 s desde entrar na cena.

### Portão final do PR6 (r3, depois da correção da Queda)

`bench/runtime/portao-pr6-r3/`, rodada única: `ruff` 0 · `pytest` **664
passed** · `npm run build` ok · `pytest e2e` **36 passed** (4 câmeras, axe nos
dois temas) · `bench.py --rapido` exit 0 (`bench/results/20261014-153054-rapido.json`):
1 câm. 1,29 análise/s, alerta 4,8 s; 4 câm. 0,31/s por câmera, alerta 5,2 s —
com **76–82 % da CPU** tomada por processos de fora do projeto (r2: 47–54 %,
1,86 e 0,36/s). O ADENDO 3 não toca o caminho por análise; a diferença
acompanha a carga de fundo (regra do bench leve: sem investigação).

## Integração com a main (ADENDO 3, Fase D) — `release-main`

`release-main` nasceu de `feat/completo-com-rebrand` (`4a65267`, PR6) e recebeu
`git merge origin/main` **sem estratégia automática** (`6c3ed61`, Sprint 4 de
IA: 15 commits). 98 arquivos entraram sem conflito (relatório e evidências da
Sprint 4, `docs/avaliacao/`, `docs/entrega/`, scripts de avaliação e treino,
3 arquivos de teste novos, o peso `models/visionepi_cppe_n416.pt`, tipos e
quiosque do frontend). Nada da main foi descartado sem registro:

| arquivo | versão que ficou | motivo |
|---|---|---|
| `.env.example` | **feat** (Vyra + runtimes aprovados) **+ main** (`PPE_MISSING_POLICY=ausencia` e seus comentários; peso da Sprint 4 documentado como alternativa, com as 3 linhas juntas) | todas as medições, guardas e E2E do NEXT foram feitos com o Vyra. **Achado:** `YOLO_CLASSES=` (vazio) e `MULTI_PERSON_DETECTION=false` da main entraram **sem conflito** e, com o Vyra, desligariam a avaliação de pessoas — voltaram para `0,1,2,3,5,11,12,13` e `true` |
| `.gitignore` | **união** | mantidos os ignores do NEXT (`runtime/`, `bench/runtime/`…) e os da main (`datasets/`, `runs_treino/`, `models/*` com a exceção do peso da Sprint 4) |
| `README.md` | **feat** + trechos da **main** | ficaram da main: o destaque da entrega Sprint 4, "Ausente não é não visto", Gemini na stack, rótulos do diagrama (regras e 2º gatilho) e o roadmap. Os trechos da main que entraram sem conflito dizendo "o default é o peso próprio" foram reescritos: padrão Vyra, peso da Sprint 4 como opção (seção "Configuração do modelo de EPI") |
| `app/config.py` | **feat** (`MULTI_PERSON_DETECTION=True`) **+ main** (`PPE_MISSING_POLICY`, também travado em `ausencia` no `TestConfig`) | padrão do Vyra precisa do detector de pessoa; a política da main com padrão `ausencia` é o comportamento atual |
| `app/services/camera_worker.py` | **feat** (laço com `_publicar`/`_depois_de_publicar`) **+ main** (2º gatilho do LLM no "não verificado" confirmado, agora dentro de `_depois_de_publicar`; `missing_policy` no `RuleEngine`) | a main mexia no laço antigo, que a feat reorganizou; a função foi levada para o lugar novo, sem mudar a regra |
| `app/services/risk_rules.py` | **feat** (continuidade da queda, "uso incorreto", mensagem com "·") **+ main** (`missing_policy`, sufixo "(visto sem o EPI)", `evidence` nos metadados) | os dois lados acrescentaram coisas independentes |
| `app/vision/person_compliance_matcher.py` | **fusão manual**: feat ("uso incorreto", `_assign` em tupla) + main (classes negativas, `evidence`, política) | decisão: OK → uso incorreto → "visto sem o EPI" → ausente (`ausencia`) ou "não verificado" (`evidencia`). Com Vyra + `ausencia`, o resultado é o de hoje (o Vyra filtra as `NO-*` por `YOLO_CLASSES`) |
| `app/vision/yolo_ppe_detector.py` | **união** (aliases de protetor auricular da feat + negativas e `PPE_NEGATIVE_CLASSES` da main) | independentes |
| `app/static/dist/*` | **build novo** do código fundido; o bundle velho da main (`index-BuHE6RZR.js`) saiu | artefato gerado |
| `docs/SPRINT4.md` | **main** (relatório oficial de IA da entrega); o da feat foi **renomeado** `docs/SPRINT4-PLANTA.md` | eram dois documentos diferentes com o mesmo nome; o README e o PDF da main apontam para o relatório |
| `frontend/src/styles/global.css` | **feat** (sistema de design do PR6) | a main só acrescentava `unverified` a `.row-dot`/`.metric`, que o PR6 removeu; o estado ficou no chip de EPI (`compliance.tsx`: neutro, nunca verde, com `title`) |

Ajustes fora dos arquivos em conflito, exigidos pela integração:
- `tests/test_onboarding.py` (veio da main sem conflito): o teste que travava o
  peso da Sprint 4 como padrão virou `test_env_example_documenta_o_peso_da_sprint4_como_opcao`
  (padrão Vyra + as 3 linhas da opção documentadas). O do SHA-256 do peso ficou como veio.
- `app/vision/runtime_do_modelo.py` — **achado na integração:** a aprovação de
  runtime é por tipo de modelo ("epi"), não por peso; com `PPE_MODEL_PATH` no
  peso da Sprint 4, o `auto` carregaria em silêncio o export OpenVINO **do
  Vyra**. Agora a aprovação só vale se o diretório do export for do mesmo peso
  (`vyra_ppe_640_dyn` ↔ `vyra_ppe.pt`); teste em `tests/test_runtime_do_modelo.py`.
- Peso da main conferido: existe, SHA-256 `f0dfeea7…` (o travado no teste), carrega
  e detecta pessoa (0,88), colete (0,85) e capacete (0,51) no `portal.mp4`.

### Teste de clone limpo (Fase D, item 1)

**Clone 1** (`feat/completo-com-rebrand` @ `4a65267`, `../ch5550-clone-1`), README
à risca (`py -3.11 -m venv` + `pip install -r requirements.txt`;
`scripts\preparar.py`; `run.py --demo`) e a fumaça `e2e/fumaca_demo.py` contra ele:
**6/6** (demo no ar em 54 s, 4 câmeras publicando análise, vídeo no canvas,
Portal no palco com as outras pausadas e "Liberado"). Mas o `preparar.py`
expôs três defeitos de setup, corrigidos aqui:

1. **Nenhum runtime acelerado aprovado para o EPI** (e a pessoa ficou só com
   `openvino:640` estático, que a ordem `openvino-gpu,onnx,pytorch` não usa):
   EPI e pessoa rodaram em PyTorch no clone. Causa: o `preparar.py` chamava o
   `concordancia.py` com a lista padrão, que é a varredura de pesquisa e não
   inclui `openvino-dyn@gpu-*`; os aprovados desta máquina vieram de rodadas
   manuais no PR2. Agora o `preparar.py` passa os candidatos do app
   (`openvino-dyn@gpu-fp32/fp16`, `openvino-dyn@cpu-fp32`, `onnx-dyn`, a 640).
2. **Export ONNX falhava** (`No module named 'onnx'`): `onnx==1.22.0` e
   `onnxslim==0.1.98` no `requirements.txt` — sem eles o fallback ONNX de
   máquina sem iGPU Intel nunca é aprovado.
3. **Auto-instalação do ultralytics** tentou `pip install` no Python **global**
   (3.14) da máquina, fora do venv: `YOLO_AUTOINSTALL=false` no
   `concordancia.py` e no ambiente que o `preparar.py` passa a ele.

**Clone 2** (`release-main` @ `4a127ae`, com as correções 1–3): o `preparar.py`
aprovou o OpenVINO dinâmico na iGPU para EPI (concordância 1,0), pessoa (1,0) e
esqueleto (1,0); a fumaça deu **6/6** com os três modelos no OpenVINO. O ONNX
ainda falhou (`onnxscript` ausente: o `pip` trouxe `torch` 2.14.1, sem pino).
Correção 4: `torch==2.13.0`, `torchvision==0.28.0` (as versões com que tudo
foi medido) e `onnxscript==0.7.1` no `requirements.txt`. Clone 3 valida.

### Portão do release-main

Rodada 1 (`bench/runtime/portao-release/`): `ruff` 0 · `pytest` **695 passed**
(os 664 da feat + os testes da Sprint 4) · build ok · `pytest e2e` **35/36** ·
`bench --rapido` exit 0, com **81–86 % da CPU tomada por terceiros**.
A falha (`test_pill_de_aproximacao_aparece`) é ambiental, com evidência:
- isolado, o mesmo teste falhou também na `feat` (1/1) e no `release-main` (2/2);
- diagnóstico com o servidor do E2E: a câmera em foco recebeu **3 inferências
  em 73 s** (agendador: `servidos` 3, espera máxima 65,9 s), sem o pré-alerta
  ter chance de medir velocidade;
- inferência direta, sem o servidor: EPI 1,0–1,4 s e pessoa 0,5–0,8 s na iGPU
  (horas antes, no clone, a pessoa levava 97 ms) — sem pico de compilação por
  forma de entrada; CPU da máquina em 100 %, com ~12 processos do Salesforce CLI
  (`sf`) abertos às 19:44, de fora do projeto.

### Depois do merge do PR7 (#16, squash `a6d303b`)

- `main` == `release-main` testado (`git diff` vazio).
- A partir da própria `main`: `e2e/fumaca_demo.py --raiz .` (sobe `run.py --demo`
  e confere com o Playwright) → **6/6**: demo no ar em 120 s (com a CPU tomada
  por outros programas e o clone 3 rodando), 4 câmeras publicando análise,
  vídeo no canvas, Portal no palco com as outras pausadas e "Liberado".
- A `fumaca_demo.py` tinha ficado fora do PR7 (foi commitada em `next-2026`
  depois do squash do PR6) e entrou neste PR, com a espera pelo HTTP alinhada
  ao limite de subida (os 120 s fixos estouraram com a CPU saturada).
- Clone 3 (`release-main` com `torch` fixo): `pip install` concluiu na 3ª
  tentativa (as duas primeiras saíram com erro sem mensagem; hipótese: arquivo
  preso com a máquina saturada); `preparar.py` aprovou o OpenVINO dinâmico na
  iGPU para o EPI (concordância 1,0 e 0,99); o restante seguia rodando no
  encerramento desta sessão.

---

# MISSÃO 4 — VisionEPI pronto de empresa

### Novidades: Pronto para a operação da empresa (17/10/2026)

- **Páginas de aviso.** Página não encontrada, erro de tela, sem conexão, sessão expirada com retorno ao ponto onde você estava e acesso negado explicado.
- **Primeiro acesso.** O Supervisor é guiado da primeira câmera até o "pronto para operar", com a senha temporária exibida uma só vez.
- **Permissões por tipo de conta.** Cada tela e cada ação respeitam o tipo de conta, e o Operador vê só a câmera do próprio setor.
- **Saúde da câmera.** O sistema avisa quando uma câmera é tampada, movida, fica escura, ofuscada ou desfocada.
- **Integração com a fábrica.** OPC UA, MQTT e webhook levam o estado da planta e cada alerta novo a outros sistemas, e a torre de luz virtual mostra o mesmo estado.
- **Modo Evacuação.** Contagem de pessoas por zona e por câmera, com cronômetro e relatório guardado na cadeia de custódia.
- **Editor de regras.** Monte regras com blocos, teste no histórico antes de ativar e mantenha as regras atuais como ponto de partida.
- **Permissão de trabalho.** Zona, janela de horário, responsável, EPIs exigidos e vigia, com o que o modelo não vê marcado como verificação manual.
- **Textos revisados.** Um termo para cada conceito em todas as telas, com números e horas no padrão brasileiro.
- **Status do sistema.** Uma página com a saúde dos modelos, das câmeras, do banco, das integrações, da segunda opinião e do espaço em disco.
- **Configurações em um lugar.** Conta, planta, câmeras, regras, integrações, privacidade e usuários em seções, com o que o seu tipo de conta não pode usar explicado.

## Fontes verificadas (agente fontes, acesso em 17/10/2026)

- **NR-33** (texto vigente, Portaria 1.690/2022, em vigor desde 03/10/2022):
  https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/participacao-social/conselhos-e-orgaos-colegiados/comissao-tripartite-partitaria-permanente/arquivos/normas-regulamentadoras/nr-33-atualizada-2022-_retificada.pdf
  - Glossário: vigia é o "trabalhador designado para permanecer fora do espaço confinado e que é responsável pelo acompanhamento, comunicação e ordem de abandono para os trabalhadores".
  - 33.7.1 c): proibida a entrada com "ausência de vigia durante a entrada, permanência e saída".
  - 33.3.4 c) e g): o vigia permanece fora, junto à entrada, e não realiza outras tarefas.
  - 33.3.4.1 a)/b): o vigia pode ser "assistido por sistema de vigilância e comunicação eletrônicas", mas o campo visual sem equipamento eletrônico continua exigido — **a câmera auxilia, não substitui o vigia** (é o que a UI diz).
  - 33.5.5/33.5.6: toda entrada precedida de PET; campos mínimos (espaço, objetivo, perigos e medidas, atmosfera, supervisores/vigias/autorizados, data e horário de emissão e encerramento, assinaturas). **EPI não é campo mínimo**: aparece só no Anexo II (modelo informativo). 33.5.12: validade limitada a uma jornada; 33.5.12.1.1: até 24 h com prorrogações.
  - A PET digital do VisionEPI (M5) NÃO é a PET da norma: é um apoio de fiscalização; a UI e os docs dizem isso.
- **NR-35** (Portaria MTP 4.218/2022, última alteração Portaria MTE 1.259/2026):
  https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/participacao-social/conselhos-e-orgaos-colegiados/comissao-tripartite-partitaria-permanente/normas-regulamentadora/normas-regulamentadoras-vigentes/nr-35-atualizada-2025-1.pdf
  — 35.5.5: todo trabalho em altura precedido de Análise de Risco; 35.5.7: atividades não rotineiras autorizadas por PT; 35.5.8.2: validade restrita ao turno/jornada. (A página do gov.br diz "15 de junho de 2026" e o PDF "15 de julho de 2026" para a Portaria 1.259 — divergência da fonte; citamos o PDF.)
- **NR-6**: URL que o projeto já cita em `app/services/nr6.py` confirmada como vigente.
- **Licenças** das dependências novas (M2):
  - asyncua 2.1.0 — LGPL-3.0-or-later (https://github.com/FreeOpcUa/opcua-asyncio/blob/master/COPYING). Usada como pacote importado, sem modificação; ao distribuir o produto, acompanhar aviso e cópia da LGPL/GPL (LGPLv3 §4). Registrado em `ATRIBUICOES.md`.
  - paho-mqtt 2.1.0 — EPL-2.0 OR BSD-3-Clause (EDL 1.0) (https://github.com/eclipse-paho/paho.mqtt.python/blob/master/LICENSE.txt).
  - amqtt 0.12.1 — MIT (https://github.com/Yakifo/amqtt/blob/main/LICENSE.md).
- **OPC UA**: exemplo oficial de servidor do asyncua (https://github.com/FreeOpcUa/opcua-asyncio/blob/master/examples/server-minimal.py); NodeId e namespace (OPC UA Part 6 §5.1.12, https://reference.opcfoundation.org/Core/Part6/v105/docs/5.1.12; Part 3 §8.2).
- **MQTT 3.1.1** (OASIS, https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html): '/' separa níveis (§4.7.1.1); RETAIN guarda a última mensagem do tópico (§3.3.1.3).
- **OpenAPI 3.1.2**: https://spec.openapis.org/oas/v3.1.2.html.
- **COCO**: "cell phone" está entre as 80 categorias do release 2014 (https://arxiv.org/pdf/1405.0312, Tabela 2); anotações CC BY 4.0, imagens sob os termos do Flickr (https://cocodataset.org/dataset/termsofuse.htm).

## Fase 1 — correções de UI achadas pelo crawler (MISSÃO 4)

- **Vibração sem gesto do usuário.** O crawler registrou no console "Blocked call to navigator.vibrate because user
  hasn't tapped on the frame or any embedded frame yet" (https://www.chromestatus.com/feature/5644273861001216). A doc
  da MDN de `Navigator.vibrate()` (https://developer.mozilla.org/en-US/docs/Web/API/Navigator/vibrate) registra que o
  método exige ativação do usuário; e `navigator.userActivation.hasBeenActive`
  (https://developer.mozilla.org/en-US/docs/Web/API/UserActivation/hasBeenActive) diz se a página já recebeu um gesto.
  `pwa.ts` e o controle do palco só vibram depois de um gesto; a notificação local segue igual.
- **Modais sem Esc.** "Prova de escala", "Adicionar câmera" e o replay não fechavam com Esc (o clique do crawler no
  item seguinte batia no fundo do modal). Hook único `useFecharComEsc` (`frontend/src/utils/teclado.ts`) e
  `aria-modal="true"` nos diálogos.
- **Perfis de recursos.** Os botões Básico/EPI/Risco/Completo não mostravam qual perfil estava aplicado e, quando já
  estava, o clique não fazia nada. Agora `aria-pressed`, e o perfil em vigor fica desabilitado com explicação.
- **Crawler (segunda rodada).** Telas de Técnico/Supervisor abertas por operador mostram "acesso negado"
  explicado em vez de chamar a API (`PAPEL_MINIMO` em `App.tsx`); o controle do palco sem o token do QR orienta a
  abrir pelo QR; "Entrar" desabilitado explica o motivo; `loadCameras` deixa a falha de rede subir para o retry do
  App (antes o store engolia e logava erro a cada navegação); `apiFetch` trata corpo 2xx interrompido como falha de
  rede; `getMe` com prazo de 20 s (servidor travado não deixa mais a tela em branco). Os "botões sem nome" que o
  crawler acusou no foco eram dele: linhas com `content-visibility` têm `innerText` vazio; agora lê `textContent`.
- **`.gitattributes`.** `app/static/dist/** text eol=lf` convertia o `palco.gif` do build (6.383.668 bytes no blob
  contra 6.383.807 no disco). GIF, WebP, ICO e vídeo passaram a `binary`; blob conferido com o mesmo tamanho.

## Fase 1 — matriz de permissões e bug hunt (MISSÃO 4)

- **Matriz** (`tests/test_matriz_de_permissoes.py`, 1403 casos, ~8 min): todo endpoint × método × (sem sessão,
  operador, operador fora do setor, operador sem setor, técnico, supervisor) e os 3 eventos de socket. Teste-guarda
  falha para rota ou evento sem classificação. 8 divergências de segurança achadas e corrigidas (D1–D8, ver
  `PERMISSOES.md`): `/snapshots/<arquivo>` sem escopo de câmera e seis listagens do parque entregues ao operador sem
  setor — decorator único `exige_setor`.
- **Bug hunt** (somente leitura) nos módulos centrais: 7 bugs confirmados com reprodução, todos corrigidos com teste
  de regressão (`tests/test_regressao_bug_hunt.py`, `tests/test_regressao_c1_poligono.py`): ponto-em-polígono em
  aresta inclinada (alerta falso de área de risco), commit falho envenenando o estado de alertas, dois loops de
  captura após stop+start, falso positivo apagado pelo `touch`, incidente que não fechava, adulteração escondida na
  verificação por incidente (hash do elo formato 2) e 500 no simulador.
- **Copy**: revisão pt-BR de todas as telas, `GLOSSARIO.md`, plurais, decimal com vírgula, hora pt-BR.

## Fase 2 — Fábrica conectada (MISSÃO 4)

- **M1 saúde visual** (`app/vision/saude_visual.py`, 83 testes com quadros derivados das fixtures): obstrução,
  escura, ofuscada, desfocada e câmera movida (ORB + RANSAC; pose por similaridade nos inliers, que errou menos que a
  homografia livre em 160 px). Histerese de 3 s para confirmar e liberar. Zero falso positivo de "movida" em 6.804
  observações densas das fixtures; recall de movida em cena renovada é baixo (fica "inconclusivo", nunca alarme falso)
  — documentado. E2E com a fonte MJPEG tampada no meio do teste: **3,8 s até OBSTRUÍDA e 9,9 s até o alerta**
  (`bench/runtime/missao4-tempos.jsonl`), e volta a OK ao destampar. Referência persistida por câmera; "Redefinir
  referência" só técnico+.
- **M2 integração**: servidor OPC UA (asyncua), publicador MQTT (paho) com broker embutido (amqtt) e webhook com
  proteção SSRF; tudo desligado por padrão, ligado no modo demo. Estado da planta a cada 1 s
  (`app/services/integracao/planta_viva.py`), torre de luz em `/torre` e no Modo TV. Porta ocupada vira "falhou" no
  status, nunca derruba o app. Teste de integração e E2E com clientes OPC UA e MQTT reais. O OPC UA levou ~5 s para
  subir nesta máquina e passou de 10 s com a CPU tomada por agentes: prazo de subida 45 s, em thread própria.
  Semântica da torre: reconhecer cala a sirene; a torre só volta a verde quando a violação acaba (na Multidão, cada
  pessoa nova sem capacete abre outro alerta crítico — o E2E verifica que os reconhecidos deixam de contar).
- **M3 evacuação**: contagem por câmera e zona com o aviso de dupla contagem sempre visível, última posição na
  planta, pico no ponto de encontro, cronômetro; relatório na cadeia de custódia (elo `evacuacao`). E2E pela tela.
- **M4 editor de regras**: blocos E/OU compilados para o MESMO `RuleEngine` (sem segundo caminho), equivalência
  provada com as 17 regras nativas, "testar no histórico" sobre as trilhas do X2 (postura e aproximação declaradas
  não simuláveis, nunca fingidas). E2E: regra testada no histórico e disparando ao vivo.
- **M5 permissão de trabalho**: zona controlada, janela, responsável em texto livre, EPIs com verificação automática
  x manual, vigia (NR-33 citada do gov.br: a câmera auxilia o vigia, não o substitui). E2E: sem vigia → crítico; com
  vigia na área → some.
- **Logout desfeito por requisição em voo (segurança).** O crawler achou o "Sair" que não deslogava: o Flask
  regravava o cookie de sessão em TODA resposta (`SESSION_REFRESH_EACH_REQUEST`, padrão); uma requisição enviada antes
  do clique em "Sair" e respondida depois devolvia o cookie antigo e a pessoa continuava logada. Reproduzido em
  `tests/test_auth.py::test_requisicao_em_voo_nao_desfaz_o_logout` (falhava com o Set-Cookie da sessão), corrigido
  com `SESSION_REFRESH_EACH_REQUEST = False` (doc: https://flask.palletsprojects.com/en/stable/config/#SESSION_REFRESH_EACH_REQUEST).
  Efeito: a sessão vale `SESSION_HOURS` (12 h, um turno) a partir do login, não do último clique — documentado.

## M9 — laboratório: celular em área de risco (MISSÃO 4)

Resultado: **ficou LABORATÓRIO, desligado por padrão** (`LAB_CELULAR_ATIVO=false`). Não há evidência medida de que o
detector enxerga celular nas imagens que o projeto tem, e "em uso" é mais do que o modelo sabe dizer.

**Fatos verificados no repositório e na máquina (17/10/2026)**

- O detector de pessoa é o YOLOv8n do COCO (`PERSON_MODEL_PATH = models/yolov8n.pt`). Carregando o peso: 80 classes,
  `names[0] = person`, `names[67] = cell phone`. Fonte da classe: COCO, Tabela 2 (https://arxiv.org/pdf/1405.0312).
- O celular é descartado **na inferência**, não depois: `MonitorService.person_detector` roda com `classes=[0]`
  (`app/services/monitor_service.py`, linha 157). Para a regra ver o celular, o filtro precisa virar `[0, 67]`.
- Fixtures de licença livre checadas (as derivadas em `tests/fixtures/`, geradas por `scripts/fetch_fixtures.py`;
  licenças em `docs/NEXT2026/ATRIBUICOES.md`): `bench.mp4` (CC BY-SA 4.0), `next_multidao.mp4` (CC0),
  `next_queda.mp4` (domínio público), `portal.mp4` (CC BY-SA 4.0) e as cenas `segura`, `risco`, `ambigua`
  (CC BY 2.0 e domínio público). Nada foi baixado da internet para isto.
- Medição: yolov8n sem filtro de classe, confiança mínima 0,05, 1 quadro a cada 5 nos vídeos (42 + 75 + 100 + 100
  quadros) e as 3 imagens inteiras. **Nenhum quadro com celular a 0,25 ou mais; o maior sinal foi 0,141, em 1 quadro
  da `multidao`** (abaixo de qualquer limiar plausível). `bench`, `queda`, `portal` e as 3 cenas: 0,000. Ou seja: as
  fixtures não têm celular visível para o detector (não revi os quadros a olho; a medição é do detector).
  Como isso mede ausência e não acerto, **não dá para afirmar recall nem falso positivo** do celular.

**O que foi entregue (inerte quando desligado)**

- `app/services/lab_celular.py`: função pura `avaliar_celular(deteccoes, *, ativo, limiar, poligono, forma_do_quadro)`
  → lista de `RuleAlert` (`celular_em_area`, severidade `medium`, mensagem "Celular em uso na área de risco · Pessoa N",
  recurso `celular`). Com `ativo=False` devolve `[]` sem olhar as detecções. Conta quando o centro do celular
  (`cell phone` com confiança ≥ limiar) está na área de risco **e** dentro da caixa de uma pessoa (a de menor caixa);
  celular sem pessoa por perto não alerta. Um alerta por pessoa, com a maior confiança.
- `Config.LAB_CELULAR_ATIVO` (padrão `false`) e `Config.LAB_CELULAR_CONF_MIN` (padrão 0,5).
- `tests/test_lab_celular.py`: detecções sintéticas (desligado, limiar, fora da área, sem pessoa, pessoas aninhadas).

**Limites que valem mesmo ligado**: "em uso" é presença do celular junto de uma pessoa na área; o sistema não sabe se
ela olha a tela ou fala. Celular na mão, de longe, em câmera de baixa resolução, é objeto pequeno: hipótese a medir.
Custo de inferência de abrir a classe 67: **hipótese**, não medido.

**Como validar na máquina da apresentação** (antes de ligar na demo)

1. `LAB_CELULAR_ATIVO=true` no `.env`; o integrador abre `classes=[0, 67]` no `person_detector` só nesse caso e chama
   `avaliar_celular` com as detecções do quadro, o polígono da câmera e `frame.shape`.
2. Câmera da demo, área de risco desenhada. Gravar 20 passagens com o celular na mão dentro da área e 20 sem (mão
   vazia, caneta, controle remoto, garrafa). Contar quadros com alerta em cada grupo.
3. Critério sugerido para ligar: pelo menos 16 das 20 passagens com celular alertam e 0 das 20 sem celular alertam;
   ajustar `LAB_CELULAR_CONF_MIN` e repetir. Medir o tempo por análise antes e depois (`scripts/` de bench do projeto).
4. Se não passar, deixa desligado e a demo segue sem a regra: nada mais depende dela.

## M10 — relatório mensal para a CIPA (MISSÃO 4)

`GET /relatorio/mensal?mes=AAAA-MM` (página A4 imprimível, sem dependência externa) e `GET /api/relatorio/mensal`
(JSON). Mesmo perfil do relatório de turno: sessão obrigatória, Operador só do setor dele (sem setor, 403).
Só totais, medianas e nomes de câmera/zona/regra; nenhum rótulo de rastreio, nome ou e-mail. Evacuações e cadeia de
custódia são da planta inteira e não aparecem para o Operador. Código em `app/services/relatorio_mensal.py`.

- **Limite honesto**: o total de minutos com gente não é gravado por mês (só os minutos conformes, como pontos da
  Liga). O relatório mostra os conformes do mês e, só no mês corrente, o contador do servidor desde que subiu; não
  inventa percentual de conformidade mensal. Para tê-lo, o fechamento de minuto no `camera_worker` teria de gravar
  também os minutos com gente.
- Mês inválido: 400 `mes_invalido`. Sem `mes`, vale o mês corrente (hora local do servidor).

## Fase 5 item 5 — segurança (auditoria)

Dezoito achados de uma auditoria, cada um com teste escrito antes (vermelho no código anterior, verde depois). Testes novos em
`tests/test_seguranca_missao4.py`; os que exigem servidor de verdade estão em `tests/test_integracao_industrial.py`.

| # | Sev. | Achado | Correção | Teste |
|---|---|---|---|---|
| 1 | Alta | OPC UA: o gerenciador de usuários padrão do asyncua torna "admin"/qualquer senha em Admin (AddNodes, DeleteNodes, AddReferences, DeleteReferences, RegisterServer) | `set_identity_tokens([Anonymous])` + `allow_remote_admin(False)` e o ruleset nega também `ADMIN_TYPES`; leitura anônima segue valendo | `test_opcua_login_admin_com_qualquer_senha_nao_vira_admin`, `test_opcua_anonimo_nao_altera_o_espaco_de_enderecos_mas_continua_lendo` |
| 2 | Média | O token do celular-câmera (`celular://<token>`) saía inteiro em `Camera.to_dict` | `redigir_segredos` troca por `celular://***` (vale também para os logs da fonte); o update de câmera Celular já ignorava o `source` do cliente | `test_camera_celular_nao_expoe_o_token_no_to_dict`, `test_api_de_cameras_nao_devolve_o_token_do_celular`, `test_atualizar_camera_celular_nao_depende_do_source_do_cliente` |
| 3 | Média | `SOCKETIO_CORS_ALLOWED_ORIGINS` padrão `*` refletia o Origin com credenciais | Padrão = mesma origem (`None`); `env_origens` aceita lista por vírgula, `*` só se explícito; sem fallback `*` no `create_app`; `.env.example` documenta (inclui `http://localhost:5173` para o Vite) | `test_env_origens_*`, `test_socketio_*` (handshake real com `Origin`) |
| 4 | Média | Sem `MAX_CONTENT_LENGTH` | `MAX_CONTENT_LENGTH = env_int(..., 6 MiB)`, acima de `MAX_BYTES_QUADRO` (4 MiB) | `test_corpo_maior_que_o_limite_e_413`, `test_corpo_pequeno_continua_passando` |
| 5 | Média | CSRF residual same-site (`SameSite=Lax` deixa passar outro subdomínio) | `app/utils/protecao_http.py`: escrita barrada (403 JSON) se `Sec-Fetch-Site` ≠ `same-origin`/`none`; sem ele compara `Origin` com `request.host_url`; sem nenhum dos dois (curl, test client) passa | `test_mutacao_*`, `test_todo_metodo_de_escrita_e_barrado`, `test_sem_sec_fetch_site_compara_o_origin_com_o_host`, `test_sec_fetch_site_tem_precedencia_sobre_o_origin` |
| 6 | Média | A demo escutava em `0.0.0.0` | `preparar_ambiente` define `HOST=127.0.0.1` (respeita um `HOST` já definido). `run.py --https` continua abrindo para a LAN (o ramo `host in (127.0.0.1, localhost) → 0.0.0.0` está vivo); `DEMO.md` ganhou a linha | `test_demo_escuta_so_no_loopback_por_padrao`, `test_demo_respeita_o_host_ja_definido` |
| 7 | Média | Broker MQTT embutido anônimo e sem TLS aceitava subir em qualquer host | `BrokerEmbutido.iniciar` recusa host fora de `127.0.0.1`/`localhost` (status `falhou`: use um broker da planta com TLS e credencial) | `test_broker_embutido_anonimo_recusa_subir_fora_do_loopback`, `test_gerente_nao_sobe_broker_embutido_fora_do_loopback` |
| 8 | Média | LGPD: contatos de `/produto` não podiam ser excluídos | `DELETE /api/contatos/<id>` (Supervisor; 404 se não existe), botão "Excluir" com confirmação na caixa de entrada, texto de guarda no formulário (dados só para responder ao contato; excluídos a pedido) | `test_excluir_contato_*`, `test_so_supervisor_exclui_contato`; linha nova na matriz de permissões |
| 9 | Média | gunicorn 22.0.0 (CVE-2024-6827) | `requirements.txt` → 23.0.0 (dry-run: só ele muda; `pip check` limpo) | `pip install --dry-run` + `pip check` |
| 10 | Baixa | Token no log de acesso do werkzeug (`?t=`, `/api/celular/<token>/`) | `FiltroDeTokensNoAcesso` no logger `werkzeug`, instalado por `configure_logging` (uma vez) | `test_filtro_do_log_de_acesso_esconde_tokens`, `test_configure_logging_instala_o_filtro_no_werkzeug_uma_vez` |
| 11 | Baixa | `endpoint` do webhook mostrava o caminho (segredo estilo Slack); Operador via endpoint/erro | `Webhook.endpoint` = `esquema://host:porta`; Operador recebe só `estado` por canal | `test_webhook_mostra_so_esquema_host_e_porta_no_status`, `test_gerente_status_do_webhook_nao_vaza_o_caminho`, `test_operador_ve_so_o_estado_de_cada_integracao` |
| 12 | Baixa | `PATCH /api/users/<id>` mudava papel/câmera sem derrubar sessões nem validar a câmera | Mudar `role` ou `camera_id` chama `revoke_sessions`; câmera inexistente ou de tipo errado = 400 | `test_mudar_o_papel_derruba_as_sessoes_da_conta`, `test_mudar_a_camera_*`, `test_camera_que_nao_existe_e_400_*` |
| 13 | Baixa | O HTML do relatório podia virar a casca offline do PWA | `relatorio` entra no `SEM_CASCA` de `frontend/public/sw.js` | `test_service_worker_nao_guarda_o_relatorio_como_casca` |
| 14 | Baixa | E-mail aceitava `?&#%/` (injeção em `mailto:`) | Regex recusa esses caracteres e usa `fullmatch` | `test_email_com_caracteres_de_mailto_e_400`, `test_email_comum_continua_valido` |
| 15 | Baixa | Polígonos sem teto de pontos | No máximo 64 pontos em `area_vigia` (`normalizar_poligono`, 400) e na área de risco (`CameraWorker._normalizar_poligono`) | `test_area_vigia_com_mais_de_64_pontos_e_recusada`, `test_area_de_risco_do_worker_recusa_mais_de_64_pontos` |
| 16 | Baixa | `_ID.match` com `$` aceitava `"abc\n"` | `_ID.fullmatch` | `test_id_de_regra_nao_aceita_quebra_de_linha` |
| 17 | Baixa | `redigir_segredos` não cobria query nem senha com `@` cru | Query (`user`, `pass`, `pwd`, `password`, `token`, `auth`, `key`, `secret`) e userinfo até o último `@` antes do host | `test_redigir_segredos_cobre_query_senha_com_arroba_e_celular` |
| 18 | Baixa | Sem cabeçalhos de segurança | `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: same-origin` em toda resposta do Flask | `test_cabecalhos_de_seguranca_em_toda_resposta` |

**Pendente: CSP.** Não entra agora: o tema da demo usa um script inline no `index.html` e o three.js do gêmeo digital
pede `blob:`/`unsafe-eval`; uma CSP restritiva quebraria os dois. Caminho: nonce no script do tema e CSP em modo
`Report-Only` primeiro.

**Notas de operação**
- Quem tem `SOCKETIO_CORS_ALLOWED_ORIGINS=*` no `.env` (cópia antiga do `.env.example`) continua com `*` até remover a linha.
  Em dev com o Vite, use `SOCKETIO_CORS_ALLOWED_ORIGINS=http://localhost:5173`.
- O CSRF compara `Origin` com `request.host_url` só quando o navegador não manda `Sec-Fetch-Site`. Atrás de proxy que
  termina TLS, repasse o esquema (`ProxyFix`) para essa comparação bater.
- Sessões abertas de uma conta caem quando o Supervisor muda o papel ou o setor dela (login de novo).

## Portão do PR9 — classificação das falhas do E2E completo (MISSÃO 4)

1ª rodada (sobre `9aae8a1`): interrompida pelo fim da sessão; o log `-q` só tinha o progresso (8 F) e nenhuma falha
pôde ser classificada. 2ª rodada, única, sobre `d250824` (dist gerado do HEAD): **9 falhas, 62 passaram, 2 skips**
(os 2 skips de sempre, porta OPC UA ocupada e broker fora, cobertos em `tests/test_integracao_industrial.py`),
1 h 50 min. A partir desta rodada o E2E grava as inferências/s de cada câmera a cada 2 s
(`bench/runtime/e2e-inferencia.jsonl`) e a janela de cada teste (`bench/runtime/e2e-testes.jsonl`);
`scripts/e2e_carga.py` cruza os dois.

Regra: (a) bug de produto; (b) premissa errada do teste; (c) sensível à carga **só** se passar isolado e a câmera
envolvida tiver recebido < 1 inferência/s durante a espera. Sem essa evidência, (a) ou (b).

| Falha | Classe | Evidência |
|---|---|---|
| `test_falhas::test_camera_cai_a_tela_diz_reconectando_e_volta` | (b) | Falha também isolada. `inner_text()` devolve `RECONECTANDO · TENTATIVA 2`: o `.feed-badge` tem `text-transform: uppercase` desde o PR7 (`global.css`), e o regex `Reconectando\|Sem sinal` diferencia caixa. O texto do DOM é `Reconectando · tentativa 2`. Correção: o assert lê `text_content()` (texto do DOM, independente do CSS), mesmo regex |
| `test_falhas::test_webcam_ausente_diz_sem_sinal_e_nao_derruba_as_outras` | (b) | Mesma causa (`RECONECTANDO · TENTATIVA 4`), mesma correção |
| `test_falhas::test_sessao_expirada_no_meio_de_uma_acao_avisa_e_volta_depois_do_login` | (b) | Falha também isolada; a captura mostra o select "Câmera" na tela. Caso mínimo no Chromium: a árvore de acessibilidade dá `combobox "Câmera"` (nome certo), mas `get_by_label("Câmera", exact=True)` compara o texto inteiro do `<label>`, que inclui as opções (`Câmera Multidão Canteiro…`) → 0 elementos. Correção: `get_by_role("combobox", name="Câmera", exact=True)` (nome acessível, mais estrito) |
| `test_jornada_04_investigacao::test_investigacao_busca_nas_trilhas_e_simulador_com_regra_editada` | (b) | Mesmo localizador, mesma correção |
| `test_fase4::test_relatorio_mensal_abre_sem_pessoa_nem_email` | (b) | Falha também isolada. `"Pessoa " not in html` pegou "Pessoa em área de risco" e "Pessoa imóvel na área de risco", nomes de **regra**, não rótulo de rastreio. Correção: regex `\bPessoa\s+(?![a-zà-ú])\S` (barra "Pessoa 3", "Pessoa A7", "Pessoa #2"; nome de regra continua em minúscula) |
| `test_jornada_09_gamificacao::test_checkin_no_portal_…_retrospectiva` | (b) | Falha também isolada. A conferência da API (`missoes ≥ 1`) vinha **depois** do `finally` que apaga a missão; a retrospectiva conta só missões ativas (`retrospectiva.py:99`), então deu 0 ("Nenhuma missão configurada pelo supervisor"). Correção: conferir antes da limpeza |
| `test_todos_os_botoes[operator-light]`, `[technical-light]`, `[supervisor-light]`: "não foi possível acionar: Ajuda / Rever tour / Enviar feedback" | (b) | Os três ficam no menu "Mais" (`<details>`). Depois que um item abre outra aba o menu fecha, e o clique seguinte esperava 5 s um item escondido. Reprodução isolada antes da correção: mesmo padrão (Ajuda → nova aba, os seguintes "falhou ao acionar"). Correção: o crawler abre o menu pelo summary **antes** de tirar a assinatura de "antes" e, ao comparar, reabre o menu, para que abrir ou fechar o menu não conte como efeito (sem isso, um item sem efeito passaria). Verificado: kiosk do operador com Ajuda → nova aba, Rever tour e Enviar feedback → mudança de estado, 0 bugs |
| `test_todos_os_botoes[technical-light]` em `/regras`: "botão sem efeito: Ajuda sobre esta tela" | (b) provisório | **Não reproduziu** em 2 rodadas isoladas (nova aba nas duas; no supervisor, na mesma rodada completa, também nova aba). A rodada completa não deixou captura (o JSON do crawler e o `e2e.log` foram sobrescritos pelas reproduções). Hipótese, não verificada: a aba nova chegou depois da janela de 2,5 s do crawler. Para não ficar sem evidência de novo, todo "sem efeito" agora grava a tela, a URL e se uma aba nova apareceu tarde (`diagnostico` no JSON do crawler e `bench/runtime/e2e-falhas/crawler-*.png`). Só registra: o item continua contado como bug. Se repetir, a classe sai desse registro |

Nenhuma falha entrou em (c): todas reproduzem isoladas e nenhuma depende de inferência (o cruzamento de
`scripts/e2e_carga.py` está nos registros acima, por teste).

Comportamento de produto observado (não é falha de teste, fica como pendência): apagar uma missão já cumprida a tira
também da contagem de "Missões cumpridas" da retrospectiva, inclusive de turnos passados, porque a contagem é refeita
sobre as missões ativas.

**3ª rodada (sobre `0257acd`), invalidada pelo ambiente.** 69 passaram, 2 skips e 2 falhas, ambas no crawler
(`[technical-light]` e `[supervisor-light]`, na rota `foco-canteiro`: "Câmeras" não apareceu em 30 s). A rodada levou
20 h 11 min. O log do Windows (Kernel-Power 506/507) mostra a tampa fechada às 15:22:52 de 17/10 e espera moderna
repetida (tampa, orçamento de bateria) até 11:03 de 18/10. O crawler do técnico caiu às 15:23; o do supervisor ficou
congelado sem nenhuma requisição de escrita entre 15:31 e 11:03. Não é (a), (b) nem (c): a rodada não vale como
rodada única. Refeita do zero (4ª rodada, mesmo commit).

**4ª rodada (sobre `0257acd`), invalidada pelo ambiente.** As 3 falhas (`test_liga_missao_cumprida_celebra_e_pontua_o_setor`,
`test_retrospectiva_exporta_card_em_png`, `test_palco_do_inicio_ao_fim_pelo_teclado_e_pelo_celular`) começaram e
terminaram exatamente nas janelas de espera moderna do Windows (11:17→12:30, 12:30→18:16 de 18/10, 18:16→09:21 de
19/10; Kernel-Power 506/507). A máquina estava na bateria e o app só segura a suspensão por inatividade quando está
na tomada. Rodada parada no crawler e refeita do zero (5ª rodada, mesmo commit) com a máquina na tomada.
Bloqueio de ambiente registrado no ESTADO: o portão precisa de ~2 h com a máquina na tomada e a tampa aberta.

**5ª rodada (sobre `0257acd`), válida: 71 passaram, 0 falhas, 2 skips, 2 h 23 min**, com a máquina na tomada.
Crawler: 78 rotas × papéis, 834 elementos, 0 botões sem efeito, 0 erros de console, 0 respostas inesperadas
(`QA.md`). O "Ajuda sobre esta tela" do técnico em `/regras` deu nova aba e não se repetiu: segue (b) provisório,
sem evidência de bug de produto.

### Suíte unitária do portão do PR9 — 3201 passaram, 4 falharam

| Falha | Classe | Evidência e correção |
|---|---|---|
| `test_credencial_rtsp::test_nenhum_arquivo_versionado_carrega_credencial_em_url` | (b) | O guarda acusou `tests/test_seguranca_missao4.py`: os dados do teste de redação (achado 17) tinham literal uma URL RTSP com usuário e senha falsa contendo `@` (o caso testado). Falha também isolada. Correção: literal concatenado, como em `test_pagina_status.py`; o caso testado é o mesmo |
| `test_palco::test_preparo_que_estoura_vira_log_e_contingencia_sem_derrubar_o_palco` | (b) | Passa isolado; falha depois de `test_feedback_contatos.py`/`test_onboarding.py` (reproduzido: os 4 arquivos juntos → 2 falhas). Esses testes rodam `flask_migrate.upgrade` no mesmo processo; o `fileConfig` do `migrations/env.py` desliga todo logger já criado (`disable_existing_loggers=True`), e o `caplog` fica vazio. O app não migra no próprio processo, então produção não é afetada. Correção: fixture autouse em `tests/conftest.py` que religa os loggers depois de cada teste |
| `test_palco::test_saida_que_estoura_vira_log_e_a_troca_de_cena_continua` | (b) | Mesma causa, mesma correção |
| `test_pagina_status::test_politicas_trazem_privacidade_e_retencao_do_config` | (b) | Passa isolado e passou na ordem acima. Mecanismo lido no código: sonda que não responde no prazo real (2,5 s de relógio) vira `_falha_da_sonda`, sem a chave `cameras`, e `_politicas` devolve `[]`. A ocorrência no full run é **hipótese**: o aviso `status_sonda_sem_resposta` teria ido para um logger desligado pela causa acima. Correção: o teste, que verifica o conteúdo das políticas, usa `prazo_s=30`; o prazo tem teste próprio (`test_sonda_que_trava_vira_falha_no_prazo`). O assert agora mostra o componente de câmeras se falhar |

Verificado: os 6 arquivos envolvidos na ordem que reproduzia: 235 passaram.

### Suíte unitária — a causa das falhas de tempo: loops de captura vazados pela matriz de permissões

Duas rodadas seguidas da suíte completa: uma travou 25 min em `test_matriz_rest[POST /api/cameras/{cam}/start :: sup]`
com o pytest gastando ~4 núcleos (parada à mão); a outra deu 4 falhas diferentes das da 1ª rodada
(`test_metricas_do_portao`: "leu 2 em 1 s" quando esperava ≥ 35; `test_pagina_status`: `KeyError 'cameras'`, a
sonda estourando o prazo de 2,5 s; e o guarda de credencial acusando o próprio CHANGELOG, corrigido no texto).
Isolada, a matriz passava (1633 em 6 min 48 s). Evidência coletada com um plugin de diagnóstico fora do repo
(threads vivas e CPU do processo depois de cada teste): a suíte inteira gastou **8327 s de CPU em 1788 s de
relógio (4,6 núcleos em média)**, e 11 threads `CameraWorker._loop` nasciam nos casos de `start` da matriz e viviam
até o fim.

Causa (classe b, isolamento do teste): `_clonar_app` cria o app sobre um banco que **já tem câmeras**; o
`create_app` monta os workers com o socketio real; o teste troca `monitor.socketio` pelo mudo e chama
`load_cameras_from_db()`, que **reaproveita** os workers existentes (config igual). Então `start` subia o loop de
captura de verdade e ninguém parava. Em produção o socketio é o real mesmo, então não há bug de produto.
Correção: o mudo também vai para cada worker já montado. Medido depois: a matriz termina com **0 threads vivas**,
em 2 min 36 s, com CPU = relógio (1 núcleo).

Fica registrado (não corrigido agora, baixo custo de CPU): `TestSecretKey` em `test_auth_revogacao.py` cria o app
fora de `TESTING` e deixa vivos o publicador do estado da planta, o controlador adaptativo e o gravador assíncrono;
os testes de Socket.IO de `test_seguranca_missao4.py` deixam threads de ping do cliente.
