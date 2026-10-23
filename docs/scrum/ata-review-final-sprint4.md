# Ata da Review Final, Sprint 4

Data da entrega: 23/10/2026. Disciplina: Engenharia de Software, FIAP 3ECR. Repositório: https://github.com/bolla-X/Challenge_5550.
Board: https://trello.com/b/zVZW2n1p/visionepi-challenge-3ecr (card "Ata da Review Final — Sprint 4", lista Reviews/Atas).

Esta ata registra o incremento, os critérios e as evidências medidas na preparação da entrega (23/10/2026), com o comando e o
número de cada uma. O que só existe depois do merge do PR (hash do squash, clone limpo da `main`, pacote zipado) está no card da ata
no Trello, para não exigir um segundo PR. Esta ata não registra falas nem presenças que não tenham sido informadas.

## 1. Participantes

Equipe (conforme informado pelo grupo): Pedro Gonçalves (RM 557936), Lucas Baraldi (RM 555407), Lucas Zolla (RM 557952), Vitor Pantarotto (RM 554961).

Correção (23/10/2026, fechamento): nos documentos antigos (`docs/challenge/`), o sobrenome do integrante do RM 557936 foi trocado para "Pedro Gonçalves", nome confirmado pelo grupo; a identificação como a mesma pessoa vem da composição da equipe (mesmos 4 integrantes).

Presenças e formato da reunião de review: **não informados ao redator**. Esta ata é a review do incremento a partir das evidências, não o registro de uma
reunião.

## 2. Incremento entregue

Solução de gestão de EPIs e segurança industrial para a Metaindústria, com a visão computacional já existente e o módulo novo desta sprint. Resumo; o
detalhamento está em [../requisitos.md](../requisitos.md) e [../arquitetura.md](../arquitetura.md).

**Já existia na `main` em 22/10 (`a4df215`):** detecção de EPI, pessoa e pose em tempo real, alertas com histerese, incidentes e linha causal, cadeia de
custódia SHA-256, replay com rosto desfocado, gêmeo digital, simulador, Portal de Entrada, saúde visual da câmera, fábrica conectada (OPC UA, MQTT, webhook),
evacuação, editor de regras, permissão de trabalho, relatório mensal, Modo Apresentação, área de detecção por câmera, matriz de permissões, modo
demonstração offline com banco isolado e a segunda opinião de um LLM, que nunca cria alerta.

**Acrescentado nesta entrega (23/10):**

| Item | RF | Onde |
|---|---|---|
| Módulo Gestão de EPIs: colaboradores com histórico, catálogo com CA e validade, entregas e devoluções, ocorrências, exportação CSV | RF41 a RF45, RF47 | `app/api/gestao.py`, `app/services/gestao_epi.py`, `frontend/src/components/gestao.tsx` e `gestao/`; migração `a8b9c0d1e2f3`; ADR 0008 |
| Seed idempotente de dados simulados (comando `flask --app wsgi gestao semear` e automático na demo) | RF46 | `app/services/gestao_seed.py`, `app/cli.py`, `app/demo.py` |
| Fallback determinístico do LLM, rotulado "modo demonstração", só com `DEMO_MODE` | RF40 | `app/llm/__init__.py`, `app/services/llm_risk_service.py`, ADR 0009 |
| Amostra de vídeo versionada (CC BY-SA 4.0) | RF39 | `amostras/`, ADR 0010 |
| Correções da revisão: vínculo colaborador–alerta proibido, CA e nome congelados na entrega, trilha de auditoria das edições, datas limitadas, 409 em duplicidade, alertas simulados fora do risco ao vivo e declarados no relatório mensal | — | auditoria da squad (seção 5.4) |
| Documentação: README âncora, arquitetura, 10 ADRs, requisitos com matriz, Scrum, manual de uso com 14 prints, evolução | F3.1 a F3.6 | `README.md`, `docs/` |
| Trello, vídeo sem narração e pacote zipado | F4 a F6 | seção 3 |

