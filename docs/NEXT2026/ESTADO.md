# ESTADO — MISSÃO 7 (área de detecção por câmera)

Retomar lendo **só** `MISSAO-7.md` (prompt), `MISSAO-7-SPEC.md` (critérios M7.x) + este arquivo. Detalhe técnico
em `CHANGELOG.md`. A MISSÃO 4 está fechada (PR10 #21, tags `missao-4-pr10` e `final-next-2026`).

## Onde estamos

- Tag `pre-missao-7` = `4ca2a7e` (HEAD da `main`), push feito.
- Branch `missao-7` criada da `main`; um único PR no fim.
- Prompt salvo em `MISSAO-7.md`; spec estruturada em `MISSAO-7-SPEC.md`.

## Próximo passo exato

M7.1 (coluna `area_deteccao` + migração + API) → M7.2 (recorte e filtro no worker) → M7.3 (editor e escurecimento)
→ M7.4 (medição) → M7.5 (E2E, crawler, capturas, DEMO.md) → M7.6 (portão, PR, merge, tag `final-next-2026-r3`).

## Rollback

- `pre-missao-7` = HEAD da `main` antes da missão. Ou `git revert` do squash do PR.

## Ações negadas pela permissão (não contornadas)

- (nenhuma até agora)

## Herdado (continua valendo)

- Antes da apresentação: `python scripts/preparar.py` (véspera e manhã: `--so-cache`), depois
  `python run.py --demo` e o roteiro de `DEMO.md`. Plano B: vídeo da Release `next-2026-demo`.
- Ameaça nº 1: CPU tomada por outros programas (Docker, Salesforce CLI, Teams).
- QA My App nunca rodou: depende de o dono rodar `/qa-my-app:init` e `/qa-my-app:run-all`.
