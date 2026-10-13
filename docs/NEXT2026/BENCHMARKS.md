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

Principais (decidem o portão):

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

<!-- GATE4 -->

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

Regra: vence o aprovado com menor idade da análise p95; empate ≤ 5 % →
PyTorch. **ONNX** (2571 ms) vence: OpenVINO fica 12 % atrás e PyTorch 55 %.
Padrão `PPE_RUNTIME=auto` / `PERSON_RUNTIME=auto` (o primeiro aprovado de
`RUNTIME_ORDEM=onnx,pytorch` que exista no disco; sem export, PyTorch).
O OpenVINO usa 1,1 GB de RSS contra 0,7 GB do ONNX.

## Tracker

ByteTrack não reduziu fragmentação de forma consistente e custou até 4,2 % da
inferência do detector de pessoa na multidão (> 3 %): fica em config
(`TRACKER=bytetrack`). Tabela e método em CHANGELOG §4.5.

## Limitações

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
