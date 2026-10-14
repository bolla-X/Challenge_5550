# DESIGN — sistema visual do VisionEPI

Fonte da verdade: `frontend/src/styles/tokens.css`. **Nenhuma cor, raio,
sombra ou duração existe fora de lá.** Este documento explica as decisões; o
arquivo tem os valores.

Direção: limpo, premium, inspirado nas interfaces da Apple
(`.agents/skills/apple-design`), sem cara de template
(`.agents/skills/design-taste-frontend`). Tema **claro** é o padrão da demo
(projetor); o escuro tem os próprios valores, não uma inversão.

## Cor: só para estado

| papel | token | onde |
|---|---|---|
| superfícies | `--canvas`, `--surface`, `--sunken` | fundo, cartão, campo/afundado |
| linhas | `--hairline` (decorativa), `--control-line` (borda de controle, 3:1) | separadores, campos |
| texto | `--text`, `--text-2`, `--text-3` | título, apoio, terciário (todos ≥ 4,5:1 nos dois temas) |
| interação | `--accent`, `--on-accent` | botão primário, link, foco, dado "proposta" |
| **conforme** | `--ok`, `--tint-ok` | ponto e rótulo de conforme, missão cumprida |
| **perigo** | `--danger`, `--tint-danger` | EPI ausente, zona, incidente ativo |
| **parada** | `--stop` | botão Parar, possível queda |
| sobre vídeo | `--v-*`, `--overlay`, `--on-overlay` | pílulas e canvas sobre o vídeo — fixos nos dois temas, iguais ao anotador do servidor |

Regras: cor nunca é decoração; todo estado colorido tem também texto ou forma
(ponto + rótulo, anel no avatar, tracejado no descarte). Gráficos: uma série
"proposta" em `--accent` e uma "real" em `--text-3` (neutra), nunca cores de
estado para série.

## Tipografia

Geist e Geist Mono (SIL OFL 1.1), self-hosted em `frontend/public/fonts`
(offline). Escala com tamanho, entrelinha e tracking juntos — maior = mais
apertado:

| token | uso |
|---|---|
| `--t-hero` 64 | número/título de palco, retrospectiva |
| `--t-display` 40 | números-chave (simulador, liga) |
| `--t-title-1` 28 | título de tela |
| `--t-title-2` 22 | título de painel/detalhe |
| `--t-title-3` 17 | título de cartão |
| `--t-body` 15 / `--t-callout` 14 / `--t-footnote` 13 / `--t-caption` 12 | texto |

Números grandes usam a **sans com algarismos tabulares**
(`font-variant-numeric: tabular-nums`); a mono fica para dado técnico curto
(hash, fps, horário de linha do tempo).

Texto visível: sem travessão como separador (frase reescrita, vírgula ou dois
pontos); ponto médio no máximo um por linha.

## Espaço, forma, sombra

- Grade de 4/8: `--s1` 4 · `--s2` 8 · `--s3` 12 · `--s4` 16 · `--s5` 24 · `--s6` 32 · `--s7` 48.
- Raios: `--r-control` 10 (campo, botão), `--r-card` 16 (cartão), `--r-sheet` 28
  (story), `--r-chip` pílula. Nada fora dessa escala.
- Sombras: `--shadow-1` (apoio), `--shadow-2` (flutuante/modal), tingidas com a
  matiz do fundo.

## Movimento

| token | valor | uso |
|---|---|---|
| `--d-instant` | 100 ms | toque |
| `--d-press` | 120 ms | `:active` (escala 0,97) |
| `--d-state` | 160 ms | troca de estado, hover |
| `--d-panel` | 260 ms | painel, barra de progresso |
| `--d-entrance` | 360 ms | entrada de cena/tela |
| `--ease-out` / `--ease-spring` | `cubic-bezier(.23,1,.32,1)` | quase tudo |
| `--ease-in-out` | `cubic-bezier(.65,0,.35,1)` | ida e volta simétrica |

- Troca de tela: **View Transitions** (`document.startViewTransition` nas telas
  internas e `@view-transition { navigation: auto }` entre rotas), com fallback
  sem animação quando o navegador não tem a API (MDN:
  https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API/Using).
- Números que mudam ao vivo animam (NumberFlow) e não "saltam".
- Entrada de alerta: opacidade + escala 0,98→1 em `--d-state`, uma vez; nada
  pulsa.
- `prefers-reduced-motion: reduce`: sem deslocamento nem escala; só troca de
  opacidade curta. O confete da Liga e o som não tocam; a interpolação do 3D
  vira salto.

## Componentes únicos

| componente | onde mora | regra |
|---|---|---|
| Botão | `button`, `.primary`, `.ghost`, `.small`, `a.button` (global.css) | um primário por região; rótulo de 1 a 3 palavras, nunca quebra |
| Cartão | `.card`, `.card-head`, `.card-body` | só quando a elevação diz hierarquia |
| Badge de estado | `.chip` + `.ok` / `.miss` | texto sempre junto da cor |
| Tabela | `.tabela` | linha divisória só embaixo; número alinhado à direita, tabular |
| Modal | `.modal-scrim` + `.modal` | Esc fecha; foco dentro; scrim escurece |
| Toast | `.message-bar` | transitório; erro com ação |
| Skeleton | `PanelSkeleton` / `.skeleton-block` | mesmo formato do conteúdo final |
| Estado vazio | `EmptyState` (`components/common.tsx`) | ilustração original (`components/ilustracoes.tsx`) + uma frase + uma ação |
| Ícone | `components/icones.tsx` | Phosphor, peso regular, 18 px; nunca SVG à mão |

## Estados

Toda tela tem os quatro: **carregando** (skeleton no formato final), **vazio**
(ilustração + como popular), **erro** (o que aconteceu + "Tentar de novo") e
**pronto**. Sem "em construção", "TODO", lorem ou placeholder visível — o
teste `e2e/test_estados.py` procura essas palavras em todas as rotas.

## Acessibilidade

- axe-core em todas as rotas, nos dois temas (`e2e/test_acessibilidade.py`):
  zero violação séria ou crítica.
- Contraste AA nos dois temas (`scripts/check_contrast.py` para os pares de
  tokens).
- Teclado: tudo alcançável por Tab com foco visível (`--accent`, 2 px);
  atalhos: **X** (Raio-X), **→ / ← / Espaço** (palco e stories), **Esc** (modal),
  **Ctrl K** (busca).
