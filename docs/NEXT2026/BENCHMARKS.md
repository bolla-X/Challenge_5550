# BENCHMARKS — VisionEPI, NEXT 2026

Todos os números daqui vêm de `bench/results/*.json` (versionados) e foram
agregados por `python scripts/resumo_bench.py <arquivos>` — mediana das
repetições em negrito, valores individuais entre colchetes. Nada foi digitado
à mão a partir de memória.

## Máquina e carga de fundo

- Intel Core i7-1355U (2 P-cores com HT + 8 E-cores = 12 lógicos), 15,7 GB,
  sem GPU dedicada, Windows 11. Python 3.11.9, torch 2.13.0+cpu, ultralytics
  8.3.40, OpenCV 4.11.0, onnxruntime 1.29.0, OpenVINO 2026.3.
- **A máquina de medição é compartilhada** com processos de outros projetos
  que não foram encerrados (encode `ffmpeg -preset veryslow`, duas JVMs, outros
  Python): a carga de fundo medida variou de **~240 % a ~1190 %** (em "% de um
  núcleo"; 1200 % = os 12 lógicos cheios). Cada rodada registra
  `carga_de_fundo_pct` e os candidatos rodam **intercalados** na mesma rodada,
  em ordem alternada entre repetições (`scripts/rodar_portao.py`).
- Consequência honesta: diferença abaixo de ~10 % entre duas rodadas isoladas
  não é sinal. Decisões usam mediana de ≥ 3 repetições intercaladas.

## Perfis

| Perfil | O que é |
|---|---|
| `atual` | a máquina como está, servidor em prioridade alta |
| `batata` | servidor preso a **2 E-cores (lógicos 10 e 11)**, escolhidos pela topologia (`GetSystemCpuSetInformation`, menor `EfficiencyClass`), `VISIONEPI_THREADS=2`, `OMP_NUM_THREADS=2`, sem GPU. O navegador do bench (o "PC do operador") roda nos OUTROS núcleos |

## Métricas

**Desde o ADENDO 1, o portão é decidido por CPU do processo do servidor**
(`scripts/resumo_cpu.py`): CPU-ms por análise concluída, CPU-ms por quadro
publicado e encodes por quadro. Reprova só se a mediana do novo for > 10 % pior
que a da base E as 3 repetições pareadas concordarem. As métricas abaixo
seguem no relatório, rotuladas "sob saturação — indicativo".

Métricas de relógio (indicativas sob saturação):

- **FPS de análise por câmera** — análises novas publicadas por segundo;
- **idade da análise p50/p95** — da captura do quadro analisado até o
  resultado sair (regras, alertas e emissão feitos);
- **latência de alerta** — do primeiro quadro com a violação
  (`bench/primeira_violacao.json`: `multidao`, `missing_helmet`, quadro 0,
  achado com a referência PyTorch@640 + `RuleEngine`) até o `alert_created`
  chegar a um cliente Socket.IO dentro do Chromium.

Secundárias (vídeo): FPS lido/publicado/exibido, idade do quadro exibido,
bytes por segundo, CPU e RSS do servidor.

Cenários: 1 câmera = `multidao`; 4 câmeras = `multidao`, `bench`, `queda`,
`bench`. A câmera 1 está aberta no foco (com vídeo); as outras só em miniatura.

## Comparação: base × PR1

"base" = `feat/completo-com-rebrand` + instrumentação de medição
(`bench/base-instrumentada`, branch local: só `pipeline_stats` e 6 linhas no
loop para medir com a mesma régua), `DETECTION_EVERY_N_FRAMES=3` como no
`.env.example` dela. "PR1" = `next-2026` com o runtime ONNX aprovado. Ambas
a `YOLO_IMGSZ=640` (referência do guarda de qualidade).

### Perfil batata (decide o portão)

Portão final do PR1: `bench/results/*-gate6-r*.json` — 3 repetições, ordem
base/PR1 alternada, WSL e Docker Desktop desligados durante a rodada (ADENDO 1,
item 2), 30 s de CPU de terceiros medidos antes de cada rodada
(`carga_terceiros_pre`): **10–29 % da máquina** (só uma rodada abaixo de 15 %
→ números absolutos NÃO valem para a banca; ver Limitações).

**Métricas do portão (CPU do processo do servidor por trabalho feito):**

| perfil | câm. | árvore | análises/rodada | CPU-ms por análise | CPU-ms por quadro | encodes por quadro |
|---|---|---|---|---|---|---|
| batata | 1 | base | 16, 11, 21 | **6,351.9** [6,351.9, 8,990.6, 5,070.9] | **2,117.3** [2,117.3, 3,002.2, 1,691.9] | **1.0** [1.0, 1.0, 1.0] |
| batata | 1 | pr1 | 17, 23, 15 | **6,343.5** [6,343.5, 4,983.1, 6,549.2] | **261.9** [271.4, 261.9, 249.7] | **1.0** [1.0, 1.0, 1.0] |
| batata | 4 | base | 23, 20, 18 | **5,521.5** [4,814.4, 5,521.5, 6,191.6] | **1,844.1** [1,607.5, 1,844.1, 2,068.5] | **0.9** [0.9, 0.9, 0.9] |
| batata | 4 | pr1 | 16, 29, 21 | **5,436.2** [7,127.8, 3,945.2, 5,436.2] | **139.6** [138.8, 140.4, 139.6] | **0.6** [0.5, 0.6, 0.6] |

Regra: pr1 reprova se mediana > base em mais de 10 % e todas as repetições pareadas concordarem.
- batata 1 câm. cpu_ms_por_analise: novo/base por repetição = 1.00, 0.55, 1.29; medianas 6,343.5 vs 6,351.9 → **passa**
- batata 1 câm. cpu_ms_por_quadro: novo/base por repetição = 0.13, 0.09, 0.15; medianas 261.9 vs 2,117.3 → **passa**
- batata 1 câm. encodes_por_quadro: novo/base por repetição = 1.02, 1.02, 1.01; medianas 1.0 vs 1.0 → **passa**
- batata 4 câm. cpu_ms_por_analise: novo/base por repetição = 1.48, 0.71, 0.88; medianas 5,436.2 vs 5,521.5 → **passa**
- batata 4 câm. cpu_ms_por_quadro: novo/base por repetição = 0.09, 0.08, 0.07; medianas 139.6 vs 1,844.1 → **passa**
- batata 4 câm. encodes_por_quadro: novo/base por repetição = 0.61, 0.62, 0.62; medianas 0.6 vs 0.9 → **passa**

**Tempo de relógio — sob saturação, indicativo:**

| perfil | câm. | árvore | n | FPS de análise/câm. | idade da análise p50 (ms) | idade p95 (ms) | latência de alerta (s) | fundo (% de 1 núcleo) |
|---|---|---|---|---|---|---|---|---|
| batata | 1 | base | 3 | **0,27** [0,27, 0,19, 0,34] | **3.394** [3.394, 5.154, 2.684] | **4.199** [4.199, 6.033, 3.275] | **38,0** [41,5, 38,0, 31,2] | 514 |
| batata | 1 | pr1 | 3 | **0,28** [0,28, 0,38, 0,26] | **4.275** [4.275, 3.302, 5.013] | **5.204** [5.204, 5.088, 5.908] | **6,0** [9,5, 6,0, 4,3] | 778 |
| batata | 4 | base | 3 | **0,08** [0,10, 0,08, 0,07] | **13.521** [11.272, 13.521, 14.262] | **14.272** [11.762, 14.272, 17.548] | **—** [—, —, —] (3× sem alerta em ≥91 s) | 590 |
| batata | 4 | pr1 | 3 | **0,09** [0,06, 0,12, 0,09] | **3.993** [5.683, 2.993, 3.993] | **4.478** [6.590, 4.122, 4.478] | **7,4** [10,2, 7,4, 6,7] | 488 |

Histórico do mesmo portão, para transparência: a 1ª rodada com a métrica de
CPU (`*-gate5-r*.json`) REPROVOU o batata 4 câm. em CPU-ms por análise (+12 %,
as 3 repetições concordando). Causa e correção no CHANGELOG ("ADENDO 1"):
regras/conformidade/`to_dict()` refeitos a cada quadro de vídeo e emissão para
sala vazia serializando o payload. Rodadas anteriores (`gate`, `gate2`–`gate4`)
foram medidas só em tempo de relógio, sob saturação, e ficam como indicativo.

### Perfil atual (2 repetições, `*-gate-at-r*.json`)

| perfil | câm. | árvore | n | FPS de análise/câm. | idade da análise p50 (ms) | idade p95 (ms) | latência de alerta (s) | fundo (% de 1 núcleo) |
|---|---|---|---|---|---|---|---|---|
| atual | 1 | base | 2 | **0,76** [0,87, 0,66] | **1.135** [984, 1.287] | **1.718** [1.210, 2.227] | **22,0** [14,7, 29,4] | 408 |
| atual | 1 | pr1 | 2 | **1,38** [1,50, 1,26] | **946** [884, 1.008] | **1.308** [1.155, 1.461] | **4,3** [3,7, 4,8] | 430 |
| atual | 4 | base | 2 | **0,25** [0,22, 0,28] | **4.048** [4.698, 3.398] | **4.607** [5.268, 3.945] | **33,4** [34,1, 32,7] | 446 |
| atual | 4 | pr1 | 2 | **0,32** [0,28, 0,37] | **1.559** [1.831, 1.287] | **2.522** [2.985, 2.060] | **6,9** [8,5, 5,4] | 437 |

(Rodadas anteriores ao aquecimento no boot e à publicação reduzida sem
espectador; o PR1 de hoje só tem mudanças que reduzem trabalho nesse cenário.)

## Decisão de runtime (batata, 1 câmera, 3 repetições intercaladas)

`*-dec1cam-r*.json`. Todos os candidatos aprovados no guarda de qualidade
(`scripts/concordancia.py`, ≥ 97 %): ONNX dinâmico 100 %, OpenVINO dinâmico
99,17 % (EPI) / 100 % (pessoa).

| perfil | câm. | árvore | n | FPS de análise/câm. | idade da análise p50 (ms) | idade p95 (ms) | latência de alerta (s) | fundo (% de 1 núcleo) |
|---|---|---|---|---|---|---|---|---|
| batata | 1 | base | 3 | **0,46** [0,37, 0,46, 0,49] | **2.054** [2.572, 2.054, 1.844] | **2.722** [3.298, 2.722, 2.589] | **21,8** [32,3, 19,6, 21,8] | 337 |
| batata | 1 | onnx | 3 | **0,64** [0,52, 0,69, 0,64] | **1.875** [2.246, 1.755, 1.875] | **2.571** [3.734, 2.309, 2.571] | **5,2** [6,3, 5,2, 4,9] | 347 |
| batata | 1 | openvino | 3 | **0,56** [0,56, 0,70, 0,52] | **1.957** [2.150, 1.656, 1.957] | **2.891** [2.891, 2.254, 3.572] | **4,7** [5,8, 4,2, 4,7] | 430 |
| batata | 1 | pytorch | 3 | **0,42** [0,37, 0,42, 0,42] | **2.707** [3.140, 2.707, 2.701] | **3.997** [3.824, 3.997, 4.059] | **6,2** [5,7, 6,4, 6,2] | 356 |

Regra original: vence o aprovado com menor idade da análise p95; empate ≤ 5 %
→ PyTorch. **Regra do ADENDO 1 (a que vale):** menor CPU-ms por análise;
empate ≤ 10 % → PyTorch. Pelas duas, ONNX: CPU-ms por análise ONNX **2.926**,
OpenVINO 3.373, PyTorch 4.427 (mesmas rodadas; `resumo_cpu.py`). **ONNX** (2571 ms) vence: OpenVINO fica 12 % atrás e PyTorch 55 %.
Padrão `PPE_RUNTIME=auto` / `PERSON_RUNTIME=auto` (o primeiro aprovado de
`RUNTIME_ORDEM=onnx,pytorch` que exista no disco; sem export, PyTorch).
O OpenVINO usa 1,1 GB de RSS contra 0,7 GB do ONNX.

## OpenVINO na iGPU (L1 do ADENDO 1)

Batata 1 câm., 3 repetições, `*-l1-r*.json` — CPU-ms do servidor por análise
ONNX → OpenVINO GPU FP32: **6.432 → 1.401 (−78 %)**. Detalhes e guarda no
CHANGELOG ("L1"). Padrão a partir do PR2: `RUNTIME_ORDEM=openvino-gpu,onnx,pytorch`.

## Tracker

ByteTrack não reduziu fragmentação de forma consistente e custou até 4,2 % da
inferência do detector de pessoa na multidão (> 3 %): fica em config
(`TRACKER=bytetrack`). Tabela e método em CHANGELOG §4.5.

## Limitações

- **Nenhuma rodada desta sessão teve a máquina livre** (CPU de terceiros
  < 15 % em todas as rodadas de um portão). Pelo ADENDO 1, item 6, os números
  absolutos daqui não são para a banca: antes da final, rodar
  `python scripts/bench.py --rapido` na máquina da apresentação (ver DEMO.md).

- Carga de fundo de terceiros alta e variável (ver acima): números absolutos
  desta máquina não valem para outra; as comparações intercaladas valem.
- As fixtures são curtas (7–20 s) e tocam em loop; o corte do loop é uma
  "troca de cena" que fragmenta IDs.
- A latência de alerta é ancorada no quadro 0 de uma fixture em que a violação
  já está presente: mede "câmera liga → alerta no navegador" com modelos
  quentes, não "pessoa tira o capacete no meio da cena".
- "base" toca o arquivo em câmera lenta (no ritmo da inferência), o que lhe
  dá CPU de graça no vídeo; o PR1 toca em tempo real, como uma câmera de verdade.
- Perfil batata simula "2 núcleos fracos" com afinidade; L3, memória e
  barramento continuam os da máquina inteira.
