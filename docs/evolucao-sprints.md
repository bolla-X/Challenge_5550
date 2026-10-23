# Do protótipo ao produto: evolução por sprint

Linha do tempo do VisionEPI de 16/04 a 23/10/2026, com commits (hash curto e data), prints que existem no repositório e métricas medidas que já
estão escritas nos documentos. Toda métrica traz a fonte. Autoria de commit aparece como o *handle* gravado no git; nenhum foi mapeado para integrante.

**Como ler os números.** Cada medida foi feita numa máquina diferente: Sprint 1 em GPU RTX; Sprint 3 em AMD Ryzen 7 5700X só com CPU; relatório de IA de
28/09 em Xeon de 2 núcleos sem GPU; NEXT 2026 em Intel i7-1355U, com a máquina disputada por outros processos. **Só se comparam os pares "antes e
depois" medidos na mesma máquina e na mesma sessão**, como cada tabela indica.

**Marcas de procedência.** Sprints 1 e 2: *reconstruído a partir dos documentos de fase (sem commits na main)*. Sprints 3 e 4: *reconstruído a partir do histórico do git*
(`docs/specs/gitlog-main.txt`), complementado pelos relatórios de fase.

## Resumo em uma tabela

| Sprint | Período | Marco | Evidência principal |
|---|---|---|---|
| 1 | 16/04 a 04/05 | Detecção de EPIs com ensemble YOLOv8, rastreio, zona de risco | FASE1; sem commits na `main` |
| 2 | 05/05 a 22/06 | Pose por pessoa: queda, postura, zona | FASE2; sem commits na `main` |
| 3 | 23/06 a 24/08 | Protótipo V5, migração para React, multicâmera, Vyra, autenticação com papéis | commits de 19/07 a 24/08 |
| 4 | 25/08 a 23/10 | Camada LLM, peso próprio, NEXT 2026, produto de empresa, Gestão de EPIs | commits de 08/09 a 22/10, relatórios de IA, CHANGELOG |

## Sprint 1 (16/04 a 04/05): detecção de EPIs

*Reconstruído a partir dos documentos de fase (sem commits na main).*

- Escopo e resultado: `docs/challenge/FASE1-DETECCAO-DE-EPIS.md`; PDF em `docs/pitch/FASE1-DETECCAO-DE-EPIS.pdf`.
- Métricas (SH17, 810 imagens de teste, imgsz 640): capacete mAP@0,5 0,669; colete 0,490; luvas 0,570; óculos 0,696; máscara 0,696; calçado 0,615; protetor
  auricular 0,244; agregado 0,621. Nenhuma classe atinge a meta sugerida de 0,75 (FASE1 §3).
- Detector de pessoa: mAP@0,5 0,740 (FASE1 §3.2). Pipeline completo, 1 câmera, GPU RTX: cerca de 19,5 quadros por segundo.
- Prints: nenhum print desta sprint está no repositório.

## Sprint 2 (05/05 a 22/06): pose estimation

*Reconstruído a partir dos documentos de fase (sem commits na main).*

- Escopo e resultado: `docs/challenge/FASE2-POSE-ESTIMATION.md`; PDF em `docs/pitch/FASE2-POSE-ESTIMATION.pdf`.
- Métricas: PCK **não medido**; 19 testes da lógica de classificação com 100 % de acerto em casos controlados (FASE2 §3). O teste ao vivo de 23/09 que o
  mesmo documento descreve é evidência da Sprint 4.
- Prints: nenhum print desta sprint está no repositório.

## Sprint 3 (23/06 a 24/08): do protótipo a um sistema multicâmera com perfis

*Reconstruído a partir do histórico do git e do relatório da Fase 3.*

### O protótipo (19/07 a 06/08)