PR único e squash: aberto e mesclado na sequência desta ata; número, hash e saída do merge no card da ata no Trello.

## 3. Critérios atendidos

Tabela por critério de `docs/specs/es-sprint4.md`.

### G: Git

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| G.1 | `fetch --all`, base `origin/main`, `merge-base --is-ancestor` registrado, rebrand não mesclado | Atendido | `git merge-base --is-ancestor` saiu com código 1, mas isso só diz que os commits da branch não são ancestrais (a `main` recebe squash). Medição correta no fechamento: o **conteúdo** do rebrand já está na `main` pelo squash do PR7 (`a6d303b`, 14/10, 11 commits `rebrand(n)` no corpo); `git diff origin/feat/completo-com-rebrand origin/main -- frontend/src/styles/tokens.css` difere só pelo token `--sinal-amarelo` da MISSÃO 4. Nada foi mesclado |
| G.2 | Branch `es-sprint4-entrega` a partir da main | Atendido | `git switch -c es-sprint4-entrega main` (`main` = `origin/main` = `a4df215`) |
| G.3 | `[skip ci]` em todo commit e no título do squash; nenhum workflow | Atendido | os 4 commits da branch terminam em `[skip ci]` (seção 5.3); não há `.github/` no repositório nem no diff |
| G.4 | Só aditivo; regressão do fluxo câmera → YOLO → alerta antes do merge | Atendido | `git status` vazio em `camera_worker.py`, `app/vision/`, `risk_rules.py`, `alert_state_service.py`, `monitor_service.py` (auditor); fumaça `e2e/fumaca_demo.py --raiz .` **6/6** (2ª rodada; a 1ª deu 5/6 por tempo na troca de cena do palco, reproduzida à mão: o Portal chega a "Liberado"); `e2e/test_fluxos.py` **17 passed in 208.53s**; `e2e/test_missao4.py e2e/test_missao7.py` **18 passed in 130.78s** |
| G.5 | Um único PR, squash com `gh pr merge --squash --delete-branch` | ver card no Trello | executado depois desta ata |

### F0: Inventário

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| F0.1 | Stack real mapeada | Atendido | tabela "Fase 0" em `docs/specs/ESTADO-es-sprint4.md` |
| F0.2 | Telas, banco e docs das Sprints 1 a 3 mapeados | Atendido | mesmo arquivo: 25 rotas de tela cheia, SQLite e PostgreSQL, 19 migrações e 18 tabelas antes da Gestão |
| F0.3 | Links existentes procurados | Atendido | nenhum link de Trello, Figma ou vídeo no repositório; board novo criado |
| F0.4 | `git log` com datas lido | Atendido | `docs/specs/gitlog-main.txt`; 1º commit em 19/07/2026 |
| F0.5 | `.agents/skills/` lidos antes de mudança visual | Atendido | `apple-design` e `design-taste-frontend` lidos pela sessão principal e pelo agente de frontend antes da tela nova; a revisão de UI-design usou `apple-design` |

