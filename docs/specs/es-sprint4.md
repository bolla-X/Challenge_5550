# Spec — Sprint 4 de Engenharia de Software (FIAP 3ECR) — VisionEPI

Prompt de origem: missão "Sprint 4 de Engenharia de Software (FIAP 3ECR, prof. Hercules Lima Ramos)", recebida em
23/10/2026. Esta spec só estrutura o prompt; o conteúdo é o dele. Prazo da entrega: **23/10/2026**.
Estado e decisões tomadas durante a execução: [ESTADO-es-sprint4.md](ESTADO-es-sprint4.md).

## Objetivo

Entregar a solução completa de gestão de EPIs e segurança industrial para a Metaindústria, demonstrando a evolução
nas 4 sprints, de forma que o avaliador consiga **instalar, rodar e navegar seguindo só o README**.

Critérios de avaliação do enunciado: 40 pts app funcionando (fluxos principais, aderência ao problema); 30 pts
documentação (README, arquitetura, Scrum); 30 pts vídeo + evolução. Rastreabilidade de requisitos e consistência
entre as sprints contam como diferencial.

Integrantes: Pedro Gonçalves (RM 557936), Lucas Baraldi (RM 555407), Lucas Zolla (RM 557952),
Vitor Pantarotto (RM 554961).

Regra de evidência: nenhuma afirmação sem medição; "compilou/buildou" não é "funciona"; todo item do relatório final
traz o comando executado e o trecho da saída; limitação de plataforma cita a página da doc oficial; nada de fatos
inventados (datas, falas, métricas, participantes); artefatos Scrum das Sprints 1–3 saem dos docs existentes e do
`git log`, e o que for reconstruído leva a marcação "reconstruído a partir do histórico do git".

## Critérios de aceite

### G — Git

- **G.1** `git fetch --all`; base = `origin/main` (final do FIAP NEXT); `git merge-base --is-ancestor
  origin/feat/completo-com-rebrand origin/main` executado e o resultado registrado. Rebrand fora da main **não** é
  mesclado.
- **G.2** Branch de trabalho `es-sprint4-entrega` criada a partir da main.
- **G.3** Toda mensagem de commit e o título do squash levam `[skip ci]`. Nenhum workflow criado ou alterado.
- **G.4** Mudanças só aditivas; o fluxo de detecção em tempo real da final do NEXT (câmera → YOLO → alerta) continua
  funcionando; regressão desse fluxo rodada **antes** do merge.
- **G.5** Um único PR consolidado, merge squash feito pela sessão com `gh pr merge --squash --delete-branch`.

### F0 — Inventário (somente leitura)

- **F0.1** Stack real mapeada (Flask, React+Vite em `frontend/` servido de `app/static/dist`, YOLO, Gemini, demais).
- **F0.2** Telas existentes, banco e docs das Sprints 1–3 mapeados.
- **F0.3** Links existentes no repo procurados (protótipo/Figma, Trello, vídeos).
- **F0.4** `git log` com datas lido para a linha do tempo por sprint.
- **F0.5** `.agents/skills/` (apple-design, design-taste-frontend) lidos antes de qualquer mudança visual.

### F1 — Aplicação

- **F1.1** Modo demonstração reprodutível: roda **sem câmera IP e sem `GEMINI_API_KEY`**.
- **F1.2** Fonte de vídeo: amostra versionada no repo (curta, leve), com webcam opcional.
- **F1.3** Sem a chave, o LLM usa um fallback determinístico, sinalizado na UI como "modo demonstração"; com a
  chave, comportamento real. (Se já existir, só documentar.)
- **F1.4** Seed idempotente com dados simulados da Metaindústria: colaboradores, catálogo de EPIs (com CA e
  validade), entregas de EPI por colaborador, ocorrências de segurança, alertas e histórico. Usa o banco existente.
- **F1.5** O seed roda automaticamente no primeiro start ou por um comando único documentado.
- **F1.6** Fluxos principais existem e funcionam: dashboard, monitoramento em tempo real, alertas, ocorrências,
  colaboradores com histórico de EPIs, relatório/exportação. Só o que faltar é criado, no design system atual, com
  tema claro e escuro.
- **F1.7** Limpeza: lint em back e front, remoção de código morto, `.env.example`.
- **F1.8** Varredura de segredos: nenhuma chave commitada; se houver, removida do código e registrada.
- **F1.9** pytest no backend, verde.
- **F1.10** Playwright E2E cobrindo cada fluxo principal, verde antes de seguir.

### F2 — Teste "avaliador"

- **F2.1** Clone limpo em diretório temporário seguindo **literalmente só o README**: venv novo, `npm ci`, build,
  start.
- **F2.2** Playwright rodado contra essa instância.
- **F2.3** Qualquer passo que falhe → corrigir README ou código e repetir do zero até passar de ponta a ponta.
- **F2.4** Tempo total da instalação limpa registrado.
- **F2.5** README com comandos para Windows (PowerShell) e macOS/Linux; o que não foi executado em uma plataforma
  marcado como "não testado em …".

### F3 — Documentação

