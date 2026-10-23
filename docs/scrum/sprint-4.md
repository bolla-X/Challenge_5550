# Sprint 4: validação industrial e produto (25/08 a 23/10/2026)

> **Reconstruído a partir do histórico do git** (`docs/specs/gitlog-main.txt`) e dos documentos `docs/challenge/FASE4-VALIDACAO-INDUSTRIAL.md`,
> `docs/SPRINT3.md`, `docs/SPRINT4.md`, `docs/NEXT2026/CHANGELOG.md`, `docs/NEXT2026/ESTADO.md` e `docs/specs/ESTADO-es-sprint4.md`. Review e retro
> abaixo são reconstruídas dos documentos, não de reunião. A sprint inclui a banca do Challenge (23/09), a final do FIAP NEXT (outubro) e a entrega
> de Engenharia de Software de 23/10.

> **Nota de nomenclatura.** `docs/SPRINT3.md` ("camada LLM", commits de 09/09) e `docs/SPRINT4.md` ("solução final", commits de 28/09) foram escritos para a
> disciplina de IA, onde essas eram a Sprint 3 e a Sprint 4. Pela regra de datas desta disciplina (Sprint 3 termina em 24/08), os dois trabalhos caem
> **na Sprint 4**. Os arquivos não foram renomeados nem reescritos. Aqui eles aparecem como "relatório de IA, camada LLM" e "relatório de IA, peso próprio".

## Objetivo da sprint

Solução completa, integrada e testada no ambiente simulado da Metaindústria (FASE4 §1): operação contínua de 30 minutos, câmeras reais, pitch e documento
consolidado; e, depois da banca, transformar o sistema em produto de empresa e entregar a **gestão de EPIs e segurança industrial** de forma que o
avaliador consiga instalar, rodar e navegar seguindo só o README (`docs/specs/es-sprint4.md`).

## Sprint backlog

### Trilha A: endurecimento e camada LLM (08 e 09/09)

| Item | RF | Estado | Evidência |
|---|---|---|---|
| Alembic dono do esquema; teste do caminho de instalação | RNF07 | Concluído | `e51d952`, `73edc00` |
| Escopo de câmera também no WebSocket | RNF02 | Concluído | `e790469`, `ec41617` |
| Detector de pessoa ligado por padrão | RF02 | Concluído | `0769c97`, `a42d2e5`; ADR 0002 |
| Histerese que conta detecção e não iteração do laço | RF08 | Concluído | `b834d7d`, `f379910` |
| Camada LLM: schema, provedor atrás de interface, dois prompts, disparo assíncrono, ligada no boot | RF18 | Concluído | `9b2f995`, `0950df0`, `fd97d46`; 6 goldens reais em `8172fbf` |
| Credencial RTSP redigida em toda saída; cadastro de câmera por CLI sem senha em argv | RNF03, RF12 | Concluído | `9737ad4`, `18b3b7a` |
| Modo fixture como estado de primeira classe; teto de abertura de fonte de rede; descarte de quadro atrasado | RF15, RF14 | Concluído | `6dcccb5`, `3088570`, `7945dcf` |
| Webcam ponta a ponta; fonte cega aparece na tela; perfil Dahua medido | RF14 | Concluído | `57c67a5`, `2f2e826`, `0ab0db9` |

### Trilha B: validação industrial (relatório da Fase 4, 23/09)

| Item | Estado | Fonte |
|---|---|---|
| Conexão com câmeras RTSP reais da planta parceira, todas ao mesmo tempo, sem cair | Entregue | FASE4 §2 |
| Operação contínua de 30 minutos sem reinício manual | Entregue | FASE4 §3 |
| Protetor auricular e uso incorreto fechando o escopo mínimo (RF16) | Entregue | FASE4 §5 |
| Confidencialidade: imagens reais usadas só ao vivo, com autorização; nada armazenado | Entregue | FASE4 §4 |
| Pitch dentro de 5 minutos | **Parcial `[~]`**: gravação de apoio de cerca de 10 min, risco declarado | FASE4 §7 e §8 |

### Trilha C: relatório de IA, peso próprio (28/09)