| Data | Commit | Handle | Marco |
|---|---|---|---|
| 19/07 | `e1e483a` | bolla-X | "Adicionar projeto VisionEPI V5": **primeiro commit da `main`**, o protótipo |
| 05/08 | `292695a` | lukiin-z | "Initial commit: VisionEPI com frontend React + TS + Vite": **migração para React** |
| 05/08 | `d771ca7` | lukiin-z | Merge que resolve os conflitos mantendo a versão migrada para React |
| 05/08 | `d224bd0` | lukiin-z | Remove artefatos de runtime e pesos do controle de versão |
| 05/08 | `e1e144f` | lukiin-z | Redesign completo: direção "Autoridade Discreta" |
| 06/08 | `07d5ed8` | lukiin-z | Motion, som e UX: chimes, sparkline, paleta de comandos, skeletons, acessibilidade |
| 06/08 | `655c10e` | lukiin-z | Perfis: Supervisor, mute por perfil |
| 06/08 | `8f10da5` | lukiin-z | Layout, polimento visual, motion e perfis (Operador, Técnico, Supervisor) |

### Multicâmera e autenticação (23 e 24/08)

| Data | Commit | Handle | Marco |
|---|---|---|---|
| 23/08 | `bd6e016` | bolla-X | Interface multicâmera: grade, quiosque do operador, foco por câmera (dados de câmera ainda simulados) |
| 23/08 | `aa852cc` | Lucas Zolla Assis | Vídeo por câmera, resolução e FPS configuráveis, detecção real de dispositivos |
| 24/08 | `e4cd04c` | lucas-baraldi | Modelo Vyra (14 classes) e detecção de óculos |
| 24/08 | `c3b5ffa` | lucas-baraldi | Revisão de qualidade em 10 itens |
| 24/08 | `f7b29c0` | lucas-baraldi | Uma pose por pessoa, geometria de queda em pixels |
| 24/08 | `c24c011` | lucas-baraldi | Reconexão automática com backoff |
| 24/08 | `6bfeb41` | lucas-baraldi | Autenticação com papéis, REST e WebSocket |
| 24/08 | `204206f` | lucas-baraldi | Operador restrito à câmera do setor |
| 24/08 | `2d74e96` | lucas-baraldi | Captura destravada e multicâmera com duas webcams |

**Métricas medidas (`docs/challenge/FASE3-NOTIFICACAO-INTELIGENTE.md` §3):** latência do alerta de severidade alta 1,17 s (meta 5 s, dentro); crítica 1,37 s (meta 1 s,
**37 % acima**).

**Prints:** nenhum print dessa data está no repositório.

## Sprint 4 (25/08 a 23/10): da camada LLM ao produto de empresa

*Reconstruído a partir do histórico do git e dos relatórios.*

### 08 e 09/09: instalação, segurança e camada LLM

| Data | Commit | Handle | Marco |
|---|---|---|---|
| 08/09 | `73edc00` | lukiin-z | Alembic passa a ser o dono do esquema (depois do teste vermelho `e51d952`) |
| 08/09 | `ec41617` | lukiin-z | Escopo de câmera passa a valer no WebSocket (teste vermelho `e790469`) |
| 09/09 | `a42d2e5` | lukiin-z | Detector de pessoa ligado por padrão (teste vermelho `0769c97`) |
| 09/09 | `f379910` | lukiin-z | Histerese conta detecção e não iteração do laço (teste vermelho `b834d7d`) |
| 09/09 | `9b2f995`, `0950df0`, `fd97d46` | lukiin-z | Camada LLM: schema e provedor; disparo assíncrono; ligada no boot |
| 09/09 | `8172fbf` | lukiin-z | 6 goldens reais gravados; os 18 testes viram verdes |
| 09/09 | `9737ad4` | lukiin-z | Credencial RTSP redigida em todas as saídas |
| 09/09 | `6dcccb5` | lukiin-z | Modo fixture como estado de primeira classe |
| 09/09 | `7945dcf` | lukiin-z | Descarte de quadro atrasado em fonte de rede |

Medidas (`docs/SPRINT3.md`, `docs/BENCH.md`; Ryzen 7 5700X, só CPU): pipeline completo, 1 câmera, **19,56 fps** (valor que o README cita); custo do LLM no caminho do quadro, FPS 19,53 para 19,45 (**-0,4 %**) e `submeter()` em **9 a 13 microssegundos**;
latência real do LLM de **16 a 38 s** por chamada; descarte de quadro atrasado, latência de **13,5 s para 2,55 s** (BENCH, Fase 7); detector de pessoa
padrão custa **-20 % de FPS** (24,32 para 19,42 a imgsz 416).

