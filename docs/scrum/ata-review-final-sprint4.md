# Ata da Review Final, Sprint 4

Data da entrega: 23/10/2026. Disciplina: Engenharia de Software, FIAP 3ECR. Repositório: https://github.com/bolla-X/Challenge_5550.
Board: https://trello.com/b/zVZW2n1p/visionepi-challenge-3ecr (card "Ata da Review Final — Sprint 4", lista Reviews/Atas).

As células `<!-- EVIDENCIA: ... -->` dependem do fim da sprint (números, hashes, prints, saídas de comando) e são preenchidas pela sessão principal.
Esta ata não registra falas nem presenças que não tenham sido informadas.

## 1. Participantes

Equipe (conforme informado pelo grupo): Pedro Gonçalves (RM 557936), Lucas Baraldi (RM 555407), Lucas Zolla (RM 557952), Vitor Pantarotto (RM 554961).

Presenças e formato da review: <!-- EVIDENCIA: quem participou da review e como foi conduzida; sem registro até a redação -->

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
| Fallback determinístico do LLM, rotulado "modo demonstração" | RF40 | `app/llm/__init__.py`, ADR 0009 |
| Amostra de vídeo versionada (CC BY-SA 4.0) | RF39 | `amostras/`, ADR 0010 |
| Documentação: arquitetura, 10 ADRs, requisitos com matriz, Scrum, manual de uso, evolução | F3.2 a F3.6 | `docs/` |
| Trello, vídeo sem narração e pacote zipado | F4 a F6 | ver seção 3 |

Estado de RF39 e RF41 a RF47 na redação: código, telas e testes existem no disco (`tests/test_gestao_epi.py`, `tests/test_gestao_seed.py`, `e2e/test_es_sprint4.py`); a execução
verde ainda não foi confirmada por quem escreveu esta ata. <!-- EVIDENCIA: estado final de cada um depois dos testes (tests/test_gestao_epi.py, tests/test_gestao_seed.py, e2e/test_es_sprint4.py) -->

PR único e commit do squash: <!-- EVIDENCIA: número do PR, hash do squash e título com [skip ci] -->

## 3. Critérios atendidos

Tabela por critério de `docs/specs/es-sprint4.md`. "Status" aceita Atendido, Parcial ou Não atendido, sempre com a evidência ao lado.

### G: Git

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| G.1 | `fetch --all`, base `origin/main`, `merge-base --is-ancestor` registrado, rebrand não mesclado | Atendido | `git merge-base --is-ancestor origin/feat/completo-com-rebrand origin/main` saiu com **código 1**: o rebrand não está na `main` e não foi mesclado (`docs/specs/ESTADO-es-sprint4.md`) |
| G.2 | Branch `es-sprint4-entrega` a partir da main | Atendido | criada de `main` = `origin/main` = `a4df215` (mesmo arquivo) |
| G.3 | `[skip ci]` em todo commit e no título do squash; nenhum workflow criado ou alterado | <!-- EVIDENCIA: git log da branch mostrando [skip ci]; git diff --stat sem .github/ --> | o inventário de 23/10 registrou que não há `.github/` no repositório |
| G.4 | Mudanças só aditivas; regressão do fluxo câmera, YOLO e alerta rodada antes do merge | <!-- EVIDENCIA: comando da regressão e saída --> | |
| G.5 | Um único PR, squash com `gh pr merge --squash --delete-branch` | <!-- EVIDENCIA: link do PR e saída do merge --> | |

### F0: Inventário

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| F0.1 | Stack real mapeada | Atendido | tabela "Fase 0" em `docs/specs/ESTADO-es-sprint4.md` (Flask, SQLAlchemy, Alembic, Socket.IO, YOLOv8, OpenVINO e ONNX, MediaPipe, Gemini, React 18, Vite, Zustand) |
| F0.2 | Telas, banco e docs das Sprints 1 a 3 mapeados | Atendido | mesmo arquivo: 25 rotas de tela cheia, SQLite e PostgreSQL, 19 migrações antes desta entrega, 18 tabelas antes da Gestão |
| F0.3 | Links existentes procurados (protótipo, Trello, vídeo) | Atendido | nenhum link de Trello, Figma ou vídeo no repositório (`rg trello.com\|figma.com\|youtu`); board novo criado |
| F0.4 | `git log` com datas lido | Atendido | `docs/specs/gitlog-main.txt`; 1º commit em 19/07/2026 |
| F0.5 | `.agents/skills/` lidos antes de mudança visual | <!-- EVIDENCIA: registro de leitura de apple-design e design-taste-frontend --> | |