### F1: Aplicação

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| F1.1 | Demo reprodutível sem câmera IP e sem `GEMINI_API_KEY` | Atendido | `python run.py --demo` com `DEMO_WEBCAM=0` e sem a chave, num clone limpo: no ar em 19 s, 4 câmeras publicando análise (fumaça 6/6) |
| F1.2 | Amostra de vídeo versionada, leve, webcam opcional | Atendido | `amostras/canteiro_amostra.mp4`: h264 640x360, 7,0 s, 469.317 bytes; `tests/test_demo_amostra.py` **3 testes** (versionada e < 2 MB; gravação baixada vence; sem gravação a demo toca a amostra e avisa) |
| F1.3 | LLM com fallback determinístico sinalizado na UI; com chave, real | Atendido | `tests/test_llm_demo_fallback.py` **7 passed**; UI: `docs/img/13-status-llm-demo.png`; E2E `test_segunda_opiniao_*` e `test_pagina_status_rotula_o_llm_como_demonstracao` |
| F1.4 | Seed idempotente com dados simulados | Atendido | `tests/test_gestao_seed.py` **21 passed** (duas execuções sem duplicar; 24 colaboradores, 10 EPIs, 60 entregas, 15 ocorrências, 40 alertas) |
| F1.5 | Seed no primeiro start ou por comando único | Atendido | automático em `run.py --demo` (`app/demo.py`); `flask --app wsgi gestao semear` fora da demo só com `--dados-ficticios` |
| F1.6 | Fluxos principais existem e funcionam, tema claro e escuro | Atendido | dashboard, monitoramento, alertas, ocorrências, colaboradores com histórico, relatório/exportação, tema escuro: `e2e/test_es_sprint4.py` **26 passed** (lista no README, seção "Funcionalidades") |
| F1.7 | Lint, código morto, `.env.example` | Atendido | `ruff check .` → All checks passed!; `npm --prefix frontend run build` (tsc -b + vite) ✓; `.env.example` ganhou `LLM_DEMO_FALLBACK`; código morto: nenhum encontrado no diff |
| F1.8 | Varredura de segredos | Atendido | `git grep` de padrões de chave no HEAD → nada; histórico inteiro: só 2 literais falsos de teste (`"…CHAVE-FALSA…"`, `"FALSA" * 6`); nada removido |
| F1.9 | `pytest` verde | Atendido | **3528 passed, 8 warnings in 701.68s** (código final) |
| F1.10 | Playwright cobrindo cada fluxo principal, verde | Atendido | `e2e/test_es_sprint4.py` **26 passed in 85.24s** |

### F2: Teste "avaliador"

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| F2.1 | Clone limpo seguindo só o README | Atendido | `%TEMP%\visionepi-avaliador-1`, comandos da seção "Instalação — Windows (PowerShell)" do README, um por um (branch `es-sprint4-entrega` antes do merge) |
| F2.2 | Playwright contra essa instância | Atendido | `VISIONEPI_RAIZ=<clone> pytest e2e/test_es_sprint4.py` → **26 passed in 102.80s**; fumaça no clone **6/6** |
| F2.3 | Falha corrigida e repetida do zero | Atendido | passou na 1ª rodada; nenhuma correção de README foi necessária. O README ganhou a nota sobre os tracebacks do ONNX durante o `preparar.py` |
| F2.4 | Tempo total da instalação limpa | Atendido | **1293 s ≈ 21 min 33 s** (clone 6,5 s; venv 25,2 s; pip 619,3 s; npm ci 67,6 s; build 28,0 s; preparar 546,4 s) |
| F2.5 | PowerShell e macOS/Linux; "não testado em …" | Atendido | blocos separados no README; testado só em Windows 11; macOS/Linux marcados "não testado" |