### 28/09: peso próprio treinado no domínio

| Data | Commit | Handle | Marco |
|---|---|---|---|
| 28/09 | `083e947` | lukiin-z | Peso VisionEPI treinado no Construction-PPE e avaliação completa |
| 28/09 | `0a42644` | lukiin-z | Classes negativas e política de "missing" (`ausencia` ou `evidencia`) |
| 28/09 | `c229c3f` | lukiin-z | Segundo gatilho do LLM e harness de avaliação por pessoa |
| 28/09 | `77a659a` | lukiin-z | `bench_pipeline` com `--classes`: FPS Sprint 3 contra Sprint 4 |
| 28/09 | `52e10e2` | lukiin-z | Evidências: dashboard rodando com o peso novo, vídeo de 96 s, casos antes e depois |
| 28/09 | `c214b37` | lukiin-z | Relatório técnico, diagrama da arquitetura final, auditoria dos erros |

Medidas na **mesma máquina e sessão** (Xeon de 2 núcleos, `docs/SPRINT4.md`):

| Medida | Antes (peso do Vyra e COCO) | Depois (peso próprio) |
|---|---|---|
| Precisão do alerta "sem capacete" (236 pessoas) | **0,39** | **0,85** |
| Revocação do alerta "sem capacete" | 0,87 | 0,92 |
| Precisão do alerta "sem colete" | 0,34 | 0,87 |
| Revocação do alerta "sem colete" | 0,79 | **0,69** (piorou) |
| Alertas falsos de capacete em canteiro, 1 imagem por cena | 27 de 92 | 3 de 92 |
| Inferência por imagem | 354 ms | 49 ms |
| FPS do pipeline completo, detecção a cada quadro | **3,42** | **11,15** |

Prints e evidências no repositório: `docs/evidencias/app/` (grade, foco, abas, visão do operador e do técnico), `docs/evidencias/casos/` (lado a lado, antes e
depois), `docs/evidencias/grafico_precisao_revocacao.png`, `docs/evidencias/demo_dashboard_sprint4.mp4` (96 s), `docs/arquitetura_sprint4.png`.

### 14 a 22/10: FIAP NEXT 2026 e produto de empresa

