# Rebranding visual, direção calma

Ramo `rebrand/calma`, nove commits `rebrand(N)`, um por etapa. Esta sessão mexe em apresentação: nenhuma rota, contrato de API, schema ou comportamento de negócio mudou.

## Números medidos (seção 7)

| Item | Comando | Esperado | Medido |
|---|---|---|---|
| 7.1 cor fora do sistema | `grep -rnE '#[0-9a-fA-F]{3,8}\b\|rgba?\([0-9]' frontend/src --include=*.tsx --include=*.ts \| wc -l` | 0 | **0** |
| 7.2 layout fora do CSS | `grep -rn 'style={{' frontend/src --include=*.tsx \| wc -l` | 4 ou menos | **1** (`timeline.tsx`, posição da marca na trilha, comentado) |
| 7.3 contraste WCAG | `python scripts/check_contrast.py` | 0 falhas | **falhas: 0** (46 pares conferidos) |
| 7.4 uppercase | `grep -rn "text-transform:\s*uppercase" frontend/src \| wc -l` | 0 | **0** |
| 7.4 raio numérico | `grep -rnE "border-radius:\s*[0-9]" frontend/src/styles/global.css \| wc -l` | 0 | **0** |
| 7.4 sombra fora dos tokens | `grep -rn "box-shadow" frontend/src/styles/global.css \| grep -v "var(--shadow" \| wc -l` | 0 | **0** |
| 7.4 transition all | `grep -rn "transition:\s*all" frontend/src \| wc -l` | 0 | **0** |
| 7.5 build | `npm --prefix frontend run build` | exit 0 e CSS citando a fonte nova | **exit 0**, `geist-latin-wght-normal` presente em `app/static/dist/assets/*.css`, URL reescrita para `/static/dist/fonts/geist-latin-wght-normal.woff2` |
| 7.6 backend | `python -m pytest -q` | verde | **348 passed** (344 existentes + 4 novos em `tests/test_annotator.py`), 69 s |
| 7.7 telas | seis PNGs, 1440x900 | olhadas | **6 capturadas e olhadas**, uma frase por tela abaixo |
| 7.8 teclado, login | focáveis vs. com anel | iguais | **3 = 3** |
| 7.8 teclado, grade | focáveis vs. com anel | iguais | **10 = 10** |
| 9.x legado | `grep -rn "Autoridade Discreta\|2FD4E6\|Geist-Variable" . --include=*.md --include=*.css --include=*.tsx \| grep -v "PROMPT-REBRAND\|REBRAND-NOTAS"` | 0 | **0** |

Fontes: `Geist-Variable.woff2` (69.652 bytes) + `GeistMono-Variable.woff2` (71.368 bytes) = 141.020 bytes; substituídas por `geist-latin-wght-normal.woff2` (29.400) + `geist-mono-latin-wght-normal.woff2` (23.128) = 52.528 bytes. Redução de 62,8%, medida com `ls -l`.

Contraste, piores pares: claro, `--ok` sobre `--sunken` 4,57:1; escuro, `--text-3` sobre `--sunken` 4,76:1. Limites de controle: 3,15:1 (claro) e 3,89:1 (escuro) sobre o fundo. `--on-accent` sobre `--accent`: 5,69:1 e 7,01:1.

`global.css`: 736 linhas antes, 429 depois. Diff total do ramo: 42 arquivos, +2440 / -2746.

## 7.7, o que apareceu em cada tela

Capturas com Playwright (Chromium 1228) contra o Flask servindo `app/static/dist` em `127.0.0.1:5000`, viewport 1440x900, tema forçado por `localStorage["visionepi-theme"]` antes do primeiro paint. Não há câmera física nesta máquina: `GET /api/cameras`, `GET /api/cameras/<id>/status` e `GET /status` foram interceptados no navegador para devolver três câmeras e dois alertas (um `critical`, um `medium`); o quadro do `video_feed` é um frame sintético anotado pelo `annotator.py` novo. Login, sessão, cookies, CSS, fontes e favicon são reais.

