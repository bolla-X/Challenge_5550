# ESTADO — MISSÃO 7 (área de detecção por câmera) — fechada em 22/10/2026

Retomar lendo **só** `MISSAO-7.md` (prompt), `MISSAO-7-SPEC.md` (critérios M7.x) + este arquivo. Detalhe técnico
em `CHANGELOG.md`. A MISSÃO 4 está fechada (PR10 #21, tags `missao-4-pr10` e `final-next-2026`).

## Onde estamos

- Tag `pre-missao-7` = `4ca2a7e` (HEAD da `main`), push feito.
- Branch `missao-7` criada da `main`; um único PR no fim.
- Prompt salvo em `MISSAO-7.md`; spec estruturada em `MISSAO-7-SPEC.md`.

## Pronto e verificado (branch `missao-7`, último commit em `origin/missao-7`)

| Critério | Evidência |
|---|---|
| M7.1 dados e API | `tests/test_area_de_deteccao.py` (API, validação, migração, reinício); matriz de permissões com as 3 rotas |
| M7.2 pipeline | mesmo arquivo: recorte, letterbox, pés convexo/côncavo, borda, identidade sem área, lote, análise em voo |
| M7.3 interface | `e2e/test_missao7.py` 2 passed; capturas `bench/runtime/capturas/m7b/` nota 4 nos dois temas |
| M7.4 medição | `bench/results/20261022-124821-area-de-deteccao.json`; tabela no CHANGELOG |
| M7.5 docs | DEMO.md item 6 (ordem da arena), GLOSSARIO, artigo de ajuda; COLA-TIME.md não existe |
| Revisões | auditor (S1, A2, M3–M6, B7, B9–B12 corrigidos), fontes, UX, CX — ver CHANGELOG "MISSÃO 7" |

Desvio registrado da spec: margem de cima do recorte 30 % (5 % nos lados e embaixo). Motivo no CHANGELOG.

## Portão (22/10)

pytest 3288 passed; ruff limpo; build ok; E2E completo 76 passed, 1 falha sensível à carga (crawler
`technical-light`, passou isolado: 26 rotas, 474 elementos, 0 problemas), 2 skips; axe ok. Detalhe no CHANGELOG.

## Entrega

- PR https://github.com/bolla-X/Challenge_5550/pull/22 → `gh pr merge --squash --delete-branch` → `a4df215` na
  `main`; tag `final-next-2026-r3` (push feito).
- Fumaça a partir da `main` (`a4df215`): **6/6** (demo no ar em 103 s), rodada com o tour guiado marcado como
  visto. A 1ª tentativa, com `e2e/fumaca_demo.py` puro, parou no 5º passo: o tour do primeiro acesso cobria o botão
  "Câmeras". O script nunca marcou o tour como visto (o `e2e/conftest.py` marca); passava antes por timing. Não é da
  MISSÃO 7 (`tour.tsx` e a fumaça sem mudança desde `d76941b`).
- `docs/NEXT2026/QA.md` regenerado pelo crawler do portão (80 rotas × papéis, 809 elementos, 3 "sem efeito" na
  rodada com carga — os três passaram na reexecução isolada; ver CHANGELOG "Portão da MISSÃO 7").

## Próximo passo exato

Pendência pequena, fora do PR único da missão: `e2e/fumaca_demo.py` marcar o tour como visto antes de entrar (o
mesmo `add_init_script` de `e2e/conftest.py`). Depois disso, só a preparação da arena (DEMO.md, item 6).

## Rollback

- `pre-missao-7` = HEAD da `main` antes da missão. Ou `git revert` do squash do PR.

## Ações negadas pela permissão (não contornadas)

- (nenhuma até agora)

## Herdado (continua valendo)

- Antes da apresentação: `python scripts/preparar.py` (véspera e manhã: `--so-cache`), depois
  `python run.py --demo` e o roteiro de `DEMO.md`. Plano B: vídeo da Release `next-2026-demo`.
- Ameaça nº 1: CPU tomada por outros programas (Docker, Salesforce CLI, Teams).
- QA My App nunca rodou: depende de o dono rodar `/qa-my-app:init` e `/qa-my-app:run-all`.