### F3: Documentação

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| F3.1 | `README.md` âncora | Atendido | problema, proposta, funcionalidades, links (protótipo, Trello, vídeo https://youtu.be/jqkfFecsIiw), instalação, uso, demo, teste do avaliador, sprints, equipe, estrutura, prints |
| F3.2 | `docs/arquitetura.md` e ADRs | Atendido | 2 diagramas de componentes e 2 de sequência; 10 ADRs e índice |
| F3.3 | `docs/requisitos.md` com matriz | Atendido | 53 RF e 14 RNF; RF → card Trello → código → teste → sprint |
| F3.4 | `docs/scrum/` completo | Atendido | backlog, sprints 1 a 4 (com review e retro), DoD, esta ata |
| F3.5 | `docs/manual-de-uso.md` com prints | Atendido | 14 prints em `docs/img/` gerados por `scripts/capturar_telas_readme.py` (Playwright, demo) |
| F3.6 | `docs/evolucao-sprints.md` | Atendido | métricas com fonte e hashes |

### F4: Trello

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| F4.1 | Ordem de acesso | Atendido | MCP do Trello (plano A) |
| F4.2 | Board criado | Atendido | https://trello.com/b/zVZW2n1p/visionepi-challenge-3ecr |
| F4.3 | Listas | Atendido | Product Backlog, Sprint 1 a 4, Concluído, Reviews/Atas |
| F4.4 | Um card por requisito, labels, DoD, Sprint 4 em Concluído | Atendido | 67 cards de requisito (61 em Concluído com o checklist DoD de 9 itens marcado; 6 planejados no backlog), 4 cards-resumo de sprint, 4 de review/ata, 1 legenda. Limitação: o conector não nomeia etiquetas, então a cor = sprint, com legenda |
| F4.5 | Card "Ata da Review Final — Sprint 4" | Atendido | https://trello.com/c/OGh7n79Y |
| F4.6 | Board público e link no README | Atendido | criado com visibilidade pública; link no README |

### F5 e F6: Vídeo e pacote

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| F5.1 | 4:00 a 4:45, 1920x1080, H.264, sem áudio | Atendido | ffprobe: **275,0 s**, h264, 1920x1080, yuv420p, 30 fps, sem stream de áudio, 22.160.690 bytes |
| F5.2 | Storyboard | Atendido | `docs/pitch/storyboard.md` (7 cenas, tempos e legendas) |
| F5.3 | Cartelas HTML gravadas | Atendido | `scripts/video/cartelas.html` + `gravar_cartelas.py` |
| F5.4 | Demo gravada com legenda e cursor | Atendido | `scripts/video/gravar_demo.py` (barra de legenda e cursor injetados no DOM) |
| F5.5 | Montagem com ffmpeg + ffprobe | Atendido | `scripts/video/montar_video.py`; a gravação da demo esticou (161 s para 150 s de roteiro) e foi comprimida para 150 s em vez de cortada |
| F5.6 | 6 frames-chave conferidos | Atendido | abertura, solução, incidente, histórico, CA vencido, evolução: legendas legíveis; onde cobrem algo, são linhas finais de tabela. Uma montagem anterior mostrou o frame do CA vencido fora de sincronia e foi refeita |
| F5.7 | Vídeo fora do repositório | Atendido | saída em `bench/runtime/video/` (ignorado); no repo só storyboard e scripts |
| F6.1 a F6.3 | `.txt`, MP4 e `.zip` | ver card no Trello | gerados depois do merge, com `docs/` da `main` |

### FC: Fechamento

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| FC.1 a FC.3 | Squash, clone limpo da `main` + Playwright, relatório | ver card no Trello | executados depois desta ata |

## 4. Cobertura dos critérios de avaliação do enunciado

| Peso | Critério | Onde está coberto |
|---|---|---|
| 40 pts | Aplicação funcionando: fluxos principais e aderência ao problema | F1 e F2: 7 fluxos com E2E (26 testes) num clone limpo; Gestão de EPIs responde à ficha de EPI e ao CA; visão ao vivo responde à segurança reativa |
| 30 pts | Documentação: README, arquitetura, Scrum | F3 e F4 |
| 30 pts | Vídeo e evolução | F5, F6 e `docs/evolucao-sprints.md` |
| Diferencial | Rastreabilidade e consistência entre sprints | matriz em `docs/requisitos.md` e os mesmos IDs nos cards do Trello |

## 5. Evidências

### 5.1 Testes

| Medida | Valor | Comando |
|---|---|---|
| `pytest` completo | **3528 passed, 8 warnings in 701.68s** | `pytest -q` |
| `ruff` | All checks passed! | `ruff check .` |
| Build e tipos do frontend | ✓ built (tsc -b + vite) | `npm --prefix frontend run build` |
| E2E da entrega | **26 passed in 85.24s** (no checkout) e **26 passed in 102.80s** (no clone limpo) | `python -m pytest e2e/test_es_sprint4.py -q` |
| E2E de regressão do NEXT | `test_fluxos.py` 17 passed; `test_missao4.py` + `test_missao7.py` 18 passed | `python -m pytest e2e/<arquivo> -q` |
| Testes novos | `test_gestao_epi.py` 84, `test_gestao_seed.py` 21, `test_llm_demo_fallback.py` 7, `test_demo_amostra.py` 3 | `pytest <arquivo>` |
| Fumaça | 6/6 no checkout e 6/6 no clone limpo | `python e2e/fumaca_demo.py --raiz <pasta>` |

A suíte E2E completa do NEXT (`python -m pytest e2e -q`, 76+ testes) **não foi rodada inteira** nesta entrega; rodaram os arquivos acima.

### 5.2 Prints (`docs/img/`)

`01-login.png`, `02-inicio-supervisor.png`, `03-grade-cameras.png`, `04-foco-camera.png`, `05-incidentes.png`, `06-gestao-colaboradores.png`,
`07-gestao-historico.png`, `08-gestao-catalogo.png`, `09-gestao-entregas.png`, `10-gestao-ocorrencias.png`, `11-gestao-exportar.png`,
`12-relatorio-mensal.png`, `13-status-llm-demo.png` (painel da segunda opinião em modo demonstração), `14-tema-escuro.png`.

### 5.3 Commits

| Marco | Commit | Data |
|---|---|---|
| Base da entrega (MISSÃO 7, PR #22) | `a4df215` | 22/10/2026 |
| Gestão de EPIs | `1402f9c` | 23/10/2026 |
| Modo demonstração reprodutível | `bb20370` | 23/10/2026 |
| Documentação e scripts do vídeo | `55606a5` | 23/10/2026 |
| Prints, ata e ajustes finais | último commit da branch (no PR) | 23/10/2026 |
| Squash do PR único | card no Trello | 23/10/2026 |

Marcos anteriores, com data e hash: [../evolucao-sprints.md](../evolucao-sprints.md).

### 5.4 Portão da squad

- **Auditor** (segurança e arquitetura): sem STOP. Achado alto S1 (uma ocorrência podia ligar colaborador a alerta com ID de rastreio e imagem) corrigido
  com 400 `vinculo_proibido`; médios S2 a S7 corrigidos; S8 (fuso via `zoneinfo`) adiado como limitação, porque exige o pacote `tzdata` no Windows.
- **UX**: 1 bloqueador (formulário abria fora da vista, sem mover o foco) e 6 importantes, corrigidos.
- **CX**: senhas sumindo do terminal, LLM de demonstração parecendo análise, relatório mensal sem avisar dos simulados, porta ocupada; corrigidos.
- **UI-design**: o CSS da tela nova perdia o desempate para o global (selos cinza) e a página rolava a 390 px; corrigidos.
- **Tester**: ampliou o E2E de 11 para 26 testes e achou uma regressão real (a 390 px a página estourava a largura por um rótulo absoluto); corrigida.

## 6. Pendências e riscos conhecidos

- O Portal da demo usa a gravação `portal.mp4` ou, sem ela, o Canteiro; a amostra versionada não entra nele.
- Os pesos dos modelos continuam sendo baixados por `scripts/preparar.py`; "roda sem internet num clone recém-feito" não é afirmado.
- "Hoje" da Gestão é a data local do servidor (limitação S8).
- A fumaça teve uma falha intermitente de tempo na troca de cena do palco (1 em 2 rodadas no checkout; 1 em 1 verde no clone limpo).
- Vídeo publicado pelo grupo no YouTube como não listado: https://youtu.be/jqkfFecsIiw (link no README e no `.txt` da entrega).
- Os PDFs de `docs/pitch/` exportados dos documentos de fase podem ainda trazer o sobrenome antigo do RM 557936: o texto deles é comprimido e não foi verificável com a stdlib nem é editável sem regenerar o PDF. O `.pptx` do pitch foi corrigido.