- **login, claro**: cartão branco de 384 px centrado no cinza `#F5F5F7`, símbolo, "VisionEPI" em 23 px, dois campos com fundo rebaixado, botão azul de largura total desabilitado até preencher; o campo E-mail já mostra a borda azul e o anel de foco.
- **login, escuro**: mesmo cartão em `#17181C` sobre `#0C0D0F`, símbolo invertido (quadrado claro), botão azul mais escuro, texto legível.
- **grade, claro**: barra translúcida com logotipo, Buscar, Exportar (desabilitado, sem histórico), tema, som, nome e papel, Sair e Parar em vermelho; título "Câmeras" com "2 de 3 no ar, 2 alertas ativos" ao lado; três cartões com a imagem no topo e nome + estado embaixo; o primeiro tem o anel laranja de 2 px; o terceiro mostra "Monitoramento parado" no lugar da imagem; cartão tracejado "Adicionar câmera".
- **grade, escuro**: mesma composição sobre `#0C0D0F`, anel laranja mais claro (`#FF8A3D`), cartões em `#17181C`.
- **foco com alerta, claro**: sidebar sem borda com "Setores" (o atual com fundo rebaixado, ponto laranja acesso, o offline com ponto apagado), "Perfis" e "Recursos" com estado em texto; título "Prensa hidráulica" com "Setor 3, RTSP rtsp://…" ao lado; sobre o vídeo, três pílulas escuras: "Recebendo 11.8 fps · 960x540", "Conectado" e, à direita, "Capacete ausente, pessoa 2 1:16" com ponto laranja; no vídeo, pessoa sem capacete em laranja 3 px, pessoa conforme em branco, capacete e colete em verde, área de risco com preenchimento a 8%, rótulos sobre pílulas escuras; à direita, abas em pílula e o painel "Alertas ativos" com a linha crítica tingida e a linha média só com o ponto aceso.
- **foco com alerta, escuro**: idem, tingimento da linha crítica em laranja a 14% sobre a superfície escura, pílulas sobre o vídeo iguais (o material sobre vídeo não muda com o tema).

Os únicos erros de rede nas capturas foram `404` em `/overlay`, `/settings` e `/risk-area`: rotas da "câmera padrão", que respondem 404 quando nenhuma câmera está cadastrada no banco (o `bootstrap()` do store já trata esse caso com `Promise.allSettled`). Nenhum erro de JavaScript.

## 7.8, teclado

Script: conta os focáveis visíveis (`a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])`), tira o foco do documento, pressiona Tab uma vez por elemento e lê `outline-style`/`outline-width` do `document.activeElement`. Login: 3 focáveis (E-mail, Senha, Entrar com campos preenchidos), 3 com anel. Grade: 10 focáveis (Buscar, tema, som, Sair, Parar, Visão geral, três cartões, Adicionar câmera), 10 com anel. O Tab que sai do documento para a interface do navegador foca `<body>` e não conta como elemento.

## Testes alterados

Nenhum teste existente mudou. Um arquivo novo, `tests/test_annotator.py`, com quatro testes: pessoa sem EPI fica laranja e EPI presente fica verde; pessoa conforme fica branca a 90%; o retângulo arredondado não pinta o canto; rótulo perto da borda não estoura o frame.

## Bifurcações da seção 6 acionadas

Nenhuma linha da tabela disparou: `@fontsource-variable/*` instalou, nenhum teste quebrou, nenhuma tela quebrou abaixo de 880 px sem tratamento (sidebar some, grade e foco empilham, sem menu hambúrguer).

Bifurcações não previstas, resolvidas pela opção mais conservadora:

- **Raio de 9 px nos itens da sidebar e 20 px no cartão de login** (etapas 5 e 7) contra "raio só pelos tokens" (etapa 2) e a checagem 7.4 que proíbe raio numérico. Ficaram nos tokens: 10 px (`--r-control`) e 16 px (`--r-card`).
- **Tokens novos**: `--overlay` e `--on-overlay` (material translúcido sobre vídeo, sempre escuro, mesma cor do fundo de rótulo do annotator) e `--scrim` (fundo de diálogo). São papéis que não existiam na seção 3; ficaram documentados em `tokens.css`.
- **Anel de foco de campo** (3 px a 22%) é feito com `outline`, não com `box-shadow`, para manter a checagem 7.4 em zero sem token de sombra novo.
- **Botão Exportar na barra**: chama a mesma função de CSV do histórico de alertas que a aba Exportação já usava (`exportAlertsCsv`, agora exportada de `export.tsx`); só aparece para quem tem visão geral (Supervisor) e fica desabilitado sem histórico carregado. A aba Exportação continua com os dois CSVs.
- **`<VideoCard/>` em `video.tsx`** não era montado por tela nenhuma desde a integração multi-câmera (só aparecia em comentários). Saiu como código morto; o `RiskAreaEditorPanel` do mesmo arquivo ficou. O canvas do editor de zona já não estava em tela alguma antes desta sessão, e continua assim.
- **Polling do vídeo principal na tela de foco**: passou do próprio `setInterval` de 2 s para o hook `useCameraEstado` compartilhado (3 s), o mesmo que a grade e o diagnóstico já usavam, para não abrir dois pollings contra a mesma rota. Só o intervalo de atualização visual mudou.
- **Tempo decorrido na pílula de alerta**: o backend grava UTC e o SQLite devolve ISO sem fuso; o relógio novo acrescenta `Z` antes do `Date()` (mesmo tratamento que `export.tsx` já fazia), senão nascia deslocado pelo fuso local.
- **Chips de recurso por câmera no cartão da grade** saíram junto com fps e chip sobre a imagem, como a etapa 7 pede; eram só exibição.
- **Ícones preenchidos** dos recursos (capacete, colete, luvas) saíram; a sidebar mostra nome, descrição curta e estado em texto, com o ponto de 7 px acendendo em `--ok` só quando o recurso está aparecendo no frame agora.

