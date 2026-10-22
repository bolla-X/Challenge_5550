# ESTADO — MISSÃO 7 (área de detecção por câmera)

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

## Próximo passo exato

Portão completo (pytest, ruff, build/typecheck, E2E completo + crawler + axe) → PR único → `gh pr merge --squash
--delete-branch` → tag `final-next-2026-r3` → fumaça a partir da `main`.

## Rollback

- `pre-missao-7` = HEAD da `main` antes da missão. Ou `git revert` do squash do PR.

## Ações negadas pela permissão (não contornadas)

- (nenhuma até agora)

## Herdado (continua valendo)

- Antes da apresentação: `python scripts/preparar.py` (véspera e manhã: `--so-cache`), depois
  `python run.py --demo` e o roteiro de `DEMO.md`. Plano B: vídeo da Release `next-2026-demo`.
- Ameaça nº 1: CPU tomada por outros programas (Docker, Salesforce CLI, Teams).
- QA My App nunca rodou: depende de o dono rodar `/qa-my-app:init` e `/qa-my-app:run-all`.