| Item | RF | Estado | Evidência |
|---|---|---|---|
| Peso VisionEPI treinado no Construction-PPE, um modelo só | RF01 | Concluído | `083e947`, `859bf4f` |
| Classes negativas e política `ausencia`/`evidencia` | RF17 | Concluído | `0a42644` |
| Segundo gatilho do LLM no "não verificado" | RF18 | Concluído | `c229c3f` |
| Avaliação por pessoa e IC por cenas | RF19 | Concluído | `c229c3f`; `docs/avaliacao/RESUMO.md` |
| Medir o LLM no conjunto anotado | RF49 | **Não feito**: sem acesso à API no ambiente | `docs/SPRINT4.md` §7 |

### Trilha D: FIAP NEXT 2026 (medições datadas de 13/10; squashes na `main` de 14 a 22/10)

| Item | RF | Estado | Evidência |
|---|---|---|---|
| Desempenho: captura contínua, agendador único, OpenVINO e ONNX com guarda de concordância | RNF05 | Concluído | PR7 `a6d303b` (#16); ADR 0006 |
| Diferenciais: replay com rosto desfocado, queda por ID, aproximação, privacidade, mapa de calor, relatório de turno, prova de escala | RF22, RF23, RF24, RF32, RNF01 | Concluído | `a6d303b` |
| Funções criativas: Portal, Você vs. a IA, Liga, Modo TV, celular como câmera, planta, rótulos | RF26, RF33, RF36 | Concluído | `a6d303b` |
| Modo demonstração, `demo reset`, fumaça da demo | RF38 | Concluído | `a6d303b`, `d76941b` (#17) |
| Fábrica conectada, saúde visual, evacuação, editor de regras, permissão de trabalho | RF27 a RF31 | Concluído | PR8 `44dafdc` (#19), PR9 `2ede29a` (#20) |
| Primeiro acesso, ajuda, status do sistema, API documentada, relatório mensal, matriz de permissões, crawler | RF32, RF37, RNF02, RNF14 | Concluído | PR9, PR10 `4ca2a7e` (#21) |
| Área de detecção por câmera | RF35 | Concluído | MISSÃO 7 `a4df215` (#22) |

### Trilha E: entrega de Engenharia de Software (23/10)

Estado na redação deste documento (23/10, antes do fechamento). O fechamento real está na [ata](ata-review-final-sprint4.md).

| Grupo da spec | Item | Estado na redação |
|---|---|---|
| G | Base `origin/main`; rebrand não mesclado; branch `es-sprint4-entrega` | Concluído (`docs/specs/ESTADO-es-sprint4.md`) |
| F0 | Inventário: stack, telas, banco, docs, links, git log | Concluído (mesmo arquivo) |
| F1 | Seed de gestão, módulo Gestão de EPIs, fallback do LLM, amostra versionada, lint, varredura de segredos, pytest, E2E | Em andamento (RF39 e RF41 a RF47: código e testes existem; execução verde a confirmar na ata) |
| F2 | Teste "avaliador" em clone limpo | Pendente |
| F3 | README, arquitetura, requisitos, Scrum, manual, evolução | Documentos F3.2 a F3.6 escritos; README é da sessão principal |
| F4 | Trello: board criado, cards por requisito, ata | Board criado e público; cards a criar |
| F5 e F6 | Vídeo sem narração e pacote zipado | Pendente |

## Incremento entregue

O produto no estado da `main` em 22/10 (`a4df215`) mais a Gestão de EPIs, o fallback do LLM e a amostra versionada desta entrega. A lista de
funcionalidades por requisito está em [../requisitos.md](../requisitos.md); a arquitetura em [../arquitetura.md](../arquitetura.md); o
histórico de marcos, com métricas e fonte, em [../evolucao-sprints.md](../evolucao-sprints.md).

### Números registrados na sprint (cada um com a fonte)

| Medida | Valor | Fonte |
|---|---|---|
| Precisão do alerta "sem capacete" (236 pessoas, por pessoa) | 0,39 para 0,85 | `docs/SPRINT4.md` |
| Alertas falsos de capacete em canteiro, 1 imagem por cena (54 cenas industriais) | 27 de 92 para 3 de 92 | `docs/SPRINT4.md` |
| FPS do pipeline completo, detecção a cada quadro (máquina de 2 núcleos) | 3,42 para 11,15 | `docs/SPRINT4.md` |
| CPU do servidor por análise, ONNX para OpenVINO GPU FP32 (perfil batata, 1 câmera) | 6.432 ms para 1.401 ms (-78 %) | `docs/NEXT2026/CHANGELOG.md`, L1 |
| Latência do 1º alerta, perfil batata, 1 câmera | 38,0 s (base, portão do PR1) e 1,941 s (PR2, outra rodada) | `docs/NEXT2026/BENCHMARKS.md` |
| Custo de `submeter()` do LLM no caminho do quadro | 9 a 13 microssegundos; delta de FPS -0,4 % | `docs/SPRINT3.md` |
| Área de detecção: pessoas fora da área | 0; sem ganho de tempo (p50 961 ms sem e 1.014 ms com) | CHANGELOG, MISSÃO 7 |
| Matriz de permissões | 1.403 casos; 8 divergências achadas e corrigidas | CHANGELOG, MISSÃO 4 |
| Suíte `pytest` no portão da MISSÃO 7 (22/10) | 3.288 aprovados | CHANGELOG, "Portão da MISSÃO 7" |
| E2E no portão da MISSÃO 7 | 76 aprovados, 1 falha sensível a carga, 2 ignorados | idem |
| Crawler botão a botão (20/10) | 78 rotas por papel e tema, 820 elementos, 0 sem efeito | `docs/NEXT2026/QA.md` |

## Review (reconstruída dos documentos)

**Entregue:** as quatro trilhas A a D e a base técnica da trilha E. A review formal desta entrega é a
[ata da Review Final](ata-review-final-sprint4.md).

**Limitações e pendências que os documentos declaram** (nenhuma foi suavizada):
- A camada LLM **não foi medida** no conjunto anotado (RF49); 3 cenas sustentam existência, não acurácia.
- Nenhuma medição do peso próprio em câmera da planta; o dataset da planta não existe (RF50).
- Pitch de apoio de cerca de 10 min contra os 5 pedidos (FASE4 §8).
- Telegram não implementado (RF48); pose por pessoa em modo stream não aplicada (RF51); ruído de alertas na multidão (RF53).
- Os números absolutos do bench foram colhidos com a máquina disputada por outros processos; só as comparações intercaladas valem.
- Falha de E2E sensível à carga no crawler, classificada com evidência e não corrigida por enfraquecer teste (MISSÃO 7).

## Retrospectiva (reconstruída dos documentos)

Não houve retro registrada. O que a documentação da própria sprint registra como lição:

- **Erros de método achados e corrigidos no caminho** (CHANGELOG, "Instrumentação e benchmark"): medir só o PID do lançador do Python dava 0 % de CPU;
  o navegador do bench passava fome numa máquina carregada; a sonda copiava o buffer inteiro a cada pedaço. As rodadas afetadas foram marcadas.
- **Registro corrigido:** uma anotação dizia "640 fica em 72 % de concordância", impossível com 640 como referência; era o 512 com o rótulo trocado
  (CHANGELOG, §4.3).
- **Expectativa refutada em parte:** na Sprint de IA o palpite "v2 reporta menos EPIs ausentes na cena ambígua" estava metade errado; o dado foi publicado
  assim (`docs/SPRINT3.md`).
- **Medido e não adotado:** ONNX no Ryzen (-26 % de FPS), `static_image_mode=False` (2,25x mais rápido, mas a documentação oficial descreve `true` como o modo para imagens estáticas possivelmente não relacionadas, que é o que o código alimenta), classe `Person` do
  Vyra, YOLOE-26 (licença do MobileCLIP), lote de câmeras (95,04 % de concordância).
- **Teste de clone limpo achou defeitos de instalação** que o desenvolvimento diário escondia: runtime acelerado nunca aprovado, export ONNX sem `onnx`,
  auto-instalação do Ultralytics no Python global, `torch` sem versão fixa (CHANGELOG, "Teste de clone limpo").
- **Ambiente:** CPU tomada por outros programas foi a ameaça nº 1 em todas as medições; partida a frio levou até 248 s depois de reiniciar o PC.
- **Ações negadas pela permissão e não contornadas** ficam registradas no ESTADO, como `git -C` nesta entrega.