### F1: Aplicação

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| F1.1 | Demo reprodutível sem câmera IP e sem `GEMINI_API_KEY` | <!-- EVIDENCIA: comando e saída da subida sem a chave --> | |
| F1.2 | Amostra de vídeo versionada, leve, webcam opcional | <!-- EVIDENCIA: tamanho do arquivo e prova de que a demo toca a amostra num clone sem fetch_fixtures --> | `amostras/canteiro_amostra.mp4` existe e `app/demo.py` chama `fonte_da_gravacao` (conferido na redação); não há teste dedicado da amostra |
| F1.3 | LLM com fallback determinístico sinalizado na UI; com chave, real | <!-- EVIDENCIA: pytest tests/test_llm_demo_fallback.py e print 13-status-llm-demo.png --> | 4 testes no arquivo |
| F1.4 | Seed idempotente com dados simulados da Metaindústria | <!-- EVIDENCIA: pytest tests/test_gestao_seed.py (duas execuções, contagens iguais) --> | |
| F1.5 | Seed no primeiro start ou por comando único | <!-- EVIDENCIA: saída de flask --app wsgi gestao semear e da demo --> | |
| F1.6 | Fluxos principais existem e funcionam, tema claro e escuro | <!-- EVIDENCIA: lista dos fluxos e do E2E que os cobre --> | |
| F1.7 | Lint no back e no front, código morto removido, `.env.example` | <!-- EVIDENCIA: ruff check . e npm --prefix frontend run build --> | |
| F1.8 | Varredura de segredos | <!-- EVIDENCIA: comando da varredura e resultado --> | |
| F1.9 | `pytest` verde | <!-- EVIDENCIA: contagem de testes aprovados e tempo --> | último número registrado antes da entrega: 3.288 aprovados (22/10) |
| F1.10 | Playwright cobrindo cada fluxo principal, verde | <!-- EVIDENCIA: python -m pytest e2e -q, contagem --> | último número registrado antes da entrega: 76 aprovados, 1 falha sensível a carga, 2 ignorados (22/10) |

### F2: Teste "avaliador"

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| F2.1 | Clone limpo seguindo só o README | <!-- EVIDENCIA: diretório, comandos e saídas --> | |
| F2.2 | Playwright contra essa instância | <!-- EVIDENCIA: resultado --> | |
| F2.3 | Falha corrigida e repetida do zero | <!-- EVIDENCIA: rodadas e correções --> | |
| F2.4 | Tempo total da instalação limpa | <!-- EVIDENCIA: tempo em minutos e segundos --> | |
| F2.5 | Comandos para PowerShell e macOS/Linux; "não testado em ..." onde couber | <!-- EVIDENCIA: trecho do README e plataformas testadas --> | |

### F3: Documentação

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| F3.1 | `README.md` âncora | <!-- EVIDENCIA: reescrita da sessão principal --> | |
| F3.2 | `docs/arquitetura.md` e ADRs | Escrito em 23/10 | `docs/arquitetura.md` (2 diagramas de componentes e 2 de sequência), `docs/adr/` (10 ADRs e índice). <!-- EVIDENCIA: conferência final dos links e do Mermaid renderizado --> |
| F3.3 | `docs/requisitos.md` com matriz | Escrito em 23/10 | 53 RF e 14 RNF; caminhos conferidos no disco, inclusive os testes da Gestão, que surgiram durante a redação. <!-- EVIDENCIA: conferência final dos caminhos de teste da Gestão --> |
| F3.4 | `docs/scrum/` completo | Escrito em 23/10 | este diretório. <!-- EVIDENCIA: preenchimento desta ata --> |
| F3.5 | `docs/manual-de-uso.md` com prints | Escrito em 23/10, prints pendentes | <!-- EVIDENCIA: os 14 prints de docs/img/ gerados com Playwright --> |
| F3.6 | `docs/evolucao-sprints.md` | Escrito em 23/10 | métricas com fonte; hashes de `docs/specs/gitlog-main.txt` |

### F4: Trello

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| F4.1 | Ordem de acesso (MCP, REST, plano C) | Atendido | acesso pelo MCP do Trello; board novo e público |
| F4.2 | Board atualizado ou criado "VisionEPI — Challenge 3ECR" | Atendido | https://trello.com/b/zVZW2n1p/visionepi-challenge-3ecr |
| F4.3 | Listas | Atendido | Product Backlog, Sprint 1 a 4, Concluído, Reviews/Atas |
| F4.4 | Um card por requisito, labels por sprint, checklists de DoD, Sprint 4 em Concluído | <!-- EVIDENCIA: contagem de cards criados e print do board --> | títulos `RFnn — nome` conforme `docs/requisitos.md` |
| F4.5 | Card "Ata da Review Final — Sprint 4" | <!-- EVIDENCIA: card criado com o conteúdo desta ata --> | |
| F4.6 | Board público e link no README | <!-- EVIDENCIA: link no README e acesso sem login --> | |