- **F3.1** `README.md` (âncora): problema da Metaindústria, proposta, funcionalidades, links (protótipo, Trello,
  vídeo https://youtu.be/jqkfFecsIiw), instalação, uso, modo demonstração, resumo das entregas por sprint, equipe com
  RMs, estrutura do repo, screenshots geradas com Playwright em `docs/img/`.
- **F3.2** `docs/arquitetura.md`: visão geral, Mermaid de componentes e de fluxo de dados, stack com justificativa,
  decisões técnicas por sprint, limitações conhecidas; ADRs curtos em `docs/adr/`.
- **F3.3** `docs/requisitos.md`: RF e RNF + matriz de rastreabilidade RF → card Trello → arquivo de código → teste →
  sprint.
- **F3.4** `docs/scrum/`: product backlog; sprint backlog das sprints 1 a 4; reviews e retros; Definition of Done;
  `ata-review-final-sprint4.md` com incremento, critérios atendidos e evidências (testes, prints, commits).
- **F3.5** `docs/manual-de-uso.md`: passo a passo com prints.
- **F3.6** `docs/evolucao-sprints.md`: do protótipo ao produto, com evidências (commits, prints, métricas medidas).

### F4 — Trello

- **F4.1** Ordem de acesso: (a) MCP do Trello; (b) REST com `TRELLO_API_KEY` + `TRELLO_TOKEN`; (c) nenhum →
  `docs/scrum/trello-board.md` com listas e cards prontos e registro de que o board não foi atualizado. Nunca
  digitar senha nem criar conta.
- **F4.2** Board: atualizar o do link existente no repo; senão criar "VisionEPI — Challenge 3ECR".
- **F4.3** Listas: Product Backlog, Sprint 1, Sprint 2, Sprint 3, Sprint 4, Concluído, Reviews/Atas.
- **F4.4** Um card por requisito, labels por sprint, checklists de DoD; Sprint 4 inteira em Concluído.
- **F4.5** Card "Ata da Review Final — Sprint 4" com o conteúdo da ata.
- **F4.6** Board público (autorizado) e link no README.

### F5 — Vídeo sem narração

- **F5.1** 4:00 a 4:45, 1920x1080, MP4 H.264, sem áudio e sem voz sintética; conteúdo só por cartelas e legendas.
- **F5.2** `docs/pitch/storyboard.md` com cenas, tempo de cada uma e texto de cada legenda, na ordem: abertura (nome,
  3ECR, 4 integrantes com RM); problema; solução e arquitetura em uma imagem; demonstração dos fluxos principais;
  impacto esperado; evolução das 4 sprints; encerramento.
- **F5.3** Cartelas (abertura, problema, solução, impacto, evolução, encerramento) são páginas HTML no visual do
  VisionEPI (tema claro), gravadas com Playwright (`recordVideo`).
- **F5.4** Demo gravada com Playwright em modo demonstração, tema claro, seguindo o storyboard; barra de legenda
  injetada no DOM, fixa embaixo, texto curto e legível; ritmo humano (pausas para leitura, cursor visível).
- **F5.5** Montagem com ffmpeg; ffprobe valida duração ≤ 5:00, resolução e codec.
- **F5.6** 6 frames-chave extraídos e conferidos (legendas legíveis, sem cobrir nada importante); se cobrirem,
  regravar a cena.
- **F5.7** Vídeo **não** commitado; no repo só o storyboard e os scripts em `scripts/video/`.

### F6 — Entregável zipado (`~/Downloads/ES_Sprint4_VisionEPI/`)

- **F6.1** `ES_Sprint4_3ECR.txt` UTF-8: integrantes e RMs; repositório https://github.com/bolla-X/Challenge_5550;
  link do Trello; `Vídeo: https://youtu.be/jqkfFecsIiw`; conferido não vazio e legível.
- **F6.2** `VisionEPI_pitch_demo.mp4`.
- **F6.3** `ES_Sprint4_VisionEPI.zip` com o .txt, o MP4, `storyboard.md`, `README.md` e `docs/` inteiros; validado
  com `unzip -t`, conteúdo listado e tamanho registrado.

### FC — Fechamento

- **FC.1** Merge squash do PR único.
- **FC.2** Depois do merge, Fase 2 repetida (clone limpo da main + Playwright); só então a entrega é declarada pronta.
- **FC.3** Relatório final no chat: o que foi feito com evidência; cobertura dos critérios 40/30/30; caminho do .zip;
  pendências humanas (subir o MP4 no YouTube como não listado e colar o link no .txt; e o board, se o plano C do
  Trello tiver sido acionado).

## Fora do escopo

- Mesclar `feat/completo-com-rebrand` (ou qualquer branch fora da main) na entrega.
- Criar ou alterar GitHub Actions / workflows.
- Qualquer mudança não aditiva no fluxo câmera → YOLO → alerta.
- Commitar o vídeo.
- Narração ou voz sintética no vídeo.
- Digitar senha ou criar conta (Trello ou qualquer serviço).
- Pedir teste manual ou aprovação a alguém.
- Qualquer coisa fora dos itens listados acima.

## Ramos pré-decididos e rollback (copiados do prompt)

- Rebrand não está na main → não mesclar, só registrar no relatório.
- Modo demo já existe → só documentar o que já existe (e completar o que faltar do F1.1–F1.3).
- O app já tem banco → usar o existente; não tem → SQLite.
- Trello: MCP → REST → plano C (`docs/scrum/trello-board.md`).
- Board: link existente no repo → atualizar; não existe → criar "VisionEPI — Challenge 3ECR".
- ffmpeg ausente → instalar.
- Frame-chave com legenda ruim → regravar a cena.
- Clone limpo falhou → corrigir README ou código e repetir do zero.
- Regressão do fluxo de tempo real falhou e não deu para corrigir → reverter o commit culpado e seguir sem aquela
  feature. **Nunca** fazer merge com a regressão vermelha.
- O que não for possível executar em Windows/macOS/Linux → marcar "não testado em …".
- Plano de branches, PRs e tags do próprio prompt vence regras genéricas: uma branch, um PR, squash.