| Data | Commit (PR) | Handle | Marco |
|---|---|---|---|
| 14/10 | `a6d303b` (#16) | lucas-baraldi | PR7: NEXT 2026 integrado com a Sprint 4 de IA (captura contínua, agendador, OpenVINO, privacidade, diferenciais, funções criativas, demo) |
| 14/10 | `d76941b` (#17) | lucas-baraldi | Fumaça da demo na `main` e verificação pós-merge |
| 17/10 | `75d0de6` (#18) | lucas-baraldi | Verificação final da `main` (15/10) |
| 17/10 | `44dafdc` (#19) | lucas-baraldi | PR8: QA de base e fábrica conectada |
| 19/10 | `2ede29a` (#20) | lucas-baraldi | PR9: experiência de empresa e operação avançada |
| 20/10 | `4ca2a7e` (#21) | lucas-baraldi | PR10: todos os caminhos testados e entrega |
| 22/10 | `a4df215` (#22) | lucas-baraldi | MISSÃO 7: área de detecção por câmera |

Medidas do NEXT 2026 (`docs/NEXT2026/BENCHMARKS.md` e `CHANGELOG.md`; máquina disputada por outros processos, valores sob saturação são indicativos):

| Medida | Valor | Fonte |
|---|---|---|
| Latência do 1º alerta, perfil batata (2 E-cores), 1 câmera | **38,0 s** (base, portão do PR1) e **1,941 s** (PR2, portão do PR2). **Atenção:** são duas rodadas diferentes; o README junta as duas em "~2 s (antes, 38 s)". No mesmo portão do PR2, a comparação direta é 5,586 s (PR1) contra 1,941 s (PR2) | BENCHMARKS |
| CPU do servidor por análise, ONNX para OpenVINO na iGPU (batata, 1 câmera) | 6.432 ms para 1.401 ms (**-78 %**) | CHANGELOG, L1 |
| Espera do lock de inferência, 4 câmeras | p50 de 37 s eliminada pelo agendador único | CHANGELOG, §4.1 |
| FPS de vídeo publicado, 4 câmeras | 0,84 para 10,7 | CHANGELOG, §4.1 |
| Concordância do runtime contra o PyTorch@640 | ONNX dinâmico 100 %; OpenVINO iGPU FP32 100 %; ONNX estático 95,04 % (reprovado) | CHANGELOG, §4.2 e L1 |
| Resolução: concordância de EPI a 416 | 63,6 % (capacete 8 %); mantido 640 | CHANGELOG, §4.3 |
| Saúde visual: câmera tampada | 3,8 s até OBSTRUÍDA e 9,9 s até o alerta | CHANGELOG, M1 |
| Matriz de permissões | 1.403 casos; 8 divergências corrigidas | CHANGELOG, MISSÃO 4 |
| Crawler botão a botão (20/10) | 78 rotas por papel e tema, 820 elementos, 0 sem efeito | `docs/NEXT2026/QA.md` |
| Área de detecção (22/10, `next_multidao.mp4`) | 0 pessoas fora da área; sem ganho de tempo (p50 961 ms sem, 1.014 ms com); +71 pessoas dentro (+24 %) | CHANGELOG, MISSÃO 7 |
| Suíte de testes | 378 (CONSOLIDADO, 23/09), 695 (release de 14/10), 3.201 a 3.288 (portões de 19 a 22/10) | CONSOLIDADO; CHANGELOG |

Prints: galeria em `docs/NEXT2026/galeria/` (nos dois temas e em três tamanhos; por exemplo `1920x1080-claro/10-gemeo-3d.webp`,
`1920x1080-claro/07-foco-alerta-critico.webp`, `1920x1080-claro/45-status.webp`, `1920x1080-claro/50-relatorio-mensal.webp`), `docs/NEXT2026/galeria/readme/palco.gif`
e as imagens "antes e depois" em `docs/NEXT2026/galeria/antes-depois/`.

### 23/10: entrega de Engenharia de Software

| Marco | Evidência |
|---|---|
| Módulo Gestão de EPIs (colaboradores, catálogo com CA, entregas, ocorrências, CSV) | ADR 0008; `app/api/gestao.py`; contrato `docs/specs/es-sprint4-contrato-gestao.md` |
| Fallback do LLM na demo | ADR 0009; `tests/test_llm_demo_fallback.py` |
| Amostra de vídeo versionada | ADR 0010; `amostras/` |
| Documentação, Trello, vídeo e pacote | `docs/arquitetura.md`, `docs/requisitos.md`, `docs/scrum/`, `docs/manual-de-uso.md`; board https://trello.com/b/zVZW2n1p/visionepi-challenge-3ecr |

Hash do commit de squash e prints novos (`docs/img/01-login.png` a `14-tema-escuro.png`): ver [scrum/ata-review-final-sprint4.md](scrum/ata-review-final-sprint4.md).

## O que mudou de natureza ao longo das sprints

| Eixo | Sprint 1 e 2 | Sprint 3 | Sprint 4 |
|---|---|---|---|
| O que é o sistema | detectores e regras sobre um quadro | sistema com perfis, portaria e multicâmera | produto que roda offline, integra com a fábrica e gere EPIs |
| Como se prova | métricas por classe num dataset público | latência medida num sistema rodando | medições intercaladas com guarda de qualidade, portão de testes e crawler |
| O que se admite não saber | PCK, desempenho na planta | gap de 37 % na latência crítica, Telegram | LLM sem medição em conjunto anotado, dataset da planta inexistente |
| Frontend | n/a | React com perfis (migrado em 05/08) | sistema de design com tema claro e escuro, 25 rotas de tela cheia |