### F5 e F6: Vídeo e pacote

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| F5.1 a F5.7 | Vídeo sem narração de 4:00 a 4:45, storyboard, cartelas, demo gravada, montagem, 6 frames, vídeo fora do repositório | <!-- EVIDENCIA: ffprobe (duração, resolução, codec), 6 frames conferidos, `docs/pitch/storyboard.md` --> | `scripts/video/` existe; o vídeo não é versionado |
| F6.1 | `ES_Sprint4_3ECR.txt` | <!-- EVIDENCIA: conteúdo conferido, link do YouTube pendente --> | |
| F6.2 | `VisionEPI_pitch_demo.mp4` | <!-- EVIDENCIA: tamanho e caminho --> | |
| F6.3 | `.zip` validado | <!-- EVIDENCIA: saída de unzip -t, lista e tamanho --> | |

### FC: Fechamento

| Critério | O que pede | Status | Evidência |
|---|---|---|---|
| FC.1 | Squash do PR único | <!-- EVIDENCIA: hash do squash na main --> | |
| FC.2 | Fase 2 repetida a partir da `main`, só então "pronto" | <!-- EVIDENCIA: clone limpo da main e Playwright --> | |
| FC.3 | Relatório final com cobertura 40/30/30 e pendências humanas | <!-- EVIDENCIA: relatório no chat --> | pendência humana conhecida: subir o MP4 no YouTube como não listado e colar o link no `.txt` |

## 4. Cobertura dos critérios de avaliação do enunciado

| Peso | Critério | Onde está coberto |
|---|---|---|
| 40 pts | Aplicação funcionando: fluxos principais e aderência ao problema | F1 e F2; `docs/manual-de-uso.md`. <!-- EVIDENCIA: resumo dos fluxos testados --> |
| 30 pts | Documentação: README, arquitetura, Scrum | F3 e F4; `docs/arquitetura.md`, `docs/adr/`, `docs/requisitos.md`, `docs/scrum/` |
| 30 pts | Vídeo e evolução | F5, F6 e `docs/evolucao-sprints.md` |
| Diferencial | Rastreabilidade de requisitos e consistência entre as sprints | matriz em `docs/requisitos.md`; `docs/scrum/sprint-1.md` a `sprint-4.md` |

## 5. Evidências

### 5.1 Testes

| Medida | Valor | Comando |
|---|---|---|
| `pytest` completo | <!-- EVIDENCIA: N aprovados, N falhas, tempo --> | `pytest` |
| `ruff` | <!-- EVIDENCIA: saída --> | `ruff check .` |
| Build e tipos do frontend | <!-- EVIDENCIA: saída --> | `npm --prefix frontend run build` |
| E2E | <!-- EVIDENCIA: N aprovados, falhas, ignorados --> | `python -m pytest e2e -q` |
| Testes novos da Gestão e do fallback | <!-- EVIDENCIA: contagem por arquivo --> | `tests/test_gestao_epi.py`, `tests/test_gestao_seed.py`, `tests/test_llm_demo_fallback.py`, `e2e/test_es_sprint4.py` |
| Fumaça do clone limpo | <!-- EVIDENCIA: 6 de 6 verificações, tempo --> | `python e2e/fumaca_demo.py --raiz .` |

### 5.2 Prints (`docs/img/`, gerados com Playwright)

`01-login.png`, `02-inicio-supervisor.png`, `03-grade-cameras.png`, `04-foco-camera.png`, `05-incidentes.png`, `06-gestao-colaboradores.png`,
`07-gestao-historico.png`, `08-gestao-catalogo.png`, `09-gestao-entregas.png`, `10-gestao-ocorrencias.png`, `11-gestao-exportar.png`,
`12-relatorio-mensal.png`, `13-status-llm-demo.png`, `14-tema-escuro.png`. <!-- EVIDENCIA: conferir que os 14 existem e mostram o que o manual descreve -->

### 5.3 Commits

| Marco | Commit | Data |
|---|---|---|
| Base da entrega (MISSÃO 7, PR #22) | `a4df215` | 22/10/2026 |
| Commits da branch `es-sprint4-entrega` | <!-- EVIDENCIA: git log --oneline da branch --> | 23/10/2026 |
| Squash do PR único | <!-- EVIDENCIA: hash --> | <!-- EVIDENCIA: data --> |

Marcos anteriores, com data e hash: [../evolucao-sprints.md](../evolucao-sprints.md).

## 6. Pendências e riscos conhecidos na redação

- RF39: a amostra versionada está ligada em `app/demo.py` (`fonte_da_gravacao`), mas não há teste dedicado nem prova de subida num clone sem as gravações (ADR 0010). O Portal só
  usa a gravação `portal.mp4` ou, sem ela, o Canteiro; a amostra não entra nele.
- `docs/NEXT2026/DEMO.md` diz que o LLM fica "desligado" na demo; desde o ADR 0009 a demo mostra "modo demonstração" (inconsistência de documento antigo).
- Os pesos dos modelos continuam sendo baixados por `scripts/preparar.py`; "roda sem internet num clone recém-feito" não é afirmado.
- Pendências humanas: subir o vídeo no YouTube como não listado e colar o link no `.txt`.