## Limitações declaradas, com a fonte

- **Espessura fracionária no OpenCV**: `cv2.line`, `cv2.rectangle`, `cv2.ellipse` e `cv2.polylines` recebem `thickness` inteiro (https://docs.opencv.org/4.x/d6/d6e/group__imgproc__draw.html). Os 1,8 px do EPI presente e 1,6 px da área de risco viraram 2 px; os 1,5 px do esqueleto de pose viraram pontos de raio 2 px a 50%. A opacidade (90%, 75%, 50%, 8%) é feita com `cv2.addWeighted` sobre uma cópia por camada.
- **Esqueleto de pose**: o annotator desenhava só os pontos (landmarks), não as conexões; continua desenhando pontos, agora brancos a 50%. Ligar os pontos exigiria a tabela de conexões do MediaPipe e é comportamento novo, fora desta sessão.
- **Latência na pílula sobre o vídeo**: o diagnóstico da câmera (`CameraDiagnostico`) expõe fps e resolução, não latência; a pílula mostra os dois que existem mais o estado do socket.

## Correções pós-rebrand (commit `rebrand(10)`)

**1. Fuso.** `frontend/src/utils/datas.ts` exporta `paraDate(valor)`, que aplica `/Z$|[+-]\d\d:\d\d$/` e acrescenta `Z` quando falta (sem valor devolve agora, como todos os pontos faziam). Usado nos sete pontos: `export.tsx` (formatDateTimeLocal), `camera-focus.tsx` (decorrido), `alerts.tsx` (formatTime e formatDateTime), `timeline.tsx` (formatTime e a posição das marcas), `risk-score.tsx` (formatBucketHour). As duas cópias do regex saíram; ele existe só em `datas.ts` (`grep` = 1 ocorrência). `formatTime` da linha do tempo continua aceitando número, porque o eixo da trilha passa instantes já calculados.

Teste: não há runner de front (`package.json` sem script `test`, sem vitest ou jest instalados), e adicionar um só para isto seria uma dependência nova para uma função de duas linhas. Foi pelo caminho de `tests/`: `tests/test_serializer_datas_naive.py` cria um alerta pelo `AlertRepository` no SQLite do fixture `app`, relê do banco e afirma que `created_at`, `first_seen_at` e `last_seen_at` do `to_dict()` saem sem `Z` nem offset, e que reler o valor como UTC cai em "agora" (menos de um minuto). É a premissa de que `paraDate` depende, conferida do lado que produz a string. 349 testes passam (348 + 1).

**2. Contraste na linha tingida.** Em `.alert-row.critical` e `.alert-row.high`, `.alert-row-meta` e `.alert-row-time` passam de `--text-3` para `--text-2`. Medido antes: 4,23:1 no escuro (`--text-3` sobre `--tint-danger` composta em `--surface`); depois: 5,50:1.

**3. Portão.** `scripts/check_contrast.py` agora compõe cada fundo rgba (`a*fg + (1-a)*bg` por canal) e confere o texto que de fato assenta nele: `--tint-danger` sobre canvas e surface com `--text`, `--text-2` e `--danger`; `--overlay` sobre canvas, surface, preto e branco puros com `--on-overlay`; `--scrim` sobre canvas e surface com `--text`. 24 pares compostos, 70 no total. A primeira rodada achou uma falha real: claro, `--danger` sobre `--tint-danger`+canvas, 4,41:1 (caso da barra de mensagem de erro e dos chips do kiosk, que ficam fora de cartão). Corrigido no token, não no script: `--danger` claro de `#AF4A06` para `#AF4606` (só o canal verde, 74 para 70), tinta acompanhando para `rgba(175,70,6,.10)`. Novo: 4,54:1 nesse par, 5,21:1 sobre canvas, 4,89:1 sobre tint+surface. Escuro inalterado. O script foi reescrito em estilo normal (uma sentença por linha, funções nomeadas), com as mesmas razões de saída conferidas por diff antes e depois; ruff limpo.

**Números rodados de novo após as correções**

| Item | Medido |
|---|---|
| 7.1 cor fora do sistema | **0** |
| 7.2 `style={{}}` | **1** (trilha do tempo, comentado) |
| 7.3 contraste | **falhas: 0** em 70 pares (46 sólidos + 24 compostos) |
| 7.4 uppercase, raio numérico, sombra fora dos tokens, `transition: all` | **0, 0, 0, 0** |
| 7.5 build | **exit 0**, `geist-latin-wght-normal` no CSS gerado, `#AF4606` presente no dist |
| 7.6 pytest | **349 passed** |

## Fora do escopo, deixado como estava

`command-palette.tsx` não precisou mudar (só rótulos, sem estilo). O `cmdk` não anima por padrão e o CSS não adiciona animação. `@number-flow` ficou só no índice de risco; `motion` ficou, com a curva trocada para `cubic-bezier(.23,1,.32,1)`.
